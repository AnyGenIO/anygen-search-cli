"""Page-extraction interface — wraps Jina Reader / Firecrawl Scrape / Tavily Extract."""
from __future__ import annotations

import asyncio
from typing import Any

from hsearch.providers import get_provider

EXTRACT_PROVIDERS = ("jina", "firecrawl", "tavily")


async def extract_one(
    url: str, provider: str = "jina", **options: Any
) -> tuple[str, str | None, str | None]:
    """Return (url, content, error).

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


async def extract_many(
    urls: list[str], provider: str = "jina", concurrency: int = 4, **options: Any
) -> list[tuple[str, str | None, str | None]]:
    sem = asyncio.Semaphore(max(1, concurrency))

    async def _one(u: str) -> tuple[str, str | None, str | None]:
        async with sem:
            return await extract_one(u, provider=provider, **options)

    return await asyncio.gather(*(_one(u) for u in urls))
