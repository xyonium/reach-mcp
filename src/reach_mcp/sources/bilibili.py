"""B站 (Bilibili) video search via the public search API (free, no login)."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class Bilibili(Source):
    name = "bilibili"
    description = "B站 video search via the public API (free, no login)."
    host = "api.bilibili.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        data = await client.get_json(
            "https://api.bilibili.com/x/web-interface/search/type",
            params={"search_type": "video", "keyword": query,
                    "page_size": str(min(limit, 30))},
            headers={"User-Agent": "reach-mcp/0.1"},
        )
        rows: list[Row] = []
        for v in ((data.get("data") or {}).get("result") or [])[:limit]:
            pub = v.get("pubdate")
            date = datetime.fromtimestamp(pub, tz=timezone.utc).isoformat() if pub else None
            owner = v.get("owner") or {}
            rows.append(Row(
                source="bilibili", id=v.get("bvid") or "",
                title=re.sub(r"<[^>]+>", "", v.get("title") or ""),
                url=v.get("arcurl") or "",
                author=owner.get("name"), date=date,
                engagement={"play": v.get("play") or 0, "reply": v.get("video_review") or 0},
                text=(v.get("description") or "")[:500],
            ))
        return rows
