from __future__ import annotations

import pytest

from reach_mcp.config import Settings
from reach_mcp.tools import _item_to_dict, _source_report_to_dict


def test_item_to_dict():
    from reach_mcp.sources.base import Item
    d = _item_to_dict(Item(source="s", id="1", title="t", url="https://x",
                           score=0.9, cluster="c1"))
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
