from __future__ import annotations

import httpx
import respx

from hsearch.cache_policy import default_cache_ttl, resolve_cache_ttl
from hsearch.engine import search_sync


def test_mode_cache_ttl_map():
    assert default_cache_ttl("realtime") == 300
    assert default_cache_ttl("news") == 300
    assert default_cache_ttl("finance") == 900
    assert default_cache_ttl("answer") == 900
    assert default_cache_ttl("general") == 3600
    assert default_cache_ttl("fast") == 3600
    assert default_cache_ttl("recall") == 3600
    assert default_cache_ttl("code") == 14400
    assert default_cache_ttl("deep") == 14400
    assert default_cache_ttl("academic") == 86400
    assert default_cache_ttl(None) == 3600
    assert default_cache_ttl("unknown") == 3600


def test_explicit_cache_ttl_override_wins():
    assert resolve_cache_ttl("news", explicit_ttl=42) == 42
    assert resolve_cache_ttl("academic", explicit_ttl=0) == 0


def test_engine_meta_reports_adaptive_cache_ttl():
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.search.brave.com/res/v1/web/search").mock(
            return_value=httpx.Response(200, json={"web": {"results": []}})
        )
        resp = search_sync("x", providers=["brave"], mode="news", no_cache=True)

    assert resp.meta["cache_ttl_seconds"] == 300


def test_engine_meta_reports_explicit_cache_ttl_override():
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.search.brave.com/res/v1/web/search").mock(
            return_value=httpx.Response(200, json={"web": {"results": []}})
        )
        resp = search_sync(
            "x",
            providers=["brave"],
            mode="academic",
            cache_ttl=123,
            no_cache=True,
        )

    assert resp.meta["cache_ttl_seconds"] == 123
