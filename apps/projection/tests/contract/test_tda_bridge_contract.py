"""Contract: the graph→TDA bridge works, and the filtration means something (spec 025).

Four defects made this stage inert, and none of them was visible in CI:

1. ``graph.adjacency.to_distance_matrix`` looked index triples up in a node-id map, so it
   raised ``KeyError: 0`` on the first edge. Zero callers, zero tests.
2. ``tda.TopologicalInvariant.run`` accepted a co-mention ``fan`` and never mentioned it
   again, so an N-ary neighbourhood contributed nothing to the signature.
3. ``tda.DirectionalFlagProvider`` used ``float(b)`` -- a vertex's *index* -- as the
   filtration, while its docstring promised a temporal delay. The unit test copied the
   same expression, so it could not fail.
4. ``gudhi``'s default ``persistence_dim_max=False`` erases H0 whenever H0 is the maximal
   dimension, which is exactly the case of an edgeless filtration: the subject an
   investigation has found nothing about yet.

What is pinned here is the behaviour those bugs prevented: a real conversion, a filtration
whose value is the thing it claims to be, isolated vertices surviving, and determinism.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from graph.adjacency import AdjacencyEdge, AdjacencyView, to_distance_matrix
from tda import TopologicalInvariant
from tda.bridge import (
    FiltrationError,
    FiltrationInput,
    ScaleKind,
    filtration_from_adjacency,
    filtration_from_edge_list,
    has_gudhi,
    persistence_of,
)
from tda.pipeline import DirectionalFlagProvider

pytestmark = pytest.mark.contract

INF = float("inf")
needs_gudhi = pytest.mark.skipif(not has_gudhi(), reason="gudhi not installed")


def _sine(n: int = 120) -> list[float]:
    return [math.sin(2 * math.pi * i / 20) for i in range(n)]


class TestDistanceMatrixIsUsable:
    """Defect 1: the only graph→distance bridge raised KeyError on every input."""

    def _view(self) -> AdjacencyView:
        return AdjacencyView(
            nodes=["a", "b", "c"],
            edges=[
                AdjacencyEdge("a", "b", "e", {"weight": 0.3}),
                AdjacencyEdge("b", "c", "e", {"weight": 0.5}),
            ],
            provenance={"method": "test"},
        )

    def test_it_computes_at_all(self) -> None:
        nodes, matrix = to_distance_matrix(self._view())
        assert nodes == ["a", "b", "c"]
        assert all(len(row) == 3 for row in matrix)

    def test_it_finds_the_two_hop_path(self) -> None:
        _nodes, matrix = to_distance_matrix(self._view())
        assert matrix[0][2] == pytest.approx(0.8)

    def test_the_matrix_is_symmetric(self) -> None:
        _nodes, matrix = to_distance_matrix(self._view())
        assert all(matrix[i][j] == matrix[j][i] for i in range(3) for j in range(3))

    def test_the_diagonal_is_zero(self) -> None:
        _nodes, matrix = to_distance_matrix(self._view())
        assert all(matrix[i][i] == 0.0 for i in range(3))

    def test_disconnected_nodes_stay_infinite(self) -> None:
        view = AdjacencyView(
            nodes=["a", "b", "lonely"],
            edges=[AdjacencyEdge("a", "b", "e", {"weight": 0.3})],
            provenance={},
        )
        _nodes, matrix = to_distance_matrix(view)
        assert any(
            math.isinf(matrix[i][j])
            for i in range(3)
            for j in range(3)
            if i != j
        )


class TestIsolatedNodesSurvive:
    """Defect: nodes were collected from edge endpoints, so a lone vertex vanished.

    The lone vertex is the one an investigation most needs shown, and it was the one the
    old ``to_tda_input`` dropped.
    """

    def test_a_declared_node_with_no_edges_is_kept(self) -> None:
        view = AdjacencyView(nodes=["x", "y"], edges=[], provenance={})
        nodes, _triples = view.to_tda_input()
        assert nodes == ["x", "y"]

    def test_an_edge_endpoint_outside_the_node_list_is_still_present(self) -> None:
        view = AdjacencyView(
            nodes=["a"],
            edges=[AdjacencyEdge("a", "b", "e", {})],
            provenance={},
        )
        nodes, _triples = view.to_tda_input()
        assert nodes == ["a", "b"]

    @needs_gudhi
    def test_an_isolated_node_has_a_persistent_h0_class(self) -> None:
        # Defect 4: gudhi's default skips the maximal dimension, and for an edgeless
        # filtration H0 *is* it, so the class disappeared.
        diagram = persistence_of(filtration_from_edge_list([], nodes=["solo"]))
        assert 0 in diagram
        assert any(death == INF for _birth, death in diagram[0])

    @needs_gudhi
    def test_each_isolated_node_is_its_own_class(self) -> None:
        diagram = persistence_of(filtration_from_edge_list([], nodes=["a", "b", "c"]))
        assert len(diagram[0]) == 3

    @needs_gudhi
    def test_an_edge_merges_two_classes_and_leaves_one(self) -> None:
        diagram = persistence_of(
            filtration_from_edge_list([("a", "b", 0.5)], nodes=["a", "b"])
        )
        deaths = sorted(d for _b, d in diagram[0])
        assert deaths == [0.5, INF]


class TestFiltrationIsReal:
    """Defect 3: the filtration was a vertex index, so it measured alphabet order."""

    def _fan(self) -> dict[str, list[str]]:
        return {"early": ["a", "b", "c"], "late": ["a", "b", "c", "d"]}

    @needs_gudhi
    def test_time_changes_the_diagram(self) -> None:
        provider = DirectionalFlagProvider()
        flat = provider.compute(self._fan(), 2)
        timed = provider.compute(self._fan(), 2, times={"late": 100.0})
        assert flat != timed, "время не влияет на фильтрацию"

    @needs_gudhi
    def test_swapping_the_times_changes_the_diagram(self) -> None:
        provider = DirectionalFlagProvider()
        forward = provider.compute(self._fan(), 2, times={"early": 100.0, "late": 900.0})
        backward = provider.compute(self._fan(), 2, times={"early": 900.0, "late": 100.0})
        assert forward != backward

    @needs_gudhi
    def test_it_is_deterministic_for_a_fixed_fan_and_clock(self) -> None:
        provider = DirectionalFlagProvider()
        times = {"early": 1.0, "late": 2.0}
        assert provider.compute(self._fan(), 2, times=times) == provider.compute(
            self._fan(), 2, times=times
        )

    def test_without_times_the_filtration_says_nothing(self) -> None:
        # The platform cannot invent when two entities met, so no times means one scale.
        provider = DirectionalFlagProvider()
        assert provider.compute(self._fan(), 2) == provider.compute(self._fan(), 2)


class TestFanReachesTheSignature:
    """Defect 2: ``run`` took a ``fan`` and dropped it on the floor."""

    @pytest.fixture(scope="class")
    def invariant(self) -> TopologicalInvariant:
        return TopologicalInvariant(dimension=2, lag=2, embed_dim=2)

    def test_no_fan_and_a_fan_differ(self, invariant: TopologicalInvariant) -> None:
        without = invariant.run("E1", _sine(), None)
        with_fan = invariant.run("E1", _sine(), {"o1": ["x", "y", "z"]})
        assert without["digest"] != with_fan["digest"]

    def test_the_series_diagram_is_unaffected_by_the_fan(
        self, invariant: TopologicalInvariant
    ) -> None:
        # Two different spaces measured separately; pooling them would be meaningless.
        without = invariant.run("E1", _sine(), None)
        with_fan = invariant.run("E1", _sine(), {"o1": ["x", "y", "z"]})
        assert without["diagram_hash"] == with_fan["diagram_hash"]

    def test_a_clique_and_a_path_are_distinguishable(
        self, invariant: TopologicalInvariant
    ) -> None:
        # Persistent homology cannot tell them apart -- both are connected, both give one
        # H0 class -- which is correct TDA and a real loss. The structure hash covers it.
        clique = invariant.run("E1", _sine(), {"o1": ["x", "y", "z"]})
        path = invariant.run("E1", _sine(), {"o1": ["x", "y"], "o2": ["y", "z"]})
        assert clique["fan_classes"] == path["fan_classes"]
        assert clique["digest"] != path["digest"]
        assert clique["fan_digest"] != path["fan_digest"]

    def test_recording_order_does_not_change_the_digest(
        self, invariant: TopologicalInvariant
    ) -> None:
        ordered = invariant.run("E1", _sine(), {"o1": ["x", "y"], "o2": ["z", "y"]})
        shuffled = invariant.run("E1", _sine(), {"o2": ["y", "z"], "o1": ["y", "x"]})
        assert ordered["digest"] == shuffled["digest"]

    def test_an_empty_fan_is_not_a_populated_one(
        self, invariant: TopologicalInvariant
    ) -> None:
        # "Nothing recorded" and "recorded, found no loops" must not read the same.
        empty = invariant.run("E1", _sine(), {})
        populated = invariant.run("E1", _sine(), {"o1": ["x", "y"]})
        assert empty["fan_digest"] == ""
        assert populated["fan_digest"] != ""
        assert empty["fan_note"]

    def test_the_signature_stays_structural_only(
        self, invariant: TopologicalInvariant
    ) -> None:
        # I-6: topology is never an identity claim.
        assert invariant.run("E1", _sine(), {"o1": ["x"]})["structural_only"] is True


class TestFiltrationInputIsHonest:
    def test_a_mixed_scale_is_refused(self) -> None:
        with pytest.raises(FiltrationError):
            FiltrationInput(("a",), ((0.0,),), scale=ScaleKind.MIXED)

    def test_a_non_square_matrix_is_refused(self) -> None:
        with pytest.raises(FiltrationError):
            FiltrationInput(("a", "b"), ((0.0, 1.0),), scale=ScaleKind.DISTANCE)

    def test_an_edge_naming_an_unknown_node_is_refused(self) -> None:
        # Silently adding the node would hide that the caller's node list was incomplete,
        # which is exactly the kind of quiet widening this platform forbids.
        with pytest.raises(FiltrationError):
            filtration_from_edge_list([("a", "ghost", 1.0)], nodes=["a"])

    def test_the_digest_is_content_addressed(self) -> None:
        left = filtration_from_edge_list([("a", "b", 0.5), ("b", "c", 0.25)])
        right = filtration_from_edge_list([("b", "c", 0.25), ("a", "b", 0.5)])
        assert left.digest == right.digest

    def test_the_digest_changes_with_the_weights(self) -> None:
        left = filtration_from_edge_list([("a", "b", 0.5)])
        right = filtration_from_edge_list([("a", "b", 0.25)])
        assert left.digest != right.digest

    def test_a_zero_weight_does_not_coincide_the_endpoints(self) -> None:
        # Two vertices at distance 0 would be one point for Vietoris-Rips purposes, erasing
        # the edge's contribution to H0.
        filtration = filtration_from_edge_list([("a", "b", 0.0)])
        assert filtration.matrix[0][1] > 0.0

    def test_an_empty_filtration_computes_nothing(self) -> None:
        assert persistence_of(filtration_from_edge_list([])) == {}

    def test_it_matches_the_adjacency_view_conversion(self) -> None:
        view = AdjacencyView(
            nodes=["a", "b", "c"],
            edges=[AdjacencyEdge("a", "b", "e", {"weight": 0.5})],
            provenance={},
        )
        from_view = filtration_from_adjacency(view)
        assert from_view.node_ids == ("a", "b", "c")
        assert from_view.matrix[0][1] == pytest.approx(0.5)
        # ``c`` has no edge at all, so a->c is unreachable rather than clamped to 1.0.
        assert math.isinf(from_view.matrix[0][2])

    def test_the_matrix_round_trips_through_numpy(self) -> None:
        filtration = filtration_from_edge_list([("a", "b", 0.5)])
        assert filtration.to_numpy().shape == (2, 2)


@needs_gudhi
def test_a_real_hole_still_surfaces_after_the_bridge_work() -> None:
    # Guards against the fixes changing well-formed behaviour: a 3x3 grid has genuine
    # Vietoris-Rips holes and must keep producing them.
    pts = [(float(x), float(y)) for x in range(3) for y in range(3)]
    edges = [
        (f"p{i}", f"p{j}", float(np.hypot(a[0] - b[0], a[1] - b[1])))
        for i, a in enumerate(pts)
        for j, b in enumerate(pts)
        if i < j
    ]
    diagram = persistence_of(
        filtration_from_edge_list(edges), dimension=2
    )
    assert 1 in diagram
    assert all(death > birth for birth, death in diagram[1])