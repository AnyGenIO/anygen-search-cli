"""Page-extraction interface — wraps Jina Reader / Firecrawl Scrape."""
from __future__ import annotations

import asyncio

from hsearch.providers import get_provider

EXTRACT_PROVIDERS = ("jina", "firecrawl")


async def extract_one(url: str, provider: str = "jina") -> tuple[str, str | None, str | None]:
    """Return (url, content, error)."""
    if provider not in EXTRACT_PROVIDERS:
        return url, None, f"provider '{provider}' does not support extract"
    p = get_provider(provider)
    try:
        async with p:
            content = await p.extract(url)
            if not content:
                return url, None, "no content returned"
            return url, content, None
    except Exception as e:  # noqa: BLE001
        return url, None, f"{type(e).__name__}: {e}"


async def extract_many(
    urls: list[str], provider: str = "jina", concurrency: int = 4
) -> list[tuple[str, str | None, str | None]]:
    sem = asyncio.Semaphore(max(1, concurrency))

    async def _one(u: str) -> tuple[str, str | None, str | None]:
        async with sem:
            return await extract_one(u, provider=provider)

    return await asyncio.gather(*(_one(u) for u in urls))
