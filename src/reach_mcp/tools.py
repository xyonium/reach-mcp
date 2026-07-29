"""MCP tool definitions: search, list_sources, synthesize."""
from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from reach_mcp.config import Settings
from reach_mcp.http import PoliteClient
from reach_mcp.pipeline import SourceReport, import_all_sources, run_search
from reach_mcp.sources import SOURCES, available_sources
from reach_mcp.sources.base import Item
from reach_mcp.synthesize import brief, rerank

log = logging.getLogger(__name__)

_SEARCH_DESC = (
    "Search up to 23 social & web sources in parallel, score by engagement, "
    "optionally synthesize a cited brief. YOU control scope.\n\n"
    "Sources (pass any subset as `sources`; omit/None = all currently-configured): "
    "free — reddit, hackernews, bluesky, github, arxiv, techmeme, polymarket, "
    "stocktwits, web; video — youtube; chinese — xueqiu, v2ex, bilibili, "
    "xiaoyuzhou; login-gated (off until creds set) — x, truthsocial, tiktok, "
    "instagram, linkedin, xiaohongshu, threads, pinterest; binary — digg.\n\n"
    "Args: `query` (str, the topic/person/ticker); `sources` (list[str] | None, "
    "None=all available); `days` (int, recency window, default 30); "
    "`max_per_source` (int, row cap per source, default 20); `synthesize` (bool, "
    "default true = also LLM-rerank + write brief).\n\n"
    "Returns: {brief: str|null, items: [Item], sources_used: [SourceReport], "
    "available_sources: [str]}. Each Item: {source, title, url, author, date, "
    "score, engagement, text}. A SourceReport tells you per-source "
    "ok/gated_off/errored so a thin result is diagnosable. Call list_sources "
    "first if unsure what's configured."
)

_LIST_DESC = (
    "List all registered sources with availability status, required credentials, "
    "and defaults. Call this FIRST to see which sources are active (credentials "
    "set) vs gated (off-by-default) before deciding `sources`. Returns "
    "[{name, description, needs_auth, available, required_env, default_days, "
    "default_limit}]. No arguments."
)

_SYNTH_DESC = (
    "Re-synthesize a cited brief from already-fetched items WITHOUT re-searching. "
    "Pass the original `query` and the `items` list from a prior "
    "search(synthesize=false). Returns {brief}. Use to re-brief cheaply with "
    "different emphasis. No source calls are made."
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
            "reach-mcp: controllable multi-source search. Call list_sources first "
            "to see what's configured, then search(query, sources?, days?, "
            "max_per_source?, synthesize?). Re-brief with synthesize(query, items)."
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
        days: int = 30,
        max_per_source: int = 20,
        synthesize: bool = True,
    ) -> dict:
        client = PoliteClient(settings)
        try:
            items, reports = await run_search(
                query, sources, days, max_per_source, client, settings
            )
            brief_text = None
            if synthesize and items:
                items = await rerank(query, items, settings)
                brief_text = await brief(query, items, settings)
            return {
                "brief": brief_text,
                "items": [_item_to_dict(i) for i in items],
                "sources_used": [_source_report_to_dict(r) for r in reports],
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

    return mcp
