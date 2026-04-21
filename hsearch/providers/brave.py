"""Brave Search API. Docs: https://api-dashboard.search.brave.com/app/documentation/web-search"""
from __future__ import annotations

from typing import Any

from hsearch.models import SearchResult
from hsearch.providers.base import SearchProvider

WEB_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
NEWS_ENDPOINT = "https://api.search.brave.com/res/v1/news/search"
VIDEOS_ENDPOINT = "https://api.search.brave.com/res/v1/videos/search"
IMAGES_ENDPOINT = "https://api.search.brave.com/res/v1/images/search"

KIND_ENDPOINTS = {
    "web": WEB_ENDPOINT,
    "news": NEWS_ENDPOINT,
    "video": VIDEOS_ENDPOINT,
    "videos": VIDEOS_ENDPOINT,
    "image": IMAGES_ENDPOINT,
    "images": IMAGES_ENDPOINT,
}


class BraveProvider(SearchProvider):
    name = "brave"
    requires_env = ["BRAVE_API_KEY"]

    async def _search(self, query: str, count: int = 10, **kwargs: Any) -> list[SearchResult]:
        kind = (kwargs.get("search_kind") or kwargs.get("search_type") or "web").lower()
        # Brave doesn't natively expose shopping/places — degrade to web search.
        if kind in ("shopping", "places"):
            kind = "web"
        url = KIND_ENDPOINTS.get(kind, WEB_ENDPOINT)
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
            ("result_filter", "result_filter"),
            ("units", "units"),
            ("offset", "offset"),
            ("safesearch", "safesearch"),
        ):
            v = kwargs.get(src)
            if v is not None and v != "":
                params[dst] = v
        if kwargs.get("extra_snippets"):
            # Brave wants the literal lowercase string "true"/"false"
            params["extra_snippets"] = "true"

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
