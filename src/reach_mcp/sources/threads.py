"""Threads (Meta) via Apify (free $5/month recurring credits).

No viable free server-side API exists otherwise - Meta's Threads API requires a
verified developer account + app review. Apify's threads-scraper Actor runs on
the Free plan's $5 monthly credits (recurring). Requires APIFY_API_TOKEN.
"""
from __future__ import annotations

from reach_mcp.sources._apify import fetch_threads as _apify_fetch
from reach_mcp.sources.base import Row, Source, register_source


@register_source
class Threads(Source):
    name = "threads"
    description = (
        "Threads (Meta) posts via Apify threads-scraper "
        "(free $5 monthly credits; set APIFY_API_TOKEN)."
    )
    host = "www.threads.net"
    needs_auth = True
    required_env = ("APIFY_API_TOKEN",)

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        if not self.available():
            return []
        return await _apify_fetch(query, limit)
