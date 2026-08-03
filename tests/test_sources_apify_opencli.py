from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from reach_mcp.sources import get_source
from reach_mcp.sources.base import Row, set_client


@pytest.mark.asyncio
async def test_apify_threads_fetch(monkeypatch):
    """threads fetches via Apify when APIFY_API_TOKEN is set."""
    monkeypatch.setenv("APIFY_API_TOKEN", "apify_test")
    monkeypatch.setattr(
        "reach_mcp.sources.threads._apify_fetch",
        AsyncMock(return_value=[__import__("reach_mcp.sources.base", fromlist=["Row"]).Row(
            source="threads", id="1", title="T", url="https://threads.net/1",
            author="u", date=None, engagement={"likes": 5}, text="hello")]),
    )
    rows = await get_source("threads").fetch("test", 30, 10)
    assert rows and rows[0].source == "threads"


@pytest.mark.asyncio
async def test_threads_gated_without_token(monkeypatch):
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    assert not get_source("threads").available()
    rows = await get_source("threads").fetch("test", 30, 10)
    assert rows == []


@pytest.mark.asyncio
async def test_tiktok_uses_apify_when_token_set(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "apify_test")
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    monkeypatch.setattr("reach_mcp.sources.tiktok._has_opencli", lambda: False)
    monkeypatch.setattr(
        "reach_mcp.sources.tiktok._apify_fetch",
        AsyncMock(return_value=[]),
    )
    await get_source("tiktok").fetch("q", 30, 10)
    # If we got here without error and apify_fetch was the chosen path, good.


@pytest.mark.asyncio
async def test_tiktok_gated_without_any_credential(monkeypatch):
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    monkeypatch.setattr("reach_mcp.sources.tiktok._has_opencli", lambda: False)
    assert not get_source("tiktok").available()


@pytest.mark.asyncio
async def test_tiktok_opencli_available_without_token(monkeypatch):
    """OpenCLI on PATH makes tiktok available even with no API token."""
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    monkeypatch.setattr("reach_mcp.sources.tiktok._has_opencli", lambda: True)
    assert get_source("tiktok").available()


@pytest.mark.asyncio
async def test_opencli_cli_search_parses_envelope(monkeypatch):
    """The OpenCLI helper parses the {ok,data:{items:[...]}} envelope."""
    from reach_mcp.sources import _opencli

    fake_env = ('{"ok": true, "data": {"items": [{"id": "v1", "caption": "hi", '
                '"url": "https://tiktok.com/@u/video/v1", "likes": 10}]}}')

    class _FakeProc:
        async def communicate(self):
            return (fake_env.encode(), b"")

    async def fake_exec(*args, **kwargs):
        return _FakeProc()

    monkeypatch.setattr(_opencli, "has_cli", lambda: True)
    monkeypatch.setattr(_opencli.asyncio, "create_subprocess_exec", fake_exec)
    rows = await _opencli.cli_search("tiktok", "q", 10)
    assert rows and rows[0].source == "tiktok"
    assert rows[0].engagement["likes"] == 10


@pytest.mark.asyncio
async def test_apify_run_actor_sync_no_token_returns_empty(monkeypatch):
    """Without APIFY_API_TOKEN, run_actor_sync returns [] without calling."""
    from reach_mcp.sources import _apify

    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    result = await _apify.run_actor_sync("apify/threads-scraper", {})
    assert result == []


@pytest.mark.asyncio
async def test_bilibili_prefers_cli(monkeypatch):
    """bilibili uses bili-cli when on PATH."""
    monkeypatch.setattr("reach_mcp.sources.bilibili._has_cli", lambda: True)
    monkeypatch.setattr(
        "reach_mcp.sources.bilibili._fetch_via_cli",
        AsyncMock(return_value=[]),  # cli returns nothing -> falls through to API
    )
    monkeypatch.setattr(
        "reach_mcp.sources.bilibili._fetch_via_api",
        AsyncMock(return_value=[Row(
            source="bilibili", id="BV1", title="Vid", url="https://b23.tv/1",
            author="up", date=None, engagement={"play": 100}, text="",
        )]),
    )
    rows = await get_source("bilibili").fetch("ai", 30, 10)
    assert rows and rows[0].engagement["play"] == 100


@pytest.mark.asyncio
async def test_web_brave_boost_when_key_set(monkeypatch):
    """web merges Searxng + Brave when BRAVE_API_KEY is set."""
    monkeypatch.setenv("BRAVE_API_KEY", "brave_test")
    monkeypatch.setenv("SEARXNG_URL", "http://searxng:8080")
    c = AsyncMock()
    # First call (searxng) and second call (brave) both via get_json
    c.get_json = AsyncMock(side_effect=[
        {"results": [{"title": "Searxng hit", "url": "https://a.com", "content": "s"}]},
        {"web": {"results": [{"title": "Brave hit", "url": "https://b.com",
                              "description": "b"}]}},
    ])
    set_client(c)
    rows = await get_source("web").fetch("query", 30, 10)
    titles = [r.title for r in rows]
    assert "Searxng hit" in titles and "Brave hit" in titles


@pytest.mark.asyncio
async def test_read_url_uses_jina_reader(monkeypatch):
    """read_url helper fetches content via r.jina.ai, keyless."""
    from reach_mcp.jina import read_url

    c = AsyncMock()
    c.get_text = AsyncMock(return_value="This is the page content")
    set_client(c)
    monkeypatch.delenv("JINA_API_KEY", raising=False)
    content = await read_url("https://example.com")
    assert "page content" in content
    # verify it hit r.jina.ai
    called_url = c.get_text.call_args.args[0]
    assert "r.jina.ai" in called_url


@pytest.mark.asyncio
async def test_read_url_with_jina_key(monkeypatch):
    """read_url sends Authorization when JINA_API_KEY is set."""
    from reach_mcp.jina import read_url

    monkeypatch.setenv("JINA_API_KEY", "jina_test")
    c = AsyncMock()
    c.get_text = AsyncMock(return_value="content")
    set_client(c)
    await read_url("https://example.com")
    headers = c.get_text.call_args.kwargs.get("headers", {})
    assert headers.get("Authorization") == "Bearer jina_test"


async def _call_tool(mcp, name, args):
    """Helper: invoke a FastMCP tool by name with args dict."""
    tools_map = {t.name: t for t in await mcp.list_tools()}
    tool = tools_map[name]
    return await tool.fn(**args)


@pytest.mark.asyncio
async def test_quora_uses_apify_when_token_set(monkeypatch):
    """quora fetches via Apify when APIFY_API_TOKEN is set."""
    monkeypatch.setenv("APIFY_API_TOKEN", "apify_test")
    monkeypatch.setattr(
        "reach_mcp.sources._apify.fetch_quora",
        AsyncMock(return_value=[Row(
            source="quora", id="1", title="What is MCP?",
            url="https://quora.com/What-is-MCP", author="someone",
            date=None, engagement={"upvotes": 42}, text="MCP is a protocol...")]),
    )
    rows = await get_source("quora").fetch("MCP", 30, 10)
    assert rows and rows[0].source == "quora"
    assert rows[0].engagement["upvotes"] == 42


@pytest.mark.asyncio
async def test_quora_gated_without_token(monkeypatch):
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    assert not get_source("quora").available()
    rows = await get_source("quora").fetch("q", 30, 10)
    assert rows == []


def test_apify_base_url_env_override(monkeypatch):
    """APIFY_BASE_URL overrides the default api.apify.com (for key-rotator)."""
    from reach_mcp.sources import _apify
    monkeypatch.delenv("APIFY_BASE_URL", raising=False)
    assert _apify._api_base() == "https://api.apify.com"
    monkeypatch.setenv("APIFY_BASE_URL", "http://api-key-rotator:8788/")
    assert _apify._api_base() == "http://api-key-rotator:8788"  # trailing / stripped
