"""Worldline store tests (idempotent ingest, tenant isolation, rebuildability)."""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest

from domain.dynamics import StreamRecord
from domain.temporal_worldline import (
    EventRelationKind,
    WorldlineError,
    WorldlineTenantError,
)
from domain.temporal_worldline_store import WorldlineStore

T0 = datetime(2024, 5, 1, 12, 0, tzinfo=UTC)
pytestmark = pytest.mark.unit


def record(
    kind: str,
    at: datetime,
    *,
    tenant: str = "t1",
    entity: str = "acme",
    sequence: int = 0,
    **payload: object,
) -> StreamRecord:
    return StreamRecord(
        entity_id=entity,
        kind=kind,
        ts=at,
        tenant_id=tenant,
        payload=dict(payload),
        observation_id=f"obs-{entity}-{kind}-{sequence}",
        dataset_id="ds-1",
        sequence=sequence,
    )


def stream() -> tuple[StreamRecord, ...]:
    return (
        record("registered", T0, sequence=1, patch={"status": "active"}),
        record(
            "sanctioned", T0 + timedelta(days=30), sequence=2, patch={"status": "sanctioned"}
        ),
        record("transfer", T0 + timedelta(days=40), entity="beta", sequence=3, actor="acme"),
    )


def test_append_builds_worldlines_and_reports_what_changed() -> None:
    store = WorldlineStore()
    result = store.append(stream(), tenant_id="t1")
    assert result.entity_ids == ("acme", "beta")
    assert len(result.new_event_ids) == 3
    assert result.changed is True
    assert result.replayed is False
    assert set(result.worldline_fingerprints) == {"acme", "beta"}
    assert store.entities(tenant_id="t1") == ("acme", "beta")
    assert store.tenants() == ("t1",)
    assert len(store) == 2


def test_replaying_the_same_records_changes_nothing() -> None:
    store = WorldlineStore()
    first = store.append(stream(), tenant_id="t1")
    before = store.fingerprint(tenant_id="t1")
    replay = store.append(stream(), tenant_id="t1")
    assert replay.replayed is True
    assert replay.changed is False
    # A pure replay touches no entity: nothing is folded, nothing is reported.
    assert replay.entity_ids == ()
    assert replay.new_event_ids == ()
    assert replay.unchanged_event_ids == ()
    assert store.fingerprint(tenant_id="t1") == before
    assert store.rebuild(tenant_id="t1") == 0
    assert set(first.new_event_ids) == set(store.event_index(tenant_id="t1"))


def test_mixed_batch_separates_new_records_from_replays() -> None:
    store = WorldlineStore()
    first = store.append(stream(), tenant_id="t1")
    acme_first = store.require(tenant_id="t1", entity_id="acme").events[0].event_id
    extra = record("closed", T0 + timedelta(days=60), sequence=4, patch={"status": "closed"})
    mixed = store.append([*stream(), extra], tenant_id="t1")
    assert mixed.replayed is True
    assert mixed.changed is True
    assert mixed.entity_ids == ("acme",)
    assert len(mixed.new_event_ids) == 1
    assert acme_first in mixed.unchanged_event_ids
    assert store.require(tenant_id="t1", entity_id="acme").event_ids[-1] == mixed.new_event_ids[0]


def test_late_record_folds_into_the_existing_worldline() -> None:
    store = WorldlineStore()
    store.append(stream()[:1], tenant_id="t1")
    before = store.require(tenant_id="t1", entity_id="acme")
    assert len(before.events) == 1
    result = store.append(stream()[1:2], tenant_id="t1")
    after = store.require(tenant_id="t1", entity_id="acme")
    assert result.entity_ids == ("acme",)
    assert len(after.events) == 2
    assert after.events[0].event_id in before.event_ids
    assert after.integrity_fingerprint != before.integrity_fingerprint
    assert store.state_at(
        tenant_id="t1", entity_id="acme", at=T0 + timedelta(days=31)
    ).fields == {"status": "sanctioned"}


def test_two_stores_fold_the_same_records_identically() -> None:
    forward, backward = WorldlineStore(), WorldlineStore()
    rows = stream()
    forward.append(rows, tenant_id="t1")
    backward.append(list(reversed(rows)), tenant_id="t1")
    assert forward.fingerprint(tenant_id="t1") == backward.fingerprint(tenant_id="t1")
    assert forward.to_dict(tenant_id="t1") == backward.to_dict(tenant_id="t1")


def test_cross_tenant_ingest_is_refused_and_tenants_stay_separate() -> None:
    store = WorldlineStore()
    with pytest.raises(WorldlineTenantError):
        store.append([record("registered", T0, tenant="t2")], tenant_id="t1")
    store.append(stream(), tenant_id="t1")
    store.append([record("seen", T0, tenant="t2")], tenant_id="t2")
    assert store.tenants() == ("t1", "t2")
    assert store.entities(tenant_id="t1") == ("acme", "beta")
    assert store.entities(tenant_id="t2") == ("acme",)
    assert store.fingerprint(tenant_id="t1") != store.fingerprint(tenant_id="t2")
    # A tenant can never read another tenant's worldline under its own key.
    assert store.get(tenant_id="t2", entity_id="beta") is None
    assert store.require(tenant_id="t1", entity_id="acme").tenant_id == "t1"


def test_state_and_event_queries_honour_windows() -> None:
    store = WorldlineStore()
    store.append(stream(), tenant_id="t1")
    assert store.state_at(tenant_id="t1", entity_id="acme", at=T0).fields == {"status": "active"}
    assert store.state_at(tenant_id="t1", entity_id="acme", at=T0 - timedelta(days=1)) is None
    assert store.state_at(tenant_id="t1", entity_id="unknown", at=T0) is None
    assert [
        e.event_type for e in store.events_at(tenant_id="t1", entity_id="acme", at=T0)
    ] == ["registered"]
    window = store.events(
        tenant_id="t1", start=T0 + timedelta(days=10), end=T0 + timedelta(days=35)
    )
    assert [e.event_type for e in window] == ["sanctioned"]
    assert [e.event_type for e in store.events(tenant_id="t1", entity_id="beta")] == ["transfer"]
    with pytest.raises(WorldlineError):
        store.events(tenant_id="t1", start=T0, end=T0 - timedelta(days=1))


def test_relations_include_cross_entity_cooccurrence() -> None:
    store = WorldlineStore()
    store.append(
        [
            record("meeting", T0, entity="acme", sequence=1, participants=["broker-7"]),
            record(
                "transfer",
                T0 + timedelta(hours=2),
                entity="beta",
                sequence=2,
                participants=["broker-7"],
            ),
        ],
        tenant_id="t1",
    )
    cross = store.relations_between(tenant_id="t1", entity_a="acme", entity_b="beta")
    assert len(cross) == 1
    assert cross[0].kind is EventRelationKind.CO_OCCURS
    assert cross[0].cue == "participant:broker-7"
    assert store.relations(tenant_id="t1", kind=EventRelationKind.CO_OCCURS) == cross
    # A pair that shares no participant is not related.
    assert store.relations_between(tenant_id="t1", entity_a="acme", entity_b="gamma") == ()


def test_relations_can_be_filtered_by_event() -> None:
    store = WorldlineStore()
    store.append(stream(), tenant_id="t1")
    acme = store.require(tenant_id="t1", entity_id="acme")
    first, second = acme.events
    # The first event precedes/follows the second, and co-occurs with beta's
    # transfer because that record names acme as its actor.
    assert {r.kind for r in store.relations(tenant_id="t1", event_id=first.event_id)} == {
        EventRelationKind.PRECEDES,
        EventRelationKind.FOLLOWS,
        EventRelationKind.CO_OCCURS,
    }
    precedes = store.relations(
        tenant_id="t1", event_id=second.event_id, kind=EventRelationKind.PRECEDES
    )
    # The query looks both ways, so the single PRECEDES edge is first -> second.
    assert len(precedes) == 1
    assert (precedes[0].source_event_id, precedes[0].target_event_id) == (
        first.event_id,
        second.event_id,
    )
    assert store.event_index(tenant_id="t1")[second.event_id].event_id == second.event_id


def test_source_records_are_exactly_what_is_needed_to_rebuild() -> None:
    store = WorldlineStore()
    store.append(stream(), tenant_id="t1")
    stored = store.source_records(tenant_id="t1", entity_id="acme")
    assert [r.record_id for r in stored] == sorted(r.record_id for r in stored)
    rebuilt = WorldlineStore()
    rebuilt.append(stored, tenant_id="t1")
    assert (
        rebuilt.require(tenant_id="t1", entity_id="acme").integrity_fingerprint
        == store.require(tenant_id="t1", entity_id="acme").integrity_fingerprint
    )


def test_evidence_free_records_are_refused_unless_opted_out() -> None:
    bare = StreamRecord(entity_id="acme", kind="seen", ts=T0, tenant_id="t1")
    with pytest.raises(WorldlineError):
        WorldlineStore().append([bare], tenant_id="t1")
    lenient = WorldlineStore(require_evidence=False)
    lenient.append([bare], tenant_id="t1")
    assert lenient.require(tenant_id="t1", entity_id="acme").events[0].evidence_backed is False
    with pytest.raises(WorldlineError):
        WorldlineStore().require(tenant_id="t1", entity_id="nobody")
    with pytest.raises(WorldlineError):
        WorldlineStore().append(stream(), tenant_id="")

