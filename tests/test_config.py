from __future__ import annotations

import os

from reach_mcp.config import get_settings


def test_defaults(monkeypatch):
    for k in list(os.environ):
        if k.startswith("REACH_MCP_") or k in {"OPENAI_BASE_URL", "OPENAI_API_KEY"}:
            monkeypatch.delenv(k, raising=False)
    s = get_settings()
    assert s.transport == "http"
    assert s.port == 8765
    assert s.rerank_model == "gemini-flash-lite"
    assert s.brief_model == "gemini-flash-lite"
    assert s.openai_base_url == "https://api.openai.com/v1"
    assert s.source_timeout == 60
    assert s.request_timeout == 15
    assert s.min_host_delay == 0.5
    assert s.max_retries == 3
    assert "127.0.0.1:*" in s.allowed_hosts


def test_allowed_hosts_override(monkeypatch):
    monkeypatch.setenv("REACH_MCP_ALLOWED_HOSTS", "reach-mcp:8765,localhost:8765")
    s = get_settings()
    assert s.allowed_hosts == ("reach-mcp:8765", "localhost:8765")


def test_openai_passthrough(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    s = get_settings()
    assert s.openai_base_url == "https://gw.example.com/v1"
    assert s.openai_api_key == "sk-test"
