"""Feature 024 Phase 12 -- science anchored to a worldline snapshot.

The properties under test are the ones Wave 0 found absent: an evaluation bound to a
snapshot, a refusal to read past it, a tolerance rule recomputed rather than stored, and
per-stage causal outcomes rather than one opaque verdict.
"""

from __future__ import annotations

import pytest

from anchoring import (
    AnchoredEvaluator,
    AnchorError,
    DurableScienceStore,
    EvaluationStatus,
    ScienceEvaluation,
    WorldlineAnchor,
)

pytestmark = pytest.mark.unit

SNAP_A = "WLS-" + "a" * 32
SNAP_B = "WLS-" + "b" * 32


class FakeWorldline:
    def __init__(self, snapshot_id: str = SNAP_A, events: int = 5) -> None:
        self.snapshot_id = snapshot_id
        self.events = tuple(range(events))

    def current_snapshot_id(self) -> str:
        return self.snapshot_id

    def snapshot_fingerprint(self, snapshot_id: str) -> str:
        return f"fp-{snapshot_id}"

    def events_through(self, snapshot_id: str, watermark: int) -> tuple[int, ...]:
        return self.events[: watermark + 1]


def evaluation(**over) -> ScienceEvaluation:
    base = {
        "evaluation_id": "EVAL-1",
        "kind": "calibration",
        "anchor": WorldlineAnchor(snapshot_id=SNAP_A, watermark=2),
        "method_fingerprint": "method@v1+deps@sha256:abc",
        "measurements": {"drift": 0.02},
        "tolerance": 0.05,
    }
    base.update(over)
    return ScienceEvaluation(**base)


# -- anchoring (FR-086) -------------------------------------------------------

def test_an_evaluation_must_name_its_snapshot():
    with pytest.raises(AnchorError) as e:
        WorldlineAnchor(snapshot_id="")
    assert e.value.code == "anchor_snapshot_missing"


def test_an_evaluation_without_a_method_fingerprint_is_refused():
    with pytest.raises(AnchorError) as e:
        evaluation(method_fingerprint="")
    assert e.value.code == "method_fingerprint_missing"


def test_the_evaluator_anchors_to_the_current_snapshot_by_default():
    anchor = AnchoredEvaluator(FakeWorldline()).anchor()
    assert anchor.snapshot_id == SNAP_A
    assert anchor.fingerprint == f"fp-{SNAP_A}"


def test_an_anchor_reads_only_up_to_its_watermark():
    wl = FakeWorldline(events=5)
    got = AnchoredEvaluator(wl).check_anchor(WorldlineAnchor(snapshot_id=SNAP_A, watermark=2))
    assert got == (0, 1, 2)


def test_an_evaluation_bound_to_a_superseded_snapshot_is_refused():
    """The behaviour that makes a science verdict reproducible. Without it, "within
    tolerance" describes no particular moment."""
    evaluator = AnchoredEvaluator(FakeWorldline())
    anchor = evaluator.anchor()
    evaluator._worldline.snapshot_id = SNAP_B
    with pytest.raises(AnchorError) as e:
        evaluator.check_anchor(anchor)
    assert e.value.code == "snapshot_superseded"


def test_staleness_is_observable_without_raising():
    evaluator = AnchoredEvaluator(FakeWorldline())
    anchor = evaluator.anchor()
    assert evaluator.is_still_current(anchor) is True
    evaluator._worldline.snapshot_id = SNAP_B
    assert evaluator.is_still_current(anchor) is False


def test_the_fingerprint_participates_in_reproducibility():
    a = evaluation(anchor=WorldlineAnchor(snapshot_id=SNAP_A, fingerprint="fp-1"))
    b = evaluation(anchor=WorldlineAnchor(snapshot_id=SNAP_A, fingerprint="fp-2"))
    assert a.anchor.fingerprint != b.anchor.fingerprint


# -- calibration (FR-089) ----------------------------------------------------

def test_within_tolerance_compares_absolute_drift():
    assert evaluation(measurements={"drift": 0.02}, tolerance=0.05).is_within_tolerance() is True
    assert evaluation(measurements={"drift": -0.02}, tolerance=0.05).is_within_tolerance() is True
    assert evaluation(measurements={"drift": 0.09}, tolerance=0.05).is_within_tolerance() is False


def test_drift_is_reported_as_an_absolute_value():
    assert evaluation(measurements={"drift": -0.07}).calibration_drift() == 0.07


def test_the_tolerance_rule_is_recomputed_not_stored():
    """A stored verdict goes stale the moment the tolerance or the measurement moves.
    The rule is derived from the numbers so it cannot."""
    e = evaluation(measurements={"drift": 0.02}, tolerance=0.05)
    tightened = replace_measurement(e, tolerance=0.01)
    assert e.is_within_tolerance() is True
    assert tightened.is_within_tolerance() is False


def replace_measurement(e: ScienceEvaluation, **over) -> ScienceEvaluation:
    from dataclasses import replace

    return replace(e, **over)


def test_a_missing_measurement_is_not_within_tolerance():
    assert evaluation(measurements={}, tolerance=0.05).is_within_tolerance() is False


def test_a_missing_tolerance_is_not_within_tolerance():
    assert evaluation(measurements={"drift": 0.0}, tolerance=None).is_within_tolerance() is False


# -- causal stages (FR-087) ---------------------------------------------------

def test_each_causal_stage_records_its_own_outcome():
    e = evaluation(
        kind="causal",
        stages={"identify": "ok", "estimate": "ok", "refute": "failed_to_refute"},
        status=EvaluationStatus.ESTIMATED,
    )
    assert e.stage_outcome("identify") == "ok"
    assert e.stage_outcome("refute") == "failed_to_refute"
    assert e.is_complete_causal() is True


def test_a_partial_causal_chain_is_not_complete():
    e = evaluation(kind="causal", stages={"identify": "ok"})
    assert e.is_complete_causal() is False


def test_a_refuted_causal_claim_is_visible_as_refuted():
    e = evaluation(
        kind="causal",
        stages={"identify": "ok", "estimate": "ok", "refute": "refuted"},
        status=EvaluationStatus.REFUTED,
    )
    assert e.status is EvaluationStatus.REFUTED


def test_a_evaluation_round_trips_with_its_anchor():
    e = evaluation(stages={"identify": "ok"})
    restored = ScienceEvaluation.from_dict(e.to_dict())
    assert restored == e
    assert restored.anchor.snapshot_id == SNAP_A


# -- durability (FR-085) ------------------------------------------------------

ENTITY_BY_EVENT = {
    "science.calibration.report": ("calibration", "report_id"),
    "science.causal.classified": ("causal", "conclusion_id"),
}


def durable(**kw) -> DurableScienceStore:
    return DurableScienceStore(entity_by_event=ENTITY_BY_EVENT, **kw)


def test_the_durable_store_declares_itself_durable():
    assert durable().durability() == "durable"


def test_an_unmapped_science_event_is_refused_rather_than_stored_loosely():
    with pytest.raises(AnchorError) as e:
        durable().collection_for("science.unknown.thing")
    assert e.value.code == "science_event_unmapped"


def test_a_record_without_its_identity_field_is_refused():
    store = durable()
    with pytest.raises(AnchorError) as e:
        store.persist([{"event_type": "science.calibration.report", "drift": 0.1}])
    assert e.value.code == "science_record_keyless"


def test_persisting_uses_the_events_deterministic_id():
    written_rows = []
    store = durable(execute=written_rows.append)
    written = store.persist(
        [
            {
                "event_type": "science.calibration.report",
                "report_id": "RPT-1",
                "drift": 0.01,
                "event_id": "evt-1",
            }
        ]
    )
    assert written == ["RPT-1"]
    assert written_rows[0]["record_id"] == "RPT-1"
    assert written_rows[0]["collection"] == "calibration"


def test_an_unbound_durable_store_refuses_rather_than_silently_dropping():
    """A store with no seam would drop writes quietly, which is worse than failing."""
    with pytest.raises(AnchorError) as e:
        durable().persist([{"event_type": "science.calibration.report", "report_id": "R"}])
    assert e.value.code in ("science_store_unbound",)