"""Contract tests: evidence-ladder gating + review events (T133, US7).

Tests-first for ``apps/science/review/*`` per interface-contracts §10 and
data-model §13: ``ladder_position`` machine-checks the recorded calibration +
null + robustness + reproduction gates (FR-013, top rung = 4); claims without
full provenance or missing robustness/calibration record a rung below top and
remain ``REVIEW_PENDING``; comments and status transitions emit review events.
"""

from __future__ import annotations

from claims.model import (
    ClaimStatus,
    CredenceDistribution,
    EvidenceDirection,
    EvidenceLink,
    ScientificClaim,
)
from review.events import ReviewEventKind, change_status, comment_on_claim
from review.ladder import LadderGates, ladder_position


def _claim(provenance: list[EvidenceLink] | None = None) -> ScientificClaim:
    links = provenance if provenance is not None else [
        EvidenceLink(
            link_id="L1",
            observation_id="O1",
            raw_sha256="sha256:1",
            direction=EvidenceDirection.SUPPORTS,
            weight=1.0,
        )
    ]
    return ScientificClaim(
        claim_id="CL-1",
        project_id="P1",
        statement="adoption grows with deployment",
        distribution=CredenceDistribution(
            states=["yes", "no"],
            labels=["yes", "no"],
            probs=[0.8, 0.2],
            method="logit@1.0",
        ),
        model_id="logit@1.0",
        provenance=links,
    )


class CaptureProducer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object, str | None]] = []

    def produce(self, topic, envelope, key=None, **kwargs) -> None:
        self.sent.append((topic, envelope, key))


class TestLadderGating:
    def test_top_rung_requires_all_recorded_gates(self) -> None:
        position = ladder_position(
            _claim(),
            LadderGates(calibrated=True, null_model=True, robustness=True, reproduction=True),
        )
        assert position == 4

    def test_missing_reproduction_cannot_reach_top(self) -> None:
        position = ladder_position(
            _claim(),
            LadderGates(calibrated=True, null_model=True, robustness=True, reproduction=False),
        )
        assert position == 3
        assert position != 4

    def test_missing_calibration_and_robustness_stays_pending(self) -> None:
        position = ladder_position(
            _claim(),
            LadderGates(calibrated=False, null_model=True, robustness=False, reproduction=True),
        )
        assert position is not None
        assert position < 4

    def test_without_full_provenance_no_position(self) -> None:
        assert ladder_position(_claim(provenance=[]), LadderGates(calibrated=True, null_model=True, robustness=True, reproduction=True)) is None


class TestReviewEvents:
    def test_comment_emits_event(self) -> None:
        producer = CaptureProducer()
        event = comment_on_claim("CL-1", actor="desk-1", body="plausible but thin", producer=producer)
        assert event.kind is ReviewEventKind.COMMENT
        assert event.claim_id == "CL-1"
        assert event.to_status is None
        event_types = [envelope.event_type for _, envelope, _ in producer.sent]
        assert "science.review.commented" in event_types

    def test_status_change_emits_event(self) -> None:
        producer = CaptureProducer()
        event = change_status(
            "CL-1",
            actor="desk-1",
            to_status=ClaimStatus.CONFIRMED,
            from_status=ClaimStatus.DRAFT,
            producer=producer,
        )
        assert event.kind is ReviewEventKind.STATUS_CHANGE
        assert event.from_status is ClaimStatus.DRAFT
        assert event.to_status is ClaimStatus.CONFIRMED
        event_types = [envelope.event_type for _, envelope, _ in producer.sent]
        assert "science.review.status_changed" in event_types