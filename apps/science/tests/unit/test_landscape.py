"""Unit tests: belief-landscape flow fields, attractors, forecast (T053)."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from beliefs.landscape import FlowField, analyze_landscape, forecast, gradient_field, streamline


def _well_grid(size: int = 7) -> np.ndarray:
    center = (size - 1) / 2.0
    y, x = np.mgrid[0:size, 0:size]
    return ((x - center) ** 2 + (y - center) ** 2).astype(float)


class TestFlowField:
    def test_gradient_points_toward_center(self):
        gradient = gradient_field(_well_grid())
        assert gradient[0, 0, 0] < 0  # x derivative at left edge
        assert gradient[0, 0, 1] < 0  # y derivative at top edge

    def test_flat_field_no_flow(self):
        flow = FlowField.from_values(np.zeros((4, 4)))
        assert np.all(flow.flow == 0.0)
        assert np.all(flow.speed == 0.0)

    def test_streamline_converges_to_minimum(self):
        flow = FlowField.from_values(_well_grid())
        path = streamline(flow, (0.0, 0.0), max_steps=600, step_size=0.05)
        end = path[-1]
        distance = (end[0] - 3.0) ** 2 + (end[1] - 3.0) ** 2
        assert distance < 1.0


class TestAttractorsAndForecast:
    def test_attractor_near_center(self):
        landscape = analyze_landscape(_well_grid())
        assert landscape.attractors
        center = 3.0

        def distance(attractor):
            return (attractor.center[0] - center) ** 2 + (attractor.center[1] - center) ** 2

        closest = min(landscape.attractors, key=distance)
        assert distance(closest) < 1.0

    def test_as_dict_contract(self):
        report = analyze_landscape(_well_grid()).as_dict()
        assert "grid" in report
        assert "attractors" in report
        assert report["grid"] == [7, 7]

    def test_forecast_moves_toward_center(self):
        values = _well_grid(size=9)
        landscape = analyze_landscape(values)
        path = forecast(landscape, (1.0, 1.0), steps=60)
        start_distance = (1.0 - 4.0) ** 2 + (1.0 - 4.0) ** 2
        end_distance = (path.destination[0] - 4.0) ** 2 + (path.destination[1] - 4.0) ** 2
        assert end_distance < start_distance

    def test_invalid_grid_shape_raises(self):
        with pytest.raises(ValueError):
            gradient_field(np.zeros(5))