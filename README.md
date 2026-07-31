# reach-mcp

> A controllable multi-source search MCP server for AI agents. Search Reddit, X, YouTube, Hacker News, GitHub, arXiv, Polymarket, 雪球, V2EX, B站, 小宇宙 and more -- **you pick the sources, the window, and whether to synthesize.** Built to replace the closed `last30days` server with an open, agent-driven one.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-green.svg?logo=python&logoColor=white)](https://www.python.org/)
[![CI](https://github.com/xyonium/reach-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/xyonium/reach-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/reach-mcp.svg)](https://pypi.org/project/reach-mcp/)
[![Docker](https://img.shields.io/badge/ghcr.io-reach-mcp-blue?logo=docker)](https://github.com/xyonium/reach-mcp/pkgs/container/reach-mcp)

---

## Why

`last30days` is a black box: the agent passes a query and gets back a finished brief. It can't choose which sources to hit, can't widen or narrow the time window (hardcoded to 30 days), can't see the raw scored rows, and can't reuse them. Every call re-searches everything.

**reach-mcp** keeps everything good about last30days -- parallel multi-source fetch, engagement-based scoring, cross-source dedup/clustering, an optional LLM-synthesized cited brief -- and hands the steering wheel to the agent:

- 🔌 **Pick your sources.** `sources=["reddit","arxiv","xueqiu"]` or omit for all configured ones.
- 📅 **Pick your window.** `days=7` for this week, `days=180` for the half-year -- no longer fixed at 30.
- 🪓 **Decide what matters.** `synthesize=false` returns raw scored rows for the agent to reason over itself; `synthesize=true` (default) also runs an LLM rerank + brief.
- 🇨🇳 **Chinese sources last30days lacks** -- 雪球, V2EX, B站, 小宇宙, 小红书 -- alongside nearly every source last30days ships.
- 🛡️ **Polite by default** -- per-host pacing, honors `Retry-After`, bounded timeouts. Never hammers a site.

## Sources (25)

| Tier | Source | Backend | Credential |
|------|------|------|------|
| **Free core** | `reddit` | RSS + scrape | none |
| | `hackernews` | Algolia API | none |
| | `bluesky` | AT Protocol (public) | `BSKY_HANDLE`/`BSKY_APP_PASSWORD` (optional) |
| | `github` | GitHub API | `GH_TOKEN` (optional, for higher rate limits) |
| | `arxiv` | arXiv API | none |
| | `techmeme` | scrape | none |
| | `polymarket` | public API | none |
| | `stocktwits` | public API | none |
| | `web` | Searxng + Brave (optional) | `SEARXNG_URL`; `BRAVE_API_KEY` optional ($5/mo) |
| | `dripstack` | DripStack API (free, keyless) | none |
| | `rss` | feedparser | `RSS_FEEDS` (comma-separated feed URLs) |
| **Video** | `youtube` | yt-dlp transcripts | `YTDLP_PROXY` (optional) |
| **Chinese** | `xueqiu` | scrape | none |
| | `v2ex` | API | none |
| | `bilibili` | bili-cli (preferred) / public API fallback | none (install `bili` for stability) |
| | `xiaoyuzhou` | public API | `GROQ_API_KEY` (optional, for transcription post-v1) |
| | `xiaohongshu` | xiaohongshu-mcp companion | `XHS_MCP_URL` |
| **Login-gated** *(off by default)* | `x` | cookies | `AUTH_TOKEN`/`CT0` |
| | `truthsocial` | Mastodon API | `TRUTHSOCIAL_TOKEN` |
| | `linkedin` | Jina (free, monthly quota) + ScrapeCreators (optional) | `JINA_API_KEY`; `SCRAPECREATORS_API_KEY` optional |
| | `tiktok` | Apify / OpenCLI / ScrapeCreators | `APIFY_API_TOKEN` ($5/mo); `SCRAPECREATORS_API_KEY`; or `opencli` on PATH |
| | `instagram` | Apify / OpenCLI / ScrapeCreators | `APIFY_API_TOKEN` ($5/mo); `SCRAPECREATORS_API_KEY`; or `opencli` on PATH |
| | `pinterest` | Apify / OpenCLI / ScrapeCreators | `APIFY_API_TOKEN` ($5/mo); `SCRAPECREATORS_API_KEY`; or `opencli` on PATH |
| **Binary** *(optional)* | `digg` | `digg-pp-cli` | none (needs the CLI on PATH) |
| **Apify** | `threads` | Apify threads-scraper | `APIFY_API_TOKEN` ($5/mo recurring) |

> 💰 **Apify gives $5 free credits EVERY MONTH** (recurring, not one-time) on the Free plan -- enough for hundreds of search runs. Set `APIFY_API_TOKEN` to enable threads + boost tiktok/instagram/pinterest (Apify is the preferred backend; OpenCLI is a free desktop alternative; ScrapeCreators is a one-time-credit fallback).

> ⚠️ **ScrapeCreators is 100 credits one-time, not free recurring.** It's now the lowest-priority fallback for tiktok/instagram/pinterest -- prefer Apify (monthly free) or OpenCLI (desktop, free). **LinkedIn uses Jina** (free `JINA_API_KEY` = monthly rate-limit quota).

## MCP tools

### `search` -- the primary tool

**Description:**
> Search up to 25 social & web sources in parallel, score by engagement, optionally synthesize a cited brief. YOU control scope.
>
> Sources (pass any subset as `sources`; omit/None = all currently-configured): free -- reddit, hackernews, bluesky, github, arxiv, techmeme, polymarket, stocktwits, web, dripstack, rss; video -- youtube; chinese -- xueqiu, v2ex, bilibili, xiaoyuzhou, xiaohongshu; login-gated (off until creds set) -- x, truthsocial, linkedin, tiktok, instagram, pinterest; binary -- digg; apify -- threads.
>
> Args: `query` (str, the topic/person/ticker); `sources` (list[str] | None, None=all available); `days` (int, recency window, default 30); `max_per_source` (int, row cap per source, default 20); `synthesize` (bool, default true = also LLM-rerank + write brief).
>
> Returns: `{brief: str|null, items: [Item], sources_used: [SourceReport], available_sources: [str]}`. Each Item: `{source, title, url, author, date, score, engagement, text}`. A SourceReport tells you per-source ok/gated_off/errored so a thin result is diagnosable. Call `list_sources` first if unsure what's configured.

### `list_sources`

> List all registered sources with availability status, required credentials, and defaults. Call this FIRST to see which sources are active (credentials set) vs gated (off-by-default) before deciding `sources`. Returns `[{name, description, needs_auth, available, required_env, default_days, default_limit}]`. No arguments.

### `synthesize`

> Re-synthesize a cited brief from already-fetched items WITHOUT re-searching. Pass the original `query` and the `items` list from a prior `search(synthesize=false)`. Returns `{brief}`. Use to re-brief cheaply with different emphasis. No source calls are made.

### `read_url`

> Read the content of any URL as clean text (via Jina Reader, free). Use this to fetch and analyze a page you found in search results -- a Reddit thread, news article, blog post, or GitHub readme -- when you need the full text beyond the snippet. Args: `url` (str). Returns `{url, content, ok}`. Keyless at 20 RPM; set `JINA_API_KEY` for 500 RPM.

## For agents -- quick usage guide

```
1. list_sources()                         # see what's configured; pick targets
2. search("Peter Steinberger",
          sources=["reddit","x","github","youtube"],
          days=14, synthesize=false)      # get raw scored rows, reason yourself
   -- or --
   search("OpenAI vs Anthropic",
          days=30, synthesize=true)        # one call → cited brief + rows
3. (optional) synthesize(query, items)     # re-brief the rows you already have
```

- **Default** (`sources=None`, `synthesize=true`): searches every configured source and returns a brief + all rows. Simplest.
- **Targeted** (`sources=[...]`): only hit what you need -- faster, cheaper, less noise.
- **Raw** (`synthesize=false`): you read the rows and draw conclusions; re-brief later with `synthesize`.
- A gated source you name returns `gated_off` in `sources_used` -- set its credential env and retry, or drop it.
- One broken source never breaks a search; check `sources_used` for what failed.

## Install

### Option A -- `uvx` in your MCP host (recommended for OpenWebUI / mcpo)

```jsonc
// mcpo config.json
"reach": {
  "command": "uvx",
  "args": ["reach-mcp", "--transport", "stdio"]
}
```
Or streamable-HTTP: `uvx reach-mcp --transport http --host 0.0.0.0 --port 8765`.

### Option B -- Docker

```bash
docker pull ghcr.io/xyonium/reach-mcp:latest
docker run -p 8765:8765 --env-file .env ghcr.io/xyonium/reach-mcp:latest
```

See [docker-compose.yml](docker-compose.yml) for a full example with all available env vars (including optional xiaohongshu-mcp companion service).

## Configuration

All config is environment variables (a `Settings` dataclass). Everything is optional -- the server degrades to free-source-only mode if you set nothing.

### Quick reference

```bash
# ===== LLM (rerank + brief) =====
OPENAI_BASE_URL="https://your-gateway/v1"    # OpenAI-compatible gateway base URL
OPENAI_API_KEY="sk-..."                      # API key for rerank + brief
REACH_MCP_RERANK_MODEL="gemini-flash-lite"   # model for reranking (default: gemini-flash-lite)
REACH_MCP_BRIEF_MODEL="gemini-flash-lite"    # model for brief synthesis (default: gemini-flash-lite)

# ===== Web search (required for web source) =====
SEARXNG_URL="http://searxng:8080"            # your Searxng instance

# ===== Free sources (optional auth boosts) =====
GH_TOKEN="ghp_..."                           # GitHub personal access token (higher rate limits)
BSKY_HANDLE="you.bsky.social"                # Bluesky handle (optional)
BSKY_APP_PASSWORD="xxxx-xxxx-xxxx-xxxx"      # Bluesky app password (optional)
YTDLP_PROXY="http://proxy:8080"              # proxy for yt-dlp (optional)
JINA_API_KEY="jina_..."                      # Jina key (LinkedIn search + read_url; free monthly quota)
BRAVE_API_KEY="BSA_..."                      # Brave Search key (web boost; $5 free credits/mo recurring)
RSS_FEEDS="https://blog.example.com/feed"    # comma-separated RSS/Atom feed URLs (rss source)

# ===== Login-gated sources =====
AUTH_TOKEN="..."                             # X/Twitter auth_token cookie
CT0="..."                                    # X/Twitter ct0 (csrf) cookie
TRUTHSOCIAL_TOKEN="..."                      # Truth Social API bearer token
APIFY_API_TOKEN="apify_api_..."              # Apify token (threads + tiktok/ig/pin boost; $5 free credits/mo)
SCRAPECREATORS_API_KEY="sc_..."              # ScrapeCreators key (tiktok + instagram + pinterest fallback; 100 one-time credits)

# ===== Chinese sources =====
XHS_MCP_URL="http://xiaohongshu-mcp:18060/mcp"  # xiaohongshu-mcp companion service URL
GROQ_API_KEY="gsk_..."                       # Groq API key (xiaoyuzhou transcription, post-v1)


# ===== Server settings =====
REACH_MCP_TRANSPORT="http"                   # http or stdio (default: http)
REACH_MCP_HOST="0.0.0.0"                     # bind host (default: 0.0.0.0)
REACH_MCP_PORT="8765"                         # bind port (default: 8765)
REACH_MCP_API_KEY="..."                      # optional lock on the HTTP surface
REACH_MCP_ALLOWED_HOSTS="reach-mcp:8765,localhost:8765"  # DNS-rebinding allow-list

# ===== HTTP tuning =====
REACH_MCP_SOURCE_TIMEOUT="60"                # per-source timeout in seconds (default: 60)
REACH_MCP_REQUEST_TIMEOUT="15"               # per-request timeout in seconds (default: 15)
REACH_MCP_MIN_HOST_DELAY="0.5"               # minimum delay between requests to same host (default: 0.5)
REACH_MCP_MAX_RETRIES="3"                    # max retries on transient errors (default: 3)
```

### Credential guide

#### X / Twitter (`AUTH_TOKEN`, `CT0`)

1. Log into x.com in any browser
2. Open DevTools (F12) → Application → Cookies → `x.com`
3. Copy the values of `auth_token` and `ct0`
4. Set `AUTH_TOKEN=<auth_token value>` and `CT0=<ct0 value>`

> ⚠️ Use a dedicated account; API-like usage may trigger platform anti-bot detection.

#### Bluesky (`BSKY_HANDLE`, `BSKY_APP_PASSWORD`)

1. Log into bsky.app → Settings → App Passwords
2. Create a new app password; copy the generated value
3. Set `BSKY_HANDLE=yourhandle.bsky.social` and `BSKY_APP_PASSWORD=<generated password>`

#### GitHub (`GH_TOKEN`)

1. GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
2. Create a token with `Public Repositories (read-only)` access
3. Set `GH_TOKEN=github_pat_...`

Without `GH_TOKEN`, GitHub search still works but hits unauthenticated rate limits (60 req/hr vs 5000 req/hr).

#### Truth Social (`TRUTHSOCIAL_TOKEN`)

1. Log into truthsocial.com in a browser
2. Open DevTools → Network tab → find any API request to `truthsocial.com`
3. Copy the `Authorization: Bearer ...` header value
4. Set `TRUTHSOCIAL_TOKEN=<the bearer token>`

#### ScrapeCreators (`SCRAPECREATORS_API_KEY`)

**⚠️ 100 credits one-time, then paid from $10/mo.** Signup gives 100 free credits (no credit card, no monthly reset). A single comprehensive search can consume 50--150+ credits. Only enable SC-backed sources (tiktok, instagram, pinterest) if you're OK with the cost.

1. Sign up at [scrapecreators.com](https://scrapecreators.com) (free, no credit card)
2. Copy your API key from the dashboard
3. Set `SCRAPECREATORS_API_KEY=sc_...`

One key enables three SC-only sources (and an optional LinkedIn boost):
- `tiktok` -- TikTok search (no free alternative exists)
- `instagram` -- Instagram search (Meta API requires app review)
- `pinterest` -- Pinterest search (no free alternative exists)
- `linkedin` -- Optional boost (Jina is the free primary)

#### LinkedIn

LinkedIn uses **Jina** as its free primary backend (agent-reach's approach). Jina's `s.jina.ai` search endpoint scopes to `linkedin.com/posts` and `linkedin.com/pulse`.

1. Get a free Jina API key at [jina.ai](https://jina.ai/) (Reader API)
2. Set `JINA_API_KEY=jina_...`

Jina's free key is a **recurring monthly rate-limit quota** (20 RPM without a key, 500 RPM with a free key, 5000 RPM paid) -- it is NOT a one-time credit. `s.jina.ai` search requires a key; `r.jina.ai` (page reader) works without one.

Optionally, setting `SCRAPECREATORS_API_KEY` adds ScrapeCreators results in parallel for a richer result set.

#### DripStack (financial newsletters)

Free and keyless -- always available, no setup. Search over premium financial newsletters (Substack/analyst write-ups). Best for ticker/company research. Complements `stocktwits` (retail sentiment) and `polymarket` (real-money odds).

#### RSS feeds (`RSS_FEEDS`)

Generic RSS/Atom source, free (uses `feedparser`, already a dependency). Set `RSS_FEEDS` to a comma-separated list of feed URLs; entries are filtered to the query within the recency window.

```bash
RSS_FEEDS="https://blog.example.com/feed,https://hnrss.org/frontpage"
```

#### Xiaohongshu / 小红书 (`XHS_MCP_URL`)

Uses the community-vetted [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) Go server (15K+ stars) as backend.

**Docker (recommended):** Add to your compose file (see `docker-compose.yml`):
```yaml
xiaohongshu-mcp:
  image: ghcr.io/xpzouying/xiaohongshu-mcp:latest
  ports: ["18060:18060"]
  restart: unless-stopped
```
Then run the login helper once and set `XHS_MCP_URL=http://xiaohongshu-mcp:18060/mcp`.

**Without Docker:** Download the binary from [releases](https://github.com/xpzouying/xiaohongshu-mcp/releases), run the login helper, then start the server. Set `XHS_MCP_URL=http://localhost:18060/mcp`.

#### Web search (`SEARXNG_URL`)

Required for the `web` source. Point to your self-hosted Searxng instance (default `http://searxng:8080`). If you don't have one, [Searxng](https://github.com/searxng/searxng) runs easily in Docker.

#### YouTube (`YTDLP_PROXY`)

Optional. Set to an HTTP proxy URL (e.g. `http://proxy:8080`) if yt-dlp needs a proxy to reach YouTube.

#### Digg (`digg-pp-cli`)

Digg is auto-enabled when the `digg-pp-cli` binary is on `PATH`. Built from the last30days project's build steps. Without the CLI, `digg` stays gated off.

#### Apify (`APIFY_API_TOKEN`) -- threads, tiktok, instagram, pinterest

Apify's Free plan gives **$5 in credits every month** (recurring, not one-time) -- enough for hundreds of search runs. One token enables:

- `threads` -- via the `apify/threads-scraper` Actor (the only viable free server-side path; Meta's own API needs app review)
- `tiktok` / `instagram` / `pinterest` -- Apify is the preferred backend

1. Sign up at [apify.com](https://apify.com) (Free plan, no card)
2. Copy your API token from Settings --> Integrations
3. Set `APIFY_API_TOKEN=apify_api_...`

#### OpenCLI (optional desktop free) -- tiktok, instagram, pinterest

[OpenCLI](https://github.com/jackwener/opencli) (Apache--2.0, free) reuses your logged-in Chrome session via a browser bridge. If the `opencli` binary is on `PATH`, tiktok/instagram/pinterest use it automatically as a free desktop backend (no API key needed). Desktop-only -- not for headless/Docker deployments.

#### bilibili (`bili` CLI)

Prefers the community-vetted [bili-cli](https://github.com/public-clis/bilibili-cli) (`uv tool install bilibili-cli`) when on PATH -- it handles B站's wbi signing and anti-scraping (HTTP 412) that raw API calls hit. Falls back to the public search API if `bili` is absent. No login needed for search.

#### Xiaoyuzhou / 小宇宙

Free podcast search -- always available, no key needed. Returns episode titles, descriptions, and metadata. Whisper transcription via Groq (`GROQ_API_KEY`) is deferred to post-v1.

#### `read_url` tool (Jina Reader)

The `read_url(url)` tool fetches any URL's content as clean text via [r.jina.ai](https://jina.ai/reader/) (Jina Reader). Use it to read a page you found in search results -- a Reddit thread, news article, blog post, or GitHub readme -- when you need the full text beyond the snippet. Keyless at 20 RPM; set `JINA_API_KEY` for 500 RPM (free monthly quota). Returns `{url, content, ok}`.

---

## Migration from last30days

If you're coming from the `last30days` MCP server (mvanhorn/last30days-skill), here's what changes:

### Env var mapping

| last30days | reach-mcp | Notes |
|------|------|------|
| `LAST30DAYS_REASONING_PROVIDER` | *(removed)* | No equivalent; reach-mcp always uses OpenAI-compatible chat |
| `LAST30DAYS_PLANNER_MODEL` | `REACH_MCP_BRIEF_MODEL` | Model for brief synthesis, default `gemini-flash-lite` |
| `LAST30DAYS_RERANK_MODEL` | `REACH_MCP_RERANK_MODEL` | Model for reranking, default `gemini-flash-lite` |
| `APIFY_API_TOKEN` | *(removed)* | reach-mcp doesn't use Apify |
| `BRAVE_API_KEY` | `SEARXNG_URL` | reach-mcp uses Searxng instead of Brave (free tier removed 2026) |
| `INCLUDE_SOURCES` | *(removed)* | Use `sources=[...]` per search call; no global include list |
| `LAST30DAYS_SEARXNG_URL` | `SEARXNG_URL` | Same purpose, shorter name |
| `OPENAI_BASE_URL` | `OPENAI_BASE_URL` | Same, but reach-mcp appends `/chat/completions` (don't include `/v1/responses`) |
| `OPENAI_API_KEY` | `OPENAI_API_KEY` | Same |
| `GH_TOKEN` | `GH_TOKEN` | Same |
| `AUTH_TOKEN`, `CT0` | `AUTH_TOKEN`, `CT0` | Same |
| `BSKY_HANDLE`, `BSKY_APP_PASSWORD` | `BSKY_HANDLE`, `BSKY_APP_PASSWORD` | Same |
| `XAI_API_KEY` / `XQUIK_API_KEY` | *(removed)* | reach-mcp only supports cookie-based X auth in v1 |

### Sources: gained and lost

| Gained (vs last30days) | Lost (vs last30days) |
|------|------|
| xueqiu (雪球), v2ex, bilibili (B站), xiaoyuzhou (小宇宙), xiaohongshu (小红书) | Perplexity (no recurring free quota) |
| linkedin via free Jina, dripstack, rss feeds | Brave Search (free tier removed 2026), Apify |
| Honest SC documentation (100 credits, not 10,000) | Apify (not integrated) |

### Behavioral differences

- **`days` is per-call**, not hardcoded to 30
- **`sources` is per-call**, not global `INCLUDE_SOURCES`
- **`synthesize=false`** returns raw scored rows (last30days always synthesizes)
- **`list_sources`** shows exactly what's configured and what each source needs
- **No `INCLUDE_SOURCES` global filter** -- just pass `sources=[...]` per search
- **No `--hiring-signals`, `--discover`, `--watchlist`** -- these were last30days CLI features; reach-mcp is server-only

## License

[MIT](LICENSE) © xyonium
