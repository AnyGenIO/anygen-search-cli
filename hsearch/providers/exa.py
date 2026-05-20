"""Exa neural search. Docs: https://exa.ai/docs/reference/search"""
from __future__ import annotations

from typing import Any

from hsearch.models import SearchResult
from hsearch.providers.base import SearchProvider

ENDPOINT = "https://api.exa.ai/search"


class ExaProvider(SearchProvider):
    name = "exa"
    requires_env = ["EXA_API_KEY"]

    async def _search(self, query: str, count: int = 10, **kwargs: Any) -> list[SearchResult]:
        payload: dict[str, Any] = {
            "query": query,
            "numResults": max(1, min(count, 100)),
            "type": kwargs.get("type", "auto"),
        }
        if kwargs.get("additional_queries"):
            payload["additionalQueries"] = kwargs["additional_queries"]
        if kwargs.get("system_prompt"):
            payload["systemPrompt"] = kwargs["system_prompt"]
        if kwargs.get("user_location"):
            payload["userLocation"] = kwargs["user_location"]
        if kwargs.get("moderation"):
            payload["moderation"] = True

        contents: dict[str, Any] = {}

        if kwargs.get("highlights", True):
            if kwargs.get("highlights_query") or kwargs.get("highlights_max_characters"):
                h: dict[str, Any] = {}
                if kwargs.get("highlights_query"):
                    h["query"] = kwargs["highlights_query"]
                if kwargs.get("highlights_max_characters") is not None:
                    try:
                        h["maxCharacters"] = int(kwargs["highlights_max_characters"])
                    except (TypeError, ValueError):
                        pass
                contents["highlights"] = h or True
            else:
                contents["highlights"] = True

        if kwargs.get("with_content") or kwargs.get("text"):
            text_opts: dict[str, Any] = {}
            max_chars = kwargs.get("text_max_characters", 1000)
            try:
                text_opts["maxCharacters"] = int(max_chars)
            except (TypeError, ValueError):
                pass
            if kwargs.get("text_verbosity"):
                text_opts["verbosity"] = kwargs["text_verbosity"]
            if kwargs.get("include_html_tags"):
                text_opts["includeHtmlTags"] = True
            if kwargs.get("include_sections"):
                text_opts["includeSections"] = kwargs["include_sections"]
            if kwargs.get("exclude_sections"):
                text_opts["excludeSections"] = kwargs["exclude_sections"]
            contents["text"] = text_opts or True

        if kwargs.get("summary_query"):
            contents["summary"] = {"query": kwargs["summary_query"]}
        elif kwargs.get("summary"):
            contents["summary"] = {} if kwargs["summary"] is True else kwargs["summary"]

        if kwargs.get("max_age_hours") is not None:
            try:
                contents["maxAgeHours"] = int(kwargs["max_age_hours"])
            except (TypeError, ValueError):
                pass
        elif kwargs.get("livecrawl"):
            legacy = str(kwargs["livecrawl"]).lower()
            if legacy in {"always", "preferred"}:
                contents["maxAgeHours"] = 0
            elif legacy == "never":
                contents["maxAgeHours"] = -1
        if kwargs.get("livecrawl_timeout") is not None:
            try:
                contents["livecrawlTimeout"] = int(kwargs["livecrawl_timeout"])
            except (TypeError, ValueError):
                pass
        if kwargs.get("subpages") is not None:
            try:
                contents["subpages"] = int(kwargs["subpages"])
            except (TypeError, ValueError):
                pass
        if kwargs.get("subpage_target"):
            contents["subpageTarget"] = kwargs["subpage_target"]

        extras: dict[str, Any] = {}
        if kwargs.get("extras"):
            extras = kwargs["extras"] if isinstance(kwargs["extras"], dict) else {}
        if kwargs.get("extras_links") is not None:
            try:
                extras["links"] = int(kwargs["extras_links"])
            except (TypeError, ValueError):
                pass
        if kwargs.get("extras_image_links") is not None:
            try:
                extras["imageLinks"] = int(kwargs["extras_image_links"])
            except (TypeError, ValueError):
                pass
        if extras:
            contents["extras"] = extras
        if contents:
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
        if kwargs.get("start_crawl_date"):
            payload["startCrawlDate"] = kwargs["start_crawl_date"]
        if kwargs.get("end_crawl_date"):
            payload["endCrawlDate"] = kwargs["end_crawl_date"]

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
                    content=text if isinstance(text, str) and text else None,
                    summary=summary_val if isinstance(summary_val, str) else None,
                    favicon=r.get("favicon") if isinstance(r.get("favicon"), str) else None,
                    author=r.get("author") if isinstance(r.get("author"), str) else None,
                    image=r.get("image") if isinstance(r.get("image"), str) else None,
                    raw=r,
                )
            )
        return out
