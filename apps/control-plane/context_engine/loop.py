"""The cognitive loop: context drives work, results feed back into context (Feature 024 Phase 13).

This is the feature's namesake deliverable. Everything before it exists to make this
one function honest:

```
Context -> obligations -> actions -> observations
        -> worldline -> science -> context (obligations, priorities, confidence)
```

Three properties it must have, and which the pieces alone do not guarantee:

1. **It runs whenever there is unresolved work**, and stops only on saturation, closure
   or suspension -- not because a run happened to end (FR-051, input.md §11.3).
2. **Science is not an epilogue.** Every science outcome must be able to change the next
   context revision: a refuted claim must produce an obligation, not a footnote.
3. **The operator stays in control.** The loop proposes; approval gates execution
   (FR-045, input.md §11.4).

Reused, not rewritten: the Context Engine components, ``research_lineage`` for the
intent-to-outcome chain, and the science anchoring contract. This module adds only the
closure between them.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from domain.investigation_context import (
    ContextRevision,
    InvestigationContext,
    InvestigationState,
)

from context_engine.engine import (
    ContextEngine,
    GapSignal,
    SatisfactionInput,
    TriggerKind,
)
from context_engine.obligations import KnowledgeType, SaturationState


class LoopStatus(enum.StrEnum):
    """Why the loop stopped. Never implicit."""

    CONTINUE = "continue"
    SATURATED = "saturated"
    CLOSED = "closed"
    SUSPENDED = "suspended"
    BLOCKED = "blocked"


class ScienceOutcome(enum.StrEnum):
    """What science said, translated into something the context can act on."""

    SUPPORTED = "supported"
    REFUTED = "refuted"
    DRIFTED = "drifted"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class ObservationOutcome:
    """What a completed action actually produced.

    ``produced_observations`` is the loop's only evidence of progress. An action that
    ran and produced nothing must not look like an action that produced something --
    that distinction is what keeps saturation honest.
    """

    action_id: str
    task_id: str
    produced_observations: tuple[str, ...] = ()
    contradicting: tuple[str, ...] = ()
    coverage_delta: float = 0.0
    marginal_gain: float = 0.0

    @property
    def produced_nothing(self) -> bool:
        return not self.produced_observations

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "task_id": self.task_id,
            "produced_observations": list(self.produced_observations),
            "contradicting": list(self.contradicting),
            "coverage_delta": self.coverage_delta,
            "marginal_gain": self.marginal_gain,
        }


@dataclass(frozen=True, slots=True)
class ScienceFeedback:
    """A science result, expressed as a context signal."""

    outcome: ScienceOutcome
    claim_ref: str
    detail: str = ""
    snapshot_id: str = ""
    method_fingerprint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome", ScienceOutcome(self.outcome))

    def to_signals(self, context_id: str) -> tuple[GapSignal, ...]:
        """Translate science into obligations the context engine can generate from.

        Refutation and drift become contradictions -- real questions the investigation
        now has to answer. Support produces no signal: there is nothing left to ask,
        and inventing a signal for a settled question is how a loop spins forever.
        """
        if self.outcome is ScienceOutcome.REFUTED:
            return (
                GapSignal(
                    kind=TriggerKind.CONTRADICTION,
                    question=f"explain refutation of {self.claim_ref}: {self.detail or 'claim refuted'}",
                    rationale=(
                        f"science refuted {self.claim_ref} "
                        f"[snapshot={self.snapshot_id} method={self.method_fingerprint}]"
                    ),
                    knowledge_type=KnowledgeType.CONTRADICTION,
                    priority=0.9,
                ),
            )
        if self.outcome is ScienceOutcome.DRIFTED:
            return (
                GapSignal(
                    kind=TriggerKind.ANOMALY,
                    question=f"explain calibration drift on {self.claim_ref}",
                    rationale=f"drift beyond tolerance [{self.snapshot_id}]",
                    knowledge_type=KnowledgeType.ATTRIBUTE,
                    priority=0.7,
                ),
            )
        return ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "claim_ref": self.claim_ref,
            "detail": self.detail,
            "snapshot_id": self.snapshot_id,
            "method_fingerprint": self.method_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class LoopStep:
    """One pass, fully accounted for."""

    status: LoopStatus
    revision: ContextRevision | None
    obligations_created: tuple[str, ...] = ()
    actions_proposed: tuple[str, ...] = ()
    awaiting_approval: tuple[str, ...] = ()
    evaluated: tuple[str, ...] = ()
    feedback_signals: int = 0
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "revision": self.revision.revision_id if self.revision else "",
            "obligations_created": list(self.obligations_created),
            "actions_proposed": list(self.actions_proposed),
            "awaiting_approval": list(self.awaiting_approval),
            "evaluated": list(self.evaluated),
            "feedback_signals": self.feedback_signals,
            "note": self.note,
        }


class ObservationSource(Protocol):
    """Where real observations come from. Injected; never faked by the loop."""

    def observe(self, *, task_id: str, context_id: str) -> tuple[str, ...]: ...


class CognitiveLoop:
    """Closes the cycle. Proposes work, records outcomes, folds results back in."""

    def __init__(
        self,
        engine: ContextEngine,
        *,
        sources: Mapping[str, ObservationSource] | None = None,
        max_steps_per_tick: int = 8,
        coverage_threshold: float = 0.9,
        marginal_gain_threshold: float = 0.05,
    ) -> None:
        self.engine = engine
        self._sources: dict[str, ObservationSource] = dict(sources or {})
        self.max_steps_per_tick = max_steps_per_tick
        self.coverage_threshold = coverage_threshold
        self.marginal_gain_threshold = marginal_gain_threshold

    # -- the tick ------------------------------------------------------------

    def tick(
        self,
        context: InvestigationContext,
        *,
        feedback: Sequence[ScienceFeedback] = (),
        saturation: SaturationState | None = None,
        outcomes: Sequence[ObservationOutcome] = (),
        event_ids: Sequence[str] = (),
        approved_action_ids: Sequence[str] = (),
        mode: str = "deterministic",
    ) -> LoopStep:
        """One pass. Returns everything it did, and why it stopped."""
        self.engine.store.put_context(context)

        halt = self._terminal_status(context)
        if halt is not LoopStatus.CONTINUE:
            return LoopStep(status=halt, revision=None, note=_halt_reason(halt, context))

        # 1. Science outcomes become questions. This runs before obligation generation
        #    so a refutation is answered in the same pass that produced it.
        signals = self._feedback_signals(feedback)

        # 2. Fold in what real actions produced.
        signals = self._outcome_signals(context, outcomes, signals)

        # Captured before ingest: an obligation created *from* this tick's signals must
        # not be evaluated against them. A contradiction must not immediately block the
        # question it just raised -- that would have the loop contradict itself inside a
        # single pass and strand the question forever.
        pre_existing = {o.obligation_id for o in self.engine.open_obligations(context.context_id)}

        revision, created = self.engine.ingest(
            context, signals, event_ids=event_ids, mode=mode
        )

        # 3. Re-evaluate obligations whose saturation moved.
        evaluated = self._reevaluate(context, saturation, outcomes, pre_existing)

        # 4. Propose the next work, gated on approval.
        proposed, pending = self._propose(context, approved_action_ids)

        return LoopStep(
            status=self._status_after(context),
            revision=revision,
            obligations_created=tuple(o.obligation_id for o in created),
            actions_proposed=proposed,
            awaiting_approval=pending,
            evaluated=evaluated,
            feedback_signals=len(signals),
        )

    # -- helpers -------------------------------------------------------------

    def _terminal_status(self, context: InvestigationContext) -> LoopStatus:
        if context.state is InvestigationState.SUSPENDED:
            return LoopStatus.SUSPENDED
        if context.state is InvestigationState.CLOSED:
            return LoopStatus.CLOSED
        return LoopStatus.CONTINUE

    def _status_after(self, context: InvestigationContext) -> LoopStatus:
        report = self.engine.termination_report(context.context_id)
        if report.is_terminal:
            return LoopStatus.SATURATED
        open_ids = self.engine.open_obligations(context.context_id)
        if open_ids and not any(self.engine.store.actions(o.obligation_id) for o in open_ids):
            return LoopStatus.BLOCKED
        return LoopStatus.CONTINUE

    def _feedback_signals(self, feedback: Sequence[ScienceFeedback]) -> list[GapSignal]:
        out: list[GapSignal] = []
        for item in feedback:
            out.extend(item.to_signals(""))
        return out

    def _outcome_signals(
        self,
        context: InvestigationContext,
        outcomes: Sequence[ObservationOutcome],
        signals: list[GapSignal],
    ) -> list[GapSignal]:
        """Contradictions from real observations become questions (FR-038)."""
        for outcome in outcomes:
            for ref in outcome.contradicting:
                signals.append(
                    GapSignal(
                        kind=TriggerKind.CONTRADICTION,
                        question=f"explain contradiction on {ref}",
                        rationale=f"observation {ref} contradicts an existing claim",
                        knowledge_type=KnowledgeType.CONTRADICTION,
                        priority=0.85,
                        evidence_refs=tuple(outcome.produced_observations),
                    )
                )
        return signals

    def _reevaluate(
        self,
        context: InvestigationContext,
        saturation: SaturationState | None,
        outcomes: Sequence[ObservationOutcome],
        pre_existing: frozenset[str] | set[str] = frozenset(),
    ) -> tuple[str, ...]:
        if saturation is None and not outcomes:
            return ()
        touched: list[str] = []
        for obligation in self.engine.open_obligations(context.context_id):
            if obligation.obligation_id not in pre_existing:
                continue
            related = [o for o in outcomes if not o.produced_nothing]
            evidence = sum(len(o.produced_observations) for o in related)
            contradicting = sum(len(o.contradicting) for o in related)
            if evidence == 0 and contradicting == 0:
                continue
            data = SatisfactionInput(
                evidence_count=evidence,
                saturation=saturation
                or SaturationState(
                    coverage=obligation.saturation.coverage if obligation.saturation else 0.0,
                    marginal_gain=obligation.saturation.marginal_gain
                    if obligation.saturation
                    else 1.0,
                    distinct_sources=0,
                    source_diversity=0,
                    coverage_threshold=self.coverage_threshold,
                    marginal_gain_threshold=self.marginal_gain_threshold,
                ),
                contradicting_evidence=contradicting,
            )
            self.engine.evaluate_obligation(obligation.obligation_id, data)
            touched.append(obligation.obligation_id)
        return tuple(sorted(touched))

    def _propose(
        self, context: InvestigationContext, approved_action_ids: Sequence[str]
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        approved = set(approved_action_ids)
        proposed: list[str] = []
        pending: list[str] = []
        for obligation in self.engine.open_obligations(context.context_id):
            if approved:
                actions = self.engine.store.actions(obligation.obligation_id)
                for action in actions:
                    if action.action_id in approved:
                        self.engine.record_attempt(
                            action,
                            outcome="approved",
                            realised_gain=action.expected_information_gain,
                        )
                        proposed.append(action.action_id)
            action = self.engine.propose_action(obligation.obligation_id)
            if action is None:
                continue
            if action.requires_operator_approval and action.action_id not in approved:
                pending.append(action.action_id)
            proposed.append(action.action_id)
        return tuple(sorted(set(proposed))), tuple(sorted(set(pending)))


def _halt_reason(status: LoopStatus, context: InvestigationContext) -> str:
    if status is LoopStatus.SUSPENDED:
        return "investigation is suspended by the operator"
    return "investigation is closed"


__all__ = [
    "CognitiveLoop",
    "LoopStatus",
    "LoopStep",
    "ObservationOutcome",
    "ObservationSource",
    "ScienceFeedback",
    "ScienceOutcome",
]