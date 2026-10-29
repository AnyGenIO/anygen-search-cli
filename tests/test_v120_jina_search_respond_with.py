"""v1.2.0 — HSEARCH_JINA_SEARCH_RESPOND_WITH default for s.jina.ai."""
from __future__ import annotations

import asyncio

import httpx
import respx

from hsearch.providers.jina import JinaProvider


def _search(**kw):
    async def go():
        p = JinaProvider()
        try:
            return await p._search("q", count=3, **kw)
        finally:
            await p.aclose()
    return asyncio.run(go())


def _capture(monkeypatch, value, **kw):
    if value is None:
        monkeypatch.delenv("HSEARCH_JINA_SEARCH_RESPOND_WITH", raising=False)
    else:
        monkeypatch.setenv("HSEARCH_JINA_SEARCH_RESPOND_WITH", value)
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post("https://s.jina.ai/").mock(
            return_value=httpx.Response(200, json={"code": 200, "data": [
                {"title": "t", "url": "https://a.example", "description": "d"}]})
        )
        out = _search(**kw)
    assert out and out[0].url == "https://a.example"
    return route.calls.last.request.headers


def test_unset_sends_no_respond_with(monkeypatch):
    assert "x-respond-with" not in _capture(monkeypatch, None)


def test_env_sets_default(monkeypatch):
    assert _capture(monkeypatch, "no-content")["x-respond-with"] == "no-content"


def test_explicit_respond_with_wins(monkeypatch):
    h = _capture(monkeypatch, "no-content", respond_with="markdown")
    assert h["x-respond-with"] == "markdown"
