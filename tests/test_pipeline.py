from __future__ import annotations

from datetime import datetime, timedelta, timezone

from reach_mcp.pipeline import SourceReport, cluster, dedup, score
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
