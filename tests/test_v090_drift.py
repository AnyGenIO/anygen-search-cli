"""v0.9.0 regression tests — 2026-08 provider drift wave.

Covers three live-verified drift findings:

1. Firecrawl `/v2/search` scrapeOptions dropped `highlights` from its formats
   enum again. Both `["highlights"]` and `[{"type": "highlights"}]` return
   HTTP 400 `invalid_union`. Because `--mode recall` sets `highlights=True`
   for Exa, the kwarg leaks into Firecrawl and 400'd the whole Firecrawl leg.
   Provider must drop it silently.

2. Exa July-2026 retired the `research paper` category in favour of
   `publication` (350M-publication index), and deprecated `pdf`/`github`/
   `tweet`. `--mode academic` must emit `publication`, and retired names
   passed by users must be normalized rather than silently degraded.

3. Tavily `/map` + `/crawl` site-traversal endpoints were never wired.
"""
from __future__ import annotations

import pytest

from hsearch.engine import _build_extra, _normalize_traversal
from hsearch.providers.exa import _normalize_category
from hsearch.providers.firecrawl import FirecrawlProvider
from hsearch.providers.tavily import TavilyProvider


# ---------------------------------------------------------------------------
# 1. Firecrawl highlights must never reach the wire
# ---------------------------------------------------------------------------


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def _fake_keys(monkeypatch):
    """Keep these tests hermetic — provider methods gate on is_configured()."""
    for var in ("FIRECRAWL_API_KEY", "EXA_API_KEY", "TAVILY_API_KEY"):
        monkeypatch.setenv(var, "test-key")


@pytest.mark.asyncio
async def test_firecrawl_drops_highlights_format(monkeypatch):
    """highlights is Exa-only; Firecrawl 400s on it. Must be dropped."""
    seen: dict = {}

    async def fake_request(self, method, url, **kwargs):
        seen.update(kwargs.get("json") or {})
        return _Resp({"data": {"web": []}})

    monkeypatch.setattr(FirecrawlProvider, "_request", fake_request, raising=False)
    p = FirecrawlProvider()
    await p._search("q", count=3, highlights=True, highlights_query="anything")

    formats = (seen.get("scrapeOptions") or {}).get("formats") or []
    flat = [f if isinstance(f, str) else f.get("type") for f in formats]
    assert "highlights" not in flat, f"highlights leaked into Firecrawl formats: {formats}"


@pytest.mark.asyncio
async def test_firecrawl_recall_mode_kwargs_do_not_400(monkeypatch):
    """The exact kwarg set --mode recall produces must yield a valid formats list."""
    seen: dict = {}

    async def fake_request(self, method, url, **kwargs):
        seen.update(kwargs.get("json") or {})
        return _Resp({"data": {"web": []}})

    monkeypatch.setattr(FirecrawlProvider, "_request", fake_request, raising=False)
    p = FirecrawlProvider()
    # recall sets highlights (Exa), with_content (Firecrawl), summary, moderation...
    await p._search("q", count=3, highlights=True, with_content=True, summary=True)

    formats = (seen.get("scrapeOptions") or {}).get("formats") or []
    flat = [f if isinstance(f, str) else f.get("type") for f in formats]
    # Only the live-verified valid values may appear.
    valid = {"markdown", "html", "rawHtml", "links", "images", "summary",
             "json", "question", "query", "screenshot"}
    assert set(flat) <= valid, f"invalid Firecrawl format(s): {set(flat) - valid}"
    assert "markdown" in flat and "summary" in flat


@pytest.mark.asyncio
async def test_firecrawl_still_supports_question_format(monkeypatch):
    """The object-shaped `question` format is still valid and must survive."""
    seen: dict = {}

    async def fake_request(self, method, url, **kwargs):
        seen.update(kwargs.get("json") or {})
        return _Resp({"data": {"web": []}})

    monkeypatch.setattr(FirecrawlProvider, "_request", fake_request, raising=False)
    p = FirecrawlProvider()
    await p._search("q", count=2, question="what is the price?")
    formats = (seen.get("scrapeOptions") or {}).get("formats") or []
    assert {"type": "question", "question": "what is the price?"} in formats


# ---------------------------------------------------------------------------
# 2. Exa category drift
# ---------------------------------------------------------------------------


def test_academic_mode_uses_publication_not_research_paper():
    extra = _build_extra(mode="academic")
    assert extra["category"] == "publication", (
        "Exa retired 'research paper' in July 2026; academic mode must send 'publication'"
    )


@pytest.mark.parametrize(
    "given,expected",
    [
        ("research paper", "publication"),
        ("Research Paper", "publication"),
        ("research papers", "publication"),
        ("papers", "publication"),
        ("publication", "publication"),
        ("linkedin profile", "people"),
        # Still-valid categories pass through untouched.
        ("company", "company"),
        ("news", "news"),
        ("people", "people"),
        ("financial report", "financial report"),
        # Deprecated-with-no-successor: passed through as a loose hint.
        ("pdf", "pdf"),
        ("github", "github"),
        # Non-strings are returned as-is.
        (None, None),
        (7, 7),
    ],
)
def test_normalize_category(given, expected):
    assert _normalize_category(given) == expected


@pytest.mark.asyncio
async def test_exa_search_normalizes_category_on_the_wire(monkeypatch):
    seen: dict = {}

    async def fake_request(self, method, url, **kwargs):
        seen.update(kwargs.get("json") or {})
        return _Resp({"results": []})

    from hsearch.providers.exa import ExaProvider

    monkeypatch.setattr(ExaProvider, "_request", fake_request, raising=False)
    p = ExaProvider()
    await p._search("q", count=3, category="research paper")
    assert seen.get("category") == "publication"


@pytest.mark.asyncio
async def test_exa_find_similar_normalizes_category(monkeypatch):
    seen: dict = {}

    async def fake_request(self, method, url, **kwargs):
        seen.update(kwargs.get("json") or {})
        return _Resp({"results": []})

    from hsearch.providers.exa import ExaProvider

    monkeypatch.setattr(ExaProvider, "_request", fake_request, raising=False)
    p = ExaProvider()
    await p.find_similar("https://example.com", count=3, category="research paper")
    assert seen.get("category") == "publication"


# ---------------------------------------------------------------------------
# 3. Tavily /map + /crawl
# ---------------------------------------------------------------------------


def test_normalize_traversal_map_shape():
    """/map returns results: list[str]."""
    data = {
        "base_url": "https://docs.example.com",
        "results": ["https://docs.example.com/", "https://docs.example.com/a"],
        "response_time": 1.11,
        "request_id": "rid",
    }
    resp = _normalize_traversal(data, "map")
    assert resp.kind == "map"
    assert len(resp.pages) == 2
    assert resp.urls == ["https://docs.example.com/", "https://docs.example.com/a"]
    assert all(p["content"] is None for p in resp.pages)
    assert resp.response_time == 1.11
    assert resp.to_dict()["count"] == 2


def test_normalize_traversal_crawl_shape():
    """/crawl returns results: list[{url, raw_content}]."""
    data = {
        "base_url": "https://docs.example.com",
        "results": [
            {"url": "https://docs.example.com/api", "raw_content": "# API\nbody"},
            {"url": "", "raw_content": "dropped — no url"},
            {"url": "https://docs.example.com/b", "raw_content": None},
        ],
        "response_time": 2.55,
    }
    resp = _normalize_traversal(data, "crawl")
    assert resp.kind == "crawl"
    assert len(resp.pages) == 2, "entries without a url must be dropped"
    assert resp.pages[0]["content"] == "# API\nbody"
    assert resp.pages[1]["content"] is None


def test_traversal_payload_builder():
    p = TavilyProvider()
    payload = p._traversal_payload(
        "https://x.com",
        max_depth=2,
        max_breadth=30,
        limit=100,
        instructions="only pricing pages",
        select_paths="/pricing/.*",
        exclude_paths=["/blog/.*"],
        allow_external=False,
        categories="Pricing",
    )
    assert payload["url"] == "https://x.com"
    assert payload["max_depth"] == 2
    assert payload["max_breadth"] == 30
    assert payload["limit"] == 100
    assert payload["instructions"] == "only pricing pages"
    # single strings get wrapped into lists
    assert payload["select_paths"] == ["/pricing/.*"]
    assert payload["exclude_paths"] == ["/blog/.*"]
    assert payload["categories"] == ["Pricing"]
    assert payload["allow_external"] is False


def test_traversal_payload_ignores_bad_ints():
    p = TavilyProvider()
    payload = p._traversal_payload("https://x.com", max_depth="not-an-int", limit=None)
    assert "max_depth" not in payload
    assert "limit" not in payload


@pytest.mark.asyncio
async def test_map_site_hits_map_endpoint(monkeypatch):
    seen: dict = {}

    async def fake_request(self, method, url, **kwargs):
        seen["url"] = url
        seen["json"] = kwargs.get("json")
        seen["timeout"] = kwargs.get("timeout")
        return _Resp({"base_url": "https://x.com", "results": ["https://x.com/a"]})

    monkeypatch.setattr(TavilyProvider, "_request", fake_request, raising=False)
    p = TavilyProvider()
    data = await p.map_site("https://x.com", limit=10)
    assert seen["url"].endswith("/map")
    assert seen["json"]["limit"] == 10
    assert seen["timeout"] == 120.0
    assert data["results"] == ["https://x.com/a"]


@pytest.mark.asyncio
async def test_crawl_site_hits_crawl_endpoint_with_extract_opts(monkeypatch):
    seen: dict = {}

    async def fake_request(self, method, url, **kwargs):
        seen["url"] = url
        seen["json"] = kwargs.get("json")
        seen["timeout"] = kwargs.get("timeout")
        return _Resp({"base_url": "https://x.com", "results": []})

    monkeypatch.setattr(TavilyProvider, "_request", fake_request, raising=False)
    p = TavilyProvider()
    await p.crawl_site(
        "https://x.com", limit=5, extract_depth="advanced", format="markdown",
        instructions="api docs only",
    )
    assert seen["url"].endswith("/crawl")
    assert seen["json"]["extract_depth"] == "advanced"
    assert seen["json"]["format"] == "markdown"
    assert seen["json"]["instructions"] == "api docs only"
    assert seen["timeout"] == 300.0


@pytest.mark.asyncio
async def test_crawl_rejects_invalid_extract_depth(monkeypatch):
    seen: dict = {}

    async def fake_request(self, method, url, **kwargs):
        seen["json"] = kwargs.get("json")
        return _Resp({"results": []})

    monkeypatch.setattr(TavilyProvider, "_request", fake_request, raising=False)
    p = TavilyProvider()
    await p.crawl_site("https://x.com", extract_depth="turbo", format="pdf")
    assert "extract_depth" not in seen["json"]
    assert "format" not in seen["json"]


# ---------------------------------------------------------------------------
# 4. Exa slow-tier timeout floor (recall was silently losing Exa)
# ---------------------------------------------------------------------------


def test_slow_exa_types_get_timeout_floor():
    from hsearch.providers.exa import _SLOW_EXA_TIMEOUT, _search_timeout

    for t in ("deep-reasoning", "deep"):
        got = _search_timeout({"type": t})
        assert got is not None and got >= _SLOW_EXA_TIMEOUT


def test_fast_exa_types_keep_default_timeout():
    from hsearch.providers.exa import _search_timeout

    for t in ("instant", "fast", "auto", "neural", "keyword", None):
        assert _search_timeout({"type": t}) is None, f"{t} should not get a floor"


def test_user_timeout_override_wins_when_higher(monkeypatch):
    from hsearch.providers.exa import _search_timeout

    monkeypatch.setenv("HSEARCH_TIMEOUT", "120")
    assert _search_timeout({"type": "deep-reasoning"}) == 120.0


@pytest.mark.asyncio
async def test_recall_mode_exa_call_uses_long_timeout(monkeypatch):
    """The exact payload --mode recall produces must carry the raised timeout."""
    seen: dict = {}

    async def fake_request(self, method, url, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return _Resp({"results": []})

    from hsearch.providers.exa import ExaProvider

    monkeypatch.setattr(ExaProvider, "_request", fake_request, raising=False)
    extra = _build_extra(mode="recall")
    p = ExaProvider()
    await p._search("q", count=3, **extra)
    assert seen["timeout"] and seen["timeout"] >= 45.0, (
        f"recall's deep-reasoning call got timeout={seen['timeout']}, "
        "will time out against the 15s default"
    )


def test_sdk_exports_traversal_surface():
    import hsearch

    for name in ("map_site", "map_site_sync", "crawl_site", "crawl_site_sync",
                 "TraversalResponse"):
        assert hasattr(hsearch, name), f"missing SDK export: {name}"
        assert name in hsearch.__all__, f"{name} not in __all__"


def test_cli_registers_map_and_crawl():
    from typer.testing import CliRunner

    from hsearch.cli import app

    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "map" in result.output
    assert "crawl" in result.output


def test_version_is_consistent():
    """Every release has shipped at least once with a stale version string."""
    import tomllib
    from pathlib import Path

    from hsearch import __version__

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with pyproject.open("rb") as fh:
        declared = tomllib.load(fh)["project"]["version"]
    assert declared == __version__, (
        f"pyproject.toml says {declared} but hsearch.__version__ says {__version__}"
    )
