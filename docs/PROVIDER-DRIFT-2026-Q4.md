# hsearch provider API drift audit — 2026-05-20

This audit re-checks the six upstream providers against the current hsearch
adapters after the 2026-05-07 review. Sources checked were the official provider
docs and changelog pages listed in `GOAL.md`; Serper's playground is login-bound,
so that check used Serper-owned public site bundles plus direct endpoint auth
responses.

## Summary

No provider had a breaking change that required replacing an existing hsearch
endpoint. The v0.4.0 work is additive: expose useful request controls that were
not reachable from the CLI, add Brave Place Search routing, add Serper patents
support, and document features that were deliberately skipped.

## Tavily

Sources:
- https://docs.tavily.com/documentation/api-reference/endpoint/search
- https://docs.tavily.com/changelog

Findings:
- `include_images` and `include_image_descriptions` are current first-class
  search params and each result may include an `images` array.
- `safe_search` exists but is enterprise-only and unavailable on fast depths.
- The params added in earlier audits remain current: `finance` topic,
  `fast`/`ultra-fast` depths, `include_answer=basic|advanced`,
  `include_favicon`, `include_usage`, and `exact_match`.

Action:
- Added `--include-images` and `--include-image-descriptions`.
- Tavily result images now populate `SearchResult.image` when present.
- Skipped `safe_search` because it is enterprise-only.

## Exa

Sources:
- https://exa.ai/docs/reference/search-api-guide-for-coding-agents
- https://exa.ai/docs/changelog

Findings:
- `/search` remains the correct endpoint. The April 2026 deprecation notice
  retired `/research` and response fields such as `resolvedSearchType`.
- Current search types are `auto`, `fast`, `instant`, `deep-lite`, `deep`, and
  `deep-reasoning`; hsearch already forwards `--exa-type`.
- `outputSchema` and `stream` are useful but return synthesized/streamed output
  that does not fit hsearch's current `SearchResult` list model.
- `compliance=hipaa` is enterprise-only.
- The changelog says `startCrawlDate`/`endCrawlDate` were deprecated/removed,
  while current reference pages still list them. hsearch leaves programmatic
  passthrough in place but does not expose new CLI flags for those fields.

Action:
- No urgent code change.
- Skipped `outputSchema`/`stream` for now because they need a response-model
  design rather than a simple search-result flag.
- Skipped enterprise `compliance`.

## Brave

Sources:
- https://api-dashboard.search.brave.com/api-reference/web/search/get
- https://api-dashboard.search.brave.com/documentation/services/place-search
- https://api-dashboard.search.brave.com/documentation/services/summarizer

Findings:
- Web Search now documents `goggles` and marks older `goggles_id` as deprecated.
- Place Search is a dedicated `/res/v1/local/place_search` endpoint, with a
  2026-01-15 launch note and 2026-03-04 radius change.
- Summarizer Search is deprecated in favor of Brave Answers; Brave Answers is a
  chat/answer endpoint rather than a normalized search-result endpoint.

Action:
- Added `--goggles` and provider passthrough for the current `goggles` param.
- Implemented Brave Place Search when `search_type=places` / `--mode places`
  falls through to Brave.
- Skipped Brave Answers and deprecated Summarizer expansion until hsearch has a
  first-class answer/chat response model for Brave.

## Firecrawl

Sources:
- https://docs.firecrawl.dev/api-reference/endpoint/search
- https://firecrawl.dev/changelog

Findings:
- v2 Search documents `ignoreInvalidURLs`.
- `scrapeOptions` now exposes practical controls such as `timeout`, `waitFor`,
  and `mobile`.
- Enterprise ZDR options (`enterprise=["zdr"|"anon"]`) still require team
  enablement.

Action:
- Added `--ignore-invalid-urls`.
- Added `--firecrawl-scrape-timeout` and `--firecrawl-wait-for`.
- Skipped ZDR and other enterprise-only options.

## Serper

Sources:
- https://serper.dev/
- https://serper.dev/playground
- Serper-owned Next.js playground bundle and direct `google.serper.dev/*`
  endpoint auth responses.

Findings:
- The public playground page now requires login before exposing full docs text.
- Public Serper-owned bundles still expose the current endpoint set:
  `search`, `news`, `images`, `videos`, `shopping`, `places`, `scholar`,
  `patents`, and `autocomplete`.
- Current request controls include `page` and `autocorrect` alongside existing
  `num`, `gl`, `hl`, `location`, and `tbs`.

Action:
- Added `--serper-type` to select Serper endpoints, including `patents`.
- Added `--page` and `--autocorrect/--no-autocorrect`.
- Skipped `autocomplete` because it returns suggestions, not search results.

## Jina

Sources:
- https://jina.ai/reader
- https://api.jina.ai/openapi.json

Findings:
- Reader/Search continue to use `r.jina.ai` and `s.jina.ai`.
- Current Reader controls include wait/remove selectors, generated image alt
  text, ReaderLM-v2 via `X-Respond-With`, locale/engine/cache controls, and
  structured extraction headers.
- hsearch already supported several headers internally but lacked CLI exposure.

Action:
- Added CLI exposure for `--jina-engine`, `--jina-respond-with`,
  `--jina-target-selector`, `--jina-wait-for`, `--jina-remove-selector`, and
  `--jina-generated-alt`.
- Added provider headers for wait selector, remove selector, and generated alt.
- Skipped structured extraction (`X-JSON-Schema` / instructions) because the
  result shape is not a plain web search hit.

## Tests

New mocked coverage in `tests/test_v040_drift.py` verifies:
- Tavily image request params and `SearchResult.image`.
- Brave Place Search normalization and `--goggles` CLI wiring.
- Serper patents endpoint, `page`, and `autocorrect`.
- Firecrawl `ignoreInvalidURLs`, scrape timeout, and wait-for options.
- Jina wait/remove/generated-alt headers.
