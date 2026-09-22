from __future__ import annotations
import os
from typing import List, Set
import httpx

DEFAULT_TIMEOUT = float(os.getenv("SEARXNG_TIMEOUT", "8.0"))
DEFAULT_BASE = os.getenv("SEARXNG_URL") or os.getenv("SEARXNG_BASE_URL") or "http://searxng:8080"

def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out

def discover_urls(query: str, k: int = 10, base_url: str | None = None, timeout: float = DEFAULT_TIMEOUT) -> List[str]:
    """
    Χτυπά SearXNG JSON API και επιστρέφει μέχρι k μοναδικά URLs.
    Προτιμά `url` πεδίο από SERP entries, αγνοεί non-http(s).
    """
    base = (base_url or DEFAULT_BASE).rstrip("/")
    # JSON endpoint: /search?q=...&format=json&categories=general
    url = f"{base}/search"
    params = {"q": query, "format": "json", "categories": "general", "pageno": 1}

    urls: List[str] = []
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("results", []):
                u = item.get("url") or ""
                if u.startswith("http://") or u.startswith("https://"):
                    urls.append(u)
                    if len(urls) >= k:
                        break
    except Exception:
        # Σιωπηλή αποτυχία: ο caller θα αποφασίσει τι θα κάνει αν δεν βρούμε τίποτα
        return []

    return _dedupe_keep_order(urls)

