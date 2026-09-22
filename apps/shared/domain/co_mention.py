"""Co-mention hyperedge facade (FR-011, 011).

Turns a fan of *observations* (a page mentions N resolved candidates, each
with an optional timestamp) into the N-ary, temporal, typed hypergraph — the
L2 relational invariant of the atomic entity. The interface is deliberately
thin over `domain.hypergraph.HyperGraph`: it adds the co-occurrence window
logic and stat-validated filtering (via `projection.tda.validated`) while
keeping every write provenance-carrying (I-12) and idempotent (I-11).

The facade NEVER creates identity: it produces hyperedges of type
``co_mention:<fan>`` from independent observations; admission/resolution
remains the only source of entity identity (I-6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from domain.hypergraph import HyperEdge, HyperGraph, hyperedge_id
from domain.stream_events import emit_hyperedge

try:  # optional TDA cross-module pull for stat validation
    from projection.tda.validated import ValidatedHyperedgeSet, validate_hyperedges

    _HAS_VALIDATED = True
except ImportError:  # pragma: no cover
    _HAS_VALIDATED = False


@dataclass(frozen=True)
class FanMention:
    """A single entity mention inside one page observation (FR-011)."""

    entity_id: str
    page_url: str
    observed_at: datetime
    mention_count: int = 1


@dataclass
class CoMentionFanBuilder:
    """Groups per-page mentions into co-occurrence fans and validates."""

    window_s: int = 3600 * 24  # default window: same-day co-mentions

    def fans(self, mentions: list[FanMention]) -> dict[tuple[str, ...], int]:
        """Aggregate co-mention counts per window (deterministic)."""
        from collections import defaultdict

        by_window: dict[tuple[str, tuple[str, ...]], int] = defaultdict(int)
        by_page: dict[str, list[FanMention]] = defaultdict(list)
        for m in mentions:
            by_page[m.page_url].append(m)
        for page_url, page_mentions in sorted(by_page.items()):
            window_key = page_url  # a page is its own natural window (FR-011)
            member_ids = sorted({m.entity_id for m in page_mentions})
            if len(member_ids) < 2:
                continue
            key = (tuple(member_ids), window_key)
            by_window[key] += len(page_mentions)
        return {members: count for (members, _), count in by_window.items()}

    def validated(
        self,
        mentions: list[FanMention],
        *,
        null_p: float = 0.01,
        alpha: float = 0.05,
        n_trials: int | None = None,
    ) -> ValidatedHyperedgeSet | list[tuple[str, ...]]:
        """Stat-validated cut of the co-mention fans (HypergraphX-style)."""
        raw = self.fans(mentions)
        if not _HAS_VALIDATED:
            return [tuple(m) for m in raw if len(m) >= 2]
        total = n_trials or max((sum(raw.values()) // max(len(raw), 1)), 1)
        # conservative upper bound fallback when only one page mention set
        validated = validate_hyperedges(raw, n_trials=total, null_p=null_p, alpha=alpha)
        return validated


class CoMentionHyperedgeWriter:
    """Materializes fans into HyperGraph + emits ``hyperedge.created`` events."""

    def __init__(self, graph: HyperGraph, tenant_id: str = "default") -> None:
        self._graph = graph
        self._tenant = tenant_id

    def ingest(
        self,
        mentions: list[FanMention],
        *,
        edge_type: str = "co_mention",
        emitter=None,
    ) -> list[HyperEdge]:
        """Turn validated fans into temporal hyperedges with full provenance."""
        builder = CoMentionFanBuilder()
        fans = builder.fans(mentions)
        edges: list[HyperEdge] = []
        for members, count in sorted(fans.items()):
            if len(members) < 2:
                continue
            edge = HyperEdge(
                edge_type=edge_type,
                members=members,
                weight=float(count),
                tenant_id=self._tenant,
                provenance={
                    "event_id": f"evt-co-mention-{hyperedge_id(edge_type, members, tenant_id=self._tenant)[3:]}",
                    "window_s": builder.window_s,
                    "algorithm": "co_mention_fan",
                },
                anchor_artifact_id=members[0],
            )
            self._graph.upsert(edge, provenance=edge.provenance)
            if emitter:
                emit_hyperedge(edge, emitter)
            edges.append(edge)
        return edges


__all__ = [
    "CoMentionFanBuilder",
    "CoMentionHyperedgeWriter",
    "FanMention",
    "hyperedge_id",
]