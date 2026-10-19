"""Research obligations, actions, saturation, and the frontier (Feature 024 Phase 4/5).

The vocabulary the Context Engine reasons over. Every object here is a frozen
dataclass with a deterministic address, following the platform's 016+ convention --
reused, not reinvented (see ``domain.investigation_context`` for the template).

The central distinction, and the reason this is not the frontier module that already
exists: ``ResearchObligation`` is **what must be learned**, while
``acquisition_tasks``/``frontier_items`` are **what has been queued**. Closing an
obligation requires saturation and coverage, never a task count (FR-053) -- a task
count measures effort, not sufficiency.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

from contracts.stage_outcome import CoverageStatement, ErrorClass
from domain.investigation_context import ContextEngineError, InvestigationState, ObligationStatus
from domain.relation_identity import canonical_material, digest128

OBLIGATION_ID_PREFIX = "OBL-"
ACTION_ID_PREFIX = "ACT-"
SATURATION_PREFIX = "SAT-"
MEMORY_PREFIX = "AM-"


class KnowledgeType(enum.StrEnum):
    """What kind of answer would settle an obligation (input.md §13.2)."""

    ENTITY = "entity"
    RELATION = "relation"
    EVENT = "event"
    ATTRIBUTE = "attribute"
    ABSENCE = "absence"
    CONTRADICTION = "contradiction"
    BOUNDARY = "boundary"


class Disposition(enum.StrEnum):
    """FR-035. A terminal disposition always carries a reason."""

    SATISFIED = "satisfied"
    ABANDONED = "abandoned"
    BLOCKED = "blocked"
    SUPERSEDED = "superseded"


class SatisfactionRule(enum.StrEnum):
    """FR-041. *How* this obligation may be discharged, declared at creation.

    There is no ``SATISFIED_BY_DEFAULT``. The rule is stated when the obligation is
    minted and the evaluator reads it; an obligation with no declared rule is refused,
    because "it closed and nobody wrote down what closed it" is the failure this spec
    exists to prevent, and a default rule would be that default.
    """

    #: Every declared :class:`AcceptanceCriterion` must be met.
    DECLARED_CRITERIA = "declared_criteria"
    #: A ``qualified_absence`` coverage statement discharges it. Still requires the
    #: declared universe and detection power -- an informational-only ``no_result`` does
    #: not (contract 03, FR-014).
    COVERAGE_STATEMENT = "coverage_statement"


class CriterionBasis(enum.StrEnum):
    """What discharges one acceptance criterion. Declared, never inferred."""

    SATURATION = "saturation"
    EVIDENCE_REF = "evidence_ref"
    COVERAGE_STATEMENT = "coverage_statement"


@dataclass(frozen=True, slots=True)
class AcceptanceCriterion:
    """One declared condition for discharge (FR-041).

    A criterion with an empty ``criterion_id`` is not a criterion -- it is a wish. The
    id is what the verdict cites when it says why the obligation closed or did not, so an
    unnamed condition could never be audited against the evidence that was supposed to
    meet it.
    """

    criterion_id: str
    statement: str
    basis: CriterionBasis = CriterionBasis.SATURATION
    required_capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.criterion_id).strip():
            raise ContextEngineError(
                "criterion_id_missing",
                "an acceptance criterion must be nameable; a verdict cites it as the reason "
                "an obligation closed, so an unnamed one cannot be audited",
            )
        if not str(self.statement).strip():
            raise ContextEngineError(
                "criterion_statement_missing",
                f"criterion {self.criterion_id!r} must say what it requires",
            )
        object.__setattr__(self, "basis", CriterionBasis(self.basis))
        object.__setattr__(self, "required_capabilities", tuple(self.required_capabilities))

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "statement": self.statement,
            "basis": self.basis.value,
            "required_capabilities": list(self.required_capabilities),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AcceptanceCriterion:
        return cls(
            criterion_id=str(payload["criterion_id"]),
            statement=str(payload["statement"]),
            basis=CriterionBasis(payload.get("basis", "saturation")),
            required_capabilities=tuple(payload.get("required_capabilities", ())),
        )


#: The components a caller may estimate, in reporting order (FR-042).
PRIORITY_COMPONENT_NAMES: tuple[str, ...] = (
    "expected_information_gain",
    "hypothesis_discrimination",
    "relevance",
    "source_quality",
    "independence_gain",
    "novelty",
    "temporal_freshness",
    "success_probability",
    "estimated_cost",
    "latency_ms",
    "repeat_penalty",
    "source_failure_rate",
    "resource_risk",
    "policy_penalty",
)

#: Weight of each *descriptive* component in the derived priority score. The cost family
#: (estimated_cost, repeat_penalty, resource_risk, policy_penalty) is excluded on
#: purpose: averaging "cheap" in with "informative" yields a number that ranks a cheap
#: useless action above an expensive decisive one, which is a value judgement wearing a
#: measurement's clothes. Those four are reported and left to the caller.
_PRIORITY_WEIGHTS: dict[str, float] = {
    "expected_information_gain": 0.30,
    "hypothesis_discrimination": 0.15,
    "relevance": 0.15,
    "source_quality": 0.10,
    "independence_gain": 0.10,
    "novelty": 0.10,
    "temporal_freshness": 0.05,
    "success_probability": 0.05,
}
_COST_COMPONENTS: frozenset[str] = frozenset(
    {"estimated_cost", "repeat_penalty", "resource_risk", "policy_penalty"}
)


@dataclass(frozen=True, slots=True)
class PriorityComponents:
    """FR-042. The inspectable component vector behind an obligation's priority.

    **Every component defaults to ``None`` and ``None`` means "not estimated".** It is
    never ``0.0``: ``0.0`` is a measurement that the expected information gain is zero,
    and reading "nobody measured it" as "it is zero" ranks a genuinely useless action
    last for the same reason a promising one was never ranked at all. Both errors are
    invisible in the output, which is why the distinction is held in the type rather than
    in a convention.

    :meth:`score` follows the same rule -- it returns ``None`` when nothing was
    estimated, so a caller cannot rank on a fabricated zero.
    """

    expected_information_gain: float | None = None
    hypothesis_discrimination: float | None = None
    relevance: float | None = None
    source_quality: float | None = None
    independence_gain: float | None = None
    novelty: float | None = None
    temporal_freshness: float | None = None
    success_probability: float | None = None
    estimated_cost: float | None = None
    latency_ms: float | None = None
    repeat_penalty: float | None = None
    source_failure_rate: float | None = None
    resource_risk: float | None = None
    policy_penalty: float | None = None

    _NAMES: ClassVar[tuple[str, ...]] = PRIORITY_COMPONENT_NAMES

    def estimated(self) -> dict[str, float]:
        """Only the components that carry an estimate. Absent keys stay absent."""
        return {
            name: value
            for name, value in ((n, getattr(self, n)) for n in self._NAMES)
            if value is not None
        }

    @property
    def basis(self) -> str:
        """``measured`` / ``partial`` / ``unestimated`` -- visible on the obligation."""
        count = len(self.estimated())
        if count == 0:
            return "unestimated"
        return "measured" if count == len(self._NAMES) else "partial"

    def score(self) -> float | None:
        """Weighted mean over the estimated descriptive components, else ``None``.

        Unestimated components are dropped from both numerator and denominator rather
        than contributing a zero, so a caller that measured two components is not
        penalised for the twelve it did not.
        """
        present = self.estimated()
        weighted = sum(
            weight * present[name]
            for name, weight in _PRIORITY_WEIGHTS.items()
            if name in present
        )
        weight_total = sum(w for name, w in _PRIORITY_WEIGHTS.items() if name in present)
        if weight_total == 0.0:
            # Nothing descriptive was estimated. Returning 0.0 here would be the exact
            # conflation this type exists to prevent: a fabricated "this action is worth
            # nothing" instead of an admitted "nobody measured it".
            return None
        return min(1.0, max(0.0, weighted / weight_total))

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self._NAMES}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PriorityComponents:
        return cls(**{name: payload.get(name) for name in cls._NAMES})


@dataclass(frozen=True, slots=True)
class ObligationTrigger:
    """FR-038: the immutable trigger block, stored on the obligation itself.

    Kept on the obligation rather than only in the decision log because the question
    "why does this obligation exist" has to be answerable from the obligation. A trigger
    that lives solely in the recorder is one query away from an obligation nobody can
    justify.

    ``event_id`` is empty for ``operator_intent`` -- the operator asked, and there is no
    prior event to point at. That is a declared fact about the trigger's kind, not a
    missing field.
    """

    kind: str
    rule_id: str
    rule_version: str
    reason: str
    event_id: str = ""
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("kind", "rule_id", "rule_version", "reason"):
            if not str(getattr(self, name)).strip():
                raise ContextEngineError(
                    "trigger_block_incomplete",
                    f"an obligation trigger must record its {name}; a trigger missing the "
                    "reason it fired cannot be audited against the rule that fired it "
                    "(FR-038)",
                )
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "event_id": self.event_id,
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "reason": self.reason,
            "evidence_refs": list(self.evidence_refs),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ObligationTrigger:
        return cls(
            kind=str(payload["kind"]),
            rule_id=str(payload["rule_id"]),
            rule_version=str(payload["rule_version"]),
            reason=str(payload["reason"]),
            event_id=str(payload.get("event_id", "")),
            evidence_refs=tuple(payload.get("evidence_refs", ())),
        )


class MemoryState(enum.StrEnum):
    """FR-045 / contract 03. What an attempt left behind.

    Four states, and the two that matter most are deliberately not mergeable:

    * :attr:`FAILED` -- *we could not look*. The capability was unavailable, the source
      was down, the query could not be expressed. This is a statement about the system.
    * :attr:`NO_RESULT` -- *we looked and the universe did not contain it*. Admissible
      evidence, provided it carries the coverage statement that says which universe and
      with what detection power.

    Collapsing the first into the second is how "the scraper 500'd" becomes "nothing was
    found", which is the single most expensive confusion in an investigation: it retires
    a question that was never asked.
    """

    GAINED = "gained"
    NO_GAIN = "no_gain"
    NO_RESULT = "no_result"
    FAILED = "failed"
    PENDING = "pending"

    @property
    def counts_as_evidence(self) -> bool:
        return self is MemoryState.GAINED


#: Legacy ``record_attempt`` outcomes mapped onto the four declared memory states.
_OUTCOME_TO_STATE: dict[str, MemoryState] = {
    "no_new_information": MemoryState.NO_GAIN,
    "no_gain": MemoryState.NO_GAIN,
    "no_change": MemoryState.NO_GAIN,
    "no_result": MemoryState.NO_RESULT,
    "failed": MemoryState.FAILED,
    "unsupported": MemoryState.FAILED,
    "quarantined": MemoryState.FAILED,
    "blocked": MemoryState.FAILED,
    "approved": MemoryState.PENDING,
    "succeeded": MemoryState.GAINED,
    "partial": MemoryState.GAINED,
}


def classify_attempt(
    outcome: str,
    *,
    coverage: CoverageStatement | None = None,
    realised_gain: float | None = None,
) -> MemoryState:
    """Map a raw outcome string onto a declared memory state.

    Unrecognised strings are :attr:`MemoryState.NO_GAIN`, never :attr:`MemoryState.FAILED`
    and never :attr:`MemoryState.GAINED`. An outcome nobody can classify is evidence that
    the attempt taught nothing; reading it as a gain would satisfy an obligation on an
    event the platform does not understand.
    """
    state = _OUTCOME_TO_STATE.get(str(outcome).strip().lower())
    if state is not None:
        return state
    if coverage is not None:
        return MemoryState.NO_RESULT
    if realised_gain is not None and realised_gain > 0.0:
        return MemoryState.GAINED
    return MemoryState.NO_GAIN


@dataclass(frozen=True, slots=True)
class ActionSuppression:
    """FR-045: an action held back, with the way back in.

    Suppression without a stated reason and without declared re-open conditions is
    indistinguishable from a bug that forgot to try again, and the two are handled
    identically by an operator -- by giving up on the tool. So both are mandatory here:
    :meth:`__post_init__` refuses an entry missing either.
    """

    reason: str
    attempts_without_gain: int
    condition_fingerprint: str
    reopen_conditions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.reason).strip():
            raise ContextEngineError(
                "suppression_reason_missing",
                "a suppressed action must say why it is being held back, or an operator "
                "cannot tell a considered decision from a forgotten one (FR-045)",
            )
        if not self.reopen_conditions:
            raise ContextEngineError(
                "suppression_reopen_conditions_missing",
                "a suppression must declare what would lift it; a bar with no stated "
                "condition for lifting it is a wall, and FR-045 requires the condition",
            )
        object.__setattr__(self, "reopen_conditions", tuple(self.reopen_conditions))

    def lifted_by(self, condition_fingerprint: str) -> bool:
        """A *declared* condition change lifts the suppression. Nothing else does.

        Deliberately a comparison of declared fingerprints and not a heuristic: the point
        is that the platform can state exactly which declared change re-admitted the
        action. A retry counter, an elapsed timer or a mood does not lift it.
        """
        return condition_fingerprint != self.condition_fingerprint

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "attempts_without_gain": self.attempts_without_gain,
            "condition_fingerprint": self.condition_fingerprint,
            "reopen_conditions": list(self.reopen_conditions),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ActionSuppression:
        return cls(
            reason=str(payload["reason"]),
            attempts_without_gain=int(payload.get("attempts_without_gain", 0)),
            condition_fingerprint=str(payload.get("condition_fingerprint", "")),
            reopen_conditions=tuple(payload.get("reopen_conditions", ())),
        )


@dataclass(frozen=True, slots=True)
class SaturationState:
    """FR-052/053. Sufficiency, never effort.

    ``coverage_known`` and ``marginal_gain_known`` exist because the two halves of
    this record are produced by two different layers and neither layer always knows
    both. The fabric computes coverage, completeness and independence; an acquisition
    outcome reports coverage delta and marginal gain; neither is a superset of the
    other. Collapsing "not measured" into ``0.0`` would read as *measured and zero*,
    and ``0.0 <= marginal_gain_threshold`` would then close an obligation on an
    absence. An unknown therefore blocks saturation rather than satisfying it.

    ``required_independent_sources`` and ``required_source_families`` default to 0,
    meaning *no requirement was declared*. A caller that cannot justify an
    independence threshold leaves them at 0 and does not claim independence; a caller
    that measured it sets them and is held to it.
    """

    coverage: float
    marginal_gain: float
    distinct_sources: int
    source_diversity: int
    stopping_condition: str = ""
    coverage_threshold: float = 0.9
    marginal_gain_threshold: float = 0.05
    coverage_known: bool = True
    marginal_gain_known: bool = True
    required_independent_sources: int = 0
    required_source_families: int = 0

    def __post_init__(self) -> None:
        for name in ("coverage", "marginal_gain", "source_diversity_factor", "source_diversity"):
            if name in ("source_diversity_factor",):
                continue
        if not 0.0 <= self.coverage <= 1.0:
            raise ContextEngineError("coverage_out_of_range", f"{self.coverage}")
        if self.marginal_gain < 0.0:
            raise ContextEngineError("marginal_gain_negative", f"{self.marginal_gain}")

    @property
    def is_saturated(self) -> bool:
        return (
            self.coverage_known
            and self.marginal_gain_known
            and self.coverage >= self.coverage_threshold
            and self.marginal_gain <= self.marginal_gain_threshold
            and self.distinct_sources >= self.required_independent_sources
            and self.source_diversity >= self.required_source_families
        )

    def reason(self) -> str:
        """FR-054: the system must be able to say *why* it considers this settled.

        A refusal names the ingredient that is missing. ``coverage=0.85`` on its own
        is unreadable -- it does not say whether 0.85 is a measurement or a default,
        nor whether something else was the blocker.
        """
        missing: list[str] = []
        if not self.coverage_known:
            missing.append("coverage_unmeasured")
        elif self.coverage < self.coverage_threshold:
            missing.append(
                f"coverage={self.coverage:.2f}<{self.coverage_threshold}"
            )
        if not self.marginal_gain_known:
            missing.append("marginal_gain_unmeasured")
        elif self.marginal_gain > self.marginal_gain_threshold:
            missing.append(
                f"marginal_gain={self.marginal_gain:.3f}>{self.marginal_gain_threshold}"
            )
        if self.distinct_sources < self.required_independent_sources:
            missing.append(
                f"independent_sources={self.distinct_sources}"
                f"<{self.required_independent_sources}"
            )
        if self.source_diversity < self.required_source_families:
            missing.append(
                f"source_families={self.source_diversity}<{self.required_source_families}"
            )
        verdict = "not_saturated" if missing else "saturated"
        detail = "; ".join(missing) if missing else "all conditions met"
        return (
            f"{verdict}: {detail} "
            f"coverage={self.coverage:.2f} known={self.coverage_known} "
            f"marginal_gain={self.marginal_gain:.3f} known={self.marginal_gain_known} "
            f"distinct_sources={self.distinct_sources} diversity={self.source_diversity}"
            + (
                f" stopping={self.stopping_condition}"
                if self.stopping_condition
                else ""
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "coverage": self.coverage,
            "marginal_gain": self.marginal_gain,
            "distinct_sources": self.distinct_sources,
            "source_diversity": self.source_diversity,
            "stopping_condition": self.stopping_condition,
            "coverage_threshold": self.coverage_threshold,
            "marginal_gain_threshold": self.marginal_gain_threshold,
            "coverage_known": self.coverage_known,
            "marginal_gain_known": self.marginal_gain_known,
            "required_independent_sources": self.required_independent_sources,
            "required_source_families": self.required_source_families,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> SaturationState:
        return cls(
            coverage=payload["coverage"],
            marginal_gain=payload["marginal_gain"],
            distinct_sources=payload["distinct_sources"],
            source_diversity=payload["source_diversity"],
            stopping_condition=payload.get("stopping_condition", ""),
            coverage_threshold=payload.get("coverage_threshold", 0.9),
            marginal_gain_threshold=payload.get("marginal_gain_threshold", 0.05),
            coverage_known=bool(payload.get("coverage_known", True)),
            marginal_gain_known=bool(payload.get("marginal_gain_known", True)),
            required_independent_sources=int(payload.get("required_independent_sources", 0)),
            required_source_families=int(payload.get("required_source_families", 0)),
        )

    def key(self) -> str:
        return SATURATION_PREFIX + digest128(canonical_material(self.to_dict()))


@dataclass(frozen=True, slots=True)
class ResearchObligation:
    """FR-033, FR-038, FR-041. What must be learned, why, and what would count as an answer.

    An obligation carries its own justification. Nothing about *why this exists* or *what
    would settle it* is reachable only from a decision log: an obligation read on its own
    has to be auditable, because that is how an analyst meets it six months later with no
    session and no recorder to hand.

    The declared half is :attr:`trigger`, :attr:`acceptance_criteria`,
    :attr:`satisfaction_rule`, :attr:`required_capabilities` and
    :attr:`priority_components`. The measured half is :attr:`confidence`,
    :attr:`saturation` and :attr:`disposition_reason`. Keeping them in one frozen record
    with one address is deliberate -- an obligation and its justification cannot drift
    apart, because there is nothing to drift.
    """

    context_id: str
    question: str
    rationale: str = ""
    target_knowledge_type: KnowledgeType = KnowledgeType.ENTITY
    priority: float = 0.5
    status: ObligationStatus = ObligationStatus.OPEN
    created_by: str = ""
    satisfaction_criteria: tuple[str, ...] = ()
    confidence: float = 0.0
    related_hypothesis_ids: tuple[str, ...] = ()
    blocking_dependencies: tuple[str, ...] = ()
    saturation: SaturationState | None = None
    disposition: Disposition | None = None
    disposition_reason: str = ""
    obligation_id: str = ""
    #: FR-038 trigger block. ``None`` only on records built before this field existed.
    trigger: ObligationTrigger | None = None
    #: What the obligation needs in order to be discharged, and what could discharge it.
    required_capabilities: tuple[str, ...] = ()
    eligible_capabilities: tuple[str, ...] = ()
    capability_justification: str = ""
    #: The declared acceptance criteria, evaluated by the evaluator and nothing else.
    acceptance_criteria: tuple[AcceptanceCriterion, ...] = ()
    satisfaction_rule: SatisfactionRule = SatisfactionRule.DECLARED_CRITERIA
    priority_components: PriorityComponents = field(default_factory=PriorityComponents)
    #: ``measured`` / ``partial`` / ``unestimated`` -- whether :attr:`priority` is a
    #: derivation from the component vector or a declared fallback.
    priority_basis: str = "unestimated"
    expected_gain: float | None = None
    cost_range: tuple[float, float] | None = None
    uncertainty: tuple[str, ...] = ()
    #: Parent gap / hypothesis / contradiction / claim references (FR-038).
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", ObligationStatus(self.status))
        object.__setattr__(
            self, "target_knowledge_type", KnowledgeType(self.target_knowledge_type)
        )
        if self.disposition is not None:
            object.__setattr__(self, "disposition", Disposition(self.disposition))
        object.__setattr__(self, "satisfaction_criteria", tuple(self.satisfaction_criteria))
        object.__setattr__(self, "acceptance_criteria", tuple(self.acceptance_criteria))
        object.__setattr__(self, "required_capabilities", tuple(self.required_capabilities))
        object.__setattr__(self, "eligible_capabilities", tuple(self.eligible_capabilities))
        object.__setattr__(self, "source_refs", tuple(self.source_refs))
        object.__setattr__(self, "uncertainty", tuple(self.uncertainty))
        object.__setattr__(self, "satisfaction_rule", SatisfactionRule(self.satisfaction_rule))
        if isinstance(self.priority_components, Mapping):
            object.__setattr__(
                self, "priority_components", PriorityComponents.from_dict(self.priority_components)
            )
        if self.cost_range is not None:
            low, high = (float(value) for value in self.cost_range)
            if low > high:
                raise ContextEngineError(
                    "obligation_cost_range_inverted", f"{low}>{high}"
                )
            object.__setattr__(self, "cost_range", (low, high))
        if not self.context_id:
            raise ContextEngineError("obligation_context_missing", "obligation needs a context")
        if not self.question.strip():
            raise ContextEngineError("obligation_question_empty", "obligation needs a question")
        if not 0.0 <= self.priority <= 1.0:
            raise ContextEngineError("obligation_priority_out_of_range", f"{self.priority}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ContextEngineError("obligation_confidence_out_of_range", f"{self.confidence}")
        if self.status is ObligationStatus.SATISFIED and self.disposition is None:
            raise ContextEngineError(
                "obligation_satisfied_without_disposition",
                "a satisfied obligation must say it is satisfied",
            )
        addressed = self.address()
        if not self.obligation_id:
            object.__setattr__(self, "obligation_id", addressed)
        elif self.obligation_id != addressed:
            raise ContextEngineError(
                "obligation_id_mismatch",
                f"declared {self.obligation_id!r} but material addresses to {addressed!r}",
            )

    def _material(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "question": self.question,
            "rationale": self.rationale,
            "target_knowledge_type": self.target_knowledge_type.value,
            "priority": self.priority,
            "status": self.status.value,
            "created_by": self.created_by,
            "satisfaction_criteria": list(self.satisfaction_criteria),
            "confidence": self.confidence,
            "related_hypothesis_ids": list(self.related_hypothesis_ids),
            "blocking_dependencies": list(self.blocking_dependencies),
            "saturation": self.saturation.to_dict() if self.saturation else None,
            "disposition": self.disposition.value if self.disposition else None,
            "disposition_reason": self.disposition_reason,
            "trigger": self.trigger.to_dict() if self.trigger else None,
            "required_capabilities": list(self.required_capabilities),
            "eligible_capabilities": list(self.eligible_capabilities),
            "capability_justification": self.capability_justification,
            "acceptance_criteria": [c.to_dict() for c in self.acceptance_criteria],
            "satisfaction_rule": self.satisfaction_rule.value,
            "priority_components": self.priority_components.to_dict(),
            "priority_basis": self.priority_basis,
            "expected_gain": self.expected_gain,
            "cost_range": list(self.cost_range) if self.cost_range else None,
            "uncertainty": list(self.uncertainty),
            "source_refs": list(self.source_refs),
        }

    def address(self) -> str:
        """Obligation identity covers *what is being asked*, not how far it has got.

        Progress lives in a new revision of the same obligation; if progress changed
        the address, action memory keyed by obligation could never match again.
        """
        return OBLIGATION_ID_PREFIX + digest128(
            canonical_material(
                {
                    "context_id": self.context_id,
                    "question": self.question,
                    "target_knowledge_type": self.target_knowledge_type.value,
                }
            )
        )

    @property
    def missing_capabilities(self) -> tuple[str, ...]:
        """Required and not eligible. FR-038: the gap is named, never inferred."""
        return tuple(
            capability
            for capability in self.required_capabilities
            if capability not in self.eligible_capabilities
        )

    def with_id(self) -> ResearchObligation:
        from dataclasses import replace

        return replace(self, obligation_id=self.address())

    def to_dict(self) -> dict[str, Any]:
        return {**self._material(), "obligation_id": self.obligation_id}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResearchObligation:
        sat = payload.get("saturation")
        disp = payload.get("disposition")
        trig = payload.get("trigger")
        cost_range = payload.get("cost_range")
        return cls(
            context_id=payload["context_id"],
            question=payload["question"],
            rationale=payload.get("rationale", ""),
            target_knowledge_type=KnowledgeType(payload.get("target_knowledge_type", "entity")),
            priority=payload.get("priority", 0.5),
            status=ObligationStatus(payload.get("status", "open")),
            created_by=payload.get("created_by", ""),
            satisfaction_criteria=tuple(payload.get("satisfaction_criteria", ())),
            confidence=payload.get("confidence", 0.0),
            related_hypothesis_ids=tuple(payload.get("related_hypothesis_ids", ())),
            blocking_dependencies=tuple(payload.get("blocking_dependencies", ())),
            saturation=SaturationState.from_dict(sat) if sat else None,
            disposition=Disposition(disp) if disp else None,
            disposition_reason=payload.get("disposition_reason", ""),
            obligation_id=payload.get("obligation_id", ""),
            trigger=ObligationTrigger.from_dict(trig) if trig else None,
            required_capabilities=tuple(payload.get("required_capabilities", ())),
            eligible_capabilities=tuple(payload.get("eligible_capabilities", ())),
            capability_justification=payload.get("capability_justification", ""),
            acceptance_criteria=tuple(
                AcceptanceCriterion.from_dict(c) for c in payload.get("acceptance_criteria", ())
            ),
            satisfaction_rule=SatisfactionRule(
                payload.get("satisfaction_rule", SatisfactionRule.DECLARED_CRITERIA)
            ),
            priority_components=PriorityComponents.from_dict(
                payload.get("priority_components", {})
            ),
            priority_basis=payload.get("priority_basis", "unestimated"),
            expected_gain=payload.get("expected_gain"),
            cost_range=tuple(cost_range) if cost_range else None,
            uncertainty=tuple(payload.get("uncertainty", ())),
            source_refs=tuple(payload.get("source_refs", ())),
        )


@dataclass(frozen=True, slots=True)
class ResearchAction:
    """FR-036. A candidate means of satisfying an obligation. Never executed here."""

    obligation_id: str
    proposed_method: str
    runtime_ref: str = ""
    expected_information_gain: float = 0.0
    estimated_cost: float = 0.0
    priority: float = 0.5
    capability_requirements: tuple[str, ...] = ()
    requires_operator_approval: bool = True
    status: str = "proposed"
    task_id: str = ""
    realised_gain: float | None = None
    action_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "capability_requirements", tuple(self.capability_requirements))
        if not self.obligation_id:
            raise ContextEngineError("action_obligation_missing", "action needs an obligation")
        if not self.proposed_method.strip():
            raise ContextEngineError("action_method_empty", "action needs a method")
        if not 0.0 <= self.expected_information_gain <= 1.0:
            raise ContextEngineError("action_gain_out_of_range", f"{self.expected_information_gain}")
        if not 0.0 <= self.estimated_cost <= 1.0:
            raise ContextEngineError("action_cost_out_of_range", f"{self.estimated_cost}")
        addressed = self.address()
        if not self.action_id:
            object.__setattr__(self, "action_id", addressed)
        elif self.action_id != addressed:
            raise ContextEngineError(
                "action_id_mismatch",
                f"declared {self.action_id!r} but material addresses to {addressed!r}",
            )

    def _material(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "proposed_method": self.proposed_method,
            "runtime_ref": self.runtime_ref,
            "expected_information_gain": self.expected_information_gain,
            "estimated_cost": self.estimated_cost,
            "priority": self.priority,
            "capability_requirements": list(self.capability_requirements),
            "requires_operator_approval": self.requires_operator_approval,
            "status": self.status,
            "task_id": self.task_id,
            "realised_gain": self.realised_gain,
        }

    def address(self) -> str:
        return ACTION_ID_PREFIX + digest128(canonical_material(self._material()))

    def with_id(self) -> ResearchAction:
        from dataclasses import replace

        return replace(self, action_id=self.address())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ResearchAction:
        """Rebuild from :meth:`to_dict`.

        Added for the durable store. Every sibling in this module already had the pair,
        and an action that can be written but not read cannot survive a restart, so the
        asymmetry was a gap in the contract rather than a missing convenience.
        """
        return cls(
            action_id=str(data.get("action_id", "")),
            obligation_id=str(data.get("obligation_id", "")),
            proposed_method=str(data.get("proposed_method", "")),
            rationale=str(data.get("rationale", "")),
            expected_gain=float(data.get("expected_gain", 0.0)),
            capability_requirements=tuple(data.get("capability_requirements", ())),
            requires_operator_approval=bool(data.get("requires_operator_approval", True)),
            status=str(data.get("status", "proposed")),
            task_id=str(data.get("task_id", "")),
            realised_gain=data.get("realised_gain"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {**self._material(), "action_id": self.action_id}


@dataclass(frozen=True, slots=True)
class ActionMemoryEntry:
    """FR-059, FR-045. What was already attempted for an obligation.

    Without this the engine re-proposes work it has already done, which looks like
    diligence and is actually a loop.

    **The address includes the memory state and the declared condition fingerprint**, so
    one attempt key can accumulate several rows -- "could not look", "looked and found
    nothing", "looked and gained" -- as separate facts rather than overwriting one
    another. That separation is not bookkeeping: it is the only reason a later reader can
    tell a source outage apart from an exhausted search, and getting it wrong retires
    questions that were never asked.
    """

    obligation_id: str
    attempt_key: str
    outcome: str
    realised_gain: float | None = None
    entry_id: str = ""
    #: ``None`` on construction is derived from :attr:`outcome` by
    #: :func:`classify_attempt`; an explicit value always wins.
    state: MemoryState | None = None
    #: Present exactly when :attr:`state` is ``no_result``. The coverage statement is what
    #: makes "found nothing" a claim about a universe rather than about the absence of one.
    coverage: CoverageStatement | None = None
    failure_class: ErrorClass | None = None
    #: The declared conditions this attempt ran under. A change to them is what lifts a
    #: suppression -- and it is declared, never inferred from the clock or a counter.
    declared_conditions: tuple[tuple[str, str], ...] = ()
    condition_fingerprint: str = ""
    suppression: ActionSuppression | None = None
    detail: str = ""
    #: Which attempt this is, counting from 1 within one ``attempt_key``.

    #: It exists to separate two obligations that are otherwise in direct conflict, and
    #: both are load-bearing:
    #:
    #: * FR-065 -- a *redelivered* attempt must be idempotent, so it must address the same
    #:   row;
    #: * FR-045 -- two genuinely distinct attempts under identical conditions must both
    #:   count, or the second is silently swallowed by the store's own deduplication and
    #:   the suppression threshold is never reached.
    #:
    #: The sequence number is what tells them apart: a redelivery carries the number it
    #: was minted with, and a new attempt gets the next one.
    attempt_seq: int = 0

    def __post_init__(self) -> None:
        state = self.state or classify_attempt(
            self.outcome, coverage=self.coverage, realised_gain=self.realised_gain
        )
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "declared_conditions", tuple(self.declared_conditions))
        if not self.condition_fingerprint:
            object.__setattr__(self, "condition_fingerprint", self._fingerprint())
        if state is MemoryState.FAILED and self.coverage is not None:
            raise ContextEngineError(
                "failed_attempt_carries_a_coverage_statement",
                "a failed attempt did not search, so a coverage statement would be a claim "
                "about a search that never happened; 'we could not look' and 'we looked and "
                "found nothing' are different facts (contract 03)",
            )
        if state is MemoryState.NO_RESULT and self.coverage is None:
            raise ContextEngineError(
                "no_result_without_a_coverage_statement",
                "a no-result attempt must carry the coverage statement that produced it; a "
                "bare no-result is indistinguishable from a query that was never run",
            )
        addressed = MEMORY_PREFIX + digest128(
            canonical_material(
                {
                    "obligation_id": self.obligation_id,
                    "attempt_key": self.attempt_key,
                    "outcome": self.outcome,
                    "state": state.value,
                    "condition_fingerprint": self.condition_fingerprint,
                    "attempt_seq": self.attempt_seq,
                }
            )
        )
        if not self.entry_id:
            object.__setattr__(self, "entry_id", addressed)

    def _fingerprint(self) -> str:
        if not self.declared_conditions:
            return "no-declared-conditions"
        return digest128(canonical_material(dict(self.declared_conditions)))

    def is_suppressed_under(self, condition_fingerprint: str) -> bool:
        """Whether this attempt is currently held back. ``False`` once conditions change."""
        return self.suppression is not None and not self.suppression.lifted_by(
            condition_fingerprint
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "attempt_key": self.attempt_key,
            "outcome": self.outcome,
            "state": self.state.value if self.state else "",
            "realised_gain": self.realised_gain,
            "coverage": self.coverage.as_dict() if self.coverage is not None else None,
            "failure_class": str(self.failure_class) if self.failure_class else None,
            "declared_conditions": [list(pair) for pair in self.declared_conditions],
            "condition_fingerprint": self.condition_fingerprint,
            "suppression": self.suppression.to_dict() if self.suppression else None,
            "detail": self.detail,
            "attempt_seq": self.attempt_seq,
            "entry_id": self.entry_id,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ActionMemoryEntry:
        coverage = payload.get("coverage")
        suppression = payload.get("suppression")
        state = payload.get("state") or None
        # ``CoverageStatement.as_dict`` carries ``epistemic_state``, which is derived from
        # the other fields. Passing it back would make the round trip impossible and, worse,
        # would let a stored row state its own epistemic status instead of deriving it.
        declared_coverage = (
            {k: v for k, v in coverage.items() if k != "epistemic_state"} if coverage else None
        )
        return cls(
            obligation_id=str(payload["obligation_id"]),
            attempt_key=str(payload["attempt_key"]),
            outcome=str(payload.get("outcome", "")),
            realised_gain=payload.get("realised_gain"),
            entry_id=str(payload.get("entry_id", "")),
            state=MemoryState(state) if state else None,
            coverage=CoverageStatement(**declared_coverage) if declared_coverage else None,
            failure_class=ErrorClass(payload["failure_class"])
            if payload.get("failure_class")
            else None,
            declared_conditions=tuple(
                (str(k), str(v)) for k, v in payload.get("declared_conditions", ())
            ),
            condition_fingerprint=str(payload.get("condition_fingerprint", "")),
            suppression=ActionSuppression.from_dict(suppression) if suppression else None,
            detail=str(payload.get("detail", "")),
            attempt_seq=int(payload.get("attempt_seq", 0)),
        )


def condition_fingerprint(conditions: Mapping[str, str] | None) -> str:
    """One definition of "the declared conditions", used by both the writer and the reader.

    Two implementations of this produced two fingerprints that never matched, so a
    suppression was lifted by a condition change that had not happened. Sharing the
    definition is the fix, and it is the same class of bug as the attempt-key mismatch
    :meth:`ContextEngine._attempt_key` documents.
    """
    if not conditions:
        return "no-declared-conditions"
    return digest128(canonical_material({str(k): str(v) for k, v in sorted(conditions.items())}))


@dataclass(frozen=True, slots=True)
class ContextFrontier:
    """FR-058. Open work, as a queryable object rather than operator memory."""

    context_id: str
    state: InvestigationState
    open_obligations: tuple[str, ...] = ()
    blocked_obligations: tuple[str, ...] = ()
    closed_obligations: tuple[str, ...] = ()
    next_actions: tuple[str, ...] = ()
    pending_approval: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ContextFrontier:
        """Rebuild from :meth:`to_dict`; see :meth:`ResearchAction.from_dict`."""
        return cls(
            context_id=str(data.get("context_id", "")),
            state=InvestigationState(str(data.get("state", InvestigationState.UNINVESTIGATED))),
            open_obligations=tuple(data.get("open_obligations", ())),
            blocked_obligations=tuple(data.get("blocked_obligations", ())),
            closed_obligations=tuple(data.get("closed_obligations", ())),
            next_actions=tuple(data.get("next_actions", ())),
            pending_approval=tuple(data.get("pending_approval", ())),
            notes=tuple(data.get("notes", ())),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "state": self.state.value,
            "open_obligations": list(self.open_obligations),
            "blocked_obligations": list(self.blocked_obligations),
            "closed_obligations": list(self.closed_obligations),
            "next_actions": list(self.next_actions),
            "pending_approval": list(self.pending_approval),
            "notes": list(self.notes),
        }


__all__ = [
    "ACTION_ID_PREFIX",
    "MEMORY_PREFIX",
    "OBLIGATION_ID_PREFIX",
    "PRIORITY_COMPONENT_NAMES",
    "SATURATION_PREFIX",
    "AcceptanceCriterion",
    "ActionMemoryEntry",
    "ActionSuppression",
    "ContextFrontier",
    "CriterionBasis",
    "Disposition",
    "KnowledgeType",
    "MemoryState",
    "ObligationTrigger",
    "PriorityComponents",
    "ResearchAction",
    "ResearchObligation",
    "SatisfactionRule",
    "SaturationState",
    "classify_attempt",
    "condition_fingerprint",
]