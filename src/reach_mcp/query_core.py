"""Deterministic per-source query adaptation.

Long, natural-language queries fail on sources whose search is *literal
keyword AND matching* (X) or that only respond to very short keyword slots
(Threads) — every word must appear, so a verbose question returns zero.
This module strips question/meta "noise" words down to the core subject and
produces per-source query variants.

Ported and extended from last30days' lib/query.py + adapter `_extract_core_subject`
wrappers (v3.18.0), whose caps are grounded in observed per-source failure modes:
  - X (bird_x.py): literal AND, max 5 words, then degrade OR-groups -> first-2-words.
  - Threads (threads.py): "3+ words or leaked boolean operators return zero" -> cap 2.

Layered noise sets let each source class strip the right vocabulary:
  BASE_NOISE    articles/prepositions/question/meta — strictest (x, bluesky, ...)
  SOCIAL_NOISE  light micro-blog set (threads)
  VIRAL_NOISE   BASE + prompt/methodology meta (tiktok, instagram, pinterest)
  CN_NOISE      Chinese meta-words (最新/评测/教程/怎么/推荐...), substring-stripped
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Noise-word sets
# ---------------------------------------------------------------------------

# Question words, articles, meta/research descriptors with no discriminating
# power in a match. Stripped for the strictest sources.
BASE_NOISE = frozenset({
    # articles / prepositions / conjunctions
    "a", "an", "the", "is", "are", "was", "were", "and", "or",
    "of", "in", "on", "for", "with", "about", "to",
    # question words
    "how", "what", "which", "who", "why", "when", "where",
    "does", "should", "could", "would",
    # research/meta descriptors
    "best", "top", "good", "great", "latest", "new", "news",
    "update", "updates", "trending", "hottest", "hot", "popular", "viral",
    "practices", "features", "guide", "tutorial", "recommendations",
    "advice", "review", "reviews", "usecases", "use", "cases", "case",
    "examples", "comparison", "versus", "vs", "tool", "tools",
    "tips", "tricks", "methods", "strategies", "approaches",
    "using", "uses", "people", "saying", "think", "said", "lately",
})

# Micro-blog platforms: research/meta words rarely appear in a post body.
SOCIAL_NOISE = frozenset({
    "best", "top", "good", "great", "awesome",
    "latest", "new", "news", "update", "updates",
    "trending", "hottest", "popular", "viral",
    "practices", "features", "recommendations", "advice",
    "or", "and",
})

# Viral/discovery platforms: BASE (drops articles/prepositions) + the
# prompt-meta and methodology clusters that flood these platforms.
VIRAL_NOISE = BASE_NOISE | frozenset({
    "killer", "prompt", "prompts", "prompting",
    "methods", "strategies", "approaches", "hacks", "ideas",
})

# Chinese meta/question words — the提问方式 (how you ask), not the内容 (内容).
# Stripped so a verbose CN question collapses to its content keywords.
# Ordered longest-first so 求推荐/大家怎么看 match before their substrings.
CN_NOISE = frozenset({
    "大家怎么看", "求推荐", "怎么样", "怎么办", "值得买", "好不好",
    "最新", "新闻", "资讯", "消息", "评测", "测评", "教程", "攻略",
    "怎么", "如何", "什么", "哪些", "哪个", "推荐", "对比", "比较",
    "怎么看", "值得", "体验", "案例", "用法", "盘点", "好用", "靠谱",
    "咋样", "近来", "最近", "近期", "表现",
})
# Longest-first so multi-char phrases are removed before their substrings.
_CN_NOISE_SORTED = sorted(CN_NOISE, key=len, reverse=True)

# Boolean operators that leak from planners ("A OR B") and zero out literal
# keyword endpoints (Threads per last30days). Stripped as standalone tokens.
_BOOLEAN_RE = re.compile(r"\b(?:OR|AND|NOT)\b")

# Question/meta prefixes stripped from the front of a query (longest first).
_PREFIXES = (
    "what are the best", "what is the best", "what are the latest",
    "what are people saying about", "what do people think about",
    "how do i use", "how to use", "how to",
    "what are", "what is", "tips for", "best practices for",
)

# Trailing meta suffixes stripped from the end (X per last30days).
_SUFFIXES = (
    "best practices", "use cases", "prompt techniques",
    "prompting techniques", "prompting tips",
)

# CJK unified ideographs — each counts as one "word" for cap purposes.
_CJK_RE = re.compile(r"[一-鿿㐀-䶿]")


def _strip_prefixes(text: str) -> str:
    for p in _PREFIXES:
        if text.startswith(p + " "):
            return text[len(p):].strip()
    return text


def _strip_suffixes(text: str) -> str:
    for s in _SUFFIXES:
        if text.endswith(" " + s):
            return text[: -len(s)].strip()
    return text


def strip_boolean(text: str) -> str:
    """Remove standalone boolean operators (OR/AND/NOT) that zero out literal
    keyword endpoints. Lowercase 'or/and' inside normal prose are noise words
    handled separately; this targets the planner-style uppercase leaks."""
    return _BOOLEAN_RE.sub(" ", text)


def word_count(text: str) -> int:
    """CJK-aware word count: each CJK char = 1 word, Latin runs split on space."""
    cjk = len(_CJK_RE.findall(text))
    latin = [w for w in _CJK_RE.sub(" ", text).split() if w.strip()]
    return cjk + len(latin)


def _strip_cn_noise(text: str) -> str:
    """Remove embedded CN noise substrings (Chinese has no spaces, so noise
    words sit inside a token: 英伟达最新财报 -> 英伟达财报). Longest-first."""
    for phrase in _CN_NOISE_SORTED:
        text = text.replace(phrase, " ")
    return re.sub(r"\s+", " ", text).strip()


def extract_core_subject(
    topic: str,
    *,
    noise: frozenset[str] | None = None,
    max_words: int | None = None,
    strip_suffixes: bool = False,
) -> str:
    """Reduce a verbose query to its core subject.

    Strips question prefixes, optional trailing meta suffixes, boolean
    operators, and per-source noise words; optionally caps word count.
    Falls back to the cleaned original if everything was noise.
    """
    text = topic.lower().strip().rstrip("?!.")
    if not text:
        return text
    text = _strip_prefixes(text)
    if strip_suffixes:
        text = _strip_suffixes(text)
    text = strip_boolean(text)

    noise_set = noise if noise is not None else BASE_NOISE
    # CN sources: noise words are substrings (no spaces), strip them first,
    # then filter whole-token Latin noise for any mixed-language remainder.
    if noise_set is CN_NOISE:
        text = _strip_cn_noise(text)
        kept = [w for w in text.split() if w not in BASE_NOISE]
    else:
        kept = [w for w in text.split() if w not in noise_set]
    if max_words is not None and kept:
        kept = kept[:max_words]
    result = " ".join(kept)
    return result if result else text.strip()


def extract_compound_terms(topic: str) -> list[str]:
    """Multi-word terms worth quoting: hyphenated compounds and title-cased
    multi-word proper nouns ("Claude Code", "React Native")."""
    terms = [m.group() for m in re.finditer(r"\b\w+-\w+(?:-\w+)*\b", topic)]
    terms += [m.group() for m in re.finditer(r"(?:[A-Z][a-z]+\s+){1,}[A-Z][a-z]+", topic)]
    return terms


# ---------------------------------------------------------------------------
# Per-source adaptation policy
# ---------------------------------------------------------------------------

# Sources that manage their own filtering or whose query is a stock code/symbol
# — never rewrite (identity).
IDENTITY_SOURCES = frozenset({"v2ex", "rss", "xueqiu", "stocktwits"})

# Strict-literal sources: core-first with degradation handled inside the source.
# Maps source -> (noise set, max_words, strip_suffixes).
_STRICT_SOURCES: dict[str, tuple[frozenset[str], int, bool]] = {
    "x": (BASE_NOISE, 5, True),
    "threads": (SOCIAL_NOISE, 2, False),
}

# Strip-only sources: remove meta words to sharpen recall, but do NOT truncate
# (these are semantic/tokenizing search or keyword slots that tolerate phrases).
# Micro-blogs use BASE_NOISE (drops articles/prepositions too — "about the X"
# -> "X"); discovery/keyword slots use VIRAL/BASE; CN uses CN_NOISE.
_STRIP_ONLY: dict[str, frozenset[str]] = {
    "bluesky": BASE_NOISE,
    "truthsocial": BASE_NOISE,
    "tiktok": VIRAL_NOISE,
    "instagram": VIRAL_NOISE,
    "pinterest": VIRAL_NOISE,
    "linkedin": BASE_NOISE,
    "quora": BASE_NOISE,
    "xiaohongshu": CN_NOISE,
}


def adapt_query(source: str, query: str) -> str:
    """Return the primary query to send to `source`.

    Identity sources pass through untouched. Strict sources collapse to the
    core subject (their fetch() may further degrade on zero results). Strip-only
    sources get meta words removed without truncation. Everything else passes
    through unchanged (semantic/tokenizing search tolerates long queries).
    """
    q = query.strip()
    if source in IDENTITY_SOURCES:
        return q
    if source in _STRICT_SOURCES:
        noise, cap, sfx = _STRICT_SOURCES[source]
        return extract_core_subject(q, noise=noise, max_words=cap, strip_suffixes=sfx)
    if source in _STRIP_ONLY:
        cleaned = extract_core_subject(q, noise=_STRIP_ONLY[source])
        return cleaned or q
    return q


def x_degradation_variants(topic: str) -> list[str]:
    """Ordered fallbacks for X when the core query returns zero, mirroring
    last30days bird_x: (1) proper-noun OR-group, (2) first two core words."""
    core = extract_core_subject(topic, noise=BASE_NOISE, max_words=5, strip_suffixes=True)
    variants: list[str] = []
    words = core.split()
    if len(words) >= 2:
        compounds = extract_compound_terms(topic)
        if compounds:
            variants.append(" OR ".join(f'"{t}"' for t in compounds[:3]))
    if len(words) > 2:
        variants.append(" ".join(words[:2]))
    return variants
