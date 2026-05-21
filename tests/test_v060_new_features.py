"""v0.6.0 — New features: Exa /answer, Jina grounding, Exa /findSimilar, --mode context."""
from __future__ import annotations

import json
import os

import httpx
import pytest
import respx
from typer.testing import CliRunner

from hsearch.cli import app
from hsearch.providers.exa import ExaProvider, ANSWER_ENDPOINT, FIND_SIMILAR_ENDPOINT
from hsearch.providers.jina import JinaProvider, GROUNDING_ENDPOINT
from hsearch.router import MODE_MAP, providers_for_mode
from hsearch.engine import _build_extra

runner = CliRunner()


# ---------- Exa /answer -------------------------------------------------------


@pytest.mark.asyncio
async def test_exa_answer_basic():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={
            "answer": "42 is the answer.",
            "citations": [
                {"url": "https://example.com", "title": "Example", "publishedDate": "2025-01-01"},
            ],
            "costDollars": {"total": 0.01},
        })

    with respx.mock(assert_all_called=True) as mock:
        mock.post(ANSWER_ENDPOINT).mock(side_effect=_h)
        async with ExaProvider() as p:
            data = await p.answer("What is the meaning of life?")
    assert captured["body"]["query"] == "What is the meaning of life?"
    assert "text" not in captured["body"]
    assert data["answer"] == "42 is the answer."
    assert len(data["citations"]) == 1
    assert data["citations"][0]["url"] == "https://example.com"


@pytest.mark.asyncio
async def test_exa_answer_with_text():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"answer": "Yes", "citations": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post(ANSWER_ENDPOINT).mock(side_effect=_h)
        async with ExaProvider() as p:
            await p.answer("q", text=True)
    assert captured["body"]["text"] is True


@pytest.mark.asyncio
async def test_exa_answer_with_output_schema():
    captured: dict = {}
    schema = {"type": "object", "properties": {"summary": {"type": "string"}}}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"answer": {"summary": "ok"}, "citations": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post(ANSWER_ENDPOINT).mock(side_effect=_h)
        async with ExaProvider() as p:
            data = await p.answer("q", output_schema=schema)
    assert captured["body"]["outputSchema"] == schema


# ---------- Exa /findSimilar ---------------------------------------------------


@pytest.mark.asyncio
async def test_exa_find_similar_basic():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={
            "results": [
                {"url": "https://similar.com", "title": "Similar", "score": 0.95},
            ]
        })

    with respx.mock(assert_all_called=True) as mock:
        mock.post(FIND_SIMILAR_ENDPOINT).mock(side_effect=_h)
        async with ExaProvider() as p:
            results = await p.find_similar("https://example.com", count=5)
    assert captured["body"]["url"] == "https://example.com"
    assert captured["body"]["numResults"] == 5
    assert len(results) == 1
    assert results[0].url == "https://similar.com"
    assert results[0].score == 0.95


@pytest.mark.asyncio
async def test_exa_find_similar_with_content():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post(FIND_SIMILAR_ENDPOINT).mock(side_effect=_h)
        async with ExaProvider() as p:
            await p.find_similar("https://example.com", with_content=True, highlights=True, summary=True)
    contents = captured["body"]["contents"]
    assert "text" in contents
    assert contents["highlights"] is True
    assert contents["summary"] is True


@pytest.mark.asyncio
async def test_exa_find_similar_with_domains():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post(FIND_SIMILAR_ENDPOINT).mock(side_effect=_h)
        async with ExaProvider() as p:
            await p.find_similar(
                "https://example.com",
                include_domains=["github.com"],
                exclude_domains=["reddit.com"],
                category="company",
            )
    assert captured["body"]["includeDomains"] == ["github.com"]
    assert captured["body"]["excludeDomains"] == ["reddit.com"]
    assert captured["body"]["category"] == "company"


# ---------- Jina Grounding (g.jina.ai) ----------------------------------------


@pytest.mark.asyncio
async def test_jina_ground_basic():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        captured["headers"] = dict(req.headers)
        return httpx.Response(200, json={
            "data": {
                "factuality": 0.85,
                "result": True,
                "reasoning": "The statement is correct.",
                "references": [
                    {"url": "https://wiki.com", "keyQuote": "confirmed", "isSupportive": True},
                ],
            }
        })

    with respx.mock(assert_all_called=True) as mock:
        mock.post(GROUNDING_ENDPOINT).mock(side_effect=_h)
        async with JinaProvider() as p:
            data = await p.ground("The sky is blue")
    assert captured["body"]["statement"] == "The sky is blue"
    assert data["data"]["factuality"] == 0.85
    assert data["data"]["result"] is True


@pytest.mark.asyncio
async def test_jina_ground_no_cache():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(req.headers)
        return httpx.Response(200, json={"data": {"factuality": 0.5, "result": False, "reasoning": "nope", "references": []}})

    with respx.mock(assert_all_called=True) as mock:
        mock.post(GROUNDING_ENDPOINT).mock(side_effect=_h)
        async with JinaProvider() as p:
            await p.ground("test", no_cache=True)
    assert captured["headers"].get("x-no-cache") == "true"


# ---------- Router: --mode context ---------------------------------------------


def test_context_mode_in_mode_map():
    assert "context" in MODE_MAP
    assert "brave" in MODE_MAP["context"]


def test_context_mode_routes_to_brave(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "test-key")
    providers = providers_for_mode("context")
    assert "brave" in providers


def test_context_mode_build_extra():
    extra = _build_extra(mode="context")
    assert extra["search_kind"] == "context"
    assert extra["context_threshold_mode"] == "balanced"


# ---------- Engine: answer/ground/similar --------------------------------------


@pytest.mark.asyncio
async def test_engine_answer():
    from hsearch.engine import answer

    def _h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "answer": "Test answer",
            "citations": [{"url": "https://a.com", "title": "A"}],
        })

    with respx.mock(assert_all_called=True) as mock:
        mock.post(ANSWER_ENDPOINT).mock(side_effect=_h)
        resp = await answer("test query")
    assert resp.answer == "Test answer"
    assert len(resp.citations) == 1
    assert resp.error is None


@pytest.mark.asyncio
async def test_engine_ground():
    from hsearch.engine import ground

    def _h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "data": {
                "factuality": 0.9,
                "result": True,
                "reasoning": "Correct",
                "references": [],
            }
        })

    with respx.mock(assert_all_called=True) as mock:
        mock.post(GROUNDING_ENDPOINT).mock(side_effect=_h)
        resp = await ground("Earth is round")
    assert resp.factuality == 0.9
    assert resp.result is True
    assert resp.reasoning == "Correct"
    assert resp.error is None


@pytest.mark.asyncio
async def test_engine_find_similar():
    from hsearch.engine import find_similar

    def _h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "results": [
                {"url": "https://b.com", "title": "B", "score": 0.8},
            ]
        })

    with respx.mock(assert_all_called=True) as mock:
        mock.post(FIND_SIMILAR_ENDPOINT).mock(side_effect=_h)
        resp = await find_similar("https://example.com", top=5)
    assert len(resp.results) == 1
    assert resp.results[0].url == "https://b.com"
    assert resp.errors == {}


# ---------- AnswerResponse / GroundingResponse serialization -------------------


def test_answer_response_to_dict():
    from hsearch.engine import AnswerResponse
    from hsearch.models import SearchResult

    resp = AnswerResponse(
        answer="Yes",
        citations=[SearchResult(url="https://a.com", title="A")],
        cost={"total": 0.01},
    )
    d = resp.to_dict()
    assert d["answer"] == "Yes"
    assert len(d["citations"]) == 1
    assert d["cost"]["total"] == 0.01


def test_grounding_response_to_dict():
    from hsearch.engine import GroundingResponse

    resp = GroundingResponse(
        factuality=0.8,
        result=True,
        reasoning="Good",
        references=[{"url": "https://a.com", "isSupportive": True}],
    )
    d = resp.to_dict()
    assert d["factuality"] == 0.8
    assert d["result"] is True
    assert d["reasoning"] == "Good"
    assert len(d["references"]) == 1


def test_answer_response_error():
    from hsearch.engine import AnswerResponse

    resp = AnswerResponse(error="provider down")
    d = resp.to_dict()
    assert d["error"] == "provider down"
    assert "answer" not in d


def test_grounding_response_error():
    from hsearch.engine import GroundingResponse

    resp = GroundingResponse(error="no key")
    d = resp.to_dict()
    assert d["error"] == "no key"
    assert "factuality" not in d


# ---------- Schema includes new tools ------------------------------------------


def test_schema_includes_answer():
    from hsearch.schema import SEARCH_SCHEMA

    tool_names = [t["name"] for t in SEARCH_SCHEMA["tools"]]
    assert "answer" in tool_names


def test_schema_includes_ground():
    from hsearch.schema import SEARCH_SCHEMA

    tool_names = [t["name"] for t in SEARCH_SCHEMA["tools"]]
    assert "ground" in tool_names


def test_schema_includes_similar():
    from hsearch.schema import SEARCH_SCHEMA

    tool_names = [t["name"] for t in SEARCH_SCHEMA["tools"]]
    assert "similar" in tool_names


# ---------- Public API exports -------------------------------------------------


def test_public_api_exports():
    import hsearch

    assert hasattr(hsearch, "answer")
    assert hasattr(hsearch, "answer_sync")
    assert hasattr(hsearch, "ground")
    assert hasattr(hsearch, "ground_sync")
    assert hasattr(hsearch, "find_similar")
    assert hasattr(hsearch, "find_similar_sync")
    assert hasattr(hsearch, "AnswerResponse")
    assert hasattr(hsearch, "GroundingResponse")


# ---------- MCP server tools ---------------------------------------------------


def test_mcp_server_registers_new_tools():
    from hsearch.mcp_server import build_server

    try:
        server = build_server()
        tool_names = [t.name for t in server._tool_manager.list_tools()]
        assert "answer" in tool_names
        assert "ground" in tool_names
        assert "similar" in tool_names
    except RuntimeError:
        pytest.skip("MCP not installed")


# ---------- CLI commands -------------------------------------------------------


def test_cli_answer_command_exists():
    result = runner.invoke(app, ["answer", "--help"])
    assert result.exit_code == 0
    assert "answer" in result.output.lower() or "query" in result.output.lower()


def test_cli_ground_command_exists():
    result = runner.invoke(app, ["ground", "--help"])
    assert result.exit_code == 0
    assert "statement" in result.output.lower() or "fact" in result.output.lower()


def test_cli_similar_command_exists():
    result = runner.invoke(app, ["similar", "--help"])
    assert result.exit_code == 0
    assert "url" in result.output.lower()
