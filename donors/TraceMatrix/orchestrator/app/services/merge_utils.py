from typing import List, Dict
from urllib.parse import urlparse


def _norm_url(u: str) -> str:
    try:
        p = urlparse(u)
        host = (p.netloc or "").lower().lstrip("www.")
        path = (p.path or "/").rstrip("/")
        return f"{host}{path}"
    except Exception:
        return (u or "").strip().lower()


def merge_username_hits(sa_hits: List[Dict], mg_hits: List[Dict]) -> List[Dict]:
    """
    Merge Social-Analyzer and Maigret hits, deduplicating by URL.
    Preference: keep the first source encountered; if same URL appears from both,
    retain the 'social-analyzer' variant to preserve its fields.
    """
    out: List[Dict] = []
    seen = {}
    for h in (sa_hits or []) + (mg_hits or []):
        url = h.get("url") or ""
        if not url:
            continue
        key = _norm_url(url)
        if key in seen:
            # prefer social-analyzer if incoming is social-analyzer
            if h.get("source") == "social-analyzer" and out[seen[key]].get("source") != "social-analyzer":
                out[seen[key]] = h
            continue
        seen[key] = len(out)
        out.append(h)
    return out

