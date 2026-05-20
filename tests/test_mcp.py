from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx

pytest.importorskip("mcp")

from hsearch import mcp_server


def test_mcp_server_tools_are_registered():
    server = mcp_server.build_server()
    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}
    assert {"search", "extract", "providers", "schema"} <= names


def test_mcp_search_tool_returns_cli_json_shape():
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://api.search.brave.com/res/v1/web/search").mock(
            return_value=httpx.Response(
                200,
                json={
                    "web": {
                        "results": [
                            {
                                "url": "https://b.test/1",
                                "title": "B1",
                                "description": "snippet",
                            }
                        ]
                    }
                },
            )
        )
        payload = asyncio.run(
            mcp_server.search("x", provider="brave", top=1, no_cache=True)
        )

    assert payload["meta"]["providers_queried"] == ["brave"]
    assert payload["meta"]["cache_ttl_seconds"] == 3600
    assert payload["results"][0]["url"] == "https://b.test/1"


def test_mcp_extract_tool_returns_cli_json_shape():
    with respx.mock(assert_all_called=True) as mock:
        mock.get("https://r.jina.ai/https://example.com").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"content": "# extracted"}},
            )
        )
        payload = asyncio.run(
            mcp_server.extract("https://example.com", provider="jina")
        )

    assert payload["meta"]["provider"] == "jina"
    assert payload["meta"]["urls_succeeded"] == 1
    assert payload["results"] == [{"url": "https://example.com", "content": "# extracted"}]


def test_mcp_schema_and_providers_are_dicts():
    provider_payload = mcp_server.providers()
    schema_payload = mcp_server.schema()
    assert "providers" in provider_payload
    assert "tools" in schema_payload
    assert json.dumps(schema_payload)
