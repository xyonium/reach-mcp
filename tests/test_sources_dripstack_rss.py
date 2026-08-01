from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from reach_mcp.sources import get_source
from reach_mcp.sources.base import set_client


@pytest.mark.asyncio
async def test_dripstack_parses_results():
    c = AsyncMock()
    c.get_json = AsyncMock(return_value={"items": [
        {"title": "Tesla Q3 earnings deep dive", "slug": "tsla-q3", "publicationSlug": "ev-insights",
         "subtitle": "Tesla beat estimates on revenue", "publishedAt": "2026-07-15T00:00:00Z",
         "relevanceScore": 0.92},
    ]})
    set_client(c)
    rows = await get_source("dripstack").fetch("tesla earnings", 30, 10)
    assert rows and rows[0].title == "Tesla Q3 earnings deep dive"
    assert rows[0].engagement["relevance"] == 0.92


@pytest.mark.asyncio
async def test_dripstack_always_available(monkeypatch):
    """DripStack is keyless and free - always available."""
    assert get_source("dripstack").available()


@pytest.mark.asyncio
async def test_dripstack_empty_on_error():
    c = AsyncMock()
    c.get_json = AsyncMock(side_effect=Exception("network error"))
    set_client(c)
    rows = await get_source("dripstack").fetch("tesla", 30, 10)
    assert rows == []


@pytest.mark.asyncio
async def test_rss_filters_by_query(monkeypatch):
    monkeypatch.setenv("RSS_FEEDS", "https://blog.example.com/feed")
    rss = '''<rss version="2.0"><channel>
      <item><title>Rust async guide</title><link>https://blog.example.com/rust</link>
      <description>about rust</description>
      <pubDate>Mon, 28 Jul 2026 00:00:00 GMT</pubDate></item>
      <item><title>Recipe blog</title><link>https://blog.example.com/recipe</link>
      <description>cooking</description></item>
      </channel></rss>'''
    c = AsyncMock()
    c.get_text = AsyncMock(return_value=rss)
    set_client(c)
    rows = await get_source("rss").fetch("rust", 30, 10)
    assert len(rows) == 1
    assert "rust" in rows[0].title.lower()


@pytest.mark.asyncio
async def test_rss_gated_without_feeds_env(monkeypatch):
    monkeypatch.delenv("RSS_FEEDS", raising=False)
    assert not get_source("rss").available()
    rows = await get_source("rss").fetch("rust", 30, 10)
    assert rows == []
