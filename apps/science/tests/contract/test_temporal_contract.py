"""Contract tests: temporal series + change detection (T113, US4).

Tests-first for ``apps/science/temporal/*`` per interface-contracts §6:
UTC-normalized series preserve original local times; injected discontinuities
are detected with confidence and segment summaries; a reprojection creates a
new version linked via SUPERSEDES while the original stays queryable (I-1,
FR-015, I-12).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from store import ScienceStore
from temporal.changedetect import ChangeDetectParams, detect_change_points
from temporal.scenario import reproject
from temporal.timeseries import ObservationSample, build_series


def _samples(start: datetime, values: list[float], step_seconds: int = 60) -> list[ObservationSample]:
    return [
        ObservationSample(time=start + timedelta(seconds=step_seconds * i), value=v)
        for i, v in enumerate(values)
    ]


class TestBuildSeries:
    def test_utc_normalized_originals_preserved(self) -> None:
        tz = timezone(timedelta(hours=5))
        local = datetime(2026, 3, 1, 12, 0, 0, tzinfo=tz)
        samples = _samples(local, [1.0, 2.0, 3.0])
        series = build_series("credence_growth", samples)
        assert series.series_id.startswith("TS-")
        assert series.timestamps[0] == datetime(2026, 3, 1, 7, 0, 0, tzinfo=UTC)  # 12:00+05 == 07:00Z
        assert series.original_timestamps[0] == local
        assert list(series.values) == [1.0, 2.0, 3.0]


class TestChangeDetection:
    def test_injected_regime_change_detected_with_segments(self) -> None:
        start = datetime(2026, 3, 1, tzinfo=UTC)
        baseline = [1.0] * 20
        regime = [5.0] * 20
        values = baseline + regime
        series = build_series("process_level", _samples(start, values))
        points = detect_change_points(
            series,
            ChangeDetectParams(window=5, min_shift=1.0),
        )
        assert points, "regime change must be detected"
        cp = points[0]
        assert 17 <= cp.index <= 22  # near the injected jump at index 20
        assert cp.confidence > 0.0
        assert cp.pre_segment["mean"] < 2.0
        assert cp.post_segment["mean"] > 4.0
        assert cp.rationale  # detector id + params recorded (transparency)

    def test_no_change_flat_series(self) -> None:
        series = build_series("flat", _samples(datetime(2026, 1, 1, tzinfo=UTC), [2.0] * 40))
        points = detect_change_points(series, ChangeDetectParams(window=5, min_shift=1.0))
        assert points == []


class TestReprojection:
    def test_reprojection_supersedes_original_stays_queryable(self) -> None:
        store = ScienceStore()
        series = build_series(
            "rho", _samples(datetime(2026, 1, 1, tzinfo=UTC), [0.5] * 30 + [0.9] * 30)
        )
        original_id = series.series_id
        scenario_spec = {"regime_count": 2, "pipeline_version": "0.1.0"}
        v2 = reproject(series, scenario_spec, store=store)[0]

        assert v2.series_id != original_id
        assert v2.parent_version == original_id
        assert v2.scenario_spec == scenario_spec

        # original projection stays queryable (FR-015: never mutated)
        original = store.get("temporal", original_id)
        assert original is not None
        assert original.get("supersedes_ref") in (None, "")
        v2_record = store.get("temporal", v2.series_id)
        assert v2_record["supersedes_ref"] == original_id