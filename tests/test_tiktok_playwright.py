"""TikTok playwright backend tests.

The playwright backend launches a headless chromium PER CALL and closes it in
a finally block — the ~1GB browser RSS must be returned between searches
(user-approved design). Tests cover: item parsing, the launch/close lifecycle
contract, graceful absence (playwright not installed -> no rows, no crash),
and backend priority (free playwright before paid Apify).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from reach_mcp.sources import get_source
from reach_mcp.sources._tiktok_playwright import fetch as pw_fetch
from reach_mcp.sources._tiktok_playwright import parse_items

# A realistic in-page fetch response (verified live 2026-08-28): top-level
# {status_code, data: [items], has_more}; each item carries an `item` dict.
_RAW = {
    "status_code": 0,
    "data": [
        {
            "item": {
                "id": "7311",
                "desc": "Starship booster static fire 🚀",
                "author": {"uniqueId": "dailyspacetime"},
                "stats": {"playCount": 15400, "diggCount": 1200, "commentCount": 45},
                "createTime": "1756200000",
            }
        },
        # promoted/non-video cards have no inner item
        {"aweme_info": None},
        {
            "item": {
                "id": "7312",
                "desc": "",
                "author": {"uniqueId": "launchheaven"},
                "stats": {"playCount": 13300},
                "createTime": None,
            }
        },
        {
            "item": {
                "id": "7313",
                "desc": "second video",
                "author": {"uniqueId": "launchheaven"},
                "stats": {"playCount": 13300},
                "createTime": None,
            }
        },
    ],
    "has_more": True,
}


def test_parse_items_maps_fields():
    rows = parse_items(_RAW, 10)
    assert len(rows) == 2  # empty-desc and no-item cards skipped
    r = rows[0]
    assert r.source == "tiktok"
    assert r.id == "7311"
    assert "static fire" in r.title
    assert r.url == "https://www.tiktok.com/@dailyspacetime/video/7311"
    assert r.author == "dailyspacetime"
    assert r.engagement["views"] == 15400
    assert r.engagement["likes"] == 1200
    assert r.engagement["comments"] == 45
    expected = datetime.fromtimestamp(1756200000, tz=timezone.utc).isoformat()
    assert r.date == expected


def test_parse_items_respects_limit():
    rows = parse_items(_RAW, 1)
    assert len(rows) == 1


def test_parse_items_handles_none_and_empty():
    assert parse_items({}, 10) == []
    assert parse_items({"data": None}, 10) == []
    assert parse_items({"data": [{"item": None}, "junk"]}, 10) == []


@pytest.mark.asyncio
async def test_fetch_launches_and_closes_browser_per_call():
    """Memory contract: the browser is launched fresh and closed exactly once
    in the same call — even when parsing raises. No browser reuse."""
    closed = []
    page = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.evaluate = AsyncMock(return_value=json.dumps(_RAW))
    context = AsyncMock()
    context.new_page = AsyncMock(return_value=page)
    browser = AsyncMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock(side_effect=lambda: closed.append(True))

    pw = AsyncMock()
    pw.chromium.launch = AsyncMock(return_value=browser)

    with (
        patch(
            "reach_mcp.sources._tiktok_playwright._playwright_available",
            lambda: True,
        ),
        patch("reach_mcp.sources._tiktok_playwright._playwright", lambda: pw),
        patch(
            "reach_mcp.sources._tiktok_playwright._launch_browser",
            AsyncMock(return_value=browser),
        ),
    ):
        rows = await pw_fetch("rocket launch", 10)

    assert len(rows) == 2
    assert closed == [True], "browser must be closed exactly once per search"
    browser.new_context.assert_called_once()  # no session reuse


@pytest.mark.asyncio
async def test_fetch_closes_browser_even_when_evaluate_raises():
    """A mid-search failure must still return the browser's memory."""
    closed = []
    page = AsyncMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.evaluate = AsyncMock(side_effect=RuntimeError("page crashed"))
    context = AsyncMock()
    context.new_page = AsyncMock(return_value=page)
    browser = AsyncMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock(side_effect=lambda: closed.append(True))

    with (
        patch(
            "reach_mcp.sources._tiktok_playwright._playwright_available",
            lambda: True,
        ),
        patch("reach_mcp.sources._tiktok_playwright._playwright", lambda: AsyncMock()),
        patch(
            "reach_mcp.sources._tiktok_playwright._launch_browser",
            AsyncMock(return_value=browser),
        ),
    ):
        rows = await pw_fetch("q", 10)

    assert rows == []
    assert closed == [True], "browser closed even after a crash"


@pytest.mark.asyncio
async def test_fetch_returns_empty_when_playwright_missing():
    """playwright/chromium not installed -> [] and no exception, so the
    source's paid fallbacks still get their turn."""
    with patch(
        "reach_mcp.sources._tiktok_playwright._playwright_available",
        lambda: False,
    ):
        rows = await pw_fetch("q", 10)
    assert rows == []


@pytest.mark.asyncio
async def test_tiktok_backend_order_playwright_before_apify(monkeypatch):
    """playwright is free/unlimited — it must be tried BEFORE Apify."""
    order = []
    monkeypatch.setenv("APIFY_API_TOKEN", "tok")

    async def pw_ok(query, limit):
        order.append("playwright")
        return ["row"]

    async def apify_never(query, limit):
        order.append("apify")
        return []

    monkeypatch.setattr("reach_mcp.sources.tiktok._pw_fetch", pw_ok)
    monkeypatch.setattr("reach_mcp.sources._apify.fetch_tiktok", apify_never)
    rows = await get_source("tiktok").fetch("q", 30, 10)
    assert order == ["playwright"]  # apify never reached
    assert rows == ["row"]


@pytest.mark.asyncio
async def test_tiktok_falls_through_to_apify_when_playwright_empty(monkeypatch):
    """playwright returning [] (uninstalled or blocked) falls through to the
    paid Apify backend instead of ending the search."""
    from reach_mcp.sources.base import set_client

    order = []
    monkeypatch.setenv("APIFY_API_TOKEN", "tok")

    async def pw_empty(query, limit):
        order.append("playwright")
        return []

    async def apify_ok(query, limit):
        order.append("apify")
        return ["row"]

    monkeypatch.setattr("reach_mcp.sources.tiktok._pw_fetch", pw_empty)
    # patch where tiktok.py looks it up (imported into the module namespace)
    monkeypatch.setattr("reach_mcp.sources.tiktok._apify_fetch", apify_ok)
    set_client(AsyncMock())  # later fallback branches touch get_client()
    rows = await get_source("tiktok").fetch("q", 30, 10)
    assert order == ["playwright", "apify"]
    assert rows == ["row"]
