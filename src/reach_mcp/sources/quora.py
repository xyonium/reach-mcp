"""Quora Q&A search: exa highlights (richest) -> Searxng -> Apify.

Quora's own endpoints are Cloudflare-walled from datacenter IPs — plain HTTP
403s and a headless-chromium challenge never clears (verified 2026-08-28), and
the cf_clearance cookie is IP-bound so cookie-seeding doesn't transfer. The
discovery ladder (all verified 2026-08-29):
1. exa includeDomains:quora.com + highlights — answer-content snippets + some
   publishedDates (EXA_API_KEY, metered but the richest discovery);
2. Searxng site:quora.com — free, title+thin-snippet, no dates;
3. Apify quora-search-scraper — engagement (upvotes/views), paid credits.
"""

from __future__ import annotations

import os

from reach_mcp.sources._apify import fetch_quora as _apify_fetch
from reach_mcp.sources._exa import search as _exa_search
from reach_mcp.sources.base import Row, Source, get_client, register_source, snip


@register_source
class Quora(Source):
    name = "quora"
    description = (
        "Quora Q&A search via exa highlights (EXA_API_KEY, answer-rich + dates), "
        "Searxng site:-scope (free), or Apify (APIFY_API_TOKEN, upvotes/views)."
    )
    host = "www.quora.com"
    needs_auth = True
    required_env = ("APIFY_API_TOKEN",)  # fallback; exa/Searxng paths keyless-config

    def available(self) -> bool:  # type: ignore[override]
        return bool(
            os.environ.get("APIFY_API_TOKEN", "").strip()
            or os.environ.get("SEARXNG_URL", "").strip()
            or os.environ.get("EXA_API_KEY", "").strip()
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
        # 1. exa: answer highlights + dates (richest), only when key is set
        if os.environ.get("EXA_API_KEY", "").strip():
            rows = await _exa_search(query, "quora.com", "quora", limit, days)
            if rows:
                return rows
        # 2. Searxng: free, title+thin snippet
        rows = await self._searxng(query, days, limit)
        if rows:
            return rows
        # 3. Apify: engagement (upvotes/views), paid credits
        if os.environ.get("APIFY_API_TOKEN", "").strip():
            return await _apify_fetch(query, limit)
        return []
