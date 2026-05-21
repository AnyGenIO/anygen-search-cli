"""Tests for v0.6.0 improvements: RRF ranking, SERP features, fallback, URL canon."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from hsearch.dedup import canonicalize_url, dedup_merge
from hsearch.engine import search as engine_search, _aggregate_answers
from hsearch.models import SearchResult
from hsearch.router import providers_for_mode, fallback_providers, FALLBACK_MAP


# ---- URL Canonicalization improvements ----


class TestURLCanonicalization:
    def test_sorts_query_params(self):
        url1 = "https://example.com/page?b=2&a=1"
        url2 = "https://example.com/page?a=1&b=2"
        assert canonicalize_url(url1) == canonicalize_url(url2)

    def test_normalizes_http_to_https(self):
        assert canonicalize_url("http://example.com/page") == canonicalize_url("https://example.com/page")

    def test_strips_trailing_index_html(self):
        assert canonicalize_url("https://example.com/index.html") == "https://example.com/"
        assert canonicalize_url("https://example.com/docs/index.htm") == "https://example.com/docs"

    def test_normalizes_percent_encoding(self):
        url1 = "https://example.com/path%2Fto%2Fpage"
        url2 = "https://example.com/path/to/page"
        assert canonicalize_url(url1) == canonicalize_url(url2)

    def test_strips_www(self):
        assert canonicalize_url("https://www.example.com/page") == canonicalize_url("https://example.com/page")

    def test_strips_utm_and_tracking(self):
        url = "https://example.com/page?utm_source=google&utm_medium=cpc&id=123"
        canonical = canonicalize_url(url)
        assert "utm_source" not in canonical
        assert "id=123" in canonical


# ---- RRF Ranking ----


class TestRRFRanking:
    def test_multi_source_result_ranks_higher(self):
        """A result found by 2 providers should rank above one found by 1."""
        results = [
            SearchResult(url="https://a.com", title="A", provider="tavily", score=0.5),
            SearchResult(url="https://b.com", title="B", provider="tavily", score=0.9),
            SearchResult(url="https://a.com", title="A", provider="brave", score=0.0),
        ]
        merged = dedup_merge(results)
        # a.com appears in both tavily and brave → higher RRF score
        assert merged[0].url == "https://a.com"
        assert len(merged[0].sources) == 2
        assert "tavily" in merged[0].sources
        assert "brave" in merged[0].sources

    def test_rrf_is_scale_invariant(self):
        """RRF should not be distorted by providers with wildly different score ranges."""
        results = [
            # Exa returns low scores (0.2), Tavily returns high (0.95)
            SearchResult(url="https://exa-result.com", title="Exa", provider="exa", score=0.2),
            SearchResult(url="https://tavily-result.com", title="Tavily", provider="tavily", score=0.95),
        ]
        merged = dedup_merge(results)
        # Both should have comparable RRF scores since they're both rank-1 in their provider
        assert len(merged) == 2
        score_diff = abs(merged[0].score - merged[1].score)
        # RRF scores should be very close (both are rank 1 in their provider)
        assert score_diff < 0.01

    def test_negative_provider_scores_dont_break_ranking(self):
        """Old Serper negative scores should not affect RRF ranking."""
        results = [
            SearchResult(url="https://a.com", title="A", provider="serper", score=-0.01),
            SearchResult(url="https://b.com", title="B", provider="tavily", score=0.5),
            SearchResult(url="https://a.com", title="A", provider="tavily", score=0.3),
        ]
        merged = dedup_merge(results)
        # a.com is in 2 sources → should rank higher regardless of the negative score
        assert merged[0].url == "https://a.com"

    def test_rrf_preserves_dedup(self):
        """Duplicate URLs should still be merged."""
        results = [
            SearchResult(url="https://example.com/page", title="Page 1", provider="brave", snippet="short"),
            SearchResult(url="https://www.example.com/page", title="Page Full", provider="tavily", snippet="longer snippet here"),
        ]
        merged = dedup_merge(results)
        assert len(merged) == 1
        assert "longer snippet here" in merged[0].snippet

    def test_richness_bonus_breaks_ties(self):
        """When RRF scores are identical, richness should break ties."""
        results = [
            SearchResult(url="https://a.com", title="A", provider="tavily", content="full content here"),
            SearchResult(url="https://b.com", title="B", provider="tavily"),
        ]
        merged = dedup_merge(results)
        assert merged[0].url == "https://a.com"


# ---- Serper SERP Features ----


class TestSerperSERPFeatures:
    @respx.mock
    async def test_serper_extracts_answer_box(self, monkeypatch):
        monkeypatch.setenv("SERPER_API_KEY", "test-key")
        respx.post("https://google.serper.dev/search").mock(
            return_value=httpx.Response(200, json={
                "organic": [
                    {"link": "https://example.com", "title": "Example", "snippet": "A result"},
                ],
                "answerBox": {
                    "answer": "42 is the answer to everything",
                    "title": "The Answer",
                    "link": "https://answer.com",
                },
            })
        )
        from hsearch.providers.serper import SerperProvider
        p = SerperProvider()
        async with p:
            results = await p.search("what is the answer")
        assert p._last_answer == "42 is the answer to everything"
        # Answer box should be inserted as a result
        assert any("[Answer]" in r.title for r in results)

    @respx.mock
    async def test_serper_extracts_knowledge_graph(self, monkeypatch):
        monkeypatch.setenv("SERPER_API_KEY", "test-key")
        respx.post("https://google.serper.dev/search").mock(
            return_value=httpx.Response(200, json={
                "organic": [
                    {"link": "https://example.com", "title": "Example", "snippet": "A result"},
                ],
                "knowledgeGraph": {
                    "title": "Python",
                    "type": "Programming Language",
                    "description": "Python is a programming language",
                    "descriptionLink": "https://python.org",
                    "attributes": {"creator": "Guido van Rossum"},
                },
            })
        )
        from hsearch.providers.serper import SerperProvider
        p = SerperProvider()
        async with p:
            results = await p.search("Python programming")
        assert p._last_knowledge_graph is not None
        assert p._last_knowledge_graph["title"] == "Python"
        assert any("[Knowledge]" in r.title for r in results)

    @respx.mock
    async def test_serper_extracts_people_also_ask(self, monkeypatch):
        monkeypatch.setenv("SERPER_API_KEY", "test-key")
        respx.post("https://google.serper.dev/search").mock(
            return_value=httpx.Response(200, json={
                "organic": [
                    {"link": "https://example.com", "title": "Example", "snippet": "A result"},
                ],
                "peopleAlsoAsk": [
                    {"question": "What is Python?", "snippet": "A language", "link": "https://paa.com"},
                    {"question": "Is Python free?", "snippet": "Yes", "link": "https://paa2.com"},
                ],
            })
        )
        from hsearch.providers.serper import SerperProvider
        p = SerperProvider()
        async with p:
            results = await p.search("Python")
        assert p._last_people_also_ask is not None
        assert len(p._last_people_also_ask) == 2
        paa_results = [r for r in results if "[PAA]" in r.title]
        assert len(paa_results) == 2

    @respx.mock
    async def test_serper_extracts_related_searches(self, monkeypatch):
        monkeypatch.setenv("SERPER_API_KEY", "test-key")
        respx.post("https://google.serper.dev/search").mock(
            return_value=httpx.Response(200, json={
                "organic": [
                    {"link": "https://example.com", "title": "Example", "snippet": "A result"},
                ],
                "relatedSearches": [
                    {"query": "python tutorial"},
                    {"query": "python download"},
                ],
            })
        )
        from hsearch.providers.serper import SerperProvider
        p = SerperProvider()
        async with p:
            await p.search("Python")
        assert p._last_related_searches == ["python tutorial", "python download"]

    @respx.mock
    async def test_serper_no_negative_scores(self, monkeypatch):
        monkeypatch.setenv("SERPER_API_KEY", "test-key")
        respx.post("https://google.serper.dev/search").mock(
            return_value=httpx.Response(200, json={
                "organic": [
                    {"link": "https://a.com", "title": "A", "snippet": "First", "position": 1},
                    {"link": "https://b.com", "title": "B", "snippet": "Second", "position": 2},
                ],
            })
        )
        from hsearch.providers.serper import SerperProvider
        p = SerperProvider()
        async with p:
            results = await p.search("test")
        # Scores should NOT be negative (old bug: position * -0.01)
        for r in results:
            assert r.score >= 0.0


# ---- Brave SERP Features ----


class TestBraveSERPFeatures:
    @respx.mock
    async def test_brave_extracts_infobox(self, monkeypatch):
        monkeypatch.setenv("BRAVE_API_KEY", "test-key")
        respx.get("https://api.search.brave.com/res/v1/web/search").mock(
            return_value=httpx.Response(200, json={
                "web": {"results": [
                    {"url": "https://example.com", "title": "Example", "description": "A result"},
                ]},
                "infobox": {
                    "title": "Python",
                    "description": "A programming language",
                    "long_desc": "Python is a high-level programming language",
                    "url": "https://python.org",
                    "website": "https://python.org",
                    "attributes": [
                        {"label": "Creator", "value": "Guido van Rossum"},
                    ],
                },
            })
        )
        from hsearch.providers.brave import BraveProvider
        p = BraveProvider()
        async with p:
            results = await p.search("Python")
        assert any("[Info]" in r.title for r in results)

    @respx.mock
    async def test_brave_extracts_faq(self, monkeypatch):
        monkeypatch.setenv("BRAVE_API_KEY", "test-key")
        respx.get("https://api.search.brave.com/res/v1/web/search").mock(
            return_value=httpx.Response(200, json={
                "web": {"results": [
                    {"url": "https://example.com", "title": "Example", "description": "A result"},
                ]},
                "faq": {
                    "results": [
                        {"question": "What is Python?", "answer": "A language", "url": "https://faq.com"},
                    ],
                },
            })
        )
        from hsearch.providers.brave import BraveProvider
        p = BraveProvider()
        async with p:
            results = await p.search("Python")
        faq_results = [r for r in results if "[FAQ]" in r.title]
        assert len(faq_results) == 1

    @respx.mock
    async def test_brave_extracts_discussions(self, monkeypatch):
        monkeypatch.setenv("BRAVE_API_KEY", "test-key")
        respx.get("https://api.search.brave.com/res/v1/web/search").mock(
            return_value=httpx.Response(200, json={
                "web": {"results": [
                    {"url": "https://example.com", "title": "Example", "description": "A result"},
                ]},
                "discussions": {
                    "results": [
                        {"url": "https://reddit.com/r/python", "title": "Python tips", "description": "Great tips", "forum_name": "r/python"},
                    ],
                },
            })
        )
        from hsearch.providers.brave import BraveProvider
        p = BraveProvider()
        async with p:
            results = await p.search("Python")
        disc_results = [r for r in results if "r/python" in r.title]
        assert len(disc_results) == 1

    @respx.mock
    async def test_brave_extra_snippets_merged(self, monkeypatch):
        monkeypatch.setenv("BRAVE_API_KEY", "test-key")
        respx.get("https://api.search.brave.com/res/v1/web/search").mock(
            return_value=httpx.Response(200, json={
                "web": {"results": [
                    {
                        "url": "https://example.com",
                        "title": "Example",
                        "description": "Main snippet",
                        "extra_snippets": ["Extra info 1", "Extra info 2"],
                    },
                ]},
            })
        )
        from hsearch.providers.brave import BraveProvider
        p = BraveProvider()
        async with p:
            results = await p.search("test")
        assert "Extra info 1" in results[0].snippet
        assert "Extra info 2" in results[0].snippet


# ---- Router Broadening ----


class TestRouterBroadening:
    def test_default_uses_two_providers(self, monkeypatch):
        for key in ["TAVILY_API_KEY", "BRAVE_API_KEY", "SERPER_API_KEY", "EXA_API_KEY"]:
            monkeypatch.setenv(key, "test")
        result = providers_for_mode("default")
        assert len(result) >= 2
        assert "tavily" in result

    def test_news_includes_tavily(self, monkeypatch):
        for key in ["TAVILY_API_KEY", "BRAVE_API_KEY", "SERPER_API_KEY"]:
            monkeypatch.setenv(key, "test")
        result = providers_for_mode("news")
        assert "tavily" in result
        assert "brave" in result
        assert "serper" in result

    def test_academic_includes_serper(self, monkeypatch):
        for key in ["EXA_API_KEY", "SERPER_API_KEY"]:
            monkeypatch.setenv(key, "test")
        result = providers_for_mode("academic")
        assert "exa" in result
        assert "serper" in result

    def test_code_includes_serper(self, monkeypatch):
        for key in ["EXA_API_KEY", "BRAVE_API_KEY", "SERPER_API_KEY"]:
            monkeypatch.setenv(key, "test")
        result = providers_for_mode("code")
        assert "serper" in result


# ---- Fallback Chains ----


class TestFallbackChains:
    def test_fallback_map_exists_for_all_providers(self):
        for prov in ["tavily", "brave", "serper", "exa", "firecrawl", "jina"]:
            assert prov in FALLBACK_MAP

    def test_fallback_returns_configured_only(self, monkeypatch):
        monkeypatch.setenv("BRAVE_API_KEY", "test")
        monkeypatch.setenv("SERPER_API_KEY", "test")
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        fb = fallback_providers("tavily")
        assert "brave" in fb
        assert "serper" in fb

    def test_fallback_excludes_unconfigured(self, monkeypatch):
        monkeypatch.delenv("BRAVE_API_KEY", raising=False)
        monkeypatch.delenv("SERPER_API_KEY", raising=False)
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        fb = fallback_providers("exa")
        assert fb == []


# ---- Answer Aggregation ----


class TestAnswerAggregation:
    def test_aggregates_from_multiple_providers(self):
        extras = {
            "tavily": {"answer": "Short Tavily answer"},
            "serper": {"answer": "This is a longer answer from Serper with more detail"},
        }
        result = _aggregate_answers(extras)
        # Should pick the longest answer
        assert result == "This is a longer answer from Serper with more detail"

    def test_single_answer_returned_directly(self):
        extras = {"tavily": {"answer": "Only answer"}}
        assert _aggregate_answers(extras) == "Only answer"

    def test_no_answers_returns_none(self):
        extras = {"tavily": {}, "brave": {"cached": True}}
        assert _aggregate_answers(extras) is None


# ---- Exa highlights default ----


class TestExaHighlightsDefault:
    @respx.mock
    async def test_exa_does_not_request_highlights_by_default(self, monkeypatch):
        monkeypatch.setenv("EXA_API_KEY", "test-key")
        respx.post("https://api.exa.ai/search").mock(
            return_value=httpx.Response(200, json={
                "results": [
                    {"url": "https://example.com", "title": "Test", "score": 0.5},
                ],
            })
        )
        from hsearch.providers.exa import ExaProvider
        p = ExaProvider()
        async with p:
            await p.search("test query")
        req = respx.calls[0].request
        body = json.loads(req.content)
        contents = body.get("contents", {})
        assert "highlights" not in contents

    @respx.mock
    async def test_exa_requests_highlights_when_explicitly_enabled(self, monkeypatch):
        monkeypatch.setenv("EXA_API_KEY", "test-key")
        respx.post("https://api.exa.ai/search").mock(
            return_value=httpx.Response(200, json={
                "results": [
                    {"url": "https://example.com", "title": "Test", "score": 0.5, "highlights": ["key point"]},
                ],
            })
        )
        from hsearch.providers.exa import ExaProvider
        p = ExaProvider()
        async with p:
            await p.search("test query", highlights=True)
        req = respx.calls[0].request
        body = json.loads(req.content)
        assert body["contents"]["highlights"] is True


# ---- Serper siteLinks ----


class TestBraveAnswerPropagation:
    @respx.mock
    async def test_brave_answer_from_summarizer(self, monkeypatch):
        monkeypatch.setenv("BRAVE_API_KEY", "test-key")
        respx.get("https://api.search.brave.com/res/v1/web/search").mock(
            return_value=httpx.Response(200, json={
                "web": {"results": [
                    {"url": "https://example.com", "title": "Example", "description": "A result"},
                ]},
                "summarizer": {
                    "summary": "This is a comprehensive Brave summary answer.",
                },
            })
        )
        from hsearch.providers.brave import BraveProvider
        p = BraveProvider()
        async with p:
            await p.search("test question")
        assert p._last_answer == "This is a comprehensive Brave summary answer."

    @respx.mock
    async def test_brave_answer_from_infobox_fallback(self, monkeypatch):
        monkeypatch.setenv("BRAVE_API_KEY", "test-key")
        respx.get("https://api.search.brave.com/res/v1/web/search").mock(
            return_value=httpx.Response(200, json={
                "web": {"results": [
                    {"url": "https://example.com", "title": "Example", "description": "A result"},
                ]},
                "infobox": {
                    "title": "Python",
                    "description": "A programming language",
                    "long_desc": "Python is a high-level, general-purpose programming language.",
                    "url": "https://python.org",
                },
            })
        )
        from hsearch.providers.brave import BraveProvider
        p = BraveProvider()
        async with p:
            await p.search("Python")
        assert p._last_answer == "Python is a high-level, general-purpose programming language."


class TestCachePolicyModes:
    def test_shopping_has_cache_ttl(self):
        from hsearch.cache_policy import default_cache_ttl
        assert default_cache_ttl("shopping") == 3600

    def test_video_has_cache_ttl(self):
        from hsearch.cache_policy import default_cache_ttl
        assert default_cache_ttl("video") == 7200

    def test_images_has_cache_ttl(self):
        from hsearch.cache_policy import default_cache_ttl
        assert default_cache_ttl("images") == 7200

    def test_places_has_cache_ttl(self):
        from hsearch.cache_policy import default_cache_ttl
        assert default_cache_ttl("places") == 7200


class TestSerperSiteLinks:
    @respx.mock
    async def test_serper_sitelinks_appended_to_snippet(self, monkeypatch):
        monkeypatch.setenv("SERPER_API_KEY", "test-key")
        respx.post("https://google.serper.dev/search").mock(
            return_value=httpx.Response(200, json={
                "organic": [
                    {
                        "link": "https://python.org",
                        "title": "Python",
                        "snippet": "Welcome to Python",
                        "sitelinks": [
                            {"title": "Downloads"},
                            {"title": "Documentation"},
                        ],
                    },
                ],
            })
        )
        from hsearch.providers.serper import SerperProvider
        p = SerperProvider()
        async with p:
            results = await p.search("Python")
        assert "Downloads" in results[0].snippet
        assert "Documentation" in results[0].snippet


# ---- Regression: aggregated answer surfaced in meta for CLI/JSON parity ----


class TestAggregatedAnswerInMeta:
    """v0.6.0 regression: --format json was dropping resp.answer because it
    only lived on SearchResponse.answer, not in meta. Fixed by mirroring
    aggregated_answer into meta['answer']."""

    @respx.mock
    async def test_meta_answer_populated_when_tavily_returns_answer(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "test-key")
        respx.post("https://api.tavily.com/search").mock(
            return_value=httpx.Response(200, json={
                "answer": "The capital of France is Paris.",
                "results": [
                    {"url": "https://example.com", "title": "Paris", "content": "..."},
                ],
            })
        )
        resp = await engine_search(
            "capital of France",
            providers=["tavily"],
            answer=True,
            top=1,
            no_cache=True,
        )
        # Both surfaces must agree
        assert resp.answer == "The capital of France is Paris."
        assert resp.meta.get("answer") == "The capital of France is Paris."

    @respx.mock
    async def test_meta_answer_absent_when_no_provider_returns_one(self, monkeypatch):
        monkeypatch.setenv("TAVILY_API_KEY", "test-key")
        respx.post("https://api.tavily.com/search").mock(
            return_value=httpx.Response(200, json={
                "results": [
                    {"url": "https://example.com", "title": "X", "content": "..."},
                ],
            })
        )
        resp = await engine_search(
            "q",
            providers=["tavily"],
            top=1,
            no_cache=True,
        )
        assert resp.answer is None
        assert "answer" not in resp.meta


# ---- Regression: ground() uses long timeout to avoid 15s default kill ----


class TestGroundLongTimeout:
    """v0.6.0 regression: hsearch ground was using the default 15s search
    timeout for g.jina.ai, which routinely takes 30-90s. Fixed by passing
    an explicit 180s timeout (overridable via HSEARCH_GROUND_TIMEOUT)."""

    @respx.mock
    async def test_ground_passes_explicit_timeout_to_request(self, monkeypatch):
        monkeypatch.setenv("JINA_API_KEY", "test-key")
        from hsearch.providers.jina import JinaProvider, GROUNDING_ENDPOINT

        respx.post(GROUNDING_ENDPOINT).mock(
            return_value=httpx.Response(200, json={
                "data": {"factuality": 0.9, "result": True, "reasoning": "ok", "references": []}
            })
        )
        # Patch the JinaProvider's _request to capture the timeout kwarg
        captured: dict = {}
        async with JinaProvider() as p:
            orig = p._request
            async def spy(*args, **kw):
                captured["timeout"] = kw.get("timeout")
                return await orig(*args, **kw)
            p._request = spy
            await p.ground("test statement")
        # Default should be 180s, override via env
        assert captured["timeout"] == 180.0

    @respx.mock
    async def test_ground_honors_env_override(self, monkeypatch):
        monkeypatch.setenv("JINA_API_KEY", "test-key")
        monkeypatch.setenv("HSEARCH_GROUND_TIMEOUT", "45")
        from hsearch.providers.jina import JinaProvider, GROUNDING_ENDPOINT

        respx.post(GROUNDING_ENDPOINT).mock(
            return_value=httpx.Response(200, json={
                "data": {"factuality": 0.9, "result": True, "reasoning": "ok", "references": []}
            })
        )
        captured: dict = {}
        async with JinaProvider() as p:
            orig = p._request
            async def spy(*args, **kw):
                captured["timeout"] = kw.get("timeout")
                return await orig(*args, **kw)
            p._request = spy
            await p.ground("test")
        assert captured["timeout"] == 45.0


class TestRequestAcceptsTimeoutKwarg:
    """v0.6.0: base.SearchProvider._request now accepts an optional ``timeout``
    kwarg so individual provider calls can override the default."""

    @respx.mock
    async def test_request_passes_timeout_to_httpx(self, monkeypatch):
        monkeypatch.setenv("JINA_API_KEY", "test-key")
        from hsearch.providers.jina import JinaProvider
        from unittest.mock import AsyncMock, MagicMock
        import httpx as _httpx

        async with JinaProvider() as p:
            # Wrap the underlying httpx client to capture the request kwargs
            captured: dict = {}
            orig_request = p._client.request
            async def spy(method, url, **kw):
                captured.update(kw)
                # Return a minimal fake response
                req = _httpx.Request(method, url)
                return _httpx.Response(200, json={"ok": True}, request=req)
            p._client.request = spy
            await p._request("GET", "https://example.com", timeout=42.0)
        assert captured.get("timeout") == 42.0

    @respx.mock
    async def test_request_omits_timeout_when_not_provided(self, monkeypatch):
        monkeypatch.setenv("JINA_API_KEY", "test-key")
        from hsearch.providers.jina import JinaProvider
        import httpx as _httpx

        async with JinaProvider() as p:
            captured: dict = {}
            async def spy(method, url, **kw):
                captured.update(kw)
                req = _httpx.Request(method, url)
                return _httpx.Response(200, json={"ok": True}, request=req)
            p._client.request = spy
            await p._request("GET", "https://example.com")
        # When timeout is not provided, it should not be in kwargs (so the
        # client's default applies)
        assert "timeout" not in captured
