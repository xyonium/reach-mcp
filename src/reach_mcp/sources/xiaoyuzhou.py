"""小宇宙 (Xiaoyuzhou) podcast search; transcripts via Whisper when a key is set.

Scaffold in v1: searches the public podcast index and, when GROQ_API_KEY or
OPENAI_API_KEY is present, marks rows as transcription-eligible. Without a key it
returns episode metadata only (no transcript text). Free (Groq has a free tier).
Actual Whisper transcription is deferred to post-v1.
"""
from __future__ import annotations

import os

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class Xiaoyuzhou(Source):
    name = "xiaoyuzhou"
    description = (
        "小宇宙 podcast episode search + metadata (free public API, no key). "
        "Whisper transcription via Groq (GROQ_API_KEY) — deferred to post-v1."
    )
    host = "api.xiaoyuzhoufm.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        try:
            data = await client.get_json(
                "https://api.xiaoyuzhoufm.com/search/episode",
                params={"q": query, "size": str(min(limit, 20))},
            )
        except Exception:  # noqa: BLE001
            return []
        has_key = bool(os.environ.get("GROQ_API_KEY") or os.environ.get("OPENAI_API_KEY"))
        rows: list[Row] = []
        for e in (data.get("data") or {}).get("episode_list") or []:
            rows.append(Row(
                source="xiaoyuzhou", id=e.get("eid") or "",
                title=e.get("title") or "", url=e.get("url") or "",
                author=(e.get("podcast") or {}).get("title"),
                date=e.get("pub_date"),
                engagement={},
                text="" if not has_key else "(transcription deferred to post-v1)",
            ))
        return rows
