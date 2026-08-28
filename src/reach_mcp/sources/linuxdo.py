"""linux.do (Discourse 社区) — playwright + 登录 cookie (LINUXDO_COOKIE).

Cloudflare 拦死了所有 datacenter-IP 的 plain HTTP（带 cookie 的 curl 也
403，2026-08-28 实测）；唯一可行路径是 headless chromium 种下 cookie 后
访问 Discourse JSON 端点：search.json（搜索）+ latest.json/top.json（热榜）。
与 tiktok/threads 同为 per-call 浏览器生命周期，内存即时释放。
"""

from __future__ import annotations

import os
from urllib.parse import quote

from reach_mcp.sources._linuxdo_playwright import fetch_endpoint as _pw_fetch_endpoint
from reach_mcp.sources.base import Row, Source, register_source


@register_source
class LinuxDo(Source):
    name = "linuxdo"
    description = (
        "linux.do (Discourse 中文技术社区) 搜索 + 热榜，需登录 cookie "
        "(LINUXDO_COOKIE)；Cloudflare  gated，走 playwright 浏览器路径。"
    )
    host = "linux.do"
    needs_auth = True
    required_env = ("LINUXDO_COOKIE",)
    supports_trending = True

    def available(self) -> bool:  # type: ignore[override]
        if not os.environ.get("LINUXDO_COOKIE", "").strip():
            return False
        from reach_mcp.sources._linuxdo_playwright import _playwright_available

        return _playwright_available()

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        self.last_notice = None
        cookie = os.environ.get("LINUXDO_COOKIE", "").strip()
        url = f"https://linux.do/search.json?q={quote(query)}"
        rows = await _pw_fetch_endpoint(url, cookie, limit)
        if not rows:
            self.last_notice = (
                "linux.do search returned nothing — cookie may be stale or "
                "Cloudflare blocked the render; refresh LINUXDO_COOKIE"
            )
        return rows

    async def fetch_trending(self, limit: int) -> list[Row]:
        self.last_notice = None
        cookie = os.environ.get("LINUXDO_COOKIE", "").strip()
        rows = await _pw_fetch_endpoint("https://linux.do/top.json?period=daily", cookie, limit)
        if not rows:
            rows = await _pw_fetch_endpoint("https://linux.do/latest.json", cookie, limit)
        if not rows:
            self.last_notice = "linux.do hot list failed — refresh LINUXDO_COOKIE"
        return rows
