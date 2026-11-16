from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest

from reach_mcp.config import Settings
from reach_mcp.content import fetch_content
from reach_mcp.sources.base import Item
from reach_mcp.tools import _backfill_rich_media


def _settings(**over):
    base = Settings()
    fields = {f.name: getattr(base, f.name) for f in base.__dataclass_fields__.values()}
    fields.update(over)
    return Settings(**fields)


@pytest.mark.asyncio
async def test_fetch_content_xiaoyuzhou_uses_audio_url(monkeypatch):
    monkeypatch.setattr(
        "reach_mcp.sources.xiaoyuzhou.transcribe_audio_url",
        AsyncMock(return_value="full transcript"),
    )
    out = await fetch_content("xiaoyuzhou", "https://media.xyzcdn.net/a.m4a", _settings())
    assert out["ok"] and out["content"] == "full transcript"
    assert out["source"] == "xiaoyuzhou"


@pytest.mark.asyncio
async def test_fetch_content_youtube_extracts_id(monkeypatch):
    seen = {}

    async def fake_transcript(vid):
        seen["vid"] = vid
        return "captions text"

    monkeypatch.setattr("reach_mcp.sources.youtube.fetch_transcript", fake_transcript)
    out = await fetch_content("youtube", "https://www.youtube.com/watch?v=abc123XYZ", _settings())
    assert out["ok"] and out["content"] == "captions text"
    assert seen["vid"] == "abc123XYZ"


@pytest.mark.asyncio
async def test_fetch_content_other_source_falls_back_to_jina(monkeypatch):
    monkeypatch.setattr(
        "reach_mcp.content.jina_read_url",
        AsyncMock(return_value="article body"),
    )
    out = await fetch_content("arxiv", "https://arxiv.org/abs/1234.5678", _settings())
    assert out["ok"] and out["content"] == "article body"


@pytest.mark.asyncio
async def test_fetch_content_failure_returns_not_ok(monkeypatch):
    monkeypatch.setattr(
        "reach_mcp.sources.youtube.fetch_transcript",
        AsyncMock(return_value=""),
    )
    out = await fetch_content("youtube", "abc123", _settings())
    assert not out["ok"] and out["content"] == ""


def _rich_items():
    return [
        Item(
            source="youtube",
            id="y1",
            title="vid",
            url="https://youtu.be/y1",
            engagement={},
            text="desc snippet",
            score=0.9,
        ),
        Item(
            source="xiaoyuzhou",
            id="x1",
            title="pod",
            url="https://xyz.fm/e1",
            engagement={},
            text="shownotes snippet",
            score=0.8,
            audio_url="https://media.xyzcdn.net/e1.m4a",
        ),
        Item(
            source="reddit",
            id="r1",
            title="post",
            url="https://redd.it/r1",
            engagement={},
            text="post body",
            score=0.95,
        ),
    ]


@pytest.mark.asyncio
async def test_backfill_fills_rich_media_skips_others(monkeypatch):
    items = _rich_items()

    async def fake_fetch(source, key, settings):
        return {"source": source, "url": key, "content": f"FULL {source}", "ok": True}

    monkeypatch.setattr("reach_mcp.content.fetch_content", fake_fetch)
    await _backfill_rich_media(items, _settings())

    yt = next(i for i in items if i.source == "youtube")
    xy = next(i for i in items if i.source == "xiaoyuzhou")
    rd = next(i for i in items if i.source == "reddit")
    assert yt.text == "FULL youtube"
    assert xy.text == "FULL xiaoyuzhou"
    assert rd.text == "post body"  # untouched


@pytest.mark.asyncio
async def test_backfill_keeps_snippet_on_failure(monkeypatch):
    items = _rich_items()

    async def fake_fetch(source, key, settings):
        return {"source": source, "url": key, "content": "", "ok": False}

    monkeypatch.setattr("reach_mcp.content.fetch_content", fake_fetch)
    await _backfill_rich_media(items, _settings())
    yt = next(i for i in items if i.source == "youtube")
    assert yt.text == "desc snippet"  # fallback intact


@pytest.mark.asyncio
async def test_fetch_content_bare_without_prior_search_installs_own_client(monkeypatch):
    """Regression: the Jina/reader path must work even when `search` never ran
    (no shared PoliteClient installed) — previously hit 'PoliteClient not set'."""
    import reach_mcp.sources.base as base

    monkeypatch.setattr(base, "_CLIENT", None)  # simulate: no search ran in this process
    monkeypatch.setattr("reach_mcp.content.jina_read_url", AsyncMock(return_value="article body"))
    out = await fetch_content("web", "https://example.com/a", _settings())
    assert out["ok"] and out["content"] == "article body"


@pytest.mark.asyncio
async def test_fetch_content_zhihu_question_uses_api(monkeypatch):
    """zhihu question/answer goes to api/v4/answers with cookie, not Jina."""

    async def fake_full(id_or_url, client):
        assert "answer" in id_or_url
        return "full answer body"

    monkeypatch.setattr("reach_mcp.sources.zhihu.fetch_full_content", fake_full)
    out = await fetch_content("zhihu", "https://www.zhihu.com/question/1/answer/2", _settings())
    assert out["ok"] and out["content"] == "full answer body"


@pytest.mark.asyncio
async def test_fetch_content_zhihu_article_falls_back_to_reader(monkeypatch):
    captured = {}

    async def fake_full(id_or_url, client):
        captured["url"] = id_or_url
        return "article lede"

    monkeypatch.setattr("reach_mcp.sources.zhihu.fetch_full_content", fake_full)
    out = await fetch_content("zhihu", "https://zhuanlan.zhihu.com/p/2028", _settings())
    assert out["ok"] and out["content"] == "article lede"
    assert "zhuanlan.zhihu.com/p/2028" in captured["url"]


def _stub_backends(monkeypatch, exa="", jina="", fc="", tav=""):
    """Swap all four reader backends for canned returns."""
    import reach_mcp.readurl as ru

    async def _ret(text, *_a, **_k):
        return text

    monkeypatch.setattr(ru, "_exa_read", lambda url, t: _ret(exa))
    monkeypatch.setattr(ru, "_jina_read", lambda url, t: _ret(jina))
    monkeypatch.setattr(ru, "_firecrawl_read", lambda url, t: _ret(fc))
    monkeypatch.setattr(ru, "_tavily_read", lambda url, t: _ret(tav))


@pytest.mark.asyncio
async def test_readurl_order_cheap_first(monkeypatch):
    """Exa valid content short-circuits — Jina/Firecrawl never run for a cached page."""
    _stub_backends(monkeypatch, exa="x" * 500)
    import reach_mcp.readurl as ru

    assert (await ru.read_url("https://x")) == "x" * 500


@pytest.mark.asyncio
async def test_readurl_skips_walled_exa_falls_to_jina(monkeypatch):
    """A consent-wall body from Exa is rejected; Jina's real body wins."""
    import reach_mcp.readurl as ru

    _stub_backends(
        monkeypatch,
        exa="Before you continue to Google. Enable JavaScript to sign in.",
        jina="real article body " * 40,
    )
    assert await ru.read_url("https://x") == "real article body " * 40


@pytest.mark.asyncio
async def test_readurl_empty_short_circuit_to_firecrawl(monkeypatch):
    """Exa+Jina empty/too-short -> Firecrawl renders the body (credits spent only here)."""
    import reach_mcp.readurl as ru

    _stub_backends(monkeypatch, exa="", jina="short", fc="rendered full body " * 60)
    assert (await ru.read_url("https://x")).startswith("rendered full body")


@pytest.mark.asyncio
async def test_readurl_all_walled_returns_empty(monkeypatch):
    import reach_mcp.readurl as ru

    _stub_backends(monkeypatch, exa="Sign in to continue", jina="", fc="log in to view", tav="")
    assert await ru.read_url("https://x") == ""


def test_looks_walled_detects_consent_and_short():
    from reach_mcp.readurl import _looks_walled

    assert _looks_walled("")  # empty
    assert _looks_walled("Before you continue to Google")  # consent shell
    assert _looks_walled("Enable JavaScript to run this app")
    assert _looks_walled("tiny")  # too short to be a body
    assert not _looks_walled("A real paragraph of content. " * 30)  # long, no wall markers


@pytest.mark.parametrize(
    "base_url,want",
    [
        (
            "http://api-key-rotator:8788/firecrawl",
            "http://api-key-rotator:8788/firecrawl/v2/scrape",
        ),
        (
            "http://api-key-rotator:8788/firecrawl/",
            "http://api-key-rotator:8788/firecrawl/v2/scrape",
        ),
        (
            "http://api-key-rotator:8788/firecrawl/v2",
            "http://api-key-rotator:8788/firecrawl/v2/scrape",
        ),
        (
            "http://api-key-rotator:8788/firecrawl/v2/",
            "http://api-key-rotator:8788/firecrawl/v2/scrape",
        ),
        ("https://api.firecrawl.dev/v1/", "https://api.firecrawl.dev/v2/scrape"),
        ("https://api.firecrawl.dev/v2/scrape", "https://api.firecrawl.dev/v2/scrape"),
        ("https://api.firecrawl.dev/v1/scrape/", "https://api.firecrawl.dev/v2/scrape"),
        ("http://firecrawl:3002", "http://firecrawl:3002/v2/scrape"),
    ],
)
def test_firecrawl_scrape_url_normalization(base_url: str, want: str):
    from reach_mcp.readurl import _firecrawl_scrape_url

    assert _firecrawl_scrape_url(base_url) == want


def _mock_firecrawl_client(monkeypatch, handler):
    import reach_mcp.readurl as ru

    real_async_client = ru.httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr(ru.httpx, "AsyncClient", factory)


@pytest.mark.asyncio
async def test_firecrawl_read_uses_v2_scrape_and_keyless_omits_auth(monkeypatch):
    import reach_mcp.readurl as ru

    monkeypatch.setenv("FIRECRAWL_API_URL", "http://api-key-rotator:8788/firecrawl/")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "   ")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"success": True, "data": {"markdown": "  # Hello v2  "}})

    _mock_firecrawl_client(monkeypatch, handler)
    out = await ru._firecrawl_read("https://example.com/page", timeout=90)
    assert out == "# Hello v2"
    assert seen["url"] == "http://api-key-rotator:8788/firecrawl/v2/scrape"
    assert "authorization" not in seen["headers"]
    assert seen["body"] == {
        "url": "https://example.com/page",
        "formats": ["markdown"],
        "onlyMainContent": True,
        "timeout": 90000,
    }


@pytest.mark.asyncio
async def test_firecrawl_read_sends_bearer_and_clamps_timeout(monkeypatch):
    import reach_mcp.readurl as ru

    monkeypatch.setenv("FIRECRAWL_API_URL", "https://api.firecrawl.dev/v1")
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fc-test-key")
    seen_timeouts = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") == "Bearer fc-test-key"
        assert str(request.url) == "https://api.firecrawl.dev/v2/scrape"
        body = json.loads(request.content.decode("utf-8"))
        seen_timeouts.append(body["timeout"])
        return httpx.Response(200, json={"success": True, "data": {"markdown": "ok"}})

    _mock_firecrawl_client(monkeypatch, handler)
    assert await ru._firecrawl_read("https://example.com", timeout=0.2) == "ok"
    assert await ru._firecrawl_read("https://example.com", timeout=600) == "ok"
    assert seen_timeouts == [1000, 300000]


@pytest.mark.asyncio
async def test_firecrawl_read_rejects_failure_envelope_and_http_errors(monkeypatch):
    import reach_mcp.readurl as ru

    monkeypatch.setenv("FIRECRAWL_API_URL", "http://api-key-rotator:8788/firecrawl")
    responses = iter(
        [
            httpx.Response(
                200,
                json={
                    "success": False,
                    "error": "Insufficient credits",
                    "data": {"markdown": "should not return"},
                },
            ),
            httpx.Response(200, json={"success": True, "data": None}),
            httpx.Response(200, json={"success": True, "data": {"markdown": ["unexpected"]}}),
            httpx.Response(410, json={"success": False, "error": "Gone"}),
        ]
    )

    _mock_firecrawl_client(monkeypatch, lambda _req: next(responses))
    assert await ru._firecrawl_read("https://example.com", timeout=30) == ""
    assert await ru._firecrawl_read("https://example.com", timeout=30) == ""
    assert await ru._firecrawl_read("https://example.com", timeout=30) == ""
    assert await ru._firecrawl_read("https://example.com", timeout=30) == ""


@pytest.mark.asyncio
async def test_readurl_falls_back_to_tavily_when_firecrawl_fails(monkeypatch):
    import reach_mcp.readurl as ru

    monkeypatch.setenv("FIRECRAWL_API_URL", "http://api-key-rotator:8788/firecrawl")
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)

    async def _empty(*_a, **_k):
        return ""

    tavily_body = "Recovered via Tavily fallback. " * 25

    monkeypatch.setattr(ru, "_exa_read", _empty)
    monkeypatch.setattr(ru, "_jina_read", _empty)
    monkeypatch.setattr(ru, "_tavily_read", lambda _u, _t: AsyncMock(return_value=tavily_body)())
    _mock_firecrawl_client(
        monkeypatch,
        lambda _req: httpx.Response(410, json={"success": False, "error": "Gone"}),
    )

    assert await ru.read_url("https://example.com") == tavily_body


@pytest.mark.asyncio
async def test_firecrawl_read_noop_without_base_url(monkeypatch):
    import reach_mcp.readurl as ru

    monkeypatch.delenv("FIRECRAWL_API_URL", raising=False)
    called = False

    def handler(_req: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    _mock_firecrawl_client(monkeypatch, handler)
    assert await ru._firecrawl_read("https://example.com", timeout=30) == ""
    assert not called
