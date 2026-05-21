"""v0.5.0 — API alignment tests: Exa deprecations, Firecrawl new params, Tavily new params."""
from __future__ import annotations

import json
import os

import httpx
import pytest
import respx
from typer.testing import CliRunner

from hsearch.cli import app
from hsearch.providers.exa import ExaProvider
from hsearch.providers.firecrawl import FirecrawlProvider
from hsearch.providers.tavily import TavilyProvider

runner = CliRunner()


# ---------- Exa ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_exa_output_schema():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.exa.ai/search").mock(side_effect=_h)
        async with ExaProvider() as p:
            await p.search("q", count=1, output_schema=schema)
    assert captured["body"]["outputSchema"] == schema


@pytest.mark.asyncio
async def test_exa_crawl_dates_not_sent():
    """startCrawlDate/endCrawlDate removed from Exa API on 2026-05-01."""
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.exa.ai/search").mock(side_effect=_h)
        async with ExaProvider() as p:
            await p.search(
                "q", count=1,
                start_crawl_date="2025-01-01",
                end_crawl_date="2026-01-01",
            )
    assert "startCrawlDate" not in captured["body"]
    assert "endCrawlDate" not in captured["body"]


# ---------- Firecrawl ---------------------------------------------------------


@pytest.mark.asyncio
async def test_firecrawl_only_clean_content():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"success": True, "data": {"web": []}})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.firecrawl.dev/v2/search").mock(side_effect=_h)
        async with FirecrawlProvider() as p:
            await p.search("q", count=1, only_clean_content=True)
    assert captured["body"]["scrapeOptions"]["onlyCleanContent"] is True


@pytest.mark.asyncio
async def test_firecrawl_max_age_min_age():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"success": True, "data": {"web": []}})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.firecrawl.dev/v2/search").mock(side_effect=_h)
        async with FirecrawlProvider() as p:
            await p.search("q", count=1, max_age=172800000, min_age=1)
    opts = captured["body"]["scrapeOptions"]
    assert opts["maxAge"] == 172800000
    assert opts["minAge"] == 1


@pytest.mark.asyncio
async def test_firecrawl_block_ads():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"success": True, "data": {"web": []}})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.firecrawl.dev/v2/search").mock(side_effect=_h)
        async with FirecrawlProvider() as p:
            await p.search("q", count=1, block_ads=False)
    assert captured["body"]["scrapeOptions"]["blockAds"] is False


@pytest.mark.asyncio
async def test_firecrawl_proxy():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"success": True, "data": {"web": []}})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.firecrawl.dev/v2/search").mock(side_effect=_h)
        async with FirecrawlProvider() as p:
            await p.search("q", count=1, proxy="enhanced")
    assert captured["body"]["scrapeOptions"]["proxy"] == "enhanced"


@pytest.mark.asyncio
async def test_firecrawl_question_format():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"success": True, "data": {"web": []}})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.firecrawl.dev/v2/search").mock(side_effect=_h)
        async with FirecrawlProvider() as p:
            await p.search("q", count=1, question="What is the main topic?")
    formats = captured["body"]["scrapeOptions"]["formats"]
    q_fmt = [f for f in formats if isinstance(f, dict) and f.get("type") == "question"]
    assert len(q_fmt) == 1
    assert q_fmt[0]["question"] == "What is the main topic?"


@pytest.mark.asyncio
async def test_firecrawl_enterprise():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"success": True, "data": {"web": []}})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.firecrawl.dev/v2/search").mock(side_effect=_h)
        async with FirecrawlProvider() as p:
            await p.search("q", count=1, enterprise="zdr")
    assert captured["body"]["enterprise"] == ["zdr"]


# ---------- Tavily -------------------------------------------------------------


@pytest.mark.asyncio
async def test_tavily_safe_search():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(side_effect=_h)
        async with TavilyProvider() as p:
            await p.search("q", count=1, safe_search=True)
    assert captured["body"]["safe_search"] is True


@pytest.mark.asyncio
async def test_tavily_project_id_header():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(req.headers)
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(side_effect=_h)
        async with TavilyProvider() as p:
            await p.search("q", count=1, project_id="my-project")
    assert captured["headers"]["x-project-id"] == "my-project"


@pytest.mark.asyncio
async def test_tavily_project_id_from_env(monkeypatch):
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(req.headers)
        return httpx.Response(200, json={"results": []})

    monkeypatch.setenv("TAVILY_PROJECT", "env-project")
    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(side_effect=_h)
        async with TavilyProvider() as p:
            await p.search("q", count=1)
    assert captured["headers"]["x-project-id"] == "env-project"


# ---------- User-Agent ---------------------------------------------------------


@pytest.mark.asyncio
async def test_user_agent_matches_version():
    from hsearch import __version__
    from hsearch.providers.base import SearchProvider

    class FakeProvider(SearchProvider):
        name = "fake"
        requires_env = []

        async def _search(self, query, count=10, **kwargs):
            return []

    p = FakeProvider()
    assert f"hsearch/{__version__}" in p._client.headers["user-agent"]
    await p.aclose()


# ---------- CLI ----------------------------------------------------------------


def test_cli_version_050():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.5.0" in result.output
