"""v0.2 tests — new provider params, retries, CLI flags."""
from __future__ import annotations

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from hsearch.cli import app
from hsearch.providers.brave import BraveProvider
from hsearch.providers.exa import ExaProvider
from hsearch.providers.firecrawl import FirecrawlProvider
from hsearch.providers.jina import JinaProvider
from hsearch.providers.tavily import TavilyProvider

runner = CliRunner()


# ---------- Tavily ----------------------------------------------------------


@pytest.mark.asyncio
async def test_tavily_auto_parameters():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(side_effect=_h)
        async with TavilyProvider() as p:
            await p.search("q", count=3, auto_parameters=True)
    assert captured["body"]["auto_parameters"] is True


@pytest.mark.asyncio
async def test_tavily_chunks_per_source():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(side_effect=_h)
        async with TavilyProvider() as p:
            await p.search("q", count=3, chunks_per_source=5, search_depth="advanced")
    assert captured["body"]["chunks_per_source"] == 5
    assert captured["body"]["search_depth"] == "advanced"


@pytest.mark.asyncio
async def test_tavily_include_raw_content():
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
                        "raw_content": "# full markdown body",
                    }
                ]
            },
        )

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(side_effect=_h)
        async with TavilyProvider() as p:
            res = await p.search("q", count=1, include_raw_content="markdown")
    assert captured["body"]["include_raw_content"] == "markdown"
    assert res[0].content == "# full markdown body"


@pytest.mark.asyncio
async def test_tavily_days():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(side_effect=_h)
        async with TavilyProvider() as p:
            await p.search("q", count=1, days=7, topic="news")
    assert captured["body"]["days"] == 7
    assert captured["body"]["topic"] == "news"


# ---------- Exa -------------------------------------------------------------


@pytest.mark.asyncio
async def test_exa_summary():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://e.test/1",
                        "title": "P1",
                        "text": "abstract",
                        "summary": "This is a 1-sentence summary.",
                    }
                ]
            },
        )

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.exa.ai/search").mock(side_effect=_h)
        async with ExaProvider() as p:
            res = await p.search("q", count=1, summary=True)
    # Payload structure
    assert "summary" in captured["body"]["contents"]
    # Result
    assert res[0].summary == "This is a 1-sentence summary."


@pytest.mark.asyncio
async def test_exa_livecrawl():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.exa.ai/search").mock(side_effect=_h)
        async with ExaProvider() as p:
            await p.search("q", count=1, livecrawl="always")
    assert captured["body"]["contents"]["livecrawl"] == "always"


@pytest.mark.asyncio
async def test_exa_use_autoprompt():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.exa.ai/search").mock(side_effect=_h)
        async with ExaProvider() as p:
            await p.search("q", count=1, use_autoprompt=True, type="deep-reasoning")
    assert captured["body"]["useAutoprompt"] is True
    assert captured["body"]["type"] == "deep-reasoning"


# ---------- Firecrawl -------------------------------------------------------


@pytest.mark.asyncio
async def test_firecrawl_multiple_sources():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "web": [
                        {"url": "https://w.test/1", "title": "W1", "description": "wd"},
                    ],
                    "news": [
                        {"url": "https://n.test/1", "title": "N1", "description": "nd"},
                    ],
                },
            },
        )

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.firecrawl.dev/v2/search").mock(side_effect=_h)
        async with FirecrawlProvider() as p:
            res = await p.search("q", count=10, sources=["web", "news"])
    assert captured["body"]["sources"] == ["web", "news"]
    urls = {r.url for r in res}
    assert "https://w.test/1" in urls
    assert "https://n.test/1" in urls


@pytest.mark.asyncio
async def test_firecrawl_categories():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"success": True, "data": {"web": []}})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.firecrawl.dev/v2/search").mock(side_effect=_h)
        async with FirecrawlProvider() as p:
            await p.search("q", count=1, categories=["github", "research"])
    assert captured["body"]["categories"] == ["github", "research"]


@pytest.mark.asyncio
async def test_firecrawl_summary_format():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "web": [
                        {
                            "url": "https://w.test/1",
                            "title": "W1",
                            "description": "d",
                            "summary": "short summary text",
                        }
                    ]
                },
            },
        )

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.firecrawl.dev/v2/search").mock(side_effect=_h)
        async with FirecrawlProvider() as p:
            res = await p.search("q", count=1, summary=True)
    formats = captured["body"]["scrapeOptions"]["formats"]
    assert {"type": "summary"} in formats
    assert res[0].summary == "short summary text"


# ---------- Brave -----------------------------------------------------------


@pytest.mark.asyncio
async def test_brave_goggles_extra_snippets():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["params"] = dict(req.url.params)
        return httpx.Response(200, json={"web": {"results": []}})

    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.search.brave.com/res/v1/web/search").mock(side_effect=_h)
        async with BraveProvider() as p:
            await p.search(
                "q",
                count=1,
                goggles_id="https://example.com/g.goggle",
                extra_snippets=True,
                result_filter="web,news",
                safesearch="moderate",
                offset=2,
            )
    assert captured["params"]["goggles_id"] == "https://example.com/g.goggle"
    assert captured["params"]["extra_snippets"] == "true"
    assert captured["params"]["result_filter"] == "web,news"
    assert captured["params"]["safesearch"] == "moderate"
    assert captured["params"]["offset"] == "2"


# ---------- Jina ------------------------------------------------------------


@pytest.mark.asyncio
async def test_jina_site_engine_locale_headers():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["headers"] = {k: v for k, v in req.headers.items()}
        return httpx.Response(200, json={"code": 200, "data": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://s.jina.ai/").mock(side_effect=_h)
        async with JinaProvider() as p:
            await p.search(
                "q",
                count=1,
                site="example.com",
                engine="browser",
                locale="zh-CN",
                no_cache=True,
            )
    h = captured["headers"]
    # httpx normalizes header names to lower-case in .headers
    assert h.get("x-site") == "example.com"
    assert h.get("x-engine") == "browser"
    assert h.get("x-locale") == "zh-CN"
    assert h.get("x-no-cache") == "true"


# ---------- retry / backoff -------------------------------------------------


@pytest.mark.asyncio
async def test_retry_429_backoff(monkeypatch):
    """Two 429s, then 200; should succeed via retries."""
    # Make backoff instant.
    import hsearch.providers.base as base_mod
    monkeypatch.setattr(base_mod.SearchProvider, "_backoff_delay", staticmethod(lambda attempt: 0))

    call_count = {"n": 0}

    def _h(req: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] < 3:
            return httpx.Response(429, json={"error": "rate"})
        return httpx.Response(
            200,
            json={"web": {"results": [{"url": "https://b.test/ok", "title": "OK", "description": ""}]}},
        )

    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.search.brave.com/res/v1/web/search").mock(side_effect=_h)
        async with BraveProvider() as p:
            res = await p.search("q", count=1, _retries=3)
    assert call_count["n"] == 3
    assert res and res[0].url == "https://b.test/ok"


@pytest.mark.asyncio
async def test_retry_respects_retry_after(monkeypatch):
    import hsearch.providers.base as base_mod

    sleeps: list[float] = []

    async def _fake_sleep(s: float) -> None:
        sleeps.append(s)

    monkeypatch.setattr(base_mod.asyncio, "sleep", _fake_sleep)

    call_count = {"n": 0}

    def _h(req: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "2"}, json={})
        return httpx.Response(200, json={"web": {"results": []}})

    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.search.brave.com/res/v1/web/search").mock(side_effect=_h)
        async with BraveProvider() as p:
            await p.search("q", count=1, _retries=2)
    assert sleeps and sleeps[0] == 2.0


# ---------- CLI integration -------------------------------------------------


def test_cli_answer_mode():
    """--mode answer should print Tavily's answer in a panel above results."""
    with respx.mock(assert_all_called=False) as mock:
        mock.post("https://api.tavily.com/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "answer": "The capital of France is Paris.",
                    "results": [
                        {
                            "url": "https://wiki.test/paris",
                            "title": "Paris",
                            "content": "Capital of France",
                            "score": 0.9,
                        }
                    ],
                },
            )
        )
        # Brave is also in `answer` route — give it a stub too.
        mock.get("https://api.search.brave.com/res/v1/web/search").mock(
            return_value=httpx.Response(200, json={"web": {"results": []}})
        )
        r = runner.invoke(
            app,
            ["search", "capital of france", "--mode", "answer", "--no-cache", "-f", "markdown"],
        )
    assert r.exit_code == 0, r.output
    assert "Paris" in r.output
    # The markdown answer header
    assert "Answer" in r.output


def test_cli_version_022():
    r = runner.invoke(app, ["--version"])
    assert r.exit_code == 0
    assert "0.2.1" in r.output


def test_cli_summary_flag_passes_through():
    """--summary should add summary={} to Exa contents block."""
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.exa.ai/search").mock(side_effect=_h)
        r = runner.invoke(
            app,
            ["search", "q", "-p", "exa", "--summary", "--no-cache", "-f", "json"],
        )
    assert r.exit_code == 0, r.output
    assert "summary" in captured["body"]["contents"]
