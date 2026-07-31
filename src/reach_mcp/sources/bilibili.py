"""B站 (Bilibili) video search.

Prefers the community-vetted `bili-cli` (pip install bilibili-cli / uv tool
install bilibili-cli) when it's on PATH - it handles B站's wbi signing and
anti-scraping (412) that a raw API call does not. Falls back to the public
search API when bili-cli is absent. This mirrors Agent Reach's choice (bili-cli
primary) rather than self-rolled scraping.
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
from datetime import datetime, timezone

from reach_mcp.sources.base import Row, Source, get_client, register_source


def _has_cli() -> bool:
    return shutil.which("bili") is not None


async def _fetch_via_cli(query: str, limit: int) -> list[Row]:
    """Search via `bili search ... --type video --json`. Output is a normalized
    envelope {ok, schema_version, data:{videos:[...]}, error}."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "bili", "search", query, "--type", "video",
            "--max", str(min(limit, 30)), "--json",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=90)
    except Exception:
        return []
    try:
        env = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    rows: list[Row] = []
    data = env.get("data") or {}
    videos = data.get("videos") or data.get("items") or []
    for v in videos[:limit]:
        rows.append(_row_from_cli(v))
    return rows


def _row_from_cli(v: dict) -> Row:
    bvid = v.get("bvid") or v.get("id") or ""
    title = re.sub(r"<[^>]+>", "", v.get("title") or "")
    owner = v.get("owner") or v.get("author") or {}
    name = owner if isinstance(owner, str) else owner.get("name")
    pub = v.get("pubdate") or v.get("pub_date") or v.get("created")
    date = None
    if pub:
        try:
            date = datetime.fromtimestamp(int(pub), tz=timezone.utc).isoformat()
        except (TypeError, ValueError):
            date = str(pub)
    return Row(
        source="bilibili", id=str(bvid),
        title=title,
        url=v.get("url") or v.get("arcurl") or f"https://www.bilibili.com/video/{bvid}",
        author=name, date=date,
        engagement={"play": v.get("play") or v.get("view") or 0,
                    "reply": v.get("reply") or v.get("video_review") or 0,
                    "like": v.get("like") or 0},
        text=(v.get("description") or v.get("desc") or "")[:500],
    )


async def _fetch_via_api(query: str, limit: int) -> list[Row]:
    """Fallback: B站 public search API (no login). May hit 412 under load."""
    client = get_client()
    try:
        data = await client.get_json(
            "https://api.bilibili.com/x/web-interface/search/type",
            params={"search_type": "video", "keyword": query,
                    "page_size": str(min(limit, 30))},
            headers={"User-Agent": "reach-mcp/0.1"},
        )
    except Exception:
        return []
    rows: list[Row] = []
    for v in ((data.get("data") or {}).get("result") or [])[:limit]:
        pub = v.get("pubdate")
        date = datetime.fromtimestamp(pub, tz=timezone.utc).isoformat() if pub else None
        owner = v.get("owner") or {}
        rows.append(Row(
            source="bilibili", id=v.get("bvid") or "",
            title=re.sub(r"<[^>]+>", "", v.get("title") or ""),
            url=v.get("arcurl") or "",
            author=owner.get("name"), date=date,
            engagement={"play": v.get("play") or 0, "reply": v.get("video_review") or 0},
            text=(v.get("description") or "")[:500],
        ))
    return rows


@register_source
class Bilibili(Source):
    name = "bilibili"
    description = (
        "B站 video search via bili-cli (preferred; handles anti-scraping) or "
        "the public API fallback. Free, no login."
    )
    host = "api.bilibili.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        if _has_cli():
            rows = await _fetch_via_cli(query, limit)
            if rows:
                return rows
        return await _fetch_via_api(query, limit)
