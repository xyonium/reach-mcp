"""V2EX topics via the public API (free, no key)."""
from __future__ import annotations

from datetime import datetime, timezone

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class V2EX(Source):
    name = "v2ex"
    description = "V2EX forum topics via the public API (free)."
    host = "www.v2ex.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        data = await client.get_json(
            "https://www.v2ex.com/api/topics/search.json",
            params={"q": query, "size": str(min(limit, 30))},
        )
        rows: list[Row] = []
        for t in data if isinstance(data, list) else []:
            ts = t.get("created")
            date = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None
            member = t.get("member") or {}
            rows.append(Row(
                source="v2ex", id=str(t.get("id", "")),
                title=t.get("title") or "", url=t.get("url") or "",
                author=member.get("username"), date=date,
                engagement={"replies": t.get("replies") or 0},
                text=(t.get("content") or "")[:500],
            ))
        return rows
