"""Exa neural search. Docs: https://docs.exa.ai/reference/search"""
from __future__ import annotations

from typing import Any

from hsearch.models import SearchResult
from hsearch.providers.base import SearchProvider

ENDPOINT = "https://api.exa.ai/search"


class ExaProvider(SearchProvider):
    name = "exa"
    requires_env = ["EXA_API_KEY"]

    async def _search(self, query: str, count: int = 10, **kwargs: Any) -> list[SearchResult]:
        # `type` is now passed through verbatim to support new values
        # (`fast`, `instant`, `deep-reasoning`, `deep-lite`, `deep`, etc.).
        payload: dict[str, Any] = {
            "query": query,
            "numResults": max(1, min(count, 100)),
            "type": kwargs.get("type", "auto"),
        }
        if kwargs.get("use_autoprompt"):
            payload["useAutoprompt"] = True

        # ---- contents block (text, summary, livecrawl, subpages) ---------
        contents: dict[str, Any] = {"text": {"maxCharacters": 500}}

        # `summary=True` -> {} so Exa picks defaults; `summary_query="..."` -> {"query": ...}
        if kwargs.get("summary_query"):
            contents["summary"] = {"query": kwargs["summary_query"]}
        elif kwargs.get("summary"):
            contents["summary"] = {} if kwargs["summary"] is True else kwargs["summary"]

        if kwargs.get("livecrawl"):
            contents["livecrawl"] = kwargs["livecrawl"]
        if kwargs.get("subpages") is not None:
            try:
                contents["subpages"] = int(kwargs["subpages"])
            except (TypeError, ValueError):
                pass
        if kwargs.get("subpage_target"):
            contents["subpage_target"] = kwargs["subpage_target"]
        payload["contents"] = contents

        if kwargs.get("category"):
            payload["category"] = kwargs["category"]
        if kwargs.get("include_domains"):
            payload["includeDomains"] = kwargs["include_domains"]
        if kwargs.get("exclude_domains"):
            payload["excludeDomains"] = kwargs["exclude_domains"]
        if kwargs.get("start_published_date"):
            payload["startPublishedDate"] = kwargs["start_published_date"]
        if kwargs.get("end_published_date"):
            payload["endPublishedDate"] = kwargs["end_published_date"]

        headers = {
            "x-api-key": self.api_key or "",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        resp = await self._request("POST", ENDPOINT, headers=headers, json=payload)
        data = resp.json()

        out: list[SearchResult] = []
        for r in (data.get("results") or [])[:count]:
            text = r.get("text") or ""
            highlights = r.get("highlights") or []
            snippet = (highlights[0] if highlights else text)[:500]
            summary_val = r.get("summary")
            if isinstance(summary_val, dict):
                summary_val = summary_val.get("text") or summary_val.get("summary")
            out.append(
                SearchResult(
                    url=r.get("url", ""),
                    title=r.get("title") or r.get("url", ""),
                    snippet=snippet,
                    provider=self.name,
                    score=float(r.get("score") or 0.0),
                    published=r.get("publishedDate"),
                    summary=summary_val if isinstance(summary_val, str) else None,
                    raw=r,
                )
            )
        return out
