# reach-mcp

> A controllable multi-source search MCP server for AI agents. Search Reddit, X, YouTube, Hacker News, GitHub, arXiv, Polymarket, 微博, 知乎, 豆瓣, 头条, 雪球, V2EX, B站, 小宇宙 and more -- **you pick the sources, the window, and whether to synthesize.** 32 sources across Chinese & English platforms, with adjustable time window, source/category scoping, trending hot lists (微博/知乎/头条热搜...), and optional LLM synthesis.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-green.svg?logo=python&logoColor=white)](https://www.python.org/)
[![CI](https://github.com/xyonium/reach-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/xyonium/reach-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/reach-mcp.svg)](https://pypi.org/project/reach-mcp/)
[![Docker](https://img.shields.io/badge/ghcr.io-reach-mcp-blue?logo=docker)](https://github.com/xyonium/reach-mcp/pkgs/container/reach-mcp)

---

## Why

`last30days` (mvanhorn/last30days-skill) wraps the search in a fixed pipeline: the agent passes a query and gets back a finished brief. It can't choose which sources to hit, can't widen or narrow the time window (hardcoded to 30 days), can't see the raw scored rows, and can't reuse them. Every call re-searches everything.

**reach-mcp** keeps the same core machinery -- parallel multi-source fetch, engagement-based scoring, cross-source dedup/clustering, an optional LLM-synthesized cited brief -- and exposes it as a plain MCP server whose knobs the agent controls per call:

- 🔌 **Pick your sources.** `sources=["reddit","arxiv","xueqiu"]` or omit for all configured ones.
- 📅 **Pick your window.** `days=7` for this week, `days=180` for the half-year -- no longer fixed at 30.
- 🪓 **Decide what matters.** `synthesize=false` returns raw scored rows for the agent to reason over itself; `synthesize=true` (default) also runs an LLM rerank + brief. `max_chars_per_item` sets each row's text-snippet length (default 500) -- raise it for fuller CN posts, lower it to save tokens.
- 🌐 **Chinese & English sources in one call** -- 微博, 知乎, 豆瓣, 头条, 雪球, V2EX, B站, 小宇宙, 小红书 alongside Reddit, X, YouTube, HN, GitHub, arXiv and the rest.
- 🛡️ **Polite by default** -- per-host pacing, honors `Retry-After`, bounded timeouts. Never hammers a site.

## Sources (32)

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
| | `stackoverflow` | Stack Exchange official API (keyless, Q&A corpus) | none |
| | `lobsters` | Lobste.rs JSON feeds (keyless; search = feed filter) | none |
| | `rss` | feedparser | `RSS_FEEDS` (comma-separated feed URLs) |
| **Video** | `youtube` | yt-dlp metadata; captions via `fetch_content` | `YTDLP_PROXY` (optional) |
| **Chinese** | `xueqiu` | API (login cookie) | `XUEQIU_COOKIE` |
| | `v2ex` | API | none |
| | `bilibili` | bili-cli (preferred) / public API fallback | none (install `bili` for stability) |
| | `xiaoyuzhou` | public API | `XIAOYUZHOU_ACCESS_TOKEN` (login); `WHISPER_BASE_URL` (for `fetch_content` transcription) |
| | `xiaohongshu` | xiaohongshu-mcp companion | `XHS_MCP_URL` |
| | `weibo` | mobile API (m.weibo.cn) + auto visitor cookies | none |
| | `zhihu` | search via `ZHIHU_COOKIE`; hot-list via mobile API | `ZHIHU_COOKIE` (optional — unlocks real search) |
| | `douban` | mobile rexxar API (movies/TV/books/music + ratings) | none |
| | `toutiao` | hot-board JSON API + search SSR scrape | none |
| **Login-gated** *(off by default)* | `x` | cookies | `AUTH_TOKEN`/`CT0` |
| | `truthsocial` | Mastodon API | `TRUTHSOCIAL_TOKEN` |
| | `linkedin` | Apify (public posts) + Searxng fallback + ScrapeCreators (optional) | `APIFY_API_TOKEN` ($5/mo); `SEARXNG_URL` for fallback; `SCRAPECREATORS_API_KEY` optional |
| | `tiktok` | playwright in-page fetch (free, optional) / Apify / OpenCLI / ScrapeCreators | none (with playwright+chromium installed); else `APIFY_API_TOKEN` ($5/mo); `SCRAPECREATORS_API_KEY`; or `opencli` on PATH |
| | `instagram` | Apify / OpenCLI / ScrapeCreators | `APIFY_API_TOKEN` ($5/mo); `SCRAPECREATORS_API_KEY`; or `opencli` on PATH |
| | `pinterest` | Apify / OpenCLI / ScrapeCreators | `APIFY_API_TOKEN` ($5/mo); `SCRAPECREATORS_API_KEY`; or `opencli` on PATH |
| **Binary** *(optional)* | `digg` | `digg-pp-cli` | none (needs the CLI on PATH) |
| **Apify** | `threads` | Apify threads-scraper | `APIFY_API_TOKEN` ($5/mo recurring) |
| | `quora` | Apify quora-search-scraper | `APIFY_API_TOKEN` (same key) |

> 💰 **Apify gives $5 free credits EVERY MONTH** (recurring, not one-time) on the Free plan -- enough for hundreds of search runs. Set `APIFY_API_TOKEN` to enable threads + quora + boost tiktok/instagram/pinterest/linkedin (Apify is the preferred backend; OpenCLI is a free desktop alternative; ScrapeCreators is a one-time-credit fallback).

> ⚠️ **ScrapeCreators is 100 credits one-time, not free recurring.** It's now the lowest-priority fallback for tiktok/instagram/pinterest -- prefer Apify (monthly free) or OpenCLI (desktop, free). **LinkedIn uses Apify** for public posts (same `APIFY_API_TOKEN`, no LinkedIn login).

## Query syntax by source

Each source has its own search-query rules. Multi-word/long queries may return
fewer results on some backends — the agent should tune the query per source.

| Source | Query syntax | Notes |
|--------|-------------|-------|
| `bluesky` | Lucene: space=AND, `"quoted phrase"`, `from:handle`, `lang:code`, `#tag`, `(a OR b)`, `-term` | Phrase/boolean recommended |
| `stocktwits` | **ticker/crypto only** (`AAPL`, `$BTC`, `BTC`) | Non-financial topics return `[]`; resolved via symbol search |
| `x` | Literal keyword AND — **all words must appear** | Long/multi-word queries may return few results |
| `techmeme` | Phrase, wildcard, `AND/OR/NOT`, `sourcename:X` | Supports quoted phrases |
| `reddit` | Space-separated words | Multiple feeds searched |
| `digg` | Phrase match | CLI-based |
| `arxiv` | arXiv syntax: `all:`, `ti:`, `au:`, quoted, boolean | Official Atom API |
| `web` | Space-separated (Searxng/Brave) | Free-text |
| `rss` | Substring match on title/summary | Filter over configured feeds |
| `v2ex` | Substring match on latest topics | search endpoint removed; latest+filter |
| `youtube` | yt-dlp search query | Free-text |
| `xiaoyuzhou` | Podcast keyword search | Requires login token |

General guidance: prefer **short, specific keywords** (2-4 words). Very long
queries or phrases that only a specific site would phrase identically will
often return `[]` — the backend isn't broken, the query is too specific.

## MCP tools

### `search` -- the primary tool

**Description:**
> Search up to 32 social & web sources in parallel, score by engagement, optionally synthesize a cited brief. YOU control scope.
>
> Best scoping: `category` -- social: x, reddit, instagram, threads, tiktok, xiaohongshu, bilibili, youtube, pinterest, bluesky, linkedin, web, weibo, zhihu, douban, toutiao; it: github, hackernews, v2ex, rss, arxiv, dripstack, stackoverflow, lobsters; tech: arxiv, techmeme, digg, dripstack, hackernews; polec (politics & economics): truthsocial, xueqiu, stocktwits, polymarket; podcast: xiaoyuzhou. Categories overlap (e.g. arxiv is both it and tech) -- multiple categories union. `sources` picks individual names; both together = union; both omitted = all available sources EXCEPT podcast (xiaoyuzhou is opt-in: episode transcription is slow, request it explicitly when you need podcasts). Search returns metadata + a snippet per item -- xiaoyuzhou/youtube/bilibili are NOT transcribed/captioned here. With synthesize=true the top rich-media items are auto-backfilled with full content before the brief; with synthesize=false call fetch_content on any item you want in full. `max_chars_per_item` caps snippet length (raise for fuller CN posts, lower to save tokens).
>
> Returns `{brief, items, sources_used, source_summary, available_sources}`. Each item: `{source, title, url, author, date, score, engagement, text}`. source_summary is one compact line per outcome -- 'x:3; reddit:5 | EMPTY: rss, v2ex | QUOTA: tiktok(monthly limit) | ERRORS: digg(429) | NOTICE: zhihu(ZHIHU_COOKIE search failed — showing 热榜 instead; refresh the cookie)'; 'gated_off' means its credential env isn't set; NOTICE marks a degraded-but-working source (stale cookie fell back to a limited path) — usable data, but surface the caveat. Match query language to platform -- Chinese keywords work best for the CN sources. WeChat 公众号 queries on `web` auto-scope to mp.weixin.qq.com. Call list_sources if unsure what's configured.

### `list_sources`

> Inventory of all registered sources. Call before search when unsure what's active. Returns `[{name, description, needs_auth, available, required_env, default_days, default_limit}]`: available=false = gated (credential in required_env not set). No arguments.

### `synthesize`

> LLM-synthesize a cited brief from items returned by a prior `search(synthesize=false)`, WITHOUT re-searching. Args: `query` (the original), `items` (the prior items list). Returns `{brief}`.

### `fetch_content`

> Fetch the full content of ONE item found via search. Two-stage retrieval: search returns metadata + a snippet for every source; call this when an item is worth reading/hearing in full. Rich-media sources have dedicated backends -- xiaoyuzhou (pass the item's `audio_url` → Whisper transcript), youtube (watch URL or video id → captions), bilibili (video URL → CC subtitles if any); every other source falls back to Jina Reader on the item's url. Args: `source`, `id_or_url`. Returns `{source, url, content, ok}`.

### `read_url`

> Fetch any URL as clean markdown via Jina Reader. Use for the full text of a page found via search -- a thread, article, or repo -- when the item's `text` snippet isn't enough. Returns `{url, content, ok}`; content is '' on failure. Keyless.

## For agents -- quick usage guide

```
1. list_sources()                         # see what's configured; pick targets
2. search("Peter Steinberger",
          sources=["reddit","x","github","youtube"],
          days=14, synthesize=false)      # get raw scored rows, reason yourself
   -- or --
   search("OpenAI vs Anthropic",
          category=["tech","it"],
          days=30, synthesize=true)          # scope by topic group
   -- or --
   search("OpenAI vs Anthropic",
          days=30, synthesize=true)          # one call → cited brief + rows
   -- or --
   search("", trending=true,
          sources=["weibo"])              # hot lists, not keyword search
3. (optional) synthesize(query, items)     # re-brief the rows you already have
```

- **Default** (`sources=None`, `category=None`, `synthesize=true`): searches every configured source EXCEPT podcast (opt-in), auto-backfills full content for the top rich-media items, and returns a cited brief + all rows. Simplest.
- **By type** (`category=["tech"]`): one keyword scopes to a topic group (social / it / tech / polec / podcast) -- the easiest way to match the sources to the kind of query. Categories overlap; several union together.
- **Targeted** (`sources=[...]`): only hit what you need -- faster, cheaper, less noise. Combines with `category` (union).
- **Trending** (`trending=true`): query-free hot lists -- weibo 实时热搜 (heat values, no login), zhihu 热榜, hackernews front page, lobste.rs hottest, bilibili 综合热门, x/X trends (trends24 mirror, no login), github newly-hot repos (created this week, sorted by stars). `query` is ignored; `sources` scopes. Use for "what's hot on weibo right now" / "今日热搜". Non-trending sources you name come back as `skipped`.
- **Raw** (`synthesize=false`): metadata + snippets only, no backfill -- fast. Read the rows, then `fetch_content(source, id_or_url)` on the ones worth full text, and `synthesize(query, items)` to re-brief.
- **Podcast** (`category=["podcast"]` or `sources=["xiaoyuzhou"]`): opt-in because transcription is slow (minutes per episode) -- enable only when you actually need podcasts.
- Rich-media sources (xiaoyuzhou/youtube/bilibili) are metadata-only at search time; their transcripts/captions come from `fetch_content` (or the synthesize=true auto-backfill).
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

### Option C -- mcpo (multi-server host, recommended for OpenWebUI)

[mcpo](https://github.com/open-webui/mcpo) launches many MCP servers via `uvx` and exposes each as an OpenAPI endpoint. If you're already running the last30days server through mcpo, reach-mcp drops into the same slot -- just swap the `config.json` entry.

**1. config.json** -- list reach-mcp (see [deploy/mcpo-config.example.json](deploy/mcpo-config.example.json) for the full env set):
```jsonc
{
  "reach": {
    "command": "uvx",
    "args": ["reach-mcp", "--transport", "stdio"],
    "env": { "SEARXNG_URL": "http://searxng:8080", "OPENAI_API_KEY": "sk-..." }
  }
}
```

**2. entrypoint.sh** -- [deploy/entrypoint.sh](deploy/entrypoint.sh) installs reach-mcp's runtime deps on first start (cached under the mounted volume): `yt-dlp` (youtube), `bili-cli` (bilibili - handles B站 wbi/412), `gh` (github), Go + `digg`/`arxiv`/`techmeme` pp-cli. Copy it into your mcpo config dir.

> **⚠️ mcp SDK 2.x pin:** mcpo 0.0.20 (and several `uvx`-launched MCP servers) import 1.x mcp SDK symbols that mcp 2.0 renamed, and crash with `ImportError: cannot import name 'streamablehttp_client'...` / `McpError`. The entrypoint sets `UV_CONSTRAINT=/config/uv-constraints.txt` (`mcp<2`), which mcpo inherits into every child `uvx` process. Ship `deploy/uv-constraints.txt` next to your entrypoint.sh to customize; if absent, the entrypoint writes the same default.


**3. compose** -- [deploy/docker-compose.mcpo.yml](deploy/docker-compose.mcpo.yml) mirrors a production setup with `UV_CACHE_DIR`/`UV_TOOL_DIR`/`npm_config_cache` persistence, plus optional Searxng and `xiaohongshu-mcp` companion services:
```yaml
mcp:
  image: ghcr.io/open-webui/mcpo:latest
  volumes:
    - ./mcpo-config:/config        # entrypoint.sh + config.json
  environment:
    UV_CACHE_DIR: /config/uv-cache
    UV_TOOL_DIR: /config/uv-tools
    UV_TOOL_BIN_DIR: /config/uv-bin
    PATH: /config/uv-bin:/config/bin:/config/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
    npm_config_cache: /config/npm-cache
  entrypoint: ["/bin/bash", "/config/entrypoint.sh"]
  command: ["--host", "0.0.0.0", "--port", "8000", "--config", "/config/config.json"]
```

OpenWebUI then connects to `http://mcp:8000/reach` (OpenAPI) or `http://mcp:8000/reach/mcp` (native MCP).

> **OpenWebUI tool description (copy-paste):** OpenWebUI lets you override a tool's human-facing description. The one below matches reach-mcp's actual categories and defaults — paste it into the tool's description field so users see what the server can do:
>
> > 一次查询横跨 32 中英文信息源 —— 社媒通用（全网搜索、小红书、微博、知乎、豆瓣、头条、B站、X/Twitter、Reddit、Instagram、Threads、TikTok、YouTube、Pinterest、Bluesky、LinkedIn、quora）、IT 技术（GitHub、Hacker News、V2EX、RSS、arXiv、Dripstack、Stack Overflow、Lobste.rs）、科技（arXiv、Techmeme、Digg、Dripstack、Hacker News）、政经（雪球、Truth Social、Stocktwits、Polymarket）、播客（小宇宙——转录较慢，按需启用）。热搜热榜模式：微博实时热搜、知乎热榜、头条热榜、B站热门、X trends、GitHub 周热榜、HN front page、Lobste.rs 热门。

> **Upgrading deps:** `touch /config/UPGRADE` in the config dir, then restart the container -- the entrypoint clears its binary caches and reinstalls fresh (yt-dlp, bili-cli, pp-cli, etc.).
>
> **OpenCLI note:** the OpenCLI desktop boost (tiktok/instagram/pinterest/xueqiu) is intentionally NOT installed in this headless container -- those sources use their server-side backends (Apify / public APIs / Searxng), which is the intended default. OpenCLI only applies if you run mcpo on a desktop machine with Chrome.


## Configuration

All config is environment variables (a `Settings` dataclass). Everything is optional -- the server degrades to free-source-only mode if you set nothing.

### Quick reference

```bash
# ===== LLM (rerank + brief) =====
OPENAI_BASE_URL="https://your-gateway/v1"    # include /v1; default https://api.openai.com/v1
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
JINA_API_KEY="jina_..."                      # Jina key (read_url page reader only; keyless works at 20 RPM)
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
XIAOYUZHOU_ACCESS_TOKEN="..."                # 小宇宙 access token (phone-SMS login; required for search)
XIAOYUZHOU_REFRESH_TOKEN="..."               # 小宇宙 refresh token (for API; access+refresh both needed)
WHISPER_BASE_URL="http://gpu.savorcare.com:8080/v1"  # OpenAI-compatible whisper endpoint (xiaoyuzhou transcription)
WHISPER_API_KEY=""                           # optional; LocalAI doesn't check it
WHISPER_MODEL="whisper-large"                # model name (default: whisper-large)
XUEQIU_COOKIE="xq_a_token=...; u=..."        # 雪球 login cookie string (from Chrome; required for search)
ZHIHU_COOKIE="z_c0=...; d_c0=..."            # 知乎 browser Cookie string (optional; unlocks real search, else hot-list only)


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

> **按顺序获取每个 key 的完整步骤、入口 URL、以及推荐 RSS feed 清单,见 [docs/CREDENTIALS.md](docs/CREDENTIALS.md)**。本节省略版;下面列出每个 key 的用途和快速要点。

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
- `linkedin` -- Optional boost (Apify is the primary)

#### LinkedIn

LinkedIn searches **public posts via Apify** (`apimaestro/linkedin-posts-search-scraper-no-cookies`) -- keyword search, no LinkedIn cookies/login needed:

1. Set `APIFY_API_TOKEN` (same key as tiktok/instagram/pinterest; $5 free credits/month recurring)
2. That's it -- `linkedin` is enabled alongside the other Apify sources

Without an Apify token it falls back to a `site:linkedin.com` query through your configured Searxng (free but sporadic -- LinkedIn blocks most crawlers). Jina's `s.jina.ai` was removed 2026-08: it doesn't index LinkedIn (every query returned 0) and burns one-time tokens. `r.jina.ai` stays for `read_url` (page reader, no search tokens).

Optionally, setting `SCRAPECREATORS_API_KEY` adds ScrapeCreators results in parallel for a richer result set.

#### DripStack (financial newsletters)

Free and keyless -- always available, no setup. Search over premium financial newsletters (Substack/analyst write-ups). Best for ticker/company research. Complements `stocktwits` (retail sentiment) and `polymarket` (real-money odds).

#### RSS feeds (`RSS_FEEDS`)

Generic RSS/Atom source, free (uses `feedparser`, already a dependency). Set `RSS_FEEDS` to a comma-separated list of feed URLs; entries are filtered to the query within the recency window.

```bash
RSS_FEEDS="https://hnrss.org/frontpage,https://www.federalreserve.gov/feeds/press_all.xml"
```

> 📚 **已验证的推荐 feed 清单**——科技媒体、财经市场、政府经济数据/政策发布、政治军事、公司财报(SEC EDGAR),见 [docs/CREDENTIALS.md](docs/CREDENTIALS.md) 第 4 级。

#### Xiaohongshu / 小红书 (`XHS_MCP_URL`)

Uses the community-vetted [xiaohongshu-mcp](https://github.com/xpzouying/xiaohongshu-mcp) Go server (15K+ stars) as backend.

**Docker (recommended):** Add to your compose file (see `docker-compose.yml`). The `./data` volume is **required** — it stores the login cookies (they are lost on recreate without it); `./images` is only needed if you publish notes:
```yaml
xiaohongshu-mcp:
  image: ghcr.io/xpzouying/xiaohongshu-mcp:latest
  ports: ["18060:18060"]
  restart: unless-stopped
  init: true
  tty: true
  volumes:
    - ./data:/app/data
    - ./images:/app/images
  environment:
    - COOKIES_PATH=/app/data/cookies.json
    - HOME=/app/data/home
    - XDG_CONFIG_HOME=/app/data/config
```
Then set `XHS_MCP_URL=http://xiaohongshu-mcp:18060/mcp` and log in (below).

**Login (QR scan, once):** the image runs only the MCP server — there is no separate login binary. Start it, then scan the QR via any MCP client:
```bash
npx @modelcontextprotocol/inspector      # MCP Inspector
# connect to http://localhost:18060/mcp
# call `get_login_qrcode` → QR code appears → scan with the 小红书 App
#    (older images called it `login`; v2.0.0 renamed it)
# call `check_login_status` to confirm (older images: `check_login`)
```
> ⚠️ **Accounts registered with a non-mainland (境外) phone get routed to rednote**
> (the international Xiaohongshu), and scanning with the mainland app keeps showing
> "not logged in". Use the mainland 小红书 app + a mainland-registered account.
Notes: open the App *before* scanning (the QR expires quickly); don't log the same account in elsewhere on the web — 小红书 single-logs-in, a web login kicks the MCP account out. Cookies persist in the `./data` volume.

**Without Docker:** Download the binary from [releases](https://github.com/xpzouying/xiaohongshu-mcp/releases). Login is the same QR flow via the MCP `login` tool (or `go run cmd/login/main.go` from source), then start the server and set `XHS_MCP_URL=http://localhost:18060/mcp`.

#### Weibo / 微博 (no credentials)

Free, zero-config. Two-step pure-HTTP flow against the mobile realm (curl-verified 2026-08): `visitor.passport.weibo.cn/visitor/genvisitor2` mints SUB/SUBP visitor cookies in one call, then `m.weibo.cn/api/container/getIndex` returns real search results (text/author/interactions). Cookies are cached module-level and auto-regenerated on auth failure (`ok:-100`). The desktop site (s.weibo.com) needs JS fingerprinting and is NOT used.

#### Zhihu / 知乎 (`ZHIHU_COOKIE` optional)

Two tiers, both curl-verified 2026-08:

- **With `ZHIHU_COOKIE`** — real search via `search_v3`. Paste the browser `Cookie:` request header from a logged-in zhihu.com session (must contain `z_c0` and `d_c0`; F12 → Network → click any request → copy the Cookie header value). Works WITHOUT the `x-zse-96` signature as long as the cookie rides along. Returns answers/articles with upvote/comment counts.
- **Without it** — 热榜 hot-list browse via the unauthenticated mobile API (`api.zhihu.com/topstory/hot-lists/total`): top-30 filtered by query keywords, degrading to the raw list when nothing matches.

Expired/invalid cookies degrade to the hot list automatically (warning logged), never error the search.

> ⚠️ The cookie is a login credential — treat `ZHIHU_COOKIE` like a password. `z_c0` rotates if you log out; re-copy after re-login.

#### Douban / 豆瓣 (no credentials)

Free, keyless (live-verified 2026-08): keyword search across movies, TV, books, and music via the mobile `m.douban.com/rexxar/api/v2/search` API with an iOS User-Agent + `Referer: https://m.douban.com/` header (both required — the API rejects bare requests). Returns titles with rating value/vote count; canonical per-type URLs (`movie.douban.com/subject/...`, `book.douban.com/subject/...`). Ad/smart-box cards are filtered. No trending endpoint (Douban has no public hot-list API). Use Chinese keywords for best results.

#### WeChat articles / 微信公众号 (via the `web` source, auto-scoped)

WeChat MP articles are searchable through the existing `web` source: Searxng indexes them (verified 2026-08, 17 real results for 人工智能). Queries containing 公众号 / 微信文章 / weixin are **auto-scoped** with `site:mp.weixin.qq.com` on Searxng — no manual `site:` needed. There is no dedicated wechat source (WeChat has no public search API; the scraped-token approaches all require desktop mitmproxy).

#### Web search (`SEARXNG_URL`)

Required for the `web` source. Point to your self-hosted Searxng instance (default `http://searxng:8080`). If you don't have one, [Searxng](https://github.com/searxng/searxng) runs easily in Docker.

#### YouTube (`YTDLP_PROXY` / `YTDLP_COOKIES`)

Optional. From a **datacenter IP** (e.g. the mcpo container), YouTube bot-walls yt-dlp ("Sign in to confirm you're not a bot") and search returns 0 — this is an egress restriction, not a code issue. Two workarounds:

- `YTDLP_PROXY` — set to a **residential** proxy URL (e.g. `socks5://...`). A normal datacenter proxy won't help; only non-datacenter egress bypasses the wall.
- `YTDLP_COOKIES` — path to a `cookies.txt` (Netscape format) exported from a logged-in browser, or a browser name (`chrome`/`firefox`). See `docs/CREDENTIALS.md` §9.5 for the export steps.

If neither is set, `youtube` still works when reach runs from a residential/host IP (e.g. the dev machine).

#### Digg (`digg-pp-cli`)

Digg is auto-enabled when the `digg-pp-cli` binary is on `PATH`. Built from the last30days project's build steps. Without the CLI, `digg` stays gated off.

#### Apify (`APIFY_API_TOKEN`) -- threads, tiktok, instagram, pinterest, linkedin, quora

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

Podcast search + Whisper transcription. **Search requires a 小宇宙 account token** (phone-SMS login):

1. Login flow: the app sends a code to your phone, which returns `accessToken`/`refreshToken` (see [xiaoyuzhou-api](https://github.com/ylw1997/xiaoyuzhou-api) for the exact flow)
2. Set `XIAOYUZHOU_ACCESS_TOKEN=...`
3. Transcription uses an OpenAI-compatible Whisper endpoint (`WHISPER_BASE_URL`, default `http://gpu.savorcare.com:8080/v1`, model `whisper-large`). Point it at any self-hosted LocalAI or Groq's `api.groq.com/openai/v1` — the API key may be empty if your server doesn't check it.

Audio constraint (Whisper): files ≤ 25 MB, formats mp3/mp4/mpeg/mpga/m4a/wav/webm; no explicit duration cap at the API layer.

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
| `OPENAI_BASE_URL` | `OPENAI_BASE_URL` | Same — include the version path (`.../v1`); reach-mcp appends `/chat/completions`. Defaults to `https://api.openai.com/v1`. If the brief fails, the hint flags a missing `/v1` and raw items are still returned |
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

#### TikTok free backend / 抖音-free-channel (playwright, optional)

The `tiktok` source gains a **free, unlimited primary backend** when playwright + chromium are installed (live-verified 2026-08): a headless chromium opens `tiktok.com/explore`, runs the search as a same-origin in-page `fetch` (out-of-page HTTP and the TikTokApi library are bot-detected from datacenter IPs; the in-page fetch is not), parses the JSON, and **closes the browser before returning** — one launch per search, memory fully released between calls (measured: ~0.9GB RSS peak during the search, 0 after).

Enable it in the image (~530MB extra disk, no runtime cost until a search runs):

```dockerfile
RUN pip install --no-cache-dir playwright && playwright install --with-deps chromium
```

Without it the source silently falls back to Apify → OpenCLI → ScrapeCreators as before; the backend order is playwright (free) → Apify → OpenCLI → ScrapeCreators (paid/one-time).
