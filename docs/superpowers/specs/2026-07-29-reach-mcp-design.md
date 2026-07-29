# reach-mcp — Design

Date: 2026-07-29
Status: Approved (brainstorming complete; ready for implementation plan)

## 1. Goal

Replace the closed, pre-compiled `last30days` MCP server (`last30days-pp-mcp`, a
Go binary run inside the `mcpo` container) with an open, agent-controllable
Python MCP server, **reach-mcp**, that:

- Exposes a single primary `search` tool with the freedom knobs last30days hid
  (selectable sources, configurable time window, per-source cap, optional
  synthesis) — so an OpenWebUI agent can target specific sources instead of a
  fixed, all-sources pipeline.
- Inherits last30days' strengths: parallel multi-source fetch, engagement-based
  scoring, relevance floor, cross-source dedup/clustering, and optional
  server-side LLM synthesis into a cited brief.
- Adds Chinese sources last30days lacks (雪球, V2EX, B站, 小宇宙) and keeps
  nearly all of last30days' sources.
- Runs two ways: a PyPI package `uvx`-run inside the existing `mcpo` container
  (1:1 replacement of the last30days config entry), **and** a standalone
  Docker image on ghcr.
- Is published as a public GitHub repo (`xyonium/reach-mcp`, MIT license) with
  CI, PyPI publish, and Docker build workflows.

Non-goals: wrapping Firecrawl (already a separate OpenWebUI MCP server);
wrapping the finance/papers/docling MCPs (already separate servers); an
auto-setup "wizard" or `doctor` command (out of scope for v1); a GUI.

## 2. Tool surface

FastMCP server exposing three tools (streamable-HTTP default + stdio):

### `search` (primary)
```
search(
  query: str,
  sources: list[str] | None = None,   # None = all currently-available sources
  days: int = 30,                      # recency window (last30days is fixed 30)
  max_per_source: int = 20,            # cap rows fetched per source
  synthesize: bool = True,             # True = also run LLM rerank + brief
) -> {
  brief: str | None,                   # LLM synthesis; None when synthesize=False
  items: list[Item],                   # scored, deduped, clustered raw rows
  sources_used: list[SourceReport],    # per-source status + count + errors
  available_sources: list[str],        # what the agent could have used (for retry)
}
```

- `Item = {source, title, url, author, date, score, text|summary, engagement}`.
- `sources=None` → every source whose required env/credentials are satisfied.
- An explicit `sources=[...]` may name gated sources; a named-but-gated source
  returns a `SourceReport` with `status=gated_off` rather than aborting.
- `SourceReport = {source, status: ok|gated_off|errored, count, error?}` so a
  thin result is diagnosable, not silent.

### `list_sources` (the inspectable source list)
Zero-arg. Returns every registered source:
`{name, description, needs_auth, available, required_env, default_days,
default_limit}`. The agent calls this first to know what it can target. This is
the "源列表工具选项" the user asked for, made inspectable.

### `synthesize` (optional re-brief)
```
synthesize(query: str, items: list[Item]) -> {brief: str}
```
Re-synthesizes already-fetched rows without re-hitting sources — cheap retry /
re-brief. ~30 lines. Can be cut as YAGNI during implementation if it adds
clutter; left in the design as a thin convenience.

## 3. Source registry & v1 source set

Architecture: **Approach C — registry of `Source` subclasses carrying their own
metadata.** Each source is one self-contained module under
`src/reach_mcp/sources/`, subclassing `Source` with metadata + an async
`fetch()`. A `register_source` decorator populates a central `SOURCES` dict.

`Source` base declares: `name`, `description`, `host`, `needs_auth`,
`required_env: tuple[str,...]`, `default_days`, `default_limit`,
`min_delay_seconds`, `max_concurrency`, and `async fetch(query, days, limit)
-> list[Row]`.

The registry introspects `required_env` against the environment to classify
each source as **available** (env satisfied) or **gated** (missing auth).
Gated sources are excluded from `sources=None` and from default search; if the
agent names a gated source explicitly it gets a `gated_off` SourceReport.

`Row = {source, id, title, url, author, date, engagement:{...}, text}`.

### v1 source set (~23 sources)

**Free core (no-auth, always available):**
| source | backend | notes |
|---|---|---|
| `reddit` | RSS + shreddit `.json` scrape | keyless path |
| `hackernews` | Algolia HN API | |
| `bluesky` | AT Protocol public | `BSKY_HANDLE`+`BSKY_APP_PASSWORD` optional |
| `github` | GitHub API (gh CLI optional) | `GH_TOKEN` optional |
| `arxiv` | arXiv API | |
| `techmeme` | scrape (date-windowed) | |
| `polymarket` | public API | real-money odds |
| `stocktwits` | public API | auto for ticker/crypto |
| `web` | Searxng (`SEARXNG_URL`) | user's existing instance at `http://searxng:8080` |

**Video:** `youtube` (yt-dlp transcripts; `YTDLP_PROXY`/deno optional)

**Chinese additions (beyond last30days):** `xueqiu`, `v2ex`, `bilibili`
(bili-cli search+detail, no login), `xiaoyuzhou` (podcast audio → Whisper
transcript; free Groq backstop)

**Login-gated (off-by-default; all qualify as "free" = no money out of pocket):**
| source | credential | how obtained |
|---|---|---|
| `x` (Twitter) | `AUTH_TOKEN`+`CT0` cookies | free account cookies |
| `truthsocial` | `TRUTHSOCIAL_TOKEN` | free-account browser bearer token |
| `tiktok` | ScrapeCreators key | free-tier key |
| `instagram` | ScrapeCreators key | free-tier key |
| `linkedin` | ScrapeCreators / Jina | free-tier |
| `xiaohongshu` | cookie | free account |
| `threads` | cookie/key | free account |
| `pinterest` | ScrapeCreators key | free-tier |

**Binary-shelling (optional, free):** `digg` — shells out to `digg-pp-cli`;
detected on PATH → available, else gated-off. README documents the install step
(the user's existing `mcpo` `entrypoint.sh` already builds it). **No Go
toolchain inside the Python package.**

**Dropped:** `perplexity` only. Reason: no recurring free quota (strictly
pay-per-use; new accounts get a one-time $5 credit that depletes, not a monthly
free allowance). Fails the user's "free = no money out of pocket, monthly free
quota counts" bar.

**Net:** nearly all of last30days' ~19 sources (Truth Social and Digg kept;
only Perplexity dropped) **plus** four Chinese sources last30days lacks.

## 4. Pipeline & scoring (server-side, per `search` call)

```
1. resolve sources
     sources=None  → all available (env satisfied) sources
     sources=[...] → those named; unknown → error in SourceReport
                     named-but-gated → SourceReport status=gated_off
2. fan-out fetch   (asyncio.gather, per-source timeout + try/except)
     each source.fetch(query, days, limit=max_per_source) -> list[Row]
     one source failing/timeout → empty rows + errored SourceReport, never aborts
3. normalize + dedup
     normalize all Rows into Items
     dedup by canonicalized URL and near-dup title+body hash
4. engagement scoring
     per-source engagement weight table (reddit upvotes, hn points, x likes/RTs,
     polymarket volume, …) → normalized 0..1
     recency decay within `days` (newer ranks higher)
     cross-source comparability via per-source z-score normalization
5. cluster (cheap)
     group near-duplicate Items across sources; pick lead + merge refs
6. LLM rerank + brief   (only if synthesize=True)
     rerank: top-N Items → cliproxy LLM re-scores relevance to query
     brief:  LLM synthesizes grounded brief with inline citations [1][2]
     synthesize=False → skip; items still returned scored
7. return {brief?, items, sources_used, available_sources}
```

Defaults: `max_per_source=20`, `days=30`, rerank top-N = 30 Items.

**Safeguards inherited from last30days:**
- **Relevance floor:** a viral but off-topic Item can't hijack the brief —
  engagement alone isn't enough; the rerank gates it.
- **Per-source isolation:** a single broken source degrades gracefully
  (reported in `sources_used`), never crashes `search`.

Scoring steps 3–5 are pure functions over Rows → scored Items, so the LLM only
touches the final rerank+brief. Keeps unit tests fast and the expensive LLM
call bounded to top-N.

## 5. Rate-limiting & polite fetching (kept simple)

Centralized in one `http.py` module — a `PoliteClient` wrapping
`httpx.AsyncClient` that every source uses. Policy:

- **Per-host min-delay** (default ~0.5s floor) so the server never hammers a
  single host; sources declare a larger `min_delay_seconds` for scrape endpoints.
- **Respect `Retry-After`** on HTTP 429/503 — back off exactly as the site asks.
- **Bounded timeouts** per request (~15s) and per source overall (~60s); a slow
  source can't stall `search`.
- **Exponential backoff** on transient errors, capped (max 3 retries), then
  give up gracefully for that source (→ `errored` SourceReport).

Deliberately NOT built: robots.txt crawling, token-bucket machinery, jitter
gymnastics. The priority is getting the most valuable info, not elaborate
politeness infrastructure — just enough to not be abusive.

## 6. LLM synthesis

Server-side, via the user's existing cliproxy (consistent with last30days'
wiring): `OPENAI_BASE_URL` + `OPENAI_API_KEY` env vars (pointing at
`cliproxy.savorcare.com`). Models configurable via env — `REACH_MCP_RERANK_MODEL`
and `REACH_MCP_BRIEF_MODEL` — both defaulting to `gemini-flash-lite` (matching
last30days' `LAST30DAYS_RERANK_MODEL`/`PLANNER_MODEL` choice) so the default
needs no extra config. Synthesis only runs when `synthesize=True`.

## 7. Configuration

Env-driven `Settings` dataclass (mirroring `officecli-mcp`'s `config.py`):
- `REACH_MCP_TRANSPORT` (http|stdio), `REACH_MCP_HOST`, `REACH_MCP_PORT`
- `REACH_MCP_ALLOWED_HOSTS` (DNS-rebinding guard; OpenWebUI calls
  `http://reach-mcp:PORT/mcp` across the docker network → must allow-list the
  service name or it 421s)
- `REACH_MCP_API_KEY` (optional lock on the HTTP surface)
- Per-source credentials: `GH_TOKEN`, `BSKY_HANDLE`/`BSKY_APP_PASSWORD`,
  `AUTH_TOKEN`/`CT0`, `TRUTHSOCIAL_TOKEN`, ScrapeCreators keys, `SEARXNG_URL`,
  `YTDLP_PROXY`, `OPENAI_BASE_URL`/`OPENAI_API_KEY`, Whisper/Groq key, etc.
- `REACH_MCP_MCP_TIMEOUT` (overall search call budget)

## 8. Packaging

```
reach-mcp/
├── src/reach_mcp/
│   ├── __init__.py  __main__.py  config.py  server.py
│   ├── http.py            # PoliteClient
│   ├── pipeline.py        # resolve→fan-out→dedup→score→cluster
│   ├── synthesize.py      # cliproxy LLM rerank + brief
│   ├── sources/           # base.py + one module per source + digg.py
│   └── tools.py           # search / list_sources / synthesize tool defs
├── tests/                 # per-source fetch (mocked) + pipeline + scoring
├── pyproject.toml  Dockerfile  docker-compose.yml
├── .dockerignore  .gitignore  LICENSE (MIT)  README.md
└── .github/workflows/{ci,publish,build-docker}.yml
```

**Dependencies:** `mcp[cli]>=1.27,<2`, `httpx`, `pydantic`, `starlette`,
`uvicorn[standard]`, `feedparser`, `yt-dlp`. Dev: pytest, pytest-asyncio,
ruff, build.

**Transport:** streamable-HTTP (default) + stdio; same `--transport`/`--host`/
`--port` + `allowed_hosts` DNS-rebinding pattern as officecli-mcp.

## 9. Deployment

Two paths (both, per user choice):

1. **PyPI package** → the `mcpo` container runs `uvx reach-mcp`, replacing the
   `last30days` entry in `config.json` 1:1. Zero new container; reuses
   `UV_CACHE_DIR`/proxy env. Auth/credential envs move from last30days' block
   into reach-mcp's block.
2. **Standalone Docker image** → `ghcr.io/xyonium/reach-mcp:latest`, its own
   compose service joining OpenWebUI's network (like officecli-mcp).

## 10. CI / GitHub

- **GitHub repo:** `xyonium/reach-mcp`, **public**, MIT license, created via
  `gh`. Initial commit = full scaffold.
- **ci.yml:** ruff check + pytest on push to main + PRs.
- **publish.yml:** tag `v*` → `python -m build` → PyPI trusted publishing
  (user has configured trusted publishing on pypi.org).
- **build-docker.yml:** on push to main (paths: Dockerfile/src/**/pyproject/
  workflow) → build & push `ghcr.io/xyonium/reach-mcp:latest` + `:sha`, GHA
  build cache. `workflow_dispatch` for manual builds.

All three workflows adapted from `officecli-mcp`'s working versions.

## 11. Testing strategy

- **Per-source fetch tests** (mocked HTTP / CLI): each source module has a test
  that feeds a fixture response and asserts normalized Rows.
- **Pipeline tests:** dedup, engagement scoring, recency decay, clustering as
  pure-function unit tests over Row fixtures.
- **Auth-gating tests:** registry marks a source gated when its env is missing,
  available when present.
- **Rate-limit tests:** `PoliteClient` enforces per-host delay and honors
  `Retry-After` (mock time).
- **Tool tests:** `search`/`list_sources`/`synthesize` with a stubbed
  source registry + stubbed LLM.

## 12. Open / deferred

- Digg's `digg-pp-cli` is an external dependency documented in README, not
  vendored.
- No `doctor`/setup-wizard in v1.
- Source backends are chosen pragmatically per source (public API where one
  exists, scrape otherwise); backend failover (last30days' "preferred + backup"
  lists) is deferred — each source has one backend in v1.
