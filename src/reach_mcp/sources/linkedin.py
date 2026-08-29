"""LinkedIn public posts search.

Backends, merged by URL:

- **Apify** (`apimaestro/linkedin-posts-search-scraper-no-cookies`, needs
  `APIFY_API_TOKEN`): keyword search over public posts, no LinkedIn cookies
  required. Returns the most results.
- **exa** (`EXA_API_KEY`): includeDomains:linkedin.com + highlights — brings
  fresh publishedDate (verified 2026-08-29: all 5 hits dated 2026-06/08) and
  post-body opening text. The first date-carrying discovery path; Apify rows
  often lack dates.
- **Searxng** (free): `site:linkedin.com` fallback when Apify isn't configured.

Jina's `s.jina.ai` was REMOVED 2026-08-03: it doesn't index LinkedIn (every
query returned 0) and burns one-time grant tokens. `r.jina.ai` stays — it's
what `read_url` uses (reads full LinkedIn post bodies free), and it doesn't
consume search tokens.
"""

from __future__ import annotations

import asyncio
import os

from reach_mcp.sources._exa import search as _exa_search
from reach_mcp.sources._scrapecreators import scrape_search
from reach_mcp.sources.base import Row, Source, get_client, register_source, snip


async def _apify_search(query: str, limit: int) -> list[Row]:
    from reach_mcp.sources._apify import fetch_linkedin_posts, has_token

    if not has_token():
        return []
    return await fetch_linkedin_posts(query, limit)


async def _searxng_search(query: str, limit: int) -> list[Row]:
    """site:linkedin.com scoped query via the same Searxng the web source uses."""
    base = os.environ.get("SEARXNG_URL", "http://searxng:8080").rstrip("/")
    client = get_client()
    try:
        data = await client.get_json(
            base + "/search",
            params={"q": f"site:linkedin.com/posts {query}", "format": "json"},
        )
    except Exception:  # noqa: BLE001
        return []
    rows: list[Row] = []
    for r in (data.get("results") or [])[:limit]:
        url = r.get("url") or ""
        if "linkedin.com" not in url:
            continue
        rows.append(
            Row(
                source="linkedin",
                id=url,
                title=(r.get("title") or "")[:200],
                url=url,
                author=None,
                date=None,
                engagement={},
                text=snip(r.get("content") or ""),
            )
        )
    return rows


@register_source
class LinkedIn(Source):
    name = "linkedin"
    description = (
        "LinkedIn public posts via Apify (APIFY_API_TOKEN) + exa (EXA_API_KEY, "
        "adds post dates) + Searxng site: fallback. Optional ScrapeCreators boost."
    )
    host = "www.linkedin.com"
    needs_auth = False
    required_env = ()

    def available(self) -> bool:  # type: ignore[override]
        # Apify token OR SC key OR exa OR a configured Searxng: any makes it
        # worth a shot.
        return bool(
            os.environ.get("APIFY_API_TOKEN", "").strip()
            or os.environ.get("SCRAPECREATORS_API_KEY", "").strip()
            or os.environ.get("SEARXNG_URL", "").strip()
            or os.environ.get("EXA_API_KEY", "").strip()
        )

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        tasks: list = [_apify_search(query, limit)]
        if os.environ.get("EXA_API_KEY", "").strip():
            # exa runs in parallel — brings publishedDate + body-opening text.
            tasks.append(_exa_search(query, "linkedin.com", "linkedin", limit, days))
        if os.environ.get("SCRAPECREATORS_API_KEY", "").strip():
            tasks.append(scrape_search(get_client(), "linkedin", query, limit))
        if not os.environ.get("APIFY_API_TOKEN", "").strip():
            # Only bother with the Searxng fallback when Apify isn't configured.
            tasks.append(_searxng_search(query, limit))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        seen, rows = set(), []
        first_exc: Exception | None = None
        for batch in results:
            if isinstance(batch, Exception):
                if first_exc is None:
                    first_exc = batch
                continue
            if not batch:
                continue
            for row in batch:
                key = row.url or row.id
                if key and key not in seen:
                    seen.add(key)
                    rows.append(row)
                elif not key:
                    rows.append(row)
        # All backends failed and nothing came back -> surface the error to the
        # pipeline (gateway 503 etc.) instead of a silent EMPTY. Partial success
        # still returns rows; all-empty-without-errors is a genuine no_results.
        if not rows and first_exc is not None:
            raise first_exc
        return rows[:limit]
