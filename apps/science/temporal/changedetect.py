"""Change-point detection (T116, US4; interface-contracts §6).

Windowed mean-shift detector: for every interior index a bounded trailing
window is compared against a bounded leading window; a segment mean difference
above ``min_shift`` marks a candidate. Candidates are merged into non-
overlapping windows (a minimum spacing keeps one change point per regime
boundary), scored by confidence, and returned with explicit segment summaries
and the detector rationale — never a bare index.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

from temporal.timeseries import ChangePoint, TemporalSeries, _normalize_utc


@dataclass(frozen=True)
class ChangeDetectParams:
    window: int = 5
    min_shift: float = 1.0
    min_spacing: int = 6
    detector: str = "mean-shift"

    def rationale(self, window: int, min_shift: float) -> dict[str, object]:
        return {
            "detector": self.detector,
            "window": window,
            "min_shift": min_shift,
        }


def _segment_summary(values: list[float]) -> dict[str, float]:
    return {"mean": mean(values), "n": float(len(values))}


def detect_change_points(
    series: TemporalSeries,
    params: ChangeDetectParams,
) -> list[ChangePoint]:
    """Detect regime discontinuities with confidence + segment summaries."""
    values = series.values
    n = len(values)
    window = max(1, params.window)
    if n < 2 * window + 2:
        return []

    candidates: list[dict[str, float]] = []
    for index in range(window, n - window):
        pre = values[index - window : index]
        post = values[index : index + window]
        pre_mean = mean(pre)
        post_mean = mean(post)
        shift = abs(post_mean - pre_mean)
        if shift >= params.min_shift:
            confidence = shift / (shift + max(params.min_shift, 1e-9))
            candidates.append(
                {"index": float(index), "confidence": confidence, "shift": shift}
            )

    # merge non-overlapping picks, keeping the strongest shift per regime boundary
    selected: list[dict[str, float]] = []
    for candidate in sorted(candidates, key=lambda c: c["shift"], reverse=True):
        if all(abs(candidate["index"] - existing["index"]) >= params.min_spacing for existing in selected):
            selected.append(candidate)
    selected.sort(key=lambda c: c["index"])

    points: list[ChangePoint] = []
    for candidate in selected:
        index = int(candidate["index"])
        points.append(
            ChangePoint(
                index=index,
                time=_normalize_utc(series.timestamps[index]),
                confidence=candidate["confidence"],
                pre_segment=_segment_summary(values[index - window : index]),
                post_segment=_segment_summary(values[index : index + window]),
                rationale=params.rationale(window, params.min_shift),
            )
        )
    return points