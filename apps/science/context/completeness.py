"""Query intent, completeness modes, and the honesty layer over a result set.

§33.1: "The platform MUST NOT claim literal global completeness unless the source
universe and coverage model make that defensible." §33.2 gives exactly three modes
and says the UI must display which one applies. Appendix P turns that into a
protocol: every query whose wording implies universality -- ``all``, ``every``,
``global``, ``none`` -- must be checked, and if the conditions for a universal claim
are not met the engine phrases the result internally as *"observed candidates under
declared coverage"*.

This module is that phrase, made executable. The load-bearing rule is
``downgrade``: a caller cannot request ``EXACT_ENUMERATION`` and get it. The mode is
*derived* from the conditions, and a request the evidence cannot support comes back
downgraded with the unmet conditions named. That inverts the failure mode -- without
it, the default action on an unreasonable request is to honour it.

The second rule concerns the universal negative. "None exist" is only expressible
as a ``CoverageQualifiedAbsence`` meeting the profile's coverage and
detection-power thresholds (Appendix P.2); otherwise it is "none observed under
declared coverage". §13A already enforces the thresholds, and here the phrasing is
tied to them so the two cannot drift apart.

:func:`degrade_universal` (FR-014) is the third layer. It takes a
:class:`ResultSet`, reads all six declared preconditions, and returns a
:class:`DegradedUniversalAnswer` whose phrasing is fixed and whose limitations are
enumerated. A caller cannot supply that phrasing, which is the point: the failure this
prevents is not a missing feature, it is a caller who wanted a universal answer and
wrote one.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from context.coverage import (
    AbsenceAdmissibility,
    CoverageQualifiedAbsence,
)
from context.locality import _digest

# -- §33.2 completeness modes --------------------------------------------------


class CompletenessMode(enum.StrEnum):
    """§33.2, transcribed."""

    #: Universe explicitly enumerable and completely scanned.
    EXACT_ENUMERATION = "exact_enumeration"
    #: All registered sources in the current catalogue exhausted under declared rules.
    KNOWN_UNIVERSE_ENUMERATION = "known_universe_enumeration"
    #: Available sources searched; universe completeness cannot be established.
    OPEN_WORLD_DISCOVERY = "open_world_discovery"


class RequestedMode(enum.StrEnum):
    """What the caller asked for. A request, not an outcome."""

    UNIVERSAL = "universal"
    BEST_EFFORT = "best_effort"


#: Words that imply universality. Appendix P names ``all``, ``every``, ``global``
#: and ``none``; the Russian equivalents are listed alongside them.
#:
#: Deliberately over-inclusive. A false positive costs a stricter completeness mode
#: and a downgrade reason, while a false negative would let a universal claim
#: through unchecked -- the asymmetry makes extra markers the safe direction.
UNIVERSAL_MARKERS: frozenset[str] = frozenset(
    {
        "all",
        "every",
        "global",
        "none",
        "все",
        "всё",
        "всех",
        "всеми",
        "каждый",
        "каждая",
        "любой",
        "ничто",
        "ничего",
        "нет",
    }
)


def implies_universal(text: str) -> bool:
    """Whether the wording semantically claims universality (Appendix P).

    Matched on word boundaries, not substrings. Substring matching is wrong in a way
    that looks harmless: "wallets" contains "all", "small" contains "all", and
    "networks" contains "net". Each false positive silently downgraded an ordinary
    query, which trains a reader to ignore the banner.
    """
    lowered = text.lower()
    tokens = set(re.findall(r"[^\W\d_]+", lowered, flags=re.UNICODE))
    return bool(tokens & UNIVERSAL_MARKERS)


# -- §32.1 query intent -------------------------------------------------------


class Objective(enum.StrEnum):
    IDENTIFY_COHORT = "identify_cohort"
    IDENTIFY_ENTITY = "identify_entity"
    TEST_HYPOTHESIS = "test_hypothesis"
    LOCATE_EVENT = "locate_event"
    ESTIMATE_QUANTITY = "estimate_quantity"
    UNIVERSAL_NEGATIVE = "universal_negative"


class TemporalMode(enum.StrEnum):
    CURRENT = "current"
    AS_OF = "as_of"
    INTERVAL = "interval"


@dataclass(frozen=True, slots=True)
class Target:
    subject_class: str
    property: str = ""
    value: float | None = None
    unit: str = ""

    def __post_init__(self) -> None:
        if not self.subject_class:
            raise ValueError("a target must name what is being looked for")

    def as_dict(self) -> dict[str, Any]:
        return {
            "subject_class": self.subject_class,
            "property": self.property,
            "value": self.value,
            "unit": self.unit,
        }


@dataclass(frozen=True, slots=True)
class QueryIntent:
    """§32.1. The machine-readable form of "find all whales over $1M"."""

    objective: Objective
    target: Target
    question: str = ""
    temporal_scope: TemporalMode = TemporalMode.CURRENT
    identity_requirement: str = "CONTROL_CLUSTER"
    allow_unresolved: bool = True
    evidence_requirements: Mapping[str, int] = field(default_factory=dict)
    saturation_enabled: bool = True
    requested_mode: RequestedMode = RequestedMode.UNIVERSAL
    intent_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "objective", Objective(self.objective))
        object.__setattr__(self, "temporal_scope", TemporalMode(self.temporal_scope))
        if self.objective is Objective.UNIVERSAL_NEGATIVE and self.allow_unresolved:
            raise ValueError(
                "a universal negative cannot allow unresolved members: 'none exist' "
                "and 'some unresolved' contradict each other"
            )
        if not self.intent_id:
            object.__setattr__(self, "intent_id", self.address())

    def _material(self) -> dict[str, Any]:
        return {
            "objective": self.objective.value,
            "target": self.target.as_dict(),
            "temporal_scope": self.temporal_scope.value,
            "identity_requirement": self.identity_requirement,
            "allow_unresolved": self.allow_unresolved,
        }

    def address(self) -> str:
        return f"QIN-{_digest(self._material())}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "objective": self.objective.value,
            "target": self.target.as_dict(),
            "question": self.question,
            "temporal_scope": self.temporal_scope.value,
            "identity_requirement": self.identity_requirement,
            "allow_unresolved": self.allow_unresolved,
            "evidence_requirement": dict(self.evidence_requirements),
            "saturation": {"enabled": self.saturation_enabled},
            "requested_mode": self.requested_mode.value,
        }


def compile_intent(question: str) -> QueryIntent:
    """Appendix P: check universality in the wording before promising anything.

    This is a declaration, not a parser. Recognising that a question claims
    universality is what Appendix P requires at this stage; extracting its
    constraints is the query compiler's own work and belongs to a language model
    that does not exist yet. Inventing a half-parser here would produce confident
    wrong intents, which is worse than an explicit "declare it yourself".
    """
    universal = implies_universal(question)
    return QueryIntent(
        objective=Objective.IDENTIFY_COHORT,
        target=Target(subject_class="UNRESOLVED"),
        question=question,
        allow_unresolved=not universal,
        requested_mode=(
            RequestedMode.UNIVERSAL if universal else RequestedMode.BEST_EFFORT
        ),
    )


# -- Appendix P.1 completeness requirement -----------------------------------


class UniverseDefinition(enum.StrEnum):
    EXPLICITLY_ENUMERABLE = "explicitly_enumerable"
    REGISTERED_SOURCES = "registered_sources"
    AVAILABLE_SOURCES = "available_sources"


@dataclass(frozen=True, slots=True)
class CompletenessCondition:
    """One Appendix P.1 condition, with whether it holds."""

    name: str
    satisfied: bool
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"condition": self.name, "satisfied": self.satisfied, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class CompletenessRequirement:
    """Appendix P.1: what was asked, what is achievable, and what is missing."""

    requested_mode: RequestedMode
    universe_definition: UniverseDefinition
    conditions: tuple[CompletenessCondition, ...] = ()
    feasible_mode: CompletenessMode = CompletenessMode.OPEN_WORLD_DISCOVERY
    downgrade_reason: str = ""

    @property
    def unmet(self) -> tuple[str, ...]:
        return tuple(
            condition.name for condition in self.conditions if not condition.satisfied
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "requested_mode": self.requested_mode.value,
            "feasible_mode": self.feasible_mode.value,
            "universe_definition": self.universe_definition.value,
            "unmet_conditions": list(self.unmet),
            "downgrade_reason": self.downgrade_reason,
            "conditions": [condition.as_dict() for condition in self.conditions],
        }


_CONDITIONS: tuple[tuple[str, str], ...] = (
    ("source_catalogue_exhausted", "every registered source was queried to the end"),
    ("temporal_scope_defined", "the window over which the claim holds is stated"),
    ("identity_resolution_complete", "every candidate resolved to one identity"),
    ("pagination_complete", "no source was truncated by a page limit"),
    ("source_errors_zero_or_accounted", "every source error is counted, not ignored"),
)


def assess_completeness(
    *,
    universe: UniverseDefinition,
    catalogue_exhausted: bool = False,
    temporal_scope_defined: bool = False,
    identity_resolution_complete: bool = False,
    pagination_complete: bool = False,
    source_errors_zero_or_accounted: bool = False,
    requested_mode: RequestedMode = RequestedMode.UNIVERSAL,
) -> CompletenessRequirement:
    """Derive the achievable mode. The caller cannot assert it.

    The mode is a function of the conditions and the universe definition:

    * an explicitly enumerable universe, fully scanned -> ``EXACT_ENUMERATION``
    * registered sources all exhausted under declared rules -> ``KNOWN_UNIVERSE_ENUMERATION``
    * anything else -> ``OPEN_WORLD_DISCOVERY``

    Requesting a mode stronger than the conditions support yields a downgrade whose
    reason names the missing conditions.
    """
    satisfied = {
        "source_catalogue_exhausted": catalogue_exhausted,
        "temporal_scope_defined": temporal_scope_defined,
        "identity_resolution_complete": identity_resolution_complete,
        "pagination_complete": pagination_complete,
        "source_errors_zero_or_accounted": source_errors_zero_or_accounted,
    }
    conditions = tuple(
        CompletenessCondition(name, satisfied[name], detail)
        for name, detail in _CONDITIONS
    )

    # A universal-negative or "find all" claim also needs identity and pagination;
    # an exact enumeration additionally needs an enumerable universe.
    required = {
        "source_catalogue_exhausted",
        "pagination_complete",
        "source_errors_zero_or_accounted",
    }
    if requested_mode is RequestedMode.UNIVERSAL:
        required |= {"temporal_scope_defined", "identity_resolution_complete"}
    unmet = tuple(name for name in required if not satisfied[name])

    if not unmet and universe is UniverseDefinition.EXPLICITLY_ENUMERABLE:
        feasible = CompletenessMode.EXACT_ENUMERATION
    elif not unmet and universe is UniverseDefinition.REGISTERED_SOURCES:
        feasible = CompletenessMode.KNOWN_UNIVERSE_ENUMERATION
    else:
        feasible = CompletenessMode.OPEN_WORLD_DISCOVERY

    reason = ""
    if requested_mode is RequestedMode.UNIVERSAL and feasible is not (
        CompletenessMode.EXACT_ENUMERATION
    ):
        reason = (
            f"universal claim downgraded to {feasible.value}; unmet: "
            f"{', '.join(unmet) if unmet else 'universe is not explicitly enumerable'}"
        )

    return CompletenessRequirement(
        requested_mode=requested_mode,
        universe_definition=universe,
        conditions=conditions,
        feasible_mode=feasible,
        downgrade_reason=reason,
    )


# -- §33.1 the returned result set --------------------------------------------


@dataclass(frozen=True, slots=True)
class ResultSet:
    """§33.1, all ten fields. Nothing is derived or omitted."""

    observed_set: tuple[str, ...] = ()
    candidate_set: tuple[str, ...] = ()
    resolved_set: tuple[str, ...] = ()
    unresolved_set: tuple[str, ...] = ()
    excluded_set: tuple[str, ...] = ()
    coverage_estimate: float | None = None
    source_universe: str = ""
    saturation_state: str = ""
    known_blind_spots: tuple[str, ...] = ()
    qualified_absences: tuple[CoverageQualifiedAbsence, ...] = ()
    completeness: CompletenessRequirement | None = None

    def __post_init__(self) -> None:
        if self.coverage_estimate is not None and not 0.0 <= self.coverage_estimate <= 1.0:
            raise ValueError(
                f"coverage_estimate must be in [0, 1], got {self.coverage_estimate}"
            )
        if not self.source_universe:
            raise ValueError("§33.1: a result must name the universe it ranges over")
        overlap = set(self.resolved_set) & set(self.unresolved_set)
        if overlap:
            raise ValueError(
                f"an item cannot be both resolved and unresolved: {sorted(overlap)}"
            )
        if not set(self.resolved_set) | set(self.unresolved_set) <= set(
            self.candidate_set
        ):
            raise ValueError(
                "every resolved or unresolved item must appear in the candidate set"
            )

    # -- the honesty rules ---------------------------------------------------

    def may_claim_universal_negative(self) -> bool:
        """Appendix P.2: only if a CQA meets the thresholds.

        "None exist" is expressible only when at least one qualified absence is
        admissible as negative evidence. Otherwise the answer is "none observed
        under declared coverage", which is a different and much weaker claim.
        """
        return any(
            absence.admissibility is AbsenceAdmissibility.NEGATIVE_EVIDENCE
            for absence in self.qualified_absences
        )

    def phrasing(self) -> str:
        """The sentence the result supports. Appendix P.2."""
        found = len(self.resolved_set)
        blind = len(self.known_blind_spots)
        mode = (
            self.completeness.feasible_mode.value
            if self.completeness is not None
            else CompletenessMode.OPEN_WORLD_DISCOVERY.value
        )
        if not found and not self.qualified_absences:
            return "nothing searched yet"
        if not found and self.may_claim_universal_negative():
            # Only reachable when an absence met the §13A thresholds, so "none
            # exist" is supported rather than merely unrefuted.
            return (
                f"no {self.source_universe} candidate satisfies the constraint "
                f"under declared coverage ({mode})"
            )
        if not found:
            return "none observed under declared coverage"
        base = f"{found} resolved, {len(self.unresolved_set)} unresolved"
        return f"{base} under declared coverage ({mode}, {blind} blind spots)"

    def banner(self) -> dict[str, Any]:
        """§33.2: the UI must display which mode applies."""
        return {
            "completeness_mode": (
                self.completeness.feasible_mode.value
                if self.completeness is not None
                else CompletenessMode.OPEN_WORLD_DISCOVERY.value
            ),
            "downgrade_reason": (
                self.completeness.downgrade_reason if self.completeness else ""
            ),
            "unmet_conditions": (
                list(self.completeness.unmet) if self.completeness else []
            ),
            "phrasing": self.phrasing(),
            "may_claim_universal_negative": self.may_claim_universal_negative(),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "observed_set": list(self.observed_set),
            "candidate_set": list(self.candidate_set),
            "resolved_set": list(self.resolved_set),
            "unresolved_set": list(self.unresolved_set),
            "excluded_set": list(self.excluded_set),
            "coverage_estimate": self.coverage_estimate,
            "source_universe": self.source_universe,
            "saturation_state": self.saturation_state,
            "known_blind_spots": list(self.known_blind_spots),
            "qualified_absences": [
                absence.as_dict() for absence in self.qualified_absences
            ],
            "completeness": (
                self.completeness.as_dict() if self.completeness else {}
            ),
            "banner": self.banner(),
        }


# -- FR-014: what a universal question actually gets answered with -------------


class LimitationKind(enum.StrEnum):
    """FR-014's enumerated limitations. Each is a *fact about the run*, not a caveat.

    Named rather than left as free text because a limitation a reader cannot act on is
    a disclaimer, and FR-014 asks for an enumeration precisely so the reader can see
    which preconditions failed and go and satisfy one.
    """

    #: FR-014's six inputs, in its own order.
    UNIVERSE_NOT_DECLARED = "universe_not_declared"
    COVERAGE_NOT_DECLARED = "coverage_not_declared"
    FRESHNESS_NOT_DECLARED = "freshness_not_declared"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    BUDGET_TRUNCATED = "budget_truncated"
    DETECTION_POWER_UNDECLARED = "detection_power_undeclared"
    #: Everything above was satisfied, so the enumeration is empty and the answer may
    #: be phrased as a universal claim.
    NONE = "none"


#: The universal phrasing FR-014 mandates when the preconditions do not hold.
#: Quoted rather than composed, because the whole point is that it is a fixed sentence
#: a reader can recognise, not one this module paraphrases differently per call site.
OBSERVED_WITHIN_STATED_COVERAGE = "candidates observed within the stated coverage"


@dataclass(frozen=True, slots=True)
class DegradedUniversalAnswer:
    """What a universal query is answered with when the world will not support it.

    Degradation is computed, never requested. :func:`degrade_universal` is the only
    constructor, it reads the declared preconditions, and a caller cannot pass its own
    phrasing -- a caller that could would reinstate exactly the failure this type
    exists to make impossible, which is a confident universal answer produced by
    someone who wanted one.

    The three fields travel together and none of them is optional:

    * ``candidates`` -- what was actually observed. Never empty by construction when
      the answer is a degradation; a degradation that observed nothing is
      :class:`SearchDisposition.FAILED`'s job, not this type's.
    * ``coverage`` -- the boundary the candidates were observed within, as text.
    * ``limitations`` -- every unmet precondition, enumerated and named.

    A bare ``[]`` is not an answer this type can express, and neither is "none exist":
    that phrasing requires :attr:`may_claim_universal_negative`, which requires a
    declared universe *and* declared detection power.
    """

    candidates: tuple[str, ...]
    coverage: str
    limitations: tuple[LimitationKind, ...]
    completeness_mode: CompletenessMode
    requested_mode: RequestedMode = RequestedMode.UNIVERSAL

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidates", tuple(str(item) for item in self.candidates))
        if not self.coverage.strip():
            raise ValueError(
                "a degraded answer must state the coverage its candidates were observed "
                f"within; '{OBSERVED_WITHIN_STATED_COVERAGE}' without a boundary is the "
                "sentence that says nothing (FR-014)"
            )
        object.__setattr__(
            self,
            "limitations",
            tuple(sorted({LimitationKind(item) for item in self.limitations}, key=str)),
        )
        if not self.limitations:
            raise ValueError(
                "a DegradedUniversalAnswer must enumerate at least one limitation; if the "
                "preconditions all hold the caller has a universal claim and not a degraded "
                "one, and mislabelling it as degraded hides a real limitation"
            )
        if LimitationKind.NONE in self.limitations:
            raise ValueError(
                "LimitationKind.NONE is the empty enumeration's marker and cannot appear "
                "inside a non-empty one"
            )
        object.__setattr__(
            self, "completeness_mode", CompletenessMode(self.completeness_mode)
        )
        object.__setattr__(self, "requested_mode", RequestedMode(self.requested_mode))

    @property
    def may_claim_universal_negative(self) -> bool:
        """Whether "none exist" is available. Only with a declared universe *and* power.

        Coverage and detection power being absent from the limitation list is the test,
        because that is precisely the two that FR-014 and contract 03 R4 make
        prerequisites of an absence claim. Everything else on the list -- an undeclared
        freshness, a missing capability -- makes the answer weaker without making the
        negative reading unavailable.
        """
        blocking = {LimitationKind.UNIVERSE_NOT_DECLARED, LimitationKind.DETECTION_POWER_UNDECLARED}
        return not (blocking & set(self.limitations))

    @property
    def phrasing(self) -> str:
        """The sentence. Never a flat "there are none"."""
        found = len(self.candidates)
        detail = (
            f"{found} candidate{'s' if found != 1 else ''} observed within "
            f"{self.coverage} ({self.completeness_mode.value})"
        )
        if self.may_claim_universal_negative:
            return (
                f"no candidate satisfies the query within {self.coverage}; "
                f"{detail}. Limitations: "
                + ", ".join(item.value for item in self.limitations)
            )
        return (
            f"{OBSERVED_WITHIN_STATED_COVERAGE}: {detail}. Not a universal answer. "
            "Limitations: "
            + ", ".join(item.value for item in self.limitations)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "answer_kind": "degraded_universal",
            "phrasing": self.phrasing,
            "candidates": list(self.candidates),
            "coverage": self.coverage,
            "requested_mode": self.requested_mode.value,
            "completeness_mode": self.completeness_mode.value,
            "limitations": [item.value for item in self.limitations],
            "may_claim_universal_negative": self.may_claim_universal_negative,
        }


def degrade_universal(
    result_set: ResultSet,
    *,
    requested_mode: RequestedMode = RequestedMode.UNIVERSAL,
    universe_declared: bool = True,
    coverage_declared: bool | None = None,
    freshness_declared: bool = True,
    capabilities_available: bool = True,
    budget_truncated: bool = False,
    detection_power_declared: bool | None = None,
) -> DegradedUniversalAnswer:
    """Answer a universal query as honestly as the declared preconditions allow (FR-014).

    Every FR-014 input is read here and each one that fails becomes a named
    limitation. The two inputs FR-014 does *not* list but contract 03 R4 does -- the
    declared universe and the declared detection power -- default to ``True`` only
    because :attr:`ResultSet.source_universe` is non-empty by construction and
    :attr:`ResultSet.may_claim_universal_negative` has already computed the power half;
    a caller wanting the stricter reading passes them explicitly.

    The interesting case is ``detection_power_declared=None``: it means "ask the
    absences", and a result set with no admissible absence answers ``False``. That is
    the route by which "we looked and found nothing" is prevented from becoming "it
    does not exist" -- the question is asked of the *evidence*, and the evidence
    decides.
    """
    if coverage_declared is None:
        coverage_declared = result_set.coverage_estimate is not None
    if detection_power_declared is None:
        detection_power_declared = result_set.may_claim_universal_negative()

    limitation_flags = {
        LimitationKind.UNIVERSE_NOT_DECLARED: not universe_declared,
        LimitationKind.COVERAGE_NOT_DECLARED: not coverage_declared,
        LimitationKind.FRESHNESS_NOT_DECLARED: not freshness_declared,
        LimitationKind.CAPABILITY_UNAVAILABLE: not capabilities_available,
        LimitationKind.BUDGET_TRUNCATED: budget_truncated,
        LimitationKind.DETECTION_POWER_UNDECLARED: not detection_power_declared,
    }
    limitations = tuple(kind for kind, unmet in limitation_flags.items() if unmet)

    if requested_mode is RequestedMode.BEST_EFFORT and not limitations:
        # Nothing is unmet because nothing was asked for. Say so rather than inventing
        # a limitation, and rather than phrasing a best-effort answer as a universal one.
        raise ValueError(
            "a best-effort request with every precondition met is not a degraded universal "
            "answer; returning the ResultSet directly says more than manufacturing a "
            "limitation to fit this type (FR-014)"
        )

    mode = (
        result_set.completeness.feasible_mode
        if result_set.completeness is not None
        else CompletenessMode.OPEN_WORLD_DISCOVERY
    )
    observed = tuple(result_set.resolved_set) or tuple(result_set.candidate_set)
    if not limitations:
        # Every precondition holds, so the universal answer is available and there is
        # nothing to degrade to. Refusing here keeps a qualified absence from being
        # phrased as a degraded one, which would understate it.
        raise ValueError(
            "every FR-014 precondition is met: the universal claim is supported and does "
            "not need degrading. Refusing is deliberate -- a supported answer phrased as a "
            "degraded one understates what was actually established"
        )
    return DegradedUniversalAnswer(
        candidates=observed,
        coverage=result_set.source_universe,
        limitations=limitations,
        completeness_mode=mode,
        requested_mode=requested_mode,
    )