"""小红书 (Xiaohongshu/RED) via cookie (free account). Off by default; v1 scaffold.

Cookie scraping against RED is brittle and tied to a logged-in session, so v1
ships this as an off-by-default scaffold: it registers and shows in list_sources,
lights up when XHS_COOKIE is set, and returns an empty list until the scrape path
is filled in. Keeps the source discoverable without a half-broken fetch.
"""
from __future__ import annotations

from reach_mcp.sources.base import Row, Source, register_source


@register_source
class Xiaohongshu(Source):
    name = "xiaohongshu"
    description = "小红书 posts via cookie (free account; v1 scaffold)."
    host = "www.xiaohongshu.com"
    needs_auth = True
    required_env = ("XHS_COOKIE",)

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        if not self.available():
            return []
        # v1: cookie scraping is fragile; left as scaffold. Returns [].
        return []
