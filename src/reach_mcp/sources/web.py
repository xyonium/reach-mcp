"""Generic web search via Searxng (free, self-hosted) with optional Brave boost.

Primary: Searxng JSON endpoint at SEARXNG_URL (free, unlimited, self-hosted).
Optional boost: Brave Search API (BRAVE_API_KEY - $5 free credits every month,
recurring). When a Brave key is set, both backends run in parallel and results
are merged + deduped.
"""
from __future__ import annotations

import asyncio
import os

from reach_mcp.sources.base import snip, Row, Source, get_client, register_source


def _searxng_params(query: str, days: int) -> dict:
    p = {"q": query, "format": "json", "safesearch": 0}
    if 0 < days <= 365:
        p["time_range"] = f"{days}d"
    return p


async def _searxng_fetch(query: str, days: int, limit: int) -> list[Row]:
    client = get_client()
    base = os.environ.get("SEARXNG_URL", "http://searxng:8080").rstrip("/")
    try:
        data = await client.get_json(
            base + "/search", params=_searxng_params(query, days)
        )
    except Exception:
        return []
    rows: list[Row] = []
    for r in (data.get("results") or [])[:limit]:
        rows.append(Row(
            source="web", id=r.get("url") or "",
            title=r.get("title") or "", url=r.get("url") or "",
            author=None, date=r.get("publishedDate"),
            engagement={}, text=snip(r.get("content") or ""),
        ))
    return rows


async def _brave_fetch(query: str, days: int, limit: int) -> list[Row]:
    """Brave Search API - $5 free credits/month (recurring). Requires key."""
    client = get_client()
    key = os.environ.get("BRAVE_API_KEY", "").strip()
    if not key:
        return []
    params = {"q": query, "count": str(min(limit, 20))}
    # Brave supports freshness filtering: "pd<N>" = past N days (max 365)
    if 0 < days <= 365:
        params["freshness"] = f"pd{days}"
    try:
        data = await client.get_json(
            "https://api.search.brave.com/res/v1/web/search",
            params=params,
            headers={"Accept": "application/json",
                     "X-Subscription-Token": key},
        )
    except Exception:
        return []
    rows: list[Row] = []
    for r in (data.get("web", {}).get("results") or [])[:limit]:
        rows.append(Row(
            source="web", id=r.get("url") or "",
            title=r.get("title") or "", url=r.get("url") or "",
            author=None, date=r.get("age") or r.get("page_age"),
            engagement={}, text=snip(r.get("description") or ""),
        ))
    return rows


@register_source
class Web(Source):
    name = "web"
    description = (
        "Web search via Searxng (free primary) + optional Brave boost "
        "(BRAVE_API_KEY, $5 free credits/month recurring)."
    )
    host = ""

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        tasks = [_searxng_fetch(query, days, limit)]
        if os.environ.get("BRAVE_API_KEY", "").strip():
            tasks.append(_brave_fetch(query, days, limit))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        seen, rows = set(), []
        for batch in results:
            if isinstance(batch, Exception) or not batch:
                continue
            for row in batch:
                if row.url and row.url not in seen:
                    seen.add(row.url)
                    rows.append(row)
        return rows[:limit]
