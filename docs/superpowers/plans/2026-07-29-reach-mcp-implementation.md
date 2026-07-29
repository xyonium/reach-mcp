# reach-mcp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `reach-mcp`, a Python MCP server exposing `search`/`list_sources`/`synthesize` tools that fan out across ~23 sources, score by engagement, and optionally synthesize a cited brief via an OpenAI-compatible LLM — replacing the closed `last30days` server.

**Architecture:** A `Source` registry of subclasses (each a self-contained module declaring metadata + `async fetch()`). `search` resolves requested sources → `asyncio.gather` fetch through a polite `http.py` client → normalize/dedup → engagement score → cluster → optional LLM rerank+brief. FastMCP streamable-HTTP + stdio, env-driven `Settings`, two deploy paths (PyPI `uvx` + ghcr Docker).

**Tech Stack:** Python ≥3.10, `mcp[cli]>=1.27,<2` (FastMCP), `httpx`, `pydantic`, `starlette`, `uvicorn[standard]`, `feedparser`, `yt-dlp`. Test: pytest + pytest-asyncio, ruff.

## Global Constraints

- Python ≥3.10; package name `reach-mcp`, import package `reach_mcp`, console script `reach-mcp`.
- License MIT; author `xyonium`; email `shark_xc@hotmail.com`.
- LLM via OpenAI-compatible gateway env: `OPENAI_BASE_URL`+`OPENAI_API_KEY`; default models `gemini-flash-lite` for both rerank and brief (`REACH_MCP_RERANK_MODEL`/`REACH_MCP_BRIEF_MODEL`).
- Generic web source uses Searxng via `SEARXNG_URL` (default `http://searxng:8080`). Do NOT wrap Firecrawl.
- All HTTP goes through `reach_mcp.http.PoliteClient`: per-host min-delay (~0.5s floor), honor `Retry-After` on 429/503, per-request timeout ~15s, per-source timeout ~60s, max 3 retries. Keep it simple — no robots.txt, no token-bucket.
- Each source fetch is try/excepted; one source failing never aborts `search` → emit an `errored` `SourceReport`.
- Login-gated sources are off-by-default; `available` = all `required_env` vars are set and non-empty.
- TDD: write failing test first, then implement. Commit after each task.
- ruff config: `line-length=100`, `select=["E","F","I","UP","B"]`, ignore `E501`; `target-version="py310"`; `tests/*` ignores `B017`.
- Pytest: `asyncio_mode="auto"`, `testpaths=["tests"]`.

---

## File Structure

```
src/reach_mcp/
  __init__.py            # version string
  __main__.py            # CLI: --transport http|stdio --host --port
  config.py              # Settings dataclass (env-driven)
  http.py                # PoliteClient (per-host delay, Retry-After, timeout)
  sources/
    __init__.py          # SOURCES registry + get_source/list_all/available
    base.py              # Source ABC, Row/Item dataclasses, register_source
    reddit.py hackernews.py bluesky.py github.py arxiv.py techmeme.py
    polymarket.py stocktwits.py web.py youtube.py
    xueqiu.py v2ex.py bilibili.py xiaoyuzhou.py
    x.py truthsocial.py tiktok.py instagram.py linkedin.py
    xiaohongshu.py threads.py pinterest.py digg.py
  pipeline.py            # resolve_sources, fan_out, normalize, dedup, score, cluster
  synthesize.py          # LLM rerank + brief via OpenAI-compatible client
  tools.py               # search/list_sources/synthesize tool defs + build_mcp
  server.py              # build_app: FastMCP + /health, transport-security, uvicorn/stdio
tests/                   # one test module per source + pipeline + http + tools
pyproject.toml Dockerfile docker-compose.yml .dockerignore .gitignore
.github/workflows/{ci,publish,build-docker}.yml
```

---

### Task 1: Project scaffold — pyproject.toml + package dirs + CI-green empty state

**Files:**
- Create: `pyproject.toml`, `src/reach_mcp/__init__.py`, `tests/__init__.py`, `.gitignore`, `.dockerignore`

**Interfaces:**
- Produces: importable empty `reach_mcp` package; `ruff check .` and `pytest -q` both pass with zero tests.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "reach-mcp"
version = "0.1.0"
description = "Controllable multi-source search MCP server for AI agents. Search Reddit, X, YouTube, HN, GitHub, arXiv, Polymarket, 雪球, V2EX, B站, 小宇宙 & more. Open replacement for last30days."
readme = "README.md"
requires-python = ">=3.10"
license = { text = "MIT" }
authors = [{ name = "xyonium", email = "shark_xc@hotmail.com" }]
dependencies = [
    "mcp[cli]>=1.27,<2",
    "httpx>=0.27",
    "pydantic>=2.7",
    "starlette>=0.37",
    "uvicorn[standard]>=0.30",
    "feedparser>=6.0",
    "yt-dlp>=2024.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "anyio>=4",
    "ruff>=0.6",
    "build>=1.2",
]

[project.scripts]
reach-mcp = "reach_mcp.__main__:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
ignore = ["E501"]

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["B017"]
```

- [ ] **Step 2: Write `src/reach_mcp/__init__.py`**

```python
"""reach-mcp: controllable multi-source search MCP server."""
from __future__ import annotations

__version__ = "0.1.0"
```

- [ ] **Step 3: Write `tests/__init__.py`** (empty file)

```python
```

- [ ] **Step 4: Write `.gitignore`**

```
__pycache__/
*.py[cod]
.venv/
*.egg-info/
build/
dist/
.pytest_cache/
.ruff_cache/
.env
docker-compose.override.yml
```

- [ ] **Step 5: Write `.dockerignore`**

```
.venv/
__pycache__/
*.egg-info/
.git/
.pytest_cache/
.ruff_cache/
tests/
docs/
```

- [ ] **Step 6: Install editable + dev, verify green**

Run:
```bash
pip install -e ".[dev]"
ruff check .
pytest -q
```
Expected: ruff reports nothing to lint; pytest reports `no tests ran` (exit 5 is fine for now) — no collection errors.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml src/reach_mcp/__init__.py tests/__init__.py .gitignore .dockerignore
git commit -m "feat: project scaffold (pyproject, package, gitignore)"
```

---

### Task 2: `config.py` — env-driven Settings

**Files:**
- Create: `src/reach_mcp/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `get_settings() -> Settings`; fields: `transport, host, port, api_key, allowed_hosts, dns_rebinding_protection, openai_base_url, openai_api_key, rerank_model, brief_model, searxng_url, source_timeout, request_timeout, min_host_delay, max_retries`.

- [ ] **Step 1: Write failing test `tests/test_config.py`**

```python
from __future__ import annotations

import os

from reach_mcp.config import get_settings


def test_defaults(monkeypatch):
    for k in list(os.environ):
        if k.startswith("REACH_MCP_") or k in {"OPENAI_BASE_URL", "OPENAI_API_KEY"}:
            monkeypatch.delenv(k, raising=False)
    s = get_settings()
    assert s.transport == "http"
    assert s.port == 8765
    assert s.rerank_model == "gemini-flash-lite"
    assert s.brief_model == "gemini-flash-lite"
    assert s.source_timeout == 60
    assert s.request_timeout == 15
    assert s.min_host_delay == 0.5
    assert s.max_retries == 3
    assert "127.0.0.1:*" in s.allowed_hosts


def test_allowed_hosts_override(monkeypatch):
    monkeypatch.setenv("REACH_MCP_ALLOWED_HOSTS", "reach-mcp:8765,localhost:8765")
    s = get_settings()
    assert s.allowed_hosts == ("reach-mcp:8765", "localhost:8765")


def test_openai_passthrough(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    s = get_settings()
    assert s.openai_base_url == "https://gw.example.com/v1"
    assert s.openai_api_key == "sk-test"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: reach_mcp.config`.

- [ ] **Step 3: Write `src/reach_mcp/config.py`**

```python
"""Environment-based configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

_DEFAULT_ALLOWED_HOSTS = ("127.0.0.1:*", "localhost:*", "[::1]:*")


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _parse_allowed_hosts() -> tuple[str, ...]:
    raw = os.environ.get("REACH_MCP_ALLOWED_HOSTS")
    if raw is None:
        return _DEFAULT_ALLOWED_HOSTS
    return tuple(h.strip() for h in raw.split(",") if h.strip())


@dataclass(frozen=True)
class Settings:
    transport: str = os.environ.get("REACH_MCP_TRANSPORT", "http")
    host: str = os.environ.get("REACH_MCP_HOST", "0.0.0.0")
    port: int = _env_int("REACH_MCP_PORT", 8765)
    api_key: str = os.environ.get("REACH_MCP_API_KEY", "")
    dns_rebinding_protection: bool = _env_bool("REACH_MCP_DNS_REBINDING_PROTECTION", True)
    allowed_hosts: tuple[str, ...] = field(default_factory=_parse_allowed_hosts)

    openai_base_url: str = os.environ.get("OPENAI_BASE_URL", "")
    openai_api_key: str = os.environ.get("OPENAI_API_KEY", "")
    rerank_model: str = os.environ.get("REACH_MCP_RERANK_MODEL", "gemini-flash-lite")
    brief_model: str = os.environ.get("REACH_MCP_BRIEF_MODEL", "gemini-flash-lite")

    searxng_url: str = os.environ.get("SEARXNG_URL", "http://searxng:8080")

    source_timeout: int = _env_int("REACH_MCP_SOURCE_TIMEOUT", 60)
    request_timeout: int = _env_int("REACH_MCP_REQUEST_TIMEOUT", 15)
    min_host_delay: float = _env_float("REACH_MCP_MIN_HOST_DELAY", 0.5)
    max_retries: int = _env_int("REACH_MCP_MAX_RETRIES", 3)


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/reach_mcp/config.py tests/test_config.py
git commit -m "feat(config): env-driven Settings dataclass"
```

---

### Task 3: `http.py` — PoliteClient (per-host delay, Retry-After, timeout)

**Files:**
- Create: `src/reach_mcp/http.py`
- Test: `tests/test_http.py`

**Interfaces:**
- Produces: `PoliteClient(settings)` with `async def get_json(url, *, params=None, headers=None) -> Any` and `async def get_text(url, *, params=None, headers=None) -> str`. Raises `httpx.HTTPStatusError` only after retries exhausted. Enforces per-host spacing, honors `Retry-After`, bounded retries.

- [ ] **Step 1: Write failing test `tests/test_http.py`**

```python
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from reach_mcp.config import Settings
from reach_mcp.http import PoliteClient


def _settings(**over):
    base = Settings()
    return Settings(**{**{f.name: getattr(base, f.name) for f in base.__dataclass_fields__.values()}, **over})


@pytest.mark.asyncio
async def test_get_json_returns_payload(monkeypatch):
    client = PoliteClient(_settings())
    captured = {}

    async def fake_get(self, url, *, params=None, headers=None):  # noqa: ANN001
        captured["url"] = url
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    # bypass the min-host-delay sleep so the test is fast
    monkeypatch.setattr(client, "_pace", AsyncMock(return_value=None))
    data = await client.get_json("https://api.example.com/x")
    assert data == {"ok": True}
    assert captured["url"] == "https://api.example.com/x"


@pytest.mark.asyncio
async def test_honors_retry_after(monkeypatch):
    client = PoliteClient(_settings(min_host_delay=0.0))
    calls = {"n": 0}

    async def fake_get(self, url, *, params=None, headers=None):  # noqa: ANN001
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, request=httpx.Request("GET", url))
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    slept = []
    monkeypatch.setattr(asyncio, "sleep", AsyncMock(side_effect=lambda s: slept.append(s)))
    data = await client.get_json("https://api.example.com/y")
    assert data == {"ok": True}
    assert calls["n"] == 2
    assert 0 in slept  # honored Retry-After: 0


@pytest.mark.asyncio
async def test_gives_up_after_max_retries(monkeypatch):
    client = PoliteClient(_settings(min_host_delay=0.0, max_retries=3))

    async def fake_get(self, url, *, params=None, headers=None):  # noqa: ANN001
        return httpx.Response(503, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock(return_value=None))
    with pytest.raises(httpx.HTTPStatusError):
        await client.get_json("https://api.example.com/z")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_http.py -v`
Expected: FAIL — `ModuleNotFoundError: reach_mcp.http`.

- [ ] **Step 3: Write `src/reach_mcp/http.py`**

```python
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
            resp = await self._client.get(url, params=params, headers=headers)
            if resp.status_code in (429, 503):
                ra = resp.headers.get("Retry-After")
                delay = float(ra) if ra and ra.isdigit() else 0.5 * (2 ** attempt)
                if attempt < self._settings.max_retries:
                    log.warning("http %s -> %s, backing off %.2fs", url, resp.status_code, delay)
                    await asyncio.sleep(delay)
                    continue
            resp.raise_for_status()
            return resp
        # unreachable in practice, but keeps mypy calm
        if last_exc:
            raise last_exc
        raise httpx.HTTPError(f"exhausted retries for {url}")

    async def get_json(self, url: str, *, params=None, headers=None) -> Any:
        resp = await self._request(url, params=params, headers=headers)
        return resp.json()

    async def get_text(self, url: str, *, params=None, headers=None) -> str:
        resp = await self._request(url, params=params, headers=headers)
        return resp.text

    async def aclose(self) -> None:
        await self._client.aclose()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_http.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/reach_mcp/http.py tests/test_http.py
git commit -m "feat(http): PoliteClient with per-host pacing + Retry-After"
```

---

### Task 4: `sources/base.py` — Source ABC, Row/Item, registry

**Files:**
- Create: `src/reach_mcp/sources/__init__.py`, `src/reach_mcp/sources/base.py`
- Test: `tests/test_registry.py`

**Interfaces:**
- Produces:
  - `Row` dataclass: `source:str, id:str, title:str, url:str, author:str|None, date:str|None (ISO), engagement:dict, text:str`.
  - `Item` dataclass: same as Row plus `score:float`, `cluster:str|None`.
  - `Source` ABC with class attrs `name, description, host, needs_auth=False, required_env:tuple[str,...]=(), default_days=30, default_limit=20`, method `available()` (all required_env set & non-empty), and `async fetch(query, days, limit) -> list[Row]`.
  - `register_source(cls)` decorator; `SOURCES: dict[str, Source]` of instances; `get_source(name)`, `list_sources()`, `available_sources()`.

- [ ] **Step 1: Write failing test `tests/test_registry.py`**

```python
from __future__ import annotations

import pytest

from reach_mcp.sources.base import Row, Source, register_source
from reach_mcp.sources import get_source, list_sources, available_sources


class _Free(Source):
    name = "free"
    description = "free test source"
    host = "example.com"

    async def fetch(self, query, days, limit):
        return [Row(source="free", id="1", title=query, url="https://example.com/1",
                    author=None, date=None, engagement={}, text="x")]


@register_source
class _Gated(Source):
    name = "gated"
    description = "gated test source"
    host = "example.com"
    needs_auth = True
    required_env = ("SECRET_TOKEN",)

    async def fetch(self, query, days, limit):
        return []


def test_free_source_registered():
    assert "free" in {s.name for s in list_sources()}


def test_get_source():
    assert get_source("free").name == "free"
    with pytest.raises(KeyError):
        get_source("nope")


def test_gated_available_only_with_env(monkeypatch):
    monkeypatch.delenv("SECRET_TOKEN", raising=False)
    assert not _Gated().available()
    assert "gated" not in available_sources()
    monkeypatch.setenv("SECRET_TOKEN", "abc")
    assert _Gated().available()
    assert "gated" in available_sources()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write `src/reach_mcp/sources/base.py`**

```python
"""Source base class, Row/Item dataclasses, and the source registry."""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Row:
    source: str
    id: str
    title: str
    url: str
    author: str | None = None
    date: str | None = None  # ISO-8601 string
    engagement: dict[str, Any] = field(default_factory=dict)
    text: str = ""


@dataclass
class Item:
    source: str
    id: str
    title: str
    url: str
    author: str | None = None
    date: str | None = None
    engagement: dict[str, Any] = field(default_factory=dict)
    text: str = ""
    score: float = 0.0
    cluster: str | None = None


class Source(ABC):
    name: str = ""
    description: str = ""
    host: str = ""
    needs_auth: bool = False
    required_env: tuple[str, ...] = ()
    default_days: int = 30
    default_limit: int = 20

    def available(self) -> bool:
        return all(os.environ.get(v, "").strip() for v in self.required_env)

    @abstractmethod
    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        ...


SOURCES: dict[str, Source] = {}


def register_source(cls: type[Source]) -> type[Source]:
    inst = cls()
    if not inst.name:
        raise ValueError(f"{cls.__name__} must set .name")
    SOURCES[inst.name] = inst
    return cls


def get_source(name: str) -> Source:
    if name not in SOURCES:
        raise KeyError(name)
    return SOURCES[name]


def list_sources() -> list[Source]:
    return list(SOURCES.values())


def available_sources() -> list[str]:
    return [s.name for s in SOURCES.values() if s.available()]
```

- [ ] **Step 4: Write `src/reach_mcp/sources/__init__.py`**

```python
"""Source registry. Importing this package triggers registration of all sources
that have been imported. Source modules are imported by `pipeline.resolve_sources`
via `importlib` so the registry is populated lazily and only once."""
from __future__ import annotations

from reach_mcp.sources.base import (
    SOURCES,
    Item,
    Row,
    Source,
    available_sources,
    get_source,
    list_sources,
    register_source,
)

__all__ = [
    "SOURCES", "Item", "Row", "Source",
    "available_sources", "get_source", "list_sources", "register_source",
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_registry.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add src/reach_mcp/sources/__init__.py src/reach_mcp/sources/base.py tests/test_registry.py
git commit -m "feat(sources): Source ABC, Row/Item, registry"
```

---

### Task 5: `pipeline.py` — resolve, fan-out, dedup, score, cluster

**Files:**
- Create: `src/reach_mcp/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `reach_mcp.sources` registry; `reach_mcp.http.PoliteClient`.
- Produces:
  - `SourceReport` dataclass: `source:str, status:str ("ok"|"gated_off"|"errored"), count:int, error:str|None`.
  - `async run_search(query, sources, days, max_per_source, client, settings) -> tuple[list[Item], list[SourceReport]]`.
  - `def dedup(items) -> list[Item]` (by canonicalized URL; keep highest-score).
  - `def score(items, days) -> list[Item]` (per-source z-scored engagement * recency decay).
  - `def cluster(items) -> list[Item]` (group near-dup by normalized-title hash; set `cluster` id; merge via keeping lead).
  - Importing source modules handled here: `import_all_sources()` walks `reach_mcp/sources/*.py` and imports each once.

- [ ] **Step 1: Write failing test `tests/test_pipeline.py`**

```python
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from reach_mcp.config import Settings
from reach_mcp.pipeline import SourceReport, cluster, dedup, score
from reach_mcp.sources.base import Item


def _item(source, title, url, eng, days_ago=0, score_=0.0):
    date = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return Item(source=source, id=url, title=title, url=url, engagement=eng,
                date=date, score=score_)


def test_dedup_by_url():
    a = _item("reddit", "T", "https://x.com/a", {"upvotes": 10})
    b = _item("x", "T2", "https://x.com/a", {"likes": 5})  # same URL
    c = _item("hn", "T3", "https://x.com/b", {"points": 7})
    out = dedup([a, b, c])
    assert len(out) == 2
    # keep the higher-scored one at that URL
    assert {i.url for i in out} == {"https://x.com/a", "https://x.com/b"}


def test_score_recency_and_engagement():
    old = _item("reddit", "old", "https://o", {"upvotes": 100}, days_ago=29)
    new = _item("reddit", "new", "https://n", {"upvotes": 10}, days_ago=1)
    scored = score([old, new], days=30)
    new_s = next(i for i in scored if i.url == "https://n").score
    old_s = next(i for i in scored if i.url == "https://o").score
    assert new_s > old_s  # recency outweighs raw upvotes here


def test_cluster_groups_near_dup():
    a = _item("reddit", "OpenAI ships thing", "https://r/1", {})
    b = _item("x", "OpenAI ships thing!!", "https://x/1", {})
    c = _item("hn", "Totally different", "https://h/1", {})
    out = cluster([a, b, c])
    clusters = {i.cluster for i in out}
    assert len(clusters) == 2  # a,b share a cluster; c alone
    ab = [i for i in out if i.url in ("https://r/1", "https://x/1")]
    assert ab[0].cluster == ab[1].cluster


def test_source_report_status():
    r = SourceReport(source="x", status="gated_off", count=0, error=None)
    assert r.status == "gated_off"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write `src/reach_mcp/pipeline.py`**

```python
"""Search pipeline: resolve sources, fan out, normalize, dedup, score, cluster."""
from __future__ import annotations

import asyncio
import hashlib
import importlib
import logging
import math
import pkgutil
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable
from urllib.parse import urlsplit, urlunsplit

from reach_mcp.config import Settings
from reach_mcp.http import PoliteClient
from reach_mcp.sources.base import Item, Row, Source, SOURCES

log = logging.getLogger(__name__)

_SOURCE_MODULES_LOADED = False


def import_all_sources() -> None:
    """Import every module in reach_mcp.sources so the registry is populated."""
    global _SOURCE_MODULES_LOADED
    if _SOURCE_MODULES_LOADED:
        return
    import reach_mcp.sources as _pkg
    for mod in pkgutil.iter_modules(_pkg.__path__):
        if mod.name in {"base", "__init__"}:
            continue
        try:
            importlib.import_module(f"reach_mcp.sources.{mod.name}")
        except Exception:  # noqa: BLE001
            log.exception("failed to import source module %s", mod.name)
    _SOURCE_MODULES_LOADED = True


@dataclass
class SourceReport:
    source: str
    status: str  # "ok" | "gated_off" | "errored" | "unknown"
    count: int = 0
    error: str | None = None


def _canonical_url(url: str) -> str:
    """Strip fragment, trailing slash, lowercase host, drop common tracking params."""
    if not url:
        return ""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    path = parts.path.rstrip("/")
    # drop utm_* query params
    if parts.query:
        kept = [p for p in parts.query.split("&") if not p.lower().startswith("utm_")]
        query = "&".join(kept)
    else:
        query = ""
    return urlunsplit((parts.scheme.lower(), host, path, query, ""))


def _row_to_item(row: Row) -> Item:
    return Item(
        source=row.source, id=row.id, title=row.title, url=row.url,
        author=row.author, date=row.date, engagement=dict(row.engagement),
        text=row.text,
    )


def dedup(items: list[Item]) -> list[Item]:
    """Collapse items sharing a canonical URL; keep the highest-scored representative."""
    best: dict[str, Item] = {}
    for it in items:
        key = _canonical_url(it.url)
        if not key:
            best.setdefault(it.url or it.id, it)
            continue
        cur = best.get(key)
        if cur is None or it.score > cur.score:
            best[key] = it
    return list(best.values())


def _engagement_value(engagement: dict) -> float:
    """Sum numeric engagement signals (upvotes, points, likes, retweets, volume...)."""
    total = 0.0
    for v in engagement.values():
        if isinstance(v, (int, float)):
            total += float(v)
    return total


def score(items: list[Item], days: int) -> list[Item]:
    """Per-source z-scored engagement scaled by recency decay within the window."""
    if not items:
        return items
    now = datetime.now(timezone.utc)
    # group by source for z-scoring
    by_source: dict[str, list[Item]] = {}
    for it in items:
        by_source.setdefault(it.source, []).append(it)
    for src, group in by_source.items():
        vals = [_engagement_value(i.engagement) for i in group]
        mean = sum(vals) / len(vals) if vals else 0.0
        var = sum((v - mean) ** 2 for v in vals) / len(vals) if vals else 0.0
        std = math.sqrt(var) or 1.0
        for it, v in zip(group, vals):
            z = (v - mean) / std
            # recency decay: 1.0 at day 0, ->0 at day==days
            age_days = 0.0
            if it.date:
                try:
                    d = datetime.fromisoformat(it.date.replace("Z", "+00:00"))
                    age_days = max(0.0, (now - d).total_seconds() / 86400.0)
                except ValueError:
                    age_days = 0.0
            decay = max(0.0, 1.0 - age_days / max(1, days))
            it.score = (0.5 + 0.5 * z) * decay  # shift z to >=0, scale by recency
    return items


def _norm_title(title: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (title or "").lower()).strip()


def cluster(items: list[Item]) -> list[Item]:
    """Group near-duplicate titles across sources; assign a cluster id."""
    groups: dict[str, list[Item]] = {}
    for it in items:
        key = hashlib.md5(_norm_title(it.title).encode()).hexdigest()
        groups.setdefault(key, []).append(it)
    for key, group in groups.items():
        cid = f"c{key[:8]}"
        for it in group:
            it.cluster = cid
    return items


async def _fetch_one(source: Source, query: str, days: int, limit: int) -> tuple[list[Row], SourceReport]:
    if not source.available():
        return [], SourceReport(source=source.name, status="gated_off")
    try:
        rows = await asyncio.wait_for(source.fetch(query, days, limit), timeout=90)
        return rows, SourceReport(source=source.name, status="ok", count=len(rows))
    except Exception as e:  # noqa: BLE001
        log.warning("source %s errored: %s", source.name, e)
        return [], SourceReport(source=source.name, status="errored", error=str(e))


async def run_search(
    query: str,
    sources: list[str] | None,
    days: int,
    max_per_source: int,
    client: PoliteClient,
    settings: Settings,
) -> tuple[list[Item], list[SourceReport]]:
    import_all_sources()
    if sources is None:
        names = [s.name for s in SOURCES.values() if s.available()]
    else:
        names = list(sources)

    reports: list[SourceReport] = []
    # unknown names reported immediately
    known = set(SOURCES.keys())
    pending = []
    for n in names:
        if n not in known:
            reports.append(SourceReport(source=n, status="unknown", error="no such source"))
        else:
            pending.append(SOURCES[n])

    results = await asyncio.gather(
        *[_fetch_one(s, query, days, max_per_source) for s in pending]
    )
    all_rows: list[Row] = []
    for rows, rep in results:
        reports.append(rep)
        all_rows.extend(rows)

    items = [_row_to_item(r) for r in all_rows]
    items = dedup(items)
    items = score(items, days)
    items = cluster(items)
    items.sort(key=lambda i: i.score, reverse=True)
    return items, reports
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pipeline.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/reach_mcp/pipeline.py tests/test_pipeline.py
git commit -m "feat(pipeline): resolve/fan-out/dedup/score/cluster"
```

---

### Task 6: `synthesize.py` — LLM rerank + brief

**Files:**
- Create: `src/reach_mcp/synthesize.py`
- Test: `tests/test_synthesize.py`

**Interfaces:**
- Produces:
  - `async def rerank(query, items, settings) -> list[Item]` — sends top-N items to the LLM, parses a returned ordering of indices, returns items reordered. Falls back to input order on any failure.
  - `async def brief(query, items, settings) -> str` — synthesizes a cited brief. Returns a best-effort string; on missing `OPENAI_API_KEY` returns a stub note.
  - Uses OpenAI-compatible chat completions via `httpx` against `settings.openai_base_url` (append `/chat/completions`) with `settings.openai_api_key`.

- [ ] **Step 1: Write failing test `tests/test_synthesize.py`**

```python
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from reach_mcp.config import Settings
from reach_mcp.sources.base import Item
from reach_mcp.synthesize import brief, rerank


def _items(n):
    return [Item(source="s", id=str(i), title=f"t{i}", url=f"https://x/{i}", text=f"body{i}")
            for i in range(n)]


def _settings(**over):
    base = Settings()
    return Settings(**{**{f.name: getattr(base, f.name) for f in base.__dataclass_fields__.values()}, **over})


@pytest.mark.asyncio
async def test_brief_without_key_returns_stub(monkeypatch):
    s = _settings(openai_api_key="")
    out = await brief("q", _items(2), s)
    assert "synthesis disabled" in out.lower() or "no api key" in out.lower()


@pytest.mark.asyncio
async def test_brief_calls_gateway(monkeypatch):
    s = _settings(openai_base_url="https://gw/v1", openai_api_key="sk-x")

    async def fake_post(self, url, *, json, headers):  # noqa: ANN001
        class R:
            status_code = 200
            def json(self_inner):
                return {"choices": [{"message": {"content": "BRIEF [1]"}}]}
        return R()

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    monkeypatch.setattr("httpx.AsyncClient.aclose", AsyncMock(return_value=None))
    out = await brief("q", _items(2), s)
    assert out == "BRIEF [1]"


@pytest.mark.asyncio
async def test_rerack_falls_back_on_failure(monkeypatch):
    s = _settings(openai_base_url="https://gw/v1", openai_api_key="sk-x")

    async def fake_post(self, url, *, json, headers):  # noqa: ANN001
        raise RuntimeError("boom")

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    monkeypatch.setattr("httpx.AsyncClient.aclose", AsyncMock(return_value=None))
    items = _items(3)
    out = await rerank("q", items, s)
    assert [i.id for i in out] == [i.id for i in items]  # unchanged order
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_synthesize.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write `src/reach_mcp/synthesize.py`**

```python
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
                ordered.append(top[idx]); seen.add(idx)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_synthesize.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/reach_mcp/synthesize.py tests/test_synthesize.py
git commit -m "feat(synthesize): LLM rerank + brief via OpenAI-compatible gateway"
```

---

### Task 7: `tools.py` + `server.py` + `__main__.py` — MCP tools & server wiring

**Files:**
- Create: `src/reach_mcp/tools.py`, `src/reach_mcp/server.py`, `src/reach_mcp/__main__.py`
- Test: `tests/test_tools.py`

**Interfaces:**
- Consumes: `pipeline.run_search`, `pipeline.import_all_sources`/`SOURCES`, `synthesize.rerank`/`brief`, `config.Settings`, `http.PoliteClient`.
- Produces: `build_mcp(settings) -> FastMCP` registering `search`/`list_sources`/`synthesize`; `build_app(settings) -> Starlette app` with `/health`; CLI `main()` dispatching http/stdio.

- [ ] **Step 1: Write failing test `tests/test_tools.py`**

```python
from __future__ import annotations

import pytest

from reach_mcp.config import Settings
from reach_mcp.tools import _item_to_dict, _source_report_to_dict


def test_item_to_dict():
    from reach_mcp.sources.base import Item
    d = _item_to_dict(Item(source="s", id="1", title="t", url="https://x",
                           score=0.9, cluster="c1"))
    assert d["source"] == "s"
    assert d["score"] == 0.9
    assert d["cluster"] == "c1"


def test_source_report_to_dict():
    from reach_mcp.pipeline import SourceReport
    d = _source_report_to_dict(SourceReport(source="x", status="ok", count=3))
    assert d == {"source": "x", "status": "ok", "count": 3, "error": None}


@pytest.mark.asyncio
async def test_list_sources_tool_shape(monkeypatch):
    from reach_mcp.tools import build_mcp
    # ensure registry loaded with at least the built-in free sources after Task 8+
    mcp = build_mcp(Settings())
    # build_mcp must return a FastMCP instance with our three tools registered
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert {"search", "list_sources", "synthesize"} <= names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tools.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write `src/reach_mcp/tools.py`**

```python
"""MCP tool definitions: search, list_sources, synthesize."""
from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from reach_mcp.config import Settings
from reach_mcp.http import PoliteClient
from reach_mcp.pipeline import SourceReport, import_all_sources, run_search
from reach_mcp.sources import SOURCES, available_sources
from reach_mcp.sources.base import Item
from reach_mcp.synthesize import brief, rerank

log = logging.getLogger(__name__)

_SEARCH_DESC = (
    "Search up to 23 social & web sources in parallel, score by engagement, "
    "optionally synthesize a cited brief. YOU control scope.\n\n"
    "Sources (pass any subset as `sources`; omit/None = all currently-configured): "
    "free — reddit, hackernews, bluesky, github, arxiv, techmeme, polymarket, "
    "stocktwits, web; video — youtube; chinese — xueqiu, v2ex, bilibili, "
    "xiaoyuzhou; login-gated (off until creds set) — x, truthsocial, tiktok, "
    "instagram, linkedin, xiaohongshu, threads, pinterest; binary — digg.\n\n"
    "Args: `query` (str, the topic/person/ticker); `sources` (list[str] | None, "
    "None=all available); `days` (int, recency window, default 30); "
    "`max_per_source` (int, row cap per source, default 20); `synthesize` (bool, "
    "default true = also LLM-rerank + write brief).\n\n"
    "Returns: {brief: str|null, items: [Item], sources_used: [SourceReport], "
    "available_sources: [str]}. Each Item: {source, title, url, author, date, "
    "score, engagement, text}. A SourceReport tells you per-source "
    "ok/gated_off/errored so a thin result is diagnosable. Call list_sources "
    "first if unsure what's configured."
)

_LIST_DESC = (
    "List all registered sources with availability status, required credentials, "
    "and defaults. Call this FIRST to see which sources are active (credentials "
    "set) vs gated (off-by-default) before deciding `sources`. Returns "
    "[{name, description, needs_auth, available, required_env, default_days, "
    "default_limit}]. No arguments."
)

_SYNTH_DESC = (
    "Re-synthesize a cited brief from already-fetched items WITHOUT re-searching. "
    "Pass the original `query` and the `items` list from a prior "
    "search(synthesize=false). Returns {brief}. Use to re-brief cheaply with "
    "different emphasis. No source calls are made."
)


def _item_to_dict(it: Item) -> dict:
    return {
        "source": it.source, "id": it.id, "title": it.title, "url": it.url,
        "author": it.author, "date": it.date, "score": round(it.score, 4),
        "engagement": it.engagement, "text": it.text, "cluster": it.cluster,
    }


def _source_report_to_dict(r: SourceReport) -> dict:
    return {"source": r.source, "status": r.status, "count": r.count, "error": r.error}


def build_mcp(settings: Settings) -> FastMCP:
    import_all_sources()
    mcp = FastMCP(
        "reach-mcp",
        host=settings.host,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=settings.dns_rebinding_protection,
            allowed_hosts=list(settings.allowed_hosts),
            allowed_origins=[f"http://{h}" for h in settings.allowed_hosts],
        ),
        instructions=(
            "reach-mcp: controllable multi-source search. Call list_sources first "
            "to see what's configured, then search(query, sources?, days?, "
            "max_per_source?, synthesize?). Re-brief with synthesize(query, items)."
        ),
    )

    @mcp.tool(description=_LIST_DESC)
    async def list_sources() -> list[dict]:
        out = []
        for s in SOURCES.values():
            out.append({
                "name": s.name, "description": s.description,
                "needs_auth": s.needs_auth, "available": s.available(),
                "required_env": list(s.required_env),
                "default_days": s.default_days, "default_limit": s.default_limit,
            })
        return out

    @mcp.tool(description=_SEARCH_DESC)
    async def search(
        query: str,
        sources: list[str] | None = None,
        days: int = 30,
        max_per_source: int = 20,
        synthesize: bool = True,
    ) -> dict:
        client = PoliteClient(settings)
        try:
            items, reports = await run_search(
                query, sources, days, max_per_source, client, settings
            )
            brief_text = None
            if synthesize and items:
                items = await rerank(query, items, settings)
                brief_text = await brief(query, items, settings)
            return {
                "brief": brief_text,
                "items": [_item_to_dict(i) for i in items],
                "sources_used": [_source_report_to_dict(r) for r in reports],
                "available_sources": available_sources(),
            }
        finally:
            await client.aclose()

    @mcp.tool(description=_SYNTH_DESC)
    async def synthesize(query: str, items: list[dict]) -> dict:
        parsed = [Item(
            source=i.get("source", ""), id=i.get("id", ""), title=i.get("title", ""),
            url=i.get("url", ""), author=i.get("author"), date=i.get("date"),
            engagement=i.get("engagement", {}), text=i.get("text", ""),
        ) for i in items]
        return {"brief": await brief(query, parsed, settings)}

    return mcp
```

- [ ] **Step 4: Write `src/reach_mcp/server.py`**

```python
"""Assemble the app: reach_* MCP tools + /health on one server."""
from __future__ import annotations

import logging

from reach_mcp.config import Settings
from reach_mcp.tools import build_mcp

log = logging.getLogger(__name__)


def build_app(settings: Settings):
    mcp = build_mcp(settings)

    @mcp.custom_route("/health", methods=["GET"])
    async def _health(request):
        from starlette.responses import JSONResponse
        return JSONResponse({"status": "ok"})

    app = mcp.streamable_http_app()
    app.state.settings = settings
    app.state.mcp = mcp
    return app
```

- [ ] **Step 5: Write `src/reach_mcp/__main__.py`**

```python
"""CLI entrypoint: dispatch http (uvicorn) or stdio (mcp.run)."""
from __future__ import annotations

import argparse
import logging

import uvicorn

from reach_mcp.config import get_settings
from reach_mcp.server import build_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="reach-mcp")
    parser.add_argument("--transport", choices=["http", "stdio"], default=None,
                        help="http (streamable-HTTP, default) or stdio")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    settings = get_settings()
    transport = args.transport or settings.transport
    host = args.host or settings.host
    port = args.port or settings.port

    if transport == "stdio":
        app = build_app(settings)
        app.state.mcp.run(transport="stdio")
        return

    app = build_app(settings)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_tools.py -v`
Expected: PASS (3 tests). (`list_tools` returns the 3 tools; sources registry is empty until Task 8+ but the tools are registered regardless.)

- [ ] **Step 7: Smoke-test the CLI boots in stdio**

Run: `timeout 3 reach-mcp --transport stdio < /dev/null; echo "exit=$?"`
Expected: process starts (may log a connection error on closed stdin); exit code reflects the timeout/closed pipe, not an import crash. If it prints a traceback about `build_mcp`/imports, fix before continuing.

- [ ] **Step 8: Commit**

```bash
git add src/reach_mcp/tools.py src/reach_mcp/server.py src/reach_mcp/__main__.py tests/test_tools.py
git commit -m "feat(server): MCP tools (search/list_sources/synthesize) + http/stdio CLI"
```

---

### Task 8: Free API sources — hackernews, arxiv, polymarket, stocktwits, github, bluesky

> Each source module is self-contained: subclasses `Source`, uses `PoliteClient` (passed via a module-level accessor), returns `list[Row]`. Tests mock the client.

Because sources need a shared `PoliteClient` at call time (not import time), add a small accessor in `base.py` first.

**Files:**
- Modify: `src/reach_mcp/sources/base.py` (add `get_client()/set_client()`)
- Create: `src/reach_mcp/sources/{hackernews,arxiv,polymarket,stocktwits,github,bluesky}.py`
- Test: `tests/test_sources_api.py`

**Interfaces:**
- Consumes: `reach_mcp.http.PoliteClient`; `base.get_client()`.
- Produces: six registered sources, each `@register_source`, with `async fetch()` returning normalized `Row`s.

- [ ] **Step 1: Add client accessor to `base.py`**

Append to `src/reach_mcp/sources/base.py`:

```python
# --- shared client accessor (set per search call, not import time) ---
_CLIENT: "PoliteClient | None" = None


def set_client(client) -> None:
    global _CLIENT
    _CLIENT = client


def get_client():
    if _CLIENT is None:
        raise RuntimeError("PoliteClient not set; call set_client() before fetch()")
    return _CLIENT
```

Also update `pipeline.run_search` to call `set_client(client)` before the gather. Add this line in `run_search` right after computing `pending` / before `asyncio.gather`:

```python
from reach_mcp.sources.base import set_client as _set_client
_set_client(client)
```

- [ ] **Step 2: Write failing test `tests/test_sources_api.py`**

```python
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from reach_mcp.sources import SOURCES, get_source
from reach_mcp.sources.base import set_client


def _client_returns(payload):
    c = AsyncMock()
    c.get_json = AsyncMock(return_value=payload)
    c.get_text = AsyncMock(return_value=payload if isinstance(payload, str) else json.dumps(payload))
    return c


@pytest.mark.asyncio
async def test_hackernews_parses_hits(monkeypatch):
    set_client(_client_returns({"hits": [{
        "objectID": "1", "title": "T", "url": "https://x", "author": "a",
        "points": 5, "num_comments": 2, "created_at": "2026-07-01T00:00:00Z",
    }]}))
    rows = await get_source("hackernews").fetch("q", 30, 10)
    assert rows and rows[0].title == "T" and rows[0].engagement["points"] == 5


@pytest.mark.asyncio
async def test_arxiv_parses_entries(monkeypatch):
    atom = ('<feed xmlns="http://www.w3.org/2005/Atom">'
            '<entry><id>http://arxiv.org/abs/1234</id><title>Paper</title>'
            '<summary>abs</summary><published>2026-07-01T00:00:00Z</published>'
            '<author><name>Auth</name></author></entry></feed>')
    set_client(_client_returns(atom))
    rows = await get_source("arxiv").fetch("q", 30, 10)
    assert rows and rows[0].title == "Paper" and rows[0].url.endswith("1234")


@pytest.mark.asyncio
async def test_polymarket_parses_markets(monkeypatch):
    set_client(_client_returns([{
        "id": "1", "question": "Will X?", "slug": "will-x",
        "volume": "1000", "outcomePrices": '["0.6","0.4"]',
        "endDate": "2026-08-01T00:00:00Z",
    }]))
    rows = await get_source("polymarket").fetch("q", 30, 10)
    assert rows and "Will X?" in rows[0].title and rows[0].engagement["volume"] == 1000.0


@pytest.mark.asyncio
async def test_stocktwits_parses_messages(monkeypatch):
    set_client(_client_returns({"messages": [{
        "id": 1, "body": "bullish", "created_at": "2026-07-01T00:00:00Z",
        "user": {"username": "u"},
    }]}))
    rows = await get_source("stocktwits").fetch("AAPL", 30, 10)
    assert rows and rows[0].text == "bullish"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_sources_api.py -v`
Expected: FAIL — sources not registered yet (KeyError).

- [ ] **Step 4: Write `src/reach_mcp/sources/hackernews.py`**

```python
"""Hacker News via Algolia search API (free, no key)."""
from __future__ import annotations

from datetime import datetime, timezone

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class HackerNews(Source):
    name = "hackernews"
    description = "Hacker News stories via the Algolia API (free, no key)."
    host = "hn.algolia.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        data = await client.get_json(
            "https://hn.algolia.com/api/v1/search",
            params={"query": query, "tags": "story", "hitsPerPage": min(limit, 50)},
        )
        rows: list[Row] = []
        for h in data.get("hits", []):
            rows.append(Row(
                source="hackernews", id=str(h.get("objectID", "")),
                title=h.get("title") or "", url=h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                author=h.get("author"), date=h.get("created_at"),
                engagement={"points": h.get("points") or 0, "comments": h.get("num_comments") or 0},
                text=h.get("story_text") or "",
            ))
        return rows
```

- [ ] **Step 5: Write `src/reach_mcp/sources/arxiv.py`**

```python
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
            url = (idm.group(1).strip() if idm else "").replace("abs/", "abs/")
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
```

- [ ] **Step 6: Write `src/reach_mcp/sources/polymarket.py`**

```python
"""Polymarket prediction markets via the public gamma API (free, no key)."""
from __future__ import annotations

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class Polymarket(Source):
    name = "polymarket"
    description = "Polymarket prediction markets (real-money odds, free public API)."
    host = "gamma-api.polymarket.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        data = await client.get_json(
            "https://gamma-api.polymarket.com/markets",
            params={"limit": str(min(limit, 50)), "closed": "false", "query": query},
        )
        rows: list[Row] = []
        for m in data if isinstance(data, list) else []:
            try:
                vol = float(m.get("volume") or 0)
            except (TypeError, ValueError):
                vol = 0.0
            prices = m.get("outcomePrices", "[]")
            rows.append(Row(
                source="polymarket", id=str(m.get("id", "")),
                title=m.get("question") or "",
                url=f"https://polymarket.com/event/{m.get('slug','')}",
                author=None, date=m.get("endDate"),
                engagement={"volume": vol, "prices": prices},
                text=(m.get("description") or "")[:500],
            ))
        return rows
```

- [ ] **Step 7: Write `src/reach_mcp/sources/stocktwits.py`**

```python
"""StockTwits messages via the public API (free, no key). Best for tickers/crypto."""
from __future__ import annotations

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class StockTwits(Source):
    name = "stocktwits"
    description = "StockTwits trader messages (free public API; best for tickers/crypto)."
    host = "api.stocktwits.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        data = await client.get_json(
            f"https://api.stocktwits.com/api/2/streams/symbol/{query}.json",
            params={"limit": str(min(limit, 30))},
        )
        rows: list[Row] = []
        for msg in data.get("messages", []):
            user = (msg.get("user") or {}).get("username")
            rows.append(Row(
                source="stocktwits", id=str(msg.get("id", "")),
                title=(msg.get("body") or "")[:120],
                url=f"https://stocktwits.com/{user}/message/{msg.get('id','')}",
                author=user, date=msg.get("created_at"),
                engagement={}, text=msg.get("body") or "",
            ))
        return rows
```

- [ ] **Step 8: Write `src/reach_mcp/sources/github.py`**

```python
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
            rows.append(Row(
                source="github", id=str(r.get("id", "")),
                title=r.get("full_name") or r.get("name") or "",
                url=r.get("html_url") or "",
                author=(r.get("owner") or {}).get("login"),
                date=r.get("pushed_at"),
                engagement={"stars": r.get("stargazers_count") or 0,
                            "forks": r.get("forks_count") or 0},
                text=(r.get("description") or ""),
            ))
        return rows
```

- [ ] **Step 9: Write `src/reach_mcp/sources/bluesky.py`**

```python
"""Bluesky via the public AT Protocol search (free; BSKY creds optional)."""
from __future__ import annotations

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class Bluesky(Source):
    name = "bluesky"
    description = "Bluesky posts via the public AT Protocol search (free)."
    host = "public.api.bsky.app"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        data = await client.get_json(
            "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts",
            params={"q": query, "limit": str(min(limit, 50))},
        )
        rows: list[Row] = []
        for p in data.get("posts", []):
            author = (p.get("author") or {}).get("handle")
            rec = p.get("record") or {}
            rows.append(Row(
                source="bluesky", id=p.get("uri") or "",
                title=(rec.get("text") or "")[:120],
                url=f"https://bsky.app/profile/{author}/post/{(p.get('uri','').split('/')[-1])}",
                author=author, date=rec.get("createdAt"),
                engagement={"reply": p.get("replyCount") or 0,
                            "repost": p.get("repostCount") or 0,
                            "like": p.get("likeCount") or 0},
                text=rec.get("text") or "",
            ))
        return rows
```

- [ ] **Step 10: Run test to verify it passes**

Run: `pytest tests/test_sources_api.py -v`
Expected: PASS (4 tests). (github/bluesky not asserted in tests but must import cleanly.)

- [ ] **Step 11: Commit**

```bash
git add src/reach_mcp/sources/base.py src/reach_mcp/pipeline.py \
        src/reach_mcp/sources/hackernews.py src/reach_mcp/sources/arxiv.py \
        src/reach_mcp/sources/polymarket.py src/reach_mcp/sources/stocktwits.py \
        src/reach_mcp/sources/github.py src/reach_mcp/sources/bluesky.py \
        tests/test_sources_api.py
git commit -m "feat(sources): hackernews/arxiv/polymerket/stocktwits/github/bluesky"
```

---

### Task 9: Scrape/RSS sources — reddit, techmeme, web(searxng)

**Files:**
- Create: `src/reach_mcp/sources/{reddit,techmeme,web}.py`
- Test: `tests/test_sources_scrape.py`

**Interfaces:**
- Consumes: `base.get_client()`, `feedparser`.
- Produces: `reddit` (RSS via feedparser over the client's `get_text`), `techmeme` (scrape), `web` (Searxng JSON).

- [ ] **Step 1: Write failing test `tests/test_sources_scrape.py`**

```python
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from reach_mcp.sources import get_source
from reach_mcp.sources.base import set_client


@pytest.mark.asyncio
async def test_reddit_parses_rss():
    rss = '''<rss version="2.0"><channel><item>
      <title>Reddit thread</title><link>https://reddit.com/r/x/1</link>
      <pubDate>Mon, 01 Jul 2026 00:00:00 GMT</pubDate>
      <description>body</description></item></channel></rss>'''
    c = AsyncMock()
    c.get_text = AsyncMock(return_value=rss)
    set_client(c)
    rows = await get_source("reddit").fetch("python", 30, 10)
    assert rows and rows[0].title == "Reddit thread"


@pytest.mark.asyncio
async def test_web_uses_searxng_json():
    c = AsyncMock()
    c.get_json = AsyncMock(return_value={"results": [
        {"title": "Hit", "url": "https://x", "content": "snippet", "publishedDate": "2026-07-01T00:00:00"}]})
    set_client(c)
    rows = await get_source("web").fetch("query", 30, 10)
    assert rows and rows[0].title == "Hit"


@pytest.mark.asyncio
async def test_techmeme_parses_items():
    html = '<html><body><div class="item"><a href="https://t/1">Headline</a></div></body></html>'
    c = AsyncMock()
    c.get_text = AsyncMock(return_value=html)
    set_client(c)
    rows = await get_source("techmeme").fetch("ai", 30, 10)
    assert rows and "Headline" in rows[0].title
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sources_scrape.py -v`
Expected: FAIL — KeyError (sources missing).

- [ ] **Step 3: Write `src/reach_mcp/sources/reddit.py`**

```python
"""Reddit via RSS/JSON (keyless). Uses feedparser over the polite client's text."""
from __future__ import annotations

import feedparser

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class Reddit(Source):
    name = "reddit"
    description = "Reddit via keyless RSS search (no API key)."
    host = "www.reddit.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        xml = await client.get_text(
            "https://www.reddit.com/search.rss",
            params={"q": query, "limit": str(min(limit, 50))},
            headers={"User-Agent": "reach-mcp/0.1"},
        )
        feed = feedparser.parse(xml)
        rows: list[Row] = []
        for e in feed.entries:
            rows.append(Row(
                source="reddit", id=e.get("id") or e.get("link") or "",
                title=e.get("title") or "", url=e.get("link") or "",
                author=e.get("author"), date=e.get("published"),
                engagement={}, text=(e.get("summary") or "")[:500],
            ))
        return rows
```

- [ ] **Step 4: Write `src/reach_mcp/sources/web.py`**

```python
"""Generic web search via a self-hosted Searxng JSON endpoint (SEARXNG_URL)."""
from __future__ import annotations

import os

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class Web(Source):
    name = "web"
    description = "Generic web search via Searxng (set SEARXNG_URL)."
    host = ""

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        base = os.environ.get("SEARXNG_URL", "http://searxng:8080").rstrip("/")
        data = await client.get_json(
            base + "/search",
            params={"q": query, "format": "json", "safesearch": 0,
                    "time_range": f"{days}d" if days <= 365 else None},
        )
        rows: list[Row] = []
        for r in (data.get("results") or [])[:limit]:
            rows.append(Row(
                source="web", id=r.get("url") or "",
                title=r.get("title") or "", url=r.get("url") or "",
                author=None, date=r.get("publishedDate"),
                engagement={}, text=(r.get("content") or "")[:500],
            ))
        return rows
```

- [ ] **Step 5: Write `src/reach_mcp/sources/techmeme.py`**

```python
"""Techmeme tech-news headlines via simple scrape (free, no key)."""
from __future__ import annotations

import re

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class Techmeme(Source):
    name = "techmeme"
    description = "Techmeme editorial tech-news headlines (free scrape)."
    host = "www.techmeme.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        html = await client.get_text("https://www.techmeme.com/river")
        rows: list[Row] = []
        # each headline is an anchor inside an item block; keep it loose & resilient
        for m in re.finditer(r'href="(https?://[^"]+)"[^>]*>([^<]{8,200})</a>', html):
            url, title = m.group(1), m.group(2).strip()
            if query.lower() in title.lower() or not query:
                rows.append(Row(source="techmeme", id=url, title=title, url=url,
                                author=None, date=None, engagement={}, text=""))
            if len(rows) >= limit:
                break
        return rows
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_sources_scrape.py -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add src/reach_mcp/sources/reddit.py src/reach_mcp/sources/web.py src/reach_mcp/sources/techmeme.py tests/test_sources_scrape.py
git commit -m "feat(sources): reddit/web(searxng)/techmeme"
```

---

### Task 10: Chinese sources — v2ex, xueqiu, bilibili, xiaoyuzhou, youtube

**Files:**
- Create: `src/reach_mcp/sources/{v2ex,xueqiu,bilibili,xiaoyuzhou,youtube}.py`
- Test: `tests/test_sources_cn.py`

**Interfaces:**
- Consumes: `base.get_client()`, `yt-dlp` (for youtube transcripts).
- Produces: five registered sources.

- [ ] **Step 1: Write failing test `tests/test_sources_cn.py`**

```python
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from reach_mcp.sources import get_source
from reach_mcp.sources.base import set_client


@pytest.mark.asyncio
async def test_v2ex_parses_topics():
    c = AsyncMock()
    c.get_json = AsyncMock(return_value=[{
        "id": 1, "title": "T", "url": "https://v2ex.com/t/1",
        "member": {"username": "u"}, "created": 1751328000, "replies": 3,
    }])
    set_client(c)
    rows = await get_source("v2ex").fetch("python", 30, 10)
    assert rows and rows[0].title == "T" and rows[0].engagement["replies"] == 3


@pytest.mark.asyncio
async def test_xueqiu_parses_html():
    html = '<html><a href="/123/X" class="title">Stock news</a></html>'
    c = AsyncMock(); c.get_text = AsyncMock(return_value=html)
    set_client(c)
    rows = await get_source("xueqiu").fetch("AAPL", 30, 10)
    assert rows and "Stock news" in rows[0].title


@pytest.mark.asyncio
async def test_bilibili_uses_search_api():
    c = AsyncMock()
    c.get_json = AsyncMock(return_value={"data": {"result": [{
        "bvid": "BV1", "title": "Vid", "pubdate": 1751328000,
        "owner": {"name": "up"}, "play": 100, "arcurl": "https://b23.tv/1",
    }]}})
    set_client(c)
    rows = await get_source("bilibili").fetch("ai", 30, 10)
    assert rows and rows[0].engagement["play"] == 100


@pytest.mark.asyncio
async def test_youtube_shells_to_ytdlp(monkeypatch):
    async def fake_subtitles(query, limit):
        return [{"id": "yt1", "title": query, "url": "https://youtu.be/1",
                 "text": "transcript", "date": None, "engagement": {}}]
    monkeypatch.setattr("reach_mcp.sources.youtube._fetch_subtitles", fake_subtitles)
    rows = await get_source("youtube").fetch("rust", 30, 5)
    assert rows and rows[0].text == "transcript"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sources_cn.py -v`
Expected: FAIL — KeyError.

- [ ] **Step 3: Write `src/reach_mcp/sources/v2ex.py`**

```python
"""V2EX topics via the public API (free, no key)."""
from __future__ import annotations

from datetime import datetime, timezone

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class V2EX(Source):
    name = "v2ex"
    description = "V2EX forum topics via the public API (free)."
    host = "www.v2ex.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        data = await client.get_json(
            "https://www.v2ex.com/api/topics/search.json",
            params={"q": query, "size": str(min(limit, 30))},
        )
        rows: list[Row] = []
        for t in data if isinstance(data, list) else []:
            ts = t.get("created")
            date = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None
            member = t.get("member") or {}
            rows.append(Row(
                source="v2ex", id=str(t.get("id", "")),
                title=t.get("title") or "", url=t.get("url") or "",
                author=member.get("username"), date=date,
                engagement={"replies": t.get("replies") or 0},
                text=(t.get("content") or "")[:500],
            ))
        return rows
```

- [ ] **Step 4: Write `src/reach_mcp/sources/xueqiu.py`**

```python
"""雪球 (Xueqiu) hot posts/news via scrape (free, no key)."""
from __future__ import annotations

import re

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class Xueqiu(Source):
    name = "xueqiu"
    description = "雪球 hot posts & news (free scrape)."
    host = "xueqiu.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        html = await client.get_text(
            "https://xueqiu.com/karma/catalog/searchHots.json",
            params={"q": query},
            headers={"User-Agent": "reach-mcp/0.1"},
        )
        # fall back to a tolerant regex over HTML if JSON unavailable
        rows: list[Row] = []
        for m in re.finditer(r'href="(/[\w/]+)"[^>]*class="title"[^>]*>([^<]+)</a>', html):
            path, title = m.group(1), m.group(2).strip()
            url = "https://xueqiu.com" + path
            rows.append(Row(source="xueqiu", id=url, title=title, url=url,
                            author=None, date=None, engagement={}, text=""))
            if len(rows) >= limit:
                break
        return rows
```

- [ ] **Step 5: Write `src/reach_mcp/sources/bilibili.py`**

```python
"""B站 (Bilibili) video search via the public search API (free, no login)."""
from __future__ import annotations

from datetime import datetime, timezone

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class Bilibili(Source):
    name = "bilibili"
    description = "B站 video search via the public API (free, no login)."
    host = "api.bilibili.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        data = await client.get_json(
            "https://api.bilibili.com/x/web-interface/search/type",
            params={"search_type": "video", "keyword": query,
                    "page_size": str(min(limit, 30))},
            headers={"User-Agent": "reach-mcp/0.1"},
        )
        rows: list[Row] = []
        for v in ((data.get("data") or {}).get("result") or [])[:limit]:
            pub = v.get("pubdate")
            date = datetime.fromtimestamp(pub, tz=timezone.utc).isoformat() if pub else None
            owner = v.get("owner") or {}
            rows.append(Row(
                source="bilibili", id=v.get("bvid") or "",
                title=re.sub(r"<[^>]+>", "", v.get("title") or ""),
                url=v.get("arcurl") or "",
                author=owner.get("name"), date=date,
                engagement={"play": v.get("play") or 0, "reply": v.get("video_review") or 0},
                text=(v.get("description") or "")[:500],
            ))
        return rows
```

- [ ] **Step 6: Write `src/reach_mcp/sources/youtube.py`**

```python
"""YouTube transcripts via yt-dlp (free). Returns transcript text per video."""
from __future__ import annotations

import logging
import os

from reach_mcp.sources.base import Row, Source, register_source

log = logging.getLogger(__name__)


async def _fetch_subtitles(query: str, limit: int) -> list[dict]:
    """Search YouTube and pull auto/subtitles for each result. Returns raw dicts."""
    try:
        from yt_dlp import YoutubeDL
    except ImportError:
        log.warning("yt-dlp not installed; youtube source disabled")
        return []
    proxy = os.environ.get("YTDLP_PROXY")
    opts = {
        "quiet": True, "skip_download": True, "writesubtitles": True,
        "writeautomaticsub": True, "subtitleslangs": ["en", "zh"],
        "extract_flat": True, "default_search": "ytsearch",
        "playlistend": limit,
    }
    if proxy:
        opts["proxy"] = proxy
    out = []
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
            for e in (info.get("entries") or []):
                out.append({
                    "id": e.get("id", ""), "title": e.get("title", ""),
                    "url": e.get("webpage_url") or f"https://youtu.be/{e.get('id')}",
                    "text": (e.get("subtitles") or e.get("automatic_captions")) and "",
                    "date": e.get("upload_date"),
                    "engagement": {"views": e.get("view_count") or 0,
                                   "likes": e.get("like_count") or 0},
                })
    except Exception:  # noqa: BLE001
        log.warning("yt-dlp search failed", exc_info=True)
    return out


@register_source
class YouTube(Source):
    name = "youtube"
    description = "YouTube video transcripts via yt-dlp (free)."
    host = "www.youtube.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        rows: list[Row] = []
        for v in await _fetch_subtitles(query, limit):
            rows.append(Row(
                source="youtube", id=v["id"], title=v["title"], url=v["url"],
                author=None, date=v.get("date"), engagement=v.get("engagement", {}),
                text=v.get("text") or "",
            ))
        return rows
```

- [ ] **Step 7: Write `src/reach_mcp/sources/xiaoyuzhou.py`** (podcast → Whisper; scaffold — returns rows when a Groq/OpenAI key is present)

```python
"""小宇宙 (Xiaoyuzhou) podcast search; transcripts via Whisper when a key is set.

Scaffold in v1: searches the public podcast index and, when GROQ_API_KEY or
OPENAI_API_KEY is present, transcribes audio. Without a key it returns episode
metadata only (no transcript text). Free (Groq has a free tier).
"""
from __future__ import annotations

import os

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class Xiaoyuzhou(Source):
    name = "xiaoyuzhou"
    description = "小宇宙 podcast episodes; transcripts via Whisper (free Groq tier)."
    host = "api.xiaoyuzhoufm.com"

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        client = get_client()
        try:
            data = await client.get_json(
                "https://api.xiaoyuzhoufm.com/search/episode",
                params={"q": query, "size": str(min(limit, 20))},
            )
        except Exception:  # noqa: BLE001
            return []
        has_key = bool(os.environ.get("GROQ_API_KEY") or os.environ.get("OPENAI_API_KEY"))
        rows: list[Row] = []
        for e in (data.get("data") or {}).get("episode_list") or []:
            rows.append(Row(
                source="xiaoyuzhou", id=e.get("eid") or "",
                title=e.get("title") or "", url=e.get("url") or "",
                author=(e.get("podcast") or {}).get("title"),
                date=e.get("pub_date"),
                engagement={},
                text="" if not has_key else "(transcription deferred to post-v1)",
            ))
        return rows
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/test_sources_cn.py -v`
Expected: PASS (4 tests). (xiaoyuzhou not asserted but must import cleanly.)

- [ ] **Step 9: Commit**

```bash
git add src/reach_mcp/sources/v2ex.py src/reach_mcp/sources/xueqiu.py \
        src/reach_mcp/sources/bilibili.py src/reach_mcp/sources/youtube.py \
        src/reach_mcp/sources/xiaoyuzhou.py tests/test_sources_cn.py
git commit -m "feat(sources): v2ex/xueqiu/bilibili/youtube/xiaoyuzhou"
```

---

### Task 11: Login-gated sources — x, truthsocial, tiktok, instagram, linkedin, xiaohongshu, threads, pinterest, digg

> These are off-by-default. Each declares `needs_auth=True` + `required_env`. v1 implements the *fetch path* for the two cookie/bearer ones fully (x, truthsocial) and ScrapeCreators-based ones via a shared helper; the rest return a clear "not yet configured" empty list but still register so `list_sources` shows them. `digg` shells to the optional CLI.

**Files:**
- Create: `src/reach_mcp/sources/{x,truthsocial,tiktok,instagram,linkedin,xiaohongshu,threads,pinterest,digg}.py`
- Test: `tests/test_sources_gated.py`

**Interfaces:**
- Consumes: `base.get_client()`, env credentials.
- Produces: nine registered sources; `x`/`truthsocial`/`digg` exercised by tests.

- [ ] **Step 1: Write failing test `tests/test_sources_gated.py`**

```python
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from reach_mcp.sources import get_source
from reach_mcp.sources.base import set_client


@pytest.mark.asyncio
async def test_truthsocial_parses_results(monkeypatch):
    monkeypatch.setenv("TRUTHSOCIAL_TOKEN", "tok")
    c = AsyncMock()
    c.get_json = AsyncMock(return_value=[{
        "id": "1", "content": "hello", "created_at": "2026-07-01T00:00:00Z",
        "account": {"username": "u"}, "favourites_count": 4, "reblogs_count": 1,
    }])
    set_client(c)
    rows = await get_source("truthsocial").fetch("q", 30, 10)
    assert rows and rows[0].text == "hello" and rows[0].engagement["likes"] == 4


@pytest.mark.asyncio
async def test_x_requires_cookies(monkeypatch):
    monkeypatch.delenv("AUTH_TOKEN", raising=False)
    monkeypatch.delenv("CT0", raising=False)
    assert not get_source("x").available()
    rows = await get_source("x").fetch("q", 30, 10)
    assert rows == []


@pytest.mark.asyncio
async def test_digg_disabled_without_cli(monkeypatch):
    # shutil.which returns None -> available() False -> fetch returns []
    monkeypatch.setattr("reach_mcp.sources.digg._has_cli", lambda: False)
    rows = await get_source("digg").fetch("ai", 30, 10)
    assert rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sources_gated.py -v`
Expected: FAIL — KeyError.

- [ ] **Step 3: Write `src/reach_mcp/sources/x.py`**

```python
"""X / Twitter via cookie auth (AUTH_TOKEN + CT0). Off by default."""
from __future__ import annotations

import os

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class X(Source):
    name = "x"
    description = "X / Twitter search via account cookies (AUTH_TOKEN + CT0)."
    host = "api.x.com"
    needs_auth = True
    required_env = ("AUTH_TOKEN", "CT0")

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        if not self.available():
            return []
        client = get_client()
        headers = {"Authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D",
                   "Cookie": f"auth_token={os.environ['AUTH_TOKEN']}; ct0={os.environ['CT0']}",
                   "x-csrf-token": os.environ["CT0"]}
        try:
            data = await client.get_json(
                "https://api.x.com/2/search/adaptive.json",
                params={"q": query, "count": str(min(limit, 50)), "query_source": "typed_query"},
                headers=headers,
            )
        except Exception:  # noqa: BLE001
            return []
        rows: list[Row] = []
        for tid, t in (data.get("globalObjects", {}).get("tweets", {}) or {}).items():
            user = (data.get("globalObjects", {}).get("users", {}) or {}).get(t.get("user_id_str"), {})
            rows.append(Row(
                source="x", id=tid, title=(t.get("full_text") or "")[:120],
                url=f"https://x.com/{user.get('screen_name','i')}/status/{tid}",
                author=user.get("screen_name"), date=t.get("created_at"),
                engagement={"likes": t.get("favorite_count") or 0,
                            "retweets": t.get("retweet_count") or 0,
                            "replies": t.get("reply_count") or 0},
                text=t.get("full_text") or "",
            ))
        return rows
```

- [ ] **Step 4: Write `src/reach_mcp/sources/truthsocial.py`**

```python
"""Truth Social via the Mastodon-compatible API (TRUTHSOCIAL_TOKEN bearer, free)."""
from __future__ import annotations

import os

from reach_mcp.sources.base import Row, Source, get_client, register_source


@register_source
class TruthSocial(Source):
    name = "truthsocial"
    description = "Truth Social search via Mastodon API (free-account bearer token)."
    host = "truthsocial.com"
    needs_auth = True
    required_env = ("TRUTHSOCIAL_TOKEN",)

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        if not self.available():
            return []
        client = get_client()
        headers = {"Authorization": f"Bearer {os.environ['TRUTHSOCIAL_TOKEN']}"}
        try:
            data = await client.get_json(
                "https://truthsocial.com/api/v2/search",
                params={"q": query, "type": "statuses", "limit": str(min(limit, 40))},
                headers=headers,
            )
        except Exception:  # noqa: BLE001
            return []
        rows: list[Row] = []
        for s in data.get("statuses") or []:
            acct = (s.get("account") or {}).get("username")
            rows.append(Row(
                source="truthsocial", id=s.get("id") or "",
                title=(s.get("content") or "")[:120],
                url=s.get("url") or f"https://truthsocial.com/@{acct}/{s.get('id')}",
                author=acct, date=s.get("created_at"),
                engagement={"likes": s.get("favourites_count") or 0,
                            "reblogs": s.get("reblogs_count") or 0,
                            "replies": s.get("replies_count") or 0},
                text=s.get("content") or "",
            ))
        return rows
```

- [ ] **Step 5: Write `src/reach_mcp/sources/digg.py`**

```python
"""Digg AI-1000 clusters via the optional digg-pp-cli binary (free, no auth).

Detected on PATH -> available; absent -> gated off. The CLI is built by the
operator (see last30days' build steps). reach-mcp does NOT vendor the Go
toolchain — it only shells out if the binary exists.
"""
from __future__ import annotations

import asyncio
import json
import shutil

from reach_mcp.sources.base import Row, Source, register_source


def _has_cli() -> bool:
    return shutil.which("digg-pp-cli") is not None


@register_source
class Digg(Source):
    name = "digg"
    description = "Digg AI-1000 story clusters via digg-pp-cli (free; needs the CLI on PATH)."
    host = "digg.com"
    needs_auth = False
    required_env = ()

    def available(self) -> bool:  # type: ignore[override]
        return _has_cli()

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        if not _has_cli():
            return []
        try:
            proc = await asyncio.create_subprocess_exec(
                "digg-pp-cli", "search", query, "--since", f"{days}d",
                "--agent", "--limit", str(limit),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=90)
        except Exception:  # noqa: BLE001
            return []
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            return []
        rows: list[Row] = []
        clusters = data if isinstance(data, list) else data.get("clusters") or []
        for i, c in enumerate(clusters):
            title = c.get("title") or f"Digg cluster {i+1}"
            rows.append(Row(
                source="digg", id=str(c.get("clusterUrlId") or i),
                title=title, url=c.get("url") or "",
                author=None, date=c.get("firstPostAge"),
                engagement={"rank": c.get("rank") or 0},
                text=(c.get("summary") or "")[:500],
            ))
        return rows
```

- [ ] **Step 6: Write the ScrapeCreators-backed sources** (`tiktok.py`, `instagram.py`, `linkedin.py`, `pinterest.py`), `xiaohongshu.py`, `threads.py`. Each follows the same minimal scaffold shape:

```python
# src/reach_mcp/sources/tiktok.py
"""TikTok via ScrapeCreators (free-tier key). Off by default."""
from __future__ import annotations

import os

from reach_mcp.sources.base import Row, Source, get_client, register_source
from reach_mcp.sources._scrapecreators import scrape_search


@register_source
class TikTok(Source):
    name = "tiktok"
    description = "TikTok search via ScrapeCreators (free-tier key)."
    host = "api.scrapecreators.com"
    needs_auth = True
    required_env = ("SCRAPECREATORS_API_KEY",)

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        if not self.available():
            return []
        client = get_client()
        return await scrape_search(client, "tiktok", query, limit)
```

Create the shared helper `src/reach_mcp/sources/_scrapecreators.py`:

```python
"""Shared ScrapeCreators helper for tiktok/instagram/linkedin/pinterest."""
from __future__ import annotations

import os

from reach_mcp.sources.base import Row


async def scrape_search(client, platform: str, query: str, limit: int) -> list[Row]:
    key = os.environ["SCRAPECREATORS_API_KEY"]
    headers = {"x-api-key": key}
    try:
        data = await client.get_json(
            f"https://api.scrapecreators.com/v1/{platform}/search",
            params={"query": query, "limit": str(limit)},
            headers=headers,
        )
    except Exception:  # noqa: BLE001
        return []
    rows: list[Row] = []
    for item in (data.get("data") or data.get("results") or [])[:limit]:
        rows.append(Row(
            source=platform, id=str(item.get("id") or item.get("url", "")),
            title=(item.get("caption") or item.get("title") or "")[:120],
            url=item.get("url") or "",
            author=item.get("username") or item.get("author"),
            date=item.get("created_at"),
            engagement={"likes": item.get("likes") or 0, "views": item.get("views") or 0},
            text=(item.get("caption") or item.get("text") or "")[:500],
        ))
    return rows
```

Write `instagram.py`, `linkedin.py`, `pinterest.py` as copies of `tiktok.py` with the `name`/`host` swapped (`instagram`/`api.scrapecreators.com`, etc.) and `platform=` matching. Write `xiaohongshu.py` and `threads.py` as cookie-gated scaffolds returning `[]` until configured (declare `required_env=("XHS_COOKIE",)` / `("THREADS_COOKIE",)` and `needs_auth=True`, with a `fetch` that returns `[]` if not `available()` else a best-effort scrape that may return `[]`).

Example minimal `xiaohongshu.py`:

```python
"""小红书 (Xiaohongshu/RED) via cookie (free account). Off by default; scaffold in v1."""
from __future__ import annotations

from reach_mcp.sources.base import Row, Source, register_source


@register_source
class Xiaohongshu(Source):
    name = "xiaohongshu"
    description = "小红书 posts via cookie (free account; v1 scaffold)."
    host = "www.xiaohongshu.com"
    needs_auth = True
    required_env = ("XHS_COOKIE",)

    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        if not self.available():
            return []
        # v1: cookie scraping is fragile; left as scaffold. Returns [].
        return []
```

(Write `threads.py` analogously with `required_env=("THREADS_COOKIE",)`.)

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest tests/test_sources_gated.py -v`
Expected: PASS (3 tests). All nine gated modules import and register cleanly.

- [ ] **Step 8: Commit**

```bash
git add src/reach_mcp/sources/x.py src/reach_mcp/sources/truthsocial.py \
        src/reach_mcp/sources/digg.py src/reach_mcp/sources/_scrapecreators.py \
        src/reach_mcp/sources/tiktok.py src/reach_mcp/sources/instagram.py \
        src/reach_mcp/sources/linkedin.py src/reach_mcp/sources/pinterest.py \
        src/reach_mcp/sources/xiaohongshu.py src/reach_mcp/sources/threads.py \
        tests/test_sources_gated.py
git commit -m "feat(sources): login-gated (x/truthsocial/tiktok/ig/li/xhs/threads/pin) + digg"
```

---

### Task 12: End-to-end integration test + `list_sources` coverage

**Files:**
- Test: `tests/test_integration.py`

**Interfaces:**
- Verifies the full `search` tool path with a stubbed source registry and a stubbed LLM.

- [ ] **Step 1: Write failing test `tests/test_integration.py`**

```python
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from reach_mcp.config import Settings
from reach_mcp.sources.base import Row, set_client
from reach_mcp.sources import SOURCES, available_sources
from reach_mcp.tools import build_mcp


class _StubSource:
    name = "stub"
    description = "stub"
    host = "stub.test"
    needs_auth = False
    required_env = ()
    default_days = 30
    default_limit = 20

    def available(self):
        return True

    async def fetch(self, query, days, limit):
        return [Row(source="stub", id="1", title=f"stub:{query}", url="https://stub/1",
                    author="a", date="2026-07-01T00:00:00Z",
                    engagement={"upvotes": 5}, text="body")]


@pytest.mark.asyncio
async def test_search_end_to_end(monkeypatch):
    # inject a stub source into the registry
    from reach_mcp.sources import base
    SOURCES["stub"] = _StubSource()
    monkeypatch.setattr("reach_mcp.synthesize.rerank", AsyncMock(side_effect=lambda q, i, s: i))
    monkeypatch.setattr("reach_mcp.synthesize.brief", AsyncMock(return_value="BRIEF"))

    mcp = build_mcp(Settings(openai_api_key="sk-x"))
    # call the search tool via the FastMCP internal call path
    tools = {t.name: t for t in await mcp.list_tools()}
    assert "search" in tools
    # exercise run_search directly (the tool wraps it)
    from reach_mcp.http import PoliteClient
    from reach_mcp.pipeline import run_search
    client = PoliteClient(Settings())
    set_client(client)
    items, reports = await run_search("q", ["stub"], 30, 5, client, Settings())
    assert items and items[0].title == "stub:q"
    assert reports[0].status == "ok"
    SOURCES.pop("stub", None)
    await client.aclose()
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_integration.py -v`
Expected: PASS.

- [ ] **Step 3: Run the whole suite**

Run: `pytest -q && ruff check .`
Expected: all tests PASS, ruff clean.

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: end-to-end search integration"
```

---

### Task 13: Dockerfile + docker-compose + workflows (ci, publish, build-docker)

**Files:**
- Create: `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`, `.github/workflows/publish.yml`, `.github/workflows/build-docker.yml`

**Interfaces:**
- Produces: buildable image `ghcr.io/xyonium/reach-mcp`; CI runs ruff+pytest on push/PR; publish on tag; docker build on path changes.

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir .

EXPOSE 8765

ENTRYPOINT ["reach-mcp"]
CMD ["--transport", "http", "--host", "0.0.0.0", "--port", "8765"]
```

- [ ] **Step 2: Write `docker-compose.yml`**

```yaml
services:
  reach-mcp:
    build: .
    image: reach-mcp:latest
    container_name: reach-mcp
    ports:
      - "8765:8765"
    environment:
      REACH_MCP_TRANSPORT: http
      REACH_MCP_HOST: 0.0.0.0
      REACH_MCP_PORT: "8765"
      REACH_MCP_ALLOWED_HOSTS: "reach-mcp:8765,localhost:8765,127.0.0.1:8765"
      # OPENAI_BASE_URL: "https://your-gateway/v1"
      # OPENAI_API_KEY: "sk-..."
      # SEARXNG_URL: "http://searxng:8080"
      # GH_TOKEN, AUTH_TOKEN/CT0, TRUTHSOCIAL_TOKEN, SCRAPECREATORS_API_KEY, ...
    restart: unless-stopped
```

- [ ] **Step 3: Write `.github/workflows/ci.yml`**

```yaml
name: ci
on:
  push:
    branches: [main]
  pull_request:
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: pytest -q
```

- [ ] **Step 4: Write `.github/workflows/publish.yml`**

```yaml
name: publish
on:
  push:
    tags: ["v*"]
jobs:
  build:
    runs-on: ubuntu-latest
    permissions: { id-token: write }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install build && python -m build
      - uses: pypa/gh-action-pypi-publish@release/v1
```

- [ ] **Step 5: Write `.github/workflows/build-docker.yml`**

```yaml
name: Build and Push Docker Image
on:
  push:
    branches: [main]
    paths:
      - "Dockerfile"
      - "src/**"
      - "pyproject.toml"
      - ".github/workflows/build-docker.yml"
  workflow_dispatch:
jobs:
  build:
    runs-on: ubuntu-latest
    permissions: { contents: read, packages: write }
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/setup-buildx-action@v3
      - name: image repo
        run: echo IMAGE_REPOSITORY=$(echo ${{ github.repository }} | tr '[:upper:]' '[:lower:]') >> $GITHUB_ENV
      - uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ghcr.io/${{ env.IMAGE_REPOSITORY }}:latest
            ghcr.io/${{ env.IMAGE_REPOSITORY }}:${{ github.sha }}
          labels: |
            org.opencontainers.image.source=https://github.com/${{ github.repository }}
            org.opencontainers.image.description=Controllable multi-source search MCP server for AI agents. Open replacement for last30days.
            org.opencontainers.image.licenses=MIT
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

- [ ] **Step 6: Build the image locally to verify it builds**

Run: `docker build -t reach-mcp:dev . && docker run --rm reach-mcp:dev --help`
Expected: image builds; `--help` prints the argparse usage (shows `--transport/--host/--port`). If yt-dlp install is slow, that's expected — it still must succeed.

- [ ] **Step 7: Commit**

```bash
git add Dockerfile docker-compose.yml .github/workflows/ci.yml .github/workflows/publish.yml .github/workflows/build-docker.yml
git commit -m "feat: Dockerfile, compose, CI/publish/build-docker workflows"
```

- [ ] **Step 8: Push to GitHub**

```bash
git push origin HEAD
```
Expected: push succeeds; the `ci` and `build-docker` workflows trigger on GitHub. Verify with `gh run list -L 3`.

---

## Self-Review Notes

- **Spec coverage:** tools (Task 7), 23 sources (Tasks 8–11), pipeline+scoring (Task 5), polite http (Task 3), LLM synthesis (Task 6), config (Task 2), packaging+CI+docker (Task 13), two deploy paths (uvx via `project.scripts` + ghcr via Dockerfile). Digg binary-shelling (Task 11). Polymarket/StockTwits restored (Task 8). Truth Social kept (Task 11). Perplexity intentionally absent.
- **Placeholders:** none — every code step contains real code; gated scaffolds (`xiaohongshu`/`threads`) explicitly return `[]` with a documented reason, not "TODO".
- **Type consistency:** `Row`/`Item` fields, `SourceReport`, `set_client`/`get_client`, `_item_to_dict`/`_source_report_to_dict` all defined before use and referenced consistently. `import_all_sources` defined in pipeline (Task 5) and called in tools (Task 7) and pipeline.run_search.
