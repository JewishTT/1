"""Deterministic temporal materialization over accepted entity stream records."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from domain.dynamics import StreamRecord

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class MaterializationError(ValueError):
    """The input cannot produce a safe materialization."""


class LifecycleState(StrEnum):
    NASCENT = "nascent"
    GROWING = "growing"
    STABLE = "stable"
    DECAYING = "decaying"
    DORMANT = "dormant"


@dataclass(frozen=True)
class SourceCut:
    tenant_id: str
    entity_id: str
    source_record_ids: tuple[str, ...]
    source_record_hashes: tuple[str, ...]
    coverage_start: datetime
    coverage_end: datetime
    cut_id: str = ""

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.entity_id:
            raise MaterializationError("source cut requires tenant_id and entity_id")
        if self.coverage_start.tzinfo is None or self.coverage_end.tzinfo is None:
            raise MaterializationError("timezone-aware coverage required")
        if self.coverage_end < self.coverage_start:
            raise MaterializationError("invalid coverage range")
        object.__setattr__(self, "cut_id", self.cut_id or "cut-" + _digest(self._value())[:32])

    def _value(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "entity_id": self.entity_id,
            "source_record_ids": self.source_record_ids,
            "source_record_hashes": self.source_record_hashes,
            "coverage_start": self.coverage_start.isoformat(),
            "coverage_end": self.coverage_end.isoformat(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {"cut_id": self.cut_id, **self._value()}


@dataclass(frozen=True)
class TemporalWindow:
    window_start: datetime
    window_end: datetime
    lifecycle: LifecycleState
    event_count: int
    first_seen: datetime | None
    last_seen: datetime | None
    source_record_ids: tuple[str, ...]
    observation_refs: tuple[str, ...]

    @property
    def is_dormant(self) -> bool:
        return self.lifecycle is LifecycleState.DORMANT

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "lifecycle": self.lifecycle.value,
            "event_count": self.event_count,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "source_record_ids": list(self.source_record_ids),
            "observation_refs": list(self.observation_refs),
        }


@dataclass(frozen=True)
class WindowRevision:
    revision_id: str
    revision_number: int
    window: TemporalWindow
    window_fingerprint: str
    source_cut_id: str
    parent_revision_id: str | None = None
    revision_reason: str = "initial"

    def to_dict(self) -> dict[str, Any]:
        return {
            "revision_id": self.revision_id,
            "revision_number": self.revision_number,
            "window": self.window.to_dict(),
            "window_fingerprint": self.window_fingerprint,
            "source_cut_id": self.source_cut_id,
            "parent_revision_id": self.parent_revision_id,
            "revision_reason": self.revision_reason,
        }


@dataclass(frozen=True)
class TemporalFeature:
    feature_name: str
    value: int | float | str | None
    available: bool
    structural_only: bool
    source_record_ids: tuple[str, ...]
    feature_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_name": self.feature_name,
            "value": self.value,
            "available": self.available,
            "structural_only": self.structural_only,
            "source_record_ids": list(self.source_record_ids),
            "feature_fingerprint": self.feature_fingerprint,
        }


@dataclass(frozen=True)
class HistoryPublication:
    publication_id: str
    source_cut: SourceCut
    revisions: tuple[WindowRevision, ...]
    features: tuple[TemporalFeature, ...]
    integrity_fingerprint: str
    projection_generation: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "publication_id": self.publication_id,
            "source_cut": self.source_cut.to_dict(),
            "revisions": [r.to_dict() for r in self.revisions],
            "features": [f.to_dict() for f in self.features],
            "integrity_fingerprint": self.integrity_fingerprint,
            "projection_generation": self.projection_generation,
        }


@dataclass(frozen=True)
class TemporalHistory:
    tenant_id: str
    entity_id: str
    publication: HistoryPublication

    def window_at(self, at: datetime) -> WindowRevision | None:
        if at.tzinfo is None:
            raise MaterializationError("timezone-aware timestamp required")
        return next(
            (
                r
                for r in self.publication.revisions
                if r.window.window_start <= at < r.window.window_end
            ),
            None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "entity_id": self.entity_id,
            "publication": self.publication.to_dict(),
        }


def _digest(value: Any) -> str:
    def norm(v: Any) -> Any:
        if isinstance(v, dict):
            return {str(k): norm(v[k]) for k in sorted(v)}
        if isinstance(v, (list, tuple)):
            return [norm(x) for x in v]
        if isinstance(v, datetime):
            return v.isoformat()
        return v

    return hashlib.sha256(
        json.dumps(norm(value), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def window_bounds(ts: datetime, window: timedelta) -> tuple[datetime, datetime]:
    if ts.tzinfo is None or window <= timedelta(0):
        raise MaterializationError("timezone-aware timestamp and positive window required")
    span = window.total_seconds()
    start = _EPOCH + timedelta(
        seconds=math.floor((ts.astimezone(UTC) - _EPOCH).total_seconds() / span) * span
    )
    return start, start + window


def _occurrence(record: StreamRecord) -> datetime:
    raw = (record.payload or {}).get("event_at")
    if raw:
        value = raw if isinstance(raw, datetime) else datetime.fromisoformat(str(raw))
        if value.tzinfo is None:
            raise MaterializationError("event_at must be timezone-aware")
        return value.astimezone(UTC)
    return record.ts.astimezone(UTC)


def _records(
    records: Iterable[StreamRecord], tenant_id: str, entity_id: str
) -> tuple[StreamRecord, ...]:
    unique: dict[str, StreamRecord] = {}
    for record in records:
        if not isinstance(record, StreamRecord):
            raise MaterializationError("StreamRecord required")
        if record.tenant_id != tenant_id or record.entity_id != entity_id:
            raise MaterializationError("mixed tenant/entity input rejected")
        if record.ts.tzinfo is None:
            raise MaterializationError("timezone-aware source timestamp required")
        unique.setdefault(record.record_hash, record)
    if not unique:
        raise MaterializationError("empty history rejected")
    return tuple(sorted(unique.values(), key=lambda r: (_occurrence(r), r.sequence, r.record_hash)))


def _windows(records: tuple[StreamRecord, ...], window: timedelta) -> tuple[TemporalWindow, ...]:
    buckets: dict[tuple[datetime, datetime], list[StreamRecord]] = {}
    for record in records:
        start, end = window_bounds(_occurrence(record), window)
        buckets.setdefault((start, end), []).append(record)
    first, _ = window_bounds(_occurrence(records[0]), window)
    _, last_end = window_bounds(_occurrence(records[-1]), window)
    cursor = first
    previous: int | None = None
    result: list[TemporalWindow] = []
    while cursor < last_end:
        end = cursor + window
        bucket = sorted(
            buckets.get((cursor, end), []),
            key=lambda r: (_occurrence(r), r.sequence, r.record_hash),
        )
        times = [_occurrence(r) for r in bucket]
        if not bucket:
            state = LifecycleState.DORMANT
        elif previous is None:
            state = LifecycleState.NASCENT
        elif len(bucket) > previous * 1.1:
            state = LifecycleState.GROWING
        elif len(bucket) < previous * 0.9:
            state = LifecycleState.DECAYING
        else:
            state = LifecycleState.STABLE
        result.append(
            TemporalWindow(
                cursor,
                end,
                state,
                len(bucket),
                min(times) if times else None,
                max(times) if times else None,
                tuple(r.record_id for r in bucket),
                tuple(r.observation_id for r in bucket if r.observation_id),
            )
        )
        if bucket:
            previous = len(bucket)
        cursor = end
    return tuple(result)


def materialize_history(
    records: Iterable[StreamRecord],
    *,
    tenant_id: str,
    entity_id: str,
    window: timedelta = timedelta(days=7),
    projection_generation: int = 1,
) -> TemporalHistory:
    """Build deterministic windows, revisions, features, and a publication."""
    if not tenant_id or not entity_id or window <= timedelta(0):
        raise MaterializationError("scope and positive window required")
    ordered = _records(records, tenant_id, entity_id)
    windows = _windows(ordered, window)
    cut = SourceCut(
        tenant_id,
        entity_id,
        tuple(r.record_id for r in ordered),
        tuple(r.record_hash for r in ordered),
        windows[0].window_start,
        windows[-1].window_end,
    )
    revisions: list[WindowRevision] = []
    features: list[TemporalFeature] = []
    for number, item in enumerate(windows, 1):
        fingerprint = _digest(item.to_dict())
        revisions.append(
            WindowRevision(
                "wr-" + fingerprint[:32],
                number,
                item,
                fingerprint,
                cut.cut_id,
                revision_reason="initial" if number == 1 else "window-derived",
            )
        )
        value = None if item.is_dormant else item.event_count
        features.append(
            TemporalFeature(
                "event_count",
                value,
                value is not None,
                False,
                item.source_record_ids,
                _digest({"name": "event_count", "value": value, "window": fingerprint}),
            )
        )
    integrity = _digest(
        {
            "cut": cut.to_dict(),
            "revisions": [r.to_dict() for r in revisions],
            "features": [f.to_dict() for f in features],
        }
    )
    return TemporalHistory(
        tenant_id,
        entity_id,
        HistoryPublication(
            "pub-" + integrity[:32],
            cut,
            tuple(revisions),
            tuple(features),
            integrity,
            projection_generation,
        ),
    )


@dataclass(frozen=True)
class CandidateComparison:
    added_window_starts: tuple[datetime, ...]
    changed_window_starts: tuple[datetime, ...]
    unchanged_window_starts: tuple[datetime, ...]

    @property
    def changed(self) -> bool:
        return bool(self.added_window_starts or self.changed_window_starts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "added_window_starts": [x.isoformat() for x in self.added_window_starts],
            "changed_window_starts": [x.isoformat() for x in self.changed_window_starts],
            "unchanged_window_starts": [x.isoformat() for x in self.unchanged_window_starts],
        }


def compare_publications(
    current: TemporalHistory | None, candidate: TemporalHistory
) -> CandidateComparison:
    old = (
        {r.window.window_start: r.window_fingerprint for r in current.publication.revisions}
        if current
        else {}
    )
    new = {r.window.window_start: r.window_fingerprint for r in candidate.publication.revisions}
    added = tuple(sorted(set(new) - set(old)))
    changed = tuple(sorted(start for start in set(new) & set(old) if new[start] != old[start]))
    unchanged = tuple(sorted(start for start in set(new) & set(old) if new[start] == old[start]))
    return CandidateComparison(added, changed, unchanged)


def compute_affected_closure(
    late_record: StreamRecord,
    *,
    window: timedelta = timedelta(days=7),
    existing: TemporalHistory | None = None,
) -> tuple[datetime, ...]:
    """Return the late event's window and later windows already covered by history."""
    start, _ = window_bounds(_occurrence(late_record), window)
    if existing is None:
        return (start,)
    starts = sorted(r.window.window_start for r in existing.publication.revisions)
    return tuple(candidate for candidate in starts if candidate >= start)


def classify_source_reuse(
    *, source_record_id: str, existing_fingerprint: str | None, incoming_fingerprint: str
) -> str:
    if existing_fingerprint is None:
        return "accepted"
    if existing_fingerprint == incoming_fingerprint:
        return "exact_duplicate"
    return "contradictory"


def reconcile_history(
    *, expected_fingerprints: set[str], actual_fingerprints: set[str]
) -> dict[str, Any]:
    missing = sorted(expected_fingerprints - actual_fingerprints)
    extra = sorted(actual_fingerprints - expected_fingerprints)
    return {"ok": not missing and not extra, "missing": missing, "extra": extra}


__all__ = [
    "CandidateComparison",
    "HistoryPublication",
    "LifecycleState",
    "MaterializationError",
    "SourceCut",
    "TemporalFeature",
    "TemporalHistory",
    "TemporalWindow",
    "WindowRevision",
    "classify_source_reuse",
    "compare_publications",
    "compute_affected_closure",
    "materialize_history",
    "reconcile_history",
    "window_bounds",
]
