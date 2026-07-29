from __future__ import annotations

import pytest

from reach_mcp.sources import available_sources, get_source, list_sources
from reach_mcp.sources.base import Row, Source, register_source


@register_source
class _Free(Source):
    name = "free"
    description = "free test source"
    host = "example.com"

    async def fetch(self, query, days, limit):
        return [Row(source="free", id="1", title=query, url="https://example.com/1",
                    author=None, date=None, engagement={}, text="x")]


@register_source
class _Gated(Source):
    name = "gated"
    description = "gated test source"
    host = "example.com"
    needs_auth = True
    required_env = ("SECRET_TOKEN",)

    async def fetch(self, query, days, limit):
        return []


def test_free_source_registered():
    assert "free" in {s.name for s in list_sources()}


def test_get_source():
    assert get_source("free").name == "free"
    with pytest.raises(KeyError):
        get_source("nope")


def test_gated_available_only_with_env(monkeypatch):
    monkeypatch.delenv("SECRET_TOKEN", raising=False)
    assert not _Gated().available()
    assert "gated" not in available_sources()
    monkeypatch.setenv("SECRET_TOKEN", "abc")
    assert _Gated().available()
    assert "gated" in available_sources()
