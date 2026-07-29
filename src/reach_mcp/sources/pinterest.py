"""Pinterest via ScrapeCreators (free-tier key). Off by default."""
from __future__ import annotations

from reach_mcp.sources._scrapecreators import scrape_search
from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class Pinterest(Source):
    name = "pinterest"
    description = "Pinterest search via ScrapeCreators (free-tier key)."
    host = "api.scrapecreators.com"
    needs_auth = True
    required_env = ("SCRAPECREATORS_API_KEY",)

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        if not self.available():
            return []
        client = get_client()
        return await scrape_search(client, "pinterest", query, limit)
