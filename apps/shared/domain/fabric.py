"""Atomic entity fabric — integration facade (feature 009, block A).

Feature-009 domain (``dynamics`` / ``hypergraph`` / ``stream_events``) was
pure and unplugged: only its own contract tests exercised it. This facade is
the composition root that wires it into the platform:

- **append-only persistence**: ``EntityStreamStore`` — one adapter per
  durable substrate (Postgres ``entity_stream`` table, object store, test).
  The store owns insertion *and* ordering (payloads are refs-only, I-5);
  duplicate ``record_hash`` is an idempotent no-op (I-11).
- **derived projections**: every appended record yields folded ``EntityState``
  (I-11/I-12 rebuildable), derived time series, and the refined
  ``entity.state.projected`` / ``entity.series.projected`` / ``hyperedge.*``
  events that consumers (admission, interpretation, TDA, search) subscribe to
  — nobody owns entity state but the fold.
- **hermetic**: persistence and emission are *injected* protocols, so the
  same facade drives Postgres + Kafka in production and an in-memory
  ``FakeSink`` in tests (matches the ``science._events`` injected-producer
  pattern).

The facade never mutates identity semantics — identity claims come only from
``identity.resolve`` records (I-6), hyperedge occurrences are never turned
into entity nodes (ontology), every derived number is honest (I-3).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from domain.dynamics import (
    EntityClass,
    EntityClassRegistry,
    EntityState,
    Series,
    StreamAppendRejected,
    StreamRecord,
    apply_event,
    build_series,
)
from domain.hypergraph import HyperEdge, HyperGraph


class EntityStreamStore(Protocol):
    """Append-only substrate of the atomic entity (I-5 refs, I-11/I-12)."""

    def append(self, rec: StreamRecord) -> bool:
        """Persist one life-event. Returns True if inserted, False if the
        ``record_hash`` already exists (idempotent dedup, I-11). A regression
        in (entity_id, sequence) order must raise.
        """
        ...

    def records(self, entity_id: str, tenant_id: str) -> list[StreamRecord]:
        """Replay an entity's life-stream in stream order (rebuildable, I-12)."""
        ...

    def entities(self, tenant_id: str) -> list[str]:
        """Every known entity_id (for rebuild/full projection scans)."""
        ...


class FabricSink(Protocol):
    """Emission side of the fabric — one sink per transport (Kafka, test)."""

    def emit_stream_record(self, rec: StreamRecord) -> None: ...
    def emit_state(self, state: EntityState) -> None: ...
    def emit_series(self, series: Series) -> None: ...
    def emit_hyperedge(self, edge: HyperEdge) -> None: ...
    def emit_hyperedge_temporal_version(self, edge: HyperEdge) -> None: ...
    def emit_hyperedge_expired(self, edge: HyperEdge, expired_at: Any) -> None: ...


@dataclass
class AppendResult:
    """Outcome of one append: what was written and what was derived."""

    inserted: bool
    state: EntityState | None = None
    series: Series | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "inserted": self.inserted,
            "state": self.state.to_dict() if self.state else None,
            "series": self.series.to_dict() if self.series else None,
        }


@dataclass
class EntityFabric:
    """Composition root of the atomic entity fabric.

    One instance per tenant. ``store`` is the durable append-only substrate;
    ``sink`` emits projectable events. ``registry`` classifies schema names
    explicitly (block I — unknown schemas are UNKNOWN, never silent DYNAMIC).
    """

    tenant_id: str = "default-tenant"
    store: EntityStreamStore | None = None
    sink: FabricSink | None = None
    registry: EntityClassRegistry | None = None
    _stated: dict[tuple[str, str], EntityState] = field(default_factory=dict, repr=False)
    _series: dict[tuple[str, str, str], Series] = field(default_factory=dict, repr=False)
    _hypergraph: HyperGraph = field(default_factory=HyperGraph, repr=False)

    # -- append ------------------------------------------------------------

    def append(
        self,
        rec: StreamRecord,
        *,
        schema_name: str = "",
        series_key: str = "event_count",
    ) -> AppendResult:
        """Append one life-event and derive its projections.

        Rejects foreign entities/tenants (fold discipline), enforces stream
        order. ``series_key`` selects the derived cumulative series replayed
        over the whole stream (honest — rebuildable from the store, I-12).
        """
        if rec.tenant_id != self.tenant_id:
            raise StreamAppendRejected(f"tenant mismatch (I-12): {rec.tenant_id}")
        if self.store is None:
            raise StreamAppendRejected("fabric requires a store")

        # per-entity hot state, rebuilt lazily on first sight
        key = (self.tenant_id, rec.entity_id)
        state = self._stated.get(key)
        if state is None:
            history = self.store.records(rec.entity_id, self.tenant_id)
            state = fold_history(
                rec.entity_id,
                history,
                schema_name=schema_name,
                tenant_id=self.tenant_id,
                registry=self.registry,
            )
            self._stated[key] = state

        inserted = self.store.append(rec)
        if not inserted:
            # idempotent re-delivery (I-11): record already durable — no
            # further folding, projections stay byte-identical.
            return AppendResult(inserted=False, state=state)

        apply_event(state, rec)
        if self.sink is not None:
            self.sink.emit_stream_record(rec)
            self.sink.emit_state(state)

        series = self._derive_series(rec, series_key=series_key)
        return AppendResult(inserted=True, state=state, series=series)

    def _derive_series(self, rec: StreamRecord, *, series_key: str) -> Series | None:
        history = self.store.records(rec.entity_id, self.tenant_id)
        series = build_series(
            rec.entity_id,
            history,
            series_key,
            tenant_id=self.tenant_id,
            description=f"cumulative {series_key} for {rec.entity_id}",
        )
        self._series[(self.tenant_id, rec.entity_id, series_key)] = series
        if self.sink is not None:
            self.sink.emit_series(series)
        return series

    # -- hypergraph ---------------------------------------------------------

    def record_hyperedge(
        self, edge: HyperEdge, *, event_id: str, observation_id: str = ""
    ) -> str:
        """Upsert a temporal hyperedge version (blocks G/H).

        Identical content is idempotent (same ``edge_id``); content that
        differs on versionable fields (weight/valid_until/anchor/provenance)
        is stored as a new temporal version of the same logical edge — never
        rejected as immutable. Emits ``hyperedge.created`` / version events.
        """
        provenance = {
            "event_id": event_id,
            "observation_id": observation_id or edge.observation_id,
        }
        edge_id = self._hypergraph.upsert(edge, provenance=provenance)
        if self.sink is not None:
            versions = self._hypergraph.versions(edge.logical_id)
            self.sink.emit_hyperedge(edge)
            if len(versions) > 1:
                self.sink.emit_hyperedge_temporal_version(edge)
        return edge_id

    def expire_hyperedge(self, edge: HyperEdge, expired_at: Any) -> None:
        """Close a logical edge at ``expired_at`` (terminal version event)."""
        if self.sink is not None:
            self.sink.emit_hyperedge_expired(edge, expired_at)

    def hyperedges(self, *, member: str | None = None) -> list[HyperEdge]:
        return self._hypergraph.edges(member=member, tenant_id=self.tenant_id)

    # -- inspect -----------------------------------------------------------

    def state(self, entity_id: str) -> EntityState | None:
        key = (self.tenant_id, entity_id)
        state = self._stated.get(key)
        if state is None:
            if self.store is None:
                return None
            history = self.store.records(entity_id, self.tenant_id)
            if not history:
                return None
            state = fold_history(
                entity_id,
                history,
                schema_name=history[-1].payload.get("schema_name", ""),
                tenant_id=self.tenant_id,
                registry=self.registry,
            )
            self._stated[key] = state
        return state

    def series(self, entity_id: str, key: str = "event_count") -> Series | None:
        return self._series.get((self.tenant_id, entity_id, key))

    def snapshot(self) -> dict[str, Any]:
        """Full tenant snapshot — explicit rebuild surface for projections."""
        return {
            "tenant_id": self.tenant_id,
            "states": {e: s.to_dict() for e, s in self._stated.items()},
            "hypergraph": self._hypergraph.to_dict(),
        }


def fold_history(
    entity_id: str,
    history: list[StreamRecord],
    *,
    schema_name: str = "",
    tenant_id: str = "default-tenant",
    entity_class: EntityClass | None = None,
    registry: EntityClassRegistry | None = None,
) -> EntityState:
    """Rebuild an entity's state from its durable life-stream (I-11/I-12)."""
    from domain.dynamics import fold_events

    return fold_events(
        entity_id,
        history,
        schema_name=schema_name,
        tenant_id=tenant_id,
        entity_class=entity_class,
        registry=registry,
    )


@dataclass(frozen=True)
class RecordCodec:
    """JSON codec for the ``entity.stream.appended`` envelope (refs-only)."""

    def encode(self, rec: StreamRecord) -> dict[str, Any]:
        return rec.to_dict()

    def decode(self, data: dict[str, Any]) -> StreamRecord:
        return StreamRecord.from_dict(data)

    @staticmethod
    def loads(raw: bytes) -> StreamRecord:
        return StreamRecord.from_dict(json.loads(raw.decode("utf-8")))


@dataclass
class MemoryEntityStreamStore:
    """Pure in-memory EntityStreamStore (tests + hermetic replays).

    Enforces the append-only substrate discipline: strictly increasing
    ``sequence`` per (tenant, entity), idempotent on ``record_hash`` (I-11),
    returns records in stream order (I-12 rebuildability).
    """

    _records: list[StreamRecord] = field(default_factory=list)
    _seen_hashes: set[str] = field(default_factory=set)
    _next_sequence: dict[tuple[str, str], int] = field(default_factory=dict)

    def append(self, rec: StreamRecord) -> bool:
        if rec.sequence <= 0:
            raise StreamAppendRejected(f"stream sequence must be positive, got {rec.sequence}")
        if rec.record_hash in self._seen_hashes:
            return False  # idempotent re-delivery wins over order checks (I-11)
        key = (rec.tenant_id, rec.entity_id)
        expected = self._next_sequence.get(key, 1)
        if rec.sequence < expected:
            raise StreamAppendRejected(
                f"sequence regression: {rec.sequence} after {expected - 1}"
            )
        self._seen_hashes.add(rec.record_hash)
        self._records.append(rec)
        self._next_sequence[key] = rec.sequence + 1
        return True

    def records(self, entity_id: str, tenant_id: str) -> list[StreamRecord]:
        return [
            rec
            for rec in sorted(self._records, key=lambda r: (r.sequence, r.record_hash))
            if rec.entity_id == entity_id and rec.tenant_id == tenant_id
        ]

    def entities(self, tenant_id: str) -> list[str]:
        return sorted({rec.entity_id for rec in self._records if rec.tenant_id == tenant_id})

    def __len__(self) -> int:
        return len(self._records)