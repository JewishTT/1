"""Contract: ``WorldlineView`` satisfies ``anchoring.WorldlineReader``.

``anchoring.py`` defined the reader protocol and shipped with no implementation
outside a test fake, so ``AnchoredEvaluator.check_anchor`` -- the gate that
refuses a verdict computed against a superseded world -- could never run in
production. These tests pin the semantics the ratified contract implies,
including the inclusive watermark established by ``test_anchoring.py``
(``events[: watermark + 1]``, watermark=2 -> three events).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from anchoring import (
    AnchoredEvaluator,
    AnchorError,
    EvaluationStatus,
    ScienceEvaluation,
)
from context.worldline import RevisionRecord, WorldlineView, records_from_payloads

pytestmark = pytest.mark.contract

SNAP_A, SNAP_B, SNAP_C = "RV-a", "RV-b", "RV-c"


def _chain() -> WorldlineView:
    return WorldlineView(
        [
            RevisionRecord(SNAP_A, 1, ("E-1", "E-2")),
            RevisionRecord(SNAP_B, 2, ("E-3",)),
            RevisionRecord(SNAP_C, 3, ("E-2", "E-4")),
        ]
    )


class TestProtocol:
    def test_satisfies_the_reader_protocol(self) -> None:
        """Structural check: the protocol is not runtime_checkable by design."""
        from anchoring import WorldlineReader

        required = (
            "current_snapshot_id",
            "snapshot_fingerprint",
            "events_through",
        )
        assert getattr(WorldlineReader, "_is_protocol", False)
        for name in required:
            assert callable(getattr(_chain(), name)), name

    def test_current_snapshot_is_the_latest_revision(self) -> None:
        assert _chain().current_snapshot_id() == SNAP_C

    def test_empty_chain_has_no_head(self) -> None:
        view = WorldlineView([])
        assert view.current_snapshot_id() == ""
        assert len(view) == 0

    def test_fingerprint_is_the_content_address(self) -> None:
        view = _chain()
        assert view.snapshot_fingerprint(SNAP_B) == SNAP_B

    def test_unknown_snapshot_is_refused(self) -> None:
        with pytest.raises(AnchorError) as excinfo:
            _chain().snapshot_fingerprint("RV-missing")
        assert excinfo.value.code == "anchor_snapshot_missing"


class TestInclusiveWatermark:
    def test_matches_the_ratified_contract(self) -> None:
        """watermark=2 -> first three events, as test_anchoring.py establishes."""
        assert _chain().events_through(SNAP_B, 2) == ("E-1", "E-2", "E-3")

    def test_zero_reads_a_single_event(self) -> None:
        assert _chain().events_through(SNAP_B, 0) == ("E-1",)

    def test_stream_is_cumulative_over_the_chain(self) -> None:
        assert _chain().events_through(SNAP_C, 3) == ("E-1", "E-2", "E-3", "E-4")

    def test_earlier_snapshot_cannot_see_later_events(self) -> None:
        assert "E-4" not in _chain().events_through(SNAP_B, 2)

    def test_repeated_event_ids_are_counted_once(self) -> None:
        """E-2 recurs in revision 3; a repeated id is one event, not two."""
        assert _chain().events_through(SNAP_C, 3).count("E-2") == 1

    def test_watermark_past_the_snapshot_is_refused_not_truncated(self) -> None:
        """Silently returning a short list would make a bad anchor look reproducible."""
        with pytest.raises(AnchorError) as excinfo:
            _chain().events_through(SNAP_B, 99)
        assert excinfo.value.code == "anchor_watermark_past_snapshot"

    def test_negative_watermark_is_refused(self) -> None:
        with pytest.raises(AnchorError) as excinfo:
            _chain().events_through(SNAP_B, -1)
        assert excinfo.value.code == "anchor_watermark_negative"

    def test_decision_only_revision_reads_as_empty_not_refused(self) -> None:
        """A revision caused by an analyst decision carries no events; that is legal."""
        view = WorldlineView([RevisionRecord("RV-d", 1, ())])
        assert view.events_through("RV-d", 0) == ()


class TestOrderingAndIntegrity:
    def test_records_are_ordered_regardless_of_input_order(self) -> None:
        view = WorldlineView(
            [
                RevisionRecord(SNAP_C, 3, ("E-4",)),
                RevisionRecord(SNAP_A, 1, ("E-1",)),
                RevisionRecord(SNAP_B, 2, ("E-3",)),
            ]
        )
        assert view.positions == (1, 2, 3)
        assert view.current_snapshot_id() == SNAP_C

    def test_duplicate_positions_are_refused(self) -> None:
        with pytest.raises(AnchorError) as excinfo:
            WorldlineView([RevisionRecord(SNAP_A, 1), RevisionRecord(SNAP_B, 1)])
        assert excinfo.value.code == "worldline_positions_duplicated"

    def test_a_revision_without_an_id_is_refused(self) -> None:
        with pytest.raises(AnchorError) as excinfo:
            WorldlineView([RevisionRecord("", 1)])
        assert excinfo.value.code == "anchor_snapshot_missing"


class TestAnchorLifecycle:
    def test_evaluator_pins_to_the_current_snapshot(self) -> None:
        evaluator = AnchoredEvaluator(_chain())
        anchor = evaluator.anchor()
        assert anchor.snapshot_id == SNAP_C
        assert anchor.fingerprint == SNAP_C

    def test_a_superseded_anchor_is_refused(self) -> None:
        """The behaviour that makes a science verdict mean a particular moment."""
        view = _chain()
        evaluator = AnchoredEvaluator(view)
        anchor = evaluator.anchor()
        newer = WorldlineView(
            [*[RevisionRecord(r.snapshot_id, r.position, r.caused_by_event_ids)
              for r in [RevisionRecord(SNAP_A, 1, ()), RevisionRecord(SNAP_B, 2, ())]],
             RevisionRecord("RV-d", 3, ()),
            ]
        )
        assert newer.current_snapshot_id() != anchor.snapshot_id
        moved = AnchoredEvaluator(newer)
        with pytest.raises(AnchorError) as excinfo:
            moved.check_anchor(anchor)
        assert excinfo.value.code == "snapshot_superseded"

    def test_evaluation_binds_to_reader_and_method(self) -> None:
        evaluator = AnchoredEvaluator(_chain())
        anchor = evaluator.anchor(snapshot_id=SNAP_C, watermark=3)
        evaluation = ScienceEvaluation(
            evaluation_id="EV-1",
            kind="calibration",
            anchor=anchor,
            method_fingerprint="mf-1",
            status=EvaluationStatus.IDENTIFIED,
            measurements={"drift": 0.1},
            tolerance=0.2,
        )
        assert evaluation.is_within_tolerance()
        assert evaluation.method_fingerprint == "mf-1"
        assert evaluation.anchor.snapshot_id == SNAP_C
        assert evaluation.anchor.fingerprint == SNAP_C


class TestPayloadAdapter:
    def test_builds_records_without_owning_the_domain_class(self) -> None:
        records = records_from_payloads(
            [
                {"revision": 1, "revision_id": SNAP_A, "caused_by_event_ids": ["E-1"]},
                {"revision": 2, "revision_id": SNAP_B, "caused_by_event_ids": []},
            ]
        )
        view = WorldlineView(records)
        assert view.current_snapshot_id() == SNAP_B
        assert view.events_through(SNAP_A, 0) == ("E-1",)

    def test_tolerates_missing_cause_list(self) -> None:
        view = WorldlineView(records_from_payloads([{"revision": 1, "revision_id": SNAP_A}]))
        assert view.events_through(SNAP_A, 0) == ()
