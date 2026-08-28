from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from reach_mcp.sources import get_source
from reach_mcp.sources.base import Row, set_client


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
async def test_linkedin_uses_apify_when_token_set(monkeypatch):
    """LinkedIn searches via Apify when APIFY_API_TOKEN is set."""
    monkeypatch.setenv("APIFY_API_TOKEN", "apify_test")
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    rows_out = [
        Row(source="linkedin", id="1", title="AI PM insights",
            url="https://linkedin.com/posts/123", author="Jane",
            date=None, engagement={"likes": 10}, text="Great post"),
    ]
    monkeypatch.setattr(
        "reach_mcp.sources._apify.fetch_linkedin_posts",
        AsyncMock(return_value=rows_out),
    )
    set_client(AsyncMock())
    rows = await get_source("linkedin").fetch("AI PM", 30, 10)
    assert rows and rows[0].title == "AI PM insights"
    assert "linkedin.com" in rows[0].url


@pytest.mark.asyncio
async def test_linkedin_falls_back_to_searxng_without_apify(monkeypatch):
    """Without an Apify token, LinkedIn uses the Searxng site: fallback."""
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    monkeypatch.setenv("SEARXNG_URL", "http://searxng.test")
    c = AsyncMock()
    c.get_json = AsyncMock(return_value={"results": [
        {"title": "LinkedIn post", "url": "https://linkedin.com/posts/x",
         "content": "post body"},
        {"title": "Other", "url": "https://example.com/", "content": "no"},
    ]})
    set_client(c)
    rows = await get_source("linkedin").fetch("AI PM", 30, 10)
    assert rows and rows[0].title == "LinkedIn post"
    assert all("linkedin.com" in r.url for r in rows)


@pytest.mark.asyncio
async def test_linkedin_available_with_apify_or_searxng(monkeypatch):
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    monkeypatch.setenv("APIFY_API_TOKEN", "apify_test")
    assert get_source("linkedin").available()
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    monkeypatch.setenv("SEARXNG_URL", "http://searxng.test")
    assert get_source("linkedin").available()


@pytest.mark.asyncio
async def test_linkedin_gated_without_any_backend(monkeypatch):
    """LinkedIn is gated off when no Apify token, no SC key, no Searxng."""
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    monkeypatch.delenv("SEARXNG_URL", raising=False)
    assert not get_source("linkedin").available()


@pytest.mark.asyncio
async def test_techmeme_parses_items():
    html = '<html><body><div class="item"><a href="https://t/1">AI Headline</a></div></body></html>'
    c = AsyncMock()
    c.get_text = AsyncMock(return_value=html)
    set_client(c)
    rows = await get_source("techmeme").fetch("ai", 30, 10)
    assert rows and "Headline" in rows[0].title


@pytest.mark.asyncio
@pytest.mark.parametrize("query", [
    "人工智能 公众号",
    "微信公众号 人工智能",
    "微信文章 AI",
    "AI weixin article",
])
async def test_web_wechat_intent_scopes_to_mp(query):
    """WeChat-intent queries get site:mp.weixin.qq.com scoping on Searxng."""
    c = AsyncMock()
    c.get_json = AsyncMock(return_value={"results": [
        {"title": "t", "url": "https://mp.weixin.qq.com/s/abc", "content": "c"}]})
    set_client(c)
    await get_source("web").fetch(query, 30, 10)
    q = c.get_json.call_args.kwargs.get("params", {}).get("q", "")
    assert "site:mp.weixin.qq.com" in q, f"intent query {query!r} not scoped"


@pytest.mark.asyncio
async def test_web_non_wechat_query_untouched():
    c = AsyncMock()
    c.get_json = AsyncMock(return_value={"results": []})
    set_client(c)
    await get_source("web").fetch("人工智能 最新进展", 30, 10)
    q = c.get_json.call_args.kwargs.get("params", {}).get("q", "")
    assert "site:" not in q
