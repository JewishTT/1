from __future__ import annotations
import os, requests
from typing import Dict, Any

def social_analyzer_username(username: str, base_url: str = None) -> Dict[str, Any]:
    # HTTP-only (no SSL). Default compose mapping exposes 9005.
    base_url = base_url or os.getenv("SOCIAL_ANALYZER_URL", "http://social-analyzer:9005")
    url = f"{base_url.rstrip('/')}/api/search"
    try:
        r = requests.post(url, json={"username": username}, timeout=60)
        r.raise_for_status()
        return {"tool":"social-analyzer", "json": r.json()}
    except Exception as e:
        return {"tool":"social-analyzer", "error": str(e)}
