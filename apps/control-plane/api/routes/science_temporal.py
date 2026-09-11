"""Science temporal API (T118, US4; contracts/science-api.md).

Base path ``/api/science/temporal``: builds UTC-normalized series, detects
change points with confidence + segment summaries, and returns versioned
projections (``SUPERSEDES`` links intact, originals stay queryable).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from store import ScienceStore
from temporal.changedetect import ChangeDetectParams, detect_change_points
from temporal.scenario import persist_series, reproject
from temporal.timeseries import ObservationSample, build_series

router = APIRouter(prefix="/api/science/temporal", tags=["science"])

_store = ScienceStore()


class SampleModel(BaseModel):
    time: str
    value: float


class BuildSeriesRequest(BaseModel):
    variable: str
    samples: list[SampleModel]


class ChangePointsRequest(BaseModel):
    series_id: str
    window: int = Field(default=5, ge=2)
    min_shift: float = Field(default=1.0, gt=0.0)


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _record_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "series_id": record.get("series_id"),
        "variable": record.get("variable"),
        "values": record.get("values"),
        "timestamps": record.get("timestamps"),
        "change_points": record.get("change_points"),
        "supersedes_ref": record.get("supersedes_ref"),
        "scenario_spec": record.get("scenario_spec"),
    }


@router.post("/series")
async def post_series(body: BuildSeriesRequest) -> dict[str, Any]:
    samples = [ObservationSample(time=_parse_time(s.time), value=s.value) for s in body.samples]
    series = build_series(body.variable, samples)
    persist_series(series, store=_store)
    record = _store.get("temporal", series.series_id)
    payload = {"series_id": series.series_id, "variable": series.variable}
    payload.update(_record_summary(record or {}))
    return payload


@router.post("/change-points")
async def post_change_points(body: ChangePointsRequest) -> dict[str, Any]:
    record = _store.get("temporal", body.series_id)
    if record is None:
        raise HTTPException(status_code=404, detail="series not found")
    series = build_series(
        record.get("variable", ""),
        [
            ObservationSample(
                time=_parse_time(t) if isinstance(t, str) else t,
                value=float(v),
            )
            for t, v in zip(record.get("timestamps", []), record.get("values", []), strict=False)
        ],
    )
    series.change_points = detect_change_points(
        series, ChangeDetectParams(window=body.window, min_shift=body.min_shift)
    )
    v2, _env = reproject(series, {"regime_count": len(series.change_points), "window": body.window, "min_shift": body.min_shift}, store=_store)
    return _record_summary(_store.get("temporal", v2.series_id) or {})


@router.get("/series/{series_id}")
async def get_series(series_id: str) -> dict[str, Any]:
    record = _store.get("temporal", series_id)
    if record is None:
        raise HTTPException(status_code=404, detail="series not found")
    return _record_summary(record)