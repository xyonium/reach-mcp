"""Source base class, Row/Item dataclasses, and the source registry."""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from reach_mcp.http import PoliteClient


@dataclass
class Row:
    source: str
    id: str
    title: str
    url: str
    author: str | None = None
    date: str | None = None  # ISO-8601 string
    engagement: dict[str, Any] = field(default_factory=dict)
    text: str = ""
    # Optional rich-media metadata (xiaoyuzhou/youtube/bilibili): lets
    # fetch_content transcribe/caption this exact item without re-searching.
    audio_url: str = ""
    duration_min: int = 0


@dataclass
class Item:
    source: str
    id: str
    title: str
    url: str
    author: str | None = None
    date: str | None = None
    engagement: dict[str, Any] = field(default_factory=dict)
    text: str = ""
    score: float = 0.0
    cluster: str | None = None
    audio_url: str = ""
    duration_min: int = 0


class Source(ABC):
    name: str = ""
    description: str = ""
    host: str = ""
    needs_auth: bool = False
    required_env: tuple[str, ...] = ()
    default_days: int = 30
    default_limit: int = 20

    def available(self) -> bool:
        return all(os.environ.get(v, "").strip() for v in self.required_env)

    @abstractmethod
    async def fetch(self, query: str, days: int, limit: int) -> list[Row]:
        ...


SOURCES: dict[str, Source] = {}


def register_source(cls: type[Source]) -> type[Source]:
    inst = cls()
    if not inst.name:
        raise ValueError(f"{cls.__name__} must set .name")
    SOURCES[inst.name] = inst
    return cls


def get_source(name: str) -> Source:
    if name not in SOURCES:
        raise KeyError(name)
    return SOURCES[name]


def list_sources() -> list[Source]:
    return list(SOURCES.values())


def available_sources() -> list[str]:
    return [s.name for s in SOURCES.values() if s.available()]


# --- shared client accessor (set per search call, not import time) ---
_CLIENT: PoliteClient | None = None


def set_client(client: PoliteClient) -> None:
    global _CLIENT
    _CLIENT = client


def get_client() -> PoliteClient:
    if _CLIENT is None:
        raise RuntimeError("PoliteClient not set; call set_client() before fetch()")
    return _CLIENT


# --- per-call snippet length (sources slice text with snip(); set per search) ---
_SNIPPET_LEN = 500


def set_snippet_len(n: int) -> None:
    global _SNIPPET_LEN
    _SNIPPET_LEN = max(0, n)


def snip(text: str) -> str:
    """Truncate source text to the current per-call snippet length.

    Sources call this instead of hardcoding [:500] so the search tool's
    `max_chars_per_item` knob reaches every source without threading a
    parameter through 25 fetch() signatures.
    """
    if _SNIPPET_LEN <= 0:
        return ""
    return text[:_SNIPPET_LEN]
