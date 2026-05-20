"""Brave Search API. Docs: https://api-dashboard.search.brave.com/app/documentation/web-search"""
from __future__ import annotations

from typing import Any

from hsearch.models import SearchResult
from hsearch.providers.base import SearchProvider

WEB_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
NEWS_ENDPOINT = "https://api.search.brave.com/res/v1/news/search"
VIDEOS_ENDPOINT = "https://api.search.brave.com/res/v1/videos/search"
IMAGES_ENDPOINT = "https://api.search.brave.com/res/v1/images/search"
LLM_CONTEXT_ENDPOINT = "https://api.search.brave.com/res/v1/llm/context"
PLACE_ENDPOINT = "https://api.search.brave.com/res/v1/local/place_search"

KIND_ENDPOINTS = {
    "web": WEB_ENDPOINT,
    "news": NEWS_ENDPOINT,
    "video": VIDEOS_ENDPOINT,
    "videos": VIDEOS_ENDPOINT,
    "image": IMAGES_ENDPOINT,
    "images": IMAGES_ENDPOINT,
    "context": LLM_CONTEXT_ENDPOINT,
    "llm": LLM_CONTEXT_ENDPOINT,
    "llm_context": LLM_CONTEXT_ENDPOINT,
    "place": PLACE_ENDPOINT,
    "places": PLACE_ENDPOINT,
}


class BraveProvider(SearchProvider):
    name = "brave"
    requires_env = ["BRAVE_API_KEY"]

    async def _search(self, query: str, count: int = 10, **kwargs: Any) -> list[SearchResult]:
        kind = (kwargs.get("search_kind") or kwargs.get("search_type") or "web").lower()
        # Brave doesn't natively expose shopping — degrade to web search.
        if kind == "shopping":
            kind = "web"
        url = KIND_ENDPOINTS.get(kind, WEB_ENDPOINT)
        if url == LLM_CONTEXT_ENDPOINT:
            return await self._search_context(query, count=count, **kwargs)
        if url == PLACE_ENDPOINT:
            return await self._search_places(query, count=count, **kwargs)
        # Brave caps count at 20 per page.
        params: dict[str, Any] = {
            "q": query,
            "count": min(max(count, 1), 20),
        }
        for src, dst in (
            ("freshness", "freshness"),
            ("country", "country"),
            ("search_lang", "search_lang"),
            ("goggles_id", "goggles_id"),
            ("goggles", "goggles"),
            ("result_filter", "result_filter"),
            ("units", "units"),
            ("offset", "offset"),
            ("safesearch", "safesearch"),
            ("ui_lang", "ui_lang"),
            ("text_decorations", "text_decorations"),
            ("operators", "operators"),
            ("include_fetch_metadata", "include_fetch_metadata"),
            ("enable_rich_callback", "enable_rich_callback"),
        ):
            v = kwargs.get(src)
            if v is not None and v != "":
                params[dst] = v
        if kwargs.get("extra_snippets"):
            params["extra_snippets"] = "true"
        if kwargs.get("spellcheck"):
            params["spellcheck"] = "true"
        if kwargs.get("summary"):
            params["summary"] = "true"

        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key or "",
        }
        resp = await self._request("GET", url, headers=headers, params=params)
        data = resp.json()
        if kind == "news":
            items = (data.get("results") or []) or ((data.get("news") or {}).get("results") or [])
        elif kind in ("video", "videos"):
            items = data.get("results") or []
        elif kind in ("image", "images"):
            items = data.get("results") or []
        else:
            items = (data.get("web") or {}).get("results") or []

        out: list[SearchResult] = []
        for r in items[:count]:
            out.append(
                SearchResult(
                    url=r.get("url", "") or r.get("link", ""),
                    title=r.get("title", "") or "",
                    snippet=r.get("description", "") or r.get("snippet", "") or "",
                    provider=self.name,
                    score=0.0,
                    published=r.get("page_age") or r.get("age") or r.get("published"),
                    raw=r,
                )
            )
        return out

    async def _search_places(self, query: str, count: int = 10, **kwargs: Any) -> list[SearchResult]:
        """Use Brave Place Search for geographic POI discovery."""
        params: dict[str, Any] = {
            "q": query,
            "count": min(max(count, 1), 50),
        }
        for src, dst in (
            ("latitude", "latitude"),
            ("longitude", "longitude"),
            ("radius", "radius"),
            ("location", "location"),
            ("country", "country"),
            ("search_lang", "search_lang"),
            ("ui_lang", "ui_lang"),
            ("units", "units"),
            ("safesearch", "safesearch"),
        ):
            v = kwargs.get(src)
            if v is not None and v != "":
                params[dst] = v
        if kwargs.get("spellcheck") is not None:
            params["spellcheck"] = "true" if kwargs.get("spellcheck") else "false"

        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key or "",
        }
        resp = await self._request("GET", PLACE_ENDPOINT, headers=headers, params=params)
        data = resp.json()
        items = data.get("results") or []

        out: list[SearchResult] = []
        for r in items[:count]:
            if not isinstance(r, dict):
                continue
            address = (r.get("postal_address") or {}).get("displayAddress")
            rating = r.get("rating") or {}
            rating_text = ""
            if isinstance(rating, dict) and rating.get("ratingValue"):
                rating_text = f"{rating.get('ratingValue')} stars"
                if rating.get("reviewCount"):
                    rating_text += f" ({rating.get('reviewCount')} reviews)"
            categories = ", ".join(str(c) for c in (r.get("categories") or []) if c)
            snippet = " | ".join(s for s in (address, rating_text, categories) if s)
            thumbnail = r.get("thumbnail") or {}
            image = thumbnail.get("src") or thumbnail.get("original") if isinstance(thumbnail, dict) else None
            out.append(
                SearchResult(
                    url=r.get("url") or r.get("provider_url") or "",
                    title=r.get("title") or r.get("name") or "",
                    snippet=snippet or r.get("description", "") or "",
                    provider=self.name,
                    image=image if isinstance(image, str) else None,
                    raw=r,
                )
            )
        return out

    async def _search_context(self, query: str, count: int = 10, **kwargs: Any) -> list[SearchResult]:
        """Use Brave's LLM Context endpoint for extracted grounding snippets."""
        max_urls = _clamped_int(kwargs.get("maximum_number_of_urls"), count, 1, 50)
        max_snippets = _clamped_int(
            kwargs.get("maximum_number_of_snippets"), max(count * 3, count), 1, 100
        )
        params: dict[str, Any] = {
            "q": query,
            "count": min(max(count, 1), 50),
            "maximum_number_of_urls": max_urls,
            "maximum_number_of_tokens": _clamped_int(
                kwargs.get("maximum_number_of_tokens"), 8192, 1024, 32768
            ),
            "maximum_number_of_snippets": max_snippets,
        }
        for src, dst in (
            ("freshness", "freshness"),
            ("country", "country"),
            ("search_lang", "search_lang"),
            ("goggles_id", "goggles"),
            ("context_threshold_mode", "context_threshold_mode"),
            ("enable_local", "enable_local"),
        ):
            v = kwargs.get(src)
            if v is not None and v != "":
                params[dst] = v

        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key or "",
        }
        resp = await self._request("GET", LLM_CONTEXT_ENDPOINT, headers=headers, params=params)
        data = resp.json()
        grounding = data.get("grounding") or {}
        sources = data.get("sources") or {}

        items: list[dict[str, Any]] = []
        generic = grounding.get("generic") or []
        if isinstance(generic, list):
            items.extend(r for r in generic if isinstance(r, dict))
        for key in ("poi", "map"):
            block = grounding.get(key)
            if isinstance(block, list):
                items.extend(r for r in block if isinstance(r, dict))
            elif isinstance(block, dict):
                items.append(block)

        out: list[SearchResult] = []
        for r in items[:count]:
            url = r.get("url", "")
            if not url:
                continue
            meta = sources.get(url) if isinstance(sources, dict) else None
            if not isinstance(meta, dict):
                meta = {}
            snippets = r.get("snippets") or []
            if isinstance(snippets, str):
                snippets = [snippets]
            content = "\n\n".join(str(s) for s in snippets if s)
            age = meta.get("age")
            published = age[1] if isinstance(age, list) and len(age) > 1 else None
            out.append(
                SearchResult(
                    url=url,
                    title=r.get("title") or meta.get("title") or url,
                    snippet=content[:500],
                    provider=self.name,
                    published=published,
                    content=content or None,
                    raw={"grounding": r, "source": meta},
                )
            )
        return out


def _clamped_int(value: Any, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value if value is not None else default)
    except (TypeError, ValueError):
        parsed = default
    return min(max(parsed, min_value), max_value)
