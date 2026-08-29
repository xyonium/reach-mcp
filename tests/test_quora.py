"""Quora source backend-order tests: Searxng site: free primary, Apify fallback.

Quora's own endpoints are Cloudflare-walled from datacenter IPs (playwright
challenge never clears, verified 2026-08-28); Searxng with a site:quora.com
scope returns real question pages without any credential.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import reach_mcp.sources.quora as q
from reach_mcp.sources import get_source
from reach_mcp.sources.base import set_client


def _searxng_payload():
    return {
        "results": [
            {
                "url": "https://www.quora.com/How-does-Kubernetes-work",
                "title": "How does Kubernetes work, and what is its functionality? - Quora",
                "content": "Kubernetes is an open-source container orchestration...",
                "publishedDate": "2025-11-02T00:00:00",
            },
            {
                "url": "https://www.quora.com/What-are-Kubernetes-clusters",
                "title": "What are the advantages of Kubernetes clusters? - Quora",
                "content": "Clusters give you...",
                "publishedDate": None,
            },
        ]
    }


@pytest.mark.asyncio
async def test_quora_prefers_exa_when_key_set(monkeypatch):
    """Backend order: exa (answer-rich highlights + dates) first; Searxng only
    when exa is unset/empty."""
    monkeypatch.setenv("EXA_API_KEY", "k")
    monkeypatch.setenv("SEARXNG_URL", "http://searxng:8080")
    from reach_mcp.sources.base import Row

    async def fake_exa(query, domain, source, limit, days=0):
        assert domain == "quora.com" and source == "quora"
        return [
            Row(
                source="quora",
                id="e1",
                title="exa quora hit",
                url="https://www.quora.com/exa",
                date="2022-08-29T00:00:00.000Z",
                text="answer highlight from exa",
            )
        ]

    monkeypatch.setattr(q, "_exa_search", fake_exa)
    # searxng must NOT be consulted when exa returns rows
    c = AsyncMock()
    c.get_json = AsyncMock(side_effect=AssertionError("searxng must not run"))
    set_client(c)
    rows = await get_source("quora").fetch("kubernetes", 30, 10)
    assert len(rows) == 1
    assert rows[0].id == "e1"
    assert "answer highlight" in rows[0].text


@pytest.mark.asyncio
async def test_quora_falls_through_exa_to_searxng(monkeypatch):
    """exa set but returns nothing -> Searxng takes over."""
    monkeypatch.setenv("EXA_API_KEY", "k")
    monkeypatch.setenv("SEARXNG_URL", "http://searxng:8080")
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    monkeypatch.setattr(q, "_exa_search", AsyncMock(return_value=[]))
    c = AsyncMock()
    c.get_json = AsyncMock(return_value=_searxng_payload())
    set_client(c)
    rows = await get_source("quora").fetch("kubernetes", 30, 10)
    assert len(rows) == 2  # searxng results


@pytest.mark.asyncio
async def test_quora_searxng_primary_parses(monkeypatch):
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    monkeypatch.setenv("SEARXNG_URL", "http://searxng:8080")
    c = AsyncMock()
    c.get_json = AsyncMock(return_value=_searxng_payload())
    set_client(c)
    rows = await get_source("quora").fetch("kubernetes", 30, 10)
    assert len(rows) == 2
    r = rows[0]
    assert r.source == "quora"
    assert "Kubernetes" in r.title
    assert r.url.startswith("https://www.quora.com/")
    assert r.text.startswith("Kubernetes is an open-source")
    # the query must be site-scoped
    params = c.get_json.call_args.kwargs["params"]
    assert "site:quora.com" in params["q"]


@pytest.mark.asyncio
async def test_quora_available_with_searxng_alone(monkeypatch):
    """No APIFY_API_TOKEN but Searxng present -> still available (free path)."""
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    monkeypatch.setenv("SEARXNG_URL", "http://searxng:8080")
    assert get_source("quora").available()


@pytest.mark.asyncio
async def test_quora_falls_back_to_apify_when_searxng_empty(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "tok")
    monkeypatch.setenv("SEARXNG_URL", "http://searxng:8080")
    c = AsyncMock()
    c.get_json = AsyncMock(return_value={"results": []})
    set_client(c)
    apify_called = {"n": 0}

    async def fake_apify(query, limit):
        apify_called["n"] += 1
        from reach_mcp.sources.base import Row

        return [Row(source="quora", id="1", title="apify hit", url="https://www.quora.com/x")]

    monkeypatch.setattr(q, "_apify_fetch", fake_apify)
    rows = await get_source("quora").fetch("kubernetes", 30, 10)
    assert apify_called["n"] == 1
    assert rows[0].title == "apify hit"


@pytest.mark.asyncio
async def test_quora_apify_not_called_when_searxng_hits(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "tok")
    monkeypatch.setenv("SEARXNG_URL", "http://searxng:8080")
    c = AsyncMock()
    c.get_json = AsyncMock(return_value=_searxng_payload())
    set_client(c)

    async def fake_apify(query, limit):
        raise AssertionError("apify must not run when searxng returned rows")

    monkeypatch.setattr(q, "_apify_fetch", fake_apify)
    rows = await get_source("quora").fetch("kubernetes", 30, 10)
    assert len(rows) == 2
