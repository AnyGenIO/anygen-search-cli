"""hsearch — unified search over 6 commercial search APIs.

Quick start::

    from hsearch import search_sync, SearchResult

    resp = search_sync("Python tutorial", mode="general", top=5)
    for r in resp.results:
        print(r.title, r.url)

Async::

    from hsearch import search

    resp = await search("Python tutorial", providers=["tavily", "brave"])
"""

__version__ = "0.3.0"

from hsearch.engine import (
    ExtractResult,
    SearchResponse,
    extract_urls,
    extract_urls_sync,
    search,
    search_sync,
)
from hsearch.filters import Filters
from hsearch.models import SearchResult

__all__ = [
    "ExtractResult",
    "Filters",
    "SearchResponse",
    "SearchResult",
    "__version__",
    "extract_urls",
    "extract_urls_sync",
    "search",
    "search_sync",
]
