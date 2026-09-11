"""Review events: comments + status transitions (T136, US7, data-model §13).

Every review interaction is an append-only ReviewEvent (COMMENT, STATUS_CHANGE
or LADDER_CHANGE) with a UTC timestamp; each emits a ``science.review.*``
envelope. Review state is derived from these events — never stored ephemerally.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any

from _events import envelope as _emit
from claims.model import ClaimStatus


class ReviewEventKind(StrEnum):
    COMMENT = "comment"
    STATUS_CHANGE = "status_change"
    LADDER_CHANGE = "ladder_change"


@dataclass(frozen=True)
class ReviewEvent:
    event_id: str
    claim_id: str
    actor: str
    kind: ReviewEventKind
    body: str | None = None
    from_status: ClaimStatus | None = None
    to_status: ClaimStatus | None = None
    at: datetime = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.at is None:
            object.__setattr__(self, "at", datetime.now(UTC))

    def to_ref(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "claim_id": self.claim_id,
            "actor": self.actor,
            "kind": self.kind.value,
            "body": self.body,
            "from_status": self.from_status.value if self.from_status else None,
            "to_status": self.to_status.value if self.to_status else None,
            "at": self.at.isoformat().replace("+00:00", "Z"),
        }


def _event_id(claim_id: str, kind: ReviewEventKind, actor: str, salt: str) -> str:
    digest = sha256(f"{claim_id}:{kind.value}:{actor}:{salt}".encode()).hexdigest()[:12]
    return f"REV-{digest}"


def comment_on_claim(
    claim_id: str,
    actor: str,
    body: str,
    *,
    producer: Any = None,
    correlation_id: str | None = None,
) -> ReviewEvent:
    if not body or not body.strip():
        raise ValueError("a review comment cannot be empty")
    event = ReviewEvent(
        event_id=_event_id(claim_id, ReviewEventKind.COMMENT, actor, body[:64]),
        claim_id=claim_id,
        actor=actor,
        kind=ReviewEventKind.COMMENT,
        body=body,
    )
    _emit(
        event_type="science.review.commented",
        payload=event.to_ref(),
        producer=producer,
        correlation_id=correlation_id,
    )
    return event


def change_status(
    claim_id: str,
    actor: str,
    to_status: ClaimStatus,
    from_status: ClaimStatus | None = None,
    *,
    producer: Any = None,
    comment: str | None = None,
    correlation_id: str | None = None,
) -> ReviewEvent:
    event = ReviewEvent(
        event_id=_event_id(claim_id, ReviewEventKind.STATUS_CHANGE, actor, str(to_status.value)),
        claim_id=claim_id,
        actor=actor,
        kind=ReviewEventKind.STATUS_CHANGE,
        body=comment,
        from_status=from_status,
        to_status=to_status,
    )
    _emit(
        event_type="science.review.status_changed",
        payload=event.to_ref(),
        producer=producer,
        correlation_id=correlation_id,
    )
    return event