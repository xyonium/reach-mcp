"""Shared ScrapeCreators helper for tiktok/instagram/linkedin/pinterest."""

from __future__ import annotations

import os

from reach_mcp.sources.base import Row, snip


async def scrape_search(client, platform: str, query: str, limit: int) -> list[Row]:
    key = os.environ["SCRAPECREATORS_API_KEY"]
    headers = {"x-api-key": key}
    try:
        data = await client.get_json(
            f"https://api.scrapecreators.com/v1/{platform}/search",
            params={"query": query, "limit": str(limit)},
            headers=headers,
        )
    except Exception:  # noqa: BLE001
        return []
    rows: list[Row] = []
    items = data.get("data") or data.get("results") or []
    for item in items[:limit]:
        rows.append(
            Row(
                source=platform,
                id=str(item.get("id") or item.get("url", "")),
                title=(item.get("caption") or item.get("title") or "")[:120],
                url=item.get("url") or "",
                author=item.get("username") or item.get("author"),
                date=item.get("created_at"),
                engagement={"likes": item.get("likes") or 0, "views": item.get("views") or 0},
                text=snip(item.get("caption") or item.get("text") or ""),
            )
        )
    return rows
