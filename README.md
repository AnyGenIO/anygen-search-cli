# anygen-search-cli (`hsearch`)

> **Unified CLI over 6 commercial search APIs** — Brave · Serper · Exa · Tavily · Firecrawl · Jina.
> One command, six providers, dedup'd results, Perplexity-style answers, full-content extraction.

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-40%20passing-brightgreen.svg)](tests/)
[![Version](https://img.shields.io/badge/version-0.2.0-blue.svg)](CHANGELOG.md)

---

## Why this exists

Every search provider has unique strengths — Tavily writes great answers, Exa
nails neural/semantic recall, Serper has cheap Google SERPs, Jina turns any
URL into clean markdown for free. **Wiring them up one-by-one in every agent
or script is wasteful.**

`hsearch` is a single fast CLI that:

- 🔑 **Auto-detects** which provider keys you've set; ignores the rest.
- 🔀 **Routes** queries by mode (`news` / `academic` / `realtime` / `answer` / …) to the best-suited provider.
- 🌐 **Parallel `--all`** — query every configured provider concurrently and dedup by URL.
- 🤖 **Perplexity-style** `--mode answer` — synthesized answer panel + sources.
- 📄 **Per-result summaries** (`--summary`) and **raw markdown** (`--raw`).
- 🆕 **Live crawl** (`--livecrawl always`), **time windows** (`--days 7`, `--time week`), **site filters**.
- 💾 **Disk cache** (1h TTL by default) — same query won't burn API credits twice.
- 📦 **5 output formats**: `table` · `json` · `jsonl` · `markdown` · `urls`.
- 🧪 **40 mocked tests**, no real keys needed to run.

---

## Install

```bash
git clone https://github.com/AnyGenIO/anygen-search-cli.git
cd anygen-search-cli
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e .
```

You now have a `hsearch` command on your PATH (and `python -m hsearch` works too).

> Requires Python **3.11+**. Dependencies: `httpx`, `typer`, `rich`,
> `python-dotenv`, `diskcache`.

### Configure provider keys

Copy [`.env.example`](.env.example) to `~/.hermes/.env` (recommended) or
project-local `./.env`, fill in **at least one** key:

```bash
cp .env.example ~/.hermes/.env
$EDITOR ~/.hermes/.env
```

Then verify:

```bash
$ hsearch providers
                  hsearch providers
┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┓
┃ Provider   ┃ Env var            ┃ Status        ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ brave      │ BRAVE_API_KEY      │ ✅ configured │
│ serper     │ SERPER_API_KEY     │ ✅ configured │
│ exa        │ EXA_API_KEY        │ ✅ configured │
│ tavily     │ TAVILY_API_KEY     │ ✅ configured │
│ firecrawl  │ FIRECRAWL_API_KEY  │ ✅ configured │
│ jina       │ JINA_API_KEY       │ ✅ configured │
└────────────┴────────────────────┴───────────────┘
```

---

## Quick recipes

```bash
# Default search (uses Tavily if configured)
hsearch search "open source RAG frameworks 2026"

# Perplexity-style synthesized answer + cited sources
hsearch search "what's new in Claude Opus 4.7" --mode answer --days 7

# Multi-provider, parallel, deduped, JSON for piping into jq/agents
hsearch search "quantum chips Q1 2026" --all --top 8 --format json

# Latest news from past 7 days
hsearch search "Anthropic announcements" --mode news --days 7

# Restrict to a domain, exclude another
hsearch search "vector DB benchmarks" --site arxiv.org --exclude reddit.com

# Academic / research with neural search + LLM summaries
hsearch search "speculative decoding" --mode academic --summary --top 5

# Force fresh fetch (bypass Exa's stale snapshot cache)
hsearch search "OpenAI Devday 2026" --provider exa --livecrawl always

# Convert any URL into clean markdown (free via Jina Reader)
hsearch extract https://anthropic.com/news/claude-opus-4-7

# Full content for top-3 results, then pipe to your favorite LLM
hsearch search "kubernetes 1.32 changes" --extract-top 3 --format markdown
```

---

## Output formats

| Format     | When to use                                  |
| ---------- | -------------------------------------------- |
| `table`    | Default — pretty terminal output (Rich).     |
| `markdown` | Paste into docs/Slack/an LLM prompt.         |
| `json`     | Pipe into `jq`, agents, downstream scripts.  |
| `jsonl`    | Stream-friendly; one JSON object per line.   |
| `urls`     | Just URLs, one per line — for `xargs curl`.  |

```bash
hsearch search "rust async runtimes" --format json | jq '.[].url'
```

---

## Content extraction

`hsearch` doubles as a **URL-to-markdown** tool. Point it at any page and get
back clean, LLM-ready markdown — no scraping logic, no boilerplate stripping
on your side.

```bash
# Single URL (default: Jina Reader, free, fast)
hsearch extract https://anthropic.com/news/claude-opus-4-7

# Many URLs in parallel
hsearch extract https://a.com/x https://b.com/y https://c.com/z --concurrency 8

# JS-heavy / paywalled? Switch to Firecrawl
hsearch extract https://app.example.com/dashboard --provider firecrawl

# JSON output for downstream pipelines
hsearch extract https://arxiv.org/abs/2410.10630 --format json | jq '.content'
```

### Flags

| Flag             | Type | Default    | Description                                          |
| ---------------- | ---- | ---------- | ---------------------------------------------------- |
| `--provider`,`-p`| str  | `jina`     | `jina` (free, fast) or `firecrawl` (JS render)       |
| `--format`, `-f` | str  | `markdown` | `markdown` or `json`                                 |
| `--concurrency`,`-c`| int | 4         | Parallel requests when extracting multiple URLs      |

### Two ways to get full page content

| Want…                                           | Use                                  |
| ----------------------------------------------- | ------------------------------------ |
| Markdown for **a known URL**                    | `hsearch extract <URL>`              |
| Markdown for **the top-N results of a search**  | `hsearch search "..." --extract-top 3` |

`--extract-top N` runs a search, then fetches and inlines the full markdown
for the first N deduped results into the `content` field — perfect for
pipelines that want both discovery and content in a single call.

```bash
# Search + auto-extract the top 3 hits, render as markdown
hsearch search "kubernetes 1.32 changes" --extract-top 3 --format markdown
```

> **Provider notes.** Jina Reader is free and handles ~95% of pages well. Use
> Firecrawl when a page is JS-heavy, requires interaction, or returns thin
> content from Jina.

---

## Documentation

- 📖 **[docs/USAGE.md](docs/USAGE.md)** — every flag, every mode, with examples
- 🔌 **[docs/PROVIDERS.md](docs/PROVIDERS.md)** — strengths/weaknesses of each provider + how to choose
- 🤖 **[docs/SKILL.md](docs/SKILL.md)** — drop-in [Claude Code](https://docs.claude.com/en/docs/claude-code/skills) / [Hermes Agent](https://github.com/NousResearch/hermes-agent) skill so your agent uses `hsearch` automatically

---

## Modes (`--mode`)

| Mode       | Default providers (fallback order)         | What it does                                               |
| ---------- | ------------------------------------------ | ---------------------------------------------------------- |
| `default`  | tavily                                     | General-purpose web search.                                |
| `general`  | tavily → brave                             | General web with broader fallback.                         |
| `news`     | brave → serper                             | Recent news; pair with `--days N`.                         |
| `academic` | exa                                        | Research papers, neural search.                            |
| `code`     | exa → brave                                | Code/library/SDK lookup.                                   |
| `realtime` | serper                                     | Past-day freshness for breaking events.                    |
| `shopping` | serper → brave                             | Product search.                                            |
| `video`    | serper → brave                             | Video results.                                             |
| `images`   | serper → brave                             | Image results.                                             |
| `places`   | serper → brave                             | Places / local search.                                     |
| `answer`   | tavily → brave                             | Synthesized **Answer panel** + sources. ⭐                 |
| `deep`     | exa                                        | Deep-reasoning / long-form research synthesis.             |

> If your preferred providers for a mode aren't configured, hsearch transparently falls back to whatever IS configured.

---

## Why use this over building it yourself?

Each provider's docs ship a Python snippet — copying 6 of them gives you 6
inconsistent error styles, 6 retry strategies, 6 result schemas, 6 places to
hide bugs. `hsearch` gives you **one schema** (`SearchResult`), **one retry
policy** (exponential backoff on 429/5xx, see `--retries`), **one cache**, and
**one CLI** that AI agents and shell scripts can both use.

---

## Development

```bash
pip install -e ".[dev]"
pytest                    # 40 tests, ~1.2s, no real keys needed
```

All providers are mocked via `respx`. To add a new provider:

1. Drop a file in `hsearch/providers/<name>.py`, subclass `BaseProvider`.
2. Register in `hsearch/providers/__init__.py` and `hsearch/config.py`.
3. (Optional) add to `MODE_MAP` in `hsearch/router.py`.
4. Add a mocked test in `tests/`.

---

## License

[MIT](LICENSE) © 2026 [AnyGenIO](https://github.com/AnyGenIO)

---

## Acknowledgements

Built and battle-tested as part of the [AnyGen](https://github.com/AnyGenIO)
ecosystem of agent tooling. Inspired by the realization that an agent
juggling six API SDKs is not as good as an agent calling **one** unified CLI.
