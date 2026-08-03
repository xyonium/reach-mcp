"""MCP tool definitions: search, list_sources, synthesize."""
from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from reach_mcp.config import Settings
from reach_mcp.http import PoliteClient
from reach_mcp.jina import read_url as jina_read_url
from reach_mcp.pipeline import (
    Category,
    SourceReport,
    expand_categories,
    import_all_sources,
    render_source_summary,
    run_search,
)
from reach_mcp.sources import SOURCES, available_sources
from reach_mcp.sources.base import Item, set_client
from reach_mcp.synthesize import brief, rerank

log = logging.getLogger(__name__)

_SEARCH_DESC = (
    "Search up to 25 social & web sources in parallel, score by engagement, "
    "optionally synthesize a cited brief. YOU control scope.\n\n"
    "Best scoping: `category` — social: x, reddit, instagram, threads, tiktok, "
    "xiaohongshu, bilibili, youtube, pinterest, bluesky, linkedin, xiaoyuzhou; "
    "it: github, hackernews, v2ex, rss, web; tech: arxiv, techmeme, digg, "
    "dripstack; polec (politics & economics): truthsocial, xueqiu, stocktwits, "
    "polymarket. `sources` picks individual names from those lists; both "
    "together = union; both omitted = all available (credential-set) sources. "
    "Each item's `text` is a snippet — `max_chars_per_item` caps its length "
    "(raise for fuller CN posts like xiaohongshu/xueqiu, lower to save "
    "tokens). Set `synthesize=false` for raw rows only — no LLM rerank or "
    "brief (re-brief later with the synthesize tool).\n\n"
    "Returns {brief, items, sources_used, source_summary, available_sources}. "
    "Each item: {source, title, url, author, date, score, engagement, text}. "
    "source_summary is one compact line per outcome — 'x:3; reddit:5 | EMPTY: "
    "rss, v2ex | QUOTA: tiktok(monthly limit) | ERRORS: digg(429)'; 'gated_off' "
    "means its credential env isn't set. Match query language to platform — "
    "Chinese keywords work best for the CN sources. Call list_sources if "
    "unsure what's configured."
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


def _item_to_dict(it: Item) -> dict:
    return {
        "source": it.source, "id": it.id, "title": it.title, "url": it.url,
        "author": it.author, "date": it.date, "score": round(it.score, 4),
        "engagement": it.engagement, "text": it.text, "cluster": it.cluster,
    }


def _source_report_to_dict(r: SourceReport) -> dict:
    return {"source": r.source, "status": r.status, "count": r.count, "error": r.error}


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
            "omitted = all configured. list_sources() shows availability; "
            "read_url(url) fetches full page text; synthesize(query, items) "
            "re-briefs prior rows without re-searching."
        ),
    )

    @mcp.tool(description=_LIST_DESC)
    async def list_sources() -> list[dict]:
        out = []
        for s in SOURCES.values():
            out.append({
                "name": s.name, "description": s.description,
                "needs_auth": s.needs_auth, "available": s.available(),
                "required_env": list(s.required_env),
                "default_days": s.default_days, "default_limit": s.default_limit,
            })
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
    ) -> dict:
        client = PoliteClient(settings)
        try:
            items, reports = await run_search(
                query, expand_categories(sources, category), days,
                max_per_source, client, settings, max_chars_per_item,
            )
            brief_text = None
            if synthesize and items:
                items = await rerank(query, items, settings)
                brief_text = await brief(query, items, settings)
            return {
                "brief": brief_text,
                "items": [_item_to_dict(i) for i in items],
                "sources_used": [_source_report_to_dict(r) for r in reports],
                "source_summary": render_source_summary(reports),
                "available_sources": available_sources(),
            }
        finally:
            await client.aclose()

    @mcp.tool(description=_SYNTH_DESC)
    async def synthesize(query: str, items: list[dict]) -> dict:
        parsed = [Item(
            source=i.get("source", ""), id=i.get("id", ""), title=i.get("title", ""),
            url=i.get("url", ""), author=i.get("author"), date=i.get("date"),
            engagement=i.get("engagement", {}), text=i.get("text", ""),
        ) for i in items]
        return {"brief": await brief(query, parsed, settings)}

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
