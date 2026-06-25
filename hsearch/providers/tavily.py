"""Tavily Search. Docs: https://docs.tavily.com/documentation/api-reference/endpoint/search"""
from __future__ import annotations

import asyncio
import os
from typing import Any

from hsearch.models import SearchResult
from hsearch.providers.base import SearchProvider

ENDPOINT = "https://api.tavily.com/search"
RESEARCH_ENDPOINT = "https://api.tavily.com/research"
EXTRACT_ENDPOINT = "https://api.tavily.com/extract"

# Tavily search_depth options as of 2026-04 (added: fast, ultra-fast).
# basic / advanced were the original two; fast / ultra-fast trade relevance for latency.
_VALID_DEPTHS = {"basic", "advanced", "fast", "ultra-fast"}
_VALID_TOPICS = {"general", "news", "finance"}
# Tavily extract endpoint options.
_VALID_EXTRACT_DEPTHS = {"basic", "advanced"}
_VALID_EXTRACT_FORMATS = {"markdown", "text"}


class TavilyProvider(SearchProvider):
    name = "tavily"
    requires_env = ["TAVILY_API_KEY"]
    supports_extract = True

    # Last raw response (so callers like `--answer` can grab tavily's answer field).
    _last_answer: str | None = None
    _last_images: list[Any] | None = None
    _last_usage: dict[str, Any] | None = None

    async def _search(self, query: str, count: int = 10, **kwargs: Any) -> list[SearchResult]:
        depth = kwargs.get("search_depth", "basic")
        if depth not in _VALID_DEPTHS:
            depth = "basic"
        topic = kwargs.get("topic", "general")
        if topic not in _VALID_TOPICS:
            topic = "general"
        payload: dict[str, Any] = {
            "query": query,
            "max_results": max(1, min(count, 20)),
            "search_depth": depth,
            "topic": topic,
        }
        # ---- v0.2 new params ----------------------------------------------
        if "auto_parameters" in kwargs and kwargs["auto_parameters"] is not None:
            payload["auto_parameters"] = bool(kwargs["auto_parameters"])
        if kwargs.get("chunks_per_source") is not None:
            try:
                payload["chunks_per_source"] = min(max(int(kwargs["chunks_per_source"]), 1), 3)
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
        # ---- 2026-04 new params (Tavily community announcements) ----------
        if kwargs.get("exact_match"):
            payload["exact_match"] = True
        if kwargs.get("include_favicon"):
            payload["include_favicon"] = True
        if kwargs.get("include_usage"):
            payload["include_usage"] = True
        if kwargs.get("safe_search"):
            payload["safe_search"] = True
        # ---- existing optional params -------------------------------------
        inc_answer = kwargs.get("include_answer")
        if inc_answer:
            if isinstance(inc_answer, str) and inc_answer in ("basic", "advanced"):
                payload["include_answer"] = inc_answer
            else:
                payload["include_answer"] = True
        if kwargs.get("time_range"):
            payload["time_range"] = kwargs["time_range"]
        if kwargs.get("start_date"):
            payload["start_date"] = kwargs["start_date"]
        if kwargs.get("end_date"):
            payload["end_date"] = kwargs["end_date"]
        if kwargs.get("country"):
            payload["country"] = kwargs["country"]
        if kwargs.get("include_domains"):
            payload["include_domains"] = kwargs["include_domains"]
        if kwargs.get("exclude_domains"):
            payload["exclude_domains"] = kwargs["exclude_domains"]

        headers: dict[str, str] = {
            "Authorization": f"Bearer {self.api_key or ''}",
            "Content-Type": "application/json",
        }
        project_id = kwargs.get("project_id") or os.environ.get("TAVILY_PROJECT")
        if project_id:
            headers["X-Project-ID"] = str(project_id)
        resp = await self._request("POST", ENDPOINT, headers=headers, json=payload)
        data = resp.json()

        # Stash answer/images/usage on the instance for ``--answer``/``--include-usage`` consumers.
        self._last_answer = data.get("answer")
        self._last_images = data.get("images")
        self._last_usage = data.get("usage") if isinstance(data.get("usage"), dict) else None

        out: list[SearchResult] = []
        for r in (data.get("results") or [])[:count]:
            raw_content = r.get("raw_content")
            favicon = r.get("favicon") if isinstance(r.get("favicon"), str) else None
            image = None
            images = r.get("images")
            if isinstance(images, list) and images:
                first = images[0]
                if isinstance(first, dict):
                    image = first.get("url")
                elif isinstance(first, str):
                    image = first
            out.append(
                SearchResult(
                    url=r.get("url", ""),
                    title=r.get("title", ""),
                    snippet=r.get("content", "") or "",
                    provider=self.name,
                    score=float(r.get("score") or 0.0),
                    published=r.get("published_date"),
                    content=raw_content if isinstance(raw_content, str) else None,
                    favicon=favicon,
                    image=image if isinstance(image, str) else None,
                    raw=r,
                )
            )
        return out

    # ------------------------------------------------------------------
    # Research API (async deep-research agent). Docs:
    # https://docs.tavily.com/documentation/api-reference/endpoint/research
    # ------------------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Authorization": f"Bearer {self.api_key or ''}",
            "Content-Type": "application/json",
        }
        project_id = os.environ.get("TAVILY_PROJECT")
        if project_id:
            headers["X-Project-ID"] = project_id
        return headers

    async def research_create(self, input_text: str, **kwargs: Any) -> dict[str, Any]:
        """POST /research — create an async research task. Returns {request_id, status, ...}."""
        if not self.is_configured():
            from hsearch.providers.base import ProviderAuthError

            raise ProviderAuthError(f"{self.name}: missing env {','.join(self.requires_env)}")
        payload: dict[str, Any] = {"input": input_text}
        model = kwargs.get("model")
        if model in ("mini", "pro", "auto"):
            payload["model"] = model
        if kwargs.get("output_schema"):
            payload["output_schema"] = kwargs["output_schema"]
        citation_format = kwargs.get("citation_format")
        if citation_format in ("numbered", "mla", "apa", "chicago"):
            payload["citation_format"] = citation_format
        if kwargs.get("output_length"):
            payload["output_length"] = kwargs["output_length"]
        if kwargs.get("include_domains"):
            payload["include_domains"] = kwargs["include_domains"]
        if kwargs.get("exclude_domains"):
            payload["exclude_domains"] = kwargs["exclude_domains"]
        resp = await self._request(
            "POST", RESEARCH_ENDPOINT, headers=self._auth_headers(), json=payload
        )
        return resp.json()

    async def research_get(self, request_id: str) -> dict[str, Any]:
        """GET /research/{id} — poll a research task's status/result."""
        if not self.is_configured():
            from hsearch.providers.base import ProviderAuthError

            raise ProviderAuthError(f"{self.name}: missing env {','.join(self.requires_env)}")
        resp = await self._request(
            "GET", f"{RESEARCH_ENDPOINT}/{request_id}", headers=self._auth_headers()
        )
        return resp.json()

    async def research(
        self,
        input_text: str,
        *,
        poll_interval: float = 5.0,
        timeout: float = 600.0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a research task and poll until completed/failed or timeout.

        Returns the final GET /research/{id} payload (contains ``content`` +
        ``sources`` on success). Raises TimeoutError when the deadline passes.
        """
        created = await self.research_create(input_text, **kwargs)
        request_id = created.get("request_id") or created.get("id")
        if not request_id:
            # API contract drift — surface the raw creation payload for debugging.
            return created
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout
        last: dict[str, Any] = created
        while loop.time() < deadline:
            await asyncio.sleep(poll_interval)
            last = await self.research_get(str(request_id))
            status = (last.get("status") or "").lower()
            if status in ("completed", "failed", "error", "cancelled"):
                return last
        raise TimeoutError(
            f"tavily research task {request_id} still '{last.get('status')}' after {timeout:.0f}s"
        )

    # ------------------------------------------------------------------
    # Extract API (clean page content + optional query-based reranking).
    # Docs: https://docs.tavily.com/documentation/api-reference/endpoint/extract
    # ------------------------------------------------------------------

    async def extract_with_options(self, url: str, **kwargs: Any) -> str | None:
        """POST /extract — return clean page content for a single URL.

        Supports ``extract_depth`` (basic|advanced — advanced retrieves tables /
        embedded content), ``format`` (markdown|text), and ``query`` (rerank the
        extracted chunks by relevance to this intent).
        """
        if not self.is_configured():
            from hsearch.providers.base import ProviderAuthError

            raise ProviderAuthError(f"{self.name}: missing env {','.join(self.requires_env)}")
        payload: dict[str, Any] = {"urls": [url]}
        depth = kwargs.get("extract_depth")
        if depth in _VALID_EXTRACT_DEPTHS:
            payload["extract_depth"] = depth
        fmt = kwargs.get("format")
        if fmt in _VALID_EXTRACT_FORMATS:
            payload["format"] = fmt
        if kwargs.get("query"):
            payload["query"] = kwargs["query"]
        if kwargs.get("include_images"):
            payload["include_images"] = True
        if kwargs.get("include_favicon"):
            payload["include_favicon"] = True
        resp = await self._request(
            "POST", EXTRACT_ENDPOINT, headers=self._auth_headers(), json=payload
        )
        data = resp.json()
        results = data.get("results") or []
        if not results or not isinstance(results, list):
            return None
        first = results[0]
        if not isinstance(first, dict):
            return None
        content = first.get("raw_content") or first.get("content")
        return content if isinstance(content, str) and content else None

    async def _extract(self, url: str) -> str | None:
        """Default extract hook — clean markdown via Tavily /extract (basic depth)."""
        return await self.extract_with_options(url, extract_depth="basic", format="markdown")
