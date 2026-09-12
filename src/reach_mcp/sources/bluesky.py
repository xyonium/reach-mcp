"""Bluesky via the public AT Protocol search (free; BSKY creds optional).

api.bsky.app 403s "Request forbidden by administrative rules" from known
datacenter egress IPs regardless of User-Agent (live-verified 2026-09 from
the reach host + container — same request via a residential IP is fine). When
SEARXNG_URL is reachable, a Bluesky-engine query through it covers the same
post corpus, so the source degrades instead of hard-failing there.
"""

from __future__ import annotations

import os

from reach_mcp.sources.base import Row, Source, get_client, register_source, snip


@register_source
class Bluesky(Source):
    name = "bluesky"
    description = "Bluesky posts via the public AT Protocol search (free)."
    host = "api.bsky.app"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        try:
            data = await client.get_json(
                "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts",
                headers={"User-Agent": "reach-mcp/0.7 (+https://github.com/xyonium)"},
                params={"q": query, "limit": str(min(limit, 50))},
            )
            return [self._row(p) for p in data.get("posts", [])]
        except Exception as e:  # noqa: BLE001
            self.last_notice = (
                f"bluesky direct api.bsky.app failed ({type(e).__name__}), "
                "fallback: searxng site filter"
            )
        return await self._searxng(query, days, limit)

    async def _searxng(self, query: str, days: int, limit: int) -> list[Row]:
        base = os.environ.get("SEARXNG_URL", "").strip().rstrip("/")
        if not base:
            self.last_notice = (self.last_notice or "") + "; SEARXNG_URL unset, 0 results"
            return []
        data = await get_client().get_json(
            base + "/search",
            params={"q": f"{query} site:bsky.app/profile", "format": "json", "safesearch": 0},
        )
        rows: list[Row] = []
        for r in (data.get("results") or [])[:limit]:
            if "/post/" not in (r.get("url") or ""):
                continue
            parts = r["url"].split("/profile/")[-1].split("/post/")
            author, rkey = (parts + [""])[:2]
            rows.append(
                Row(
                    source="bluesky",
                    id=r.get("url") or "",
                    title=(r.get("title") or "")[:120],
                    url=r["url"],
                    author=author or None,
                    date=r.get("publishedDate"),
                    engagement={},
                    text=snip(r.get("content") or ""),
                )
            )
        return rows

    @staticmethod
    def _row(p: dict) -> Row:
        author = (p.get("author") or {}).get("handle")
        rec = p.get("record") or {}
        rkey = (p.get("uri", "") or "").split("/")[-1]
        return Row(
            source="bluesky",
            id=p.get("uri") or "",
            title=(rec.get("text") or "")[:120],
            url=f"https://bsky.app/profile/{author}/post/{rkey}",
            author=author,
            date=rec.get("createdAt"),
            engagement={
                "reply": p.get("replyCount") or 0,
                "repost": p.get("repostCount") or 0,
                "like": p.get("likeCount") or 0,
            },
            text=rec.get("text") or "",
        )
