"""Serper.dev (Google SERP). Docs: https://serper.dev/api-key"""
from __future__ import annotations

from typing import Any

from hsearch.models import SearchResult
from hsearch.providers.base import SearchProvider

ENDPOINTS = {
    "search": "https://google.serper.dev/search",
    "news": "https://google.serper.dev/news",
    "scholar": "https://google.serper.dev/scholar",
    "images": "https://google.serper.dev/images",
    "videos": "https://google.serper.dev/videos",
    "shopping": "https://google.serper.dev/shopping",
    "places": "https://google.serper.dev/places",
}

# Map search_kind -> serper sub-endpoint
KIND_MAP = {
    "web": "search",
    "news": "news",
    "scholar": "scholar",
    "academic": "scholar",
    "image": "images",
    "images": "images",
    "video": "videos",
    "videos": "videos",
    "shopping": "shopping",
    "places": "places",
}


class SerperProvider(SearchProvider):
    name = "serper"
    requires_env = ["SERPER_API_KEY"]

    async def _search(self, query: str, count: int = 10, **kwargs: Any) -> list[SearchResult]:
        kind = (kwargs.get("search_kind") or kwargs.get("search_type") or kwargs.get("endpoint") or "web").lower()
        endpoint_key = KIND_MAP.get(kind, "search") if kind in KIND_MAP else (kind if kind in ENDPOINTS else "search")
        url = ENDPOINTS.get(endpoint_key, ENDPOINTS["search"])

        payload: dict[str, Any] = {"q": query, "num": max(1, min(count, 20))}
        if kwargs.get("country"):
            payload["gl"] = kwargs["country"]
        if kwargs.get("locale"):
            payload["hl"] = kwargs["locale"]
        if kwargs.get("tbs"):
            payload["tbs"] = kwargs["tbs"]
        if kwargs.get("location"):
            payload["location"] = kwargs["location"]

        headers = {
            "X-API-KEY": self.api_key or "",
            "Content-Type": "application/json",
        }
        resp = await self._request("POST", url, headers=headers, json=payload)
        data = resp.json()

        out: list[SearchResult] = []
        if endpoint_key == "news":
            items = data.get("news") or []
            for r in items[:count]:
                out.append(
                    SearchResult(
                        url=r.get("link", ""),
                        title=r.get("title", ""),
                        snippet=r.get("snippet", "") or "",
                        provider=self.name,
                        published=r.get("date"),
                        raw=r,
                    )
                )
        elif endpoint_key == "images":
            items = data.get("images") or []
            for r in items[:count]:
                out.append(
                    SearchResult(
                        url=r.get("imageUrl") or r.get("link", ""),
                        title=r.get("title", "") or "",
                        snippet=r.get("source", "") or "",
                        provider=self.name,
                        raw=r,
                    )
                )
        elif endpoint_key == "videos":
            items = data.get("videos") or []
            for r in items[:count]:
                out.append(
                    SearchResult(
                        url=r.get("link", ""),
                        title=r.get("title", "") or "",
                        snippet=r.get("snippet", "") or r.get("source", "") or "",
                        provider=self.name,
                        published=r.get("date"),
                        raw=r,
                    )
                )
        elif endpoint_key == "shopping":
            items = data.get("shopping") or []
            for r in items[:count]:
                price = r.get("price") or ""
                out.append(
                    SearchResult(
                        url=r.get("link", ""),
                        title=r.get("title", "") or "",
                        snippet=f"{price} — {r.get('source', '')}".strip(" —"),
                        provider=self.name,
                        raw=r,
                    )
                )
        elif endpoint_key == "places":
            items = data.get("places") or []
            for r in items[:count]:
                addr = r.get("address", "") or ""
                rating = r.get("rating", "")
                out.append(
                    SearchResult(
                        url=r.get("website") or r.get("link", "") or f"https://maps.google.com/?q={r.get('title','')}",
                        title=r.get("title", "") or "",
                        snippet=(f"{addr} (★{rating})" if rating else addr).strip(),
                        provider=self.name,
                        raw=r,
                    )
                )
        elif endpoint_key == "scholar":
            items = data.get("organic") or []
            for r in items[:count]:
                out.append(
                    SearchResult(
                        url=r.get("link", ""),
                        title=r.get("title", "") or "",
                        snippet=r.get("snippet", "") or r.get("publicationInfo", "") or "",
                        provider=self.name,
                        published=r.get("year"),
                        raw=r,
                    )
                )
        else:
            items = data.get("organic") or []
            for r in items[:count]:
                out.append(
                    SearchResult(
                        url=r.get("link", ""),
                        title=r.get("title", ""),
                        snippet=r.get("snippet", "") or "",
                        provider=self.name,
                        score=float(r.get("position", 0) or 0) * -0.01,
                        published=r.get("date"),
                        raw=r,
                    )
                )
        return out
