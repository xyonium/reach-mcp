from __future__ import annotations

import pkgutil
from datetime import datetime, timedelta, timezone

from reach_mcp.pipeline import (
    CATEGORIES,
    DEFAULT_EXCLUDED,
    SourceReport,
    classify_error,
    cluster,
    dedup,
    expand_categories,
    render_source_summary,
    score,
)
from reach_mcp.sources.base import Item


def _item(source, title, url, eng, days_ago=0, score_=0.0):
    date = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return Item(source=source, id=url, title=title, url=url, engagement=eng,
                date=date, score=score_)


def test_dedup_by_url():
    a = _item("reddit", "T", "https://x.com/a", {"upvotes": 10})
    b = _item("x", "T2", "https://x.com/a", {"likes": 5})  # same URL
    c = _item("hn", "T3", "https://x.com/b", {"points": 7})
    out = dedup([a, b, c])
    assert len(out) == 2
    # keep the higher-scored one at that URL
    assert {i.url for i in out} == {"https://x.com/a", "https://x.com/b"}


def test_score_recency_and_engagement():
    old = _item("reddit", "old", "https://o", {"upvotes": 100}, days_ago=29)
    new = _item("reddit", "new", "https://n", {"upvotes": 10}, days_ago=1)
    scored = score([old, new], days=30)
    new_s = next(i for i in scored if i.url == "https://n").score
    old_s = next(i for i in scored if i.url == "https://o").score
    assert new_s > old_s  # recency outweighs raw upvotes here


def test_cluster_groups_near_dup():
    a = _item("reddit", "OpenAI ships thing", "https://r/1", {})
    b = _item("x", "OpenAI ships thing!!", "https://x/1", {})
    c = _item("hn", "Totally different", "https://h/1", {})
    out = cluster([a, b, c])
    clusters = {i.cluster for i in out}
    assert len(clusters) == 2  # a,b share a cluster; c alone
    ab = [i for i in out if i.url in ("https://r/1", "https://x/1")]
    assert ab[0].cluster == ab[1].cluster


def test_source_report_status():
    r = SourceReport(source="x", status="gated_off", count=0, error=None)
    assert r.status == "gated_off"


def test_classify_error_rate_limited():
    assert classify_error("HTTP 429 Too Many Requests") == "rate_limited"
    assert classify_error("monthly limit exceeded for credits") == "rate_limited"
    assert classify_error("quota exceeded") == "rate_limited"


def test_classify_error_generic():
    assert classify_error("connection reset") == "errored"
    assert classify_error("403 Forbidden") == "errored"


def test_expand_categories_both_empty_is_none():
    assert expand_categories(None, None) is None
    assert expand_categories([], []) is None


def test_expand_categories_expands_and_unions():
    out = expand_categories(["reddit"], ["tech"])
    assert out is not None
    # explicit sources kept, category members appended, no duplicates
    assert out[0] == "reddit"
    assert set(out) == {"reddit", *CATEGORIES["tech"]}
    assert len(out) == len(set(out))
    # passing a source already inside the category must not duplicate it
    out2 = expand_categories(["arxiv"], ["tech"])
    assert out2 is not None and out2.count("arxiv") == 1


def test_expand_categories_unknown_category_ignored():
    assert expand_categories(None, ["bogus"]) is None
    assert expand_categories(["reddit"], ["bogus"]) == ["reddit"]


def test_categories_cover_every_registered_source():
    # Compare against the source modules on disk, not the global registry —
    # other tests (test_registry, test_integration) register stub sources
    # ("free"/"gated"/"stub") into SOURCES that must not leak into categories.
    import reach_mcp.sources as pkg
    on_disk = {
        m.name for m in pkgutil.iter_modules(pkg.__path__)
        if m.name not in {"base", "__init__"} and not m.name.startswith("_")
    }
    grouped = {n for names in CATEGORIES.values() for n in names}
    assert grouped == on_disk  # no source left out, no phantom names


def test_xiaoyuzhou_only_in_podcast_and_default_excluded():
    assert CATEGORIES["podcast"] == ["xiaoyuzhou"]
    assert "xiaoyuzhou" not in CATEGORIES["social"]
    assert "xiaoyuzhou" in DEFAULT_EXCLUDED


def test_sources_may_overlap_categories():
    # arxiv/dripstack/hackernews are intentionally in two categories —
    # category expansion unions, so overlap must not error or duplicate.
    assert "arxiv" in CATEGORIES["it"] and "arxiv" in CATEGORIES["tech"]
    out = expand_categories(None, ["it", "tech"])
    assert out is not None and out.count("arxiv") == 1


def test_render_summary_groups_empty_and_shows_counts():
    reports = [
        SourceReport(source="x", status="ok", count=3),
        SourceReport(source="reddit", status="ok", count=5),
        SourceReport(source="rss", status="no_results"),
        SourceReport(source="v2ex", status="gated_off"),
        SourceReport(source="tiktok", status="rate_limited",
                     error="Monthly usage limit exceeded"),
        SourceReport(source="digg", status="errored", error="HTTP 429"),
    ]
    s = render_source_summary(reports)
    assert "reddit:5; x:3" in s or "x:3; reddit:5" in s  # ok sources w/ counts
    assert "EMPTY: rss, v2ex" in s  # silent merged on one line
    assert "QUOTA: tiktok(" in s and "limit" in s  # quota with reason
    assert "ERRORS: digg(" in s


def test_weibo_zhihu_in_social_category():
    """CN sources (2026-08): weibo full search, zhihu hot-list — both social."""
    assert "weibo" in CATEGORIES["social"]
    assert "zhihu" in CATEGORIES["social"]


def test_source_report_notice_field_renders_in_summary():
    """Degraded-but-working sources surface a NOTICE line (e.g. zhihu cookie
    search fell back to the hot list — data is fine but the agent should know)."""
    reports = [
        SourceReport(source="zhihu", status="ok", count=30,
                     notice="ZHIHU_COOKIE search failed (403) — showing 热榜 hot list instead; refresh the cookie for real search"),
        SourceReport(source="weibo", status="ok", count=5),
    ]
    s = render_source_summary(reports)
    assert "NOTICE: zhihu" in s
    assert "热榜" in s
    assert "zhihu:30" in s  # still counted as ok
    assert "NOTICE: weibo" not in s


def test_weibo_visitor_failure_reported_when_cookieless_results():
    """If weibo's visitor flow dies entirely it returns no rows — that must NOT
    be a silent EMPTY: the summary should point at the visitor-cookie mechanism."""
    reports = [
        SourceReport(source="weibo", status="no_results", count=0,
                     notice="visitor cookie flow failed (genvisitor2 unreachable?) — weibo returns nothing without visitor cookies"),
    ]
    s = render_source_summary(reports)
    assert "NOTICE: weibo" in s
    assert "visitor" in s
