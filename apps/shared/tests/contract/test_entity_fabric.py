"""Feature-009 contract tests: atomic entity fabric (stream-first).

Covers the process-centric atomic entity: stream identity (append-only
life-stream), deterministic rebuildable fold (I-11/I-12), temporal time
series, hyperedge-first occurrences, and provenance/tenant invariants
(I-1/I-2/I-5/I-6/I-12).
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parents[3]
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from domain.dynamics import (  # noqa: E402
    EntityClass,
    SeriesStats,
    StreamAppendRejected,
    StreamRecord,
    apply_event,
    build_series,
    classify_entity,
    fold_events,
)
from domain.hypergraph import HyperEdge, HyperGraph  # noqa: E402

T0 = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


# --------------------------------------------------------------------------
# Ontology: the separation question
# --------------------------------------------------------------------------


class TestEntityClassification:
    def test_person_is_dynamic_continuant(self) -> None:
        assert classify_entity("Person") is EntityClass.DYNAMIC_CONTINUANT

    def test_document_is_artifact_continuant(self) -> None:
        # The document-evidence anchors hyperedges; it does not act.
        assert classify_entity("Document") is EntityClass.ARTIFACT_CONTINUANT

    def test_event_is_occurrence(self) -> None:
        # An occurrence is a hyperedge over participants, never an entity node.
        assert classify_entity("Event") is EntityClass.OCCURRENCE

    def test_unknown_defaults_to_unknown(self) -> None:
        # An unregistered schema is UNKNOWN — never silently DYNAMIC.
        assert classify_entity("NovelSchema") is EntityClass.UNKNOWN

    def test_registry_override(self) -> None:
        from domain.dynamics import EntityClassRegistry

        reg = EntityClassRegistry({"NovelSchema": EntityClass.DYNAMIC_CONTINUANT})
        assert classify_entity("NovelSchema", registry=reg) is EntityClass.DYNAMIC_CONTINUANT
        # the global registry is untouched
        assert classify_entity("NovelSchema") is EntityClass.UNKNOWN


# --------------------------------------------------------------------------
# Stream record: the atomic event
# --------------------------------------------------------------------------


class TestStreamRecord:
    def test_requires_entity_kind_tenant_and_tz(self) -> None:
        with pytest.raises(StreamAppendRejected):
            StreamRecord(entity_id="", kind="mention", ts=T0)
        with pytest.raises(StreamAppendRejected):
            StreamRecord(entity_id="E-1", kind="", ts=T0)
        with pytest.raises(StreamAppendRejected):
            StreamRecord(entity_id="E-1", kind="mention", ts=T0, tenant_id="")
        naive = datetime(2026, 9, 20, 12, 0)
        with pytest.raises(StreamAppendRejected):
            StreamRecord(entity_id="E-1", kind="mention", ts=naive)

    def test_hash_is_deterministic_and_content_bound(self) -> None:
        a = StreamRecord(entity_id="E-1", kind="mention", ts=T0, sequence=1)
        b = StreamRecord(entity_id="E-1", kind="mention", ts=T0, sequence=1)
        c = StreamRecord(entity_id="E-1", kind="mention", ts=T0, sequence=2)
        assert a.record_hash == b.record_hash
        assert a.record_hash != c.record_hash
        # from_dict round-trip preserves the hash (replay stability)
        d = StreamRecord.from_dict(a.to_dict())
        assert d.record_hash == a.record_hash

    def test_hash_covers_temporal_validity(self) -> None:
        # valid_from / valid_until are part of the atomic fact — two facts that
        # differ only in temporal validity must NOT share a provenance hash.
        base = {"property": "x", "value": "1"}
        no_window = StreamRecord(
            entity_id="E-1", kind="property.set", ts=T0, payload=base, sequence=1
        )
        from_window = StreamRecord(
            entity_id="E-1",
            kind="property.set",
            ts=T0,
            payload=base,
            valid_from=T0,
            sequence=1,
        )
        full_window = StreamRecord(
            entity_id="E-1",
            kind="property.set",
            ts=T0,
            payload=base,
            valid_from=T0,
            valid_until=T0 + timedelta(days=1),
            sequence=1,
        )
        assert no_window.record_hash != from_window.record_hash
        assert no_window.record_hash != full_window.record_hash
        assert from_window.record_hash != full_window.record_hash
        # round-trip stays hash-stable after the fix
        assert StreamRecord.from_dict(from_window.to_dict()).record_hash == from_window.record_hash
        assert StreamRecord.from_dict(full_window.to_dict()).record_hash == full_window.record_hash


# --------------------------------------------------------------------------
# The fold: state = deterministic function of the stream
# --------------------------------------------------------------------------


def _life() -> list[StreamRecord]:
    return [
        StreamRecord(
            entity_id="E-1",
            kind="property.set",
            ts=T0,
            payload={"property": "name", "value": "Alice"},
            sequence=1,
        ),
        StreamRecord(
            entity_id="E-1",
            kind="property.set",
            ts=T0 + timedelta(hours=1),
            payload={"property": "alias", "value": "A."},
            sequence=2,
        ),
        StreamRecord(
            entity_id="E-1",
            kind="mention",
            ts=T0 + timedelta(hours=2),
            sequence=3,
        ),
        StreamRecord(
            entity_id="E-1",
            kind="property.set",
            ts=T0 + timedelta(hours=3),
            payload={"property": "alias", "value": "B."},
            sequence=4,
        ),
    ]


class TestFold:
    def test_extensible_property_accumulates(self) -> None:
        state = fold_events("E-1", _life(), schema_name="Person")
        assert state.props["alias"].values == ["A.", "B."]
        assert state.props["name"].values == ["Alice"]

    def test_replay_is_deterministic(self) -> None:
        s1 = fold_events("E-1", _life(), schema_name="Person")
        s2 = fold_events("E-1", _life(), schema_name="Person")
        assert s1.head_hash == s2.head_hash
        assert s1.revision == s2.revision
        assert s1.event_count == s2.event_count

    def test_identity_resolve_is_only_identity_source(self) -> None:
        events = _life() + [
            StreamRecord(
                entity_id="E-1",
                kind="identity.resolve",
                ts=T0 + timedelta(hours=4),
                payload={"resolved_id": "ENT-42", "method": "exact"},
                sequence=5,
            ),
        ]
        state = fold_events("E-1", events, schema_name="Person")
        assert state.resolution["resolved_id"] == "ENT-42"
        # single-step fold matches batch fold (streaming hot path)
        live = fold_events("E-1", events[:-1], schema_name="Person")
        apply_event(live, events[-1])
        assert live.resolution["resolved_id"] == "ENT-42"
        assert live.head_hash == state.head_hash

    def test_freeze_enforces_artifact_discipline(self) -> None:
        events = _life() + [
            StreamRecord(
                entity_id="E-1",
                kind="entity.freeze",
                ts=T0 + timedelta(hours=4),
                sequence=5,
            ),
        ]
        state = fold_events("E-1", events, schema_name="Person")
        assert state.frozen and state.frozen_at == T0 + timedelta(hours=4)
        events.append(
            StreamRecord(
                entity_id="E-1",
                kind="property.set",
                ts=T0 + timedelta(hours=5),
                payload={"property": "name", "value": "Bob"},
                sequence=6,
            ),
        )
        with pytest.raises(StreamAppendRejected, match="frozen"):
            fold_events("E-1", events, schema_name="Person")

    def test_sequence_regression_rejected(self) -> None:
        events = [
            StreamRecord(entity_id="E-1", kind="mention", ts=T0, sequence=2),
            StreamRecord(entity_id="E-1", kind="mention", ts=T0, sequence=1),
        ]
        with pytest.raises(StreamAppendRejected, match="sequence regression"):
            fold_events("E-1", events, schema_name="Person")

    def test_hash_corruption_detected(self) -> None:
        rec = StreamRecord(entity_id="E-1", kind="mention", ts=T0, sequence=1)
        corrupt = StreamRecord(
            entity_id="E-1", kind="mention", ts=T0, sequence=1, record_hash="deadbeef"
        )
        with pytest.raises(StreamAppendRejected, match="corrupted"):
            fold_events("E-1", [rec, corrupt], schema_name="Person")

    def test_tenant_isolation_enforced(self) -> None:
        foreign = StreamRecord(
            entity_id="E-1", kind="mention", ts=T0, tenant_id="other", sequence=1
        )
        with pytest.raises(StreamAppendRejected, match="tenant"):
            fold_events("E-1", [foreign], schema_name="Person", tenant_id="default-tenant")

    def test_foreign_entity_rejected(self) -> None:
        other = StreamRecord(entity_id="E-9", kind="mention", ts=T0, sequence=1)
        with pytest.raises(StreamAppendRejected, match="foreign"):
            fold_events("E-1", [other], schema_name="Person")

    def test_apply_event_sequence_regression_rejected(self) -> None:
        # the single-step hot path must enforce stream order exactly like the
        # batch fold (previously only fold_events checked monotonicity).
        state = fold_events("E-1", [], schema_name="Person")
        apply_event(state, StreamRecord(entity_id="E-1", kind="mention", ts=T0, sequence=2))
        assert state.last_sequence == 2
        with pytest.raises(StreamAppendRejected, match="sequence regression"):
            apply_event(state, StreamRecord(entity_id="E-1", kind="mention", ts=T0, sequence=2))
        with pytest.raises(StreamAppendRejected, match="sequence regression"):
            apply_event(state, StreamRecord(entity_id="E-1", kind="mention", ts=T0, sequence=1))

    def test_extensible_false_pins_slot_and_archives_history(self) -> None:
        events = [
            StreamRecord(
                entity_id="E-1",
                kind="property.set",
                ts=T0,
                payload={"property": "alias", "value": "A."},
                sequence=1,
            ),
            StreamRecord(
                entity_id="E-1",
                kind="property.set",
                ts=T0 + timedelta(hours=1),
                payload={"property": "alias", "value": "B."},
                sequence=2,
            ),
            StreamRecord(
                entity_id="E-1",
                kind="property.set",
                ts=T0 + timedelta(hours=2),
                payload={"property": "alias", "value": "C.", "extensible": False},
                sequence=3,
            ),
        ]
        state = fold_events("E-1", events, schema_name="Person")
        slot = state.props["alias"]
        assert slot.value == "C."
        assert slot.extensible is False
        assert slot.values == ["C."]
        # the accumulated variants went to history, not into the void
        assert len(state.history["alias"]) == 1
        hist = state.history["alias"][0]
        assert hist.values == ["A.", "B."]
        assert hist.active is False

        # a pinned slot supersedes on new value and archives the old one
        supersede = StreamRecord(
            entity_id="E-1",
            kind="property.set",
            ts=T0 + timedelta(hours=3),
            payload={"property": "alias", "value": "D."},
            sequence=4,
        )
        state2 = fold_events("E-1", events + [supersede], schema_name="Person")
        assert state2.props["alias"].value == "D."
        assert state2.props["alias"].extensible is False
        assert [h.value for h in state2.history["alias"]] == ["A.", "C."]

        # identical re-assertion on a pinned slot is idempotent (I-11)
        echo = StreamRecord(
            entity_id="E-1",
            kind="property.set",
            ts=T0 + timedelta(hours=4),
            payload={"property": "alias", "value": "D."},
            sequence=5,
        )
        state3 = fold_events("E-1", events + [supersede, echo], schema_name="Person")
        assert len(state3.history["alias"]) == 2
        assert state3.props["alias"].value == "D."

    def test_extensible_false_history_rebuilds_deterministically(self) -> None:
        events = [
            StreamRecord(
                entity_id="E-1",
                kind="property.set",
                ts=T0,
                payload={"property": "alias", "value": "A."},
                sequence=1,
            ),
            StreamRecord(
                entity_id="E-1",
                kind="property.set",
                ts=T0 + timedelta(hours=1),
                payload={"property": "alias", "value": "B.", "extensible": False},
                sequence=2,
            ),
        ]
        batch = fold_events("E-1", events, schema_name="Person")
        live = fold_events("E-1", events[:1], schema_name="Person")
        apply_event(live, events[1])
        # single-step fold equals batch fold, including the archived history
        assert live.props["alias"].value == batch.props["alias"].value
        assert live.props["alias"].extensible is False
        assert [h.values for h in live.history["alias"]] == [
            h.values for h in batch.history["alias"]
        ]
        assert live.head_hash == batch.head_hash

    def test_valuation_spine_preserves_per_value_temporal_validity(self) -> None:
        # Block B: each assertion keeps its own validity window + provenance,
        # so "which value was effective at time t" is answerable.
        events = [
            StreamRecord(
                entity_id="E-1",
                kind="property.set",
                ts=T0,
                payload={"property": "alias", "value": "A."},
                sequence=1,
            ),
            StreamRecord(
                entity_id="E-1",
                kind="property.set",
                ts=T0 + timedelta(hours=1),
                payload={"property": "alias", "value": "B."},
                sequence=2,
            ),
        ]
        state = fold_events("E-1", events, schema_name="Person")
        slot = state.props["alias"]
        assert slot.valuations[0].value == "A."
        assert slot.valuations[0].valid_from == T0
        assert slot.valuations[1].value == "B."
        assert slot.valuations[1].valid_from == T0 + timedelta(hours=1)
        # values stays a convenience over the spine
        assert slot.values == ["A.", "B."]
        # temporal queries: slot was "A." at T0+30min, "B." afterwards
        assert slot.value_at(T0 + timedelta(minutes=30)) == "A."
        assert slot.value_at(T0 + timedelta(hours=2)) == "B."
        assert slot.valuations_at(T0 + timedelta(minutes=30)) == [slot.valuations[0]]
        # end-to-end fold is deterministic with the spine
        again = fold_events("E-1", events, schema_name="Person")
        assert again.props["alias"].to_dict() == slot.to_dict()
        assert again.head_hash == state.head_hash

    def test_freeze_blocks_every_mutation_kind(self) -> None:
        # Block E: freeze is terminal for counters and resolution too, not only
        # for property mutations.
        events = [
            StreamRecord(entity_id="E-1", kind="mention", ts=T0, sequence=1),
            StreamRecord(
                entity_id="E-1",
                kind="entity.freeze",
                ts=T0 + timedelta(hours=1),
                sequence=2,
            ),
        ]
        frozen = fold_events("E-1", events, schema_name="Person")
        assert frozen.frozen
        mention_after = StreamRecord(
            entity_id="E-1", kind="mention", ts=T0 + timedelta(hours=2), sequence=3
        )
        with pytest.raises(StreamAppendRejected, match="frozen"):
            fold_events("E-1", events + [mention_after], schema_name="Person")

        resolve_after = StreamRecord(
            entity_id="E-1",
            kind="identity.resolve",
            ts=T0 + timedelta(hours=2),
            payload={"resolved_id": "ENT-9"},
            sequence=3,
        )
        with pytest.raises(StreamAppendRejected, match="frozen"):  # noqa: SIM105
            fold_events("E-1", events + [resolve_after], schema_name="Person")

        # double-frozen is a stream violation
        double = StreamRecord(
            entity_id="E-1", kind="entity.freeze", ts=T0 + timedelta(hours=2), sequence=3
        )
        with pytest.raises(StreamAppendRejected, match="twice"):
            fold_events("E-1", events + [double], schema_name="Person")

    def test_resolution_history_preserves_changes(self) -> None:
        # Block D: identity.resolve records the previous claim into history
        # instead of silently overwriting (I-6).
        events = [
            StreamRecord(
                entity_id="E-1",
                kind="identity.resolve",
                ts=T0,
                payload={"resolved_id": "ENT-1", "method": "exact"},
                sequence=1,
            ),
            StreamRecord(
                entity_id="E-1",
                kind="identity.resolve",
                ts=T0 + timedelta(hours=1),
                payload={"resolved_id": "ENT-2", "method": "fuzzy"},
                sequence=2,
            ),
        ]
        state = fold_events("E-1", events, schema_name="Person")
        assert state.resolution["resolved_id"] == "ENT-2"
        assert len(state.resolution_history) == 1
        assert state.resolution_history[0]["resolved_id"] == "ENT-1"
        assert state.resolution_history[0]["method"] == "exact"
        # rebuild identical
        again = fold_events("E-1", events, schema_name="Person")
        assert again.resolution_history == state.resolution_history

    def test_expire_closes_slot_terminal_and_archives(self) -> None:
        # Block D: property.expire pops the slot into history with the record's
        # validity end (event ts, respecting rec.valid_until) — never last_seen.
        events = [
            StreamRecord(
                entity_id="E-1",
                kind="property.set",
                ts=T0,
                payload={"property": "email", "value": "a@x.io"},
                sequence=1,
            ),
            StreamRecord(
                entity_id="E-1",
                kind="property.expire",
                ts=T0 + timedelta(days=10),
                payload={"property": "email"},
                sequence=2,
            ),
        ]
        state = fold_events("E-1", events, schema_name="Person")
        assert "email" not in state.props  # terminal: gone from the active set
        assert len(state.history["email"]) == 1
        arch = state.history["email"][0]
        assert arch.valid_until == T0 + timedelta(days=10)  # supersede time, not last_seen
        assert arch.active is False
        # property.set after expire starts a FRESH slot (a new lifecycle)
        rebirth = StreamRecord(
            entity_id="E-1",
            kind="property.set",
            ts=T0 + timedelta(days=11),
            payload={"property": "email", "value": "b@x.io"},
            sequence=3,
        )
        state2 = fold_events("E-1", events + [rebirth], schema_name="Person")
        assert state2.props["email"].value == "b@x.io"
        assert len(state2.history["email"]) == 1


# --------------------------------------------------------------------------
# Time series: temporal dynamics of the atomic entity
# --------------------------------------------------------------------------


class TestSeries:
    def test_cumulative_series(self) -> None:
        series = build_series("E-1", _life(), "event_count")
        assert len(series) == 4
        assert series.values() == [1.0, 2.0, 3.0, 4.0]

    def test_inter_arrival_honest_gaps(self) -> None:
        series = build_series("E-1", _life(), "mention", metric="inter_arrival")
        assert series.is_empty()  # single mention -> no gaps (no fabrication)

    def test_velocity_and_stats(self) -> None:
        series = build_series("E-1", _life(), "event_count")
        velocity = series.velocity(per=timedelta(hours=1))
        assert [v for _, v in velocity] == [1.0, 1.0, 1.0]
        stats = series.stats()
        assert stats.n == 4 and stats.min == 1.0 and stats.max == 4.0

    def test_empty_series_honest_no_fabricated_zeros(self) -> None:
        series = build_series("E-1", [], "event_count")
        assert series.is_empty()
        stats = series.stats()
        assert stats.n == 0 and stats.mean is None and stats.min is None

    def test_series_hash_stable_and_content_bound(self) -> None:
        s1 = build_series("E-1", _life(), "event_count")
        s2 = build_series("E-1", _life(), "event_count")
        assert s1.series_hash == s2.series_hash
        s3 = build_series("E-1", _life()[:-1], "event_count")
        assert s1.series_hash != s3.series_hash

    def test_unknown_metric_rejected(self) -> None:
        with pytest.raises(StreamAppendRejected, match="metric"):
            build_series("E-1", [], "event_count", metric="magic")

    def test_series_stats_direct(self) -> None:
        st = SeriesStats.from_values([2.0, 4.0])
        assert st.mean == 3.0 and st.variance == pytest.approx(2.0)
        single = SeriesStats.from_values([5.0])
        assert single.variance == 0.0
        empty = SeriesStats.from_values([])
        assert empty.n == 0

    def test_duplicate_timestamps_are_kept_not_rejected(self) -> None:
        # Block F: a batch observation legitimately shares one timestamp across
        # many records; that is not a corrupted stream and must not raise.
        events = [
            StreamRecord(entity_id="E-1", kind="mention", ts=T0, sequence=1),
            StreamRecord(entity_id="E-1", kind="mention", ts=T0, sequence=2),
            StreamRecord(entity_id="E-1", kind="mention", ts=T0, sequence=3),
        ]
        series = build_series("E-1", events, "event_count")
        assert len(series) == 3
        assert series.values() == [1.0, 2.0, 3.0]


# --------------------------------------------------------------------------
# Hypergraph: occurrences as N-ary relations
# --------------------------------------------------------------------------


class TestHyperEdge:
    def test_requires_two_plus_distinct_members(self) -> None:
        with pytest.raises(StreamAppendRejected):
            HyperEdge(edge_type="x", members=("A",))
        with pytest.raises(StreamAppendRejected):
            HyperEdge(edge_type="x", members=("A", "A"))

    def test_deterministic_id_and_member_ordering(self) -> None:
        a = HyperEdge(edge_type="transaction", members=("P-2", "P-1", "P-3"))
        b = HyperEdge(edge_type="transaction", members=("P-3", "P-1", "P-2"))
        assert a.edge_id == b.edge_id
        assert a.members == ("P-1", "P-2", "P-3")

    def test_temporal_activity_window(self) -> None:
        edge = HyperEdge(
            edge_type="membership",
            members=("P-1", "ORG-1"),
            valid_from=T0,
            valid_until=T0 + timedelta(days=30),
        )
        assert edge.is_active_at(T0 + timedelta(days=1))
        assert not edge.is_active_at(T0 + timedelta(days=31))

    def test_idempotent_upsert_and_temporal_versioning(self) -> None:
        # Block H: identical content is byte-identical and idempotent; content
        # differing on versionable fields (weight, valid_until) is a NEW
        # temporal version of the SAME logical edge — never an "immutable"
        # rejection.
        hg = HyperGraph()
        prov = {"event_id": "EVT-1", "observation_id": "OBS-1"}
        edge = HyperEdge(edge_type="t", members=("A", "B"))
        vid1 = hg.upsert(edge, prov)
        vid1_again = hg.upsert(edge, prov)
        assert len(hg) == 1
        assert vid1 == vid1_again
        # same logical relation, changed weight -> a new temporal version
        evolved = HyperEdge(edge_type="t", members=("A", "B"), weight=7.0)
        vid2 = hg.upsert(evolved, prov)
        assert vid1 != vid2
        assert len(hg) == 2
        # both belong to the same logical edge; logical id is shared with the
        # graph projection (block G)
        assert edge.logical_id == evolved.logical_id
        versions = hg.versions(edge.logical_id)
        assert [e.edge_id for e in versions] == [vid1, vid2]

    def test_upsert_requires_provenance(self) -> None:
        hg = HyperGraph()
        edge = HyperEdge(edge_type="t", members=("A", "B"))
        with pytest.raises(StreamAppendRejected, match="provenance"):
            hg.upsert(edge, provenance={})

    def test_member_and_tenant_filters(self) -> None:
        hg = HyperGraph()
        prov = {"event_id": "EVT-1", "observation_id": "OBS-1"}
        hg.upsert(HyperEdge(edge_type="t", members=("A", "B"), tenant_id="t1"), prov)
        hg.upsert(HyperEdge(edge_type="t", members=("B", "C"), tenant_id="t2"), prov)
        assert len(hg.edges(member="B")) == 2
        assert len(hg.edges(member="B", tenant_id="t1")) == 1
        assert len(hg.edges(tenant_id="t2")) == 1

    def test_clique_projection_deterministic(self) -> None:
        hg = HyperGraph()
        prov = {"event_id": "EVT-1", "observation_id": "OBS-1"}
        hg.upsert(HyperEdge(edge_type="transaction", members=("A", "B", "C")), prov)
        hg.upsert(HyperEdge(edge_type="transaction", members=("A", "D")), prov)
        cliques = hg.clique_projection()
        assert cliques == [
            ("A", "B", "transaction"),
            ("A", "C", "transaction"),
            ("A", "D", "transaction"),
            ("B", "C", "transaction"),
        ]

    def test_incidence_complex_for_tda(self) -> None:
        hg = HyperGraph()
        prov = {"event_id": "EVT-1", "observation_id": "OBS-1"}
        hg.upsert(HyperEdge(edge_type="transaction", members=("A", "B", "C", "D")), prov)
        simplex = hg.incidence_complex()["maximal_simplices"][0]
        assert simplex["nodes"] == ["A", "B", "C", "D"]
        assert simplex["dim"] == 3


# --------------------------------------------------------------------------
# Block A: integration facade — fabric wiring end-to-end
# --------------------------------------------------------------------------


class _RecordingSink:
    """Fake FabricSink recording every emission (hermetic, matching kafka)."""

    def __init__(self) -> None:
        self.stream_records: list[str] = []
        self.states: list[str] = []
        self.series: list[str] = []
        self.hyperedges: list[str] = []
        self.hyperedge_versions: list[str] = []
        self.hyperedge_expirations: list[tuple[str, str]] = []

    def emit_stream_record(self, rec) -> None:
        self.stream_records.append(rec.entity_id)

    def emit_state(self, state) -> None:
        self.states.append(state.entity_id)

    def emit_series(self, series) -> None:
        self.series.append(series.key)

    def emit_hyperedge(self, edge) -> None:
        self.hyperedges.append(edge.logical_id)

    def emit_hyperedge_temporal_version(self, edge) -> None:
        self.hyperedge_versions.append(edge.logical_id)

    def emit_hyperedge_expired(self, edge, expired_at) -> None:
        self.hyperedge_expirations.append((edge.logical_id, "expired"))


class TestFabric:
    def test_append_folds_and_emits_projections(self) -> None:
        from domain.fabric import EntityFabric, MemoryEntityStreamStore

        store = MemoryEntityStreamStore()
        sink = _RecordingSink()
        fabric = EntityFabric(store=store, sink=sink)

        recs = [
            StreamRecord(
                entity_id="E-1",
                kind="property.set",
                ts=T0,
                payload={"property": "name", "value": "Alice"},
                sequence=1,
            ),
            StreamRecord(
                entity_id="E-1",
                kind="property.set",
                ts=T0 + timedelta(hours=1),
                payload={"property": "alias", "value": "A."},
                sequence=2,
            ),
        ]
        for rec in recs:
            result = fabric.append(rec, schema_name="Person")
            assert result.inserted

        state = fabric.state("E-1")
        assert state is not None
        assert state.props["name"].value == "Alice"
        series = fabric.series("E-1", "event_count")
        assert series is not None and series.values() == [1.0, 2.0]
        # the sink saw each derived projection exactly once
        assert sink.states == ["E-1", "E-1"]
        assert sink.series == ["event_count", "event_count"]

    def test_idempotent_redelivery_does_not_double_fold(self) -> None:
        from domain.fabric import EntityFabric, MemoryEntityStreamStore

        store = MemoryEntityStreamStore()
        fabric = EntityFabric(store=store, sink=None)
        rec = StreamRecord(
            entity_id="E-1",
            kind="mention",
            ts=T0,
            sequence=1,
        )
        assert fabric.append(rec, schema_name="Person").inserted
        # re-delivery of the same record_hash (at-least-once, I-11)
        duplicate = StreamRecord(
            entity_id="E-1",
            kind="mention",
            ts=T0,
            sequence=1,
        )
        assert fabric.append(duplicate, schema_name="Person").inserted is False
        state = fabric.state("E-1")
        assert state is not None
        assert state.event_count == 1

    def test_store_sequence_regression_rejected(self) -> None:
        from domain.fabric import EntityFabric, MemoryEntityStreamStore

        store = MemoryEntityStreamStore()
        fabric = EntityFabric(store=store, sink=None)
        fabric.append(
            StreamRecord(entity_id="E-1", kind="mention", ts=T0, sequence=2),
            schema_name="Person",
        )
        with pytest.raises(StreamAppendRejected, match="sequence regression"):
            fabric.append(
                StreamRecord(entity_id="E-1", kind="mention", ts=T0, sequence=1),
                schema_name="Person",
            )

    def test_tenant_isolation_in_fabric(self) -> None:
        from domain.fabric import EntityFabric, MemoryEntityStreamStore

        store = MemoryEntityStreamStore()
        fabric = EntityFabric(store=store, sink=None)
        foreign = StreamRecord(
            entity_id="E-1",
            kind="mention",
            ts=T0,
            tenant_id="other",
            sequence=1,
        )
        with pytest.raises(StreamAppendRejected, match="tenant"):
            fabric.append(foreign, schema_name="Person")

    def test_rebuild_from_store_matches_hot_path(self) -> None:
        from domain.fabric import EntityFabric, MemoryEntityStreamStore

        store = MemoryEntityStreamStore()
        fabric = EntityFabric(store=store, sink=None)
        events = _life()
        for rec in events:
            fabric.append(rec, schema_name="Person")
        hot = fabric.state("E-1")

        # a fresh fabric over the same durable store rebuilds identically (I-12)
        fabric2 = EntityFabric(store=store, sink=None)
        rebuilt = fabric2.state("E-1")
        assert rebuilt is not None and hot is not None
        assert rebuilt.head_hash == hot.head_hash
        assert rebuilt.props["alias"].to_dict() == hot.props["alias"].to_dict()

    def test_hyperedge_versioning_via_fabric(self) -> None:
        from domain.fabric import EntityFabric, MemoryEntityStreamStore
        from domain.hypergraph import HyperEdge

        store = MemoryEntityStreamStore()
        sink = _RecordingSink()
        fabric = EntityFabric(store=store, sink=sink)

        base = HyperEdge(edge_type="membership", members=("P-1", "ORG-1"))
        evolved = HyperEdge(
            edge_type="membership", members=("P-1", "ORG-1"), valid_until=T0 + timedelta(days=30)
        )
        vid1 = fabric.record_hyperedge(base, event_id="EVT-1", observation_id="OBS-1")
        vid2 = fabric.record_hyperedge(evolved, event_id="EVT-2", observation_id="OBS-1")

        assert vid1 != vid2  # two temporal versions, not one "immutable" clash
        assert len(fabric.hyperedges()) == 2
        assert sink.hyperedges == [base.logical_id, evolved.logical_id]
        assert sink.hyperedge_versions == [evolved.logical_id]  # second version event
        versions = fabric._hypergraph.versions(base.logical_id)
        assert [e.edge_id for e in versions] == [vid1, vid2]

    def test_expire_hyperedge_emits_terminal_event(self) -> None:
        from domain.fabric import EntityFabric, MemoryEntityStreamStore
        from domain.hypergraph import HyperEdge

        store = MemoryEntityStreamStore()
        sink = _RecordingSink()
        fabric = EntityFabric(store=store, sink=sink)
        edge = HyperEdge(
            edge_type="membership", members=("P-1", "ORG-1"), valid_from=T0, valid_until=None
        )
        fabric.record_hyperedge(edge, event_id="EVT-1")
        expired_at = T0 + timedelta(days=400)
        fabric.expire_hyperedge(edge, expired_at)
        assert sink.hyperedge_expirations == [(edge.logical_id, "expired")]
