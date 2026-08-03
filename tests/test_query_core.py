"""Unit tests for deterministic per-source query adaptation (query_core)."""
from __future__ import annotations

from reach_mcp.query_core import (
    CN_NOISE,
    SOCIAL_NOISE,
    adapt_query,
    extract_core_subject,
    strip_boolean,
    word_count,
    x_degradation_variants,
)


class TestExtractCoreSubject:
    def test_strips_question_prefix(self):
        assert extract_core_subject("what are the best LLM frameworks") == "llm frameworks"

    def test_strips_noise_words(self):
        assert extract_core_subject("latest news about nvidia earnings") == "nvidia earnings"

    def test_strips_suffix_when_enabled(self):
        assert extract_core_subject(
            "hermes agent use cases", strip_suffixes=True
        ) == "hermes agent"

    def test_max_words_caps(self):
        assert extract_core_subject(
            "claude code production workflow pipeline deploy", max_words=3
        ) == "claude code production"

    def test_strips_boolean_operators(self):
        assert extract_core_subject("multi-agent OR agent simulation") == "multi-agent agent simulation"

    def test_fallback_when_all_noise(self):
        # Everything is noise -> fall back to the cleaned original, not "".
        out = extract_core_subject("best top latest", noise=SOCIAL_NOISE)
        assert out == "best top latest"

    def test_empty(self):
        assert extract_core_subject("") == ""


class TestCJK:
    def test_cjk_chars_count_as_words(self):
        assert word_count("英伟达") == 3
        assert word_count("英伟达 财报") == 5  # 3 + 2 CJK chars, space-separated
        assert word_count("vibe coding") == 2

    def test_cn_noise_stripped(self):
        out = extract_core_subject("英伟达最新财报怎么样", noise=CN_NOISE)
        assert "最新" not in out and "怎么样" not in out
        assert "英伟达" in out and "财报" in out

    def test_cn_noise_keeps_content(self):
        out = extract_core_subject("求推荐 好用的耳机", noise=CN_NOISE)
        assert "耳机" in out


class TestStripBoolean:
    def test_removes_uppercase_or_and(self):
        assert strip_boolean("agents OR tools AND mcp").split() == ["agents", "tools", "mcp"]

    def test_keeps_lowercase_prose(self):
        # lowercase 'or' is a normal word, not an operator leak
        assert strip_boolean("mac or cheese") == "mac or cheese"


class TestAdaptQuery:
    def test_identity_sources_untouched(self):
        for src in ("v2ex", "rss", "xueqiu", "stocktwits"):
            assert adapt_query(src, "NVDA 最新 财报 怎么样") == "NVDA 最新 财报 怎么样"

    def test_x_collapses_to_core(self):
        assert adapt_query("x", "what are the latest claude code prompting techniques") == \
            "claude code"

    def test_x_caps_five_words(self):
        out = adapt_query("x", "one two three four five six seven")
        assert out == "one two three four five"

    def test_threads_caps_two_words(self):
        assert adapt_query("threads", "claude code production workflow") == "claude code"

    def test_threads_strips_boolean(self):
        assert adapt_query("threads", "multi-agent OR agent simulation tools") == \
            "multi-agent agent"

    def test_bluesky_strips_but_no_truncate(self):
        out = adapt_query("bluesky", "latest news about the claude code release today")
        assert "latest" not in out and "news" not in out
        assert "claude code release" in out  # content words preserved, not capped to 2

    def test_xiaohongshu_cn_strip_only(self):
        out = adapt_query("xiaohongshu", "英伟达最新财报表现怎么样")
        assert "最新" not in out and "怎么样" not in out
        assert "英伟达" in out and "财报" in out

    def test_semantic_sources_passthrough(self):
        q = "what are the best LLM agent frameworks for production"
        for src in ("reddit", "web", "arxiv", "github", "youtube", "bilibili"):
            assert adapt_query(src, q) == q


class TestXDegradation:
    def test_or_group_for_multiword(self):
        variants = x_degradation_variants("Claude Code multi-agent simulation")
        assert any('"' in v and "OR" in v for v in variants)

    def test_first_two_words_fallback(self):
        variants = x_degradation_variants("claude code production workflow pipeline")
        assert "claude code" in variants

    def test_short_query_no_variants(self):
        assert x_degradation_variants("nvda") == []
