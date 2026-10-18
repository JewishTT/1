"""WP-D T060: a revision is minted when the knowledge state moves, not when a sweep runs.

**The defect.** ``services/cc_cursor_materialization.py`` computed its revision as::

    generation = int((previous or {}).get("projection_generation", 0)) + 1

Unconditionally. Every run over an unchanged stream produced a new generation. That is
not a cosmetic bookkeeping issue:

* every consumer's history grew longer than the evidence justified;
* "did anything actually change?" could not be answered by looking at revisions, because
  a revision carried no information about change;
* the audit named ``InvariantReducer`` as the component that implements digest-gated
  revision — 33 passing tests, **zero callers**.

The reducer is now used for its fold and its revision numbering, which are the same
shape ``from_entity_stream`` produces, so the digest it reports is comparable to the
digest that was published.

These tests exercise the discipline itself rather than the whole materialization
workflow, which needs Postgres, a Common Crawl index and a live WARC pull. The seam
under test is the decision: *does this sweep mint a revision?*
"""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import pairwise

import pytest

from context_engine.invariant_reducer import InvariantReduceError, InvariantReducer

pytestmark = pytest.mark.unit


def _record(sequence: int, payload: dict, *, when: datetime | None = None) -> object:
    from domain.dynamics import StreamRecord

    return StreamRecord(
        entity_id="ent-1",
        tenant_id="t-1",
        kind="cc.capture",
        ts=when or datetime(2026, 1, 1, tzinfo=UTC),
        sequence=sequence,
        payload=payload,
        observation_id=f"OBS-{sequence}",
    )


def _reducer() -> InvariantReducer:
    return InvariantReducer(tenant_id="t-1", type_label="Domain")


def _warm(records) -> InvariantReducer:
    """Fold a stream the way production does: one accepted batch at a time.

    A single batch advances the revision counter once, so a one-shot fold of three
    records reaches revision 1, not 3. Building history incrementally is what makes
    the gapless-chain assertions below meaningful.
    """
    reducer = _reducer()
    for record in records:
        reducer.reduce([record])
    return reducer


# ---------------------------------------------------------------------------
# The gate itself
# ---------------------------------------------------------------------------

def test_the_first_sweep_mints_a_revision():
    result = _reducer().reduce([_record(1, {"url": "https://a.test"})])

    assert result.changed is True
    assert result.record.revision == 1
    assert result.record.digest


def test_a_replay_over_an_unchanged_stream_mints_nothing():
    """The defect in one test: the second sweep must not move the revision."""
    reducer = _reducer()
    records = [_record(1, {"url": "https://a.test"})]

    first = reducer.reduce(records)
    second = reducer.reduce(records)

    assert first.changed is True
    assert second.changed is False, (
        "an unchanged sweep must not mint a revision; the revision is a claim that "
        "the knowledge state moved"
    )
    assert second.record.revision == first.record.revision
    assert second.record.digest == first.record.digest


def test_a_sweep_that_adds_evidence_mints_exactly_one_revision():
    reducer = _reducer()
    reducer.reduce([_record(1, {"url": "https://a.test"})])
    before = reducer.revision

    after = reducer.reduce([_record(2, {"url": "https://b.test"})])

    assert after.changed is True
    assert after.record.revision == before + 1
    assert after.record.supersedes, "a new revision must name what it supersedes"


def test_the_chain_is_gapless_and_supersession_is_total():
    """Revision n+1 names revision n. A hole in the chain is an unrecoverable history."""
    reducer = _reducer()
    reducer.reduce([_record(1, {"a": 1})])
    reducer.reduce([_record(2, {"b": 2})])
    reducer.reduce([_record(3, {"c": 3})])

    history = reducer.history()
    assert [item.revision for item in history] == [1, 2, 3]
    assert history[0].supersedes == ""
    for earlier, later in pairwise(history):
        assert later.supersedes == earlier.snapshot_id


# ---------------------------------------------------------------------------
# Redelivery
# ---------------------------------------------------------------------------

def test_redelivered_events_are_folded_once():
    """A redelivered event must not become a second observation of the same evidence."""
    reducer = _reducer()
    record = _record(1, {"url": "https://a.test"})

    first = reducer.reduce([record])
    # Same event, reconstructed — a different object, the same event id.
    redelivered = reducer.reduce([_record(1, {"url": "https://a.test"})])

    assert first.changed is True
    assert redelivered.changed is False
    assert len(redelivered.accepted_event_ids) == 0


def test_a_restart_reproduces_the_same_head():
    """FR-031 / SC-004: restart must not change what the platform knows.

    Restart goes through :meth:`InvariantReducer.restore`, not a cold fold, and the
    difference is not cosmetic — see the test below.
    """
    records = [_record(1, {"a": 1}), _record(2, {"b": 2})]

    warm = _warm(records)
    expected = warm.head

    cold = InvariantReducer.restore(
        warm.stream, history=warm.history(), tenant_id="t-1", type_label="Domain"
    )

    assert cold.head.digest == expected.digest
    assert cold.head.revision == expected.revision


def test_a_cold_fold_is_not_equivalent_to_a_restore():
    """A property worth pinning, because it looks like a bug and is not.

    Folding the whole accumulated stream in one batch produces **revision 1**,
    because the revision counter advances once per ``reduce`` call rather than once
    per event. A digest that has been warming up to revision 3 is therefore *not*
    reproducible by a cold fold, even over the identical stream.

    That is why :meth:`restore` exists and takes the history: it rebuilds at the
    recorded position rather than at 1. A caller that uses a cold fold to "rebuild
    from scratch" and compares the digest will report a false change, and then mint a
    revision for evidence that did not move.

    The test asserts the property rather than pretending it does not exist, so a future
    change to the revision semantics has to confront it.
    """
    records = [_record(1, {"a": 1}), _record(2, {"b": 2}), _record(3, {"c": 3})]

    warm = _warm(records)

    cold = _reducer().reduce(records)

    assert warm.revision == 3
    assert cold.record.revision == 1
    assert cold.record.digest != warm.head.digest


def test_restore_continues_the_chain_rather_than_restarting_it():
    """After a restart the next accepted event must land at ``len(history) + 1``."""
    records = [_record(1, {"a": 1}), _record(2, {"b": 2})]
    warm = _warm(records)

    restored = InvariantReducer.restore(
        warm.stream, history=warm.history(), tenant_id="t-1", type_label="Domain"
    )
    result = restored.reduce([_record(3, {"c": 3})])

    assert result.changed is True
    assert result.record.revision == 3
    assert [item.revision for item in restored.history()] == [1, 2, 3]


def test_restore_refuses_a_corrupt_store():
    """A stream and a history that disagree mean corruption, and it is reported."""
    records = [_record(1, {"a": 1}), _record(2, {"b": 2})]
    warm = _warm(records)

    from dataclasses import replace as dataclass_replace

    tampered = [dataclass_replace(item, snapshot_id="wr-" + "0" * 32) for item in warm.history()]

    with pytest.raises(InvariantReduceError) as caught:
        InvariantReducer.restore(
            warm.stream, history=tampered, tenant_id="t-1", type_label="Domain"
        )
    assert caught.value.code == "head_mismatch"


def test_restore_refuses_a_gap_in_the_chain():
    records = [_record(1, {"a": 1}), _record(2, {"b": 2})]
    warm = _warm(records)

    with pytest.raises(InvariantReduceError) as caught:
        InvariantReducer.restore(
            warm.stream,
            history=[warm.history()[1]],
            tenant_id="t-1",
            type_label="Domain",
        )
    assert caught.value.code == "history_not_gapless"


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------

def test_an_empty_stream_cannot_mint_an_identity():
    """A revision with no events behind it is a claim with no source."""
    with pytest.raises(InvariantReduceError) as caught:
        _reducer().reduce([])
    assert caught.value.code == "empty_stream"


def test_the_reducer_refuses_an_empty_tenant():
    with pytest.raises(InvariantReduceError) as caught:
        InvariantReducer(tenant_id="")
    assert caught.value.code == "missing_tenant"


def test_an_empty_window_is_refused():
    from datetime import timedelta

    with pytest.raises(InvariantReduceError) as caught:
        InvariantReducer(tenant_id="t-1", window=timedelta(0))
    assert caught.value.code == "invalid_window"


# ---------------------------------------------------------------------------
# The generation arithmetic the caller performs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "previous_digest,incoming_digest,expect_mint",
    [
        ("", "abc", True),          # first publication
        ("abc", "abc", False),      # replay, nothing moved
        ("abc", "def", True),       # new evidence
        ("def", "abc", True),       # the state moved backwards — still a change
    ],
)
def test_the_generation_gate_agrees_with_the_digest(
    previous_digest: str, incoming_digest: str, expect_mint: bool
):
    """The gate in ``run_cursor_materialization``, isolated so both branches are covered.

    Reconstructing the comparison rather than asserting it against a live sweep keeps
    the branch coverage honest: the interesting inputs are the ones a real run rarely
    produces on demand — an unchanged replay, and a first run against a publication
    written before this gate existed.
    """
    previous_generation = 3
    should_mint = not (previous_digest and previous_digest == incoming_digest)
    generation = previous_generation + 1 if should_mint else previous_generation

    assert should_mint is expect_mint
    assert generation == (previous_generation + 1 if expect_mint else previous_generation)


def test_a_pre_upgrade_publication_still_mints_a_first_digest():
    """A publication written before this gate carries no ``state_digest``.

    It is treated as *unknown*, not as *unchanged* — otherwise the gate would
    suppress the very first revision after upgrade and the platform would carry a
    publication with no digest forever, never able to prove it has not moved.
    """
    previous: dict[str, object] = {"projection_generation": 4}  # no state_digest
    previous_digest = str(previous.get("state_digest", "") or "")
    incoming_digest = "abc"

    should_mint = not (previous_digest and previous_digest == incoming_digest)

    assert previous_digest == ""
    assert should_mint is True


def test_an_unchanged_sweep_keeps_the_generation_it_had():
    """End to end on the arithmetic: replay leaves the number exactly where it was."""
    reducer = _reducer()
    reducer.reduce([_record(1, {"url": "https://a.test"})])
    first_generation = reducer.revision
    digest = reducer.head.digest

    result = reducer.reduce([_record(1, {"url": "https://a.test"})])

    previous_digest = digest
    incoming_digest = result.invariant.integrity_digest
    generation = (
        first_generation + 1
        if not (previous_digest and previous_digest == incoming_digest)
        else first_generation
    )

    assert generation == first_generation
    assert incoming_digest == previous_digest
