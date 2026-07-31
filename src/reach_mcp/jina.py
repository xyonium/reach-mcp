"""Jina Reader / Search helpers - free, recurring monthly-quota APIs.

r.jina.ai/{url}  - page reader. Keyless: 20 RPM. With JINA_API_KEY: 500 RPM.
s.jina.ai/{q}    - web search. Requires JINA_API_KEY (free key works).

Both are recurring monthly rate-limit quotas, NOT one-time credits.
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


async def jina_search(query: str, limit: int = 20) -> list[dict]:
    """Web search via s.jina.ai (requires free JINA_API_KEY).

    Returns a list of {title, url, content, publishedTime} dicts.
    """
    client = get_client()
    key = os.environ.get("JINA_API_KEY", "").strip()
    if not key:
        return []
    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "X-Retain-Images": "none",
    }
    try:
        data = await client.get_json(
            "https://s.jina.ai/",
            params={"q": query, "count": str(min(limit, 20))},
            headers=headers,
        )
    except Exception:
        return []
    return data.get("data") or []
