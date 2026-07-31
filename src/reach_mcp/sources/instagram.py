"""Instagram via Apify (primary, free $5/mo) + OpenCLI (optional desktop free)
+ ScrapeCreators (fallback, one-time credits).

Priority: Apify (server-side, recurring free credits) -> OpenCLI (desktop, free)
-> ScrapeCreators (one-time credits). First configured backend wins.
"""
from __future__ import annotations

import os

from reach_mcp.sources._apify import fetch_instagram as _apify_fetch
from reach_mcp.sources._opencli import cli_search
from reach_mcp.sources._opencli import has_cli as _has_opencli
from reach_mcp.sources._scrapecreators import scrape_search
from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class Instagram(Source):
    name = "instagram"
    description = (
        "Instagram via Apify (free $5/mo; APIFY_API_TOKEN) or OpenCLI (desktop, "
        "free) or ScrapeCreators (100 one-time credits; SCRAPECREATORS_API_KEY)."
    )
    host = "api.scrapecreators.com"
    needs_auth = True
    required_env = ("APIFY_API_TOKEN",)

    def available(self) -> bool:  # type: ignore[override]
        return bool(
            os.environ.get("APIFY_API_TOKEN", "").strip()
            or os.environ.get("SCRAPECREATORS_API_KEY", "").strip()
            or _has_opencli()
        )

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        if os.environ.get("APIFY_API_TOKEN", "").strip():
            return await _apify_fetch(query, limit)
        if _has_opencli():
            rows = await cli_search("instagram", query, limit)
            if rows:
                return rows
        if os.environ.get("SCRAPECREATORS_API_KEY", "").strip():
            return await scrape_search(get_client(), "instagram", query, limit)
        return []
