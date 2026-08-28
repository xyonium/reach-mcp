"""豆瓣 (Douban) search via the mobile rexxar API — keyless.

m.douban.com/rexxar/api/v2/search returns movies, TV, books, and music with
ratings. Verified live 2026-08-28: works with plain httpx given an iOS
User-Agent and a Referer header (the earlier bare-curl 400 was missing
headers, NOT a TLS-fingerprint wall — curl_cffi impersonation is unnecessary).
No login, no cookie; heavy pagination or aggressive polling may trip Douban's
risk control, which the PoliteClient's per-host pacing already guards against.
"""

from __future__ import annotations

from reach_mcp.sources.base import Row, Source, get_client, register_source, snip

_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 "
    "Mobile/15E148 Safari/604.1"
)
_SEARCH_URL = "https://m.douban.com/rexxar/api/v2/search"
_HEADERS = {"User-Agent": _UA, "Referer": "https://m.douban.com/", "Accept": "application/json"}

# subject id -> canonical web URL. Rexxar returns numeric ids without the
# per-type host; the mobile web app routes via these known hosts.
_TYPE_HOSTS = {
    "movie": "https://movie.douban.com/subject/{}/",
    "tv": "https://movie.douban.com/subject/{}/",
    "book": "https://book.douban.com/subject/{}/",
    "music": "https://music.douban.com/subject/{}/",
}


@register_source
class Douban(Source):
    name = "douban"
    description = (
        "豆瓣 movies, TV, books, and music with ratings (keyless via the mobile rexxar API)."
    )
    host = "m.douban.com"
    default_days = 3650  # ratings corpus is evergreen — recency decay shouldn't bury classics

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        self.last_notice = None
        try:
            data = await client.get_json(
                _SEARCH_URL,
                params={"q": query, "count": str(min(limit, 50))},
                headers=_HEADERS,
            )
        except Exception as e:  # noqa: BLE001
            self.last_notice = f"douban rexxar search failed ({e}) — no results"
            return []
        rows: list[Row] = []
        for item in (data.get("subjects") or {}).get("items") or []:
            target = item.get("target") or {}
            subject_id = str(target.get("id") or "")
            title = str(target.get("title") or "").strip()
            if not subject_id or not title:
                continue  # ads/smart_box/market cards lack a real subject
            target_type = str(item.get("target_type") or "")
            url = (_TYPE_HOSTS.get(target_type) or "https://www.douban.com/subject/{}/").format(
                subject_id
            )
            rating = target.get("rating") or {}
            subtitle = str(target.get("card_subtitle") or "")
            rows.append(
                Row(
                    source="douban",
                    id=subject_id,
                    title=title,
                    url=url,
                    author=None,
                    date=None,
                    engagement={
                        "rating": rating.get("value") or 0,
                        "votes": rating.get("count") or 0,
                        "type": str(item.get("type_name") or target_type),
                    },
                    text=snip(subtitle or str(target.get("abstract") or "")),
                )
            )
            if len(rows) >= limit:
                break
        return rows
