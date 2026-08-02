"""X / Twitter via bird (Twitter GraphQL) or cookie fallback. Off by default.

Preferred backend mirrors last30days' bird_x: a vendored @steipete/bird
search wrapper run via Node.js, authenticated with AUTH_TOKEN+CT0 cookies.
Falls back to the legacy api.x.com search/adaptive.json cookie endpoint when
node/bird-search.mjs is unavailable.

X search is literal keyword AND matching — all words in the query must appear
in results, so long/multi-word queries may return few or no results.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path

from reach_mcp.sources.base import Row, Source, get_client, register_source

# Path to last30days' vendored bird-search.mjs (shared with the last30days
# deployment). reach-mcp does NOT vendor it; it reuses the one last30days ships.
_BIRD_SEARCH_MJS = (
    Path("/config/last30days/cache/last30days-pp-mcp/v3.18.0/lib/vendor")
    / "bird-search" / "bird-search.mjs"
)


def _bird_available() -> bool:
    return (
        shutil.which("node") is not None
        and _BIRD_SEARCH_MJS.exists()
    )


async def _fetch_via_bird(query: str, limit: int) -> list[Row]:
    """Search via node bird-search.mjs (Twitter GraphQL)."""
    env = os.environ.copy()
    env.setdefault("BIRD_DISABLE_BROWSER_COOKIES", "1")
    # Query gets a since: filter for the recency window (bird supports it)
    try:
        proc = await asyncio.create_subprocess_exec(
            "node", str(_BIRD_SEARCH_MJS), query,
            "--count", str(min(limit, 30)), "--json",
            env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=90)
    except Exception:  # noqa: BLE001
        return []
    try:
        items = json.loads(stdout)
    except json.JSONDecodeError:
        return []  # anti-bot interstitial etc.
    if not isinstance(items, list):
        return []
    rows: list[Row] = []
    for t in items:
        author = (t.get("author") or {}).get("username")
        rows.append(Row(
            source="x", id=str(t.get("id") or ""),
            title=(t.get("text") or "")[:120],
            url=f"https://x.com/{author}/status/{t.get('id')}" if author else "",
            author=author,
            date=t.get("createdAt"),
            engagement={"likes": t.get("likeCount") or 0,
                        "retweets": t.get("retweetCount") or 0,
                        "replies": t.get("replyCount") or 0},
            text=t.get("text") or "",
        ))
    return rows


async def _fetch_via_cookie(query: str, limit: int) -> list[Row]:
    """Fallback: legacy api.x.com search/adaptive.json with cookies."""
    client = get_client()
    headers = {
        "Authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D",
        "Cookie": f"auth_token={os.environ['AUTH_TOKEN']}; ct0={os.environ['CT0']}",
        "x-csrf-token": os.environ["CT0"],
    }
    try:
        data = await client.get_json(
            "https://api.x.com/2/search/adaptive.json",
            params={"q": query, "count": str(min(limit, 50)),
                    "query_source": "typed_query"},
            headers=headers,
        )
    except Exception:  # noqa: BLE001
        return []
    rows: list[Row] = []
    g = data.get("globalObjects", {}) or {}
    tweets = g.get("tweets", {}) or {}
    users = g.get("users", {}) or {}
    for tid, t in tweets.items():
        user = users.get(t.get("user_id_str"), {})
        rows.append(Row(
            source="x", id=tid, title=(t.get("full_text") or "")[:120],
            url=f"https://x.com/{user.get('screen_name','i')}/status/{tid}",
            author=user.get("screen_name"), date=t.get("created_at"),
            engagement={"likes": t.get("favorite_count") or 0,
                        "retweets": t.get("retweet_count") or 0,
                        "replies": t.get("reply_count") or 0},
            text=t.get("full_text") or "",
        ))
    return rows


@register_source
class X(Source):
    name = "x"
    description = "X / Twitter search via bird (GraphQL) or cookie fallback (AUTH_TOKEN + CT0)."
    host = "x.com"
    needs_auth = True
    required_env = ("AUTH_TOKEN", "CT0")

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        if not self.available():
            return []
        if _bird_available():
            rows = await _fetch_via_bird(query, limit)
            if rows:
                return rows
        # Cookie fallback (bird unavailable or empty)
        return await _fetch_via_cookie(query, limit)
