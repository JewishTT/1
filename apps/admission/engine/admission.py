"""Admission engine core (T036, FR-013/FR-014).

Score vector fields are separate (structural, corroboration, independence); the
decision policy applies hard-reject rules first, then profile thresholds.
Output: AdmissionResult with explicit reason codes + evidence refs; rejected
assertions are kept replayable (never deleted) and recorded per FR-013.

The policy is an ordered ladder, first match wins, mirroring the table in
`calibration.py`. It is written as an explicit sequence of guards rather than a
list of (name, condition) pairs scored in one pass, because the previous
single-pass form made the outcome depend on every rule firing at once: it
attached *all* satisfied rules to the reason codes, so a hard-rejected candidate
could report ``accept_strong_corroboration`` alongside
``hard_reject_invalid_id``. Reason codes now describe only the branch that
actually decided the outcome.

ACCEPT_EXISTING is the merge case: resolution matched this candidate to an
entity that is already admitted, so admitting it strengthens an existing entity
instead of creating a duplicate one. It is reachable only once the candidate has
cleared the evidence floors, and the matched entity is carried on the result so
callers can route the merge without re-running resolution.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .assertions import EvidenceLink
from .calibration import AdmissionInput, CalibrationProfile, MediaProfile
from .temporal import AssertionRecord


class AdmitDecision(str, enum.Enum):
    ACCEPT_NEW = "ACCEPT_NEW"
    ACCEPT_EXISTING = "ACCEPT_EXISTING"
    DEFER = "DEFER"
    REJECT = "REJECT"
    QUARANTINE = "QUARANTINE"


@dataclass
class ScoreVector:
    structural: float
    corroboration: float
    independence: float
    evidence_publications: int = 0

    def to_dict(self) -> dict[str, float]:
        return {
            "structural": self.structural,
            "corroboration": self.corroboration,
            "independence": self.independence,
            "evidence_publications": float(self.evidence_publications),
        }


@dataclass
class AdmissionResult:
    admission_id: str = field(default_factory=lambda: "AD-" + uuid.uuid4().hex[:12])
    candidate_id: str = ""
    decision: AdmitDecision = AdmitDecision.DEFER
    score_vector: ScoreVector | None = None
    reason_codes: list[str] = field(default_factory=list)
    evidence: EvidenceLink | None = None
    assertion: AssertionRecord | None = None
    policy_version: str = "UNCALIBRATED-v1"
    profile: CalibrationProfile | None = None
    decided_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    replayable: bool = True  # FR-013: rejected kept replayable
    # Set when resolution matched this candidate to an already-admitted entity.
    matched_entity_id: str | None = None
    match_score: float = 0.0
    #: The counts that fed the decision, carried onto the decision itself.
    #:
    #: **WP-E T071.** These were computed by intake and then dropped on the floor: the
    #: score vector carries the three derived scalars, but not the raw counts they came
    #: from, and certainly not *which measure* produced them. A reader of the decision
    #: could see corroboration 0.5 and not know whether that meant two hosts or two
    #: origins. Storing the distinction is what makes it auditable after the fact.
    evidence_counts: dict[str, int | str] = field(default_factory=dict)

    @property
    def is_merge(self) -> bool:
        """True when the decision strengthens an existing entity, not a new one."""
        return self.decision is AdmitDecision.ACCEPT_EXISTING

    @property
    def target_entity_id(self) -> str | None:
        """Entity the admission applies to: the merge target, else the candidate."""
        return self.matched_entity_id if self.is_merge else None


class AdmissionEngine:
    def __init__(self, profiles: MediaProfile | None = None) -> None:
        self._profiles = profiles or MediaProfile()
        self._decisions: dict[str, AdmissionResult] = {}

    def decide(self, inp: AdmissionInput, evidence: EvidenceLink | None = None) -> AdmissionResult:
        """Apply the admission ladder and retain the decision for replay (FR-013)."""
        profile = self._profiles.lookup(inp.entity_type, inp.language, inp.script)
        vector = ScoreVector(
            structural=inp.structural_score,
            corroboration=inp.corroboration_score,
            independence=inp.independence_score,
            evidence_publications=len(evidence.evidence_refs) if evidence else 0,
        )
        result = AdmissionResult(
            admission_id="AD-" + uuid.uuid4().hex[:12],
            candidate_id=inp.candidate_id,
            score_vector=vector,
            evidence=evidence,
            policy_version=profile.version,
            profile=profile,
            matched_entity_id=inp.matched_entity_id,
            match_score=inp.match_score,
            evidence_counts=dict(inp.evidence_counts),
        )
        result.decision, result.reason_codes = self._apply_ladder(inp, vector, profile)
        self._decisions[result.admission_id] = result  # replayable
        return result

    def _apply_ladder(
        self, inp: AdmissionInput, vector: ScoreVector, profile: CalibrationProfile
    ) -> tuple[AdmitDecision, list[str]]:
        """Ordered rules, first match wins. Returns (decision, reason codes)."""
        if not inp.has_valid_identifier:
            return AdmitDecision.REJECT, ["hard_reject_invalid_id"]
        if inp.strong_contradiction:
            # Contradictory evidence is not merely wrong, it is untrustworthy
            # evidence: park it for review instead of rejecting it outright.
            return AdmitDecision.QUARANTINE, ["hard_reject_contradiction"]
        if vector.corroboration < profile.threshold_defer:
            return AdmitDecision.DEFER, ["defer_insufficient_evidence"]
        if profile.require_independence and vector.independence < profile.min_independent_support:
            return AdmitDecision.DEFER, ["defer_weak_independence"]
        if self._is_merge(inp, profile):
            # The candidate is a second sighting of an admitted entity.
            return AdmitDecision.ACCEPT_EXISTING, ["accept_existing_match"]
        # **WP-E T070:** an unconfirmed match that cleared an uncalibrated bar did
        # *not* merge. The candidate continues down the ladder, and the reason the
        # merge was withheld travels with the decision so a reviewer sees why this is
        # sitting in front of them rather than being silently fused or silently lost.
        withheld = self.merge_refusal(inp, profile)
        if withheld:
            reasons = [withheld]
        else:
            reasons = []
        if vector.corroboration >= profile.threshold_accept:
            return AdmitDecision.ACCEPT_NEW, reasons + ["accept_strong_corroboration"]
        if vector.structural >= 0.7:
            return AdmitDecision.ACCEPT_NEW, reasons + ["accept_qualified_structurally"]
        return AdmitDecision.DEFER, reasons + ["no_confident_signal"]

    @staticmethod
    def _is_merge(inp: AdmissionInput, profile: CalibrationProfile) -> bool:
        """Whether an unconfirmed match may merge without review.

        **WP-E T070.** A *reviewed* match (``match_confirmed``) always merges: a human
        looked at it, and no threshold can overrule that. An *unreviewed* one may not
        merge at all when the profile declares itself uncalibrated.

        Previously the gate was ``match_score >= profile.threshold_match`` — a bar of
        0.8, against a profile whose own ``version`` field reads
        ``"UNCALIBRATED-v1"``, out of a ``MediaProfile`` that starts empty so every
        unregistered entity type falls back to exactly these defaults. The audit found
        this: a merge decided by a number nobody fitted.

        The bar is not lowered here. It is *not applied* unless someone has declared
        that the number means something. That is the difference between a threshold and
        a guess, and a guess that fuses two people is not recoverable after the fact.

        Refusing to merge is not refusing the candidate: the ladder still runs, and an
        unmerged candidate with strong corroboration is still admitted as a new
        entity and routed to review rather than silently fused.
        """
        if not inp.has_existing_match:
            return False
        if inp.match_confirmed:
            return True
        if not profile.is_calibrated:
            return False
        return inp.match_score >= profile.threshold_match

    @staticmethod
    def merge_refusal(inp: AdmissionInput, profile: CalibrationProfile) -> str:
        """Why an automatic merge was withheld, or ``""`` when it was allowed."""
        if not inp.has_existing_match or inp.match_confirmed:
            return ""
        if profile.is_calibrated:
            return ""
        return profile.merge_bar()

    def resident(self, admission_id: str) -> AdmissionResult | None:
        return self._decisions.get(admission_id)