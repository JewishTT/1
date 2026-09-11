"""Versioned reprojection (T117, US4; FR-015, I-12).

Re-running an analysis under new parameters never mutates the prior projection:
``reproject`` persists the parent series (when absent) and emits a fresh
``science.temporal.change_point`` envelope carrying the new series state plus a
``parent_version`` (``SUPERSEDES``) link. Every version stays queryable and the
event log fully reconstructs all of them.
"""

from __future__ import annotations

import hashlib
from typing import Any

from _events import envelope as _emit
from store import ScienceStore
from temporal.changedetect import ChangeDetectParams, detect_change_points
from temporal.timeseries import ObservationSample, TemporalSeries, build_series


def _versioned_id(parent: str, scenario_spec: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        f"{parent}|{scenario_spec}".encode()
    ).hexdigest()[:12]
    return f"TS-{digest}"


def _change_point_payload(
    series: TemporalSeries,
    *,
    supersedes_ref: str | None,
    scenario_spec: dict[str, Any],
) -> dict[str, Any]:
    return {
        "series_id": series.series_id,
        "variable": series.variable,
        "values": series.values,
        "timestamps": [t.isoformat() for t in series.timestamps],
        "change_points": [
            {
                "index": cp.index,
                "time": cp.time.isoformat(),
                "confidence": cp.confidence,
                "pre_segment": cp.pre_segment,
                "post_segment": cp.post_segment,
                "rationale": cp.rationale,
            }
            for cp in series.change_points
        ],
        "supersedes_ref": supersedes_ref,
        "scenario_spec": scenario_spec,
    }


def persist_series(
    series: TemporalSeries,
    *,
    store: ScienceStore,
    producer: Any = None,
) -> object:
    """Persist a series projection so it stays queryable (I-12)."""
    env = _emit(
        event_type="science.temporal.change_point",
        payload=_change_point_payload(
            series,
            supersedes_ref=series.parent_version,
            scenario_spec=series.scenario_spec,
        ),
        producer=producer,
        key=series.series_id,
    )
    store.apply(env)
    return env


def reproject(
    series: TemporalSeries,
    scenario_spec: dict[str, Any],
    *,
    change_params: ChangeDetectParams | None = None,
    producer: Any = None,
    store: ScienceStore | None = None,
) -> tuple[TemporalSeries, object]:
    """Reproject under new scenario params; supersedes the parent version."""
    if store is not None and store.get("temporal", series.series_id) is None:
        persist_series(series, store=store, producer=producer)

    samples = [
        ObservationSample(time=t, value=v)
        for t, v in zip(series.timestamps, series.values, strict=True)
    ]
    rebuilt = build_series(
        series.variable,
        samples,
        scenario_spec=scenario_spec,
        parent_version=series.series_id,
    )
    rebuilt.series_id = _versioned_id(series.series_id, scenario_spec)

    params = change_params or ChangeDetectParams()
    rebuilt.change_points = detect_change_points(rebuilt, params)

    env = _emit(
        event_type="science.temporal.change_point",
        payload=_change_point_payload(
            rebuilt,
            supersedes_ref=series.series_id,
            scenario_spec=scenario_spec,
        ),
        producer=producer,
        key=rebuilt.series_id,
    )
    if store is not None:
        store.apply(env)
    return rebuilt, env