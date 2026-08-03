"""arXiv papers via the Atom API (free, no key), parsed with feedparser."""
from __future__ import annotations

import feedparser

from reach_mcp.sources.base import Row, Source, get_client, register_source, snip


@register_source
class Arxiv(Source):
    name = "arxiv"
    description = "arXiv preprints via the Atom API (free, no key)."
    host = "export.arxiv.org"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        xml = await client.get_text(
            "https://export.arxiv.org/api/query",
            params={"search_query": f"all:{query}", "max_results": str(min(limit, 50))},
        )
        feed = feedparser.parse(xml)
        rows: list[Row] = []
        for e in feed.entries:
            authors = ", ".join(a.get("name", "") for a in e.get("authors", [])) or None
            rows.append(Row(
                source="arxiv",
                id=e.get("id") or "",
                title=e.get("title", "").strip(),
                url=e.get("id") or e.get("link") or "",
                author=authors,
                date=e.get("published"),
                engagement={},
                text=snip(e.get("summary") or ""),
            ))
        return rows
