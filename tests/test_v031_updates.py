"""v0.3.1 tests — Firecrawl sources object format, Firecrawl lang fix,
Exa new params (moderation, crawl dates, livecrawlTimeout, author/image),
Tavily finance topic + advanced answer, Brave spellcheck/ui_lang,
Jina new X-* headers, dedup content merging, finance mode.
"""
from __future__ import annotations

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from hsearch.cli import app
from hsearch.dedup import dedup_merge
from hsearch.models import SearchResult
from hsearch.providers.brave import BraveProvider
from hsearch.providers.exa import ExaProvider
from hsearch.providers.firecrawl import FirecrawlProvider
from hsearch.providers.jina import JinaProvider
from hsearch.providers.tavily import TavilyProvider
from hsearch.router import MODE_MAP, providers_for_mode

runner = CliRunner()


# ---------- Firecrawl --------------------------------------------------------


@pytest.mark.asyncio
async def test_firecrawl_sources_object_format():
    """Firecrawl v2 expects sources as [{type: 'web'}] objects."""
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(
            200, json={"success": True, "data": {"web": []}}
        )

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.firecrawl.dev/v2/search").mock(side_effect=_h)
        async with FirecrawlProvider() as p:
            await p.search("q", count=1)
    assert captured["body"]["sources"] == [{"type": "web"}]


@pytest.mark.asyncio
async def test_firecrawl_lang_in_scrape_options():
    """lang should go into scrapeOptions.location.languages, not top-level."""
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(
            200, json={"success": True, "data": {"web": []}}
        )

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.firecrawl.dev/v2/search").mock(side_effect=_h)
        async with FirecrawlProvider() as p:
            await p.search("q", count=1, lang="zh")
    body = captured["body"]
    assert "lang" not in body
    assert body["scrapeOptions"]["location"]["languages"] == ["zh"]


@pytest.mark.asyncio
async def test_firecrawl_timeout_param():
    """Firecrawl timeout should be passed as integer."""
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(
            200, json={"success": True, "data": {"web": []}}
        )

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.firecrawl.dev/v2/search").mock(side_effect=_h)
        async with FirecrawlProvider() as p:
            await p.search("q", count=1, timeout=30000)
    assert captured["body"]["timeout"] == 30000


@pytest.mark.asyncio
async def test_firecrawl_highlights_format():
    """Firecrawl scrapeOptions.formats should include 'highlights' string."""
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(
            200, json={"success": True, "data": {"web": []}}
        )

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.firecrawl.dev/v2/search").mock(side_effect=_h)
        async with FirecrawlProvider() as p:
            await p.search("q", count=1, highlights=True)
    assert "highlights" in captured["body"]["scrapeOptions"]["formats"]


# ---------- Exa --------------------------------------------------------------


@pytest.mark.asyncio
async def test_exa_moderation():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.exa.ai/search").mock(side_effect=_h)
        async with ExaProvider() as p:
            await p.search("q", count=1, moderation=True)
    assert captured["body"]["moderation"] is True


@pytest.mark.asyncio
async def test_exa_crawl_dates():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.exa.ai/search").mock(side_effect=_h)
        async with ExaProvider() as p:
            await p.search(
                "q", count=1,
                start_crawl_date="2025-01-01T00:00:00.000Z",
                end_crawl_date="2026-01-01T00:00:00.000Z",
            )
    assert captured["body"]["startCrawlDate"] == "2025-01-01T00:00:00.000Z"
    assert captured["body"]["endCrawlDate"] == "2026-01-01T00:00:00.000Z"


@pytest.mark.asyncio
async def test_exa_livecrawl_timeout():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.exa.ai/search").mock(side_effect=_h)
        async with ExaProvider() as p:
            await p.search("q", count=1, livecrawl_timeout=20000)
    assert captured["body"]["contents"]["livecrawlTimeout"] == 20000


@pytest.mark.asyncio
async def test_exa_text_verbosity():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.exa.ai/search").mock(side_effect=_h)
        async with ExaProvider() as p:
            await p.search(
                "q", count=1, with_content=True,
                text_verbosity="full", include_html_tags=True,
            )
    text_opts = captured["body"]["contents"]["text"]
    assert text_opts["verbosity"] == "full"
    assert text_opts["includeHtmlTags"] is True


@pytest.mark.asyncio
async def test_exa_extras_links():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.exa.ai/search").mock(side_effect=_h)
        async with ExaProvider() as p:
            await p.search("q", count=1, extras_links=5, extras_image_links=3)
    extras = captured["body"]["contents"]["extras"]
    assert extras["links"] == 5
    assert extras["imageLinks"] == 3


@pytest.mark.asyncio
async def test_exa_author_and_image_in_result():
    def _h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "results": [{
                "url": "https://test.com/1",
                "title": "Test",
                "text": "content",
                "author": "John Doe",
                "image": "https://test.com/img.jpg",
                "favicon": "https://test.com/fav.ico",
            }]
        })

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.exa.ai/search").mock(side_effect=_h)
        async with ExaProvider() as p:
            res = await p.search("q", count=1)
    assert res[0].author == "John Doe"
    assert res[0].image == "https://test.com/img.jpg"
    assert res[0].favicon == "https://test.com/fav.ico"


# ---------- Tavily ------------------------------------------------------------


@pytest.mark.asyncio
async def test_tavily_finance_topic():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(side_effect=_h)
        async with TavilyProvider() as p:
            await p.search("q", count=1, topic="finance")
    assert captured["body"]["topic"] == "finance"


@pytest.mark.asyncio
async def test_tavily_invalid_topic_falls_back():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(side_effect=_h)
        async with TavilyProvider() as p:
            await p.search("q", count=1, topic="invalid_topic")
    assert captured["body"]["topic"] == "general"


@pytest.mark.asyncio
async def test_tavily_advanced_answer():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": [], "answer": "test answer"})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(side_effect=_h)
        async with TavilyProvider() as p:
            await p.search("q", count=1, include_answer="advanced")
    assert captured["body"]["include_answer"] == "advanced"


@pytest.mark.asyncio
async def test_tavily_basic_answer():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(side_effect=_h)
        async with TavilyProvider() as p:
            await p.search("q", count=1, include_answer="basic")
    assert captured["body"]["include_answer"] == "basic"


# ---------- Brave -------------------------------------------------------------


@pytest.mark.asyncio
async def test_brave_spellcheck():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["params"] = dict(req.url.params)
        return httpx.Response(200, json={"web": {"results": []}})

    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.search.brave.com/res/v1/web/search").mock(side_effect=_h)
        async with BraveProvider() as p:
            await p.search("q", count=1, spellcheck=True)
    assert captured["params"]["spellcheck"] == "true"


@pytest.mark.asyncio
async def test_brave_ui_lang():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["params"] = dict(req.url.params)
        return httpx.Response(200, json={"web": {"results": []}})

    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.search.brave.com/res/v1/web/search").mock(side_effect=_h)
        async with BraveProvider() as p:
            await p.search("q", count=1, ui_lang="en-US")
    assert captured["params"]["ui_lang"] == "en-US"


# ---------- Jina --------------------------------------------------------------


@pytest.mark.asyncio
async def test_jina_new_headers():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["headers"] = {k: v for k, v in req.headers.items()}
        return httpx.Response(200, json={"code": 200, "data": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://s.jina.ai/").mock(side_effect=_h)
        async with JinaProvider() as p:
            await p.search(
                "q", count=1,
                jina_timeout=30,
                max_tokens=1000,
                cache_tolerance=600,
                preset="research",
                target_selector=".main-content",
                retain_images="none",
            )
    h = captured["headers"]
    assert h["x-timeout"] == "30"
    assert h["x-max-tokens"] == "1000"
    assert h["x-cache-tolerance"] == "600"
    assert h["x-preset"] == "research"
    assert h["x-target-selector"] == ".main-content"
    assert h["x-retain-images"] == "none"


@pytest.mark.asyncio
async def test_jina_respond_with_header():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["headers"] = {k: v for k, v in req.headers.items()}
        return httpx.Response(200, json={"code": 200, "data": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://s.jina.ai/").mock(side_effect=_h)
        async with JinaProvider() as p:
            await p.search("q", count=1, respond_with="frontmatter")
    assert captured["headers"]["x-respond-with"] == "frontmatter"


# ---------- Dedup -------------------------------------------------------------


def test_dedup_merges_content_and_summary():
    r1 = SearchResult(url="https://test.com/page", title="Short", snippet="s", provider="a")
    r2 = SearchResult(
        url="https://test.com/page", title="Longer Title",
        snippet="longer snippet here", provider="b",
        content="Full page content here", summary="A good summary",
        author="Author Name", image="https://test.com/img.jpg",
    )
    merged = dedup_merge([r1, r2])
    assert len(merged) == 1
    assert merged[0].content == "Full page content here"
    assert merged[0].summary == "A good summary"
    assert merged[0].author == "Author Name"
    assert merged[0].image == "https://test.com/img.jpg"
    assert set(merged[0].sources) == {"a", "b"}


def test_dedup_richness_scoring():
    r1 = SearchResult(
        url="https://rich.com", title="Rich", snippet="s", provider="a",
        content="full", summary="summary", published="2026-01-01",
    )
    r2 = SearchResult(
        url="https://bare.com", title="Bare", snippet="s", provider="b",
    )
    merged = dedup_merge([r1, r2])
    assert merged[0].url == "https://rich.com"
    assert merged[0].score > merged[1].score


# ---------- Router ------------------------------------------------------------


def test_finance_mode_in_router():
    assert "finance" in MODE_MAP
    assert "tavily" in MODE_MAP["finance"]


def test_providers_for_mode_finance():
    prov = providers_for_mode("finance")
    assert len(prov) >= 1


# ---------- CLI ---------------------------------------------------------------


def test_cli_answer_depth_flag():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": [], "answer": "test"})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(side_effect=_h)
        r = runner.invoke(
            app,
            ["search", "q", "-p", "tavily", "--answer", "--answer-depth", "advanced",
             "--no-cache", "-f", "json"],
        )
    assert r.exit_code == 0, r.output
    assert captured["body"]["include_answer"] == "advanced"


def test_cli_moderation_flag():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.exa.ai/search").mock(side_effect=_h)
        r = runner.invoke(
            app,
            ["search", "q", "-p", "exa", "--moderation", "--no-cache", "-f", "json"],
        )
    assert r.exit_code == 0, r.output
    assert captured["body"]["moderation"] is True


def test_cli_mode_finance():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": [], "answer": "finance data"})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(side_effect=_h)
        r = runner.invoke(
            app,
            ["search", "AAPL stock", "--mode", "finance", "-p", "tavily",
             "--no-cache", "-f", "json"],
        )
    assert r.exit_code == 0, r.output
    assert captured["body"]["topic"] == "finance"
    assert captured["body"]["search_depth"] == "advanced"
    assert captured["body"]["include_answer"] == "advanced"


def test_cli_version_031():
    r = runner.invoke(app, ["--version"])
    assert r.exit_code == 0
    assert "0.3.1" in r.output
