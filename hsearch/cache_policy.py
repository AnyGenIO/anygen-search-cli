"""Adaptive cache TTL defaults for search modes."""
from __future__ import annotations

DEFAULT_CACHE_TTL_SECONDS = 3600

MODE_CACHE_TTL_SECONDS: dict[str, int] = {
    "realtime": 300,
    "news": 300,
    "finance": 900,
    "answer": 900,
    "general": 3600,
    "fast": 3600,
    "recall": 3600,
    "shopping": 3600,
    "video": 7200,
    "images": 7200,
    "places": 7200,
    "code": 14400,
    "deep": 14400,
    "company": 14400,
    "academic": 86400,
}


def default_cache_ttl(mode: str | None = None) -> int:
    """Return the default cache TTL for a routing mode."""
    key = (mode or "").lower() or "default"
    return MODE_CACHE_TTL_SECONDS.get(key, DEFAULT_CACHE_TTL_SECONDS)


def resolve_cache_ttl(mode: str | None = None, explicit_ttl: int | None = None) -> int:
    """Return the effective TTL, with explicit caller overrides taking precedence."""
    if explicit_ttl is not None:
        return int(explicit_ttl)
    return default_cache_ttl(mode)
