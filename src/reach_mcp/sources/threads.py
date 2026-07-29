"""Threads via cookie (free account). Off by default; v1 scaffold.

Like xiaohongshu, ships as an off-by-default scaffold so it's discoverable in
list_sources; the fetch path returns [] until a stable scrape is implemented.
"""
from __future__ import annotations

from reach_mcp.sources.base import Row, Source, register_source


@register_source
class Threads(Source):
    name = "threads"
    description = "Threads posts via cookie (free account; v1 scaffold)."
    host = "www.threads.net"
    needs_auth = True
    required_env = ("THREADS_COOKIE",)

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        if not self.available():
            return []
        # v1 scaffold; returns [].
        return []
