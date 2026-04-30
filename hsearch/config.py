"""Configuration loading for provider API keys.

Load env vars from project-local ``.env``, the active Hermes profile ``.env``
(via ``HERMES_HOME``), and the user-level Hermes ``~/.hermes/.env``.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def _candidate_env_files() -> list[Path]:
    """Return env files in priority order.

    ``load_dotenv(..., override=False)`` means earlier files win, while explicit
    shell/process environment variables still win over every file. Hermes
    gateway sessions often set ``HOME`` to the profile sandbox
    (``.../profiles/<name>/home``), so relying only on ``Path.home()`` misses the
    real profile secrets. ``HERMES_HOME`` points at the active profile root.
    """
    files: list[Path] = []

    explicit = os.environ.get("HSEARCH_ENV_FILE")
    if explicit:
        files.append(Path(explicit).expanduser())

    files.append(Path.cwd() / ".env")

    hermes_home_raw = os.environ.get("HERMES_HOME")
    if hermes_home_raw:
        hermes_home = Path(hermes_home_raw).expanduser()
        files.append(hermes_home / ".env")
        # If HERMES_HOME is ~/.hermes/profiles/<profile>, also load the global
        # ~/.hermes/.env as a lower-priority fallback.
        if hermes_home.parent.name == "profiles":
            files.append(hermes_home.parent.parent / ".env")

    files.append(Path.home() / ".hermes" / ".env")

    seen: set[Path] = set()
    unique: list[Path] = []
    for path in files:
        resolved = path.expanduser()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


# Existing env vars take precedence (override=False) so explicit shell exports win.
for _env_file in _candidate_env_files():
    if _env_file.exists():
        load_dotenv(_env_file, override=False)


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
