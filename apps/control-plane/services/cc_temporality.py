"""CC temporality orchestrator (CC-TEMPORALITY v1, L3 composition root).

Glues the temporality circle into one synchronous, auditable call:

    L1 plan (acquisition.cc_plan) → L0 pull (zero.cc_capture, transport only) →
    L1 extract (acquisition.cc_extract) → L2 series (series_lifecycle.project_cc_series)

The orchestrator composes; it owns nothing (no storage, no caching) and knows
no network itself — L0 does, through the injectable ``session`` seam. The UI
request is intentionally synchronous and small (limit ≤ 50): no background
tasks, progress is a single honest SSE event (``cc.temporality``) published at
the end.

Honesty (I-3): missing identity, missing captures, unparseable timestamps —
each yields an *empty* structure plus a note in ``notes``, never a fabricated
series or interpolated point.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

# Import bootstrap (mirrors zero/tests/conftest.py): the workspace apps are
# resolved by path until ``uv sync`` installs cognitive-zero/cognitive-acquisition.
_APPS_DIR = Path(__file__).resolve().parents[2]  # 1/apps
for _p in (_APPS_DIR, _APPS_DIR / "zero"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from acquisition.cc_extract import CaptureObservation, normalize_captures  # noqa: E402
from acquisition.cc_plan import build_cc_plan  # noqa: E402
from api.sse import hub  # noqa: E402
from domain.temporal_metrics import burstiness, events_per_day  # noqa: E402
from services.series_lifecycle import SeriesRow, project_cc_series  # noqa: E402
from zero.cc_capture import RawCapture, pull_capture_index  # noqa: E402

_EMPTY_METRICS: dict[str, float | None] = {"burstiness": None, "events_per_day": None}


def _plan_payload(plan) -> dict[str, Any]:
    return {
        "kind": plan.kind,
        "url_query": plan.url_query,
        "match_type": plan.match_type,
        "surt_prefix": plan.surt_prefix,
        "limit": plan.limit,
    }


def _raw_mappings(raw: list[RawCapture]) -> list[Mapping[str, object]]:
    """L1 boundary: L0 records (dataclass with ``to_dict``) → plain Mappings."""
    return [r.to_dict() if hasattr(r, "to_dict") else dict(r) for r in raw]


def _observations_payload(observations: list[CaptureObservation]) -> list[dict[str, Any]]:
    return [
        {
            "url": o.url,
            "observed_at": o.observed_at,
            "status": o.status,
            "digest": o.digest,
        }
        for o in observations
    ]


def _series_payload(rows: list[SeriesRow]) -> list[dict[str, Any]]:
    """Daily capture-count buckets (metric ``cc_capture_count``) → UI bars."""
    return [
        {"t": r.ts.date().isoformat(), "count": int(r.metric_value or 0)}
        for r in sorted(rows, key=lambda r: r.ts)
        if r.metric_name == "cc_capture_count"
    ]


def _metrics_payload(observations: list[CaptureObservation]) -> dict[str, float | None]:
    timestamps = [
        datetime.fromisoformat(o.observed_at.replace("Z", "+00:00")).replace(tzinfo=UTC)
        for o in observations
    ]
    if not timestamps:
        return dict(_EMPTY_METRICS)
    try:
        b: float | None = burstiness(timestamps)
    except ValueError:  # < 2 events: burstiness undefined — None, not a guess (I-3)
        b = None
    return {"burstiness": b, "events_per_day": events_per_day(timestamps)}


def run_cc_temporality(
    entity_id: str,
    canonical_identity: Mapping[str, str],
    *,
    session: Any | None = None,
) -> dict[str, Any]:
    """Run the CC temporality circle for one atomic entity and publish it.

    Returns the final API payload:
    ``{entity_id, plan, captures, series, metrics, notes}``.
    ``session=None`` lets L0 build its live ``CcIndexSession``; hermetic tests
    inject a fake session (or monkeypatch ``pull_capture_index``).
    """
    notes: list[str] = []
    plan = build_cc_plan(entity_id, canonical_identity)

    if plan is None:
        notes.append(
            "insufficient data: canonical identity has no url/domain/host/site/"
            "name/full_name/account key — no CC query plan (I-3)"
        )
        payload: dict[str, Any] = {
            "entity_id": entity_id,
            "plan": None,
            "captures": [],
            "series": [],
            "metrics": dict(_EMPTY_METRICS),
            "notes": notes,
        }
        hub.publish("cc.temporality", payload)
        return payload

    raw = pull_capture_index(
        plan.url_query,
        plan.match_type,
        plan.surt_prefix,
        limit=plan.limit,
        session=session,
    )
    observations = normalize_captures(_raw_mappings(raw))
    if not observations:
        notes.append(
            "insufficient data: Common Crawl index returned no captures for this identity (I-3)"
        )

    rows = project_cc_series(entity_id, _observations_payload(observations))
    series = _series_payload(rows)
    if not series:
        notes.append(
            "insufficient data: no parseable capture timestamps — series left empty (I-3)"
        )

    payload = {
        "entity_id": entity_id,
        "plan": _plan_payload(plan),
        "captures": _observations_payload(observations),
        "series": series,
        "metrics": _metrics_payload(observations),
        "notes": notes,
    }
    hub.publish("cc.temporality", payload)
    return payload


__all__ = ["run_cc_temporality"]
