"""v0.8.0 — Exa Agent API, Tavily Extract endpoint, Firecrawl scrape-control flags."""
from __future__ import annotations

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from hsearch.cli import app
from hsearch.engine import _build_extra, AgentResponse
from hsearch.providers.exa import ExaProvider, AGENT_ENDPOINT
from hsearch.providers.firecrawl import FirecrawlProvider, SEARCH_ENDPOINT as FC_SEARCH
from hsearch.providers.tavily import TavilyProvider, EXTRACT_ENDPOINT
from hsearch.extract import EXTRACT_PROVIDERS

runner = CliRunner()


# ---------- Exa Agent provider methods ----------------------------------------


@pytest.mark.asyncio
async def test_agent_create_payload():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        captured["key"] = req.headers.get("x-api-key")
        return httpx.Response(200, json={"id": "agent_run_1", "status": "running"})

    with respx.mock(assert_all_called=True) as mock:
        mock.post(AGENT_ENDPOINT).mock(side_effect=_h)
        async with ExaProvider() as p:
            data = await p.agent_create(
                "find companies",
                effort="low",
                output_schema={"type": "object"},
            )
    assert data["id"] == "agent_run_1"
    body = captured["body"]
    assert body["query"] == "find companies"
    assert body["effort"] == "low"
    assert body["outputSchema"] == {"type": "object"}
    assert captured["key"]  # x-api-key header set


@pytest.mark.asyncio
async def test_agent_create_rejects_bad_effort():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"id": "agent_run_2", "status": "running"})

    with respx.mock(assert_all_called=True) as mock:
        mock.post(AGENT_ENDPOINT).mock(side_effect=_h)
        async with ExaProvider() as p:
            await p.agent_create("q", effort="turbo")  # invalid enum
    assert "effort" not in captured["body"]


@pytest.mark.asyncio
async def test_agent_create_input_data_and_previous_run():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"id": "agent_run_3", "status": "running"})

    with respx.mock(assert_all_called=True) as mock:
        mock.post(AGENT_ENDPOINT).mock(side_effect=_h)
        async with ExaProvider() as p:
            await p.agent_create(
                "enrich",
                input_data=[{"company": "Apple"}],
                input_exclusion=[{"company": "Apple", "person": "Tim Cook"}],
                previous_run_id="agent_run_prev",
            )
    body = captured["body"]
    assert body["input"]["data"] == [{"company": "Apple"}]
    assert body["input"]["exclusion"] == [{"company": "Apple", "person": "Tim Cook"}]
    assert body["previousRunId"] == "agent_run_prev"


@pytest.mark.asyncio
async def test_agent_get_by_id():
    def _h(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/agent/runs/agent_run_4")
        return httpx.Response(200, json={"id": "agent_run_4", "status": "completed"})

    with respx.mock(assert_all_called=True) as mock:
        mock.get(f"{AGENT_ENDPOINT}/agent_run_4").mock(side_effect=_h)
        async with ExaProvider() as p:
            data = await p.agent_get("agent_run_4")
    assert data["status"] == "completed"


@pytest.mark.asyncio
async def test_agent_run_polls_until_completed():
    calls = {"n": 0}

    def _get(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 2:
            return httpx.Response(200, json={"id": "agent_run_5", "status": "running"})
        return httpx.Response(
            200,
            json={
                "id": "agent_run_5",
                "status": "completed",
                "output": {"text": "Done report", "structured": None, "grounding": [{"x": 1}]},
                "costDollars": {"total": 0.012},
            },
        )

    with respx.mock() as mock:
        mock.post(AGENT_ENDPOINT).mock(
            return_value=httpx.Response(200, json={"id": "agent_run_5", "status": "running"})
        )
        mock.get(f"{AGENT_ENDPOINT}/agent_run_5").mock(side_effect=_get)
        async with ExaProvider() as p:
            data = await p.agent_run("q", poll_interval=0.01, timeout=5.0)
    assert data["status"] == "completed"
    assert data["output"]["text"] == "Done report"


# ---------- engine.agent() ----------------------------------------------------


@pytest.mark.asyncio
async def test_engine_agent_returns_response(monkeypatch):
    from hsearch import engine

    async def fake_agent_run(self, query, **kwargs):
        return {
            "id": "agent_run_6",
            "status": "completed",
            "output": {"text": "Synthesized", "structured": {"a": 1}, "grounding": [1, 2]},
            "costDollars": {"total": 0.02},
            "usage": {"searches": 3},
        }

    monkeypatch.setattr(ExaProvider, "agent_run", fake_agent_run)
    resp = await engine.agent("question")
    assert isinstance(resp, AgentResponse)
    assert resp.text == "Synthesized"
    assert resp.structured == {"a": 1}
    assert resp.grounding == [1, 2]
    assert resp.status == "completed"
    assert resp.run_id == "agent_run_6"
    assert resp.cost == {"total": 0.02}
    assert resp.error is None
    d = resp.to_dict()
    assert d["text"] == "Synthesized"
    assert d["run_id"] == "agent_run_6"


@pytest.mark.asyncio
async def test_engine_agent_failed_status(monkeypatch):
    from hsearch import engine

    async def fake_agent_run(self, query, **kwargs):
        return {"id": "agent_run_7", "status": "failed", "stopReason": "boom"}

    monkeypatch.setattr(ExaProvider, "agent_run", fake_agent_run)
    resp = await engine.agent("question")
    assert resp.status == "failed"
    assert resp.error == "boom"


@pytest.mark.asyncio
async def test_engine_agent_timeout(monkeypatch):
    from hsearch import engine

    async def fake_agent_run(self, query, **kwargs):
        raise TimeoutError("exa agent run agent_run_8 still 'running' after 1s")

    monkeypatch.setattr(ExaProvider, "agent_run", fake_agent_run)
    resp = await engine.agent("question", timeout=1.0)
    assert resp.error and "agent_run_8" in resp.error


def test_sdk_exports_agent():
    import hsearch

    assert callable(hsearch.agent)
    assert callable(hsearch.agent_sync)
    assert hsearch.AgentResponse is AgentResponse


# ---------- CLI agent command -------------------------------------------------


def test_cli_agent_json(monkeypatch):
    from hsearch import cli as cli_mod

    async def fake_engine_agent(query, **kwargs):
        assert query == "find AI infra companies"
        assert kwargs["effort"] == "low"
        return AgentResponse(text="report", status="completed", run_id="agent_run_9")

    monkeypatch.setattr(cli_mod, "engine_agent", fake_engine_agent)
    result = runner.invoke(app, ["agent", "find AI infra companies", "--effort", "low", "-f", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["text"] == "report"
    assert data["status"] == "completed"


def test_cli_agent_error_exit(monkeypatch):
    from hsearch import cli as cli_mod

    async def fake_engine_agent(query, **kwargs):
        return AgentResponse(error="timeout after 600s")

    monkeypatch.setattr(cli_mod, "engine_agent", fake_engine_agent)
    result = runner.invoke(app, ["agent", "q"])
    assert result.exit_code == 1


def test_cli_has_agent_command():
    result = runner.invoke(app, ["agent", "--help"])
    assert result.exit_code == 0
    assert "--effort" in result.output
    assert "--schema-file" in result.output


# ---------- Tavily Extract endpoint -------------------------------------------


@pytest.mark.asyncio
async def test_tavily_extract_payload():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        captured["auth"] = req.headers.get("authorization")
        return httpx.Response(
            200,
            json={"results": [{"url": "https://x.com", "raw_content": "clean text"}], "failed_results": []},
        )

    with respx.mock(assert_all_called=True) as mock:
        mock.post(EXTRACT_ENDPOINT).mock(side_effect=_h)
        async with TavilyProvider() as p:
            content = await p.extract_with_options(
                "https://x.com", extract_depth="advanced", format="markdown", query="satellites"
            )
    assert content == "clean text"
    body = captured["body"]
    assert body["urls"] == ["https://x.com"]
    assert body["extract_depth"] == "advanced"
    assert body["format"] == "markdown"
    assert body["query"] == "satellites"
    assert captured["auth"].startswith("Bearer ")


@pytest.mark.asyncio
async def test_tavily_extract_rejects_bad_enums():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"results": [{"url": "u", "raw_content": "c"}]})

    with respx.mock(assert_all_called=True) as mock:
        mock.post(EXTRACT_ENDPOINT).mock(side_effect=_h)
        async with TavilyProvider() as p:
            await p.extract_with_options("u", extract_depth="ultra", format="pdf")
    # invalid enum values are dropped
    assert "extract_depth" not in captured["body"]
    assert "format" not in captured["body"]


@pytest.mark.asyncio
async def test_tavily_default_extract_hook():
    def _h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{"url": "u", "raw_content": "hook content"}]})

    with respx.mock(assert_all_called=True) as mock:
        mock.post(EXTRACT_ENDPOINT).mock(side_effect=_h)
        async with TavilyProvider() as p:
            content = await p.extract("https://u.com")
    assert content == "hook content"


def test_tavily_is_extract_provider():
    assert "tavily" in EXTRACT_PROVIDERS
    assert TavilyProvider.supports_extract is True


def test_cli_extract_has_tavily_options():
    result = runner.invoke(app, ["extract", "--help"])
    assert result.exit_code == 0
    assert "--query" in result.output
    assert "--extract-depth" in result.output


# ---------- Firecrawl scrape-control flags ------------------------------------


@pytest.mark.asyncio
async def test_firecrawl_scrape_control_flags():
    captured: dict = {}

    def _h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content.decode())
        return httpx.Response(200, json={"success": True, "data": {"web": []}})

    with respx.mock(assert_all_called=True) as mock:
        mock.post(FC_SEARCH).mock(side_effect=_h)
        async with FirecrawlProvider() as p:
            await p.search(
                "q",
                count=2,
                store_in_cache=True,
                lockdown=True,
                zero_data_retention=True,
                skip_tls_verification=True,
            )
    so = captured["body"]["scrapeOptions"]
    assert so["storeInCache"] is True
    assert so["lockdown"] is True
    assert so["zeroDataRetention"] is True
    assert so["skipTlsVerification"] is True


def test_build_extra_firecrawl_scrape_controls():
    extra = _build_extra(
        firecrawl_store_in_cache=True,
        firecrawl_lockdown=False,
        firecrawl_zero_data_retention=True,
        firecrawl_skip_tls_verification=False,
    )
    assert extra["store_in_cache"] is True
    assert extra["lockdown"] is False
    assert extra["zero_data_retention"] is True
    assert extra["skip_tls_verification"] is False


def test_cli_search_has_firecrawl_v080_flags():
    result = runner.invoke(app, ["search", "--help"])
    assert result.exit_code == 0
    # Rich truncates long flag names — assert on truncation-safe prefixes.
    assert "--firecrawl-store-" in result.output
    assert "--firecrawl-lockdo" in result.output
    assert "--firecrawl-zdr" in result.output
    assert "--firecrawl-skip-t" in result.output


# ---------- version + integration --------------------------------------------


def test_version_bumped():
    from hsearch import __version__

    assert __version__ == "0.8.0"


def test_cli_version():
    from hsearch import __version__

    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_mcp_agent_tool_registered():
    from hsearch import mcp_server

    assert hasattr(mcp_server, "agent_tool")


def test_schema_includes_agent():
    from hsearch.schema import render_schema

    s = json.loads(render_schema())
    names = [t["name"] for t in s["tools"]]
    assert "agent" in names
    extract_tool = next(t for t in s["tools"] if t["name"] == "extract")
    assert "tavily" in extract_tool["parameters"]["properties"]["provider"]["enum"]
