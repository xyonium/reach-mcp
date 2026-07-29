"""LLM rerank + brief via an OpenAI-compatible gateway."""
from __future__ import annotations

import json
import logging
import re

import httpx

from reach_mcp.config import Settings
from reach_mcp.sources.base import Item

log = logging.getLogger(__name__)

_TOP_N = 30


def _chat_url(settings: Settings) -> str:
    base = settings.openai_base_url.rstrip("/")
    return base + "/chat/completions"


async def _chat(messages: list[dict], model: str, settings: Settings) -> str:
    if not settings.openai_api_key:
        return ""
    headers = {"Authorization": f"Bearer {settings.openai_api_key}",
               "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "temperature": 0.2}
    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        resp = await client.post(_chat_url(settings), json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"]


async def rerank(query: str, items: list[Item], settings: Settings) -> list[Item]:
    top = items[:_TOP_N]
    if len(top) <= 1 or not settings.openai_api_key:
        return items
    catalog = [{"idx": i, "title": it.title, "url": it.url,
                "source": it.source, "text": (it.text or "")[:500]}
               for i, it in enumerate(top)]
    prompt = (
        f"Re-rank these items by relevance to the query: {query!r}. "
        "Return ONLY a JSON array of the original idx values, most relevant first. "
        f"Items: {json.dumps(catalog)}"
    )
    try:
        content = await _chat([{"role": "user", "content": prompt}],
                              settings.rerank_model, settings)
        order = [int(x) for x in re.findall(r"\d+", content)]
        seen, ordered = set(), []
        for idx in order:
            if 0 <= idx < len(top) and idx not in seen:
                ordered.append(top[idx])
                seen.add(idx)
        for i, it in enumerate(top):
            if i not in seen:
                ordered.append(it)
        return ordered + items[_TOP_N:]
    except Exception:  # noqa: BLE001
        log.warning("rerank failed; keeping input order", exc_info=True)
        return items


async def brief(query: str, items: list[Item], settings: Settings) -> str:
    if not settings.openai_api_key:
        return "Synthesis disabled: set OPENAI_API_KEY (and OPENAI_BASE_URL) to get a brief."
    top = items[:_TOP_N]
    lines = [f"[{i}] ({it.source}) {it.title} — {it.url}\n    {(it.text or '')[:400]}"
             for i, it in enumerate(top)]
    prompt = (
        f"Write a concise, grounded brief answering: {query!r}. "
        "Cite items with [n] markers. Only use provided items.\n\n" + "\n".join(lines)
    )
    try:
        return await _chat([{"role": "user", "content": prompt}],
                           settings.brief_model, settings)
    except Exception as e:  # noqa: BLE001
        log.warning("brief failed: %s", e, exc_info=True)
        return f"Synthesis failed: {e}. See returned items."
