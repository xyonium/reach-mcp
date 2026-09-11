"""Jina Reader helper - free, recurring monthly rate-limit quota.

r.jina.ai/{url}  - page reader. Keyless: 20 RPM. With JINA_API_KEY: 500 RPM.

s.jina.ai (Jina's search endpoint) is intentionally NOT used: it doesn't index
LinkedIn (the one place we tried it), and it burns one-time grant tokens.
Web search is covered by Searxng (free) and Brave ($5/mo recurring credits).

Reads go through a Jina-hosted reader pass, which can be slow for heavy pages
(observed >15s behind our proxy) — so this path uses a dedicated read budget,
not the shared fast-request timeout.
"""

from __future__ import annotations

import os

import httpx

from reach_mcp.sources.base import get_client

# Deep-page reads can legitimately exceed the shared 15s request_timeout; we
# only fetch ONE page here, so a wider budget is safe. Overridable via env.
_DEFAULT_READ_TIMEOUT = 90


async def read_url(url: str, timeout: float | None = None) -> str:
    """Fetch a URL's content as clean text via r.jina.ai (Jina Reader).

    Works keyless at 20 RPM; set JINA_API_KEY for 500 RPM. Returns the
    page content as markdown/plain text, or "" on failure.
    """
    key = os.environ.get("JINA_API_KEY", "").strip()
    headers = {"Accept": "text/plain", "X-Retain-Images": "none"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    budget = timeout if timeout is not None else float(
        os.environ.get("REACH_MCP_READ_TIMEOUT", str(_DEFAULT_READ_TIMEOUT))
    )
    target = f"https://r.jina.ai/{url}"
    try:
        # Reuse the shared polite client when one is live (search/fetch_content
        # installs it), with a wider per-request budget for heavy pages.
        try:
            client = get_client()
        except RuntimeError:
            client = None
        if client is not None:
            return await client.get_text(target, headers=headers, timeout=budget)
        async with httpx.AsyncClient(timeout=budget) as direct:
            resp = await direct.get(target, headers=headers)
            resp.raise_for_status()
            return resp.text
    except Exception:
        return ""
