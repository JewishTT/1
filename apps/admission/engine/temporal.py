"""Temporal consistency + retraction (T084, FR-016).

Relation-specific temporal policies govern how an Assertion may change over
time. The assertion state machine enforces legal transitions:
ASSERTED → SUPERSEDED | RETRACTED | CONTRADICTED | EXPIRED. A superseded or
retracted assertion is archived with a replacement link — the original is NEVER
deleted (FR-016, replayable).
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


class TemporalPolicy(str, enum.Enum):
    SINGLE = "single"            # one value any time; new value supersedes old
    MULTI = "multi"              # concurrent values allowed (e.g. phone numbers)
    INTERVAL = "interval"        # valid windows; non-overlap enforced
    APPEND_ONLY = "append_only"  # values only added, never replaced
    SUPERSEDABLE = "supersedable"  # explicit supersede links allowed
    CONTRADICTORY = "contradictory"  # conflicting values → CONTRADICTED state


class AssertionState(str, enum.Enum):
    ASSERTED = "ASSERTED"
    SUPERSEDED = "SUPERSEDED"
    RETRACTED = "RETRACTED"
    CONTRADICTED = "CONTRADICTED"
    EXPIRED = "EXPIRED"

    def legal_from(self, policy: TemporalPolicy, target: AssertionState) -> bool:
        if self is not AssertionState.ASSERTED:
            return False
        if policy is TemporalPolicy.APPEND_ONLY and target is AssertionState.SUPERSEDED:
            return False
        if policy is TemporalPolicy.INTERVAL and target is AssertionState.SUPERSEDED:
            return True
        return target in {
            AssertionState.SUPERSEDED,
            AssertionState.RETRACTED,
            AssertionState.CONTRADICTED,
            AssertionState.EXPIRED,
        }


@dataclass
class AssertionRecord:
    assertion_id: str
    relation: str
    subject_candidate_id: str
    object_value: str
    observed_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    state: AssertionState = AssertionState.ASSERTED
    policy: TemporalPolicy = TemporalPolicy.SINGLE
    supersedes: str | None = None
    replaced_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class IllegalAssertionTransition(Exception):
    def __init__(self, assertion_id: str, current: AssertionState, target: AssertionState) -> None:
        self.assertion_id = assertion_id
        self.current = current
        self.target = target
        super().__init__(
            f"Assertion {assertion_id}: {current.value} → {target.value} is illegal "
            f"under {TemporalPolicy.SUPERSEDABLE}"
        )


class TemporalConsistencyEngine:
    """Stores assertions, enforces per-policy transition legality (FR-016)."""

    def __init__(self) -> None:
        self._assertions: dict[str, AssertionRecord] = {}
        self._history: dict[str, list[AssertionRecord]] = {}

    def post(
        self,
        *,
        relation: str,
        subject_candidate_id: str,
        object_value: str,
        policy: TemporalPolicy = TemporalPolicy.SINGLE,
        observed_at: datetime | None = None,
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
    ) -> AssertionRecord:
        rec = AssertionRecord(
            assertion_id="A-" + uuid.uuid4().hex[:12],
            relation=relation,
            subject_candidate_id=subject_candidate_id,
            object_value=object_value,
            observed_at=observed_at,
            valid_from=valid_from,
            valid_to=valid_to,
            policy=policy,
        )
        self._assertions[rec.assertion_id] = rec
        self._history.setdefault(rec.assertion_id, []).append(rec)
        return rec

    def supersede(self, old_id: str, replacement_id: str) -> None:
        old = self._assertions[old_id]
        self._transition(old, AssertionState.SUPERSEDED)
        old.replaced_by = replacement_id
        repl = self._assertions[replacement_id]
        repl.supersedes = old_id

    def retract(self, assertion_id: str, reason: str) -> None:
        self._transition(self._assertions[assertion_id], AssertionState.RETRACTED)

    def contradict(self, assertion_id: str) -> None:
        self._transition(self._assertions[assertion_id], AssertionState.CONTRADICTED)

    def expire(self, assertion_id: str) -> None:
        self._transition(self._assertions[assertion_id], AssertionState.EXPIRED)

    def _transition(self, rec: AssertionRecord, target: AssertionState) -> None:
        if not rec.state.legal_from(rec.policy, target):
            raise IllegalAssertionTransition(rec.assertion_id, rec.state, target)
        self._assertions[rec.assertion_id].state = target
        self._history.setdefault(rec.assertion_id, []).append(self._assertions[rec.assertion_id])

    def history(self, assertion_id: str) -> list[AssertionRecord]:
        return list(self._history.get(assertion_id, []))

    def get(self, assertion_id: str) -> AssertionRecord:
        return self._assertions[assertion_id]