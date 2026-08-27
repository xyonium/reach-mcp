"""知乎 (Zhihu) via the mobile API host api.zhihu.com — hot-list only.

Curl-verified 2026-08-27: `api.zhihu.com/topstory/hot-lists/total` returns the
full 30-item 热榜 (title + follower/answer counts) with a plain UA and NO login.
The desktop host (www.zhihu.com) 403s everything behind a WAF, and the search /
question-detail endpoints require the x-zse-96 signature (code 10003), so this
source is a theme-browse of the hot list: fetch the list, filter by query
keywords, and fall back to the unfiltered list when nothing matches (the hot
list is better signal than an empty result for a browse source).
"""

from __future__ import annotations

from reach_mcp.sources.base import Row, Source, get_client, register_source, snip

_HOT_URL = "https://api.zhihu.com/topstory/hot-lists/total"
_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36"
)


def _rows_from_payload(data: dict, limit: int) -> list[Row]:
    rows: list[Row] = []
    for entry in (data.get("data") or [])[:limit]:
        t = entry.get("target") or {}
        qid = str(t.get("id") or "")
        title = (t.get("title") or "").strip()
        if not title:
            continue
        rows.append(
            Row(
                source="zhihu",
                id=qid,
                title=title,
                # api host URL needs the x-zse-96 signature; link the canonical page
                url=f"https://www.zhihu.com/question/{qid}" if qid else (t.get("url") or ""),
                author=None,
                date=None,  # hot list carries no timestamps
                engagement={
                    "followers": t.get("follower_count") or 0,
                    "answers": t.get("answer_count") or 0,
                },
                text=snip(entry.get("detail_text") or ""),
            )
        )
    return rows


def _matches(row: Row, ql: str) -> bool:
    return ql in row.title.lower()


@register_source
class Zhihu(Source):
    name = "zhihu"
    description = (
        "知乎热榜 (Zhihu hot list) via the mobile API — no login needed. Filters "
        "the top-30 trending questions by query; returns the unfiltered list "
        "when nothing matches. (Full search needs a signed login session.)"
    )
    host = "zhihu.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        data = await client.get_json(_HOT_URL, params={"limit": 50}, headers={"User-Agent": _UA})
        rows = _rows_from_payload(data, limit * 2)  # headroom for filtering
        ql = query.strip().lower()
        if not ql:
            return rows[:limit]
        hits = [r for r in rows if _matches(r, ql)]
        # Substring misses plurals/tokens ("AI" in "人工智能" won't hit); try
        # per-word matching before degrading to the raw hot list.
        if not hits:
            words = [w for w in ql.split() if len(w) >= 2]
            hits = [r for r in rows if any(w in r.title.lower() for w in words)]
        return (hits or rows)[:limit]
