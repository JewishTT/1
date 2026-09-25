"""Tenant-scoped worldline store: incremental fold of stream records (I-11/I-12).

``WorldlineStore`` is the projection-side container for
:mod:`domain.temporal_worldline`. It keeps one :class:`EntityWorldline` per
``(tenant_id, entity_id)``, rebuilds it from the records it has seen, and
answers point-in-time and cross-entity questions.

Two properties are load-bearing for callers:
- **idempotent ingest** — re-applying the same record (same ``record_hash``)
  never changes a worldline, so at-least-once delivery is safe (I-11);
- **tenant isolation** — every read and write is keyed by tenant, and a record
  from another tenant is refused rather than folded in (I-12).

Like every projection here, the store holds nothing that cannot be rebuilt from
the durable record stream: :meth:`WorldlineStore.source_records` returns the
exact input needed to reproduce it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock

from domain.dynamics import StreamRecord
from domain.temporal_worldline import (
    EntityWorldline,
    EventRelation,
    EventRelationKind,
    StateSnapshot,
    WorldlineError,
    WorldlineEvent,
    WorldlineTenantError,
    build_worldline,
    derive_cooccurrence_relations,
    event_order_key,
    overlaps_window,
)

DEFAULT_TENANT = "default-tenant"

_MIN_TS = datetime.min.replace(tzinfo=UTC)
_MAX_TS = datetime.max.replace(tzinfo=UTC)


def _fingerprint(value: object) -> str:
    material = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IngestResult:
    """Outcome of one append batch: what changed, and what did not."""

    tenant_id: str
    entity_ids: tuple[str, ...]
    new_event_ids: tuple[str, ...]
    unchanged_event_ids: tuple[str, ...]
    worldline_fingerprints: dict[str, str]
    replayed: bool = False

    @property
    def changed(self) -> bool:
        return bool(self.new_event_ids)

    def to_dict(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "entity_ids": list(self.entity_ids),
            "new_event_ids": list(self.new_event_ids),
            "unchanged_event_ids": list(self.unchanged_event_ids),
            "worldline_fingerprints": dict(self.worldline_fingerprints),
            "replayed": self.replayed,
            "changed": self.changed,
        }


class WorldlineStore:
    """In-memory, tenant-scoped store of per-entity worldlines.

    Records are retained next to the folded worldline so a rebuild is always
    possible: the store is a cache of a deterministic function, never a source
    of truth (I-12).
    """

    def __init__(self, *, require_evidence: bool = True) -> None:
        self._records: dict[tuple[str, str], dict[str, StreamRecord]] = {}
        self._worldlines: dict[tuple[str, str], EntityWorldline] = {}
        self._cooccurrence: dict[str, tuple[EventRelation, ...]] = {}
        self._require_evidence = require_evidence
        self._lock = RLock()

    # -- ingest ---------------------------------------------------------

    def append(
        self,
        records: Iterable[StreamRecord],
        *,
        tenant_id: str = DEFAULT_TENANT,
    ) -> IngestResult:
        """Fold a record batch into the worldlines of one tenant.

        Idempotent: a record already known (same ``record_hash``) is ignored, so
        a replay reports ``changed=False`` and leaves every fingerprint intact.
        """
        if not tenant_id:
            raise WorldlineError("tenant_id is required")
        batch = list(records)
        foreign = [r for r in batch if r.tenant_id != tenant_id]
        if foreign:
            raise WorldlineTenantError(
                f"{len(foreign)} record(s) do not belong to tenant {tenant_id!r} (I-12)"
            )
        with self._lock:
            touched: set[str] = set()
            replayed = False
            new_ids: list[str] = []
            unchanged: list[str] = []
            fingerprints: dict[str, str] = {}
            for record in batch:
                key = (tenant_id, record.entity_id)
                bucket = self._records.setdefault(key, {})
                if record.record_hash in bucket:
                    replayed = True
                    continue
                bucket[record.record_hash] = record
                touched.add(record.entity_id)
            for entity_id in sorted(touched):
                key = (tenant_id, entity_id)
                previous = self._worldlines.get(key)
                known = set(previous.event_ids) if previous else set()
                rebuilt = build_worldline(
                    self._records[key].values(),
                    tenant_id=tenant_id,
                    entity_id=entity_id,
                    require_evidence=self._require_evidence,
                )
                self._worldlines[key] = rebuilt
                new_ids.extend(e for e in rebuilt.event_ids if e not in known)
                unchanged.extend(e for e in rebuilt.event_ids if e in known)
                fingerprints[entity_id] = rebuilt.integrity_fingerprint
            if touched:
                self._reindex_cooccurrence(tenant_id)
            return IngestResult(
                tenant_id=tenant_id,
                entity_ids=tuple(sorted(touched)),
                new_event_ids=tuple(sorted(new_ids)),
                unchanged_event_ids=tuple(sorted(unchanged)),
                worldline_fingerprints=fingerprints,
                replayed=replayed,
            )

    def _reindex_cooccurrence(self, tenant_id: str) -> None:
        worldlines = [w for key, w in sorted(self._worldlines.items()) if key[0] == tenant_id]
        self._cooccurrence[tenant_id] = derive_cooccurrence_relations(worldlines)

    def rebuild(self, *, tenant_id: str = DEFAULT_TENANT) -> int:
        """Recompute a tenant's worldlines from the retained records.

        The rebuild is the honest proof that the store is derived (I-12): it
        returns how many worldlines ended up with a different fingerprint.
        """
        with self._lock:
            changed = 0
            for key in sorted(self._worldlines):
                if key[0] != tenant_id:
                    continue
                before = self._worldlines[key].integrity_fingerprint
                rebuilt = build_worldline(
                    self._records[key].values(),
                    tenant_id=tenant_id,
                    entity_id=key[1],
                    require_evidence=self._require_evidence,
                )
                self._worldlines[key] = rebuilt
                if rebuilt.integrity_fingerprint != before:
                    changed += 1
            self._reindex_cooccurrence(tenant_id)
            return changed

    # -- reads ----------------------------------------------------------

    def get(self, *, tenant_id: str, entity_id: str) -> EntityWorldline | None:
        """Worldline of one entity, or ``None`` if nothing is known for it."""
        return self._worldlines.get((tenant_id, entity_id))

    def require(self, *, tenant_id: str, entity_id: str) -> EntityWorldline:
        worldline = self.get(tenant_id=tenant_id, entity_id=entity_id)
        if worldline is None:
            raise WorldlineError(f"no worldline for {tenant_id}/{entity_id}")
        return worldline

    def entities(self, *, tenant_id: str = DEFAULT_TENANT) -> tuple[str, ...]:
        """Entity ids known for a tenant, deterministically ordered."""
        return tuple(sorted(key[1] for key in self._worldlines if key[0] == tenant_id))

    def tenants(self) -> tuple[str, ...]:
        """Tenants with at least one worldline."""
        return tuple(sorted({key[0] for key in self._worldlines}))

    def source_records(
        self, *, tenant_id: str = DEFAULT_TENANT, entity_id: str | None = None
    ) -> tuple[StreamRecord, ...]:
        """The exact records behind a worldline — enough to rebuild it (I-12)."""
        rows: list[StreamRecord] = []
        for key in sorted(self._records):
            if key[0] != tenant_id or (entity_id is not None and key[1] != entity_id):
                continue
            rows.extend(self._records[key][h] for h in sorted(self._records[key]))
        return tuple(rows)

    def events(
        self,
        *,
        tenant_id: str = DEFAULT_TENANT,
        entity_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[WorldlineEvent, ...]:
        """Events of a tenant (optionally one entity, one window), in worldline order."""
        found: list[WorldlineEvent] = []
        for key in sorted(self._worldlines):
            if key[0] != tenant_id or (entity_id is not None and key[1] != entity_id):
                continue
            found.extend(self._worldlines[key].events)
        if start is not None or end is not None:
            low, high = start or _MIN_TS, end or _MAX_TS
            if high < low:
                raise WorldlineError("query window ends before it starts")
            found = [event for event in found if overlaps_window(event.interval, low, high)]
        return tuple(sorted(found, key=event_order_key))

    def event_index(self, *, tenant_id: str = DEFAULT_TENANT) -> dict[str, WorldlineEvent]:
        """Every event of a tenant by id, for relation lookups across entities."""
        index: dict[str, WorldlineEvent] = {}
        for key in sorted(self._worldlines):
            if key[0] == tenant_id:
                for event in self._worldlines[key].events:
                    index[event.event_id] = event
        return index

    def relations(
        self,
        *,
        tenant_id: str = DEFAULT_TENANT,
        event_id: str | None = None,
        kind: EventRelationKind | None = None,
    ) -> tuple[EventRelation, ...]:
        """In-worldline plus cross-worldline relations of a tenant, in order."""
        rows: list[EventRelation] = []
        for key in sorted(self._worldlines):
            if key[0] == tenant_id:
                rows.extend(self._worldlines[key].relations)
        rows.extend(self._cooccurrence.get(tenant_id, ()))
        positions = {event.event_id: i for i, event in enumerate(self.events(tenant_id=tenant_id))}
        selected = [
            r
            for r in rows
            if (event_id is None or r.source_event_id == event_id or r.target_event_id == event_id)
            and (kind is None or r.kind is kind)
        ]
        return tuple(
            sorted(
                selected,
                key=lambda r: (
                    positions.get(r.source_event_id, 0),
                    positions.get(r.target_event_id, 0),
                    r.kind.value,
                    r.relation_id,
                ),
            )
        )

    def relations_between(
        self, *, tenant_id: str, entity_a: str, entity_b: str
    ) -> tuple[EventRelation, ...]:
        """Relations whose two events belong to two different entities."""
        wanted = {(entity_a, entity_b), (entity_b, entity_a)}
        return tuple(
            r
            for r in self.relations(tenant_id=tenant_id, kind=EventRelationKind.CO_OCCURS)
            if (r.source_entity_id, r.target_entity_id) in wanted
        )

    def state_at(self, *, tenant_id: str, entity_id: str, at: datetime) -> StateSnapshot | None:
        """Entity state at an instant (``None`` when unknown, never fabricated)."""
        worldline = self.get(tenant_id=tenant_id, entity_id=entity_id)
        return worldline.state_at(at) if worldline else None

    def events_at(
        self, *, tenant_id: str, entity_id: str, at: datetime
    ) -> tuple[WorldlineEvent, ...]:
        """Events whose occurrence window contains ``at``."""
        worldline = self.get(tenant_id=tenant_id, entity_id=entity_id)
        if worldline is None:
            return ()
        found = [event for event in worldline.events if event.interval.contains(at)]
        return tuple(sorted(found, key=event_order_key))

    # -- integrity ------------------------------------------------------

    def fingerprint(self, *, tenant_id: str = DEFAULT_TENANT) -> str:
        """Store-wide fingerprint: two equal stores produce the same digest."""
        payload = {
            entity_id: self._worldlines[(tenant_id, entity_id)].integrity_fingerprint
            for entity_id in self.entities(tenant_id=tenant_id)
        }
        return "WLS-" + _fingerprint(payload)[:32]

    def to_dict(self, *, tenant_id: str = DEFAULT_TENANT) -> dict[str, object]:
        return {
            "tenant_id": tenant_id,
            "entities": list(self.entities(tenant_id=tenant_id)),
            "worldlines": {
                entity_id: self._worldlines[(tenant_id, entity_id)].to_dict()
                for entity_id in self.entities(tenant_id=tenant_id)
            },
            "fingerprint": self.fingerprint(tenant_id=tenant_id),
        }

    def __len__(self) -> int:
        return len(self._worldlines)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"WorldlineStore(tenants={list(self.tenants())}, entities={len(self)})"


__all__ = ["DEFAULT_TENANT", "IngestResult", "WorldlineStore"]
