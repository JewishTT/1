"""Process-centric entity dynamics (feature 009).

The atomic entity is not a record but a *stream identity*: the persistent,
append-only ``entity.stream.appended`` flow keyed by ``entity_id`` is the
substrate; "state" is always a deterministic, rebuildable fold over that flow
(I-11/I-12 — projections are derived, never authoritative). This module owns
the fold and the derived dynamics: a rebuildable univariate time series per
(property, metric), and honest bounded statistics over it (never assertion of
truth — I-3 semantics apply to every derived number).

Ontology test for atomic identity (process/event-centric philosophy):
- *dynamic continuant* (person, org, account): persists AND acts — full
  stream/dynamics/hypergraph mode;
- *artifact continuant* (document, image, observation): persists, does not
  act — identity + provenance anchor of hyperedges, no own dynamics (its
  state is fixed once, immutably — I-1);
- *occurrence* (transaction, meeting, publication): does not persist as an
  entity at all — it IS a hyperedge over participant entities.

Design contract:
- stdlib-only, dataclass-based, matches the domain package conventions;
- every derived artifact carries provenance and tenant isolation;
- replaying the same events in the same order yields the identical state
  (deterministic fold, tested).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

# --------------------------------------------------------------------------
# Ontology classes (how to "separate" entities)
# --------------------------------------------------------------------------


class EntityClass(StrEnum):
    """Atomic identity classes — the process-centric separation answer.

    - DYNAMIC_CONTINUANT: persists and acts (person, org, account, domain).
      Full mode: stream identity + state fold + time series + hyperedges.
    - ARTIFACT_CONTINUANT: persists, does not act (document, evidence
      bundle). Identity + provenance anchor for hyperedges; no own dynamics
      beyond observation/mention counts, which belong to *relations*, not to
      the artifact itself.
    - OCCURRENCE: does not persist as an entity — it is a hyperedge over
      participants (transaction, meeting, transfer). Materialized as
      HyperEdge, never as an Entity node.
    - UNKNOWN: schema not registered — we do NOT silently guess a class;
      unknown schemas stay UNKNOWN until someone registers them explicitly.
    """

    DYNAMIC_CONTINUANT = "dynamic_continuant"
    ARTIFACT_CONTINUANT = "artifact_continuant"
    OCCURRENCE = "occurrence"
    UNKNOWN = "unknown"


class EntityClassRegistry:
    """Explicitly extensible schema -> class mapping (block I).

    Unlike the old hardcoded dict, classification is an *assertion* that
    lives in one place, not a silent default scattered across the fold. The
    registries passed to ``fold_events`` override this global registry.
    """

    def __init__(self, mappings: dict[str, EntityClass] | None = None) -> None:
        self._mappings: dict[str, EntityClass] = {}
        for name, cls in (mappings or {}).items():
            if not isinstance(cls, EntityClass):
                raise StreamAppendRejected(f"invalid entity class for {name}: {cls!r}")
            self._mappings[str(name)] = cls

    def register(self, schema_name: str, cls: EntityClass) -> EntityClass:
        """Register (or override) a schema -> class binding."""
        if not schema_name:
            raise StreamAppendRejected("schema_name is required")
        if not isinstance(cls, EntityClass):
            raise StreamAppendRejected(f"invalid entity class for {schema_name}: {cls!r}")
        self._mappings[str(schema_name)] = cls
        return cls

    def classify(self, schema_name: str) -> EntityClass:
        return self._mappings.get(schema_name, EntityClass.UNKNOWN)

    def to_dict(self) -> dict[str, str]:
        return {name: cls.value for name, cls in sorted(self._mappings.items())}


#: Built-in registry — the schema names we actually know about. Everything
#: else classifies UNKNOWN (never silently DYNAMIC).
DEFAULT_ENTITY_REGISTRY = EntityClassRegistry(
    {
        "Person": EntityClass.DYNAMIC_CONTINUANT,
        "LegalEntity": EntityClass.DYNAMIC_CONTINUANT,
        "Organization": EntityClass.DYNAMIC_CONTINUANT,
        "Company": EntityClass.DYNAMIC_CONTINUANT,
        "UserAccount": EntityClass.DYNAMIC_CONTINUANT,
        "Document": EntityClass.ARTIFACT_CONTINUANT,
        "Email": EntityClass.ARTIFACT_CONTINUANT,
        "Event": EntityClass.OCCURRENCE,
        "Membership": EntityClass.OCCURRENCE,
        "Ownership": EntityClass.OCCURRENCE,
        "Employment": EntityClass.OCCURRENCE,
        "Location": EntityClass.DYNAMIC_CONTINUANT,
        "Address": EntityClass.DYNAMIC_CONTINUANT,
        "Phone": EntityClass.DYNAMIC_CONTINUANT,
        "CryptoAddress": EntityClass.DYNAMIC_CONTINUANT,
        "Asset": EntityClass.DYNAMIC_CONTINUANT,
        "Vehicle": EntityClass.DYNAMIC_CONTINUANT,
    }
)


def classify_entity(
    schema_name: str,
    registry: EntityClassRegistry | None = None,
) -> EntityClass:
    """Ontological test: dynamic continuant / artifact / occurrence / unknown.

    Unknown/unregistered schemas return UNKNOWN — a caller that has no
    registry entry cannot pretend to know the class. The registry is explicit
    (add a binding, don't rely on a broad silent default).
    """
    if not schema_name:
        return EntityClass.UNKNOWN
    return (registry or DEFAULT_ENTITY_REGISTRY).classify(schema_name)


# --------------------------------------------------------------------------
# Stream record — the atomic event of an entity's life
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class StreamRecord:
    """One atomic fact appended to an entity's life-stream.

    Carries per-tenant provenance (I-12) and temporal validity. Payload is a
    plain JSON-serializable dict (I-5: refs/fields only — never blobs; raw
    evidence stays in object storage and is referenced by ``observation_id``
    when present). ``record_hash`` is deterministic, so replaying the stream
    rebuilds byte-identical hashes (provenance chain check).
    """

    entity_id: str
    kind: str
    ts: datetime
    tenant_id: str = "default-tenant"
    payload: dict[str, Any] = field(default_factory=dict)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    observation_id: str = ""
    dataset_id: str = ""
    extraction_version: str = ""
    sequence: int = 0
    record_hash: str = ""
    record_id: str = ""

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise StreamAppendRejected("stream record requires entity_id")
        if not self.kind:
            raise StreamAppendRejected("stream record requires kind")
        if not self.tenant_id:
            raise StreamAppendRejected("stream record requires tenant_id (I-12)")
        if self.ts.tzinfo is None:
            raise StreamAppendRejected("stream record ts must be timezone-aware (I-12)")
        object.__setattr__(self, "record_hash", self.record_hash or self.compute_hash())
        object.__setattr__(self, "record_id", self.record_id or f"stream-{self.record_hash}")

    def compute_hash(self) -> str:
        """Deterministic sha256 over the immutable content of this record."""
        material = json.dumps(
            {
                "entity_id": self.entity_id,
                "kind": self.kind,
                "ts": self.ts.isoformat(),
                "tenant_id": self.tenant_id,
                "payload": _canonical(self.payload),
                "valid_from": self.valid_from.isoformat() if self.valid_from else None,
                "valid_until": self.valid_until.isoformat() if self.valid_until else None,
                "observation_id": self.observation_id,
                "dataset_id": self.dataset_id,
                "extraction_version": self.extraction_version,
                "sequence": self.sequence,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "kind": self.kind,
            "ts": self.ts.isoformat(),
            "tenant_id": self.tenant_id,
            "payload": _canonical(self.payload),
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "observation_id": self.observation_id,
            "dataset_id": self.dataset_id,
            "extraction_version": self.extraction_version,
            "sequence": self.sequence,
            "record_hash": self.record_hash,
            "record_id": self.record_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StreamRecord:
        """Rebuild from ``to_dict`` output — hash-stable round-trip (replay)."""
        return cls(
            entity_id=data["entity_id"],
            kind=data["kind"],
            ts=datetime.fromisoformat(data["ts"]),
            tenant_id=data.get("tenant_id", "default-tenant"),
            payload=data.get("payload") or {},
            valid_from=(
                datetime.fromisoformat(data["valid_from"]) if data.get("valid_from") else None
            ),
            valid_until=(
                datetime.fromisoformat(data["valid_until"]) if data.get("valid_until") else None
            ),
            observation_id=data.get("observation_id", ""),
            dataset_id=data.get("dataset_id", ""),
            extraction_version=data.get("extraction_version", ""),
            sequence=data.get("sequence", 0),
            record_hash=data.get("record_hash", ""),
            record_id=data.get("record_id", ""),
        )


class StreamAppendRejected(ValueError):
    """Raised when an event violates the append-only stream contract."""


@dataclass(frozen=True)
class SeriesStats:
    """Honest, bounded statistics over a derived series (no truth claims).

    Empty series report ``None`` everywhere — the absence of data is never
    fabricated into zeros (honesty discipline, I-3 semantics for numbers).
    """

    n: int = 0
    mean: float | None = None
    variance: float | None = None
    min: float | None = None
    max: float | None = None

    @staticmethod
    def from_values(values: list[float]) -> SeriesStats:
        if not values:
            return SeriesStats()
        n = len(values)
        mean = sum(values) / n
        if n > 1:
            variance = sum((v - mean) ** 2 for v in values) / (n - 1)
        else:
            variance = 0.0
        return SeriesStats(n=n, mean=mean, variance=variance, min=min(values), max=max(values))

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "mean": self.mean,
            "variance": self.variance,
            "min": self.min,
            "max": self.max,
        }


def _canonical(obj: Any) -> Any:
    """JSON-canonical normalization so hashes are replay-stable."""
    if isinstance(obj, dict):
        return {str(k): _canonical(v) for k, v in sorted(obj.items())}
    if isinstance(obj, (list, tuple)):
        return [_canonical(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    return str(obj)


# --------------------------------------------------------------------------
# The fold: state = deterministic, rebuildable function of the stream
# --------------------------------------------------------------------------

_MUTATING_KINDS = frozenset(
    {"property.set", "property.observe", "property.frozen", "property.expire"}
)
_COUNT_ONLY_KINDS = frozenset({"fact", "mention", "observed_at", "relation.observed"})


@dataclass(frozen=True)
class Valuation:
    """One asserted value of a property — the per-value temporal spine.

    Every assertion carries its *own* validity window, last-seen and
    provenance. This is what makes the fold answer temporal questions
    ("which alias was effective at time t?") instead of remembering only a
    flat list of strings with a single global last-seen.
    """

    value: str
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    last_seen: datetime | None = None
    confidence: float | None = None
    provenance: dict[str, Any] = field(default_factory=dict)

    def active_at(self, ts: datetime) -> bool:
        start_ok = self.valid_from is None or self.valid_from <= ts
        end_ok = self.valid_until is None or ts < self.valid_until
        return start_ok and end_ok

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "confidence": self.confidence,
            "provenance": self.provenance,
        }


class StreamProperty:
    """A temporal, extensible property-slot inside an entity's folded state.

    - ``valuations``: the authoritative per-value spine — each assertion is
      one ``Valuation`` with its own validity window and provenance.
      ``values`` is a derived convenience over it (all asserted values).
    - ``valid_from / valid_until``: slot-level temporal validity (FtM
      statement pattern).
    - ``active``: whether currently within validity window.
    - ``frozen``: immutable from the moment of freezing (artifact discipline).
    """

    __slots__ = (
        "name",
        "value",
        "original_value",
        "valuations",
        "last_set",
        "last_seen",
        "valid_from",
        "valid_until",
        "active",
        "extensible",
        "frozen",
        "confidence",
        "revision",
    )

    def __init__(
        self,
        name: str,
        value: str = "",
        original_value: str = "",
        valuations: list[Valuation] | None = None,
        last_set: datetime | None = None,
        last_seen: datetime | None = None,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
        active: bool = True,
        extensible: bool = True,
        frozen: bool = False,
        confidence: float | None = None,
        revision: int = 1,
    ) -> None:
        self.name = name
        self.value = value
        self.original_value = original_value or value
        if valuations is None:
            valuations = (
                [
                    Valuation(
                        value=value,
                        valid_from=valid_from,
                        valid_until=valid_until,
                        last_seen=last_seen or last_set,
                        confidence=confidence,
                    )
                ]
                if value
                else []
            )
        self.valuations = valuations
        self.last_set = last_set
        self.last_seen = last_seen or last_set
        self.valid_from = valid_from
        self.valid_until = valid_until
        self.active = active
        self.extensible = extensible
        self.frozen = frozen
        self.confidence = confidence
        self.revision = revision

    @property
    def values(self) -> list[str]:
        """All values ever asserted (derived from the valuation spine)."""
        return [v.value for v in self.valuations]

    def value_at(self, ts: datetime) -> str | None:
        """Most recent value whose validity window contains ``ts``."""
        for v in reversed(self.valuations):
            if v.active_at(ts):
                return v.value
        return None

    def valuations_at(self, ts: datetime) -> list[Valuation]:
        """Every valuation active at ``ts`` (aliases can be concurrent)."""
        return [v for v in self.valuations if v.active_at(ts)]

    def as_history(self, superseded_at: datetime | None = None) -> StreamProperty:
        """Detach this slot as a historical (inactive) record.

        ``valid_until`` is the *supersede time* — when the replacing fact
        arrived — never ``last_seen``: when a value stopped being true is an
        assertion, when we last observed it is an observation. Conflating the
        two would fabricate expiry (I-3 honesty).
        """
        until = (
            superseded_at
            if superseded_at is not None
            else (self.valid_until or self.last_seen)
        )
        return StreamProperty(
            name=self.name,
            value=self.value,
            original_value=self.original_value,
            valuations=list(self.valuations),
            last_set=self.last_set,
            last_seen=self.last_seen,
            valid_from=self.valid_from,
            valid_until=until,
            active=False,
            extensible=False,
            frozen=self.frozen,
            confidence=self.confidence,
            revision=self.revision,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "original_value": self.original_value,
            "values": self.values,
            "valuations": [v.to_dict() for v in self.valuations],
            "last_set": self.last_set.isoformat() if self.last_set else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "active": self.active,
            "extensible": self.extensible,
            "frozen": self.frozen,
            "confidence": self.confidence,
            "revision": self.revision,
        }


@dataclass
class EntityState:
    """Rebuildable fold of an entity's life-stream.

    State as derived view: ALWAYS rebuildable by replaying the ordered
    stream (I-11/I-12). Identity fields are written exclusively by
    ``identity.resolve`` records (I-6); structural/TDA layers may read this
    state but never mutate identity semantics.
    """

    entity_id: str
    schema_name: str = ""
    tenant_id: str = "default-tenant"
    entity_class: EntityClass = EntityClass.DYNAMIC_CONTINUANT

    first_event_ts: datetime | None = None
    last_event_ts: datetime | None = None
    event_count: int = 0
    event_counts: dict[str, int] = field(default_factory=dict)
    event_hashes: list[str] = field(default_factory=list)

    props: dict[str, StreamProperty] = field(default_factory=dict)
    frozen_props: set[str] = field(default_factory=set)
    history: dict[str, list[StreamProperty]] = field(default_factory=dict)

    # resolution identity (I-6: only source of identity claims)
    resolution: dict[str, Any] = field(default_factory=dict)
    resolution_history: list[dict[str, Any]] = field(default_factory=list)

    # artifact freeze (I-1 discipline)
    frozen: bool = False
    frozen_at: datetime | None = None

    mention_count: int = 0
    observation_ids: set[str] = field(default_factory=set)
    dataset_ids: set[str] = field(default_factory=set)
    revision: int = 0
    last_sequence: int = -1  # stream-order enforcement (strictly increasing)

    @property
    def head_hash(self) -> str:
        """Deterministic hash of the folded state (provenance chain tip)."""
        if not self.event_hashes:
            return ""
        digest = hashlib.sha256()
        for h in self.event_hashes:
            digest.update(h.encode("utf-8"))
        return digest.hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "schema_name": self.schema_name,
            "tenant_id": self.tenant_id,
            "entity_class": self.entity_class.value,
            "first_event_ts": self.first_event_ts.isoformat() if self.first_event_ts else None,
            "last_event_ts": self.last_event_ts.isoformat() if self.last_event_ts else None,
            "event_count": self.event_count,
            "event_counts": dict(sorted(self.event_counts.items())),
            "event_hashes": list(self.event_hashes),
            "props": {name: slot.to_dict() for name, slot in self.props.items()},
            "frozen_props": sorted(self.frozen_props),
            "history": {name: [h.to_dict() for h in slots] for name, slots in self.history.items()},
            "resolution": dict(self.resolution),
            "resolution_history": [dict(h) for h in self.resolution_history],
            "frozen": self.frozen,
            "frozen_at": self.frozen_at.isoformat() if self.frozen_at else None,
            "mention_count": self.mention_count,
            "observation_ids": sorted(self.observation_ids),
            "dataset_ids": sorted(self.dataset_ids),
            "revision": self.revision,
            "last_sequence": self.last_sequence,
            "head_hash": self.head_hash,
        }


def fold_events(
    entity_id: str,
    events: list[StreamRecord],
    *,
    schema_name: str = "",
    tenant_id: str = "default-tenant",
    entity_class: EntityClass | None = None,
    registry: EntityClassRegistry | None = None,
) -> EntityState:
    """Deterministically fold an ordered stream into EntityState.

    Replay with the same ordered events yields a byte-identical state —
    the rebuildability guarantee (I-11/I-12). Every record's hash is
    verified during the fold (provenance chain check).
    """
    cls = entity_class or (
        classify_entity(schema_name, registry=registry)
        if schema_name
        else EntityClass.DYNAMIC_CONTINUANT
    )
    state = EntityState(
        entity_id=entity_id, schema_name=schema_name, tenant_id=tenant_id, entity_class=cls
    )
    # Fold in ARRIVAL order — the stream is append-only, so sequence numbers
    # must strictly increase exactly as they arrive; sorting would silently
    # "repair" a corrupted order (a regression must be detected, not fixed).
    # Monotonicity is enforced inside ``_apply_event`` so the batch fold and
    # the single-step hot path behave identically.
    for rec in events:
        if rec.entity_id != entity_id:
            raise StreamAppendRejected(f"foreign record: {rec.entity_id} != {entity_id}")
        if rec.tenant_id != tenant_id:
            raise StreamAppendRejected(f"tenant mismatch (I-12): {rec.tenant_id} != {tenant_id}")
        if rec.record_hash and rec.record_hash != rec.compute_hash():
            raise StreamAppendRejected(
                f"hash mismatch at sequence {rec.sequence}: stream corrupted"
            )
        if state.first_event_ts is None or rec.ts < state.first_event_ts:
            state.first_event_ts = rec.ts
        _apply_event(state, rec)
    return state


def apply_event(state: EntityState, rec: StreamRecord) -> None:
    """Single-step fold (hot path for streaming consumers)."""
    if rec.entity_id != state.entity_id:
        raise StreamAppendRejected(f"foreign record: {rec.entity_id} != {state.entity_id}")
    if rec.tenant_id != state.tenant_id:
        raise StreamAppendRejected(f"tenant mismatch (I-12): {rec.tenant_id} != {state.tenant_id}")
    if rec.record_hash and rec.record_hash != rec.compute_hash():
        raise StreamAppendRejected(f"hash mismatch at sequence {rec.sequence}: stream corrupted")
    if state.first_event_ts is None or rec.ts < state.first_event_ts:
        state.first_event_ts = rec.ts
    _apply_event(state, rec)


def _push_history(state: EntityState, prop: str, slot: StreamProperty) -> None:
    """Archive a demoted property slot (I-1: superseded values are preserved)."""
    state.history.setdefault(prop, []).append(slot)


def _apply_event(state: EntityState, rec: StreamRecord) -> None:
    """Apply one stream record to state — the whole "how" of the fold.

    Mutation policy per record kind:
    - ``entity.freeze``: artifact discipline — the entity is closed to every
      kind of mutation (properties, resolution, counters) thereafter (I-1).
    - ``fact`` / ``mention`` / ``observed_at`` / ``relation.observed``:
      monotone counters (never decrease).
    - ``property.set``: extensible properties accumulate *valuations* (each
      with its own validity window and provenance); a record carrying
      ``extensible: false`` pins the slot to a single value and archives the
      accumulated variants as history (I-1 discipline).
    - ``property.expire``: the slot is closed (archived) — it leaves the
      active set; a later ``property.set`` starts a fresh slot.
    - ``identity.resolve``: sets resolution identity (I-6 — the ONLY source);
      each change is preserved in ``resolution_history``, never overwritten
      silently.
    """
    state.event_count += 1
    state.last_event_ts = rec.ts
    if rec.sequence <= state.last_sequence:
        raise StreamAppendRejected(
            f"sequence regression: {rec.sequence} after {state.last_sequence}"
        )
    state.last_sequence = rec.sequence
    if rec.observation_id:
        state.observation_ids.add(rec.observation_id)
    if rec.dataset_id:
        state.dataset_ids.add(rec.dataset_id)
    state.event_counts[rec.kind] = state.event_counts.get(rec.kind, 0) + 1
    state.event_hashes.append(rec.record_hash)

    if rec.kind == "entity.freeze":
        if state.frozen:
            raise StreamAppendRejected("entity.freeze applied twice")
        state.frozen = True
        state.frozen_at = rec.ts
        return

    # Frozen entities reject EVERY kind — including counters and resolution,
    # not only property mutations. "No further mutations ever" is literal.
    if state.frozen:
        raise StreamAppendRejected("entity frozen (I-1): no further mutations ever")

    if rec.kind == "identity.resolve":
        resolved = rec.payload.get("resolved_id")
        if not resolved:
            raise StreamAppendRejected("identity.resolve requires resolved_id")
        claim = {
            "resolved_id": resolved,
            "resolved_at": rec.ts.isoformat(),
            "method": rec.payload.get("method", ""),
            "record_hash": rec.record_hash,
        }
        if state.resolution:
            state.resolution_history.append(dict(state.resolution))
        state.resolution = claim
        return

    if rec.kind in _COUNT_ONLY_KINDS:
        if rec.kind == "mention":
            state.mention_count += 1
        return

    if rec.kind not in _MUTATING_KINDS:
        raise StreamAppendRejected(f"unknown stream record kind: {rec.kind}")

    now = rec.ts
    vf, vu = rec.valid_from, rec.valid_until
    if vf is not None and vf > now:
        raise StreamAppendRejected("valid_from in the future of event ts")
    if vf is not None and vu is not None and vu < vf:
        raise StreamAppendRejected("valid_until < valid_from")
    active = (vf is None or vf <= now) and (vu is None or vu > now)

    if rec.kind == "property.expire":
        prop = rec.payload.get("property")
        if not prop:
            raise StreamAppendRejected("property.expire requires property name")
        current = state.props.pop(prop, None)
        if current is not None:
            # close the CURRENT slot using the record's explicit validity end
            # (rec.valid_until if given), otherwise the event ts — but never
            # last_seen (that would conflate observation with expiry, I-3).
            current.valid_until = vu or now
            current.active = False
            _push_history(state, prop, current)
        return

    prop = rec.payload.get("property")
    value = rec.payload.get("value")
    if not prop:
        raise StreamAppendRejected(f"{rec.kind} requires property name")
    if value is None or not str(value).strip():
        raise StreamAppendRejected(f"{rec.kind} requires non-empty value")

    new_valuation = Valuation(
        value=str(value),
        valid_from=vf or now,
        valid_until=vu,
        last_seen=now,
        confidence=(
            float(rec.payload["confidence"])
            if rec.payload.get("confidence") is not None
            else None
        ),
        provenance={
            "record_hash": rec.record_hash,
            "observation_id": rec.observation_id,
            "dataset_id": rec.dataset_id,
            "extraction_version": rec.extraction_version,
        },
    )

    def _fresh_slot() -> StreamProperty:
        return StreamProperty(
            name=prop,
            value=str(value),
            original_value=rec.payload.get("original_value", str(value)),
            valuations=[new_valuation],
            last_set=now,
            valid_from=vf or now,
            valid_until=vu,
            active=active,
            extensible=False,
        )

    if prop in state.frozen_props:
        raise StreamAppendRejected(f"property {prop} is frozen (I-1); use history")

    if rec.kind == "property.frozen":
        state.frozen_props.add(prop)
        current = state.props.get(prop)
        if current is not None:
            current.frozen = True
            current.extensible = False
        return

    current = state.props.get(prop)
    incoming_extensible = bool(rec.payload.get("extensible", True))

    if current is None:
        state.props[prop] = StreamProperty(
            name=prop,
            value=str(value),
            original_value=rec.payload.get("original_value", str(value)),
            valuations=[new_valuation],
            last_set=now,
            valid_from=vf or now,
            valid_until=vu,
            active=active,
            extensible=incoming_extensible,
        )
        state.revision += 1
        return

    if not incoming_extensible:
        # asserted fixed (I-1): prior variants become history, this is the
        # single authoritative value; a later extensible record may never
        # revive accumulation on a pinned slot.
        _push_history(state, prop, current.as_history(superseded_at=now))
        state.props[prop] = _fresh_slot()
        state.revision += 1
        return

    if not current.extensible:
        if current.value == str(value) and active:
            # identical re-assertion: idempotent (I-11), refresh last_seen
            current.last_seen = now
            return
        _push_history(state, prop, current.as_history(superseded_at=now))
        state.props[prop] = _fresh_slot()
        state.revision += 1
        return

    # extensible slot + extensible record: same value -> idempotent refresh;
    # new value -> append a NEW valuation (own window + provenance), the old
    # valuation stays in the spine (per-value temporal validity).
    if str(value) not in current.values:
        current.valuations.append(new_valuation)
        current.revision += 1
        state.revision += 1
    current.last_seen = now
    new_conf = rec.payload.get("confidence")
    if new_conf is not None:
        current.confidence = max(current.confidence or 0.0, float(new_conf))


# --------------------------------------------------------------------------
# Derived dynamics: time series over an entity's stream
# --------------------------------------------------------------------------


@dataclass
class Series:
    """Deterministic derived time series from an entity's life-stream.

    The temporal-dynamics layer of the atomic entity: derived, rebuildable,
    honest (empty series yield no fabricated points). ``series_hash`` makes
    the series content-addressable, so every consumer (TDA, analytics,
    science) can verify what exactly was analyzed.
    """

    entity_id: str
    key: str
    description: str = ""
    points: list[tuple[datetime, float]] = field(default_factory=list)
    tenant_id: str = "default-tenant"
    window: timedelta | None = None

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise StreamAppendRejected("series requires entity_id")
        if not self.key:
            raise StreamAppendRejected("series requires key")
        if not self.tenant_id:
            raise StreamAppendRejected("series requires tenant_id (I-12)")
        # Stable sort by timestamp: same-ts points keep their arrival order.
        # Duplicate timestamps are NOT an error — a batch observation can
        # legitimately timestamp many records identically; refusing them would
        # fabricate a "corrupt stream" where none exists (honesty, I-3).
        self.points = sorted(self.points, key=lambda p: p[0])

    # -- accessors ---------------------------------------------------------

    def values(self) -> list[float]:
        return [v for _, v in self.points]

    def stamps(self) -> list[datetime]:
        return [ts for ts, _ in self.points]

    def __len__(self) -> int:
        return len(self.points)

    def is_empty(self) -> bool:
        return not self.points

    # -- metrics -----------------------------------------------------------

    def stats(self) -> SeriesStats:
        return SeriesStats.from_values(self.values())

    def moving_average(self, window_size: int) -> list[tuple[datetime, float]]:
        """Simple moving average over ``window_size`` trailing points."""
        if window_size <= 0:
            raise StreamAppendRejected("window_size must be positive")
        if len(self.points) < window_size:
            return []
        out: list[tuple[datetime, float]] = []
        vals = self.values()
        for i in range(window_size - 1, len(self.points)):
            chunk = vals[i - window_size + 1 : i + 1]
            out.append((self.points[i][0], sum(chunk) / window_size))
        return out

    def velocity(self, per: timedelta = timedelta(days=1)) -> list[tuple[datetime, float]]:
        """Rate of change rescaled to ``per`` interval (honest: no padding)."""
        if len(self.points) < 2:
            return []
        out: list[tuple[datetime, float]] = []
        for (t0, v0), (t1, v1) in zip(self.points, self.points[1:], strict=False):
            dt = (t1 - t0).total_seconds()
            if dt <= 0:
                continue
            out.append((t1, (v1 - v0) / dt * per.total_seconds()))
        return out

    def deltas(self) -> list[tuple[datetime, float]]:
        """First differences of the series."""
        if len(self.points) < 2:
            return []
        return [
            (t1, v1 - v0) for (_, v0), (t1, v1) in zip(self.points, self.points[1:], strict=False)
        ]

    @property
    def series_hash(self) -> str:
        payload = [[ts.isoformat(), _canonical_num(v)] for ts, v in self.points]
        material = json.dumps(
            {
                "entity_id": self.entity_id,
                "key": self.key,
                "tenant_id": self.tenant_id,
                "description": self.description,
                "points": payload,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "key": self.key,
            "description": self.description,
            "tenant_id": self.tenant_id,
            "points": [[ts.isoformat(), _canonical_num(v)] for ts, v in self.points],
            "window_s": self.window.total_seconds() if self.window else None,
            "series_hash": self.series_hash,
        }


def _canonical_num(v: float) -> float | str:
    """NaN/inf are not JSON-canonical — encode them explicitly (honesty)."""
    if math.isnan(v):
        return "nan"
    if math.isinf(v):
        return "inf" if v > 0 else "-inf"
    return v


def build_series(
    entity_id: str,
    events: list[StreamRecord],
    key: str = "event_count",
    *,
    metric: str = "cumulative",
    tenant_id: str = "default-tenant",
    description: str = "",
    window: timedelta | None = None,
) -> Series:
    """Build a derived series over an entity's stream.

    Metrics:
    - ``cumulative`` — running count of records of kind ``key`` (all kinds
      when ``key == "event_count"``).
    - ``inter_arrival`` — seconds between consecutive records of ``key``
      (honest gaps; no interpolation, no fabricated points).
    """
    if metric not in {"cumulative", "inter_arrival"}:
        raise StreamAppendRejected(f"unknown series metric: {metric}")
    relevant = [r for r in events if r.entity_id == entity_id]
    if key != "event_count":
        relevant = [r for r in relevant if r.kind == key]
    # arrival order preserved (append-only discipline, same as fold_events)
    points: list[tuple[datetime, float]] = []
    if metric == "cumulative":
        running = 0
        for rec in relevant:
            running += 1
            points.append((rec.ts, float(running)))
    else:
        for a, b in zip(relevant, relevant[1:], strict=False):
            points.append((b.ts, (b.ts - a.ts).total_seconds()))
    return Series(
        entity_id=entity_id,
        key=key,
        description=description or f"{metric} {key}",
        points=points,
        tenant_id=tenant_id,
        window=window,
    )
