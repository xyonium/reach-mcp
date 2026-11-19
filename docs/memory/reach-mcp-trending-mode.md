# 热搜 / 热榜模式

reach-mcp has a dedicated trending mode (commit 39ba6f0, 2026-08-28): `search(query, trending=true)` routes to `pipeline.run_trending` which fans out over sources with `supports_trending = True` + `fetch_trending(limit)` override. Query is ignored in this mode; `sources` scopes; non-trending sources get an explicit "skipped" report; items ordered by raw engagement sum (no query scoring); notices flow through SourceReport.notice as usual.

**Live sources (all verified 2026-08-28):**
- weibo 实时热搜: containerid `106003type=25&t=3&disable_hot=1&filter_type=realtimehot` via the same genvisitor2 visitor cookies — **NO login/cookie needed** (user asked; confirmed). ~85 items, `desc_extr` = heat value.
- zhihu 热榜: `api.zhihu.com/topstory/hot-lists/total` (unauthenticated; same endpoint as cookieless browse).
- hackernews: Algolia `tags=front_page`.
- bilibili: `api.bilibili.com/x/web-interface/ranking/v2?rid=0&type=all` (no auth, no wbi signing on this endpoint).
- x/X trends (commit 21d0b41): scrape `trends24.in/{X_TRENDS_LOCATION}/` — **keyless**, mirrors the login-gated x.com trends data; `trend-link` anchors + `tweet-count data-count` (often empty). run_trending deliberately skips the available() gate so this works while x search stays AUTH_TOKEN-gated.
- github trending (commit 21d0b41): NO official API — approximation via search API `created:>{7d} stars:>50&sort=stars` (keyless 10 req/min, GH_TOKEN raises). Engagement includes language.

**TODO candidates (not yet implemented, recorded 2026-08-28):**
- douyin hot search (Apify `kjames2001/douyin-hot-search` or cloudcharlestom hot-rank-scraper — Apify = backup only per user rule)
- toutiao 热搜 (so.toutiao.com SSR has hot sections; fragile schema)
- baidu 热搜/贴吧热议 (top.baidu.com used to be plain HTML — untested)

**How to apply:** adding a trending source = override `fetch_trending`, set `supports_trending = True`; no category changes needed. See [zhihu-weibo-toutiao-wechat-endpoints-verified](zhihu-weibo-toutiao-wechat-endpoints-verified.md), [source-backend-priority-rule](source-backend-priority-rule.md).
