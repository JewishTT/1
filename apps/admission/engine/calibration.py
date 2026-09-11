"""Risk-sensitive calibrated admission (T086, FR-013/FR-014).

Categorical hard-reject rules are applied FIRST by the admission engine (see
`admission.py`): invalid identifier → REJECT; explicit strong contradiction →
QUARANTINE/REJECT; insufficient evidence → DEFER; strong corroboration →
ACCEPT. CalibrationProfile is keyed by (entity_type, language, script) with
per-type thresholds. Uncertified bootstrap: UNCALIBRATED v1 (later calibrated
per T085). Consumes T081-T084, T087.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CalibrationProfile:
    entity_type: str
    language: str = "*"
    script: str = "*"
    threshold_defer: float = 0.35
    threshold_accept: float = 0.65
    require_independence: bool = False
    min_independent_support: float = 0.4
    version: str = "UNCALIBRATED-v1"


@dataclass
class AdmissionInput:
    candidate_id: str
    entity_type: str
    language: str = "*"
    script: str = "*"
    structural_score: float = 0.0
    corroboration_score: float = 0.0
    independence_score: float = 0.0
    has_valid_identifier: bool = True
    strong_contradiction: bool = False
    evidence_counts: dict[str, int] = field(default_factory=dict)


class MediaProfile:
    """RFC-000-pattern profile lookup with defaults."""

    def __init__(self) -> None:
        self._profiles: dict[tuple[str, str, str], CalibrationProfile] = {}

    def register(self, profile: CalibrationProfile) -> None:
        self._profiles[
            (profile.entity_type, profile.language, profile.script)
        ] = profile

    def lookup(self, entity_type: str, language: str, script: str) -> CalibrationProfile:
        for key in (
            (entity_type, language, script),
            (entity_type, "*", script),
            (entity_type, "*", "*"),
        ):
            found = self._profiles.get(key)
            if found:
                return found
        return CalibrationProfile(entity_type=entity_type)

    def __len__(self) -> int:
        return len(self._profiles)