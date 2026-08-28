"""Environment-based configuration.

Defaults are read at *instantiation* time (via default_factory), not at class
definition, so tests and runtime env changes are honored.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

_DEFAULT_ALLOWED_HOSTS = ("127.0.0.1:*", "localhost:*", "[::1]:*")


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _parse_allowed_hosts() -> tuple[str, ...]:
    raw = os.environ.get("REACH_MCP_ALLOWED_HOSTS")
    if raw is None:
        return _DEFAULT_ALLOWED_HOSTS
    return tuple(h.strip() for h in raw.split(",") if h.strip())


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    transport: str = field(default_factory=lambda: _env("REACH_MCP_TRANSPORT", "http"))
    host: str = field(default_factory=lambda: _env("REACH_MCP_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _env_int("REACH_MCP_PORT", 8765))
    api_key: str = field(default_factory=lambda: _env("REACH_MCP_API_KEY"))
    dns_rebinding_protection: bool = field(
        default_factory=lambda: _env_bool("REACH_MCP_DNS_REBINDING_PROTECTION", True)
    )
    allowed_hosts: tuple[str, ...] = field(default_factory=_parse_allowed_hosts)

    openai_base_url: str = field(
        default_factory=lambda: _env("OPENAI_BASE_URL", "https://api.openai.com/v1")
    )
    openai_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    rerank_model: str = field(
        default_factory=lambda: _env("REACH_MCP_RERANK_MODEL", "gemini-flash-lite")
    )
    brief_model: str = field(
        default_factory=lambda: _env("REACH_MCP_BRIEF_MODEL", "gemini-flash-lite")
    )

    searxng_url: str = field(default_factory=lambda: _env("SEARXNG_URL", "http://searxng:8080"))

    # Whisper transcription (OpenAI-compatible /v1/audio/transcriptions; self-hosted
    # LocalAI etc.). GROQ_API_KEY is NOT used — point WHISPER_BASE_URL at any
    # OpenAI-compatible whisper endpoint. Key may be empty (LocalAI doesn't check).
    whisper_base_url: str = field(
        default_factory=lambda: _env("WHISPER_BASE_URL", "http://gpu.savorcare.com:8080/v1")
    )
    whisper_api_key: str = field(default_factory=lambda: _env("WHISPER_API_KEY"))
    whisper_model: str = field(default_factory=lambda: _env("WHISPER_MODEL", "whisper-large"))

    # Optional free-tier monthly-quota credentials (not one-time credits)
    jina_api_key: str = field(default_factory=lambda: _env("JINA_API_KEY"))
    brave_api_key: str = field(default_factory=lambda: _env("BRAVE_API_KEY"))
    apify_api_token: str = field(default_factory=lambda: _env("APIFY_API_TOKEN"))

    source_timeout: int = field(default_factory=lambda: _env_int("REACH_MCP_SOURCE_TIMEOUT", 60))
    request_timeout: int = field(default_factory=lambda: _env_int("REACH_MCP_REQUEST_TIMEOUT", 15))
    min_host_delay: float = field(
        default_factory=lambda: _env_float("REACH_MCP_MIN_HOST_DELAY", 0.5)
    )
    max_retries: int = field(default_factory=lambda: _env_int("REACH_MCP_MAX_RETRIES", 3))


def get_settings() -> Settings:
    return Settings()
