"""Perturbation grid for robustness analysis (T128, US6, FR-011).

The three declared families — missing evidence, flipped labels, biased
subsample — are applied over an explicit grid with a seeded RNG. Perturbations
build fresh copies of evidence links; the original attachments are never
mutated (FR-015). Grid levels are auditable and configurable (research §7).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from random import Random
from typing import Any

from claims.model import EvidenceDirection, EvidenceLink


class PerturbationFamily(StrEnum):
    MISSING = "missing"
    FLIP = "flip"
    BIASED_SUBSAMPLE = "biased_subsample"


@dataclass(frozen=True)
class PerturbationGrid:
    """Declared grid levels per family (FR-011); empty tuple disables a family."""

    missing_fraction: tuple[float, ...] = (0.2,)
    label_flip: tuple[float, ...] = (0.1,)
    biased_subsample: tuple[float, ...] = (0.5, 0.7)
    seed: int = 7

    def levels(self, family: PerturbationFamily) -> tuple[float, ...]:
        return {
            PerturbationFamily.MISSING: self.missing_fraction,
            PerturbationFamily.FLIP: self.label_flip,
            PerturbationFamily.BIASED_SUBSAMPLE: self.biased_subsample,
        }[family]

    def as_dict(self) -> dict[str, Any]:
        return {
            "missing_fraction": list(self.missing_fraction),
            "label_flip": list(self.label_flip),
            "biased_subsample": list(self.biased_subsample),
            "seed": self.seed,
        }


def apply_perturbation(
    evidence: Sequence[EvidenceLink],
    family: PerturbationFamily,
    level: float,
    *,
    seed: int,
) -> list[EvidenceLink]:
    """Return a perturbed copy of ``evidence`` for one grid cell (seeded).

    - MISSING: drop ``level`` fraction of links.
    - FLIP: reverse the direction of ``level`` fraction of SUPPORTS/REFUTES links.
    - BIASED_SUBSAMPLE: keep ``level`` fraction sampled without replacement.
    """
    rng = Random(f"{family.value}:{level}:{seed}")
    pool = list(evidence)
    if family is PerturbationFamily.MISSING:
        keep = max(0, round(len(pool) * (1.0 - level)))
        return [pool[i] for i in _sample_indices(len(pool), keep, rng)]

    if family is PerturbationFamily.FLIP:
        flipped: list[EvidenceLink] = []
        remaining = min(len(pool), max(1, round(len(pool) * level)))
        chosen = set(_sample_indices(len(pool), remaining, rng))
        for index, link in enumerate(pool):
            direction = link.direction
            if index in chosen and direction in {
                EvidenceDirection.SUPPORTS,
                EvidenceDirection.REFUTES,
            }:
                direction = EvidenceDirection.REFUTES if direction is EvidenceDirection.SUPPORTS else EvidenceDirection.SUPPORTS
            flipped.append(
                EvidenceLink(
                    link_id=link.link_id,
                    observation_id=link.observation_id,
                    raw_sha256=link.raw_sha256,
                    direction=direction,
                    weight=link.weight,
                    attached_at=link.attached_at,
                )
            )
        return flipped

    if family is PerturbationFamily.BIASED_SUBSAMPLE:
        keep = max(0, round(len(pool) * level))
        return [pool[i] for i in _sample_indices(len(pool), keep, rng)]

    raise ValueError(f"unknown perturbation family: {family}")


def _sample_indices(size: int, keep: int, rng: Random) -> list[int]:
    if size <= 0 or keep <= 0:
        return []
    return sorted(rng.sample(range(size), min(keep, size)))