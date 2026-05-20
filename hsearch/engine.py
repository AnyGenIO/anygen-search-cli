"""Programmatic search API — the core engine behind both CLI and library use.

Usage::

    from hsearch import search, search_sync, SearchResult

    # async
    resp = await search("Python async tutorial", mode="general", top=5)

    # sync
    resp = search_sync("Python async tutorial", mode="general", top=5)

    resp.results   # list[SearchResult]
    resp.answer    # str | None  (Tavily synthesized answer)
    resp.errors    # dict[str, str]
    resp.meta      # dict with query, mode, providers_queried, etc.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from hsearch.cache import ResultCache
from hsearch.config import configured_providers
from hsearch.dedup import dedup_merge
from hsearch.extract import EXTRACT_PROVIDERS, extract_many
from hsearch.filters import Filters, apply as apply_filters
from hsearch.models import SearchResult
from hsearch.providers import ProviderAuthError, ProviderHTTPError, get_provider
from hsearch.router import providers_for_mode


@dataclass
class SearchResponse:
    """Structured response from a search call."""

    results: list[SearchResult] = field(default_factory=list)
    answer: str | None = None
    errors: dict[str, str] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.meta:
            out["meta"] = self.meta
        if self.answer:
            out["meta"] = {**out.get("meta", {}), "answer": self.answer}
        out["results"] = [r.to_dict() for r in self.results]
        if self.errors:
            out["errors"] = self.errors
        return out


@dataclass
class ExtractResult:
    """Result from a URL content extraction."""

    url: str
    content: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Internal helpers (moved from cli.py)
# ---------------------------------------------------------------------------


async def _run_one(
    provider_name: str,
    query: str,
    count: int,
    use_cache: bool,
    cache: ResultCache | None,
    extra: dict,
    filters: Filters | None = None,
    cache_ttl_override: int | None = None,
) -> tuple[str, list[SearchResult] | None, str | None, dict]:
    if filters is not None:
        eff_query, eff_extra = apply_filters(provider_name, query, filters, extra)
    else:
        eff_query, eff_extra = query, dict(extra)
    extras_out: dict = {}
    cache_params = {
        k: v
        for k, v in {"count": count, **eff_extra}.items()
        if not str(k).startswith("_")
    }
    if use_cache and cache is not None:
        hit = cache.get(provider_name, eff_query, cache_params)
        if hit is not None:
            results = [SearchResult(**r) for r in hit]
            extras_out["cached"] = True
            return provider_name, results, None, extras_out
    try:
        provider = get_provider(provider_name)
    except KeyError as e:
        return provider_name, None, str(e), extras_out
    try:
        async with provider:
            results = await provider.search(eff_query, count=count, **eff_extra)
            ans = getattr(provider, "_last_answer", None)
            if ans:
                extras_out["answer"] = ans
            usage = getattr(provider, "_last_usage", None)
            if isinstance(usage, dict) and usage:
                extras_out["usage"] = usage
    except ProviderAuthError as e:
        return provider_name, None, f"auth: {e}", extras_out
    except ProviderHTTPError as e:
        return provider_name, None, f"http: {e}", extras_out
    except Exception as e:  # noqa: BLE001
        return provider_name, None, f"{type(e).__name__}: {e}", extras_out

    if use_cache and cache is not None:
        cache.set(
            provider_name,
            eff_query,
            cache_params,
            [r.to_dict() | {"raw": {}} for r in results],
            ttl=cache_ttl_override,
        )
    extras_out["cached"] = False
    return provider_name, results, None, extras_out


async def _run_many(
    providers: list[str],
    query: str,
    count: int,
    use_cache: bool,
    extra: dict,
    filters: Filters | None = None,
    cache_ttl_override: int | None = None,
) -> tuple[list[SearchResult], dict[str, str], dict[str, dict]]:
    cache: ResultCache | None = ResultCache() if use_cache else None
    try:
        coros = [
            _run_one(p, query, count, use_cache, cache, extra, filters, cache_ttl_override)
            for p in providers
        ]
        outcomes = await asyncio.gather(*coros)
    finally:
        if cache is not None:
            cache.close()

    merged: list[SearchResult] = []
    errors: dict[str, str] = {}
    extras_by_provider: dict[str, dict] = {}
    for name, results, err, extras in outcomes:
        if extras:
            extras_by_provider[name] = extras
        if err is not None or results is None:
            errors[name] = err or "no results"
            continue
        merged.extend(results)
    return merged, errors, extras_by_provider


def _resolve_providers(
    providers: list[str] | None = None,
    mode: str | None = None,
    all_providers: bool = False,
) -> list[str]:
    if all_providers:
        return configured_providers()
    if providers:
        return list(providers)
    return providers_for_mode(mode)


def _build_extra(mode: str | None = None, **kwargs: Any) -> dict[str, Any]:
    """Translate high-level options into provider kwargs."""
    extra: dict[str, Any] = {}
    mode_key = (mode or "").lower() or None

    if mode_key == "news":
        extra["topic"] = "news"
        extra["freshness"] = "pw"
    elif mode_key == "academic":
        extra["category"] = "research paper"
    elif mode_key == "realtime":
        extra["freshness"] = "pd"
    elif mode_key == "shopping":
        extra["search_type"] = "shopping"
    elif mode_key == "video":
        extra["search_type"] = "videos"
    elif mode_key == "images":
        extra["search_type"] = "images"
    elif mode_key == "places":
        extra["search_type"] = "places"
    elif mode_key == "answer":
        kwargs.setdefault("answer", True)
    elif mode_key == "deep":
        extra["type"] = "deep-reasoning"
        extra["summary"] = True
    elif mode_key == "fast":
        extra["type"] = "instant"
        extra["search_depth"] = "ultra-fast"
    elif mode_key == "recall":
        extra["type"] = "deep-reasoning"
        extra["highlights"] = True
        extra["summary"] = True
        extra["search_depth"] = "advanced"
        extra["chunks_per_source"] = 3
        extra["auto_parameters"] = True
        extra["search_kind"] = "context"
        extra["context_threshold_mode"] = "lenient"
        extra["sources"] = ["web", "news"]
        extra["with_content"] = True

    if kwargs.get("answer"):
        extra["include_answer"] = True
    if kwargs.get("summary"):
        extra["summary"] = True
    if kwargs.get("sources"):
        src = kwargs["sources"]
        extra["sources"] = [s.strip() for s in src.split(",")] if isinstance(src, str) else src
    if kwargs.get("livecrawl"):
        extra["livecrawl"] = kwargs["livecrawl"]
    if kwargs.get("auto"):
        extra["auto_parameters"] = True
    if kwargs.get("raw"):
        extra["include_raw_content"] = "markdown"
    if kwargs.get("days") is not None:
        extra["days"] = kwargs["days"]
    if kwargs.get("chunks_per_source") is not None:
        extra["chunks_per_source"] = kwargs["chunks_per_source"]
    if kwargs.get("additional_queries"):
        extra["additional_queries"] = list(kwargs["additional_queries"])
    if kwargs.get("max_age_hours") is not None:
        extra["max_age_hours"] = kwargs["max_age_hours"]
    if kwargs.get("highlights"):
        extra["highlights"] = True
    if kwargs.get("context_threshold"):
        extra["context_threshold_mode"] = kwargs["context_threshold"]
    if kwargs.get("retries") is not None:
        extra["_retries"] = kwargs["retries"]
    if kwargs.get("exact"):
        extra["exact_match"] = True
    if kwargs.get("depth"):
        extra["search_depth"] = kwargs["depth"]
    if kwargs.get("exa_type"):
        extra["type"] = kwargs["exa_type"]
    if kwargs.get("include_favicon"):
        extra["include_favicon"] = True
    if kwargs.get("include_usage"):
        extra["include_usage"] = True

    return extra


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def search(
    query: str,
    *,
    providers: list[str] | None = None,
    mode: str | None = None,
    all_providers: bool = False,
    top: int = 10,
    no_cache: bool = False,
    cache_ttl: int | None = None,
    time: str | None = None,
    lang: str | None = None,
    region: str | None = None,
    sites: list[str] | None = None,
    exclude: list[str] | None = None,
    extract_top: int = 0,
    extract_provider: str = "jina",
    api_keys: dict[str, str] | None = None,
    **kwargs: Any,
) -> SearchResponse:
    """Run a search across one or more providers.

    Args:
        query: The search query string.
        providers: Explicit provider list (e.g. ["tavily", "brave"]).
        mode: Routing mode — default|news|academic|code|general|realtime|
              shopping|video|images|places|answer|deep|fast|recall.
        all_providers: Query every configured provider.
        top: Max results per provider.
        no_cache: Disable result cache.
        cache_ttl: Override cache TTL in seconds.
        time: Time filter — day|week|month|year or YYYY-MM-DD..YYYY-MM-DD.
        lang: ISO 639-1 language code.
        region: ISO 3166 country code.
        sites: Restrict to these domains.
        exclude: Exclude these domains.
        extract_top: Extract content from top N results.
        extract_provider: Provider for content extraction (jina|firecrawl).
        api_keys: Override API keys (e.g. {"tavily": "tvly-xxx"}).
        **kwargs: Provider-specific options (answer, summary, raw, depth, etc.)

    Returns:
        SearchResponse with results, answer, errors, and meta.
    """
    import os

    if api_keys:
        from hsearch.config import PROVIDER_ENV

        for prov, key in api_keys.items():
            env_var = PROVIDER_ENV.get(prov)
            if env_var:
                os.environ[env_var] = key

    resolved_providers = _resolve_providers(providers, mode, all_providers)
    if not resolved_providers:
        return SearchResponse(
            errors={"_": "No providers configured. Set API keys via env vars or api_keys param."},
        )

    filters = Filters.from_cli(
        time=time, lang=lang, region=region, sites=sites, exclude=exclude,
    )
    extra = _build_extra(mode=mode, **kwargs)
    mode_key = (mode or "").lower() or None

    results, errors, extras_by_provider = await _run_many(
        resolved_providers,
        query,
        top,
        use_cache=not no_cache,
        extra=extra,
        filters=filters,
        cache_ttl_override=cache_ttl,
    )

    merged = dedup_merge(results)
    limit = max(top, 1) if not all_providers else top * len(resolved_providers)
    merged = merged[:limit]

    if extract_top and extract_top > 0 and merged and extract_provider in EXTRACT_PROVIDERS:
        urls = [r.url for r in merged[:extract_top] if r.url]
        outcomes = await extract_many(urls, provider=extract_provider, concurrency=4)
        url_to_content = {u: c for (u, c, _e) in outcomes if c}
        for r in merged:
            if r.url in url_to_content:
                r.content = url_to_content[r.url]

    tavily_answer = (extras_by_provider.get("tavily") or {}).get("answer")
    cache_status = {
        p: extras_by_provider.get(p, {}).get("cached")
        for p in resolved_providers
        if "cached" in extras_by_provider.get(p, {})
    }
    meta: dict[str, Any] = {
        "query": query,
        "mode": mode_key or "default",
        "providers_queried": resolved_providers,
        "total_results": len(merged),
        "cached": cache_status,
    }
    usage_by_provider = {
        p: extras_by_provider[p]["usage"]
        for p in resolved_providers
        if isinstance(extras_by_provider.get(p, {}).get("usage"), dict)
    }
    if usage_by_provider:
        meta["usage"] = usage_by_provider
    if extract_top and extract_top > 0:
        meta["extract_top"] = extract_top
        meta["extract_provider"] = extract_provider

    return SearchResponse(
        results=merged,
        answer=tavily_answer,
        errors=errors,
        meta=meta,
    )


def search_sync(
    query: str,
    **kwargs: Any,
) -> SearchResponse:
    """Synchronous wrapper around :func:`search`."""
    return asyncio.run(search(query, **kwargs))


async def extract_urls(
    urls: list[str],
    provider: str = "jina",
    concurrency: int = 4,
) -> list[ExtractResult]:
    """Extract clean text/markdown content from URLs.

    Args:
        urls: URLs to extract content from.
        provider: Extraction provider (jina or firecrawl).
        concurrency: Max parallel requests.

    Returns:
        List of ExtractResult with url, content, and error fields.
    """
    outcomes = await extract_many(urls, provider=provider, concurrency=concurrency)
    return [ExtractResult(url=u, content=c, error=e) for u, c, e in outcomes]


def extract_urls_sync(
    urls: list[str],
    provider: str = "jina",
    concurrency: int = 4,
) -> list[ExtractResult]:
    """Synchronous wrapper around :func:`extract_urls`."""
    return asyncio.run(extract_urls(urls, provider=provider, concurrency=concurrency))
