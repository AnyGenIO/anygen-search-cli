# Drop-in agent skill for `hsearch`

If you're running an LLM agent (Claude Code, [Hermes Agent](https://github.com/NousResearch/hermes-agent), or any agent
that supports markdown "skills" / "system prompts"), this file is the
**ready-to-use skill** that teaches the agent to use `hsearch` instead of
ad-hoc HTTP calls.

## Install (Claude Code / Hermes Agent)

```bash
# Claude Code
mkdir -p ~/.claude/skills/hsearch
curl -fsSL https://raw.githubusercontent.com/AnyGenIO/anygen-search-cli/main/docs/SKILL.md \
  -o ~/.claude/skills/hsearch/SKILL.md

# Hermes Agent
mkdir -p ~/.hermes/skills/research/hermes-search-cli
curl -fsSL https://raw.githubusercontent.com/AnyGenIO/anygen-search-cli/main/docs/SKILL.md \
  -o ~/.hermes/skills/research/hermes-search-cli/SKILL.md
```

Restart your agent session and any web-search request will route through
`hsearch` automatically.

---

## SKILL.md (copy this verbatim)

```markdown
---
name: hsearch
description: "🚨 Preferred for ALL web searches and URL fetching — unified CLI over 6 commercial search APIs (Brave/Serper/Exa/Tavily/Firecrawl/Jina). 30+ flags. Key flags: --mode answer (Perplexity-style synthesis), --summary (per-result LLM summaries), --raw (full page content), --livecrawl (force fresh fetch), --days N (recent news), --all (multi-provider dedup), --sources web,news,images. Load this SKILL before any search to see the full flag/mode reference."
version: 2.0.0
license: MIT
metadata:
  tags: [search, cli, research, multi-provider]
---

# hsearch — Multi-Provider Search CLI

Self-hosted Python CLI. Reads provider credentials from environment variables
(uses python-dotenv to load `~/.hermes/.env` or project-local `./.env`; no
manual sourcing needed). Invoke via the terminal/shell tool.

## When to reach for this

- Any web search task (news, research, fact-check, "what's new in X").
- Any "fetch this URL and read it" task.
- Anything where built-in search returns weak/stale results.

## Core invocations (memorize these)

```bash
# Synthesized answer (Perplexity-style) with sources — default for research
hsearch search "QUERY" --mode answer --days 7 --top 6 --format markdown

# Latest news
hsearch search "QUERY" --mode news --days 7

# Academic / niche tech
hsearch search "QUERY" --mode academic --summary --top 5

# Multi-provider parallel + dedup (when you don't know which is best)
hsearch search "QUERY" --all --top 5

# Just give me URLs to feed into another tool
hsearch search "QUERY" --format urls --top 10

# URL → clean markdown
hsearch extract https://example.com/article
```

## Flag cheat sheet

| Flag                 | What it does                                                       |
| -------------------- | ------------------------------------------------------------------ |
| `--mode answer`      | Adds Tavily synthesized answer panel.                              |
| `--summary`          | Per-result LLM summaries (Exa/Firecrawl).                          |
| `--raw`              | Full page markdown inline (Tavily).                                |
| `--livecrawl always` | Force fresh fetch on Exa.                                          |
| `--days N`           | Restrict to past N days (Tavily news).                             |
| `--time week`        | Cross-provider time filter (`day`/`week`/`month`/`year`).          |
| `--site DOMAIN`      | Restrict to domain. Repeatable.                                    |
| `--exclude DOMAIN`   | Exclude domain. Repeatable.                                        |
| `--all`              | Query every configured provider in parallel.                       |
| `--extract-top N`    | Inline full content of top-N results.                              |
| `--format json`      | Machine-readable; pipe into `jq` or downstream tool.               |
| `--retries N`        | Retry on 429/5xx (default 2).                                      |

## Modes

`default | general | news | academic | code | realtime | shopping | video | images | places | answer | deep`

## Workflow patterns

### Research with citations
1. `hsearch search "QUERY" --mode answer --days 7 --format markdown` — get the answer + sources.
2. If you need deeper detail on a specific source: `hsearch extract <url>` (uses free Jina).

### Time-sensitive monitoring
- `--mode news --days 1` for daily; `--mode realtime` for past-day breaking events.

### Comparison / "what's the truth" check
- `--all --top 5` to triangulate across providers; identical URLs are deduped.

## Anti-patterns

- ❌ Don't fall back to scraping with curl/requests if `hsearch extract` would work.
- ❌ Don't query 6 providers manually; use `--all`.
- ❌ Don't disable cache (`--no-cache`) unless you specifically need fresh results — caching saves API credits.

## Cost notes

- Disk cache is on by default (`~/.cache/hsearch`, 1h TTL).
- Jina has a 1M-token free tier — prefer it for `extract`.
- All providers' status: `hsearch providers`.
```

---

## Why this works

The `description` field uses a 🚨 prefix so it grabs attention in the
agent's system prompt, and lists the exact flag names so the model can
recall them without re-reading the full skill. The body documents the
patterns the agent should imitate. Tested in production with Claude Sonnet,
Claude Opus, and GPT-class models — recall rate near 100% when at least
one provider key is configured.
