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

import httpx

from reach_mcp.config import get_settings
from reach_mcp.sources.base import snip, Row, Source, get_client, register_source
from reach_mcp.whisper import download_audio, transcribe

log = logging.getLogger(__name__)

# Xiaoyuzhou app headers — mirror the reference xiaoyuzhou-api client exactly.
# The API rejects requests missing the app headers or the refresh token
# ("无效参数"/400). device-id is derived from the refresh token.
_UA = "Xiaoyuzhou/2.57.1 (build:1576; iOS 17.4.1)"
_APP_HEADERS = {
    "Host": "api.xiaoyuzhoufm.com",
    "User-Agent": _UA,
    "Market": "AppStore",
    "App-BuildNo": "1576",
    "OS": "ios",
    "Manufacturer": "Apple",
    "BundleID": "app.podcast.cosmos",
    "Connection": "keep-alive",
    "Accept-Language": "zh-Hant-HK;q=1.0, zh-Hans-CN;q=0.9",
    "Model": "iPhone14,2",
    "app-permissions": "4",
    "Accept": "*/*",
    "App-Version": "2.57.1",
    "WifiConnected": "true",
    "OS-Version": "17.4.1",
    "x-custom-xiaoyuzhou-app-dev": "",
    "abtest-info": "{}",
    "Timezone": "Asia/Shanghai",
}
_API = "https://api.xiaoyuzhoufm.com"


def _token(name: str) -> str:
    return os.environ.get(name, "").strip()


def _device_id(token: str) -> str:
    """Deterministic device id derived from the refresh token (matches upstream)."""
    import re
    if not token or len(token) < 10:
        return "81ADBFD6-6921-482B-9AB9-A29E7CC7BB55"
    normalized = re.sub(r"[^a-f0-9]", "", token.lower())
    if len(normalized) < 32:
        normalized = normalized.ljust(32, "0")
    normalized = normalized[:32]
    return (f"{normalized[:8]}-{normalized[8:12]}-"
            f"4{normalized[13:16]}-a{normalized[17:20]}-{normalized[20:32]}").upper()


def _headers() -> dict:
    h = dict(_APP_HEADERS)
    access = _token("XIAOYUZHOU_ACCESS_TOKEN")
    refresh = _token("XIAOYUZHOU_REFRESH_TOKEN")
    if access:
        h["x-jike-access-token"] = access
    if refresh:
        h["x-jike-refresh-token"] = refresh
    h["x-jike-device-id"] = _device_id(refresh or access)
    return h


async def _refresh_access_token() -> bool:
    """Refresh the access token via app_auth_tokens.refresh (needs refresh token).

    On success, writes the new access token back to the environment so
    subsequent calls in this process use it. Returns True on success.
    """
    refresh = _token("XIAOYUZHOU_REFRESH_TOKEN")
    if not refresh:
        return False
    try:
        async with httpx.AsyncClient(timeout=30) as hc:
            r = await hc.post(
                f"{_API}/app_auth_tokens.refresh",
                headers={"x-jike-refresh-token": refresh},
            )
            if r.status_code != 200:
                log.warning("xiaoyuzhou refresh failed: %s", r.status_code)
                return False
            new_access = r.headers.get("x-jike-access-token", "")
            if not new_access:
                return False
            os.environ["XIAOYUZHOU_ACCESS_TOKEN"] = new_access
            log.info("xiaoyuzhou access token refreshed")
            return True
    except Exception:  # noqa: BLE001
        log.debug("xiaoyuzhou refresh error", exc_info=True)
        return False


async def _search_podcasts(client, query: str) -> list[dict]:
    """Search podcasts by keyword; returns list of podcast dicts (with pid).

    Note: do NOT send loadMoreKey:{} — the API returns "无效参数" (400) on an
    empty loadMoreKey. Mirrors the reference xiaoyuzhou-api client. On 401
    (expired access token), refresh and retry once.
    """
    try:
        data = await client.post_json(
            f"{_API}/v1/search/create",
            json={"keyword": query, "type": "PODCAST"},
            headers=_headers(),
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401 and await _refresh_access_token():
            try:
                data = await client.post_json(
                    f"{_API}/v1/search/create",
                    json={"keyword": query, "type": "PODCAST"},
                    headers=_headers(),
                )
            except Exception:  # noqa: BLE001
                return []
        else:
            log.debug("xiaoyuzhou search failed", exc_info=True)
            return []
    except Exception:  # noqa: BLE001
        log.debug("xiaoyuzhou search failed", exc_info=True)
        return []
    # /v1/search/create returns {data: [ {type:PODCAST, pid, title, ...} ]}
    pods = data.get("data") if isinstance(data, dict) else data
    if not isinstance(pods, list):
        return []
    out = []
    for item in pods:
        if isinstance(item, dict) and item.get("pid"):
            out.append(item)
    return out


async def _episodes(client, pid: str, limit: int) -> list[dict]:
    """Fetch a podcast's recent episodes (no empty loadMoreKey — API rejects it)."""
    try:
        data = await client.post_json(
            f"{_API}/v1/episode/list",
            json={"pid": pid, "order": "desc"},
            headers=_headers(),
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401 and await _refresh_access_token():
            try:
                data = await client.post_json(
                    f"{_API}/v1/episode/list",
                    json={"pid": pid, "order": "desc"},
                    headers=_headers(),
                )
            except Exception:  # noqa: BLE001
                return []
        else:
            log.debug("xiaoyuzhou episode list failed", exc_info=True)
            return []
    except Exception:  # noqa: BLE001
        log.debug("xiaoyuzhou episode list failed", exc_info=True)
        return []
    eps = data.get("data") if isinstance(data, dict) else data
    return eps if isinstance(eps, list) else []


def _episode_audio_url(e: dict) -> str:
    """Extract the playable audio URL from an episode dict."""
    media = e.get("media") or {}
    src = media.get("source") or {}
    url = src.get("url") or ""
    if not url:
        url = (e.get("enclosure") or {}).get("url") or ""
    return url


# Whisper upload cap. The 25 MB figure in OpenAI's docs applies to the hosted
# API; self-hosted LocalAI gateways accept far more. Measured against the
# configured gateway (2026-08-03): 50.4 MB / 60-min audio transcribed in
# ~137 s, and 86.4 MB / 120-min in ~371 s — both HTTP 200. We cap at 90 MB as
# a pragmatic ceiling (~2 h episodes); beyond that a single episode would
# stall the search past the wrapper timeout. Oversized audio is SKIPPED, not
# compressed (no ffmpeg dependency).
_MAX_AUDIO_BYTES = 90 * 1024 * 1024
# Measured ~3.1 s per minute of audio on the configured GPU gateway (371 s
# for 120 min) plus first-call model load. 900 s covers the 90 MB ceiling
# with ~2x headroom. Must stay under the pipeline wrapper timeout
# (_SLOW_SOURCE_TIMEOUTS in pipeline.py).
_TRANSCRIBE_TIMEOUT = 900


async def transcribe_audio_url(audio_url: str) -> str:
    """Download one episode's audio and transcribe it via Whisper; "" on failure.

    This is the on-demand full-content path (see reach_mcp.content.fetch_content)
    — NOT called during search, which only returns episode metadata + shownotes.
    Skips audio over _MAX_AUDIO_BYTES (no ffmpeg compression).
    """
    settings = get_settings()
    audio = await download_audio(audio_url, settings)
    if not audio:
        return ""
    if len(audio) > _MAX_AUDIO_BYTES:
        log.debug("xiaoyuzhou audio too large to transcribe: %d bytes", len(audio))
        return ""
    # Allow time for the first-call model load on the GPU server.
    try:
        return await asyncio.wait_for(transcribe(audio, settings), timeout=_TRANSCRIBE_TIMEOUT)
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
        return bool(_token("XIAOYUZHOU_ACCESS_TOKEN"))

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        if not _token("XIAOYUZHOU_ACCESS_TOKEN"):
            return []
        client = get_client()
        rows: list[Row] = []
        # Search podcasts, then pull episodes for the top ones. Keep it bounded:
        # 2 podcasts x up to (limit/2) episodes each. Metadata only — the audio
        # is NOT transcribed here; full text comes from fetch_content on demand.
        pods = await _search_podcasts(client, query)
        per_pod = max(1, (limit + 1) // 2)
        for pod in pods[:2]:
            eps = await _episodes(client, pod.get("pid", ""), per_pod)
            for e in eps[:per_pod]:
                audio_url = _episode_audio_url(e)
                dur = e.get("duration") or (e.get("media") or {}).get("duration") or 0
                try:
                    mins = int(dur) // 60
                except (TypeError, ValueError):
                    mins = 0
                rows.append(Row(
                    source="xiaoyuzhou",
                    id=e.get("eid") or "",
                    title=e.get("title") or "",
                    url=e.get("url") or f"https://www.xiaoyuzhoufm.com/episode/{e.get('eid')}",
                    author=pod.get("title"),
                    date=e.get("pubDate") or e.get("pub_date"),
                    engagement={"commentCount": e.get("commentCount") or 0,
                                "playCount": e.get("playCount") or 0},
                    # shownotes snippet, not a transcript; audio_url kept so
                    # fetch_content can transcribe this exact episode on demand.
                    text=snip(e.get("shownotes") or e.get("description") or ""),
                    audio_url=audio_url,
                    duration_min=mins,
                ))
                if len(rows) >= limit:
                    return rows
        return rows
