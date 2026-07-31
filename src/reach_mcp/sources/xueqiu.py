"""雪球 (Xueqiu) stock search.

Primary: public stock-suggest JSON API (`xueqiu.com/query/v1/suggest_stock.json`),
headless and free. The OpenCLI `xueqiu` adapter (a desktop Chrome bridge) is
used only as an installed-boost: when `opencli` is on PATH it runs in parallel
and any extra hits are merged in. This keeps a server-side path first and only
opts into the desktop backend when the user has installed it.
"""
from __future__ import annotations

import asyncio
import json
import shutil

from reach_mcp.sources.base import Row, Source, get_client, register_source


def _has_cli() -> bool:
    return shutil.which("opencli") is not None


async def _fetch_via_cli(query: str, limit: int) -> list[Row]:
    """`opencli xueqiu search "<query>"` - searches stocks by code or name."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "opencli", "xueqiu", "search", query,
            "--limit", str(min(limit, 30)), "-f", "json",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=90)
    except Exception:
        return []
    try:
        env = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(env, dict) and env.get("ok") is False:
        return []
    data = env.get("data") if isinstance(env, dict) else env
    items = _extract_items(data)
    return [_row_from_cli(s) for s in items[:limit]]


def _extract_items(data) -> list[dict]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("items", "results", "stocks", "list"):
            v = data.get(k)
            if isinstance(v, list):
                return v
    return []


def _row_from_cli(s: dict) -> Row:
    code = s.get("symbol") or s.get("code") or s.get("id") or ""
    name = s.get("name") or s.get("stockName") or code
    return Row(
        source="xueqiu", id=str(code),
        title=name,
        url=f"https://xueqiu.com/S/{code}" if code else "",
        author=None, date=None,
        engagement={}, text=(s.get("description") or "")[:500],
    )


async def _fetch_via_api(query: str, limit: int) -> list[Row]:
    """Fallback: Xueqiu public stock-suggest JSON API. Requires a session
    cookie (xq_a_token) for most queries; degrades to [] otherwise."""
    client = get_client()
    try:
        data = await client.get_json(
            "https://xueqiu.com/query/v1/suggest_stock.json",
            params={"q": query, "count": str(min(limit, 20))},
            headers={"User-Agent": "reach-mcp/0.1",
                     "Referer": "https://xueqiu.com/"},
        )
    except Exception:
        return []
    rows: list[Row] = []
    for s in (data.get("data") or {}).get("result") or []:
        if not isinstance(s, dict):
            continue
        rows.append(_row_from_cli(s))
    return rows[:limit]


@register_source
class Xueqiu(Source):
    name = "xueqiu"
    description = (
        "雪球 stock search via public JSON API (headless, free). OpenCLI adapter "
        "used as an extra boost when installed (desktop only)."
    )
    host = "xueqiu.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        # Server-side JSON API is primary (headless). OpenCLI is a desktop-only
        # boost: run it in parallel when installed and merge any extra hits.
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
