"""Truth Social via the Mastodon-compatible API (TRUTHSOCIAL_TOKEN bearer, free)."""
from __future__ import annotations

import os

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class TruthSocial(Source):
    name = "truthsocial"
    description = "Truth Social search via Mastodon API (free-account bearer token)."
    host = "truthsocial.com"
    needs_auth = True
    required_env = ("TRUTHSOCIAL_TOKEN",)

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        if not self.available():
            return []
        client = get_client()
        headers = {"Authorization": f"Bearer {os.environ['TRUTHSOCIAL_TOKEN']}"}
        try:
            data = await client.get_json(
                "https://truthsocial.com/api/v2/search",
                params={"q": query, "type": "statuses", "limit": str(min(limit, 40))},
                headers=headers,
            )
        except Exception:  # noqa: BLE001
            return []
        rows: list[Row] = []
        statuses = data.get("statuses") if isinstance(data, dict) else data
        for s in statuses or []:
            acct = (s.get("account") or {}).get("username")
            rows.append(Row(
                source="truthsocial", id=s.get("id") or "",
                title=(s.get("content") or "")[:120],
                url=s.get("url") or f"https://truthsocial.com/@{acct}/{s.get('id')}",
                author=acct, date=s.get("created_at"),
                engagement={"likes": s.get("favourites_count") or 0,
                            "reblogs": s.get("reblogs_count") or 0,
                            "replies": s.get("replies_count") or 0},
                text=s.get("content") or "",
            ))
        return rows
