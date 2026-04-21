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

