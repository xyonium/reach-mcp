from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from reach_mcp.sources import get_source
from reach_mcp.sources.base import Row, set_client


@pytest.mark.asyncio
async def test_v2ex_parses_topics():
    c = AsyncMock()
    c.get_json = AsyncMock(return_value=[{
        "id": 1, "title": "T", "url": "https://v2ex.com/t/1",
        "member": {"username": "u"}, "created": 1751328000, "replies": 3,
    }])
    set_client(c)
    rows = await get_source("v2ex").fetch("python", 30, 10)
    assert rows and rows[0].title == "T" and rows[0].engagement["replies"] == 3


@pytest.mark.asyncio
async def test_xueqiu_api_primary_without_cli(monkeypatch):
    """Without OpenCLI, xueqiu uses the headless JSON API only."""
    monkeypatch.setattr("reach_mcp.sources.xueqiu._has_cli", lambda: False)
    c = AsyncMock()
    c.get_json = AsyncMock(return_value={"data": {"result": [
        {"symbol": "AAPL", "name": "Apple Inc.", "description": "tech giant"},
    ]}})
    set_client(c)
    rows = await get_source("xueqiu").fetch("AAPL", 30, 10)
    assert rows and rows[0].title == "Apple Inc."
    assert "AAPL" in rows[0].url


@pytest.mark.asyncio
async def test_xueqiu_merges_opencli_boost(monkeypatch):
    """With OpenCLI installed, its extra hits are merged onto the API results."""
    monkeypatch.setattr("reach_mcp.sources.xueqiu._has_cli", lambda: True)
    monkeypatch.setattr(
        "reach_mcp.sources.xueqiu._fetch_via_cli",
        AsyncMock(return_value=[Row(source="xueqiu", id="TSLA", title="Tesla",
                                    url="https://xueqiu.com/S/TSLA",
                                    author=None, date=None, engagement={}, text="")]),
    )
    c = AsyncMock()
    c.get_json = AsyncMock(return_value={"data": {"result": [
        {"symbol": "AAPL", "name": "Apple"},
    ]}})
    set_client(c)
    rows = await get_source("xueqiu").fetch("stock", 30, 10)
    titles = [r.title for r in rows]
    assert "Apple" in titles and "Tesla" in titles  # API + OpenCLI merged


@pytest.mark.asyncio
async def test_bilibili_uses_search_api():
    c = AsyncMock()
    c.get_json = AsyncMock(return_value={"data": {"result": [{
        "bvid": "BV1", "title": "Vid", "pubdate": 1751328000,
        "owner": {"name": "up"}, "play": 100, "arcurl": "https://b23.tv/1",
    }]}})
    set_client(c)
    rows = await get_source("bilibili").fetch("ai", 30, 10)
    assert rows and rows[0].engagement["play"] == 100


@pytest.mark.asyncio
async def test_youtube_shells_to_ytdlp(monkeypatch):
    async def fake_subtitles(query, limit):
        return [{"id": "yt1", "title": query, "url": "https://youtu.be/1",
                 "text": "transcript", "date": None, "engagement": {}}]
    monkeypatch.setattr("reach_mcp.sources.youtube._fetch_subtitles", fake_subtitles)
    rows = await get_source("youtube").fetch("rust", 30, 5)
    assert rows and rows[0].text == "transcript"
