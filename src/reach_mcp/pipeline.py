"""Search pipeline: resolve sources, fan out, normalize, dedup, score, cluster."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from reach_mcp.config import Settings
from reach_mcp.http import PoliteClient
from reach_mcp.query_core import adapt_query
from reach_mcp.sources.base import SOURCES, Item, Row, set_client, set_snippet_len

log = logging.getLogger(__name__)


def import_all_sources() -> None:
    """Populate the source registry. Delegates to the lazy loader in the
    sources package so there is one source of truth for discovery."""
    from reach_mcp.sources import _ensure_loaded  # noqa: PLC0415

    _ensure_loaded()


@dataclass
class SourceReport:
    source: str
    status: str  # "ok" | "no_results" | "rate_limited" | "gated_off" | "errored" | "unknown"
    count: int = 0
    error: str | None = None
    # Non-fatal caveat the agent should see even when the fetch "worked" —
    # e.g. zhihu's cookie search degraded to the hot list, or a cookie-based
    # source returned results that may be partial because a credential is stale.
    notice: str | None = None


# Topic categories for the `category` filter on the search tool. Mirrors the
# human-facing grouping in the tool description / README. A source may belong
# to several categories — category expansion is a union, so overlap is fine.
# `podcast` is deliberately separate from `social`: transcribing episodes is
# slow (minutes), so it's opt-in rather than part of the default social sweep.
CATEGORIES: dict[str, list[str]] = {
    "social": [
        "x",
        "reddit",
        "instagram",
        "threads",
        "tiktok",
        "xiaohongshu",
        "bilibili",
        "youtube",
        "pinterest",
        "bluesky",
        "linkedin",
        "web",
        "quora",
        "weibo",
        "zhihu",
        "douban",
        "toutiao",
        "linuxdo",
    ],
    "it": [
        "github",
        "hackernews",
        "v2ex",
        "rss",
        "arxiv",
        "dripstack",
        "stackoverflow",
        "lobsters",
    ],
    "tech": ["arxiv", "techmeme", "digg", "dripstack", "hackernews"],
    "polec": ["truthsocial", "xueqiu", "stocktwits", "polymarket"],
    "podcast": ["xiaoyuzhou"],
}

Category = Literal["social", "it", "tech", "polec", "podcast"]

# Sources left out of the default (no-explicit-sources) sweep. Opt-in only:
# podcast transcription is too slow for a default search.
DEFAULT_EXCLUDED = ("xiaoyuzhou",)


def expand_categories(sources: list[str] | None, categories: list[str] | None) -> list[str] | None:
    """Expand category names into source names, unioned with explicit `sources`.

    Returns None (search all available) when both inputs are empty. Unknown
    categories are silently ignored — search is a loose tool: an unknown token
    there shouldn't hard-fail the call the way an unknown source name does
    (that already surfaces as an "unknown" report).
    """
    if not categories:
        return list(sources) if sources else None
    names: list[str] = []
    seen: set[str] = set()
    for token in sources or []:
        if token not in seen:
            seen.add(token)
            names.append(token)
    for c in categories:
        for n in CATEGORIES.get(c.strip().lower(), []):
            if n not in seen:
                seen.add(n)
                names.append(n)
    return names or None


# Quota/rate-limit detection for actionable error reporting. Mirrors last30days'
# RATE_LIMITED health state: when a source is blocked on quota, the user needs a
# clear reason, not a generic error. Errors matching any of these are classified
# as rate_limited so the summary says "quota" instead of a stack trace.
_QUOTA_RE = re.compile(
    r"(429|rate\s*limit|quota|insufficient|daily\s+limit|too\s+many\s+requests|"
    r"monthly\s+limit|credits?\s+exhausted|payment\s+required|402|"
    r"usage\s+limit|max(?:imum)?\s+credits|billing|plan\s+limit|"
    r"access\s+denied\s+due\s+to\s+quota)",
    re.IGNORECASE,
)


def classify_error(err: str) -> str:
    """Map an exception message to a SourceReport status.

    ``rate_limited`` for quota/429 errors (actionable: add credits/limits),
    ``errored`` otherwise (transient or source-specific).
    """
    return "rate_limited" if _QUOTA_RE.search(str(err)) else "errored"


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
        source=row.source,
        id=row.id,
        title=row.title,
        url=row.url,
        author=row.author,
        date=row.date,
        engagement=dict(row.engagement),
        text=row.text,
        audio_url=row.audio_url,
        duration_min=row.duration_min,
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
        for it, v in zip(group, vals, strict=False):
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


async def _fetch_one(
    source, query: str, days: int, limit: int, timeout: float = 90
) -> tuple[list[Row], SourceReport]:
    if not source.available():
        return [], SourceReport(source=source.name, status="gated_off")
    # Adapt the raw query to this source's matching semantics: literal-AND /
    # keyword-slot sources collapse a verbose question to its core subject,
    # semantic sources pass through. See query_core for the policy.
    q = adapt_query(source.name, query)
    source.last_notice = None  # notices are per-call, never sticky
    try:
        rows = await asyncio.wait_for(source.fetch(q, days, limit), timeout=timeout)
        status = "ok" if rows else "no_results"
        return rows, SourceReport(
            source=source.name,
            status=status,
            count=len(rows),
            notice=source.last_notice,
        )
    except Exception as e:  # noqa: BLE001
        status = classify_error(str(e))
        err = _actionable_err(source.name, str(e))
        if status == "rate_limited":
            log.warning("source %s rate-limited: %s", source.name, e)
        else:
            log.warning("source %s errored: %s", source.name, e)
        return [], SourceReport(
            source=source.name,
            status=status,
            error=err[:300],
            notice=source.last_notice,
        )


def _actionable_err(source_name: str, err: str) -> str:
    """Add a fix hint to raw errors so source_summary is actionable, not a stack
    trace. The recurring case: an Apify gateway/proxy (APIFY_BASE_URL) that can't
    hold the long synchronous actor run returns 503 — lead with the actionable
    part so it survives the summary's 60-char trim."""
    if source_name in _APIFY_SOURCES and "503" in err:
        base = os.environ.get("APIFY_BASE_URL", "").strip()
        if base:
            return (
                f"503 from gateway {base} (can't hold sync actor run; check "
                f"APIFY_BASE_URL/gateway) — {err}"
            )
    return err


# Sources backed by Apify actors (via _apify.run_actor_sync) — used to attach a
# gateway hint to 503s.
_APIFY_SOURCES = frozenset(
    {
        "threads",
        "tiktok",
        "instagram",
        "pinterest",
        "linkedin",
        "quora",
    }
)


# Sources exempt from the default per-source wrapper timeout — they manage
# their own internal deadlines that legitimately exceed it. Currently empty:
# xiaoyuzhou/youtube/bilibili moved heavy fetching (Whisper transcription,
# captions) out of search into the on-demand fetch_content path, so every
# source's search-time fetch fits the default 90s again.
_SLOW_SOURCE_TIMEOUTS: dict[str, float] = {}


async def run_search(
    query: str,
    sources: list[str] | None,
    days: int,
    max_per_source: int,
    client: PoliteClient,
    settings: Settings,
    max_chars_per_item: int = 500,
) -> tuple[list[Item], list[SourceReport]]:
    import_all_sources()
    set_client(client)
    set_snippet_len(max_chars_per_item)
    if sources is None:
        names = [
            s.name for s in SOURCES.values() if s.available() and s.name not in DEFAULT_EXCLUDED
        ]
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
        *[
            _fetch_one(
                s, query, days, max_per_source, timeout=_SLOW_SOURCE_TIMEOUTS.get(s.name, 90)
            )
            for s in pending
        ]
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


async def run_trending(
    sources: list[str] | None,
    max_per_source: int,
    client: PoliteClient,
) -> tuple[list[Item], list[SourceReport]]:
    """Current hot/trending items from every source that has a native endpoint.

    Independent of run_search: query-free hot lists (weibo 实时热搜, zhihu 热榜,
    HN front page, bilibili ranking). `sources` picks specific ones; None = all
    available sources with supports_trending. Sources without trending support
    get a "skipped" report so the summary is explicit about coverage.
    """
    import_all_sources()
    set_client(client)
    if sources is None:
        targets = [s for s in SOURCES.values() if s.supports_trending and s.available()]
        reports: list[SourceReport] = []
    else:
        targets, reports = [], []
        for n in sources:
            s = SOURCES.get(n)
            if s is None:
                reports.append(SourceReport(source=n, status="unknown", error="no such source"))
            elif not s.supports_trending:
                reports.append(
                    SourceReport(source=n, status="skipped", error="no trending endpoint")
                )
            else:
                targets.append(s)

    async def _trending_one(s) -> tuple[list[Row], SourceReport]:
        # NOTE: no `available()` gate here on purpose — some trending backends
        # are keyless even when the source's search is login-gated (x trends via
        # trends24.in needs no AUTH_TOKEN). fetch_trending failures surface as
        # errored/no_results reports instead.
        s.last_notice = None
        try:
            rows = await asyncio.wait_for(s.fetch_trending(max_per_source), timeout=90)
            status = "ok" if rows else "no_results"
            return rows, SourceReport(
                source=s.name, status=status, count=len(rows), notice=s.last_notice
            )
        except Exception as e:  # noqa: BLE001
            log.warning("source %s trending errored: %s", s.name, e)
            return [], SourceReport(
                source=s.name,
                status=classify_error(str(e)),
                error=_short_err(str(e), 120),
                notice=s.last_notice,
            )

    results = await asyncio.gather(*[_trending_one(s) for s in targets])
    all_rows: list[Row] = []
    for rows, rep in results:
        reports.append(rep)
        all_rows.extend(rows)
    items = [_row_to_item(r) for r in all_rows]
    items = dedup(items)
    # Trending IS the freshness/engagement signal; skip query scoring (there is
    # no query) but keep a stable heat-based order where the source provides one.
    items.sort(key=lambda i: float(_engagement_value(i.engagement)), reverse=True)
    return items, reports


# Statuses that mean the source ran but found nothing or was blocked — grouped
# together in the summary so a thin result is readable, not a wall of zeros.
_SILENT_STATUSES = {"no_results", "gated_off"}


def render_source_summary(reports: list[SourceReport]) -> str:
    """Compact per-source outcome summary (mirrors last30days' Source Coverage).

    One line per successful source ("N from <src>"), then a single merged line
    for sources that returned nothing or are gated, and one line per errored /
    rate-limited source with the reason. Intentionally short — agents get the
    counts they need without a wall of zeros.
    """
    ok: list[tuple[str, int]] = []
    silent: list[str] = []
    errored: list[tuple[str, str]] = []
    rate_limited: list[tuple[str, str]] = []
    unknown: list[str] = []
    notices: list[tuple[str, str]] = []

    for r in reports:
        if r.status == "ok":
            ok.append((r.source, r.count))
        elif r.status == "rate_limited":
            rate_limited.append((r.source, _short_err(r.error)))
        elif r.status == "errored":
            errored.append((r.source, _short_err(r.error)))
        elif r.status == "unknown":
            unknown.append(r.source)
        else:  # no_results / gated_off
            silent.append(r.source)
        if r.notice:
            notices.append((r.source, _short_err(r.notice)))

    lines: list[str] = []
    if ok:
        ok.sort(key=lambda t: -t[1])
        lines.append("; ".join(f"{n}:{c}" for n, c in ok))
    if rate_limited:
        lines.append("QUOTA: " + "; ".join(f"{n}({e})" for n, e in rate_limited))
    if errored:
        lines.append("ERRORS: " + "; ".join(f"{n}({e})" for n, e in errored))
    if notices:
        lines.append("NOTICE: " + "; ".join(f"{n}({e})" for n, e in notices))
    if silent:
        lines.append("EMPTY: " + ", ".join(sorted(silent)))
    if unknown:
        lines.append("UNKNOWN: " + ", ".join(sorted(unknown)))
    return " | ".join(lines) if lines else "no sources ran"


def _short_err(err: str | None, max_len: int = 60) -> str:
    """Trim a long error to a single compact line for the summary."""
    if not err:
        return "unknown"
    one = " ".join((err or "").split())
    return one[:max_len].rstrip() + "..." if len(one) > max_len else one
