"""V2EX search via the community-run sov2ex API (free, no key).

The old /api/topics/latest.json approach fetched the ~10 newest topics and
client-side text-matched the query — a "search" that only hits an ancient
topic if it happens to be in the current hot window. sov2ex
(https://www.sov2ex.com/api/search) is a proper Elasticsearch over all V2EX
topics+replies, with highlighted content; live-verified 2026-09 (~13KB for
"远程"). Kept the latest.json path as a no-query fallback.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from reach_mcp.sources.base import Row, Source, get_client, register_source, snip

_TAG_RE = re.compile(r"</?em>")
_SO_URL = "https://www.sov2ex.com/api/search"


@register_source
class V2ex(Source):
    name = "v2ex"
    description = "V2EX topics and replies via the sov2ex search index (free, no key)."
    host = "www.sov2ex.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        data = await get_client().get_json(
            _SO_URL, params={"q": query, "size": str(min(limit, 20)), "sort": "created"}
        )
        rows: list[Row] = []
        for hit in data.get("hits", []):
            src = hit.get("_source") or {}
            title = src.get("title") or ""
            if not title:
                continue
            hl = (hit.get("highlight") or {}).get("content") or []
            text = _TAG_RE.sub("", hl[0]) if hl else (src.get("content") or "")
            rows.append(
                Row(
                    source="v2ex",
                    id=str(hit.get("_id") or src.get("id") or ""),
                    title=title,
                    url=src.get("url") or f"https://www.v2ex.com/t/{src.get('id')}",
                    author=src.get("member")
                    if isinstance(src.get("member"), str)
                    else (src.get("member") or {}).get("username"),
                    date=_iso(src.get("created")),
                    engagement={"replies": src.get("replies") or 0},
                    text=snip(text),
                )
            )
        return rows

    async def fetch_trending(self, limit: int) -> list[Row]:
        data = await get_client().get_json("https://www.v2ex.com/api/topics/hot.json")
        rows: list[Row] = []
        for t in data if isinstance(data, list) else []:
            rows.append(
                Row(
                    source="v2ex",
                    id=str(t.get("id", "")),
                    title=t.get("title") or "",
                    url=t.get("url") or "",
                    author=(t.get("member") or {}).get("username"),
                    date=_iso(t.get("created")),
                    engagement={"replies": t.get("replies") or 0},
                    text=snip(t.get("content") or ""),
                )
            )
        return rows


def _iso(ts) -> str | None:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None
