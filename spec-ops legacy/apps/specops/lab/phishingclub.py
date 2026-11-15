"""HTTP adapter for the full Phishing Club donor service.

The donor is a Go/Gin service with its own admin console, API-key auth and SQLite store.
It is not imported as a library. The platform runs it as a local service and forwards
console/API traffic through this adapter, which keeps the donor's full feature set
(campaigns, templates, recipients, SMTP/API senders, remote browser, reporting) available
without re-implementing it.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx

DEFAULT_BASE_URL = "https://127.0.0.1:8002"
DEFAULT_CONSOLE_URL = "https://127.0.0.1:8002"
_API_KEY_HEADER = "x-API"
_TIMEOUT = 10.0
_FORWARDED_RESPONSE_HEADERS = (
    "content-type",
    "content-disposition",
    "location",
    "set-cookie",
    "cache-control",
)


def _verify_tls(base_url: str) -> bool:
    explicit = os.environ.get("PHISHINGCLUB_VERIFY_TLS")
    if explicit is not None:
        return explicit.strip().lower() not in {"0", "false", "no", "off"}
    host = urlsplit(base_url).hostname or ""
    return host not in {"127.0.0.1", "localhost", "::1"}


def config() -> dict[str, Any]:
    base_url = (os.environ.get("PHISHINGCLUB_URL") or DEFAULT_BASE_URL).rstrip("/")
    console_url = (
        os.environ.get("PHISHINGCLUB_CONSOLE_URL") or base_url or DEFAULT_CONSOLE_URL
    ).rstrip("/")
    api_key = os.environ.get("PHISHINGCLUB_API_KEY") or ""
    return {
        "base_url": base_url,
        "console_url": console_url,
        "api_key": api_key,
        "api_key_configured": bool(api_key),
        "verify_tls": _verify_tls(base_url),
        "configured": bool(base_url),
    }


def _headers(api_key: str, incoming: dict[str, str] | None = None) -> dict[str, str]:
    headers: dict[str, str] = {"accept": "application/json, text/html;q=0.9, */*;q=0.8"}
    incoming = incoming or {}
    for name in ("cookie", "content-type", "accept-language"):
        value = incoming.get(name)
        if value:
            headers[name] = value
    if api_key:
        headers[_API_KEY_HEADER] = api_key
    elif incoming.get(_API_KEY_HEADER):
        headers[_API_KEY_HEADER] = incoming[_API_KEY_HEADER]
    return headers


async def health() -> dict[str, Any]:
    cfg = config()
    if not cfg["base_url"]:
        return {"configured": False, "reachable": False, "status": None, "error": "PHISHINGCLUB_URL is empty"}
    try:
        async with httpx.AsyncClient(
            timeout=3.0, follow_redirects=False, verify=cfg["verify_tls"]
        ) as client:
            response = await client.get(
                f"{cfg['base_url']}/api/v1/healthz", headers=_headers(cfg["api_key"])
            )
        return {
            "configured": True,
            "reachable": response.status_code < 500,
            "status": response.status_code,
            "error": None if response.status_code < 500 else response.text[:300],
        }
    except httpx.HTTPError as exc:
        return {
            "configured": True,
            "reachable": False,
            "status": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


async def forward(
    method: str,
    path: str,
    *,
    query: str = "",
    headers: dict[str, str] | None = None,
    body: bytes = b"",
) -> tuple[int, dict[str, str], bytes]:
    cfg = config()
    if not cfg["base_url"]:
        return 503, {"content-type": "application/json"}, b'{"error":"PhishingClubUnconfigured"}'
    url = f"{cfg['base_url']}/{path.lstrip('/')}"
    if query:
        url = f"{url}?{query}"
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT, follow_redirects=False, verify=cfg["verify_tls"]
        ) as client:
            response = await client.request(
                method,
                url,
                headers=_headers(cfg["api_key"], headers),
                content=body or None,
            )
    except httpx.HTTPError as exc:
        payload = urlencode({"error": type(exc).__name__, "reason": str(exc)}).encode()
        return 502, {"content-type": "application/json"}, payload
    forwarded = {
        name: value
        for name, value in response.headers.items()
        if name.lower() in _FORWARDED_RESPONSE_HEADERS
    }
    return response.status_code, forwarded, response.content
