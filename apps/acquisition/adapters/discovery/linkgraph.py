"""Link-graph discovery source (FR-004, US3).

Turns edges already materialized in the graph projection into new candidates:
links extracted from fetched content are the cheapest discovery source we own
(no external index, no manual search). Unseen targets only — known URLs are
deduplicated downstream by the registry/frontier.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

from .contracts import Candidate, canonicalize, candidates_from_urls

# An edge provider returns (source, target, edge_type) triples.
EdgeProvider = Callable[[], Iterable[tuple[str, str, str]]]


class LinkGraphSource:
    """Discovers unseen link targets from the graph projection."""

    def __init__(
        self,
        *,
        edge_provider: EdgeProvider,
        known_urls: Callable[[], frozenset[str]] | None = None,
        edge_types: frozenset[str] | None = None,
    ) -> None:
        self._edge_provider = edge_provider
        self._known_urls = known_urls
        self._edge_types = edge_types

    @property
    def name(self) -> str:
        return "link-graph"

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"web-graph", "links"})

    def discover(self, query: str) -> list[Candidate]:
        """``query`` filters targets by substring; empty means "everything".

        A caller that wants graph-wide expansion passes an empty query; the
        frontier policy (per-host budgets, ADR-0016) bounds the actual work.
        """
        known = self._known_urls() if self._known_urls is not None else frozenset()
        needle = query.strip().lower()
        out: list[Candidate] = []
        provenance: dict[str, Any] = {"provider": "graph-projection"}

        for source, target, edge_type in self._edge_provider():
            if self._edge_types is not None and edge_type not in self._edge_types:
                continue
            canonical = canonicalize(target)
            if canonical is None or canonical in known:
                continue
            if needle and needle not in canonical:
                continue
            out.append(
                Candidate(
                    url=target,
                    canonical_url=canonical,
                    source=self.name,
                    method=f"link:{edge_type}",
                    confidence=0.55,
                    query=query,
                    provenance={
                        **provenance,
                        "from_uri": source,
                        "edge_type": edge_type,
                    },
                )
            )

        # Reuse the shared builder semantics (dedup + canonical filter) while
        # preserving per-target provenance by rebuilding in encounter order.
        urls = [c.url for c in out]
        rebuilt = candidates_from_urls(
            urls,
            source=self.name,
            method="link",
            query=query,
            confidence=0.55,
            provenance=provenance,
        )
        by_url = {c.canonical_url: c for c in out}
        merged: list[Candidate] = []
        for base in rebuilt:
            original = by_url.get(base.canonical_url)
            if original is None:
                merged.append(base)
                continue
            merged.append(
                Candidate(
                    url=original.url,
                    canonical_url=original.canonical_url,
                    source=original.source,
                    method=original.method,
                    confidence=original.confidence,
                    query=original.query,
                    provenance=original.provenance,
                )
            )
        return merged
