"""Feature 005 US2: resolution candidates, review decisions, non-destructive reverse."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datetime import UTC, datetime

import pytest

from resolution.candidate import (
    CandidateState,
    apply_review,
    create_candidate,
    decide_candidate,
    is_merge_blocked,
    pair_key,
    reverse_resolution,
    state_from_review,
)
from resolution.collective import CorrelationService, ResolvedPair


class _MockProducer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object, str | None]] = []

    def produce(self, topic, envelope, key=None, **kwargs) -> None:
        self.sent.append((topic, envelope, key))


class TestPairKey:
    def test_deterministic_and_order_insensitive(self):
        assert pair_key("ENT-A", "ENT-B") == pair_key("ENT-B", "ENT-A")
        assert pair_key("ENT-A", "ENT-B").find("ENT-A") < pair_key("ENT-A", "ENT-B").find("ENT-B")

    def test_self_pair_rejected(self):
        with pytest.raises(ValueError):
            pair_key("ENT-A", "ENT-A")


class TestCandidateLifecycle:
    def test_accept_keeps_both_entities_queryable(self):
        cand = create_candidate("ENT-A", "ENT-B", raw_pair_score=0.9, reasons=["email", "handle"])
        record = decide_candidate(cand, CandidateState.ACCEPTED, decided_by="human")
        assert cand.state == CandidateState.ACCEPTED
        assert cand.latest_record is record
        assert cand.pair_key == pair_key("ENT-A", "ENT-B")
        # I-2: no auto-merge — both original entities remain distinct and queryable.
        assert cand.candidate_a == "ENT-A" and cand.candidate_b == "ENT-B"

    def test_reject_persists_not_reproposed_at_equal_evidence(self):
        cand = create_candidate("ENT-A", "ENT-B", reasons=["email", "handle"])
        decide_candidate(cand, CandidateState.REJECTED, decided_by="human", reasons=["email", "handle"])
        assert cand.state == CandidateState.REJECTED
        assert is_merge_blocked(cand, reasons=["email", "handle"]) is True
        # A superset of evidence is a NEW decision, not the rejected one.
        assert is_merge_blocked(cand, reasons=["email", "handle", "id"]) is False

    def test_reverse_appends_never_mutates(self):
        cand = create_candidate("ENT-A", "ENT-B", raw_pair_score=0.8)
        accept = decide_candidate(cand, CandidateState.ACCEPTED, decided_by="human")
        assert len(cand.decision_revision) == 1
        revoke = reverse_resolution(cand, decided_by="human")
        assert cand.state == CandidateState.REVERSED
        assert len(cand.decision_revision) == 2
        assert cand.decision_revision[0] is accept  # original record untouched
        assert revoke.revokes_resolution_id == accept.resolution_id
        assert not is_merge_blocked(cand, reasons=[])  # reversed pair is re-proposable

    def test_reverse_requires_prior_accept(self):
        cand = create_candidate("ENT-A", "ENT-B")
        with pytest.raises(ValueError):
            reverse_resolution(cand, decided_by="human")

    def test_rejected_cannot_enable_reverse(self):
        cand = create_candidate("ENT-A", "ENT-B")
        with pytest.raises(ValueError):
            decide_candidate(cand, CandidateState.REVERSED, decided_by="human")

    def test_decision_revision_is_append_only(self):
        cand = create_candidate("ENT-A", "ENT-B")
        first = decide_candidate(cand, CandidateState.OPEN, decided_by="auto")
        second = decide_candidate(cand, CandidateState.REJECTED, decided_by="human")
        assert cand.decision_revision == [first, second]
        assert first.decision == CandidateState.OPEN


class TestApplyReview:
    def test_maps_review_decision_to_state(self):
        assert state_from_review("ACCEPT") == CandidateState.ACCEPTED
        assert state_from_review("REJECT") == CandidateState.REJECTED
        assert state_from_review("UNCERTAIN") == CandidateState.OPEN

    def test_unknown_review_decision_rejected(self):
        with pytest.raises(ValueError):
            state_from_review("MAYBE")

    def test_reject_on_accepted_pair_reverses(self):
        cand = create_candidate("ENT-A", "ENT-B")
        apply_review(cand, "ACCEPT", reviewer_id="analyst-1")
        assert cand.state == CandidateState.ACCEPTED
        apply_review(cand, "REJECT", reviewer_id="analyst-2")
        assert cand.state == CandidateState.REVERSED
        assert len(cand.decision_revision) == 2


class TestCollectiveService:
    def test_create_candidates_deterministic_pair_keys(self):
        svc = CorrelationService()
        pairs = [
            ResolvedPair(candidate_a="ENT-A", candidate_b="ENT-B", raw_pair_score=0.8,
                         collective_score=0.82, reasons=["email"]),
            ResolvedPair(candidate_a="ENT-C", candidate_b="ENT-D", raw_pair_score=0.0),  # filtered
        ]
        candidates = svc.create_candidates(pairs)
        assert len(candidates) == 1
        assert candidates[0].pair_key == pair_key("ENT-A", "ENT-B")
        assert svc.candidate_for(pair_key("ENT-A", "ENT-B")) is not None

    def test_decide_emits_candidate_events_refs_only(self):
        producer = _MockProducer()
        svc = CorrelationService(producer=producer)
        svc.create_candidates(
            [ResolvedPair(candidate_a="ENT-A", candidate_b="ENT-B", raw_pair_score=0.7,
                          collective_score=0.7, reasons=["email", "handle"])]
        )
        key = pair_key("ENT-A", "ENT-B")
        cand = svc.decide(key, "ACCEPT", reviewer_id="analyst-1",
                          reviewed_at=datetime(2026, 1, 1, tzinfo=UTC))
        assert cand.state == CandidateState.ACCEPTED

        topics = {t for t, _, _ in producer.sent}
        assert topics == {"resolution"}
        types = {e.event_type for _, e, _ in producer.sent}
        assert "resolution.candidate_created" in types
        assert "resolution.candidate_decided" in types
        assert "resolution.merge_recorded" in types
        for _, envelope, _ in producer.sent:
            payload = envelope.payload.decode("utf-8")
            assert "pair_key" in payload  # refs-only records, no blobs (I-5)

    def test_decide_unknown_pair_raises(self):
        svc = CorrelationService()
        with pytest.raises(KeyError):
            svc.decide(pair_key("ENT-A", "ENT-B"), "ACCEPT")