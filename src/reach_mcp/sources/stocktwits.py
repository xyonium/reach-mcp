"""StockTwits trader messages via public API (ticker/crypto topics only).

Mirrors last30days' stocktwits source: StockTwits is cashtag-native, so a topic
must first resolve to a symbol. Non-financial topics (e.g. "OpenAI", "AI")
return [] rather than erroring — the old code wrongly used the raw query as the
symbol, which 404s for anything that isn't a bare ticker.

Flow: finance gate -> resolve symbol via /api/2/search/symbols.json -> pull
messages from /api/2/streams/symbol/{SYMBOL}.json. Uses urllib (avoids the
httpx TLS fingerprint that some CDNs block) + a friendly UA. Unauthenticated
quota is ~200 req/hr; keep requests sparse.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from reach_mcp.sources.base import Row, Source, register_source

_STREAM_URL = "https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"
_SEARCH_URL = "https://api.stocktwits.com/api/2/search/symbols.json"
_UA = "reach-mcp/0.1 (StockTwits source)"

# Finance gate: only ticker/crypto-like topics get symbol resolution.
_CASHTAG = re.compile(r"\$([A-Za-z][A-Za-z0-9.\-]{0,5})")
_FINANCE_HINTS = re.compile(
    r"\b(stock|stocks|ticker|cashtag|equit(?:y|ies)|price target|earnings|"
    r"premarket|pre-?market|after\s?hours|dividend|valuation|crypto|altcoin|"
    r"defi|market cap|bullish|bearish|bitcoin|ethereum|btc|eth)\b",
    re.IGNORECASE,
)
# Crypto names -> StockTwits symbols (a few common ones).
_CRYPTO_ALIASES = {
    "bitcoin": "BTC.X", "btc": "BTC.X", "ethereum": "ETH.X", "eth": "ETH.X",
}


def _is_financial_topic(topic: str) -> bool:
    return bool(_CASHTAG.search(topic) or _FINANCE_HINTS.search(topic))


def _get_json(url: str, timeout: int = 20) -> dict | list:
    # StockTwits intermittently 403s on rapid requests (Cloudflare). Retry with
    # backoff, and keep the default UA. Proxy state doesn't matter; the 403 is
    # frequency-based, so pacing + retry is the fix.
    last = None
    for attempt in range(3):
        try:
            req = Request(url, headers={"User-Agent": _UA})
            with urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 403:  # transient Cloudflare block; back off and retry
                time.sleep(1.0 * (2 ** attempt) + 0.5)
                continue
            raise
        except Exception:
            raise
    raise last if last else RuntimeError("stocktwits request failed")


def _resolve_symbols(topic: str, max_symbols: int = 2) -> list[str]:
    """Resolve a topic to StockTwits symbols. [] for non-financial topics."""
    found: list[str] = []
    for m in _CASHTAG.finditer(topic):
        sym = m.group(1).upper()
        if sym not in found:
            found.append(sym)
    if found:
        return found[:max_symbols]
    # Bare uppercase ticker (AAPL, TSLA, BTC.X) — trust as-is, no finance gate.
    # Exclude common English words that uppercase by accident (APPLE, TESLA,
    # OPEN, etc.) — real tickers are abbreviations, not whole words.
    bare = topic.strip().upper()
    _COMMON_WORDS = {"APPLE", "TESLA", "OPEN", "AI", "IRA", "LIFE", "NEW",
                     "TIME", "HOME", "STAR", "PLAY", "GOOD", "WORK", "SOFT",
                     "WINDOW", "CLOUD"}
    if bare not in _COMMON_WORDS and re.fullmatch(
        r"[A-Z]{1,5}(?:[.\-][A-Z0-9]{1,3})?", bare
    ):
        return [bare]
    for word in topic.lower().split():
        if word in _CRYPTO_ALIASES:
            sym = _CRYPTO_ALIASES[word]
            if sym not in found:
                found.append(sym)
    if found:
        return found[:max_symbols]
    # Company/product name -> symbol search, but only if finance-gated.
    if not _is_financial_topic(topic):
        return []
    try:
        url = _SEARCH_URL + "?" + urlencode({"q": topic})
        data = _get_json(url)
        for result in data.get("results", []):
            sym = (result.get("symbol") or "").upper()
            if sym and sym not in found:
                found.append(sym)
            if len(found) >= max_symbols:
                break
    except Exception:  # noqa: BLE001
        return []
    return found[:max_symbols]


def _fetch_stream(symbol: str, limit: int) -> list[dict]:
    """Pull messages for a symbol (paginated lightly, polite pacing)."""
    messages: list[dict] = []
    cursor_max = None
    try:
        while len(messages) < limit:
            url = _STREAM_URL.format(symbol=symbol)
            if cursor_max:
                url += f"?max={cursor_max}"
            data = _get_json(url)
            batch = data.get("messages", []) if isinstance(data, dict) else []
            if not batch:
                break
            messages.extend(batch)
            cursor = (data.get("cursor") or {}) if isinstance(data, dict) else {}
            if not cursor.get("more") or not cursor.get("max"):
                break
            cursor_max = cursor["max"]
            time.sleep(0.8)  # respect unauthenticated quota
    except Exception:  # noqa: BLE001
        pass
    return messages[:limit]


@register_source
class StockTwits(Source):
    name = "stocktwits"
    description = "StockTwits trader messages (ticker/crypto topics; resolves symbol first)."
    host = "api.stocktwits.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        symbols = await asyncio.to_thread(_resolve_symbols, query)
        if not symbols:
            return []
        messages = await asyncio.to_thread(_fetch_stream, symbols[0], limit)
        rows: list[Row] = []
        for msg in messages:
            user = (msg.get("user") or {}).get("username")
            rows.append(Row(
                source="stocktwits", id=str(msg.get("id", "")),
                title=(msg.get("body") or "")[:120],
                url=f"https://stocktwits.com/{user}/message/{msg.get('id','')}",
                author=user, date=msg.get("created_at"),
                engagement={}, text=msg.get("body") or "",
            ))
        return rows
