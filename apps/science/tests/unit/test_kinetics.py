"""Unit tests: kinetics macro-state graph & dominant pathways (T057)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kinetics.pathways import (
    assign_macrostate,
    build_macro_graph,
    chi_order,
    dominant_pathways,
    find_intervals,
)


class TestFindIntervals:
    def test_single_state_within_tolerance(self):
        intervals = find_intervals([0.0, 0.4, 0.9], 1.0)
        assert len(intervals) == 1
        assert intervals[0].lower == 0.0
        assert intervals[0].upper == 0.9

    def test_gap_splits_interval(self):
        intervals = find_intervals([0.0, 0.2, 1.5, 1.7], 0.5)
        assert len(intervals) == 2
        assert intervals[0].index == 0
        assert intervals[1].index == 1

    def test_assign_macrostate_roundtrip(self):
        intervals = find_intervals([0.0, 2.0], 0.5)
        assert assign_macrostate(0.0, intervals) == 0
        assert assign_macrostate(2.0, intervals) == 1


class TestBuildMacroGraph:
    def test_monotonic_ramp(self):
        graph = build_macro_graph([0, 1, 2, 3, 4, 5], tolerance=0.5)
        assert graph.num_states() == 6
        assert all(graph.occupation[s] == 1 for s in range(6))
        assert graph.total_flux() == 5
        assert graph.transition_density() == pytest.approx(5 / 30)

    def test_single_interval_no_transitions(self):
        graph = build_macro_graph([0, 0.1, 0.2, 0.1], tolerance=0.5)
        assert graph.num_states() == 1
        assert graph.transitions == {}

    def test_deterministic(self):
        series = [0.0, 1.2, 2.3, 0.8, 1.1, 3.3, 0.2]
        assert build_macro_graph(series, 0.5).as_dict() == build_macro_graph(series, 0.5).as_dict()


class TestDominantPathways:
    def test_known_chain_produces_paths(self):
        graph = build_macro_graph([0, 0, 1, 2, 0, 1, 3], tolerance=0.5)
        paths = dominant_pathways(graph, max_edges=3, top_k=2)
        assert paths
        assert paths[0].flux >= 1.0
        assert len(paths[0].states) <= 4

    def test_ranked_by_flux_desc(self):
        graph = build_macro_graph([0, 0, 0, 1, 2, 0, 1, 3, 4, 0, 1, 2, 3], tolerance=0.5)
        paths = dominant_pathways(graph, max_edges=4, top_k=4)
        fluxes = [path.flux for path in paths]
        assert fluxes == sorted(fluxes, reverse=True)


class TestChiOrder:
    def test_all_ordered_state(self):
        assert chi_order([1, 1, 1, 1], {0}, tolerance=0.5) == pytest.approx(1.0)

    def test_half_ordered(self):
        series = [0, 0, 0, 0, 5, 5, 5, 5]
        assert chi_order(series, {0}, tolerance=0.5) == pytest.approx(0.5)