"""Digg AI-1000 clusters via the optional digg-pp-cli binary (free, no auth).

Detected on PATH -> available; absent -> gated off. The CLI is built by the
operator (see last30days' build steps). reach-mcp does NOT vendor the Go
toolchain — it only shells out if the binary exists.
"""

from __future__ import annotations

import asyncio
import json
import shutil

from reach_mcp.sources.base import Row, Source, register_source, snip


def _has_cli() -> bool:
    return shutil.which("digg-pp-cli") is not None


@register_source
class Digg(Source):
    name = "digg"
    description = "Digg AI-1000 story clusters via digg-pp-cli (free; needs the CLI on PATH)."
    host = "digg.com"
    needs_auth = False
    required_env = ()

    def available(self) -> bool:  # type: ignore[override]
        return _has_cli()

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        if not _has_cli():
            return []
        try:
            proc = await asyncio.create_subprocess_exec(
                "digg-pp-cli",
                "search",
                query,
                "--since",
                f"{days}d",
                "--agent",
                "--limit",
                str(limit),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=90)
        except Exception:  # noqa: BLE001
            return []
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return []
        rows: list[Row] = []
        clusters = data if isinstance(data, list) else data.get("clusters") or []
        for i, c in enumerate(clusters):
            title = c.get("title") or f"Digg cluster {i + 1}"
            rows.append(
                Row(
                    source="digg",
                    id=str(c.get("clusterUrlId") or i),
                    title=title,
                    url=c.get("url") or "",
                    author=None,
                    date=c.get("firstPostAge"),
                    engagement={"rank": c.get("rank") or 0},
                    text=snip(c.get("summary") or ""),
                )
            )
        return rows
