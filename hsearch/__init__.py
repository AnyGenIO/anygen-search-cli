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

__version__ = "0.6.0"

from hsearch.engine import (
    AnswerResponse,
    ExtractResult,
    GroundingResponse,
    SearchResponse,
    answer,
    answer_sync,
    extract_urls,
    extract_urls_sync,
    find_similar,
    find_similar_sync,
    ground,
    ground_sync,
    search,
    search_sync,
)
from hsearch.filters import Filters
from hsearch.models import SearchResult

__all__ = [
    "AnswerResponse",
    "ExtractResult",
    "Filters",
    "GroundingResponse",
    "SearchResponse",
    "SearchResult",
    "__version__",
    "answer",
    "answer_sync",
    "extract_urls",
    "extract_urls_sync",
    "find_similar",
    "find_similar_sync",
    "ground",
    "ground_sync",
    "search",
    "search_sync",
]
