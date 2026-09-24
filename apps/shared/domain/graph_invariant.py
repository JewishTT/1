"""Dynamic-invariant graph model — the 2-kind atomic entity (spec 012).

Exactly TWO kinds of graph objects exist (product-locked, do not re-litigate):

1. DYNAMIC INVARIANT (``GraphInvariant``) — a person, company, domain, channel
   or event: the *center of analysis*. Stream-anchored identity (the append-only
   ``entity.stream.appended`` flow is the substrate; nothing here is a separate
   authority), temporality/lifecycle (windowed, deterministic), versions
   (revision), and topology (per-window neighbor signature + TDA proxies).
2. STATIC OBJECT (``StaticObject``) — a document, photo or conversation: a
   content-addressed, immutable leaf that CARRIES evidence (I-1). It is never a
   dynamic center; it has no own dynamics beyond its descriptor. Entities reach
   it only through a TYPED edge (``hasEvidence`` / ``depicts`` /
   ``inConversation``).

Embedded-vs-linked decision (this model is the answer):
- EMBEDDED inside the invariant: identity block (``entity_id``, canonical stream
  anchor, type label, revision), temporal block (ordered window slices with
  lifecycle states and cadence metrics), topological block (degree, community,
  neighbor signature, per-window TDA-proxy features), evidence block (observation
  count, content-addressed anchors, assertion ids) and provenance block.
- NEVER embedded: static-object *content* (byte payloads stay in object storage,
  I-5; the invariant carries only ``SO-…`` refs in ``links``), co-mention facts
  (they remain N-ary hyperedges — I-6, never identity), and evidence-dependent
  attribute values (they stay versioned ``Valuation`` properties with confidence
  folded from the stream — referenced by the stream anchor, rebuildable I-12).

Layer separation (respected): L2 (Neo4j) stores the *current* relational graph
state for navigation — this module is the domain shape it materializes; L3 (TDA)
consumes ``to_tda_input`` / ``to_multiplex`` per window and stores only *feature*
time series (barcodes/landscapes/PH0DM) in ClickHouse — never "a TDA graph".
Persistence features are rebuildable from events (I-12); only features are
stored. This module is pure: stdlib-only, no IO/DB, no projection imports.

Design contract (mirrors ``domain.dynamics`` / ``domain.hypergraph``):
- frozen dataclasses; deterministic ``as_dict`` (sorted keys, canonical values);
- ``integrity_digest`` = sha256 over the canonical JSON — same events in any
  order replay to a byte-identical digest (I-11/I-12); the event-id convention
  is ``evt-<record_hash>``, applied verbatim when records carry their hash;
- ``from_entity_stream`` is a pure deterministic builder: same events ⇒ same
  invariant; exact duplicates are idempotent-deduped (I-11); empty input is
  rejected (an identity must come from somewhere, I-3 honesty);
- ``to_tda_input`` reproduces the documented ``AdjacencyView.to_tda_input``
  shape ``(node_ids, [(i, j, weight), ...])`` without importing projection.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

DYNAMIC_INVARIANT = "dynamic_invariant"
STATIC_OBJECT = "static_object"

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

#: Relative band around a slice's predecessor count that counts as STABLE
#: (10% — deterministic, no fabrication of precision the stream does not have).
_LIFECYCLE_TOLERANCE = 0.10

#: Documented typed-relations vocabulary for invariant -> static-object edges.
#: The model accepts any non-empty relation but these three are canonical.
TYPED_RELATIONS = frozenset({"hasEvidence", "depicts", "inConversation"})


class LifecycleState(StrEnum):
    """Deterministic lifecycle state of one ordered window slice (spec 012).

    - NASCENT:   first window containing any activity.
    - GROWING:   event count above the previous slice's band (+10%).
    - STABLE:    event count within the previous slice's ±10% band.
    - DECAYING:  event count below the previous slice's band (−10%).
    - DORMANT:   no events at all in the window (an explicit, honest gap).
    """

    NASCENT = "nascent"
    GROWING = "growing"
    STABLE = "stable"
    DECAYING = "decaying"
    DORMANT = "dormant"


# --------------------------------------------------------------------------
# Identity block — stream-anchored, stable across re-versioning
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class InvariantIdentity:
    """Identity of a dynamic invariant (never a merge decision — I-6).

    ``entity_id`` and ``stream_anchor`` together are the canonical stream
    anchor: the anchor is the content address of the stream's GENESIS record
    (``evt-<record_hash>`` when the record carries one). Genesis is the lowest
    accepted stream sequence, not the earliest event time, so a late arrival
    with an older timestamp cannot move identity. ``type_label`` is the
    registered schema/class label (explicit, never guessed).
    """

    entity_id: str
    stream_anchor: str
    type_label: str
    revision: int = 1

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise ValueError("invariant identity requires entity_id")
        if not self.stream_anchor:
            raise ValueError("invariant identity requires stream_anchor")
        if self.revision < 1:
            raise ValueError(f"revision must be >= 1, got {self.revision}")
        object.__setattr__(self, "stream_anchor", str(self.stream_anchor))

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "stream_anchor": self.stream_anchor,
            "type_label": self.type_label,
            "revision": self.revision,
        }


# --------------------------------------------------------------------------
# Temporal block — ordered window slices + lifecycle + cadence metrics
# --------------------------------------------------------------------------


def window_bounds(ts: datetime, window: timedelta) -> tuple[datetime, datetime]:
    """Epoch-aligned half-open window ``[start, end)`` containing ``ts``.

    Deterministic: anchored to the UTC epoch, never to "now". The same window
    size yields the same slicing for every stream, so per-window slices of
    different entities line up for multiplex-over-time TDA.
    """
    if ts.tzinfo is None:
        raise ValueError("window arithmetic requires timezone-aware timestamps (I-12)")
    if window is None or window <= timedelta(0):
        raise ValueError(f"window must be positive, got {window!r}")
    span_s = window.total_seconds()
    offset_s = (ts - _EPOCH).total_seconds()
    start_s = math.floor(offset_s / span_s) * span_s
    start = _EPOCH + timedelta(seconds=start_s)
    return start, start + window


@dataclass(frozen=True)
class TemporalSlice:
    """One ordered window of an invariant's life — time series tiling.

    Honest per-window cadence (I-3): ``events_per_period`` is count / window
    days (0.0 for an empty slice, never fabricated); ``burstiness`` follows the
    documented B = (σ/μ − 1)/(σ/μ + 1) formula and is None when the slice holds
    fewer than two events (no data, no number). ``first_seen``/``last_seen``
    are None for dormant slices.
    """

    window_start: datetime
    window_end: datetime
    state: LifecycleState
    event_count: int
    events_per_period: float
    burstiness: float | None
    first_seen: datetime | None
    last_seen: datetime | None

    def __post_init__(self) -> None:
        if self.window_end <= self.window_start:
            raise ValueError("slice window_end must be after window_start")
        if self.event_count < 0:
            raise ValueError(f"event_count must be >= 0, got {self.event_count}")
        if self.window_start.tzinfo is None or self.window_end.tzinfo is None:
            raise ValueError("slice window bounds must be timezone-aware (I-12)")

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "state": self.state.value,
            "event_count": self.event_count,
            "events_per_period": self.events_per_period,
            "burstiness": self.burstiness,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }


@dataclass(frozen=True)
class TemporalLifecycle:
    """Ordered series of windows (deterministic sort) + lifecycle summary.

    Slices are normalized to ``(window_start, window_end, state)`` order on
    construction so the digest is byte-identical regardless of the order in
    which slices were assembled. ``state`` is the *current* lifecycle state:
    the last slice's state, or DORMANT for an empty lifecycle (honest).
    """

    slices: tuple[TemporalSlice, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "slices",
            tuple(
                sorted(
                    self.slices,
                    key=lambda s: (s.window_start, s.window_end, s.state.value),
                )
            ),
        )

    @property
    def first_seen(self) -> datetime | None:
        return self.slices[0].first_seen if self.slices else None

    @property
    def last_seen(self) -> datetime | None:
        return self.slices[-1].last_seen if self.slices else None

    @property
    def state(self) -> LifecycleState:
        return self.slices[-1].state if self.slices else LifecycleState.DORMANT

    @property
    def active_slices(self) -> tuple[TemporalSlice, ...]:
        """Windows containing at least one event (the "active windows")."""
        return tuple(s for s in self.slices if s.event_count > 0)

    def to_dict(self) -> dict[str, Any]:
        first = self.slices[0].window_start if self.slices else None
        last = self.slices[-1].window_end if self.slices else None
        return {
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "first_window_start": first.isoformat() if first else None,
            "last_window_end": last.isoformat() if last else None,
            "state": self.state.value,
            "slices": [s.to_dict() for s in self.slices],
        }


# --------------------------------------------------------------------------
# Topological block — per-window neighbor signature + TDA-proxy features
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TDAProxy:
    """Per-window TDA-proxy features (structural only — I-6, never identity).

    Computed over the *ego-star* (self + weighted neighbors) the invariant
    actually holds, using edge filtration ``1/(1 + weight)`` (a co-occurrence
    weight as a similarity; smaller feet-first distances). These are the honest
    PH0 numbers of that star, not a guessed global graph:
    - ``h0_classes`` — β₀ at filtration 0: vertices = neighbors + the self node;
    - ``ph0dm``      — PH0 max-death proxy: the largest finite H0 death, i.e.
      ``max 1/(1+w)`` over the window's edges; 0.0 when the ego has no edges.
    L3 stores these as feature rows in ClickHouse (keyed by window), not the
    adjacency itself — the adjacency stays rebuildable from events (I-12).
    """

    window_start: datetime
    window_end: datetime
    h0_classes: int
    ph0dm: float
    weight_sum: float
    structural_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "h0_classes": self.h0_classes,
            "ph0dm": self.ph0dm,
            "weight_sum": self.weight_sum,
            "structural_only": self.structural_only,
        }


@dataclass(frozen=True)
class WindowTopology:
    """Lossless per-window weighted adjacency of the invariant's ego-star.

    ``neighbor_weights`` is sorted by neighbor id — this is what ``to_tda_input``
    and ``to_multiplex`` consume per layer (never the "TDA graph" itself).
    """

    window_start: datetime
    window_end: datetime
    neighbor_weights: tuple[tuple[str, float], ...] = ()
    community: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "neighbor_weights",
            tuple(
                sorted(
                    ((str(nid), float(w)) for nid, w in self.neighbor_weights),
                    key=lambda item: item[0],
                )
            ),
        )

    @property
    def degree(self) -> int:
        return len(self.neighbor_weights)

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "community": self.community,
            "neighbor_weights": [[nid, w] for nid, w in self.neighbor_weights],
        }


@dataclass(frozen=True)
class TopologicalState:
    """Topological block of the invariant (structural signals only, I-6).

    ``neighbor_signature`` is the sorted union of neighbor ids across all
    windows; ``degree`` is its size; ``community`` is a label when the stream
    asserts one (empty string = honestly unknown). Per-window adjacency lives
    in ``window_topology`` and its derived proxies in ``tda_proxy`` (aligned,
    one entry per lifecycle slice).
    """

    degree: int
    community: str
    neighbor_signature: tuple[str, ...] = ()
    window_topology: tuple[WindowTopology, ...] = ()
    tda_proxy: tuple[TDAProxy, ...] = ()

    def __post_init__(self) -> None:
        if self.degree < 0:
            raise ValueError(f"degree must be >= 0, got {self.degree}")
        object.__setattr__(self, "neighbor_signature", tuple(sorted(set(self.neighbor_signature))))
        object.__setattr__(
            self,
            "window_topology",
            tuple(sorted(self.window_topology, key=lambda w: (w.window_start, w.window_end))),
        )
        object.__setattr__(
            self,
            "tda_proxy",
            tuple(sorted(self.tda_proxy, key=lambda p: (p.window_start, p.window_end))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "degree": self.degree,
            "community": self.community,
            "neighbor_signature": list(self.neighbor_signature),
            "window_topology": [w.to_dict() for w in self.window_topology],
            "tda_proxy": [p.to_dict() for p in self.tda_proxy],
        }


# --------------------------------------------------------------------------
# Evidence + provenance blocks (I-3, I-12)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceBlock:
    """Evidence carried BY the invariant — anchors, never bytes (I-5).

    ``observation_anchors`` are the content-addressed observation ids of the
    observations feeding the stream (refs-only): the invariant may prove it was
    observed but never embeds raw evidence. ``assertion_ids`` are the admitted
    assertion ids attached to stream records, and ``content_digests`` any
    payload digests (``digest``/``content_sha256``) surfaced by the stream.
    """

    observation_count: int = 0
    observation_anchors: tuple[str, ...] = ()
    content_digests: tuple[str, ...] = ()
    assertion_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.observation_count < 0:
            raise ValueError(f"observation_count must be >= 0, got {self.observation_count}")
        object.__setattr__(
            self, "observation_anchors", tuple(sorted(set(self.observation_anchors)))
        )
        object.__setattr__(self, "content_digests", tuple(sorted(set(self.content_digests))))
        object.__setattr__(self, "assertion_ids", tuple(sorted(set(self.assertion_ids))))

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_count": self.observation_count,
            "observation_anchors": list(self.observation_anchors),
            "content_digests": list(self.content_digests),
            "assertion_ids": list(self.assertion_ids),
        }


@dataclass(frozen=True)
class ProvenanceBlock:
    """Provenance of THIS projection write (I-12: every write carries it).

    Hermetic by design: no wall-clock ``built_at`` — determinism forbids it.
    ``stream_head`` is the sha256 over the source record hashes in canonical
    stream order (the chain tip; changes when events are appended); ``event_id``
    follows the ``evt-<record_hash>`` convention over the head, exactly like
    ``entity.state.projected``. ``source_hashes`` preserve that order because
    the sequence, not event time, defines provenance order for late arrivals.
    """

    tenant_id: str
    event_id: str = ""
    observation_id: str = ""
    stream_head: str = ""
    source_hashes: tuple[str, ...] = ()
    builder: str = "graph_invariant.from_entity_stream"
    schema: str = "cognitive/graph_invariant@0.1.0"

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("provenance requires tenant_id (I-12)")
        # ``source_hashes`` is already in canonical stream-sequence order.
        # Deduplicate without changing that order; lexical sorting here would
        # move a late-arriving hash ahead of earlier stream records.
        object.__setattr__(
            self,
            "source_hashes",
            tuple(dict.fromkeys(str(value) for value in self.source_hashes)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "event_id": self.event_id,
            "observation_id": self.observation_id,
            "stream_head": self.stream_head,
            "source_hashes": list(self.source_hashes),
            "builder": self.builder,
            "schema": self.schema,
        }


# --------------------------------------------------------------------------
# Static object — kind 2: content-addressed immutable evidence leaf
# --------------------------------------------------------------------------

_PREFIX_LEN = 32


def content_sha256(data: bytes) -> str:
    """Bare sha256 hex digest of raw content (the content address)."""
    return hashlib.sha256(data).hexdigest()


def static_object_id(digest: str) -> str:
    """Deterministic id of a static object from its content address (I-11)."""
    return f"SO-{digest[:_PREFIX_LEN]}"


def static_object_for(data: bytes, *, media_type: str, source_uri: str = "") -> StaticObject:
    """Build the content-addressed descriptor for raw evidence bytes.

    The descriptor is the pure-model surface of a document/photo/conversation:
    only content-address + type + size + provenance pointing at object storage
    (I-5 — the bytes themselves never enter the model).
    """
    digest = content_sha256(data)
    return StaticObject(
        object_id=static_object_id(digest),
        media_type=media_type,
        content_sha256=digest,
        byte_length=len(data),
        source_uri=source_uri,
    )


@dataclass(frozen=True)
class StaticObject:
    """Kind 2 graph object: content-addressed, immutable evidence leaf.

    Never a dynamic center: no lifecycle, no topology — only a descriptor that
    anchors evidence in object storage. ``object_id`` is derived from the
    content address, so identical bytes yield the identical id (I-11) and the
    object can never be edited in place (I-1). ``captured_at`` is the honest
    instant of capture where known (None = unknown, never fabricated).
    """

    object_id: str
    media_type: str
    content_sha256: str
    byte_length: int
    captured_at: datetime | None = None
    source_uri: str = ""
    kind: str = STATIC_OBJECT

    def __post_init__(self) -> None:
        if not self.object_id:
            raise ValueError("static object requires object_id")
        if not self.media_type:
            raise ValueError("static object requires media_type")
        if self.byte_length < 0:
            raise ValueError(f"byte_length must be >= 0, got {self.byte_length}")
        if self.captured_at is not None and self.captured_at.tzinfo is None:
            raise ValueError("captured_at must be timezone-aware (I-12)")

    @property
    def integrity_digest(self) -> str:
        """sha256 over the canonical descriptor JSON (rebuildable, I-12)."""
        return _digest_hex(_canonical_json(self.to_dict()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "object_id": self.object_id,
            "media_type": self.media_type,
            "content_sha256": self.content_sha256,
            "byte_length": self.byte_length,
            "captured_at": self.captured_at.isoformat() if self.captured_at else None,
            "source_uri": self.source_uri,
        }


# --------------------------------------------------------------------------
# Typed links — the ONLY way a dynamic invariant reaches a static object
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TypedLink:
    """Outbound typed edge from an invariant to an EXTERNAL artifact.

    The invariant embeds refs, never the target: ``target_id`` is the static
    object's ``SO-…`` content address (or equivalent external ref) and
    ``relation`` is the canonical vocabulary ``hasEvidence`` / ``depicts`` /
    ``inConversation`` (any non-empty relation is accepted for extension).
    """

    target_id: str
    relation: str
    target_kind: str = STATIC_OBJECT

    def __post_init__(self) -> None:
        if not self.target_id:
            raise ValueError("typed link requires target_id")
        if not self.relation:
            raise ValueError("typed link requires relation (hasEvidence/depicts/inConversation)")
        if not self.target_kind:
            raise ValueError("typed link requires target_kind")

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "relation": self.relation,
            "target_kind": self.target_kind,
        }


# --------------------------------------------------------------------------
# GraphInvariant — kind 1: the dynamic center of analysis
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class GraphInvariant:
    """A dynamic invariant: stream-anchored identity flowing through time.

    Blocks, exactly as specified: ``identity`` (entity_id, canonical stream
    anchor, type label, revision), ``lifecycle`` (ordered window slices),
    ``topology`` (degree, community, neighbor signature, per-window TDA
    proxies), ``evidence`` (observation count + content-addressed anchors +
    assertion ids), ``links`` (typed refs to EXTERNAL static objects — never
    their content), and ``provenance`` (I-12). ``integrity_digest`` content-
    addresses the whole projection so consumers verify what they analyzed.
    """

    identity: InvariantIdentity
    lifecycle: TemporalLifecycle
    topology: TopologicalState
    evidence: EvidenceBlock
    provenance: ProvenanceBlock
    links: tuple[TypedLink, ...] = ()
    kind: str = DYNAMIC_INVARIANT

    def __post_init__(self) -> None:
        if self.kind != DYNAMIC_INVARIANT:
            raise ValueError(f"kind must be {DYNAMIC_INVARIANT!r} for a GraphInvariant")
        object.__setattr__(
            self,
            "links",
            tuple(
                sorted(
                    self.links,
                    key=lambda link: (link.relation, link.target_id, link.target_kind),
                )
            ),
        )

    @property
    def content_id(self) -> str:
        """Short content address of this projection version (``GI-…``)."""
        return f"GI-{self.integrity_digest[:_PREFIX_LEN]}"

    @property
    def integrity_digest(self) -> str:
        """sha256 over the canonical invocation-independent projection JSON.

        Same events in any order (deduped, sorted) replay to a byte-identical
        digest — the rebuildability guarantee (I-11/I-12). The ``evt-`` spirit:
        derived ids come from content hashes, never from uuids.
        """
        return _digest_hex(_canonical_json(self.as_dict()))

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "identity": self.identity.to_dict(),
            "lifecycle": self.lifecycle.to_dict(),
            "topology": self.topology.to_dict(),
            "evidence": self.evidence.to_dict(),
            "links": [link.to_dict() for link in self.links],
            "provenance": self.provenance.to_dict(),
        }


def with_links(invariant: GraphInvariant, links: Sequence[TypedLink]) -> GraphInvariant:
    """Return a copy with the typed outgoing links replaced (immutable model).

    Attaching an evidence link changes the projection version (new digest) but
    never the identity block — links are external references, not identity.
    """
    return replace(invariant, links=tuple(links))


# --------------------------------------------------------------------------
# Deterministic builder — same events ⇒ same invariant
# --------------------------------------------------------------------------


def _entry_field(entry: Any, name: str) -> Any:
    if isinstance(entry, Mapping):
        return entry.get(name)
    return getattr(entry, name, None)


def _payload_of(entry: Any) -> dict[str, Any]:
    raw = _entry_field(entry, "payload")
    return dict(raw) if isinstance(raw, Mapping) else {}


def _canonical(obj: Any) -> Any:
    """JSON-canonical normalization (stable hashes across replays)."""
    if isinstance(obj, Mapping):
        return {str(k): _canonical(v) for k, v in sorted(obj.items())}
    if isinstance(obj, (list, tuple)):
        return [_canonical(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, StrEnum):
        return obj.value
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    return str(obj)


def _canonical_json(data: Any) -> str:
    return json.dumps(_canonical(data), sort_keys=True, separators=(",", ":"))


def _digest_hex(material: str) -> str:
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _stream_hash(entry: Any, ts: datetime) -> str:
    """Content address of ONE stream entry: declared hash or a canonical fallback.

    Uses the record's own ``record_hash`` verbatim when present (so the result
    matches ``evt-<record_hash>`` exactly); otherwise hashes the entry's
    payload-bearing material so identical entries collapse to one hash (I-11).
    """
    declared = _entry_field(entry, "record_hash")
    if declared:
        return str(declared)
    material = _canonical_json(
        {
            "ts": ts.isoformat(),
            "kind": str(_entry_field(entry, "kind") or ""),
            "sequence": int(_entry_field(entry, "sequence") or 0),
            "payload": _canonical(_payload_of(entry)),
        }
    )
    return _digest_hex(material)


def _burstiness(timestamps: Sequence[datetime]) -> float | None:
    """B = (σ/μ − 1)/(σ/μ + 1); None for fewer than 2 events (I-3 honesty)."""
    if len(timestamps) < 2:
        return None
    ordered = sorted(set(timestamps))
    if len(ordered) < 2:
        return 1.0
    deltas = [(b - a).total_seconds() for a, b in zip(ordered, ordered[1:], strict=False)]
    mean = sum(deltas) / len(deltas)
    if mean == 0.0:
        return 1.0
    variance = sum((d - mean) ** 2 for d in deltas) / len(deltas)
    ratio = math.sqrt(variance) / mean
    return (ratio - 1.0) / (ratio + 1.0)


def _slice_state(index: int, count: int, prev_count: int) -> LifecycleState:
    if count <= 0:
        return LifecycleState.DORMANT
    if index == 0:
        return LifecycleState.NASCENT
    high = prev_count * (1.0 + _LIFECYCLE_TOLERANCE)
    low = prev_count * (1.0 - _LIFECYCLE_TOLERANCE)
    if count > high:
        return LifecycleState.GROWING
    if count < low:
        return LifecycleState.DECAYING
    return LifecycleState.STABLE


def _window_community(entries: Sequence[tuple[Any, int]]) -> str:
    """Community label of one window: first asserted value in stream order.

    Entries are already stream-ordered; the first window entry that asserts a
    community wins (multiple assertions in one window resolve to the first —
    deterministic, documented). No assertion ⇒ "" (honestly unknown, I-3).
    """
    for entry, _ in entries:
        value = str(_payload_of(entry).get("community") or "")
        if value:
            return value
    return ""


def _neighbor_hints(entry: Any) -> list[tuple[str, float]]:
    payload = _payload_of(entry)
    raw = payload.get("neighbors")
    if raw is None:
        return []
    if isinstance(raw, Mapping):
        return [(str(nid), float(w)) for nid, w in raw.items()]
    items = raw if isinstance(raw, (list, tuple)) else [raw]
    return [(str(item), 1.0) for item in items if item not in (None, "")]


def from_entity_stream(
    entries: Sequence[Any],
    *,
    window: timedelta = timedelta(days=7),
    tenant_id: str = "default-tenant",
    type_label: str = "",
    revision: int = 1,
    community: str = "",
    links: Sequence[TypedLink] = (),
) -> GraphInvariant:
    """Deterministically derive the invariant from an entity's life-stream.

    Contract (mirrors ``fold_events``): the input is any sequence of mappings
    or objects exposing ``ts``/``kind``/``sequence``/``record_hash``/
    ``observation_id``/``payload`` (e.g. ``domain.dynamics.StreamRecord``).
    Entries are ordered by ``(sequence, ts, stream hash)``, so an accepted
    stream prefix remains stable when a later sequence carries an older event
    time. Exact duplicates are idempotent-deduped (I-11), so the same set of
    events in ANY input order replays to a byte-identical invariant. Timestamps
    must be tz-aware (I-12); temporal windows still use event time. The stream
    must be non-empty and single-tenant/single-entity (I-12).

    Neighbor/community hints are read from record payloads where present
    (``payload["neighbors"]`` as ``{id: weight}`` or id list, ``payload[
    "community"]``); the invariant's topology is the ego-star over those hints
    — the full relational graph remains the L2 adjacency's job.
    """
    if not window or window <= timedelta(0):
        raise ValueError(f"window must be positive, got {window!r}")

    prepared: list[tuple[str, datetime, int, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        ts = _entry_field(entry, "ts")
        if not isinstance(ts, datetime):
            raise ValueError(f"stream entry requires a datetime ts, got {ts!r}")
        if ts.tzinfo is None:
            raise ValueError("stream entry ts must be timezone-aware (I-12)")
        tenant = _entry_field(entry, "tenant_id")
        if tenant and str(tenant) != tenant_id:
            raise ValueError(f"tenant mismatch (I-12): {tenant} != {tenant_id}")
        stream_hash = _stream_hash(entry, ts)
        if stream_hash in seen:
            continue  # idempotent dedup (I-11)
        seen.add(stream_hash)
        sequence = int(_entry_field(entry, "sequence") or 0)
        prepared.append((stream_hash, ts, sequence, entry))

    if not prepared:
        raise ValueError("from_entity_stream requires >= 1 stream entry (identity source, I-3)")

    # Stream order is the accepted append order. Event time remains independent:
    # a late arrival sorts into its timestamp window without becoming genesis.
    prepared.sort(key=lambda item: (item[2], item[1], item[0]))

    entity_ids = {str(_entry_field(entry, "entity_id") or "") for _, _, _, entry in prepared}
    entity_ids.discard("")
    if len(entity_ids) != 1:
        raise ValueError("stream entries must share exactly one entity_id (I-6)")
    entity_id = entity_ids.pop()

    # identity block: genesis-grounded, stable across re-versioning
    genesis_hash, genesis_ts, _, _ = prepared[0]
    stream_anchor = f"evt-{genesis_hash}"
    label = type_label or str(_payload_of(prepared[0][3]).get("schema_name") or "")

    # evidence collection (refs only — content stays in object storage, I-5)
    observation_anchors: set[str] = set()
    content_digests: set[str] = set()
    assertion_ids: set[str] = set()
    for _, _, _, entry in prepared:
        obs = str(_entry_field(entry, "observation_id") or "")
        if obs and obs != "None":
            observation_anchors.add(obs)
        payload = _payload_of(entry)
        for key in ("digest", "content_sha256"):
            value = str(payload.get(key) or "")
            if value and value != "None":
                content_digests.add(value)
        single = str(payload.get("assertion_id") or "")
        plurals = payload.get("assertion_ids") or []
        for value in ([single] if single and single != "None" else []) + list(plurals):
            text = str(value)
            if text and text != "None":
                assertion_ids.add(text)

    # temporal fold: epoch-aligned windows from first to last event, gaps → dormant
    grouped: dict[tuple[datetime, datetime], list[tuple[Any, int]]] = {}
    for _, ts, sequence, entry in prepared:
        start, end = window_bounds(ts, window)
        grouped.setdefault((start, end), []).append((entry, sequence))
    spans: list[tuple[datetime, datetime]] = []
    if grouped:
        first_start = min(grouped)[0]
        last_end = max(grouped)[1]
        cursor = first_start
        while cursor < last_end:
            spans.append((cursor, cursor + window))
            cursor += window

    slices: list[TemporalSlice] = []
    topology_rows: list[WindowTopology] = []
    proxy_rows: list[TDAProxy] = []
    prev_count = 0
    for index, (start, end) in enumerate(spans):
        window_entries = grouped.get((start, end), [])  # gap window → dormant, no events
        timestamps = sorted(
            (_entry_field(entry, "ts") for entry, _ in window_entries), key=lambda t: t
        )
        count = len(timestamps)
        weights: dict[str, float] = {}
        for entry, _ in window_entries:
            for neighbor, weight in _neighbor_hints(entry):
                if neighbor == entity_id or not neighbor:
                    continue
                weights[neighbor] = weights.get(neighbor, 0.0) + weight
        neighbor_weights = tuple(sorted(weights.items(), key=lambda item: item[0]))
        community_label = community or _window_community(window_entries)

        days = max((end - start).total_seconds() / 86400.0, 1e-12)
        slices.append(
            TemporalSlice(
                window_start=start,
                window_end=end,
                state=_slice_state(index, count, prev_count),
                event_count=count,
                events_per_period=count / days,
                burstiness=_burstiness(timestamps),
                first_seen=timestamps[0] if timestamps else None,
                last_seen=timestamps[-1] if timestamps else None,
            )
        )
        topology_rows.append(
            WindowTopology(
                window_start=start,
                window_end=end,
                neighbor_weights=neighbor_weights,
                community=community_label,
            )
        )
        weight_sum = sum(w for _, w in weights.items()) if weights else 0.0
        ph0dm = max((1.0 / (1.0 + w) for _, w in weights.items()), default=0.0)
        proxy_rows.append(
            TDAProxy(
                window_start=start,
                window_end=end,
                h0_classes=len(weights) + 1,
                ph0dm=ph0dm,
                weight_sum=weight_sum,
            )
        )
        prev_count = count

    aggregate_community = community
    if not aggregate_community:
        ranks: dict[str, int] = {}
        for row in topology_rows:
            if row.community:
                ranks[row.community] = ranks.get(row.community, 0) + 1
        if ranks:
            top = max(sorted(ranks), key=lambda label: (ranks[label], label))
            aggregate_community = top  # mode with lexicographic tie-break

    neighbor_signature = tuple(
        sorted({nid for row in topology_rows for nid, _ in row.neighbor_weights})
    )

    source_hashes = tuple(stream_hash for stream_hash, _, _, _ in prepared)
    stream_head = _digest_hex("\n".join(source_hashes))

    return GraphInvariant(
        identity=InvariantIdentity(
            entity_id=entity_id,
            stream_anchor=stream_anchor,
            type_label=label,
            revision=revision,
        ),
        lifecycle=TemporalLifecycle(slices=tuple(slices)),
        topology=TopologicalState(
            degree=len(neighbor_signature),
            community=aggregate_community,
            neighbor_signature=neighbor_signature,
            window_topology=tuple(topology_rows),
            tda_proxy=tuple(proxy_rows),
        ),
        evidence=EvidenceBlock(
            observation_count=len(observation_anchors),
            observation_anchors=tuple(observation_anchors),
            content_digests=tuple(content_digests),
            assertion_ids=tuple(assertion_ids),
        ),
        provenance=ProvenanceBlock(
            tenant_id=tenant_id,
            event_id=f"evt-{stream_head}",
            observation_id=(
                str(_entry_field(prepared[0][3], "observation_id") or "") or ""
            ),
            stream_head=stream_head,
            source_hashes=source_hashes,
        ),
        links=tuple(links),
    )


# --------------------------------------------------------------------------
# TDA-readiness — same shapes as projection.adjacency.AdjacencyView.to_tda_input
# --------------------------------------------------------------------------


def to_tda_input(invariant: GraphInvariant) -> tuple[list[str], list[tuple[int, int, float]]]:
    """Persistence-input triples in the documented adjacency shape.

    Returns ``(node_ids, [(i, j, weight), ...])`` exactly like
    ``AdjacencyView.to_tda_input``: node ids sorted, indexes are positions in
    ``node_ids``, triples sorted deterministic (source is always the invariant's
    own node — this is the ego-star). Per-window weights are summed across
    windows (an aggregation, documented — the lossless per-window form is
    ``to_multiplex`` / ``window_tda_input``).
    """
    me = invariant.identity.entity_id
    nodes = sorted({me} | set(invariant.topology.neighbor_signature))
    lookup = {node: position for position, node in enumerate(nodes)}
    weights: dict[str, float] = {}
    for row in invariant.topology.window_topology:
        for neighbor, weight in row.neighbor_weights:
            weights[neighbor] = weights.get(neighbor, 0.0) + weight
    triples = [
        (lookup[me], lookup[neighbor], weights[neighbor])
        for neighbor in sorted(weights)
        if neighbor in lookup
    ]
    return nodes, triples


@dataclass(frozen=True)
class MultiplexLayer:
    """One time-layer of the invariant's ego-graph (multiplex-over-time).

    ``nodes``/``triples`` use the ``to_tda_input`` shape; a dormant window has
    the self node and no edges (honest, I-3). Layers align 1:1 with
    ``TemporalLifecycle.slices`` so L3 can compute per-window persistence and
    store only the FEATURES (barcodes/landscapes/PH0DM) as time series.
    """

    window_start: datetime
    window_end: datetime
    nodes: list[str]
    triples: list[tuple[int, int, float]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "nodes": list(self.nodes),
            "triples": [list(triple) for triple in self.triples],
        }


def _layer_tda_input(
    me: str, weights: dict[str, float]
) -> tuple[list[str], list[tuple[int, int, float]]]:
    nodes = sorted({me} | set(weights))
    lookup = {node: position for position, node in enumerate(nodes)}
    triples = [
        (lookup[me], lookup[neighbor], weights[neighbor])
        for neighbor in sorted(weights)
        if neighbor in lookup
    ]
    return nodes, triples


def window_tda_input(
    invariant: GraphInvariant, window_start: datetime
) -> tuple[list[str], list[tuple[int, int, float]]]:
    """Ego-star triples for ONE window (lossless per-window persistence input)."""
    me = invariant.identity.entity_id
    for row in invariant.topology.window_topology:
        if row.window_start == window_start:
            weights = dict(row.neighbor_weights)
            return _layer_tda_input(me, weights)
    return [me], []


def to_multiplex(invariant: GraphInvariant) -> tuple[MultiplexLayer, ...]:
    """Lossless multiplex-over-time layers, one per lifecycle slice (ordered)."""
    me = invariant.identity.entity_id
    by_window = {
        row.window_start: dict(row.neighbor_weights) for row in invariant.topology.window_topology
    }
    layers: list[MultiplexLayer] = []
    for slice_ in invariant.lifecycle.slices:
        weights = by_window.get(slice_.window_start, {})
        nodes, triples = _layer_tda_input(me, weights)
        layers.append(
            MultiplexLayer(
                window_start=slice_.window_start,
                window_end=slice_.window_end,
                nodes=nodes,
                triples=triples,
            )
        )
    return tuple(layers)


__all__ = [
    "DYNAMIC_INVARIANT",
    "STATIC_OBJECT",
    "TYPED_RELATIONS",
    "EvidenceBlock",
    "GraphInvariant",
    "InvariantIdentity",
    "LifecycleState",
    "MultiplexLayer",
    "ProvenanceBlock",
    "StaticObject",
    "TDAProxy",
    "TemporalLifecycle",
    "TemporalSlice",
    "TopologicalState",
    "TypedLink",
    "WindowTopology",
    "content_sha256",
    "from_entity_stream",
    "static_object_for",
    "static_object_id",
    "to_multiplex",
    "to_tda_input",
    "window_bounds",
    "window_tda_input",
    "with_links",
]