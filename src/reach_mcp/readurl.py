"""Pluggable page-reader backends for fetch_content/read_url.

Some pages (support.google.com consent-walls, three.co.uk's heavy/JS body)
return a login/interstitial stub to the plain Jina Reader from a datacenter
egress. This layer walks a chain of readers, cheapest-quota first:

1. **Exa /contents** — returns full text for already-crawled pages, near-instant
   (content cache hit). Uses EXA_API_KEY / EXA_BASE_URL.
2. **Jina Reader (r.jina.ai)** — free, keyless; fetches live. Default path.
3. **Firecrawl (v2 `/scrape`)** — Chromium full-render scrape. Best body, but
   consumes server quota/credits, so it only runs when the cheap readers
   yield a wall/empty/stub. Enabled via FIRECRAWL_API_URL.
4. **Tavily /extract** — generous free tier, JS-rendered. Enabled via TAVILY_API_KEY.

Each backend returns clean markdown/text. read_url validates the result and
returns the first one that looks like a real page body, else "".
"""

from __future__ import annotations

import logging
import os
import re

import httpx

from reach_mcp.jina import read_url as _jina_read

log = logging.getLogger(__name__)

# Deep reads can legitimately exceed the shared 15s request_timeout (heavy
# pages, browser render). One page per call, so a wide budget is safe.
_DEFAULT_READ_TIMEOUT = 90
# Below this many chars a "success" is almost always a consent/login stub,
# not a real article body — fall through to the next reader.
_MIN_BODY = 400

# Consent / login / JS-required shells. A body that is short AND matches one
# of these is a wall, not content.
_WALL_PATT = re.compile(
    r"before you continue|enable javascript|javascript is (disabled|required)|"
    r"to continue,?\s+(please )?(enable|sign in|log in)|verify you are a human|"
    r"unusual traffic|accept (all )?cookies|请选择验证|验证您是|登录/注册|扫一扫登录",
    re.IGNORECASE,
)


def _looks_walled(body: str) -> bool:
    """Heuristic: is this a real body or a consent/login/JS shell?"""
    if not body:
        return True
    if len(body) >= _MIN_BODY and not _WALL_PATT.search(body):
        return False
    # short, or a long consent page (some walls ramble) — a wall marker wins
    return bool(_WALL_PATT.search(body)) or len(body) < _MIN_BODY


async def _exa_read(url: str, timeout: float) -> str:
    """Exa /contents: full text of an already-crawled page (cache-fast)."""
    key = os.environ.get("EXA_API_KEY", "").strip()
    if not key:
        return ""
    base = os.environ.get("EXA_BASE_URL", "").strip().rstrip("/") or "https://api.exa.ai"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base}/contents",
                json={"urls": [url], "text": True},
                headers={"x-api-key": key, "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
        for r in data.get("results") or []:
            txt = (r.get("text") or "").strip()
            if txt:
                return txt
        return ""
    except Exception as e:  # noqa: BLE001
        log.debug("exa read %s failed: %s", url, e)
        return ""


def _firecrawl_scrape_url(base_url: str) -> str:
    """Normalize FIRECRAWL_API_URL to the v2 /scrape endpoint.

    Accepts a root or gateway-prefixed base URL (e.g.
    ``https://api.firecrawl.dev``, ``http://api-key-rotator:8788/firecrawl``),
    a ``/v2``- or legacy ``/v1``-suffixed base, or an explicit ``/scrape`` URL.
    """
    base = base_url.strip().rstrip("/")
    if base.endswith("/v2/scrape"):
        return base
    if base.endswith("/v1/scrape"):
        return f"{base[: -len('/v1/scrape')]}/v2/scrape"
    if base.endswith("/v2"):
        return f"{base}/scrape"
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return f"{base}/v2/scrape"


async def _firecrawl_read(url: str, timeout: float) -> str:
    """Firecrawl v2 scrape via FIRECRAWL_API_URL — self-hosted (:3002),
    official Cloud, or the key-rotator gateway (same host as EXA).
    Chromium-rendered; best body. The rotator form injects/rotates the real
    key, so FIRECRAWL_API_KEY may be omitted or dummy when using it."""
    raw_base = os.environ.get("FIRECRAWL_API_URL", "").strip().rstrip("/")
    if not raw_base:
        return ""
    endpoint = _firecrawl_scrape_url(raw_base)
    api_key = os.environ.get("FIRECRAWL_API_KEY", "").strip()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    scrape_timeout_ms = max(1000, min(300_000, int(timeout * 1000)))
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                endpoint,
                json={
                    "url": url,
                    "formats": ["markdown"],
                    "onlyMainContent": True,
                    "timeout": scrape_timeout_ms,
                },
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
        if not isinstance(data, dict) or data.get("success") is False:
            return ""
        inner = data.get("data")
        if not isinstance(inner, dict):
            return ""
        md = inner.get("markdown")
        return md.strip() if isinstance(md, str) else ""
    except Exception as e:  # noqa: BLE001
        log.debug("firecrawl read %s failed: %s", url, e)
        return ""


async def _tavily_read(url: str, timeout: float) -> str:
    """Tavily /extract — JS-rendered, generous free tier.

    Supports a key-rotator/proxy gateway via TAVILY_BASE_URL (same pattern as
    EXA_BASE_URL); the gateway then owns the real API key and the key sent here
    is a dummy it accepts, so this works without a per-service key in config.
    """
    key = os.environ.get("TAVILY_API_KEY", "").strip() or "dummy"
    # Through the rotator the service is mounted under /tavily
    # (POST {rotator}/tavily/extract); direct api.tavily.com mounts at root.
    base = os.environ.get("TAVILY_BASE_URL", "").strip().rstrip("/") or "https://api.tavily.com"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base}/extract",
                json={"urls": [url]},
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        for r in data.get("results") or []:
            txt = (r.get("raw_content") or r.get("content") or "").strip()
            if txt:
                return txt
        return ""
    except Exception as e:  # noqa: BLE001
        log.debug("tavily read %s failed: %s", url, e)
        return ""


async def read_url(url: str, timeout: float | None = None) -> str:
    """Read one URL to clean text across the configured readers, cheap first.

    Exa → Jina → Firecrawl → Tavily; returns the first result that passes the
    wall/stub check, else "".
    """
    budget = float(
        timeout
        if timeout is not None
        else os.environ.get("REACH_MCP_READ_TIMEOUT", str(_DEFAULT_READ_TIMEOUT))
    )
    for backend in (_exa_read, _jina_read, _firecrawl_read, _tavily_read):
        body = await backend(url, budget)
        if body and not _looks_walled(body):
            return body
        if body:
            log.debug(
                "read_url: %s returned a wall/stub (%d chars) for %s; next backend",
                backend.__name__,
                len(body),
                url,
            )
    return ""
