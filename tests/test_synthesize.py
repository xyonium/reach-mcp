from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from reach_mcp.config import Settings
from reach_mcp.sources.base import Item
from reach_mcp.synthesize import _chat_url, brief, rerank


def _items(n):
    return [Item(source="s", id=str(i), title=f"t{i}", url=f"https://x/{i}", text=f"body{i}")
            for i in range(n)]


def _settings(**over):
    base = Settings()
    fields = {f.name: getattr(base, f.name) for f in base.__dataclass_fields__.values()}
    fields.update(over)
    return Settings(**fields)


@pytest.mark.asyncio
async def test_brief_without_key_returns_stub(monkeypatch):
    s = _settings(openai_api_key="")
    out = await brief("q", _items(2), s)
    assert "synthesis disabled" in out.lower() or "no api key" in out.lower()


@pytest.mark.asyncio
async def test_brief_calls_gateway(monkeypatch):
    s = _settings(openai_base_url="https://gw/v1", openai_api_key="sk-x")

    async def fake_post(self, url, *, json, headers):  # noqa: ANN001
        class R:
            status_code = 200
            def json(self_inner):
                return {"choices": [{"message": {"content": "BRIEF [1]"}}]}
            def raise_for_status(self_inner):
                return None
        return R()

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    monkeypatch.setattr("httpx.AsyncClient.aclose", AsyncMock(return_value=None))
    out = await brief("q", _items(2), s)
    assert out == "BRIEF [1]"


def test_chat_url_appends_chat_completions():
    s = _settings(openai_base_url="https://gw.example.com/v1/")
    assert _chat_url(s) == "https://gw.example.com/v1/chat/completions"


@pytest.mark.asyncio
async def test_brief_failure_hint_flags_missing_v1(monkeypatch):
    # brief must never raise — it returns a hint string and leaves items
    # untouched. When the base URL lacks /v1 the hint should say so.
    s = _settings(openai_base_url="https://gateway.example.com", openai_api_key="sk-x")

    async def fake_post(self, url, *, json, headers):  # noqa: ANN001
        import httpx
        req = httpx.Request("POST", url)
        resp = httpx.Response(404, request=req)
        raise httpx.HTTPStatusError("404", request=req, response=resp)

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    out = await brief("q", _items(2), s)
    assert out.startswith("Synthesis failed (HTTPStatusError)")
    assert "version path" in out and "/v1" in out
    assert "unaffected" in out


@pytest.mark.asyncio
async def test_brief_failure_hint_generic_error(monkeypatch):
    s = _settings(openai_base_url="https://gw.example.com/v1", openai_api_key="sk-x")

    async def fake_post(self, url, *, json, headers):  # noqa: ANN001
        raise RuntimeError("connection reset")

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    out = await brief("q", _items(2), s)
    assert out.startswith("Synthesis failed (RuntimeError)")
    assert "version path" not in out  # no bogus hint when base URL is fine
    assert "unaffected" in out


@pytest.mark.asyncio
async def test_rerank_falls_back_on_failure(monkeypatch):
    s = _settings(openai_base_url="https://gw/v1", openai_api_key="sk-x")

    async def fake_post(self, url, *, json, headers):  # noqa: ANN001
        raise RuntimeError("boom")

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    monkeypatch.setattr("httpx.AsyncClient.aclose", AsyncMock(return_value=None))
    items = _items(3)
    out = await rerank("q", items, s)
    assert [i.id for i in out] == [i.id for i in items]  # unchanged order
