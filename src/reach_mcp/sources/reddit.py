"""Reddit via RSS/JSON (keyless). Uses feedparser over the polite client's text."""
from __future__ import annotations

import feedparser

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class Reddit(Source):
    name = "reddit"
    description = "Reddit via keyless RSS search (no API key)."
    host = "www.reddit.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        xml = await client.get_text(
            "https://www.reddit.com/search.rss",
            params={"q": query, "limit": str(min(limit, 50))},
            headers={"User-Agent": "reach-mcp/0.1"},
        )
        feed = feedparser.parse(xml)
        rows: list[Row] = []
        for e in feed.entries:
            rows.append(Row(
                source="reddit", id=e.get("id") or e.get("link") or "",
                title=e.get("title") or "", url=e.get("link") or "",
                author=e.get("author"), date=e.get("published"),
                engagement={}, text=(e.get("summary") or "")[:500],
            ))
        return rows
