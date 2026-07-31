from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from reach_mcp.sources import get_source
from reach_mcp.sources.base import set_client


@pytest.mark.asyncio
async def test_reddit_parses_rss():
    rss = '''<rss version="2.0"><channel><item>
      <title>Reddit thread</title><link>https://reddit.com/r/x/1</link>
      <pubDate>Mon, 01 Jul 2026 00:00:00 GMT</pubDate>
      <description>body</description></item></channel></rss>'''
    c = AsyncMock()
    c.get_text = AsyncMock(return_value=rss)
    set_client(c)
    rows = await get_source("reddit").fetch("python", 30, 10)
    assert rows and rows[0].title == "Reddit thread"


@pytest.mark.asyncio
async def test_web_uses_searxng_json():
    c = AsyncMock()
    c.get_json = AsyncMock(return_value={"results": [
        {"title": "Hit", "url": "https://x", "content": "snippet", "publishedDate": "2026-07-01T00:00:00"}]})
    set_client(c)
    rows = await get_source("web").fetch("query", 30, 10)
    assert rows and rows[0].title == "Hit"


@pytest.mark.asyncio
async def test_linkedin_uses_jina_search(monkeypatch):
    """LinkedIn searches via Jina s.jina.ai when JINA_API_KEY is set."""
    monkeypatch.setenv("JINA_API_KEY", "jina_test_key")
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    c = AsyncMock()
    c.get_json = AsyncMock(return_value={"data": [
        {"title": "AI Product Manager insights", "url": "https://linkedin.com/posts/123",
         "content": "Great post about AI PM", "publishedTime": "2026-07-01T00:00:00Z"},
    ]})
    set_client(c)
    rows = await get_source("linkedin").fetch("AI PM", 30, 10)
    assert rows and rows[0].title == "AI Product Manager insights"
    assert "linkedin.com" in rows[0].url


@pytest.mark.asyncio
async def test_linkedin_available_with_jina_key(monkeypatch):
    """LinkedIn is available when JINA_API_KEY is set (free monthly quota)."""
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    monkeypatch.setenv("JINA_API_KEY", "jina_test_key")
    assert get_source("linkedin").available()


@pytest.mark.asyncio
async def test_linkedin_gated_without_any_key(monkeypatch):
    """LinkedIn is gated off when neither Jina nor SC key is set."""
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    monkeypatch.delenv("JINA_API_KEY", raising=False)
    assert not get_source("linkedin").available()


@pytest.mark.asyncio
async def test_linkedin_returns_empty_without_jina_key(monkeypatch):
    """Without JINA_API_KEY, the Jina search path returns []."""
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    monkeypatch.delenv("JINA_API_KEY", raising=False)
    set_client(AsyncMock())
    rows = await get_source("linkedin").fetch("AI PM", 30, 10)
    assert rows == []


@pytest.mark.asyncio
async def test_techmeme_parses_items():
    html = '<html><body><div class="item"><a href="https://t/1">AI Headline</a></div></body></html>'
    c = AsyncMock()
    c.get_text = AsyncMock(return_value=html)
    set_client(c)
    rows = await get_source("techmeme").fetch("ai", 30, 10)
    assert rows and "Headline" in rows[0].title
