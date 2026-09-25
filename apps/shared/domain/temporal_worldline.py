"""Temporal worldline extraction over entity life-streams (I-5/I-11/I-12).

A *worldline* is the evidence-backed trajectory of one entity: the ordered
occurrences (:class:`WorldlineEvent`) reconstructed from that entity's
append-only stream records, the participants acting in each occurrence, the
state of the entity immediately before and after it, and the typed relations
(:class:`EventRelation`) between occurrences.

Design contract (platform invariants):
- **I-5** refs only: derived artifacts carry record/observation/dataset
  references, never raw text or blobs;
- **I-11** deterministic + idempotent: ids are content-addressed, so replaying
  a stream in any order yields a byte-identical worldline;
- **I-12** rebuildable: a worldline is a pure fold of durable stream records and
  carries an integrity fingerprint over exactly the records that built it;
- **I-3** honesty: no evidence, no event; an unknown state is ``None``, never a
  fabricated empty snapshot.

Ordering is *total and tenant-scoped*: events sort by
``(occurred_at, precision rank, event_id)`` — a total order that does not
depend on input order, so two consumers replaying the same stream agree on the
trajectory without coordination.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from domain.dynamics import StreamRecord

#: Confidence assumed when a producer declares none (I-3: unknown != certain).
DEFAULT_CONFIDENCE = 0.5

#: Role given to a record's own entity when the record names no participants.
ANCHOR_ROLE = "record_subject"


class WorldlineError(ValueError):
    """A stream record cannot produce a safe worldline."""


class WorldlineEvidenceError(WorldlineError):
    """A record carries no observation/dataset reference (I-3, I-5)."""


class WorldlineTenantError(WorldlineError):
    """A cross-tenant record or lookup was attempted (I-12)."""


class TimePrecision(StrEnum):
    """Precision of an occurrence timestamp — unknown stays explicitly unknown."""

    UNKNOWN = "unknown"
    YEAR = "year"
    MONTH = "month"
    DAY = "day"
    HOUR = "hour"
    MINUTE = "minute"
    SECOND = "second"
    RANGE = "range"


PRECISION_RANK: dict[TimePrecision, int] = {
    TimePrecision.UNKNOWN: 0,
    TimePrecision.YEAR: 1,
    TimePrecision.MONTH: 2,
    TimePrecision.DAY: 3,
    TimePrecision.HOUR: 4,
    TimePrecision.MINUTE: 5,
    TimePrecision.SECOND: 6,
    TimePrecision.RANGE: 7,
}


class EventRelationKind(StrEnum):
    """Typed event-relation vocabulary (directed where the direction matters)."""

    PRECEDES = "precedes"
    FOLLOWS = "follows"
    OVERLAPS = "overlaps"
    CAUSES = "causes"
    CO_OCCURS = "co_occurs"


RELATION_RANK: dict[EventRelationKind, int] = {
    EventRelationKind.PRECEDES: 0,
    EventRelationKind.FOLLOWS: 1,
    EventRelationKind.OVERLAPS: 2,
    EventRelationKind.CAUSES: 3,
    EventRelationKind.CO_OCCURS: 4,
}

_PRECISIONS = frozenset(PRECISION_RANK)

#: Payload keys owned by the temporal layer; everything else is an attribute.
_RESERVED_PAYLOAD_KEYS = frozenset(
    {
        "occurred_at",
        "event_at",
        "ended_at",
        "time_precision",
        "participants",
        "patch",
        "state",
        "state_delta",
        "confidence",
        "causes",
    }
)

#: Payload keys that may name a participant with an implicit role.
_ROLE_KEYS = (
    "actor",
    "subject",
    "object",
    "target",
    "counterparty",
    "beneficiary",
    "source",
    "participant",
)


def _digest(value: Any) -> str:
    """Deterministic sha256 over JSON-canonical material."""
    material = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _canonical(value: Any) -> Any:
    """Recursive JSON-canonical normalization (replay-stable hashes)."""
    if isinstance(value, dict):
        return {str(k): _canonical(value[k]) for k in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return str(value.value)
    if isinstance(value, bool | int | float | str) or value is None:
        return value
    return str(value)


#: Calendar literals without a time part ("2024", "2024-03", "2024-03-01").
_DATE_ONLY = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def parse_timestamp(value: Any, *, field_name: str = "timestamp") -> datetime:
    """Parse an ISO-8601 (or datetime) value into an aware datetime.

    A naive timestamp is rejected rather than assumed local: a worldline built
    on a silently-relocated instant is a wrong trajectory, not a fuzzy one.
    Use :func:`parse_temporal` for literals that may legitimately be date-only.
    """
    parsed, _ = parse_temporal(value, field_name=field_name, allow_date_only=False)
    return parsed


def parse_temporal(
    value: Any,
    *,
    declared: Any = None,
    field_name: str = "timestamp",
    allow_date_only: bool = True,
) -> tuple[datetime, TimePrecision]:
    """Parse an occurrence literal into ``(aware datetime, precision)``.

    A calendar literal without a time part denotes a *span*, not an instant, so
    it is anchored at UTC midnight and keeps its declared precision — the text
    says "on 2024-03-01", and inventing a local midnight would invent a fact.
    A date *with* a time but no offset is genuinely ambiguous and is rejected.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise WorldlineError(f"timezone-aware {field_name} required, got {value!r}")
        return value, _infer_precision(value, declared)
    text = str(value or "").strip()
    if not text:
        raise WorldlineError(f"missing {field_name}")
    normalized = text.replace("Z", "+00:00")
    parsed: datetime | None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = None
    if parsed is not None and parsed.tzinfo is not None:
        return parsed, _infer_precision(normalized, declared)
    if allow_date_only and _DATE_ONLY.match(text):
        parts = [int(part) for part in text.split("-")]
        parts += [1] * (3 - len(parts))
        return datetime(parts[0], parts[1], parts[2], tzinfo=UTC), _infer_precision(text, declared)
    if parsed is not None:
        raise WorldlineError(f"timezone-aware {field_name} required, got {value!r}")
    raise WorldlineError(f"unparseable {field_name}: {value!r}")


@dataclass(frozen=True)
class EventInterval:
    """Half-open ``[start, end)`` occurrence window of an event.

    A point-in-time occurrence is a zero-width interval (``end == start``); a
    declared ``ended_at`` / ``valid_until`` gives a genuine window, which is
    what makes "concurrent" decidable rather than assumed.
    """

    start: datetime
    end: datetime
    precision: TimePrecision = TimePrecision.SECOND

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise WorldlineError("timezone-aware event interval required")
        if self.end < self.start:
            raise WorldlineError(f"event interval ends before it starts: {self.start!r}")

    @property
    def is_range(self) -> bool:
        return self.end > self.start

    @property
    def point(self) -> datetime:
        """Canonical ordering point: a point occurrence is its start."""
        return self.start

    def overlaps(self, other: EventInterval) -> bool:
        return self.start < other.end and other.start < self.end

    def contains(self, at: datetime) -> bool:
        if at.tzinfo is None:
            raise WorldlineError("timezone-aware timestamp required")
        return self.start <= at < self.end if self.is_range else at == self.start

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "precision": self.precision.value,
        }


def overlaps_window(interval: EventInterval, start: datetime, end: datetime) -> bool:
    """Does ``interval`` intersect the half-open query window ``[start, end)``?

    A zero-width occurrence is a point, so it matches only when the point falls
    inside the window; a genuine range matches on any overlap.
    """
    if interval.is_range:
        return interval.start < end and start < interval.end
    return start <= interval.point < end


def _infer_precision(raw: Any, declared: Any) -> TimePrecision:
    """Declared precision wins; otherwise infer it from the literal's shape."""
    if isinstance(declared, str) and declared.strip().lower() in _PRECISIONS:
        return TimePrecision(declared.strip().lower())
    if isinstance(raw, datetime):
        return TimePrecision.SECOND
    text = str(raw or "").strip()
    if len(text) == 4 and text.isdigit():
        return TimePrecision.YEAR
    if len(text) == 7 and text.count("-") == 1:
        return TimePrecision.MONTH
    if len(text) == 10 and text.count("-") == 2:
        return TimePrecision.DAY
    if "T" in text:
        return TimePrecision.SECOND if len(text) > 16 else TimePrecision.MINUTE
    return TimePrecision.UNKNOWN


def resolve_interval(record: StreamRecord) -> EventInterval:
    """Occurrence window of one record, honouring declared validity.

    Precedence: explicit ``occurred_at`` / ``event_at`` in the payload, then the
    record's ``valid_from``, then the append timestamp ``ts``. A declared
    ``ended_at`` / ``valid_until`` widens the point into a range.
    """
    payload = record.payload or {}
    raw_start = payload.get("occurred_at") or payload.get("event_at") or record.valid_from
    if raw_start is None:
        raw_start = record.ts
    start, precision = parse_temporal(
        raw_start, declared=payload.get("time_precision"), field_name="occurred_at"
    )
    raw_end = payload.get("ended_at") or record.valid_until
    if raw_end is not None:
        end, _ = parse_temporal(raw_end, field_name="ended_at")
        return EventInterval(start, end, TimePrecision.RANGE)
    return EventInterval(start, start, precision)


def _declared_confidence(record: StreamRecord) -> tuple[float, bool]:
    """``(confidence, declared)`` — a missing number is unknown, not 1.0 (I-3)."""
    raw = (record.payload or {}).get("confidence")
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return DEFAULT_CONFIDENCE, False
    value = float(raw)
    if not 0.0 <= value <= 1.0:
        raise WorldlineError(f"confidence must be within [0, 1], got {raw!r}")
    return value, True


def _span_of(record: StreamRecord) -> tuple[int, int] | None:
    """Offsets of the cue inside the source document — a ref, not the text (I-5)."""
    payload = record.payload or {}
    start, end = payload.get("span_start"), payload.get("span_end")
    if isinstance(start, int) and isinstance(end, int) and not isinstance(start, bool):
        if end < start:
            raise WorldlineError(f"invalid evidence span: [{start}, {end})")
        return start, end
    return None


@dataclass(frozen=True)
class EvidenceRef:
    """Ref-only provenance of one observation backing a derived artifact (I-5)."""

    source_record_id: str
    record_hash: str
    observation_id: str = ""
    dataset_id: str = ""
    extraction_version: str = ""
    extractor: str = ""
    span: tuple[int, int] | None = None

    @property
    def evidence_backed(self) -> bool:
        return bool(self.observation_id or self.dataset_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_record_id": self.source_record_id,
            "record_hash": self.record_hash,
            "observation_id": self.observation_id,
            "dataset_id": self.dataset_id,
            "extraction_version": self.extraction_version,
            "extractor": self.extractor,
            "span": list(self.span) if self.span else None,
            "evidence_backed": self.evidence_backed,
        }


def evidence_for(record: StreamRecord) -> EvidenceRef:
    """Evidence ref of one record — references only, never the payload (I-5)."""
    return EvidenceRef(
        source_record_id=record.record_id,
        record_hash=record.record_hash,
        observation_id=record.observation_id,
        dataset_id=record.dataset_id,
        extraction_version=record.extraction_version,
        extractor=str((record.payload or {}).get("extractor", "")),
        span=_span_of(record),
    )


@dataclass(frozen=True)
class Participant:
    """An entity taking part in an occurrence, with its role and confidence."""

    entity_id: str
    role: str = ANCHOR_ROLE
    schema_name: str = ""
    confidence: float = DEFAULT_CONFIDENCE
    confidence_declared: bool = False

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise WorldlineError("participant requires entity_id")
        if not 0.0 <= self.confidence <= 1.0:
            raise WorldlineError(f"participant confidence out of range: {self.confidence}")

    @property
    def sort_key(self) -> tuple[str, str]:
        return (self.entity_id, self.role)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "role": self.role,
            "schema_name": self.schema_name,
            "confidence": self.confidence,
            "confidence_declared": self.confidence_declared,
        }


def extract_participants(record: StreamRecord) -> tuple[Participant, ...]:
    """Participants of one record, deduplicated and deterministically ordered.

    Accepted shapes: ``participants`` as a list of ids or of role mappings, and
    the role shortcuts (``actor``/``target``/...). A record naming nobody
    yields its own entity as anchor — an occurrence always has an anchor.
    """
    payload = record.payload or {}
    confidence, declared = _declared_confidence(record)
    found: dict[tuple[str, str], Participant] = {}

    def add(entity_id: Any, role: str, schema_name: str = "", own: Any = None) -> None:
        if entity_id is None:
            return
        text = str(entity_id).strip()
        if not text:
            return
        value = confidence
        own_declared = declared
        if isinstance(own, int | float) and not isinstance(own, bool) and 0.0 <= float(own) <= 1.0:
            value, own_declared = float(own), True
        key = (text, role)
        current = found.get(key)
        if current is None or current.confidence < value:
            found[key] = Participant(
                entity_id=text,
                role=role,
                schema_name=schema_name,
                confidence=value,
                confidence_declared=own_declared,
            )

    raw = payload.get("participants")
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                add(
                    item.get("entity_id") or item.get("id") or item.get("mention"),
                    str(item.get("role") or "participant"),
                    str(item.get("schema_name") or item.get("type") or ""),
                    item.get("confidence"),
                )
            else:
                add(item, "participant")
    for key in _ROLE_KEYS:
        add(payload.get(key), key)
    if not found:
        add(record.entity_id, ANCHOR_ROLE)
    return tuple(found[key] for key in sorted(found))


def merge_state(base: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    """Shallow deterministic state merge; ``None`` is an explicit removal."""
    merged = dict(base)
    for key in sorted(delta, key=str):
        value = delta[key]
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = _canonical(value)
    return merged


@dataclass(frozen=True)
class StateSnapshot:
    """Entity state at one instant, fingerprinted over its contributing records."""

    fields: dict[str, Any] = field(default_factory=dict)
    as_of: datetime | None = None
    source_record_ids: tuple[str, ...] = ()
    fingerprint: str = ""

    def __post_init__(self) -> None:
        if self.as_of is None or self.as_of.tzinfo is None:
            raise WorldlineError("state snapshot requires an aware as_of")
        object.__setattr__(self, "fields", _canonical(self.fields))
        object.__setattr__(self, "source_record_ids", tuple(sorted(set(self.source_record_ids))))
        if not self.fingerprint:
            object.__setattr__(self, "fingerprint", "state-" + _digest(self._value())[:32])

    def _value(self) -> dict[str, Any]:
        return {
            "fields": self.fields,
            "as_of": self.as_of.isoformat(),
            "source_record_ids": list(self.source_record_ids),
        }

    @property
    def empty(self) -> bool:
        return not self.fields

    def to_dict(self) -> dict[str, Any]:
        return {**self._value(), "fingerprint": self.fingerprint}

    def __bool__(self) -> bool:
        return not self.empty


@dataclass(frozen=True)
class WorldlineEvent:
    """One evidence-backed occurrence on an entity's worldline.

    The event id is *content-addressed* over the tenant, the entity, the
    occurrence window, the participants, the state transition and the hashes of
    the records that produced it — so a replay of the same records always
    rebuilds the same id (I-11) and two events can never silently collide.
    """

    event_id: str
    tenant_id: str
    entity_id: str
    event_type: str
    interval: EventInterval
    participants: tuple[Participant, ...] = ()
    before_state: StateSnapshot | None = None
    after_state: StateSnapshot | None = None
    evidence: tuple[EvidenceRef, ...] = ()
    confidence: float = DEFAULT_CONFIDENCE
    confidence_declared: bool = False
    source_record_ids: tuple[str, ...] = ()
    source_record_hashes: tuple[str, ...] = ()
    attributes: dict[str, Any] = field(default_factory=dict)
    declared_causes: tuple[str, ...] = ()
    sequence: int = 0

    def __post_init__(self) -> None:
        if not self.event_id:
            raise WorldlineError("worldline event requires event_id")
        if not self.tenant_id or not self.entity_id:
            raise WorldlineError("worldline event requires tenant_id and entity_id")
        if not self.event_type:
            raise WorldlineError("worldline event requires event_type")
        if not 0.0 <= self.confidence <= 1.0:
            raise WorldlineError(f"event confidence out of range: {self.confidence}")
        ordered = tuple(sorted(self.participants, key=lambda p: p.sort_key))
        object.__setattr__(self, "participants", ordered)
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "attributes", _canonical(self.attributes))
        object.__setattr__(self, "declared_causes", tuple(sorted(set(self.declared_causes))))
        object.__setattr__(self, "source_record_ids", tuple(sorted(set(self.source_record_ids))))
        object.__setattr__(
            self, "source_record_hashes", tuple(sorted(set(self.source_record_hashes)))
        )

    @property
    def occurred_at(self) -> datetime:
        """Ordering point of the occurrence (see ``EventInterval.point``)."""
        return self.interval.point

    @property
    def evidence_backed(self) -> bool:
        return any(ref.evidence_backed for ref in self.evidence)

    @property
    def sort_key(self) -> tuple[datetime, int, str]:
        return event_order_key(self)

    def participant_ids(self, *, role: str | None = None) -> tuple[str, ...]:
        """Participant entity ids, optionally filtered by role."""
        return tuple(
            sorted(p.entity_id for p in self.participants if role is None or p.role == role)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "tenant_id": self.tenant_id,
            "entity_id": self.entity_id,
            "event_type": self.event_type,
            "interval": self.interval.to_dict(),
            "participants": [p.to_dict() for p in self.participants],
            "before_state": self.before_state.to_dict() if self.before_state else None,
            "after_state": self.after_state.to_dict() if self.after_state else None,
            "evidence": [ref.to_dict() for ref in self.evidence],
            "evidence_backed": self.evidence_backed,
            "confidence": self.confidence,
            "confidence_declared": self.confidence_declared,
            "source_record_ids": list(self.source_record_ids),
            "source_record_hashes": list(self.source_record_hashes),
            "attributes": self.attributes,
            "declared_causes": list(self.declared_causes),
            "sequence": self.sequence,
        }


def event_order_key(event: WorldlineEvent) -> tuple[datetime, int, str]:
    """Total, input-order-independent event ordering key.

    Timestamp first, precision rank second (an imprecise date never outranks a
    precise one at the same instant), event id last so that fully equal
    occurrences still have a stable, replay-stable order.
    """
    return (event.interval.point, PRECISION_RANK[event.interval.precision], event.event_id)


def event_identity_material(
    *,
    tenant_id: str,
    entity_id: str,
    event_type: str,
    interval: EventInterval,
    participants: Sequence[Participant],
    before_state: StateSnapshot | None,
    after_state: StateSnapshot | None,
    record_hashes: Sequence[str],
    declared_causes: Sequence[str] = (),
) -> dict[str, Any]:
    """The exact material an ``event_id`` is derived from (auditable, I-11)."""
    return {
        "tenant_id": tenant_id,
        "entity_id": entity_id,
        "event_type": event_type,
        "interval": interval.to_dict(),
        "participants": [p.to_dict() for p in sorted(participants, key=lambda p: p.sort_key)],
        "before_state": before_state.to_dict() if before_state else None,
        "after_state": after_state.to_dict() if after_state else None,
        "record_hashes": sorted(set(record_hashes)),
        "declared_causes": sorted(set(declared_causes)),
    }


def event_id_for(**kwargs: Any) -> str:
    """Content-addressed worldline event id (``EV-<sha256[:32]>``)."""
    return "EV-" + _digest(event_identity_material(**kwargs))[:32]


@dataclass(frozen=True)
class EventRelation:
    """A typed, directed relation between two worldline events.

    ``declared`` relations are asserted by a producer (an explicit causal cue in
    the evidence); inferred relations are derived by this module from the
    occurrence windows and participants. Consumers can therefore tell a claim
    from a deduction instead of reading one as the other (I-3).
    """

    relation_id: str
    tenant_id: str
    source_event_id: str
    target_event_id: str
    kind: EventRelationKind
    lag: tuple[int, int] | None = None  # (seconds, microseconds) — plain ints
    declared: bool = False
    cue: str = ""
    evidence: tuple[EvidenceRef, ...] = ()
    confidence: float = DEFAULT_CONFIDENCE
    confidence_declared: bool = False
    source_entity_id: str = ""
    target_entity_id: str = ""

    def __post_init__(self) -> None:
        if not self.relation_id:
            raise WorldlineError("event relation requires relation_id")
        if not self.tenant_id:
            raise WorldlineError("event relation requires tenant_id")
        if self.source_event_id == self.target_event_id:
            raise WorldlineError("an event cannot be related to itself")
        if not 0.0 <= self.confidence <= 1.0:
            raise WorldlineError(f"relation confidence out of range: {self.confidence}")

    @property
    def is_declared(self) -> bool:
        """True when a producer asserted the relation, False when inferred."""
        return self.declared

    def to_dict(self) -> dict[str, Any]:
        return {
            "relation_id": self.relation_id,
            "tenant_id": self.tenant_id,
            "source_event_id": self.source_event_id,
            "target_event_id": self.target_event_id,
            "kind": self.kind.value,
            "lag_seconds": self.lag[0] if self.lag else None,
            "declared": self.declared,
            "cue": self.cue,
            "evidence": [ref.to_dict() for ref in self.evidence],
            "confidence": self.confidence,
            "confidence_declared": self.confidence_declared,
            "source_entity_id": self.source_entity_id,
            "target_entity_id": self.target_entity_id,
        }


def relation_id_for(
    *, tenant_id: str, source_event_id: str, target_event_id: str, kind: EventRelationKind
) -> str:
    """Content-addressed relation id — direction and kind are load-bearing."""
    return (
        "ER-"
        + _digest(
            {
                "tenant_id": tenant_id,
                "source_event_id": source_event_id,
                "target_event_id": target_event_id,
                "kind": kind.value,
            }
        )[:32]
    )


def relation_order_key(
    relation: EventRelation, order_index: dict[str, int]
) -> tuple[int, int, int, str]:
    """Deterministic relation ordering along the worldline, then by kind."""
    return (
        order_index.get(relation.source_event_id, len(order_index)),
        order_index.get(relation.target_event_id, len(order_index)),
        RELATION_RANK[relation.kind],
        relation.relation_id,
    )


@dataclass(frozen=True)
class EntityWorldline:
    """The ordered trajectory of one entity: its events and their relations.

    The aggregate is a pure fold of durable stream records (I-12): drop it and
    rebuild from ``source_record_ids`` and you get the same bytes, which is why
    ``integrity_fingerprint`` covers both the events and the exact record set
    that produced them.
    """

    tenant_id: str
    entity_id: str
    events: tuple[WorldlineEvent, ...] = ()
    relations: tuple[EventRelation, ...] = ()
    integrity_fingerprint: str = ""
    projection_generation: int = 1

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.entity_id:
            raise WorldlineError("worldline requires tenant_id and entity_id")
        events = tuple(sorted(self.events, key=event_order_key))
        object.__setattr__(self, "events", events)
        index = {event.event_id: i for i, event in enumerate(events)}
        for event in events:
            if event.tenant_id != self.tenant_id or event.entity_id != self.entity_id:
                raise WorldlineError(
                    f"event {event.event_id} does not belong to {self.tenant_id}/{self.entity_id}"
                )
        for relation in self.relations:
            if relation.tenant_id != self.tenant_id:
                raise WorldlineError(
                    f"relation {relation.relation_id} crosses tenant boundary {self.tenant_id}"
                )
            if relation.source_event_id not in index or relation.target_event_id not in index:
                raise WorldlineError(
                    f"relation {relation.relation_id} references an event outside the worldline"
                )
        object.__setattr__(
            self,
            "relations",
            tuple(sorted(self.relations, key=lambda r: relation_order_key(r, index))),
        )
        if not self.integrity_fingerprint:
            object.__setattr__(self, "integrity_fingerprint", "WL-" + _digest(self._value())[:32])

    def _value(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "entity_id": self.entity_id,
            "events": [e.to_dict() for e in self.events],
            "relations": [r.to_dict() for r in self.relations],
            "projection_generation": self.projection_generation,
        }

    @property
    def event_ids(self) -> tuple[str, ...]:
        return tuple(event.event_id for event in self.events)

    @property
    def source_record_ids(self) -> tuple[str, ...]:
        return tuple(sorted({rid for event in self.events for rid in event.source_record_ids}))

    def event_at(self, at: datetime) -> WorldlineEvent | None:
        """First event whose occurrence window contains ``at`` (deterministic)."""
        if at.tzinfo is None:
            raise WorldlineError("timezone-aware timestamp required")
        for event in self.events:
            if event.interval.contains(at):
                return event
        return None

    def events_between(self, start: datetime, end: datetime) -> tuple[WorldlineEvent, ...]:
        """Events overlapping the half-open ``[start, end)`` query window."""
        if start.tzinfo is None or end.tzinfo is None:
            raise WorldlineError("timezone-aware bounds required")
        if end < start:
            raise WorldlineError("query window ends before it starts")
        return tuple(event for event in self.events if overlaps_window(event.interval, start, end))

    def state_at(self, at: datetime) -> StateSnapshot | None:
        """State after the last event at or before ``at`` (``None`` if unknown)."""
        if at.tzinfo is None:
            raise WorldlineError("timezone-aware timestamp required")
        seen = [e for e in self.events if e.interval.point <= at]
        return seen[-1].after_state if seen else None

    def relations_of(
        self, event_id: str, *, kind: EventRelationKind | None = None
    ) -> tuple[EventRelation, ...]:
        """Relations touching ``event_id`` in either direction."""
        return tuple(
            r
            for r in self.relations
            if (r.source_event_id == event_id or r.target_event_id == event_id)
            and (kind is None or r.kind is kind)
        )

    def to_dict(self) -> dict[str, Any]:
        return {**self._value(), "integrity_fingerprint": self.integrity_fingerprint}


def _check_tenant(records: Iterable[StreamRecord], tenant_id: str) -> None:
    """Reject a mixed-tenant batch outright rather than leaking across tenants."""
    for record in records:
        if record.tenant_id != tenant_id:
            raise WorldlineTenantError(
                f"record {record.record_id} belongs to tenant {record.tenant_id!r}, "
                f"not {tenant_id!r} (I-12)"
            )


def _dedupe_records(records: Iterable[StreamRecord]) -> tuple[StreamRecord, ...]:
    """Collapse exact replays (same record hash) — idempotent ingest (I-11)."""
    unique: dict[str, StreamRecord] = {}
    for record in records:
        unique.setdefault(record.record_hash, record)
    return tuple(unique[key] for key in sorted(unique))


def _state_delta(record: StreamRecord) -> dict[str, Any] | None:
    """The state change a record declares: ``patch``/``state_delta``/``state``.

    ``None`` when the record says nothing about entity state — an unknown state
    is never folded into a fabricated one.
    """
    payload = record.payload or {}
    for key in ("patch", "state_delta", "state"):
        value = payload.get(key)
        if isinstance(value, dict):
            return {str(k): v for k, v in value.items()}
    return None


def build_event(
    record: StreamRecord,
    *,
    before_state: dict[str, Any] | None,
    after_state: dict[str, Any] | None,
    before_records: Sequence[str] = (),
    after_records: Sequence[str] = (),
) -> WorldlineEvent:
    """Turn one stream record into one content-addressed worldline event.

    The state positions are supplied by the caller so this stays pure and the
    state machine lives in exactly one place: :func:`extract_events`.
    """
    interval = resolve_interval(record)
    participants = extract_participants(record)
    confidence, declared = _declared_confidence(record)
    before = (
        StateSnapshot(
            fields=dict(before_state or {}),
            as_of=interval.start,
            source_record_ids=tuple(before_records),
        )
        if before_state is not None
        else None
    )
    after = (
        StateSnapshot(
            fields=dict(after_state or {}),
            as_of=interval.end,
            source_record_ids=tuple(after_records),
        )
        if after_state is not None
        else None
    )
    payload = record.payload or {}
    attributes = {k: v for k, v in sorted(payload.items()) if k not in _RESERVED_PAYLOAD_KEYS}
    declared_causes = _parse_declared_causes(payload)
    event_id = event_id_for(
        tenant_id=record.tenant_id,
        entity_id=record.entity_id,
        event_type=record.kind,
        interval=interval,
        participants=participants,
        before_state=before,
        after_state=after,
        record_hashes=(record.record_hash,),
        declared_causes=declared_causes,
    )
    return WorldlineEvent(
        event_id=event_id,
        tenant_id=record.tenant_id,
        entity_id=record.entity_id,
        event_type=record.kind,
        interval=interval,
        participants=participants,
        before_state=before,
        after_state=after,
        evidence=(evidence_for(record),),
        confidence=confidence,
        confidence_declared=declared,
        source_record_ids=(record.record_id,),
        source_record_hashes=(record.record_hash,),
        attributes=attributes,
        declared_causes=declared_causes,
        sequence=record.sequence,
    )


def extract_events(
    records: Iterable[StreamRecord],
    *,
    tenant_id: str,
    entity_id: str | None = None,
    require_evidence: bool = True,
) -> tuple[WorldlineEvent, ...]:
    """Extract the ordered, evidence-backed events of one (or every) entity.

    The fold is total: records are tenant-checked, deduplicated by record hash,
    sorted by ``(occurred_at, precision, record hash)`` and folded into a
    before/after state track. The result therefore depends only on the *set* of
    records, never on the order they arrived in.

    ``require_evidence`` enforces I-3: a record with neither an observation nor
    a dataset reference is rejected instead of silently becoming an event.
    """
    pool = [r for r in records if entity_id is None or r.entity_id == entity_id]
    _check_tenant(pool, tenant_id)
    if require_evidence:
        for record in pool:
            if not evidence_for(record).evidence_backed:
                raise WorldlineEvidenceError(
                    f"record {record.record_id} has no observation/dataset reference"
                )
    by_entity: dict[str, list[StreamRecord]] = {}
    for record in _dedupe_records(pool):
        by_entity.setdefault(record.entity_id, []).append(record)

    events: list[WorldlineEvent] = []
    for entity in sorted(by_entity):
        state: dict[str, Any] = {}
        # Records that have contributed to the state track so far; a snapshot
        # names exactly them, so a state can always be re-derived (I-12).
        state_records: list[str] = []
        ordered = sorted(
            by_entity[entity], key=lambda r: (resolve_interval(r).point, r.record_hash)
        )
        for record in ordered:
            delta = _state_delta(record)
            before_records = tuple(state_records)
            # Captured *before* the merge: this is the state the event changed.
            before_fields = dict(state) if (delta is not None and state) else None
            if delta is not None:
                state = merge_state(state, delta)
                state_records.append(record.record_id)
            # An empty state is indistinguishable from an unknown one, so no
            # snapshot is emitted for it (I-3: absence is never fabricated).
            events.append(
                build_event(
                    record,
                    before_state=before_fields,
                    after_state=dict(state) if state else None,
                    before_records=before_records,
                    after_records=tuple(state_records),
                )
            )
    return tuple(sorted(events, key=event_order_key))


def _lag_between(source: WorldlineEvent, target: WorldlineEvent) -> tuple[int, int]:
    """Signed distance between two occurrences as ``(seconds, microseconds)``."""
    delta = target.interval.point - source.interval.point
    return (delta.days * 86400 + delta.seconds, delta.microseconds)


def _parse_declared_causes(payload: dict[str, Any]) -> tuple[str, ...]:
    """Event ids a record explicitly claims to cause (``payload.causes``).

    Accepted shapes: a bare id, a list of ids, or ``{"event_id": ...}`` /
    ``{"record_id": ...}`` mappings. Unresolvable values are kept verbatim here
    and simply produce no relation until a matching event exists — a dangling
    causal claim is dropped, never guessed at.
    """
    raw = payload.get("causes")
    if raw is None:
        return ()
    items = raw if isinstance(raw, list) else [raw]
    targets: list[str] = []
    for item in items:
        if isinstance(item, dict):
            value = item.get("event_id") or item.get("record_id")
        else:
            value = item
        if value:
            targets.append(str(value))
    return tuple(sorted(set(targets)))


def derive_temporal_relations(
    events: Sequence[WorldlineEvent],
    *,
    tenant_id: str,
    entity_id: str | None = None,
    max_events: int = 512,
) -> tuple[EventRelation, ...]:
    """Derive ``precedes`` / ``follows`` / ``overlaps`` between worldline events.

    Ordering is decided on the *occurrence windows*, not on arrival order:
    overlapping windows yield ``overlaps``, disjoint windows yield the
    ``precedes``/``follows`` pair. Declared causal links (``payload.causes``)
    become ``declared=True`` relations so consumers can separate a producer's
    claim from this module's deduction (I-3).

    Complexity is O(n²) in the number of events, hence ``max_events``.
    """
    ordered = sorted(events, key=event_order_key)
    if len(ordered) > max_events:
        raise WorldlineError(
            f"too many events for pairwise derivation: {len(ordered)} > {max_events}"
        )
    by_id = {event.event_id: event for event in ordered}
    # A producer knows record ids at emit time and event ids only after the
    # fold, so a declared cause may name either — both are stable identities.
    for event in ordered:
        for record_id in event.source_record_ids:
            by_id.setdefault(record_id, event)

    relations: dict[tuple[str, str, EventRelationKind], EventRelation] = {}

    def add(
        source: WorldlineEvent,
        target: WorldlineEvent,
        kind: EventRelationKind,
        *,
        declared: bool,
        cue: str,
    ) -> None:
        if source.event_id == target.event_id:
            return
        rid = relation_id_for(
            tenant_id=tenant_id,
            source_event_id=source.event_id,
            target_event_id=target.event_id,
            kind=kind,
        )
        relations.setdefault(
            (source.event_id, target.event_id, kind),
            EventRelation(
                relation_id=rid,
                tenant_id=tenant_id,
                source_event_id=source.event_id,
                target_event_id=target.event_id,
                kind=kind,
                lag=_lag_between(source, target),
                declared=declared,
                cue=cue,
                evidence=tuple(source.evidence),
                confidence=source.confidence,
                confidence_declared=source.confidence_declared,
                source_entity_id=source.entity_id,
                target_entity_id=target.entity_id,
            ),
        )

    for i, left in enumerate(ordered):
        for right in ordered[i + 1 :]:
            if entity_id is not None and right.entity_id != entity_id:
                continue
            if left.interval.overlaps(right.interval):
                # Overlap is symmetric: both directions are emitted so a query
                # from either event finds it.
                add(left, right, EventRelationKind.OVERLAPS, declared=False, cue="interval_overlap")
                add(right, left, EventRelationKind.OVERLAPS, declared=False, cue="interval_overlap")
            elif left.interval.point <= right.interval.point:
                add(left, right, EventRelationKind.PRECEDES, declared=False, cue="occurrence_order")
                add(right, left, EventRelationKind.FOLLOWS, declared=False, cue="occurrence_order")
    for event in ordered:
        for target_id in event.declared_causes:
            target = by_id.get(target_id)
            if target is not None:
                add(event, target, EventRelationKind.CAUSES, declared=True, cue="declared_causes")
    index = {event.event_id: i for i, event in enumerate(ordered)}
    return tuple(sorted(relations.values(), key=lambda r: relation_order_key(r, index)))


def derive_cooccurrence_relations(
    worldlines: Sequence[EntityWorldline],
    *,
    max_pairs_per_entity: int = 256,
) -> tuple[EventRelation, ...]:
    """Relate events that share a participant, across entities of one tenant.

    Co-occurrence is *inferred*, never declared: two events that merely name the
    same participant are related, and the relation is explicitly not a claim
    that the events describe the same real-world occurrence. The shared
    participant is the evidence, so a consumer can always re-derive it.

    Events of the *same* worldline are skipped — their relations come from
    :func:`derive_temporal_relations`. Cross-tenant linking is impossible by
    construction: participant ids are only grouped within one tenant.
    """
    by_tenant: dict[str, dict[str, list[WorldlineEvent]]] = {}
    for worldline in worldlines:
        bucket = by_tenant.setdefault(worldline.tenant_id, {})
        for event in worldline.events:
            bucket.setdefault(event.entity_id, []).append(event)

    relations: dict[tuple[str, str, str], EventRelation] = {}
    for tenant in sorted(by_tenant):
        per_participant: dict[str, list[WorldlineEvent]] = {}
        for entity in sorted(by_tenant[tenant]):
            for event in by_tenant[tenant][entity]:
                for participant in event.participant_ids():
                    per_participant.setdefault(participant, []).append(event)
        for participant in sorted(per_participant):
            events = sorted(per_participant[participant], key=event_order_key)
            if len(events) > max_pairs_per_entity:
                raise WorldlineError(
                    f"participant {participant} appears in more than {max_pairs_per_entity} events"
                )
            for i, left in enumerate(events):
                for right in events[i + 1 :]:
                    if left.entity_id == right.entity_id:
                        continue
                    source, target = (
                        (left, right) if left.sort_key <= right.sort_key else (right, left)
                    )
                    if source.entity_id > target.entity_id:
                        source, target = target, source
                    rid = relation_id_for(
                        tenant_id=tenant,
                        source_event_id=source.event_id,
                        target_event_id=target.event_id,
                        kind=EventRelationKind.CO_OCCURS,
                    )
                    key = (tenant, source.event_id, target.event_id)
                    if key in relations:
                        continue
                    relations[key] = EventRelation(
                        relation_id=rid,
                        tenant_id=tenant,
                        source_event_id=source.event_id,
                        target_event_id=target.event_id,
                        kind=EventRelationKind.CO_OCCURS,
                        lag=_lag_between(source, target),
                        declared=False,
                        cue=f"participant:{participant}",
                        evidence=tuple(source.evidence),
                        confidence=min(source.confidence, target.confidence),
                        confidence_declared=source.confidence_declared
                        and target.confidence_declared,
                        source_entity_id=source.entity_id,
                        target_entity_id=target.entity_id,
                    )
    return tuple(relations[key] for key in sorted(relations))


def build_worldline(
    records: Iterable[StreamRecord],
    *,
    tenant_id: str,
    entity_id: str,
    require_evidence: bool = True,
    projection_generation: int = 1,
) -> EntityWorldline:
    """Fold one entity's stream records into its complete worldline."""
    events = extract_events(
        records, tenant_id=tenant_id, entity_id=entity_id, require_evidence=require_evidence
    )
    relations = derive_temporal_relations(events, tenant_id=tenant_id, entity_id=entity_id)
    return EntityWorldline(
        tenant_id=tenant_id,
        entity_id=entity_id,
        events=events,
        relations=relations,
        projection_generation=projection_generation,
    )


def extract_worldlines(
    records: Iterable[StreamRecord],
    *,
    tenant_id: str | None = None,
    require_evidence: bool = True,
) -> tuple[EntityWorldline, ...]:
    """Fold a mixed stream into one worldline per entity, deterministically ordered.

    With ``tenant_id`` omitted the batch must belong to exactly one tenant;
    anything else is a cross-tenant read and is refused (I-12).
    """
    pool = list(records)
    tenants = sorted({r.tenant_id for r in pool})
    if tenant_id is None:
        if len(tenants) > 1:
            raise WorldlineTenantError(
                f"tenant_id is required for a multi-tenant batch: {', '.join(tenants)}"
            )
        tenant_id = tenants[0] if tenants else "default-tenant"
    _check_tenant(pool, tenant_id)
    return tuple(
        build_worldline(
            pool,
            tenant_id=tenant_id,
            entity_id=entity,
            require_evidence=require_evidence,
        )
        for entity in sorted({r.entity_id for r in pool})
    )


__all__ = [
    "ANCHOR_ROLE",
    "DEFAULT_CONFIDENCE",
    "PRECISION_RANK",
    "RELATION_RANK",
    "EntityWorldline",
    "EventInterval",
    "EventRelation",
    "EventRelationKind",
    "EvidenceRef",
    "Participant",
    "StateSnapshot",
    "TimePrecision",
    "WorldlineError",
    "WorldlineEvent",
    "WorldlineEvidenceError",
    "WorldlineTenantError",
    "build_event",
    "build_worldline",
    "derive_cooccurrence_relations",
    "derive_temporal_relations",
    "event_id_for",
    "event_order_key",
    "evidence_for",
    "extract_events",
    "extract_participants",
    "extract_worldlines",
    "merge_state",
    "overlaps_window",
    "parse_timestamp",
    "relation_id_for",
    "relation_order_key",
    "resolve_interval",
]
