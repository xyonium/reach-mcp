# ScrapeCreators 一次性额度

In reach-mcp, ScrapeCreators (`SCRAPECREATORS_API_KEY`) backs tiktok/instagram/pinterest/linkedin-boost. Verified 2026-07: ScrapeCreators' free tier is **100 credits, one-time, no monthly reset** (confirmed by last30days GitHub issue #367 - they had wrongly claimed "10,000 free calls"). A single comprehensive search run consumes ~176 credits, so it's not viable long-term without paying ($10/mo+).

**Why:** reach-mcp's README previously inherited last30days' wrong "free" framing.

**How to apply:** For LinkedIn, use **Jina** (`JINA_API_KEY`) as the free primary backend instead - Jina's free key is a recurring monthly rate-limit quota (20 RPM no key, 500 RPM free key, 5000 RPM paid), NOT one-time credits. `s.jina.ai` search needs a key; `r.jina.ai` reader works keyless. tiktok/instagram/pinterest have NO free server-side alternative (confirmed via Agent Reach audit - they don't implement these either), so they stay SC-only and gated by default. See [reach-mcp-source-implementation-status](reach-mcp-source-implementation-status.md).
