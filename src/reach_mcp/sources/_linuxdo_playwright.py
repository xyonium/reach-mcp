"""linux.do (Discourse) via headless chromium with a seeded login cookie.

linux.do is behind Cloudflare: plain HTTP 403s, and even curl WITH the login
cookie gets the JS challenge from a datacenter IP (verified 2026-08-28). The
path that passes is a headless chromium with the LINUXDO_COOKIE pairs seeded
into the browser context — the challenge clears and same-origin navigation to
the Discourse JSON endpoints (latest/top/search.json) returns real data.

Memory contract (same as tiktok/threads): one browser per call, closed in a
finally; playwright imported lazily so the source degrades to unavailable when
playwright/chromium isn't installed. Requires LINUXDO_COOKIE (the browser
Cookie string with _t + _forum_session + cf_clearance).
"""

from __future__ import annotations

import asyncio
import json
import logging

from reach_mcp.sources.base import Row

log = logging.getLogger(__name__)

_BASE = "https://linux.do"


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


def parse_topics(topics: list, limit: int) -> list[Row]:
    """Map Discourse topic dicts into Rows (shared by latest/top/search)."""
    rows: list[Row] = []
    for t in topics or []:
        tid = t.get("id")
        title = str(t.get("title") or "").strip()
        slug = str(t.get("slug") or "topic")
        if not tid or not title:
            continue
        rows.append(
            Row(
                source="linuxdo",
                id=str(tid),
                title=title,
                url=f"{_BASE}/t/{slug}/{tid}",
                author=t.get("last_poster_username") or None,
                date=str(t.get("created_at") or "") or None,
                engagement={
                    "posts": t.get("posts_count") or 0,
                    "likes": t.get("like_count") or 0,
                    "views": t.get("views") or 0,
                },
                text=str(t.get("excerpt") or title),
            )
        )
        if len(rows) >= limit:
            break
    return rows


def _cookie_pairs(cookie_str: str) -> list[dict]:
    out = []
    for pair in (cookie_str or "").split(";"):
        pair = pair.strip()
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        out.append({"name": k.strip(), "value": v, "domain": ".linux.do", "path": "/"})
    return out


async def fetch_endpoint(url: str, cookie_str: str, limit: int, timeout: float = 60) -> list[Row]:
    """Open one Discourse JSON endpoint in a cookie-seeded browser and parse
    its topic list. Raises nothing: failures log and return []."""
    if not _playwright_available() or not cookie_str.strip():
        return []
    try:
        return await asyncio.wait_for(_fetch(url, cookie_str, limit), timeout=timeout)
    except Exception as e:  # noqa: BLE001
        log.warning("linux.do playwright fetch failed for %s: %s", url, e)
        return []


async def _fetch(url: str, cookie_str: str, limit: int) -> list[Row]:
    async with _playwright() as pw:
        browser = await _launch_browser(pw)
        try:
            context = await browser.new_context(
                locale="zh-CN",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                ),
            )
            await context.add_cookies(_cookie_pairs(cookie_str))
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            # Cloudflare challenge resolves during this settle window
            await page.wait_for_timeout(5_000)
            body = await page.evaluate("() => document.body.innerText")
            data = json.loads(body)
            # latest/top: topic_list.topics; search.json: topics at top level
            topics = (data.get("topic_list") or {}).get("topics") or data.get("topics") or []
            return parse_topics(topics, limit)
        finally:
            try:
                await browser.close()
            except Exception:  # noqa: BLE001
                pass
