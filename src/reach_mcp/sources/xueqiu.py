"""雪球 (Xueqiu) stock search via API with optional login cookie.

Mirrors Agent-Reach's xueqiu channel: the public suggest/search endpoints
require a logged-in session cookie (xq_a_token). Without it they return
400016/empty. Provide XUEQIU_COOKIE (a "name=value; name2=value" string from
Chrome's xueqiu.com cookies) to unlock authenticated search/quote endpoints.

OpenCLI (desktop Chrome bridge) remains an optional boost when installed.
"""

from __future__ import annotations

import asyncio
import http.cookiejar
import json
import os
import shutil
import urllib.parse
import urllib.request

from reach_mcp.sources.base import Row, Source, register_source, snip

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_REFERER = "https://xueqiu.com/"
_API_BASE = "https://xueqiu.com"


def _has_cli() -> bool:
    return shutil.which("opencli") is not None


def _cookie_str() -> str:
    return os.environ.get("XUEQIU_COOKIE", "").strip()


def _build_opener() -> urllib.request.OpenerDirector:
    """Cookie-aware opener, seeded with XUEQIU_COOKIE if set."""
    jar = http.cookiejar.CookieJar()
    for pair in _cookie_str().split(";"):
        pair = pair.strip()
        if "=" not in pair:
            continue
        name, _, value = pair.partition("=")
        jar.set_cookie(
            http.cookiejar.Cookie(
                version=0,
                name=name.strip(),
                value=value.strip(),
                port=None,
                port_specified=False,
                domain=".xueqiu.com",
                domain_specified=True,
                domain_initial_dot=True,
                path="/",
                path_specified=True,
                secure=True,
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={},
            )
        )
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def _get_json(url: str, timeout: int = 20):
    opener = _build_opener()
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Referer": _REFERER})
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def _search_stock(query: str, limit: int) -> list[Row]:
    """Search stocks via xueqiu.com/stock/search.json (needs login cookie)."""
    if not _cookie_str():
        return []
    try:
        url = f"{_API_BASE}/stock/search.json?code={urllib.parse.quote(query)}&size={limit}"
        data = await asyncio.to_thread(_get_json, url)
    except Exception:  # noqa: BLE001
        return []
    rows: list[Row] = []
    for s in (data.get("stocks") or [])[:limit]:
        code = s.get("code") or s.get("symbol") or ""
        name = s.get("name") or code
        rows.append(
            Row(
                source="xueqiu",
                id=str(code),
                title=name,
                url=f"https://xueqiu.com/S/{code}" if code else "",
                author=None,
                date=None,
                engagement={},
                text=snip(s.get("exchange") or ""),
            )
        )
    return rows


async def _fetch_via_api(query: str, limit: int) -> list[Row]:
    """Fallback: public suggest API (works without login for some queries)."""
    try:
        url = f"{_API_BASE}/query/v1/suggest_stock.json?q={urllib.parse.quote(query)}&count={limit}"
        data = await asyncio.to_thread(_get_json, url)
    except Exception:  # noqa: BLE001
        return []
    rows: list[Row] = []
    # suggest returns {data: [ {code, name/query, ...} ]}
    results = data.get("data") if isinstance(data, dict) else data
    for s in (results if isinstance(results, list) else [])[:limit]:
        if not isinstance(s, dict):
            continue
        code = s.get("code") or s.get("symbol") or s.get("id") or ""
        rows.append(
            Row(
                source="xueqiu",
                id=str(code),
                title=s.get("name") or s.get("query") or s.get("stockName") or code,
                url=f"https://xueqiu.com/S/{code}" if code else "",
                author=None,
                date=None,
                engagement={},
                text=snip(s.get("description") or ""),
            )
        )
    return rows


async def _fetch_via_cli(query: str, limit: int) -> list[Row]:
    """OpenCLI boost (desktop Chrome bridge) when installed."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "opencli",
            "xueqiu",
            "search",
            query,
            "--limit",
            str(min(limit, 30)),
            "-f",
            "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=90)
    except Exception:  # noqa: BLE001
        return []
    try:
        env = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    data = env.get("data") if isinstance(env, dict) else env
    items = data if isinstance(data, list) else []
    rows: list[Row] = []
    for s in items[:limit]:
        code = s.get("symbol") or s.get("code") or s.get("id") or ""
        rows.append(
            Row(
                source="xueqiu",
                id=str(code),
                title=s.get("name") or s.get("stockName") or code,
                url=f"https://xueqiu.com/S/{code}" if code else "",
                author=None,
                date=None,
                engagement={},
                text=snip(s.get("description") or ""),
            )
        )
    return rows


@register_source
class Xueqiu(Source):
    name = "xueqiu"
    description = (
        "雪球 stock search via API (needs XUEQIU_COOKIE login cookie for search; "
        "public suggest API fallback; OpenCLI boost when installed)."
    )
    host = "xueqiu.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        self.last_notice = None
        # With login cookie: use authenticated search. Otherwise fall back to the
        # public suggest API (may return [] for many queries).
        if _cookie_str():
            rows = await _search_stock(query, limit)
            if rows:
                return rows
            self.last_notice = (
                "XUEQIU_COOKIE search returned 0 — fell back to public suggest "
                "API; the cookie may be stale, refresh it for full search"
            )
        else:
            self.last_notice = (
                "XUEQIU_COOKIE not set — using public suggest API only "
                "(results are stock tickers, not posts/discussions)"
            )
        api_rows = await _fetch_via_api(query, limit)
        if _has_cli():
            cli_rows = await _fetch_via_cli(query, limit)
            seen = {r.url for r in api_rows if r.url}
            for r in cli_rows:
                if r.url and r.url not in seen:
                    seen.add(r.url)
                    api_rows.append(r)
                elif not r.url:
                    api_rows.append(r)
        return api_rows[:limit]
