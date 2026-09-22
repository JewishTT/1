import httpx, os
from typing import List, Dict
from ..services.cache import cache

# Try import base URL from config; fall back to a sensible local default
try:
    from ..config import SEARXNG_BASE_URL as _SX_BASE
except Exception:
    _SX_BASE = "http://localhost:8081"

async def search_searxng(query: str, target_total: int, *, max_pages: int = 10, timeout_s: float = 10.0) -> List[Dict]:
    # Support both SEARXNG_BASE_URL and SEARX_BASE env vars
    base = os.getenv("SEARXNG_BASE_URL") or os.getenv("SEARX_BASE") or _SX_BASE
    results: List[Dict] = []
    pageno = 1
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        while len(results) < target_total and pageno <= max_pages:
            params = {"q": query, "format": "json", "pageno": pageno}
            cache_key = f"sx:{query}:{pageno}"
            data = cache.get(cache_key)
            if data is None:
                try:
                    r = await client.get(f"{base}/search", params=params)
                    r.raise_for_status()
                    data = r.json()
                except Exception:
                    # SearXNG not reachable or invalid; stop paging gracefully
                    break
                cache.set(cache_key, data)
            items = data.get("results") or []
            for idx, it in enumerate(items, start=1):
                results.append({
                    "title": it.get("title") or "",
                    "url": it.get("url") or "",
                    "snippet": it.get("content") or "",
                    "source": "searxng",
                    "engine_rank": ((pageno - 1) * 10) + idx,
                })
            if not items: break
            pageno += 1
    return results
