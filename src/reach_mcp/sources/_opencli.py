"""Shared OpenCLI helper - free desktop backends for tiktok/instagram/pinterest.

OpenCLI (https://github.com/jackwener/opencli) is Apache-2.0, free, and reuses
your logged-in Chrome session via a browser bridge. It's a desktop-only backend
(needs Chrome + the OpenCLI extension running locally) - not viable in a headless
Docker deployment, but a great free path when reach-mcp runs on a developer
machine that already has OpenCLI installed.

Detect via `shutil.which("opencli")`. Each platform's adapter command differs:
  - tiktok:    `opencli tiktok search "<q>" --limit N`
  - instagram: `opencli instagram explore --limit N`  (search = users only;
               explore returns posts/reels, which is what we want)
  - pinterest: `opencli pinterest search-pins "<q>" --limit N`

All emit JSON via `-f json` as a normalized {ok, schema_version, data, error}
envelope.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil

from reach_mcp.sources.base import Row, snip

log = logging.getLogger(__name__)

# platform -> (subcommand, needs_query_positional)
# tiktok/pinterest take the query as a positional arg after the subcommand;
# instagram explore takes no query (it returns trending/recommended posts).
_COMMANDS: dict[str, tuple[str, bool]] = {
    "tiktok": ("search", True),
    "instagram": ("explore", False),  # explore = trending posts, no query arg
    "pinterest": ("search-pins", True),
}


def has_cli() -> bool:
    return shutil.which("opencli") is not None


async def cli_search(platform: str, query: str, limit: int) -> list[Row]:
    """Run an OpenCLI search command and parse the JSON envelope.

    Returns [] on any failure (CLI missing, not logged in, adapter error).
    Note: instagram `explore` ignores the query (returns trending posts);
    instagram keyword post-search is not exposed by the OpenCLI adapter, so
    instagram via OpenCLI is best-effort topical rather than query-exact.
    """
    if not has_cli():
        return []
    spec = _COMMANDS.get(platform)
    if spec is None:
        return []
    subcmd, takes_query = spec
    argv = ["opencli", platform, subcmd]
    if takes_query:
        argv.append(query)
    argv += ["--limit", str(min(limit, 30)), "-f", "json"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=90)
    except Exception:  # noqa: BLE001
        log.debug("opencli %s %s failed", platform, subcmd, exc_info=True)
        return []
    try:
        env = json.loads(stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(env, dict) and env.get("ok") is False:
        return []
    data = env.get("data") if isinstance(env, dict) else env
    items = _extract_items(data)
    return [_to_row(it, platform) for it in items[:limit]]


def _extract_items(data) -> list[dict]:
    """OpenCLI adapters return items under varying keys; collect the first list."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("items", "results", "posts", "pins", "videos", "feed"):
            v = data.get(k)
            if isinstance(v, list):
                return v
    return []


def _to_row(item: dict, source: str) -> Row:
    text = (item.get("caption") or item.get("text") or item.get("desc")
            or item.get("description") or item.get("title") or "")
    url = (item.get("url") or item.get("link") or item.get("permalink")
           or item.get("webVideoUrl") or "")
    author = item.get("author") or item.get("username")
    return Row(
        source=source,
        id=str(item.get("id") or item.get("postId") or item.get("shortCode") or url),
        title=text[:120],
        url=url,
        author=author,
        date=item.get("createTime") or item.get("createdAt")
        or item.get("timestamp") or item.get("publishedAt"),
        engagement={
            "likes": item.get("likes") or item.get("likesCount") or 0,
            "comments": item.get("comments") or item.get("commentsCount") or 0,
            "views": item.get("views") or item.get("plays") or item.get("playCount") or 0,
        },
        text=snip(text),
    )
