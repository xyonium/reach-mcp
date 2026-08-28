from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from reach_mcp.sources import get_source
from reach_mcp.sources.base import Row, set_client


@pytest.mark.asyncio
async def test_bluesky_parses_posts():
    c = AsyncMock()
    c.get_json = AsyncMock(
        return_value={
            "posts": [
                {
                    "uri": "at://did/app.bsky.feed.post/abc",
                    "author": {"handle": "alice.bsky.social"},
                    "record": {"text": "hello world", "createdAt": "2026-07-01T00:00:00Z"},
                    "replyCount": 1,
                    "repostCount": 2,
                    "likeCount": 3,
                }
            ]
        }
    )
    set_client(c)
    rows = await get_source("bluesky").fetch("hello", 30, 10)
    assert rows and rows[0].text == "hello world"
    assert rows[0].engagement["like"] == 3
    assert "alice.bsky.social" in rows[0].url


@pytest.mark.asyncio
async def test_github_parses_repos():
    c = AsyncMock()
    c.get_json = AsyncMock(
        return_value={
            "items": [
                {
                    "id": 1,
                    "full_name": "foo/bar",
                    "name": "bar",
                    "html_url": "https://github.com/foo/bar",
                    "owner": {"login": "foo"},
                    "pushed_at": "2026-07-01T00:00:00Z",
                    "stargazers_count": 42,
                    "forks_count": 7,
                    "description": "a repo",
                }
            ]
        }
    )
    set_client(c)
    rows = await get_source("github").fetch("bar", 30, 10)
    assert rows and rows[0].title == "foo/bar"
    assert rows[0].engagement["stars"] == 42


@pytest.mark.asyncio
async def test_github_uses_token_when_set(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ghp_test")
    c = AsyncMock()
    c.get_json = AsyncMock(return_value={"items": []})
    set_client(c)
    await get_source("github").fetch("q", 30, 10)
    # verify Authorization header was passed
    headers = c.get_json.call_args.kwargs.get("headers", {})
    assert headers.get("Authorization") == "Bearer ghp_test"


@pytest.mark.asyncio
async def test_xiaoyuzhou_parses_episodes(monkeypatch):
    # Search needs the access token; without it the source is gated off.
    monkeypatch.delenv("XIAOYUZHOU_ACCESS_TOKEN", raising=False)
    assert not get_source("xiaoyuzhou").available()
    monkeypatch.setenv("XIAOYUZHOU_ACCESS_TOKEN", "x-jike-token")

    c = AsyncMock()
    # POST /v1/search/create -> one podcast; POST /v1/episode/list -> empty
    c.post_json = AsyncMock(
        side_effect=[
            {"data": {"data": [{"podcast": {"pid": "p1", "title": "Cast"}}]}},
            {"data": {"data": []}},
        ]
    )
    set_client(c)

    # The token is set, so fetch runs; search returns one podcast, episodes empty
    rows = await get_source("xiaoyuzhou").fetch("podcast", 30, 10)
    assert rows == []


@pytest.mark.asyncio
async def test_xiaoyuzhou_with_token_and_episodes(monkeypatch):
    monkeypatch.setenv("XIAOYUZHOU_ACCESS_TOKEN", "x-jike-token")
    c = AsyncMock()
    c.post_json = AsyncMock()
    # search -> one podcast; episode list -> one episode with audio + shownotes
    c.post_json.side_effect = [
        {"data": [{"type": "PODCAST", "pid": "p1", "title": "Cast"}]},
        {
            "data": [
                {
                    "eid": "e1",
                    "title": "Podcast ep",
                    "url": "https://xyz.fm/e1",
                    "pubDate": "2026-07-01",
                    "media": {"source": {"url": "https://media.xyzcdn.net/a.m4a"}},
                    "shownotes": "本期聊了 AI 搜索的架构。",
                    "duration": 3660,
                    "commentCount": 12,
                }
            ]
        },
    ]
    set_client(c)
    rows = await get_source("xiaoyuzhou").fetch("podcast", 30, 10)
    assert rows and rows[0].title == "Podcast ep"
    assert rows[0].author == "Cast"
    # metadata only: shownotes as text, audio_url carried for fetch_content,
    # NO transcription during search
    assert rows[0].text == "本期聊了 AI 搜索的架构。"
    assert rows[0].audio_url == "https://media.xyzcdn.net/a.m4a"
    assert rows[0].duration_min == 61
    assert rows[0].engagement["commentCount"] == 12


@pytest.mark.asyncio
async def test_instagram_uses_apify_when_token_set(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "apify_test")
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    monkeypatch.setattr("reach_mcp.sources.instagram._has_opencli", lambda: False)
    monkeypatch.setattr(
        "reach_mcp.sources.instagram._apify_fetch",
        AsyncMock(
            return_value=[
                Row(
                    source="instagram",
                    id="1",
                    title="T",
                    url="https://instagram.com/p/1",
                    author="u",
                    date=None,
                    engagement={},
                    text="x",
                )
            ]
        ),
    )
    rows = await get_source("instagram").fetch("q", 30, 10)
    assert rows and rows[0].source == "instagram"


@pytest.mark.asyncio
async def test_instagram_gated_without_any_credential(monkeypatch):
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    monkeypatch.setattr("reach_mcp.sources.instagram._has_opencli", lambda: False)
    assert not get_source("instagram").available()


@pytest.mark.asyncio
async def test_pinterest_uses_apify_when_token_set(monkeypatch):
    monkeypatch.setenv("APIFY_API_TOKEN", "apify_test")
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    monkeypatch.setattr("reach_mcp.sources.pinterest._has_opencli", lambda: False)
    monkeypatch.setattr(
        "reach_mcp.sources.pinterest._apify_fetch",
        AsyncMock(
            return_value=[
                Row(
                    source="pinterest",
                    id="1",
                    title="Pin",
                    url="https://pinterest.com/pin/1",
                    author=None,
                    date=None,
                    engagement={},
                    text="x",
                )
            ]
        ),
    )
    rows = await get_source("pinterest").fetch("q", 30, 10)
    assert rows and rows[0].source == "pinterest"


@pytest.mark.asyncio
async def test_pinterest_gated_without_any_credential(monkeypatch):
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    monkeypatch.setattr("reach_mcp.sources.pinterest._has_opencli", lambda: False)
    assert not get_source("pinterest").available()


@pytest.mark.asyncio
async def test_apify_run_actor_sync_http_branch(monkeypatch):
    """run_actor_sync posts to Apify and returns the dataset items list."""
    monkeypatch.setenv("APIFY_API_TOKEN", "apify_test")
    from reach_mcp.sources import _apify

    class _FakeResp:
        status_code = 200
        text = "ok"

        def json(self):
            return [{"id": "x", "text": "hello"}]

    class _FakeClient:
        _client = type("_C", (), {"post": AsyncMock(return_value=_FakeResp())})()

    set_client(_FakeClient())  # type: ignore[arg-type]
    items = await _apify.run_actor_sync("apify/threads-scraper", {"q": "test"})
    assert items == [{"id": "x", "text": "hello"}]
    # verify the POST URL hit the sync endpoint
    post_url = _FakeClient._client.post.call_args.args[0]
    assert "run-sync-get-dataset-items" in post_url
    assert "token=apify_test" in post_url


@pytest.mark.asyncio
async def test_apify_to_row_normalizes_fields():
    """_to_row maps common Apify field aliases."""
    from reach_mcp.sources._apify import _to_row

    row = _to_row(
        {
            "id": "p1",
            "text": "caption text",
            "url": "https://x.com/p1",
            "authorMeta": {"username": "user1"},
            "timestamp": "2026-07-01",
            "likesCount": 5,
            "commentsCount": 2,
            "playCount": 100,
        },
        "tiktok",
    )
    assert row.source == "tiktok"
    assert row.author == "user1"
    assert row.engagement["likes"] == 5
    assert row.engagement["views"] == 100
