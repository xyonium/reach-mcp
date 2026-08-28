"""On-demand full-content fetch for a single item found via `search`.

Two-stage retrieval: `search` returns metadata + a text snippet for every
source (fast, no heavy fetches). When the agent wants the full content of one
item — a podcast transcript, video captions, or an article body — it calls
`fetch_content(source, id_or_url)` explicitly.

Rich-media sources have dedicated backends; every other source falls back to
Jina Reader on the item's URL.
"""

from __future__ import annotations

import asyncio
import logging

from reach_mcp.config import Settings
from reach_mcp.jina import read_url as jina_read_url

log = logging.getLogger(__name__)

# Sources whose full content can't be had from a plain page fetch.
RICH_MEDIA = ("xiaoyuzhou", "youtube", "bilibili")

_FETCH_TIMEOUT = 900  # mirrors the whisper transcribe budget for long episodes


async def fetch_content(source: str, id_or_url: str, settings: Settings) -> dict:
    """Return {source, url, content, ok} for one item. Never raises."""
    source = (source or "").strip().lower()
    id_or_url = (id_or_url or "").strip()
    if not id_or_url:
        return {"source": source, "url": "", "content": "", "ok": False}
    try:
        if source == "xiaoyuzhou":
            from reach_mcp.sources import xiaoyuzhou as mod

            content = await asyncio.wait_for(
                mod.transcribe_audio_url(id_or_url), timeout=_FETCH_TIMEOUT
            )
            return {"source": source, "url": id_or_url, "content": content, "ok": bool(content)}
        if source == "youtube":
            from reach_mcp.sources import youtube as mod

            vid = mod.video_id_from(id_or_url)
            content = await mod.fetch_transcript(vid) if vid else ""
            return {"source": source, "url": id_or_url, "content": content, "ok": bool(content)}
        if source == "bilibili":
            from reach_mcp.sources import bilibili as mod

            content = await mod.fetch_subtitles(id_or_url)
            return {"source": source, "url": id_or_url, "content": content, "ok": bool(content)}
        content = await jina_read_url(id_or_url)
        return {
            "source": source or "web",
            "url": id_or_url,
            "content": content,
            "ok": bool(content),
        }
    except Exception as e:  # noqa: BLE001
        log.debug("fetch_content(%s, %s) failed: %s", source, id_or_url, e)
        return {"source": source, "url": id_or_url, "content": "", "ok": False}
