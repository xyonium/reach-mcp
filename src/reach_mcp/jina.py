"""Jina Reader helper - free, recurring monthly rate-limit quota.

r.jina.ai/{url}  - page reader. Keyless: 20 RPM. With JINA_API_KEY: 500 RPM.

s.jina.ai (Jina's search endpoint) is intentionally NOT used: it doesn't index
LinkedIn (the one place we tried it), and it burns one-time grant tokens.
Web search is covered by Searxng (free) and Brave ($5/mo recurring credits).
"""
from __future__ import annotations

import os

from reach_mcp.sources.base import get_client


async def read_url(url: str) -> str:
    """Fetch a URL's content as clean text via r.jina.ai (Jina Reader).

    Works keyless at 20 RPM; set JINA_API_KEY for 500 RPM. Returns the
    page content as markdown/plain text, or "" on failure.
    """
    client = get_client()
    key = os.environ.get("JINA_API_KEY", "").strip()
    headers = {"Accept": "text/plain", "X-Retain-Images": "none"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        return await client.get_text(
            f"https://r.jina.ai/{url}",
            headers=headers,
        )
    except Exception:
        return ""
