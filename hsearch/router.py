"""Mode → providers routing."""
from __future__ import annotations

from hsearch.config import configured_providers

# Per-mode provider preference order. Real selection is intersected with what's configured.
MODE_MAP: dict[str, list[str]] = {
    "default": ["tavily"],
    "news": ["brave", "serper"],
    "academic": ["exa"],
    "code": ["exa", "brave"],
    "general": ["tavily", "brave"],
    "realtime": ["serper"],
    "shopping": ["serper", "brave"],
    "video": ["serper", "brave"],
    "images": ["serper", "brave"],
    "places": ["serper", "brave"],
    "answer": ["tavily", "brave"],
    "deep": ["exa"],
}

ALL_MODES: tuple[str, ...] = tuple(MODE_MAP)


def providers_for_mode(mode: str | None) -> list[str]:
    """Return the configured providers chosen for a given mode (in priority order).

    Falls back to the first configured provider if none of the preferred ones have keys.
    """
    key = (mode or "default").lower()
    pref = MODE_MAP.get(key, MODE_MAP["default"])
    available = set(configured_providers())
    chosen = [p for p in pref if p in available]
    if chosen:
        return chosen
    # Fallback: pick any configured provider deterministically.
    fallback = configured_providers()
    return fallback[:1]
