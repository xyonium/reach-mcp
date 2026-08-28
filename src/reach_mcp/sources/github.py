"""GitHub via the REST API (free; GH_TOKEN optional for higher rate limits)."""

from __future__ import annotations

import os

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class GitHub(Source):
    name = "github"
    description = "GitHub repos, issues, and user activity via the REST API (free)."
    host = "api.github.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        headers = {"Accept": "application/vnd.github+json"}
        token = os.environ.get("GH_TOKEN", "")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = await client.get_json(
            "https://api.github.com/search/repositories",
            params={"q": query, "per_page": str(min(limit, 30))},
            headers=headers,
        )
        rows: list[Row] = []
        for r in data.get("items", []):
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
                    text=(r.get("description") or ""),
                )
            )
        return rows
