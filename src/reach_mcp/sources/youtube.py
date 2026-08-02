"""YouTube search + transcripts via yt-dlp CLI (free).

Backend: a **pure CLI subprocess** run of ``yt-dlp --flat-playlist --dump-json
ytsearchN:<query>``. Verified 2026-08 against the mcpo container's datacenter
IP: the search-list page passes even with a captcha challenge active, whereas
**full (deep) extraction per-video triggers the captcha/bot-wall and returns 0**
("Video unavailable. YouTube is requiring a captcha challenge"). So search uses
``--flat-playlist`` (shallow; id/title/views/date, no subtitles), and captions
are fetched per-video separately (best-effort — they may also be captcha'd on a
datacenter IP). Cookies (YTDLP_COOKIES) and a residential proxy (YTDLP_PROXY)
both help; cookies are the practical fix from the container.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil

from reach_mcp.sources.base import Row, Source, register_source

log = logging.getLogger(__name__)

# --flat-playlist = shallow search-list extraction (id/title/views/date).
# Deep per-video extraction (without it) trips the captcha on datacenter IPs.
_YTDLP_BASE = [
    "yt-dlp",
    "--ignore-config",
    "--no-cookies-from-browser",
    "--no-warnings",
    "--no-download",
    "--flat-playlist",
    "--dump-json",
]


def _ytdlp_common_args(base: list[str]) -> list[str]:
    """Return proxy/cookies args to prepend to a yt-dlp command.

    Mirrors the env contract documented in docs/CREDENTIALS.md:
      - YTDLP_PROXY: residential proxy to bypass the datacenter-IP bot-wall.
      - YTDLP_COOKIES: path to a cookies.txt file (Netscape format) OR a browser
        name (chrome/firefox) — see docs/CREDENTIALS.md §9.5.

    When a browser-name cookie is requested, the base command's
    ``--no-cookies-from-browser`` must be dropped (last flag wins, so leaving it
    would silently kill the cookie path).
    """
    extra: list[str] = []
    proxy = os.environ.get("YTDLP_PROXY")
    if proxy:
        extra += ["--proxy", proxy]
    yt_cookies = os.environ.get("YTDLP_COOKIES")
    if yt_cookies:
        if os.path.exists(yt_cookies):
            extra += ["--cookies", yt_cookies]
        else:
            extra += ["--cookies-from-browser", yt_cookies]
            base[:] = [a for a in base if a != "--no-cookies-from-browser"]
    return extra


async def _search_videos(query: str, limit: int) -> list[dict]:
    """Search YouTube via the yt-dlp CLI (search-list page only)."""
    if shutil.which("yt-dlp") is None:
        log.warning("yt-dlp not installed; youtube source disabled")
        return []
    cmd = [*_ytdlp_common_args(list(_YTDLP_BASE)), f"ytsearch{limit}:{query}"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=90)
    except Exception:  # noqa: BLE001
        log.debug("yt-dlp search subprocess failed", exc_info=True)
        return []
    if not stdout.strip():
        err = stderr.decode("utf-8", "replace")[:200]
        # Surface the common bot-wall / auth failures so the reason for 0
        # results is diagnosable (e.g. container datacenter IP needs a
        # residential proxy or cookies).
        if "Sign in to confirm" in err or "bot" in err.lower():
            log.warning(
                "yt-dlp youtube search bot-walled (0 results): %s. "
                "The container's datacenter IP is blocked; use a residential "
                "proxy (YTDLP_PROXY) or cookies (YTDLP_COOKIES).", err.splitlines()[-1][:80]
            )
        elif err:
            log.warning("yt-dlp youtube search returned nothing: %s", err.splitlines()[-1][:80])
        return []
    out: list[dict] = []
    for line in stdout.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            v = json.loads(line)
        except json.JSONDecodeError:
            continue
        out.append({
            "id": v.get("id", ""),
            "title": v.get("title", ""),
            "url": f"https://www.youtube.com/watch?v={v.get('id', '')}",
            "text": _first_subtitle_text(v),  # shallow; "" unless the search payload carried subs
            "date": v.get("upload_date"),
            "engagement": {
                "views": v.get("view_count") or 0,
                "likes": v.get("like_count") or 0,
                "comments": v.get("comment_count") or 0,
            },
        })
    # Bounded transcript backfill for the top results (mirrors last30days'
    # TRANSCRIPT_LIMITS approach): the search-list payload carries no subs, so
    # fetch captions per-video via `--write-auto-subs`. Cap the count so a slow
    # video never dominates the run. Per-video fetch is a subprocess with its
    # own timeout; failures leave text empty (no hard fail).
    backfill = max(1, min(limit, 2))
    for v in out[:backfill]:
        if v["text"]:
            continue
        v["text"] = await _fetch_transcript(v["id"])
    return out[:limit]


async def _fetch_transcript(video_id: str) -> str:
    """Fetch a video's auto-captions via the yt-dlp CLI (VTT -> plaintext).

    Mirrors last30days' _fetch_transcript_ytdlp: `yt-dlp --write-auto-subs
    --sub-lang en.* --sub-format vtt --skip-download`. The caption tracks live
    on the video page; this subprocess route does not trip the search bot-wall.
    Returns "" on any failure (video without captions, timeout, bot-gate).
    """
    import tempfile

    with tempfile.TemporaryDirectory(prefix="reach-yt-") as tmp:
        cmd = [
            "yt-dlp", "--ignore-config", "--no-cookies-from-browser",
            "--write-auto-subs", "--sub-lang", "en.*", "--sub-format", "vtt",
            "--skip-download", "--no-warnings", "-o", f"{tmp}/%(id)s",
            f"https://www.youtube.com/watch?v={video_id}",
        ]
        cmd = [*_ytdlp_common_args(cmd), *cmd]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=45)
        except Exception:  # noqa: BLE001
            log.debug("yt-dlp transcript failed for %s", video_id, exc_info=True)
            return ""
        # The VTT may be written as <id>.en.vtt or <id>.en-orig.vtt
        vtt = _read_vtt(tmp, video_id)
        if not vtt:
            return ""
        return _clean_vtt(vtt)[:1000]


def _read_vtt(tmp_dir: str, video_id: str) -> str:
    """Return the concatenated plaintext of any VTT files for video_id in tmp_dir."""
    import glob

    files = sorted(glob.glob(f"{tmp_dir}/{video_id}*.vtt"))
    if not files:
        return ""
    parts = []
    for f in files:
        with open(f, encoding="utf-8", errors="replace") as fh:
            parts.append(fh.read())
    return "\n".join(parts)


def _clean_vtt(vtt_text: str) -> str:
    """Strip VTT headers/timestamps/cue tags, return plaintext transcript."""
    import re

    # Drop the WEBVTT header and cue metadata lines; keep the actual words.
    lines = []
    for raw in vtt_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("WEBVTT") or line.startswith("Kind:") \
                or line.startswith("Language:") or line.startswith("NOTE"):
            continue
        if "-->" in line:  # timestamp cue line
            continue
        # Inline cue tags: <00:00:00.320><c> President</c> -> "President"
        line = re.sub(r"<[^>]+>", "", line)
        line = line.replace("&nbsp;", " ").replace("&#39;", "'").strip()
        if line:
            lines.append(line)
    return " ".join(lines).strip()


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
    description = "YouTube video transcripts via yt-dlp CLI (free, no cookies)."
    host = "www.youtube.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        rows: list[Row] = []
        for v in await _search_videos(query, limit):
            rows.append(Row(
                source="youtube", id=v["id"], title=v["title"], url=v["url"],
                author=None, date=v.get("date"), engagement=v.get("engagement", {}),
                text=v.get("text") or "",
            ))
        return rows
