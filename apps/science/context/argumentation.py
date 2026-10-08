"""Candidate ranking under a declared mode (spec 025 §20.3, §46.1).

§20.3 removes the v1 ranking outright:

> The v1 multiplicative utility (``IG x feasibility x quality x discrimination /
> cost``) is **removed**.

and replaces it with six rules. The one that matters most in practice is the first:

> **Hard gates are filters, not factors.** Policy status, capability availability,
> safety policy and feasibility act as *filters*; they never multiply into a score.

That is not cosmetic. In a multiplicative formula a candidate blocked by policy can
still win by having a large enough gain, because the gain multiplies and the
blocker does not. A safety filter that can be outvoted by a good score is not a
safety filter.

Two further rules are enforced here rather than documented:

* **No cross-tier numeric comparison.** ``IG_PROBABILISTIC`` values are compared
  only with other ``IG_PROBABILISTIC`` values (§20.3 rule 3). Comparing a
  calibrated probability against a surrogate separation score produces a number
  with no meaning.
* **A declared cost floor.** Where cost appears as a divisor, ``epsilon > 0``
  applies, so zero or unknown cost cannot produce an infinite ranking.

``PARETO_THEN_TIEBREAK`` keeps the non-dominated set, which is the honest default
when criteria are not commensurable: the answer is a set, not a winner.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


class RankingMode(enum.StrEnum):
    """§20.3 rule 2, exactly these three, spelled as the specification spells them."""

    LEXICOGRAPHIC = "LEXICOGRAPHIC"
    PARETO_THEN_TIEBREAK = "PARETO_THEN_TIEBREAK"
    WEIGHTED_ADDITIVE_NORMALIZED = "WEIGHTED_ADDITIVE_NORMALIZED"


class GainTier(enum.StrEnum):
    """§20.1, spelled as the specification spells them."""

    IG_PROBABILISTIC = "IG_PROBABILISTIC"
    SURROGATE_SEPARATION = "SURROGATE_SEPARATION"
    SURROGATE_CONTRADICTION_REDUCTION = "SURROGATE_CONTRADICTION_REDUCTION"
    SURROGATE_COVERAGE = "SURROGATE_COVERAGE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class Candidate:
    """One actionable option with everything ranking needs, and nothing else."""

    candidate_id: str
    #: Numeric criteria keyed by name. Tiered values live in ``gain_tier`` instead,
    #: so a tiered value can never be silently mixed with a numeric one.
    criteria: Mapping[str, float]
    gain_tier: GainTier = GainTier.UNKNOWN
    gain_value: float | None = None
    #: Hard filters. A false here removes the candidate; it never lowers a score.
    policy_allowed: bool = True
    capabilities_available: bool = True
    safety_clear: bool = True
    feasible: bool = True
    cost: float | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.candidate_id:
            raise ValueError("a candidate must be identifiable")
        if self.cost is not None and self.cost < 0:
            raise ValueError(f"cost must be non-negative, got {self.cost}")

    @property
    def blocked_reason(self) -> str:
        """Which filter removed it, or ``""``."""
        if not self.policy_allowed:
            return "policy"
        if not self.capabilities_available:
            return "capability"
        if not self.safety_clear:
            return "safety"
        if not self.feasible:
            return "feasibility"
        return ""

    @property
    def is_viable(self) -> bool:
        """§20.3 rule 1: filters, not factors."""
        return not self.blocked_reason


def effective_cost(candidate: Candidate, *, floor: float = 1e-9) -> float:
    """§20.3 rule 5: a declared positive floor, so zero/unknown cannot divide out."""
    if candidate.cost is None:
        return floor
    return max(candidate.cost, floor)


def _dominated_by(candidate: Candidate, other: Candidate, dimensions: Sequence[str]) -> bool:
    """§46.1 dominance, restricted to the declared dimensions.

    Equal values do not dominate: a candidate is dominated only when another is
    *no worse* everywhere and *strictly* better somewhere.
    """
    if candidate.candidate_id == other.candidate_id:
        return False
    no_worse = all(
        other.criteria.get(name, 0.0) >= candidate.criteria.get(name, 0.0)
        for name in dimensions
    )
    strictly_better = any(
        other.criteria.get(name, 0.0) > candidate.criteria.get(name, 0.0)
        for name in dimensions
    )
    return no_worse and strictly_better


def rank_candidates(
    candidates: Sequence[Candidate],
    *,
    mode: str = RankingMode.LEXICOGRAPHIC,
    criteria_order: Sequence[str] = (),
    dimensions: Sequence[str] = (),
    tiebreak: str = "candidate_id",
) -> dict[str, Any]:
    """Rank under one declared mode, returning the mode alongside the result.

    Returning the mode is deliberate: §20.3 rule 6 requires every factor and
    transformation to be declared in the profile and *echoed*, so a stored ranking
    must say how it was produced.
    """
    selected = RankingMode(mode)
    viable = [candidate for candidate in candidates if candidate.is_viable]
    blocked = [
        {"candidate_id": candidate.candidate_id, "reason": candidate.blocked_reason}
        for candidate in candidates
        if not candidate.is_viable
    ]

    if selected is RankingMode.PARETO_THEN_TIEBREAK:
        axes = tuple(dimensions) or tuple(criteria_order)
        front = [
            candidate
            for candidate in viable
            if not any(_dominated_by(candidate, other, axes) for other in viable)
        ]
        ranked = sorted(front, key=_tiebreak_key(tiebreak))
        return {
            "mode": selected.value,
            "ranked": [candidate.candidate_id for candidate in ranked],
            "non_dominated": [candidate.candidate_id for candidate in ranked],
            "blocked": blocked,
            "note": "non-commensurable criteria return a set, not a winner",
        }

    order = tuple(criteria_order) or tuple(sorted(viable[0].criteria)) if viable else ()

    if selected is RankingMode.LEXICOGRAPHIC:
        # Tier-aware: candidates in different gain tiers never compare numerically.
        def sort_key(candidate: Candidate):
            tier_rank = sorted(GainTier, key=lambda item: item.value).index(candidate.gain_tier)
            values = tuple(-candidate.criteria.get(name, 0.0) for name in order)
            gain = -(candidate.gain_value if candidate.gain_value is not None else 0.0)
            return (tier_rank, gain, values, _tiebreak_key(tiebreak)(candidate))

        ranked = sorted(viable, key=sort_key)
        return {
            "mode": selected.value,
            "ranked": [candidate.candidate_id for candidate in ranked],
            "criteria_order": list(order),
            "blocked": blocked,
        }

    # WEIGHTED_ADDITIVE_NORMALIZED, permitted only over a common declared scale.
    scales = sorted({name for candidate in viable for name in candidate.criteria})
    spread: dict[str, float] = {}
    for name in scales:
        values = [candidate.criteria.get(name, 0.0) for candidate in viable]
        span = max(values) - min(values) if values else 0.0
        spread[name] = span if span > 0 else 1.0

    def additive_key(candidate: Candidate):
        total = 0.0
        for name in order:
            value = candidate.criteria.get(name, 0.0)
            total += value / spread.get(name, 1.0)
        return (-total, _tiebreak_key(tiebreak)(candidate))

    ranked = sorted(viable, key=additive_key)
    return {
        "mode": selected.value,
        "ranked": [candidate.candidate_id for candidate in ranked],
        "normalized_over": list(order),
        "blocked": blocked,
    }


def _tiebreak_key(tiebreak: str):
    """Declared tie-break only. There is no default preference."""
    if tiebreak == "cost":
        return lambda candidate: (
            effective_cost(candidate),
            candidate.candidate_id,
        )
    return lambda candidate: candidate.candidate_id


def dominance_front(
    candidates: Sequence[Candidate], dimensions: Sequence[str]
) -> tuple[str, ...]:
    """The §46.1 non-dominated set, exposed for the UI."""
    viable = [candidate for candidate in candidates if candidate.is_viable]
    return tuple(
        candidate.candidate_id
        for candidate in viable
        if not any(_dominated_by(candidate, other, dimensions) for other in viable)
    )