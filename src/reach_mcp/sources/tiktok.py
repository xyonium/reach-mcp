"""TikTok via playwright in-page fetch (free primary) + Apify (paid fallback)
+ ScrapeCreators (one-time) + OpenCLI (optional desktop free).

Priority: playwright (free/unlimited — headless browser per search, closed
immediately after) -> Apify (server-side, recurring free credits) -> OpenCLI
(if on PATH, desktop) -> ScrapeCreators (one-time credits). playwright needs
`pip install playwright && playwright install chromium` in the deployment; it
degrades to a no-op [] when absent.
"""

from __future__ import annotations

import os

from reach_mcp.sources._apify import fetch_tiktok as _apify_fetch
from reach_mcp.sources._opencli import cli_search
from reach_mcp.sources._opencli import has_cli as _has_opencli
from reach_mcp.sources._scrapecreators import scrape_search
from reach_mcp.sources._tiktok_playwright import fetch as _pw_fetch
from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class TikTok(Source):
    name = "tiktok"
    description = (
        "TikTok via free in-browser fetch (playwright+chromium, if installed) "
        "or Apify (APIFY_API_TOKEN) or OpenCLI (desktop) or ScrapeCreators "
        "(SCRAPECREATORS_API_KEY)."
    )
    host = "api.scrapecreators.com"
    needs_auth = True
    required_env = ("APIFY_API_TOKEN",)  # primary; others checked at runtime

    def available(self) -> bool:  # type: ignore[override]
        return bool(
            os.environ.get("APIFY_API_TOKEN", "").strip()
            or os.environ.get("SCRAPECREATORS_API_KEY", "").strip()
            or _has_opencli()
        )

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        # Free playwright backend first (per-call browser lifecycle); [] when
        # uninstalled or blocked -> fall through to the paid backends.
        rows = await _pw_fetch(query, limit)
        if rows:
            return rows
        if os.environ.get("APIFY_API_TOKEN", "").strip():
            return await _apify_fetch(query, limit)
        if _has_opencli():
            rows = await cli_search("tiktok", query, limit)
            if rows:
                return rows
        if os.environ.get("SCRAPECREATORS_API_KEY", "").strip():
            return await scrape_search(get_client(), "tiktok", query, limit)
        return []
