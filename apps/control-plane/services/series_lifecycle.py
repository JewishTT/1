"""Series → ClickHouse lifecycle projector (FR-006, 011).

The full lifecycle time-series of an atomic entity is a *projection* (block I):
it never mutates the delimiter stream (L0), it is deterministically rebuildable
from it (I-12), and it is materialized into ClickHouse as a ReplacingMergeTree
whose rows carry a monotone ``version`` equal to the source timestamp.

ReplacingMergeTree(version) semantic: rows with the same (pk) are collapsed on
merge (background), and query-time ``FINAL`` returns the true latest state —
so a replayed / re-fetched SourceRecording row idempotently converges to the
*canonical* SeriesRow. This is exactly the "honest rebuild" contract: the
projection is NEVER the source of truth, the stream is.

Storage is behind a tiny protocol so tests run on an in-memory table while
production talks to ClickHouse. Empty/None metric values are stored as NULL
(I-3 honesty: we never fabricate numbers).
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable, Mapping, Protocol

from domain.temporal_metrics import temporal_metrics


@dataclass(frozen=True)
class SeriesRow:
    """One materialized row of an entity's life-series (replaces-on-version)."""

    tenant_id: str
    entity_id: str
    key: str
    ts: datetime
    metric_name: str
    metric_value: float | None
    series_hash: str
    source_provenance: str  # e.g. CAFEBABE@observation_id (I-12 required)

    @property
    def pk(self) -> tuple[str, str, str, str, str]:
        """ReplacingMergeTree ORDER BY key: (tenant, entity, key, metric, ts)."""
        return (self.tenant_id, self.entity_id, self.key, self.metric_name, self.ts.isoformat())


class SeriesTable(Protocol):
    def upsert(self, rows: list[SeriesRow]) -> int: ...

    def canonical(self, *, entity_id: str, key: str, tenant_id: str = "default") -> list[SeriesRow]: ...


class MemorySeriesTable:
    """In-memory ReplacingMergeTree-equivalent for tests and pilot."""

    def __init__(self) -> None:
        self._rows: dict[tuple, SeriesRow] = {}

    def upsert(self, rows: list[SeriesRow]) -> int:
        previous = len(self._rows)
        for r in rows:
            self._rows[r.pk] = r
        return len(self._rows) - previous

    def canonical(self, *, entity_id: str, key: str, tenant_id: str = "default") -> list[SeriesRow]:
        out = [
            r
            for r in self._rows.values()
            if r.entity_id == entity_id and r.key == key and r.tenant_id == tenant_id
        ]
        return sorted(out, key=lambda r: r.ts)


SeriesTableDDL = """
CREATE TABLE IF NOT EXISTS entity_series
(
    tenant_id        LowCardinality(String),
    entity_id        String,
    key              String,
    ts               DateTime64(6),
    metric_name      LowCardinality(String),
    metric_value     Nullable(Float64),
    series_hash      String,
    source_provenance String
)
ENGINE = ReplacingMergeTree(ts)
PARTITION BY toYYYYMM(ts)
ORDER BY (tenant_id, entity_id, key, metric_name, ts);
"""
# ReplacingMergeTree(ts): the ts is the *version* — replaying a row with the
# same pk converges to the newest, so re-fetches are idempotent (SC-004).


class SeriesProjector:
    """Deterministic projector: stream events (or folded Series) → SeriesRow.

    The projector must be a pure function of its input: given the same
    underlying observations it always reaches the same canonical life-series.
    If the hosting app has ClickHouse it binds the DDL above; otherwise the
    caller passes a MemorySeriesTable (pilot/tests).
    """

    def __init__(self, table: SeriesTable, tenant_id: str = "default") -> None:
        self._table = table
        self._tenant = tenant_id

    def project_series(
        self,
        *,
        entity_id: str,
        key: str,
        timestamps: list[datetime],
        series_hash: str,
        source_provenance: str,
    ) -> list[SeriesRow]:
        metrics = temporal_metrics(timestamps)
        rows: list[SeriesRow] = []
        for name, value in metrics.items():
            rows.append(
                SeriesRow(
                    tenant_id=self._tenant,
                    entity_id=entity_id,
                    key=key,
                    ts=timestamps[-1] if timestamps else datetime.now(UTC),
                    metric_name=name,
                    metric_value=float(value) if value is not None else None,
                    series_hash=series_hash,
                    source_provenance=source_provenance,
                )
            )
        self._table.upsert(rows)
        return rows

    def canonical(self, *, entity_id: str, key: str) -> list[SeriesRow]:
        return self._table.canonical(entity_id=entity_id, key=key, tenant_id=self._tenant)


def _parse_observed_at(value: object) -> datetime | None:
    """Parse an ISO-UTC observation timestamp (I-3: invalid → None, never fabricated)."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def project_cc_series(
    entity_id: str,
    observations: Iterable[Mapping[str, object]],
    *,
    key: str = "cc_captures",
    tenant_id: str = "default",
    table: SeriesTable | None = None,
) -> list[SeriesRow]:
    """Project CC-capture observations (L1 extract) into the entity's life-series.

    Contract CC-TEMPORALITY v1: mapping keys are ``url``/``observed_at``/
    ``status``/``digest`` (what L1 ``normalize_captures`` emits). The projector
    is a pure function of its input — deterministic bucketing by ``observed_at``
    (daily UTC buckets, honest counts — I-3), dedup by ``(digest, observed_at)``,
    and temporal metrics (burstiness, events_per_day, ...) materialized through
    the existing ``SeriesProjector`` (ReplacingMergeTree-ready, ClickHouse-ready).
    """
    seen: set[tuple[str, str]] = set()
    events: list[tuple[datetime, str]] = []
    for obs in observations:
        ts = _parse_observed_at(obs.get("observed_at"))
        if ts is None:
            continue  # unparseable timestamp: skipped, not fabricated
        digest = str(obs.get("digest") or "")
        identity = (digest, ts.isoformat())
        if identity in seen:
            continue
        seen.add(identity)
        events.append((ts, digest))
    events.sort(key=lambda e: (e[0], e[1]))
    if not events:
        return []  # empty stream ⇒ empty projection (I-3)

    timestamps = [ts for ts, _ in events]
    digests = [digest for _, digest in events]
    fingerprint = hashlib.sha256(
        "\n".join(f"{ts.isoformat()}|{digest}" for ts, digest in events).encode("utf-8")
    ).hexdigest()[:32]
    series_hash = f"cc-{fingerprint}"
    # I-12 provenance: deterministic anchor into the delimiter stream (L0 digest).
    source_provenance = f"cc-index@{digests[0]}"

    table = table if table is not None else MemorySeriesTable()
    projector = SeriesProjector(table, tenant_id=tenant_id)
    rows: list[SeriesRow] = list(
        projector.project_series(
            entity_id=entity_id,
            key=key,
            timestamps=timestamps,
            series_hash=series_hash,
            source_provenance=source_provenance,
        )
    )

    counts = Counter(ts.date() for ts in timestamps)
    buckets = [
        SeriesRow(
            tenant_id=tenant_id,
            entity_id=entity_id,
            key=key,
            ts=datetime(day.year, day.month, day.day, tzinfo=UTC),
            metric_name="cc_capture_count",
            metric_value=float(counts[day]),
            series_hash=series_hash,
            source_provenance=source_provenance,
        )
        for day in sorted(counts)
    ]
    table.upsert(buckets)
    rows.extend(buckets)
    rows.sort(key=lambda r: (r.ts, r.metric_name))
    return rows


__all__ = [
    "MemorySeriesTable",
    "SeriesProjector",
    "SeriesRow",
    "SeriesTable",
    "SeriesTableDDL",
    "project_cc_series",
]