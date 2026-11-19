# 源分类（category）维护

reach-mcp `search` tool accepts `category: list[str]` alongside `sources`. Defined in `pipeline.py::CATEGORIES`, expanded by `expand_categories()` (union with explicit `sources`, both empty = all configured MINUS `DEFAULT_EXCLUDED`, unknown category silently ignored). The five groups (xiaoyuzhou lives only in podcast, and is excluded from the default sweep because transcription is slow):

- **social** — x, reddit, instagram, threads, tiktok, xiaohongshu, bilibili, youtube, pinterest, bluesky, linkedin, web
- **it** — github, hackernews, v2ex, rss, arxiv, dripstack
- **tech** — arxiv, techmeme, digg, dripstack, hackernews
- **polec** (政经) — truthsocial, xueqiu, stocktwits, polymarket
- **podcast** — xiaoyuzhou

A source may sit in MULTIPLE categories (arxiv/dripstack/hackernews are both it+tech) — expansion unions, so overlap is intended. github is it-only (user call 2026-08-03: it's code/dev, not science/tech-news). web (Searxng) sits in social as the generic catch-all. `DEFAULT_EXCLUDED = ("xiaoyuzhou",)` in pipeline.py keeps podcast out of the no-explicit-sources default. The human-facing OpenWebUI description matching these groups lives in README §Option C ("OpenWebUI tool description (copy-paste)").

**Why:** user wanted the OpenWebUI description and the tool to share one grouping; category names must stay in sync across `pipeline.py::CATEGORIES`, `_SEARCH_DESC` in tools.py, and README. `tests/test_pipeline.py` pins membership = source modules on disk, the xiaoyuzhou-only-in-podcast rule, and the multi-category overlap. The category Literal type must include every CATEGORIES key (podcast was added 2026-08-03).

**How to apply:** adding a source means putting it in ≥1 CATEGORIES group or the coverage test fails; adding a category means adding the key AND the Literal member. See [reach-mcp-source-implementation-status](reach-mcp-source-implementation-status.md), [reach-mcp-whisper-gateway-behavior](reach-mcp-whisper-gateway-behavior.md).
