"""Admission engine core (T036, FR-013/FR-014).

Score vector fields are separate (structural, corroboration, independence);
the decision policy applies hard-reject rules first, then profile thresholds.
Output: ADMIT_DECISION with explicit reason codes + evidence refs; rejected
assertions are kept replayable (never deleted) and recorded per FR-013.
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


class AdmissionEngine:
    def __init__(self, profiles: MediaProfile | None = None) -> None:
        self._profiles = profiles or MediaProfile()
        self._decisions: dict[str, AdmissionResult] = {}

    def decide(self, inp: AdmissionInput, evidence: EvidenceLink | None = None) -> AdmissionResult:
        profile = self._profiles.lookup(inp.entity_type, inp.language, inp.script)
        vector = ScoreVector(
            structural=inp.structural_score,
            corroboration=inp.corroboration_score,
            independence=inp.independence_score,
            evidence_publications=len(evidence.evidence_refs) if evidence else 0,
        )

        rules = [
            ("hard_reject_invalid_id", inp.has_valid_identifier is False),
            ("hard_reject_contradiction", inp.strong_contradiction is True),
            ("defer_insufficient_evidence", vector.corroboration < profile.threshold_defer),
            ("defer_weak_independence", profile.require_independence and vector.independence < profile.min_independent_support),
            ("accept_strong_corroboration", vector.corroboration >= profile.threshold_accept),
            ("accept_qualified_structurally", vector.structural >= 0.7),
        ]
        result = AdmissionResult(
            admission_id="AD-" + uuid.uuid4().hex[:12],
            candidate_id=inp.candidate_id,
            score_vector=vector,
            evidence=evidence,
            policy_version=profile.version,
            profile=profile,
        )
        if rules[0][1] or rules[1][1]:
            result.decision = AdmitDecision.QUARANTINE if inp.strong_contradiction else AdmitDecision.REJECT
            result.reason_codes = [name for name, hit in rules if hit]
            if rules[0][1]:
                result.decision = AdmitDecision.REJECT
        elif rules[2][1] or rules[3][1]:
            result.decision = AdmitDecision.DEFER
            result.reason_codes = [name for name, hit in rules[2:4] if hit]
        elif rules[4][1] or rules[5][1]:
            result.decision = AdmitDecision.ACCEPT_NEW
            result.reason_codes = [name for name, hit in rules[4:] if hit]
        else:
            result.decision = AdmitDecision.DEFER
            result.reason_codes = ["no_confident_signal"]

        self._decisions[result.admission_id] = result  # replayable
        return result

    def resident(self, admission_id: str) -> AdmissionResult | None:
        return self._decisions.get(admission_id)