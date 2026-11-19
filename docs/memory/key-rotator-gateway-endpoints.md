# key-rotator 网关端点

reach-mcp routes paid/limited third-party APIs through a local **key-rotator** gateway so secrets (and rotation/quotas) live in one place instead of the service config: `http://api-key-rotator:8788` (Docker-internal name; also on the same key pattern as `APIFY_BASE_URL`).

Verified 2026-09-11:
- **`/exa/*`** — Exa search + `/exa/contents` (full text). Real key = `EXA_API_KEY` (the rotated credential the gateway accepts). Used by `_exa.py` (search) and `readurl.py` (`exa_read` for fetch_content).
- **`/firecrawl/v2/scrape`** (or legacy fallback `/v2/scrape`; v1 `/v1/scrape` shuts down 2026-12-10 UTC) — **Firecrawl Cloud through the rotator, NO key required** (any Bearer, incl. "dummy", or omitted `Authorization` returns 200). Equivalent to the direct self-hosted `http://firecrawl:3002` (also keyless on the trusted net). Both scrape to full markdown. Note: `api-key-rotator` currently uses a shared 30s upstream HTTP timeout for Firecrawl and does per-request key selection (no crawl/batch job-key affinity).
- **`/tavily/extract`** — Tavily extract, mounted under `/tavily`. Verified 200 + `raw_content` with dummy Bearer. NOTE: probing `/tavily/*` from a datacenter IP can transiently IP-block the path (404/127) — retry before concluding it's absent. `readurl.py` `TAVILY_BASE_URL` defaults to `api.tavily.com`, set `http://api-key-rotator:8788/tavily` to route via rotator.

**Pattern for a new proxied service `X`:** add `X_BASE_URL` defaulting to the real API, accept the (possibly dummy) key from env, point the env at the rotator. Services behind the rotator must be in `NO_PROXY` so the container's HTTP(S)_PROXY doesn't hijack the Docker-internal call.

**Why:** adding a keyless base so future services can be swapped/rotated centrally without touching reach-mcp's config.json secrets.
**How to apply:** for any new paid API, prefer `_BASE_URL` env + dummy-key default (see `readurl._tavily_read` / `_exa._base`); set `X_BASE_URL=http://api-key-rotator:8788` in config.json.
