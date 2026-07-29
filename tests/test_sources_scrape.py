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
async def test_techmeme_parses_items():
    html = '<html><body><div class="item"><a href="https://t/1">AI Headline</a></div></body></html>'
    c = AsyncMock()
    c.get_text = AsyncMock(return_value=html)
    set_client(c)
    rows = await get_source("techmeme").fetch("ai", 30, 10)
    assert rows and "Headline" in rows[0].title
