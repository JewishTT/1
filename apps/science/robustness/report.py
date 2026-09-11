"""Flip rates, sensitivity and noise regions (T129, US6, FR-011).

The "conclusion" of a claim is its signed evidence margin (weighted SUPPORTS
minus REFUTES, normalised by total weight); a perturbation cell flips the
conclusion when that margin's sign changes. Flip rates per family + a
sensitivity summary + explicit noise regions are reported, so fragility is
made visible rather than hidden behind a bare "significant" label (research §7).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Any

from claims.model import EvidenceDirection, EvidenceLink
from robustness.perturb import (
    PerturbationFamily,
    PerturbationGrid,
    apply_perturbation,
)


class RobustnessOutcome(StrEnum):
    STABLE = "stable"
    FLIPPED = "flipped"


@dataclass(frozen=True)
class RobustnessReport:
    report_id: str
    claim_ref: str
    perturbations: list[dict[str, Any]]
    flip_rates: dict[str, float]
    sensitivity_summary: dict[str, float]
    noise_regions: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "claim_ref": self.claim_ref,
            "perturbations": self.perturbations,
            "flip_rates": self.flip_rates,
            "sensitivity_summary": self.sensitivity_summary,
            "noise_regions": self.noise_regions,
        }


def _margin(evidence: Sequence[EvidenceLink]) -> tuple[float, float]:
    """Signed evidence margin (SUPPORTS − REFUTES) normalised to [−1, 1]."""
    signed = 0.0
    for link in evidence:
        if link.direction is EvidenceDirection.SUPPORTS:
            signed += link.weight
        elif link.direction is EvidenceDirection.REFUTES:
            signed -= link.weight
    total = sum(link.weight for link in evidence) or 0.0
    if total <= 0.0:
        return 0.0, 0.0
    margin = signed / total
    return margin, margin if margin >= 0 else -margin


def _conclusion(evidence: Sequence[EvidenceLink]) -> int:
    margin, _ = _margin(evidence)
    if margin > 0:
        return 1
    if margin < 0:
        return -1
    return 0


def analyze_robustness(
    claim_id: str,
    evidence: Sequence[EvidenceLink],
    *,
    perturbations: PerturbationGrid,
) -> RobustnessReport:
    """Run the declared perturbation grid and report per-family flip rates."""
    baseline = _conclusion(evidence)
    baseline_margin, _ = _margin(evidence)

    flip_rates: dict[str, float] = {family.value: 0.0 for family in PerturbationFamily}
    sensitivity: dict[str, float] = {}
    noise_regions: list[dict[str, Any]] = []
    grid_spec: list[dict[str, Any]] = []

    for family in PerturbationFamily:
        levels = perturbations.levels(family)
        grid_spec.append({"family": family.value, "levels": list(levels)})
        if not levels:
            sensitivity[family.value] = 0.0
            continue
        flipped_count = 0
        margin_deltas: list[float] = []
        for level in levels:
            perturbed = apply_perturbation(evidence, family, level, seed=perturbations.seed)
            margin, _ = _margin(perturbed)
            outcome = RobustnessOutcome.FLIPPED if _conclusion(perturbed) != baseline else RobustnessOutcome.STABLE
            if outcome is RobustnessOutcome.FLIPPED:
                flipped_count += 1
            margin_deltas.append(abs(margin - baseline_margin))
            noise_regions.append(
                {
                    "family": family.value,
                    "level": level,
                    "flipped": outcome is RobustnessOutcome.FLIPPED,
                    "margin": round(margin, 6),
                }
            )
        flip_rates[family.value] = round(flipped_count / len(levels), 6)
        sensitivity[family.value] = round(sum(margin_deltas) / len(margin_deltas), 6)

    digest = sha256(f"rb:{claim_id}:{perturbations.as_dict()}".encode()).hexdigest()[:12]
    return RobustnessReport(
        report_id=f"RB-{digest}",
        claim_ref=claim_id,
        perturbations=grid_spec,
        flip_rates=flip_rates,
        sensitivity_summary=sensitivity,
        noise_regions=noise_regions,
    )