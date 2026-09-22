import os, httpx
from typing import List, Dict
from ..services.cache import cache
from ..services.quota import guarded_google_get, QuotaExceeded

# Try to import constants from config; if missing, use safe defaults
try:
    from ..config import GOOGLE_CSE_ENDPOINT as _G_ENDPOINT
except Exception:
    _G_ENDPOINT = "https://customsearch.googleapis.com/customsearch/v1"
try:
    from ..config import GOOGLE_PAGE_SIZE as _G_PAGE_SIZE
except Exception:
    _G_PAGE_SIZE = 10
try:
    from ..config import GOOGLE_MAX_TOTAL as _G_MAX_TOTAL
except Exception:
    _G_MAX_TOTAL = 100

def google_available() -> bool:
    return bool(os.getenv("GOOGLE_CSE_API_KEY") and os.getenv("GOOGLE_CSE_CX"))

async def search_google_cse(query: str, target_total: int, timeout_s: float = 10.0) -> List[Dict]:
    if not google_available():
        return []
    key, cx = os.environ["GOOGLE_CSE_API_KEY"], os.environ["GOOGLE_CSE_CX"]
    to_fetch, start = min(target_total, _G_MAX_TOTAL), 1
    out: List[Dict] = []
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        while len(out) < to_fetch and start <= _G_MAX_TOTAL:
            num = min(_G_PAGE_SIZE, to_fetch - len(out))
            cache_key = f"g:{query}:{start}:{num}"
            data = cache.get(cache_key)
            if data is None:
                try:
                    data = await guarded_google_get(
                        client,
                        _G_ENDPOINT,
                        {"q": query, "key": key, "cx": cx, "num": num, "start": start},
                    )
                except QuotaExceeded:
                    break
                cache.set(cache_key, data)
            items = data.get("items") or []
            for idx, it in enumerate(items, start=1):
                out.append({
                    "title": it.get("title") or "",
                    "url": it.get("link") or "",
                    "snippet": it.get("snippet") or "",
                    "source": "google",
                    "engine_rank": start + (idx - 1),
                })
            if not items or len(items) < num: break
            start += _G_PAGE_SIZE
    return out
