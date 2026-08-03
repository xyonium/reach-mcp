"""V2EX topics via the public API (free, no key).

The old search endpoint (/api/topics/search.json) was removed upstream, so we
use /api/topics/latest.json and filter by the query in title/content. Degraded
but functional.
"""
from __future__ import annotations

from datetime import datetime, timezone

from reach_mcp.sources.base import Row, Source, get_client, register_source, snip


@register_source
class V2EX(Source):
    name = "v2ex"
    description = "V2EX latest topics filtered by query (public API; search endpoint removed upstream)."
    host = "www.v2ex.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        data = await client.get_json(
            "https://www.v2ex.com/api/topics/latest.json",
        )
        ql = query.lower()
        rows: list[Row] = []
        for t in data if isinstance(data, list) else []:
            title = t.get("title") or ""
            content = t.get("content") or ""
            # Filter by query in title or content; keep all if query empty.
            if ql and ql not in title.lower() and ql not in content.lower():
                continue
            ts = t.get("created")
            date = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None
            member = t.get("member") or {}
            rows.append(Row(
                source="v2ex", id=str(t.get("id", "")),
                title=title, url=t.get("url") or "",
                author=member.get("username"), date=date,
                engagement={"replies": t.get("replies") or 0},
                text=snip(content),
            ))
            if len(rows) >= limit:
                break
        return rows
