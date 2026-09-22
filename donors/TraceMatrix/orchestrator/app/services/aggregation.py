from __future__ import annotations
from typing import Iterable, List
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import re
from ..models import SearchResult

_TRACKING_RE = re.compile(r"^(utm_|fbclid|gclid|yclid|mc_cid|mc_eid|ref|ref_src)$", re.I)

def normalize_url(u: str) -> str:
    try:
        parts = urlsplit(u)
        q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _TRACKING_RE.match(k)]
        q.sort()
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), re.sub(r"/+", "/", parts.path), urlencode(q, doseq=True), ""))
    except Exception:
        return u

def dedup(items: Iterable[SearchResult]) -> List[SearchResult]:
    seen, out = set(), []
    for it in items:
        key = normalize_url(it.url)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out

def apply_rrf(results: List[SearchResult], k: int = 60) -> List[SearchResult]:
    for r in results:
        r.rank = r.rank if r.rank is not None else getattr(r, "engine_rank", 1000)
        r.rrf = 1.0 / (k + (r.rank or 1000))
    return sorted(results, key=lambda x: x.rrf or 0.0, reverse=True)

