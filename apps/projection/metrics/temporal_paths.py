"""Temporal-path metrics: journeys, reachability, motifs (T041/T060).

Concept adapted from Raphtory (GPL-3.0). No Raphtory code is copied — this is
a clean-room, pure-stdlib subset implementing the *concepts* of temporal
graphs (edges carry a timestamp; a journey is a time-respecting path) that
motivated the Raphtory pilot. Also incorporates the temporal-motif idea from
IO-detecting-and-anticipating (MIT, T041).

   Source repo : donors/Raphtory (GPL-3.0) — methods only, no code copied
   License     : GPL-3.0 (concept adaptation; implementation is original)
   What changed: original implementation; earliest-arrival semantics with
                 non-strict time ordering; deterministic motif counting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

INF = float("inf")


@dataclass(frozen=True)
class TimedEdge:
    """A directed temporal edge observed at time ``t``."""
    source: str
    target: str
    t: float
    edge_id: str = ""
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class TemporalGraph:
    """A graph whose edges carry timestamps (deterministic traversal order)."""
    edges: list[TimedEdge] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.edges = sorted(self.edges, key=lambda edge: (edge.t, edge.source, edge.target, edge.edge_id))

    def add_edge(
        self,
        source: str,
        target: str,
        t: float,
        *,
        edge_id: str = "",
        **properties: Any,
    ) -> None:
        self.edges.append(TimedEdge(source=source, target=target, t=t, edge_id=edge_id, properties=properties))
        self.edges = sorted(self.edges, key=lambda edge: (edge.t, edge.source, edge.target, edge.edge_id))

    @property
    def nodes(self) -> list[str]:
        seen: set[str] = set()
        for edge in self.edges:
            seen.add(edge.source)
            seen.add(edge.target)
        return sorted(seen)

    def num_edges(self) -> int:
        return len(self.edges)

    def outgoing_at_or_after(self, node: str, t: float) -> list[TimedEdge]:
        return [edge for edge in self.edges if edge.source == node and edge.t >= t]

    def earliest_arrival(self, source: str) -> dict[str, float]:
        """Earliest arrival time reachable from ``source`` via journeys.

        A journey may traverse consecutive edges whose timestamps satisfy
        ``t_next >= t_prev`` (same tick is allowed — the agent moves within the
        tick). Returns node → earliest arrival time; the source arrives at 0.
        """
        arrival = {source: 0.0}
        for _ in range(len(self.nodes) + 1):
            improved = False
            for edge in self.edges:
                if arrival.get(edge.source, INF) <= edge.t and edge.t < arrival.get(edge.target, INF):
                    arrival[edge.target] = edge.t
                    improved = True
            if not improved:
                break
        return {node: arrival.get(node, INF) for node in self.nodes}

    def reachable_from(self, source: str) -> list[str]:
        arrival = self.earliest_arrival(source)
        return [node for node in sorted(arrival) if node != source and arrival[node] < INF]

    def temporal_distance_matrix(self) -> dict[str, dict[str, float]]:
        return {
            node: self.earliest_arrival(node)
            for node in self.nodes
        }

    def journey(self, source: str, target: str) -> tuple[list[TimedEdge], float]:
        """One earliest-arrival journey (greedy, timestamp-respecting).

        Returns (edges, arrival time); empty list and ``INF`` when the target
        is unreachable.
        """
        arrival = self.earliest_arrival(source)
        if target not in arrival or arrival[target] >= INF:
            return [], INF
        path: list[TimedEdge] = []
        current = target
        time = arrival[target]
        while current != source:
            options = [
                edge
                for edge in self.edges
                if edge.target == current and edge.t >= arrival.get(edge.source, INF)
                and edge.t <= time
            ]
            if not options:
                return [], INF
            edge = max(options, key=lambda e: (e.t, e.edge_id))
            path.append(edge)
            current = edge.source
            time = edge.t
        return list(reversed(path)), arrival[target]

    def count_temporal_motifs(self) -> dict[str, int]:
        """Count 2-edge temporal motifs on 3 nodes (deterministic).

        - ``out_star``: source u emits two edges, u→a then u→b, t1 < t2.
        - ``in_star``:  u receives two edges, a→u then b→u, t1 < t2.
        - ``relay``:    u→a (t1) then a→v (t2), t1 < t2.
        """
        edges = self.edges
        out_star = in_star = relay = 0
        for left in edges:
            for right in edges:
                if right.t <= left.t:
                    continue
                if left.source == right.source and left.source not in {left.target, right.target}:
                    out_star += 1
                if left.target == right.target and left.target not in {left.source, right.source}:
                    in_star += 1
                if left.target == right.source and right.target not in {left.source, left.target}:
                    relay += 1
        return {"out_star": out_star, "in_star": in_star, "relay": relay}

    def timeline(self) -> list[tuple[float, list[str]]]:
        """Batches of observed edge ids per timestamp (ordered, deterministic)."""
        grouped: dict[float, list[str]] = {}
        for edge in self.edges:
            grouped.setdefault(edge.t, []).append(edge.edge_id or f"{edge.source}->{edge.target}@{edge.t}")
        return [(t, grouped[t]) for t in sorted(grouped)]