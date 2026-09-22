import asyncio, json, os, random
from typing import List, Dict, Any
from .opensearch_client import index_email_accounts

REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "40"))
BACKOFF = float(os.getenv("RETRY_BACKOFF_SECONDS", "2.5"))
PROXY_POOL = [p.strip() for p in os.getenv("OUTBOUND_HTTP_PROXIES", "").split(",") if p.strip()]


def _env_with_proxy() -> dict:
    if not PROXY_POOL:
        return os.environ.copy()
    proxy = random.choice(PROXY_POOL)
    env = os.environ.copy()
    env.update({"HTTP_PROXY": proxy, "HTTPS_PROXY": proxy})
    return env


async def _run_holehe(email: str) -> List[Dict[str, Any]]:
    """
    Run holehe CLI with JSON output.
    Returns a list of dicts like:
      {"name": "...", "rateLimit": false, "exists": true, "emailrecovery": "...", "phoneNumber": "...", "others": ...}
    """
    cmd = ["holehe", "-j", "--only-used", email]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        env=_env_with_proxy(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=REQUEST_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("holehe timed out")
    if proc.returncode not in (0,):
        raise RuntimeError(f"holehe failed: {stderr.decode(errors='ignore')}")
    raw = stdout.decode().strip()
    # Holehe may print an array or newline-separated JSON objects; normalize to list
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
    except json.JSONDecodeError:
        data = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return data


async def holehe_lookup_and_index(email: str) -> List[Dict[str, Any]]:
    """
    Execute holehe with basic backoff on rateLimit=true entries and index successful hits.
    """
    results = await _run_holehe(email)
    # simple backoff retry once for rate-limited modules
    if any(r.get("rateLimit") for r in results):
        await asyncio.sleep(BACKOFF)
        retry = await _run_holehe(email)
        # merge (prefer exists:true from either try)
        merged = {}
        for r in results + retry:
            key = r.get("name") or r.get("service") or "unknown"
            merged[key] = r if r.get("exists") else merged.get(key, r)
        results = list(merged.values())
    # index only exists:true hits
    hits = [r for r in results if r.get("exists") is True]
    await index_email_accounts(email, hits)
    return hits

