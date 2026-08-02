"""小红书 (Xiaohongshu/RED) via xiaohongshu-mcp companion service.

Uses the community-vetted xiaohongshu-mcp Go server (15K+ GitHub stars) as
the backend. This is the most stable server-side approach — xiaohongshu-mcp
handles auth, cookie refresh, and request signing internally.

Requirements:
  - xiaohongshu-mcp running at XHS_MCP_URL (default http://localhost:18060/mcp)
  - xiaohongshu-mcp logged in (call its get_login_qrcode tool once — search
    returns {feeds: [], count: 0} while logged out)

Verified 2026-08 against xiaohongshu-mcp v2.0.0: the search tool is
``search_feeds`` (NOT the legacy ``search_notes`` — that name errors with
method-not-found). It takes ``keyword`` + optional ``filters`` (sort_by,
note_type, publish_time, search_scope, location); there is NO ``limit`` param
(the tool returns one page). Results come back as a JSON text blob:
{feeds: [{noteId, title, xsecToken, ...}], count: N}.
"""
from __future__ import annotations

import logging
import os

from reach_mcp.sources.base import Row, Source, register_source

log = logging.getLogger(__name__)

# xiaohongshu-mcp search tool name (v2.0.0). Legacy `search_notes` is gone.
_SEARCH_TOOL = "search_feeds"


async def _fetch_via_mcp(url: str, query: str, days: int, limit: int) -> list[Row]:
    """Fetch search results from xiaohongshu-mcp via JSON-RPC over HTTP."""
    import httpx

    endpoint = url.rstrip("/") + "/message"
    # Map recency window to the tool's publish_time filter, if meaningful.
    filters = {}
    if days <= 1:
        filters["publish_time"] = "一天内"
    elif days <= 7:
        filters["publish_time"] = "一周内"
    elif days <= 180:
        filters["publish_time"] = "半年内"

    try:
        async with httpx.AsyncClient(timeout=30) as hclient:
            # Step 1: initialize MCP session
            init_r = await hclient.post(
                endpoint,
                json={"jsonrpc": "2.0", "method": "initialize",
                      "params": {"protocolVersion": "2024-11-05",
                                "capabilities": {}, "clientInfo": {"name": "reach-mcp", "version": "0.1"}},
                      "id": 1},
                headers={"Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream"},
            )
            sid = init_r.headers.get("mcp-session-id", "")

            # Step 2: call search_feeds tool
            call_headers = {"Content-Type": "application/json",
                          "Accept": "application/json, text/event-stream"}
            if sid:
                call_headers["mcp-session-id"] = sid

            call_r = await hclient.post(
                endpoint,
                json={"jsonrpc": "2.0", "method": "tools/call",
                      "params": {"name": _SEARCH_TOOL,
                                "arguments": {"keyword": query, "filters": filters}},
                      "id": 2},
                headers=call_headers,
            )
            if call_r.status_code != 200:
                log.warning("xiaohongshu-mcp returned %s: %s", call_r.status_code, call_r.text[:200])
                return []

            result = call_r.json()
    except Exception:
        log.debug("xiaohongshu-mcp call failed", exc_info=True)
        return []

    # Parse MCP tool result — search_feeds returns a JSON text block.
    try:
        content = result.get("result", {}).get("content", [])
    except (AttributeError, KeyError):
        return []

    text = ""
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text += block.get("text", "")
    if not text:
        return []

    rows = _parse_feeds_json(text, limit)
    _dedup_rows(rows)
    return rows[:limit]


def _parse_feeds_json(text: str, limit: int) -> list[Row]:
    """Parse search_feeds' {feeds:[{...}]} JSON output into Row objects.

    xiaohongshu-mcp v2.0.0 feed shape (verified 2026-08):
      {xsecToken, id, modelType, index,
       noteCard: {type, displayTitle,
                  user: {nickname},
                  interactInfo: {likedCount, commentCount, collectedCount,
                                 sharedCount},
                  cover: {url}}}
    The xsecToken is required to open a note's detail page, so we surface the
    canonical xiaohongshu URL built from noteId + xsecToken.
    """
    import json

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Non-JSON (e.g. an error message like "❌ 未登录") — nothing to parse.
        if text.strip().startswith("❌"):
            log.warning("xiaohongshu-mcp not logged in: %s", text.strip()[:60])
        return []

    feeds = data.get("feeds") or []
    if data.get("count") == 0 or not feeds:
        return []

    rows: list[Row] = []
    for f in feeds:
        if not isinstance(f, dict):
            continue
        note_id = str(f.get("id") or f.get("noteId") or "")
        token = f.get("xsecToken") or ""
        # Canonical URL requires the xsec_token (bare noteId isn't readable).
        if note_id:
            url = f"https://www.xiaohongshu.com/explore/{note_id}"
            if token:
                url += f"?xsec_token={token}&xsec_source=pc_search"
        else:
            url = f.get("url") or ""
        # Nested noteCard (v2.0.0) with flat fallbacks.
        nc = f.get("noteCard") or {}
        title = nc.get("displayTitle") or f.get("title") or ""
        user = nc.get("user") or {}
        author = user.get("nickname") or f.get("authorName")
        inter = nc.get("interactInfo") or {}
        engagement = {
            "likes": _int_or_zero(inter.get("likedCount") or f.get("likeCount")),
            "collects": _int_or_zero(inter.get("collectedCount") or f.get("collectCount")),
            "comments": _int_or_zero(inter.get("commentCount") or f.get("commentCount")),
            "shares": _int_or_zero(inter.get("sharedCount") or f.get("sharedCount")),
        }
        rows.append(Row(
            source="xiaohongshu",
            id=note_id or url or title,
            title=title[:200],
            url=url,
            author=author,
            date=str(f.get("publishTime") or ""),
            engagement=engagement,
            text=(f.get("desc") or f.get("description") or "")[:500],
        ))
        if len(rows) >= limit:
            break
    return rows


def _int_or_zero(v) -> int:
    """Coerce a string/int count to int; 0 on empty/None."""
    try:
        return int(v or 0)
    except (ValueError, TypeError):
        return 0


def _dedup_rows(rows: list[Row]) -> None:
    """Remove duplicate rows by URL in-place."""
    seen = set()
    i = len(rows) - 1
    while i >= 0:
        key = rows[i].url
        if key in seen:
            rows.pop(i)
        else:
            seen.add(key)
        i -= 1


@register_source
class Xiaohongshu(Source):
    name = "xiaohongshu"
    description = (
        "小红书 search via xiaohongshu-mcp companion (most stable server-side approach; "
        "set XHS_MCP_URL to enable, default http://localhost:18060/mcp). Requires the "
        "companion to be logged in (get_login_qrcode)."
    )
    host = "www.xiaohongshu.com"
    needs_auth = True
    required_env = ("XHS_MCP_URL",)

    def available(self) -> bool:  # type: ignore[override]
        # Available when XHS_MCP_URL is set; we check connectivity at fetch time
        return bool(os.environ.get("XHS_MCP_URL", "").strip())

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        xhs_mcp_url = os.environ.get("XHS_MCP_URL", "http://localhost:18060/mcp").strip()
        return await _fetch_via_mcp(xhs_mcp_url, query, days, limit)
