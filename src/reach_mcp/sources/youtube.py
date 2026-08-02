"""YouTube transcripts via yt-dlp (free). Returns transcript text per video."""
from __future__ import annotations

import logging
import os

from reach_mcp.sources.base import Row, Source, register_source

log = logging.getLogger(__name__)


async def _fetch_subtitles(query: str, limit: int) -> list[dict]:
    """Search YouTube and pull subtitles for each result. Returns raw dicts.

    Uses a synchronous yt-dlp call (yt-dlp has no first-class async API) — the
    surrounding `asyncio.wait_for(..., timeout=90)` in the pipeline bounds it.
    """
    try:
        from yt_dlp import YoutubeDL
    except ImportError:
        log.warning("yt-dlp not installed; youtube source disabled")
        return []
    proxy = os.environ.get("YTDLP_PROXY")
    opts = {
        "quiet": True, "skip_download": True, "writesubtitles": True,
        "writeautomaticsub": True, "subtitleslangs": ["en", "zh"],
        # NOTE: extract_flat is intentionally False. With extract_flat=True yt-dlp
        # returns shallow entries that carry no subtitles/automatic_captions, so
        # the transcript text would always be empty. Fetching full info per video
        # is slower but is what makes transcripts actually populate.
        "extract_flat": False, "default_search": "ytsearch",
        "playlistend": limit,
        # Default player_client gets bot-walled on datacenter IPs (search returns
        # 0 results). The android client sometimes bypasses the search bot-wall.
        "extractor_args": {"youtube": {"player_client": ["android"]}},
    }
    if proxy:
        opts["proxy"] = proxy
    # Optional YouTube cookies (from browser) to bypass the bot-wall for search
    # and subtitles. Path to a cookies.txt file (Netscape format) or a browser
    # name like "chrome"/"firefox".
    yt_cookies = os.environ.get("YTDLP_COOKIES")
    if yt_cookies:
        if os.path.exists(yt_cookies):
            opts["cookiefile"] = yt_cookies
        else:
            opts["cookiesfrombrowser"] = (yt_cookies,)
    out = []
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
            for e in (info.get("entries") or []):
                out.append({
                    "id": e.get("id", ""), "title": e.get("title", ""),
                    "url": e.get("webpage_url") or f"https://youtu.be/{e.get('id')}",
                    "text": _first_subtitle_text(e),
                    "date": e.get("upload_date"),
                    "engagement": {"views": e.get("view_count") or 0,
                                   "likes": e.get("like_count") or 0},
                })
    except Exception:  # noqa: BLE001
        log.warning("yt-dlp search failed", exc_info=True)
    return out


def _first_subtitle_text(entry: dict) -> str:
    """Best-effort: pull the textual content of the first available subtitle track."""
    subs = entry.get("subtitles") or {}
    auto = entry.get("automatic_captions") or {}
    track = None
    for store in (subs, auto):
        for lang in ("en", "zh"):
            if store.get(lang):
                track = store[lang]
                break
        if track:
            break
    if not track or not isinstance(track, list) or not track:
        return ""
    # yt-dlp subtitle entries are dicts with a 'text' (or 'ext') field
    parts = []
    for seg in track:
        if isinstance(seg, dict) and seg.get("text"):
            parts.append(seg["text"])
    return " ".join(parts)[:1000]


@register_source
class YouTube(Source):
    name = "youtube"
    description = "YouTube video transcripts via yt-dlp (free)."
    host = "www.youtube.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        rows: list[Row] = []
        for v in await _fetch_subtitles(query, limit):
            rows.append(Row(
                source="youtube", id=v["id"], title=v["title"], url=v["url"],
                author=None, date=v.get("date"), engagement=v.get("engagement", {}),
                text=v.get("text") or "",
            ))
        return rows
