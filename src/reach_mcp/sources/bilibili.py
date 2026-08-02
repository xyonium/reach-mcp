"""B站 (Bilibili) video search.

Prefers the community-vetted `bili-cli` (pip install bilibili-cli / uv tool
install bilibili-cli) when it's on PATH - it handles B站's wbi signing and
anti-scraping (412) that a raw API call does not. Falls back to the public
search API when bili-cli is absent. This mirrors Agent Reach's choice (bili-cli
primary) rather than self-rolled scraping.
"""
from __future__ import annotations

import asyncio
import http.cookiejar
import json
import re
import shutil
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from reach_mcp.sources.base import Row, Source, register_source

# Bilibili risk control 412s requests with generic UAs and without cookies.
# Warm up the homepage first (seeds buvid3/b_nut cookies) then call the search
# API with a browser UA + Referer (mirrors Agent-Reach).
_BILI_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
_BILI_REFERER = "https://www.bilibili.com/"


def _bili_opener():
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    # Warm up homepage to seed buvid cookies.
    try:
        opener.open(urllib.request.Request(
            _BILI_REFERER, headers={"User-Agent": _BILI_UA}), timeout=15)
    except Exception:  # noqa: BLE001
        pass
    return opener


def _bili_get_json(opener, url: str, timeout: int = 20) -> dict:
    req = urllib.request.Request(
        url, headers={"User-Agent": _BILI_UA, "Referer": _BILI_REFERER})
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


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
    # bili-cli returns {ok, schema_version, data: [...]} where data is the list
    # of videos. Handle both that and an older {data:{videos:[...]}} envelope.
    data = env.get("data") if isinstance(env, dict) else env
    if isinstance(data, list):
        videos = data
    elif isinstance(data, dict):
        videos = data.get("videos") or data.get("items") or []
    else:
        videos = []
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
    """Fallback: B站 search API with warm-up cookies (avoids 412)."""
    try:
        def _fetch():
            opener = _bili_opener()
            url = ("https://api.bilibili.com/x/web-interface/search/all/v2"
                   f"?keyword={urllib.parse.quote(query)}&page=1")
            return _bili_get_json(opener, url)
        data = await asyncio.to_thread(_fetch)
    except Exception:  # noqa: BLE001
        return []
    rows: list[Row] = []
    if data.get("code") != 0:
        return []
    # search/all/v2 returns {data: {result: [ {result_type:"video", data:[...]}, ... ]}}
    result_sections = (data.get("data") or {}).get("result") or []
    videos: list[dict] = []
    for section in result_sections:
        if section.get("result_type") == "video":
            videos = section.get("data") or []
            break
    for v in videos[:limit]:
        pub = v.get("pubdate")
        date = datetime.fromtimestamp(pub, tz=timezone.utc).isoformat() if pub else None
        # search/all/v2 video items carry author as a plain string
        author = v.get("author") or (v.get("owner") or {}).get("name")
        rows.append(Row(
            source="bilibili", id=v.get("bvid") or "",
            title=re.sub(r"<[^>]+>", "", v.get("title") or ""),
            url=v.get("arcurl") or "",
            author=author, date=date,
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
