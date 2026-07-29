"""StockTwits messages via the public API (free, no key). Best for tickers/crypto."""
from __future__ import annotations

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class StockTwits(Source):
    name = "stocktwits"
    description = "StockTwits trader messages (free public API; best for tickers/crypto)."
    host = "api.stocktwits.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        data = await client.get_json(
            f"https://api.stocktwits.com/api/2/streams/symbol/{query}.json",
            params={"limit": str(min(limit, 30))},
        )
        rows: list[Row] = []
        for msg in data.get("messages", []):
            user = (msg.get("user") or {}).get("username")
            rows.append(Row(
                source="stocktwits", id=str(msg.get("id", "")),
                title=(msg.get("body") or "")[:120],
                url=f"https://stocktwits.com/{user}/message/{msg.get('id','')}",
                author=user, date=msg.get("created_at"),
                engagement={}, text=msg.get("body") or "",
            ))
        return rows
