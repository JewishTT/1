
from __future__ import annotations
import os, requests
from typing import List, Dict, Optional

class GoogleCSEClient:
    def __init__(self, api_key: Optional[str] = None, cx: Optional[str] = None, per_query_num: int = 10, timeout: float = 15.0):
        self.api_key = api_key or os.getenv("GOOGLE_CSE_API_KEY", "")
        self.cx = cx or os.getenv("GOOGLE_CSE_CX", "")
        self.per_query_num = max(1, min(int(per_query_num), 10))
        self.timeout = timeout
        if not self.api_key or not self.cx:
            raise ValueError("Google CSE requires GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX.")

    def _join_query(self, q: str, site_filters: Optional[List[str]] = None) -> str:
        if not site_filters: return q
        sf = " OR ".join(site_filters)
        return f"({q}) ({sf})"

    def search(self, query: str, site_filters: Optional[List[str]] = None, num: Optional[int] = None, extra_params: Optional[Dict[str, str]] = None) -> List[Dict]:
        url = "https://customsearch.googleapis.com/customsearch/v1"
        params = {"key": self.api_key, "cx": self.cx, "q": self._join_query(query, site_filters), "num": str(num or self.per_query_num), "safe": "off"}
        if extra_params: params.update(extra_params)
        resp = requests.get(url, params=params, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", []) or []
        results = []
        for it in items:
            results.append({
                "title": it.get("title"),
                "url": it.get("link"),
                "snippet": it.get("snippet"),
                "display_link": it.get("displayLink"),
                "source": "google_cse",
                "site_weight": 1.0,
            })
        return results

def google_search(query: str, site_filters: Optional[List[str]] = None, num: int = 10):
    client = GoogleCSEClient(per_query_num=num)
    return client.search(query=query, site_filters=site_filters, num=num)

class ReacherClient:
    def __init__(self, base_url: Optional[str] = None, timeout: float = 15.0):
        self.base_url = (base_url or os.getenv("REACHER_BASE_URL") or "http://reacher:8080").rstrip("/")
        self.timeout = timeout

    def check_email(self, email: str) -> Dict:
        url = f"{self.base_url}/v0/check_email"
        payload = {"to_email": email}
        resp = requests.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

def verify_email_reacher(email: str, base_url: Optional[str] = None) -> Dict:
    client = ReacherClient(base_url=base_url)
    try:
        data = client.check_email(email)
    except Exception as e:
        return {"email": email, "provider": "reacher", "status": f"error:{e}", "mx_records_found": None, "score": 0.0}
    status = (data or {}).get("is_reachable") or "unknown"
    mx_found = bool(((data.get("mx") or {}).get("records") or [])) if data else None
    status_score_map = {"deliverable": 1.0, "risky": 0.6, "unknown": 0.5, "undeliverable": 0.0, "invalid": 0.0}
    score = status_score_map.get(status, 0.5)
    return {"email": email, "provider": "reacher", "status": status, "mx_records_found": mx_found, "score": score}
