"""012: graph_invariant — determinism, windowing, 2-kind boundary, TDA shapes."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest

from domain.graph_invariant import (
    LifecycleState,
    TypedLink,
    content_sha256,
    from_entity_stream,
    static_object_for,
    to_multiplex,
    to_tda_input,
    window_bounds,
)

pytestmark = pytest.mark.unit

T0 = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)


def _entry(
    i: int,
    *,
    ts: datetime | None = None,
    obs: str | None = None,
    payload: dict | None = None,
    ent: str = "EA-1",
    kind: str = "mention",
    record_hash: str | None = None,
    tenant_id: str = "tenant-a",
) -> dict:
    return {
        "entity_id": ent,
        "kind": kind,
        "ts": ts if ts is not None else T0 + timedelta(hours=i),
        "sequence": i + 1,
        "observation_id": obs or f"obs-{i:04d}",
        "tenant_id": tenant_id,
        "record_hash": record_hash if record_hash is not None else f"rh-{i:04d}",
        "payload": payload or {},
    }


# -- determinism (I-11/I-12): same events ⇒ byte-identical digest ------------


def test_deterministic_same_input_same_digest() -> None:
    entries = [_entry(i) for i in range(5)]
    first = from_entity_stream(entries, tenant_id="tenant-a")
    second = from_entity_stream(entries, tenant_id="tenant-a")
    assert first.as_dict() == second.as_dict()
    assert first.integrity_digest == second.integrity_digest
    assert json.dumps(first.as_dict(), sort_keys=True) == json.dumps(
        second.as_dict(), sort_keys=True
    )


def test_digest_stable_under_input_reorder_and_duplicates() -> None:
    entries = [_entry(i) for i in range(6)]
    canonical = from_entity_stream(entries, tenant_id="tenant-a")
    shuffled = from_entity_stream(list(reversed(entries)), tenant_id="tenant-a")
    assert canonical.integrity_digest == shuffled.integrity_digest
    # exact duplicates are idempotent-deduped (I-11): a copy changes nothing
    with_copy = from_entity_stream(entries + [dict(entries[2])], tenant_id="tenant-a")
    assert canonical.integrity_digest == with_copy.integrity_digest


def test_content_id_is_prefix_of_digest() -> None:
    inv = from_entity_stream([_entry(0)], tenant_id="tenant-a")
    assert inv.content_id == f"GI-{inv.integrity_digest[:32]}"


# -- windowing arithmetic ----------------------------------------------------


def test_window_bounds_epoch_aligned() -> None:
    # Epoch-anchored: pick a timestamp ON a 7-day boundary (1970-01-01 + 2817*7d)
    # so the same-window expectation below holds for the epoch grid — the
    # calendar week (e.g. 2024-01-01, a Monday) is NOT an epoch-aligned boundary.
    boundary = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(days=7 * 2817)
    start, end = window_bounds(boundary, timedelta(days=7))
    assert start == boundary
    assert end - start == timedelta(days=7)
    assert start <= boundary < end
    # 3 days later is the same window; 8 days later is the next one
    assert window_bounds(boundary + timedelta(days=3), timedelta(days=7))[0] == start
    assert window_bounds(boundary + timedelta(days=8), timedelta(days=7))[0] == end


def test_window_bounds_requires_tz_and_positive_window() -> None:
    with pytest.raises(ValueError):
        window_bounds(datetime(2024, 1, 1), timedelta(days=7))
    with pytest.raises(ValueError):
        window_bounds(T0, timedelta(days=0))


def test_slices_ordered_and_bucketed() -> None:
    events = [_entry(0, ts=T0), _entry(1, ts=T0 + timedelta(minutes=1)), _entry(2, ts=T0 + HOUR)]
    inv = from_entity_stream(events, tenant_id="tenant-a", window=HOUR)
    slices = inv.lifecycle.slices
    assert len(slices) == 2
    assert [s.window_start for s in slices] == sorted(s.window_start for s in slices)
    assert slices[0].event_count == 2  # same-hour events land in one window
    assert slices[0].window_start <= T0 < slices[0].window_end
    assert slices[1].window_start == slices[0].window_end


# -- identity block: stable across re-versioning ----------------------------


def test_identity_stable_across_reversioning() -> None:
    def stream(n: int) -> list[dict]:
        return [_entry(i, payload={"schema_name": "Person"}) for i in range(n)]

    early = from_entity_stream(stream(4), tenant_id="tenant-a")
    grown = from_entity_stream(stream(8), tenant_id="tenant-a")
    assert early.identity.entity_id == grown.identity.entity_id == "EA-1"
    assert early.identity.stream_anchor == grown.identity.stream_anchor == "evt-rh-0000"
    assert early.identity.type_label == grown.identity.type_label == "Person"
    assert early.identity.revision == grown.identity.revision == 1
    # the projection version changed (more events), the identity did not
    assert early.integrity_digest != grown.integrity_digest
    assert early.provenance.stream_head != grown.provenance.stream_head


def test_late_arrival_with_older_event_time_keeps_stream_anchor() -> None:
    initial = [_entry(1), _entry(2)]
    late = _entry(0, ts=T0 - timedelta(minutes=30), record_hash="rh-0000-late")
    late["sequence"] = 4

    early = from_entity_stream(initial, tenant_id="tenant-a")
    grown = from_entity_stream(initial + [late], tenant_id="tenant-a")
    reordered = from_entity_stream(list(reversed(initial + [late])), tenant_id="tenant-a")

    assert early.identity.stream_anchor == "evt-rh-0001"
    assert grown.identity.stream_anchor == early.identity.stream_anchor
    assert reordered.identity.stream_anchor == early.identity.stream_anchor
    assert grown.integrity_digest == reordered.integrity_digest


def test_late_arrival_appends_to_stream_ordered_provenance() -> None:
    initial = [_entry(1), _entry(2)]
    late = _entry(0, ts=T0 - timedelta(minutes=30), record_hash="rh-0000-late")
    late["sequence"] = 4
    entries = initial + [late]

    early = from_entity_stream(initial, tenant_id="tenant-a")
    grown = from_entity_stream(entries, tenant_id="tenant-a")
    reordered = from_entity_stream(list(reversed(entries)), tenant_id="tenant-a")
    expected_order = ("rh-0001", "rh-0002", "rh-0000-late")
    expected_head = hashlib.sha256("\n".join(expected_order).encode()).hexdigest()

    assert early.provenance.source_hashes == expected_order[:2]
    assert grown.provenance.source_hashes == expected_order
    assert grown.provenance.source_hashes == reordered.provenance.source_hashes
    assert grown.provenance.stream_head == expected_head
    assert grown.provenance.event_id == f"evt-{expected_head}"


def test_revision_bump_changes_digest_not_identity() -> None:
    inv = from_entity_stream([_entry(i) for i in range(3)], tenant_id="tenant-a", revision=3)
    assert inv.identity.revision == 3
    assert inv.identity.entity_id == "EA-1"


# -- lifecycle states + honest cadence -------------------------------------


def test_lifecycle_states_derived_deterministically() -> None:
    def at(hour: int, n: int) -> list[dict]:
        return [
            _entry(hour * 10 + j, ts=T0 + HOUR * hour + timedelta(minutes=j))
            for j in range(n)
        ]

    entries = at(0, 3) + at(1, 5) + at(2, 3) + at(4, 3)  # window 3 is an empty gap
    inv = from_entity_stream(entries, tenant_id="tenant-a", window=HOUR)
    states = [s.state for s in inv.lifecycle.slices]
    assert states == [
        LifecycleState.NASCENT,
        LifecycleState.GROWING,
        LifecycleState.DECAYING,
        LifecycleState.DORMANT,
        LifecycleState.GROWING,
    ]
    assert len(inv.lifecycle.active_slices) == 4
    assert inv.lifecycle.state == LifecycleState.GROWING


def test_burstiness_honest_empty_and_max() -> None:
    entries = [
        _entry(0, ts=T0),
        _entry(1, ts=T0 + HOUR),
        _entry(2, ts=T0 + HOUR),  # two events in the second window, same instant
    ]
    inv = from_entity_stream(entries, tenant_id="tenant-a", window=HOUR)
    assert inv.lifecycle.slices[0].burstiness is None  # <2 events ⇒ no number (I-3)
    assert inv.lifecycle.slices[1].burstiness == 1.0  # identical inter-arrival ⇒ max burst


def test_static_object_never_fabricates_events() -> None:
    inv = from_entity_stream([_entry(0, ts=T0)], tenant_id="tenant-a", window=HOUR)
    assert inv.lifecycle.slices[0].events_per_period > 0.0
    assert inv.lifecycle.slices[0].first_seen == T0
    assert inv.lifecycle.slices[0].last_seen == T0


# -- static object: kind-2 content addressing + immutability ----------------


def test_static_object_content_addressing_and_immutability() -> None:
    data_a = b"CONFIDENTIAL LEAK DOCUMENT v1"
    first = static_object_for(data_a, media_type="text/plain", source_uri="s3://bucket/obj")
    second = static_object_for(data_a, media_type="text/plain")
    assert first.object_id == second.object_id  # same bytes ⇒ same id (I-11)
    assert first.object_id == f"SO-{content_sha256(data_a)[:32]}"
    assert first.content_sha256 == content_sha256(data_a)
    assert first.byte_length == len(data_a)
    other = static_object_for(b"CONFIDENTIAL LEAK DOCUMENT v2", media_type="text/plain")
    assert other.object_id != first.object_id
    # immutable leaf: no in-place edit, characteristic descriptor fields only
    with pytest.raises(FrozenInstanceError):
        first.byte_length = 0  # type: ignore[misc]


def test_static_object_descriptor_has_no_text() -> None:
    secret = "MEMO: NUCLEAR LAUNDRY PROTOCOL"
    obj = static_object_for(secret.encode("utf-8"), media_type="text/plain")
    descriptor = obj.to_dict()
    serialized = json.dumps(descriptor)
    assert secret not in serialized
    # only a descriptor, never content (I-5): fixed key set with no payload field
    assert set(descriptor) == {
        "kind",
        "object_id",
        "media_type",
        "content_sha256",
        "byte_length",
        "captured_at",
        "source_uri",
    }
    assert descriptor["byte_length"] == len(secret.encode("utf-8"))


# -- embedded-vs-linked boundary --------------------------------------------


def test_person_invariant_embeds_anchors_but_not_document_text() -> None:
    secret_text = "MEMO: THE IP OF THE URANIUM ACCOUNT IS 74.x"
    doc = static_object_for(
        secret_text.encode("utf-8"), media_type="text/plain", source_uri="s3://bucket/leak"
    )
    payload = {
        "schema_name": "Person",
        "assertion_id": "asrt-1",
        "digest": "deadbeef",
        "neighbors": {"N-1": 2.0, "N-2": 1.0},
        "community": "crypto",
    }
    entries = [_entry(0, obs="obs-evid", payload=payload)]
    inv = from_entity_stream(
        entries,
        tenant_id="tenant-a",
        links=[TypedLink(doc.object_id, "hasEvidence")],
    )
    serialized = json.dumps(inv.as_dict())
    # embedded: evidence anchors + assertion id + observation count
    assert inv.evidence.observation_count == 1
    assert inv.evidence.observation_anchors == ("obs-evid",)
    assert inv.evidence.content_digests == ("deadbeef",)
    assert inv.evidence.assertion_ids == ("asrt-1",)
    assert "obs-evid" in serialized and "asrt-1" in serialized
    # linked only: the static object appears as an SO- ref on a typed edge, never its text
    assert doc.object_id in serialized
    assert "hasEvidence" in serialized
    assert secret_text not in serialized
    assert [link.target_id for link in inv.links] == [doc.object_id]
    assert inv.topology.neighbor_signature == ("N-1", "N-2")
    assert inv.topology.community == "crypto"
    assert all(proxy.structural_only for proxy in inv.topology.tda_proxy)


def test_typed_link_requires_target_and_relation() -> None:
    with pytest.raises(ValueError):
        TypedLink("", "hasEvidence")
    with pytest.raises(ValueError):
        TypedLink("SO-abc", "")


# -- errors under stream discipline (I-8/I-12) -------------------------------


def test_empty_stream_rejected() -> None:
    with pytest.raises(ValueError):
        from_entity_stream([])


def test_naive_timestamps_rejected() -> None:
    entry = {"entity_id": "EA-1", "kind": "mention", "ts": datetime(2024, 1, 1), "sequence": 1}
    with pytest.raises(ValueError):
        from_entity_stream([entry])


def test_tenant_and_entity_mismatch_rejected() -> None:
    with pytest.raises(ValueError):
        from_entity_stream([_entry(0, tenant_id="tenant-b")], tenant_id="tenant-a")
    foreign = _entry(1)
    foreign["entity_id"] = "EA-2"
    with pytest.raises(ValueError):
        from_entity_stream([_entry(0), foreign], tenant_id="tenant-a")


# -- provenance block --------------------------------------------------------


def test_provenance_block_conventions() -> None:
    entries = [_entry(i) for i in range(3)]
    inv = from_entity_stream(entries, tenant_id="tenant-a")
    assert inv.provenance.tenant_id == "tenant-a"
    assert inv.provenance.source_hashes == tuple(sorted("rh-0000 rh-0001 rh-0002".split()))
    assert inv.provenance.event_id == f"evt-{inv.provenance.stream_head}"
    assert inv.identity.stream_anchor == "evt-rh-0000"  # evt-<record_hash> spirit
    assert inv.provenance.builder == "graph_invariant.from_entity_stream"


# -- TDA-readiness: adjacency-compatible triples + multiplex -----------------


def test_to_tda_input_shape_and_weight_merge() -> None:
    entries = [
        _entry(0, ts=T0, payload={"neighbors": {"N-1": 2.0, "N-2": 1.0}}),
        _entry(1, ts=T0 + timedelta(minutes=1), payload={"neighbors": {"N-2": 1.0}}),
        _entry(2, ts=T0 + HOUR, payload={"neighbors": {"N-1": 3.0}}),
    ]
    inv = from_entity_stream(entries, tenant_id="tenant-a", window=HOUR)
    nodes, triples = to_tda_input(inv)
    assert isinstance(nodes, list) and all(isinstance(n, str) for n in nodes)
    assert isinstance(triples, list) and all(len(t) == 3 for t in triples)
    assert nodes == ["EA-1", "N-1", "N-2"]
    me = nodes.index("EA-1")
    # weights merged across windows: N-1 = 2 + 3, N-2 = 1 + 1
    assert triples == [
        (me, nodes.index("N-1"), 5.0),
        (me, nodes.index("N-2"), 2.0),
    ]
    assert to_tda_input(inv) == (nodes, triples)


def test_to_multiplex_layers_align_with_slices() -> None:
    entries = [
        _entry(0, ts=T0, payload={"neighbors": {"N-1": 1.0}}),
        _entry(1, ts=T0 + HOUR, payload={"neighbors": {"N-1": 2.0, "N-2": 1.0}}),
    ]
    inv = from_entity_stream(entries, tenant_id="tenant-a", window=HOUR)
    layers = to_multiplex(inv)
    assert len(layers) == len(inv.lifecycle.slices)
    for layer, slice_ in zip(layers, inv.lifecycle.slices, strict=True):
        assert layer.window_start == slice_.window_start
        assert layer.window_end == slice_.window_end
        assert "EA-1" in layer.nodes
        if slice_.state == LifecycleState.DORMANT:
            assert layer.triples == []