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
from dataclasses import dataclass, field
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
from context_engine.obligations import (
    KnowledgeType,
    ResearchObligation,
    SaturationState,
)


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


def _outcome_scopes(
    outcomes: Sequence[ObservationOutcome],
) -> dict[str, tuple[str, ...]]:
    """Collect the referents each outcome established, keyed by observation id.

    Merged across outcomes rather than taken from the first one that mentions an
    observation: two actions can contribute to the same observation, and taking the first
    would silently drop the other's entities and narrow its scope.
    """
    collected: dict[str, list[str]] = {}
    for outcome in outcomes:
        for observation_id, entities in (getattr(outcome, "entities", {}) or {}).items():
            bucket = collected.setdefault(str(observation_id), [])
            for entity in entities:
                if entity and entity not in bucket:
                    bucket.append(str(entity))
    return {key: tuple(value) for key, value in collected.items()}


def _outcome_anchors(outcomes: Sequence[ObservationOutcome]) -> dict[str, str]:
    """Collect which prior observation revealed each new observation's referents."""
    anchors: dict[str, str] = {}
    for outcome in outcomes:
        for observation_id, anchor in (getattr(outcome, "revealed_by", {}) or {}).items():
            if anchor:
                anchors[str(observation_id)] = str(anchor)
    return anchors


@dataclass(frozen=True, slots=True)
class ObservationOutcome:
    """What a completed action actually produced.

    ``produced_observations`` is the loop's only evidence of progress. An action that
    ran and produced nothing must not look like an action that produced something --
    that distinction is what keeps saturation honest.

    ``entities`` and ``revealed_by`` carry the observation's *membership*: which referents
    an observation established, and which prior observation revealed them. They exist
    because an observation id alone cannot be placed. The context fabric needs to know
    which cell an observation belongs to, and §0.2 forbids inventing that membership when
    nobody established it -- so an outcome that does not say leaves the scope
    undetermined, and the fabric refuses the placement and records why. That is the
    correct outcome, and it is much cheaper than a placement attached to whatever cell
    happened to be first.

    ``revealed_by`` is what lets a genuinely new scope join the context at all: without an
    anchor to a known observation, a disjoint scope is refused with ``NO_ANCHOR``.
    """

    action_id: str
    task_id: str
    produced_observations: tuple[str, ...] = ()
    #: observation id -> the referents that observation established.
    entities: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    #: observation id -> the observation that revealed these referents.
    revealed_by: Mapping[str, str] = field(default_factory=dict)
    contradicting: tuple[str, ...] = ()
    coverage_delta: float = 0.0
    marginal_gain: float = 0.0

    @property
    def produced_nothing(self) -> bool:
        return not self.produced_observations

    def entities_for(self, observation_id: str) -> tuple[str, ...]:
        return tuple(self.entities.get(observation_id, ()))

    def anchor_for(self, observation_id: str) -> str:
        return str(self.revealed_by.get(observation_id, "") or "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "task_id": self.task_id,
            "produced_observations": list(self.produced_observations),
            "entities": {k: list(v) for k, v in sorted(self.entities.items())},
            "revealed_by": dict(sorted(self.revealed_by.items())),
            "contradicting": list(self.contradicting),
            "coverage_delta": self.coverage_delta,
            "marginal_gain": self.marginal_gain,
        }


@dataclass(frozen=True, slots=True)
class ScienceFeedback:
    """A science result, expressed as a context signal.

    Built from an anchored ``ScienceEvaluation`` (see ``apps/science/context/
    bridge.py``) rather than assembled field by field. Both the snapshot and the
    method fingerprint are required: a science verdict that cannot name the
    world position and the method that produced it is not evidence, it is an
    assertion -- and an assertion cannot close an obligation.
    """

    outcome: ScienceOutcome
    claim_ref: str
    detail: str = ""
    snapshot_id: str = ""
    method_fingerprint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome", ScienceOutcome(self.outcome))
        if not self.claim_ref:
            raise ValueError("ScienceFeedback must name the claim it speaks about")

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> ScienceFeedback:
        """Build from the science bridge's wire shape."""
        return cls(
            outcome=ScienceOutcome(payload["outcome"]),
            claim_ref=str(payload.get("claim_ref") or ""),
            detail=str(payload.get("detail") or ""),
            snapshot_id=str(payload.get("snapshot_id") or ""),
            method_fingerprint=str(payload.get("method_fingerprint") or ""),
        )

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
    """Closes the cycle. Proposes work, records outcomes, folds results back in.

    The ``fabric`` runner is injected rather than imported. The loop must remain
    testable with no database and no science layer loaded, and a hard dependency on
    either would make that impossible -- the same reason ``ObservationSource`` is a
    Protocol. When no runner is supplied the tick behaves exactly as it did before
    the fabric existed, which is what keeps the 104 existing context tests honest.
    """

    def __init__(
        self,
        engine: ContextEngine,
        *,
        sources: Mapping[str, ObservationSource] | None = None,
        max_steps_per_tick: int = 8,
        coverage_threshold: float = 0.9,
        marginal_gain_threshold: float = 0.05,
        fabric: Any | None = None,
    ) -> None:
        self.engine = engine
        self._sources: dict[str, ObservationSource] = dict(sources or {})
        self.max_steps_per_tick = max_steps_per_tick
        self.coverage_threshold = coverage_threshold
        self.marginal_gain_threshold = marginal_gain_threshold
        self.fabric = fabric
        #: The last pass's report, so a caller can inspect what the fabric concluded
        #: without re-running it. Not persisted here; the durable runner does that.
        self.last_fabric_report: Any | None = None
        #: The last pass's saturation verdict, already translated into the engine's
        #: vocabulary. Reset at the top of every tick: a stale verdict from a previous
        #: pass would decide this pass's obligations, and a loop that consults its own
        #: memory rather than the current evidence is precisely the failure mode this
        #: field exists to prevent.
        self._fabric_saturation: SaturationState | None = None
        #: obligation id -> the basis it was re-evaluated on, so the stop reason can
        #: report what was actually measured rather than a summary it invented.
        self._evaluated_bases: dict[str, SaturationState] = {}

    # -- the tick ------------------------------------------------------------

    async def tick(
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
        await self.engine.store.put_context(context)
        # Reset before anything can read it. See ``_fabric_saturation``.
        self._fabric_saturation = None
        self._evaluated_bases = {}

        halt = self._terminal_status(context)
        if halt is not LoopStatus.CONTINUE:
            return LoopStep(status=halt, revision=None, note=_halt_reason(halt, context))

        # 1. Science outcomes become questions. This runs before obligation generation
        #    so a refutation is answered in the same pass that produced it.
        signals = self._feedback_signals(feedback)

        # 2. Fold in what real actions produced.
        signals = self._outcome_signals(context, outcomes, signals)

        # 2b. The fabric pass. Runs after the outcome signals so the fabric sees the
        #     same evidence they describe, and before obligation generation so a
        #     contradiction it finds is answered in the same tick rather than the next.
        #     Signals are merged in priority order rather than appended, because the
        #     generator consumes them in order and a contradiction filed behind a
        #     coverage question is one nobody reaches this pass.
        if self.fabric is not None:
            fabric_signals = await self._fabric_signals(context, outcomes)
            signals = self._merge(signals, fabric_signals)

        # Captured before ingest: an obligation created *from* this tick's signals must
        # not be evaluated against them. A contradiction must not immediately block the
        # question it just raised -- that would have the loop contradict itself inside a
        # single pass and strand the question forever.
        pre_existing = {o.obligation_id for o in await self.engine.open_obligations(context.context_id)}

        revision, created = await self.engine.ingest(
            context, signals, event_ids=event_ids, mode=mode
        )

        # The fabric ran before ingest so a contradiction it found could be answered in
        # this same tick; that ordering leaves the report unattributed until now.
        if self.fabric is not None:
            link_revision = getattr(self.fabric, "link_revision", None)
            if link_revision is not None:
                await link_revision(context.context_id, revision.revision_id)

        # 3. Re-evaluate obligations whose saturation moved.
        evaluated = await self._reevaluate(context, saturation, outcomes, pre_existing)

        # 4. Propose the next work, gated on approval.
        proposed, pending = await self._propose(context, approved_action_ids)

        # 5. Decide, then say why. ``_status_after`` reads the engine's termination
        #    report, which carries the per-status reasons; before WP-A the report was
        #    built and thrown away on this path, so a SATURATED or BLOCKED tick
        #    returned ``note == ""`` and a caller could see only that the loop had
        #    stopped, never why. An investigation that ends without a reason is
        #    indistinguishable from one that crashed.
        status = await self._status_after(context)
        return LoopStep(
            status=status,
            revision=revision,
            obligations_created=tuple(o.obligation_id for o in created),
            actions_proposed=proposed,
            awaiting_approval=pending,
            evaluated=evaluated,
            feedback_signals=len(signals),
            note=await self._stop_reason(context, status, supplied=saturation),
        )

    # -- helpers -------------------------------------------------------------

    async def _fabric_signals(
        self,
        context: InvestigationContext,
        outcomes: Sequence[ObservationOutcome],
        revision_id: str = "",
    ) -> tuple[GapSignal, ...]:
        """One fabric pass, or nothing when no runner is wired.

        Import is deferred to the call so a deployment without the science layer on
        its path still constructs a loop; the dependency is optional by design.

        The root scope comes from the investigation's own ``scope_refs``. It is the only
        warrant available for a first cell: observations arrive carrying ids but no
        membership, and §0.2 forbids inventing one. With no ``scope_refs`` there is no
        root, every placement is refused, and the report says so -- which is the honest
        outcome, not a reason to guess.
        """
        from context.fabric import Scope

        from context_engine.fabric_bridge import to_engine_saturation
        from context_engine.fabric_runner import observations_from_outcomes

        observations = observations_from_outcomes(
            outcomes,
            scopes=_outcome_scopes(outcomes),
            revealed_by=_outcome_anchors(outcomes),
        )
        scope_refs = tuple(getattr(context, "scope_refs", ()) or ())
        root_scope = Scope.entity(*scope_refs) if scope_refs else None
        produced, report = await self.fabric.run(
            context_id=context.context_id,
            observations=observations,
            question=context.question,
            root_scope=root_scope,
            revision_id=revision_id,
        )
        self.last_fabric_report = report
        # The pass just computed a measured saturation verdict with reason codes. That
        # verdict is the only thing in the tick that was *measured* rather than assumed,
        # so it becomes the re-evaluation basis below. Before this, the basis was a
        # literal `SaturationState(marginal_gain=1.0)`, which is above every threshold
        # the loop ships with -- so `is_saturated` was a constant False and no
        # obligation could ever be satisfied. See WP-A / T010 in specs/028.
        self._fabric_saturation = to_engine_saturation(
            report,
            coverage_threshold=self.coverage_threshold,
            marginal_gain_threshold=self.marginal_gain_threshold,
        )
        return tuple(produced)

    @staticmethod
    def _merge(
        primary: Sequence[GapSignal], secondary: Sequence[GapSignal]
    ) -> list[GapSignal]:
        """Merge two signal streams by priority, keeping every distinct question.

        Deduplicated on ``(kind, question)`` so a fact reachable from two paths does
        not become two obligations -- the generator would create both, and the
        frontier would show the same question twice.
        """
        merged = list(primary)
        seen = {(signal.kind, signal.question) for signal in primary}
        for signal in secondary:
            key = (signal.kind, signal.question)
            if key in seen:
                continue
            seen.add(key)
            merged.append(signal)
        merged.sort(key=lambda signal: (-signal.priority, signal.question))
        return merged

    def _terminal_status(self, context: InvestigationContext) -> LoopStatus:
        if context.state is InvestigationState.SUSPENDED:
            return LoopStatus.SUSPENDED
        if context.state is InvestigationState.CLOSED:
            return LoopStatus.CLOSED
        return LoopStatus.CONTINUE

    async def _status_after(self, context: InvestigationContext) -> LoopStatus:
        report = await self.engine.termination_report(context.context_id)
        if report.is_terminal:
            return LoopStatus.SATURATED
        open_ids = await self.engine.open_obligations(context.context_id)
        if open_ids and not any([await self.engine.store.actions(o.obligation_id) for o in open_ids]):
            return LoopStatus.BLOCKED
        return LoopStatus.CONTINUE

    async def _stop_reason(
        self,
        context: InvestigationContext,
        status: LoopStatus,
        *,
        supplied: SaturationState | None = None,
    ) -> str:
        """Why this pass ended where it did, in every terminal case.

        CONTINUE returns the empty string deliberately: a pass that did not stop has
        nothing to explain, and padding it with a reason would make the note useless
        for the case that matters.
        """
        if status is LoopStatus.CONTINUE:
            return ""

        report = await self.engine.termination_report(context.context_id)
        if status is LoopStatus.SATURATED:
            reasons = "; ".join(report.reasons_by_status) or "all obligations settled"
            # Report the basis each obligation was actually settled on. Inventing a
            # summary basis here -- rather than reading back the one
            # ``_reevaluate`` computed -- produces a note that contradicts the
            # decision it is explaining: the obligation closes on measured coverage,
            # and the note says "coverage_unmeasured".
            bases: dict[str, str] = {}
            for obligation_id, basis in sorted(self._evaluated_bases.items()):
                bases[obligation_id] = basis.reason()
            detail = (
                "; ".join(f"{key}: {value}" for key, value in bases.items())
                if bases
                else "settled on evidence carried by the obligation, not re-evaluated this pass"
            )
            return f"saturated: {reasons} | basis: {detail}"

        if status is LoopStatus.BLOCKED:
            open_ids = await self.engine.open_obligations(context.context_id)
            # ``await`` cannot appear inside a generator expression's condition -- it
            # silently produces an async generator, and the failure surfaces as
            # "async_generator object is not iterable" three frames away from the cause.
            stalled = [
                obligation
                for obligation, action in zip(
                    open_ids,
                    [await self.engine.store.actions(item.obligation_id) for item in open_ids],
                )
                if not action
            ]
            # The stalled obligations are named rather than counted. A count tells an
            # analyst that work is stuck; the ids tell them which question to read.
            return (
                "blocked: "
                + (
                    "; ".join(sorted(item.obligation_id for item in stalled))
                    if stalled
                    else "open obligations have no action"
                )
                + " | no capability is currently available for them"
            )

        return _halt_reason(status, context)

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

    async def _reevaluate(
        self,
        context: InvestigationContext,
        saturation: SaturationState | None,
        outcomes: Sequence[ObservationOutcome],
        pre_existing: frozenset[str] | set[str] = frozenset(),
    ) -> tuple[str, ...]:
        if saturation is None and not outcomes:
            return ()
        touched: list[str] = []
        self._evaluated_bases = {}
        for obligation in await self.engine.open_obligations(context.context_id):
            if obligation.obligation_id not in pre_existing:
                continue
            related = [o for o in outcomes if not o.produced_nothing]
            evidence = sum(len(o.produced_observations) for o in related)
            contradicting = sum(len(o.contradicting) for o in related)
            if evidence == 0 and contradicting == 0:
                continue
            basis = self._basis_for(obligation, saturation, related)
            self._evaluated_bases[obligation.obligation_id] = basis
            data = SatisfactionInput(
                evidence_count=evidence,
                saturation=basis,
                contradicting_evidence=contradicting,
            )
            await self.engine.evaluate_obligation(obligation.obligation_id, data)
            touched.append(obligation.obligation_id)
        return tuple(sorted(touched))

    def _basis_for(
        self,
        obligation: ResearchObligation,
        supplied: SaturationState | None,
        related: Sequence[ObservationOutcome],
    ) -> SaturationState:
        """The saturation basis for one obligation, from the best evidence available.

        Three sources, in strict order of authority:

        1. ``supplied`` -- the caller measured it. Taken as given.
        2. The fabric pass that just ran. Measured coverage, measured independence,
           measured gain, with reason codes.
        3. What this tick's outcomes actually reported.

        The third source is the one that matters for a loop with no fabric runner, and
        it is what replaces the old ``marginal_gain=1.0`` placeholder. ``ObservationOutcome``
        already carries ``coverage_delta`` and ``marginal_gain``; nothing read them.

        On marginal gain this source is deliberately conservative: the maximum across
        related outcomes, not the mean. One action that still reported learning is
        evidence that learning is still possible, and averaging it away would let a
        single productive step be cancelled by several unproductive ones.

        On independence it claims nothing. ``required_independent_sources`` stays 0
        because the loop holds observation ids and no source lineage, and counting
        documents is exactly the mistake the constitution forbids (domain invariant 4:
        publication count is not independent-source count). A caller that measured
        independence supplies it through source 2.
        """
        if supplied is not None:
            return supplied
        if self._fabric_saturation is not None:
            return self._fabric_saturation
        if not related:
            return _unknown_saturation(self.coverage_threshold, self.marginal_gain_threshold)

        prior = obligation.saturation
        coverage = (prior.coverage if prior else 0.0) + sum(
            o.coverage_delta for o in related
        )
        return SaturationState(
            coverage=min(1.0, max(0.0, coverage)),
            coverage_known=True,
            marginal_gain=max(o.marginal_gain for o in related),
            marginal_gain_known=True,
            distinct_sources=prior.distinct_sources if prior else 0,
            source_diversity=prior.source_diversity if prior else 0,
            stopping_condition=(
                f"outcomes:{len(related)}"
                f"[max_gain={max(o.marginal_gain for o in related):.3f}]"
            ),
            coverage_threshold=self.coverage_threshold,
            marginal_gain_threshold=self.marginal_gain_threshold,
        )

    async def _propose(
        self, context: InvestigationContext, approved_action_ids: Sequence[str]
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Split the next work into "cleared to run" and "waiting on a human".

        ``proposed`` means *cleared*. An action requiring operator approval that has not been
        granted is returned in the second tuple and **omitted from the first**.

        It used to be appended to both. ``awaiting_approval`` was therefore a label rather than
        a gate: anything that scheduled work from ``LoopStep.actions_proposed`` would run an
        unapproved action, and the only thing telling it not to was that it also happened to see
        the id listed under a different field. Spec 030 FR-095: the engine proposes, and does
        not execute, until the decision is recorded.
        """
        approved = set(approved_action_ids)
        proposed: list[str] = []
        pending: list[str] = []
        for obligation in await self.engine.open_obligations(context.context_id):
            if approved:
                actions = await self.engine.store.actions(obligation.obligation_id)
                for action in actions:
                    if action.action_id in approved:
                        await self.engine.record_attempt(
                            action,
                            outcome="approved",
                            realised_gain=action.expected_information_gain,
                        )
                        proposed.append(action.action_id)
            action = await self.engine.propose_action(obligation.obligation_id)
            if action is None:
                continue
            if action.requires_operator_approval and action.action_id not in approved:
                # Gated. Recorded as awaiting a decision, and deliberately not proposed --
                # proposing it would hand a scheduler a work item it is meant to refuse.
                pending.append(action.action_id)
                continue
            proposed.append(action.action_id)
        return tuple(sorted(set(proposed))), tuple(sorted(set(pending)))


def _unknown_saturation(
    coverage_threshold: float, marginal_gain_threshold: float
) -> SaturationState:
    """A basis that refuses, and says so.

    This replaces a literal ``SaturationState(marginal_gain=1.0)`` that sat on the
    re-evaluation path. That placeholder had two defects, and they are related:

    * It was a constant. ``1.0`` exceeds every ``marginal_gain_threshold`` the loop
      ships with, so ``is_saturated`` was unconditionally ``False`` and no obligation
      could ever be satisfied on this path. The loop had no reachable terminal state
      short of a human editing the context.
    * It was silently decisive. Even had the threshold been above 1.0, it would have
      been a number that *decided* saturation while claiming to measure nothing.

    So the honest answer is not a number. It is ``coverage_known=False`` and
    ``marginal_gain_known=False``, which reads as "nothing was measured" and therefore
    blocks saturation -- the same direction as the old placeholder, but now because
    the input is absent rather than because the constant was high. The difference is
    visible: ``reason()`` names the missing ingredient, and the moment a real
    measurement arrives the state flips without any code change.
    """
    return SaturationState(
        coverage=0.0,
        coverage_known=False,
        marginal_gain=0.0,
        marginal_gain_known=False,
        distinct_sources=0,
        source_diversity=0,
        stopping_condition="unmeasured",
        coverage_threshold=coverage_threshold,
        marginal_gain_threshold=marginal_gain_threshold,
    )


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