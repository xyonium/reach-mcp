"""Lobste.rs — keyless JSON feeds, search via client-side filtering.

hottest.json and newest.json (plus /t/<tag>.json per tag) are public JSON with
score/comment_count/tags — verified live 2026-08-28. search.json 404s without
login, so keyword search pulls the hottest+newest feeds and filters by query
words over title+description (the v2ex pattern). Trending = hottest feed.
The Row URL is the lobste.rs discussion page (comments_url), not the outlink —
that's where the community value is.
"""

from __future__ import annotations

from reach_mcp.sources.base import Row, Source, get_client, register_source, snip

_BASE = "https://lobste.rs"


@register_source
class Lobsters(Source):
    name = "lobsters"
    description = (
        "Lobste.rs tech community: hottest feed (keyless) and keyword search via "
        "client-side filtering over the JSON feeds (search.json is login-gated)."
    )
    host = "lobste.rs"
    supports_trending = True

    async def _stories(self, client, urls: list[str]) -> list[dict]:
        """Pull several feeds, dedup by short_id, tolerate per-feed failure."""
        seen: set[str] = set()
        stories: list[dict] = []
        for url in urls:
            try:
                data = await client.get_json(url)
            except Exception:  # noqa: BLE001
                continue
            for s in data or []:
                sid = str(s.get("short_id") or "")
                if sid and sid not in seen:
                    seen.add(sid)
                    stories.append(s)
        return stories

    @staticmethod
    def _row(s: dict) -> Row | None:
        sid = str(s.get("short_id") or "")
        title = str(s.get("title") or "").strip()
        if not sid or not title:
            return None
        # live JSON: submitter_user is a plain username string (not an object)
        submitter = s.get("submitter_user")
        author = submitter.get("username") if isinstance(submitter, dict) else submitter
        return Row(
            source="lobsters",
            id=sid,
            title=title,
            url=str(s.get("comments_url") or f"{_BASE}/s/{sid}"),
            author=author or None,
            date=str(s.get("created_at") or "") or None,
            engagement={
                "score": s.get("score") or 0,
                "comments": s.get("comment_count") or 0,
                "tags": list(s.get("tags") or []),
            },
            text=snip(str(s.get("description") or "")),
        )

    async def fetch_trending(self, limit: int) -> list[Row]:
        client = get_client()
        self.last_notice = None
        try:
            stories = await client.get_json(f"{_BASE}/hottest.json")
        except Exception as e:  # noqa: BLE001
            self.last_notice = f"lobste.rs hottest feed failed ({e})"
            return []
        rows = [r for r in (self._row(s) for s in stories or []) if r]
        return rows[:limit]

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        self.last_notice = None
        stories = await self._stories(
            client, [f"{_BASE}/hottest.json", f"{_BASE}/newest.json"]
        )
        if not stories:
            self.last_notice = "lobste.rs feeds returned nothing (network or block)"
            return []
        words = [w.lower() for w in query.split() if len(w) > 1]
        rows: list[Row] = []
        for s in stories:
            hay = f"{s.get('title') or ''} {s.get('description') or ''} {' '.join(s.get('tags') or [])}".lower()
            if words and not all(w in hay for w in words):
                continue
            row = self._row(s)
            if row:
                rows.append(row)
            if len(rows) >= limit:
                break
        return rows
