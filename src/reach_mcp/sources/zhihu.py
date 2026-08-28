"""知乎 (Zhihu): cookie search (ZHIHU_COOKIE) + unauthenticated hot-list browse.

Two verified tiers (curl-tested 2026-08):

1. **Search** — `www.zhihu.com/api/v4/search_v3?t=general&q=...` with a
   logged-in Cookie header (ZHIHU_COOKIE, the browser `Cookie:` string
   containing z_c0). Verified working WITHOUT the x-zse-96 signature when the
   cookie rides along; results are search_result objects (answers/articles)
   with voteup/comment counts and excerpts. Anonymous/WAF'd requests get 403
   code 10003 (needs signature) — no cookie means tier 2.
2. **Hot list** — `api.zhihu.com/topstory/hot-lists/total` (mobile host)
   returns the top-30 热榜 with a plain UA and no login. Theme-browse: the
   list is filtered by query keywords, degrading to the raw list when
   nothing matches.

Search failures (expired cookie, WAF) degrade to the hot list rather than
erroring the whole source.
"""

from __future__ import annotations

import html
import logging
import os
import re
from datetime import datetime, timezone
from urllib.parse import quote

from reach_mcp.sources.base import Row, Source, get_client, register_source, snip

log = logging.getLogger(__name__)

_HOT_URL = "https://api.zhihu.com/topstory/hot-lists/total"
_SEARCH_URL = "https://www.zhihu.com/api/v4/search_v3"
_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36"
)
_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def _cookie_str() -> str:
    return os.environ.get("ZHIHU_COOKIE", "").strip()


def _strip_tags(text: str) -> str:
    """excerpt/title carry <em> highlights and HTML entities."""
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _rows_from_search(data: dict, limit: int) -> list[Row]:
    rows: list[Row] = []
    for entry in data.get("data") or []:
        if entry.get("type") != "search_result":
            continue  # gaokao/hot_timing/knowledge_ad noise
        obj = entry.get("object") or {}
        oid = str(obj.get("id") or "")
        if not oid:
            continue
        # answers nest the question title; articles carry their own
        question = obj.get("question") or {}
        title = _strip_tags(question.get("title") or obj.get("title") or "")
        if not title:
            continue
        created = obj.get("created_time")
        date = datetime.fromtimestamp(created, tz=timezone.utc).isoformat() if created else None
        # canonical web URL from ids (obj.url points at the signed api host)
        if obj.get("type") == "article":
            url = f"https://zhuanlan.zhihu.com/p/{oid}"
        elif question.get("id"):
            url = f"https://www.zhihu.com/question/{question['id']}/answer/{oid}"
        else:
            url = f"https://www.zhihu.com/answer/{oid}"
        rows.append(
            Row(
                source="zhihu",
                id=oid,
                title=title,
                url=url,
                author=(obj.get("author") or {}).get("name") or None,
                date=date,
                engagement={
                    "upvotes": obj.get("voteup_count") or 0,
                    "comments": obj.get("comment_count") or 0,
                },
                text=snip(_strip_tags(obj.get("excerpt") or "")),
            )
        )
        if len(rows) >= limit:
            break
    return rows


async def _search(client, query: str, limit: int) -> list[Row]:
    cookie = _cookie_str()
    if not cookie:
        return []
    data = await client.get_json(
        _SEARCH_URL,
        params={
            "t": "general",
            "q": query,
            "correction": 1,
            "offset": 0,
            "limit": min(limit * 2, 20),
        },
        headers={
            "User-Agent": _DESKTOP_UA,
            "Cookie": cookie,
            # headers must be latin-1: percent-encode the CN query in Referer
            "Referer": f"https://www.zhihu.com/search?type=content&q={quote(query)}",
            "x-requested-with": "fetch",
        },
    )
    return _rows_from_search(data, limit)


def _rows_from_payload(data: dict, limit: int) -> list[Row]:
    rows: list[Row] = []
    for entry in (data.get("data") or [])[:limit]:
        t = entry.get("target") or {}
        qid = str(t.get("id") or "")
        title = (t.get("title") or "").strip()
        if not title:
            continue
        rows.append(
            Row(
                source="zhihu",
                id=qid,
                title=title,
                # api host URL needs the x-zse-96 signature; link the canonical page
                url=f"https://www.zhihu.com/question/{qid}" if qid else (t.get("url") or ""),
                author=None,
                date=None,  # hot list carries no timestamps
                engagement={
                    "followers": t.get("follower_count") or 0,
                    "answers": t.get("answer_count") or 0,
                },
                text=snip(entry.get("detail_text") or ""),
            )
        )
    return rows


def _matches(row: Row, ql: str) -> bool:
    return ql in row.title.lower()


@register_source
class Zhihu(Source):
    name = "zhihu"
    description = (
        "知乎 (Zhihu): real search via search_v3 with ZHIHU_COOKIE (browser "
        "Cookie string with z_c0); without it, 热榜 hot-list browse via the "
        "mobile API — top-30 filtered by query, degrading to the raw list. "
        "Search failures fall back to the hot list."
    )
    host = "zhihu.com"
    required_env = ()  # hot-list works without anything; cookie is a boost

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        if _cookie_str():
            try:
                rows = await _search(client, query, limit)
                if rows:
                    return rows
            except Exception as e:  # noqa: BLE001
                log.warning("zhihu search failed (%s); degrading to hot list", e)
        data = await client.get_json(_HOT_URL, params={"limit": 50}, headers={"User-Agent": _UA})
        rows = _rows_from_payload(data, limit * 2)  # headroom for filtering
        ql = query.strip().lower()
        if not ql:
            return rows[:limit]
        hits = [r for r in rows if _matches(r, ql)]
        # Substring misses plurals/tokens ("AI" in "人工智能" won't hit); try
        # per-word matching before degrading to the raw hot list.
        if not hits:
            words = [w for w in ql.split() if len(w) >= 2]
            hits = [r for r in rows if any(w in r.title.lower() for w in words)]
        return (hits or rows)[:limit]
