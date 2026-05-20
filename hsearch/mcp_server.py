"""MCP stdio server for hsearch."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from hsearch.config import PROVIDER_ENV, configured_providers, get_key
from hsearch.engine import extract_urls, search_sync
from hsearch.providers import list_providers
from hsearch.schema import render_schema

try:  # pragma: no cover - exercised by CLI fallback when the extra is missing.
    from mcp.server.fastmcp import FastMCP
except ImportError as e:  # pragma: no cover
    FastMCP = None  # type: ignore[assignment]
    MCP_IMPORT_ERROR: ImportError | None = e
else:
    MCP_IMPORT_ERROR = None


INSTALL_HINT = 'Install MCP support with: pip install -e ".[mcp]"'


def _as_list(value: str | list[str] | tuple[str, ...] | None) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value]


async def search(
    query: str,
    mode: str | None = None,
    provider: str | list[str] | None = None,
    top: int = 10,
    time: str | None = None,
    lang: str | None = None,
    region: str | None = None,
    site: str | list[str] | None = None,
    exclude: str | list[str] | None = None,
    answer: bool = False,
    summary: bool = False,
    max_age_hours: int | None = None,
    depth: str | None = None,
    all_providers: bool = False,
    no_cache: bool = False,
    cache_ttl: int | None = None,
    extract_top: int = 0,
    extract_provider: str = "jina",
    sources: str | None = None,
    goggles: str | list[str] | None = None,
    serper_type: str | None = None,
    page: int | None = None,
    autocorrect: bool | None = None,
    livecrawl: str | None = None,
    auto: bool = False,
    raw: bool = False,
    retries: int = 2,
    days: int | None = None,
    chunks_per_source: int | None = None,
    additional_query: str | list[str] | None = None,
    highlights: bool = False,
    context_threshold: str | None = None,
    exact: bool = False,
    exa_type: str | None = None,
    include_favicon: bool = False,
    include_usage: bool = False,
    include_images: bool = False,
    include_image_descriptions: bool = False,
    answer_depth: str | None = None,
    moderation: bool = False,
    livecrawl_timeout: int | None = None,
    ignore_invalid_urls: bool = False,
    location: str | None = None,
) -> dict[str, Any]:
    """Run hsearch and return the same JSON shape as ``hsearch search -f json``."""
    resp = await asyncio.to_thread(
        search_sync,
        query,
        providers=_as_list(provider),
        mode=mode,
        all_providers=all_providers,
        top=top,
        no_cache=no_cache,
        cache_ttl=cache_ttl,
        time=time,
        lang=lang,
        region=region,
        sites=_as_list(site),
        exclude=_as_list(exclude),
        extract_top=extract_top,
        extract_provider=extract_provider,
        answer=answer,
        summary=summary,
        max_age_hours=max_age_hours,
        depth=depth,
        sources=sources,
        goggles=_as_list(goggles),
        serper_type=serper_type,
        page=page,
        autocorrect=autocorrect,
        livecrawl=livecrawl,
        auto=auto,
        raw=raw,
        retries=retries,
        days=days,
        chunks_per_source=chunks_per_source,
        additional_queries=_as_list(additional_query),
        highlights=highlights,
        context_threshold=context_threshold,
        exact=exact,
        exa_type=exa_type,
        include_favicon=include_favicon,
        include_usage=include_usage,
        include_images=include_images,
        include_image_descriptions=include_image_descriptions,
        answer_depth=answer_depth,
        moderation=moderation,
        livecrawl_timeout=livecrawl_timeout,
        ignore_invalid_urls=ignore_invalid_urls,
        location=location,
    )
    return resp.to_dict()


async def extract(url: str, provider: str = "jina") -> dict[str, Any]:
    """Extract a URL and return the same JSON shape as ``hsearch extract -f json``."""
    results = await extract_urls([url], provider=provider, concurrency=1)
    ok = [{"url": r.url, "content": r.content} for r in results if not r.error]
    errors = {r.url: r.error for r in results if r.error}
    out: dict[str, Any] = {
        "meta": {
            "provider": provider,
            "urls_requested": 1,
            "urls_succeeded": len(ok),
        },
        "results": ok,
    }
    if errors:
        out["errors"] = errors
    return out


def providers() -> dict[str, Any]:
    """Return available providers and API-key configuration status."""
    items = [
        {
            "name": name,
            "env_var": PROVIDER_ENV[name],
            "configured": bool(get_key(name)),
        }
        for name in list_providers()
    ]
    return {"providers": items, "configured": configured_providers()}


def schema() -> dict[str, Any]:
    """Return the same tool schema as ``hsearch schema``."""
    return json.loads(render_schema())


def build_server() -> Any:
    """Build a FastMCP server with hsearch tools registered."""
    if FastMCP is None:
        raise RuntimeError(INSTALL_HINT) from MCP_IMPORT_ERROR
    server = FastMCP(
        "hsearch",
        instructions="Unified search and extraction over Brave, Serper, Exa, Tavily, Firecrawl, and Jina.",
    )
    server.tool(name="search")(search)
    server.tool(name="extract")(extract)
    server.tool(name="providers")(providers)
    server.tool(name="schema")(schema)
    return server


def run_stdio() -> None:
    """Run the MCP server over stdio. stdout is reserved for MCP frames."""
    build_server().run(transport="stdio")
