"""Jina s.jina.ai search + r.jina.ai reader. Docs: https://jina.ai/reader/"""
from __future__ import annotations

from typing import Any

from hsearch.models import SearchResult
from hsearch.providers.base import SearchProvider

SEARCH_ENDPOINT = "https://s.jina.ai/"
READER_BASE = "https://r.jina.ai/"


class JinaProvider(SearchProvider):
    name = "jina"
    requires_env = ["JINA_API_KEY"]
    supports_extract = True

    def _headers(self, *, json_resp: bool = True, no_content: bool = True) -> dict[str, str]:
        h = {
            "Authorization": f"Bearer {self.api_key or ''}",
            "Accept": "application/json" if json_resp else "text/plain",
        }
        # Search-only mode (skip page fetch) is much faster + cheaper.
        if no_content:
            h["X-Respond-With"] = "no-content"
        return h

    async def _search(self, query: str, count: int = 10, **kwargs: Any) -> list[SearchResult]:
        # POST form to s.jina.ai with `q` body for arbitrary queries (avoids URL-encoding issues).
        headers = self._headers(json_resp=True, no_content=not kwargs.get("with_content", False))
        headers["Content-Type"] = "application/json"
        # ---- v0.2 new pass-through headers --------------------------------
        if kwargs.get("site"):
            headers["X-Site"] = str(kwargs["site"])
        if kwargs.get("engine"):
            headers["X-Engine"] = str(kwargs["engine"])
        if kwargs.get("locale"):
            headers["X-Locale"] = str(kwargs["locale"])
        if kwargs.get("no_cache"):
            headers["X-No-Cache"] = "true"
        payload = {"q": query}
        resp = await self._request("POST", SEARCH_ENDPOINT, headers=headers, json=payload)
        body = resp.json()
        # Jina JSON shape: { "code": 200, "data": [ { "title", "url", "description", ... }, ... ] }
        items = body.get("data") or []
        if isinstance(items, dict):
            items = items.get("results") or []

        out: list[SearchResult] = []
        for r in items[:count]:
            if not isinstance(r, dict):
                continue
            out.append(
                SearchResult(
                    url=r.get("url", "") or r.get("link", ""),
                    title=r.get("title", "") or "",
                    snippet=r.get("description", "")
                    or (r.get("content", "") or "")[:500],
                    provider=self.name,
                    published=r.get("date"),
                    raw=r,
                )
            )
        return out

    async def _extract(self, url: str) -> str | None:
        headers = {
            "Authorization": f"Bearer {self.api_key or ''}",
            "Accept": "application/json",
            "X-Return-Format": "markdown",
        }
        resp = await self._request("GET", f"{READER_BASE}{url}", headers=headers)
        try:
            body = resp.json()
            return ((body.get("data") or {}).get("content")) or None
        except Exception:
            return resp.text or None
