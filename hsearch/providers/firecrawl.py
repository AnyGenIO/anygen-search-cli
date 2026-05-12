"""Firecrawl v2 search + scrape. Docs: https://docs.firecrawl.dev/api-reference/endpoint/search"""
from __future__ import annotations

from typing import Any

from hsearch.models import SearchResult
from hsearch.providers.base import SearchProvider

SEARCH_ENDPOINT = "https://api.firecrawl.dev/v2/search"
SCRAPE_ENDPOINT = "https://api.firecrawl.dev/v2/scrape"

_VALID_SOURCES = {"web", "news", "images"}


class FirecrawlProvider(SearchProvider):
    name = "firecrawl"
    requires_env = ["FIRECRAWL_API_KEY"]
    supports_extract = True

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key or ''}",
            "Content-Type": "application/json",
        }

    async def _search(self, query: str, count: int = 10, **kwargs: Any) -> list[SearchResult]:
        # ---- sources -------------------------------------------------------
        raw_sources = kwargs.get("sources")
        if isinstance(raw_sources, str):
            raw_sources = [s.strip() for s in raw_sources.split(",") if s.strip()]
        if not raw_sources:
            sources = ["web"]
        else:
            sources = [s for s in raw_sources if s in _VALID_SOURCES] or ["web"]

        payload: dict[str, Any] = {
            "query": query,
            "limit": max(1, min(count, 100)),
            "sources": sources,
        }
        if kwargs.get("categories"):
            cats = kwargs["categories"]
            if isinstance(cats, str):
                cats = [c.strip() for c in cats.split(",") if c.strip()]
            # v2 API now expects [{"type": "github"}] objects; older string form
            # ["github"] is still accepted for backward compatibility but the
            # docs steer toward the object shape, so normalize on send.
            normalized: list[dict[str, Any]] = []
            for c in cats:
                if isinstance(c, dict):
                    normalized.append(c)
                elif isinstance(c, str) and c:
                    normalized.append({"type": c})
            if normalized:
                payload["categories"] = normalized
        if kwargs.get("country"):
            payload["country"] = kwargs["country"]
        if kwargs.get("location"):
            payload["location"] = kwargs["location"]
        if kwargs.get("lang"):
            payload["lang"] = kwargs["lang"]
        if kwargs.get("tbs"):
            payload["tbs"] = kwargs["tbs"]
        if kwargs.get("include_domains"):
            payload["includeDomains"] = kwargs["include_domains"]
        if kwargs.get("exclude_domains"):
            payload["excludeDomains"] = kwargs["exclude_domains"]

        # ---- scrapeOptions -------------------------------------------------
        # Build formats based on with_content / summary flags. Both new
        # `[{"type": "markdown"}]` and `[{"type": "summary"}]` shapes are
        # supported by the v2 API.
        formats: list[dict[str, Any]] = []
        if kwargs.get("with_content"):
            formats.append({"type": "markdown"})
        if kwargs.get("summary"):
            formats.append({"type": "summary"})
        if formats:
            payload["scrapeOptions"] = {"formats": formats, "onlyMainContent": True}

        resp = await self._request(
            "POST", SEARCH_ENDPOINT, headers=self._headers(), json=payload
        )
        data = resp.json()
        block = data.get("data") or {}

        out: list[SearchResult] = []
        per_source_cap = max(1, count)
        # iterate in user-specified order so first source wins relative ranking
        for src in sources:
            items = block.get(src) or []
            if not isinstance(items, list):
                continue
            for r in items[:per_source_cap]:
                if not isinstance(r, dict):
                    continue
                url = r.get("url") or r.get("link") or r.get("imageUrl") or ""
                if not url:
                    continue
                summary_val = r.get("summary")
                content_val = r.get("markdown") or r.get("content")
                out.append(
                    SearchResult(
                        url=url,
                        title=r.get("title", "") or url,
                        snippet=r.get("description", "") or r.get("snippet", "") or "",
                        provider=self.name,
                        published=r.get("date") or r.get("published"),
                        summary=summary_val if isinstance(summary_val, str) else None,
                        content=content_val if isinstance(content_val, str) else None,
                        raw=r,
                    )
                )
        # Honor the global cap.
        return out[:count] if count else out

    async def _extract(self, url: str) -> str | None:
        payload = {"url": url, "formats": ["markdown"], "onlyMainContent": True}
        resp = await self._request("POST", SCRAPE_ENDPOINT, headers=self._headers(), json=payload)
        data = resp.json()
        return ((data.get("data") or {}).get("markdown")) or None
