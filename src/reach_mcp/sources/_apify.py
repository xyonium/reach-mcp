"""Shared Apify helper for threads/tiktok/instagram/pinterest.

Apify gives $5 free credits EVERY MONTH (recurring, not one-time) on the Free
plan. This runs an Actor synchronously via the run-sync-get-dataset-items
endpoint and returns the dataset items directly.

Verified 2026-08 — actor IDs and their real input schemas:
  - threads   -> futurizerush/meta-threads-scraper   (mode=search, keywords[], max_posts>=10)
  - tiktok    -> clockworks/tiktok-scraper           (searchQueries[], resultsPerPage)
  - instagram -> apify/instagram-search-scraper      (search=<str>, searchType, searchLimit)
  - pinterest -> automation-lab/pinterest-scraper    (searchQueries[], maxItems)
The earlier IDs (apify/threads-scraper, apify/pinterest-scraper) do NOT exist
on Apify and always returned "record-not-found".

Endpoint: POST https://api.apify.com/v2/acts/{actorId}/run-sync-get-dataset-items?token={TOKEN}
  - input is the POST body (JSON)
  - response body is the dataset items array (JSON)
  - the run blocks until the Actor finishes (timeout via ?timeout=<sec>)
"""
from __future__ import annotations

import json
import logging
import os

from reach_mcp.sources.base import snip, Row, get_client

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
    Returns [] on any failure (token missing, network error, non-2xx) — except
    quota/billing failures (402/403/429), which raise so the pipeline can
    classify them as rate_limited instead of a silent [].
    """
    token = _token()
    if not token:
        return []
    client = get_client()
    # Apify's run-sync endpoint requires the tilde actor form (username~actor),
    # NOT the slash form — the slash form returns 404 page-not-found.
    tilde_id = actor_id.replace("/", "~")
    url = (
        f"{_API_BASE}/{tilde_id}"
        f"/run-sync-get-dataset-items?token={token}&timeout=120"
    )
    # PoliteClient only does GET via get_json/get_text; use its underlying
    # httpx client for the POST with a JSON body.
    try:
        resp = await client._client.post(  # noqa: SLF001
            url,
            json=run_input,
            headers={"Content-Type": "application/json"},
            # Actors run synchronously and can take 30-120s (threads/instagram
            # commonly ~25s+). Override the polite client's default request
            # timeout so the run isn't cut short by a ReadTimeout.
            timeout=180,
        )
        # run-sync-get-dataset-items returns 201 Created when it completes with
        # items in the body (2xx is success; 200/201 both carry the dataset).
        if not (200 <= resp.status_code < 300):
            # Surface quota/billing failures explicitly so the pipeline can
            # report them as rate_limited (actionable) instead of a silent [].
            if resp.status_code in (402, 403, 429):
                raise RuntimeError(
                    f"apify {actor_id}: {resp.status_code} — {resp.text[:200]}"
                )
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
        text=snip(text),
    )


async def fetch_threads(query: str, limit: int) -> list[Row]:
    """Threads via futurizerush/meta-threads-scraper (keyword search mode).

    Actor verified 2026-08: mode=search + keywords[] returns posts; max_posts
    is capped at a minimum of 10 by the actor.
    """
    items = await run_actor_sync("futurizerush/meta-threads-scraper", {
        "mode": "search",
        "keywords": [query],
        "max_posts": max(10, min(limit, 50)),
    })
    return [_to_row_threads(it) for it in items[:limit]]


async def fetch_tiktok(query: str, limit: int) -> list[Row]:
    items = await run_actor_sync("clockworks/tiktok-scraper", {
        "searchQueries": [query],
        "resultsPerPage": min(limit, 30),
        "searchSection": "/video",
    })
    return [_to_row(it, "tiktok") for it in items[:limit]]


async def fetch_instagram(query: str, limit: int) -> list[Row]:
    """Instagram via apify/instagram-search-scraper (keyword -> hashtags).

    Actor uses a single `search` string + `searchType` (place/user/hashtag/
    popular) + `searchLimit`. Returns hashtag/search-result records, not posts.
    """
    items = await run_actor_sync("apify/instagram-search-scraper", {
        "search": query,
        "searchType": "hashtag",
        "searchLimit": min(limit, 30),
    })
    return [_to_row_instagram(it) for it in items[:limit]]


async def fetch_pinterest(query: str, limit: int) -> list[Row]:
    """Pinterest via automation-lab/pinterest-scraper (keyword search).

    Actor verified 2026-08: searchQueries[] + maxItems returns pins with
    description/title/saves. Result dicts carry pin fields (id, title,
    description, url, imageUrl, saves, pinnerUsername).
    """
    items = await run_actor_sync("automation-lab/pinterest-scraper", {
        "searchQueries": [query],
        "maxItems": min(limit, 30),
    })
    return [_to_row_pinterest(it) for it in items[:limit]]


def _to_row_pinterest(item: dict) -> Row:
    """Normalize an automation-lab/pinterest-scraper item into a Row.

    Pin shape: {id, title, description, url, imageUrl, thumbnailUrl, altText,
    domain, link, saves, pinnerUsername, pinnerName, pinnerFollowers, boardName}
    The generic _to_row misses these because pins carry no text/caption — the
    meaningful text lives in title/altText.
    """
    title = item.get("title") or item.get("altText") or ""
    text = (item.get("altText") or item.get("description") or "").strip()
    return Row(
        source="pinterest",
        id=str(item.get("id") or ""),
        title=title[:120],
        url=item.get("url") or "",
        author=_str_field(item, "pinnerUsername", "pinnerName"),
        date=None,
        engagement={"saves": item.get("saves") or 0,
                    "followers": item.get("pinnerFollowers") or 0},
        text=snip(text),
    )


def _to_row_threads(item: dict) -> Row:
    """Normalize a futurizerush/meta-threads-scraper item into a Row.

    Post shape: {record_type, post_url, post_code, text_content, created_at,
    like_count, reply_count, repost_count, quote_count, share_count, ...}
    """
    text = (item.get("text_content") or item.get("caption") or "")
    return Row(
        source="threads",
        id=str(item.get("post_code") or item.get("id") or ""),
        title=text[:120],
        url=item.get("post_url") or "",
        author=_str_field(item, "username", "authorMeta.username", "author"),
        date=item.get("created_at"),
        engagement={
            "likes": item.get("like_count") or 0,
            "replies": item.get("reply_count") or 0,
            "reposts": item.get("repost_count") or 0,
            "views": item.get("view_count") or 0,
        },
        text=snip(text),
    )


def _to_row_instagram(item: dict) -> Row:
    """Normalize an apify/instagram-search-scraper item into a Row.

    Hashtag-search records: {searchTerm, searchSource, name, postsCount, url,
    id}. We surface the hashtag name + post count as the row.
    """
    name = item.get("name") or item.get("shortCode") or ""
    return Row(
        source="instagram",
        id=str(item.get("id") or name),
        title=f"#{name}",
        url=item.get("url") or "",
        author=None,
        date=None,
        engagement={"posts": item.get("postsCount") or 0},
        text=f"#{name} — {item.get('postsCount', 0)} posts",
    )


__all__ = [
    "has_token", "run_actor_sync",
    "fetch_threads", "fetch_tiktok", "fetch_instagram", "fetch_pinterest",
]
# keep json import referenced for clarity (used by callers if needed)
_ = json
