"""The X source must use its bundled bird-search, not the last30days cache."""

from pathlib import Path

from reach_mcp.sources.x import _BIRD_SEARCH_MJS


def test_bird_search_is_bundled_inside_reach_mcp():
    path = Path(_BIRD_SEARCH_MJS)
    assert path.name == "bird-search.mjs"
    assert path.is_file(), f"bundled bird-search missing: {path}"
    assert "vendor/bird-search" in path.as_posix()

    vendor = path.parent
    for rel in (
        "package.json",
        "LICENSE",
        "lib/cookies.js",
        "lib/twitter-client-base.js",
        "lib/twitter-client-search.js",
        "lib/runtime-query-ids.js",
        "lib/features.json",
        "lib/query-ids.json",
    ):
        assert (vendor / rel).is_file(), f"missing vendored file: {rel}"


def test_bird_search_does_not_point_at_last30days_cache():
    assert "/config/last30days" not in str(_BIRD_SEARCH_MJS)
