from typing import Dict, Any
import httpx

class QuotaExceeded(Exception): ...

async def guarded_google_get(client: httpx.AsyncClient, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    r = await client.get(url, params=params)
    if r.status_code in (403, 429):
        try:
            reason = r.json().get("error", {}).get("errors", [{}])[0].get("reason", "")
        except Exception:
            reason = ""
        if "dailyLimitExceeded" in reason or "userRateLimitExceeded" in reason or r.status_code == 429:
            raise QuotaExceeded(reason or "quota")
    r.raise_for_status()
    return r.json()

