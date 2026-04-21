# Changelog

All notable changes to **anygen-search-cli** (`hsearch`) are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project adheres to [SemVer](https://semver.org/).

## [0.2.0] — 2026-04-21

### Added — provider feature parity & answer mode
- **`--mode answer`** — Perplexity-style synthesized answer panel (powered by Tavily `include_answer`); printed at the top in `table` and `markdown` output.
- **`--answer / -a`** — explicit flag, equivalent to `--mode answer` but composable with other modes.
- **`--summary`** — request per-result LLM summaries from Exa/Firecrawl (when supported).
- **`--raw`** — fetch full markdown of each Tavily result (`include_raw_content="markdown"`); content is truncated to 2000 chars per result in render to avoid console flooding while remaining grep-friendly.
- **`--livecrawl always|fallback|never`** — control Exa `contents.livecrawl` to force fresh fetches.
- **`--days N`** — restrict Tavily news mode to the last N days.
- **`--auto`** — enable Tavily `auto_parameters=True` (let Tavily auto-pick depth/topic).
- **`--sources web,news,images`** — Firecrawl multi-source merge.
- **`--retries N`** — per-request retry count on 429/5xx with exponential backoff (default 2).
- **17 new unit tests** covering all of the above (40 tests total, all green).

### Changed — output rendering
- Markdown snippet truncated at 500 chars (was full body); prevents 80+ line dumps in `--mode answer`.
- `--raw` content rendered up to 2000 chars per result (was a hidden 200-char clip — now matches the flag's contract).
- `--summary` field surfaced in both `markdown` and `table` outputs.

### Internal
- Provider HTTP layer: shared retry/backoff middleware in `providers/base.py`.
- Cache key params now strip private flags (anything prefixed `_`) so retries don't pollute the cache.

## [0.1.0] — 2026-04 (initial)

- 6 providers wired: **Brave, Serper, Exa, Tavily, Firecrawl, Jina**.
- Routing modes: `default | news | academic | code | general | realtime | shopping | video | images | places | answer | deep`.
- `search` / `extract` / `providers` / `config` / `cache` subcommands.
- Filters: `--time / --lang / --region / --site / --exclude`.
- Output formats: `table | json | jsonl | markdown | urls`.
- Disk cache (diskcache, default 1h TTL).
- Multi-provider parallel mode (`--all`) with cross-provider URL dedup.
- 23 unit tests (mocked HTTP via `respx`).
