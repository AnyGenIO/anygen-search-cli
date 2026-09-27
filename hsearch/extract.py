"""Page-extraction interface — wraps Jina Reader / Firecrawl Scrape / Tavily Extract."""
from __future__ import annotations

import asyncio
from typing import Any

from hsearch.config import default_extract_provider, extract_fallback_chain
from hsearch.providers import get_provider

EXTRACT_PROVIDERS = ("jina", "firecrawl", "tavily")


async def _extract_with(
    url: str, provider: str, **options: Any
) -> tuple[str, str | None, str | None]:
    """Single-provider extraction. Return (url, content, error).

    ``options`` are provider-specific extras. For the ``tavily`` provider they
    map onto the /extract endpoint (``query`` to rerank chunks, ``extract_depth``
    basic|advanced, ``format`` markdown|text). Other providers ignore them.
    """
    if provider not in EXTRACT_PROVIDERS:
        return url, None, f"provider '{provider}' does not support extract"
    p = get_provider(provider)
    try:
        async with p:
            # Tavily supports richer extract options via extract_with_options;
            # jina/firecrawl use the plain extract() hook.
            if provider == "tavily" and options:
                content = await p.extract_with_options(url, **options)  # type: ignore[attr-defined]
            else:
                content = await p.extract(url)
            if not content:
                return url, None, "no content returned"
            return url, content, None
    except Exception as e:  # noqa: BLE001
        return url, None, f"{type(e).__name__}: {e}"


async def extract_one_detailed(
    url: str, provider: str | None = None, fallback: bool = True, **options: Any
) -> tuple[str, str | None, str | None, str]:
    """Extract ``url``; on error retry through :func:`extract_fallback_chain`.

    Returns ``(url, content, error, served_by)``. ``served_by`` is the provider
    that produced the content (or the primary provider on total failure).
    Provider-specific ``options`` are only sent to the primary provider.
    """
    primary = (provider or default_extract_provider()).lower()
    u, content, err = await _extract_with(url, primary, **options)
    if not err or not fallback or primary not in EXTRACT_PROVIDERS:
        return u, content, err, primary
    errors = [f"{primary}: {err}"]
    for fb in extract_fallback_chain(primary):
        if fb not in EXTRACT_PROVIDERS:
            continue
        _u, c2, e2 = await _extract_with(url, fb)
        if c2:
            return u, c2, None, fb
        errors.append(f"{fb}: {e2}")
    return u, None, "; ".join(errors), primary


async def extract_one(
    url: str, provider: str | None = None, fallback: bool = True, **options: Any
) -> tuple[str, str | None, str | None]:
    """Return (url, content, error). ``provider=None`` = HSEARCH_EXTRACT_PROVIDER / jina."""
    u, c, e, _by = await extract_one_detailed(url, provider=provider, fallback=fallback, **options)
    return u, c, e


async def extract_many_detailed(
    urls: list[str],
    provider: str | None = None,
    concurrency: int = 4,
    fallback: bool = True,
    **options: Any,
) -> list[tuple[str, str | None, str | None, str]]:
    sem = asyncio.Semaphore(max(1, concurrency))

    async def _one(u: str) -> tuple[str, str | None, str | None, str]:
        async with sem:
            return await extract_one_detailed(u, provider=provider, fallback=fallback, **options)

    return await asyncio.gather(*(_one(u) for u in urls))


async def extract_many(
    urls: list[str],
    provider: str | None = None,
    concurrency: int = 4,
    fallback: bool = True,
    **options: Any,
) -> list[tuple[str, str | None, str | None]]:
    out = await extract_many_detailed(
        urls, provider=provider, concurrency=concurrency, fallback=fallback, **options
    )
    return [(u, c, e) for u, c, e, _by in out]
