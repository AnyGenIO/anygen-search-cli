"""Tool schema definitions for LLM integration.

``hsearch schema`` outputs these as JSON so any LLM agent can self-discover
how to call the CLI.
"""
from __future__ import annotations

import json
from typing import Any

from hsearch import __version__
from hsearch.router import ALL_MODES

SEARCH_SCHEMA: dict[str, Any] = {
    "name": "hsearch",
    "version": __version__,
    "description": (
        "Unified web search CLI over 6 commercial search APIs "
        "(Brave, Serper, Exa, Tavily, Firecrawl, Jina). "
        "Supports multi-provider fan-out, deduplication, content extraction, "
        "and structured JSON output. Install: pip install anygen-search-cli"
    ),
    "tools": [
        {
            "name": "search",
            "description": (
                "Run a web search across one or more providers. "
                "Returns structured JSON with results, metadata, and optional answer synthesis."
            ),
            "cli_usage": "hsearch search <query> [options]",
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query string.",
                        "cli_flag": "positional argument",
                    },
                    "provider": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["brave", "serper", "exa", "tavily", "firecrawl", "jina"],
                        },
                        "description": "Provider(s) to query. Repeat -p for multiple.",
                        "cli_flag": "--provider / -p",
                    },
                    "mode": {
                        "type": "string",
                        "enum": list(ALL_MODES),
                        "description": (
                            "Routing mode. 'default' uses tavily. 'news' uses brave+serper. "
                            "'academic' uses exa. 'fast' minimizes latency. 'recall' maximizes coverage. "
                            "'answer' enables Tavily answer synthesis."
                        ),
                        "cli_flag": "--mode / -m",
                    },
                    "top": {
                        "type": "integer",
                        "default": 10,
                        "description": "Max results per provider.",
                        "cli_flag": "--top / -n",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["json", "jsonl", "markdown", "table", "urls"],
                        "default": "json",
                        "description": "Output format. Use 'json' for programmatic access.",
                        "cli_flag": "--format / -f",
                    },
                    "time": {
                        "type": "string",
                        "description": "Time filter: day|week|month|year or YYYY-MM-DD..YYYY-MM-DD",
                        "cli_flag": "--time / -t",
                    },
                    "lang": {
                        "type": "string",
                        "description": "ISO 639-1 language code (en, zh, ja, ...)",
                        "cli_flag": "--lang / -l",
                    },
                    "region": {
                        "type": "string",
                        "description": "ISO 3166 country code (US, CN, JP, ...)",
                        "cli_flag": "--region / -r",
                    },
                    "location": {
                        "type": "string",
                        "description": "Provider location hint for local/geotargeted searches.",
                        "cli_flag": "--location",
                    },
                    "site": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Restrict to site(s). Repeatable.",
                        "cli_flag": "--site",
                    },
                    "exclude": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Exclude site(s). Repeatable.",
                        "cli_flag": "--exclude",
                    },
                    "answer": {
                        "type": "boolean",
                        "default": False,
                        "description": "Ask Tavily for a synthesized answer.",
                        "cli_flag": "--answer / -a",
                    },
                    "extract_top": {
                        "type": "integer",
                        "default": 0,
                        "description": "Extract full content from top N results.",
                        "cli_flag": "--extract-top",
                    },
                    "all": {
                        "type": "boolean",
                        "default": False,
                        "description": "Query every configured provider in parallel.",
                        "cli_flag": "--all",
                    },
                    "agent": {
                        "type": "boolean",
                        "default": False,
                        "description": "Agent-friendly preset: --format json --top 5.",
                        "cli_flag": "--agent",
                    },
                    "no_cache": {
                        "type": "boolean",
                        "default": False,
                        "description": "Disable result cache.",
                        "cli_flag": "--no-cache",
                    },
                    "cache_ttl": {
                        "type": "integer",
                        "description": "Override adaptive cache TTL in seconds.",
                        "cli_flag": "--cache-ttl",
                    },
                    "answer_depth": {
                        "type": "string",
                        "enum": ["basic", "advanced"],
                        "description": "Tavily answer detail level (requires --answer).",
                        "cli_flag": "--answer-depth",
                    },
                    "moderation": {
                        "type": "boolean",
                        "default": False,
                        "description": "Exa: enable content moderation to filter unsafe results.",
                        "cli_flag": "--moderation",
                    },
                    "livecrawl_timeout": {
                        "type": "integer",
                        "description": "Exa: livecrawl timeout in milliseconds.",
                        "cli_flag": "--livecrawl-timeout",
                    },
                    "goggles": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Brave: Goggle URL or inline definition.",
                        "cli_flag": "--goggles",
                    },
                    "serper_type": {
                        "type": "string",
                        "enum": ["search", "news", "images", "videos", "shopping", "places", "scholar", "patents"],
                        "description": "Serper endpoint override.",
                        "cli_flag": "--serper-type",
                    },
                    "include_images": {
                        "type": "boolean",
                        "default": False,
                        "description": "Tavily: include query/result images.",
                        "cli_flag": "--include-images",
                    },
                    "ignore_invalid_urls": {
                        "type": "boolean",
                        "default": False,
                        "description": "Firecrawl: filter out URLs invalid for follow-on scrape endpoints.",
                        "cli_flag": "--ignore-invalid-urls",
                    },
                    "safe_search": {
                        "type": "boolean",
                        "default": False,
                        "description": "Tavily: filter adult/unsafe content (Enterprise only).",
                        "cli_flag": "--safe-search",
                    },
                    "project_id": {
                        "type": "string",
                        "description": "Tavily: X-Project-ID for per-project usage tracking.",
                        "cli_flag": "--project-id",
                    },
                    "firecrawl_clean_content": {
                        "type": "boolean",
                        "default": False,
                        "description": "Firecrawl: LLM-based boilerplate cleanup (beta).",
                        "cli_flag": "--firecrawl-clean-content",
                    },
                    "firecrawl_question": {
                        "type": "string",
                        "description": "Firecrawl: ask a question about each scraped page.",
                        "cli_flag": "--firecrawl-question",
                    },
                    "highlights_query": {
                        "type": "string",
                        "description": "Firecrawl/Exa: relevance query for highlights extraction.",
                        "cli_flag": "--highlights-query",
                    },
                },
            },
            "output_schema": {
                "type": "object",
                "properties": {
                    "meta": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "mode": {"type": "string"},
                            "providers_queried": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "total_results": {"type": "integer"},
                            "cache_ttl_seconds": {"type": "integer"},
                            "answer": {
                                "type": "string",
                                "description": "Aggregated answer from providers (Tavily, Serper answerBox, Brave summarizer)",
                            },
                            "related_searches": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Related search queries from Serper/Brave (up to 10)",
                            },
                            "fallback_providers": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Providers that were used as fallback when primary providers failed",
                            },
                        },
                    },
                    "results": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "url": {"type": "string"},
                                "title": {"type": "string"},
                                "snippet": {"type": "string"},
                                "provider": {"type": "string"},
                                "score": {
                                    "type": "number",
                                    "description": "RRF (Reciprocal Rank Fusion) score — scale-invariant cross-provider ranking",
                                },
                                "published": {"type": ["string", "null"]},
                                "sources": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "content": {
                                    "type": ["string", "null"],
                                    "description": "Full page content (when --extract-top or --raw is used)",
                                },
                            },
                        },
                    },
                    "errors": {
                        "type": "object",
                        "description": "Provider name → error message, if any provider failed.",
                    },
                },
            },
            "examples": [
                {
                    "description": "Basic search",
                    "command": 'hsearch search "Python async tutorial" --agent',
                },
                {
                    "description": "News search with time filter",
                    "command": 'hsearch search "AI regulation" --mode news --time week --agent',
                },
                {
                    "description": "Get answer + search results",
                    "command": 'hsearch search "what is quantum computing" --answer --agent',
                },
                {
                    "description": "Multi-provider with content extraction",
                    "command": 'hsearch search "React hooks" -p tavily -p brave --extract-top 3 --agent',
                },
                {
                    "description": "Academic search",
                    "command": 'hsearch search "transformer architecture" --mode academic --agent',
                },
                {
                    "description": "Site-restricted search",
                    "command": 'hsearch search "deployment guide" --site docs.aws.amazon.com --agent',
                },
                {
                    "description": "Finance search with advanced answer",
                    "command": 'hsearch search "AAPL earnings Q1 2026" --mode finance --agent',
                },
                {
                    "description": "High-recall multi-provider search",
                    "command": 'hsearch search "new battery technology 2026" --mode recall --agent',
                },
            ],
        },
        {
            "name": "extract",
            "description": "Fetch one or more URLs and return clean markdown/text content.",
            "cli_usage": "hsearch extract <url1> [url2 ...] [options]",
            "parameters": {
                "type": "object",
                "required": ["urls"],
                "properties": {
                    "urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "One or more URLs to extract content from.",
                        "cli_flag": "positional arguments",
                    },
                    "provider": {
                        "type": "string",
                        "enum": ["jina", "firecrawl"],
                        "default": "jina",
                        "description": "Extraction provider.",
                        "cli_flag": "--provider / -p",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["json", "markdown"],
                        "default": "json",
                        "description": "Output format.",
                        "cli_flag": "--format / -f",
                    },
                },
            },
            "examples": [
                {
                    "description": "Extract content from a URL",
                    "command": 'hsearch extract "https://example.com/article" --format json',
                },
            ],
        },
        {
            "name": "answer",
            "description": "Get an LLM-generated answer with citations from Exa's /answer endpoint.",
            "cli_usage": "hsearch answer <query> [options]",
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The question to answer.",
                        "cli_flag": "positional argument",
                    },
                    "text": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include full text content in citations.",
                        "cli_flag": "--text",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["json", "markdown"],
                        "default": "json",
                        "description": "Output format.",
                        "cli_flag": "--format / -f",
                    },
                },
            },
            "examples": [
                {
                    "description": "Get a direct answer",
                    "command": 'hsearch answer "What is the latest valuation of SpaceX?"',
                },
                {
                    "description": "Answer with full citation text",
                    "command": 'hsearch answer "How does RAG work?" --text -f json',
                },
            ],
        },
        {
            "name": "ground",
            "description": "Fact-check a statement using Jina's Grounding API (g.jina.ai). Returns factuality score, boolean verdict, reasoning, and web references.",
            "cli_usage": "hsearch ground <statement> [options]",
            "parameters": {
                "type": "object",
                "required": ["statement"],
                "properties": {
                    "statement": {
                        "type": "string",
                        "description": "The claim or statement to fact-check.",
                        "cli_flag": "positional argument",
                    },
                    "no_cache": {
                        "type": "boolean",
                        "default": False,
                        "description": "Bypass Jina cache for fresh results.",
                        "cli_flag": "--no-cache",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["json", "markdown"],
                        "default": "json",
                        "description": "Output format.",
                        "cli_flag": "--format / -f",
                    },
                },
            },
            "examples": [
                {
                    "description": "Fact-check a claim",
                    "command": 'hsearch ground "The Eiffel Tower is 330 meters tall"',
                },
                {
                    "description": "Fact-check with JSON output",
                    "command": 'hsearch ground "Python 4.0 was released in 2025" -f json',
                },
            ],
        },
        {
            "name": "similar",
            "description": "Find pages semantically similar to a given URL using Exa's /findSimilar endpoint.",
            "cli_usage": "hsearch similar <url> [options]",
            "parameters": {
                "type": "object",
                "required": ["url"],
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The reference URL to find similar pages for.",
                        "cli_flag": "positional argument",
                    },
                    "top": {
                        "type": "integer",
                        "default": 10,
                        "description": "Max results.",
                        "cli_flag": "--top / -n",
                    },
                    "text": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include full text content.",
                        "cli_flag": "--text",
                    },
                    "highlights": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include highlight excerpts.",
                        "cli_flag": "--highlights",
                    },
                    "summary": {
                        "type": "boolean",
                        "default": False,
                        "description": "Include LLM summaries.",
                        "cli_flag": "--summary",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["json", "table", "markdown", "urls"],
                        "default": "json",
                        "description": "Output format.",
                        "cli_flag": "--format / -f",
                    },
                },
            },
            "examples": [
                {
                    "description": "Find similar pages",
                    "command": 'hsearch similar "https://example.com/article" --top 5',
                },
            ],
        },
        {
            "name": "providers",
            "description": "List all providers and their configuration status (which API keys are set).",
            "cli_usage": "hsearch providers",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "schema",
            "description": "Output this tool schema as JSON for LLM self-discovery.",
            "cli_usage": "hsearch schema",
            "parameters": {"type": "object", "properties": {}},
        },
    ],
    "install": "pip install anygen-search-cli",
    "env_vars": {
        "SERPER_API_KEY": "Serper.dev API key",
        "TAVILY_API_KEY": "Tavily API key",
        "BRAVE_API_KEY": "Brave Search API key",
        "EXA_API_KEY": "Exa API key",
        "FIRECRAWL_API_KEY": "Firecrawl API key",
        "JINA_API_KEY": "Jina API key",
    },
    "tips_for_llm": [
        "Always use --agent flag for structured JSON output with sensible defaults.",
        "Use --mode to pick the right provider combo: 'news' for current events, 'academic' for papers, 'fast' for speed, 'finance' for financial data, 'recall' for maximum coverage.",
        "Use --answer to get a synthesized answer aggregated from Tavily, Serper answerBox, and Brave summarizer.",
        "Use --extract-top N to get full page content for the top N results.",
        "Results are ranked using RRF (Reciprocal Rank Fusion) — multi-source results automatically rank higher.",
        "Check meta.related_searches for query expansion ideas from Google/Brave.",
        "If a provider fails, fallback providers are automatically queried — check meta.fallback_providers.",
        "Serper results include [Knowledge], [PAA], [Answer] tagged results from Google SERP features.",
        "Brave results include [Info], [FAQ], and discussion forum results for richer recall.",
        "Errors are in stderr, structured JSON is in stdout — parse stdout only.",
        "Use 'hsearch schema' to get this schema programmatically.",
        "Use --moderation with Exa to filter unsafe content.",
        "Use 'hsearch answer' for direct Q&A with citations (powered by Exa).",
        "Use 'hsearch ground' to fact-check claims against the live web (powered by Jina g.jina.ai).",
        "Use 'hsearch similar' to find pages semantically related to a URL (powered by Exa /findSimilar).",
        "Use --mode context for Brave LLM Context endpoint — pre-extracted grounding snippets for RAG.",
    ],
}


def render_schema() -> str:
    return json.dumps(SEARCH_SCHEMA, indent=2, ensure_ascii=False)
