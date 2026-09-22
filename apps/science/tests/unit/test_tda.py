"""Unit tests: VR persistence barcodes + PHoDMSs spatiotemporal invariants (T054/T056)."""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tda.persistence import (
    ActionPoint,
    AgentFeatures,
    Barcode,
    BarcodeCollection,
    Metric,
    PointCloud,
    persistence_barcodes,
)
from tda.phodms import betti0_erosion_distance, betti_zero_surface, rank_invariant


def _cloud(coords: list[tuple[float, float]], metric: Metric = Metric.EUCLIDEAN) -> PointCloud:
    return PointCloud(
        [ActionPoint(str(i), 0.0, coord) for i, coord in enumerate(coords)],
        metric=metric,
    )


class TestVRPersistence:
    def test_single_point_infinite_h0(self):
        barcodes = persistence_barcodes(_cloud([(0.0, 0.0)]), max_dim=0)
        h0 = barcodes.dimension(0)
        assert h0 is not None
        assert h0.bars == [(0.0, float("inf"))]

    def test_two_points_merge(self):
        barcodes = persistence_barcodes(_cloud([(0.0, 0.0), (2.0, 0.0)]), max_dim=1)
        h0 = barcodes.dimension(0)
        assert h0 is not None
        assert sorted(h0.bars) == [(0.0, 2.0), (0.0, float("inf"))]
        assert h0.betti_at(1.0) == 2
        assert h0.betti_at(2.0) == 1
        assert h0.betti_at(10.0) == 1

    def test_betti_curve(self):
        h0 = Barcode(dimension=0, bars=[(0.0, float("inf")), (0.0, 3.0)])
        assert h0.betti_curve([0.0, 1.0, 3.0, 4.0]) == [2, 2, 1, 1]

    def test_persistence_statistics(self):
        h0 = Barcode(dimension=0, bars=[(0.0, 1.0), (0.0, 3.0), (0.0, float("inf"))])
        assert h0.mean_persistence() == 2.0
        assert h0.max_persistence() == 3.0
        assert h0.total_persistence() == 4.0

    def test_square_h1_until_diagonal(self):
        square = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        barcodes = persistence_barcodes(_cloud(square), max_dim=2)
        h1 = barcodes.dimension(1)
        assert h1 is not None
        assert h1.bars == [(1.0, pytest.approx(math.sqrt(2), abs=1e-9))]

    def test_manhattan_metric(self):
        cloud = _cloud([(0.0, 0.0), (2.0, 1.0)], metric=Metric.MANHATTAN)
        h0 = persistence_barcodes(cloud, max_dim=1).dimension(0)
        assert h0 is not None
        assert h0.bars == [(0.0, 3.0), (0.0, float("inf"))]

    def test_deterministic(self):
        square = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        assert persistence_barcodes(_cloud(square), max_dim=2) == persistence_barcodes(
            _cloud(square), max_dim=2
        )

    def test_budget_guard(self):
        cloud = _cloud([(float(i), 0.0) for i in range(12)])
        with pytest.raises(ValueError):
            persistence_barcodes(cloud, max_dim=2, budget=32)


class TestAgentFeatures:
    def test_steady_single_component(self):
        barcodes = BarcodeCollection(
            [Barcode(dimension=0, bars=[(0.0, float("inf")), (0.0, float("inf"))])]
        )
        features = AgentFeatures.from_barcodes(barcodes)
        assert features.stability == 1.0
        assert features.archetype() == "Steady"

    def test_adaptability_short_lived_loops(self):
        barcodes = BarcodeCollection(
            [Barcode(dimension=1, bars=[(0.1, 0.2), (0.3, 0.4), (0.5, 0.6), (0.7, 0.8), (1.0, 3.0)])]
        )
        features = AgentFeatures.from_barcodes(barcodes)
        assert features.adaptability > 0.0
        assert features.as_dict()["archetype"] in {"Explorer", "Balanced", "Volatile"}

    def test_empty_barcodes_zero_features(self):
        features = AgentFeatures.from_barcodes(BarcodeCollection([]))
        assert features.personality_vector == (0.0, 0.0, 0.0)

    def test_personality_vector_coherent(self):
        features = AgentFeatures(stability=0.6, adaptability=0.4, depth=0.2, personality_vector=(0.6, 0.4, 0.2))
        assert features.personality_vector == (0.6, 0.4, 0.2)
        assert features.archetype() == "Balanced"


class TestPHoDMSs:
    @staticmethod
    def _approaching_clouds():
        # two particles drift together over two timesteps
        return [
            [[0.0, 0.0], [2.0, 0.0]],
            [[0.0, 0.0], [1.0, 0.0]],
        ]

    def test_betti_zero_surface_stays_monotone(self):
        surface = betti_zero_surface(self._approaching_clouds(), [0.5, 1.5, 2.5])
        # half-grid: upper triangle only
        assert surface[0][0][0] == 2  # below cone distance, both components
        assert surface[1][0][0] == 2
        assert surface[2][0][0] == 1  # after merging at cone distance 2
        assert surface[1][0][1] == 1  # cone over both windows has min distance 1
        assert surface[0][1][0] == 0  # lower triangle stays zero

    def test_rank_invariant_valid_window(self):
        clouds = self._approaching_clouds()
        result = rank_invariant(
            clouds, [0.5, 1.5, 2.5], dim=0,
            s1=0, t1=0, t2=0, s2=1, t3=0, t4=1,
        )
        assert result.verdict == "valid"
        assert result.rank == 2

    def test_rank_invariant_margin_verdict(self):
        clouds = self._approaching_clouds()
        result = rank_invariant(
            clouds, [0.5, 1.5, 2.5], dim=0,
            s1=1, t1=0, t2=1, s2=0, t3=1, t4=0,
        )
        assert result.verdict in {"in_margin", "outside_window"}

    def test_rank_outside_window(self):
        clouds = self._approaching_clouds()
        result = rank_invariant(
            clouds, [0.5, 1.5, 2.5], dim=0,
            s1=0, t1=1, t2=0, s2=0, t3=0, t4=1,
        )
        assert result.verdict == "outside_window"
        assert result.rank == -1

    def test_erosion_distance_zero_identical(self):
        surface = [[[2], [2]], [[1], [1]]]
        assert betti0_erosion_distance(surface, surface) == 0

    def test_erosion_distance_positive(self):
        left = [[[2], [2]], [[1], [1]]]
        right = [[[2], [2]], [[2], [2]]]
        assert betti0_erosion_distance(left, right) == 1

    def test_erosion_distance_shape_mismatch(self):
        with pytest.raises(ValueError):
            betti0_erosion_distance([[[1]]], [[[1], [1]]])