"""InvariantReducer: revisions move only when the digest moves (spec 012).

The reducer's contract is narrow and every test here pins one clause of it:
a new event id advances the revision, a redelivered one does not, the chain
links to its predecessor, a restart continues rather than restarts, and the
projection body is exactly what ``from_entity_stream`` would have produced for
the same input.

Hermetic: fixed timestamps, no clock, no network, no database.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest
from context.worldline import WorldlineView
from domain.dynamics import StreamRecord
from domain.graph_invariant import from_entity_stream

from context_engine.invariant_reducer import (
    InvariantReduceError,
    InvariantReducer,
    ReduceResult,
    RevisionRecord,
)

WINDOW = timedelta(days=7)
BASE = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)


def _record(sequence: int, *, day: int = 0, neighbors=None, community: str = "", **kwargs):
    """One stream record; ``sequence`` alone makes each one a distinct event."""
    payload: dict[str, object] = {}
    if neighbors:
        payload["neighbors"] = neighbors
    if community:
        payload["community"] = community
    return StreamRecord(
        entity_id="ent-1",
        kind="entity.observed",
        ts=BASE + timedelta(days=day),
        tenant_id="default-tenant",
        payload=payload,
        sequence=sequence,
        **kwargs,
    )


def _batch(*sequences: int, day: int = 0, **kwargs) -> tuple[StreamRecord, ...]:
    return tuple(_record(seq, day=day, **kwargs) for seq in sequences)


def _reducer(**kwargs) -> InvariantReducer:
    return InvariantReducer(window=WINDOW, **kwargs)


def _stream_with_three_windows() -> tuple[StreamRecord, ...]:
    """Nine records: three per week across three lifecycle windows."""
    return _batch(1, 2, 3, day=0) + _batch(4, 5, 6, day=7) + _batch(7, 8, 9, day=14)


# -- revision increments only on a real change ------------------------------


def test_first_batch_mints_the_genesis_revision() -> None:
    reducer = _reducer()
    result = reducer.reduce(_batch(1, 2, 3))

    assert result.changed is True
    assert reducer.revision == 1
    assert result.record.revision == 1
    assert result.record.supersedes == ""
    assert reducer.invariant.identity.revision == 1


def test_second_batch_advances_the_revision_by_one() -> None:
    reducer = _reducer()
    reducer.reduce(_batch(1, 2, 3))

    result = reducer.reduce(_batch(4, 5, 6))

    assert result.changed is True
    assert reducer.revision == 2
    assert result.record.revision == 2


def test_revision_never_skips_a_step() -> None:
    reducer = _reducer()
    for batch in (_batch(1), _batch(2), _batch(3), _batch(4), _batch(5)):
        reducer.reduce(batch)

    assert [record.revision for record in reducer.history()] == [1, 2, 3, 4, 5]


def test_three_runs_of_three_events_yield_three_revisions() -> None:
    """The reported example: 3 batches x 3 events -> 3 revisions, not 1 and not 9."""
    reducer = _reducer()
    for batch in (_batch(1, 2, 3), _batch(4, 5, 6), _batch(7, 8, 9)):
        reducer.reduce(batch)

    assert reducer.revision == 3
    assert len(reducer.history()) == 3
    assert len(reducer.stream) == 9


# -- idempotency of a replayed batch ---------------------------------------


def test_replaying_the_same_batch_changes_nothing() -> None:
    reducer = _reducer()
    first = reducer.reduce(_batch(1, 2, 3))
    digest_before = reducer.invariant.integrity_digest

    replay = reducer.reduce(_batch(1, 2, 3))

    assert replay.changed is False
    assert replay.accepted_event_ids == ()
    assert reducer.revision == 1
    assert reducer.invariant.integrity_digest == digest_before
    assert replay.invariant is first.invariant
    assert len(reducer.history()) == 1


def test_replaying_equivalent_record_instances_changes_nothing() -> None:
    """Same content rebuilt into new objects: still the same events (I-11)."""
    reducer = _reducer()
    reducer.reduce(_batch(1, 2, 3))

    replay = reducer.reduce(_batch(1, 2, 3))

    assert replay.changed is False
    assert reducer.revision == 1


def test_replay_after_a_later_revision_does_not_rewind() -> None:
    reducer = _reducer()
    reducer.reduce(_batch(1, 2, 3))
    reducer.reduce(_batch(4, 5, 6))

    replay = reducer.reduce(_batch(1, 2, 3))

    assert replay.changed is False
    assert reducer.revision == 2
    assert len(reducer.history()) == 2


def test_a_batch_that_only_redelivers_does_not_mint_a_revision() -> None:
    reducer = _reducer()
    reducer.reduce(_batch(1, 2, 3))

    mixed = reducer.reduce(_batch(2, 3, 1, 2, 3))

    assert mixed.changed is False
    assert mixed.record.revision == 1
    assert len(reducer.stream) == 3


def test_empty_batch_on_a_warm_reducer_is_a_noop() -> None:
    reducer = _reducer()
    reducer.reduce(_batch(1))

    result = reducer.reduce(())

    assert isinstance(result, ReduceResult)
    assert result.changed is False
    assert reducer.revision == 1


def test_empty_batch_on_a_cold_reducer_is_rejected() -> None:
    """An identity needs a source; "" is not one (I-3)."""
    with pytest.raises(InvariantReduceError) as excinfo:
        _reducer().reduce(())

    assert excinfo.value.code == "empty_stream"


def test_the_invariant_property_refuses_to_answer_before_the_first_batch() -> None:
    reducer = _reducer()

    assert reducer.revision == 0
    assert reducer.head is None
    assert reducer.history() == ()
    with pytest.raises(InvariantReduceError) as excinfo:
        _ = reducer.invariant

    assert excinfo.value.code == "no_revision"


# -- the supersedes chain ---------------------------------------------------


def test_history_is_a_linked_chain() -> None:
    reducer = _reducer()
    for batch in (_batch(1, 2, 3), _batch(4, 5, 6), _batch(7, 8, 9)):
        reducer.reduce(batch)

    chain = reducer.history()
    assert chain[0].supersedes == ""
    for previous, current in pairwise(chain):
        assert current.supersedes == previous.snapshot_id
        assert current.revision == previous.revision + 1
        assert current.snapshot_id != previous.snapshot_id


def test_history_snapshot_ids_are_the_invariant_content_addresses() -> None:
    reducer = _reducer()
    reducer.reduce(_batch(1, 2, 3))
    reducer.reduce(_batch(4, 5, 6))

    first, second = reducer.history()
    assert first.snapshot_id == f"GI-{first.digest[:32]}"
    assert second.snapshot_id == f"GI-{second.digest[:32]}"
    assert second.snapshot_id == reducer.invariant.content_id


def test_history_digests_are_unique_and_ordered() -> None:
    reducer = _reducer()
    for batch in (_batch(1, 2, 3), _batch(4, 5, 6), _batch(7, 8, 9)):
        reducer.reduce(batch)

    digests = [record.digest for record in reducer.history()]
    assert len(set(digests)) == len(digests) == 3


def test_caused_by_event_ids_partition_the_stream() -> None:
    """Every event is absorbed by exactly one revision (auditable replay)."""
    reducer = _reducer()
    for batch in (_batch(1, 2, 3), _batch(4, 5, 6), _batch(7, 8, 9)):
        reducer.reduce(batch)

    caused = [event for record in reducer.history() for event in record.caused_by_event_ids]
    assert len(caused) == 9
    assert len(set(caused)) == 9
    assert set(caused) == {f"evt-{h}" for h in reducer.invariant.provenance.source_hashes}
    assert all(event.startswith("evt-") for event in caused)


def test_a_record_may_not_supersede_itself() -> None:
    with pytest.raises(InvariantReduceError) as excinfo:
        RevisionRecord(
            entity_id="ent-1",
            revision=1,
            snapshot_id="GI-abc",
            digest="abc",
            supersedes="GI-abc",
        )

    assert excinfo.value.code == "self_supersession"


def test_the_chain_projects_onto_the_anchor_worldline_view() -> None:
    reducer = _reducer()
    reducer.reduce(_batch(1, 2, 3))
    reducer.reduce(_batch(4, 5, 6))

    view = WorldlineView([record.to_worldline_record() for record in reducer.history()])

    assert view.current_snapshot_id() == reducer.invariant.content_id
    assert view.positions == (1, 2)


# -- restore ----------------------------------------------------------------


def test_restore_continues_from_the_last_revision() -> None:
    original = _reducer()
    original.reduce(_batch(1, 2, 3))
    original.reduce(_batch(4, 5, 6))
    stream, chain = original.snapshot()

    restored = InvariantReducer.restore(stream, history=chain, window=WINDOW)
    result = restored.reduce(_batch(7, 8, 9))

    assert restored.revision == 3
    assert result.record.supersedes == chain[-1].snapshot_id
    assert len(restored.history()) == 3


def test_restored_digest_is_identical_to_the_pre_restart_digest() -> None:
    original = _reducer()
    for batch in (_batch(1, 2, 3), _batch(4, 5, 6), _batch(7, 8, 9)):
        original.reduce(batch)

    stream, chain = original.snapshot()
    restored = InvariantReducer.restore(stream, history=chain, window=WINDOW)

    assert restored.invariant.integrity_digest == original.invariant.integrity_digest
    assert restored.revision == original.revision
    assert restored.history() == original.history()


def test_restored_reducer_reduces_to_the_same_state_as_the_original() -> None:
    """The incremental path and the restart path converge on the same chain."""
    original = _reducer()
    for batch in (_batch(1, 2, 3), _batch(4, 5, 6)):
        original.reduce(batch)

    stream, chain = original.snapshot()
    restored = InvariantReducer.restore(stream, history=chain, window=WINDOW)
    original.reduce(_batch(7, 8, 9))
    restored.reduce(_batch(7, 8, 9))

    assert restored.history() == original.history()
    assert restored.invariant.integrity_digest == original.invariant.integrity_digest


def test_restore_rejects_a_history_whose_head_the_stream_does_not_reproduce() -> None:
    original = _reducer()
    original.reduce(_batch(1, 2, 3))
    original.reduce(_batch(4, 5, 6))
    stream, chain = original.snapshot()

    tampered = (*chain[:-1], replace(chain[-1], snapshot_id="GI-" + "0" * 32))
    with pytest.raises(InvariantReduceError) as excinfo:
        InvariantReducer.restore(stream, history=tampered, window=WINDOW)

    assert excinfo.value.code == "head_mismatch"


def test_restore_rejects_a_history_that_is_not_gapless() -> None:
    original = _reducer()
    original.reduce(_batch(1, 2, 3))
    stream, chain = original.snapshot()

    with pytest.raises(InvariantReduceError) as excinfo:
        InvariantReducer.restore(stream, history=(chain[0], chain[0]), window=WINDOW)

    assert excinfo.value.code == "history_not_gapless"


def test_restore_rejects_an_empty_stream() -> None:
    with pytest.raises(InvariantReduceError) as excinfo:
        InvariantReducer.restore(())

    assert excinfo.value.code == "empty_stream"


def test_restore_without_history_lands_on_the_single_rebuild_revision() -> None:
    records = _batch(1, 2, 3)

    restored = InvariantReducer.restore(records, window=WINDOW)

    assert restored.revision == 1
    assert restored.history() == ()
    assert restored.head is None
    assert (
        restored.invariant.integrity_digest
        == from_entity_stream(records, window=WINDOW).integrity_digest
    )


# -- determinism ------------------------------------------------------------


def test_permuting_events_within_each_batch_changes_nothing() -> None:
    ordered = _reducer()
    for batch in (_batch(1, 2, 3), _batch(4, 5, 6), _batch(7, 8, 9)):
        ordered.reduce(batch)

    shuffled = _reducer()
    for batch in (_batch(3, 1, 2), _batch(6, 4, 5), _batch(9, 7, 8)):
        shuffled.reduce(batch)

    assert shuffled.invariant.integrity_digest == ordered.invariant.integrity_digest
    assert shuffled.history() == ordered.history()
    assert shuffled.revision == ordered.revision


def test_permuting_the_batches_does_not_change_the_final_body() -> None:
    """Ordering of arrival is independent of the projection that results."""
    forward = _reducer()
    forward.reduce(_batch(1, 2, 3, 4, 5, 6, 7, 8, 9))

    backward = _reducer()
    backward.reduce(_batch(7, 8, 9))
    backward.reduce(_batch(4, 5, 6))
    backward.reduce(_batch(1, 2, 3))

    assert backward.invariant.identity.stream_anchor == forward.invariant.identity.stream_anchor
    assert backward.invariant.provenance.source_hashes == (
        forward.invariant.provenance.source_hashes
    )
    # Only the revision watermark differs, and only because the body was reached
    # through three mutations instead of one.
    assert backward.revision == 3
    assert forward.revision == 1


def test_a_late_arrival_with_an_older_timestamp_does_not_move_the_anchor() -> None:
    reducer = _reducer()
    reducer.reduce(_batch(1, 2, day=10))
    anchor = reducer.invariant.identity.stream_anchor

    result = reducer.reduce((_record(3, day=1),))

    assert result.changed is True
    assert reducer.invariant.identity.stream_anchor == anchor
    assert reducer.revision == 2


def test_the_snapshot_stream_rebuilds_to_the_same_digest_in_any_order() -> None:
    reducer = _reducer()
    for batch in (_batch(1, 2, 3), _batch(4, 5, 6), _batch(7, 8, 9)):
        reducer.reduce(batch)
    stream, _ = reducer.snapshot()

    assert (
        InvariantReducer.restore(
            reversed(stream), history=reducer.history(), window=WINDOW
        ).invariant.integrity_digest
        == reducer.invariant.integrity_digest
    )


# -- the digest matches from_entity_stream (the load-bearing claim) --------


def test_digest_matches_from_entity_stream_on_a_single_batch() -> None:
    records = _batch(1, 2, 3, neighbors={"n-1": 1.0}, community="guild")

    reduced = _reducer().reduce(records).invariant
    rebuilt = from_entity_stream(records, window=WINDOW)

    assert reduced.integrity_digest == rebuilt.integrity_digest
    assert reduced.as_dict() == rebuilt.as_dict()
    assert reduced.identity.revision == 1


def test_digest_matches_from_entity_stream_after_three_batches() -> None:
    reducer = _reducer()
    for batch in (_batch(1, 2, 3), _batch(4, 5, 6), _batch(7, 8, 9)):
        reducer.reduce(batch)

    rebuilt = from_entity_stream(reducer.stream, window=WINDOW, revision=reducer.revision)

    assert reducer.invariant.integrity_digest == rebuilt.integrity_digest
    assert reducer.invariant.as_dict() == rebuilt.as_dict()


def test_digest_matches_from_entity_stream_under_constructor_configuration() -> None:
    from domain.graph_invariant import TypedLink

    links = (TypedLink(target_id="SO-abc", relation="hasEvidence"),)
    reducer = InvariantReducer(
        window=WINDOW,
        tenant_id="default-tenant",
        type_label="person",
        community="guild",
        links=links,
    )
    records = _batch(1, 2, neighbors={"n-1": 2.0}, community="guild")
    reducer.reduce(records)
    reducer.reduce(_batch(3, 4, day=7, neighbors={"n-2": 1.0}))

    rebuilt = from_entity_stream(
        reducer.stream,
        window=WINDOW,
        tenant_id="default-tenant",
        type_label="person",
        revision=reducer.revision,
        community="guild",
        links=links,
    )

    assert reducer.invariant.integrity_digest == rebuilt.integrity_digest
    assert reducer.invariant.identity.type_label == "person"


def test_row_mappings_are_accepted_exactly_like_stream_records() -> None:
    """An entity-stream row (mapping) and a ``StreamRecord`` are the same event.

    Mappings carry a real ``datetime`` in ``ts``, which is what
    ``from_entity_stream`` requires; its ``to_dict`` serialisation (ISO string)
    is a wire form the builder does not read back.
    """
    records = _batch(1, 2, 3)

    reducer = _reducer()
    reducer.reduce(records)
    from_objects = reducer.invariant.integrity_digest

    rows = [
        {
            "entity_id": record.entity_id,
            "kind": record.kind,
            "ts": record.ts,
            "tenant_id": record.tenant_id,
            "payload": record.payload,
            "sequence": record.sequence,
            "record_hash": record.record_hash,
        }
        for record in records
    ]
    from_mappings = _reducer()
    from_mappings.reduce(rows)

    assert from_mappings.invariant.integrity_digest == from_objects
    assert from_mappings.revision == 1
    assert from_mappings.history()[0].caused_by_event_ids == (
        reducer.history()[0].caused_by_event_ids
    )


def test_a_full_stream_in_one_batch_equals_the_three_batched_run_at_one_revision() -> None:
    records = _stream_with_three_windows()

    single = _reducer()
    single.reduce(records)

    batched = _reducer()
    for batch in (records[0:3], records[3:6], records[6:9]):
        batched.reduce(batch)

    assert single.invariant.identity.revision == 1
    assert batched.revision == 3
    assert (
        from_entity_stream(records, window=WINDOW, revision=batched.revision).integrity_digest
        == batched.invariant.integrity_digest
    )
    # Same stream, same body modulo the revision watermark the reducer owns.
    assert single.invariant.identity.stream_anchor == batched.invariant.identity.stream_anchor


def test_lifecycle_and_topology_grow_across_revisions() -> None:
    reducer = _reducer()
    first = reducer.reduce(
        _batch(1, 2, 3, neighbors={"n-1": 1.0}, observation_id="obs-1")
    ).invariant
    second = reducer.reduce(
        _batch(4, 5, 6, day=7, neighbors={"n-2": 3.0}, observation_id="obs-2")
    ).invariant

    assert first.topology.neighbor_signature == ("n-1",)
    assert second.topology.neighbor_signature == ("n-1", "n-2")
    assert len(second.lifecycle.slices) > len(first.lifecycle.slices)
    assert first.evidence.observation_count == 1
    assert second.evidence.observation_count == 2
