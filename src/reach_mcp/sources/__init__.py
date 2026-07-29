"""Source registry with lazy population.

The registry is populated on first access (get_source/list_sources/available_sources)
by importing every module in this package. This keeps tests and entry points simple
— no explicit import_all_sources() needed — while still failing gracefully if one
module errors at import.
"""
from __future__ import annotations

import importlib
import logging
import pkgutil

from reach_mcp.sources.base import (
    SOURCES,
    Item,
    Row,
    Source,
    available_sources as _available_sources,
    get_source as _get_source,
    list_sources as _list_sources,
    register_source,
    set_client,
    get_client,
)

log = logging.getLogger(__name__)
_LOADED = False


def _ensure_loaded() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    import reach_mcp.sources as _pkg
    for mod in pkgutil.iter_modules(_pkg.__path__):
        if mod.name in {"base", "__init__"} or mod.name.startswith("_"):
            continue
        try:
            importlib.import_module(f"reach_mcp.sources.{mod.name}")
        except Exception:  # noqa: BLE001
            log.exception("failed to import source module %s", mod.name)


def get_source(name: str) -> Source:
    _ensure_loaded()
    return _get_source(name)


def list_sources() -> list[Source]:
    _ensure_loaded()
    return _list_sources()


def available_sources() -> list[str]:
    _ensure_loaded()
    return _available_sources()


__all__ = [
    "SOURCES", "Item", "Row", "Source",
    "available_sources", "get_client", "get_source", "list_sources",
    "register_source", "set_client",
]
