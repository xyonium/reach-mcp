# 知乎 / 微博 / 头条 / 微信端点验证

curl-verified from this box (2026-08-27, datacenter IP, no login):

**微博 Weibo — WORKS (纯HTTP两步):**
1. `GET visitor.passport.weibo.cn/visitor/genvisitor2?cb=visitor_callback&from=weibo.cn` → JSONP with `sub`/`subp` directly (one call, no tid+incarnate needed)
2. Set SUB/SUBP cookies on `.weibo.cn` domain → `GET m.weibo.cn/api/container/getIndex?containerid=100103type=1&q={kw}&page_type=searchall` (headers: Referer m.weibo.cn, MWeibo-Pwa:1, X-Requested-With) → `ok:1`, 16 cards with mblog text/author/engagement. Hot search: containerid `106003type=25&t=3&disable_hot=1&filter_type=realtimehot`.
- Desktop visitor flow (passport.weibo.com/visitor/genvisitor + incarnate) gets cookies but they DON'T work on m.weibo.cn (separate wapsso realm) and desktop s.weibo.com shows "Sina Visitor System" JS fingerprint page. Use genvisitor2 only.
- `qinyuanpei/mcp-server-weibo` (pip: mcp-server-weibo, `weibo-cli`) VERIFIED working: trending/users/search_content/topics/comments/feeds/profile/fans/followers, auto visitor cookie + optional QR login. Used as reference implementation; its source at src/mcp_server_weibo/weibo.py.

**知乎 Zhihu — 热榜 WORKS, search WORKS WITH COOKIE (updated 2026-08-28, commit de848a1):**
- `GET api.zhihu.com/topstory/hot-lists/total?limit=N` (mobile host, plain UA) → 200, 30 items with target.title + heat. NO login, NO signature.
- **Search unlocked**: `GET www.zhihu.com/api/v4/search_v3?t=general&q={kw}&correction=1&offset=0&limit=N` with the user's browser Cookie header (must contain `z_c0` + `d_c0`) works WITHOUT x-zse-96 signature. Response: `data[]` with `type: search_result` (skip gaokao/hot_timing/knowledge_ad noise) → object = answer (nested question.title) or article, voteup_count/comment_count/created_time/excerpt (has `<em>` tags). Desktop SSR search page still WAF-blocked even WITH cookie (403 zh-zse-ck challenge). Gotcha: percent-encode CN query in Referer header (httpx rejects non-latin-1 header bytes).
- Implemented in sources/zhihu.py: ZHIHU_COOKIE env → search; unset/stale → hot-list degrade. Live-verified with user's real cookie: 人工智能 → 4 results incl. 8.6k-upvote zhuanlan article.
- ⚠️ **WAF poisoning**: one request with a REJECTED z_c0 blacklists the client (~IP+UA) briefly — even the cookie-free hot-list endpoint then 401s. So: hot-list requests never carry the cookie; a 401/403 on search stops the source with a SourceReport notice instead of degrading (non-auth 5xx still degrade). SourceReport.notice / Source.last_notice render as `NOTICE: zhihu(...)` in source_summary (commit 0dc79e6).
- Question-detail API still needs signature (code 10003) — fetch_content for zhihu not implemented.
- **WeChat (commit 0dc79e6)**: web source auto-scopes `site:mp.weixin.qq.com` when the query contains 公众号/微信文章/weixin (regex `_WECHAT_INTENT` in sources/web.py); agent guidance in _SEARCH_DESC mentions it.

**头条 Toutiao — WORKS (SSR):** `GET so.toutiao.com/search?keyword={kw}` → 200, ~2MB HTML, results embedded in SSR JSON blobs (`"title":"..."` with `<em>` highlights, ~15 unique). Parseable but fragile (no stable schema); secondary sources (51CTO/百科) mixed in.

**微信公众号 — covered by EXISTING web source:** local Searxng (port 3080 in compose) `?q=site:mp.weixin.qq.com+{kw}&format=json` → 17 real article URLs. No new source needed; just guidance/query-adaptation.

**贴吧 Tieba — BLOCKED:** tieba.baidu.com/f/search/res returns 200 but JS shell (no s_post elements server-side). Would need Playwright (MediaCrawler) — skip for now.

**Apify actors (untested, fallback only per user: Apify quota is small, backup-only):** blackfalcondata/zhihu-scraper (hotList/questions/profiles ops), piotrv1001/weibo-scraper (profile/posts, may not do search), kuaima/douyin-search.

**How to apply:** implementing weibo source: port the two-step genvisitor2+search flow with cookie caching (SUB/SUBP last ~days; re-gen on ok:-100). Zhihu source: hot-list only, or behind ZHIHU_COOKIE env for search/detail. See [reach-mcp-source-implementation-status](reach-mcp-source-implementation-status.md), [source-backend-priority-rule](source-backend-priority-rule.md).
