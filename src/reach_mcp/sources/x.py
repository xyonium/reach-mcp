"""X / Twitter via cookie auth (AUTH_TOKEN + CT0). Off by default."""
from __future__ import annotations

import os

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class X(Source):
    name = "x"
    description = "X / Twitter search via account cookies (AUTH_TOKEN + CT0)."
    host = "api.x.com"
    needs_auth = True
    required_env = ("AUTH_TOKEN", "CT0")

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        if not self.available():
            return []
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
