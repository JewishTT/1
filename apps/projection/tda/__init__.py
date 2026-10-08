"""Topological invariant (L3) — public facade (T4-01).

``TopologicalInvariant.run()`` is the stable CLI/API entry that turns a Series +
hyperedge fan into a topology signature: entity state stream -> point cloud ->
barcode -> quantitative features. Everything is structural-only (I-6: never an
identity claim) and rebuildable (I-12: same input, same hash).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence

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

    **The fan used to be accepted and discarded.** ``run()`` took a ``fan`` argument
    and never mentioned it in the body, so an N-ary co-mention -- the one piece of
    structure the entity's own time-series cannot express -- contributed nothing, and
    the unit test passed a ``fan`` without ever checking that the output moved. Two
    entities with identical histories but completely different co-occurrence
    neighbourhoods produced identical signatures.

    Both now contribute, and each is reported separately because they measure different
    things and cannot be pooled honestly:

    * ``series_diagram`` -- the entity's own trajectory. One space.
    * ``fan_diagram`` -- the topology of the neighbourhood it sits in. Another space.

    The combined ``digest`` covers both, so the signature changes when either does, while
    ``diagram_hash`` stays the hash of the series alone for callers that mean "this
    entity's trajectory".
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
        *,
        times: Mapping[str, float] | None = None,
    ) -> dict:
        """Series + fan -> two diagrams -> features (never an identity claim).

        Returns a content-addressed payload: ``diagram_hash`` and ``digest``
        identify the analysis output; ``structural_only=True`` everywhere (I-6).

        An empty ``fan`` yields an empty ``fan_diagram`` rather than a zero one, and the
        reason is recorded. "This entity had no recorded co-occurrences" and "its
        co-occurrences formed no loops" are different facts, and a zero diagram would
        claim the second.
        """
        cplx = DelaySeriesComplex(series=series, lag=self._lag, dim=self._embed_dim)
        dm = cplx.distance_matrix()
        series_diagrams: dict[int, list[tuple[float, float | None]]] = {}
        if dm.shape[0] > 0 and _has_gudhi():
            # gudhi absent => honest empty topology, never fabricated (I-3).
            series_diagrams = GudhiProvider().compute(dm, self._dimension)
        diagram = PersistenceDiagram(series_diagrams)

        fan_diagram = PersistenceDiagram({})
        fan_note = "no co-occurrence fan supplied"
        members: list[str] = []
        if fan:
            members = sorted({m for group in fan.values() for m in group})
            if _has_gudhi():
                fan_diagram = PersistenceDiagram(
                    DirectionalFlagProvider().compute(fan, self._dimension, times=times)
                )
                fan_note = "" if len(fan_diagram) else "co-occurrences produced no persistent class"
            else:
                fan_note = "gudhi absent: fan topology not computed"

        features = compute_features(diagram) if diagram else compute_features({})
        fan_features = (
            compute_features(fan_diagram) if fan_diagram else compute_features({})
        )
        # Persistent homology cannot see the difference between a 3-clique and a 3-path:
        # both are connected, both give one H0 class born at 0 and never dying. That is
        # correct TDA, and it is also a real loss for this platform -- "these three entities
        # all appear together" and "these three appear pairwise in a chain" are different
        # findings, and a context engine that cannot tell them apart is guessing.
        #
        # So the neighbourhood's own canonical form is hashed alongside its topology. The
        # two are reported separately and neither is presented as the other.
        fan_digest = _fan_digest(fan)
        digest = features_digest(
            {
                "series": features,
                "fan_topology": fan_features if fan else None,
                "fan_structure": fan_digest or None,
            }
        )
        return {
            "entity_id": entity_id,
            "diagram_hash": diagram.diagram_hash,
            "digest": digest,
            "features": features,
            "fan_features": fan_features,
            "fan_diagram_hash": fan_diagram.diagram_hash,
            "fan_digest": fan_digest,
            "fan_members": len(members),
            "fan_note": fan_note,
            "dimensions": diagram.dims(),
            "classes": len(diagram),
            "fan_classes": len(fan_diagram),
            "structural_only": True,  # I-6
            "generator": "topological_invariant_v2",
        }


def _fan_digest(fan: Mapping[str, Sequence[str]] | None) -> str:
    """Content hash of the fan's shape, independent of its persistence.

    Fan keys sorted, members sorted, so two callers who recorded the same co-occurrences
    in a different order get the same digest (I-11). Empty input gives ``""`` rather than
    the hash of nothing, so "no fan" stays distinguishable from "a fan with no members".
    """
    if not fan:
        return ""
    material = ";".join(
        f"{key}={'|'.join(sorted(set(members)))}" for key, members in sorted(fan.items())
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _has_gudhi() -> bool:
    try:
        import gudhi  # noqa: F401

        return True
    except ImportError:
        return False