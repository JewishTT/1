"""Temporal series builder (T115, US4; interface-contracts §6, I-1).

Builds a ``TemporalSeries`` from observation samples: timestamps are normalized
to UTC while every original local value is preserved (I-1) in
``original_timestamps`` — nothing about the raw record is dropped.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class ObservationSample:
    """One time-ordered observation (I-1: original time always preserved)."""

    time: datetime
    value: float


@dataclass
class ChangePoint:
    index: int
    time: datetime
    confidence: float
    pre_segment: dict[str, float]
    post_segment: dict[str, float]
    rationale: dict[str, Any]


@dataclass
class TemporalSeries:
    series_id: str
    variable: str
    timestamps: list[datetime] = field(default_factory=list)
    values: list[float] = field(default_factory=list)
    original_timestamps: list[datetime] = field(default_factory=list)
    change_points: list[ChangePoint] = field(default_factory=list)
    scenario_spec: dict[str, Any] = field(default_factory=dict)
    parent_version: str | None = None

    def to_ref(self) -> dict[str, Any]:
        return {
            "series_id": self.series_id,
            "variable": self.variable,
            "timestamps": [t.isoformat() for t in self.timestamps],
            "values": self.values,
            "original_timestamps": [t.isoformat() for t in self.original_timestamps],
            "change_points": [
                {
                    "index": cp.index,
                    "time": cp.time.isoformat(),
                    "confidence": cp.confidence,
                    "pre_segment": cp.pre_segment,
                    "post_segment": cp.post_segment,
                    "rationale": cp.rationale,
                }
                for cp in self.change_points
            ],
            "scenario_spec": self.scenario_spec,
            "parent_version": self.parent_version,
        }


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _series_id(variable: str, samples: list[ObservationSample]) -> str:
    digest = hashlib.sha256(
        f"{variable}|{'|'.join(s.time.isoformat() for s in samples[:16])}".encode()
    ).hexdigest()[:12]
    return f"TS-{digest}"


def build_series(
    variable: str,
    samples: list[ObservationSample],
    *,
    scenario_spec: dict[str, Any] | None = None,
    parent_version: str | None = None,
) -> TemporalSeries:
    """Build a UTC-normalized series, preserving original local times (I-1)."""
    ordered = sorted(samples, key=lambda s: s.time)
    return TemporalSeries(
        series_id=_series_id(variable, ordered),
        variable=variable,
        timestamps=[_normalize_utc(s.time) for s in ordered],
        values=[s.value for s in ordered],
        original_timestamps=[s.time for s in ordered],
        scenario_spec=scenario_spec or {},
        parent_version=parent_version,
    )