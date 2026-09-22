"""Discovery registry + frontier sink (T008-02, FR-005/FR-006).

The registry runs the registered sources for a seed, coalesces candidates and
pushes them into the frontier. The frontier is a protocol here: production
binds the Postgres frontier (ADR-0015); tests bind the in-memory sink. Kafka
is never the queue.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol

from .contracts import Candidate, DiscoverySource, coalesce


class FrontierSink(Protocol):
    """Minimal frontier contract discovery depends on (ADR-0015)."""

    def enqueue(
        self,
        *,
        uri: str,
        tenant_id: str,
        investigation_id: str,
        source: str,
        method: str,
        priority: int = 0,
        provenance: dict[str, Any] | None = None,
    ) -> None: ...


@dataclass
class InMemoryFrontierSink:
    """Deterministic sink for contract tests: idempotent by canonical URI."""

    items: dict[str, dict[str, Any]] = field(default_factory=dict)

    def enqueue(
        self,
        *,
        uri: str,
        tenant_id: str,
        investigation_id: str,
        source: str,
        method: str,
        priority: int = 0,
        provenance: dict[str, Any] | None = None,
    ) -> None:
        if uri in self.items:
            return  # idempotent by canonical URL (FR-006)
        self.items[uri] = {
            "uri": uri,
            "tenant_id": tenant_id,
            "investigation_id": investigation_id,
            "source": source,
            "method": method,
            "priority": priority,
            "provenance": dict(provenance or {}),
        }

    def uris(self) -> list[str]:
        return sorted(self.items)


@dataclass(frozen=True)
class DiscoveryReport:
    """Auditable result of one discovery pass (never a silent hang)."""

    query: str
    sources_run: list[str]
    sources_failed: list[dict[str, str]]
    candidates_found: int
    enqueued: int
    empty_sources: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "sources_run": self.sources_run,
            "sources_failed": self.sources_failed,
            "candidates_found": self.candidates_found,
            "enqueued": self.enqueued,
            "empty_sources": self.empty_sources,
        }


class DiscoveryRegistry:
    """Runs registered discovery sources and feeds the frontier."""

    def __init__(self) -> None:
        self._sources: dict[str, DiscoverySource] = {}

    def register(self, source: DiscoverySource) -> None:
        if not source.name:
            raise ValueError("discovery source requires a name")
        self._sources[source.name] = source

    def names(self) -> list[str]:
        return sorted(self._sources)

    def get(self, name: str) -> DiscoverySource | None:
        return self._sources.get(name)

    def discover(
        self,
        query: str,
        *,
        sources: Iterable[str] | None = None,
        frontier: FrontierSink | None = None,
        tenant_id: str = "default",
        investigation_id: str = "",
        priority: int = 0,
    ) -> DiscoveryReport:
        """Run sources for ``query``; coalesce; enqueue once per canonical URL."""
        selected = list(sources) if sources is not None else self.names()
        collected: list[Candidate] = []
        failed: list[dict[str, str]] = []
        empty: list[str] = []

        for name in selected:
            source = self._sources.get(name)
            if source is None:
                failed.append({"source": name, "error": "not registered"})
                continue
            try:
                found = source.discover(query)
            except Exception as exc:  # audited, never silently dropped
                failed.append({"source": name, "error": f"{type(exc).__name__}: {exc}"})
                continue
            if not found:
                empty.append(name)
            collected.extend(found)

        coalesced = coalesce(collected)

        enqueued = 0
        if frontier is not None:
            before = len(getattr(frontier, "items", {}))
            for cand in coalesced:
                provenance = dict(cand.provenance)
                provenance.setdefault("discovery", {})
                provenance["discovery"].update(
                    {"source": cand.source, "method": cand.method, "query": cand.query}
                )
                frontier.enqueue(
                    uri=cand.canonical_url,
                    tenant_id=tenant_id,
                    investigation_id=investigation_id,
                    source=cand.source,
                    method=cand.method,
                    priority=priority,
                    provenance=provenance,
                )
            after = len(getattr(frontier, "items", {}))
            if after > before:
                enqueued = after - before
            else:
                # Sink without introspection: count unique canonical candidates.
                enqueued = len(coalesced)

        return DiscoveryReport(
            query=query,
            sources_run=selected,
            sources_failed=failed,
            candidates_found=len(coalesced),
            enqueued=enqueued,
            empty_sources=empty,
        )
