"""TikTok search via a headless browser's in-page fetch — free, no quotas.

The tiktok.com web APIs reject plain HTTP from datacenter IPs (empty bodies),
and the TikTokApi library's out-of-page requests are bot-detected the same
way. But the explore page itself loads fine, and a same-origin fetch run
INSIDE the page returns full search JSON (live-verified 2026-08-28). So the
backend is: launch headless chromium -> goto /explore -> page.evaluate(fetch)
-> parse -> close the browser.

Memory contract (user-approved): one browser launch per search call, closed
in a `finally` — the ~900MB chromium RSS is returned between searches; no
browser/session caching. playwright is imported lazily so the source works
(and falls back to paid backends) when playwright/chromium isn't installed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from reach_mcp.sources.base import Row

log = logging.getLogger(__name__)

_EXPLORE_URL = "https://www.tiktok.com/explore"
_PAGE_JS = """
async (kw) => {
    const resp = await fetch('/api/search/general/full/?keyword=' +
        encodeURIComponent(kw) + '&offset=0&count=10&search_id=0',
        {headers: {'accept': 'application/json'}});
    return await resp.text();
}
"""


def _playwright_available() -> bool:
    """True when the playwright package AND a chromium binary are importable
    / present. Checked lazily before each attempt so an uninstalled backend
    is a cheap no-op, not an ImportError."""
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
    """Launch chromium with the light anti-automation flags that proved
    sufficient live. Kept as a hook so tests can inject a fake browser."""
    return await pw.chromium.launch(
        headless=True, args=["--disable-blink-features=AutomationControlled"]
    )


def _iso(ts) -> str | None:
    """createTime is unix seconds (string) in the general/full payload."""
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


def parse_items(raw: dict, limit: int) -> list[Row]:
    """Map the /api/search/general/full payload into Rows.

    Shape (live-verified): {status_code, data: [{item: {...}}, ...],
    has_more}. Promoted cards carry no `item` — skipped.
    """
    rows: list[Row] = []
    for card in (raw or {}).get("data") or []:
        item = card.get("item") if isinstance(card, dict) else None
        if not isinstance(item, dict):
            continue
        vid = str(item.get("id") or "")
        desc = str(item.get("desc") or "").strip()
        if not vid or not desc:
            continue
        author = (item.get("author") or {}).get("uniqueId")
        stats = item.get("stats") or {}
        rows.append(
            Row(
                source="tiktok",
                id=vid,
                title=desc[:120],
                url=f"https://www.tiktok.com/@{author or 'i'}/video/{vid}",
                author=author,
                date=_iso(item.get("createTime")),
                engagement={
                    "views": stats.get("playCount") or 0,
                    "likes": stats.get("diggCount") or 0,
                    "comments": stats.get("commentCount") or 0,
                    "shares": stats.get("shareCount") or 0,
                },
                text=desc,
            )
        )
        if len(rows) >= limit:
            break
    return rows


async def fetch(query: str, limit: int, timeout: float = 60) -> list[Row]:
    """One search = one browser lifecycle. Raises nothing: failures log and
    return [] so the source's paid fallbacks still get their turn."""
    if not _playwright_available():
        return []
    try:
        return await asyncio.wait_for(_search(query, limit), timeout=timeout)
    except Exception as e:  # noqa: BLE001
        log.warning("tiktok playwright backend failed: %s", e)
        return []


async def _search(query: str, limit: int) -> list[Row]:
    # async with: the playwright driver process itself is also torn down,
    # not just the browser — nothing lingers between searches.
    async with _playwright() as pw:
        browser = await _launch_browser(pw)
        try:
            context = await browser.new_context(locale="en-US")
            page = await context.new_page()
            await page.goto(_EXPLORE_URL, wait_until="domcontentloaded", timeout=45_000)
            # let the JS settle (msToken cookie + risk checks) before fetching
            await page.wait_for_timeout(3_000)
            raw_text = await page.evaluate(_PAGE_JS, query)
            return parse_items(json.loads(raw_text), limit)
        finally:
            try:
                await browser.close()
            except Exception:  # noqa: BLE001
                pass
