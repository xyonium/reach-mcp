# Apify 替代与 IT 源缺口调研

Researched 2026-08-28 for reach-mcp (30 sources):

**Q1 — sources with Apify as PRIMARY (6):**
- tiktok: FIXED — playwright in-page fetch is primary now (free).
- threads: Apify-only in code. threads.net/search?q= loads via browser (264KB HTML w/ posts) — a playwright in-page fetch like tiktok's is the plausible free path; NOT yet implemented/tested.
- instagram: Apify primary → OpenCLI → ScrapeCreators. explore/ returns 200 but content is login-walled; free scrape unlikely headless.
- pinterest: Apify primary → OpenCLI → ScrapeCreators. The public BaseSearchResource endpoint 403s from datacenter IP (needs browser+cookies).
- linkedin: Apify + ScrapeCreators merged + Searxng fallback already. Guest jobs API 302s. Public-post search free path = Searxng (already wired); fine as is.
- quora: Apify-only. GraphQL 403s keyless. Searxng site:quora.com is the free fallback candidate.
Cheapest wins: **threads playwright backend** (mirror tiktok's _tiktok_playwright pattern) + **quora via Searxng site:** fallback. pinterest/instagram realistically stay paid/gated.

**Q2 — IT-platform gap probes (all live from container):**
- **stackoverflow: WORKS keyless** — api.stackexchange.com 2.3 search/advanced (fromdate/sort/tags), 24.2M questions, no quota concerns at search volume. Best new IT source candidate. Site param covers stackexchange network (serverfault, superuser, unix.SX...).
- **lobste.rs: WORKS keyless** — hottest.json (25 stories w/ score/comment_count/tags), /t/<tag>.json (tag feeds: rust, python, devops...). search.json 404s without auth — search = client-side filter over tag feeds, like v2ex pattern.
- **linux.do: 403** even latest.json/top.json with browser UA (Cloudflare anon-block from datacenter IP). Discourse JSON is right IF reachable; needs cookie (LINUXDO_COOKIE?) or residential — untested with cookie. Also reachable via Searxng site:linux.do through the existing web source.
- **juejin (掘金): recommend feed keyless WORKS** (recommend_api/v1/article/recommend_all_feed → item_info.article_info{title,brief_content,view_count}); search_api needs auth (returns 0); article_rank returns []. Feed-only = trending-style source, not keyword search.
- cnblogs 301 (fine, has RSS), oschina 200 (has RSS).
- StackOverflow value verdict: NOT dead — still the canonical Q&A corpus (2.55 q/min); its "decline" is about new-question volume, not corpus value. Deep-IT coverage gap is real: current IT sources (github/hn/v2ex/rss/arxiv/dripstack) have no Q&A corpus at all.

**How to apply:** implement priority: stackoverflow source (keyless, trivial, biggest IT-depth win) > lobste.rs (keyless, niche but quality) > threads playwright (free tiktok-pattern) > juejin feed (trending-only) > linux.do (needs cookie decision). See [reach-mcp-source-implementation-status](reach-mcp-source-implementation-status.md), [source-backend-priority-rule](source-backend-priority-rule.md).
