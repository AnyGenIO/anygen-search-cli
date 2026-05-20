"""URL canonicalization + multi-provider result merging."""
from __future__ import annotations

from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from hsearch.models import SearchResult

# Tracking parameters to strip during canonicalization.
_STRIP_PREFIXES = ("utm_",)
_STRIP_EXACT = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "igshid",
    "yclid",
    "msclkid",
    "spm",
    "_hsenc",
    "_hsmi",
}


def canonicalize_url(url: str) -> str:
    """Normalize URL for dedup: lower host, strip tracking params + fragments + trailing slash."""
    if not url:
        return url
    try:
        p = urlparse(url.strip())
    except ValueError:
        return url
    scheme = (p.scheme or "https").lower()
    netloc = p.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    # Filter query params
    kept = [
        (k, v)
        for k, v in parse_qsl(p.query, keep_blank_values=False)
        if not (k.lower().startswith(_STRIP_PREFIXES) or k.lower() in _STRIP_EXACT)
    ]
    query = urlencode(kept, doseq=True)
    path = p.path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", query, ""))


def dedup_merge(results: list[SearchResult]) -> list[SearchResult]:
    """Merge duplicates by canonical URL; multi-source hits get a score boost."""
    bucket: dict[str, SearchResult] = {}
    order: list[str] = []
    for r in results:
        key = canonicalize_url(r.url)
        if not key:
            continue
        if key not in bucket:
            r.sources = list(dict.fromkeys(r.sources or [r.provider]))
            bucket[key] = r
            order.append(key)
        else:
            existing = bucket[key]
            for src in r.sources or [r.provider]:
                if src and src not in existing.sources:
                    existing.sources.append(src)
            if len(r.snippet) > len(existing.snippet):
                existing.snippet = r.snippet
            if r.title and (not existing.title or len(r.title) > len(existing.title)):
                existing.title = r.title
            if r.published and not existing.published:
                existing.published = r.published
            if r.content and (not existing.content or len(r.content) > len(existing.content)):
                existing.content = r.content
            if r.summary and not existing.summary:
                existing.summary = r.summary
            if r.favicon and not existing.favicon:
                existing.favicon = r.favicon
            if r.author and not existing.author:
                existing.author = r.author
            if r.image and not existing.image:
                existing.image = r.image

    merged = [bucket[k] for k in order]
    for r in merged:
        base = r.score or 0.0
        source_boost = max(0, len(r.sources) - 1)
        richness = sum([
            0.3 if r.content else 0,
            0.2 if r.summary else 0,
            0.1 if r.published else 0,
        ])
        r.score = base + source_boost + richness
    merged.sort(key=lambda x: (-(x.score or 0.0), -len(x.sources)))
    return merged
