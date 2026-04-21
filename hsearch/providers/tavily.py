"""Tavily Search. Docs: https://docs.tavily.com/documentation/api-reference/endpoint/search"""
from __future__ import annotations

from typing import Any

from hsearch.models import SearchResult
from hsearch.providers.base import SearchProvider

ENDPOINT = "https://api.tavily.com/search"


class TavilyProvider(SearchProvider):
    name = "tavily"
    requires_env = ["TAVILY_API_KEY"]

    # Last raw response (so callers like `--answer` can grab tavily's answer field).
    _last_answer: str | None = None
    _last_images: list[Any] | None = None

    async def _search(self, query: str, count: int = 10, **kwargs: Any) -> list[SearchResult]:
        payload: dict[str, Any] = {
            "query": query,
            "max_results": max(1, min(count, 20)),
            "search_depth": kwargs.get("search_depth", "basic"),
            "topic": kwargs.get("topic", "general"),
        }
        # ---- v0.2 new params ----------------------------------------------
        if "auto_parameters" in kwargs and kwargs["auto_parameters"] is not None:
            payload["auto_parameters"] = bool(kwargs["auto_parameters"])
        if kwargs.get("chunks_per_source") is not None:
            try:
                payload["chunks_per_source"] = int(kwargs["chunks_per_source"])
            except (TypeError, ValueError):
                pass
        if "include_raw_content" in kwargs and kwargs["include_raw_content"] is not None:
            payload["include_raw_content"] = kwargs["include_raw_content"]
        if kwargs.get("days") is not None:
            try:
                payload["days"] = int(kwargs["days"])
            except (TypeError, ValueError):
                pass
        if kwargs.get("include_images"):
            payload["include_images"] = True
        if kwargs.get("include_image_descriptions"):
            payload["include_image_descriptions"] = True
        # ---- existing optional params -------------------------------------
        if kwargs.get("include_answer"):
            payload["include_answer"] = kwargs["include_answer"]
        if kwargs.get("time_range"):
            payload["time_range"] = kwargs["time_range"]
        if kwargs.get("country"):
            payload["country"] = kwargs["country"]
        if kwargs.get("include_domains"):
            payload["include_domains"] = kwargs["include_domains"]
        if kwargs.get("exclude_domains"):
            payload["exclude_domains"] = kwargs["exclude_domains"]

        headers = {
            "Authorization": f"Bearer {self.api_key or ''}",
            "Content-Type": "application/json",
        }
        resp = await self._request("POST", ENDPOINT, headers=headers, json=payload)
        data = resp.json()

        # Stash answer/images on the instance for ``--answer`` consumers.
        self._last_answer = data.get("answer")
        self._last_images = data.get("images")

        out: list[SearchResult] = []
        for r in (data.get("results") or [])[:count]:
            raw_content = r.get("raw_content")
            out.append(
                SearchResult(
                    url=r.get("url", ""),
                    title=r.get("title", ""),
                    snippet=r.get("content", "") or "",
                    provider=self.name,
                    score=float(r.get("score") or 0.0),
                    published=r.get("published_date"),
                    content=raw_content if isinstance(raw_content, str) else None,
                    raw=r,
                )
            )
        return out
