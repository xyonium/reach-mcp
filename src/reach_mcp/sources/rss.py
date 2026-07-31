"""Generic RSS/Atom feed source - free (feedparser, already a dependency).

Query-driven: set RSS_FEEDS to a comma-separated list of feed URLs. Each feed
is fetched and its entries filtered to those matching the query (case-insensitive
substring on title or summary). Opt-in: off unless RSS_FEEDS is set.

This mirrors Agent Reach's rss channel (free, keyless) adapted to reach-mcp's
search(query, days, limit) signature.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import feedparser

from reach_mcp.sources.base import Row, Source, get_client, register_source


def _feed_urls() -> list[str]:
    raw = os.environ.get("RSS_FEEDS", "")
    return [u.strip() for u in raw.split(",") if u.strip()]


def _within_days(date_str: str | None, days: int) -> bool:
    if not date_str:
        return True  # keep undated entries
    try:
        dt = feedparser._parse_date(date_str)  # noqa: SLF001
        if dt is None:
            return True
        # feedparser returns naive local time tuples in some cases; use parsed
        import time as _time
        ts = _time.mktime(dt) if isinstance(dt, _time.struct_time) else None
        if ts is None:
            return True
        age_days = (datetime.now(tz=timezone.utc).timestamp() - ts) / 86400.0
        return age_days <= days
    except Exception:
        return True


@register_source
class Rss(Source):
    name = "rss"
    description = (
        "Generic RSS/Atom feeds (free). Set RSS_FEEDS=url1,url2 to enable; "
        "entries filtered to the query within the recency window."
    )
    host = ""
    needs_auth = False
    required_env = ("RSS_FEEDS",)

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        urls = _feed_urls()
        if not urls:
            return []
        client = get_client()
        ql = query.lower()
        rows: list[Row] = []
        for url in urls:
            try:
                xml = await client.get_text(url, headers={"User-Agent": "reach-mcp/0.1"})
            except Exception:
                continue
            feed = feedparser.parse(xml)
            for e in feed.entries:
                title = e.get("title") or ""
                summary = e.get("summary") or ""
                if ql and ql not in title.lower() and ql not in summary.lower():
                    continue
                if not _within_days(e.get("published"), days):
                    continue
                rows.append(Row(
                    source="rss", id=e.get("id") or e.get("link") or title,
                    title=title, url=e.get("link") or "",
                    author=e.get("author"),
                    date=e.get("published") or e.get("updated"),
                    engagement={},
                    text=summary[:500],
                ))
                if len(rows) >= limit:
                    break
            if len(rows) >= limit:
                break
        return rows[:limit]
