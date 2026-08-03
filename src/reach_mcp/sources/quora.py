"""Quora question/answer search via Apify (api-empire/quora-search-scraper).

Keyword search over public Quora content — no login/cookies needed. Actor
verified 2026-08: `searchQueries[]` + `maxResults` returns questions and
answers with engagement (upvotes, comments, shares, views).
"""
from __future__ import annotations

import os

from reach_mcp.sources.base import Row, Source, register_source


@register_source
class Quora(Source):
    name = "quora"
    description = (
        "Quora Q&A search via Apify (keyword search, no login; set "
        "APIFY_API_TOKEN). Returns questions and answers with upvotes/views."
    )
    host = "www.quora.com"
    needs_auth = True
    required_env = ("APIFY_API_TOKEN",)

    def available(self) -> bool:  # type: ignore[override]
        return bool(os.environ.get("APIFY_API_TOKEN", "").strip())

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        from reach_mcp.sources._apify import fetch_quora
        return await fetch_quora(query, limit)
