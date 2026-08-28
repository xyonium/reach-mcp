"""Quora Q&A search: Searxng site:-scoped free primary + Apify fallback.

Quora's own endpoints are Cloudflare-walled from datacenter IPs — plain HTTP
403s and a headless-chromium challenge never clears (verified 2026-08-28).
The stable free path is Searxng with a site:quora.com scope (real question
pages, no credential, no browser). Apify's quora-search-scraper (which returns
engagement: upvotes/views) is the fallback when Searxng is unset or empty.
"""

from __future__ import annotations

import os

from reach_mcp.sources._apify import fetch_quora as _apify_fetch
from reach_mcp.sources.base import Row, Source, get_client, register_source, snip


@register_source
class Quora(Source):
    name = "quora"
    description = (
        "Quora Q&A search via Searxng site:-scope (free, no login) with Apify "
        "fallback (APIFY_API_TOKEN adds upvote/view engagement)."
    )
    host = "www.quora.com"
    needs_auth = True
    required_env = ("APIFY_API_TOKEN",)  # fallback; Searxng path is keyless

    def available(self) -> bool:  # type: ignore[override]
        return bool(
            os.environ.get("APIFY_API_TOKEN", "").strip()
            or os.environ.get("SEARXNG_URL", "").strip()
        )

    async def _searxng(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        base = os.environ.get("SEARXNG_URL", "http://searxng:8080").rstrip("/")
        # No time_range: Quora pages carry no publish date, so Searxng's date
        # filter discards nearly all of them (live: 35 -> 15 -> 1 for
        # year/month). The Q&A corpus is evergreen; undated rows just score
        # lower in the pipeline's recency decay.
        params = {"q": f"{query} site:quora.com", "format": "json", "safesearch": 0}
        try:
            data = await client.get_json(base + "/search", params=params)
        except Exception:  # noqa: BLE001
            return []
        rows: list[Row] = []
        for r in (data.get("results") or [])[:limit]:
            url = str(r.get("url") or "")
            title = str(r.get("title") or "").strip()
            if not url or not title or "quora.com" not in url:
                continue
            rows.append(
                Row(
                    source="quora",
                    id=url,
                    title=title,
                    url=url,
                    author=None,
                    date=r.get("publishedDate"),
                    engagement={},
                    text=snip(str(r.get("content") or "")),
                )
            )
        return rows

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        self.last_notice = None
        rows = await self._searxng(query, days, limit)
        if rows:
            return rows
        if os.environ.get("APIFY_API_TOKEN", "").strip():
            return await _apify_fetch(query, limit)
        return []
