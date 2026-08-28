"""Stack Overflow search via the official Stack Exchange API — keyless.

api.stackexchange.com/2.3/search/advanced works with no key at search volume
(anonymous quota ~300 req/day/IP, far above per-search usage). Verified live
2026-08-28 from the container: 24.2M questions searchable, `fromdate` unix
window + `sort=activity` + `filter=withbody` for question bodies. The `site`
param is what makes this the whole Stack Exchange network in one source.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone

from reach_mcp.sources.base import Row, Source, get_client, register_source, snip

_API = "https://api.stackexchange.com/2.3/search/advanced"
_TAG_RE = re.compile(r"<[^>]+>")


def _iso(ts) -> str | None:
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


@register_source
class StackOverflow(Source):
    name = "stackoverflow"
    description = (
        "Stack Overflow Q&A search via the official Stack Exchange API (keyless, "
        "24M+ questions; score/answers/tags engagement)."
    )
    host = "api.stackexchange.com"
    default_days = 90  # Q&A corpus ages slowly; wider window beats recency decay

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        self.last_notice = None
        try:
            data = await client.get_json(
                _API,
                params={
                    "q": query,
                    "site": "stackoverflow",
                    "pagesize": str(min(limit, 100)),
                    "order": "desc",
                    # relevance = best title/body match within the fromdate
                    # window (activity/votes bury the keyword match)
                    "sort": "relevance",
                    "fromdate": str(int(time.time()) - days * 86400),
                    "filter": "withbody",  # include question body for snippets
                },
            )
        except Exception as e:  # noqa: BLE001
            self.last_notice = f"stackoverflow API failed ({e}) — no results"
            return []
        rows: list[Row] = []
        for q in data.get("items") or []:
            qid = str(q.get("question_id") or "")
            title = str(q.get("title") or "").strip()
            link = str(q.get("link") or "")
            if not qid or not title or not link:
                continue
            rows.append(
                Row(
                    source="stackoverflow",
                    id=qid,
                    title=title,
                    url=link,
                    author=(q.get("owner") or {}).get("display_name"),
                    date=_iso(q.get("creation_date")),
                    engagement={
                        "score": q.get("score") or 0,
                        "answers": q.get("answer_count") or 0,
                        "answered": bool(q.get("is_answered")),
                        "views": q.get("view_count") or 0,
                        "tags": list(q.get("tags") or []),
                    },
                    text=snip(_TAG_RE.sub("", str(q.get("body") or ""))),
                )
            )
            if len(rows) >= limit:
                break
        return rows
