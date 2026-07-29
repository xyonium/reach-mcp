from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from reach_mcp.config import Settings
from reach_mcp.http import PoliteClient
from reach_mcp.pipeline import run_search
from reach_mcp.sources import SOURCES
from reach_mcp.sources.base import Row, set_client
from reach_mcp.tools import build_mcp


class _StubSource:
    name = "stub"
    description = "stub"
    host = "stub.test"
    needs_auth = False
    required_env = ()
    default_days = 30
    default_limit = 20

    def available(self):
        return True

    async def fetch(self, query, days, limit):
        return [Row(source="stub", id="1", title=f"stub:{query}", url="https://stub/1",
                    author="a", date="2026-07-01T00:00:00Z",
                    engagement={"upvotes": 5}, text="body")]


@pytest.mark.asyncio
async def test_search_end_to_end(monkeypatch):
    # inject a stub source into the registry
    SOURCES["stub"] = _StubSource()
    try:
        monkeypatch.setattr("reach_mcp.synthesize.rerank",
                            AsyncMock(side_effect=lambda q, i, s: i))
        monkeypatch.setattr("reach_mcp.synthesize.brief", AsyncMock(return_value="BRIEF"))

        mcp = build_mcp(Settings(openai_api_key="sk-x"))
        tools = {t.name: t for t in await mcp.list_tools()}
        assert {"search", "list_sources", "synthesize"} <= set(tools)

        client = PoliteClient(Settings())
        set_client(client)
        items, reports = await run_search("q", ["stub"], 30, 5, client, Settings())
        assert items and items[0].title == "stub:q"
        assert reports[0].status == "ok"
        await client.aclose()
    finally:
        SOURCES.pop("stub", None)


@pytest.mark.asyncio
async def test_list_sources_includes_all_registered():
    mcp = build_mcp(Settings())
    # build_mcp triggers import_all_sources; 23 real sources must be present
    tools = {t.name: t for t in await mcp.list_tools()}
    assert "list_sources" in tools
    # available_sources reflects env; at minimum the registry is populated
    assert "hackernews" in SOURCES
    assert "xueqiu" in SOURCES
    assert len(SOURCES) >= 23
