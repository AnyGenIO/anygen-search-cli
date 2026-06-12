"""v0.7.0 — Tavily Research API, Exa company mode/--category, Firecrawl parsers/redactPII."""
from __future__ import annotations

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from hsearch.cli import app
from hsearch.engine import _build_extra, ResearchResponse
from hsearch.providers.firecrawl import FirecrawlProvider, SEARCH_ENDPOINT as FC_SEARCH
from hsearch.providers.tavily import TavilyProvider, RESEARCH_ENDPOINT
from hsearch.router import MODE_MAP, providers_for_mode
from hsearch.cache_policy import default_cache_ttl

runner = CliRunner()


# ---------- Tavily Research provider methods ---------------------------------


@pytest.mark.asyncio
async def test_research_create_payload():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        captured["auth"] = req.headers.get("authorization")
        return httpx.Response(200, json={"request_id": "rid-1", "status": "pending"})

    with respx.mock(assert_all_called=True) as mock:
        mock.post(RESEARCH_ENDPOINT).mock(side_effect=_h)
        async with TavilyProvider() as p:
            data = await p.research_create(
                "What is X?",
                model="mini",
                citation_format="apa",
                output_schema={"type": "object"},
                include_domains=["example.com"],
            )
    assert data["request_id"] == "rid-1"
    body = captured["body"]
    assert body["input"] == "What is X?"
    assert body["model"] == "mini"
    assert body["citation_format"] == "apa"
    assert body["output_schema"] == {"type": "object"}
    assert body["include_domains"] == ["example.com"]
    assert captured["auth"].startswith("Bearer ")


@pytest.mark.asyncio
async def test_research_create_rejects_bad_model_and_citation():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"request_id": "rid-2", "status": "pending"})

    with respx.mock(assert_all_called=True) as mock:
        mock.post(RESEARCH_ENDPOINT).mock(side_effect=_h)
        async with TavilyProvider() as p:
            await p.research_create("q", model="gpt-7", citation_format="harvard")
    # Invalid enum values must not be sent.
    assert "model" not in captured["body"]
    assert "citation_format" not in captured["body"]


@pytest.mark.asyncio
async def test_research_get_polls_by_id():
    def _h(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/research/rid-3")
        return httpx.Response(200, json={"request_id": "rid-3", "status": "completed", "content": "done"})

    with respx.mock(assert_all_called=True) as mock:
        mock.get(f"{RESEARCH_ENDPOINT}/rid-3").mock(side_effect=_h)
        async with TavilyProvider() as p:
            data = await p.research_get("rid-3")
    assert data["status"] == "completed"


@pytest.mark.asyncio
async def test_research_poll_until_completed():
    calls = {"n": 0}

    def _get(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(200, json={"request_id": "rid-4", "status": "in_progress"})
        return httpx.Response(
            200,
            json={
                "request_id": "rid-4",
                "status": "completed",
                "content": "Report body [1]",
                "sources": [{"url": "https://example.com", "title": "Example"}],
            },
        )

    with respx.mock() as mock:
        mock.post(RESEARCH_ENDPOINT).mock(
            return_value=httpx.Response(200, json={"request_id": "rid-4", "status": "pending"})
        )
        mock.get(f"{RESEARCH_ENDPOINT}/rid-4").mock(side_effect=_get)
        async with TavilyProvider() as p:
            data = await p.research("q", poll_interval=0.01, timeout=5.0)
    assert data["status"] == "completed"
    assert data["content"].startswith("Report body")


# ---------- engine.research() -------------------------------------------------


@pytest.mark.asyncio
async def test_engine_research_returns_response(monkeypatch):
    from hsearch import engine

    async def fake_research(self, input_text, **kwargs):
        return {
            "request_id": "rid-5",
            "status": "completed",
            "content": "Synthesized report",
            "sources": [{"url": "https://a.com", "title": "A"}],
            "response_time": 12.5,
        }

    monkeypatch.setattr(TavilyProvider, "research", fake_research)
    resp = await engine.research("question")
    assert isinstance(resp, ResearchResponse)
    assert resp.content == "Synthesized report"
    assert resp.status == "completed"
    assert resp.sources and resp.sources[0]["url"] == "https://a.com"
    assert resp.error is None
    d = resp.to_dict()
    assert d["content"] == "Synthesized report"
    assert d["request_id"] == "rid-5"


@pytest.mark.asyncio
async def test_engine_research_failed_status(monkeypatch):
    from hsearch import engine

    async def fake_research(self, input_text, **kwargs):
        return {"request_id": "rid-6", "status": "failed", "error": "boom"}

    monkeypatch.setattr(TavilyProvider, "research", fake_research)
    resp = await engine.research("question")
    assert resp.error == "boom"
    assert resp.status == "failed"


@pytest.mark.asyncio
async def test_engine_research_timeout(monkeypatch):
    from hsearch import engine

    async def fake_research(self, input_text, **kwargs):
        raise TimeoutError("tavily research task rid-7 still 'in_progress' after 1s")

    monkeypatch.setattr(TavilyProvider, "research", fake_research)
    resp = await engine.research("question", timeout=1.0)
    assert resp.error and "rid-7" in resp.error


def test_sdk_exports_research():
    import hsearch

    assert callable(hsearch.research)
    assert callable(hsearch.research_sync)
    assert hsearch.ResearchResponse is ResearchResponse


# ---------- CLI research command ----------------------------------------------


def test_cli_research_json(monkeypatch):
    from hsearch import cli as cli_mod

    async def fake_engine_research(input_text, **kwargs):
        assert input_text == "my question"
        assert kwargs["model"] == "mini"
        return ResearchResponse(content="The report", status="completed", request_id="rid-8")

    monkeypatch.setattr(cli_mod, "engine_research", fake_engine_research)
    result = runner.invoke(app, ["research", "my question", "-f", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["content"] == "The report"
    assert data["status"] == "completed"


def test_cli_research_error_exit(monkeypatch):
    from hsearch import cli as cli_mod

    async def fake_engine_research(input_text, **kwargs):
        return ResearchResponse(error="timeout after 600s")

    monkeypatch.setattr(cli_mod, "engine_research", fake_engine_research)
    result = runner.invoke(app, ["research", "q"])
    assert result.exit_code == 1


# ---------- company mode + --category ------------------------------------------


def test_company_mode_routes_to_exa():
    assert MODE_MAP["company"] == ["exa"]


def test_company_mode_extra():
    extra = _build_extra(mode="company")
    assert extra["type"] == "auto"
    assert extra["category"] == "company"


def test_category_kwarg_passthrough():
    extra = _build_extra(category="financial report")
    assert extra["category"] == "financial report"


def test_category_does_not_override_academic_mode():
    # academic mode sets category itself; explicit --category wins (last write).
    extra = _build_extra(mode="academic", category="pdf")
    assert extra["category"] == "pdf"


def test_company_mode_cache_ttl():
    assert default_cache_ttl("company") == 14400


def test_cli_search_has_category_flag():
    result = runner.invoke(app, ["search", "--help"])
    assert result.exit_code == 0
    assert "--category" in result.output


# ---------- Firecrawl parsers / redactPII --------------------------------------


@pytest.mark.asyncio
async def test_firecrawl_parsers_and_redact_pii():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"success": True, "data": {"web": []}})

    with respx.mock(assert_all_called=True) as mock:
        mock.post(FC_SEARCH).mock(side_effect=_h)
        async with FirecrawlProvider() as p:
            await p.search("q", count=2, parsers="pdf", redact_pii=True)
    so = captured["body"]["scrapeOptions"]
    assert so["parsers"] == ["pdf"]
    assert so["redactPII"] is True


@pytest.mark.asyncio
async def test_firecrawl_parsers_list_form():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"success": True, "data": {"web": []}})

    with respx.mock(assert_all_called=True) as mock:
        mock.post(FC_SEARCH).mock(side_effect=_h)
        async with FirecrawlProvider() as p:
            await p.search("q", count=2, parsers=["pdf"])
    assert captured["body"]["scrapeOptions"]["parsers"] == ["pdf"]


def test_cli_search_has_firecrawl_v070_flags():
    result = runner.invoke(app, ["search", "--help"])
    assert result.exit_code == 0
    # Rich truncates long flag names in --help tables, so assert on prefixes.
    assert "--firecrawl-parsers" in result.output
    assert "--firecrawl-redact" in result.output


# ---------- version consistency -------------------------------------------------


def test_version_bumped():
    from hsearch import __version__

    assert __version__ == "0.7.0"


def test_cli_version():
    from hsearch import __version__

    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_mcp_research_tool_registered():
    from hsearch import mcp_server

    assert hasattr(mcp_server, "research_tool")


def test_schema_includes_research():
    from hsearch.schema import render_schema

    s = json.loads(render_schema())
    names = [t["name"] for t in s["tools"]]
    assert "research" in names
    search_tool = next(t for t in s["tools"] if t["name"] == "search")
    assert "company" in search_tool["parameters"]["properties"]["mode"]["enum"]
