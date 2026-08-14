"""v1.0.0 tests — Exa contents.context, research streaming, usage endpoint.

All three were live-probed before implementation (2026-08-14). Notable findings
encoded here:

1. Exa `context` has TWO homes with the same name. Top-level `context: true`
   is silently IGNORED (the 2026-06-25 drift review saw it marked deprecated
   and dropped the whole feature); `contents.context` WORKS. Unbounded it
   returned 168,235 chars, so hsearch always sends maxCharacters.
2. Tavily /research with stream=True returns `text/event-stream` framed as
   OpenAI `chat.completion.chunk` objects; deltas live in
   choices[].delta.content.
3. Only Tavily (/usage) and Firecrawl (/v2/team/credit-usage) publish usage.
   Probed and rejected: Firecrawl /v2/ask (404), /v2/monitors (404),
   Tavily keyless search (401 despite being documented).
"""
from __future__ import annotations

import json

import pytest

from hsearch.engine import _build_extra
from hsearch.providers.exa import (
    _DEFAULT_CONTEXT_CHARS,
    ExaProvider,
)
from hsearch.providers.tavily import TavilyProvider


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _fake_keys(monkeypatch):
    for var in ("EXA_API_KEY", "TAVILY_API_KEY", "FIRECRAWL_API_KEY"):
        monkeypatch.setenv(var, "test-key")


# ---------------------------------------------------------------------------
# 1. Exa contents.context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_goes_under_contents_not_top_level(monkeypatch):
    """The top-level `context` param is deprecated/ignored — must use contents."""
    seen: dict = {}

    async def fake_request(self, method, url, **kwargs):
        seen.update(kwargs.get("json") or {})
        return _Resp({"results": []})

    monkeypatch.setattr(ExaProvider, "_request", fake_request, raising=False)
    p = ExaProvider()
    await p._search("q", count=3, context=True)

    assert "context" not in seen or not isinstance(seen.get("context"), bool), (
        "must NOT send a top-level boolean `context` — Exa ignores it"
    )
    assert "context" in (seen.get("contents") or {}), "context must live under contents"


@pytest.mark.asyncio
async def test_context_is_always_bounded(monkeypatch):
    """Unbounded context returned 168K chars live — always cap it."""
    seen: dict = {}

    async def fake_request(self, method, url, **kwargs):
        seen.update(kwargs.get("json") or {})
        return _Resp({"results": []})

    monkeypatch.setattr(ExaProvider, "_request", fake_request, raising=False)
    p = ExaProvider()
    await p._search("q", count=3, context=True)
    ctx = seen["contents"]["context"]
    assert isinstance(ctx, dict), "context must be an object carrying maxCharacters"
    assert ctx["maxCharacters"] == _DEFAULT_CONTEXT_CHARS


@pytest.mark.asyncio
async def test_context_max_characters_override(monkeypatch):
    seen: dict = {}

    async def fake_request(self, method, url, **kwargs):
        seen.update(kwargs.get("json") or {})
        return _Resp({"results": []})

    monkeypatch.setattr(ExaProvider, "_request", fake_request, raising=False)
    p = ExaProvider()
    await p._search("q", count=3, context=True, context_max_characters=800)
    assert seen["contents"]["context"]["maxCharacters"] == 800


@pytest.mark.asyncio
async def test_bad_context_max_falls_back_to_default(monkeypatch):
    seen: dict = {}

    async def fake_request(self, method, url, **kwargs):
        seen.update(kwargs.get("json") or {})
        return _Resp({"results": []})

    monkeypatch.setattr(ExaProvider, "_request", fake_request, raising=False)
    p = ExaProvider()
    await p._search("q", count=3, context=True, context_max_characters="lots")
    assert seen["contents"]["context"]["maxCharacters"] == _DEFAULT_CONTEXT_CHARS


@pytest.mark.asyncio
async def test_context_captured_from_response(monkeypatch):
    async def fake_request(self, method, url, **kwargs):
        return _Resp({"context": "PRE-ASSEMBLED CONTEXT", "results": []})

    monkeypatch.setattr(ExaProvider, "_request", fake_request, raising=False)
    p = ExaProvider()
    await p._search("q", count=1, context=True)
    assert p._last_context == "PRE-ASSEMBLED CONTEXT"


@pytest.mark.asyncio
async def test_no_context_requested_leaves_last_context_none(monkeypatch):
    seen: dict = {}

    async def fake_request(self, method, url, **kwargs):
        seen.update(kwargs.get("json") or {})
        return _Resp({"results": []})

    monkeypatch.setattr(ExaProvider, "_request", fake_request, raising=False)
    p = ExaProvider()
    await p._search("q", count=1)
    assert p._last_context is None
    # and we must not have asked for it
    assert "context" not in (seen.get("contents") or {})


def test_rag_mode_enables_context():
    extra = _build_extra(mode="rag")
    assert extra["context"] is True
    assert extra["type"] == "auto"


def test_rag_mode_routes_to_exa_only():
    from hsearch.router import MODE_MAP

    assert MODE_MAP["rag"] == ["exa"]


def test_rag_mode_has_cache_ttl():
    from hsearch.cache_policy import default_cache_ttl

    assert default_cache_ttl("rag") == 3600


def test_context_flag_flows_through_build_extra():
    extra = _build_extra(context=True, context_max_characters=500)
    assert extra["context"] is True
    assert extra["context_max_characters"] == 500


def test_search_response_exposes_context_in_meta():
    """CLI --format json must see meta.context (the v0.5.0 answer-drop trap)."""
    from hsearch.engine import SearchResponse

    r = SearchResponse(results=[], context="CTX")
    assert r.to_dict()["meta"]["context"] == "CTX"


def test_search_response_omits_context_when_absent():
    from hsearch.engine import SearchResponse

    assert "context" not in (SearchResponse(results=[]).to_dict().get("meta") or {})


# ---------------------------------------------------------------------------
# 2. Tavily research streaming (SSE)
# ---------------------------------------------------------------------------


class _FakeStream:
    """Minimal async context manager mimicking httpx's streaming response."""

    def __init__(self, lines, status=200):
        self._lines = lines
        self.status_code = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def aiter_lines(self):
        for ln in self._lines:
            yield ln

    async def aread(self):
        return b'{"detail":"boom"}'


def _chunk(text):
    return "data: " + json.dumps(
        {"id": "x", "object": "chat.completion.chunk", "model": "mini",
         "choices": [{"delta": {"content": text}}]}
    )


@pytest.mark.asyncio
async def test_research_stream_yields_deltas(monkeypatch):
    lines = [
        "event: chat.completion.chunk",
        _chunk("Hello "),
        "",
        "event: chat.completion.chunk",
        _chunk("world"),
        "data: [DONE]",
    ]

    p = TavilyProvider()

    class _Client:
        def stream(self, *a, **kw):
            _Client.seen = kw
            return _FakeStream(lines)

    monkeypatch.setattr(p, "_client", _Client(), raising=False)
    out = [piece async for piece in p.research_stream("q", model="mini")]
    assert out == ["Hello ", "world"]
    assert _Client.seen["json"]["stream"] is True
    assert _Client.seen["json"]["model"] == "mini"


@pytest.mark.asyncio
async def test_research_stream_skips_malformed_and_non_data_lines(monkeypatch):
    lines = [
        "event: chat.completion.chunk",
        "data: {not json",
        "data: " + json.dumps({"choices": [{"delta": {}}]}),        # no content
        "data: " + json.dumps({"choices": [{"delta": {"content": ""}}]}),  # empty
        _chunk("ok"),
        ": comment",
    ]
    p = TavilyProvider()

    class _Client:
        def stream(self, *a, **kw):
            return _FakeStream(lines)

    monkeypatch.setattr(p, "_client", _Client(), raising=False)
    out = [piece async for piece in p.research_stream("q")]
    assert out == ["ok"], "malformed/empty frames must be skipped, not crash"


@pytest.mark.asyncio
async def test_research_stream_raises_on_http_error(monkeypatch):
    from hsearch.providers.base import ProviderHTTPError

    p = TavilyProvider()

    class _Client:
        def stream(self, *a, **kw):
            return _FakeStream([], status=429)

    monkeypatch.setattr(p, "_client", _Client(), raising=False)
    with pytest.raises(ProviderHTTPError):
        [piece async for piece in p.research_stream("q")]


@pytest.mark.asyncio
async def test_research_stream_rejects_bad_model(monkeypatch):
    p = TavilyProvider()

    class _Client:
        def stream(self, *a, **kw):
            _Client.seen = kw
            return _FakeStream([_chunk("x")])

    monkeypatch.setattr(p, "_client", _Client(), raising=False)
    [x async for x in p.research_stream("q", model="turbo")]
    assert "model" not in _Client.seen["json"]


def test_research_streaming_exported():
    import hsearch

    assert hasattr(hsearch, "research_streaming")
    assert "research_streaming" in hsearch.__all__


def test_cli_research_has_stream_flag():
    from typer.testing import CliRunner

    from hsearch.cli import app

    r = CliRunner().invoke(app, ["research", "--help"])
    assert r.exit_code == 0
    assert "--stream" in r.output


# ---------------------------------------------------------------------------
# 3. usage endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_account_usage_shapes_both_providers(monkeypatch):
    from hsearch.engine import account_usage

    async def fake_request(self, method, url, **kwargs):
        if "tavily" in url:
            return _Resp({
                "key": {"usage": 611, "search_usage": 611, "crawl_usage": 0,
                        "extract_usage": 0, "map_usage": 0, "research_usage": 0},
                "account": {"current_plan": "Growth", "plan_usage": 10358,
                            "plan_limit": 100000},
            })
        return _Resp({"success": True, "data": {
            "remainingCredits": 1367, "planCredits": 1000,
            "billingPeriodStart": "2026-08-01T23:22:03.636Z",
            "billingPeriodEnd": "2026-09-01T23:22:03.636Z"}})

    from hsearch.providers.firecrawl import FirecrawlProvider

    monkeypatch.setattr(TavilyProvider, "_request", fake_request, raising=False)
    monkeypatch.setattr(FirecrawlProvider, "_request", fake_request, raising=False)

    out = await account_usage()
    assert out["tavily"]["plan"] == "Growth"
    assert out["tavily"]["plan_usage"] == 10358
    assert out["tavily"]["by_capability"]["search"] == 611
    assert "usage" not in out["tavily"]["by_capability"], "suffix must be stripped"
    assert out["firecrawl"]["remaining_credits"] == 1367
    assert out["firecrawl"]["period_end"].startswith("2026-09-01")


@pytest.mark.asyncio
async def test_account_usage_isolates_provider_failures(monkeypatch):
    """One dead endpoint must not break the whole report."""
    from hsearch.engine import account_usage
    from hsearch.providers.firecrawl import FirecrawlProvider

    async def boom(self, method, url, **kwargs):
        raise RuntimeError("network down")

    async def ok(self, method, url, **kwargs):
        return _Resp({"success": True, "data": {"remainingCredits": 5}})

    monkeypatch.setattr(TavilyProvider, "_request", boom, raising=False)
    monkeypatch.setattr(FirecrawlProvider, "_request", ok, raising=False)

    out = await account_usage()
    assert "error" in out["tavily"]
    assert out["firecrawl"]["remaining_credits"] == 5


@pytest.mark.asyncio
async def test_account_usage_reports_unconfigured(monkeypatch):
    from hsearch.engine import account_usage

    for var in ("TAVILY_API_KEY", "FIRECRAWL_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    out = await account_usage()
    assert out["tavily"]["error"] == "not configured"
    assert out["firecrawl"]["error"] == "not configured"


def test_usage_exported_and_registered():
    import hsearch

    for n in ("account_usage", "account_usage_sync"):
        assert hasattr(hsearch, n) and n in hsearch.__all__

    from typer.testing import CliRunner

    from hsearch.cli import app

    r = CliRunner().invoke(app, ["--help"])
    assert r.exit_code == 0
    assert "usage" in r.output


def test_schema_lists_new_surfaces():
    from hsearch.schema import render_schema

    d = json.loads(render_schema())
    names = {t["name"] for t in d["tools"]}
    for expected in ("map", "crawl", "usage"):
        assert expected in names, f"schema missing {expected}"
    search = next(t for t in d["tools"] if t["name"] == "search")
    assert "rag" in search["parameters"]["properties"]["mode"]["enum"]


def test_version_and_pyproject_agree():
    import tomllib
    from pathlib import Path

    from hsearch import __version__

    pp = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with pp.open("rb") as fh:
        declared = tomllib.load(fh)["project"]["version"]
    assert declared == __version__
    assert tuple(int(x) for x in __version__.split(".")[:3]) >= (1, 0, 0)
