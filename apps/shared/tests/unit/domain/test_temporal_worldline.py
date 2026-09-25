"""Temporal worldline extraction tests (evidence, ordering, state, relations)."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest

from domain.dynamics import StreamAppendRejected, StreamRecord
from domain.temporal_worldline import (
    DEFAULT_CONFIDENCE,
    EntityWorldline,
    EventRelationKind,
    TimePrecision,
    WorldlineError,
    WorldlineEvidenceError,
    WorldlineTenantError,
    build_worldline,
    derive_cooccurrence_relations,
    derive_temporal_relations,
    event_order_key,
    extract_events,
    extract_worldlines,
    resolve_interval,
)

T0 = datetime(2024, 3, 1, 9, 0, tzinfo=UTC)
pytestmark = pytest.mark.unit


def record(
    kind: str,
    at: datetime,
    *,
    tenant: str = "t1",
    entity: str = "acme",
    obs: str | None = "obs-1",
    sequence: int = 0,
    **payload: object,
) -> StreamRecord:
    """One evidence-backed stream record (``obs=None`` drops the evidence)."""
    return StreamRecord(
        entity_id=entity,
        kind=kind,
        ts=at,
        tenant_id=tenant,
        payload=dict(payload),
        observation_id=f"{obs}-{kind}-{sequence}" if obs is not None else "",
        sequence=sequence,
    )


# --------------------------------------------------------------------------
# Evidence backing (I-3: no evidence, no event)
# --------------------------------------------------------------------------


def test_event_carries_evidence_refs_and_no_payload_blobs() -> None:
    events = extract_events(
        [record("transfer", T0, obs="obs-a", sequence=1, amount=100, currency="usd")],
        tenant_id="t1",
    )
    assert len(events) == 1
    event = events[0]
    assert event.evidence_backed is True
    ref = event.evidence[0]
    assert ref.observation_id == "obs-a-transfer-1"
    assert ref.dataset_id == ""
    assert ref.evidence_backed is True
    # Attributes are the record's own fields — never the source text.
    assert event.attributes == {"amount": 100, "currency": "usd"}
    assert event.to_dict()["evidence"][0]["source_record_id"] == ref.source_record_id


def test_record_without_observation_or_dataset_is_rejected() -> None:
    bare = StreamRecord(entity_id="acme", kind="transfer", ts=T0, tenant_id="t1")
    with pytest.raises(WorldlineEvidenceError):
        extract_events([bare], tenant_id="t1")
    # Opt-out is explicit, and the event then declares it is not backed.
    events = extract_events([bare], tenant_id="t1", require_evidence=False)
    assert events[0].evidence_backed is False
    assert events[0].confidence == DEFAULT_CONFIDENCE
    assert events[0].confidence_declared is False


def test_declared_confidence_is_marked_and_range_checked() -> None:
    events = extract_events(
        [
            record("transfer", T0, sequence=1, confidence=0.82),
            record("audit", T0 + timedelta(hours=1), sequence=2),
        ],
        tenant_id="t1",
    )
    assert events[0].confidence == 0.82
    assert events[0].confidence_declared is True
    assert events[1].confidence == DEFAULT_CONFIDENCE
    assert events[1].confidence_declared is False
    with pytest.raises(WorldlineError):
        extract_events([record("transfer", T0, confidence=1.7)], tenant_id="t1")


# --------------------------------------------------------------------------
# Deterministic, tenant-scoped ordering
# --------------------------------------------------------------------------


def test_event_order_is_independent_of_input_order() -> None:
    rows = [
        record("c", T0 + timedelta(days=2), sequence=1),
        record("a", T0, sequence=2),
        record("b", T0 + timedelta(days=1), sequence=3),
    ]
    forward = extract_events(rows, tenant_id="t1")
    backward = extract_events(list(reversed(rows)), tenant_id="t1")
    assert [e.event_type for e in forward] == ["a", "b", "c"]
    assert [e.event_id for e in forward] == [e.event_id for e in backward]
    assert [event_order_key(e) for e in forward] == sorted(event_order_key(e) for e in forward)


def test_precision_breaks_ties_and_stays_explicit() -> None:
    day = record("day_level", T0, sequence=1, occurred_at="2024-03-01")
    exact = record("exact", T0, sequence=2, occurred_at=T0.isoformat())
    events = extract_events([day, exact], tenant_id="t1")
    assert [e.event_type for e in events] == ["day_level", "exact"]
    assert events[0].interval.precision is TimePrecision.DAY
    assert events[1].interval.precision is TimePrecision.SECOND
    assert resolve_interval(record("x", T0, occurred_at="2024")).precision is TimePrecision.YEAR
    assert resolve_interval(record("x", T0, occurred_at="2024-03")).precision is TimePrecision.MONTH
    # A declared precision wins over the literal's shape...
    declared = record("x", T0, occurred_at="2024-03-01", time_precision="month")
    assert resolve_interval(declared).precision is TimePrecision.MONTH
    # ...and text that is not a date at all is refused, not guessed at.
    with pytest.raises(WorldlineError):
        resolve_interval(record("x", T0, occurred_at="last thursday"))


def test_naive_timestamp_is_rejected_not_localized() -> None:
    with pytest.raises(StreamAppendRejected):
        StreamRecord(entity_id="acme", kind="transfer", ts=datetime(2024, 3, 1), tenant_id="t1")
    with pytest.raises(WorldlineError):
        extract_events(
            [record("transfer", T0, occurred_at="2024-03-01 10:00")], tenant_id="t1"
        )


def test_cross_tenant_records_and_batches_are_refused() -> None:
    with pytest.raises(WorldlineTenantError):
        extract_events([record("transfer", T0, tenant="t2")], tenant_id="t1")
    mixed = [
        record("transfer", T0, tenant="t1"),
        record("transfer", T0, tenant="t2", entity="beta"),
    ]
    # A tenant is never guessed, and foreign records are never silently dropped.
    with pytest.raises(WorldlineTenantError):
        extract_worldlines(mixed)
    with pytest.raises(WorldlineTenantError):
        extract_worldlines(mixed, tenant_id="t1")
    assert [w.entity_id for w in extract_worldlines(mixed[:1], tenant_id="t1")] == ["acme"]


# --------------------------------------------------------------------------
# Idempotency (I-11)
# --------------------------------------------------------------------------


def test_replayed_records_are_deduplicated_and_ids_are_stable() -> None:
    rows = [
        record("transfer", T0, sequence=1),
        record("audit", T0 + timedelta(days=1), sequence=2),
    ]
    first = build_worldline(rows, tenant_id="t1", entity_id="acme")
    second = build_worldline(rows + rows, tenant_id="t1", entity_id="acme")
    third = build_worldline(list(reversed(rows)), tenant_id="t1", entity_id="acme")
    assert first.event_ids == second.event_ids == third.event_ids
    assert first.integrity_fingerprint == third.integrity_fingerprint
    assert second.source_record_ids == first.source_record_ids


def test_event_id_changes_when_evidence_content_changes() -> None:
    base = build_worldline(
        [record("transfer", T0, sequence=1, amount=10)], tenant_id="t1", entity_id="acme"
    )
    more = build_worldline(
        [record("transfer", T0, sequence=1, amount=11)], tenant_id="t1", entity_id="acme"
    )
    assert base.event_ids[0] != more.event_ids[0]
    assert base.integrity_fingerprint != more.integrity_fingerprint


# --------------------------------------------------------------------------
# Before/after state fold
# --------------------------------------------------------------------------


def test_before_and_after_state_track_the_fold() -> None:
    rows = [
        record("registered", T0, sequence=1, patch={"status": "active", "tier": "gold"}),
        record("moved", T0 + timedelta(days=1), sequence=2, patch={"tier": "platinum"}),
        record("closed", T0 + timedelta(days=2), sequence=3, patch={"status": None, "closed": True}),
    ]
    events = extract_events(rows, tenant_id="t1")
    assert [e.event_type for e in events] == ["registered", "moved", "closed"]
    assert events[0].before_state is None
    assert events[0].after_state.fields == {"status": "active", "tier": "gold"}
    assert events[1].before_state.fields == {"status": "active", "tier": "gold"}
    assert events[1].after_state.fields == {"status": "active", "tier": "platinum"}
    # ``None`` is an explicit removal, not a lingering value.
    assert events[2].after_state.fields == {"tier": "platinum", "closed": True}
    assert events[2].after_state.source_record_ids == tuple(
        events[1].after_state.source_record_ids
    ) + (events[2].source_record_ids[0],)


def test_state_snapshot_fingerprint_is_content_addressed() -> None:
    rows = [record("registered", T0, sequence=1, patch={"status": "active"})]
    first = extract_events(rows, tenant_id="t1")[0]
    second = extract_events(rows, tenant_id="t1")[0]
    assert first.after_state.fingerprint == second.after_state.fingerprint
    assert first.after_state.fingerprint.startswith("state-")


def test_records_without_state_never_fabricate_a_snapshot() -> None:
    events = extract_events([record("seen", T0, sequence=1)], tenant_id="t1")
    assert events[0].before_state is None
    assert events[0].after_state is None
    worldline = build_worldline(
        [record("seen", T0, sequence=1)], tenant_id="t1", entity_id="acme"
    )
    assert worldline.state_at(T0) is None
    assert worldline.state_at(T0 - timedelta(days=400)) is None


def test_state_at_returns_last_known_state_on_the_worldline() -> None:
    rows = [
        record("registered", T0, sequence=1, patch={"status": "active"}),
        record("moved", T0 + timedelta(days=10), sequence=2, patch={"tier": "gold"}),
    ]
    worldline = build_worldline(rows, tenant_id="t1", entity_id="acme")
    assert worldline.state_at(T0).fields == {"status": "active"}
    assert worldline.state_at(T0 + timedelta(days=9)).fields == {"status": "active"}
    assert worldline.state_at(T0 + timedelta(days=30)).fields == {
        "status": "active",
        "tier": "gold",
    }



# --------------------------------------------------------------------------
# Participants
# --------------------------------------------------------------------------


def test_participants_come_from_roles_lists_and_default_to_the_anchor() -> None:
    listed = extract_events(
        [
            record(
                "payment",
                T0,
                sequence=1,
                participants=[{"entity_id": "vendor-x", "role": "beneficiary"}, "notary-1"],
                actor="acme",
            )
        ],
        tenant_id="t1",
    )[0]
    assert listed.participant_ids() == ("acme", "notary-1", "vendor-x")
    assert {p.role for p in listed.participants if p.entity_id == "acme"} == {"actor"}
    assert listed.participant_ids(role="beneficiary") == ("vendor-x",)
    anchored = extract_events([record("seen", T0, sequence=2)], tenant_id="t1")[0]
    assert anchored.participant_ids() == ("acme",)


def test_participants_are_deduplicated_and_ordered() -> None:
    event = extract_events(
        [
            record(
                "payment",
                T0,
                sequence=1,
                participants=["zeta", "alpha", "alpha", "mid"],
                actor="zeta",
            )
        ],
        tenant_id="t1",
    )[0]
    assert [p.entity_id for p in event.participants] == ["alpha", "mid", "zeta", "zeta"]
    assert [p.role for p in event.participants if p.entity_id == "zeta"] == ["actor", "participant"]


# --------------------------------------------------------------------------
# Relations
# --------------------------------------------------------------------------


def test_temporal_relations_precede_follows_and_overlap() -> None:
    rows = [
        record("a", T0, sequence=1),
        record("b", T0 + timedelta(days=1), sequence=2),
        record(
            "c",
            T0 + timedelta(days=2),
            sequence=3,
            ended_at=(T0 + timedelta(days=3)).isoformat(),
        ),
        record(
            "d",
            T0 + timedelta(days=2, hours=6),
            sequence=4,
            ended_at=(T0 + timedelta(days=4)).isoformat(),
        ),
    ]
    events = extract_events(rows, tenant_id="t1")
    relations = derive_temporal_relations(events, tenant_id="t1")
    kinds = {(r.source_event_id, r.target_event_id): r.kind for r in relations}
    by_type = {e.event_type: e.event_id for e in events}
    assert kinds[(by_type["a"], by_type["b"])] is EventRelationKind.PRECEDES
    assert kinds[(by_type["b"], by_type["a"])] is EventRelationKind.FOLLOWS
    assert kinds[(by_type["c"], by_type["d"])] is EventRelationKind.OVERLAPS
    assert kinds[(by_type["d"], by_type["c"])] is EventRelationKind.OVERLAPS
    # a and c are disjoint, so they are ordered rather than overlapping.
    assert kinds[(by_type["a"], by_type["c"])] is EventRelationKind.PRECEDES
    precede = next(
        r
        for r in relations
        if r.source_event_id == by_type["a"] and r.target_event_id == by_type["b"]
    )
    assert precede.lag == (86400, 0)
    assert precede.is_declared is False
    assert precede.tenant_id == "t1"



def test_declared_causal_relations_are_marked_as_claims() -> None:
    target = record("transfer", T0 + timedelta(hours=2), sequence=1, obs="obs-target")
    source = record("approval", T0, sequence=2, obs="obs-source", causes=[target.record_id])
    events = extract_events([source, target], tenant_id="t1")
    by_id = {e.event_type: e.event_id for e in events}
    relations = derive_temporal_relations(events, tenant_id="t1")
    causal = [r for r in relations if r.kind is EventRelationKind.CAUSES]
    assert len(causal) == 1
    assert causal[0].source_event_id == by_id["approval"]
    assert causal[0].target_event_id == by_id["transfer"]
    assert causal[0].is_declared is True
    assert causal[0].cue == "declared_causes"


def test_dangling_causal_claim_produces_no_relation() -> None:
    events = extract_events(
        [record("approval", T0, sequence=1, causes="EV-does-not-exist")], tenant_id="t1"
    )
    assert [
        r
        for r in derive_temporal_relations(events, tenant_id="t1")
        if r.kind is EventRelationKind.CAUSES
    ] == []


def test_cooccurrence_relations_cross_entities_not_tenants() -> None:
    left = [record("meeting", T0, entity="acme", sequence=1, participants=["shared-x"])]
    right = [
        record(
            "transfer",
            T0 + timedelta(hours=1),
            entity="beta",
            sequence=1,
            participants=["shared-x"],
        )
    ]
    foreign = [
        record(
            "meeting", T0, entity="gamma", tenant="t2", sequence=1, participants=["shared-x"]
        )
    ]
    worldlines = [
        *extract_worldlines(left + right, tenant_id="t1"),
        *extract_worldlines(foreign, tenant_id="t2"),
    ]
    relations = derive_cooccurrence_relations(worldlines)
    assert len(relations) == 1
    assert relations[0].kind is EventRelationKind.CO_OCCURS
    assert {relations[0].source_entity_id, relations[0].target_entity_id} == {"acme", "beta"}
    assert relations[0].tenant_id == "t1"
    assert relations[0].cue == "participant:shared-x"
    assert relations[0].is_declared is False


def test_worldline_rejects_relations_pointing_outside_it() -> None:
    events = extract_events([record("a", T0, sequence=1)], tenant_id="t1")
    outside = extract_events([record("b", T0, entity="other", sequence=2)], tenant_id="t1")
    relation = derive_temporal_relations([*events, *outside], tenant_id="t1")[0]
    with pytest.raises(WorldlineError):
        EntityWorldline(
            tenant_id="t1",
            entity_id="acme",
            events=events,
            relations=(relation,),
        )


# --------------------------------------------------------------------------
# Point-in-time queries
# --------------------------------------------------------------------------


def test_event_at_and_events_between_respect_windows() -> None:
    rows = [
        record("a", T0, sequence=1),
        record(
            "b",
            T0 + timedelta(days=2),
            sequence=2,
            ended_at=(T0 + timedelta(days=5)).isoformat(),
        ),
    ]
    worldline = build_worldline(rows, tenant_id="t1", entity_id="acme")
    assert worldline.event_at(T0).event_type == "a"
    assert worldline.event_at(T0 + timedelta(days=3)).event_type == "b"
    assert worldline.event_at(T0 + timedelta(days=1)) is None
    assert worldline.event_at(T0 + timedelta(days=5)) is None
    inside = worldline.events_between(T0 + timedelta(days=1), T0 + timedelta(days=3))
    assert [e.event_type for e in inside] == ["b"]
    assert [e.event_type for e in worldline.events_between(T0, T0 + timedelta(days=1))] == ["a"]
    with pytest.raises(WorldlineError):
        worldline.event_at(datetime(2024, 3, 1))


def test_relations_of_filters_by_event_and_kind() -> None:
    worldline = build_worldline(
        [record("a", T0, sequence=1), record("b", T0 + timedelta(days=1), sequence=2)],
        tenant_id="t1",
        entity_id="acme",
    )
    first, second = worldline.events
    # ``relations_of`` looks both ways: the first event both precedes and is
    # followed by the second one.
    assert {r.kind for r in worldline.relations_of(first.event_id)} == {
        EventRelationKind.PRECEDES,
        EventRelationKind.FOLLOWS,
    }
    assert {r.kind for r in worldline.relations_of(second.event_id)} == {
        EventRelationKind.PRECEDES,
        EventRelationKind.FOLLOWS,
    }
    assert worldline.relations_of(first.event_id, kind=EventRelationKind.OVERLAPS) == ()
    assert len(worldline.relations_of("EV-nonexistent")) == 0


def test_empty_stream_yields_an_empty_but_valid_worldline() -> None:
    worldline = build_worldline([], tenant_id="t1", entity_id="acme")
    assert worldline.events == ()
    assert worldline.integrity_fingerprint.startswith("WL-")
    assert extract_worldlines([], tenant_id="t1") == ()

