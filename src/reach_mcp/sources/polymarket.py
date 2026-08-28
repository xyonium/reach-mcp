"""Polymarket prediction markets via the public gamma API (free, no key)."""

from __future__ import annotations

from reach_mcp.sources.base import Row, Source, get_client, register_source, snip


@register_source
class Polymarket(Source):
    name = "polymarket"
    description = "Polymarket prediction markets (real-money odds, free public API)."
    host = "gamma-api.polymarket.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        data = await client.get_json(
            "https://gamma-api.polymarket.com/markets",
            params={"limit": str(min(limit, 50)), "closed": "false", "query": query},
        )
        rows: list[Row] = []
        for m in data if isinstance(data, list) else []:
            try:
                vol = float(m.get("volume") or 0)
            except (TypeError, ValueError):
                vol = 0.0
            prices = m.get("outcomePrices", "[]")
            rows.append(
                Row(
                    source="polymarket",
                    id=str(m.get("id", "")),
                    title=m.get("question") or "",
                    url=f"https://polymarket.com/event/{m.get('slug', '')}",
                    author=None,
                    date=m.get("endDate"),
                    engagement={"volume": vol, "prices": prices},
                    text=snip(m.get("description") or ""),
                )
            )
        return rows
