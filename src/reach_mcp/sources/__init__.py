"""Source registry. Importing this package triggers registration of all sources
that have been imported. Source modules are imported by `pipeline.import_all_sources`
via `importlib` so the registry is populated lazily and only once."""
from __future__ import annotations

from reach_mcp.sources.base import (
    SOURCES,
    Item,
    Row,
    Source,
    available_sources,
    get_client,
    get_source,
    list_sources,
    register_source,
    set_client,
)

__all__ = [
    "SOURCES", "Item", "Row", "Source",
    "available_sources", "get_client", "get_source", "list_sources",
    "register_source", "set_client",
]
