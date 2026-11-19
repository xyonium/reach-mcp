# 中文平台抓取工具评估（TikTok / 豆瓣 / 大众点评 / 知识星球）

Evaluated + live-tested 2026-08-28 for reach-mcp:

**TikTok (container, no proxy):**
- davidteather/TikTok-Api lib (6.6k★, active): its own HTTP requests get EmptyResponseException (bot-detected) even with harvested msToken, anti-automation flags, custom viewport. tiktokapipy/PyTok dead libraries, unusable.
- BUT the working path: playwright headless chromium → goto `tiktok.com/explore` → **in-page `fetch('/api/search/general/full/?keyword=...&offset=0&count=10&search_id=0')` returns 200 with real items** (desc/playCount/diggCount/author/id; top-level `{status_code, data:[{item:{...}}], has_more}`). Page itself loads fine (~365KB, no real captcha; "captcha/verify" strings are just JS bundle config). msToken cookie auto-set by JS.
- Cost: playwright + chromium ≈ 250MB in container + system deps. No desktop needed — fully server-side.

**Douban 豆瓣 (all keyless, from container):**
- `m.douban.com/rexxar/api/v2/search?q=&count=` — works with **plain httpx** given iOS UA + `Referer: https://m.douban.com/` (the earlier bare-curl 400 was missing headers, NOT TLS fingerprint — curl_cffi NOT required). Response: `subjects.items[] = {layout, target:{title, rating:{value,count}, card_subtitle, cover_url, year, id}, target_type, type_name}`.
- `movie.douban.com/j/search_subjects` — only on the movie host, tag-browse not keyword search (book/music hosts 404).
- Reviews: `rexxar/api/v2/subject/{id}/reviews?count=&start=` returns 200 (valid subject id needed).
- Engine reference: goesByhc/cn-scraper-mcp `engines/douban.py` (m.douban.com/rexxar/api/v2, safari_ios impersonation + optional cookie).

**Dianping 大众点评: DEAD from this container** — search 302→`account.dianping.com/pclogin` even with curl_cffi chrome TLS impersonation. IP-based, not fingerprint. Kills the sidecar option too (same container IP).

**ZSXQ 知识星球: DEAD for reach-mcp — confirmed with a real cookie (2026-08-28).** API is login+membership double-gated: valid cookie with zero joined groups → platform-wide topics search returns EMPTY topics (scope = joined groups only); non-member group info → code 1005 "not a member"; no cookie → 401. Some endpoints now also reject third-party tools outright (code 1059 "use official Skill"). No free/public content layer exists. Do NOT implement even if a cookie is offered.

**cn-scraper-mcp / MediaCrawler:** see [reach-mcp-container-egress-diagnosis](reach-mcp-container-egress-diagnosis.md); MediaCrawler = local-Chrome CDP architecture, fails headless-first.

**Verdict (2026-08-28): BOTH IMPLEMENTED + SHIPPED v0.4.1.** douban source (commit 0aaf1fd, keyless rexxar via plain httpx + iOS UA + Referer). TikTok playwright backend (commit c4b45c2): `sources/_tiktok_playwright.py` launches headless chromium PER SEARCH CALL, in-page fetch to `/api/search/general/full/`, browser closed in `finally` — measured 0 MB chromium RSS after each search (~0.9GB peak during). Backend order: playwright (free) → Apify → OpenCLI → ScrapeCreators.

**Deployment (mcpo container, NOT a standalone image):** reach-mcp runs via `uvx` inside the `mcp` (mcpo) container, installed from PyPI — GitHub push alone is NOT live. Release flow: bump version in pyproject+`__init__`, tag `v*`, push → GitHub Actions publish.yml → PyPI. v0.4.1 live 2026-08-28.
- playwright python pkg ships behind the `[tiktok]` extra: `uvx --from "reach-mcp[tiktok]" reach-mcp` (a `uv tool install playwright` would land in an isolated env the server can't import — don't). Production config at `/mnt/docker/mcpserver/config.json` updated (backup `.bak-*` alongside).
- chromium binary: entrypoint section 7b installs into `PLAYWRIGHT_BROWSERS_PATH=/config/ms-playwright` (on the mounted /config volume → persists); pwenv venv on the volume hosts the installer/driver; skipped when `.chromium-ok` marker exists; `/config/UPGRADE` flag wipes it.
- CI gotcha: tests run WITHOUT playwright installed — any lifecycle test must patch `_playwright_available` AND `_playwright`, else fetch returns [] before the browser mock is reached (v0.4.0 shipped with this broken test; fixed in 0.4.1).
- Pending: `docker restart mcp` to activate (entrypoint installs chromium ~5min one-time, then uvx --refresh picks 0.4.1 with tiktok extra).

**How to apply:** douban source = rexxar search + iOS UA + Referer headers via existing PoliteClient; dianping = skip; zsxq = gated on ZSXQ cookie env; tiktok = playwright backend if user accepts the chromium dependency. See [reach-mcp-source-implementation-status](reach-mcp-source-implementation-status.md), [source-backend-priority-rule](source-backend-priority-rule.md).
