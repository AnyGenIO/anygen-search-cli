# Provider Cheat Sheet

Six providers, each best at something different. Pick based on your job.

| Provider      | Sweet spot                                 | Pricing model       | Free tier           | Auth header                    |
| ------------- | ------------------------------------------ | ------------------- | ------------------- | ------------------------------ |
| **Brave**     | General web, privacy-respecting, news      | Per-query           | 2k queries/mo       | `X-Subscription-Token`         |
| **Serper**    | Google SERP wrapper (web/news/img/video/shopping/places) | Credits | 2.5k credits free   | `X-API-KEY`                    |
| **Exa**       | Neural / semantic search, research papers, "find similar" | Credits | Yes (small)         | `Authorization: Bearer`         |
| **Tavily**    | LLM-optimized search, **synthesized answers**, RAG-friendly | Credits | 1k/mo               | JSON `api_key`                 |
| **Firecrawl** | Search + crawl + extract, multi-source merge, structured | Credits | Yes                 | `Authorization: Bearer`         |
| **Jina Reader** | URL → clean markdown, content extraction (also doubles as a search backend) | Tokens | **1M tokens free, no card** | `Authorization: Bearer`         |

---

## When to use which

### "Just give me the best web results"
→ **Tavily** (default mode) or **Brave** (more privacy, less ML-flavored).

### "I need the AI to write me a summary with citations"
→ **Tavily** with `--mode answer`. Has `include_answer` baked in.

### "Find me research papers / niche tech content"
→ **Exa** with `--mode academic`. Neural recall finds things keyword search misses.

### "Latest breaking news"
→ **Brave** or **Serper** with `--mode news --days 1`.

### "Google SERP for shopping/images/videos/places"
→ **Serper** — straightforward Google wrapper, those verticals are its forte.

### "Get me the actual page content, not just snippets"
→ **`hsearch extract`** with **Jina** (free) or **Firecrawl** (better for JS-heavy sites).
For inline content during search: **`--extract-top N`** or **`--raw`** (Tavily).

### "I want fresh content, not stale crawl snapshots"
→ **Exa** with `--livecrawl always`. Forces a live fetch.

### "Multi-source merge: web + news + images all at once"
→ **Firecrawl** with `--sources web,news,images`.

### "I don't know — try them all and dedup"
→ **`--all`**. Hits every configured provider in parallel, dedups by URL.

---

## Cost-conscious tips

1. **Disk cache is on by default** (`~/.cache/hsearch`, 1h TTL). Same query won't burn a credit twice within the hour. Bump it for stable queries: `HSEARCH_CACHE_TTL=86400`.
2. **Jina's free tier is huge** — 1M tokens, no card. Use it as your default `extract` provider.
3. **Avoid `--all`** when you don't need it; it fans out to every configured provider.
4. **Pick a mode, not 6 providers**. `--mode academic` only hits Exa.
5. **`hsearch cache stats`** to see what's pre-warmed.

---

## Provider-specific quirks

### Brave
- Strong privacy story, fast.
- News results need `freshness=pw|pd|pm` (set automatically by `--mode news`).

### Serper
- 8 search verticals via `search_type` (web/news/images/videos/shopping/places/scholar/maps).
- Cheapest Google SERP available.

### Exa
- Score reflects neural similarity, not popularity.
- `livecrawl=fallback` is a smart default cost-wise.
- Has `category="research paper"` for academic recall.

### Tavily
- The only one with a real native **answer synthesis** (`include_answer`).
- `auto_parameters=True` lets it pick search depth — useful when you don't know what you're looking for.
- `include_raw_content="markdown"` returns the page body as markdown.

### Firecrawl
- Multi-source endpoint can return web + news + images in one call.
- LLM extract pipeline available (advanced; not exposed via current `hsearch` flags).

### Jina
- Free 1M tokens — best deal in the table.
- Strictly URL → clean markdown via `r.jina.ai/<url>`. Use for `extract` whenever possible.

---

## Adding a new provider

`hsearch` is designed to grow. To wire up a new provider:

1. Subclass `BaseProvider` in `hsearch/providers/<name>.py` (implement `_request()` returning a list of `SearchResult`).
2. Register in `hsearch/providers/__init__.py` and `PROVIDER_ENV` in `hsearch/config.py`.
3. (Optional) add to `MODE_MAP` in `hsearch/router.py` so it's auto-picked for relevant modes.
4. Add a `respx`-mocked test under `tests/`.

PRs welcome.
