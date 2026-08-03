"""Whisper transcription via an OpenAI-compatible /v1/audio/transcriptions endpoint.

Self-hosted LocalAI etc. — GROQ_API_KEY is not used. Point WHISPER_BASE_URL at
any OpenAI-compatible whisper server, e.g. http://gpu.savorcare.com:8080/v1.
API key may be empty (LocalAI doesn't check it). Model default whisper-large.

Audio constraints (OpenAI Whisper): file <= 25 MB, formats mp3/mp4/mpeg/mpga/
m4a/wav/webm. No explicit duration cap at the API layer (30s sliding window
internally); only split when the file exceeds 25 MB.
"""
from __future__ import annotations

import logging

import httpx

from reach_mcp.config import Settings

log = logging.getLogger(__name__)


async def download_audio(url: str, settings: Settings) -> bytes:
    """Fetch audio bytes from an episode URL. Returns b"" on failure."""
    headers = {"User-Agent": "reach-mcp/0.1"}
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout) as c:
            r = await c.get(url, headers=headers, follow_redirects=True)
            if r.status_code != 200:
                log.debug("audio download %s -> %s", url, r.status_code)
                return b""
            return r.content
    except Exception:  # noqa: BLE001
        log.debug("audio download failed: %s", url, exc_info=True)
        return b""


async def transcribe(audio: bytes, settings: Settings, timeout: float = 600) -> str:
    """Transcribe audio bytes via POST {base}/audio/transcriptions.

    Returns the transcript text, or "" on any failure (missing base, network
    error, non-200, empty response). `timeout` defaults to 600s because a
    full podcast episode (tens of MB) takes minutes on a self-hosted gateway;
    the response can be large (verbose_json segment lists), so this is not
    the place for the small per-request timeout.
    """
    base = settings.whisper_base_url.rstrip("/")
    if not base or not audio:
        return ""
    headers = {}
    if settings.whisper_api_key:
        headers["Authorization"] = f"Bearer {settings.whisper_api_key}"
    files = {
        "file": ("audio.mp3", audio, "audio/mpeg"),
        "model": (None, settings.whisper_model or "whisper-large"),
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(f"{base}/audio/transcriptions",
                             headers=headers, files=files)
            if r.status_code != 200:
                log.warning("whisper returned %s: %s", r.status_code, r.text[:200])
                return ""
            data = r.json()
    except Exception:  # noqa: BLE001
        log.debug("whisper transcription failed", exc_info=True)
        return ""
    if not isinstance(data, dict):
        return ""
    # OpenAI simple json: {"text": "..."}; verbose_json (LocalAI default):
    # {"segments": [{"text": ...}, ...]}. Accept both.
    text = data.get("text") or ""
    if not text:
        segs = data.get("segments")
        if isinstance(segs, list):
            text = " ".join(s.get("text", "") for s in segs if isinstance(s, dict))
    return text.strip()
