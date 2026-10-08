"""Contract: the science seam turns anchored verdicts into context obligations.

Before this, the science layer's results reached nothing. Topic ``science`` was
declared in the catalog with 18 ``science.*`` types, every ``envelope()`` call
passed ``producer=None``, and no consumer existed -- eight HTTP routes computed
verdicts and dropped them on return. Meanwhile ``loop.py`` defined its own
``ScienceFeedback`` with fields mirroring ``anchoring.ScienceEvaluation`` and
never imported it, so a refutation could have been read as support.

These tests pin both directions of the translation, and pin the rule that
matters most for loop termination: support must generate no obligation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

for _source in ("shared", "science", "", "control-plane"):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / _source))

from context_engine.loop import ScienceFeedback, ScienceOutcome
from context_engine.science_bridge import (
    FEEDBACK_EVENT_TYPES,
    feedback_from_envelope,
    project_and_translate,
)
from events.kafka import build_envelope

from anchoring import (
    EvaluationStatus,
    ScienceEvaluation,
    WorldlineAnchor,
)
from context.bridge import (
    DRIFTED,
    INCONCLUSIVE,
    REFUTED,
    SUPPORTED,
    feedback_payload,
    outcome_of,
)
from store import shared_store

pytestmark = pytest.mark.contract


def _envelope(event_type: str, payload: dict[str, Any]):
    return build_envelope(
        event_type=event_type,
        event_version="1.0",
        producer="science.fabric",
        producer_version="0.1.0",
        payload=json.dumps(payload, sort_keys=True).encode(),
        investigation_id="INV-1",
    )


def _evaluation(
    *,
    status: EvaluationStatus = EvaluationStatus.IDENTIFIED,
    drift: float | None = None,
    tolerance: float | None = None,
    kind: str = "calibration",
) -> ScienceEvaluation:
    measurements = {"drift": drift} if drift is not None else {}
    return ScienceEvaluation(
        evaluation_id="EV-1",
        kind=kind,
        anchor=WorldlineAnchor(snapshot_id="RV-x", watermark=1),
        method_fingerprint="mf-1",
        status=status,
        measurements=measurements,
        tolerance=tolerance,
    )


class TestEvaluationToOutcome:
    def test_refuted_is_the_only_contradiction(self) -> None:
        assert outcome_of(_evaluation(status=EvaluationStatus.REFUTED)) == REFUTED

    def test_identified_is_support(self) -> None:
        assert outcome_of(_evaluation(status=EvaluationStatus.IDENTIFIED)) == SUPPORTED

    def test_inconclusive_stays_inconclusive(self) -> None:
        assert outcome_of(_evaluation(status=EvaluationStatus.INCONCLUSIVE)) == INCONCLUSIVE

    def test_estimated_outside_tolerance_is_drift(self) -> None:
        evaluation = _evaluation(
            status=EvaluationStatus.ESTIMATED, drift=0.4, tolerance=0.2
        )
        assert outcome_of(evaluation) == DRIFTED

    def test_estimated_within_tolerance_is_support(self) -> None:
        evaluation = _evaluation(
            status=EvaluationStatus.ESTIMATED, drift=0.01, tolerance=0.2
        )
        assert outcome_of(evaluation) == SUPPORTED

    def test_drift_without_a_declared_tolerance_is_still_drift(self) -> None:
        """No tolerance means we cannot certify the drift as acceptable.

        Reporting support here would assert something no measurement supports.
        DRIFTED only raises a question (an anomaly signal), which is the
        weaker and therefore correct claim.
        """
        evaluation = _evaluation(status=EvaluationStatus.ESTIMATED, drift=0.9)
        assert evaluation.is_within_tolerance() is False
        assert outcome_of(evaluation) == DRIFTED

    def test_estimate_with_no_measurement_is_support(self) -> None:
        evaluation = _evaluation(status=EvaluationStatus.ESTIMATED)
        assert outcome_of(evaluation) == SUPPORTED


class TestPayloadShape:
    def test_payload_carries_anchor_and_method(self) -> None:
        payload = feedback_payload(_evaluation())
        assert payload["snapshot_id"] == "RV-x"
        assert payload["method_fingerprint"] == "mf-1"
        assert payload["evaluation_id"] == "EV-1"

    def test_payload_describes_drift_in_words(self) -> None:
        payload = feedback_payload(
            _evaluation(status=EvaluationStatus.ESTIMATED, drift=0.4, tolerance=0.2)
        )
        assert "outside" in payload["detail"]
        assert "0.4" in payload["detail"]

    def test_payload_never_leaves_the_claim_unnamed(self) -> None:
        payload = feedback_payload(_evaluation(kind="calibration"))
        assert payload["claim_ref"]

    def test_round_trips_into_the_control_plane_type(self) -> None:
        payload = feedback_payload(_evaluation(status=EvaluationStatus.REFUTED))
        feedback = ScienceFeedback.from_payload(payload)
        assert feedback.outcome is ScienceOutcome.REFUTED
        assert feedback.claim_ref == payload["claim_ref"]


class TestEnvelopeTranslation:
    def test_discarded_claim_becomes_a_refutation(self) -> None:
        feedback = feedback_from_envelope(
            _envelope(
                "science.claim.status_changed",
                {"claim_id": "CLM-1", "to_status": "discarded"},
            )
        )
        assert feedback is not None
        assert feedback.outcome is ScienceOutcome.REFUTED
        assert feedback.claim_ref == "CLM-1"

    def test_weakened_claim_becomes_drift(self) -> None:
        feedback = feedback_from_envelope(
            _envelope(
                "science.claim.status_changed",
                {"claim_id": "CLM-1", "to_status": "weakened"},
            )
        )
        assert feedback.outcome is ScienceOutcome.DRIFTED

    def test_confirmed_claim_becomes_support(self) -> None:
        feedback = feedback_from_envelope(
            _envelope(
                "science.claim.status_changed",
                {"claim_id": "CLM-1", "to_status": "confirmed"},
            )
        )
        assert feedback.outcome is ScienceOutcome.SUPPORTED

    def test_overconfident_calibration_becomes_drift(self) -> None:
        feedback = feedback_from_envelope(
            _envelope(
                "science.calibration.report",
                {"report_id": "CR-1", "verdict": "overconfident", "drift": 0.4},
            )
        )
        assert feedback.outcome is ScienceOutcome.DRIFTED

    def test_a_claim_that_flips_under_perturbation_is_drift(self) -> None:
        """A verdict that does not survive its own perturbation grid is not support."""
        feedback = feedback_from_envelope(
            _envelope(
                "science.robustness.report",
                {"report_id": "RB-1", "claim_ref": "CLM-1", "flip_rates": {"missing": 0.5}},
            )
        )
        assert feedback.outcome is ScienceOutcome.DRIFTED

    def test_a_stable_claim_is_support(self) -> None:
        feedback = feedback_from_envelope(
            _envelope(
                "science.robustness.report",
                {"report_id": "RB-1", "claim_ref": "CLM-1", "flip_rates": {"missing": 0.0}},
            )
        )
        assert feedback.outcome is ScienceOutcome.SUPPORTED

    def test_change_point_carries_its_series(self) -> None:
        feedback = feedback_from_envelope(
            _envelope("science.temporal.change_point", {"series_id": "TS-1", "index": 4})
        )
        assert feedback is not None
        assert feedback.claim_ref == "TS-1"

    def test_structure_results_are_not_obligations(self) -> None:
        """A projection an analyst reads later is not a question to ask."""
        assert (
            feedback_from_envelope(
                _envelope("science.structure.analyzed", {"result_id": "ST-1"})
            )
            is None
        )

    def test_corrupt_payload_manufactures_no_obligation(self) -> None:
        envelope = build_envelope(
            event_type="science.claim.status_changed",
            event_version="1.0",
            producer="x",
            producer_version="1",
            payload=b"not json",
        )
        assert feedback_from_envelope(envelope) is None

    def test_payload_without_any_ref_is_skipped(self) -> None:
        envelope = _envelope("science.claim.status_changed", {"to_status": "discarded"})
        assert feedback_from_envelope(envelope) is None

    def test_every_feedback_type_is_registered_in_the_catalog(self) -> None:
        from events.topics import topic_for

        for event_type in FEEDBACK_EVENT_TYPES:
            assert topic_for(event_type) == topic_for("science.claim.registered")


class TestLoopEffect:
    def test_refutation_creates_exactly_one_obligation(self) -> None:
        feedback = ScienceFeedback(
            outcome=ScienceOutcome.REFUTED,
            claim_ref="CLM-1",
            detail="evidence contradicts",
            snapshot_id="RV-x",
            method_fingerprint="mf-1",
        )
        signals = feedback.to_signals("CXI-1")
        assert len(signals) == 1
        assert signals[0].kind.value == "contradiction"
        assert "CLM-1" in signals[0].question

    def test_support_creates_no_obligation(self) -> None:
        """A settled question must not manufacture new work, or the loop never ends."""
        feedback = ScienceFeedback(outcome=ScienceOutcome.SUPPORTED, claim_ref="CLM-1")
        assert feedback.to_signals("CXI-1") == ()

    def test_inconclusive_creates_no_obligation(self) -> None:
        feedback = ScienceFeedback(outcome=ScienceOutcome.INCONCLUSIVE, claim_ref="CLM-1")
        assert feedback.to_signals("CXI-1") == ()

    def test_feedback_must_name_its_claim(self) -> None:
        with pytest.raises(ValueError):
            ScienceFeedback(outcome=ScienceOutcome.REFUTED, claim_ref="")

    def test_anchor_provenance_reaches_the_rationale(self) -> None:
        feedback = ScienceFeedback(
            outcome=ScienceOutcome.REFUTED,
            claim_ref="CLM-1",
            snapshot_id="RV-x",
            method_fingerprint="mf-1",
        )
        rationale = feedback.to_signals("CXI-1")[0].rationale
        assert "RV-x" in rationale
        assert "mf-1" in rationale


class TestProjection:
    def test_projection_happens_even_without_a_signal(self) -> None:
        """I-12: the log determines the snapshot, so folding is unconditional."""
        before = shared_store().log_len
        feedback = project_and_translate(
            _envelope("science.structure.analyzed", {"result_id": "ST-9"})
        )
        assert feedback is None
        assert shared_store().log_len == before + 1

    def test_projection_is_idempotent_by_deterministic_id(self) -> None:
        envelope = _envelope(
            "science.robustness.report",
            {"report_id": "RB-7", "claim_ref": "CLM-7", "flip_rates": {"missing": 0.0}},
        )
        project_and_translate(envelope)
        project_and_translate(envelope)
        assert sum(
            1 for record in shared_store().all("robustness")
            if record.get("report_id") == "RB-7"
        ) == 1
