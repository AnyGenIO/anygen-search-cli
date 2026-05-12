# `hsearch` — Full Usage Reference

Run `hsearch --help`, `hsearch search --help`, etc. for inline help.
This page is the long-form companion: **every flag, every mode, with examples.**

---

## Subcommands

| Command                    | Purpose                                                      |
| -------------------------- | ------------------------------------------------------------ |
| `hsearch search QUERY`     | Search across one, many, or all providers.                   |
| `hsearch extract URL...`   | Fetch URL(s) and return clean markdown (Jina or Firecrawl).  |
| `hsearch providers`        | List providers and which keys are configured.                |
| `hsearch config`           | Show resolved config + cache stats.                          |
| `hsearch cache clear`      | Wipe disk cache.                                             |
| `hsearch cache stats`      | Cache size + entry count.                                    |
| `hsearch --version` / `-V` | Print version.                                               |

---

## `hsearch search` — every flag

### Provider / mode selection

| Flag                       | Type     | Default | Description                                                                                          |
| -------------------------- | -------- | ------- | ---------------------------------------------------------------------------------------------------- |
| `--provider`, `-p`         | repeat   | —       | Pin to specific provider(s). e.g. `-p exa -p tavily`                                                 |
| `--mode`, `-m`             | string   | —       | Routing mode (see [Modes](#modes)).                                                                  |
| `--all`                    | bool     | false   | Query **every configured provider** in parallel and dedup-merge.                                     |

> Selection precedence: `--all` > `--provider` > `--mode` > default.

### Result shaping

| Flag                       | Type     | Default | Description                                                              |
| -------------------------- | -------- | ------- | ------------------------------------------------------------------------ |
| `--top`, `-n`              | int      | 10      | Max results per provider.                                                |
| `--format`, `-f`           | string   | auto    | `table` \| `json` \| `jsonl` \| `markdown` \| `urls`; auto JSON when piped. |
| `--agent`                  | bool     | false   | Agent preset: `--format json --top 5` unless explicitly overridden.      |

### Filters

| Flag                       | Type     | Default | Description                                                                  |
| -------------------------- | -------- | ------- | ---------------------------------------------------------------------------- |
| `--time`, `-t`             | string   | —       | `day` \| `week` \| `month` \| `year` \| `YYYY-MM-DD..YYYY-MM-DD`             |
| `--lang`, `-l`             | string   | —       | ISO 639-1 (`en`, `zh`, `ja`, …).                                             |
| `--region`, `-r`           | string   | —       | ISO 3166 (`US`, `CN`, `JP`, …).                                              |
| `--site`                   | repeat   | —       | Restrict to site(s). `--site arxiv.org --site openreview.net`                |
| `--exclude`                | repeat   | —       | Exclude site(s). `--exclude pinterest.com --exclude reddit.com`              |

### v0.2 — answer & content enrichment

| Flag                       | Type     | Default  | Description                                                                            |
| -------------------------- | -------- | -------- | -------------------------------------------------------------------------------------- |
| `--answer`, `-a`           | bool     | false    | Tavily synthesized answer panel at top.                                                |
| `--summary`                | bool     | false    | Per-result LLM summaries (Exa/Firecrawl).                                              |
| `--raw`                    | bool     | false    | Tavily `include_raw_content="markdown"` — fills `SearchResult.content` (≤2000 chars).  |
| `--livecrawl`              | string   | —        | Legacy Exa freshness alias: `always` \| `fallback` \| `never`; prefer `--max-age-hours`. |
| `--auto`                   | bool     | false    | Tavily `auto_parameters=True` — let Tavily auto-pick depth/topic.                       |
| `--sources`                | string   | —        | Firecrawl multi-source CSV: `web,news,images`.                                          |
| `--days`                   | int      | —        | Tavily news mode: results from the past N days.                                         |
| `--retries`                | int      | 2        | Per-request retries on 429/5xx (exponential backoff).                                   |

### v0.2.3 — recall controls

| Flag                       | Type     | Default  | Description                                                                            |
| -------------------------- | -------- | -------- | -------------------------------------------------------------------------------------- |
| `--chunks-per-source`      | int      | —        | Tavily chunks per source for `advanced` / `fast` depth (`1..3`).                        |
| `--highlights`             | bool     | false    | Exa `contents.highlights=True` for relevant source excerpts.                            |
| `--additional-query`       | repeat   | —        | Exa extra query variation for deep-search variants.                                     |
| `--max-age-hours`          | int      | —        | Exa `contents.maxAgeHours`; `0` forces live content, `-1` disables live crawling.        |
| `--context-threshold`      | string   | —        | Brave LLM Context threshold: `strict` \| `balanced` \| `lenient` \| `disabled`.          |

### Content extraction

| Flag                       | Type     | Default | Description                                                                  |
| -------------------------- | -------- | ------- | ---------------------------------------------------------------------------- |
| `--extract-top`            | int      | 0       | After search, fetch & inline full markdown for the top-N merged results.      |
| `--extract-provider`       | string   | `jina`  | Extractor for `--extract-top`: `jina` or `firecrawl` for JS-heavy pages.      |

### Cache control

| Flag                       | Type     | Default     | Description                                                  |
| -------------------------- | -------- | ----------- | ------------------------------------------------------------ |
| `--no-cache`               | bool     | false       | Bypass cache for this call (still writes back).              |
| `--cache-ttl`              | int      | (3600s)     | Override TTL in seconds for this call only.                  |

---

## Modes

A mode is a **named preset** that maps to one or more providers and may
toggle provider-specific extras.

| Mode       | Default providers          | Implicit extras                          |
| ---------- | -------------------------- | ---------------------------------------- |
| `default`  | tavily                     | —                                        |
| `general`  | tavily → brave             | —                                        |
| `news`     | brave → serper             | `topic=news`, `freshness=pw`             |
| `academic` | exa                        | `category="research paper"`              |
| `code`     | exa → brave                | —                                        |
| `realtime` | serper                     | `freshness=pd`                           |
| `shopping` | serper → brave             | `search_type=shopping`                   |
| `video`    | serper → brave             | `search_type=videos`                     |
| `images`   | serper → brave             | `search_type=images`                     |
| `places`   | serper → brave             | `search_type=places`                     |
| `answer`   | tavily → brave             | enables `--answer`                        |
| `deep`     | exa                        | `type=deep-reasoning`, `summary=True`    |
| `fast`     | exa → tavily               | `type=instant`, `search_depth=ultra-fast` |
| `recall`   | exa → tavily → brave → serper → firecrawl → jina | Exa `deep-reasoning` highlights/summaries, Tavily `advanced` chunks, Brave LLM Context `lenient`, Firecrawl `web,news` with content |

If your configured providers don't include a mode's preferred ones, hsearch
falls back to *any* configured provider.

---

## Real-world recipes

### 1. Quick research with citations

```bash
hsearch search "best open-source vector databases 2026" \
  --mode answer --days 30 --top 6 --format markdown
```

### 2. Multi-provider price-of-truth check

```bash
hsearch search "Anthropic Opus 4.7 pricing" --all --top 5
```

### 3. Recent news from past week, news-tuned providers

```bash
hsearch search "stock market" --mode news --days 7 --region US
```

### 4. Academic paper hunt with summaries

```bash
hsearch search "speculative decoding latency" \
  --mode academic --summary --top 8 --format json | jq '.results[] | {title, url, summary}'
```

### 5. Force-fresh deep dive on one site

```bash
hsearch search "site:openai.com new models" \
  --provider exa --max-age-hours 0 --extract-top 3 --extract-provider firecrawl --format markdown
```

### 6. Maximum recall for hard research

```bash
hsearch search "production RAG evaluation failures 2026" \
  --mode recall --top 8 --format markdown
```

### 7. Just give me URLs to feed into a downstream tool

```bash
hsearch search "kubernetes 1.32 release notes" --format urls --top 10
```

### 8. URL extraction (works on anything Jina can read)

```bash
hsearch extract https://github.com/AnyGenIO/anygen-search-cli
hsearch extract URL1 URL2 URL3 --concurrency 4 --format json
```

---

## Output schema (`json` / `jsonl`)

`--format json` returns a structured envelope:

```json
{
  "meta": {
    "query": "...",
    "mode": "default",
    "providers_queried": ["tavily"],
    "total_results": 1,
    "cached": {"tavily": false}
  },
  "results": [
    {
      "url": "https://...",
      "title": "...",
      "snippet": "short description",
      "provider": "tavily",
      "score": 0.87,
      "published": "2026-04-21",
      "sources": ["tavily"],
      "content": "(optional) full markdown if --raw / --extract-top",
      "summary": "(optional) provider-side LLM summary if --summary"
    }
  ]
}
```

`--format jsonl` emits one bare `SearchResult` object per line for streaming.

Cross-provider URL dedup keeps the first occurrence (provider priority order)
and merges any unique fields.

---

## Environment variables

| Var                    | Required | Description                                  |
| ---------------------- | -------- | -------------------------------------------- |
| `BRAVE_API_KEY`        | optional | Brave Search                                 |
| `SERPER_API_KEY`       | optional | Serper.dev (Google SERP)                     |
| `EXA_API_KEY`          | optional | Exa neural search                            |
| `TAVILY_API_KEY`       | optional | Tavily LLM-tuned search & answers            |
| `FIRECRAWL_API_KEY`    | optional | Firecrawl search/crawl/extract               |
| `JINA_API_KEY`         | optional | Jina Reader (URL → markdown)                 |
| `HSEARCH_TIMEOUT`      | optional | HTTP timeout, sec (default 20)               |
| `HSEARCH_CACHE_TTL`    | optional | Cache TTL in sec (default 3600)              |
| `HSEARCH_CACHE_DIR`    | optional | Override cache dir (default `~/.cache/hsearch`) |

Load order: explicit shell/process env (highest) → `HSEARCH_ENV_FILE` → project `./.env` → active Hermes profile `$HERMES_HOME/.env` → global `~/.hermes/.env`.
This is profile-aware for Hermes gateway sessions where `HOME` may point at a sandbox like `~/.hermes/profiles/<name>/home`.

---

## Exit codes

| Code | Meaning                                                    |
| ---- | ---------------------------------------------------------- |
| 0    | Success (≥1 result returned, or extract OK).                |
| 1    | All providers errored or returned 0 results.                |
| 2    | Bad CLI args / no providers configured.                     |

---

## See also

- [PROVIDERS.md](PROVIDERS.md) — when to pick which provider.
- [SKILL.md](SKILL.md) — drop-in agent skill so AI uses `hsearch` automatically.
