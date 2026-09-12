"""GitHub repo search (free; optional proxy/token for higher rate limits).

Backend priority: ``GITHUB_BASE_URL`` (firecrawl research-proxy compatible,
which does its own token pool rotation) → ``GH_TOKEN`` directly against
api.github.com → anonymous direct. Proxy failures fall back to the direct
path for that call and surface a notice.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from reach_mcp.sources.base import Row, Source, get_client, register_source

_DIRECT_API = "https://api.github.com"


def _proxy_base() -> str:
    return os.environ.get("GITHUB_BASE_URL", "").strip().rstrip("/")


def _direct_headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GH_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


@register_source
class GitHub(Source):
    name = "github"
    description = "GitHub repos, issues, and user activity via the REST API (free; GITHUB_BASE_URL/GH_TOKEN optional). Also exposes newly-hot repos as trending."
    host = "api.github.com"
    supports_trending = True

    async def _search_repos(
        self, query: str, limit: int, *, sort: str | None = None
    ) -> list[dict[str, Any]]:
        """Repo search → normalised dicts (full_name/html_url/owner/description/…)."""
        client = get_client()
        base = _proxy_base()
        if base:
            try:
                data = await client.get_json(
                    f"{base}/v2/research/github",
                    params={"query": query, "k": str(min(limit, 100))},
                    headers={"Accept": "application/json"},
                )
                self.last_notice = f"github backend: proxy {base}"
                return [self._norm_proxy_item(it) for it in data.get("results", [])]
            except Exception as e:  # noqa: BLE001 — proxy down: fall back direct
                self.last_notice = (
                    f"github proxy {base} failed ({type(e).__name__}), "
                    f"fallback: direct+{'token' if os.environ.get('GH_TOKEN') else 'anonymous'}"
                )
        else:
            self.last_notice = (
                f"github backend: direct+{'token' if os.environ.get('GH_TOKEN') else 'anonymous'}"
            )
        params: dict[str, str] = {"q": query, "per_page": str(min(limit, 30))}
        if sort:
            params["sort"] = sort
            params["order"] = "desc"
        data = await client.get_json(
            f"{_DIRECT_API}/search/repositories", params=params, headers=_direct_headers()
        )
        return list(data.get("items", []))

    @staticmethod
    def _norm_proxy_item(it: dict[str, Any]) -> dict[str, Any]:
        """research-proxy repo_readme item → direct-API repo shape."""
        full = it.get("repo") or ""
        owner, _, _name = full.partition("/")
        snippet = it.get("snippet") or ""
        content = it.get("contentMd") or ""
        return {
            "id": full,
            "full_name": full,
            "name": _name or full,
            "html_url": it.get("readmeUrl") or "",
            "owner": {"login": owner},
            "description": snippet,
            "created_at": None,
            "pushed_at": None,
            # stargazers/forks absent from the proxy payload — engagement stays 0
            "text": f"{snippet}\n\n{content[:4000]}" if content else snippet,
        }

    async def fetch_trending(self, limit: int, days: int = 7) -> list[Row]:
        """Newly-hot repos: created within the window, sorted by stars.

        GitHub has no official trending API; the community approximation is a
        search over recent creations ordered by stars (keyless works, GH_TOKEN
        raises the rate limit).
        """
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        items = await self._search_repos(f"created:>{since} stars:>50", limit, sort="stars")
        rows: list[Row] = []
        for r in items:
            rows.append(
                Row(
                    source="github",
                    id=str(r.get("id", "")),
                    title=r.get("full_name") or r.get("name") or "",
                    url=r.get("html_url") or "",
                    author=(r.get("owner") or {}).get("login"),
                    date=r.get("created_at"),
                    engagement={
                        "stars": r.get("stargazers_count") or 0,
                        "forks": r.get("forks_count") or 0,
                        "language": r.get("language") or "",
                    },
                    text=(r.get("text") or r.get("description") or ""),
                )
            )
        return rows

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        items = await self._search_repos(query, limit)
        rows: list[Row] = []
        for r in items:
            rows.append(
                Row(
                    source="github",
                    id=str(r.get("id", "")),
                    title=r.get("full_name") or r.get("name") or "",
                    url=r.get("html_url") or "",
                    author=(r.get("owner") or {}).get("login"),
                    date=r.get("pushed_at"),
                    engagement={
                        "stars": r.get("stargazers_count") or 0,
                        "forks": r.get("forks_count") or 0,
                    },
                    text=(r.get("text") or r.get("description") or ""),
                )
            )
        return rows
