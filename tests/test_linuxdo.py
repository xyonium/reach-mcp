"""linux.do (Discourse) source tests — playwright + seeded-cookie backend.

linux.do sits behind Cloudflare that 403s plain HTTP AND cookie-carrying curl
from datacenter IPs (verified 2026-08-28); the only path that passes is a
headless chromium with the LINUXDO_COOKIE pairs seeded into the browser
context, then same-origin navigation to the Discourse JSON endpoints
(latest.json / top.json / search.json). Live-verified: 30 latest topics,
50 search hits.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import reach_mcp.sources._linuxdo_playwright as lp
from reach_mcp.sources import get_source


def _topic(tid=2782702, title="claude如何破啊", slug="claude-ru-he-po",
           posts=12, likes=34, views=567, created="2026-08-25T08:00:00.000Z",
           username="neo"):
    return {
        "id": tid,
        "title": title,
        "slug": slug,
        "posts_count": posts,
        "like_count": likes,
        "views": views,
        "created_at": created,
        "last_poster_username": username,
    }


def test_parse_topics_maps_rows():
    rows = lp.parse_topics([_topic()], 10)
    assert len(rows) == 1
    r = rows[0]
    assert r.source == "linuxdo"
    assert r.id == "2782702"
    assert r.title == "claude如何破啊"
    assert r.url == "https://linux.do/t/claude-ru-he-po/2782702"
    assert r.author == "neo"
    assert r.date and r.date.startswith("2026-08-25")
    assert r.engagement["posts"] == 12
    assert r.engagement["likes"] == 34
    assert r.engagement["views"] == 567


def test_parse_topics_skips_garbage_and_limits():
    rows = lp.parse_topics([{"id": 1}, _topic(), _topic(tid=9, title="x")], 1)
    assert len(rows) == 1


class _FakePage:
    def __init__(self, bodies):
        self._bodies = list(bodies)

    async def goto(self, url, **kw):
        self.url = url

    async def wait_for_timeout(self, *a, **kw):
        pass

    async def evaluate(self, *a, **kw):
        return self._bodies.pop(0) if self._bodies else "{}"


class _FakeBrowser:
    def __init__(self, bodies):
        self.closed = 0
        self._page = _FakePage(bodies)
        self.cookies_seeded = None

    async def new_context(self, **kw):
        return self

    async def add_cookies(self, cookies):
        self.cookies_seeded = cookies

    async def new_page(self):
        return self._page

    async def close(self):
        self.closed += 1


class _PW:
    def __init__(self, browser):
        self._b = browser

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass


def _patch(monkeypatch, browser):
    monkeypatch.setattr(lp, "_playwright_available", lambda: True)
    monkeypatch.setattr(lp, "_playwright", lambda: _PW(browser))
    monkeypatch.setattr(lp, "_launch_browser", AsyncMock(return_value=browser))


@pytest.mark.asyncio
async def test_fetch_latest_seeds_cookies_and_closes(monkeypatch):
    import json as _json

    body = _json.dumps({"topic_list": {"topics": [_topic()]}})
    browser = _FakeBrowser([body])
    _patch(monkeypatch, browser)
    rows = await lp.fetch_endpoint("https://linux.do/latest.json", "x=1; y=2", 10)
    assert len(rows) == 1
    assert browser.closed == 1
    # cookies were seeded into the context before navigation
    names = {c["name"] for c in (browser.cookies_seeded or [])}
    assert names == {"x", "y"}


@pytest.mark.asyncio
async def test_fetch_endpoint_closes_browser_on_goto_failure(monkeypatch):
    class _Boom(_FakeBrowser):
        async def new_page(self):
            raise RuntimeError("renderer dead")

    browser = _Boom([])
    _patch(monkeypatch, browser)
    rows = await lp.fetch_endpoint("https://linux.do/latest.json", "c", 10)
    assert rows == []
    assert browser.closed == 1


@pytest.mark.asyncio
async def test_fetch_endpoint_empty_when_playwright_absent(monkeypatch):
    monkeypatch.setattr(lp, "_playwright_available", lambda: False)
    assert await lp.fetch_endpoint("https://linux.do/latest.json", "c", 10) == []


@pytest.mark.asyncio
async def test_linuxdo_source_gated_without_cookie(monkeypatch):
    monkeypatch.delenv("LINUXDO_COOKIE", raising=False)
    assert not get_source("linuxdo").available()


@pytest.mark.asyncio
async def test_linuxdo_source_search_and_trending(monkeypatch):
    import json as _json

    monkeypatch.setenv("LINUXDO_COOKIE", "_t=abc; _forum_session=def")
    # CI has no playwright installed — available() gates on it, so patch it in
    monkeypatch.setattr(lp, "_playwright_available", lambda: True)
    search_body = _json.dumps({"topics": [_topic()]})
    latest_body = _json.dumps({"topic_list": {"topics": [_topic(tid=5, title="hot")]}})

    async def fake_endpoint(url, cookie, limit):
        if "search" in url:
            return lp.parse_topics(_json.loads(search_body)["topics"], limit)
        return lp.parse_topics(_json.loads(latest_body)["topic_list"]["topics"], limit)

    monkeypatch.setattr("reach_mcp.sources.linuxdo._pw_fetch_endpoint", fake_endpoint)
    src = get_source("linuxdo")
    assert src.available()
    assert src.supports_trending is True

    rows = await src.fetch("claude", 30, 10)
    assert len(rows) == 1 and rows[0].id == "2782702"

    hot = await src.fetch_trending(10)
    assert len(hot) == 1 and hot[0].title == "hot"
