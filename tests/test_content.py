from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from reach_mcp.config import Settings
from reach_mcp.content import fetch_content
from reach_mcp.sources.base import Item
from reach_mcp.tools import _backfill_rich_media


def _settings(**over):
    base = Settings()
    fields = {f.name: getattr(base, f.name) for f in base.__dataclass_fields__.values()}
    fields.update(over)
    return Settings(**fields)


@pytest.mark.asyncio
async def test_fetch_content_xiaoyuzhou_uses_audio_url(monkeypatch):
    monkeypatch.setattr(
        "reach_mcp.sources.xiaoyuzhou.transcribe_audio_url",
        AsyncMock(return_value="full transcript"),
    )
    out = await fetch_content("xiaoyuzhou", "https://media.xyzcdn.net/a.m4a", _settings())
    assert out["ok"] and out["content"] == "full transcript"
    assert out["source"] == "xiaoyuzhou"


@pytest.mark.asyncio
async def test_fetch_content_youtube_extracts_id(monkeypatch):
    seen = {}

    async def fake_transcript(vid):
        seen["vid"] = vid
        return "captions text"

    monkeypatch.setattr("reach_mcp.sources.youtube.fetch_transcript", fake_transcript)
    out = await fetch_content("youtube", "https://www.youtube.com/watch?v=abc123XYZ", _settings())
    assert out["ok"] and out["content"] == "captions text"
    assert seen["vid"] == "abc123XYZ"


@pytest.mark.asyncio
async def test_fetch_content_other_source_falls_back_to_jina(monkeypatch):
    monkeypatch.setattr(
        "reach_mcp.content.jina_read_url",
        AsyncMock(return_value="article body"),
    )
    out = await fetch_content("arxiv", "https://arxiv.org/abs/1234.5678", _settings())
    assert out["ok"] and out["content"] == "article body"


@pytest.mark.asyncio
async def test_fetch_content_failure_returns_not_ok(monkeypatch):
    monkeypatch.setattr(
        "reach_mcp.sources.youtube.fetch_transcript",
        AsyncMock(return_value=""),
    )
    out = await fetch_content("youtube", "abc123", _settings())
    assert not out["ok"] and out["content"] == ""


def _rich_items():
    return [
        Item(
            source="youtube",
            id="y1",
            title="vid",
            url="https://youtu.be/y1",
            engagement={},
            text="desc snippet",
            score=0.9,
        ),
        Item(
            source="xiaoyuzhou",
            id="x1",
            title="pod",
            url="https://xyz.fm/e1",
            engagement={},
            text="shownotes snippet",
            score=0.8,
            audio_url="https://media.xyzcdn.net/e1.m4a",
        ),
        Item(
            source="reddit",
            id="r1",
            title="post",
            url="https://redd.it/r1",
            engagement={},
            text="post body",
            score=0.95,
        ),
    ]


@pytest.mark.asyncio
async def test_backfill_fills_rich_media_skips_others(monkeypatch):
    items = _rich_items()

    async def fake_fetch(source, key, settings):
        return {"source": source, "url": key, "content": f"FULL {source}", "ok": True}

    monkeypatch.setattr("reach_mcp.content.fetch_content", fake_fetch)
    await _backfill_rich_media(items, _settings())

    yt = next(i for i in items if i.source == "youtube")
    xy = next(i for i in items if i.source == "xiaoyuzhou")
    rd = next(i for i in items if i.source == "reddit")
    assert yt.text == "FULL youtube"
    assert xy.text == "FULL xiaoyuzhou"
    assert rd.text == "post body"  # untouched


@pytest.mark.asyncio
async def test_backfill_keeps_snippet_on_failure(monkeypatch):
    items = _rich_items()

    async def fake_fetch(source, key, settings):
        return {"source": source, "url": key, "content": "", "ok": False}

    monkeypatch.setattr("reach_mcp.content.fetch_content", fake_fetch)
    await _backfill_rich_media(items, _settings())
    yt = next(i for i in items if i.source == "youtube")
    assert yt.text == "desc snippet"  # fallback intact
