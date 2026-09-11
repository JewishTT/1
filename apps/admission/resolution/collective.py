"""Collective/graph-aware resolution (T083, FR-013).

Builds a candidate-resolution graph from pairwise scores, propagates evidence
along edges (a↔b and b↔c strong ⇒ a↔c boosted), and iterates until the graph
converges. Output per-pair `collective_score` + reasons. Transparent: every
score is a documented arithmetic function of pair evidence, not a black-box.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

from donor.correlation_graph import CorrelationGraph, CorrelationKind, CorrelationLink, make_node
from donor.temporal import scan as temporal_conflicts_scan
from events.kafka import build_envelope
from events.topics import topic_for

from .candidate import (
    Candidate,
    CandidateState,
    apply_review,
    create_candidate,
)
from .resolver import ResolvedPair


@dataclass
class CorrelationEdge:
    """possible_match edge between candidates (FR-004, I-2, OpenOSINT pattern).

    An edge expresses "these two candidates are somehow related" — it NEVER
    collapses them into an entity. Identity comes only from an admitted assertion;
    the edge carries raw_pair_score + reasons and an explicit OPEN→REVIEWED→RESOLVED
    lifecycle driven by analysts/projections.
    """

    candidate_a: str
    candidate_b: str
    edge_id: str = field(default_factory=lambda: "CE-" + uuid.uuid4().hex[:12])
    kind: str = "possible_match"
    raw_pair_score: float = 0.0
    collective_score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    state: str = "OPEN"

    def to_dict(self) -> dict:
        return {
            "edge_id": self.edge_id,
            "candidate_a": self.candidate_a,
            "candidate_b": self.candidate_b,
            "kind": self.kind,
            "raw_pair_score": round(self.raw_pair_score, 3),
            "collective_score": round(self.collective_score, 3),
            "reasons": list(self.reasons),
            "state": self.state,
        }


def correlate(pairs: list[ResolvedPair]) -> list[CorrelationEdge]:
    """Build possible_match correlation edges WITHOUT any auto-merge (I-2)."""
    edges: list[CorrelationEdge] = []
    for p in sorted(pairs, key=lambda p: (p.candidate_a, p.candidate_b)):
        if p.raw_pair_score <= 0.0:
            continue
        edges.append(
            CorrelationEdge(
                candidate_a=p.candidate_a,
                candidate_b=p.candidate_b,
                kind="possible_match",
                raw_pair_score=p.raw_pair_score,
                collective_score=p.collective_score,
                reasons=list(p.reasons),
                state="OPEN",
            )
        )
    return edges


class CorrelationService:
    """Creates correlation edges and emits ``correlation.edge_created`` events (T033).

    Projections rebuild the correlation graph from these durable events (I-12);
    the service never merges candidates (I-2).
    """

    def __init__(self, producer=None) -> None:
        self._producer = producer
        self._edges: dict[str, CorrelationEdge] = {}
        self._candidates: dict[str, Candidate] = {}

    def create_edges(self, pairs: list[ResolvedPair]) -> list[CorrelationEdge]:
        edges = correlate(pairs)
        for edge in edges:
            self._edges[edge.edge_id] = edge
            if self._producer is not None:
                envelope = build_envelope(
                    event_type="correlation.edge_created",
                    event_version="1.0",
                    producer="admission.correlation",
                    producer_version="0.1.0",
                    payload=json.dumps(edge.to_dict(), default=str).encode("utf-8"),
                    entity_id=edge.candidate_a,
                    event_id=f"evt-{edge.edge_id}",
                )
                self._producer.produce(
                    topic_for("correlation.edge_created"), envelope, key=edge.edge_id
                )
        return edges

    def create_candidates(self, pairs: list[ResolvedPair]) -> list[Candidate]:
        """Materialise reviewable Candidates for every correlated pair (feature 005 US2).

        Candidates are paired ``possible identity`` records with a deterministic
        ``pair_key`` — no merge ever happens here (I-2). Emits
        ``resolution.candidate_created`` (refs-only payload, I-5).
        """
        candidates: list[Candidate] = []
        for edge in correlate(pairs):
            candidate = create_candidate(
                edge.candidate_a,
                edge.candidate_b,
                raw_pair_score=edge.raw_pair_score,
                collective_score=edge.collective_score,
                reasons=edge.reasons,
            )
            self._candidates[candidate.pair_key] = candidate
            candidates.append(candidate)
            if self._producer is not None:
                envelope = build_envelope(
                    event_type="resolution.candidate_created",
                    event_version="1.0",
                    producer="admission.resolution",
                    producer_version="0.1.0",
                    payload=json.dumps(candidate.to_dict(), default=str).encode("utf-8"),
                    entity_id=edge.candidate_a,
                    event_id=f"evt-{candidate.pair_key}",
                )
                self._producer.produce(
                    topic_for("resolution.candidate_created"),
                    envelope,
                    key=candidate.pair_key,
                )
        return candidates

    def decide(
        self,
        pair_key: str,
        decision: str,
        *,
        reviewer_id: str | None = None,
        reviewed_at=None,
    ) -> Candidate:
        """Human review of a pair (ACCEPT/REJECT/UNCERTAIN) as a non-destructive decision.

        Appends a ``ResolutionRecord`` via ``apply_review`` and emits
        ``resolution.candidate_decided`` (and ``resolution.merge_recorded`` on
        accept) so projections replay merges from durable events.
        """
        candidate = self._candidates.get(pair_key)
        if candidate is None:
            raise KeyError(f"no candidate for pair {pair_key!r}")
        apply_review(candidate, decision, reviewer_id=reviewer_id, reviewed_at=reviewed_at)
        if self._producer is not None:
            record = candidate.latest_record
            envelope = build_envelope(
                event_type="resolution.candidate_decided",
                event_version="1.0",
                producer="admission.resolution",
                producer_version="0.1.0",
                payload=json.dumps(record.to_dict(), default=str).encode("utf-8"),
                entity_id=candidate.candidate_a,
                event_id=f"evt-{record.resolution_id}",
            )
            self._producer.produce(
                topic_for("resolution.candidate_decided"),
                envelope,
                key=candidate.pair_key,
            )
            if candidate.state == CandidateState.ACCEPTED:
                merge = build_envelope(
                    event_type="resolution.merge_recorded",
                    event_version="1.0",
                    producer="admission.resolution",
                    producer_version="0.1.0",
                    payload=json.dumps(record.to_dict(), default=str).encode("utf-8"),
                    entity_id=candidate.candidate_a,
                    event_id=f"evt-merge-{record.resolution_id}",
                )
                self._producer.produce(
                    topic_for("resolution.merge_recorded"),
                    merge,
                    key=candidate.pair_key,
                )
        return candidate

    def candidates(self) -> list[Candidate]:
        return list(self._candidates.values())

    def candidate_for(self, pair_key: str) -> Candidate | None:
        return self._candidates.get(pair_key)

    def get(self, edge_id: str) -> CorrelationEdge | None:
        return self._edges.get(edge_id)

    def edges_for(self, candidate_id: str) -> list[CorrelationEdge]:
        return [
            e for e in self._edges.values()
            if candidate_id in (e.candidate_a, e.candidate_b)
        ]

    def export_graph(
        self,
        *,
        conflict_days: int | None = None,
        observed_dates: dict | None = None,
        ordering_edges: list | None = None,
    ) -> dict:
        """Export correlation edges as a donor-style `CorrelationGraph` (spec 003).

        Nodes are candidates (never merged, I-2), links are the ``possible_match``
        edges. Returns D3 node-link (for the webapp GraphPanel contract) plus a
        Mermaid rendering for analyst docs.

        When ``conflict_days`` is set, the summary also carries a temporal
        conflict report (spec 004, investigator port): spread contradictions per
        event id under ``observed_dates`` and ordering contradictions under
        ``ordering_edges`` (``event_followed_by``).
        """
        graph = CorrelationGraph()
        for edge in self._edges.values():
            a = make_node(
                CorrelationKind.CANDIDATE,
                edge.candidate_a,
                edge.raw_pair_score,
                observation=edge.edge_id,
            )
            b = make_node(
                CorrelationKind.CANDIDATE,
                edge.candidate_b,
                edge.collective_score,
                observation=edge.edge_id,
            )
            canonical_a = graph.add_node(a)
            canonical_b = graph.add_node(b)
            graph.add_link(
                CorrelationLink(
                    source=canonical_a,
                    target=canonical_b,
                    kind=edge.kind,
                    observation=edge.edge_id,
                    confidence=edge.collective_score,
                )
            )
        summary = graph.summary()
        payload: dict = {
            "node_link": graph.to_dict(),
            "mermaid": graph.to_mermaid(),
            "summary": summary,
        }
        if conflict_days is not None:
            payload["conflicts"] = temporal_conflicts_scan(
                observed_dates or {},
                ordering_edges or [],
                tol_days=conflict_days,
            )
        return payload


@dataclass
class CollectiveResult:
    pairs: list[ResolvedPair] = field(default_factory=list)
    iterations: int = 0

    @property
    def cluster_count(self) -> int:
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            parent.setdefault(x, x)
            root = x
            while parent[root] != root:
                root = parent[root]
            while parent[x] != root:
                parent[x], x = root, parent[x]
            return root

        for p in self.pairs:
            if p.collective_score >= 0.6:
                fa, fb = find(p.candidate_a), find(p.candidate_b)
                if fa != fb:
                    parent[fb] = fa
        return len({find(k) for k in parent})


class CollectiveResolver:
    """Relational propagation over the pair graph until convergence."""

    def __init__(self, iterations: int = 8, relax: float = 0.35) -> None:
        self._max_iterations = iterations
        self._relax = relax

    def resolve(self, pairs: list[ResolvedPair]) -> CollectiveResult:
        running = [ResolvedPair(
            candidate_a=p.candidate_a,
            candidate_b=p.candidate_b,
            raw_pair_score=p.raw_pair_score,
            reasons=list(p.reasons),
            strategies=set(p.strategies),
            collective_score=p.raw_pair_score,
        ) for p in pairs]

        for it in range(self._max_iterations):
            by_node: dict[str, list[int]] = {}
            for idx, p in enumerate(running):
                by_node.setdefault(p.candidate_a, []).append(idx)
                by_node.setdefault(p.candidate_b, []).append(idx)

            changed = False
            new_scores = [p.collective_score for p in running]
            for idx, p in enumerate(running):
                support = p.raw_pair_score
                for node in (p.candidate_a, p.candidate_b):
                    for j in by_node.get(node, []):
                        if j == idx:
                            continue
                        support += 0.15 * running[j].collective_score
                boosted = min(1.0, p.raw_pair_score + self._relax * max(0.0, support - p.raw_pair_score))
                boosted = round(boosted, 3)
                if abs(boosted - new_scores[idx]) > 1e-4:
                    changed = True
                    new_scores[idx] = boosted
            for idx, s in enumerate(new_scores):
                running[idx].collective_score = s
            if not changed:
                return CollectiveResult(pairs=running, iterations=it + 1)
        return CollectiveResult(pairs=running, iterations=self._max_iterations)