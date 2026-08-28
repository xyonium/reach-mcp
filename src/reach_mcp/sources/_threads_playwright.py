"""Threads (Meta) search via headless-browser SSR scrape — free, no quotas.

threads.net/search server-renders results for anonymous browser sessions: the
page HTML embeds a Relay-prefetched JSON blob carrying searchResults.edges[]
(thread_items[].post with pk/code/user/caption/taken_at/like_count/
text_post_app_info counts). Live-verified 2026-08-28 from the container: plain
curl 301->threads.com serves a login shell, but headless chromium gets the full
1.8MB render with posts. No GraphQL replay needed — just render + parse.

Memory contract (same as tiktok's): one browser per search call, closed in a
finally; playwright imported lazily so the source degrades to Apify when
playwright/chromium isn't installed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone

from reach_mcp.sources.base import Row

log = logging.getLogger(__name__)

_SEARCH_URL = "https://www.threads.net/search"
_BLOB_RE = re.compile(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', re.S)


def _playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError:
        return False
    return True


def _playwright():
    from playwright.async_api import async_playwright

    return async_playwright()


async def _launch_browser(pw):
    return await pw.chromium.launch(
        headless=True, args=["--disable-blink-features=AutomationControlled"]
    )


def _iso(ts) -> str | None:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def extract_search_results(payload) -> dict | None:
    """Walk an arbitrarily-nested Relay require-chain blob and return the
    first dict that has searchResults with edges. The blob nests several
    layers deep (ScheduledServerJS -> __bbox -> RelayPrefetchedStreamCache ->
    result.data.searchResults) and the path varies — walk, don't assume."""
    stack = [payload]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            sr = cur.get("searchResults")
            if isinstance(sr, dict) and isinstance(sr.get("edges"), list):
                return sr
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return None


def parse_items(raw: dict, limit: int) -> list[Row]:
    """Map searchResults.edges[] into Rows. Skips ads/modules without a real
    thread_items post, and posts missing pk/code (can't build a URL)."""
    rows: list[Row] = []
    for edge in (raw or {}).get("edges") or []:
        thread = ((edge or {}).get("node") or {}).get("thread") or {}
        items = thread.get("thread_items") or []
        if not items:
            continue
        post = items[0].get("post") or {}
        pk = str(post.get("pk") or "")
        code = str(post.get("code") or "")
        username = (post.get("user") or {}).get("username") or ""
        caption = ((post.get("caption") or {}).get("text") or "").strip()
        if not pk or not code or not caption:
            continue
        info = post.get("text_post_app_info") or {}
        rows.append(
            Row(
                source="threads",
                id=pk,
                title=caption[:120],
                url=f"https://www.threads.net/@{username}/post/{code}",
                author=username or None,
                date=_iso(post.get("taken_at")),
                engagement={
                    "likes": post.get("like_count") or 0,
                    "replies": info.get("direct_reply_count") or 0,
                    "reposts": info.get("repost_count") or 0,
                    "quotes": info.get("quote_count") or 0,
                },
                text=caption,
            )
        )
        if len(rows) >= limit:
            break
    return rows


async def fetch(query: str, limit: int, timeout: float = 60) -> list[Row]:
    """One search = one browser lifecycle. Raises nothing: failures log and
    return [] so the Apify fallback still gets its turn."""
    if not _playwright_available():
        return []
    try:
        return await asyncio.wait_for(_search(query, limit), timeout=timeout)
    except Exception as e:  # noqa: BLE001
        log.warning("threads playwright backend failed: %s", e)
        return []


async def _search(query: str, limit: int) -> list[Row]:
    async with _playwright() as pw:
        browser = await _launch_browser(pw)
        try:
            context = await browser.new_context(locale="en-US")
            page = await context.new_page()
            await page.goto(
                f"{_SEARCH_URL}?q={query}&serp_type=default",
                wait_until="domcontentloaded",
                timeout=45_000,
            )
            # SSR blob streams in after first paint; give Relay time to land
            await page.wait_for_timeout(6_000)
            html = await page.content()
            for blob in _BLOB_RE.findall(html):
                if "searchResults" not in blob:
                    continue
                try:
                    payload = json.loads(blob)
                except json.JSONDecodeError:
                    continue
                sr = extract_search_results(payload)
                if sr and sr.get("edges"):
                    return parse_items(sr, limit)
            return []
        finally:
            try:
                await browser.close()
            except Exception:  # noqa: BLE001
                pass
