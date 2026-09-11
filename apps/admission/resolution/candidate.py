"""Resolution candidates with human review and non-destructive merge (feature 005, US2).

Ported pattern: OpenOSINT (MIT) `openosint/graph/store/resolutions.py` +
`openosint/graph/review.py` — an append-only merge-decision record (a decision
never mutates statements or history; "which entity is canonical" is a QUERY,
not a stored mutable fact) and a reviewable candidate queue where a human
decision is the ONLY path that may mark a pair positive.

Mapping onto the platform vocabulary: a pair of correlated candidates
(``CorrelationService`` edges, I-2) becomes a ``Candidate`` whose ``pair_key``
is deterministic; ``decide_candidate()`` / ``reverse_resolution()`` append
immutable ``ResolutionRecord`` entries (reject persists so the pair is not
re-proposed at equal evidence; reverse appends a superseding record that
revokes a prior accept). ``apply_review`` bridges the control-plane
``ReviewRecord`` (ReviewDecision ACCEPT/REJECT/UNCERTAIN) onto candidate state.

   Source repo : https://github.com/owtf/OpenOSINT (donors/OpenOSINT)
   License     : MIT
   What changed: store/graph → in-memory dataclasses; ``judgements`` vocabulary
                 mapped to candidate review states; reverse/reject semantics
                 merged into one append-only revision list.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class CandidateState(str, Enum):
    OPEN = "open"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REVERSED = "reversed"


# Review decision vocabulary (control-plane ReviewDecision) → candidate state.
def state_from_review(decision: str) -> CandidateState:
    mapping = {
        "ACCEPT": CandidateState.ACCEPTED,
        "REJECT": CandidateState.REJECTED,
        "UNCERTAIN": CandidateState.OPEN,
    }
    try:
        return mapping[decision]
    except KeyError as exc:
        raise ValueError(f"unknown review decision: {decision!r}") from exc


def pair_key(candidate_a: str, candidate_b: str) -> str:
    """Deterministic, order-insensitive key identifying an unordered pair (I-2)."""
    if candidate_a == candidate_b:
        raise ValueError("a candidate pair links two DISTINCT entities")
    return f"{min(candidate_a, candidate_b)}&&{max(candidate_a, candidate_b)}"


def _evidence_fingerprint(reasons: list[str]) -> tuple[str, ...]:
    return tuple(sorted(reasons))


@dataclass
class ResolutionRecord:
    """One append-only merge decision; existing records are never mutated (I-2).

    ``revokes_resolution_id`` is audit metadata pointing at the ``ResolutionRecord``
    this record supersedes (reverse appends one). "Latest record per pair" drives
    the pair's state; original entities remain queryable either way.
    """

    resolution_id: str = field(default_factory=lambda: "RESV-" + uuid.uuid4().hex[:12])
    pair_key: str = ""
    decision: CandidateState = CandidateState.OPEN
    decided_by: str = ""  # human|auto
    decided_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    reviewer_id: str | None = None
    revokes_resolution_id: str | None = None
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "resolution_id": self.resolution_id,
            "pair_key": self.pair_key,
            "decision": self.decision.value,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
            "reviewer_id": self.reviewer_id,
            "revokes_resolution_id": self.revokes_resolution_id,
            "detail": dict(self.detail),
        }


@dataclass
class Candidate:
    """A reviewable possible-identity pair (never auto-merged, I-2)."""

    pair_key: str
    candidate_a: str
    candidate_b: str
    schema_name: str = ""
    raw_pair_score: float = 0.0
    collective_score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    state: CandidateState = CandidateState.OPEN
    decision_revision: list[ResolutionRecord] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict:
        return {
            "pair_key": self.pair_key,
            "candidate_a": self.candidate_a,
            "candidate_b": self.candidate_b,
            "schema_name": self.schema_name,
            "raw_pair_score": round(self.raw_pair_score, 3),
            "collective_score": round(self.collective_score, 3),
            "reasons": list(self.reasons),
            "state": self.state.value,
            "decision_count": len(self.decision_revision),
            "created_at": self.created_at,
        }

    @property
    def latest_record(self) -> ResolutionRecord | None:
        return self.decision_revision[-1] if self.decision_revision else None


def create_candidate(
    candidate_a: str,
    candidate_b: str,
    *,
    schema_name: str = "",
    raw_pair_score: float = 0.0,
    collective_score: float = 0.0,
    reasons: list[str] | None = None,
) -> Candidate:
    """Build a Candidate with a deterministic pair_key."""
    return Candidate(
        pair_key=pair_key(candidate_a, candidate_b),
        candidate_a=candidate_a,
        candidate_b=candidate_b,
        schema_name=schema_name,
        raw_pair_score=raw_pair_score,
        collective_score=collective_score,
        reasons=list(reasons or []),
    )


def decide_candidate(
    candidate: Candidate,
    decision: CandidateState,
    *,
    decided_by: str = "human",
    decided_at: datetime | None = None,
    reviewer_id: str | None = None,
    revokes_resolution_id: str | None = None,
    detail: dict | None = None,
    reasons: list[str] | None = None,
) -> ResolutionRecord:
    """Append a human decision to a pair (append-only; earlier records untouched).

    ``REJECTED`` persists as a blocking record: the pair stays queryable but is
    not re-proposed at the same evidence. ``ACCEPTED`` records a merge intent —
    the original entities are always retained (I-2); the record is what a
    projection replays to rebuild identity.
    """
    if decision not in CandidateState:
        raise ValueError(f"invalid candidate decision: {decision!r}")
    if decision == CandidateState.REVERSED and candidate.state != CandidateState.ACCEPTED:
        raise ValueError("reverse is only valid on an accepted candidate")
    record = ResolutionRecord(
        pair_key=candidate.pair_key,
        decision=decision,
        decided_by=decided_by,
        decided_at=(decided_at or datetime.now(UTC)).isoformat(),
        reviewer_id=reviewer_id,
        revokes_resolution_id=revokes_resolution_id,
        detail={"evidence": _evidence_fingerprint(reasons or candidate.reasons), **(detail or {})},
    )
    candidate.decision_revision.append(record)
    candidate.state = decision
    return record


def reverse_resolution(
    candidate: Candidate,
    *,
    decided_by: str = "human",
    decided_at: datetime | None = None,
    reviewer_id: str | None = None,
    reasons: list[str] | None = None,
) -> ResolutionRecord:
    """Revoke a prior accept by appending a superseding record (never in-place)."""
    prior = candidate.latest_record
    if candidate.state != CandidateState.ACCEPTED or prior is None:
        raise ValueError("reverse requires a previously accepted candidate")
    return decide_candidate(
        candidate,
        CandidateState.REVERSED,
        decided_by=decided_by,
        decided_at=decided_at,
        reviewer_id=reviewer_id,
        revokes_resolution_id=prior.resolution_id,
        reasons=reasons,
    )


def apply_review(
    candidate: Candidate,
    decision: str,
    *,
    reviewer_id: str | None = None,
    reviewed_at: datetime | None = None,
    reasons: list[str] | None = None,
) -> ResolutionRecord:
    """Bridge a control-plane ReviewDecision ('ACCEPT'|'REJECT'|'UNCERTAIN') to state.

    A REJECT on an accepted pair is a reversal (OpenOSINT: append a
    non-positive row for the same pair), so it supersedes rather than erases.
    """
    desired = state_from_review(decision)
    if desired == CandidateState.REJECTED and candidate.state == CandidateState.ACCEPTED:
        return reverse_resolution(
            candidate, decided_at=reviewed_at, reviewer_id=reviewer_id, reasons=reasons
        )
    return decide_candidate(
        candidate,
        desired,
        decided_at=reviewed_at,
        reviewer_id=reviewer_id,
        reasons=reasons,
    )


def is_merge_blocked(
    candidate: Candidate, *, reasons: list[str] | None = None
) -> bool:
    """REJECT persists: at equal evidence the pair is not re-proposed (I-2).

    A later candidate with stronger evidence (a superset of the rejected
    features) is NOT blocked — only identical evidence is suppressed. A
    REVERSED pair (prior accept revoked) remains eligible for re-review.
    """
    if candidate.state != CandidateState.REJECTED:
        return False
    if not candidate.decision_revision:
        return False
    prior = candidate.decision_revision[-1]
    previous = set(prior.detail.get("evidence") or ())
    current = set(_evidence_fingerprint(reasons or candidate.reasons))
    return current == previous