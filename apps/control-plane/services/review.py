"""Analyst review decisions as immutable provenance (T019, FR-006, Vitni pattern).

Review decisions (ACCEPT/REJECT/UNCERTAIN) are append-only provenance rows:
recorded via events, never mutated in place, replayable. Each new decision
emits a ``review.recorded`` EventEnvelope (T033) so projections rebuild the
review timeline from durable events (I-12). The in-memory store is a hermetic
stand-in for the Postgres `review_decisions` table surfaced by the control
plane.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import ClassVar

from events.kafka import build_envelope
from events.topics import topic_for


class ReviewDecision(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    UNCERTAIN = "UNCERTAIN"


class ReviewTargetType(str, Enum):
    CANDIDATE = "candidate"
    ASSERTION = "assertion"
    CORRELATION_EDGE = "correlation_edge"
    FINDING = "finding"


class ReviewAppendOnlyError(Exception):
    """FR-006: an existing review decision is immutable."""

    def __init__(self, review_id: str) -> None:
        self.review_id = review_id
        super().__init__(f"Review {review_id} is immutable; mutation rejected")


_IMMUTABLE_FIELDS = ("decision", "target_type", "target_id", "analyst_id", "reviewed_at")


@dataclass
class ReviewRecord:
    review_id: str = field(default_factory=lambda: "RV-" + uuid.uuid4().hex[:12])
    target_type: ReviewTargetType = ReviewTargetType.CANDIDATE
    target_id: str = ""
    decision: ReviewDecision = ReviewDecision.UNCERTAIN
    analyst_id: str = ""
    reasoning: str = ""
    reviewed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    tenant_id: str = "default-tenant"
    provenance: dict = field(default_factory=dict)
    replayed: bool = False

    def to_dict(self) -> dict:
        return {
            "review_id": self.review_id,
            "target_type": self.target_type.value,
            "target_id": self.target_id,
            "decision": self.decision.value,
            "analyst_id": self.analyst_id,
            "reasoning": self.reasoning,
            "reviewed_at": self.reviewed_at,
            "tenant_id": self.tenant_id,
            "provenance": dict(self.provenance),
            "replayed": self.replayed,
        }


class ReviewService:
    """Append-only, replayable analyst-review store (FR-006)."""

    # ReviewDecision → candidate review state (admission resolution vocabulary).
    CANDIDATE_STATE: ClassVar[dict[ReviewDecision, str]] = {
        ReviewDecision.ACCEPT: "accepted",
        ReviewDecision.REJECT: "rejected",
        ReviewDecision.UNCERTAIN: "open",
    }

    def __init__(self, producer=None) -> None:
        self._reviews: dict[str, ReviewRecord] = {}
        self._events: list[str] = []
        self._producer = producer

    def record_candidate_review(
        self,
        *,
        tenant_id: str,
        analyst_id: str,
        pair_key: str,
        decision: ReviewDecision,
        reasoning: str = "",
        roles: frozenset[str] = frozenset(),
    ) -> tuple[ReviewRecord, str]:
        """Persist a candidate decision (target = pair_key) and its candidate state."""
        record = self.record(
            tenant_id=tenant_id,
            analyst_id=analyst_id,
            target_type=ReviewTargetType.CANDIDATE,
            target_id=pair_key,
            decision=decision,
            reasoning=reasoning,
            roles=roles,
        )
        return record, self.CANDIDATE_STATE[decision]

    def record(
        self,
        *,
        tenant_id: str,
        analyst_id: str,
        target_type: ReviewTargetType,
        target_id: str,
        decision: ReviewDecision,
        reasoning: str = "",
        roles: frozenset[str] = frozenset(),
        event_id: str | None = None,
    ) -> ReviewRecord:
        """Append a new review decision; cannot overwrite an existing one."""
        record = ReviewRecord(
            target_type=target_type,
            target_id=target_id,
            decision=decision,
            analyst_id=analyst_id,
            reasoning=reasoning,
            tenant_id=tenant_id,
            provenance={
                "actor": analyst_id,
                "roles": sorted(roles),
                "event_id": event_id or "rev-" + uuid.uuid4().hex[:12],
            },
        )
        self._reviews[record.review_id] = record
        self._events.append(record.provenance["event_id"])
        if self._producer is not None:
            envelope = build_envelope(
                event_type="review.recorded",
                event_version="1.0",
                producer="control-plane.review",
                producer_version="0.1.0",
                payload=json.dumps(record.to_dict(), default=str).encode("utf-8"),
                entity_id=record.target_id,
                event_id=record.provenance["event_id"],
            )
            self._producer.produce(
                topic_for("review.recorded"), envelope, key=record.review_id
            )
        return record

    def mutate_attempt(self, review_id: str, update: dict) -> ReviewRecord:
        """FR-006 enforcement: existing review decisions cannot change in place."""
        record = self._reviews.get(review_id)
        if record is None:
            raise KeyError(review_id)
        changed = [
            k for k in _IMMUTABLE_FIELDS
            if k in update and update.get(k) != getattr(record, k)
        ]
        if changed:
            raise ReviewAppendOnlyError(review_id)
        return record

    def replay(self, event_id: str) -> ReviewRecord | None:
        """Idempotent replay marker: re-processing the same event is a no-op."""
        for record in self._reviews.values():
            if record.provenance.get("event_id") == event_id:
                record.replayed = True
                return record
        return None

    def by_target(
        self,
        tenant_id: str,
        target_type: ReviewTargetType,
        target_id: str,
    ) -> list[ReviewRecord]:
        return [
            r for r in self._reviews.values()
            if r.tenant_id == tenant_id and r.target_type == target_type and r.target_id == target_id
        ]

    def all(self, tenant_id: str) -> list[ReviewRecord]:
        return [r for r in self._reviews.values() if r.tenant_id == tenant_id]