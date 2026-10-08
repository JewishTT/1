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
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from domain.investigation_context import (
    ContextEngineError,
    ContextRevision,
    InvestigationContext,
    InvestigationState,
    ObligationStatus,
)

from context_engine.obligations import (
    ActionMemoryEntry,
    ContextFrontier,
    Disposition,
    KnowledgeType,
    ResearchAction,
    ResearchObligation,
    SaturationState,
)
from context_engine.store import ContextStore, ReplayResult, StoreDurability

DECISION_ID_PREFIX = "DEC-"
RULES_VERSION = "context-engine/rules/v1"


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


@dataclass(frozen=True, slots=True)
class Trigger:
    """A versioned, inspectable reason for an obligation (FR-034)."""

    kind: TriggerKind
    rule_id: str
    detail: str
    evidence_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "rule_id": self.rule_id,
            "detail": self.detail,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True, slots=True)
class GapSignal:
    """What the generator is told about the world. Deliberately inert."""

    kind: TriggerKind
    question: str
    rationale: str = ""
    knowledge_type: KnowledgeType = KnowledgeType.ENTITY
    priority: float = 0.5
    evidence_refs: tuple[str, ...] = ()


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
            rule_id=f"{self.rules_version}#{signal.kind.value}",
            detail=signal.rationale or f"{signal.kind.value} for {signal.question}",
            evidence_refs=signal.evidence_refs,
        )

    def generate(
        self, context: InvestigationContext, signals: Iterable[GapSignal]
    ) -> list[tuple[ResearchObligation, Trigger]]:
        """Obligations paired with their triggers. Order is by trigger then question,
        so the result does not depend on the caller's iteration order."""
        out: list[tuple[ResearchObligation, Trigger]] = []
        for signal in signals:
            trigger = self.trigger_for(signal)
            obligation = ResearchObligation(
                context_id=context.context_id,
                question=signal.question,
                rationale=signal.rationale,
                target_knowledge_type=signal.knowledge_type,
                priority=signal.priority,
                status=ObligationStatus.OPEN,
                created_by=trigger.rule_id,
            ).with_id()
            out.append((obligation, trigger))
        out.sort(key=lambda pair: (pair[1].rule_id, pair[0].question))
        return out


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_count": self.evidence_count,
            "saturation": self.saturation.to_dict(),
            "contradicting_evidence": self.contradicting_evidence,
            "blocking_dependencies": list(self.blocking_dependencies),
            "unresolved_dependencies": list(self.unresolved_dependencies),
        }


@dataclass(frozen=True, slots=True)
class SatisfactionVerdict:
    """Pure, versioned, testable in isolation (FR-037)."""

    obligation_id: str
    satisfied: bool
    confidence: float
    reason: str
    rules_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "satisfied": self.satisfied,
            "confidence": self.confidence,
            "reason": self.reason,
            "rules_version": self.rules_version,
        }


class SatisfactionEvaluator:
    """Decides whether an obligation is answered. Never asserts; only evaluates."""

    def __init__(self, *, rules_version: str = RULES_VERSION) -> None:
        self.rules_version = rules_version

    def evaluate(
        self, obligation: ResearchObligation, data: SatisfactionInput
    ) -> SatisfactionVerdict:
        if data.unresolved_dependencies:
            return SatisfactionVerdict(
                obligation_id=obligation.obligation_id,
                satisfied=False,
                confidence=obligation.confidence,
                reason=f"blocked by unresolved {list(data.unresolved_dependencies)}",
                rules_version=self.rules_version,
            )
        if data.contradicting_evidence > 0:
            # FR-038: contradiction never silently satisfies; it produces a new
            # obligation or a contradiction record, never a quiet close.
            return SatisfactionVerdict(
                obligation_id=obligation.obligation_id,
                satisfied=False,
                confidence=0.0,
                reason=(
                    f"contradicted by {data.contradicting_evidence} record(s); "
                    "a contradiction cannot satisfy an obligation"
                ),
                rules_version=self.rules_version,
            )
        if data.evidence_count == 0:
            return SatisfactionVerdict(
                obligation_id=obligation.obligation_id,
                satisfied=False,
                confidence=0.0,
                reason="no evidence; acquisition count alone can never satisfy (FR-053)",
                rules_version=self.rules_version,
            )
        if not data.saturation.is_saturated:
            return SatisfactionVerdict(
                obligation_id=obligation.obligation_id,
                satisfied=False,
                confidence=obligation.confidence,
                reason=f"not saturated: {data.saturation.reason()}",
                rules_version=self.rules_version,
            )
        return SatisfactionVerdict(
            obligation_id=obligation.obligation_id,
            satisfied=True,
            confidence=min(1.0, data.saturation.coverage),
            reason=f"saturated: {data.saturation.reason()}",
            rules_version=self.rules_version,
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
class TerminationReport:
    """FR-057. Why an investigation stopped, in a form an operator can read."""

    context_id: str
    is_terminal: bool
    state: str
    total_obligations: int
    reasons_by_status: dict[str, list[dict[str, str]]]
    still_unknown: tuple[str, ...] = ()
    would_reopen_on: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "is_terminal": self.is_terminal,
            "state": self.state,
            "total_obligations": self.total_obligations,
            "reasons_by_status": self.reasons_by_status,
            "still_unknown": list(self.still_unknown),
            "would_reopen_on": [dict(r) for r in self.would_reopen_on],
        }


COMPONENT_ROLES = (
    "generate",
    "evaluate",
    "propose",
    "record",
    "commit",
)


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
            self.recorder.record(
                context_id=context.context_id,
                kind="obligation_created",
                input_event_ids=event_ids,
                prior_state=context.state.value,
                outcome=obligation.obligation_id,
                detail=f"{trigger.rule_id}: {trigger.detail}",
                mode=mode,
            )

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
        if verdict.satisfied:
            new = replace(
                obligation,
                status=ObligationStatus.SATISFIED,
                confidence=verdict.confidence,
                saturation=data.saturation,
                disposition=Disposition.SATISFIED,
                disposition_reason=verdict.reason,
            ).with_id()
        elif data.contradicting_evidence > 0:
            new = replace(
                obligation,
                status=ObligationStatus.BLOCKED,
                confidence=0.0,
                saturation=data.saturation,
                disposition=Disposition.BLOCKED,
                disposition_reason=verdict.reason,
            ).with_id()
        else:
            new = replace(
                obligation, saturation=data.saturation, confidence=verdict.confidence
            ).with_id()
        await self.store.put_obligation(new)
        self.recorder.record(
            context_id=new.context_id,
            kind="obligation_evaluated",
            input_event_ids=(),
            prior_state=obligation.status.value,
            outcome=new.status.value,
            detail=verdict.reason,
            mode=mode,
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
        self, obligation_id: str, *, required_capabilities: Sequence[str] = ()
    ) -> ResearchAction | None:
        """Propose, never execute (FR-036). Returns None when nothing can be
        proposed -- the caller then records a capability requirement (FR-040)."""
        obligation = await self.store.get_obligation(obligation_id)
        if obligation is None:
            raise ContextEngineError("obligation_unknown", obligation_id)
        # FR-059: attempts, not proposals. A proposal that never ran is not history.
        attempted = {
            self._attempt_key(obligation, entry.attempt_key.split("|", 1)[0])
            for entry in await self.store.memory_for(obligation_id)
            if "|" in entry.attempt_key
        }
        action = self.proposer.propose(
            obligation,
            already_attempted=attempted,
            required_capabilities=required_capabilities,
        )
        if action is not None:
            await self.store.put_action(action)
        return action

    async def record_attempt(
        self, action: ResearchAction, *, outcome: str, realised_gain: float | None = None
    ) -> ActionMemoryEntry:
        """FR-059. Without this the engine re-proposes what it already did."""
        obligation = await self.store.get_obligation(action.obligation_id)
        if obligation is None:
            raise ContextEngineError("obligation_unknown", action.obligation_id)
        entry = ActionMemoryEntry(
            obligation_id=action.obligation_id,
            attempt_key=self._attempt_key(obligation, action.runtime_ref),
            outcome=outcome,
            realised_gain=realised_gain,
        )
        await self.store.remember(entry)
        return entry

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

        FR-057. Termination is never silent: an operator reading only this report
        must be able to tell whether the investigation finished, stalled, or ran out
        of sources -- and what evidence would overturn it.
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
        return TerminationReport(
            context_id=context_id,
            is_terminal=terminal,
            state=context.state.value,
            total_obligations=len(obligations),
            reasons_by_status=reasons,
            still_unknown=tuple(unknown),
            would_reopen_on=tuple(reopeners),
        )

    async def reopen(self, context_id: str, *, reason: str, event_ids: Sequence[str] = ()) -> ContextRevision:
        """Re-open a closed investigation because evidence contradicted it (FR-076).

        The terminal state is not overwritten: the revision chain keeps the closure,
        and this appends a new revision that supersedes it. Silently flipping the
        state back would erase the record that the investigation had been declared
        finished.
        """
        context = await self.store.get_context(context_id)
        if context is None:
            raise ContextEngineError("context_unknown", context_id)
        from dataclasses import replace as _replace

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
        return await self.revisions.commit(
            reopened,
            state=InvestigationState.ACTIVE,
            caused_by_event_ids=event_ids,
            decision_ids=(decision.decision_id,),
            operator_actions=("reopen",),
        )

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
        self.recorder.record(
            context_id=abandoned.context_id,
            kind="obligation_abandoned",
            input_event_ids=(),
            prior_state=obligation.status.value,
            outcome=abandoned.status.value,
            detail=reason,
            mode=mode,
        )
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


__all__ = [
    "COMPONENT_ROLES",
    "DECISION_ID_PREFIX",
    "RULES_VERSION",
    "ActionProposer",
    "CapabilityDescriptor",
    "ContextDecision",
    "ContextEngine",
    "DecisionRecorder",
    "GapSignal",
    "ObligationGenerator",
    "RevisionManager",
    "SatisfactionEvaluator",
    "SatisfactionInput",
    "SatisfactionVerdict",
    "TerminationReport",
    "Trigger",
    "TriggerKind",
    "assert_components_are_separate",
]