# Apify run-sync 接口的坑

When calling Apify's `run-sync-get-dataset-items` (used by reach-mcp tiktok/threads/instagram/pinterest):

- **Actor ID must be tilde form** `user~actor` in the URL, NOT `user/actor` — the slash form returns 404 `page-not-found`. (verified 2026-08-02)
- **Success is any 2xx**, not just 200 — completed runs return **201 Created** with the dataset items in the body. Checking `!= 200` silently discards all data.
- **Synchronous runs are slow**: threads ~26s, tiktok ~10s, instagram/others longer. The polite HTTP client's default timeout (~15s) kills them → pass an explicit `timeout=180` on the POST.
- Verified working actor IDs + input schemas (2026-08-02):
  - threads: `futurizerush/meta-threads-scraper` — `{mode:"search", keywords:[q], max_posts>=10}`
  - tiktok: `clockworks/tiktok-scraper` — `{searchQueries:[q], resultsPerPage:N, searchSection:"/video"}`
  - instagram: `apify/instagram-search-scraper` — `{search:q, searchType:"hashtag", searchLimit:N}`
  - pinterest: `automation-lab/pinterest-scraper` — `{searchQueries:[q], maxItems:N}`
- Free plan: $5/month recurring credits. Get actor input schema via `https://apify.com/<user>/<actor>/input-schema` (firecrawl scrape).
