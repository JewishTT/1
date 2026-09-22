"""Wayback CDX discovery source (FR-003).

Reads the Internet Archive CDX index through its public interface only
(Constitution VII). Transport is injected so contract tests run offline.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from .contracts import Candidate, candidates_from_urls

Transport = Callable[[str], str]

_DEFAULT_BASE = "https://web.archive.org/cdx/search/cdx"


class WaybackCdxSource:
    """Historical URL discovery via the Wayback CDX index."""

    def __init__(
        self,
        *,
        base_url: str = _DEFAULT_BASE,
        limit: int = 500,
        transport: Transport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._limit = limit
        self._transport = transport

    @property
    def name(self) -> str:
        return "wayback-cdx"

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"archive", "cdx"})

    def discover(self, query: str) -> list[Candidate]:
        body = self._fetch(self._build_url(query))
        urls = self._parse(body)
        return candidates_from_urls(
            urls,
            source=self.name,
            method="cdx",
            query=query,
            confidence=0.6,
            provenance={"endpoint": self._base_url},
        )

    def _build_url(self, query: str) -> str:
        domain = query.strip()
        return (
            f"{self._base_url}?url=*.{domain}"
            f"&output=json&fl=original,timestamp,statuscode"
            f"&collapse=urlkey&limit={self._limit}"
        )

    def _fetch(self, url: str) -> str:
        if self._transport is not None:
            return self._transport(url)
        import httpx  # lazy: keep module import cheap and offline-safe

        response = httpx.get(url, timeout=30.0)
        response.raise_for_status()
        return response.text

    @staticmethod
    def _parse(body: str) -> list[str]:
        """Parse a CDX JSON response (``[["original","timestamp","statuscode"], ...]``)."""
        if not body or not body.strip():
            return []
        try:
            payload: list[list[Any]] = json.loads(body)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list) or not payload:
            return []
        rows = payload[1:] if payload and isinstance(payload[0], list) and payload[0] and str(payload[0][0]).lower() == "original" else payload
        out: list[str] = []
        for row in rows:
            if isinstance(row, list) and row:
                out.append(str(row[0]))
        return out
