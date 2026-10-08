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