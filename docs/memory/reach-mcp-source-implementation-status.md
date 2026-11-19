# 各源实现状态

reach-mcp has 29 registered sources. **Verified working in the container deployment (v0.1.23, 2026-08-02)**:

**NEW 2026-08-28 (commit 0aaf1fd, TDD, live-verified):** douban — keyless search via m.douban.com/rexxar/api/v2/search with iOS UA + `Referer: https://m.douban.com/` (both headers REQUIRED; plain httpx passes — no TLS impersonation). Movies/TV/books/music with rating/votes, per-type URLs, ad cards filtered. Category: social. No trending endpoint exists.

**NEW 2026-08-28 (commits 40468b8 + de848a1, TDD, live-verified):** weibo — genvisitor2 SUB/SUBP cookies → m.weibo.cn getIndex search, zero credentials (see [zhihu-weibo-toutiao-wechat-endpoints-verified](zhihu-weibo-toutiao-wechat-endpoints-verified.md); gotcha: page_type must be separate param or you get hot-search cards with 0 mblogs); zhihu — ZHIHU_COOKIE (browser cookie with z_c0) unlocks real search_v3 WITHOUT x-zse-96 signature; without cookie = api.zhihu.com hot-list browse (filter top-30 by query, degrade to raw list; search errors also degrade). Both in CATEGORIES social.

**Free, server-side, verified (theme keywords return results):** arxiv, bilibili, bluesky, dripstack, github, hackernews, polymarket, reddit, techmeme, web (Searxng), v2ex (Python/AI keywords return 3+; search endpoint removed upstream → latest+filter), rss (AI keyword matches hnrss Show HN), youtube (now pure CLI yt-dlp + flat-playlist; search/title/views work, subtitles don't on datacenter IP), x (bird GraphQL), xueqiu (login cookie), xiaoyuzhou (search+whisper), truthsocial (urllib+last30days UA), stocktwits (bitcoin→3; ticker-only).

**Free $5/mo Apify (verified 2026-08-02):** tiktok, threads, instagram, pinterest — all 4 now work after fixing actor IDs + inputs:
- threads → `futurizerush/meta-threads-scraper` (mode=search, keywords[], max_posts>=10)
- tiktok → `clockworks/tiktok-scraper` (searchQueries[], resultsPerPage)
- instagram → `apify/instagram-search-scraper` (search=<str>, searchType, searchLimit)
- pinterest → `automation-lab/pinterest-scraper` (searchQueries[], maxItems)
CRITICAL: Apify run-sync endpoint needs TILDE form (`user~actor`) not slash (`user/actor`) → 404. Accept 2xx (201 carries data).

**Companion-service backed (VERIFIED WORKING 2026-08-02, user logged in):** xiaohongshu → xiaohongshu-mcp at `XHS_MCP_URL`. Tool is `search_feeds` (v2.0.0, NOT `search_notes`). Returns {feeds:[{id, xsecToken, noteCard:{displayTitle, user.nickname, interactInfo.{likedCount,commentCount,collectedCount,sharedCount}}}]}. Needs companion LOGGED IN (get_login_qrcode + check_login_status, renamed in v2.0.0). URL needs xsec_token. ⚠️ companion intermittently slow (>30s) → reach uses 45s timeout + retry. ⚠️ 境外-phone accounts route to rednote (mainland app scan fails) — documented in README/CREDENTIALS.

**Binary-gated:** digg — needs `digg-pp-cli` (installed). BUT digg's API (di.gg/api/search/stories) is rate-limited (429) from datacenter IP → CLI falls back to local FTS5 = 0 results even for theme keywords (AI/Apple/Trump all 0). Shared with last30days, not a reach bug.

**Platform-limited (expected 0 even for theme keywords):** linkedin (Jina generic search returns 0 for CEO/Microsoft/Google — Jina doesn't index LinkedIn; site: scoping 500s).

**Infrastructure-limited:** youtube SUBTITLES from the container datacenter IP return 0 (never succeeded in container; host yt-dlp DOES get en subs for some videos). Search/title/views work from container via flat-playlist + cookies. Precise mechanism (diagnosed 2026-08-03): cookies+proxy get yt-dlp past the bot-wall to "Downloading subtitles", but android/tv player clients serve only storyboard formats on datacenter IPs → "Requested format is not available". Needs residential egress (see [reach-mcp-container-egress-diagnosis](reach-mcp-container-egress-diagnosis.md)).

**How to apply:** When a user asks about a "missing" source or why only N sources work, reference this list. The source code is correct (mirrors last30days/Agent-Reach); most "0 result" cases are (a) query doesn't match the source's domain (use theme keywords: v2ex→Python/AI, rss→AI, stocktwits→ticker), (b) auth/credential not set (xueqiu cookie, xiaohongshu login), or (c) infrastructure egress (youtube subtitles, digg). See [scrapecreators-one-time-credits](scrapecreators-one-time-credits.md) and [source-backend-priority-rule](source-backend-priority-rule.md).
