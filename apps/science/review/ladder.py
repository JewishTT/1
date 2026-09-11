"""Machine-checked evidence ladder (T135, US7, FR-013).

A claim's ladder position is never arbitrary: it equals the number of recorded
artifacts among the four gates (calibration, null model, robustness,
reproduction). The top rung requires ALL recorded gates; a claim without full
provenance cannot be rated at all and renders ``REVIEW_PENDING`` (None).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from claims.model import ScientificClaim


@dataclass(frozen=True)
class LadderGates:
    calibrated: bool = False
    null_model: bool = False
    robustness: bool = False
    reproduction: bool = False

    def held(self) -> int:
        return sum(
            (self.calibrated, self.null_model, self.robustness, self.reproduction)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "calibrated": self.calibrated,
            "null_model": self.null_model,
            "robustness": self.robustness,
            "reproduction": self.reproduction,
        }


def top_rung() -> int:
    """Position of the top rung: all four gates recorded (FR-013)."""
    return 4


def ladder_position(claim: ScientificClaim, gates: LadderGates) -> int | None:
    """Machine-check the gates; ``None`` means the claim cannot be rated.

    Full provenance is the precondition for any rung; without it the claim
    stays ``REVIEW_PENDING`` and the top rung is unreachable.
    """
    if not claim.provenance:
        return None
    return gates.held()