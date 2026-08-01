"""小宇宙 (Xiaoyuzhou) podcast search + Whisper transcription.

Search requires a 小宇宙 login token (`XIAOYUZHOU_ACCESS_TOKEN`, obtained via
phone-SMS login — see docs/CREDENTIALS.md). Without a token the source returns
[] (gated off). Transcription uses an OpenAI-compatible Whisper endpoint
(`WHISPER_BASE_URL`, default http://gpu.savorcare.com:8080/v1) — point it at
any self-hosted LocalAI; the API key may be empty.
"""
from __future__ import annotations

import asyncio
import logging
import os

from reach_mcp.config import get_settings
from reach_mcp.sources.base import Row, Source, get_client, register_source
from reach_mcp.whisper import download_audio, transcribe

log = logging.getLogger(__name__)

# Xiaoyuzhou app headers (mirrors the reference xiaoyuzhou-api client).
_UA = "Xiaoyuzhou/2.57.1 (build:1576; iOS 17.4.1)"
_APP_HEADERS = {
    "User-Agent": _UA,
    "BundleID": "app.podcast.cosmos",
    "App-Version": "2.57.1",
    "x-jike-device-id": "81ADBFD6-6921-482B-9AB9-A29E7CC7BB55",
    "Accept-Language": "zh-Hans-CN;q=0.9",
}
_API = "https://api.xiaoyuzhoufm.com"


def _token() -> str:
    return os.environ.get("XIAOYUZHOU_ACCESS_TOKEN", "").strip()


def _headers() -> dict:
    h = dict(_APP_HEADERS)
    t = _token()
    if t:
        h["x-jike-access-token"] = t
    return h


async def _search_podcasts(client, query: str) -> list[dict]:
    """Search podcasts by keyword; returns list of podcast dicts (with pid)."""
    try:
        data = await client.post_json(
            f"{_API}/v1/search/create",
            json={"keyword": query, "type": "PODCAST", "loadMoreKey": {}},
            headers=_headers(),
        )
    except Exception:  # noqa: BLE001
        log.debug("xiaoyuzhou search failed", exc_info=True)
        return []
    pods = (data.get("data") or {}).get("data") or []
    # /v1/search/create returns {data:{data:[{podcast:{...}}]}} for podcasts
    out = []
    for item in pods:
        pod = item.get("podcast") or item
        if isinstance(pod, dict) and pod.get("pid"):
            out.append(pod)
    return out


async def _episodes(client, pid: str, limit: int) -> list[dict]:
    """Fetch a podcast's recent episodes."""
    try:
        data = await client.post_json(
            f"{_API}/v1/episode/list",
            json={"pid": pid, "order": "desc", "loadMoreKey": {}},
            headers=_headers(),
        )
    except Exception:  # noqa: BLE001
        log.debug("xiaoyuzhou episode list failed", exc_info=True)
        return []
    return (data.get("data") or {}).get("data") or []


def _episode_audio_url(e: dict) -> str:
    """Extract the playable audio URL from an episode dict."""
    media = e.get("media") or {}
    src = media.get("source") or {}
    url = src.get("url") or ""
    if not url:
        url = (e.get("enclosure") or {}).get("url") or ""
    return url


async def _transcribe_episode(audio_url: str) -> str:
    """Download + transcribe one episode's audio; "" on any failure."""
    settings = get_settings()
    audio = await download_audio(audio_url, settings)
    if not audio:
        return ""
    # Bound per-episode transcription so a slow/huge file can't stall the
    # whole search (pipeline already wraps fetch in a 90s timeout).
    try:
        return await asyncio.wait_for(transcribe(audio, settings), timeout=60)
    except asyncio.TimeoutError:
        log.debug("xiaoyuzhou transcription timed out: %s", audio_url)
        return ""


@register_source
class Xiaoyuzhou(Source):
    name = "xiaoyuzhou"
    description = (
        "小宇宙 podcast search + Whisper transcription. Search needs "
        "XIAOYUZHOU_ACCESS_TOKEN (phone-SMS login); transcription via "
        "OpenAI-compatible WHISPER_BASE_URL."
    )
    host = "api.xiaoyuzhoufm.com"
    needs_auth = True
    required_env = ("XIAOYUZHOU_ACCESS_TOKEN",)

    def available(self) -> bool:  # type: ignore[override]
        return bool(_token())

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        if not _token():
            return []
        client = get_client()
        rows: list[Row] = []
        # Search podcasts, then pull episodes for the top ones. Keep it bounded:
        # 2 podcasts x up to (limit/2) episodes each.
        pods = await _search_podcasts(client, query)
        per_pod = max(1, (limit + 1) // 2)
        for pod in pods[:2]:
            eps = await _episodes(client, pod.get("pid", ""), per_pod)
            for e in eps[:per_pod]:
                audio_url = _episode_audio_url(e)
                text = await _transcribe_episode(audio_url) if audio_url else ""
                rows.append(Row(
                    source="xiaoyuzhou",
                    id=e.get("eid") or "",
                    title=e.get("title") or "",
                    url=e.get("url") or f"https://www.xiaoyuzhoufm.com/episode/{e.get('eid')}",
                    author=pod.get("title"),
                    date=e.get("pubDate") or e.get("pub_date"),
                    engagement={},
                    text=text[:500],
                ))
                if len(rows) >= limit:
                    return rows
        return rows
