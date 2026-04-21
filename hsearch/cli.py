"""hsearch — typer-based CLI."""
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
from hsearch.dedup import dedup_merge
from hsearch.extract import extract_many
from hsearch.filters import Filters, apply as apply_filters
from hsearch.models import SearchResult
from hsearch.output import emit
from hsearch.providers import (
    ProviderAuthError,
    ProviderHTTPError,
    get_provider,
    list_providers,
)
from hsearch.router import ALL_MODES, providers_for_mode

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


async def _run_one(
    provider_name: str,
    query: str,
    count: int,
    use_cache: bool,
    cache: ResultCache,
    extra: dict,
    filters: Filters | None = None,
    cache_ttl_override: int | None = None,
) -> tuple[str, list[SearchResult] | None, str | None, dict]:
    # Translate filters to per-provider kwargs + possibly rewrite query.
    if filters is not None:
        eff_query, eff_extra = apply_filters(provider_name, query, filters, extra)
    else:
        eff_query, eff_extra = query, dict(extra)
    extras_out: dict = {}
    # Cache key params should not include private flags like _retries.
    cache_params = {k: v for k, v in {"count": count, **eff_extra}.items() if not str(k).startswith("_")}
    if use_cache:
        hit = cache.get(provider_name, eff_query, cache_params)
        if hit is not None:
            results = [SearchResult(**r) for r in hit]
            return provider_name, results, None, extras_out
    try:
        provider = get_provider(provider_name)
    except KeyError as e:
        return provider_name, None, str(e), extras_out
    try:
        async with provider:
            results = await provider.search(eff_query, count=count, **eff_extra)
            # Capture provider-specific extras.
            ans = getattr(provider, "_last_answer", None)
            if ans:
                extras_out["answer"] = ans
    except ProviderAuthError as e:
        return provider_name, None, f"auth: {e}", extras_out
    except ProviderHTTPError as e:
        return provider_name, None, f"http: {e}", extras_out
    except Exception as e:  # noqa: BLE001
        return provider_name, None, f"{type(e).__name__}: {e}", extras_out

    if use_cache:
        cache.set(
            provider_name,
            eff_query,
            cache_params,
            [r.to_dict() | {"raw": {}} for r in results],
            ttl=cache_ttl_override,
        )
    return provider_name, results, None, extras_out


async def _run_many(
    providers: list[str],
    query: str,
    count: int,
    use_cache: bool,
    extra: dict,
    filters: Filters | None = None,
    cache_ttl_override: int | None = None,
) -> tuple[list[SearchResult], dict[str, str], dict[str, dict]]:
    cache = ResultCache()
    try:
        coros = [
            _run_one(p, query, count, use_cache, cache, extra, filters, cache_ttl_override)
            for p in providers
        ]
        outcomes = await asyncio.gather(*coros)
    finally:
        cache.close()

    merged: list[SearchResult] = []
    errors: dict[str, str] = {}
    extras_by_provider: dict[str, dict] = {}
    for name, results, err, extras in outcomes:
        if extras:
            extras_by_provider[name] = extras
        if err is not None or results is None:
            errors[name] = err or "no results"
            continue
        merged.extend(results)
    return merged, errors, extras_by_provider


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
    fmt: str = typer.Option(
        "table", "--format", "-f", help="Output: table | json | jsonl | markdown | urls"
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
    site: list[str] = typer.Option(None, "--site", help="Restrict to site(s); repeatable."),
    exclude: list[str] = typer.Option(None, "--exclude", help="Exclude site(s); repeatable."),
    extract_top: int = typer.Option(
        0, "--extract-top", help="Extract content of top-N merged results via Jina."
    ),
    # ---- v0.2 new options ---------------------------------------------------
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
    livecrawl: Optional[str] = typer.Option(
        None, "--livecrawl",
        help="Exa contents.livecrawl: always|fallback|never.",
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
    days: Optional[int] = typer.Option(
        None, "--days",
        help="Tavily news mode: results from past N days.",
    ),
) -> None:
    """Run a search across one, many, or all providers."""
    try:
        filters = Filters.from_cli(
            time=time, lang=lang, region=region, sites=site, exclude=exclude
        )
    except ValueError as e:
        err_console.print(f"[red]Invalid filter:[/] {e}")
        raise typer.Exit(2)

    if all_providers:
        providers = configured_providers()
    elif provider:
        providers = list(provider)
    else:
        providers = providers_for_mode(mode)

    if not providers:
        err_console.print("[red]No providers configured.[/] Set API keys in ~/.hermes/.env")
        raise typer.Exit(2)

    extra: dict = {}
    if mode == "news":
        extra["topic"] = "news"
        extra["freshness"] = "pw"
    elif mode == "academic":
        extra["category"] = "research paper"
    elif mode == "realtime":
        extra["freshness"] = "pd"
    elif mode == "shopping":
        extra["search_type"] = "shopping"
    elif mode == "video":
        extra["search_type"] = "videos"
    elif mode == "images":
        extra["search_type"] = "images"
    elif mode == "places":
        extra["search_type"] = "places"
    elif mode == "answer":
        # Auto-enable answer panel.
        answer = True
    elif mode == "deep":
        extra["type"] = "deep-reasoning"
        extra["summary"] = True

    # ---- v0.2 flags -> provider kwargs -----------------------------------
    if answer:
        # Tavily understands include_answer; other providers ignore it.
        extra["include_answer"] = True
    if summary:
        extra["summary"] = True
    if sources:
        extra["sources"] = [s.strip() for s in sources.split(",") if s.strip()]
    if livecrawl:
        extra["livecrawl"] = livecrawl
    if auto:
        extra["auto_parameters"] = True
    if raw:
        extra["include_raw_content"] = "markdown"
    if days is not None:
        extra["days"] = days
    if retries is not None:
        extra["_retries"] = retries

    results, errors, extras_by_provider = asyncio.run(
        _run_many(
            providers, query, top, use_cache=not no_cache, extra=extra,
            filters=filters, cache_ttl_override=cache_ttl_opt,
        )
    )

    merged = dedup_merge(results)
    limit = max(top, 1) if not all_providers else top * len(providers)
    merged = merged[:limit]

    if extract_top and extract_top > 0 and merged:
        urls = [r.url for r in merged[:extract_top] if r.url]
        outcomes = asyncio.run(extract_many(urls, provider="jina", concurrency=4))
        url_to_content = {u: c for (u, c, _e) in outcomes if c}
        for r in merged:
            if r.url in url_to_content:
                r.content = url_to_content[r.url]

    # ---- Top-of-output answer panel (Tavily) -----------------------------
    tavily_answer = (extras_by_provider.get("tavily") or {}).get("answer")
    if (answer or mode == "answer") and tavily_answer and fmt in ("table", "markdown", "md"):
        if fmt == "table":
            console.print(
                Panel(
                    tavily_answer,
                    title="[bold green]Tavily Answer[/]",
                    border_style="green",
                    expand=True,
                )
            )
        else:
            sys.stdout.write(f"## Answer\n\n{tavily_answer}\n\n")

    emit(merged, fmt, console=console)
    _print_errors(errors)
    if not merged and errors:
        raise typer.Exit(1)


@app.command()
def extract(
    urls: list[str] = typer.Argument(..., help="One or more URLs to extract."),
    provider: str = typer.Option(
        "jina", "--provider", "-p", help="jina | firecrawl"
    ),
    fmt: str = typer.Option("markdown", "--format", "-f", help="markdown | json"),
    concurrency: int = typer.Option(4, "--concurrency", "-c", help="Parallel requests."),
) -> None:
    """Fetch one or more URLs and return clean markdown/text."""
    outcomes = asyncio.run(extract_many(urls, provider=provider, concurrency=concurrency))
    if fmt == "json":
        import json

        payload = [
            {"url": u, "content": c, "error": e} for (u, c, e) in outcomes
        ]
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return
    # markdown
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
        status = "[green]✅ configured[/]" if ok else "[red]❌ missing[/]"
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
    table.add_row("cache_dir", str(cache_dir()))
    table.add_row("cache_entries", str(s["entries"]))
    table.add_row("cache_size_bytes", str(s["size_bytes"]))
    table.add_row("configured_providers", ", ".join(configured_providers()) or "(none)")
    console.print(table)


@cache_app.command("clear")
def cache_clear() -> None:
    """Clear all cached search results."""
    c = ResultCache()
    n = c.clear()
    c.close()
    console.print(f"[green]Cleared[/] {n} cache entries from {cache_dir()}")


@cache_app.command("stats")
def cache_stats() -> None:
    """Show cache statistics."""
    c = ResultCache()
    s = c.stats()
    c.close()
    console.print(s)


if __name__ == "__main__":
    app()
