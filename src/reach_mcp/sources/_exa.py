"""exa.ai neural search backend — domain-scoped discovery with answer highlights.

POST api.exa.ai/search with includeDomains scopes a query to one site; the
contents.highlights option returns ANSWER-content snippets that bypass the
Cloudflare wall (contents.text gets the login shell on quora/linkedin, so we
deliberately don't request it — wasted cost). publishedDate comes back on many
results, making this the first date-carrying discovery path for quora/linkedin.

Metered: $0.007/neural search (auto type). EXA_API_KEY env; absent key = cheap
no-op so sources fall through to their free backends. Live-verified 2026-08-29:
quora.com returns 5/5 question pages with answer core-sentences in highlights;
linkedin.com returns 5/5 posts all with fresh publishedDate.
"""

from __future__ import annotations

import os

from reach_mcp.sources.base import Row, snip


def _base() -> str:
    """EXA_BASE_URL overrides the default api.exa.ai — for a key-rotator/proxy
    gateway (same pattern as APIFY_BASE_URL). Trailing slash stripped."""
    return os.environ.get("EXA_BASE_URL", "").strip().rstrip("/") or "https://api.exa.ai"


def available() -> bool:
    return bool(os.environ.get("EXA_API_KEY", "").strip())


async def search(
    query: str, domain: str, source: str, limit: int, days: int = 0
) -> list[Row]:
    """Neural search scoped to `domain`, Rows tagged as `source`.

    days>0 adds a startPublishedDate filter (ISO). Highlights become the row
    text (answer content); title stays the question/post title.
    """
    from reach_mcp.sources.base import get_client

    key = os.environ.get("EXA_API_KEY", "").strip()
    if not key:
        return []
    body: dict = {
        "query": query,
        "includeDomains": [domain],
        "numResults": min(limit, 100),
        "type": "auto",
        "contents": {"highlights": True},  # NOT text — CF-walled on these sites
    }
    if days and days > 0:
        from datetime import datetime, timedelta, timezone

        start = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        body["startPublishedDate"] = start
    try:
        data = await get_client().post_json(
            f"{_base()}/search",
            json=body,
            headers={"x-api-key": key, "Content-Type": "application/json"},
        )
    except Exception:  # noqa: BLE001
        return []
    rows: list[Row] = []
    for r in (data.get("results") or [])[:limit]:
        url = str(r.get("url") or "")
        title = str(r.get("title") or "").strip()
        if not url or not title:
            continue
        highlights = r.get("highlights") or []
        text = highlights[0] if highlights else ""
        rows.append(
            Row(
                source=source,
                id=str(r.get("id") or url),
                title=title,
                url=url,
                author=r.get("author") or None,
                date=r.get("publishedDate") or None,
                engagement={},
                text=snip(text),
            )
        )
    return rows
