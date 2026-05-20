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
                            "answer": {
                                "type": "string",
                                "description": "Tavily synthesized answer (when --answer is used)",
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
                                "score": {"type": "number"},
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
        "Use --mode to pick the right provider combo: 'news' for current events, 'academic' for papers, 'fast' for speed.",
        "Use --answer to get a synthesized answer from Tavily (good for factual questions).",
        "Use --extract-top N to get full page content for the top N results.",
        "Errors are in stderr, structured JSON is in stdout — parse stdout only.",
        "Use 'hsearch schema' to get this schema programmatically.",
    ],
}


def render_schema() -> str:
    return json.dumps(SEARCH_SCHEMA, indent=2, ensure_ascii=False)
