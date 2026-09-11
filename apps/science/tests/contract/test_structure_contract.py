"""Contract tests: structure analyze + DEFERRED (T119, US5).

Tests-first for ``apps/science/structure/*`` per interface-contracts §7: scores
are normalized to a documented range, motif counts carry permutation-null
significance (or explicit DEFERRED), complexity-budget-exceeding graphs are
deferred with a sampling plan — never a truncated guess (SC-006) — and the
scope guard runs first (T111).
"""

from __future__ import annotations

import pytest

from errors import ScopeBoundaryError
from structure.graph import AnalysisBudget, Graph, NullParams, StructureKind, analyze


def _ring(size: int) -> Graph:
    g = Graph(graph_ref=f"graph:ring-{size}")
    for i in range(size):
        g.add_edge(f"n{i}", f"n{(i + 1) % size}")
    return g


class TestAnalyze:
    def test_spectral_scores_normalized(self) -> None:
        result = analyze(
            _ring(8),
            budget=AnalysisBudget(),
            kind=StructureKind.SPECTRAL,
            null_params=NullParams(seed=1, n_permutations=100),
        )
        assert result.status.value == "ok"
        assert result.kind.value == "spectral"
        assert result.algorithm.startswith("spectral")
        for value in result.scores.values():
            assert 0.0 <= value <= 1.0, result.scores
        assert result.significance is not None

    def test_motif_counts_carry_permutation_null(self) -> None:
        result = analyze(
            _ring(8),
            budget=AnalysisBudget(),
            kind=StructureKind.MOTIF,
            null_params=NullParams(seed=3, n_permutations=200),
        )
        assert result.scores["triangle_count"] == 0  # a ring has no triangles
        assert result.significance is not None
        assert result.significance.shuffle_kind == "degree_preserving_stub_swap"
        assert len(result.significance.null_distribution) == 200
        assert result.significance.observed_statistic == 0.0

    def test_over_budget_returns_deferred(self) -> None:
        dense = Graph(graph_ref="graph:dense")
        for i in range(40):
            for j in range(i + 1, 40):
                dense.add_edge(f"n{i}", f"n{j}")
        result = analyze(
            dense,
            budget=AnalysisBudget(max_ops=10_000, max_permutations=50),
            kind=StructureKind.MOTIF,
            null_params=NullParams(seed=1, n_permutations=50),
        )
        assert result.status.value == "deferred"
        assert result.significance is None
        assert "sampling" in (result.budget_rationale or "").lower()

    def test_unknown_kind_deferred_not_truncated(self) -> None:
        result = analyze(
            _ring(6),
            budget=AnalysisBudget(),
            kind=StructureKind.HYPERGRAPH,
            null_params=NullParams(seed=1, n_permutations=100),
        )
        assert result.status.value == "deferred"
        assert result.scores == {}
        assert result.budget_rationale

    def test_output_is_structural_only(self) -> None:
        result = analyze(
            _ring(8),
            budget=AnalysisBudget(),
            kind=StructureKind.SPECTRAL,
            null_params=NullParams(seed=1, n_permutations=100),
        )
        keys = set(result.scores)
        assert keys <= {"spectral_radius_norm", "density"}  # counts/density, no person verdicts

    def test_scope_guard_runs_first(self) -> None:
        with pytest.raises(ScopeBoundaryError):
            analyze(
                Graph(graph_ref="an individual's political network"),
                budget=AnalysisBudget(),
                kind=StructureKind.SPECTRAL,
                null_params=NullParams(seed=1, n_permutations=100),
            )