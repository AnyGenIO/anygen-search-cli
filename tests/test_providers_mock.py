"""Mock-based tests — no real API calls."""
import pytest
import respx
import httpx

from hsearch.providers.brave import BraveProvider
from hsearch.providers.serper import SerperProvider
from hsearch.providers.exa import ExaProvider
from hsearch.providers.tavily import TavilyProvider
from hsearch.providers.firecrawl import FirecrawlProvider
from hsearch.providers.jina import JinaProvider


@pytest.mark.asyncio
async def test_brave():
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.search.brave.com/res/v1/web/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "web": {
                        "results": [
                            {"url": "https://x.test/a", "title": "A", "description": "desc"},
                            {"url": "https://x.test/b", "title": "B", "description": "d2"},
                        ]
                    }
                },
            )
        )
        async with BraveProvider() as p:
            res = await p.search("x", count=2)
        assert len(res) == 2
        assert res[0].provider == "brave"
        assert res[0].url == "https://x.test/a"


@pytest.mark.asyncio
async def test_serper():
    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://google.serper.dev/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "organic": [
                        {"link": "https://y.test/1", "title": "T1", "snippet": "s1", "position": 1},
                    ]
                },
            )
        )
        async with SerperProvider() as p:
            res = await p.search("x", count=5)
        assert res[0].url == "https://y.test/1"
        assert res[0].provider == "serper"


@pytest.mark.asyncio
async def test_exa():
    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.exa.ai/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "url": "https://e.test/p",
                            "title": "Paper",
                            "text": "abstract here",
                            "score": 0.92,
                            "publishedDate": "2024-01-01T00:00:00Z",
                        }
                    ]
                },
            )
        )
        async with ExaProvider() as p:
            res = await p.search("ml", count=3)
        assert res[0].score > 0.9
        assert res[0].published.startswith("2024")


@pytest.mark.asyncio
async def test_tavily():
    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "results": [
                        {"url": "https://t.test/1", "title": "T", "content": "snippet", "score": 0.7},
                    ]
                },
            )
        )
        async with TavilyProvider() as p:
            res = await p.search("foo", count=1)
        assert res[0].provider == "tavily"
        assert res[0].snippet == "snippet"


@pytest.mark.asyncio
async def test_firecrawl_search():
    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.firecrawl.dev/v2/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "success": True,
                    "data": {
                        "web": [
                            {"url": "https://f.test/x", "title": "FX", "description": "d"}
                        ]
                    },
                },
            )
        )
        async with FirecrawlProvider() as p:
            res = await p.search("hello", count=1)
        assert res[0].url == "https://f.test/x"


@pytest.mark.asyncio
async def test_firecrawl_extract():
    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.firecrawl.dev/v2/scrape").mock(
            return_value=httpx.Response(
                200, json={"success": True, "data": {"markdown": "# hi"}}
            )
        )
        async with FirecrawlProvider() as p:
            md = await p.extract("https://example.com")
        assert md == "# hi"


@pytest.mark.asyncio
async def test_jina_search():
    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://s.jina.ai/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "code": 200,
                    "data": [
                        {"url": "https://j.test/1", "title": "J1", "description": "jd"}
                    ],
                },
            )
        )
        async with JinaProvider() as p:
            res = await p.search("hi", count=1)
        assert res[0].url == "https://j.test/1"


@pytest.mark.asyncio
async def test_auth_error():
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.search.brave.com/res/v1/web/search").mock(
            return_value=httpx.Response(401, json={"error": "bad key"})
        )
        from hsearch.providers.base import ProviderAuthError

        async with BraveProvider() as p:
            with pytest.raises(ProviderAuthError):
                await p.search("x", count=1)
