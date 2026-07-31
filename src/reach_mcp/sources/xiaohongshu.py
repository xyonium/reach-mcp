"""小红书 (Xiaohongshu/RED) via xiaohongshu-mcp companion service.

Uses the community-vetted xiaohongshu-mcp Go server (15K+ GitHub stars) as
the backend. This is the most stable server-side approach — xiaohongshu-mcp
handles auth, cookie refresh, and request signing internally.

Requirements:
  - xiaohongshu-mcp running at XHS_MCP_URL (default http://localhost:18060/mcp)
  - xiaohongshu-mcp logged in (run the login helper once)
  - Docker: add xiaohongshu-mcp as a companion service in compose (see docker-compose.yml)

Without the companion service the source degrades gracefully (returns []).
"""
from __future__ import annotations

import logging
import os

from reach_mcp.sources.base import Row, Source, register_source

log = logging.getLogger(__name__)

# xiaohongshu-mcp tool name
_SEARCH_TOOL = "search_notes"


async def _fetch_via_mcp(url: str, query: str, limit: int) -> list[Row]:
    """Fetch search results from xiaohongshu-mcp via JSON-RPC over HTTP."""
    import httpx

    endpoint = url.rstrip("/") + "/message"
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

            # Step 2: call search_notes tool
            call_headers = {"Content-Type": "application/json",
                          "Accept": "application/json, text/event-stream"}
            if sid:
                call_headers["mcp-session-id"] = sid

            call_r = await hclient.post(
                endpoint,
                json={"jsonrpc": "2.0", "method": "tools/call",
                      "params": {"name": _SEARCH_TOOL,
                                "arguments": {"keyword": query, "limit": min(limit, 20)}},
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

    # Parse MCP tool result
    try:
        content = result.get("result", {}).get("content", [])
    except (AttributeError, KeyError):
        return []

    rows: list[Row] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        text = block.get("text", "")
        if not text:
            continue
        # xiaohongshu-mcp returns markdown; extract note entries
        for note in _parse_xhs_markdown(text):
            rows.append(note)

    _dedup_rows(rows)
    return rows[:limit]


def _parse_xhs_markdown(text: str) -> list[Row]:
    """Parse xiaohongshu-mcp's markdown output into Row objects."""
    import re

    rows: list[Row] = []
    # xiaohongshu-mcp returns structured markdown like:
    # **Title** | ❤️ 120 | 💬 34 | 🔗 https://...
    # or JSON-style blocks
    lines = text.split("\n")
    current_title = ""
    current_url = ""
    current_likes = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Try to extract URL + title patterns
        url_m = re.search(r"https?://(?:www\.)?xiaohongshu\.com/\S+", line)
        if url_m:
            current_url = url_m.group(0).rstrip(")[].,;")
        # Title: bold text or first substantial text
        title_m = re.search(r"\*\*(.+?)\*\*", line)
        if title_m:
            current_title = title_m.group(1).strip()
        elif current_title and not current_url and len(line) > 10 and not line.startswith("http"):
            # Might be a title on its own line after URL
            pass
        # Engagement: ❤️ 120  💬 34  ⭐ 56
        like_m = re.search(r"[❤👍]\S*\s*(\d[\d,]*)", line)
        if like_m:
            try:
                current_likes = int(like_m.group(1).replace(",", ""))
            except ValueError:
                pass

        if current_url and current_title:
            rows.append(Row(
                source="xiaohongshu", id=current_url,
                title=current_title[:200], url=current_url,
                author=None, date=None,
                engagement={"likes": current_likes},
                text=line[:500],
            ))
            current_title = ""
            current_url = ""
            current_likes = 0

    return rows


def _dedup_rows(rows: list[Row]) -> None:
    """Remove duplicate rows by URL in-place."""
    seen = set()
    # Iterate backwards so we can pop
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
        "set XHS_MCP_URL to enable, default http://localhost:18060/mcp)."
    )
    host = "www.xiaohongshu.com"
    needs_auth = True
    required_env = ("XHS_MCP_URL",)

    def available(self) -> bool:  # type: ignore[override]
        # Available when XHS_MCP_URL is set; we check connectivity at fetch time
        return bool(os.environ.get("XHS_MCP_URL", "").strip())

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        xhs_mcp_url = os.environ.get("XHS_MCP_URL", "http://localhost:18060/mcp").strip()
        return await _fetch_via_mcp(xhs_mcp_url, query, limit)
