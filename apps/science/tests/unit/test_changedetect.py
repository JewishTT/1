"""Unit tests: change-point detector on injected regime shift (T114, US4).

A step change hidden in noise must be recovered with a confidence score, the
pre/post segment summaries, and an explicit detector/rationale record — so the
detector never emits a discontinuity the analyst cannot explain.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np

from temporal.changedetect import ChangeDetectParams, detect_change_points
from temporal.timeseries import ObservationSample, build_series


def _series(values: list[float], start: datetime | None = None) -> object:
    start = start or datetime(2026, 2, 1, tzinfo=UTC)
    samples = [
        ObservationSample(time=start + timedelta(minutes=i), value=v)
        for i, v in enumerate(values)
    ]
    return build_series("level", samples)


class TestChangeDetector:
    def test_step_change_identified_with_segments(self) -> None:
        rng = np.random.default_rng(13)
        noise = rng.normal(0.0, 0.2, 60)
        low = [1.0 + n for n in noise[:30]]
        high = [6.0 + n for n in noise[30:]]
        series = _series(low + high)
        points = detect_change_points(series, ChangeDetectParams(window=6, min_shift=1.5))
        assert len(points) >= 1
        cp = points[0]
        assert 24 <= cp.index <= 35
        assert cp.post_segment["mean"] - cp.pre_segment["mean"] > 3.0
        assert "mean-shift" in cp.rationale["detector"]

    def test_confidence_scales_with_shift(self) -> None:
        series = _series([1.0] * 20 + [2.0] * 20)
        detect_change_points(series, ChangeDetectParams(window=4, min_shift=0.2))
        ratio = detect_change_points(series, ChangeDetectParams(window=4, min_shift=0.2))[0].confidence
        big = detect_change_points(
            _series([1.0] * 20 + [10.0] * 20), ChangeDetectParams(window=4, min_shift=0.2)
        )[0].confidence
        assert big > ratio

    def test_segments_bound_the_transition(self) -> None:
        series = _series([0.0] * 25 + [10.0] * 25)
        (cp,) = detect_change_points(series, ChangeDetectParams(window=8, min_shift=3.0))
        assert 20 <= cp.index <= 28
        assert cp.pre_segment["mean"] < 2.0
        assert cp.post_segment["mean"] > 8.0