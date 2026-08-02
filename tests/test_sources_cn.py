from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from reach_mcp.sources import get_source
from reach_mcp.sources.base import Row, set_client


@pytest.mark.asyncio
async def test_v2ex_parses_topics():
    c = AsyncMock()
    c.get_json = AsyncMock(return_value=[{
        "id": 1, "title": "Python tips", "url": "https://v2ex.com/t/1",
        "member": {"username": "u"}, "created": 1751328000, "replies": 3,
    }])
    set_client(c)
    rows = await get_source("v2ex").fetch("python", 30, 10)
    assert rows and rows[0].title == "Python tips" and rows[0].engagement["replies"] == 3


@pytest.mark.asyncio
async def test_xueqiu_api_primary_without_cli(monkeypatch):
    """Without OpenCLI and without cookie, xueqiu uses the public suggest API."""
    monkeypatch.setattr("reach_mcp.sources.xueqiu._has_cli", lambda: False)
    monkeypatch.delenv("XUEQIU_COOKIE", raising=False)
    monkeypatch.setattr(
        "reach_mcp.sources.xueqiu._fetch_via_api",
        AsyncMock(return_value=[Row(source="xueqiu", id="AAPL", title="Apple Inc.",
                                    url="https://xueqiu.com/S/AAPL",
                                    author=None, date=None, engagement={}, text="")]),
    )
    rows = await get_source("xueqiu").fetch("AAPL", 30, 10)
    assert rows and rows[0].title == "Apple Inc."
    assert "AAPL" in rows[0].url


@pytest.mark.asyncio
async def test_xueqiu_merges_opencli_boost(monkeypatch):
    """With OpenCLI installed, its extra hits are merged onto the API results."""
    monkeypatch.setattr("reach_mcp.sources.xueqiu._has_cli", lambda: True)
    monkeypatch.delenv("XUEQIU_COOKIE", raising=False)
    monkeypatch.setattr(
        "reach_mcp.sources.xueqiu._fetch_via_cli",
        AsyncMock(return_value=[Row(source="xueqiu", id="TSLA", title="Tesla",
                                    url="https://xueqiu.com/S/TSLA",
                                    author=None, date=None, engagement={}, text="")]),
    )
    monkeypatch.setattr(
        "reach_mcp.sources.xueqiu._fetch_via_api",
        AsyncMock(return_value=[Row(source="xueqiu", id="AAPL", title="Apple",
                                    url="https://xueqiu.com/S/AAPL",
                                    author=None, date=None, engagement={}, text="")]),
    )
    rows = await get_source("xueqiu").fetch("stock", 30, 10)
    titles = [r.title for r in rows]
    assert "Apple" in titles and "Tesla" in titles  # API + OpenCLI merged


@pytest.mark.asyncio
async def test_bilibili_uses_search_api(monkeypatch):
    monkeypatch.setattr("reach_mcp.sources.bilibili._has_cli", lambda: False)
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
async def test_youtube_shells_to_ytdlp(monkeypatch):
    async def fake_search(query, limit):
        return [{"id": "yt1", "title": query, "url": "https://youtu.be/1",
                 "text": "transcript", "date": None, "engagement": {}}]
    monkeypatch.setattr("reach_mcp.sources.youtube._search_videos", fake_search)
    rows = await get_source("youtube").fetch("rust", 30, 5)
    assert rows and rows[0].text == "transcript"


@pytest.mark.asyncio
async def test_youtube_search_cmd_argv0_is_ytdlp(monkeypatch, tmp_path):
    """The search command must start with `yt-dlp`, not the cookies flag.

    Regression: _ytdlp_common_args returns ONLY the extra args; prepending them
    without also expanding _YTDLP_BASE made argv[0] = '--cookies', which
    FileNotFoundError'd in the container.
    """

    import reach_mcp.sources.youtube as yt

    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    monkeypatch.setenv("YTDLP_COOKIES", str(cookies))
    monkeypatch.delenv("YTDLP_PROXY", raising=False)

    captured = []

    class _FakeProc:
        async def communicate(self):
            return (b"", b"")

    async def fake_exec(*args, **kwargs):
        captured.append(args)
        return _FakeProc()

    monkeypatch.setattr(yt.asyncio, "create_subprocess_exec", fake_exec)
    await yt._search_videos("test", 3)
    assert captured, "expected a subprocess call"
    argv = captured[0]  # args IS the argv list: (yt-dlp, --cookies, ...)
    assert argv[0] == "yt-dlp"
    assert "--flat-playlist" in argv
    assert "--cookies" in argv
