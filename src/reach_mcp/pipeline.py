"""Search pipeline: resolve sources, fan out, normalize, dedup, score, cluster."""
from __future__ import annotations

import asyncio
import hashlib
import importlib
import logging
import math
import pkgutil
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from reach_mcp.config import Settings
from reach_mcp.http import PoliteClient
from reach_mcp.sources.base import Item, Row, SOURCES, set_client

log = logging.getLogger(__name__)

_SOURCE_MODULES_LOADED = False


def import_all_sources() -> None:
    """Import every module in reach_mcp.sources so the registry is populated."""
    global _SOURCE_MODULES_LOADED
    if _SOURCE_MODULES_LOADED:
        return
    import reach_mcp.sources as _pkg
    for mod in pkgutil.iter_modules(_pkg.__path__):
        if mod.name in {"base", "__init__"} or mod.name.startswith("_"):
            continue
        try:
            importlib.import_module(f"reach_mcp.sources.{mod.name}")
        except Exception:  # noqa: BLE001
            log.exception("failed to import source module %s", mod.name)
    _SOURCE_MODULES_LOADED = True


@dataclass
class SourceReport:
    source: str
    status: str  # "ok" | "gated_off" | "errored" | "unknown"
    count: int = 0
    error: str | None = None


def _canonical_url(url: str) -> str:
    """Strip fragment, trailing slash, lowercase host, drop utm_* tracking params."""
    if not url:
        return ""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    path = parts.path.rstrip("/")
    if parts.query:
        kept = [p for p in parts.query.split("&") if not p.lower().startswith("utm_")]
        query = "&".join(kept)
    else:
        query = ""
    return urlunsplit((parts.scheme.lower(), host, path, query, ""))


def _row_to_item(row: Row) -> Item:
    return Item(
        source=row.source, id=row.id, title=row.title, url=row.url,
        author=row.author, date=row.date, engagement=dict(row.engagement),
        text=row.text,
    )


def dedup(items: list[Item]) -> list[Item]:
    """Collapse items sharing a canonical URL; keep the highest-scored representative."""
    best: dict[str, Item] = {}
    for it in items:
        key = _canonical_url(it.url)
        if not key:
            best.setdefault(it.url or it.id, it)
            continue
        cur = best.get(key)
        if cur is None or it.score > cur.score:
            best[key] = it
    return list(best.values())


def _engagement_value(engagement: dict) -> float:
    """Sum numeric engagement signals (upvotes, points, likes, retweets, volume...)."""
    total = 0.0
    for v in engagement.values():
        if isinstance(v, (int, float)):
            total += float(v)
    return total


def score(items: list[Item], days: int) -> list[Item]:
    """Per-source z-scored engagement scaled by recency decay within the window."""
    if not items:
        return items
    now = datetime.now(timezone.utc)
    by_source: dict[str, list[Item]] = {}
    for it in items:
        by_source.setdefault(it.source, []).append(it)
    for group in by_source.values():
        vals = [_engagement_value(i.engagement) for i in group]
        mean = sum(vals) / len(vals) if vals else 0.0
        var = sum((v - mean) ** 2 for v in vals) / len(vals) if vals else 0.0
        std = math.sqrt(var) or 1.0
        for it, v in zip(group, vals):
            z = (v - mean) / std
            age_days = 0.0
            if it.date:
                try:
                    d = datetime.fromisoformat(it.date.replace("Z", "+00:00"))
                    age_days = max(0.0, (now - d).total_seconds() / 86400.0)
                except ValueError:
                    age_days = 0.0
            decay = max(0.0, 1.0 - age_days / max(1, days))
            # engagement factor floored at 0.1 so a recent-but-modest item still
            # outranks an ancient viral one — recency is the dominant signal
            # within the window. z in [-1,1] -> factor in [0.1, 1.0].
            factor = max(0.1, 0.5 + 0.5 * z)
            it.score = factor * decay
    return items


def _norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (title or "").lower()).strip()


def cluster(items: list[Item]) -> list[Item]:
    """Group near-duplicate titles across sources; assign a cluster id."""
    groups: dict[str, list[Item]] = {}
    for it in items:
        key = hashlib.md5(_norm_title(it.title).encode()).hexdigest()
        groups.setdefault(key, []).append(it)
    for key, group in groups.items():
        cid = f"c{key[:8]}"
        for it in group:
            it.cluster = cid
    return items


async def _fetch_one(source, query: str, days: int, limit: int) -> tuple[list[Row], SourceReport]:
    if not source.available():
        return [], SourceReport(source=source.name, status="gated_off")
    try:
        rows = await asyncio.wait_for(source.fetch(query, days, limit), timeout=90)
        return rows, SourceReport(source=source.name, status="ok", count=len(rows))
    except Exception as e:  # noqa: BLE001
        log.warning("source %s errored: %s", source.name, e)
        return [], SourceReport(source=source.name, status="errored", error=str(e))


async def run_search(
    query: str,
    sources: list[str] | None,
    days: int,
    max_per_source: int,
    client: PoliteClient,
    settings: Settings,
) -> tuple[list[Item], list[SourceReport]]:
    import_all_sources()
    set_client(client)
    if sources is None:
        names = [s.name for s in SOURCES.values() if s.available()]
    else:
        names = list(sources)

    reports: list[SourceReport] = []
    known = set(SOURCES.keys())
    pending = []
    for n in names:
        if n not in known:
            reports.append(SourceReport(source=n, status="unknown", error="no such source"))
        else:
            pending.append(SOURCES[n])

    results = await asyncio.gather(
        *[_fetch_one(s, query, days, max_per_source) for s in pending]
    )
    all_rows: list[Row] = []
    for rows, rep in results:
        reports.append(rep)
        all_rows.extend(rows)

    items = [_row_to_item(r) for r in all_rows]
    items = dedup(items)
    items = score(items, days)
    items = cluster(items)
    items.sort(key=lambda i: i.score, reverse=True)
    return items, reports
