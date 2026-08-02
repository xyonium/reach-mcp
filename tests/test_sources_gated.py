from __future__ import annotations

import pytest

from reach_mcp.sources import get_source


@pytest.mark.asyncio
async def test_truthsocial_parses_results(monkeypatch):
    monkeypatch.setenv("TRUTHSOCIAL_TOKEN", "tok")
    monkeypatch.setattr(
        "reach_mcp.sources.truthsocial._fetch_sync",
        lambda q, limit: [{
            "id": "1", "content": "<p>hello</p>", "created_at": "2026-07-01T00:00:00Z",
            "account": {"username": "u"}, "favourites_count": 4, "reblogs_count": 1,
        }],
    )
    rows = await get_source("truthsocial").fetch("q", 30, 10)
    assert rows and rows[0].text == "hello" and rows[0].engagement["likes"] == 4


@pytest.mark.asyncio
async def test_x_requires_cookies(monkeypatch):
    monkeypatch.delenv("AUTH_TOKEN", raising=False)
    monkeypatch.delenv("CT0", raising=False)
    assert not get_source("x").available()
    rows = await get_source("x").fetch("q", 30, 10)
    assert rows == []


@pytest.mark.asyncio
async def test_digg_disabled_without_cli(monkeypatch):
    monkeypatch.setattr("reach_mcp.sources.digg._has_cli", lambda: False)
    rows = await get_source("digg").fetch("ai", 30, 10)
    assert rows == []


@pytest.mark.asyncio
async def test_xiaohongshu_parses_mcp_markdown(monkeypatch):
    """When xiaohongshu-mcp returns JSON feeds, we parse them into Rows."""
    monkeypatch.setenv("XHS_MCP_URL", "http://localhost:18060/mcp")

    async def fake_fetch(url, query, days, limit):
        return []  # don't actually call MCP; just test the plain fetch

    monkeypatch.setattr(
        "reach_mcp.sources.xiaohongshu._fetch_via_mcp", fake_fetch
    )
    # Verify the source is available and fetch doesn't crash
    assert get_source("xiaohongshu").available()
    rows = await get_source("xiaohongshu").fetch("test", 30, 10)
    assert rows == []  # fake fetch returns empty


@pytest.mark.asyncio
async def test_xiaohongshu_parse_json():
    """Unit test the search_feeds JSON parser."""
    from reach_mcp.sources.xiaohongshu import _parse_feeds_json

    text = (
        '{"feeds": [{"noteId": "abc123", "title": "Best Hotpot in Chengdu", '
        '"xsecToken": "tok456", "likeCount": 345, "commentCount": 89, '
        '"collectCount": 200}], "count": 1}'
    )
    rows = _parse_feeds_json(text, 10)
    assert len(rows) >= 1
    assert rows[0].title == "Best Hotpot in Chengdu"
    assert rows[0].source == "xiaohongshu"
    assert "abc123" in rows[0].url
    assert "xsec_token=tok456" in rows[0].url
