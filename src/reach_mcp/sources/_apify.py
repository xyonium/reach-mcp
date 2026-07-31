"""Shared Apify helper for threads/tiktok/instagram/pinterest.

Apify gives $5 free credits EVERY MONTH (recurring, not one-time) on the Free
plan. This runs an Actor synchronously via the run-sync-get-dataset-items
endpoint and returns the dataset items directly.

Endpoint: POST https://api.apify.com/v2/acts/{actorId}/run-sync-get-dataset-items?token={TOKEN}
  - input is the POST body (JSON)
  - response body is the dataset items array (JSON)
  - the run blocks until the Actor finishes (timeout via ?timeout=<sec>)
"""
from __future__ import annotations

import json
import logging
import os
from urllib.parse import quote

from reach_mcp.sources.base import Row, get_client

log = logging.getLogger(__name__)

_API_BASE = "https://api.apify.com/v2/acts"
# Synchronous runs can take a while; let the pipeline's per-source timeout bound it.


def _token() -> str:
    return os.environ.get("APIFY_API_TOKEN", "").strip()


def has_token() -> bool:
    return bool(_token())


async def run_actor_sync(actor_id: str, run_input: dict) -> list[dict]:
    """Run an Apify Actor synchronously and return its dataset items.

    actor_id is the `username/actor-name` form (URL-encoded automatically).
    Returns [] on any failure (token missing, network error, non-200).
    """
    token = _token()
    if not token:
        return []
    client = get_client()
    url = (
        f"{_API_BASE}/{quote(actor_id, safe='/')}"
        f"/run-sync-get-dataset-items?token={token}&timeout=120"
    )
    # PoliteClient only does GET via get_json/get_text; use its underlying
    # httpx client for the POST with a JSON body.
    try:
        resp = await client._client.post(  # noqa: SLF001
            url,
            json=run_input,
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code != 200:
            log.warning("apify actor %s returned %s: %s",
                        actor_id, resp.status_code, resp.text[:200])
            return []
        data = resp.json()
    except Exception:  # noqa: BLE001
        log.debug("apify actor %s failed", actor_id, exc_info=True)
        return []
    # run-sync-get-dataset-items returns the items array directly
    if isinstance(data, list):
        return data
    # some actors wrap in {items:[...]} or {data:[...]}
    if isinstance(data, dict):
        return data.get("items") or data.get("data") or []
    return []


def _get(item: dict, path: str):
    """Fetch a (possibly dotted) path like 'authorMeta.username' from a dict."""
    cur: object = item
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return cur


def _str_field(item: dict, *keys: str) -> str:
    for k in keys:
        v = _get(item, k)
        if v:
            return str(v)
    return ""


def _to_row(item: dict, source: str) -> Row:
    """Normalize an Apify item into a Row. Field names vary per actor, so we
    try common aliases (including dotted paths) for each attribute."""
    text = (item.get("text") or item.get("caption") or item.get("description")
            or item.get("textContent") or "")
    url = _str_field(item, "url", "permalinkUrl", "link", "postUrl", "webVideoUrl")
    author = (_str_field(item, "authorMeta.username", "authorUsername",
                         "ownerUsername", "author", "username", "authorMeta.name")
              or None)
    return Row(
        source=source,
        id=_str_field(item, "id", "postId", "shortCode", "videoId"),
        title=text[:120] or _str_field(item, "title"),
        url=url,
        author=author,
        date=_str_field(item, "timestamp", "createdAt", "createTime", "publishedAt"),
        engagement={
            "likes": item.get("likesCount") or item.get("likes") or 0,
            "comments": item.get("commentsCount") or item.get("comments") or 0,
            "views": item.get("playCount") or item.get("videoViewCount")
            or item.get("views") or 0,
            "shares": item.get("shares") or item.get("shareCount") or 0,
        },
        text=text[:500],
    )


async def fetch_threads(query: str, limit: int) -> list[Row]:
    items = await run_actor_sync("apify/threads-scraper", {
        "searchQueries": [query],
        "resultsType": "posts",
        "resultsLimit": min(limit, 50),
    })
    return [_to_row(it, "threads") for it in items[:limit]]


async def fetch_tiktok(query: str, limit: int) -> list[Row]:
    items = await run_actor_sync("clockworks/tiktok-scraper", {
        "searchQueries": [query],
        "resultsPerPage": min(limit, 30),
    })
    return [_to_row(it, "tiktok") for it in items[:limit]]


async def fetch_instagram(query: str, limit: int) -> list[Row]:
    items = await run_actor_sync("apify/instagram-search-scraper", {
        "searchQueries": [query],
        "searchType": "hashtag",
        "resultsLimit": min(limit, 30),
    })
    return [_to_row(it, "instagram") for it in items[:limit]]


async def fetch_pinterest(query: str, limit: int) -> list[Row]:
    items = await run_actor_sync("apify/pinterest-scraper", {
        "searchQueries": [query],
        "maxItems": min(limit, 30),
    })
    return [_to_row(it, "pinterest") for it in items[:limit]]


__all__ = [
    "has_token", "run_actor_sync",
    "fetch_threads", "fetch_tiktok", "fetch_instagram", "fetch_pinterest",
]
# keep json import referenced for clarity (used by callers if needed)
_ = json
