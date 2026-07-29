"""Techmeme tech-news headlines via simple scrape (free, no key)."""
from __future__ import annotations

import re

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class Techmeme(Source):
    name = "techmeme"
    description = "Techmeme editorial tech-news headlines (free scrape)."
    host = "www.techmeme.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        html = await client.get_text("https://www.techmeme.com/river")
        rows: list[Row] = []
        # each headline is an anchor; keep the regex loose & resilient to markup drift
        for m in re.finditer(r'href="(https?://[^"]+)"[^>]*>([^<]{8,200})</a>', html):
            url, title = m.group(1), m.group(2).strip()
            if query.lower() in title.lower() or not query:
                rows.append(Row(source="techmeme", id=url, title=title, url=url,
                                author=None, date=None, engagement={}, text=""))
            if len(rows) >= limit:
                break
        return rows
