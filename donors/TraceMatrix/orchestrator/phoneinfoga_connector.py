from __future__ import annotations
import os
from typing import Any, Dict, Optional
import requests

DEFAULT_BASE = os.getenv("PHONEINFOGA_URL", "http://phoneinfoga:8080").rstrip("/")

def _try_post_lookup(base: str, number: str, timeout: float) -> Optional[Dict[str, Any]]:
    try:
        url = f"{base}/api/lookup"
        r = requests.post(url, json={"number": number}, timeout=timeout)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def _try_get_scan(base: str, number: str, timeout: float) -> Optional[Dict[str, Any]]:
    # Some versions expose GET endpoints
    for path in (f"/api/numbers/{number}", f"/api/lookup?number={number}", f"/api/scan?number={number}"):
        try:
            url = f"{base}{path}"
            r = requests.get(url, timeout=timeout)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            return r.json()
        except Exception:
            continue
    return None

def phoneinfoga_lookup(number: str, base_url: Optional[str] = None, timeout: float = 30.0) -> Dict[str, Any]:
    base = (base_url or DEFAULT_BASE).rstrip("/")
    data = _try_post_lookup(base, number, timeout) or _try_get_scan(base, number, timeout)
    if data is not None:
        return {"tool": "phoneinfoga", "number": number, "json": data}
    return {"tool": "phoneinfoga", "number": number, "error": "lookup_failed"}

