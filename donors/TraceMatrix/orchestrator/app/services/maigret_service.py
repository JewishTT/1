import asyncio, json, os, random
from typing import List, Dict, Any
from .opensearch_client import ensure_indices  # ensure indices available when indexing

REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "60"))
PROXY_POOL = [p.strip() for p in os.getenv("OUTBOUND_HTTP_PROXIES", "").split(",") if p.strip()]


def _env_with_proxy() -> dict:
    if not PROXY_POOL:
        return os.environ.copy()
    proxy = random.choice(PROXY_POOL)
    env = os.environ.copy()
    env.update({"HTTP_PROXY": proxy, "HTTPS_PROXY": proxy})
    return env


async def _run_maigret(username: str) -> List[Dict[str, Any]]:
    """
    Run maigret CLI with JSON lines output.
    Maigret prints one JSON object per line (NDJSON) when using --json or --json-out=-.
    We'll prefer NDJSON via --json --no-color and parse per line.
    """
    # Using NDJSON: --json prints results to stdout line by line in recent versions
    cmd = [
        "maigret",
        "--json",
        "--no-color",
        "--timeout", os.getenv("MAIGRET_TIMEOUT", "30"),
        username,
    ]
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
        raise RuntimeError("maigret timed out")
    if proc.returncode not in (0,):
        # Some versions return non-zero even if partial output exists; try to parse anyway
        raw = stdout.decode(errors="ignore").strip()
        if not raw:
            raise RuntimeError(f"maigret failed: {stderr.decode(errors='ignore')}")
    else:
        raw = stdout.decode(errors="ignore").strip()

    hits: List[Dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Expected keys in tests: site, url_user, status
        site = obj.get("site") or obj.get("name")
        url = obj.get("url_user") or obj.get("url") or ""
        status = (obj.get("status") or "").upper()
        if status == "FOUND" and url:
            hits.append({"site": site or "", "url": url, "source": "maigret"})
    return hits


async def maigret_lookup(username: str) -> List[Dict[str, Any]]:
    hits = await _run_maigret(username)
    # Optionally ensure indices; indexing usernames is handled by opensearch_client if needed later
    try:
        await ensure_indices()
    except Exception:
        pass
    return hits

