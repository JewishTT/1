"""Topological invariant (L3) — public facade (T4-01).

``TopologicalInvariant.run()`` is the stable CLI/API entry that turns a Series +
hyperedge fan into a topology signature: entity state stream -> point cloud ->
barcode -> quantitative features. Everything is structural-only (I-6: never an
identity claim) and rebuildable (I-12: same input, same hash).
"""

from __future__ import annotations

from .diagram import PersistenceDiagram, simplify
from .features import (
    amplitude,
    betti_curve,
    bottleneck,
    compute_features,
    drift,
    features_digest,
    landscapes,
    persistence_entropy,
    wasserstein,
)
from .pipeline import (
    DelaySeriesComplex,
    DirectionalFlagProvider,
    Filtration,
    GudhiProvider,
    MemoryBudgetExceeded,
    PersistenceProvider,
    TDAPipeline,
)
from .validated import (
    ValidatedHyperedge,
    ValidatedHyperedgeSet,
    hyperedge_survival,
    order_hyperlaplacian_values,
    validate_hyperedges,
)

__all__ = [
    "DelaySeriesComplex",
    "DirectionalFlagProvider",
    "Filtration",
    "GudhiProvider",
    "MemoryBudgetExceeded",
    "PersistenceDiagram",
    "PersistenceProvider",
    "TDAPipeline",
    "TopologicalInvariant",
    "ValidatedHyperedge",
    "ValidatedHyperedgeSet",
    "amplitude",
    "betti_curve",
    "bottleneck",
    "compute_features",
    "drift",
    "features_digest",
    "hyperedge_survival",
    "landscapes",
    "order_hyperlaplacian_values",
    "persistence_entropy",
    "simplify",
    "validate_hyperedges",
    "wasserstein",
]


class TopologicalInvariant:
    """End-to-end L3 topology signature (T4-01).

    ``series`` is the atomic entity's life-stream (L1); ``fan`` the N-ary
    co-mention edges (L2). The invariant is computed deterministically: hash →
    diagram → features, all content-addressed. ``gudhi`` is only needed for the
    persistence stage; feature-level analysis runs without it.
    """

    def __init__(self, *, dimension: int = 2, lag: int = 1, embed_dim: int = 2) -> None:
        self._dimension = dimension
        self._lag = lag
        self._embed_dim = embed_dim

    def run(
        self,
        entity_id: str,
        series: list[float],
        fan: dict[str, list[str]] | None = None,
    ) -> dict:
        """Series -> persistence diagram -> features (never an identity claim).

        Returns a content-addressed payload: ``diagram_hash`` and ``digest``
        identify the analysis output; ``structural_only=True`` everywhere (I-6).
        """
        cplx = DelaySeriesComplex(series=series, lag=self._lag, dim=self._embed_dim)
        dm = cplx.distance_matrix()
        diagrams: dict[int, list[tuple[float, float | None]]] = {}
        if dm.shape[0] > 0 and _has_gudhi():
            # gudhi absent => honest empty topology, never fabricated (I-3).
            diagrams = GudhiProvider().compute(dm, self._dimension)
        diagram = PersistenceDiagram(diagrams)
        features = compute_features(diagram) if diagram else compute_features({})
        return {
            "entity_id": entity_id,
            "diagram_hash": diagram.diagram_hash,
            "digest": features_digest(features),
            "features": features,
            "dimensions": diagram.dims(),
            "classes": len(diagram),
            "structural_only": True,  # I-6
            "generator": "topological_invariant_v1",
        }


def _has_gudhi() -> bool:
    try:
        import gudhi  # noqa: F401

        return True
    except ImportError:
        return False