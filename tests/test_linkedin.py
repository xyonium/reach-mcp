"""LinkedIn exa-dates tests: exa discovery merges in, bringing publishedDate.

exa's includeDomains:linkedin.com + highlights returns posts WITH fresh
publishedDate (verified 2026-08-29) — the first date-carrying LinkedIn
discovery path (Apify often lacks dates). It runs as a parallel discovery task
and merges by URL; exa rows win on date presence.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import reach_mcp.sources.linkedin as li
from reach_mcp.sources import get_source
from reach_mcp.sources.base import Row


def _row(rid, url, date=None, text=""):
    return Row(
        source="linkedin",
        id=rid,
        title=f"t-{rid}",
        url=url,
        author=None,
        date=date,
        engagement={},
        text=text,
    )


@pytest.mark.asyncio
async def test_linkedin_prefers_exa_over_apify(monkeypatch):
    """exa is PRIMARY for linkedin (fresh dates + body opening beat Apify's
    often-undated rows); Apify only fills when exa returns nothing."""
    monkeypatch.setenv("APIFY_API_TOKEN", "apify_test")
    monkeypatch.setenv("EXA_API_KEY", "k")
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    apify_called = {"n": 0}

    async def fake_apify(query, limit):
        apify_called["n"] += 1
        return [_row("a1", "https://linkedin.com/posts/apify1")]

    monkeypatch.setattr(li, "_apify_search", fake_apify)
    monkeypatch.setattr(
        li, "_exa_search",
        AsyncMock(return_value=[_row("e1", "https://linkedin.com/posts/exa1",
                                     date="2026-06-28T00:00:00.000Z")]),
    )
    rows = await get_source("linkedin").fetch("kubernetes", 30, 10)
    assert apify_called["n"] == 0  # exa hit -> Apify untouched
    assert len(rows) == 1
    assert rows[0].url.endswith("exa1")


@pytest.mark.asyncio
async def test_linkedin_falls_back_to_apify_when_exa_empty(monkeypatch):
    """exa set but returns nothing (quota/block) -> Apify takes over."""
    monkeypatch.setenv("APIFY_API_TOKEN", "apify_test")
    monkeypatch.setenv("EXA_API_KEY", "k")
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    monkeypatch.setattr(li, "_exa_search", AsyncMock(return_value=[]))
    monkeypatch.setattr(li, "_apify_search",
                        AsyncMock(return_value=[_row("a1", "https://linkedin.com/posts/apify1")]))
    rows = await get_source("linkedin").fetch("kubernetes", 30, 10)
    assert len(rows) == 1
    assert rows[0].url.endswith("apify1")


@pytest.mark.asyncio
async def test_linkedin_exa_merges_and_brings_dates(monkeypatch):
    """With EXA_API_KEY set, exa runs as a discovery task and its dated rows
    appear alongside Apify's."""
    monkeypatch.setenv("APIFY_API_TOKEN", "apify_test")
    monkeypatch.setenv("EXA_API_KEY", "k")
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    monkeypatch.setattr(
        li, "_apify_search",
        AsyncMock(return_value=[_row("a1", "https://linkedin.com/posts/apify1")]),
    )
    monkeypatch.setattr(
        li, "_exa_search",
        AsyncMock(return_value=[_row("e1", "https://linkedin.com/posts/exa1",
                                     date="2026-06-28T00:00:00.000Z",
                                     text="post body opening from exa highlight")]),
    )
    rows = await get_source("linkedin").fetch("kubernetes", 30, 10)
    # exa is primary: its dated row wins; Apify is NOT merged in on an exa hit
    assert len(rows) == 1
    exa_row = rows[0]
    assert exa_row.url.endswith("exa1")
    assert exa_row.date and exa_row.date.startswith("2026-06-28")


@pytest.mark.asyncio
async def test_linkedin_exa_not_called_without_key(monkeypatch):
    """No EXA_API_KEY -> exa task skipped entirely."""
    monkeypatch.setenv("APIFY_API_TOKEN", "apify_test")
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    called = {"n": 0}

    async def fake_exa(*a, **kw):
        called["n"] += 1
        return []

    monkeypatch.setattr(li, "_exa_search", fake_exa)
    monkeypatch.setattr(li, "_apify_search", AsyncMock(return_value=[_row("a1", "https://linkedin.com/posts/1")]))
    rows = await get_source("linkedin").fetch("kubernetes", 30, 10)
    assert called["n"] == 0
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_linkedin_exa_failure_doesnt_break_apify(monkeypatch):
    """exa exhausted (402) returns [] at the backend layer -> Apify fallback
    still delivers rows. The _exa backend swallows its own errors, so the
    ladder sees empty, not an exception."""
    monkeypatch.setenv("APIFY_API_TOKEN", "apify_test")
    monkeypatch.setenv("EXA_API_KEY", "k")
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    monkeypatch.setattr(li, "_apify_search",
                        AsyncMock(return_value=[_row("a1", "https://linkedin.com/posts/1")]))
    # _exa backend returns [] on failure (402 quota), it doesn't raise
    monkeypatch.setattr(li, "_exa_search", AsyncMock(return_value=[]))
    rows = await get_source("linkedin").fetch("kubernetes", 30, 10)
    assert len(rows) == 1
    assert rows[0].url.endswith("posts/1")


@pytest.mark.asyncio
async def test_linkedin_available_with_exa_alone(monkeypatch):
    """EXA_API_KEY alone makes linkedin available (free discovery path)."""
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    monkeypatch.delenv("SEARXNG_URL", raising=False)
    monkeypatch.setenv("EXA_API_KEY", "k")
    assert get_source("linkedin").available()
