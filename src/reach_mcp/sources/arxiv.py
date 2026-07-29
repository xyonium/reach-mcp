"""arXiv papers via the Atom API (free, no key)."""
from __future__ import annotations

import re

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class Arxiv(Source):
    name = "arxiv"
    description = "arXiv preprints via the Atom API (free, no key)."
    host = "export.arxiv.org"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        xml = await client.get_text(
            "http://export.arxiv.org/api/query",
            params={"search_query": f"all:{query}", "max_results": str(min(limit, 50))},
        )
        rows: list[Row] = []
        for entry in _entries(xml):
            idm = re.search(r"<id>(.*?)</id>", entry, re.S)
            title = re.search(r"<title>(.*?)</title>", entry, re.S)
            summ = re.search(r"<summary>(.*?)</summary>", entry, re.S)
            pub = re.search(r"<published>(.*?)</published>", entry, re.S)
            author = re.search(r"<name>(.*?)</name>", entry, re.S)
            url = (idm.group(1).strip() if idm else "")
            rows.append(Row(
                source="arxiv", id=url, title=(title.group(1).strip() if title else ""),
                url=url, author=(author.group(1).strip() if author else None),
                date=(pub.group(1).strip() if pub else None),
                engagement={}, text=(summ.group(1).strip() if summ else ""),
            ))
        return rows


def _entries(xml: str) -> list[str]:
    parts = xml.split("<entry>")
    return parts[1:] if len(parts) > 1 else []
