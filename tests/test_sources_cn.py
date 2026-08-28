from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from reach_mcp.sources import get_source
from reach_mcp.sources.base import Row, set_client


@pytest.mark.asyncio
async def test_v2ex_parses_topics():
    c = AsyncMock()
    c.get_json = AsyncMock(return_value=[{
        "id": 1, "title": "Python tips", "url": "https://v2ex.com/t/1",
        "member": {"username": "u"}, "created": 1751328000, "replies": 3,
    }])
    set_client(c)
    rows = await get_source("v2ex").fetch("python", 30, 10)
    assert rows and rows[0].title == "Python tips" and rows[0].engagement["replies"] == 3


@pytest.mark.asyncio
async def test_xueqiu_api_primary_without_cli(monkeypatch):
    """Without OpenCLI and without cookie, xueqiu uses the public suggest API."""
    monkeypatch.setattr("reach_mcp.sources.xueqiu._has_cli", lambda: False)
    monkeypatch.delenv("XUEQIU_COOKIE", raising=False)
    monkeypatch.setattr(
        "reach_mcp.sources.xueqiu._fetch_via_api",
        AsyncMock(return_value=[Row(source="xueqiu", id="AAPL", title="Apple Inc.",
                                    url="https://xueqiu.com/S/AAPL",
                                    author=None, date=None, engagement={}, text="")]),
    )
    rows = await get_source("xueqiu").fetch("AAPL", 30, 10)
    assert rows and rows[0].title == "Apple Inc."
    assert "AAPL" in rows[0].url


@pytest.mark.asyncio
async def test_xueqiu_merges_opencli_boost(monkeypatch):
    """With OpenCLI installed, its extra hits are merged onto the API results."""
    monkeypatch.setattr("reach_mcp.sources.xueqiu._has_cli", lambda: True)
    monkeypatch.delenv("XUEQIU_COOKIE", raising=False)
    monkeypatch.setattr(
        "reach_mcp.sources.xueqiu._fetch_via_cli",
        AsyncMock(return_value=[Row(source="xueqiu", id="TSLA", title="Tesla",
                                    url="https://xueqiu.com/S/TSLA",
                                    author=None, date=None, engagement={}, text="")]),
    )
    monkeypatch.setattr(
        "reach_mcp.sources.xueqiu._fetch_via_api",
        AsyncMock(return_value=[Row(source="xueqiu", id="AAPL", title="Apple",
                                    url="https://xueqiu.com/S/AAPL",
                                    author=None, date=None, engagement={}, text="")]),
    )
    rows = await get_source("xueqiu").fetch("stock", 30, 10)
    titles = [r.title for r in rows]
    assert "Apple" in titles and "Tesla" in titles  # API + OpenCLI merged


@pytest.mark.asyncio
async def test_bilibili_uses_search_api(monkeypatch):
    monkeypatch.setattr("reach_mcp.sources.bilibili._has_cli", lambda: False)
    monkeypatch.setattr(
        "reach_mcp.sources.bilibili._fetch_via_api",
        AsyncMock(return_value=[Row(
            source="bilibili", id="BV1", title="Vid", url="https://b23.tv/1",
            author="up", date=None, engagement={"play": 100}, text="",
        )]),
    )
    rows = await get_source("bilibili").fetch("ai", 30, 10)
    assert rows and rows[0].engagement["play"] == 100


@pytest.mark.asyncio
async def test_youtube_shells_to_ytdlp(monkeypatch):
    async def fake_search(query, limit):
        return [{"id": "yt1", "title": query, "url": "https://youtu.be/1",
                 "text": "transcript", "date": None, "engagement": {}}]
    monkeypatch.setattr("reach_mcp.sources.youtube._search_videos", fake_search)
    rows = await get_source("youtube").fetch("rust", 30, 5)
    assert rows and rows[0].text == "transcript"


@pytest.mark.asyncio
async def test_youtube_search_cmd_argv0_is_ytdlp(monkeypatch, tmp_path):
    """The search command must start with `yt-dlp`, not the cookies flag.

    Regression: _ytdlp_common_args returns ONLY the extra args; prepending them
    without also expanding _YTDLP_BASE made argv[0] = '--cookies', which
    FileNotFoundError'd in the container.
    """

    import reach_mcp.sources.youtube as yt

    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    monkeypatch.setenv("YTDLP_COOKIES", str(cookies))
    monkeypatch.delenv("YTDLP_PROXY", raising=False)

    captured = []

    class _FakeProc:
        async def communicate(self):
            return (b"", b"")

    async def fake_exec(*args, **kwargs):
        captured.append(args)
        return _FakeProc()

    monkeypatch.setattr(yt.asyncio, "create_subprocess_exec", fake_exec)
    await yt._search_videos("test", 3)
    assert captured, "expected a subprocess call"
    argv = captured[0]  # args IS the argv list: (yt-dlp, --cookies, ...)
    assert argv[0] == "yt-dlp"
    assert "--flat-playlist" in argv
    assert "--cookies" in argv


@pytest.mark.asyncio
async def test_weibo_parses_search_cards(monkeypatch):
    """Happy path: visitor cookies exist, getIndex returns cards with mblogs."""
    monkeypatch.setattr(
        "reach_mcp.sources.weibo._visitor_cookies",
        AsyncMock(return_value={"SUB": "x", "SUBP": "y"}))
    c = AsyncMock()
    c.get_json = AsyncMock(return_value={"ok": 1, "data": {"cards": [
        {"mblog": {
            "id": "5112", "bid": "AbCdEf",
            "text": "AI 长文要点 <br />人工智能",
            "created_at": "Tue Aug 25 12:00:00 +0800 2026",
            "user": {"screen_name": "人民日报"},
            "reposts_count": 10, "comments_count": 5, "attitudes_count": 100,
        }},
        {"card_type": 11, "card_group": [
            {"mblog": {"id": "5113", "bid": "XyZ", "text": "第二条",
                        "created_at": "Tue Aug 25 13:00:00 +0800 2026",
                        "user": {"screen_name": "胡锡进"},
                        "reposts_count": 1, "comments_count": 2, "attitudes_count": 3}},
        ]},
    ]}})
    set_client(c)
    rows = await get_source("weibo").fetch("人工智能", 30, 10)
    assert len(rows) == 2
    r0 = rows[0]
    assert r0.source == "weibo" and r0.id == "5112"
    assert r0.author == "人民日报"
    assert r0.url == "https://m.weibo.cn/status/AbCdEf"
    assert "人工智能" in r0.text and "<br />" not in r0.text
    assert r0.engagement == {"reposts": 10, "comments": 5, "likes": 100}
    # cookie header sent to m.weibo.cn
    headers = c.get_json.call_args.kwargs.get("headers", {})
    assert "SUB=x" in headers.get("Cookie", "")


@pytest.mark.asyncio
async def test_weibo_regenerates_cookie_on_auth_failure(monkeypatch):
    """ok:-100 means the cached visitor cookie died; regen once and retry."""
    calls = {"n": 0}

    async def fake_cookies():
        calls["n"] += 1
        return {"SUB": f"v{calls['n']}", "SUBP": f"p{calls['n']}"}

    monkeypatch.setattr("reach_mcp.sources.weibo._visitor_cookies", fake_cookies)
    monkeypatch.setattr("reach_mcp.sources.weibo._reset_cookie_cache", lambda: None)
    c = AsyncMock()
    c.get_json = AsyncMock(side_effect=[
        {"ok": -100},  # first attempt: stale cookie
        {"ok": 1, "data": {"cards": [{"mblog": {
            "id": "1", "bid": "B", "text": "t",
            "created_at": "Tue Aug 25 12:00:00 +0800 2026",
            "user": {"screen_name": "u"},
            "reposts_count": 0, "comments_count": 0, "attitudes_count": 0,
        }}]}},
    ])
    set_client(c)
    rows = await get_source("weibo").fetch("ai", 30, 10)
    assert calls["n"] == 2 and len(rows) == 1  # regen happened, second call succeeded


@pytest.mark.asyncio
async def test_weibo_returns_empty_when_visitor_flow_fails(monkeypatch):
    monkeypatch.setattr(
        "reach_mcp.sources.weibo._visitor_cookies",
        AsyncMock(return_value=None))
    rows = await get_source("weibo").fetch("ai", 30, 10)
    assert rows == []


@pytest.mark.asyncio
async def test_zhihu_parses_hot_list():
    """api.zhihu.com/topstory/hot-lists/total works without login (verified)."""
    c = AsyncMock()
    c.get_json = AsyncMock(return_value={"data": [
        {"target": {
            "id": 2076281057649718231,
            "title": "帮扶老人被索赔事件，怎样看待这一结果？",
            "url": "https://api.zhihu.com/questions/2076281057649718231",
            "follower_count": 604,
            "answer_count": 192,
        }},
        {"target": {
            "id": 2, "title": "电视台的新闻主播会是第一个被AI彻底取代的职业岗位吗？",
            "url": "https://api.zhihu.com/questions/2",
            "follower_count": 141, "answer_count": 55,
        }},
    ]})
    set_client(c)
    rows = await get_source("zhihu").fetch("AI", 30, 10)
    assert len(rows) == 1  # only the AI-matching item passes the filter
    r = rows[0]
    assert r.source == "zhihu" and r.author is None
    assert "AI" in r.title
    assert r.engagement["answers"] == 55
    assert r.url == "https://www.zhihu.com/question/2"  # api host rewritten to www


@pytest.mark.asyncio
async def test_zhihu_empty_query_returns_top_items():
    """Empty/short query = theme browse: return the hot list unfiltered."""
    c = AsyncMock()
    c.get_json = AsyncMock(return_value={"data": [
        {"target": {"id": 1, "title": "问题一", "url": "https://api.zhihu.com/questions/1",
                     "follower_count": 10, "answer_count": 2}},
        {"target": {"id": 2, "title": "问题二", "url": "https://api.zhihu.com/questions/2",
                     "follower_count": 20, "answer_count": 4}},
    ]})
    set_client(c)
    rows = await get_source("zhihu").fetch("", 30, 10)
    assert len(rows) == 2  # unfiltered hot list


@pytest.mark.asyncio
async def test_zhihu_falls_back_to_top_items_when_no_match():
    """Query matches nothing -> degrade to top hot items (like v2ex would 0 out)."""
    c = AsyncMock()
    c.get_json = AsyncMock(return_value={"data": [
        {"target": {"id": 1, "title": "帮扶老人被索赔事件",
                     "url": "https://api.zhihu.com/questions/1",
                     "follower_count": 10, "answer_count": 2}},
    ]})
    set_client(c)
    rows = await get_source("zhihu").fetch("量子计算", 30, 10)
    assert rows and rows[0].title == "帮扶老人被索赔事件"  # fallback: hot list itself


@pytest.mark.asyncio
async def test_zhihu_search_via_cookie(monkeypatch):
    """With ZHIHU_COOKIE, search_v3 returns real results (verified 2026-08: no
    x-zse-96 signature needed when the request carries a logged-in cookie)."""
    monkeypatch.setenv("ZHIHU_COOKIE", "z_c0=abc; d_c0=def")
    c = AsyncMock()
    c.get_json = AsyncMock(return_value={"data": [
        {"type": "gaokao", "object": {"type": "major"}},          # noise: skipped
        {"type": "hot_timing", "object": {}},                      # noise: skipped
        {"type": "search_result", "object": {
            "type": "answer", "id": "2074807194219033769",
            "question": {"id": 42, "title": "人工智能的本质是不是就是数学？"},
            "title": "",
            "excerpt": "军事是最早相信<em>人工智能</em>的",
            "url": "https://api.zhihu.com/answers/2074807194219033769",
            "voteup_count": 4, "comment_count": 0,
            "created_time": 1787452583,
        }},
        {"type": "knowledge_ad", "object": {}},                    # ad: skipped
    ]})
    set_client(c)
    rows = await get_source("zhihu").fetch("人工智能", 30, 10)
    assert len(rows) == 1
    r = rows[0]
    assert r.source == "zhihu" and r.id == "2074807194219033769"
    assert r.title == "人工智能的本质是不是就是数学？"
    assert "人工智能" in r.text and "<em>" not in r.text
    assert r.engagement["upvotes"] == 4 and r.engagement["comments"] == 0
    assert r.url == "https://www.zhihu.com/question/42/answer/2074807194219033769"
    assert (r.date or "").startswith("2026-")
    # cookie header was sent
    headers = c.get_json.call_args.kwargs.get("headers", {})
    assert "z_c0=abc" in headers.get("Cookie", "")


@pytest.mark.asyncio
async def test_zhihu_search_results_beat_hot_list(monkeypatch):
    """Cookie search takes priority over hot-list filtering."""
    monkeypatch.setenv("ZHIHU_COOKIE", "z_c0=abc")
    c = AsyncMock()
    c.get_json = AsyncMock(return_value={"data": [
        {"type": "search_result", "object": {
            "type": "article", "id": "9",
            "title": "一篇专栏文章", "excerpt": "内容",
            "url": "https://api.zhihu.com/articles/9",
            "voteup_count": 1, "comment_count": 0,
        }},
    ]})
    set_client(c)
    rows = await get_source("zhihu").fetch("随便什么", 30, 10)
    assert rows and rows[0].title == "一篇专栏文章"
    # hot-list endpoint was never called
    assert "hot-lists" not in c.get_json.call_args.args[0]


@pytest.mark.asyncio
async def test_zhihu_search_failure_degrades_to_hotlist(monkeypatch):
    """Non-auth search failures (network hiccup, 5xx) still degrade to the
    hot list."""
    monkeypatch.setenv("ZHIHU_COOKIE", "z_c0=ok")

    async def boom(*a, **k):
        raise RuntimeError("502 bad gateway")
    c = AsyncMock()
    calls = {"n": 0}

    async def get_json(url, **kwargs):
        calls["n"] += 1
        if "search" in url:
            raise RuntimeError("502")
        return {"data": [{"target": {"id": 7, "title": "热榜问题",
                                      "follower_count": 5, "answer_count": 1}}]}
    c.get_json = AsyncMock(side_effect=get_json)
    set_client(c)
    rows = await get_source("zhihu").fetch("人工智能", 30, 10)
    assert rows and rows[0].title == "热榜问题"


@pytest.mark.asyncio
async def test_zhihu_rejected_cookie_stops_with_notice(monkeypatch):
    """A REJECTED cookie (401/403) stops the source with a notice — hot-list
    is skipped because the WAF poisons the whole client after a bad login
    cookie (verified: even cookie-free hot-list 401s right after)."""
    monkeypatch.setenv("ZHIHU_COOKIE", "z_c0=stale")

    async def fail_search(client, query, limit):
        raise RuntimeError("401 unauthorized")

    monkeypatch.setattr("reach_mcp.sources.zhihu._search", fail_search)
    c = AsyncMock()
    set_client(c)
    src = get_source("zhihu")
    rows = await src.fetch("人工智能", 30, 10)
    assert rows == []
    assert src.last_notice and "ZHIHU_COOKIE" in src.last_notice
    c.get_json.assert_not_called()  # hot-list deliberately not attempted


@pytest.mark.asyncio
async def test_zhihu_clean_hotlist_path_clears_notice(monkeypatch):
    monkeypatch.delenv("ZHIHU_COOKIE", raising=False)
    c = AsyncMock()
    c.get_json = AsyncMock(return_value={"data": [
        {"target": {"id": 1, "title": "热榜问题", "follower_count": 5, "answer_count": 1}},
    ]})
    set_client(c)
    src = get_source("zhihu")
    await src.fetch("热榜", 30, 10)
    assert src.last_notice is None  # no cookie configured: nothing to warn about


@pytest.mark.asyncio
async def test_xueqiu_cookieless_sets_notice(monkeypatch):
    monkeypatch.delenv("XUEQIU_COOKIE", raising=False)
    monkeypatch.setattr("reach_mcp.sources.xueqiu._has_cli", lambda: False)
    monkeypatch.setattr(
        "reach_mcp.sources.xueqiu._fetch_via_api",
        AsyncMock(return_value=[]))
    set_client(AsyncMock())
    src = get_source("xueqiu")
    await src.fetch("AAPL", 30, 10)
    assert src.last_notice and "XUEQIU_COOKIE not set" in src.last_notice


@pytest.mark.asyncio
async def test_weibo_visitor_failure_sets_notice(monkeypatch):
    async def no_cookies():
        return None
    monkeypatch.setattr("reach_mcp.sources.weibo._visitor_cookies", no_cookies)
    set_client(AsyncMock())
    src = get_source("weibo")
    rows = await src.fetch("ai", 30, 10)
    assert rows == []
    assert src.last_notice and "visitor" in src.last_notice
