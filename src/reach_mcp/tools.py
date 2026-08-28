"""MCP tool definitions: search, list_sources, synthesize, read_url, fetch_content."""

from __future__ import annotations

import asyncio
import logging

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from reach_mcp.config import Settings
from reach_mcp.content import fetch_content
from reach_mcp.http import PoliteClient
from reach_mcp.jina import read_url as jina_read_url
from reach_mcp.pipeline import (
    Category,
    SourceReport,
    expand_categories,
    import_all_sources,
    render_source_summary,
    run_search,
    run_trending,
)
from reach_mcp.sources import SOURCES
from reach_mcp.sources.base import Item, set_client
from reach_mcp.synthesize import brief, rerank

log = logging.getLogger(__name__)

_SEARCH_DESC = (
    "Search up to 32 social & web sources in parallel, score by engagement, "
    "and synthesize a cited brief. YOU control scope.\n\n"
    "Best scoping: `category` — social: x, reddit, instagram, threads, tiktok, "
    "xiaohongshu, weibo, zhihu, douban, toutiao, bilibili, youtube, pinterest, "
    "bluesky, linkedin, web, quora; "
    "it: github, hackernews, v2ex, rss, arxiv, dripstack, stackoverflow, "
    "lobsters; "
    "tech: arxiv, techmeme, digg, dripstack, hackernews; "
    "polec (politics & economics): truthsocial, xueqiu, stocktwits, polymarket; "
    "podcast: xiaoyuzhou. Categories overlap (e.g. github is both it and tech) "
    "— multiple categories union. `sources` picks individual names; both "
    "together = union; both omitted = all available sources EXCEPT podcast "
    "(xiaoyuzhou is opt-in: episode transcription is slow, request it "
    "explicitly when you need podcasts).\n\n"
    "QUERY STYLE: write a short keyword query, not a full question. Literal "
    "keyword-AND sources (x, threads) match every word — 2-5 content words, no "
    "'latest/news/how-to' filler. Keyword-slot sources (bluesky, tiktok, "
    "instagram, pinterest, linkedin, quora, xiaohongshu, weibo) take a compact "
    "phrase. Semantic sources (reddit, web, arxiv, github, hackernews, youtube, "
    "bilibili) tolerate longer natural phrasing; stackoverflow (official SE "
    "API, Q&A corpus) and lobsters (feed-filtered, so specific tech terms) "
    "take English tech keywords; douban (豆瓣 movie/TV/book/"
    "music ratings, keyless) and zhihu take Chinese titles/keywords; zhihu is "
    "hot-list browse "
    "(filtering, not search — Chinese keywords work best). The pipeline already "
    "strips question/meta words per source and retries X with shorter variants, "
    "so lead with the core subject. Match query language to platform — Chinese "
    "keywords work best for the CN sources. For WeChat 公众号 articles, use the "
    "web source with 公众号 in the query (auto-scoped to mp.weixin.qq.com) — "
    "there is no dedicated wechat source.\n\n"
    "TRENDING (热搜/热榜): set trending=true to fetch what's hot RIGHT NOW "
    "instead of searching — weibo 实时热搜 (with heat values), zhihu 热榜, "
    "toutiao 头条热榜 (with hot values), "
    "hackernews front page, lobsters hottest, bilibili 综合热门 ranking, "
    "x/X trends (via the "
    "trends24 mirror — works WITHOUT the x login cookies), and github "
    "newly-hot repos (created this week, sorted by stars). `query` is IGNORED in "
    'this mode (pass ""); `sources` still scopes (e.g. sources=["weibo"]). '
    "Use it for 'what's trending on weibo', '今日热搜', or to seed a topic "
    "before a keyword search.\n\n"
    "CREDENTIAL HEALTH: if source_summary carries NOTICE lines, that source "
    "degraded (e.g. a stale login cookie fell back to a limited public path). "
    "Results are still usable, but mention the notice when it matters and "
    "suggest refreshing the named env var.\n\n"
    "The default (synthesize=true) returns a cited brief plus scored items — "
    "one call = a finished report. It auto-backfills full content for the top "
    "rich-media items (xiaoyuzhou/youtube/bilibili) before the brief. "
    "synthesize=false returns raw metadata + a per-item snippet instead, for "
    "custom post-processing; pair it with fetch_content to read any item in "
    "full. `max_chars_per_item` caps snippet length (raise for fuller CN "
    "posts, lower to save tokens).\n\n"
    "Returns {brief, items, sources_used, source_summary}. "
    "Each item: {source, title, url, author, date, score, engagement, text}. "
    "source_summary is one compact line per outcome — 'x:3; reddit:5 | EMPTY: "
    "rss, v2ex | QUOTA: tiktok(monthly limit) | ERRORS: digg(429)'; 'gated_off' "
    "means its credential env isn't set. Call list_sources if unsure what's "
    "configured."
)

_LIST_DESC = (
    "Inventory of all registered sources. Call before search when unsure "
    "what's active. Returns [{name, description, needs_auth, available, "
    "required_env, default_days, default_limit}]: available=false = gated "
    "(credential in required_env not set). No arguments."
)

_SYNTH_DESC = (
    "LLM-synthesize a cited brief from items returned by a prior "
    "search(synthesize=false), WITHOUT re-searching. Args: `query` (the "
    "original), `items` (the prior items list). Returns {brief}."
)

_READ_URL_DESC = (
    "Fetch any URL as clean markdown via Jina Reader. Use for the full text "
    "of a page found via search — a thread, article, or repo — when the "
    "item's `text` snippet isn't enough. Returns {url, content, ok}; content "
    "is '' on failure. Keyless."
)

_FETCH_CONTENT_DESC = (
    "Fetch the full content of ONE item found via search. Two-stage "
    "retrieval: search returns metadata + a snippet for every source; call "
    "this when an item is worth reading/hearing in full — especially after "
    "search(synthesize=false), which returns snippets only. Rich-media sources "
    "have dedicated backends — xiaoyuzhou (pass the item's audio_url → "
    "Whisper transcript of the episode), youtube (watch URL or video id → "
    "captions), bilibili (video URL → CC subtitles if the video has them, "
    "else ''); every other source falls back to Jina Reader on the item's "
    "url. Args: `source` (the item's source field), `id_or_url` (audio_url "
    "for xiaoyuzhou, url/id otherwise). Returns {source, url, content, ok}. "
    "With synthesize=true, search already backfills the top rich-media items "
    "automatically — use this for anything beyond those."
)

# Sources whose full text comes from fetch_content, not from the search-time
# snippet — the search(synthesize=true) auto-backfill loop targets these.
_AUTO_BACKFILL_SOURCES = ("xiaoyuzhou", "youtube", "bilibili")
_AUTO_BACKFILL_TOP_K = 3


async def _backfill_rich_media(items: list[Item], settings: Settings) -> None:
    """Fill `text` for the top rich-media items via fetch_content, in place.

    With synthesize=true the rerank/brief needs real content to work with —
    a shownotes/description snippet alone is too thin to rank or summarize.
    We backfill the top-K rich-media items (by score) before rerank so the
    brief cites transcripts/captions, not blurbs. Failures leave the snippet.
    """
    from reach_mcp.content import fetch_content  # local to avoid an import cycle

    async def _fill(it: Item) -> None:
        key = it.audio_url if (it.source == "xiaoyuzhou" and it.audio_url) else it.url
        res = await fetch_content(it.source, key, settings)
        if res.get("ok") and res.get("content"):
            it.text = res["content"]

    # top-K per rich-media source, so no single source hogs the budget
    targets: list[Item] = []
    for src in _AUTO_BACKFILL_SOURCES:
        cands = [i for i in items if i.source == src]
        cands.sort(key=lambda i: i.score, reverse=True)
        targets.extend(cands[:_AUTO_BACKFILL_TOP_K])
    if targets:
        await asyncio.gather(*[_fill(i) for i in targets])


def _item_to_dict(it: Item) -> dict:
    d = {
        "source": it.source,
        "id": it.id,
        "title": it.title,
        "url": it.url,
        "author": it.author,
        "date": it.date,
        "score": round(it.score, 4),
        "engagement": it.engagement,
        "text": it.text,
        "cluster": it.cluster,
    }
    if it.audio_url:
        d["audio_url"] = it.audio_url
    if it.duration_min:
        d["duration_min"] = it.duration_min
    return d


def _source_report_to_dict(r: SourceReport) -> dict:
    d = {"source": r.source, "status": r.status, "count": r.count, "error": r.error}
    if r.notice:
        d["notice"] = r.notice
    return d


def build_mcp(settings: Settings) -> FastMCP:
    import_all_sources()
    mcp = FastMCP(
        "reach-mcp",
        host=settings.host,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=settings.dns_rebinding_protection,
            allowed_hosts=list(settings.allowed_hosts),
            allowed_origins=[f"http://{h}" for h in settings.allowed_hosts],
        ),
        instructions=(
            "Multi-source search. search(query, category=[...]) scopes by topic "
            "group; search(query, sources=[...]) picks sources by name; both "
            "omitted = all configured. Search returns metadata + snippets; "
            "fetch_content(source, id_or_url) gets an item's full content "
            "(podcast transcript, video captions, article body). list_sources() "
            "shows availability; synthesize(query, items) re-briefs prior rows."
        ),
    )

    @mcp.tool(description=_LIST_DESC)
    async def list_sources() -> list[dict]:
        out = []
        for s in SOURCES.values():
            out.append(
                {
                    "name": s.name,
                    "description": s.description,
                    "needs_auth": s.needs_auth,
                    "available": s.available(),
                    "required_env": list(s.required_env),
                    "default_days": s.default_days,
                    "default_limit": s.default_limit,
                }
            )
        return out

    @mcp.tool(description=_SEARCH_DESC)
    async def search(
        query: str,
        sources: list[str] | None = None,
        category: list[Category] | None = None,
        days: int = 30,
        max_per_source: int = 20,
        max_chars_per_item: int = 500,
        synthesize: bool = True,
        trending: bool = False,
    ) -> dict:
        client = PoliteClient(settings)
        try:
            if trending:
                items, reports = await run_trending(
                    sources or expand_categories(sources, category),
                    max_per_source,
                    client,
                )
                return {
                    "brief": None,
                    "items": [_item_to_dict(i) for i in items],
                    "sources_used": [_source_report_to_dict(r) for r in reports],
                    "source_summary": render_source_summary(reports),
                }
            items, reports = await run_search(
                query,
                expand_categories(sources, category),
                days,
                max_per_source,
                client,
                settings,
                max_chars_per_item,
            )
            brief_text = None
            if synthesize and items:
                await _backfill_rich_media(items, settings)
                items = await rerank(query, items, settings)
                brief_text = await brief(query, items, settings)
            return {
                "brief": brief_text,
                "items": [_item_to_dict(i) for i in items],
                "sources_used": [_source_report_to_dict(r) for r in reports],
                "source_summary": render_source_summary(reports),
            }
        finally:
            await client.aclose()

    @mcp.tool(description=_SYNTH_DESC)
    async def synthesize(query: str, items: list[dict]) -> dict:
        parsed = [
            Item(
                source=i.get("source", ""),
                id=i.get("id", ""),
                title=i.get("title", ""),
                url=i.get("url", ""),
                author=i.get("author"),
                date=i.get("date"),
                engagement=i.get("engagement", {}),
                text=i.get("text", ""),
            )
            for i in items
        ]
        return {"brief": await brief(query, parsed, settings)}

    @mcp.tool(name="fetch_content", description=_FETCH_CONTENT_DESC)
    async def fetch_content_tool(source: str, id_or_url: str) -> dict:
        return await fetch_content(source, id_or_url, settings)

    @mcp.tool(description=_READ_URL_DESC)
    async def read_url(url: str) -> dict:
        # Use a dedicated client with a longer timeout: page reads via Jina can
        # take several seconds. read_url is independent of the search pipeline.
        client = PoliteClient(settings)
        try:
            set_client(client)
            content = await jina_read_url(url)
            return {"url": url, "content": content, "ok": bool(content)}
        finally:
            await client.aclose()

    return mcp
