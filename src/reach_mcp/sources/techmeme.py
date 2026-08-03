"""Techmeme tech-news headlines.

Prefers the `techmeme-pp-cli` binary (last30days' vetted CLI, the same
shell-out pattern used for bili/digg/opencli) when on PATH. Falls back to
scraping the public /river page and matching headlines against the query.
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil

from reach_mcp.sources.base import snip, Row, Source, get_client, register_source


def _has_cli() -> bool:
    return shutil.which("techmeme-pp-cli") is not None


async def _fetch_via_cli(query: str, days: int, limit: int) -> list[Row]:
    """`techmeme-pp-cli search <q> --days <N> --json`.

    The CLI's `search` command hits Techmeme's live archive search (back to
    ~2005) with a --days window. Do NOT pass --agent: it implies --compact,
    which on some binary versions strips headline records to {} (see last30days'
    note + printing-press-library PR #1383). --json without --compact keeps the
    populated record shape.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "techmeme-pp-cli", "search", query,
            "--days", str(days), "--json",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
    except Exception:
        return []
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    items = data if isinstance(data, list) else (data.get("items") or data.get("results") or [])
    rows: list[Row] = []
    for i, item in enumerate(items[:limit]):
        url = item.get("link") or item.get("url") or ""
        title = item.get("headline") or item.get("title") or f"Techmeme {i+1}"
        rows.append(Row(
            source="techmeme", id=url or str(i),
            title=title, url=url,
            author=item.get("source") or item.get("author"),
            date=item.get("date") or item.get("time") or item.get("publishedAt"),
            engagement={}, text=snip(item.get("summary") or item.get("description") or ""),
        ))
    return rows


async def _fetch_via_scrape(query: str, limit: int) -> list[Row]:
    """Fallback: scrape /river, keep headlines matching the query.

    The /river page lists outbound story links; we keep only those whose anchor
    text contains the query (case-insensitive) to avoid nav/sponsor noise.
    """
    client = get_client()
    try:
        html = await client.get_text("https://www.techmeme.com/river")
    except Exception:
        return []
    ql = query.lower()
    rows: list[Row] = []
    seen = set()
    for m in re.finditer(r'href="(https?://[^"]+)"[^>]*>([^<]{8,200})</a>', html):
        url, title = m.group(1).strip(), m.group(2).strip()
        if not title or url in seen:
            continue
        if ql and ql not in title.lower():
            continue
        seen.add(url)
        rows.append(Row(source="techmeme", id=url, title=title, url=url,
                        author=None, date=None, engagement={}, text=""))
        if len(rows) >= limit:
            break
    return rows


@register_source
class Techmeme(Source):
    name = "techmeme"
    description = (
        "Techmeme editorial tech-news via techmeme-pp-cli (preferred) or "
        "/river scrape fallback. Free, no key."
    )
    host = "www.techmeme.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        if _has_cli():
            rows = await _fetch_via_cli(query, days, limit)
            if rows:
                return rows
        return await _fetch_via_scrape(query, limit)
