"""Discovery contracts: Candidate, source protocol, canonicalization (T008-01).

A Candidate is a *candidate for acquisition*, never an observation: it carries
provenance (source, method, query/seed, originating observation) and is
idempotent by canonical URL (FR-006). Canonicalization is intentionally
conservative: scheme/host lowercased, fragment dropped, default ports
normalized, trailing slash preserved (it is significant).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol
from urllib.parse import urlsplit, urlunsplit

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_DEFAULT_PORTS = {"http": 80, "https": 443}


def canonicalize(url: str) -> str | None:
    """Return the canonical form of ``url`` or None if it is not http(s).

    Deterministic and allocation-light: same input always yields same output.
    """
    if not url or not url.strip():
        return None
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        return None
    host = parts.hostname or ""
    if not host:
        return None
    host = host.lower().rstrip(".")
    if host.endswith(":"):
        host = host[:-1]
    port = parts.port
    netloc = host
    if port is not None and _DEFAULT_PORTS.get(scheme) != port:
        netloc = f"{host}:{port}"
    path = parts.path or "/"
    query = parts.query
    return urlunsplit((scheme, netloc, path, query, ""))


@dataclass(frozen=True)
class Candidate:
    """A discovered URL with provenance (FR-007)."""

    url: str
    canonical_url: str
    source: str
    method: str
    confidence: float = 0.5
    query: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)

    def as_event_payload(self) -> dict[str, Any]:
        """Payload for a ``discovery.discovered`` envelope."""
        return {
            "uri": self.url,
            "canonical_url": self.canonical_url,
            "source": self.source,
            "method": self.method,
            "confidence": self.confidence,
            "query": self.query,
            "provenance": dict(self.provenance),
        }


class DiscoverySource(Protocol):
    """Contract every discovery source implements (FR-001)."""

    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> frozenset[str]: ...

    def discover(self, query: str) -> list[Candidate]: ...


def candidates_from_urls(
    urls: Iterable[str],
    *,
    source: str,
    method: str,
    query: str = "",
    confidence: float = 0.5,
    provenance: dict[str, Any] | None = None,
) -> list[Candidate]:
    """Build candidates from raw URLs, dropping non-http(s) and duplicates."""
    out: list[Candidate] = []
    seen: set[str] = set()
    for raw in urls:
        canonical = canonicalize(raw)
        if canonical is None or canonical in seen:
            continue
        seen.add(canonical)
        out.append(
            Candidate(
                url=raw.strip(),
                canonical_url=canonical,
                source=source,
                method=method,
                confidence=confidence,
                query=query,
                provenance=dict(provenance or {}),
            )
        )
    return out


def coalesce(candidates: Iterable[Candidate]) -> list[Candidate]:
    """Coalesce duplicates by canonical URL, merging provenance (FR-006).

    Deterministic: first occurrence wins for scalar fields, provenance lists
    are accumulated in encounter order so replay produces identical output.
    """
    merged: dict[str, Candidate] = {}
    for cand in candidates:
        existing = merged.get(cand.canonical_url)
        if existing is None:
            merged[cand.canonical_url] = cand
            continue
        prov = dict(existing.provenance)
        seen_by: list[dict[str, Any]] = list(prov.get("seen_by", []))
        seen_by.append({"source": cand.source, "method": cand.method})
        prov["seen_by"] = seen_by
        prov.setdefault("sources", [existing.source])
        if cand.source not in prov["sources"]:
            prov["sources"].append(cand.source)
        merged[cand.canonical_url] = Candidate(
            url=existing.url,
            canonical_url=existing.canonical_url,
            source=existing.source,
            method=existing.method,
            confidence=max(existing.confidence, cand.confidence),
            query=existing.query,
            provenance=prov,
        )
    return [merged[key] for key in sorted(merged)]
