"""LinkedIn via Jina (free, agent-reach's approach) + optional ScrapeCreators.

Agent Reach uses Jina Reader for LinkedIn's basic content. reach-mcp follows
the same approach:

- Primary: Jina search (`s.jina.ai`) scoped to linkedin.com, returns public
  posts/articles. Needs a free `JINA_API_KEY` (free monthly rate-limit quota,
  not one-time credits). Without a key, s.jina.ai is blocked.
- Fallback reader: `r.jina.ai` reads the body of any LinkedIn URL (free even
  without a key, 20 RPM). Not used for discovery, only if a URL is known.
- Optional boost: ScrapeCreators (`SCRAPECREATORS_API_KEY`) - 100 one-time
  credits, runs in parallel only if a key is set.

Jina's free key is a recurring monthly rate-limit quota (20 RPM no key,
500 RPM free key, 5000 RPM paid) - it is NOT a one-time credit.
"""
from __future__ import annotations

import asyncio
import os
import re

from reach_mcp.sources._scrapecreators import scrape_search
from reach_mcp.sources.base import Row, Source, get_client, register_source


async def _jina_search(query: str, limit: int) -> list[Row]:
    """Search LinkedIn via Jina's s.jina.ai endpoint (needs free JINA_API_KEY)."""
    client = get_client()
    key = os.environ.get("JINA_API_KEY", "").strip()
    if not key:
        return []  # s.jina.ai is blocked without a key
    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "X-Retain-Images": "none",
    }
    # Scope to LinkedIn public content (posts + pulse articles)
    scoped = f"site:linkedin.com/posts OR site:linkedin.com/pulse {query}"
    try:
        data = await client.get_json(
            "https://s.jina.ai/",
            params={"q": scoped, "count": str(min(limit, 20))},
            headers=headers,
        )
    except Exception:
        return []
    rows: list[Row] = []
    results = data.get("data") or []
    for r in results[:limit]:
        url = r.get("url") or ""
        title = (r.get("title") or "")[:200]
        content = r.get("content") or ""
        rows.append(Row(
            source="linkedin", id=url or title, title=title, url=url,
            author=None, date=r.get("publishedTime"),
            engagement={}, text=content[:500],
        ))
    return rows


def _parse_jina_reader_markdown(md: str) -> list[Row]:
    """Best-effort extraction of LinkedIn post/article links from a Jina reader
    markdown blob. Jina reader returns the page text; we pull linkedin URLs."""
    rows: list[Row] = []
    seen = set()
    for m in re.finditer(
        r"https?://(?:www\.)?linkedin\.com/(?:posts|pulse)/[\w-]+", md
    ):
        url = m.group(0).rstrip(").,]")
        if url in seen:
            continue
        seen.add(url)
        # Try to grab a nearby title line
        start = md.rfind("\n", 0, m.start())
        line = md[start:m.start()].strip(" \n#*")
        title = (line[:200] if line else "LinkedIn post") or "LinkedIn post"
        rows.append(Row(source="linkedin", id=url, title=title, url=url,
                        author=None, date=None, engagement={}, text=""))
    return rows


@register_source
class LinkedIn(Source):
    name = "linkedin"
    description = (
        "LinkedIn public posts/articles via Jina (free, monthly rate-limit quota; "
        "set JINA_API_KEY for search). Optional ScrapeCreators boost "
        "(SCRAPECREATORS_API_KEY, 100 one-time credits)."
    )
    host = "www.linkedin.com"
    needs_auth = False
    required_env = ()

    def available(self) -> bool:  # type: ignore[override]
        # Available if Jina key is set OR an SC key is set for the boost path.
        return bool(
            os.environ.get("JINA_API_KEY", "").strip()
            or os.environ.get("SCRAPECREATORS_API_KEY", "").strip()
        )

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        tasks: list = [_jina_search(query, limit)]
        if os.environ.get("SCRAPECREATORS_API_KEY", "").strip():
            tasks.append(scrape_search(get_client(), "linkedin", query, limit))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        seen, rows = set(), []
        for batch in results:
            if isinstance(batch, Exception) or not batch:
                continue
            for row in batch:
                key = row.url or row.id
                if key and key not in seen:
                    seen.add(key)
                    rows.append(row)
                elif not key:
                    rows.append(row)
        return rows[:limit]
