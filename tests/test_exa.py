"""exa.ai search backend tests — domain-scoped discovery with answer highlights.

exa is a POST /search API (x-api-key). The rich path: includeDomains scopes to
one site (quora.com/linkedin.com), contents.highlights returns ANSWER-content
snippets that bypass the CF wall (contents.text gets the login shell on quora,
so we don't request it). publishedDate comes back on many results — the first
date-carrying discovery path for linkedin/quora. $0.007/neural search, metered.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import reach_mcp.sources._exa as exa
from reach_mcp.sources.base import set_client


def _exa_payload():
    return {
        "results": [
            {
                "title": "What is Kubernetes container orchestration? - Quora",
                "url": "https://www.quora.com/What-is-Kubernetes-container-orchestration",
                "publishedDate": "2022-08-29T00:00:00.000Z",
                "author": None,
                "id": "https://www.quora.com/What-is-Kubernetes-container-orchestration",
                "highlights": [
                    "Kubernetes container orchestration is a platform and set of "
                    "abstractions for deploying, managing, scaling applications"
                ],
                "highlightScores": [0.62],
            },
            {
                "title": "How does Kubernetes work? - Quora",
                "url": "https://www.quora.com/How-does-Kubernetes-work",
                "publishedDate": None,
                "author": None,
                "id": "https://www.quora.com/How-does-Kubernetes-work",
                "highlights": ["For the first three, Kubernetes works by..."],
                "highlightScores": [0.55],
            },
        ],
        "costDollars": {"total": 0.007},
    }


@pytest.mark.asyncio
async def test_exa_search_posts_with_domain_and_highlights(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "k")
    c = AsyncMock()
    c.post_json = AsyncMock(return_value=_exa_payload())
    set_client(c)
    rows = await exa.search("kubernetes", "quora.com", "quora", 10)
    assert len(rows) == 2
    r = rows[0]
    assert r.source == "quora"
    assert r.url == "https://www.quora.com/What-is-Kubernetes-container-orchestration"
    assert r.date and r.date.startswith("2022-08-29")
    # text comes from the answer highlight, not the title
    assert "platform and set of abstractions" in r.text
    # request shape: POST to /search with includeDomains + highlights, NO text
    body = c.post_json.call_args.kwargs["json"]
    assert body["includeDomains"] == ["quora.com"]
    assert "highlights" in body["contents"]
    assert "text" not in body["contents"]
    headers = c.post_json.call_args.kwargs["headers"]
    assert headers["x-api-key"] == "k"


@pytest.mark.asyncio
async def test_exa_search_uses_query_variation(monkeypatch):
    """highlights carry the answer; title-only results still produce a row."""
    monkeypatch.setenv("EXA_API_KEY", "k")
    c = AsyncMock()
    c.post_json = AsyncMock(return_value=_exa_payload())
    set_client(c)
    rows = await exa.search("kubernetes", "linkedin.com", "linkedin", 10)
    assert rows[0].source == "linkedin"


@pytest.mark.asyncio
async def test_exa_search_missing_key_returns_empty(monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    c = AsyncMock()
    set_client(c)
    assert await exa.search("q", "quora.com", "quora", 10) == []


@pytest.mark.asyncio
async def test_exa_search_failure_returns_empty(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "k")
    c = AsyncMock()

    async def post_json(url, **kw):
        raise RuntimeError("402 payment required")

    c.post_json = AsyncMock(side_effect=post_json)
    set_client(c)
    assert await exa.search("q", "quora.com", "quora", 10) == []


def test_exa_available(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "k")
    assert exa.available()
    monkeypatch.delenv("EXA_API_KEY")
    assert not exa.available()


def test_exa_base_url_override(monkeypatch):
    """EXA_BASE_URL overrides the default api.exa.ai (for key-rotator/proxy)."""
    monkeypatch.delenv("EXA_BASE_URL", raising=False)
    assert exa._base() == "https://api.exa.ai"
    monkeypatch.setenv("EXA_BASE_URL", "http://api-key-rotator:8788/exa/")
    assert exa._base() == "http://api-key-rotator:8788/exa"  # trailing slash stripped


@pytest.mark.asyncio
async def test_exa_search_uses_base_override(monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "k")
    monkeypatch.setenv("EXA_BASE_URL", "http://gw:9000/exa")
    c = AsyncMock()
    c.post_json = AsyncMock(return_value=_exa_payload())
    set_client(c)
    await exa.search("kubernetes", "quora.com", "quora", 10)
    url = c.post_json.call_args.args[0]
    assert url == "http://gw:9000/exa/search"
