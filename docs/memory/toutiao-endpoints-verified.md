# 头条端点验证

Toutiao access verified live from the container 2026-08-28 (source shipped, commit 643a95f, 30 sources):

- **Trending 热榜**: `GET www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc` — keyless JSON, ~50 items: `{ClusterIdStr, Title, HotValue, Url, LabelDesc}`. No signature, no cookie. Perfect for supports_trending.
- **Search**: `GET so.toutiao.com/search?dvpf=pc&keyword=<kw>` with ONLY a desktop UA (NO Referer!) — the SSR HTML embeds results in `<script type="application/json">` card blobs. Walk the blobs, collect dicts carrying `article_url`/`display_url`, strip `<b>` highlight tags from title/abstract, `publish_time` = unix seconds. Dedup on URL.
- **CRITICAL gotcha**: adding `Referer: https://www.toutiao.com/` makes the server return a 211KB JS-shell page with ZERO result cards; the UA-only request returns the full ~610KB server render (isolated via A/B curl). Counter-intuitive — normally Referer helps.
- **DEAD path**: `/api/search/content/?keyword=...` returns 200 with `return_count:0` both bare and in-page (playwright) — msToken-signature gated. Don't retry without a signature impl.
- m.toutiao.com 302s; mobile search API path 404s.

**How to apply:** toutiao source needs no cookie/credential ever; if search starts returning 0, first check the page size (shell ≈210KB vs full ≈600KB) before suspecting the parser. See [zhihu-weibo-toutiao-wechat-endpoints-verified](zhihu-weibo-toutiao-wechat-endpoints-verified.md) (supersedes its toutiao TODO), [reach-mcp-source-implementation-status](reach-mcp-source-implementation-status.md).
