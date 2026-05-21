"""hsearch — typer-based CLI (thin wrapper over engine.py)."""
from __future__ import annotations

import asyncio
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from hsearch import __version__
from hsearch.cache import ResultCache
from hsearch.config import (
    ALL_PROVIDERS,
    PROVIDER_ENV,
    cache_dir,
    cache_ttl,
    configured_providers,
    get_key,
    timeout_seconds,
)
from hsearch.engine import search as engine_search, SearchResponse
from hsearch.extract import EXTRACT_PROVIDERS, extract_many
from hsearch.filters import Filters
from hsearch.models import SearchResult
from hsearch.output import emit
from hsearch.providers import list_providers
from hsearch.router import ALL_MODES

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="hsearch — unified CLI over 6 commercial search APIs.",
    rich_markup_mode="rich",
)
cache_app = typer.Typer(help="Cache utilities", no_args_is_help=True)
app.add_typer(cache_app, name="cache")

console = Console()
err_console = Console(stderr=True)


# --- helpers -----------------------------------------------------------------


def _cli_option_present(long_name: str, short_name: str | None = None) -> bool:
    for arg in sys.argv[1:]:
        if arg == long_name or arg.startswith(f"{long_name}="):
            return True
        if short_name and (arg == short_name or arg.startswith(short_name)):
            return True
    return False


def _print_errors(errors: dict[str, str]) -> None:
    if not errors:
        return
    for name, msg in errors.items():
        err_console.print(f"[yellow]![/] [bold]{name}[/]: {msg}")


# --- commands ----------------------------------------------------------------


def _version_cb(value: bool) -> None:
    if value:
        typer.echo(f"hsearch {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None, "--version", "-V", callback=_version_cb, is_eager=True, help="Show version."
    ),
) -> None:
    """hsearch — unified search over Brave, Serper, Exa, Tavily, Firecrawl, Jina."""


@app.command()
def search(
    query: str = typer.Argument(..., help="Query string."),
    provider: list[str] = typer.Option(
        None, "--provider", "-p",
        help=f"Provider(s) to query; repeat for multiple ({'|'.join(ALL_PROVIDERS)}).",
    ),
    mode: Optional[str] = typer.Option(
        None, "--mode", "-m", help=f"Routing mode ({'|'.join(ALL_MODES)})."
    ),
    all_providers: bool = typer.Option(
        False, "--all", help="Query every configured provider in parallel + merge."
    ),
    top: int = typer.Option(10, "--top", "-n", help="Max results per provider."),
    fmt: Optional[str] = typer.Option(
        None, "--format", "-f", help="Output: table | json | jsonl | markdown | urls (auto: json when piped, table in terminal)"
    ),
    no_cache: bool = typer.Option(False, "--no-cache", help="Disable result cache."),
    cache_ttl_opt: Optional[int] = typer.Option(
        None, "--cache-ttl", help="Override cache TTL in seconds for this call."
    ),
    time: Optional[str] = typer.Option(
        None, "--time", "-t", help="day|week|month|year or YYYY-MM-DD..YYYY-MM-DD"
    ),
    lang: Optional[str] = typer.Option(None, "--lang", "-l", help="ISO 639-1 (en, zh, ja, ...)"),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="ISO 3166 (US, CN, ...)"),
    location: Optional[str] = typer.Option(
        None, "--location", help="Provider location hint (e.g. San Francisco,CA,US)."
    ),
    site: list[str] = typer.Option(None, "--site", help="Restrict to site(s); repeatable."),
    exclude: list[str] = typer.Option(None, "--exclude", help="Exclude site(s); repeatable."),
    extract_top: int = typer.Option(
        0, "--extract-top", help="Extract content of top-N merged results."
    ),
    extract_provider: str = typer.Option(
        "jina",
        "--extract-provider",
        help="Provider for --extract-top content fetch: jina | firecrawl.",
    ),
    agent: bool = typer.Option(
        False,
        "--agent",
        help="Agent-friendly preset: --format json --top 5 unless explicitly overridden.",
    ),
    answer: bool = typer.Option(
        False, "--answer", "-a",
        help="Ask Tavily for a synthesized answer (printed at top).",
    ),
    summary: bool = typer.Option(
        False, "--summary",
        help="Ask Exa/Firecrawl for per-result LLM summaries.",
    ),
    sources: Optional[str] = typer.Option(
        None, "--sources",
        help="Firecrawl multi-source (comma-sep): web,news,images.",
    ),
    goggles: list[str] = typer.Option(
        None, "--goggles",
        help="Brave: Goggle URL or inline definition; repeatable.",
    ),
    serper_type: Optional[str] = typer.Option(
        None, "--serper-type",
        help="Serper endpoint: search | news | images | videos | shopping | places | scholar | patents.",
    ),
    page: Optional[int] = typer.Option(
        None, "--page",
        help="Serper page number for paginated endpoints.",
    ),
    autocorrect: Optional[bool] = typer.Option(
        None, "--autocorrect/--no-autocorrect",
        help="Serper: enable or disable query autocorrection.",
    ),
    livecrawl: Optional[str] = typer.Option(
        None, "--livecrawl",
        help="Legacy Exa freshness alias: always|fallback|never (mapped to maxAgeHours).",
    ),
    auto: bool = typer.Option(
        False, "--auto",
        help="Tavily auto_parameters=True (let Tavily pick depth/topic).",
    ),
    raw: bool = typer.Option(
        False, "--raw",
        help="Tavily include_raw_content='markdown' — fills SearchResult.content.",
    ),
    retries: int = typer.Option(
        2, "--retries",
        help="Per-request retries on 429/5xx (exponential backoff).",
    ),
    fanout_timeout: Optional[float] = typer.Option(
        None, "--fanout-timeout",
        help="Max seconds to wait for all providers; returns partial results on timeout.",
    ),
    days: Optional[int] = typer.Option(
        None, "--days",
        help="Tavily news mode: results from past N days.",
    ),
    chunks_per_source: Optional[int] = typer.Option(
        None, "--chunks-per-source",
        help="Tavily chunks per source for advanced/fast depth (1-3).",
    ),
    additional_query: list[str] = typer.Option(
        None, "--additional-query",
        help="Exa extra query variation for deep-search modes; repeatable.",
    ),
    max_age_hours: Optional[int] = typer.Option(
        None, "--max-age-hours",
        help="Exa contents.maxAgeHours: 0 live, -1 cache-only, omit for default fallback.",
    ),
    highlights: bool = typer.Option(
        False, "--highlights",
        help="Exa contents.highlights=True for relevant excerpts.",
    ),
    context_threshold: Optional[str] = typer.Option(
        None, "--context-threshold",
        help="Brave LLM Context threshold: strict | balanced | lenient | disabled.",
    ),
    exact: bool = typer.Option(
        False, "--exact",
        help="Tavily exact_match=True — quoted phrases must appear verbatim (no synonyms).",
    ),
    depth: Optional[str] = typer.Option(
        None, "--depth",
        help="Tavily search_depth: basic | advanced | fast | ultra-fast.",
    ),
    exa_type: Optional[str] = typer.Option(
        None, "--exa-type",
        help="Exa type: auto | fast | instant | neural | deep-lite | deep | deep-reasoning.",
    ),
    include_favicon: bool = typer.Option(
        False, "--include-favicon",
        help="Tavily: return favicon URL per result.",
    ),
    include_usage: bool = typer.Option(
        False, "--include-usage",
        help="Tavily: include credit usage info in response meta.",
    ),
    include_images: bool = typer.Option(
        False, "--include-images",
        help="Tavily: include query/result images.",
    ),
    include_image_descriptions: bool = typer.Option(
        False, "--include-image-descriptions",
        help="Tavily: include image descriptions with --include-images.",
    ),
    answer_depth: Optional[str] = typer.Option(
        None, "--answer-depth",
        help="Tavily answer detail level: basic | advanced (requires --answer).",
    ),
    moderation: bool = typer.Option(
        False, "--moderation",
        help="Exa: enable content moderation to filter unsafe results.",
    ),
    livecrawl_timeout: Optional[int] = typer.Option(
        None, "--livecrawl-timeout",
        help="Exa: livecrawl timeout in milliseconds (default 10000).",
    ),
    ignore_invalid_urls: bool = typer.Option(
        False, "--ignore-invalid-urls",
        help="Firecrawl: exclude URLs that are invalid for follow-on scrape endpoints.",
    ),
    firecrawl_scrape_timeout: Optional[int] = typer.Option(
        None, "--firecrawl-scrape-timeout",
        help="Firecrawl scrapeOptions.timeout in milliseconds.",
    ),
    firecrawl_wait_for: Optional[int] = typer.Option(
        None, "--firecrawl-wait-for",
        help="Firecrawl scrapeOptions.waitFor in milliseconds.",
    ),
    jina_engine: Optional[str] = typer.Option(
        None, "--jina-engine",
        help="Jina X-Engine header for Reader/Search.",
    ),
    jina_respond_with: Optional[str] = typer.Option(
        None, "--jina-respond-with",
        help="Jina X-Respond-With header, e.g. no-content, markdown, readerlm-v2.",
    ),
    jina_target_selector: Optional[str] = typer.Option(
        None, "--jina-target-selector",
        help="Jina X-Target-Selector CSS selector.",
    ),
    jina_wait_for: Optional[str] = typer.Option(
        None, "--jina-wait-for",
        help="Jina X-Wait-For-Selector CSS selector.",
    ),
    jina_remove_selector: Optional[str] = typer.Option(
        None, "--jina-remove-selector",
        help="Jina X-Remove-Selector CSS selector.",
    ),
    jina_generated_alt: bool = typer.Option(
        False, "--jina-generated-alt",
        help="Jina: caption images with generated alt text.",
    ),
    safe_search: bool = typer.Option(
        False, "--safe-search",
        help="Tavily: filter adult/unsafe content (Enterprise only).",
    ),
    project_id: Optional[str] = typer.Option(
        None, "--project-id",
        help="Tavily: X-Project-ID header for per-project usage tracking.",
    ),
    firecrawl_only_clean_content: bool = typer.Option(
        False, "--firecrawl-clean-content",
        help="Firecrawl: LLM-based cleanup of residual boilerplate (beta).",
    ),
    firecrawl_max_age: Optional[int] = typer.Option(
        None, "--firecrawl-max-age",
        help="Firecrawl scrapeOptions.maxAge in ms (cache freshness threshold).",
    ),
    firecrawl_min_age: Optional[int] = typer.Option(
        None, "--firecrawl-min-age",
        help="Firecrawl scrapeOptions.minAge in ms (cache-only mode, set 1 for any cached).",
    ),
    firecrawl_block_ads: Optional[bool] = typer.Option(
        None, "--firecrawl-block-ads/--firecrawl-no-block-ads",
        help="Firecrawl: enable/disable ad and cookie popup blocking.",
    ),
    firecrawl_proxy: Optional[str] = typer.Option(
        None, "--firecrawl-proxy",
        help="Firecrawl proxy tier: basic | enhanced | auto.",
    ),
    firecrawl_question: Optional[str] = typer.Option(
        None, "--firecrawl-question",
        help="Firecrawl: ask a question about each scraped page (returns answer).",
    ),
    highlights_query: Optional[str] = typer.Option(
        None, "--highlights-query",
        help="Firecrawl/Exa: query string for highlights relevance.",
    ),
) -> None:
    """Run a search across one, many, or all providers."""
    if agent:
        if fmt is None:
            fmt = "json"
        if not _cli_option_present("--top", "-n"):
            top = 5

    if extract_top and extract_top > 0 and extract_provider not in EXTRACT_PROVIDERS:
        err_console.print(
            f"[red]Invalid --extract-provider:[/] {extract_provider} "
            f"(choose {'|'.join(EXTRACT_PROVIDERS)})"
        )
        raise typer.Exit(2)

    try:
        resp: SearchResponse = asyncio.run(
            engine_search(
                query,
                providers=list(provider) if provider else None,
                mode=mode,
                all_providers=all_providers,
                top=top,
                no_cache=no_cache,
                cache_ttl=cache_ttl_opt,
                time=time,
                lang=lang,
                region=region,
                location=location,
                sites=site,
                exclude=exclude,
                extract_top=extract_top,
                extract_provider=extract_provider,
                fanout_timeout=fanout_timeout,
                answer=answer,
                summary=summary,
                sources=sources,
                goggles=list(goggles) if goggles else None,
                serper_type=serper_type,
                page=page,
                autocorrect=autocorrect,
                livecrawl=livecrawl,
                auto=auto,
                raw=raw,
                retries=retries,
                days=days,
                chunks_per_source=chunks_per_source,
                additional_queries=list(additional_query) if additional_query else None,
                max_age_hours=max_age_hours,
                highlights=highlights,
                context_threshold=context_threshold,
                exact=exact,
                depth=depth,
                exa_type=exa_type,
                include_favicon=include_favicon,
                include_usage=include_usage,
                include_images=include_images,
                include_image_descriptions=include_image_descriptions,
                answer_depth=answer_depth,
                moderation=moderation,
                livecrawl_timeout=livecrawl_timeout,
                ignore_invalid_urls=ignore_invalid_urls,
                firecrawl_scrape_timeout=firecrawl_scrape_timeout,
                firecrawl_wait_for=firecrawl_wait_for,
                jina_engine=jina_engine,
                jina_respond_with=jina_respond_with,
                jina_target_selector=jina_target_selector,
                jina_wait_for=jina_wait_for,
                jina_remove_selector=jina_remove_selector,
                jina_generated_alt=jina_generated_alt,
                safe_search=safe_search,
                project_id=project_id,
                firecrawl_only_clean_content=firecrawl_only_clean_content,
                firecrawl_max_age=firecrawl_max_age,
                firecrawl_min_age=firecrawl_min_age,
                firecrawl_block_ads=firecrawl_block_ads,
                firecrawl_proxy=firecrawl_proxy,
                firecrawl_question=firecrawl_question,
                highlights_query=highlights_query,
            )
        )
    except ValueError as e:
        err_console.print(f"[red]Invalid filter:[/] {e}")
        raise typer.Exit(2)

    merged = resp.results
    mode_key = (mode or "").lower() or None

    if fmt is None:
        fmt = "table" if sys.stdout.isatty() else "json"

    meta = resp.meta
    if agent:
        meta["agent_preset"] = True

    if (answer or mode_key == "answer") and resp.answer and fmt in ("table", "markdown", "md"):
        if fmt == "table":
            console.print(
                Panel(
                    resp.answer,
                    title="[bold green]Tavily Answer[/]",
                    border_style="green",
                    expand=True,
                )
            )
        else:
            sys.stdout.write(f"## Answer\n\n{resp.answer}\n\n")

    emit(merged, fmt, console=console, meta=meta, errors=resp.errors)
    if fmt != "json":
        _print_errors(resp.errors)
    if not merged and resp.errors:
        raise typer.Exit(1)


@app.command()
def extract(
    urls: list[str] = typer.Argument(..., help="One or more URLs to extract."),
    provider: str = typer.Option(
        "jina", "--provider", "-p", help="jina | firecrawl"
    ),
    fmt: Optional[str] = typer.Option(
        None, "--format", "-f", help="markdown | json (auto: json when piped, markdown in terminal)"
    ),
    concurrency: int = typer.Option(4, "--concurrency", "-c", help="Parallel requests."),
) -> None:
    """Fetch one or more URLs and return clean markdown/text."""
    if fmt is None:
        fmt = "markdown" if sys.stdout.isatty() else "json"
    outcomes = asyncio.run(extract_many(urls, provider=provider, concurrency=concurrency))
    if fmt == "json":
        import json

        results_ok = [{"url": u, "content": c} for u, c, e in outcomes if not e]
        errs = {u: e for u, _c, e in outcomes if e}
        meta = {
            "provider": provider,
            "urls_requested": len(urls),
            "urls_succeeded": len(results_ok),
        }
        out: dict = {"meta": meta, "results": results_ok}
        if errs:
            out["errors"] = errs
        sys.stdout.write(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
        return
    for url, content, err in outcomes:
        console.rule(f"[bold]{url}[/]")
        if err:
            err_console.print(f"[red]error:[/] {err}")
            continue
        sys.stdout.write((content or "") + "\n\n")


@app.command("providers")
def providers_cmd() -> None:
    """List all providers and key status."""
    table = Table(title="hsearch providers", header_style="bold cyan")
    table.add_column("Provider", style="bold")
    table.add_column("Env var", style="dim")
    table.add_column("Status")
    for name in list_providers():
        env = PROVIDER_ENV[name]
        ok = bool(get_key(name))
        status = "[green]configured[/]" if ok else "[red]missing[/]"
        table.add_row(name, env, status)
    console.print(table)


@app.command()
def config() -> None:
    """Show current configuration."""
    cache = ResultCache()
    s = cache.stats()
    cache.close()
    table = Table(title="hsearch config", header_style="bold cyan")
    table.add_column("Setting", style="bold")
    table.add_column("Value")
    table.add_row("version", __version__)
    table.add_row("timeout (s)", str(timeout_seconds()))
    table.add_row("cache_ttl (s)", str(cache_ttl()))
    table.add_row("cache_dir", str(s.get("path") or cache_dir()))
    table.add_row("cache_entries", str(s["entries"]))
    table.add_row("cache_size_bytes", str(s["size_bytes"]))
    table.add_row("configured_providers", ", ".join(configured_providers()) or "(none)")
    console.print(table)


@app.command("schema")
def schema_cmd() -> None:
    """Output tool schema as JSON for LLM self-discovery.

    LLM agents can run ``hsearch schema`` to learn how to call this CLI.
    """
    from hsearch.schema import render_schema

    sys.stdout.write(render_schema() + "\n")


@app.command("mcp")
def mcp_cmd() -> None:
    """Start hsearch as a stdio MCP server."""
    try:
        from hsearch.mcp_server import run_stdio

        run_stdio()
    except RuntimeError as e:
        err_console.print(f"[red]MCP support is not installed.[/] {e}")
        raise typer.Exit(1)
    except ImportError:
        err_console.print(
            '[red]MCP support is not installed.[/] Install MCP support with: pip install -e ".[mcp]"'
        )
        raise typer.Exit(1)


@cache_app.command("clear")
def cache_clear() -> None:
    """Clear all cached search results."""
    c = ResultCache()
    path = c.stats().get("path") or str(cache_dir())
    n = c.clear()
    c.close()
    console.print(f"[green]Cleared[/] {n} cache entries from {path}")


@cache_app.command("stats")
def cache_stats() -> None:
    """Show cache statistics."""
    c = ResultCache()
    s = c.stats()
    c.close()
    console.print(s)


if __name__ == "__main__":
    app()
