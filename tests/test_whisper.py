from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from reach_mcp.config import Settings
from reach_mcp.whisper import transcribe


def _settings(**over):
    base = Settings()
    fields = {f.name: getattr(base, f.name) for f in base.__dataclass_fields__.values()}
    fields.update(over)
    return Settings(**fields)


class _Resp:
    def __init__(self, payload, status=200):
        self.status_code = status
        self._payload = payload
        self.text = str(payload)[:200]

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_transcribe_simple_json(monkeypatch):
    async def fake_post(self, url, *, headers, files):
        return _Resp({"text": "你好世界"})

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    out = await transcribe(b"audio", _settings(whisper_base_url="http://gw/v1"))
    assert out == "你好世界"


@pytest.mark.asyncio
async def test_transcribe_verbose_json_segments(monkeypatch):
    # LocalAI's default response_format=verbose_json has no top-level "text" —
    # the transcript lives in segments[].text. Regression test: before this
    # parsing, every xiaoyuzhou transcription silently returned "".
    async def fake_post(self, url, *, headers, files):
        return _Resp({"segments": [
            {"start": 0, "end": 30, "text": " 第一段"},
            {"start": 30, "end": 60, "text": "第二段 "},
        ]})

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    out = await transcribe(b"audio", _settings(whisper_base_url="http://gw/v1"))
    assert out == "第一段 第二段"


@pytest.mark.asyncio
async def test_transcribe_uses_long_timeout(monkeypatch):
    seen = {}

    class FakeClient:
        def __init__(self, *, timeout):
            seen["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, *, headers, files):
            return _Resp({"text": "ok"})

    monkeypatch.setattr("httpx.AsyncClient", FakeClient)
    out = await transcribe(b"audio", _settings(whisper_base_url="http://gw/v1"))
    assert out == "ok"
    assert seen["timeout"] >= 600  # full podcast episodes take minutes


@pytest.mark.asyncio
async def test_transcribe_failure_returns_empty(monkeypatch):
    async def fake_post(self, url, *, headers, files):
        return _Resp({}, status=500)

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    assert await transcribe(b"audio", _settings(whisper_base_url="http://gw/v1")) == ""
