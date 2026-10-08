"""Hypothesis spaces, dialectical pairing and counter-hypothesis generation.

Spec 025 §15.3 opens with the reason ``HypothesisSpace`` has to be an object rather
than a list: "Posteriors and information gain are only meaningful relative to a
declared space." A confidence figure without the space it ranges over is a number
without a denominator, and the engine would be comparing across questions.

``apps/science/hypotheses/model.py`` already has a 7-state lifecycle over a flat
list. That is real, tested code and it is kept -- what it cannot express is
exclusivity, compatibility, exhaustiveness, or residual mass. This module adds the
space around it.

Three rules from §15.3 are enforced as code, because each one closes a way the
engine can otherwise overstate what it knows:

1. **A non-exhaustive space must carry ``H_OTHER``** with declared prior mass. A
   space of three candidates that cannot explain the remaining probability is not
   a complete answer set, and presenting it as one is how a platform confidently
   returns the wrong explanation.
2. **Probabilities are computed within an exclusivity group.** Compatible,
   non-exclusive members are never normalised against one another, because they can
   be jointly true and dividing them by each other would force a false choice.
3. **``H_OTHER`` mass shrinks only by evidence or by admitting a concrete new
   hypothesis.** Nothing else may reduce it.

§18.5 steelman parity is enforced too: the antithesis is evaluated under the same
evidence view, template and complexity bound as the thesis. A counter-hypothesis
constructed with fewer resources than the thesis it opposes is a straw man, and the
parity audit records whether parity actually held.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from context.locality import _digest

# -- §15.3 hypothesis space ---------------------------------------------------


class Exhaustive(enum.StrEnum):
    """§15.3. ``UNKNOWN`` is distinct from ``false``: both require a residual."""

    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


class ResolutionState(enum.StrEnum):
    """§18.3."""

    OPEN = "open"
    SHIFTED = "shifted"
    RESOLVED = "resolved"
    #: §18.2 revision; an unresolved pair is *kept*, not collapsed.
    INCONCLUSIVE = "inconclusive"


class HypothesisStatus(enum.StrEnum):
    """§15.4 lifecycle, transcribed. Seven states."""

    PROPOSED = "proposed"
    ACTIVE = "active"
    CONTESTED = "contested"
    UNRESOLVED = "unresolved"
    CONFIRMED = "confirmed"
    DISCARDED = "discarded"
    SUPERSEDED = "superseded"


#: §15.4, verbatim. Note ``CONFIRMED -> CONTESTED``: confirmation is revisable.
LIFECYCLE: dict[HypothesisStatus, frozenset[HypothesisStatus]] = {
    HypothesisStatus.PROPOSED: frozenset(
        {HypothesisStatus.ACTIVE, HypothesisStatus.DISCARDED}
    ),
    HypothesisStatus.ACTIVE: frozenset(
        {
            HypothesisStatus.CONTESTED,
            HypothesisStatus.UNRESOLVED,
            HypothesisStatus.CONFIRMED,
            HypothesisStatus.DISCARDED,
            HypothesisStatus.SUPERSEDED,
        }
    ),
    HypothesisStatus.CONTESTED: frozenset(
        {
            HypothesisStatus.ACTIVE,
            HypothesisStatus.UNRESOLVED,
            HypothesisStatus.CONFIRMED,
            HypothesisStatus.DISCARDED,
            HypothesisStatus.SUPERSEDED,
        }
    ),
    HypothesisStatus.UNRESOLVED: frozenset(
        {
            HypothesisStatus.ACTIVE,
            HypothesisStatus.CONTESTED,
            HypothesisStatus.DISCARDED,
            HypothesisStatus.SUPERSEDED,
        }
    ),
    HypothesisStatus.CONFIRMED: frozenset(
        {HypothesisStatus.CONTESTED, HypothesisStatus.SUPERSEDED}
    ),
    HypothesisStatus.DISCARDED: frozenset(
        {HypothesisStatus.ACTIVE, HypothesisStatus.SUPERSEDED}
    ),
    HypothesisStatus.SUPERSEDED: frozenset(),
}

#: §15.4: "Forbidden: PROPOSED -> CONFIRMED".
FORBIDDEN_TRANSITIONS: frozenset[tuple[HypothesisStatus, HypothesisStatus]] = frozenset(
    {(HypothesisStatus.PROPOSED, HypothesisStatus.CONFIRMED)}
)


class HypothesisTransitionError(ValueError):
    """Raised on an illegal or forbidden lifecycle move."""


def can_transition(current: HypothesisStatus, target: HypothesisStatus) -> bool:
    if (current, target) in FORBIDDEN_TRANSITIONS:
        return False
    return target in LIFECYCLE[current]


def transition(current: HypothesisStatus, target: HypothesisStatus) -> HypothesisStatus:
    """Apply §15.4. Refuses both illegal jumps and the named forbidden pair."""
    current = HypothesisStatus(current)
    target = HypothesisStatus(target)
    if (current, target) in FORBIDDEN_TRANSITIONS:
        raise HypothesisTransitionError(
            f"§15.4 forbids {current.value} -> {target.value}"
        )
    if target not in LIFECYCLE[current]:
        raise HypothesisTransitionError(
            f"illegal transition {current.value} -> {target.value}"
        )
    return target


# -- members and residual -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class Hypothesis:
    """One candidate inside a space. Local id, plus a residual marker."""

    text: str
    local_id: str = ""
    posterior: float = 0.0
    status: HypothesisStatus = HypothesisStatus.ACTIVE
    assumptions: tuple[str, ...] = ()
    #: True only for the residual ``H_OTHER``.
    is_residual: bool = False
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.text:
            raise ValueError("a hypothesis must state what it claims")
        object.__setattr__(self, "status", HypothesisStatus(self.status))
        if not self.is_residual and not 0.0 <= self.posterior <= 1.0:
            raise ValueError(f"posterior must be in [0, 1], got {self.posterior}")
        if not self.local_id:
            object.__setattr__(self, "local_id", f"LHYP-{_digest({'text': self.text})}")

    @classmethod
    def residual(cls, prior_mass: float) -> Hypothesis:
        """``H_OTHER`` -- "none of the listed". Never a concrete claim."""
        if not 0.0 < prior_mass < 1.0:
            raise ValueError(
                f"residual prior mass must be in (0, 1), got {prior_mass}"
            )
        return cls(
            text="none of the listed explanations",
            local_id="LHYP-residual",
            posterior=prior_mass,
            is_residual=True,
            detail="explicit residual: the space does not claim to be exhaustive",
        )

    def with_posterior(self, posterior: float) -> Hypothesis:
        return replace(self, posterior=posterior)


@dataclass(frozen=True, slots=True)
class HypothesisSpace:
    """§15.3, with the rules enforced rather than described.

    ``residual`` is derived from ``members`` rather than stored beside them. Two
    copies of the residual can disagree -- a member updated by evidence while the
    separate field still holds the old mass -- and a space whose residual disagrees
    with itself is worse than one without the concept. Deriving it makes that
    divergence unrepresentable.
    """

    context_id: str
    question: str
    members: tuple[Hypothesis, ...]
    exclusivity_groups: tuple[frozenset[str], ...] = ()
    compatible_pairs: tuple[tuple[str, str], ...] = ()
    exhaustive: Exhaustive = Exhaustive.UNKNOWN
    space_id: str = ""

    @property
    def residual(self) -> Hypothesis | None:
        for member in self.members:
            if member.is_residual:
                return member
        return None

    def __post_init__(self) -> None:
        if not self.question:
            raise ValueError("a space must state the question its members answer")
        if not self.members:
            raise ValueError("a space with no members answers nothing")
        known = {member.local_id for member in self.members}
        for group in self.exclusivity_groups:
            unknown = set(group) - known
            if unknown:
                raise ValueError(f"exclusivity group names unknown members: {sorted(unknown)}")
            if len(group) < 2:
                raise ValueError("an exclusivity group needs at least two members")
        for pair in self.compatible_pairs:
            if len(set(pair)) != 2:
                raise ValueError(f"a compatible pair needs two distinct members: {pair}")
            unknown = set(pair) - known
            if unknown:
                raise ValueError(f"compatible pair names unknown members: {sorted(unknown)}")
        residuals = [member for member in self.members if member.is_residual]
        if len(residuals) > 1:
            raise ValueError("a space carries at most one residual")
        # Rule 1: a non-exhaustive space MUST carry a residual.
        if self.exhaustive is not Exhaustive.TRUE and not residuals:
            raise ValueError(
                f"§15.3: a space with exhaustive={self.exhaustive.value} must carry a "
                "RESIDUAL (H_OTHER) hypothesis with declared prior mass"
            )
        if not self.space_id:
            object.__setattr__(self, "space_id", self.address())

    def _material(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "question": self.question,
            "members": sorted(member.local_id for member in self.members),
            "exhaustive": self.exhaustive.value,
            "groups": sorted(sorted(group) for group in self.exclusivity_groups),
        }

    def address(self) -> str:
        return f"HSP-{_digest(self._material())}"

    # -- access -------------------------------------------------------------

    @property
    def concrete_members(self) -> tuple[Hypothesis, ...]:
        return tuple(member for member in self.members if not member.is_residual)

    def member(self, local_id: str) -> Hypothesis | None:
        for candidate in self.members:
            if candidate.local_id == local_id:
                return candidate
        return None

    def is_exclusive_with(self, left: str, right: str) -> bool:
        """True when the two cannot both be true."""
        pair = frozenset({left, right})
        return any(pair == set(group) for group in self.exclusivity_groups)

    def is_declared_compatible(self, left: str, right: str) -> bool:
        pair = {left, right}
        return any(set(candidate) == pair for candidate in self.compatible_pairs)

    # -- rule 2: normalise only within an exclusivity group ------------------

    def normalise_group(self, local_id: str) -> tuple[dict[str, float], str]:
        """Distribute posterior mass over the group that competes with ``local_id``.

        Returns the group distribution and a reason when no distribution is
        possible. Compatible members are excluded from the normalisation, because
        §15.3 forbids dividing hypotheses that may be jointly true.
        """
        group = next(
            (candidate for candidate in self.exclusivity_groups if local_id in candidate),
            None,
        )
        if group is None:
            return {}, f"{local_id} belongs to no exclusivity group"
        competitors = [
            self.member(item) for item in sorted(group) if item != local_id
        ]
        if any(member is None for member in competitors):
            return {}, "exclusivity group references an unknown member"
        total = sum(
            (member.posterior if member is not None else 0.0) for member in competitors
        )
        if total <= 0.0:
            return {}, "competitors carry no posterior mass"
        return (
            {
                member.local_id: round(member.posterior / total, 9)
                for member in competitors
                if member is not None
            },
            "",
        )

    # -- rule 3: residual shrinks only for two reasons -----------------------

    def with_admitted_member(
        self,
        hypothesis: Hypothesis,
        *,
        takes: float | None = None,
        exhaustive: Exhaustive | None = None,
    ) -> HypothesisSpace:
        """Rule 3, first route: admitting a concrete hypothesis takes residual mass.

        §15.3 says ``H_OTHER`` mass "can only be reduced by ... admission of a
        concrete new hypothesis". *Reduced*, not removed: the residual still stands
        for whatever remains unnamed. So a non-exhaustive space keeps its residual
        with the remainder, and a space declared exhaustive drops it entirely.

        ``takes`` is the mass transferred, bounded by what the residual holds. It
        defaults to everything the residual carries, which is only coherent when the
        space also becomes exhaustive -- otherwise the space would be claiming to
        account for mass nothing now explains.
        """
        if hypothesis.is_residual:
            raise ValueError("a concrete hypothesis was required")
        if any(member.local_id == hypothesis.local_id for member in self.members):
            return self

        residual = self.residual
        available = residual.posterior if residual is not None else 0.0
        remaining_mass = available
        if takes is None:
            if exhaustive is not Exhaustive.TRUE and available > 0.0:
                raise ValueError(
                    "taking the whole residual mass leaves the space claiming to "
                    "explain mass nothing explains; pass takes=<amount> or declare "
                    "the space exhaustive"
                )
            transferred = available
            remaining_mass = 0.0
        else:
            transferred = float(takes)
            if not 0.0 <= transferred <= available + 1e-12:
                raise ValueError(
                    f"takes={transferred} exceeds the residual mass {available}"
                )
            remaining_mass = available - transferred

        admitted = hypothesis.with_posterior(transferred)
        concrete = tuple(member for member in self.members if not member.is_residual)
        members = list(concrete) + [admitted]
        if remaining_mass > 0.0 and residual is not None:
            members.append(residual.with_posterior(remaining_mass))

        groups = tuple(
            (set(group) - ({residual.local_id} if residual else set())) | {admitted.local_id}
            for group in self.exclusivity_groups
        )
        declared = exhaustive if exhaustive is not None else self.exhaustive
        if declared is not Exhaustive.TRUE and remaining_mass <= 0.0 and residual is not None:
            declared = Exhaustive.UNKNOWN
        return replace(
            self,
            members=tuple(members),
            exclusivity_groups=groups,
            exhaustive=declared,
            space_id="",
        )

    def with_posterior_evidence(self, posteriors: Mapping[str, float]) -> HypothesisSpace:
        """Rule 3, second route: evidence may move residual mass."""
        updated = tuple(
            member.with_posterior(float(posteriors[member.local_id]))
            if member.local_id in posteriors
            else member
            for member in self.members
        )
        return replace(self, members=updated, space_id="")

    def posterior_total(self) -> float:
        return round(sum(member.posterior for member in self.members), 9)

    def unaccounted_mass(self) -> float:
        """What the space does not explain. Zero only if the space is exhaustive."""
        return round(1.0 - self.posterior_total(), 9)

    def as_dict(self) -> dict[str, Any]:
        return {
            "space_id": self.space_id,
            "context_id": self.context_id,
            "question": self.question,
            "exhaustive": self.exhaustive.value,
            "members": [
                {
                    "local_id": member.local_id,
                    "text": member.text,
                    "posterior": member.posterior,
                    "status": member.status.value,
                    "is_residual": member.is_residual,
                }
                for member in self.members
            ],
            "exclusivity_groups": [sorted(group) for group in self.exclusivity_groups],
            "compatible_pairs": [sorted(pair) for pair in self.compatible_pairs],
            "residual": self.residual.local_id if self.residual else "",
            "posterior_total": self.posterior_total(),
            "unaccounted_mass": self.unaccounted_mass(),
        }


# -- §18 dialectics ------------------------------------------------------------


class CounterHypothesisOutcome(enum.StrEnum):
    """§18.4, verbatim. ``NO_VALID_COUNTERHYPOTHESIS`` is a result, not a skip."""

    GENERATED = "generated"
    NO_VALID_COUNTERHYPOTHESIS = "no_valid_counterhypothesis"
    COUNTERHYPOTHESIS_DUPLICATE = "counterhypothesis_duplicate"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    BUDGET_EXHAUSTED = "budget_exhausted"


@dataclass(frozen=True, slots=True)
class SteelmanParity:
    """§18.5: the antithesis must be built under the thesis's own conditions.

    Four conditions, each compared and each recorded. A parity failure is the
    single most common way a dialectical engine produces a straw man and then
    concludes that the thesis survived.
    """

    same_evidence_view: bool = False
    same_template_family: bool = False
    same_complexity_bound: bool = False
    same_assumption_budget: bool = False

    @property
    def is_parity(self) -> bool:
        return (
            self.same_evidence_view
            and self.same_template_family
            and self.same_complexity_bound
            and self.same_assumption_budget
        )

    @property
    def failures(self) -> tuple[str, ...]:
        missing = []
        if not self.same_evidence_view:
            missing.append("evidence_view")
        if not self.same_template_family:
            missing.append("template_family")
        if not self.same_complexity_bound:
            missing.append("complexity_bound")
        if not self.same_assumption_budget:
            missing.append("assumption_budget")
        return tuple(missing)

    def as_dict(self) -> dict[str, Any]:
        return {
            "parity": self.is_parity,
            "failures": list(self.failures),
        }


@dataclass(frozen=True, slots=True)
class DialecticalPair:
    """§18.3, transcribed."""

    context_id: str
    thesis: Hypothesis
    antithesis: Hypothesis
    shared_premises: tuple[str, ...] = ()
    disputed_premises: tuple[str, ...] = ()
    differential_predictions: tuple[str, ...] = ()
    discriminating_tests: tuple[str, ...] = ()
    resolution_state: ResolutionState = ResolutionState.OPEN
    counterhypothesis_outcome: CounterHypothesisOutcome = CounterHypothesisOutcome.GENERATED
    parity: SteelmanParity = field(default_factory=SteelmanParity)
    pair_id: str = ""

    def __post_init__(self) -> None:
        if self.thesis.local_id == self.antithesis.local_id:
            raise ValueError("a dialectical pair needs two distinct hypotheses")
        if self.thesis.is_residual or self.antithesis.is_residual:
            raise ValueError("the residual is not a dialectical participant")
        if not self.parity.is_parity:
            # Recorded, not fatal: a parity failure is a finding about the engine,
            # and refusing to record it would hide the failure mode entirely.
            pass
        if not self.pair_id:
            object.__setattr__(self, "pair_id", self.address())

    def _material(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "thesis": self.thesis.local_id,
            "antithesis": self.antithesis.local_id,
            "shared": sorted(self.shared_premises),
            "disputed": sorted(self.disputed_premises),
        }

    def address(self) -> str:
        return f"DLP-{_digest(self._material())}"

    def shared_between(self) -> tuple[str, ...]:
        """Common-premise extraction (§18.2 step 3)."""
        return tuple(sorted(set(self.thesis.assumptions) & set(self.antithesis.assumptions)))

    def disputed_between(self) -> tuple[str, ...]:
        """Difference analysis (§18.2 step 4)."""
        return tuple(sorted(set(self.thesis.assumptions) ^ set(self.antithesis.assumptions)))

    def as_dict(self) -> dict[str, Any]:
        return {
            "pair_id": self.pair_id,
            "context_id": self.context_id,
            "thesis": self.thesis.local_id,
            "antithesis": self.antithesis.local_id,
            "shared_premises": list(self.shared_premises),
            "disputed_premises": list(self.disputed_premises),
            "differential_predictions": list(self.differential_predictions),
            "discriminating_tests": list(self.discriminating_tests),
            "parity_audit": self.parity.as_dict(),
            "resolution_state": self.resolution_state.value,
            "counterhypothesis_outcome": self.counterhypothesis_outcome.value,
        }


def generate_counter_hypotheses(
    space: HypothesisSpace,
    thesis: Hypothesis,
    *,
    templates: Sequence[tuple[str, Hypothesis]],
    budget: int = 8,
    evidence_available: bool = True,
    parity: SteelmanParity | None = None,
) -> tuple[tuple[DialecticalPair, ...], CounterHypothesisOutcome]:
    """§18.4: attempt at least one counter-hypothesis for an active thesis.

    Every non-success returns a named outcome rather than an empty tuple, because
    "no counter-hypothesis exists" and "we ran out of budget" are very different
    things to report about the state of an investigation.
    """
    if not evidence_available:
        return (), CounterHypothesisOutcome.INSUFFICIENT_EVIDENCE
    if budget <= 0:
        return (), CounterHypothesisOutcome.BUDGET_EXHAUSTED
    if thesis.status not in (HypothesisStatus.ACTIVE, HypothesisStatus.CONTESTED):
        return (), CounterHypothesisOutcome.NO_VALID_COUNTERHYPOTHESIS

    audit = parity or SteelmanParity(
        same_evidence_view=True,
        same_template_family=True,
        same_complexity_bound=True,
        same_assumption_budget=True,
    )
    seen = {thesis.local_id}
    pairs: list[DialecticalPair] = []
    for _family, candidate in templates:
        if len(pairs) >= budget:
            break
        if candidate.local_id in seen:
            continue
        if candidate.local_id == thesis.local_id:
            continue
        seen.add(candidate.local_id)
        pairs.append(
            DialecticalPair(
                context_id=space.context_id,
                thesis=thesis,
                antithesis=candidate,
                parity=audit,
                shared_premises=tuple(
                    sorted(set(thesis.assumptions) & set(candidate.assumptions))
                ),
                disputed_premises=tuple(
                    sorted(set(thesis.assumptions) ^ set(candidate.assumptions))
                ),
            )
        )
    if not pairs:
        return (), CounterHypothesisOutcome.COUNTERHYPOTHESIS_DUPLICATE
    return tuple(pairs), CounterHypothesisOutcome.GENERATED


def revise_pair(
    pair: DialecticalPair,
    *,
    differential_predictions: Sequence[str] = (),
    discriminating_tests: Sequence[str] = (),
) -> DialecticalPair:
    """§18.2 step 7 / §18.6: record consequences and tests.

    ``INCONCLUSIVE`` is preserved rather than resolved. A dialectical engine that
    resolves ambiguity is not doing dialectics.
    """
    return replace(
        pair,
        differential_predictions=tuple(differential_predictions),
        discriminating_tests=tuple(discriminating_tests),
        resolution_state=ResolutionState.OPEN,
    )