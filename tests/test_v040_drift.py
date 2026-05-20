"""v0.4.0 provider drift tests."""
from __future__ import annotations

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from hsearch.cli import app
from hsearch.providers.brave import BraveProvider
from hsearch.providers.firecrawl import FirecrawlProvider
from hsearch.providers.jina import JinaProvider
from hsearch.providers.serper import SerperProvider
from hsearch.providers.tavily import TavilyProvider

runner = CliRunner()


@pytest.mark.asyncio
async def test_tavily_include_images_maps_result_image():
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
                        "content": "snippet",
                        "images": [{"url": "https://t.test/image.jpg"}],
                    }
                ]
            },
        )

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(side_effect=_h)
        async with TavilyProvider() as p:
            res = await p.search(
                "q",
                count=1,
                include_images=True,
                include_image_descriptions=True,
            )

    assert captured["body"]["include_images"] is True
    assert captured["body"]["include_image_descriptions"] is True
    assert res[0].image == "https://t.test/image.jpg"


@pytest.mark.asyncio
async def test_brave_place_search():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["params"] = dict(req.url.params)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Blue Bottle Coffee",
                        "url": "https://bluebottlecoffee.com",
                        "postal_address": {"displayAddress": "66 Mint St"},
                        "rating": {"ratingValue": 4.5, "reviewCount": 1250},
                        "categories": ["Coffee"],
                    }
                ]
            },
        )

    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.search.brave.com/res/v1/local/place_search").mock(
            side_effect=_h
        )
        async with BraveProvider() as p:
            res = await p.search(
                "coffee",
                count=1,
                search_type="places",
                location="san francisco ca united states",
            )

    assert captured["params"]["location"] == "san francisco ca united states"
    assert captured["params"]["count"] == "1"
    assert res[0].title == "Blue Bottle Coffee"
    assert "66 Mint St" in res[0].snippet


def test_cli_wires_brave_goggles_flag():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["params"] = dict(req.url.params)
        return httpx.Response(200, json={"web": {"results": []}})

    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.search.brave.com/res/v1/web/search").mock(side_effect=_h)
        r = runner.invoke(
            app,
            [
                "search",
                "q",
                "-p",
                "brave",
                "--goggles",
                "https://example.com/goggle",
                "--no-cache",
                "-f",
                "json",
            ],
        )

    assert r.exit_code == 0, r.output
    assert captured["params"]["goggles"] == "https://example.com/goggle"


@pytest.mark.asyncio
async def test_serper_page_autocorrect_and_patents():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(
            200,
            json={
                "organic": [
                    {
                        "link": "https://patents.test/1",
                        "title": "Patent",
                        "snippet": "A test patent",
                        "publicationDate": "2026-01-01",
                    }
                ]
            },
        )

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://google.serper.dev/patents").mock(side_effect=_h)
        async with SerperProvider() as p:
            res = await p.search(
                "battery",
                count=1,
                search_type="patents",
                page=2,
                autocorrect=False,
            )

    assert captured["body"]["page"] == 2
    assert captured["body"]["autocorrect"] is False
    assert res[0].url == "https://patents.test/1"


@pytest.mark.asyncio
async def test_firecrawl_ignore_invalid_urls_and_scrape_options():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"success": True, "data": {"web": []}})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.firecrawl.dev/v2/search").mock(side_effect=_h)
        async with FirecrawlProvider() as p:
            await p.search(
                "q",
                count=1,
                ignore_invalid_urls=True,
                scrape_timeout=30000,
                wait_for=1000,
            )

    body = captured["body"]
    assert body["ignoreInvalidURLs"] is True
    assert body["scrapeOptions"]["timeout"] == 30000
    assert body["scrapeOptions"]["waitFor"] == 1000


@pytest.mark.asyncio
async def test_jina_new_reader_headers():
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
                wait_for_selector=".ready",
                remove_selector="nav",
                with_generated_alt=True,
            )

    assert captured["headers"]["x-wait-for-selector"] == ".ready"
    assert captured["headers"]["x-remove-selector"] == "nav"
    assert captured["headers"]["x-with-generated-alt"] == "true"
