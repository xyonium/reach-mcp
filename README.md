# reach-mcp

> A controllable multi-source search MCP server for AI agents. Search Reddit, X, YouTube, Hacker News, GitHub, arXiv, Polymarket, 雪球, V2EX, B站, 小宇宙 and more — **you pick the sources, the window, and whether to synthesize.** Built to replace the closed `last30days` server with an open, agent-driven one.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-green.svg?logo=python&logoColor=white)](https://www.python.org/)
[![CI](https://github.com/xyonium/reach-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/xyonium/reach-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/reach-mcp.svg)](https://pypi.org/project/reach-mcp/)
[![Docker](https://img.shields.io/badge/ghcr.io-reach--mcp-blue?logo=docker)](https://github.com/xyonium/reach-mcp/pkgs/container/reach-mcp)

---

## Why

`last30days` is a black box: the agent passes a query and gets back a finished brief. It can't choose which sources to hit, can't widen or narrow the time window (hardcoded to 30 days), can't see the raw scored rows, and can't reuse them. Every call re-searches everything.

**reach-mcp** keeps everything good about last30days — parallel multi-source fetch, engagement-based scoring, cross-source dedup/clustering, an optional LLM-synthesized cited brief — and hands the steering wheel to the agent:

- 🔌 **Pick your sources.** `sources=["reddit","arxiv","xueqiu"]` or omit for all configured ones.
- 📅 **Pick your window.** `days=7` for this week, `days=180` for the half-year — no longer fixed at 30.
- 🪓 **Decide what matters.** `synthesize=false` returns raw scored rows for the agent to reason over itself; `synthesize=true` (default) also runs an LLM rerank + brief.
- 🇨🇳 **Chinese sources last30days lacks** — 雪球, V2EX, B站, 小宇宙 — alongside nearly every source last30days ships.
- 🛡️ **Polite by default** — per-host pacing, honors `Retry-After`, bounded timeouts. Never hammers a site.

## Sources (23)

| Tier | Source | Backend | Credential (all free-tier / no payment) |
|---|---|---|---|
| **Free core** | `reddit` | RSS + scrape | none |
| | `hackernews` | Algolia API | none |
| | `bluesky` | AT Protocol | `BSKY_HANDLE`/`BSKY_APP_PASSWORD` (optional) |
| | `github` | GitHub API | `GH_TOKEN` (optional) |
| | `arxiv` | arXiv API | none |
| | `techmeme` | scrape | none |
| | `polymarket` | public API | none |
| | `stocktwits` | public API | none |
| | `web` | Searxng | `SEARXNG_URL` |
| **Video** | `youtube` | yt-dlp transcripts | `YTDLP_PROXY` (optional) |
| **Chinese** | `xueqiu` | scrape | none |
| | `v2ex` | API | none |
| | `bilibili` | bili-cli | none |
| | `xiaoyuzhou` | audio → Whisper | Groq key (free tier) |
| **Login-gated** *(off by default)* | `x` | cookies | `AUTH_TOKEN`/`CT0` |
| | `truthsocial` | Mastodon API | `TRUTHSOCIAL_TOKEN` |
| | `tiktok` | ScrapeCreators | SC key |
| | `instagram` | ScrapeCreators | SC key |
| | `linkedin` | ScrapeCreators/Jina | SC key |
| | `xiaohongshu` | cookie | RED cookie |
| | `threads` | cookie/key | free account |
| | `pinterest` | ScrapeCreators | SC key |
| **Binary** *(optional)* | `digg` | `digg-pp-cli` | none (needs the CLI on PATH) |

Login-gated sources are **off by default** and light up the moment you set their (free) credentials — an account you already have, no payment. Only `perplexity` from last30days was dropped (no recurring free quota).

## MCP tools

> The `description` text below is exactly what the agent sees — copy these verbatim into `src/reach_mcp/tools.py`.

### `search` — the primary tool

**Description:**
> Search up to 23 social & web sources in parallel, score by engagement, optionally synthesize a cited brief. YOU control scope.
>
> Sources (pass any subset as `sources`; omit/None = all currently-configured): free — reddit, hackernews, bluesky, github, arxiv, techmeme, polymarket, stocktwits, web; video — youtube; chinese — xueqiu, v2ex, bilibili, xiaoyuzhou; login-gated (off until creds set) — x, truthsocial, tiktok, instagram, linkedin, xiaohongshu, threads, pinterest; binary — digg.
>
> Args: `query` (str, the topic/person/ticker); `sources` (list[str] | None, None=all available); `days` (int, recency window, default 30); `max_per_source` (int, row cap per source, default 20); `synthesize` (bool, default true = also LLM-rerank + write brief).
>
> Returns: `{brief: str|null, items: [Item], sources_used: [SourceReport], available_sources: [str]}`. Each Item: `{source, title, url, author, date, score, engagement, text}`. A SourceReport tells you per-source ok/gated_off/errored so a thin result is diagnosable. Call `list_sources` first if unsure what's configured.

**Signature:**
```python
search(query: str, sources: list[str] | None = None, days: int = 30,
       max_per_source: int = 20, synthesize: bool = True) -> dict
```

### `list_sources`

> List all registered sources with availability status, required credentials, and defaults. Call this FIRST to see which sources are active (credentials set) vs gated (off-by-default) before deciding `sources`. Returns `[{name, description, needs_auth, available, required_env, default_days, default_limit}]`. No arguments.

### `synthesize`

> Re-synthesize a cited brief from already-fetched items WITHOUT re-searching. Pass the original `query` and the `items` list from a prior `search(synthesize=false)`. Returns `{brief}`. Use to re-brief cheaply with different emphasis. No source calls are made.

## For agents — quick usage guide

```
1. list_sources()                         # see what's configured; pick targets
2. search("Peter Steinberger",
          sources=["reddit","x","github","youtube"],
          days=14, synthesize=false)      # get raw scored rows, reason yourself
   — or —
   search("OpenAI vs Anthropic",
          days=30, synthesize=true)        # one call → cited brief + rows
3. (optional) synthesize(query, items)     # re-brief the rows you already have
```

- **Default** (`sources=None`, `synthesize=true`): searches every configured source and returns a brief + all rows. Simplest.
- **Targeted** (`sources=[...]`): only hit what you need — faster, cheaper, less noise.
- **Raw** (`synthesize=false`): you read the rows and draw conclusions; re-brief later with `synthesize`.
- A gated source you name returns `gated_off` in `sources_used` — set its credential env and retry, or drop it.
- One broken source never breaks a search; check `sources_used` for what failed.

## Install

### Option A — `uvx` in your MCP host (recommended for OpenWebUI / mcpo)

```jsonc
// mcpo config.json
"reach": {
  "command": "uvx",
  "args": ["reach-mcp", "--transport", "stdio"]
}
```
Or streamable-HTTP: `uvx reach-mcp --transport http --host 0.0.0.0 --port 8765`.

### Option B — Docker

```bash
docker pull ghcr.io/xyonium/reach-mcp:latest
docker run -p 8765:8765 --env-file .env ghcr.io/xyonium/reach-mcp:latest
```
```yaml
# docker-compose.yml
services:
  reach-mcp:
    image: ghcr.io/xyonium/reach-mcp:latest
    ports: ["8765:8765"]
    environment:
      REACH_MCP_ALLOWED_HOSTS: "reach-mcp:8765,localhost:8765"
      # …credentials below…
    restart: unless-stopped
```

OpenWebUI connects to `http://reach-mcp:8765/mcp` (native MCP, streamable-HTTP).

## Configuration

All config is environment variables (a `Settings` dataclass). Everything is optional — the server degrades to free-source-only mode if you set nothing.

| Env | Purpose |
|---|---|
| `OPENAI_BASE_URL`, `OPENAI_API_KEY` | LLM for rerank + brief (your OpenAI-compatible gateway) |
| `REACH_MCP_RERANK_MODEL`, `REACH_MCP_BRIEF_MODEL` | model ids, default `gemini-flash-lite` |
| `SEARXNG_URL` | your Searxng instance for the `web` source |
| `GH_TOKEN` | optional, for higher GitHub rate limits |
| `BSKY_HANDLE`, `BSKY_APP_PASSWORD` | optional Bluesky auth |
| `AUTH_TOKEN`, `CT0` | Twitter/X cookies |
| `TRUTHSOCIAL_TOKEN` | Truth Social bearer (free account) |
| `YTDLP_PROXY` | proxy for yt-dlp |
| `REACH_MCP_ALLOWED_HOSTS` | DNS-rebinding allow-list (cross-container Host headers) |
| `REACH_MCP_API_KEY` | optional lock on the HTTP surface |

For `digg`: install `digg-pp-cli` on PATH (see last30days' build steps) — reach-mcp detects it and enables the source automatically; without it, `digg` stays gated.

## License

[MIT](LICENSE) © xyonium
