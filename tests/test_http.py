from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from reach_mcp.config import Settings
from reach_mcp.http import PoliteClient


def _settings(**over):
    base = Settings()
    fields = {f.name: getattr(base, f.name) for f in base.__dataclass_fields__.values()}
    fields.update(over)
    return Settings(**fields)


@pytest.mark.asyncio
async def test_get_json_returns_payload(monkeypatch):
    client = PoliteClient(_settings())
    captured = {}

    async def fake_get(self, url, *, params=None, headers=None):  # noqa: ANN001
        captured["url"] = url
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(client, "_pace", AsyncMock(return_value=None))
    data = await client.get_json("https://api.example.com/x")
    assert data == {"ok": True}
    assert captured["url"] == "https://api.example.com/x"


@pytest.mark.asyncio
async def test_honors_retry_after(monkeypatch):
    client = PoliteClient(_settings(min_host_delay=0.0))
    calls = {"n": 0}

    async def fake_get(self, url, *, params=None, headers=None):  # noqa: ANN001
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                429, headers={"Retry-After": "0"}, request=httpx.Request("GET", url)
            )
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    slept = []
    monkeypatch.setattr(asyncio, "sleep", AsyncMock(side_effect=lambda s: slept.append(s)))
    data = await client.get_json("https://api.example.com/y")
    assert data == {"ok": True}
    assert calls["n"] == 2
    assert 0 in slept  # honored Retry-After: 0


@pytest.mark.asyncio
async def test_gives_up_after_max_retries(monkeypatch):
    client = PoliteClient(_settings(min_host_delay=0.0, max_retries=3))

    async def fake_get(self, url, *, params=None, headers=None):  # noqa: ANN001
        return httpx.Response(503, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock(return_value=None))
    with pytest.raises(httpx.HTTPStatusError):
        await client.get_json("https://api.example.com/z")
