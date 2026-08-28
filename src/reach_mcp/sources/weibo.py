"""微博 (Weibo) search via the mobile API with auto-managed visitor cookies.

Flow (curl-verified 2026-08-27 against m.weibo.cn, datacenter IP, no login):
1. GET visitor.passport.weibo.cn/visitor/genvisitor2 -> JSONP carrying fresh
   SUB/SUBP visitor cookies in one call (the desktop passport two-step flow
   does NOT work for m.weibo.cn — separate wapsso realm).
2. GET m.weibo.cn/api/container/getIndex?containerid=100103type=1&q=<kw>
   with the SUB/SUBP cookies -> ok:1 + cards of real posts.

`ok:-100` means the visitor session died; we regenerate once and retry.
Cookie cache is module-level so consecutive searches in one process reuse it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone

import httpx

from reach_mcp.http import PoliteClient
from reach_mcp.sources.base import Row, Source, get_client, register_source, snip

log = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36"
)
_GENVISITOR_URL = "https://visitor.passport.weibo.cn/visitor/genvisitor2"
_SEARCH_URL = "https://m.weibo.cn/api/container/getIndex"
_HEADERS = {
    "User-Agent": _UA,
    "Referer": "https://m.weibo.cn/",
    "MWeibo-Pwa": "1",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/plain, */*",
}

# Module-level visitor-cookie cache: {SUB, SUBP, fetched_at}. Visitor sessions
# live for days; refetch only on ok:-100 (auth failure) or when absent.
_COOKIE_CACHE: dict | None = None


def _reset_cookie_cache() -> None:
    global _COOKIE_CACHE
    _COOKIE_CACHE = None


async def _visitor_cookies() -> dict[str, str] | None:
    """Return cached SUB/SUBP cookies, fetching fresh ones via genvisitor2.

    The genvisitor2 exchange goes to a different host than the paced search
    client, so it's a direct blocking httpx call run in a worker thread.
    Returns None when the visitor flow fails so fetch() can report
    no_results instead of erroring.
    """
    global _COOKIE_CACHE
    if _COOKIE_CACHE and _COOKIE_CACHE.get("SUB"):
        return _COOKIE_CACHE
    try:
        resp = await asyncio.to_thread(
            httpx.get,
            _GENVISITOR_URL,
            params={"cb": "visitor_callback", "from": "weibo.cn"},
            headers={"User-Agent": _UA},
            timeout=20,
        )
        data = resp.text
    except Exception:  # noqa: BLE001
        log.warning("weibo: genvisitor2 request failed", exc_info=True)
        return None
    match = re.search(r"\((\{.*\})\)", data if isinstance(data, str) else json.dumps(data))
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
        sub, subp = payload["data"]["sub"], payload["data"]["subp"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    if not sub or not subp:
        return None
    _COOKIE_CACHE = {"SUB": sub, "SUBP": subp, "fetched_at": time.monotonic()}
    return _COOKIE_CACHE


def _clean_html(text: str) -> str:
    """mblog text carries inline HTML (<br/>, <a href>): keep the words only."""
    text = re.sub(r"<a [^>]*>", "", text)
    text = re.sub(r"<img[^>]*>", "[图]", text)
    text = re.sub(r"</?br\s*/?>", " ", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


_WEIBO_TS = "%a %b %d %H:%M:%S %z %Y"


def _to_iso(created_at: str) -> str | None:
    """'Tue Aug 25 12:00:00 +0800 2026' -> ISO-8601 in UTC."""
    try:
        return datetime.strptime(created_at, _WEIBO_TS).astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError):
        return None


def _rows_from_cards(data: dict, limit: int) -> list[Row]:
    cards = (data.get("data") or {}).get("cards") or []
    rows: list[Row] = []

    def _emit(mblog: dict) -> None:
        if len(rows) >= limit or not mblog:
            return
        bid = mblog.get("bid") or mblog.get("id") or ""
        user = mblog.get("user") or {}
        rows.append(
            Row(
                source="weibo",
                id=str(mblog.get("id") or bid),
                title=_clean_html(mblog.get("text") or "")[:80] or f"微博 {bid}",
                url=f"https://m.weibo.cn/status/{bid}" if bid else "",
                author=user.get("screen_name"),
                date=_to_iso(mblog.get("created_at") or ""),
                engagement={
                    "reposts": mblog.get("reposts_count") or 0,
                    "comments": mblog.get("comments_count") or 0,
                    "likes": mblog.get("attitudes_count") or 0,
                },
                text=snip(_clean_html(mblog.get("text") or "")),
            )
        )

    for card in cards:
        if card.get("mblog"):
            _emit(card["mblog"])
        for sub_card in card.get("card_group") or []:
            if sub_card.get("mblog"):
                _emit(sub_card["mblog"])
        if len(rows) >= limit:
            break
    return rows


async def _search_once(client: PoliteClient, query: str, limit: int) -> list[Row]:
    cookies = await _visitor_cookies()
    if not cookies:
        return []
    cookie_header = f"SUB={cookies['SUB']}; SUBP={cookies['SUBP']}"
    # NOTE: page_type MUST be a separate query param — putting it inside the
    # containerid string makes the API return hot-search cards (0 mblogs).
    params = {
        "containerid": f"100103type=1&q={query}",
        "page_type": "searchall",
    }
    headers = {**_HEADERS, "Cookie": cookie_header}
    data = await client.get_json(_SEARCH_URL, params=params, headers=headers)
    if data.get("ok") != 1:
        raise RuntimeError(f"weibo auth/session failure: ok={data.get('ok')}")
    return _rows_from_cards(data, limit)


@register_source
class Weibo(Source):
    name = "weibo"
    description = (
        "微博 Weibo search via the mobile API (m.weibo.cn) with auto-rotated "
        "visitor cookies — free, no login. Also exposes 实时热搜 realtimehot."
    )
    host = "m.weibo.cn"
    supports_trending = True

    async def fetch_trending(self, limit: int) -> list[Row]:
        """实时热搜 via filter_type=realtimehot (same visitor cookies)."""
        client = get_client()
        self.last_notice = None
        cookies = await _visitor_cookies()
        if not cookies:
            self.last_notice = (
                "weibo trending unavailable — visitor cookie flow failed "
                "(genvisitor2 unreachable or blocked)"
            )
            return []
        headers = {**_HEADERS, "Cookie": f"SUB={cookies['SUB']}; SUBP={cookies['SUBP']}"}
        params = {
            "containerid": "106003type=25&t=3&disable_hot=1&filter_type=realtimehot",
        }
        data = await client.get_json(_SEARCH_URL, params=params, headers=headers)
        if data.get("ok") != 1:
            raise RuntimeError(f"weibo trending auth failure: ok={data.get('ok')}")
        rows: list[Row] = []
        for card in (data.get("data") or {}).get("cards") or []:
            for g in card.get("card_group") or [card]:
                desc = (g.get("desc") or "").strip()
                if not desc:
                    continue
                scheme = g.get("scheme") or ""
                heat = g.get("desc_extr")
                rows.append(
                    Row(
                        source="weibo",
                        id=f"hot:{desc}",
                        title=desc,
                        url=scheme
                        or f"https://m.weibo.cn/search?containerid=100103type=1&q={desc}",
                        author=None,
                        date=None,
                        engagement={"heat": int(heat) if str(heat).isdigit() else 0},
                        text="微博实时热搜" if not str(heat).isdigit() else f"热度 {heat}",
                    )
                )
                if len(rows) >= limit:
                    return rows
        return rows

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        self.last_notice = None
        try:
            rows = await _search_once(client, query, limit)
        except RuntimeError:
            # Stale/invalid visitor cookie: regenerate once and retry.
            _reset_cookie_cache()
            try:
                rows = await _search_once(client, query, limit)
            except RuntimeError as e:
                # Both attempts failed even with fresh visitor cookies — that's
                # an upstream/anti-bot shift, not a query problem.
                self.last_notice = f"weibo visitor session rejected twice ({e})"
                raise
        if not rows and not self.last_notice:
            # genvisitor2 dead => _visitor_cookies() returned None => empty rows
            self.last_notice = (
                "weibo returned 0 rows — visitor cookie flow may be failing "
                "(genvisitor2 unreachable or blocked); check network egress"
            )
        return rows
