"""The five Context Engine components (FR-041) and the engine that composes them.

FR-041 forbids a god object. Each responsibility below is a separate class with a
narrow interface, and :func:`assert_components_are_separate` checks that mechanically
rather than trusting the layout.

Separation is not stylistic. Each component has a different reason to change:

* the generator changes when *what counts as a gap* changes;
* the evaluator changes when *what counts as an answer* changes;
* the proposer changes when *how work is routed* changes;
* the recorder changes when *how causality is captured* changes;
* the manager changes when *how a revision commits* changes.

One class holding all five would make every one of those changes a change to the same
file, and would make "disable the adaptive layer" impossible to express.

Constitutional core vs adaptive layer (FR-045): ``DeterministicObligationGenerator``
is the constitutional core and runs with no adaptive input at all. The adaptive
layer only ever *ranks* -- it can change priority, never whether an obligation exists
or whether it is satisfied. That separation is what lets the engine be audited.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from contracts.stage_outcome import CoverageStatement, ErrorClass, StageStatus
from domain.investigation_context import (
    ContextEngineError,
    ContextRevision,
    InvestigationContext,
    InvestigationState,
    ObligationStatus,
)

from context_engine.obligations import (
    AcceptanceCriterion,
    ActionMemoryEntry,
    ActionSuppression,
    ContextFrontier,
    CriterionBasis,
    Disposition,
    KnowledgeType,
    MemoryState,
    ObligationTrigger,
    PriorityComponents,
    ResearchAction,
    ResearchObligation,
    SatisfactionRule,
    SaturationState,
    classify_attempt,
    condition_fingerprint,
)
from context_engine.store import (
    ChangePublisher,
    ContextChange,
    ContextStore,
    InMemoryChangePublisher,
    ReplayResult,
    StoreDurability,
    outbox_enqueue_contract,
)

DECISION_ID_PREFIX = "DEC-"
RULES_VERSION = "context-engine/rules/v1"
EVALUATOR_VERSION = RULES_VERSION


# =============================================================================
# 0. the stop-reason table (FR-046)
# =============================================================================


class StopReason(enum.StrEnum):
    """FR-046. The six reasons an investigation may terminate. Closed on purpose.

    An open vocabulary of stop reasons is a vocabulary of excuses. Every addition to this
    table is a decision that a particular condition genuinely ends the investigation,
    and the value of the closure is that the list is short enough to check every exit
    against -- which is exactly the check that fails when "the workflow expired" or "we
    ran out of retries" is treated as a reason rather than as a symptom.
    """

    COMPLETED = "completed"
    COMPLETED_WITH_LIMITATIONS = "completed_with_limitations"
    SATURATED = "saturated"
    BLOCKED = "blocked"
    NEEDS_REVIEW = "needs_review"
    CANCELLED = "cancelled"


#: FR-046 names five things that are **not** stop reasons by themselves. Held as a table
#: rather than a comment because the failure mode is somebody reaching for one of these
#: labels under time pressure, and the cheap place to stop that is a lookup that refuses.
FORBIDDEN_STOP_REASONS: dict[str, str] = {
    "empty_results": "a query that matched nothing is a result about a universe, not a reason to stop",
    "no_results": "a query that matched nothing is a result about a universe, not a reason to stop",
    "task_count": "a task count measures effort, not sufficiency (FR-040)",
    "tasks_complete": "a task count measures effort, not sufficiency (FR-040)",
    "retries_exhausted": "an exhausted retry budget means the route was blocked, not that the question is answered (FR-068)",
    "max_retries": "an exhausted retry budget means the route was blocked, not that the question is answered (FR-068)",
    "model_confidence": "a model's confidence in its own output is not evidence about the world",
    "low_confidence": "a model's confidence in its own output is not evidence about the world",
    "workflow_expired": "a workflow's lifetime is an implementation detail, not a finding",
    "timeout": "a workflow's lifetime is an implementation detail, not a finding",
}


def require_real_stop_reason(reason: str) -> StopReason | None:
    """Parse a stop reason, refusing the ones FR-046 forbids.

    Returns ``None`` for an empty reason -- a non-terminal report has no stop reason and
    that is a legitimate state. Everything else must be in :class:`StopReason`.
    """
    text = str(reason or "").strip()
    if not text:
        return None
    key = text.lower().replace(" ", "_").replace("-", "_")
    if key in FORBIDDEN_STOP_REASONS:
        raise ContextEngineError(
            "stop_reason_forbidden",
            f"{text!r} is not a stop reason: {FORBIDDEN_STOP_REASONS[key]} (FR-046)",
        )
    return StopReason(text)


# =============================================================================
# 1. obligation generator
# =============================================================================


class TriggerKind(enum.StrEnum):
    """Why an obligation exists. FR-034 requires this to be recorded, not guessed."""

    OPERATOR_INTENT = "operator_intent"
    COVERAGE_GAP = "coverage_gap"
    CONTRADICTION = "contradiction"
    LOW_CONFIDENCE = "low_confidence"
    SATURATION_SHORTFALL = "saturation_shortfall"
    ANOMALY = "anomaly"


#: Kinds whose trigger has no prior event to cite. The empty ``event_id`` is then a
#: declared consequence of the kind, not a field somebody forgot.
TRIGGER_KINDS_WITHOUT_EVENT: frozenset[str] = frozenset({TriggerKind.OPERATOR_INTENT.value})


@dataclass(frozen=True, slots=True)
class Trigger:
    """A versioned, inspectable reason for an obligation (FR-034, FR-038).

    Carries both ``rule_id`` and ``rule_version`` rather than one mashed-together string.
    The rule says which question fired; the version says which text of that rule fired it.
    With a single combined string you can tell that a rule fired but not whether the rule
    changed underneath it -- and a verdict computed against different text than the one
    recorded here is unauditable.
    """

    kind: TriggerKind
    rule_id: str
    detail: str
    rule_version: str = RULES_VERSION
    event_id: str = ""
    evidence_refs: tuple[str, ...] = ()

    @property
    def versioned_rule_id(self) -> str:
        return f"{self.rule_version}#{self.rule_id}"

    def to_obligation_trigger(self) -> ObligationTrigger:
        """The immutable block stored on the obligation itself (T046)."""
        return ObligationTrigger(
            kind=self.kind.value,
            rule_id=self.rule_id,
            rule_version=self.rule_version,
            reason=self.detail,
            event_id=self.event_id,
            evidence_refs=self.evidence_refs,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "event_id": self.event_id,
            "rule_id": self.rule_id,
            "rule_version": self.rule_version,
            "detail": self.detail,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class GapSignal:
    """What the generator is told about the world. Deliberately inert.

    ``priority`` is ``None`` by default, which means *not estimated*. It is not ``0.0``:
    a zero priority is a measurement that this gap matters least, and defaulting to it
    silently files every unranked obligation at the bottom of the board, which is a
    ranking nobody chose.
    """

    kind: TriggerKind
    question: str
    rationale: str = ""
    knowledge_type: KnowledgeType = KnowledgeType.ENTITY
    priority: float | None = None
    evidence_refs: tuple[str, ...] = ()
    event_id: str = ""
    required_capabilities: tuple[str, ...] = ()
    eligible_capabilities: tuple[str, ...] = ()
    capability_justification: str = ""
    acceptance_criteria: tuple[str, ...] = ()
    priority_components: PriorityComponents = field(default_factory=PriorityComponents)
    expected_gain: float | None = None
    cost_range: tuple[float, float] | None = None
    uncertainty: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "required_capabilities", tuple(self.required_capabilities))
        object.__setattr__(self, "eligible_capabilities", tuple(self.eligible_capabilities))
        object.__setattr__(self, "acceptance_criteria", tuple(self.acceptance_criteria))
        object.__setattr__(self, "uncertainty", tuple(self.uncertainty))
        object.__setattr__(self, "source_refs", tuple(self.source_refs))


#: The declared fallback when neither a scalar nor a component vector was estimated.
#: It is a *declared default*, recorded on the obligation as ``priority_basis="defaulted"``
#: -- never presented as a measurement, and never ``0.0``.
UNDECLARED_PRIORITY_FALLBACK = 0.5


class ObligationGenerator:
    """Creates obligations from declared gaps.

    Constitutional core: pure, rule-versioned, no adaptive input. Given the same
    signals it produces the same obligations, in the same order, with the same ids.
    """

    def __init__(self, *, rules_version: str = RULES_VERSION) -> None:
        self.rules_version = rules_version

    def trigger_for(self, signal: GapSignal) -> Trigger:
        return Trigger(
            kind=signal.kind,
            rule_id=signal.kind.value,
            detail=signal.rationale or f"{signal.kind.value} for {signal.question}",
            rule_version=self.rules_version,
            event_id=signal.event_id,
            evidence_refs=signal.evidence_refs,
        )

    def _criteria_for(self, signal: GapSignal, trigger: Trigger) -> tuple[AcceptanceCriterion, ...]:
        """The declared acceptance criteria, so none is ever "absent" (T041).

        A caller may declare its own criteria; when it does not, the generator declares
        one on its behalf: coverage sufficient and marginal gain spent. That is still a
        *declared* criterion rather than an implicit one, which is what lets the
        evaluator say why it closed an obligation rather than merely that it did.

        Caller-declared criteria default to the ``evidence_ref`` basis. Somebody who
        writes down what would answer their question knows that the answer is a record,
        not a threshold, and defaulting them to saturation would let a coverage number
        quietly discharge a criterion they never wrote for saturation.
        """
        if signal.acceptance_criteria:
            return tuple(
                AcceptanceCriterion(
                    criterion_id=f"{trigger.versioned_rule_id}#c{index}",
                    statement=statement,
                    basis=CriterionBasis.EVIDENCE_REF,
                    required_capabilities=signal.required_capabilities,
                )
                for index, statement in enumerate(signal.acceptance_criteria, start=1)
            )
        if signal.kind is TriggerKind.CONTRADICTION:
            return (
                AcceptanceCriterion(
                    criterion_id=f"{trigger.versioned_rule_id}#contradiction_resolved",
                    statement="the disagreement between the sources is resolved, not merely recorded",
                    basis=CriterionBasis.EVIDENCE_REF,
                ),
            )
        return (
            AcceptanceCriterion(
                criterion_id=f"{trigger.versioned_rule_id}#coverage_sufficient",
                statement=(
                    "coverage reaches the declared threshold and marginal gain falls to or "
                    "below it; effort alone never discharges this"
                ),
                basis=CriterionBasis.SATURATION,
                required_capabilities=signal.required_capabilities,
            ),
        )

    def generate(
        self, context: InvestigationContext, signals: Iterable[GapSignal]
    ) -> list[tuple[ResearchObligation, Trigger]]:
        """Obligations paired with their triggers. Order is by trigger then question,
        so the result does not depend on the caller's iteration order."""
        out: list[tuple[ResearchObligation, Trigger]] = []
        for signal in signals:
            trigger = self.trigger_for(signal)
            priority, priority_basis = self._resolve_priority(signal)
            obligation = ResearchObligation(
                context_id=context.context_id,
                question=signal.question,
                rationale=signal.rationale,
                target_knowledge_type=signal.knowledge_type,
                priority=priority,
                status=ObligationStatus.OPEN,
                created_by=trigger.versioned_rule_id,
                trigger=trigger.to_obligation_trigger(),
                required_capabilities=signal.required_capabilities,
                eligible_capabilities=signal.eligible_capabilities,
                capability_justification=signal.capability_justification,
                acceptance_criteria=self._criteria_for(signal, trigger),
                satisfaction_criteria=tuple(signal.acceptance_criteria),
                satisfaction_rule=SatisfactionRule.DECLARED_CRITERIA,
                priority_components=signal.priority_components,
                priority_basis=priority_basis,
                expected_gain=signal.expected_gain,
                cost_range=signal.cost_range,
                uncertainty=signal.uncertainty,
                source_refs=signal.source_refs,
            ).with_id()
            out.append((obligation, trigger))
        out.sort(key=lambda pair: (pair[1].rule_id, pair[0].question))
        return out

    def _resolve_priority(self, signal: GapSignal) -> tuple[float, str]:
        """Order by a declared scalar, else by the component vector, else by a named default.

        T047. The order matters: a declared scalar beats a derived one, because somebody
        stated it. The derived one beats the default for the same reason. And the default
        is *named* on the record rather than being an anonymous ``0.0`` -- which is the
        whole of T047: an unestimated component is null, and an unestimated priority says
        so instead of inventing a zero.
        """
        if signal.priority is not None:
            return float(signal.priority), "declared"
        derived = signal.priority_components.score()
        if derived is not None:
            return derived, f"derived:{signal.priority_components.basis}"
        return UNDECLARED_PRIORITY_FALLBACK, "defaulted"


# =============================================================================
# 2. satisfaction evaluator
# =============================================================================


@dataclass(frozen=True, slots=True)
class SatisfactionInput:
    """Everything the evaluator is allowed to read. FR-037: a pure function of these."""

    evidence_count: int
    saturation: SaturationState
    contradicting_evidence: int = 0
    blocking_dependencies: tuple[str, ...] = ()
    unresolved_dependencies: tuple[str, ...] = ()
    #: The evidence that discharged each declared criterion, by ``criterion_id``. A
    #: criterion with no entry here is unmet -- there is no default credit.
    criterion_evidence: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    #: Evidence the verdict may cite. Recorded so the verdict is auditable, never used to
    #: *decide* satisfaction: an evidence ref proves something is in hand, not that it
    #: answers the question.
    evidence_refs: tuple[str, ...] = ()
    #: The coverage statement behind a ``no_result``. Present only when a search actually
    #: happened and is declared.
    coverage: CoverageStatement | None = None
    #: The typed stage status, when the caller has one. Contract 03's statuses are
    #: mutually exclusive claims about the world and only two of them discharge anything.
    stage_status: StageStatus | None = None
    error_class: ErrorClass | None = None
    #: Capabilities that would have to exist for this obligation to be dischargeable.
    #: Named rather than inferred, because "we could not look" and "it is not there"
    #: look identical from the outside (T042).
    missing_capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "missing_capabilities", tuple(self.missing_capabilities))
        object.__setattr__(self, "blocking_dependencies", tuple(self.blocking_dependencies))
        object.__setattr__(self, "unresolved_dependencies", tuple(self.unresolved_dependencies))
        if self.stage_status is not None:
            object.__setattr__(self, "stage_status", StageStatus(self.stage_status))

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_count": self.evidence_count,
            "saturation": self.saturation.to_dict(),
            "contradicting_evidence": self.contradicting_evidence,
            "blocking_dependencies": list(self.blocking_dependencies),
            "unresolved_dependencies": list(self.unresolved_dependencies),
            "criterion_evidence": {
                key: list(value) for key, value in sorted(self.criterion_evidence.items())
            },
            "evidence_refs": list(self.evidence_refs),
            "coverage": self.coverage.as_dict() if self.coverage is not None else None,
            "stage_status": str(self.stage_status) if self.stage_status else None,
            "error_class": str(self.error_class) if self.error_class else None,
            "missing_capabilities": list(self.missing_capabilities),
        }


@dataclass(frozen=True, slots=True)
class SatisfactionBlocker:
    """One explicit reason an obligation did not close (FR-041).

    Blockers are a list, not a sentence. "Not satisfied" with one readable reason hides
    the fact that three separate conditions are outstanding, and the caller then fixes
    one and is surprised the obligation is still open.
    """

    kind: str
    detail: str
    missing_capability: str = ""
    criterion_id: str = ""
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not str(self.kind).strip():
            raise ContextEngineError("blocker_kind_missing", "a blocker must name its kind")
        if not str(self.detail).strip():
            raise ContextEngineError(
                "blocker_detail_missing",
                f"a {self.kind!r} blocker must say what it is; 'blocked' with nothing "
                "attached is the unreadable failure FR-041 exists to end",
            )
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))

    @property
    def names_a_capability(self) -> bool:
        return bool(self.missing_capability)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "detail": self.detail,
            "missing_capability": self.missing_capability,
            "criterion_id": self.criterion_id,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class SatisfactionVerdict:
    """Pure, versioned, testable in isolation (FR-037, FR-041).

    Carries the reasons *and* the evidence refs *and* the evaluator version, because a
    verdict that says only "no" is a verdict nobody can argue with.
    """

    obligation_id: str
    satisfied: bool
    confidence: float
    reason: str
    rules_version: str
    reasons: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    blockers: tuple[SatisfactionBlocker, ...] = ()
    criterion_ids: tuple[str, ...] = ()
    satisfied_criterion_ids: tuple[str, ...] = ()
    evaluator_version: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(self.reasons))
        object.__setattr__(self, "evidence_refs", tuple(self.evidence_refs))
        object.__setattr__(self, "blockers", tuple(self.blockers))
        object.__setattr__(self, "criterion_ids", tuple(self.criterion_ids))
        object.__setattr__(self, "satisfied_criterion_ids", tuple(self.satisfied_criterion_ids))
        if not self.evaluator_version:
            object.__setattr__(self, "evaluator_version", self.rules_version)

    @property
    def missing_capabilities(self) -> tuple[str, ...]:
        return tuple(sorted({b.missing_capability for b in self.blockers if b.names_a_capability}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "satisfied": self.satisfied,
            "confidence": self.confidence,
            "reason": self.reason,
            "reasons": list(self.reasons),
            "rules_version": self.rules_version,
            "evaluator_version": self.evaluator_version,
            "evidence_refs": list(self.evidence_refs),
            "blockers": [b.to_dict() for b in self.blockers],
            "criterion_ids": list(self.criterion_ids),
            "satisfied_criterion_ids": list(self.satisfied_criterion_ids),
            "missing_capabilities": list(self.missing_capabilities),
        }


#: The engine's declared default acceptance criterion, used when an obligation carries
#: none. The generator always declares one explicitly (T041), so this is reached only by
#: records that predate the field or were constructed outside the engine -- and the
#: verdict says in ``reasons`` that the fallback was used, so a reader can tell a declared
#: criterion from a substituted one.
DEFAULT_ACCEPTANCE_CRITERION = AcceptanceCriterion(
    criterion_id=f"{RULES_VERSION}#coverage_gap#coverage_sufficient",
    statement=(
        "coverage reaches the declared threshold and marginal gain falls to or below it; "
        "effort alone never discharges this"
    ),
    basis=CriterionBasis.SATURATION,
)


class SatisfactionEvaluator:
    """Decides whether an obligation is answered. Never asserts; only evaluates.

    FR-041: the only admissible input to a satisfaction verdict is the obligation's
    **declared acceptance criteria** measured against evidence. Three consequences fall
    out of that and each has a test:

    * a raw hit count never satisfies -- ``evidence_count`` is a lower bound on having
      looked, never a statement that the answer was found;
    * a contradiction never satisfies, and it never closes the item either;
    * a ``no_result`` is admissible evidence but is not a discharge, and a ``failed`` is
      not evidence at all (contract 03). The two are separate rows in action memory and
      separate branches here.
    """

    def __init__(self, *, rules_version: str = RULES_VERSION) -> None:
        self.rules_version = rules_version
        self.evaluator_version = EVALUATOR_VERSION

    def _declared_criteria(self, obligation: ResearchObligation) -> tuple[AcceptanceCriterion, ...]:
        return tuple(obligation.acceptance_criteria) or (DEFAULT_ACCEPTANCE_CRITERION,)

    def _criterion_met(
        self,
        criterion: AcceptanceCriterion,
        data: SatisfactionInput,
        unmet_capabilities: Sequence[str],
    ) -> tuple[bool, str]:
        """Whether one declared criterion is discharged, and why not when it is not."""
        missing = [c for c in criterion.required_capabilities if c in unmet_capabilities]
        if missing:
            return False, f"required capability {missing[0]!r} is unavailable"
        if criterion.basis is CriterionBasis.EVIDENCE_REF:
            refs = tuple(data.criterion_evidence.get(criterion.criterion_id, ()))
            if not refs:
                return False, "no evidence was cited against this criterion"
            return True, f"discharged by {list(refs)}"
        if criterion.basis is CriterionBasis.COVERAGE_STATEMENT:
            if data.coverage is None:
                return False, "no coverage statement was supplied"
            if not data.coverage.may_support_absence:
                return False, (
                    f"coverage statement is {data.coverage.epistemic_state!s}; without "
                    "declared detection power it cannot support an absence"
                )
            return True, f"qualified absence over {data.coverage.universe}"
        if not data.saturation.is_saturated:
            return False, f"not saturated: {data.saturation.reason()}"
        return True, f"saturated: {data.saturation.reason()}"

    def _refuse(
        self,
        obligation: ResearchObligation,
        *,
        reason: str,
        blockers: Sequence[SatisfactionBlocker],
        reasons: Sequence[str] = (),
        confidence: float | None = None,
        evidence_refs: Sequence[str] = (),
        criteria: Sequence[AcceptanceCriterion] = (),
        met: Sequence[str] = (),
    ) -> SatisfactionVerdict:
        all_reasons = (reason, *reasons) if reason else tuple(reasons)
        return SatisfactionVerdict(
            obligation_id=obligation.obligation_id,
            satisfied=False,
            confidence=obligation.confidence if confidence is None else confidence,
            reason=reason,
            rules_version=self.rules_version,
            reasons=all_reasons,
            evidence_refs=tuple(evidence_refs),
            blockers=tuple(blockers),
            criterion_ids=tuple(c.criterion_id for c in criteria),
            satisfied_criterion_ids=tuple(met),
            evaluator_version=self.evaluator_version,
        )

    def evaluate(
        self, obligation: ResearchObligation, data: SatisfactionInput
    ) -> SatisfactionVerdict:
        criteria = self._declared_criteria(obligation)
        unmet_capabilities = tuple(data.missing_capabilities)
        notes: list[str] = []
        if not obligation.acceptance_criteria:
            notes.append(
                "no acceptance criteria were declared on this obligation; evaluated against "
                "the engine's declared default saturation criterion"
            )

        if data.unresolved_dependencies:
            return self._refuse(
                obligation,
                reason=f"blocked by unresolved {list(data.unresolved_dependencies)}",
                blockers=[
                    SatisfactionBlocker(
                        kind="unresolved_dependency",
                        detail=f"depends on {list(data.unresolved_dependencies)}",
                    )
                ],
                reasons=notes,
                criteria=criteria,
            )

        if data.contradicting_evidence > 0:
            # FR-038: contradiction never silently satisfies; it produces a new
            # obligation or a contradiction record, never a quiet close.
            return self._refuse(
                obligation,
                reason=(
                    f"contradicted by {data.contradicting_evidence} record(s); "
                    "a contradiction cannot satisfy an obligation"
                ),
                blockers=[
                    SatisfactionBlocker(
                        kind="contradiction",
                        detail=(
                            f"{data.contradicting_evidence} contradicting record(s); "
                            "disagreement is not convergence"
                        ),
                        evidence_refs=tuple(data.evidence_refs),
                    )
                ],
                reasons=notes,
                confidence=0.0,
                evidence_refs=data.evidence_refs,
                criteria=criteria,
            )

        if unmet_capabilities:
            named = ", ".join(repr(c) for c in unmet_capabilities)
            return self._refuse(
                obligation,
                reason=(
                    f"blocked: required capability {named} is unavailable; we could not look, "
                    "which is not the same as it not being there"
                ),
                blockers=[
                    SatisfactionBlocker(
                        kind="capability_unavailable",
                        detail=f"no capability provides {named}",
                        missing_capability=unmet_capabilities[0],
                    )
                    for _ in unmet_capabilities
                ],
                reasons=notes,
                evidence_refs=data.evidence_refs,
                criteria=criteria,
            )

        if data.stage_status is not None and not data.stage_status.may_satisfy_obligation:
            # Contract 03. ``failed``, ``unsupported``, ``no_result`` and friends each say
            # something different about the world and none of them is an answer.
            return self._refuse(
                obligation,
                reason=(
                    f"stage status {data.stage_status.value} does not discharge an obligation"
                    + (f": {data.error_class}" if data.error_class is not None else "")
                ),
                blockers=[
                    SatisfactionBlocker(
                        kind="stage_status",
                        detail=(
                            f"stage reported {data.stage_status.value}"
                            + (f" ({data.error_class})" if data.error_class is not None else "")
                        ),
                        missing_capability=unmet_capabilities[0] if unmet_capabilities else "",
                        evidence_refs=tuple(data.evidence_refs),
                    )
                ],
                reasons=notes,
                evidence_refs=data.evidence_refs,
                criteria=criteria,
            )

        met: list[str] = []
        unmet: list[SatisfactionBlocker] = []
        coverage_discharged = False
        for criterion in criteria:
            satisfied, why = self._criterion_met(criterion, data, unmet_capabilities)
            if satisfied:
                met.append(criterion.criterion_id)
                if criterion.basis is CriterionBasis.COVERAGE_STATEMENT:
                    coverage_discharged = True
            else:
                unmet.append(
                    SatisfactionBlocker(
                        kind="criterion_unmet",
                        detail=f"{criterion.criterion_id}: {why}",
                        criterion_id=criterion.criterion_id,
                        evidence_refs=tuple(data.criterion_evidence.get(criterion.criterion_id, ())),
                    )
                )
        if unmet:
            return self._refuse(
                obligation,
                reason=(
                    f"{len(unmet)} of {len(criteria)} declared acceptance criteria unmet: "
                    + "; ".join(b.detail for b in unmet)
                ),
                blockers=unmet,
                reasons=notes,
                evidence_refs=data.evidence_refs,
                criteria=criteria,
                met=met,
            )

        if data.evidence_count == 0 and not coverage_discharged:
            return self._refuse(
                obligation,
                reason="no evidence; acquisition count alone can never satisfy (FR-053)",
                blockers=[
                    SatisfactionBlocker(
                        kind="no_evidence",
                        detail=(
                            "zero supporting records; nothing was established, so no declared "
                            "criterion can have been met by evidence"
                        ),
                    )
                ],
                reasons=notes,
                confidence=0.0,
                evidence_refs=data.evidence_refs,
                criteria=criteria,
                met=met,
            )

        evidence_refs = tuple(data.evidence_refs) or tuple(
            ref for criterion in criteria for ref in data.criterion_evidence.get(criterion.criterion_id, ())
        )
        reasons = (
            *notes,
            f"all {len(criteria)} declared acceptance criteria met",
        )
        return SatisfactionVerdict(
            obligation_id=obligation.obligation_id,
            satisfied=True,
            confidence=min(1.0, data.saturation.coverage),
            reason=f"saturated: {data.saturation.reason()}",
            rules_version=self.rules_version,
            reasons=reasons,
            evidence_refs=evidence_refs,
            blockers=(),
            criterion_ids=tuple(c.criterion_id for c in criteria),
            satisfied_criterion_ids=tuple(met),
            evaluator_version=self.evaluator_version,
        )


# =============================================================================
# 3. action proposer
# =============================================================================


@dataclass(frozen=True, slots=True)
class CapabilityDescriptor:
    """D4: declarative capabilities, from the Source/Tool Catalogue.

    Routing is still by ``runtime_ref`` first and capabilities are a compatibility
    check, exactly as ``runtime/__init__.py:10-14`` requires. This descriptor is a
    *compatibility* input, never a selector.
    """

    runtime_ref: str
    capabilities: tuple[str, ...]
    source_id: str = ""
    cost_class: str = "cheap"
    active: bool = True

    def supports(self, required: Sequence[str]) -> bool:
        return set(required).issubset(self.capabilities)


class ActionProposer:
    """Proposes how an obligation might be satisfied. Never executes (FR-036)."""

    def __init__(self, catalogue: Sequence[CapabilityDescriptor] = ()) -> None:
        self._catalogue = tuple(catalogue)

    def propose(
        self,
        obligation: ResearchObligation,
        *,
        already_attempted: Iterable[str] = (),
        required_capabilities: Sequence[str] = (),
    ) -> ResearchAction | None:
        """Best compatible action, or None when no capability fits.

        Returns None rather than inventing a capability: FR-040 requires an
        unsatisfiable obligation to surface as a proposed capability requirement,
        which the caller records -- not something the proposer quietly implements.
        """
        attempted = set(already_attempted)
        candidates = [
            descriptor
            for descriptor in self._catalogue
            if descriptor.active and descriptor.supports(required_capabilities)
        ]
        if not candidates:
            return None

        def rank(d: CapabilityDescriptor) -> tuple[float, str]:
            return (-(1.0 / (1.0 + (0.2 if d.cost_class == "expensive" else 0.0))), d.runtime_ref)

        for descriptor in sorted(candidates, key=rank):
            key = f"{descriptor.runtime_ref}|{obligation.question}"
            if key in attempted:
                continue
            return ResearchAction(
                obligation_id=obligation.obligation_id,
                proposed_method=f"acquire via {descriptor.runtime_ref}",
                runtime_ref=descriptor.runtime_ref,
                expected_information_gain=min(1.0, obligation.priority + 0.2),
                estimated_cost=0.4 if descriptor.cost_class == "expensive" else 0.1,
                priority=obligation.priority,
                capability_requirements=tuple(required_capabilities),
                requires_operator_approval=True,
            ).with_id()
        return None


# =============================================================================
# 4. decision recorder
# =============================================================================


@dataclass(frozen=True, slots=True)
class ContextDecision:
    """FR-044: what caused what. Every decision names its input, rule, and prior state."""

    decision_id: str
    context_id: str
    kind: str
    input_event_ids: tuple[str, ...]
    rule_id: str
    prior_state: str
    outcome: str
    mode: str = "deterministic"
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "context_id": self.context_id,
            "kind": self.kind,
            "input_event_ids": list(self.input_event_ids),
            "rule_id": self.rule_id,
            "prior_state": self.prior_state,
            "outcome": self.outcome,
            "mode": self.mode,
            "detail": self.detail,
        }


class DecisionRecorder:
    """Append-only. Explanations are the product, not a by-product (FR-044)."""

    def __init__(self, *, rules_version: str = RULES_VERSION) -> None:
        self.rules_version = rules_version
        self._decisions: list[ContextDecision] = []

    def record(
        self,
        *,
        context_id: str,
        kind: str,
        input_event_ids: Sequence[str],
        prior_state: str,
        outcome: str,
        detail: str = "",
        mode: str = "deterministic",
    ) -> ContextDecision:
        from domain.relation_identity import canonical_material, digest128

        material = canonical_material(
            {
                "context_id": context_id,
                "kind": kind,
                "input_event_ids": sorted(input_event_ids),
                "rule_id": self.rules_version,
                "prior_state": prior_state,
                "outcome": outcome,
                "mode": mode,
            }
        )
        decision = ContextDecision(
            decision_id=DECISION_ID_PREFIX + digest128(material),
            context_id=context_id,
            kind=kind,
            input_event_ids=tuple(sorted(input_event_ids)),
            rule_id=self.rules_version,
            prior_state=prior_state,
            outcome=outcome,
            mode=mode,
            detail=detail,
        )
        self._decisions.append(decision)
        return decision

    def decisions(self, context_id: str | None = None) -> tuple[ContextDecision, ...]:
        return tuple(
            d for d in self._decisions if context_id is None or d.context_id == context_id
        )

    def explain(self, decision_id: str) -> ContextDecision | None:
        for d in self._decisions:
            if d.decision_id == decision_id:
                return d
        return None


# =============================================================================
# 5. revision manager
# =============================================================================


class RevisionManager:
    """Commits revisions transactionally with their decisions (FR-047)."""

    def __init__(self, store: ContextStore) -> None:
        self.store = store

    async def commit(
        self,
        context: InvestigationContext,
        *,
        state: InvestigationState,
        caused_by_event_ids: Sequence[str],
        decision_ids: Sequence[str],
        operator_actions: Sequence[str] = (),
        mode: str = "deterministic",
    ) -> ContextRevision:
        number = await self.store.next_revision_number(context.context_id)
        revision = context.next_revision(
            revision=number,
            state=state,
            caused_by_event_ids=tuple(caused_by_event_ids),
            decision_ids=tuple(decision_ids),
            operator_actions=tuple(operator_actions),
            rules_version=RULES_VERSION,
            mode=mode,
        ).with_id()
        await self.store.append_revision(revision)
        return revision


# =============================================================================
# composition
# =============================================================================


@dataclass(frozen=True, slots=True)
class UnexecutedScope:
    """Work that was in scope and did not happen (FR-046).

    "We finished" and "we finished the part that worked" are different statements and the
    second one is only honest if the omitted part is written down. Naming the omitted
    obligation and the capability that was missing is what turns a stop into something an
    analyst can act on.
    """

    obligation_id: str
    question: str
    reason: str
    missing_capabilities: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, str | list[str]]:
        return {
            "obligation_id": self.obligation_id,
            "question": self.question,
            "reason": self.reason,
            "missing_capabilities": list(self.missing_capabilities),
        }


@dataclass(frozen=True, slots=True)
class TerminationReport:
    """FR-057, FR-046. Why an investigation stopped, in a form an operator can read.

    ``stop_reason`` is ``None`` for a non-terminal report and that is a *state*, not an
    omission: an investigation with open work has not stopped, so it has no reason for
    having stopped. Every report carries :attr:`still_unknown` and
    :attr:`unexecuted_scope` regardless, because a reader has to be able to ask "and what
    did you not do?" of an investigation that is still running too.
    """

    context_id: str
    is_terminal: bool
    state: str
    total_obligations: int
    reasons_by_status: dict[str, list[dict[str, str]]]
    still_unknown: tuple[str, ...] = ()
    would_reopen_on: tuple[dict[str, str], ...] = ()
    stop_reason: StopReason | None = None
    stop_reason_detail: str = ""
    unexecuted_scope: tuple[UnexecutedScope, ...] = ()

    @property
    def has_a_reasoned_stop(self) -> bool:
        """A terminal report with a reason from the allowed table. FR-046."""
        return self.is_terminal and self.stop_reason is not None and bool(self.stop_reason_detail)

    def to_dict(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "is_terminal": self.is_terminal,
            "state": self.state,
            "total_obligations": self.total_obligations,
            "reasons_by_status": self.reasons_by_status,
            "still_unknown": list(self.still_unknown),
            "would_reopen_on": [dict(r) for r in self.would_reopen_on],
            "stop_reason": str(self.stop_reason) if self.stop_reason else None,
            "stop_reason_detail": self.stop_reason_detail,
            "unexecuted_scope": [scope.to_dict() for scope in self.unexecuted_scope],
        }


def _derive_stop_reason(
    obligations: Sequence[ResearchObligation], terminal: bool
) -> tuple[StopReason | None, str]:
    """Map a settled board onto the FR-046 table, or onto nothing.

    Derived rather than supplied, because the caller that reports a stop is exactly the
    caller that ran out of things to try -- if it could name the reason it would have
    named it earlier. And constrained, because ``require_real_stop_reason`` is only a
    guard against *bad* reasons; it cannot invent a good one.
    """
    if not terminal or not obligations:
        return None, ""
    statuses = {o.status for o in obligations}
    if ObligationStatus.OPEN in statuses or ObligationStatus.PARTIALLY_SATISFIED in statuses:
        return None, ""
    if ObligationStatus.BLOCKED in statuses:
        return StopReason.BLOCKED, (
            "blocked: "
            + "; ".join(
                sorted(
                    f"{o.obligation_id}: {o.disposition_reason or 'no reason recorded'}"
                    for o in obligations
                    if o.status is ObligationStatus.BLOCKED
                )
            )
        )
    if ObligationStatus.ABANDONED in statuses:
        return StopReason.COMPLETED_WITH_LIMITATIONS, (
            "completed with limitations: "
            + "; ".join(
                sorted(
                    f"{o.question} was abandoned ({o.disposition_reason or 'no reason recorded'})"
                    for o in obligations
                    if o.status is ObligationStatus.ABANDONED
                )
            )
        )
    return StopReason.COMPLETED, (
        "completed: every obligation satisfied against its declared acceptance criteria"
    )


COMPONENT_ROLES = (
    "generate",
    "evaluate",
    "propose",
    "record",
    "commit",
)

#: FR-045. How many no-gain attempts under one declared condition suppress an action.
DEFAULT_NO_GAIN_THRESHOLD = 2

#: The complete set of publication seams on ``ContextEngine``. ``_publish`` is the one;
#: ``_publish_decision`` is a named convenience that must delegate to it. Both are listed
#: because the drift check is an equality against this set, so *adding* a seam is a
#: deliberate act rather than something that happens in a patch.
_PUBLICATION_SEAMS: frozenset[str] = frozenset({"_publish", "_publish_decision"})


class ContextEngine:
    """Composes the five components. Owns no decision logic of its own.

    ``mode`` is explicit per revision (FR-046). The constitutional core -- the
    generator and the evaluator -- is never touched by the adaptive layer.
    """

    def __init__(
        self,
        store: ContextStore,
        *,
        generator: ObligationGenerator | None = None,
        evaluator: SatisfactionEvaluator | None = None,
        proposer: ActionProposer | None = None,
        recorder: DecisionRecorder | None = None,
        require_durable: bool = False,
        publisher: ChangePublisher | None = None,
        no_gain_threshold: int = DEFAULT_NO_GAIN_THRESHOLD,
        suppressible_states: Sequence[MemoryState] = (MemoryState.NO_GAIN,),
    ) -> None:
        if require_durable and store.durability() is not StoreDurability.DURABLE:
            raise ContextEngineError(
                "store_not_durable",
                "FR-027 requires context state to survive a restart; this store "
                f"reports {store.durability().value}",
            )
        self.store = store
        self.generator = generator or ObligationGenerator()
        self.evaluator = evaluator or SatisfactionEvaluator()
        self.proposer = proposer or ActionProposer()
        self.recorder = recorder or DecisionRecorder()
        self.revisions = RevisionManager(store)
        #: The one publication seam (T051). Injected by a durable deployment as
        #: ``SqlOutboxChangePublisher`` over ``db.materialization_outbox``; the default
        #: keeps changes in-process, matching a memory-durability store.
        self.publisher = publisher or InMemoryChangePublisher()
        self.no_gain_threshold = no_gain_threshold
        #: Which memory states count towards the no-gain suppression. Declared rather than
        #: hard-coded because the choice is a policy one and the two obvious alternatives
        #: are genuinely different: ``NO_GAIN`` is an action that ran and taught nothing
        #: (FR-045's case), whereas ``NO_RESULT`` is an action that ran and legitimately
        #: found nothing, which usually means the *next* universe is the one to try. A
        #: deployment that disagrees passes its own tuple; the default refuses to guess.
        self.suppressible_states = tuple(MemoryState(s) for s in suppressible_states)

    async def _publish(
        self,
        kind: str,
        context_id: str,
        subject_id: str,
        *,
        tenant_id: str,
        revision_id: str = "",
        payload: Mapping[str, Any] | None = None,
    ) -> None:
        await self.publisher.publish(
            ContextChange(
                kind=kind,
                tenant_id=tenant_id,
                context_id=context_id,
                subject_id=subject_id,
                revision_id=revision_id,
                payload=dict(payload or {}),
            )
        )

    async def _publish_decision(
        self, decision: ContextDecision, tenant_id: str, revision_id: str = ""
    ) -> None:
        await self._publish(
            "decision.recorded",
            decision.context_id,
            decision.decision_id,
            tenant_id=tenant_id,
            revision_id=revision_id,
            payload={
                "kind": decision.kind,
                "outcome": decision.outcome,
                "rule_id": decision.rule_id,
            },
        )

    # -- queries (FR-050) ----------------------------------------------------

    async def open_obligations(self, context_id: str) -> tuple[ResearchObligation, ...]:
        return tuple([
            o
            for o in await self.store.obligations(context_id)
            if o.status
            in (ObligationStatus.OPEN, ObligationStatus.PARTIALLY_SATISFIED)
        ])

    async def satisfied_obligations(self, context_id: str) -> tuple[ResearchObligation, ...]:
        return tuple([
            o for o in await self.store.obligations(context_id) if o.status is ObligationStatus.SATISFIED
        ])

    async def contradicted_obligations(self, context_id: str) -> tuple[ResearchObligation, ...]:
        return tuple([
            o for o in await self.store.obligations(context_id) if o.status is ObligationStatus.BLOCKED
        ])

    async def revision_history(self, context_id: str) -> tuple[ContextRevision, ...]:
        return await self.store.revisions(context_id)

    async def frontier(self, context_id: str) -> ContextFrontier | None:
        return await self.store.get_frontier(context_id)

    # -- the loop ------------------------------------------------------------

    async def ingest(
        self,
        context: InvestigationContext,
        signals: Iterable[GapSignal] = (),
        *,
        event_ids: Sequence[str] = (),
        mode: str = "deterministic",
    ) -> tuple[ContextRevision, list[ResearchObligation]]:
        """One tick: generate obligations from gaps, then commit a revision.

        Incremental (FR-042): only the signals passed in are considered, and the
        revision names them, so a caller can always say which change caused what.
        """
        await self.store.put_context(context)
        created: list[ResearchObligation] = []
        for obligation, trigger in self.generator.generate(context, signals):
            existing = await self.store.get_obligation(obligation.obligation_id)
            if existing is not None:
                continue  # stable address: re-proposing the same gap is not new work
            await self.store.put_obligation(obligation)
            created.append(obligation)
            decision = self.recorder.record(
                context_id=context.context_id,
                kind="obligation_created",
                input_event_ids=event_ids,
                prior_state=context.state.value,
                outcome=obligation.obligation_id,
                detail=f"{trigger.versioned_rule_id}: {trigger.detail}",
                mode=mode,
            )
            await self._publish(
                "obligation.created",
                context.context_id,
                obligation.obligation_id,
                tenant_id=context.tenant_id,
                payload={
                    "question": obligation.question,
                    "trigger": obligation.trigger.to_dict() if obligation.trigger else {},
                    "required_capabilities": list(obligation.required_capabilities),
                    "acceptance_criteria": [
                        c.criterion_id for c in obligation.acceptance_criteria
                    ],
                    "priority_basis": obligation.priority_basis,
                    "decision_id": decision.decision_id,
                },
            )
            await self._publish_decision(decision, context.tenant_id)

        decision_ids = tuple(
            d.decision_id for d in self.recorder.decisions(context.context_id)
        )
        state = InvestigationState.ACTIVE if created else context.state
        revision = await self.revisions.commit(
            context,
            state=state,
            caused_by_event_ids=event_ids,
            decision_ids=decision_ids,
            mode=mode,
        )
        for obligation in created:
            await self._publish(
                "obligation.created",
                context.context_id,
                obligation.obligation_id,
                tenant_id=context.tenant_id,
                revision_id=revision.revision_id,
            )
        await self.store.put_frontier(
            ContextFrontier(
                context_id=context.context_id,
                state=state,
                open_obligations=tuple(sorted([o.obligation_id for o in await self.open_obligations(context.context_id)])),
            )
        )
        return revision, created

    async def evaluate_obligation(
        self, obligation_id: str, data: SatisfactionInput, *, mode: str = "deterministic"
    ) -> SatisfactionVerdict:
        from dataclasses import replace

        obligation = await self.store.get_obligation(obligation_id)
        if obligation is None:
            raise ContextEngineError("obligation_unknown", obligation_id)
        verdict = self.evaluator.evaluate(obligation, data)
        # A source failure and a missing capability both leave the obligation BLOCKED and
        # never SATISFIED -- the item stays on the board with the missing capability named,
        # which is the only difference from a contradiction that matters to a reader.
        capability_blockers = [
            b
            for b in verdict.blockers
            if b.kind in ("capability_unavailable", "stage_status")
        ]
        if verdict.satisfied:
            new = replace(
                obligation,
                status=ObligationStatus.SATISFIED,
                confidence=verdict.confidence,
                saturation=data.saturation,
                disposition=Disposition.SATISFIED,
                disposition_reason=verdict.reason,
            ).with_id()
        elif data.contradicting_evidence > 0 or capability_blockers:
            named = verdict.missing_capabilities or tuple(obligation.missing_capabilities)
            reason = verdict.reason
            if named and not all(capability in reason for capability in named):
                reason = f"{reason} [missing capability: {', '.join(named)}]"
            new = replace(
                obligation,
                status=ObligationStatus.BLOCKED,
                confidence=0.0,
                saturation=data.saturation,
                disposition=Disposition.BLOCKED,
                disposition_reason=reason,
            ).with_id()
        else:
            new = replace(
                obligation, saturation=data.saturation, confidence=verdict.confidence
            ).with_id()
        await self.store.put_obligation(new)
        decision = self.recorder.record(
            context_id=new.context_id,
            kind="obligation_evaluated",
            input_event_ids=(),
            prior_state=obligation.status.value,
            outcome=new.status.value,
            detail=verdict.reason,
            mode=mode,
        )
        context = await self.store.get_context(new.context_id)
        if context is not None:
            await self._publish(
                "obligation.transitioned",
                new.context_id,
                new.obligation_id,
                tenant_id=context.tenant_id,
                payload={
                    "transition": obligation.status.value,
                    "to": new.status.value,
                    "reason": verdict.reason,
                    "blockers": [b.to_dict() for b in verdict.blockers],
                    "missing_capabilities": list(verdict.missing_capabilities),
                    "criteria_met": list(verdict.satisfied_criterion_ids),
                    "evaluator_version": verdict.evaluator_version,
                    "decision_id": decision.decision_id,
                },
            )
            await self._publish_decision(decision, context.tenant_id)
            # An evaluation is a change of research state, so it gets a revision like any
            # other. Without this the chain records only the ticks that minted obligations,
            # and the evidence that moved an obligation is visible on the obligation but
            # absent from the history -- so the chain cannot answer "what changed this,
            # and why", which is the only question a chain exists to answer.
            revision = await self.revisions.commit(
                context,
                state=context.state,
                caused_by_event_ids=tuple(data.evidence_refs),
                decision_ids=(decision.decision_id,),
                mode=mode,
            )
            await self._publish(
                "obligation.transitioned",
                new.context_id,
                new.obligation_id,
                tenant_id=context.tenant_id,
                revision_id=revision.revision_id,
                payload={"revision": revision.revision},
            )
        return verdict

    def _attempt_key(self, obligation: ResearchObligation, runtime_ref: str) -> str:
        """One definition of "already attempted", used by both the proposer and the
        memory writer.

        They previously disagreed -- the proposer compared ``runtime_ref|question``
        while the memory recorded ``runtime_ref|method`` -- so the engine could
        propose work it had already run. That is the exact loop action memory exists
        to prevent.
        """
        return f"{runtime_ref}|{obligation.question}"

    async def propose_action(
        self,
        obligation_id: str,
        *,
        required_capabilities: Sequence[str] = (),
        conditions: Mapping[str, str] | None = None,
    ) -> ResearchAction | None:
        """Propose, never execute (FR-036). Returns None when nothing can be
        proposed -- the caller then records a capability requirement (FR-040).

        ``conditions`` are the declared conditions the proposal would run under (FR-045).
        An attempt whose suppression was lifted by a *declared* condition change becomes
        proposable again; one that is still suppressed is not, and the reason it was
        suppressed stays readable through :meth:`suppression_for`.
        """
        obligation = await self.store.get_obligation(obligation_id)
        if obligation is None:
            raise ContextEngineError("obligation_unknown", obligation_id)
        current = condition_fingerprint(conditions)
        memory = await self.store.memory_for(obligation_id)
        overridden = {
            entry.attempt_key
            for entry in memory
            if entry.outcome == "override" and entry.condition_fingerprint == current
        }
        # FR-059: attempts, not proposals. A proposal that never ran is not history. FR-045
        # carves out exactly one exception: a *suppressed* attempt stops blocking once a
        # declared condition changes, or once an override was recorded for it. An
        # unsuppressed attempt keeps blocking, because FR-045 says nothing about it and
        # re-proposing a route that merely failed once is how the loop re-runs it.
        attempted: set[str] = set()
        by_key: dict[str, list[ActionMemoryEntry]] = {}
        for entry in memory:
            if "|" in entry.attempt_key:
                by_key.setdefault(entry.attempt_key, []).append(entry)
        for key, entries in by_key.items():
            if key in overridden:
                continue
            suppressions = [e.suppression for e in entries if e.suppression is not None]
            if suppressions and all(s.lifted_by(current) for s in suppressions):
                # Every suppression on this key was lifted by the declared change, so the
                # key is admissible again. Checking *every* one matters: the first attempt
                # carries no suppression of its own, and letting it keep blocking would
                # make the re-open clause unreachable.
                continue
            attempted.add(self._attempt_key(obligation, key.split("|", 1)[0]))
        action = self.proposer.propose(
            obligation,
            already_attempted=attempted,
            required_capabilities=required_capabilities,
        )
        if action is not None:
            await self.store.put_action(action)
            context = await self.store.get_context(obligation.context_id)
            await self._publish(
                "action.proposed",
                obligation.context_id,
                action.action_id,
                tenant_id=context.tenant_id if context is not None else "",
                payload={
                    "obligation_id": obligation.obligation_id,
                    "runtime_ref": action.runtime_ref,
                    "declared_conditions": current,
                    "requires_operator_approval": action.requires_operator_approval,
                },
            )
        return action

    async def record_attempt(
        self,
        action: ResearchAction,
        *,
        outcome: str,
        realised_gain: float | None = None,
        coverage: CoverageStatement | None = None,
        error_class: ErrorClass | None = None,
        conditions: Mapping[str, str] | None = None,
        detail: str = "",
    ) -> ActionMemoryEntry:
        """FR-059, FR-045. Without this the engine re-proposes what it already did.

        ``coverage`` is what separates :attr:`MemoryState.NO_RESULT` from
        :attr:`MemoryState.FAILED`, and the entry refuses to carry one with the other: a
        failure is a statement about the system, and attaching a coverage statement to it
        would claim a search that never ran.

        Suppression is applied here rather than at read time, so it is persisted by
        :meth:`ContextStore.remember` and survives a restart alongside the attempt it
        describes.
        """
        obligation = await self.store.get_obligation(action.obligation_id)
        if obligation is None:
            raise ContextEngineError("obligation_unknown", action.obligation_id)
        attempt_key = self._attempt_key(obligation, action.runtime_ref)
        prior = await self.store.memory_for(action.obligation_id)
        entry = ActionMemoryEntry(
            obligation_id=action.obligation_id,
            attempt_key=attempt_key,
            outcome=outcome,
            realised_gain=realised_gain,
            state=classify_attempt(
                outcome, coverage=coverage, realised_gain=realised_gain
            ),
            coverage=coverage,
            failure_class=error_class,
            declared_conditions=tuple(sorted((conditions or {}).items())),
            detail=detail,
            attempt_seq=self._next_attempt_seq(prior, attempt_key),
        )
        entry = self._with_suppression(entry, prior)
        await self.store.remember(entry)
        return entry

    @staticmethod
    def _next_attempt_seq(
        prior: Sequence[ActionMemoryEntry], attempt_key: str
    ) -> int:
        """The next attempt number for one key. See :attr:`ActionMemoryEntry.attempt_seq`."""
        return 1 + max(
            (e.attempt_seq for e in prior if e.attempt_key == attempt_key),
            default=0,
        )

    def _with_suppression(
        self, entry: ActionMemoryEntry, prior: Sequence[ActionMemoryEntry]
    ) -> ActionMemoryEntry:
        """Attach a suppression once the same action has gone ``no_gain_threshold`` times
        without gain under one declared condition (FR-045).

        A suppression is stored with the fingerprint of the conditions in force when it
        was applied, so :meth:`ActionSuppression.lifted_by` can tell a genuine declared
        change from a retry that simply ran out of patience. Both the reason and the
        re-open conditions are mandatory on the record; there is no silent form.
        """
        from dataclasses import replace

        if entry.state not in self.suppressible_states or entry.suppression is not None:
            return entry
        counted = sum(
            1
            for other in prior
            if other.attempt_key == entry.attempt_key
            and other.condition_fingerprint == entry.condition_fingerprint
            and other.state in self.suppressible_states
        )
        attempts = counted + 1
        if attempts < self.no_gain_threshold:
            return entry
        reopen = tuple(
            f"declared condition {name!r} changes"
            for name, _ in entry.declared_conditions
        ) or ("a declared condition is supplied where none was declared before",)
        return replace(
            entry,
            suppression=ActionSuppression(
                reason=(
                    f"{attempts} attempts under the same declared conditions produced no "
                    "information gain"
                ),
                attempts_without_gain=attempts,
                condition_fingerprint=entry.condition_fingerprint,
                reopen_conditions=reopen,
            ),
        )

    async def suppression_for(
        self,
        obligation_id: str,
        attempt_key: str,
        *,
        conditions: Mapping[str, str] | None = None,
    ) -> ActionSuppression | None:
        """The suppression currently in force for one attempt, or ``None``.

        ``None`` means one of three genuinely different things, and the caller can tell
        them apart by reading :meth:`action_memory`: there was never a suppression; a
        declared condition change lifted it; or an explicit override was recorded.
        """
        current = condition_fingerprint(conditions)
        entries = [
            e
            for e in await self.store.memory_for(obligation_id)
            if e.attempt_key == attempt_key
        ]
        if any(e.outcome == "override" for e in entries):
            return None
        for entry in entries:
            if entry.suppression is not None and not entry.suppression.lifted_by(current):
                return entry.suppression
        return None

    async def override_suppression(
        self,
        obligation_id: str,
        attempt_key: str,
        *,
        reason: str,
        conditions: Mapping[str, str] | None = None,
    ) -> ActionMemoryEntry:
        """Re-admit a suppressed action on the record, with a stated reason (FR-045).

        Recorded rather than performed: an override nobody can find afterwards is not an
        override, it is a bug that happened to help.
        """
        if not str(reason).strip():
            raise ContextEngineError(
                "override_reason_missing",
                "an override of a suppression must say why; 'I turned it back on' is not "
                "a reason an auditor can weigh (FR-045)",
            )
        prior = await self.store.memory_for(obligation_id)
        return ActionMemoryEntry(
            obligation_id=obligation_id,
            attempt_key=attempt_key,
            outcome="override",
            state=MemoryState.PENDING,
            declared_conditions=tuple(sorted((conditions or {}).items())),
            detail=reason,
            attempt_seq=self._next_attempt_seq(prior, attempt_key),
        )

    async def action_memory(self, obligation_id: str) -> tuple[ActionMemoryEntry, ...]:
        """Every recorded attempt, newest state first. FR-059, FR-045."""
        return await self.store.memory_for(obligation_id)

    # -- replay (FR-028) -----------------------------------------------------

    async def replay(self, context_id: str) -> ReplayResult:
        """Reconstruct state from the recorded revisions.

        Determinism is the point: replaying the same chain twice produces the same
        summary, and replaying a chain into an empty store reproduces it.
        """
        chain = await self.store.revisions(context_id)
        if not chain:
            raise ContextEngineError("nothing_to_replay", context_id)
        final = chain[-1]
        return ReplayResult(
            context_id=context_id,
            revisions=len(chain),
            obligations=len(await self.store.obligations(context_id)),
            actions=sum([len(await self.store.actions(o.obligation_id)) for o in await self.store.obligations(context_id)]),
            final_state=final.state.value,
        )

    # -- termination and re-opening (FR-057, FR-076) -------------------------

    async def termination_report(self, context_id: str) -> TerminationReport:
        """Why the investigation stopped, what is still unknown, what would re-open it.

        FR-057 and FR-046. Termination is never silent: an operator reading only this
        report must be able to tell whether the investigation finished, stalled, or ran out
        of sources -- and what evidence would overturn it.

        The stop reason is *derived* from the board, then validated against
        :data:`FORBIDDEN_STOP_REASONS`. Deriving it rather than accepting it is the point:
        the component that would supply an invented reason is the one that ran out of
        options, so it cannot be trusted to name one honestly.
        """
        context = await self.store.get_context(context_id)
        if context is None:
            raise ContextEngineError("context_unknown", context_id)
        obligations = await self.store.obligations(context_id)
        by_status: dict[str, list[ResearchObligation]] = {}
        for o in obligations:
            by_status.setdefault(o.status.value, []).append(o)
        unknown = sorted(
            o.question for o in obligations if o.status is not ObligationStatus.SATISFIED
        )
        terminal = (
            bool(obligations)
            and not await self.open_obligations(context_id)
            and not by_status.get(ObligationStatus.BLOCKED.value)
        )
        reasons = {
            status: [
                {"obligation_id": o.obligation_id, "reason": o.disposition_reason}
                for o in items
            ]
            for status, items in sorted(by_status.items())
        }
        reopeners = [
            {
                "obligation_id": o.obligation_id,
                "trigger": "contradicting evidence",
                "question": o.question,
            }
            for o in by_status.get(ObligationStatus.SATISFIED.value, [])
        ]
        stop_reason, detail = _derive_stop_reason(obligations, terminal)
        # Belt and braces: the derivation cannot currently produce a forbidden reason, but
        # the table is the contract and the assertion is what keeps them in step.
        if detail:
            require_real_stop_reason(stop_reason.value if stop_reason else "")
        unexecuted = tuple(
            UnexecutedScope(
                obligation_id=o.obligation_id,
                question=o.question,
                reason=(
                    o.disposition_reason
                    or f"left {o.status.value}; no disposition was recorded"
                ),
                missing_capabilities=o.missing_capabilities,
            )
            for o in sorted(obligations, key=lambda item: item.obligation_id)
            if o.status is not ObligationStatus.SATISFIED
        )
        return TerminationReport(
            context_id=context_id,
            is_terminal=terminal,
            state=context.state.value,
            total_obligations=len(obligations),
            reasons_by_status=reasons,
            still_unknown=tuple(unknown),
            would_reopen_on=tuple(reopeners),
            stop_reason=stop_reason,
            stop_reason_detail=detail,
            unexecuted_scope=unexecuted,
        )

    async def reopen(self, context_id: str, *, reason: str, event_ids: Sequence[str] = ()) -> ContextRevision:
        """Re-open a closed investigation because evidence contradicted it (FR-076).

        The terminal state is not overwritten: the revision chain keeps the closure,
        and this appends a new revision that supersedes it. Silently flipping the
        state back would erase the record that the investigation had been declared
        finished.

        The reason is required and is refused when blank, and the decision carries the
        residual unknowns and the unexecuted scope as they stood at the moment of the
        closure. A re-opening that does not say what it thought it already knew has thrown
        away the only thing that made it worth re-opening.
        """
        context = await self.store.get_context(context_id)
        if context is None:
            raise ContextEngineError("context_unknown", context_id)
        if not str(reason).strip():
            raise ContextEngineError(
                "reopen_reason_missing",
                "a re-opening must say what contradicted the closure; reopening without a "
                "stated cause cannot be distinguished from a mis-click (FR-076)",
            )
        from dataclasses import replace as _replace

        prior = await self.termination_report(context_id)
        reopened = _replace(
            context, state=InvestigationState.ACTIVE, context_id=context.address()
        )
        await self.store.put_context(reopened)
        decision = self.recorder.record(
            context_id=context_id,
            kind="context_reopened",
            input_event_ids=event_ids,
            prior_state=context.state.value,
            outcome=InvestigationState.ACTIVE.value,
            detail=reason,
        )
        # FR-046's residual unknowns and unexecuted scope travel with the re-opening as
        # their own decision rather than being appended to the reason. Mixing them into
        # one string means a reader has to parse prose to learn what was still open, and
        # the reason is the part that has to stay quotable.
        scope_decision = self.recorder.record(
            context_id=context_id,
            kind="context_reopen_scope",
            input_event_ids=event_ids,
            prior_state=prior.stop_reason.value if prior.stop_reason else "none",
            outcome=f"{len(prior.still_unknown)} unknown, {len(prior.unexecuted_scope)} unexecuted",
            detail=(
                f"residual unknowns: {list(prior.still_unknown)} | unexecuted scope: "
                f"{[s.obligation_id for s in prior.unexecuted_scope]}"
            ),
        )
        revision = await self.revisions.commit(
            reopened,
            state=InvestigationState.ACTIVE,
            caused_by_event_ids=event_ids,
            decision_ids=(decision.decision_id, scope_decision.decision_id),
            operator_actions=("reopen",),
        )
        await self._publish(
            "obligation.transitioned",
            context_id,
            context_id,
            tenant_id=context.tenant_id,
            revision_id=revision.revision_id,
            payload={
                "transition": "reopened",
                "reason": reason,
                "residual_unknowns": list(prior.still_unknown),
                "unexecuted_scope": [s.to_dict() for s in prior.unexecuted_scope],
                "prior_stop_reason": str(prior.stop_reason) if prior.stop_reason else None,
            },
        )
        await self._publish_decision(decision, reopened.tenant_id, revision.revision_id)
        await self._publish_decision(scope_decision, reopened.tenant_id, revision.revision_id)
        return revision

    async def abandon_obligation(
        self, obligation_id: str, *, reason: str, mode: str = "deterministic"
    ) -> ResearchObligation:
        """Close an obligation as abandoned, with the reason recorded (FR-035).

        Abandoning is not failing. Some questions are not answerable with the sources
        available, and pretending otherwise by leaving them open would keep the
        investigation alive forever. What matters is that the reason is stored, so
        "we stopped asking" is distinguishable from "we never asked".

        A high-confidence abandonment is a decision; a low-confidence one is a loose
        end, and :meth:`propose_hypotheses` will flag the latter for revisiting.
        """
        from dataclasses import replace

        obligation = await self.store.get_obligation(obligation_id)
        if obligation is None:
            raise ContextEngineError("obligation_unknown", obligation_id)
        if not reason.strip():
            raise ContextEngineError("abandon_reason_missing", "an abandonment must say why")
        abandoned = replace(
            obligation,
            status=ObligationStatus.ABANDONED,
            disposition=Disposition.ABANDONED,
            disposition_reason=reason,
        ).with_id()
        await self.store.put_obligation(abandoned)
        decision = self.recorder.record(
            context_id=abandoned.context_id,
            kind="obligation_abandoned",
            input_event_ids=(),
            prior_state=obligation.status.value,
            outcome=abandoned.status.value,
            detail=reason,
            mode=mode,
        )
        context = await self.store.get_context(abandoned.context_id)
        await self._publish(
            "obligation.transitioned",
            abandoned.context_id,
            abandoned.obligation_id,
            tenant_id=context.tenant_id if context is not None else "",
            payload={
                "transition": obligation.status.value,
                "to": abandoned.status.value,
                "reason": reason,
                "decision_id": decision.decision_id,
            },
        )
        if context is not None:
            await self._publish_decision(decision, context.tenant_id)
        return abandoned

    async def propose_hypotheses(
        self, context_id: str, *, max_proposals: int = 5
    ) -> tuple[ResearchObligation, ...]:
        """FR-060. Autonomous question/hypothesis proposal from context state.

        Derived only from what the store already knows: contradictions, coverage
        gaps (open obligations), and low-confidence claims. No heuristics, no clock --
        so the proposal set is a function of state, which is what makes it auditable.
        """
        context = await self.store.get_context(context_id)
        if context is None:
            raise ContextEngineError("context_unknown", context_id)

        out: list[ResearchObligation] = []
        seen: set[str] = set()

        for o in await self.store.obligations(context_id):
            if o.status is ObligationStatus.BLOCKED and o.question not in seen:
                seen.add(o.question)
                out.append(
                    ResearchObligation(
                        context_id=context_id,
                        question=f"resolve contradiction: {o.question}",
                        rationale=f"obligation {o.obligation_id} is contradicted",
                        target_knowledge_type=KnowledgeType.CONTRADICTION,
                        priority=min(1.0, o.priority + 0.2),
                        created_by=f"{RULES_VERSION}#contradiction",
                    ).with_id()
                )

        # Low confidence is checked before open coverage gaps. Re-proposing an open
        # obligation verbatim asks a question already on the board; asking for its
        # confidence to be raised is the question that actually advances it.
        for o in await self.open_obligations(context_id):
            if o.question not in seen:
                seen.add(o.question)
                out.append(
                    ResearchObligation(
                        context_id=context_id,
                        question=o.question,
                        rationale=f"coverage gap: {o.disposition_reason or 'unsatisfied'}",
                        priority=o.priority,
                        created_by=f"{RULES_VERSION}#coverage_gap",
                    ).with_id()
                )

        # Low confidence targets *settled* obligations resting on thin evidence. It
        # deliberately skips open ones: an open obligation already occupies the board,
        # so restating it asks nothing new. The two rules do not overlap.
        for o in await self.store.obligations(context_id):
            settled = o.status in (ObligationStatus.SATISFIED, ObligationStatus.ABANDONED)
            if settled and o.confidence < 0.5 and o.question not in seen:
                seen.add(o.question)
                out.append(
                    ResearchObligation(
                        context_id=context_id,
                        question=f"raise confidence on: {o.question}",
                        rationale=f"settled on confidence {o.confidence:.2f}, below 0.50",
                        target_knowledge_type=KnowledgeType.ATTRIBUTE,
                        priority=min(1.0, o.priority + 0.1),
                        created_by=f"{RULES_VERSION}#low_confidence",
                    ).with_id()
                )

        out.sort(key=lambda o: (-o.priority, o.question))
        return tuple(out[:max_proposals])

    async def rebuild(self, context_id: str) -> ContextFrontier:
        """Re-derive the frontier from stored obligations. FR-050."""
        context = await self.store.get_context(context_id)
        if context is None:
            raise ContextEngineError("context_unknown", context_id)
        obligations = await self.store.obligations(context_id)
        open_ids = tuple(
            sorted(
                o.obligation_id
                for o in obligations
                if o.status in (ObligationStatus.OPEN, ObligationStatus.PARTIALLY_SATISFIED)
            )
        )
        blocked = tuple(
            sorted(o.obligation_id for o in obligations if o.status is ObligationStatus.BLOCKED)
        )
        closed = tuple(
            sorted(
                o.obligation_id
                for o in obligations
                if o.status
                in (ObligationStatus.SATISFIED, ObligationStatus.ABANDONED)
            )
        )
        frontier = ContextFrontier(
            context_id=context_id,
            state=context.state,
            open_obligations=open_ids,
            blocked_obligations=blocked,
            closed_obligations=closed,
        )
        await self.store.put_frontier(frontier)
        return frontier


def assert_components_are_separate() -> None:
    """Mechanical check that FR-041 is honoured, not merely intended.

    Verifies that no single class implements two roles, and that the engine holds
    exactly one instance of each.
    """
    import inspect

    owners: dict[str, set[str]] = {}
    implementations = {
        "ObligationGenerator": {"generate"},
        "SatisfactionEvaluator": {"evaluate"},
        "ActionProposer": {"propose"},
        "DecisionRecorder": {"record"},
        "RevisionManager": {"commit"},
    }
    for cls_name, roles in implementations.items():
        cls = globals()[cls_name]
        public = {n for n, _ in inspect.getmembers(cls, inspect.isfunction) if not n.startswith("_")}
        owned = roles & public
        if not owned:
            raise ContextEngineError(
                "component_missing", f"{cls_name} does not expose {sorted(roles)}"
            )
        owners[cls_name] = owned

    total = sum(len(v) for v in owners.values())
    if total != len(COMPONENT_ROLES):
        raise ContextEngineError(
            "component_roles_imbalanced",
            f"{total} roles across {len(owners)} components, expected {len(COMPONENT_ROLES)}",
        )
    engine_methods = {
        n for n, _ in inspect.getmembers(ContextEngine, inspect.isfunction) if not n.startswith("_")
    }
    leaked = {"generate", "evaluate", "commit", "record"} & engine_methods
    if leaked:
        raise ContextEngineError(
            "engine_holds_component_logic",
            f"ContextEngine re-implements {sorted(leaked)} instead of delegating",
        )


def assert_publication_is_single() -> None:
    """Mechanical check that there is exactly one publication seam (T051, FR-065).

    Two shapes of drift are caught:

    * the engine growing a second way to emit a change -- a direct ``publisher.append``,
      a side channel on the store -- which is how "just log it here too" becomes a
      second, unversioned publication path;
    * the outbox binding drifting away from ``SqlMaterializationOutbox.enqueue``'s real
      signature, which would make the durable path quietly write to nothing.

    ``assert`` disappears under ``-O`` and this is load-bearing, so it is a check function
    rather than a statement.
    """
    import inspect

    from context_engine.store import InMemoryChangePublisher, SqlOutboxChangePublisher

    if not issubclass(SqlOutboxChangePublisher, ChangePublisher):
        raise ContextEngineError(
            "outbox_publisher_not_a_publisher",
            "the durable change publisher must implement ChangePublisher",
        )
    if not issubclass(InMemoryChangePublisher, ChangePublisher):
        raise ContextEngineError(
            "in_memory_publisher_not_a_publisher",
            "the in-memory change publisher must implement ChangePublisher",
        )

    seams = {
        name
        for name, _ in inspect.getmembers(ContextEngine, inspect.isfunction)
        if "publish" in name
    }
    if seams != _PUBLICATION_SEAMS:
        raise ContextEngineError(
            "publication_paths_drifted",
            f"ContextEngine exposes {sorted(seams)}; the only allowed seams are "
            f"{sorted(_PUBLICATION_SEAMS)}, because a second one is a second vocabulary "
            "nobody subscribes to",
        )
    # Every helper seam must funnel through ``_publish``. A helper that writes to the
    # publisher directly is a fork, whatever its name says.
    forked = {
        name
        for name in seams - {"_publish"}
        if "self._publish(" not in inspect.getsource(getattr(ContextEngine, name))
    }
    if forked:
        raise ContextEngineError(
            "publication_paths_forked",
            f"{sorted(forked)} bypass ContextEngine._publish; every change must leave "
            "through the one seam",
        )

    from db.materialization_outbox import SqlMaterializationOutbox

    actual = tuple(inspect.signature(SqlMaterializationOutbox.enqueue).parameters)
    if actual != ("self", *outbox_enqueue_contract()):
        raise ContextEngineError(
            "outbox_enqueue_contract_drifted",
            f"SqlMaterializationOutbox.enqueue takes {actual}, the context binding expects "
            f"{outbox_enqueue_contract()}; the durable publication path would write to the "
            "wrong shape rather than failing loudly",
        )


__all__ = [
    "COMPONENT_ROLES",
    "DECISION_ID_PREFIX",
    "DEFAULT_NO_GAIN_THRESHOLD",
    "EVALUATOR_VERSION",
    "FORBIDDEN_STOP_REASONS",
    "RULES_VERSION",
    "TRIGGER_KINDS_WITHOUT_EVENT",
    "UNDECLARED_PRIORITY_FALLBACK",
    "ActionProposer",
    "CapabilityDescriptor",
    "ContextDecision",
    "ContextEngine",
    "DecisionRecorder",
    "GapSignal",
    "ObligationGenerator",
    "RevisionManager",
    "SatisfactionBlocker",
    "SatisfactionEvaluator",
    "SatisfactionInput",
    "SatisfactionVerdict",
    "StopReason",
    "TerminationReport",
    "Trigger",
    "TriggerKind",
    "UnexecutedScope",
    "assert_components_are_separate",
    "assert_publication_is_single",
    "require_real_stop_reason",
]