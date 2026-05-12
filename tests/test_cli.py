import json

import httpx
import respx
from typer.testing import CliRunner

from hsearch.cli import app
from hsearch.router import providers_for_mode

runner = CliRunner()


def test_help():
    r = runner.invoke(app, ["--help"])
    assert r.exit_code == 0
    assert "search" in r.stdout
    assert "providers" in r.stdout


def test_providers_cmd():
    r = runner.invoke(app, ["providers"])
    assert r.exit_code == 0
    assert "brave" in r.stdout
    assert "serper" in r.stdout


def test_config_cmd():
    r = runner.invoke(app, ["config"])
    assert r.exit_code == 0
    assert "version" in r.stdout


# --- new tests for filters / multi-provider / jsonl / router modes ----------

_BRAVE_BODY = {
    "web": {
        "results": [
            {"url": "https://b.test/1", "title": "B1", "description": "bd1"},
        ]
    }
}
_SERPER_BODY = {
    "organic": [
        {"link": "https://s.test/1", "title": "S1", "snippet": "sd1", "position": 1},
    ]
}


def test_search_lang_flag():
    """--lang should reach Brave as search_lang=zh."""
    captured: dict = {}

    def _brave_handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=_BRAVE_BODY)

    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.search.brave.com/res/v1/web/search").mock(side_effect=_brave_handler)
        r = runner.invoke(
            app, ["search", "x", "-p", "brave", "--lang", "zh", "--no-cache", "-f", "json"]
        )
    assert r.exit_code == 0, r.output
    assert captured["params"].get("search_lang") == "zh"


def test_search_time_word():
    """--time week should be accepted and translated to freshness=pw for Brave."""
    captured: dict = {}

    def _brave_handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=_BRAVE_BODY)

    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.search.brave.com/res/v1/web/search").mock(side_effect=_brave_handler)
        r = runner.invoke(
            app, ["search", "x", "-p", "brave", "--time", "week", "--no-cache", "-f", "json"]
        )
    assert r.exit_code == 0, r.output
    assert captured["params"].get("freshness") == "pw"


def test_tavily_date_range_and_region_filters():
    captured: dict = {}

    def _tavily_handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"results": []})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.tavily.com/search").mock(side_effect=_tavily_handler)
        r = runner.invoke(
            app,
            [
                "search", "x", "-p", "tavily",
                "--time", "2026-05-01..2026-05-12",
                "--region", "US",
                "--no-cache", "-f", "json",
            ],
        )
    assert r.exit_code == 0, r.output
    assert captured["body"]["start_date"] == "2026-05-01"
    assert captured["body"]["end_date"] == "2026-05-12"
    assert captured["body"]["country"] == "united states"


def test_firecrawl_site_filter_uses_native_domains():
    captured: dict = {}

    def _firecrawl_handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, json={"success": True, "data": {"web": []}})

    with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.firecrawl.dev/v2/search").mock(side_effect=_firecrawl_handler)
        r = runner.invoke(
            app,
            ["search", "x", "-p", "firecrawl", "--site", "docs.example.com", "--no-cache", "-f", "json"],
        )
    assert r.exit_code == 0, r.output
    assert captured["body"]["includeDomains"] == ["docs.example.com"]
    assert captured["body"]["query"] == "x"


def test_search_time_invalid():
    r = runner.invoke(
        app, ["search", "x", "-p", "brave", "--time", "invalid", "--no-cache"]
    )
    assert r.exit_code != 0


def test_search_multi_provider():
    """-p brave -p serper should fan out to both endpoints."""
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.search.brave.com/res/v1/web/search").mock(
            return_value=httpx.Response(200, json=_BRAVE_BODY)
        )
        mock.post("https://google.serper.dev/search").mock(
            return_value=httpx.Response(200, json=_SERPER_BODY)
        )
        r = runner.invoke(
            app,
            [
                "search", "x",
                "-p", "brave", "-p", "serper",
                "--no-cache", "-f", "json",
            ],
        )
    assert r.exit_code == 0, r.output
    payload = json.loads(r.stdout)
    assert "meta" in payload
    assert "results" in payload
    urls = {item["url"] for item in payload["results"]}
    assert "https://b.test/1" in urls
    assert "https://s.test/1" in urls


def test_search_jsonl_format():
    """--format jsonl produces one JSON object per line."""
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.search.brave.com/res/v1/web/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "web": {
                        "results": [
                            {"url": "https://b.test/1", "title": "B1", "description": "d1"},
                            {"url": "https://b.test/2", "title": "B2", "description": "d2"},
                        ]
                    }
                },
            )
        )
        r = runner.invoke(
            app, ["search", "x", "-p", "brave", "--no-cache", "-f", "jsonl"]
        )
    assert r.exit_code == 0, r.output
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    assert len(lines) == 2
    for ln in lines:
        obj = json.loads(ln)
        assert "url" in obj and "title" in obj




def test_router_new_modes():
    for m in ("shopping", "video", "images", "places"):
        chosen = providers_for_mode(m)
        assert chosen, f"{m} returned no providers"
        assert chosen[0] == "serper", f"{m} should prefer serper, got {chosen}"


def test_search_agent_preset_defaults_to_json_top_5():
    """--agent should be a compact preset for machine/LLM consumption."""
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.search.brave.com/res/v1/web/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "web": {
                        "results": [
                            {
                                "url": f"https://b.test/{i}",
                                "title": f"B{i}",
                                "description": f"d{i}",
                            }
                            for i in range(1, 8)
                        ]
                    }
                },
            )
        )
        r = runner.invoke(app, ["search", "x", "-p", "brave", "--agent", "--no-cache"])
    assert r.exit_code == 0, r.output
    payload = json.loads(r.stdout)
    assert payload["meta"]["agent_preset"] is True
    assert payload["meta"]["total_results"] == 5
    assert len(payload["results"]) == 5


def test_search_agent_preset_respects_explicit_format_and_top():
    """Explicit --format/--top should override --agent defaults."""
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.search.brave.com/res/v1/web/search").mock(
            return_value=httpx.Response(200, json=_BRAVE_BODY)
        )
        r = runner.invoke(
            app,
            [
                "search", "x", "-p", "brave",
                "--agent", "--top", "1", "--format", "urls", "--no-cache",
            ],
        )
    assert r.exit_code == 0, r.output
    assert r.stdout.strip() == "https://b.test/1"


def test_search_extract_provider_firecrawl():
    """--extract-provider should choose the backend used by --extract-top."""
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.search.brave.com/res/v1/web/search").mock(
            return_value=httpx.Response(200, json=_BRAVE_BODY)
        )
        mock.post("https://api.firecrawl.dev/v2/scrape").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"markdown": "# Firecrawl extracted content"}},
            )
        )
        r = runner.invoke(
            app,
            [
                "search", "x", "-p", "brave",
                "--extract-top", "1", "--extract-provider", "firecrawl",
                "--no-cache", "-f", "json",
            ],
        )
    assert r.exit_code == 0, r.output
    payload = json.loads(r.stdout)
    assert payload["meta"]["extract_provider"] == "firecrawl"
    assert payload["results"][0]["content"] == "# Firecrawl extracted content"


def test_search_extract_provider_invalid_requires_extract_top():
    r = runner.invoke(
        app,
        ["search", "x", "-p", "brave", "--extract-top", "1", "--extract-provider", "bad"],
    )
    assert r.exit_code == 2
    assert "Invalid --extract-provider" in r.output


def test_no_cache_skips_cache_initialization(monkeypatch):
    """--no-cache should still work when the cache directory is unavailable."""
    import hsearch.cli as cli_mod

    class BrokenCache:
        def __init__(self) -> None:
            raise RuntimeError("cache unavailable")

    monkeypatch.setattr(cli_mod, "ResultCache", BrokenCache)

    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.search.brave.com/res/v1/web/search").mock(
            return_value=httpx.Response(200, json=_BRAVE_BODY)
        )
        r = runner.invoke(
            app, ["search", "x", "-p", "brave", "--no-cache", "-f", "json"]
        )
    assert r.exit_code == 0, r.output
    payload = json.loads(r.stdout)
    assert payload["results"][0]["url"] == "https://b.test/1"
