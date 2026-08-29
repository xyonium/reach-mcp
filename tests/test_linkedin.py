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
    urls = {r.url for r in rows}
    assert "https://linkedin.com/posts/apify1" in urls
    assert "https://linkedin.com/posts/exa1" in urls
    exa_row = next(r for r in rows if r.url.endswith("exa1"))
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
    """exa raising (402 quota exhausted) must not kill the Apify rows."""
    monkeypatch.setenv("APIFY_API_TOKEN", "apify_test")
    monkeypatch.setenv("EXA_API_KEY", "k")
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    monkeypatch.setattr(li, "_apify_search",
                        AsyncMock(return_value=[_row("a1", "https://linkedin.com/posts/1")]))
    monkeypatch.setattr(li, "_exa_search",
                        AsyncMock(side_effect=RuntimeError("402 payment required")))
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
