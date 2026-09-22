"""Certificate-transparency subdomain discovery (FR-003).

Reads crt.sh through its public JSON interface only (Constitution VII).
Transport is injected so contract tests run offline.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from .contracts import Candidate, candidates_from_urls

Transport = Callable[[str], str]

_DEFAULT_BASE = "https://crt.sh"


class CrtshSource:
    """Subdomain discovery from certificate-transparency logs."""

    def __init__(
        self,
        *,
        base_url: str = _DEFAULT_BASE,
        transport: Transport | None = None,
        max_hosts: int = 200,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._max_hosts = max_hosts

    @property
    def name(self) -> str:
        return "crtsh"

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"ct-logs", "subdomains"})

    def discover(self, query: str) -> list[Candidate]:
        body = self._fetch(self._build_url(query))
        hosts = self._parse(body)
        urls = [f"https://{host}/" for host in hosts[: self._max_hosts]]
        return candidates_from_urls(
            urls,
            source=self.name,
            method="ct-logs",
            query=query,
            confidence=0.65,
            provenance={"endpoint": self._base_url},
        )

    def _build_url(self, query: str) -> str:
        domain = query.strip().lstrip(".")
        return f"{self._base_url}/?q=%25.{domain}&output=json"

    def _fetch(self, url: str) -> str:
        if self._transport is not None:
            return self._transport(url)
        import httpx  # lazy import: offline-safe

        response = httpx.get(url, timeout=45.0)
        response.raise_for_status()
        return response.text

    @staticmethod
    def _parse(body: str) -> list[str]:
        """Extract unique hostnames from a crt.sh JSON response."""
        if not body or not body.strip():
            return []
        try:
            payload: list[dict[str, Any]] = json.loads(body)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        seen: set[str] = set()
        out: list[str] = []
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            for raw in str(entry.get("name_value", "")).splitlines():
                host = raw.strip().lower().lstrip("*.").rstrip(".")
                if host and host not in seen:
                    seen.add(host)
                    out.append(host)
        return out
