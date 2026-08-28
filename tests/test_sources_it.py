"""IT-category source tests: stackoverflow (keyless Stack Exchange API), lobste.rs."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from reach_mcp.sources import get_source
from reach_mcp.sources.base import set_client


@pytest.mark.asyncio
async def test_stackoverflow_search_parses_questions():
    """api.stackexchange.com/2.3/search/advanced — keyless official API."""
    c = AsyncMock()
    c.get_json = AsyncMock(
        return_value={
            "has_more": False,
            "items": [
                {
                    "question_id": 79521563,
                    "title": "How to await multiple asyncio tasks?",
                    "link": "https://stackoverflow.com/questions/79521563/x",
                    "score": 42,
                    "answer_count": 3,
                    "view_count": 1234,
                    "is_answered": True,
                    "creation_date": 1748000000,
                    "tags": ["python", "asyncio"],
                    "owner": {"display_name": "alice", "user_type": "registered"},
                },
                {
                    "question_id": 79521600,
                    "title": "pytest fixture scope confusion",
                    "link": "https://stackoverflow.com/questions/79521600/y",
                    "score": 7,
                    "answer_count": 1,
                    "view_count": 200,
                    "is_answered": False,
                    "creation_date": 1748100000,
                    "tags": ["pytest"],
                    "owner": {"display_name": "bob", "user_type": "registered"},
                },
            ],
        }
    )
    set_client(c)
    rows = await get_source("stackoverflow").fetch("asyncio gather", 30, 10)
    assert len(rows) == 2
    r = rows[0]
    assert r.source == "stackoverflow"
    assert r.id == "79521563"
    assert r.title == "How to await multiple asyncio tasks?"
    assert r.url == "https://stackoverflow.com/questions/79521563/x"
    assert r.author == "alice"
    assert r.date and r.date.startswith("2025-05-23")  # 1748000000 unix
    assert r.engagement["score"] == 42
    assert r.engagement["answers"] == 3
    assert r.engagement["answered"] is True
    assert r.engagement["tags"] == ["python", "asyncio"]
    # request params: site + time window + keyword
    params = c.get_json.call_args.kwargs["params"]
    assert params["site"] == "stackoverflow"
    assert "fromdate" in params and int(params["fromdate"]) > 0
    assert params["q"] == "asyncio gather" or params.get("intitle") == "asyncio gather"


@pytest.mark.asyncio
async def test_stackoverflow_respects_limit():
    c = AsyncMock()
    c.get_json = AsyncMock(
        return_value={
            "has_more": False,
            "items": [
                {
                    "question_id": i,
                    "title": f"q{i}",
                    "link": f"https://stackoverflow.com/questions/{i}",
                    "score": 1,
                    "answer_count": 0,
                    "view_count": 1,
                    "is_answered": False,
                    "creation_date": 1748000000,
                    "tags": [],
                    "owner": {},
                }
                for i in range(10)
            ],
        }
    )
    set_client(c)
    rows = await get_source("stackoverflow").fetch("x", 30, 3)
    assert len(rows) == 3


@pytest.mark.asyncio
async def test_stackoverflow_failure_sets_notice():
    c = AsyncMock()

    async def get_json(url, **kwargs):
        raise RuntimeError("502 bad gateway")

    c.get_json = AsyncMock(side_effect=get_json)
    set_client(c)
    src = get_source("stackoverflow")
    rows = await src.fetch("asyncio", 30, 10)
    assert rows == []
    assert src.last_notice and "stackoverflow" in src.last_notice.lower()


@pytest.mark.asyncio
async def test_lobsters_search_filters_tag_feed():
    """lobste.rs has no public search.json (404s) — search = pull tag feeds
    (hottest + newest) and filter client-side by query words, v2ex-style."""
    c = AsyncMock()

    async def get_json(url, **kwargs):
        if "hottest" in url:
            return [
                {
                    "short_id": "abc123",
                    "title": "Writing a JIT compiler in Rust",
                    "url": "https://example.com/jit",
                    "comments_url": "https://lobste.rs/s/abc123/x",
                    "score": 84,
                    "comment_count": 32,
                    "created_at": "2026-08-20T10:00:00.000Z",
                    "description": "A walkthrough of a tracing JIT in Rust",
                    "submitter_user": {"username": "cruster"},
                    "tags": ["rust", "compilers"],
                },
                {
                    "short_id": "def456",
                    "title": "Kubernetes cost traps",
                    "url": "https://example.com/k8s",
                    "comments_url": "https://lobste.rs/s/def456/y",
                    "score": 21,
                    "comment_count": 5,
                    "created_at": "2026-08-21T10:00:00.000Z",
                    "description": "Cloud billing pitfalls",
                    "submitter_user": {"username": "opsdude"},
                    "tags": ["devops"],
                },
            ]
        return []  # newest.json etc.

    c.get_json = AsyncMock(side_effect=get_json)
    set_client(c)
    rows = await get_source("lobsters").fetch("rust compiler", 30, 10)
    assert len(rows) == 1
    r = rows[0]
    assert r.source == "lobsters"
    assert r.id == "abc123"
    assert r.title == "Writing a JIT compiler in Rust"
    assert r.url == "https://lobste.rs/s/abc123/x"  # discussion link, not outlink
    assert r.author == "cruster"
    assert r.engagement["score"] == 84
    assert r.engagement["comments"] == 32
    assert r.engagement["tags"] == ["rust", "compilers"]


@pytest.mark.asyncio
async def test_lobsters_trending_hottest():
    c = AsyncMock()
    c.get_json = AsyncMock(
        return_value=[
            {
                "short_id": "abc123",
                "title": "Story one",
                "url": "https://example.com/1",
                "comments_url": "https://lobste.rs/s/abc123/x",
                "score": 84,
                "comment_count": 32,
                "created_at": "2026-08-20T10:00:00.000Z",
                "description": "desc",
                "submitter_user": {"username": "cruster"},
                "tags": ["rust"],
            }
        ]
    )
    set_client(c)
    src = get_source("lobsters")
    assert src.supports_trending is True
    rows = await src.fetch_trending(10)
    assert len(rows) == 1
    assert rows[0].engagement["score"] == 84


@pytest.mark.asyncio
async def test_lobsters_submitter_user_as_plain_string():
    """Live lobste.rs JSON has submitter_user as a plain username STRING,
    not an object (caught by E2E 2026-08-28)."""
    c = AsyncMock()
    c.get_json = AsyncMock(
        return_value=[
            {
                "short_id": "xyz789",
                "title": "Some rust story",
                "url": "https://example.com/1",
                "comments_url": "https://lobste.rs/s/xyz789/x",
                "score": 10,
                "comment_count": 2,
                "created_at": "2026-08-25T10:00:00.000Z",
                "description": "rust inside",
                "submitter_user": "cruster",
                "tags": ["rust"],
            }
        ]
    )
    set_client(c)
    rows = await get_source("lobsters").fetch_trending(10)
    assert len(rows) == 1
    assert rows[0].author == "cruster"


@pytest.mark.asyncio
async def test_lobsters_failure_sets_notice():
    c = AsyncMock()

    async def get_json(url, **kwargs):
        raise RuntimeError("connection reset")

    c.get_json = AsyncMock(side_effect=get_json)
    set_client(c)
    src = get_source("lobsters")
    rows = await src.fetch("rust", 30, 10)
    assert rows == []
    assert src.last_notice and "lobste" in src.last_notice.lower()
