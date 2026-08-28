"""Truth Social via the Mastodon-compatible API (TRUTHSOCIAL_TOKEN bearer, free).

Truth Social sits behind Cloudflare that 403s httpx (TLS-fingerprint) and
generic/browser UAs, but passes urllib with the last30days skill UA. So this
source uses stdlib urllib (mirroring last30days) rather than PoliteClient.
Content is HTML; strip tags like last30days does.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from reach_mcp.sources.base import Row, Source, register_source


def _strip_html(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html)
    return re.sub(r"<[^>]+>", "", text).strip()


def _fetch_sync(query: str, limit: int) -> list[dict]:
    """Synchronous urllib call, run via asyncio.to_thread so fetch stays async."""
    token = os.environ.get("TRUTHSOCIAL_TOKEN", "").strip()
    if not token:
        return []
    params = urlencode({"q": query, "type": "statuses", "limit": str(min(limit, 40))})
    url = f"https://truthsocial.com/api/v2/search?{params}"
    req = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            # Cloudflare passes this UA + urllib TLS, blocks httpx/generic.
            "User-Agent": "last30days-skill/3.0 (Assistant Skill)",
        },
    )
    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return []
    statuses = data.get("statuses") if isinstance(data, dict) else data
    return statuses if isinstance(statuses, list) else []


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
        statuses = await asyncio.to_thread(_fetch_sync, query, limit)
        rows: list[Row] = []
        for s in statuses:
            acct = (s.get("account") or {}).get("username")
            content = _strip_html(s.get("content") or "")
            rows.append(
                Row(
                    source="truthsocial",
                    id=s.get("id") or "",
                    title=content[:120],
                    url=s.get("url") or f"https://truthsocial.com/@{acct}/{s.get('id')}",
                    author=acct,
                    date=s.get("created_at"),
                    engagement={
                        "likes": s.get("favourites_count") or 0,
                        "reblogs": s.get("reblogs_count") or 0,
                        "replies": s.get("replies_count") or 0,
                    },
                    text=content,
                )
            )
        return rows
