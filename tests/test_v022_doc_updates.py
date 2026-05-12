"""v0.2.2 tests — Tavily 2026-04 params (exact_match, include_favicon, include_usage,
search_depth=fast/ultra-fast), Exa fast/instant types, --mode fast router preset.
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from hsearch.cli import app
from hsearch.providers.exa import ExaProvider
from hsearch.providers.tavily import TavilyProvider
from hsearch.router import MODE_MAP, providers_for_mode

runner = CliRunner()


# ---------- Tavily 2026-04 params ------------------------------------------


@pytest.mark.asyncio
async def test_tavily_exact_match():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(side_effect=_h)
        async with TavilyProvider() as p:
            await p.search('"Hermes Agent"', count=2, exact_match=True)
    assert captured["body"]["exact_match"] is True


@pytest.mark.asyncio
async def test_tavily_include_favicon():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://t.test/1",
                        "title": "T",
                        "content": "snip",
                        "favicon": "https://t.test/favicon.ico",
                    }
                ]
            },
        )

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(side_effect=_h)
        async with TavilyProvider() as p:
            res = await p.search("q", count=1, include_favicon=True)
    assert captured["body"]["include_favicon"] is True
    assert res[0].favicon == "https://t.test/favicon.ico"


@pytest.mark.asyncio
async def test_tavily_include_usage():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(
            200,
            json={
                "results": [],
                "usage": {"credits": 1},
            },
        )

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(side_effect=_h)
        async with TavilyProvider() as p:
            await p.search("q", count=1, include_usage=True)
    assert captured["body"]["include_usage"] is True
    # provider stashes usage for CLI to surface in meta
    async with TavilyProvider() as p2:
        # _last_usage is per-instance; simply assert the field exists post-call
        assert hasattr(p2, "_last_usage")


@pytest.mark.parametrize("depth", ["basic", "advanced", "fast", "ultra-fast"])
@pytest.mark.asyncio
async def test_tavily_search_depth_variants(depth: str):
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(side_effect=_h)
        async with TavilyProvider() as p:
            await p.search("q", count=1, search_depth=depth)
    assert captured["body"]["search_depth"] == depth


@pytest.mark.asyncio
async def test_tavily_invalid_depth_falls_back_to_basic():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(side_effect=_h)
        async with TavilyProvider() as p:
            await p.search("q", count=1, search_depth="bogus")
    # Should silently coerce to a known good depth, not 400 the whole call.
    assert captured["body"]["search_depth"] == "basic"


# ---------- Exa fast / instant types ---------------------------------------


@pytest.mark.parametrize("etype", ["fast", "instant", "auto", "deep-reasoning"])
@pytest.mark.asyncio
async def test_exa_type_passthrough(etype: str):
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.exa.ai/search").mock(side_effect=_h)
        async with ExaProvider() as p:
            await p.search("q", count=1, type=etype)
    assert captured["body"]["type"] == etype


# ---------- router 'fast' mode ---------------------------------------------


def test_router_has_fast_mode():
    assert "fast" in MODE_MAP
    # both providers in priority order
    assert MODE_MAP["fast"][0] == "exa"
    assert "tavily" in MODE_MAP["fast"]


def test_providers_for_mode_fast(monkeypatch):
    # When both keys are configured, fast picks both.
    from hsearch import config as cfg

    monkeypatch.setattr(cfg, "configured_providers", lambda: ["exa", "tavily", "brave"])
    chosen = providers_for_mode("fast")
    assert "exa" in chosen
    assert "tavily" in chosen


# ---------- CLI flag wiring ------------------------------------------------


def test_cli_exact_flag_sets_tavily_exact_match():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(side_effect=_h)
        r = runner.invoke(
            app,
            ["search", '"hermes agent"', "-p", "tavily", "--exact", "--no-cache", "-f", "json"],
        )
    assert r.exit_code == 0, r.output
    assert captured["body"]["exact_match"] is True


def test_cli_depth_flag_sets_tavily_search_depth():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(side_effect=_h)
        r = runner.invoke(
            app,
            ["search", "q", "-p", "tavily", "--depth", "ultra-fast", "--no-cache", "-f", "json"],
        )
    assert r.exit_code == 0, r.output
    assert captured["body"]["search_depth"] == "ultra-fast"


def test_cli_exa_type_flag_sets_exa_type():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.exa.ai/search").mock(side_effect=_h)
        r = runner.invoke(
            app,
            ["search", "q", "-p", "exa", "--exa-type", "instant", "--no-cache", "-f", "json"],
        )
    assert r.exit_code == 0, r.output
    assert captured["body"]["type"] == "instant"


def test_cli_include_favicon_flag():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(side_effect=_h)
        r = runner.invoke(
            app,
            ["search", "q", "-p", "tavily", "--include-favicon", "--no-cache", "-f", "json"],
        )
    assert r.exit_code == 0, r.output
    assert captured["body"]["include_favicon"] is True


def test_cli_include_usage_surfaces_in_meta():
    """--include-usage should request usage from Tavily AND echo it in the JSON meta."""
    def _h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [{"url": "https://t.test/1", "title": "T", "content": "x"}],
                "usage": {"credits": 1},
            },
        )

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(side_effect=_h)
        r = runner.invoke(
            app,
            ["search", "q", "-p", "tavily", "--include-usage", "--no-cache", "-f", "json"],
        )
    assert r.exit_code == 0, r.output
    parsed = json.loads(r.stdout)
    assert "usage" in parsed["meta"]
    assert parsed["meta"]["usage"]["tavily"]["credits"] == 1


def test_cli_mode_fast_chooses_exa_instant_and_tavily_ultrafast(monkeypatch):
    """`--mode fast` should pick exa+tavily and auto-attach the latency presets."""
    from hsearch import config as cfg

    # Pretend only exa+tavily are configured so router gives us both.
    monkeypatch.setattr(cfg, "configured_providers", lambda: ["exa", "tavily"])

    exa_body: dict = {}
    tav_body: dict = {}

    def _exa_h(req: httpx.Request) -> httpx.Response:
        exa_body.update(json.loads(req.content.decode()))
        return httpx.Response(200, json={"results": []})

    def _tav_h(req: httpx.Request) -> httpx.Response:
        tav_body.update(json.loads(req.content.decode()))
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.exa.ai/search").mock(side_effect=_exa_h)
        mock.post("https://api.tavily.com/search").mock(side_effect=_tav_h)
        r = runner.invoke(
            app,
            ["search", "q", "--mode", "fast", "--no-cache", "-f", "json"],
        )
    assert r.exit_code == 0, r.output
    assert exa_body.get("type") == "instant"
    assert tav_body.get("search_depth") == "ultra-fast"


def test_cli_mode_recall_sets_high_recall_params():
    exa_body: dict = {}
    tavily_body: dict = {}
    brave_params: dict = {}
    firecrawl_body: dict = {}
    jina_headers: dict = {}

    def _exa_h(req: httpx.Request) -> httpx.Response:
        exa_body.update(json.loads(req.content.decode()))
        return httpx.Response(200, json={"results": []})

    def _tavily_h(req: httpx.Request) -> httpx.Response:
        tavily_body.update(json.loads(req.content.decode()))
        return httpx.Response(200, json={"results": []})

    def _brave_h(req: httpx.Request) -> httpx.Response:
        brave_params.update(dict(req.url.params))
        return httpx.Response(200, json={"grounding": {"generic": [], "map": []}, "sources": {}})

    def _firecrawl_h(req: httpx.Request) -> httpx.Response:
        firecrawl_body.update(json.loads(req.content.decode()))
        return httpx.Response(200, json={"success": True, "data": {"web": [], "news": []}})

    def _jina_h(req: httpx.Request) -> httpx.Response:
        jina_headers.update({k: v for k, v in req.headers.items()})
        return httpx.Response(200, json={"code": 200, "data": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.exa.ai/search").mock(side_effect=_exa_h)
        mock.post("https://api.tavily.com/search").mock(side_effect=_tavily_h)
        mock.get("https://api.search.brave.com/res/v1/llm/context").mock(side_effect=_brave_h)
        mock.post("https://google.serper.dev/search").mock(
            return_value=httpx.Response(200, json={"organic": []})
        )
        mock.post("https://api.firecrawl.dev/v2/search").mock(side_effect=_firecrawl_h)
        mock.post("https://s.jina.ai/").mock(side_effect=_jina_h)
        r = runner.invoke(
            app,
            ["search", "q", "--mode", "recall", "--top", "2", "--no-cache", "-f", "json"],
        )
    assert r.exit_code == 0, r.output
    assert exa_body["type"] == "deep-reasoning"
    assert exa_body["contents"]["highlights"] is True
    assert "summary" in exa_body["contents"]
    assert tavily_body["search_depth"] == "advanced"
    assert tavily_body["chunks_per_source"] == 3
    assert tavily_body["auto_parameters"] is True
    assert brave_params["context_threshold_mode"] == "lenient"
    assert firecrawl_body["sources"] == ["web", "news"]
    assert {"type": "markdown"} in firecrawl_body["scrapeOptions"]["formats"]
    assert {"type": "summary"} in firecrawl_body["scrapeOptions"]["formats"]
    assert "x-respond-with" not in jina_headers
