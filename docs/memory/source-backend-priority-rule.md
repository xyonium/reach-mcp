# 源后端优先级规则

When choosing backends for reach-mcp sources, the user's rule is: **server-side headless-capable approaches come FIRST; OpenCLI (which needs desktop Chrome via a browser bridge) is only an installed-boost or a last resort when no free non-desktop option exists.**

**Why:** reach-mcp is deployed server-side (Docker/headless). A desktop-Chrome-dependent backend (OpenCLI) won't work in that deployment, so it must not preempt a working server-side path. Only when the user has OpenCLI installed locally should it contribute (as a parallel boost, not the primary).

**How to apply:**
- Sources with a free headless API (xueqiu JSON API, web Searxng, linkedin Jina, threads/tiktok/ig/pin Apify): API is primary; OpenCLI runs in parallel as a boost only when `opencli` is on PATH, merging extra hits.
- tiktok/instagram/pinterest priority: **Apify (headless, $5/mo) -> OpenCLI (desktop) -> ScrapeCreators**. Apify first.
- xueqiu: JSON API first, OpenCLI boost merged when installed (NOT CLI-first — the earlier version had this backwards and was corrected).
- Independent CLIs that run headless (NOT desktop Chrome) CAN be primary: **bili-cli** (user confirmed: headless binary, handles wbi/412 — preferred over raw API), **techmeme-pp-cli**, **digg-pp-cli**. These are fine as primary because they don't need a desktop browser.
- Do NOT invert: never let OpenCLI preempt a headless server-side backend.

See [reach-mcp-source-implementation-status](reach-mcp-source-implementation-status.md).
