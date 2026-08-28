"""今日头条 (Toutiao) — keyless hot-list API + SSR search scraping.

Two live-verified paths (2026-08-28), both cookie-free from a datacenter IP:
- Trending: www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc returns a
  clean JSON list (50 items, Title/HotValue/Url) — no signature needed.
- Search: the so.toutiao.com search page server-renders results into
  <script type="application/json"> card blobs (title/abstract/article_url/
  source/publish_time, with <b> highlight tags). The dedicated content API
  (/api/search/content) requires msToken signing and returns empty without a
  browser — the SSR scrape avoids that entirely.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from reach_mcp.sources.base import Row, Source, get_client, register_source, snip

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_HOT_URL = "https://www.toutiao.com/hot-event/hot-board/"
_SEARCH_URL = "https://so.toutiao.com/search"
_BLOB_RE = re.compile(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', re.S)
_TAG_RE = re.compile(r"<[^>]+>")


@register_source
class Toutiao(Source):
    name = "toutiao"
    description = (
        "今日头条 hot list (热搜榜, keyless) and keyword search across CN news "
        "articles (SSR scrape, keyless)."
    )
    host = "www.toutiao.com"
    supports_trending = True

    async def fetch_trending(self, limit: int) -> list[Row]:
        client = get_client()
        self.last_notice = None
        data = await client.get_json(
            _HOT_URL, params={"origin": "toutiao_pc"}, headers={"User-Agent": _UA}
        )
        rows: list[Row] = []
        for item in (data.get("data") or [])[:limit]:
            title = str(item.get("Title") or "").strip()
            if not title:
                continue
            try:
                hot = int(str(item.get("HotValue") or "0"))
            except ValueError:
                hot = 0
            rows.append(
                Row(
                    source="toutiao",
                    id=str(item.get("ClusterIdStr") or item.get("ClusterId") or title),
                    title=title,
                    url=str(item.get("Url") or ""),
                    author=None,
                    date=None,
                    engagement={"hot": hot},
                    text=str(item.get("LabelDesc") or "头条热榜"),
                )
            )
        return rows

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        self.last_notice = None
        # NOTE: no Referer — sending one makes so.toutiao.com serve a JS-shell
        # page without the SSR result cards (verified live: 610KB w/ results vs
        # 211KB shell). Plain UA-only request gets the full server render.
        html = await client.get_text(
            _SEARCH_URL,
            params={"dvpf": "pc", "keyword": query},
            headers={"User-Agent": _UA},
        )
        rows: list[Row] = []
        seen: set[str] = set()
        for blob in _BLOB_RE.findall(html):
            try:
                payload = json.loads(blob)
            except json.JSONDecodeError:
                continue
            for card in self._find_cards(payload):
                url = str(card.get("article_url") or card.get("display_url") or "")
                if not url or url in seen:
                    continue
                title = _TAG_RE.sub("", str(card.get("title") or "")).strip()
                if not title:
                    continue
                seen.add(url)
                abstract = _TAG_RE.sub("", str(card.get("abstract") or "")).strip()
                rows.append(
                    Row(
                        source="toutiao",
                        id=str(card.get("id") or card.get("gid") or url),
                        title=title,
                        url=url,
                        author=str(card.get("source") or "") or None,
                        date=self._iso(card.get("publish_time")),
                        engagement={},
                        text=snip(abstract),
                    )
                )
                if len(rows) >= limit:
                    return rows
        return rows

    @staticmethod
    def _iso(ts) -> str | None:
        """publish_time is unix seconds; None/unparseable stays None."""
        try:
            return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _find_cards(payload) -> list[dict]:
        """Walk an arbitrarily-nested card blob collecting result items —
        they are the dicts carrying an article_url."""
        found: list[dict] = []
        stack = [payload]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                if "article_url" in cur or "display_url" in cur:
                    found.append(cur)
                stack.extend(cur.values())
            elif isinstance(cur, list):
                stack.extend(cur)
        return found
