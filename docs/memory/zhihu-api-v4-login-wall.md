# 知乎 api/v4 登录墙

From the reach-mcp server's egress (datacenter proxy), zhihu serves only a login-walled truncated stub for both zhuanlan articles and question/answer pages (even keyed Jina). Verified 2026-09:

- **Question/answer** → `https://www.zhihu.com/api/v4/answers/{id}?include=content` with a desktop UA + `ZHIHU_COOKIE` returns **200 + full body** (clean `<p>` HTML), NO `x-zse-96` signature needed. This is the only reliable full-body path.
- **zhuanlan article** → `api/v4/articles/{id}` 403s (code 10003) — it needs a mobile signature; even keyed Jina returns only the lede + login wall. No full-body path from the server IP.
- Native `zhihu.com/question/...` HTML page → **403** from this IP.

reach-mcp content-fetch (`sources/zhihu.py::fetch_full_content`) routes question/answer via api/v4 with the cookie. See [reach-mcp-source-implementation-status](reach-mcp-source-implementation-status.md), [zhihu-weibo-toutiao-wechat-endpoints-verified](zhihu-weibo-toutiao-wechat-endpoints-verified.md).

**Why:** the old Jina fallback returned either the login-wall stub (garbage "content") or "" (ok:false) depending on Jina's upstream cache — flaky.
**How to apply:** never rely on zhihu HTML pages or plain Jina for full zhihu bodies; use api/v4 + cookie for answers, accept lede-only for zhuanlan.
