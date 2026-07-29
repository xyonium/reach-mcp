"""Generic web search via a self-hosted Searxng JSON endpoint (SEARXNG_URL)."""
from __future__ import annotations

import os

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class Web(Source):
    name = "web"
    description = "Generic web search via Searxng (set SEARXNG_URL)."
    host = ""

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        base = os.environ.get("SEARXNG_URL", "http://searxng:8080").rstrip("/")
        params = {"q": query, "format": "json", "safesearch": 0}
        if 0 < days <= 365:
            params["time_range"] = f"{days}d"
        data = await client.get_json(base + "/search", params=params)
        rows: list[Row] = []
        for r in (data.get("results") or [])[:limit]:
            rows.append(Row(
                source="web", id=r.get("url") or "",
                title=r.get("title") or "", url=r.get("url") or "",
                author=None, date=r.get("publishedDate"),
                engagement={}, text=(r.get("content") or "")[:500],
            ))
        return rows
