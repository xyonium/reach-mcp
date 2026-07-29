"""Hacker News via Algolia search API (free, no key)."""
from __future__ import annotations

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class HackerNews(Source):
    name = "hackernews"
    description = "Hacker News stories via the Algolia API (free, no key)."
    host = "hn.algolia.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        data = await client.get_json(
            "https://hn.algolia.com/api/v1/search",
            params={"query": query, "tags": "story", "hitsPerPage": min(limit, 50)},
        )
        rows: list[Row] = []
        for h in data.get("hits", []):
            rows.append(Row(
                source="hackernews", id=str(h.get("objectID", "")),
                title=h.get("title") or "",
                url=h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                author=h.get("author"), date=h.get("created_at"),
                engagement={"points": h.get("points") or 0, "comments": h.get("num_comments") or 0},
                text=h.get("story_text") or "",
            ))
        return rows
