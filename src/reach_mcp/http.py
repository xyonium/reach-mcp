"""Polite async HTTP client: per-host pacing, Retry-After, bounded retries.

Every source fetches through this client so rate-limiting policy is central
and testable, not scattered across 23 sources. Kept deliberately simple.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from reach_mcp.config import Settings

log = logging.getLogger(__name__)


class PoliteClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(timeout=settings.request_timeout)
        # host -> monotonic time we may next send a request
        self._next_allowed: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def _pace(self, host: str) -> None:
        """Sleep so we never fire two requests to the same host closer than min_host_delay."""
        async with self._lock:
            now = time.monotonic()
            wait = self._next_allowed.get(host, 0.0) - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._next_allowed[host] = time.monotonic() + self._settings.min_host_delay

    async def _request(self, url: str, *, params, headers) -> httpx.Response:
        host = urlparse(url).netloc
        last_exc: Exception | None = None
        for attempt in range(self._settings.max_retries + 1):
            await self._pace(host)
            try:
                resp = await self._client.get(url, params=params, headers=headers)
            except Exception as e:  # noqa: BLE001
                last_exc = e
                if attempt < self._settings.max_retries:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise
            if resp.status_code in (429, 503):
                ra = resp.headers.get("Retry-After")
                delay = float(ra) if ra and ra.isdigit() else 0.5 * (2**attempt)
                if attempt < self._settings.max_retries:
                    log.warning("http %s -> %s, backing off %.2fs", url, resp.status_code, delay)
                    await asyncio.sleep(delay)
                    continue
            resp.raise_for_status()
            return resp
        if last_exc:
            raise last_exc
        raise httpx.HTTPError(f"exhausted retries for {url}")

    async def get_json(self, url: str, *, params=None, headers=None) -> Any:
        resp = await self._request(url, params=params, headers=headers)
        return resp.json()

    async def get_text(self, url: str, *, params=None, headers=None) -> str:
        resp = await self._request(url, params=params, headers=headers)
        return resp.text

    async def post_json(self, url: str, *, json: Any, headers=None) -> Any:
        """POST a JSON body and return the JSON response (paced + retried)."""
        host = urlparse(url).netloc
        last_exc: Exception | None = None
        for attempt in range(self._settings.max_retries + 1):
            await self._pace(host)
            try:
                resp = await self._client.post(url, json=json, headers=headers)
            except Exception as e:  # noqa: BLE001
                last_exc = e
                if attempt < self._settings.max_retries:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise
            if resp.status_code in (429, 503):
                ra = resp.headers.get("Retry-After")
                delay = float(ra) if ra and ra.isdigit() else 0.5 * (2**attempt)
                if attempt < self._settings.max_retries:
                    log.warning("http %s -> %s, backing off %.2fs", url, resp.status_code, delay)
                    await asyncio.sleep(delay)
                    continue
            resp.raise_for_status()
            return resp.json()
        if last_exc:
            raise last_exc
        raise httpx.HTTPError(f"exhausted retries for {url}")

    async def aclose(self) -> None:
        await self._client.aclose()
