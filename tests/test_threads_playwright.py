"""Threads playwright backend tests — parse + browser lifecycle contract.

Mirrors tests/test_tiktok_playwright.py: the backend renders threads.net search
in a per-call headless chromium and parses the SSR Relay JSON blob; lifecycle
tests patch _playwright_available AND _playwright so CI (no playwright) still
exercises the browser mock.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import reach_mcp.sources._threads_playwright as tp
from reach_mcp.sources import get_source


def _edge(pk="3653472235508723805", code="DKzvaQqP_Bd", username="ubuntu_os",
          text="How would YOU explain Kubernetes to an 8-year-old?",
          taken_at=1749747851, likes=42, replies=20, reposts=3, quotes=1):
    return {
        "node": {
            "thread": {
                "id": pk,
                "thread_items": [
                    {
                        "post": {
                            "pk": pk,
                            "code": code,
                            "taken_at": taken_at,
                            "like_count": likes,
                            "user": {"username": username},
                            "caption": {"text": text},
                            "text_post_app_info": {
                                "direct_reply_count": replies,
                                "repost_count": reposts,
                                "quote_count": quotes,
                            },
                        }
                    }
                ],
            }
        }
    }


def test_parse_items_maps_edges():
    raw = {"edges": [_edge(), _edge(pk="1", code="abc", username="bob", text="hi")]}
    rows = tp.parse_items(raw, 10)
    assert len(rows) == 2
    r = rows[0]
    assert r.source == "threads"
    assert r.id == "3653472235508723805"
    assert r.url == "https://www.threads.net/@ubuntu_os/post/DKzvaQqP_Bd"
    assert r.author == "ubuntu_os"
    assert "Kubernetes" in r.text
    assert r.date and r.date.startswith("2025-06-12")  # 1749747851 unix
    assert r.engagement["likes"] == 42
    assert r.engagement["replies"] == 20
    assert r.engagement["reposts"] == 3
    assert r.engagement["quotes"] == 1


def test_parse_items_respects_limit_and_skips_garbage():
    raw = {"edges": [_edge(), {"node": {}}, _edge(pk="2", code="x", text="two")]}
    rows = tp.parse_items(raw, 1)
    assert len(rows) == 1


def test_extract_search_results_finds_nested_edges():
    """The Relay blob nests searchResults deep inside ScheduledServerJS
    require-chains — the extractor must walk to it, not assume a path."""
    sr = {"edges": [_edge()]}
    payload = {
        "require": [
            [
                "ScheduledServerJS",
                "handle",
                None,
                [
                    {
                        "__bbox": {
                            "require": [
                                [
                                    "RelayPrefetchedStreamCache",
                                    "next",
                                    [],
                                    ["key", {"__bbox": {"result": {"data": {"searchResults": sr}}}}],
                                ]
                            ]
                        }
                    }
                ],
            ]
        ]
    }
    res = tp.extract_search_results(payload)
    assert res is not None
    assert len(res["edges"]) == 1


def test_extract_search_results_missing_returns_none():
    assert tp.extract_search_results({"require": []}) is None
    assert tp.extract_search_results({}) is None


class _FakePage:
    def __init__(self, html):
        self._html = html

    async def goto(self, *a, **kw):
        pass

    async def wait_for_timeout(self, *a, **kw):
        pass

    async def content(self):
        return self._html


class _FakeBrowser:
    def __init__(self, html):
        self.closed = 0
        self._html = html

    async def new_context(self, **kw):
        return self

    async def new_page(self):
        return _FakePage(self._html)

    async def close(self):
        self.closed += 1


def _html_with_blob(edges):
    import json as _json

    payload = {"data": {"searchResults": {"edges": edges}}}
    blob = _json.dumps(payload)
    return f'<html><script type="application/json">{blob}</script></html>'


@pytest.mark.asyncio
async def test_fetch_closes_browser_once_per_call(monkeypatch):
    html = _html_with_blob([_edge()])
    browser = _FakeBrowser(html)

    class _PW:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

    monkeypatch.setattr(tp, "_playwright_available", lambda: True)
    monkeypatch.setattr(tp, "_playwright", lambda: _PW())
    monkeypatch.setattr(tp, "_launch_browser", AsyncMock(return_value=browser))
    rows = await tp.fetch("kubernetes", 10)
    assert len(rows) == 1
    assert browser.closed == 1  # exactly one close per search call


@pytest.mark.asyncio
async def test_fetch_closes_browser_even_when_content_raises(monkeypatch):
    class _BoomBrowser(_FakeBrowser):
        async def new_page(self):
            raise RuntimeError("renderer crashed")

    browser = _BoomBrowser("")

    class _PW:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

    monkeypatch.setattr(tp, "_playwright_available", lambda: True)
    monkeypatch.setattr(tp, "_playwright", lambda: _PW())
    monkeypatch.setattr(tp, "_launch_browser", AsyncMock(return_value=browser))
    rows = await tp.fetch("kubernetes", 10)
    assert rows == []
    assert browser.closed == 1  # no leak on failure


@pytest.mark.asyncio
async def test_fetch_returns_empty_when_playwright_absent(monkeypatch):
    monkeypatch.setattr(tp, "_playwright_available", lambda: False)
    assert await tp.fetch("kubernetes", 10) == []


@pytest.mark.asyncio
async def test_threads_source_prefers_playwright_then_apify(monkeypatch):
    """Source order: free playwright backend first; Apify only when it
    returns nothing (mirrors the tiktok wiring)."""
    import reach_mcp.sources.threads as th

    monkeypatch.setenv("APIFY_API_TOKEN", "x")
    called = {"apify": 0}

    async def fake_apify(query, limit):
        called["apify"] += 1
        return []

    monkeypatch.setattr(th, "_apify_fetch", fake_apify)
    monkeypatch.setattr(th, "_pw_fetch", AsyncMock(return_value=[_edge_row()]))
    rows = await get_source("threads").fetch("kubernetes", 30, 10)
    assert len(rows) == 1
    assert called["apify"] == 0  # playwright result wins, Apify untouched

    # playwright empty -> Apify fallback engaged
    monkeypatch.setattr(th, "_pw_fetch", AsyncMock(return_value=[]))
    rows = await get_source("threads").fetch("kubernetes", 30, 10)
    assert called["apify"] == 1


def _edge_row():
    from reach_mcp.sources.base import Row

    return Row(source="threads", id="1", title="t", url="https://www.threads.net/@a/post/b")
