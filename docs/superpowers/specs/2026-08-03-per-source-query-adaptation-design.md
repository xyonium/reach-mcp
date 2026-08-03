# Per-Source Query Adaptation — Design (condensed)

**Date:** 2026-08-03 · **Status:** implemented · **Commit:** 0869841

## Problem
Agents pass long natural-language queries to `search`. On sources with **literal
keyword-AND matching** (x) or **short keyword slots** (threads), every word must
appear, so a verbose question returns zero. Separately, agents over-pick
`synthesize=false` because the tool description mentioned it 3× with concrete
actions while `true` appeared once with a cost warning.

## Approach
Deterministic per-source query adaptation, ported from last30days `lib/query.py`
+ adapter `_extract_core_subject` wrappers, extended with CJK support. Plus
description rebalancing. (An LLM query-planner was considered and deferred — the
deterministic layer covers the failure modes at zero cost/latency.)

## Source groups (verified against last30days comments + live probes)
| Group | Sources | Policy |
|---|---|---|
| Identity | v2ex, rss, xueqiu, stocktwits | untouched (own filter / stock code) |
| Strict | x (≤5 words + strip suffixes), threads (≤2 words + strip boolean OR/AND) | collapse to core, degrade on zero |
| Strip-only | bluesky, truthsocial (BASE); tiktok, instagram, pinterest (VIRAL); linkedin, quora (BASE); xiaohongshu (CN) | strip meta words, **no truncate** |
| Semantic | reddit, web, arxiv, github, hackernews, youtube, bilibili, xiaoyuzhou, polymarket, dripstack, digg, techmeme | passthrough |

## Key verified decisions
- **x** (bird_x.py evidence: "literal keyword AND, max 5 words"): collapse to
  core, then degrade — proper-noun OR-group → first-2-words.
- **threads** (threads.py evidence: "3+ words or leaked boolean operators return
  zero"): strip boolean, cap 2.
- **xiaohongshu**: live probe (2026-08-03) — 16-char full sentence returns 20
  results; it is **semantic recall, not literal AND**. Moved out of strict group;
  only CN meta-words stripped, no truncation. (8-char cap idea rejected on data.)
- **bluesky**: last30days uses light SOCIAL_NOISE, but that leaves "about the X";
  upgraded to BASE_NOISE.

## Noise sets
- `BASE_NOISE`: articles/prepositions/question/meta EN words.
- `SOCIAL_NOISE`: light micro-blog set. `VIRAL_NOISE`: BASE + prompt/methodology.
- `CN_NOISE`: Chinese meta-words (最新/评测/教程/怎么/推荐...), **substring**-stripped
  (Chinese has no spaces, so noise sits inside tokens: 英伟达最新财报 → 英伟达 财报).

## Implementation
- `query_core.py` (new): noise sets, `extract_core_subject`, `adapt_query`,
  `x_degradation_variants`, CJK-aware `word_count`.
- `pipeline._fetch_one`: `adapt_query(source.name, query)` before `fetch`.
- `x.py`: backend chain extracted to `_search_backends`; `fetch` iterates
  `[core] + degradation_variants`.
- `threads.py`: comment documents the pipeline-side contract.
- `tools.py`: `_SEARCH_DESC` rewrite — synthesize=true stated as the default
  one-call report path up front; false demoted to a custom-post-processing side
  path; per-source query-length guidance added; fetch_content pointer moved to
  `_FETCH_CONTENT_DESC`.

## Tests
`tests/test_query_core.py` — 23 tests (EN/CJK extraction, x/threads adaptation,
group passthrough, degradation variants). Full suite: 121 passed, ruff clean.

## Deferred
LLM query-planner (subqueries + ranking_query feeding rerank) — only worth it if
deterministic adaptation still leaves complex cross-domain queries empty.
