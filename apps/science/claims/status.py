"""Claim status transitions (T095; data-model §state transitions).

Append-only: changing a claim's status emits a new ``science.claim.status_changed``
event; the store's Supersedes semantics keep the latest state while the log
remains an immutable history (FR-015, I-12). Illegal jumps are rejected.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from _events import envelope as _emit
from claims.model import ClaimStatus, ScientificClaim

_ALLOWED: dict[ClaimStatus, set[ClaimStatus]] = {
    ClaimStatus.DRAFT: {
        ClaimStatus.CONFIRMED,
        ClaimStatus.WEAKENED,
        ClaimStatus.DISCARDED,
        ClaimStatus.UNCERTAIN,
    },
    ClaimStatus.WEAKENED: {ClaimStatus.UNCERTAIN, ClaimStatus.DISCARDED},
    ClaimStatus.UNCERTAIN: {ClaimStatus.DISCARDED, ClaimStatus.CONFIRMED},
    ClaimStatus.CONFIRMED: {ClaimStatus.WEAKENED, ClaimStatus.UNCERTAIN},
    ClaimStatus.DISCARDED: set(),
}


def transition_status(
    claim: ScientificClaim,
    to_status: ClaimStatus,
    *,
    actor: str = "system",
    producer: Any = None,
    store: Any = None,
) -> ScientificClaim:
    """Transition a claim's status, emitting an append-only event (T095)."""
    if to_status not in _ALLOWED.get(claim.status, set()):
        raise ValueError(
            f"illegal transition {claim.status.value} -> {to_status.value} for {claim.claim_id}"
        )
    env = _emit(
        event_type="science.claim.status_changed",
        payload={
            "claim_id": claim.claim_id,
            "from_status": claim.status.value,
            "to_status": to_status.value,
            "actor": actor,
            "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        },
        producer=producer,
        investigation_id=claim.project_id,
    )
    if store is not None:
        store.apply(env)
    claim.status = to_status
    return claim