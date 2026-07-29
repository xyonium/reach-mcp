"""雪球 (Xueqiu) hot posts/news via scrape (free, no key)."""
from __future__ import annotations

import re

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class Xueqiu(Source):
    name = "xueqiu"
    description = "雪球 hot posts & news (free scrape)."
    host = "xueqiu.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        html = await client.get_text(
            "https://xueqiu.com/karma/catalog/searchHots.json",
            params={"q": query},
            headers={"User-Agent": "reach-mcp/0.1"},
        )
        rows: list[Row] = []
        # tolerant regex over HTML when the JSON endpoint is gated/changed
        for m in re.finditer(r'href="(/[\w/]+)"[^>]*class="title"[^>]*>([^<]+)</a>', html):
            path, title = m.group(1), m.group(2).strip()
            url = "https://xueqiu.com" + path
            rows.append(Row(source="xueqiu", id=url, title=title, url=url,
                            author=None, date=None, engagement={}, text=""))
            if len(rows) >= limit:
                break
        return rows
