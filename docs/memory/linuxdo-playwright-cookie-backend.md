# linux.do 的 Playwright + Cookie 后端

linux.do access (source shipped v0.5.0, commit c354c9e):

- **Cloudflare blocks everything from datacenter IP**: plain HTTP 403, AND curl WITH the full login cookie still gets the JS challenge. The ONLY path that passes is headless chromium with the LINUXDO_COOKIE pairs seeded into the browser context via `context.add_cookies` (domain `.linux.do`), then same-origin `page.goto` to the Discourse JSON endpoints. Verified live: 30 latest topics, 50 search hits.
- **Endpoints** (all Discourse-standard JSON): `latest.json` (topic_list.topics), `top.json?period=daily` (topic_list.topics), `search.json?q=` (topics at TOP level, not under topic_list). Topic shape: `{id,title,slug,posts_count,like_count,views,created_at,last_poster_username}`; URL = `linux.do/t/{slug}/{id}`.
- **Cookie**: needs `_t` + `_forum_session` + `cf_clearance` in the browser Cookie string. cf_clearance is UA+IP-bound but the playwright chromium UA passes it. Written to prod `/mnt/docker/mcpserver/config.json` reach env as `LINUXDO_COOKIE`.
- **JSON paste gotcha**: cookie contains `g_state={"i_l":1,...}` with BARE double quotes — pasting by hand into config.json breaks the JSON. Fixed by programmatically escaping inner quotes. If editing config.json by hand, the whole file then fails to parse (mcpo won't start).
- Per-call browser lifecycle (tiktok/threads memory contract); lazy playwright import; gated on LINUXDO_COOKIE + playwright presence.

**How to apply:** if linuxdo returns nothing, first check cookie staleness (re-export from browser) — CF clearance rotates. See [reach-mcp-release-flow](reach-mcp-release-flow.md), [apify-replacement-and-it-gap-research](apify-replacement-and-it-gap-research.md) (Q2 linuxdo 403 anon entry now resolved).
