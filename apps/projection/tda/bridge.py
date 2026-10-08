"""The bridge that was missing: invariant/graph → filtration → persistence (spec 025).

Everything here already existed, and none of it was connected. Two independent
``to_tda_input`` implementations -- ``graph_invariant.py:963`` and
``graph/adjacency.py:42`` -- produced the documented ``(nodes, triples)`` shape, and
nothing converted that shape into anything ``gudhi`` would accept. ``TDAPipeline.run()``
took ``features: dict[str, ndarray]`` instead, which no graph in the platform produces.
So the whole L3 topology stage ran on unit tests and had no production caller.

This module is that converter, and it is deliberately the *only* place that knows how to
get from an entity's accumulated structure to a persistence diagram. Three reasons:

**One conversion, not four.** The shapes involved are the invariant's ego-star, the
invariant's multiplex layers, an ``AdjacencyView`` of a wider neighbourhood, and a plain
edge list. Each needs a different filtration and each has a trap: an aggregate weight is
not a distance, a multiplex layer has no meaningful absolute scale, and an unweighted
matrix is not a filtration (every non-zero is at distance 1, which collapses the complex).
Keeping the four conversions together makes the differences visible instead of spreading
four subtly wrong versions through four call sites.

**Filtration values must be honest about what they measure.** A weight that is a count of
co-mentions is not comparable to a weight that is a year; both end up in the same matrix,
and a persistence diagram computed across mixed units is a diagram of an artefact. Each
conversion therefore names its scale and refuses to pool across kinds.

**Determinism is a property of the input, not of the caller.** Node order is sorted, edge
order is sorted, and the digest is content-addressed, so the same invariant always yields
the same barcode (I-11/I-12) regardless of how it was reached.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "FiltrationError",
    "FiltrationInput",
    "ScaleKind",
    "filtration_from_adjacency",
    "filtration_from_edge_list",
    "filtration_from_invariant",
    "multiplex_filtrations",
    "persistence_of",
]


class FiltrationError(ValueError):
    """The requested conversion cannot be made honestly."""


class ScaleKind(str):
    """What the filtration numbers mean. Named so a diagram cannot lie by omission."""

    DISTANCE = "distance"
    WEIGHT = "weight"
    TIME = "time"
    MIXED = "mixed"


@dataclass(frozen=True, slots=True)
class FiltrationInput:
    """A filtration ready for persistence: node ids, a metric, and what it measures.

    ``scale`` travels with the data because the most common way to produce a wrong
    barcode is to put weights and times in one matrix and report the result as either.
    """

    node_ids: tuple[str, ...]
    matrix: tuple[tuple[float, ...], ...]
    scale: str = ScaleKind.DISTANCE
    provenance: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        size = len(self.node_ids)
        if len(self.matrix) != size:
            raise FiltrationError(
                f"matrix has {len(self.matrix)} rows for {size} nodes"
            )
        for index, row in enumerate(self.matrix):
            if len(row) != size:
                raise FiltrationError(
                    f"row {index} has {len(row)} entries, expected {size}"
                )
        if self.scale == ScaleKind.MIXED:
            raise FiltrationError(
                "a mixed-scale filtration is refused: weights and times in one matrix "
                "produce a barcode of the artefact, not of the structure"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_ids": list(self.node_ids),
            "scale": self.scale,
            "digest": self.digest,
            "nodes": len(self.node_ids),
        }

    @property
    def digest(self) -> str:
        """Content digest, stable across calls (I-11)."""
        material = json.dumps(
            {
                "nodes": list(self.node_ids),
                "scale": self.scale,
                "matrix": [
                    [None if v == float("inf") else round(v, 12) for v in row]
                    for row in self.matrix
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def to_numpy(self) -> Any:
        import numpy as np

        return np.asarray(self.matrix, dtype=float)


def _nodes_and_matrix(
    nodes: Sequence[str],
    edges: Iterable[tuple[str, str, float]],
) -> tuple[tuple[str, ...], tuple[tuple[float, ...], ...]]:
    """Symmetric metric over ``nodes`` with the minimum weight per pair.

    Minimum, not sum: two co-mentions of the same pair are not "more distant", they are
    the same edge seen twice, and summing would make evidence of frequency look like
    evidence of distance.
    """
    size = len(nodes)
    index = {node: position for position, node in enumerate(nodes)}
    inf = float("inf")
    matrix = [[0.0 if i == j else inf for j in range(size)] for i in range(size)]
    for source, target, weight in edges:
        i, j = index[source], index[target]
        if i == j:
            continue
        value = float(weight)
        if value <= 0.0:
            # A non-positive weight is unusable as a distance: it would place two distinct
            # vertices at the same point and delete the edge's contribution to H0. Clamped
            # rather than dropped, so the connectivity survives.
            value = 1.0
        if value < matrix[i][j]:
            matrix[i][j] = value
            matrix[j][i] = value
    for k in range(size):
        for i in range(size):
            through_k = matrix[i][k]
            if through_k == inf:
                continue
            for j in range(size):
                candidate = through_k + matrix[k][j]
                if candidate < matrix[i][j]:
                    matrix[i][j] = candidate
                    matrix[j][i] = candidate
    return tuple(nodes), tuple(tuple(row) for row in matrix)


def filtration_from_edge_list(
    edges: Iterable[tuple[str, str, float]],
    *,
    nodes: Sequence[str] | None = None,
    scale: str = ScaleKind.DISTANCE,
    provenance: Mapping[str, Any] | None = None,
) -> FiltrationInput:
    """A metric over a plain weighted edge list.

    ``nodes`` should be supplied whenever there are isolated vertices. Without it they are
    invisible, and an isolated vertex is exactly what an investigation most needs shown --
    the subject nothing has been found about.
    """
    materialised = [tuple(edge) for edge in edges]
    if nodes is None:
        seen = {endpoint for edge in materialised for endpoint in edge[:2]}
        nodes = sorted(seen)
    ordered = tuple(sorted(set(nodes)))
    known = set(ordered)
    for edge in materialised:
        unknown = {endpoint for endpoint in edge[:2]} - known
        if unknown:
            raise FiltrationError(
                f"edge references {len(unknown)} node(s) absent from the node list: "
                f"{sorted(unknown)[:5]}"
            )
    ids, matrix = _nodes_and_matrix(ordered, materialised)
    return FiltrationInput(ids, matrix, scale=scale, provenance=provenance)


def filtration_from_adjacency(
    view: Any,
    *,
    scale: str = ScaleKind.DISTANCE,
) -> FiltrationInput:
    """A metric over an ``AdjacencyView``.

    Thin on purpose: the view already owns the ``(nodes, triples)`` shape and the index
    convention, so this reuses it rather than re-deriving an index the two could disagree
    about -- which is how the bridge stayed broken the first time.
    """
    nodes, triples = view.to_tda_input()
    edges = [
        (nodes[source], nodes[target], float(weight))
        for source, target, weight in triples
    ]
    return filtration_from_edge_list(
        edges,
        nodes=nodes,
        scale=scale,
        provenance=getattr(view, "provenance", None),
    )


def filtration_from_invariant(
    invariant: Any,
    *,
    scale: str = ScaleKind.DISTANCE,
) -> FiltrationInput:
    """A metric over one entity's invariant (the ego-star, weights summed per window).

    Summed, not averaged, because ``to_tda_input`` already declares that aggregation and
    averaging here would disagree with the docstring while looking equally reasonable.
    """
    from domain.graph_invariant import to_tda_input

    nodes, triples = to_tda_input(invariant)
    edges = [(nodes[i], nodes[j], float(w)) for i, j, w in triples]
    return filtration_from_edge_list(
        edges,
        nodes=nodes,
        scale=scale,
        provenance={"generator": "graph_invariant.to_tda_input"},
    )


def multiplex_filtrations(invariant: Any) -> tuple[FiltrationInput, ...]:
    """One filtration per lifecycle window, aligned 1:1 with the slices.

    Lossless where :func:`filtration_from_invariant` aggregates. Each layer carries its own
    window bounds in provenance so a caller can say *which* period a class belongs to --
    without that, a merged barcode over layers answers "how many loops" and never "when".

    Layers whose window has no neighbours still produce a filtration, carrying that window's
    nodes alone. Dropping them would silently delete the periods where an entity was
    observed and connected to nothing, which is a finding.
    """
    from domain.graph_invariant import to_multiplex

    out: list[FiltrationInput] = []
    for layer in to_multiplex(invariant):
        out.append(
            filtration_from_edge_list(
                [
                    (layer.nodes[i], layer.nodes[j], float(w))
                    for i, j, w in layer.triples
                ],
                nodes=layer.nodes,
                provenance={
                    "generator": "graph_invariant.to_multiplex",
                    "window_start": layer.window_start,
                    "window_end": layer.window_end,
                },
            )
        )
    return tuple(out)


def persistence_of(
    filtration: FiltrationInput,
    *,
    dimension: int = 2,
    provider: Any = None,
) -> dict[int, list[tuple[float, float | None]]]:
    """Persistence diagram for one filtration, or an honest empty result.

    ``gudhi`` absent, or a filtration with no points, yields ``{}`` -- never a fabricated
    diagram (I-3). The caller can distinguish "computed and empty" from "not computed"
    because :func:`has_gudhi` is public.

    One case is handled rather than passed through. ``gudhi``'s default
    ``persistence_dim_max=False`` skips the maximal dimension, and for a filtration with
    no edges at all H0 *is* the maximal dimension -- so a lone vertex came back with an
    empty diagram. That is the one node an investigation most needs shown, and it is
    exactly the node the default erases. Lifting the flag restores the class; the rest of
    the pipeline's own convention (strict ``death > birth``) still discards the
    zero-persistence bars, so nothing else changes.
    """
    if not filtration.node_ids:
        return {}
    if not has_gudhi():
        return {}
    engine = provider
    if engine is None:
        import gudhi

        from tda.pipeline import GudhiProvider

        engine = GudhiProvider()

    size = len(filtration.node_ids)
    has_edges = any(
        filtration.matrix[i][j] != float("inf")
        for i in range(size)
        for j in range(i + 1, size)
    )
    if has_edges:
        return engine.compute(filtration.to_numpy(), dimension)

    # Edge-free: build the 0-complex directly so the isolated vertices survive.
    tree = gudhi.SimplexTree()
    for index in range(size):
        tree.insert([index], filtration=0.0)
    out: dict[int, list[tuple[float, float | None]]] = {}
    for dim, (birth, death) in tree.persistence(persistence_dim_max=True):
        out.setdefault(int(dim), []).append((float(birth), death))
    return out


def has_gudhi() -> bool:
    try:
        import gudhi  # noqa: F401

        return True
    except ImportError:
        return False
