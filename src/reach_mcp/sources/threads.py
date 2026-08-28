"""Threads (Meta) via playwright SSR scrape (free primary) + Apify (paid fallback).

threads.net/search server-renders posts for anonymous browser sessions — a
per-call headless chromium parses the Relay JSON blob (free, unlimited, no
login). Apify's threads-scraper (free $5/month recurring credits) is the
fallback when playwright/chromium isn't installed or gets blocked.
"""

from __future__ import annotations

import os

from reach_mcp.sources._apify import fetch_threads as _apify_fetch
from reach_mcp.sources._threads_playwright import fetch as _pw_fetch
from reach_mcp.sources.base import Row, Source, register_source


@register_source
class Threads(Source):
    name = "threads"
    description = (
        "Threads (Meta) posts via free in-browser SSR scrape (playwright+chromium, "
        "if installed) or Apify threads-scraper (APIFY_API_TOKEN)."
    )
    host = "www.threads.net"
    needs_auth = True
    required_env = ("APIFY_API_TOKEN",)  # fallback; playwright path is keyless

    def available(self) -> bool:  # type: ignore[override]
        # available with the token OR with the free playwright backend present
        if os.environ.get("APIFY_API_TOKEN", "").strip():
            return True
        from reach_mcp.sources._threads_playwright import _playwright_available

        return _playwright_available()

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        # Free playwright backend first (per-call browser lifecycle); [] when
        # uninstalled or blocked -> fall through to Apify.
        rows = await _pw_fetch(query, limit)
        if rows:
            return rows
        if os.environ.get("APIFY_API_TOKEN", "").strip():
            # The pipeline already collapsed `query` to <=2 salient words with
            # boolean operators stripped (Threads keyword search returns zero
            # for 3+ words or leaked "A OR B" — see query_core._STRICT_SOURCES).
            return await _apify_fetch(query, limit)
        return []
