"""Bluesky via the public AT Protocol search (free; BSKY creds optional)."""
from __future__ import annotations

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class Bluesky(Source):
    name = "bluesky"
    description = "Bluesky posts via the public AT Protocol search (free)."
    host = "public.api.bsky.app"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        data = await client.get_json(
            "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts",
            params={"q": query, "limit": str(min(limit, 50))},
        )
        rows: list[Row] = []
        for p in data.get("posts", []):
            author = (p.get("author") or {}).get("handle")
            rec = p.get("record") or {}
            rkey = (p.get("uri", "") or "").split("/")[-1]
            rows.append(Row(
                source="bluesky", id=p.get("uri") or "",
                title=(rec.get("text") or "")[:120],
                url=f"https://bsky.app/profile/{author}/post/{rkey}",
                author=author, date=rec.get("createdAt"),
                engagement={"reply": p.get("replyCount") or 0,
                            "repost": p.get("repostCount") or 0,
                            "like": p.get("likeCount") or 0},
                text=rec.get("text") or "",
            ))
        return rows
