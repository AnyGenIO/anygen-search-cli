from hsearch.dedup import canonicalize_url, dedup_merge
from hsearch.models import SearchResult


def test_canonicalize_strips_utm_and_fragment():
    a = canonicalize_url("https://Example.com/path/?utm_source=x&id=1#frag")
    b = canonicalize_url("https://www.example.com/path?id=1")
    assert a == b


def test_canonicalize_preserves_real_query():
    u = canonicalize_url("https://example.com/q?id=42&utm_medium=foo")
    assert "id=42" in u
    assert "utm_medium" not in u


def test_dedup_merges_sources_and_boosts_score():
    r1 = SearchResult(url="https://a.com/x?utm_source=z", title="A", snippet="short", provider="brave", score=0.5)
    r2 = SearchResult(url="https://A.COM/x", title="A long title", snippet="much longer snippet here", provider="tavily", score=0.6)
    r3 = SearchResult(url="https://b.com/y", title="B", snippet="b", provider="exa", score=0.4)

    merged = dedup_merge([r1, r2, r3])
    assert len(merged) == 2
    top = merged[0]
    assert set(top.sources) == {"brave", "tavily"}
    assert top.title == "A long title"  # longer kept
    assert top.snippet.startswith("much longer")
    # multi-source hit ranks first
    assert merged[0].score >= merged[1].score
