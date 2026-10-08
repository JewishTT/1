"""Temporal graph in ClickHouse (Feature 024, D2 / input.md §11.2).

The gap this closes
-------------------
``apps/projection/analytics/store.py`` is self-described as an "in-memory
ClickHouse-analog" -- 62 lines over a ``dict``. It keeps per-source counters and
nothing else. Meanwhile the platform already has a real temporal model in
``domain/dynamics.py`` (``StreamRecord``, ``EntityState``, ``Series``) and a worldline
builder in ``domain/temporal_worldline.py``. So the temporal graph existed as domain
logic and as *nothing at all* as analytical storage: no validity interval was ever
queryable, so "what was true about this entity between T1 and T2" had no answer.

Schema mirrors the platform's own record, not an invention:

* ``entity_id``    -- the subject
* ``kind``         -- event kind, ``domain.dynamics`` vocabulary
* ``valid_from`` / ``valid_until`` -- the validity interval, half-open
* ``sequence``     -- ordering within one entity
* ``record_hash``  -- content address; its leading 60 bits become the ReplacingMergeTree ``version``

``ReplacingMergeTree(version)`` gives idempotency natively: replaying the same
stream converges instead of duplicating, which is what Constitution III means by a
rebuildable projection. The interval columns carry the graph's temporality, so a query
can ask what was true at any instant without re-materialising the worldline.

Measured on ClickHouse 24.8, because the guarantee is weaker than it looks: collapsing
happens at merge time. A replayed row is still physically present until then (3 rows),
reads correctly only through ``FINAL`` (2 rows), and becomes visible without ``FINAL``
after ``OPTIMIZE TABLE ... FINAL``. Every read in this module uses ``FINAL``.
Deduplication is guaranteed; it is not immediate.

Reused, not rewritten: the record vocabulary and the identity discipline in
``domain.dynamics``. Nothing here re-decides what an observation is.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

SCHEMA_VERSION = "temporal-ch/v1"


class ClickHouseClient(Protocol):
    """The subset of a ClickHouse client this store uses.

    A Protocol rather than a concrete driver so domain logic carries no vendor class,
    and so the store is testable without a server.
    """

    async def execute(self, query: str) -> None: ...
    async def fetch_all(self, query: str) -> list[dict[str, Any]]: ...


#: The entity event stream. ReplacingMergeTree on ``record_hash`` means a replayed
#: record collapses onto its earlier copy instead of accumulating.
ENTITY_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS entity_events (
    tenant_id          LowCardinality(String),
    entity_id          String,
    kind               LowCardinality(String),
    entity_class       LowCardinality(String),
    observation_id     String,
    dataset_id         String,
    record_hash        String,
    record_id          String,
    sequence           UInt32,
    extraction_version LowCardinality(String),
    ts                 DateTime64(6, 'UTC'),
    valid_from         Nullable(DateTime64(6, 'UTC')),
    valid_until        Nullable(DateTime64(6, 'UTC')),
    payload            String,
    -- ReplacingMergeTree's version column must be an integer or Date/DateTime
    -- (Code 169 BAD_TYPE_OF_FIELD), so the content hash cannot be the version
    -- directly. `version` is its leading 60 bits, supplied by the writer: still
    -- derived purely from content, so replaying a stream collapses onto itself.
    version            UInt64,
    -- valid_from stays nullable because "no explicit validity bound" is a real,
    -- meaningful state. But MergeTree refuses a nullable sorting key (Code 44), so
    -- ordering runs on this non-nullable projection instead: an event with no
    -- explicit bound sorts at its ts, which is where it was actually observed.
    sort_valid_from    DateTime64(6, 'UTC') MATERIALIZED coalesce(valid_from, ts),
    ingested_at        DateTime64(6, 'UTC') DEFAULT now64(6)
)
ENGINE = ReplacingMergeTree(version)
PARTITION BY tenant_id
ORDER BY (tenant_id, entity_id, sort_valid_from, sequence)
"""

#: Latest known state per entity. ReplacingMergeTree keeps the newest row per entity,
#: which is "current" by definition.
#:
#: An AggregatingMergeTree + materialized view was tried first and is the wrong tool
#: here: it forces AggregateFunction state columns and a view that must not GROUP BY,
#: which is fragile to extend and impossible to read without a -Merge combinator. The
#: aggregate is cheap over entity_events and reads far more clearly, so ``current_entities``
#: asks for it directly instead of maintaining a second copy that can drift.
ENTITY_STATE_DDL = """
CREATE TABLE IF NOT EXISTS entity_state_current (
    tenant_id     LowCardinality(String),
    entity_id     String,
    entity_class  LowCardinality(String),
    kind          LowCardinality(String),
    ts            DateTime64(6, 'UTC'),
    valid_from    Nullable(DateTime64(6, 'UTC')),
    valid_until   Nullable(DateTime64(6, 'UTC')),
    observation_id String,
    dataset_id    String,
    payload       String,
    record_hash   String,
    version       UInt64
)
ENGINE = ReplacingMergeTree(version)
ORDER BY (tenant_id, entity_id)
"""

#: Validity intervals per entity, the answer to "when was this true".
ENTITY_INTERVALS_DDL = """
CREATE TABLE IF NOT EXISTS entity_validity (
    tenant_id   LowCardinality(String),
    entity_id   String,
    prop        LowCardinality(String),
    value       String,
    valid_from  DateTime64(6, 'UTC'),
    valid_until Nullable(DateTime64(6, 'UTC')),
    record_hash String,
    version     UInt64,
    -- An open interval means "still true", i.e. it runs to the end of time, so the
    -- sentinel is a far-future date rather than NULL. It also has to exist at all:
    -- valid_until is nullable and cannot be in the sorting key (Code 44), and without
    -- it an open interval and its later-closed version would collide on the same
    -- ORDER BY tuple and ReplacingMergeTree would silently drop one of them.
    sort_valid_until DateTime64(6, 'UTC') MATERIALIZED
        coalesce(valid_until, toDateTime64('2262-04-11 00:00:00.000000', 6, 'UTC'))
)
ENGINE = ReplacingMergeTree(version)
-- `value` is in the key because a graph property is not single-valued: an entity that
-- stood in five relations at one instant holds five concurrent true facts, and a key
-- of (entity, prop, valid_from) alone would collapse them to whichever arrived last.
-- The event stream keeps every assertion regardless; this is what makes the *queryable*
-- view complete too.
ORDER BY (tenant_id, entity_id, prop, valid_from, sort_valid_until, value)
"""

DDL_STATEMENTS = (
    ENTITY_EVENTS_DDL,
    ENTITY_STATE_DDL,
    ENTITY_INTERVALS_DDL,
)




@dataclass(frozen=True, slots=True)
class TemporalEvent:
    """One row of the entity event stream.

    Mirrors ``domain.dynamics.StreamRecord`` field for field. Built here rather than
    imported so the store's own vocabulary stays explicit at the boundary -- but the
    names and meanings are the platform's, not a second dialect.
    """

    tenant_id: str
    entity_id: str
    kind: str
    entity_class: str = "unknown"
    observation_id: str = ""
    dataset_id: str = ""
    record_id: str = ""
    sequence: int = 0
    extraction_version: str = ""
    ts: datetime | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    payload: Mapping[str, Any] | None = None

    #: True when ``ts`` was defaulted to wall-clock rather than asserted. Kept out of
    #: the content hash: an ingestion artifact is not content, and hashing it would
    #: make replay non-idempotent (every replay would mint a fresh hash and duplicate).
    _ts_defaulted: bool = field(default=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("temporal event needs tenant_id")
        if not self.entity_id:
            raise ValueError("temporal event needs entity_id")
        if not self.kind:
            raise ValueError("temporal event needs kind")
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError(
                f"validity inverted for {self.entity_id}: {self.valid_until} < {self.valid_from}"
            )
        if self.ts is None:
            object.__setattr__(self, "_ts_defaulted", True)
            object.__setattr__(self, "ts", self.valid_from or datetime.now(UTC))
        else:
            object.__setattr__(self, "_ts_defaulted", False)

    @property
    def record_hash(self) -> str:
        """Content address, via the same derivation the store uses for foreign events."""
        return _record_hash(
            tenant_id=self.tenant_id,
            entity_id=self.entity_id,
            kind=self.kind,
            entity_class=self.entity_class,
            observation_id=self.observation_id,
            dataset_id=self.dataset_id,
            sequence=self.sequence,
            ts=self.ts,
            valid_from=self.valid_from,
            valid_until=self.valid_until,
            payload=dict(self.payload or {}),
            ts_is_defaulted=self._ts_defaulted,
        )

    @property
    def version(self) -> int:
        """Leading 60 bits of the content hash: an integer version for
        ReplacingMergeTree that stays a pure function of content."""
        return int(self.record_hash[:15], 16)

    def to_row(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "entity_id": self.entity_id,
            "kind": self.kind,
            "entity_class": self.entity_class,
            "observation_id": self.observation_id,
            "dataset_id": self.dataset_id,
            "record_hash": self.record_hash,
            "record_id": self.record_id,
            "sequence": int(self.sequence),
            "extraction_version": self.extraction_version,
            "version": self.version,
            "ts": _aware(self.ts) or datetime(1970, 1, 1, tzinfo=UTC),
            "valid_from": _aware(self.valid_from),
            "valid_until": _aware(self.valid_until),
            "payload": json.dumps(dict(self.payload or {}), sort_keys=True, default=str),
        }

    def to_intervals(self) -> list[dict[str, Any]]:
        """Project payload properties into validity rows.

        A scalar property becomes an interval with an open end; an explicit
        ``{"valid_from": ..., "valid_until": ...}`` property keeps its own bounds.
        Anything non-scalar is stored on the event and not on the interval -- an
        interval over a nested structure would be a claim the data does not make.
        """
        rows: list[dict[str, Any]] = []
        for prop, value in (self.payload or {}).items():
            if isinstance(value, dict) and (
                "valid_from" in value or "valid_until" in value
            ):
                rows.append(
                    {
                        "tenant_id": self.tenant_id,
                        "entity_id": self.entity_id,
                        "prop": prop,
                        "value": json.dumps(value.get("value"), sort_keys=True, default=str),
                        "valid_from": value.get("valid_from") or _aware(self.valid_from),
                        "valid_until": value.get("valid_until") or _aware(self.valid_until),
                        "record_hash": self.record_hash,
                        "version": self.version,
                    }
                )
                continue
            if isinstance(value, (str, int, float, bool)):
                rows.append(
                    {
                        "tenant_id": self.tenant_id,
                        "entity_id": self.entity_id,
                        "prop": prop,
                        "value": str(value),
                        "valid_from": _aware(self.valid_from) or _aware(self.ts) or datetime(1970, 1, 1, tzinfo=UTC),
                        "valid_until": _aware(self.valid_until),
                        "record_hash": self.record_hash,
                        "version": self.version,
                    }
                )
        return rows


def _hash_ts(value: datetime | None) -> str | None:
    """Stable string form for content hashing.

    The hash must not depend on the server's accepted literal syntax, so this stays
    ISO-8601 in UTC and is deliberately independent of how the row is later written.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("a temporal timestamp crossing into ClickHouse must be tz-aware")
    return value.astimezone(UTC).isoformat()


def _aware(value: datetime | None) -> datetime | None:
    """Validate tz-awareness at the boundary and hand ClickHouse a real datetime.

    DateTime64('UTC') is tz-explicit, so a naive datetime would be an offset guess.
    Refuse it here rather than let it land as silent corruption.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("a temporal timestamp crossing into ClickHouse must be tz-aware")
    return value.astimezone(UTC)


class ClickHouseTemporalStore:
    """The temporal graph. Durable, replayable, queryable by instant."""

    def __init__(self, client: ClickHouseClient) -> None:
        self._client = client

    async def ensure_schema(self) -> None:
        for ddl in DDL_STATEMENTS:
            await self._client.execute(ddl)

    async def ingest(self, events: Sequence[Any]) -> int:
        """Insert events and their validity intervals. Returns rows written.

        Structural, not nominal: anything exposing the boundary attributes (see
        ``control-plane/services/temporal_port.py``) is accepted, so neither side has
        to import the other. That matters because control-plane importing projection
        is a forbidden dependency edge.

        Idempotent by construction: the content ``version`` is the
        ReplacingMergeTree version, so re-ingesting the same events collapses them
        rather than duplicating. That is what lets the canonical loop replay from the
        beginning of the stream without a cleanup pass.
        """
        if not events:
            return 0
        await self.ensure_schema()
        written = 0
        for event in events:
            row = _row_from(event)
            await self._client.execute(_insert("entity_events", row))
            for interval in _intervals_from(event):
                await self._client.execute(_insert("entity_validity", interval))
            written += 1
        return written

    # -- queries -------------------------------------------------------------

    async def state_at(
        self, *, tenant_id: str, entity_id: str, at: datetime
    ) -> list[dict[str, Any]]:
        """Everything believed about an entity at a given instant.

        Half-open interval semantics: ``valid_from <= at < valid_until``. An open
        ``valid_until`` means "still true", which is the common case and must not be
        mistaken for an absent value.
        """
        moment = _ch_datetime(at)
        return await self._client.fetch_all(
            f"""
            SELECT prop, value, valid_from, valid_until
            FROM entity_validity FINAL
            WHERE tenant_id = {_q(tenant_id)}
              AND entity_id = {_q(entity_id)}
              AND valid_from <= {moment}
              AND (valid_until IS NULL OR valid_until > {moment})
            ORDER BY prop
            """
        )

    async def history(
        self, *, tenant_id: str, entity_id: str, limit: int = 500
    ) -> list[dict[str, Any]]:
        """The raw event stream for one entity, ordered by validity then sequence."""
        return await self._client.fetch_all(
            f"""
            SELECT kind, ts, valid_from, valid_until, sequence,
                   observation_id, extraction_version, payload
            FROM entity_events FINAL
            WHERE tenant_id = {_q(tenant_id)}
              AND entity_id = {_q(entity_id)}
            ORDER BY sort_valid_from, sequence
            LIMIT {int(limit)}
            """
        )

    async def current_entities(
        self, *, tenant_id: str, limit: int = 1000
    ) -> list[dict[str, Any]]:
        """Every entity a tenant knows, with how much evidence stands behind it."""
        return await self._client.fetch_all(
            f"""
            SELECT entity_id,
                   any(entity_class)      AS entity_class,
                   min(ts)                AS first_seen,
                   max(ts)                AS last_seen,
                   count()                AS events,
                   uniqExact(observation_id) AS observations
            FROM entity_events FINAL
            WHERE tenant_id = {_q(tenant_id)}
            GROUP BY entity_id
            ORDER BY last_seen DESC, entity_id
            LIMIT {int(limit)}
            """
        )


def _q(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _insert(table: str, row: Mapping[str, Any]) -> str:
    columns = ", ".join(f"`{k}`" for k in row)
    values = ", ".join(_literal(v) for v in row.values())
    return f"INSERT INTO {table} ({columns}) VALUES ({values})"


def _record_hash(
    *,
    tenant_id: str,
    entity_id: str,
    kind: str,
    entity_class: str,
    observation_id: str,
    dataset_id: str,
    sequence: int,
    ts: datetime | None,
    valid_from: datetime | None,
    valid_until: datetime | None,
    payload: Mapping[str, Any],
    ts_is_defaulted: bool,
) -> str:
    """Content address of one assertion.

    Only *asserted* content is hashed. A defaulted ``ts`` is an ingestion artifact --
    including it would give every replay a fresh hash and break the idempotency the
    ReplacingMergeTree version depends on.
    """
    material = json.dumps(
        {
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "kind": kind,
            "entity_class": entity_class,
            "observation_id": observation_id,
            "dataset_id": dataset_id,
            "sequence": sequence,
            "ts": None if ts_is_defaulted else _hash_ts(ts),
            "valid_from": _hash_ts(valid_from),
            "valid_until": _hash_ts(valid_until),
            "payload": dict(payload),
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _row_from(event: Any) -> dict[str, Any]:
    """Build the event row from any object exposing the boundary attributes.

    Structural on purpose (see ``ingest``). ``record_hash`` and ``version`` are
    derived here rather than read off the producer, so the deduplication guarantee
    cannot be weakened by a caller that supplies its own or omits one.
    """
    tenant_id = str(getattr(event, "tenant_id", "") or "")
    entity_id = str(getattr(event, "entity_id", "") or "")
    kind = str(getattr(event, "kind", "") or "")
    for name, value in (("tenant_id", tenant_id), ("entity_id", entity_id), ("kind", kind)):
        if not value:
            raise ValueError(f"temporal event needs {name}")
    payload = dict(getattr(event, "payload", None) or {})
    ts = getattr(event, "ts", None)
    valid_from = getattr(event, "valid_from", None)
    valid_until = getattr(event, "valid_until", None)
    if valid_from and valid_until and valid_until < valid_from:
        raise ValueError(f"validity inverted for {entity_id}")
    record_hash = _record_hash(
        tenant_id=tenant_id,
        entity_id=entity_id,
        kind=kind,
        entity_class=str(getattr(event, "entity_class", "") or "unknown"),
        observation_id=str(getattr(event, "observation_id", "") or ""),
        dataset_id=str(getattr(event, "dataset_id", "") or ""),
        sequence=int(getattr(event, "sequence", 0) or 0),
        ts=ts,
        valid_from=valid_from,
        valid_until=valid_until,
        payload=payload,
        ts_is_defaulted=ts is None,
    )
    return {
        "tenant_id": tenant_id,
        "entity_id": entity_id,
        "kind": kind,
        "entity_class": str(getattr(event, "entity_class", "") or "unknown"),
        "observation_id": str(getattr(event, "observation_id", "") or ""),
        "dataset_id": str(getattr(event, "dataset_id", "") or ""),
        "record_hash": record_hash,
        "record_id": str(getattr(event, "record_id", "") or ""),
        "sequence": int(getattr(event, "sequence", 0) or 0),
        "extraction_version": str(getattr(event, "extraction_version", "") or ""),
        "version": int(record_hash[:15], 16),
        "ts": _aware(ts) or _aware(valid_from) or datetime(1970, 1, 1, tzinfo=UTC),
        "valid_from": _aware(valid_from),
        "valid_until": _aware(valid_until),
        "payload": json.dumps(payload, sort_keys=True, default=str),
    }


def _intervals_from(event: Any) -> list[dict[str, Any]]:
    """Project payload properties onto validity rows.

    A scalar property becomes an interval with an open end; an explicit
    ``{"valid_from": ..., "valid_until": ...}`` property keeps its own bounds.
    Anything non-scalar is left on the event only -- an interval over a nested
    structure would be a claim the data does not make.
    """
    entity_id = str(getattr(event, "entity_id", "") or "")
    tenant_id = str(getattr(event, "tenant_id", "") or "")
    payload = dict(getattr(event, "payload", None) or {})
    valid_from = getattr(event, "valid_from", None)
    valid_until = getattr(event, "valid_until", None)
    ts = getattr(event, "ts", None)
    row_hash = _record_hash(
        tenant_id=tenant_id,
        entity_id=entity_id,
        kind=str(getattr(event, "kind", "") or ""),
        entity_class=str(getattr(event, "entity_class", "") or "unknown"),
        observation_id=str(getattr(event, "observation_id", "") or ""),
        dataset_id=str(getattr(event, "dataset_id", "") or ""),
        sequence=int(getattr(event, "sequence", 0) or 0),
        ts=ts,
        valid_from=valid_from,
        valid_until=valid_until,
        payload=payload,
        ts_is_defaulted=ts is None,
    )
    version = int(row_hash[:15], 16)
    fallback = _aware(valid_from) or _aware(ts) or datetime(1970, 1, 1, tzinfo=UTC)
    rows: list[dict[str, Any]] = []
    for prop, value in payload.items():
        if isinstance(value, dict) and ("valid_from" in value or "valid_until" in value):
            rows.append(
                {
                    "tenant_id": tenant_id,
                    "entity_id": entity_id,
                    "prop": prop,
                    "value": json.dumps(value.get("value"), sort_keys=True, default=str),
                    "valid_from": value.get("valid_from") or _aware(valid_from) or fallback,
                    "valid_until": value.get("valid_until") or _aware(valid_until),
                    "record_hash": row_hash,
                    "version": version,
                }
            )
        elif isinstance(value, (str, int, float, bool)):
            rows.append(
                {
                    "tenant_id": tenant_id,
                    "entity_id": entity_id,
                    "prop": prop,
                    "value": str(value),
                    "valid_from": fallback,
                    "valid_until": _aware(valid_until),
                    "record_hash": row_hash,
                    "version": version,
                }
            )
    return rows


def _ch_datetime(value: datetime) -> str:
    """ClickHouse-native DateTime64 literal.

    Not an ISO string: parseDateTime64BestEffort rejects the '+00:00' offset form
    (Code 6 CANNOT_PARSE_TEXT, fails at the sign). A quoted 'YYYY-MM-DD hh:mm:ss.ffffff'
    is parsed directly and unambiguously, which is what a tz-explicit column wants.
    """
    if value.tzinfo is None:
        raise ValueError("a temporal timestamp crossing into ClickHouse must be tz-aware")
    return _q(value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f"))


def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, datetime):
        return _ch_datetime(value)
    return _q(str(value))


__all__ = [
    "DDL_STATEMENTS",
    "ENTITY_EVENTS_DDL",
    "ENTITY_INTERVALS_DDL",
    "ENTITY_STATE_DDL",
    "SCHEMA_VERSION",
    "ClickHouseClient",
    "ClickHouseTemporalStore",
    "TemporalEvent",
]