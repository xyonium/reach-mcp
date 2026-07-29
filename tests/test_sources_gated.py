from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from reach_mcp.sources import get_source
from reach_mcp.sources.base import set_client


@pytest.mark.asyncio
async def test_truthsocial_parses_results(monkeypatch):
    monkeypatch.setenv("TRUTHSOCIAL_TOKEN", "tok")
    c = AsyncMock()
    c.get_json = AsyncMock(return_value=[{
        "id": "1", "content": "hello", "created_at": "2026-07-01T00:00:00Z",
        "account": {"username": "u"}, "favourites_count": 4, "reblogs_count": 1,
    }])
    set_client(c)
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
