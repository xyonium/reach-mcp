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


@pytest.mark.asyncio
async def test_fetch_content_tool_raises_toolerror_on_failure(monkeypatch):
    """Regression: a failed fetch must raise ToolError so MCP sets isError
    (OWUI then shows ✗), not return a 200 body that renders as a green ✓."""
    from mcp.server.fastmcp.exceptions import ToolError

    from reach_mcp.tools import build_mcp

    async def fake_fetch(source, id_or_url, settings):
        return {"source": source, "url": id_or_url, "content": "", "ok": False}

    monkeypatch.setattr("reach_mcp.tools.fetch_content", fake_fetch)
    mcp = build_mcp(Settings())
    tool = mcp._tool_manager.get_tool("fetch_content")
    with pytest.raises(ToolError):
        await tool.run({"source": "web", "id_or_url": "https://example.com/x"})


@pytest.mark.asyncio
async def test_fetch_content_tool_passes_through_on_success(monkeypatch):
    from reach_mcp.tools import build_mcp

    async def fake_fetch(source, id_or_url, settings):
        return {"source": source, "url": id_or_url, "content": "body", "ok": True}

    monkeypatch.setattr("reach_mcp.tools.fetch_content", fake_fetch)
    mcp = build_mcp(Settings())
    tool = mcp._tool_manager.get_tool("fetch_content")
    out = await tool.run({"source": "web", "id_or_url": "https://example.com/x"})
    assert out["ok"] and out["content"] == "body"


def test_searxng_time_range_uses_valid_enum():
    """Regression: searxng only accepts day/week/month/year for time_range;
    the buggy f'{days}d' produced '30d' → 400 Invalid value → silent empty web."""
    from reach_mcp.sources.web import _searxng_params

    assert _searxng_params("q", 1)["time_range"] == "day"
    assert _searxng_params("q", 7)["time_range"] == "week"
    assert _searxng_params("q", 30)["time_range"] == "month"
    assert _searxng_params("q", 31)["time_range"] == "month"
    assert _searxng_params("q", 90)["time_range"] == "year"
    assert _searxng_params("q", 365)["time_range"] == "year"
    assert "time_range" not in _searxng_params("q", 400)   # all-time, omit
    assert "time_range" not in _searxng_params("q", 1800)


def test_synthesize_uses_dedicated_openai_timeout():
    """Regression: LLM brief/rerank shared the 15s page-fetch request_timeout and
    timed out (httpx.ReadTimeout) on slower gateways; it now uses openai_timeout."""
    from reach_mcp.config import Settings

    s = Settings()
    assert s.openai_timeout == 120
    assert s.openai_timeout > s.request_timeout


def test_config_read_timeout_larger_than_request_timeout():
    from reach_mcp.config import Settings

    s = Settings()
    assert s.read_timeout == 90 and s.read_timeout > s.request_timeout
