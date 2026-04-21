"""Configuration loading: env vars from ~/.hermes/.env (and project .env)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load order: project-local .env (if any), then user-level ~/.hermes/.env.
# Existing env vars take precedence (override=False) so explicit shell exports win.
_PROJECT_ENV = Path.cwd() / ".env"
_HERMES_ENV = Path.home() / ".hermes" / ".env"

if _PROJECT_ENV.exists():
    load_dotenv(_PROJECT_ENV, override=False)
if _HERMES_ENV.exists():
    load_dotenv(_HERMES_ENV, override=False)


PROVIDER_ENV: dict[str, str] = {
    "brave": "BRAVE_API_KEY",
    "serper": "SERPER_API_KEY",
    "exa": "EXA_API_KEY",
    "tavily": "TAVILY_API_KEY",
    "firecrawl": "FIRECRAWL_API_KEY",
    "jina": "JINA_API_KEY",
}

ALL_PROVIDERS: list[str] = list(PROVIDER_ENV)


def get_key(provider: str) -> str | None:
    var = PROVIDER_ENV.get(provider)
    if not var:
        return None
    val = os.environ.get(var)
    return val.strip() if val else None


def configured_providers() -> list[str]:
    return [p for p in ALL_PROVIDERS if get_key(p)]


def cache_dir() -> Path:
    base = os.environ.get("HSEARCH_CACHE_DIR")
    p = Path(base) if base else Path.home() / ".cache" / "hsearch"
    p.mkdir(parents=True, exist_ok=True)
    return p


def timeout_seconds() -> float:
    raw = os.environ.get("HSEARCH_TIMEOUT", "15")
    try:
        return float(raw)
    except ValueError:
        return 15.0


def cache_ttl() -> int:
    raw = os.environ.get("HSEARCH_CACHE_TTL", "3600")
    try:
        return int(raw)
    except ValueError:
        return 3600
