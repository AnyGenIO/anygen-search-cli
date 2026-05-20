# Changelog

All notable changes to **anygen-search-cli** (`hsearch`) are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project adheres to [SemVer](https://semver.org/).

## [0.4.0] — 2026-05-20

Optimization release: provider drift follow-up, native MCP server mode, and
adaptive cache TTLs by search mode.

### Added
- **MCP server mode** — `hsearch mcp` starts a stdio MCP server with `search`,
  `extract`, `providers`, and `schema` tools. The optional extra is declared as
  `mcp = ["mcp[cli]>=1.0"]`.
- **MCP docs** — `docs/MCP.md` includes Claude Desktop and Codex config examples.
- **Adaptive cache TTLs** — mode defaults now use 5 minutes for
  `news`/`realtime`, 15 minutes for `finance`/`answer`, 1 hour for
  `general`/`fast`/`recall`, 4 hours for `code`/`deep`, and 24 hours for
  `academic`. JSON output now includes `meta.cache_ttl_seconds`.
- **Provider drift flags**:
  - Tavily `--include-images` and `--include-image-descriptions`.
  - Brave `--goggles` and native Place Search handling for `places`.
  - Serper `--serper-type`, `--page`, `--autocorrect/--no-autocorrect`, and
    patents endpoint support.
  - Firecrawl `--ignore-invalid-urls`, `--firecrawl-scrape-timeout`, and
    `--firecrawl-wait-for`.
  - Jina `--jina-engine`, `--jina-respond-with`, `--jina-target-selector`,
    `--jina-wait-for`, `--jina-remove-selector`, and `--jina-generated-alt`.
- **Provider audit doc** — `docs/PROVIDER-DRIFT-2026-Q4.md` records findings,
  implemented flags, and skipped enterprise/niche items.

### Changed
- Version bumped to `0.4.0`.
- `--cache-ttl` remains the explicit override and now takes precedence over
  mode-derived defaults everywhere in the SDK/CLI.
- `--no-cache` documentation now matches behavior: it bypasses cache reads and
  writes.

### Tests
- **113 unit tests passing**.
- New coverage: MCP tool registration/direct calls, adaptive cache policy and
  engine metadata, Tavily/Brave/Serper/Firecrawl/Jina drift wiring.

### Verified
- `.venv/bin/pytest -q`
- `.venv/bin/hsearch --version`
- `.venv/bin/hsearch mcp --help`

## [0.3.1] — 2026-05-20

API alignment update: verified all 6 providers against their latest official docs (2026-05).

### Fixed
- **Firecrawl sources format** — now sends `[{type: "web"}]` objects per v2 API spec (was incorrectly sending `["web"]` strings).
- **Firecrawl `lang`** — moved from invalid top-level param to correct `scrapeOptions.location.languages` placement.
- **Firecrawl `scrapeOptions.formats`** — now sends plain strings (`"markdown"`, `"summary"`) per v2 docs, not objects.
- **Tavily topic validation** — invalid topics now fall back to `"general"` instead of being forwarded to the API.

### Added
- **`--mode finance`** — new router preset using Tavily `topic=finance` + `search_depth=advanced` + advanced answer.
- **`--answer-depth basic|advanced`** — Tavily answer detail level control (Tavily now accepts string values for `include_answer`).
- **`--moderation`** — Exa content moderation filter for unsafe content.
- **`--livecrawl-timeout`** — Exa livecrawl timeout in milliseconds.
- **Exa new params**: `startCrawlDate`/`endCrawlDate` (crawl date filtering), `contents.text.verbosity`/`includeHtmlTags`/`includeSections`/`excludeSections` (text extraction control), `contents.extras.links`/`imageLinks` (link/image extraction), `contents.livecrawlTimeout`.
- **Exa response fields**: `author` and `image` now captured in `SearchResult`.
- **Brave**: `spellcheck` and `ui_lang` parameters.
- **Jina**: `X-Timeout`, `X-Max-Tokens`, `X-Cache-Tolerance`, `X-Preset`, `X-Target-Selector`, `X-Retain-Images`, `X-Respond-With` headers.
- **Firecrawl**: `timeout` param, `highlights` scrape format.
- **Dedup**: content/summary/favicon/author/image merging across providers; richness-based scoring (results with content/summary/dates rank higher).
- **Recall mode**: now also enables Brave `spellcheck`+`extra_snippets` and Exa `moderation`.
- `SearchResult.author` and `SearchResult.image` fields.

### Changed
- **Tavily `topic`** validated against `{general, news, finance}` with fallback.
- Schema updated with new params, finance example, and recall tips.

### Tests
- **+26 unit tests** (99 total): Firecrawl sources/lang/timeout/highlights, Exa moderation/crawl-dates/livecrawl-timeout/text-verbosity/extras-links/author-image, Tavily finance-topic/invalid-topic/advanced-answer/basic-answer, Brave spellcheck/ui_lang, Jina new headers/respond-with, dedup content-merging/richness-scoring, router finance-mode, CLI answer-depth/moderation/mode-finance/version.

## [0.2.3] — 2026-05-12

High-recall search update based on current Tavily, Exa, Brave, and Firecrawl docs.

### Added
- **`--mode recall`** — broad, recall-first preset over Exa, Tavily, Brave, Serper, Firecrawl, and Jina.
- **Brave LLM Context support** via `search_kind=context`, used automatically by `--mode recall`.
- **`--chunks-per-source`** — Tavily `chunks_per_source` passthrough for high-context advanced/fast search.
- **`--highlights`**, **`--additional-query`**, **`--max-age-hours`** — Exa Search API controls for current `contents.*` parameters.
- **`--context-threshold`** — Brave LLM Context threshold control.

### Changed
- Exa Search now nests content options under `contents`, requests `highlights` by default, and translates legacy `--livecrawl` values to current `contents.maxAgeHours`.
- `--time YYYY-MM-DD..YYYY-MM-DD` now maps to Tavily `start_date` / `end_date`.
- Firecrawl now uses native `includeDomains` / `excludeDomains` filters when only one side is specified.
- Jina `--lang` now maps to `X-Locale`.
- Cache initialization now falls back to `/tmp/hsearch-cache`, and `--no-cache` no longer initializes diskcache.

### Tests
- **73 unit tests passing**.

## [0.2.2] — 2026-05-07

Tracks 2026-04 provider doc updates: Tavily new params, Exa Fast/Instant search types, Firecrawl v2 categories format.

### Added
- **`--exact`** — Tavily `exact_match=True`: quoted phrases must appear verbatim, no synonym expansion. Useful for exact-name lookups.
- **`--depth basic|advanced|fast|ultra-fast`** — Tavily `search_depth` selector. `fast`/`ultra-fast` are new latency-first depths added by Tavily in 2026-04 (sub-second responses).
- **`--exa-type auto|fast|instant|neural|keyword|deep-reasoning`** — explicit Exa `type` selector. `instant` (Exa 2.0) returns in ~400ms; `fast` in ~1s.
- **`--include-favicon`** — Tavily: each result includes its `favicon` URL (now exposed via the new `SearchResult.favicon` field).
- **`--include-usage`** — Tavily: response usage block (`{"credits": N}`) is surfaced in the JSON `meta.usage[provider]`.
- **`--mode fast`** — new latency-first router preset: queries Exa with `type=instant` and Tavily with `search_depth=ultra-fast` in parallel for sub-second multi-provider grounding.
- `SearchResult.favicon: str | None` field.
- Provider `_last_usage` introspection hook (mirrors existing `_last_answer`).

### Changed
- **Firecrawl `categories`** — string array form (`["github"]`) is now auto-normalized to the v2 object form (`[{"type": "github"}]`) before sending. Existing callers continue to work; the wire format matches current Firecrawl docs. Backward-compatible.
- Tavily `search_depth` is validated against `{basic, advanced, fast, ultra-fast}` and falls back to `basic` on unknown values instead of forwarding garbage to the API.

### Tests
- **+21 unit tests** (68 total): Tavily exact_match / include_favicon / include_usage / depth variants + invalid-depth fallback, Exa type passthrough (parametrized over fast/instant/auto/deep-reasoning), router `fast` mode, full CLI flag wiring (`--exact`, `--depth`, `--exa-type`, `--include-favicon`, `--include-usage`, `--mode fast`), Firecrawl categories object-form passthrough.

### Verified live (2026-05-07)
- `--mode fast`: 1.4s for exa+tavily double-fetch with deduped merge.
- `--depth ultra-fast`: 0.97s tavily-only.
- `--exa-type instant`: 0.7s exa-only.
- `--include-favicon`: real favicon URLs returned for Wikipedia + anthropic.com.
- `--include-usage`: surfaces `meta.usage.tavily.credits=1`.
- Firecrawl categories normalized form `[{"type": "github"}]` confirmed on the wire.

## [0.2.1] — 2026-04-30

### Added
- **`search --agent`** — compact agent preset: defaults to structured JSON output and `--top 5` unless the caller explicitly overrides `--format` or `--top`.
- **`search --extract-provider jina|firecrawl`** — lets `--extract-top` use Firecrawl for JS-heavy pages instead of always using Jina.

### Fixed
- Provider key loading is now Hermes-profile-aware: `hsearch` reads `$HERMES_HOME/.env` and global `~/.hermes/.env`, so Telegram/gateway sessions see the active profile's search keys even when `HOME` points at the profile sandbox.

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
