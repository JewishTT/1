"""Size-aware bounded structural primitives + analyze dispatch (T121, US5).

Complexity is bounded *before* any heavy loop (``estimate_complexity`` uses the
standard O(Σ_{edges} d_u·d_v) triangle bound); a graph whose estimate exceeds
the budget is DEFERRED with a sampling plan — the kernel never runs an
unbounded computation and never emits a truncated guess (SC-006). The scope
guard (T086) runs first at this single entry point (T111).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256

from causal.scope import ensure_scoped
from structure.model import (
    NullModelResult,
    StructureAnalysisResult,
    StructureKind,
    StructureStatus,
)
from structure.motif import degree_preserving_null
from structure.spectral import spectral_radius_norm


@dataclass
class Graph:
    """Undirected graph assembled inline for structural analysis."""

    graph_ref: str
    _edges: list[tuple[str, str]] = field(default_factory=list, repr=False)

    def add_edge(self, a: str, b: str) -> None:
        if a == b:
            raise ValueError("self-loops are not part of the structural kernel")
        self._edges.append((a, b))

    def edges(self) -> list[tuple[str, str]]:
        return list(self._edges)

    def adjacency(self) -> dict[str, set[str]]:
        adj: dict[str, set[str]] = {}
        for a, b in self._edges:
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)
        return adj

    def n_nodes(self) -> int:
        return len(self.adjacency())

    def n_edges(self) -> int:
        return len(self._edges)

    def density(self) -> float:
        n = self.n_nodes()
        if n < 2:
            return 0.0
        return min(1.0, 2 * self.n_edges() / (n * (n - 1)))

    def triangle_count(self) -> int:
        """Count triangles via sorted-neighbor intersection.

        The caller must have verified complexity (``estimate_complexity``);
        this method itself performs the O(Σ d²) walk. Each triangle is summed
        once per adjacent pair in it, so the raw sum is divided by three.
        """
        adj = self.adjacency()
        sorted_adj = {node: sorted(nbrs) for node, nbrs in adj.items()}
        pairs = 0
        for u, nbrs in sorted_adj.items():
            for v in nbrs:
                if u < v:
                    pairs += len(set(nbrs).intersection(sorted_adj[v]))
        return pairs // 3


@dataclass(frozen=True)
class AnalysisBudget:
    max_ops: int = 200_000
    max_permutations: int = 200


@dataclass(frozen=True)
class NullParams:
    shuffle_kind: str = "degree_preserving_stub_swap"
    n_permutations: int = 200
    seed: int = 42


def estimate_complexity(graph: Graph) -> int:
    """Upper bound of the heavy KERNEL walk (triangle counting)."""
    adj = graph.adjacency()
    return sum(len(adj[u]) * len(adj[v]) for u, v in graph.edges())


def _deferred(
    *,
    graph: Graph,
    kind: StructureKind,
    rationale: str,
) -> StructureAnalysisResult:
    digest = sha256(f"struct:{graph.graph_ref}:{kind.value}".encode()).hexdigest()[:12]
    return StructureAnalysisResult(
        result_id=f"ST-{digest}",
        graph_ref=graph.graph_ref,
        kind=kind,
        algorithm=f"{kind.value}:deferred@0.1",
        status=StructureStatus.DEFERRED,
        scores={},
        significance=None,
        budget_rationale=rationale,
    )


def analyze(
    graph: Graph,
    *,
    budget: AnalysisBudget,
    kind: StructureKind,
    null_params: NullParams,
) -> StructureAnalysisResult:
    """Guard scope, bound complexity, then run the requested structural kernel.

    Returns DEFERRED (never a truncated estimate) when the kind is not in the
    kernel or when the graph exceeds the complexity budget.
    """
    ensure_scoped(graph.graph_ref, entry_point="structure.analyze")

    if kind not in (StructureKind.SPECTRAL, StructureKind.MOTIF):
        return _deferred(
            graph=graph,
            kind=kind,
            rationale=(
                f"deferred with sampling plan: kernel covers SPECTRAL and MOTIF; "
                f"{kind.value} requires a higher-order kernel not in the KVK build, "
                "no estimate emitted (SC-006)"
            ),
        )

    estimated = estimate_complexity(graph)
    if estimated > budget.max_ops:
        return _deferred(
            graph=graph,
            kind=kind,
            rationale=(
                f"deferred with sampling plan: estimated ops {estimated} exceed "
                f"budget {budget.max_ops}; random-edge subsample capped at "
                "budget and flagged in output — no truncated estimate (SC-006)"
            ),
        )

    n_permutations = min(null_params.n_permutations, budget.max_permutations)
    if kind is StructureKind.MOTIF:
        statistic_fn = Graph.triangle_count
        observed = float(graph.triangle_count())
        algorithm = "motif:triangle-count@1.0"
    else:
        statistic_fn = spectral_radius_norm
        observed = float(spectral_radius_norm(graph))
        algorithm = "spectral:radius-norm@1.0"

    null = degree_preserving_null(
        graph,
        statistic_fn=statistic_fn,
        n_permutations=n_permutations,
        seed=null_params.seed,
    )
    null_result = NullModelResult.build(
        data={"graph_ref": graph.graph_ref, "shuffle_kind": null_params.shuffle_kind},
        observed=observed,
        null=null.null_distribution,
    )

    if kind is StructureKind.MOTIF:
        scores = {
            "triangle_count": float(graph.triangle_count()),
            "density": round(graph.density(), 6),
        }
    else:
        scores = {
            "spectral_radius_norm": round(spectral_radius_norm(graph), 6),
            "density": round(graph.density(), 6),
        }

    digest = sha256(f"struct:{graph.graph_ref}:{kind.value}:{scores}".encode()).hexdigest()[:12]
    return StructureAnalysisResult(
        result_id=f"ST-{digest}",
        graph_ref=graph.graph_ref,
        kind=kind,
        algorithm=algorithm,
        scores=scores,
        significance=null_result,
        status=StructureStatus.OK,
    )