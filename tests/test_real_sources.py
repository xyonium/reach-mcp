"""Live health-check: one "must-hit" query per source against the production endpoint.

A mock-unit-test suite can't catch a source whose endpoint changed shape or whose
query param is silently ignored upstream (polymarket /markets?query=, 2026-09).
Each source here gets one SHORT query (≤4 words) chosen to always have results on
that platform regardless of when the test runs — evergreens, not news. One round =
one HTTP request per available source; pay-walled sources (apify/x/cookie-…)
skip themselves when the credential isn't in the environment, so no tokens are
burned by default.

Run the whole sweep (not in CI):
    pytest -m real -q

Run one source while iterating:
    pytest -m real -k polymarket -q
"""

from __future__ import annotations

import os

import pytest

from reach_mcp.config import Settings
from reach_mcp.http import PoliteClient
from reach_mcp.sources import get_source
from reach_mcp.sources.base import set_client

# Short evergreen queries that will keep returning results for years:
# generic platform-topic nouns, no dates, no events.
REAL_QUERIES: dict[str, str] = {
    "arxiv": "attention",
    "bilibili": "美食",
    "bluesky": "hello",
    "digg": "climate",
    "douban": "三体",
    "dripstack": "fed",  # English-only index (CN queries -> upstream 0-hit, not a bug)
    "github": "python",
    "hackernews": "AI",
    "lobsters": "rust",
    "polymarket": "Trump",
    "reddit": "technology",
    "stackoverflow": "python",
    "techmeme": "AI",
    "toutiao": "天气",
    "v2ex": "远程",
    "weibo": "中秋",
    "xueqiu": "600519",  # suggest API prefix-matches the bare code; with XUEQIU_COOKIE "茅台" works too
    "youtube": "music",
    "zhihu": "人工智能",
    # credential-gated (run only when the env var is set)
    "instagram": "sunset",
    "linkedin": "openai",
    "linuxdo": "claude",
    "pinterest": "recipes",
    "quora": "startup",
    "rss": "news",
    "threads": "sports",
    "tiktok": "dance",
    "truthsocial": "news",
    "x": "AI",
    "xiaohongshu": "咖啡",
    "xiaoyuzhou": "商业",
    # config-gated
    "web": "openai",
}


@pytest.fixture(autouse=True)
async def _shared_client():
    client = PoliteClient(Settings())
    set_client(client)
    yield client
    await client.aclose()


# Sources whose backend is configuration, not a credential: skip if the
# dependency isn't reachable in this environment.
_CONFIG_SKIP = {
    "web": "SEARXNG_URL",  # self-hosted searxng; not resolvable from a bare laptop/test host
    "bluesky": "SEARXNG_URL",  # api.bsky.app 403s datacenter IPs; fallback needs searxng
    "rss": "RSS_FEEDS",  # feed list must be configured
    "xueqiu": "XUEQIU_COOKIE",  # anonymous suggest API now returns 400016 — cookie is required
    "arxiv": "PROBE",  # probe export.arxiv.org before running; skip on connect fail (egress blocked), ARXIV_OK=1 forces run
}


@pytest.mark.real
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source,query",
    sorted(REAL_QUERIES.items()),
    ids=sorted(REAL_QUERIES),
)
async def test_real_source_returns_rows(source: str, query: str, _shared_client):
    if source in _CONFIG_SKIP:
        gate = _CONFIG_SKIP[source]
        if gate == "PROBE":
            import httpx

            force = os.environ.get("ARXIV_OK", "").strip() == "1"
            if not force:
                try:
                    async with httpx.AsyncClient(timeout=5) as hc:
                        await hc.get(
                            "https://export.arxiv.org/api/query",
                            params={"search_query": "all:test", "max_results": "1"},
                        )
                except httpx.HTTPError as e:
                    pytest.skip(f"arxiv: export.arxiv.org unreachable from this egress ({type(e).__name__}); ARXIV_OK=1 forces the test")
        elif not os.environ.get(gate, "").strip():
            pytest.skip(f"{source}: {gate} not configured")
    src = get_source(source)
    if not src.available():
        pytest.skip(f"{source}: backend credential not set")
    rows = await src.fetch(query, days=90, limit=5)
    assert rows, (
        f"{source} with evergreen query {query!r} returned 0 rows — "
        f"upstream endpoint or query param likely broken. "
        f"last_notice: {src.last_notice!r}"
    )
    for r in rows:
        assert r.source == source
        assert r.title, f"{source} row missing title: {r}"
        assert r.url.startswith("http"), f"{source} row malformed url: {r.url!r}"
