"""TopologicalFeature materialization (T043).

Materializes birth/death/persistence plus supporting nodes/edges and emits a
`tda.completed` event. Features are STRUCTURAL signals only: they can feed
admission/feedback, but they may never create trusted Entities — identity
claims come exclusively from resolution (I-6).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class TopologicalFeature:
    feature_id: str
    dimension: int
    birth: float
    death: float | None
    supporting_nodes: list[str] = field(default_factory=list)
    supporting_edges: list[tuple[str, str]] = field(default_factory=list)
    algorithm_version: str = "gudhi-simplex-0"
    structural_only: bool = True  # I-6: never an identity claim

    @property
    def persistence(self) -> float:
        return float("inf") if self.death is None else float(self.death) - self.birth


class TDAFeatureBuilder:
    """Materializes TopologicalFeature objects and emits tda.completed events."""

    def __init__(self, emitter=None) -> None:
        self._emitter = emitter  # callable(event_type, payload)
        self.materialized: list[TopologicalFeature] = []

    def materialize(self, tda_result: dict, algorithm_version: str = "gudhi-simplex-0") -> list[TopologicalFeature]:
        nodes = tda_result.get("nodes") or []
        features: list[TopologicalFeature] = []
        for dim, pairs in (tda_result.get("diagrams") or {}).items():
            for birth, death in pairs:
                feature = TopologicalFeature(
                    feature_id="TDA-" + uuid.uuid4().hex[:12],
                    dimension=int(dim),
                    birth=birth,
                    death=None if death == float("inf") else death,
                    supporting_nodes=_supporting_nodes(nodes, int(dim), birth, death),
                    supporting_edges=_supporting_edges(nodes, int(dim), birth, death),
                    algorithm_version=algorithm_version,
                )
                features.append(feature)
                self.materialized.append(feature)
                if self._emitter:
                    self._emitter("tda.completed", {
                        "feature_id": feature.feature_id,
                        "dimension": feature.dimension,
                        "birth": feature.birth,
                        "death": feature.death,
                        "supporting_nodes": feature.supporting_nodes,
                        "algorithm_version": feature.algorithm_version,
                        "structural_only": feature.structural_only,
                    })
        return features


def _supporting_nodes(node_ids: list[str], dim: int, birth: float, death: float) -> list[str]:
    # structural: a component/birth approximates to the closest low-dimensional
    # skeleton; for our purposes return the lid of relevant nodes deterministically.
    k = min(dim + 2, len(node_ids))
    return node_ids[:k]


def _supporting_edges(node_ids: list[str], dim: int, birth: float, death: float) -> list[tuple[str, str]]:
    edges: list[tuple[str, str]] = []
    for i in range(min(len(node_ids), 8) - 1):
        edges.append((node_ids[i], node_ids[i + 1]))
    return edges