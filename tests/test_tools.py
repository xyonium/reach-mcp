from __future__ import annotations

import pytest

from reach_mcp.config import Settings
from reach_mcp.tools import _item_to_dict, _source_report_to_dict


def test_item_to_dict():
    from reach_mcp.sources.base import Item

    d = _item_to_dict(Item(source="s", id="1", title="t", url="https://x", score=0.9, cluster="c1"))
    assert d["source"] == "s"
    assert d["score"] == 0.9
    assert d["cluster"] == "c1"


def test_source_report_to_dict():
    from reach_mcp.pipeline import SourceReport

    d = _source_report_to_dict(SourceReport(source="x", status="ok", count=3))
    assert d == {"source": "x", "status": "ok", "count": 3, "error": None}


@pytest.mark.asyncio
async def test_list_sources_tool_shape(monkeypatch):
    from reach_mcp.tools import build_mcp

    mcp = build_mcp(Settings())
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert {"search", "list_sources", "synthesize"} <= names


@pytest.mark.asyncio
async def test_search_tool_trending_mode(monkeypatch):
    """trending=true routes to run_trending and skips the query pipeline."""
    from unittest.mock import AsyncMock

    import reach_mcp.tools as tl

    monkeypatch.setenv("REACH_MCP_TRANSPORT", "stdio")
    from reach_mcp.pipeline import SourceReport
    from reach_mcp.sources.base import Item

    fake_items = [Item(source="weibo", id="h", title="热搜", url="https://m.weibo.cn/s/1")]
    fake_reports = [SourceReport(source="weibo", status="ok", count=1)]

    called = {}

    async def fake_run_trending(sources, max_per_source, client):
        called["sources"] = sources
        return fake_items, fake_reports

    monkeypatch.setattr(tl, "run_trending", fake_run_trending)
    monkeypatch.setattr(
        tl,
        "run_search",
        AsyncMock(side_effect=AssertionError("run_search must not run in trending mode")),
    )

    from reach_mcp.config import Settings as S
    from reach_mcp.tools import build_mcp

    mcp = build_mcp(S())
    result = await mcp.call_tool("search", {"query": "", "trending": True, "synthesize": False})
    data = result[0] if isinstance(result, tuple) else result
    payload = data[0].text if hasattr(data[0], "text") else data
    import json as _json

    out = _json.loads(payload) if isinstance(payload, str) else payload
    assert out["items"][0]["title"] == "热搜"
    assert called["sources"] is None  # None = all trending sources
    assert "NOTICE" not in out["source_summary"]
