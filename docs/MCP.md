# hsearch MCP server

`hsearch mcp` starts a stdio MCP server that exposes hsearch search,
extraction, provider discovery, and schema tools to MCP-aware clients.

Install the optional dependency first:

```bash
cd /home/chenshangshang/hermes-search
python -m pip install -e ".[mcp]"
```

The server reserves stdout for MCP transport frames. Any diagnostics go to
stderr so MCP clients can parse stdout safely.

## Tools

- `search(query, mode?, provider?, top?, time?, lang?, region?, site?, exclude?, answer?, summary?, max_age_hours?, depth?, ...)`
  returns the same JSON shape as `hsearch search --format json`.
- `extract(url, provider?)` returns the same JSON shape as
  `hsearch extract --format json`.
- `providers()` returns all providers plus API-key configuration status.
- `schema()` returns the same JSON document as `hsearch schema`.

## Claude Desktop

Add this to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "hsearch": {
      "command": "/home/chenshangshang/hermes-search/.venv/bin/hsearch",
      "args": ["mcp"]
    }
  }
}
```

## Codex

Add this to `~/.codex/config.toml`:

```toml
[mcp_servers.hsearch]
command = "/home/chenshangshang/hermes-search/.venv/bin/hsearch"
args = ["mcp"]
```

## Smoke Tests

List tools over stdio:

```bash
{
  printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}\n'
  printf '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}\n'
  printf '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n'
} | /home/chenshangshang/hermes-search/.venv/bin/hsearch mcp
```

Run normal CLI help without MCP installed:

```bash
/home/chenshangshang/hermes-search/.venv/bin/hsearch mcp --help
```

If the optional extra is missing, invoking `hsearch mcp` prints:

```text
Install MCP support with: pip install -e ".[mcp]"
```
