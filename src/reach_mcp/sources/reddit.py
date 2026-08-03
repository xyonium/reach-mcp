"""Reddit via keyless RSS (no API key), multiple feeds combined.

Reddit's .json search is 403/429 keyless, but RSS feeds still serve HTTP 200.
A bare `reach-mcp/0.1` UA works (tested); aggressive/browser UAs and rapid
repeated calls trigger 429, so we fetch a small set of feeds and keep pacing
conservative (min_host_delay is applied by the polite client).

Mirrors last30days' reddit_rss: combine search.rss + subreddit search feeds +
top/monthly listings, dedup by URL.
"""
from __future__ import annotations

import asyncio

import feedparser

from reach_mcp.sources.base import snip, Row, Source, get_client, register_source

_UA = "reach-mcp/0.1"

# Subreddits to probe alongside the global search (community-vetted, high-signal
# for tech topics). Expandable via config later.
_SUBREDDITS = ("technology", "programming", "MachineLearning", "artificial")


async def _fetch_feed(client, url: str, params: dict) -> list[dict]:
    """Fetch one RSS feed, return entries (or [])."""
    try:
        xml = await client.get_text(url, params=params, headers={"User-Agent": _UA})
    except Exception:  # noqa: BLE001
        return []
    feed = feedparser.parse(xml)
    return list(feed.entries)


def _to_row(e) -> Row:
    return Row(
        source="reddit", id=e.get("id") or e.get("link") or "",
        title=e.get("title") or "", url=e.get("link") or "",
        author=e.get("author"), date=e.get("published"),
        engagement={}, text=snip(e.get("summary") or ""),
    )


@register_source
class Reddit(Source):
    name = "reddit"
    description = "Reddit via keyless RSS search (multiple feeds, no API key)."
    host = "www.reddit.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        # Conservative window: RSS t=month caps depth; days maps to t=week for
        # short windows but month is the max Reddit RSS serves for search.
        t = "week" if days <= 14 else "month"

        tasks = [
            # Global search (relevance + time window)
            _fetch_feed(client, "https://www.reddit.com/search.rss",
                        {"q": query, "sort": "relevance", "t": t,
                         "limit": str(min(limit, 50))}),
        ]
        # Subreddit-scoped searches for a couple of the most relevant communities.
        for sub in _SUBREDDITS[:2]:
            tasks.append(_fetch_feed(
                client,
                f"https://www.reddit.com/r/{sub}/search.rss",
                {"q": query, "restrict_sr": "on", "sort": "relevance", "t": t,
                 "limit": str(min(limit, 25))},
            ))

        batches = await asyncio.gather(*tasks, return_exceptions=True)
        seen: set[str] = set()
        rows: list[Row] = []
        for batch in batches:
            if isinstance(batch, Exception) or not batch:
                continue
            for e in batch:
                url = e.get("link") or e.get("id") or ""
                if url and url in seen:
                    continue
                if url:
                    seen.add(url)
                rows.append(_to_row(e))
        return rows[:limit]
