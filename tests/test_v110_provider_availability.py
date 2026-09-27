"""v1.1.0 — provider availability knobs.

HSEARCH_DISABLED_PROVIDERS / HSEARCH_EXTRACT_PROVIDER / HSEARCH_EXTRACT_FALLBACK.
Motivation: a provider whose key is set but whose domain is blocked on the
local network made every --all / --mode recall fan-out and every default
`extract` wait the full HTTP timeout (~30s) and then fail.
"""
from __future__ import annotations

import asyncio
import json

import httpx
import respx
from typer.testing import CliRunner

from hsearch import config
from hsearch.cli import app
from hsearch.extract import extract_many_detailed, extract_one
from hsearch.router import fallback_providers, providers_for_mode

runner = CliRunner()


def _clear(monkeypatch):
    for k in ("HSEARCH_DISABLED_PROVIDERS", "HSEARCH_EXTRACT_PROVIDER", "HSEARCH_EXTRACT_FALLBACK"):
        monkeypatch.delenv(k, raising=False)


# --- HSEARCH_DISABLED_PROVIDERS ----------------------------------------------

def test_disabled_unset_keeps_all(monkeypatch):
    _clear(monkeypatch)
    assert "jina" in config.configured_providers()
    assert config.disabled_providers() == set()


def test_disabled_filters_auto_routing(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("HSEARCH_DISABLED_PROVIDERS", " Jina , exa ")
    got = config.configured_providers()
    assert "jina" not in got and "exa" not in got
    assert "tavily" in got
    assert "jina" not in providers_for_mode("recall")
    assert "exa" not in providers_for_mode("deep")
    assert "jina" not in fallback_providers("firecrawl")


def test_explicit_provider_still_allowed_when_disabled(monkeypatch):
    """Disabled != removed: `-p jina` must still hit jina (diagnosability)."""
    _clear(monkeypatch)
    monkeypatch.setenv("HSEARCH_DISABLED_PROVIDERS", "jina")
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get("https://r.jina.ai/https://example.com").mock(
            return_value=httpx.Response(200, text="# hello from jina")
        )
        res = runner.invoke(app, ["extract", "https://example.com", "-p", "jina", "-f", "json"])
    assert res.exit_code == 0, res.output
    assert route.called
    assert json.loads(res.output)["results"][0]["provider"] == "jina"


def test_providers_cmd_shows_disabled(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("HSEARCH_DISABLED_PROVIDERS", "jina")
    res = runner.invoke(app, ["providers"])
    assert res.exit_code == 0
    assert "disabled" in res.output


# --- HSEARCH_EXTRACT_PROVIDER -------------------------------------------------

def test_default_extract_provider(monkeypatch):
    _clear(monkeypatch)
    assert config.default_extract_provider() == "jina"
    monkeypatch.setenv("HSEARCH_EXTRACT_PROVIDER", "Tavily")
    assert config.default_extract_provider() == "tavily"


def test_cli_extract_uses_env_default(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("HSEARCH_EXTRACT_PROVIDER", "firecrawl")
    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.firecrawl.dev/v2/scrape").mock(
            return_value=httpx.Response(200, json={"success": True, "data": {"markdown": "# fc"}})
        )
        res = runner.invoke(app, ["extract", "https://example.com", "-f", "json"])
    assert res.exit_code == 0, res.output
    out = json.loads(res.output)
    assert out["meta"]["provider"] == "firecrawl"
    assert out["results"][0]["content"] == "# fc"
    assert "fallback" not in out["meta"]


# --- HSEARCH_EXTRACT_FALLBACK -------------------------------------------------

def test_fallback_chain_defaults_and_filters(monkeypatch):
    _clear(monkeypatch)
    assert config.extract_fallback_chain("jina") == ["firecrawl", "tavily"]
    assert config.extract_fallback_chain("tavily") == ["firecrawl", "jina"]
    monkeypatch.setenv("HSEARCH_DISABLED_PROVIDERS", "jina")
    assert config.extract_fallback_chain("tavily") == ["firecrawl"]
    monkeypatch.setenv("HSEARCH_EXTRACT_FALLBACK", "none")
    assert config.extract_fallback_chain("tavily") == []
    monkeypatch.setenv("HSEARCH_EXTRACT_FALLBACK", "tavily,serper")
    # serper can't extract but chain filtering is by availability; extract layer skips it
    assert config.extract_fallback_chain("jina") == ["tavily", "serper"]


def test_fallback_recovers_failed_url(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("HSEARCH_EXTRACT_FALLBACK", "firecrawl")
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://r.jina.ai/https://example.com").mock(
            side_effect=httpx.ConnectTimeout("blocked")
        )
        mock.post("https://api.firecrawl.dev/v2/scrape").mock(
            return_value=httpx.Response(200, json={"success": True, "data": {"markdown": "# rescued"}})
        )
        res = runner.invoke(app, ["extract", "https://example.com", "-p", "jina", "-f", "json"])
    assert res.exit_code == 0, res.output
    out = json.loads(res.output)
    assert out["meta"]["urls_succeeded"] == 1
    assert out["results"][0]["provider"] == "firecrawl"
    assert out["meta"]["fallback"] == {"https://example.com": "firecrawl"}


def test_no_fallback_flag(monkeypatch):
    _clear(monkeypatch)
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://r.jina.ai/https://example.com").mock(
            side_effect=httpx.ConnectTimeout("blocked")
        )
        res = runner.invoke(
            app, ["extract", "https://example.com", "-p", "jina", "--no-fallback", "-f", "json"]
        )
    out = json.loads(res.output)
    assert out["meta"]["urls_succeeded"] == 0
    err = out["errors"]["https://example.com"]
    assert "timeout" in err.lower()
    assert "firecrawl" not in err  # no fallback attempted


def test_all_failed_reports_every_provider(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("HSEARCH_EXTRACT_FALLBACK", "firecrawl")
    with respx.mock() as mock:
        mock.get("https://r.jina.ai/https://example.com").mock(return_value=httpx.Response(500))
        mock.post("https://api.firecrawl.dev/v2/scrape").mock(return_value=httpx.Response(500))
        u, c, e = asyncio.run(extract_one("https://example.com", provider="jina"))
    assert c is None and e is not None
    assert e.startswith("jina: ") and "firecrawl: " in e


def test_sdk_detailed_reports_served_by(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("HSEARCH_EXTRACT_PROVIDER", "firecrawl")
    with respx.mock() as mock:
        mock.post("https://api.firecrawl.dev/v2/scrape").mock(
            return_value=httpx.Response(200, json={"success": True, "data": {"markdown": "ok"}})
        )
        out = asyncio.run(extract_many_detailed(["https://example.com"]))
    assert out == [("https://example.com", "ok", None, "firecrawl")]


def test_search_all_skips_disabled(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("HSEARCH_DISABLED_PROVIDERS", "brave,serper,exa,firecrawl,jina")
    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(
            return_value=httpx.Response(200, json={"results": [{"url": "https://a.com", "title": "A", "content": "x"}]})
        )
        res = runner.invoke(app, ["search", "q", "--all", "--no-cache", "-f", "json"])
    assert res.exit_code == 0, res.output
    assert json.loads(res.output)["meta"]["providers_queried"] == ["tavily"]
