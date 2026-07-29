from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from reach_mcp.sources import get_source
from reach_mcp.sources.base import set_client


def _client_returns(payload):
    c = AsyncMock()
    c.get_json = AsyncMock(return_value=payload)
    c.get_text = AsyncMock(return_value=payload if isinstance(payload, str) else json.dumps(payload))
    return c


@pytest.mark.asyncio
async def test_hackernews_parses_hits():
    set_client(_client_returns({"hits": [{
        "objectID": "1", "title": "T", "url": "https://x", "author": "a",
        "points": 5, "num_comments": 2, "created_at": "2026-07-01T00:00:00Z",
    }]}))
    rows = await get_source("hackernews").fetch("q", 30, 10)
    assert rows and rows[0].title == "T" and rows[0].engagement["points"] == 5


@pytest.mark.asyncio
async def test_arxiv_parses_entries():
    atom = ('<feed xmlns="http://www.w3.org/2005/Atom">'
            '<entry><id>http://arxiv.org/abs/1234</id><title>Paper</title>'
            '<summary>abs</summary><published>2026-07-01T00:00:00Z</published>'
            '<author><name>Auth</name></author></entry></feed>')
    set_client(_client_returns(atom))
    rows = await get_source("arxiv").fetch("q", 30, 10)
    assert rows and rows[0].title == "Paper" and rows[0].url.endswith("1234")


@pytest.mark.asyncio
async def test_polymarket_parses_markets():
    set_client(_client_returns([{
        "id": "1", "question": "Will X?", "slug": "will-x",
        "volume": "1000", "outcomePrices": '["0.6","0.4"]',
        "endDate": "2026-08-01T00:00:00Z",
    }]))
    rows = await get_source("polymarket").fetch("q", 30, 10)
    assert rows and "Will X?" in rows[0].title and rows[0].engagement["volume"] == 1000.0


@pytest.mark.asyncio
async def test_stocktwits_parses_messages():
    set_client(_client_returns({"messages": [{
        "id": 1, "body": "bullish", "created_at": "2026-07-01T00:00:00Z",
        "user": {"username": "u"},
    }]}))
    rows = await get_source("stocktwits").fetch("AAPL", 30, 10)
    assert rows and rows[0].text == "bullish"
