from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from reach_mcp.config import Settings
from reach_mcp.sources.base import Item
from reach_mcp.synthesize import brief, rerank


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
