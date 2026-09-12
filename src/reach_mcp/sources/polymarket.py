"""Polymarket prediction markets via the public gamma API (free, no key).

The naive ``/markets?query=...`` endpoint IGNORES the query param (live-verified
2026-09: a garbage query and no query return the identical volume-sorted hot
list — that's why searches surfaced the same 2028-nomination markets for every
topic). The working text-search endpoint is ``/public-search?q=...``, which
returns scored ``events[]`` whose embedded ``markets[]`` carry question,
description, outcomePrices, volume and endDate — one call is enough.
"""

from __future__ import annotations

from typing import Any

from reach_mcp.query_core import adapt_query
from reach_mcp.sources.base import Row, Source, get_client, register_source, snip

_SEARCH_URL = "https://gamma-api.polymarket.com/public-search"
_MARKETS_URL = "https://gamma-api.polymarket.com/markets"


@register_source
class Polymarket(Source):
    name = "polymarket"
    description = "Polymarket prediction markets (real-money odds, free public API)."
    host = "gamma-api.polymarket.com"
    supports_trending = True

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        q = adapt_query("polymarket", query)
        # strict -> relaxed tail-drop, paper-search style: long natural-language
        # queries over-match nothing on keyword-intersection search
        words = q.split()
        # strict first at min(len,5), then drop tail words one by one down to 2;
        # 1-word queries run the single attempt unchanged (range floor is 1)
        for k in range(min(max(len(words), 1), 5), 0 if len(words) == 1 else 1, -1):
            attempt = " ".join(words[:k])
            rows = await self._search(attempt, limit)
            if rows:
                if attempt != q:
                    self.last_notice = f"polymarket relaxed '{q}' -> '{attempt}'"
                return rows
        return []

    async def fetch_trending(self, limit: int) -> list[Row]:
        """Open markets ranked by volume — what /markets is actually good for."""
        data = await get_client().get_json(
            _MARKETS_URL,
            params={
                "limit": str(min(limit, 50)),
                "closed": "false",
                "order": "volume",
                "ascending": "false",
            },
        )
        return [
            r for r in (self._market_row(m) for m in (data if isinstance(data, list) else [])) if r
        ]

    async def _search(self, q: str, limit: int) -> list[Row]:
        data = await get_client().get_json(
            _SEARCH_URL, params={"q": q, "limit_per_type": str(min(limit, 20))}
        )
        rows: list[Row] = []
        for ev in (data or {}).get("events") or []:
            if ev.get("closed"):
                continue
            markets = [m for m in ev.get("markets") or [] if not m.get("closed")]
            markets.sort(key=lambda m: -_vol(m))
            for m in markets:
                row = self._market_row(m, ev)
                if row:
                    rows.append(row)
                if len(rows) >= limit:
                    return rows
        return rows

    @staticmethod
    def _market_row(m: dict[str, Any], ev: dict[str, Any] | None = None) -> Row | None:
        question = m.get("question") or (ev or {}).get("title") or ""
        if not question:
            return None
        try:
            vol = float(m.get("volume") or 0)
        except (TypeError, ValueError):
            vol = 0.0
        slug = (ev or {}).get("slug") or m.get("slug") or ""
        text = m.get("description") or (ev or {}).get("description") or ""
        return Row(
            source="polymarket",
            id=str(m.get("id", "")),
            title=question,
            url=f"https://polymarket.com/event/{slug}",
            author=None,
            date=m.get("endDate") or (ev or {}).get("endDate"),
            engagement={"volume": vol, "prices": m.get("outcomePrices", "[]")},
            text=snip(text),
        )


def _vol(m: dict[str, Any]) -> float:
    try:
        return float(m.get("volume") or 0)
    except (TypeError, ValueError):
        return 0.0
