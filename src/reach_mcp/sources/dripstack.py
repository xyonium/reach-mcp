"""DripStack - free, keyless search over premium financial newsletters.

Public JSON API at https://dripstack.xyz/api/v1/search - no key, no payment.
Indexes Substack-style analyst write-ups; returns metadata + snippets
(full articles are behind a paid layer, which we deliberately do not touch).

Complements the finance cluster: stocktwits = retail sentiment,
polymarket = real-money odds, dripstack = professional analyst/newsletter takes.
"""

from __future__ import annotations

import re

from reach_mcp.sources.base import Row, Source, get_client, register_source, snip


@register_source
class Dripstack(Source):
    name = "dripstack"
    description = (
        "DripStack: free keyless search over premium financial newsletters "
        "(analyst/Substack write-ups). Best for ticker/company research."
    )
    host = "dripstack.xyz"
    needs_auth = False
    required_env = ()

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        try:
            data = await client.get_json(
                "https://dripstack.xyz/api/v1/search",
                params={"q": query, "limit": str(min(limit, 30))},
                headers={"User-Agent": "reach-mcp/0.1"},
            )
        except Exception:
            return []
        rows: list[Row] = []
        items = data.get("items") if isinstance(data, dict) else data
        if not isinstance(items, list):
            items = []
        for item in items[:limit]:
            title = item.get("title") or item.get("headline") or ""
            # API has no full URL; items carry slug + publicationSlug. Build a
            # stable permalink from them (best effort).
            slug = item.get("slug") or item.get("id") or ""
            pub = item.get("publicationSlug") or ""
            url = item.get("url") or item.get("link") or ""
            if not url and slug:
                url = (
                    f"https://dripstack.xyz/{pub}/{slug}"
                    if pub
                    else f"https://dripstack.xyz/{slug}"
                )
            snippet = (
                item.get("subtitle")
                or item.get("snippet")
                or item.get("summary")
                or item.get("whyMatched")
                or ""
            )
            # strip HTML tags from snippet if present
            text = re.sub(r"<[^>]+>", "", snippet) if snippet else ""
            rows.append(
                Row(
                    source="dripstack",
                    id=url or title,
                    title=title[:200],
                    url=url,
                    author=item.get("author") or item.get("newsletter"),
                    date=item.get("publishedAt") or item.get("date"),
                    engagement={
                        "relevance": item.get("relevanceScore") or item.get("matchConfidence") or 0
                    },
                    text=snip(text),
                )
            )
        return rows
