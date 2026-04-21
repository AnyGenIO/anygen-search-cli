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
            # Clone-light: keep the first hit but ensure sources is set.
            r.sources = list(dict.fromkeys(r.sources or [r.provider]))
            bucket[key] = r
            order.append(key)
        else:
            existing = bucket[key]
            for src in r.sources or [r.provider]:
                if src and src not in existing.sources:
                    existing.sources.append(src)
            # Prefer the longer snippet/title when merging.
            if len(r.snippet) > len(existing.snippet):
                existing.snippet = r.snippet
            if r.title and (not existing.title or len(r.title) > len(existing.title)):
                existing.title = r.title
            if r.published and not existing.published:
                existing.published = r.published

    merged = [bucket[k] for k in order]
    # Score = base score + 1 per additional source. Sort stable by score desc.
    for r in merged:
        r.score = (r.score or 0.0) + max(0, len(r.sources) - 1)
    merged.sort(key=lambda x: (-(x.score or 0.0), -len(x.sources)))
    return merged
