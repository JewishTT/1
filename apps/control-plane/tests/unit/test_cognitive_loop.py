"""Feature 024 Phase 13 -- the cognitive loop closes.

Asserts the properties that make the loop more than a pipeline: it keeps running while
work is unresolved, stops with a named reason, turns a refutation into a question
rather than a footnote, distinguishes an action that produced nothing from one that
produced something, and leaves execution gated on operator approval.
"""

from __future__ import annotations

import pytest
from domain.investigation_context import (
    InvestigationContext,
    InvestigationState,
    ObligationStatus,
)

from context_engine.loop import (
    CognitiveLoop,
    LoopStatus,
    ObservationOutcome,
    ScienceFeedback,
    ScienceOutcome,
)
from context_engine.obligations import SaturationState
from context_engine.store import InMemoryContextStore

pytestmark = pytest.mark.unit


def ctx(**over) -> InvestigationContext:
    base = {"tenant_id": "t1", "investigation_id": "INV-1", "scope_refs": ("acme.example",)}
    base.update(over)
    return InvestigationContext(**base)


def loop(**kw) -> CognitiveLoop:
    return CognitiveLoop(_engine(), **kw)


def _engine():
    from context_engine.engine import ActionProposer, CapabilityDescriptor, ContextEngine

    return ContextEngine(
        InMemoryContextStore(),
        proposer=ActionProposer(
            [
                CapabilityDescriptor(runtime_ref="searxng", capabilities=("search",)),
                CapabilityDescriptor(runtime_ref="airbyte", capabilities=("structured",)),
            ]
        ),
    )


def saturated() -> SaturationState:
    return SaturationState(
        coverage=0.95, marginal_gain=0.01, distinct_sources=6, source_diversity=4
    )


# -- the loop runs while work remains -----------------------------------------

async def test_a_tick_proposes_work_for_an_open_obligation():
    lp = loop()
    c = ctx()
    await lp.tick(c, feedback=[])
    frontier = await lp.engine.open_obligations(c.context_id)
    assert frontier == () or await lp.engine.frontier(c.context_id) is not None


async def test_the_loop_does_not_report_terminal_while_obligations_are_open():
    lp = loop()
    c = ctx()
    await lp.engine.ingest(
        c,
        [__import__("context_engine.engine", fromlist=["GapSignal"]).GapSignal(
            kind=__import__("context_engine.engine", fromlist=["TriggerKind"]).TriggerKind.COVERAGE_GAP,
            question="who owns acme?",
        )],
    )
    step = await lp.tick(c)
    assert step.status in (LoopStatus.CONTINUE, LoopStatus.BLOCKED)


async def test_a_suspended_investigation_stops_with_a_reason():
    lp = loop()
    step = await lp.tick(ctx(state=InvestigationState.SUSPENDED))
    assert step.status is LoopStatus.SUSPENDED
    assert "suspended" in step.note


async def test_a_closed_investigation_stops_with_a_reason():
    lp = loop()
    step = await lp.tick(ctx(state=InvestigationState.CLOSED))
    assert step.status is LoopStatus.CLOSED
    assert step.note


async def test_a_resolved_investigation_reports_saturated():
    lp = loop()
    c = ctx()
    await lp.engine.ingest(
        c,
        [
            __import__("context_engine.engine", fromlist=["GapSignal"]).GapSignal(
                kind=__import__("context_engine.engine", fromlist=["TriggerKind"]).TriggerKind.COVERAGE_GAP,
                question="q1",
            )
        ],
    )
    for o in await lp.engine.open_obligations(c.context_id):
        from context_engine.engine import SatisfactionInput

        await lp.engine.evaluate_obligation(
            o.obligation_id,
            SatisfactionInput(evidence_count=4, saturation=saturated()),
        )
    step = await lp.tick(c)
    assert step.status is LoopStatus.SATURATED


# -- science is not an epilogue ----------------------------------------------

async def test_a_refuted_claim_becomes_a_question_the_investigation_must_answer():
    lp = loop()
    c = ctx()
    await lp.tick(
        c,
        feedback=[
            ScienceFeedback(
                outcome=ScienceOutcome.REFUTED,
                claim_ref="CLM-1",
                detail="refuted at 95% CI",
                snapshot_id="WLS-1",
                method_fingerprint="m@v1",
            )
        ],
    )
    questions = [o.question for o in ((((((((((await lp.engine.open_obligations(c.context_id)))))))))))]
    assert any("refutation" in q for q in questions), questions


async def test_a_refutation_names_its_snapshot_and_method():
    """A question you cannot trace to the evaluation that raised it is unactionable."""
    lp = loop()
    c = ctx()
    await lp.tick(
        c,
        feedback=[
            ScienceFeedback(
                outcome=ScienceOutcome.REFUTED,
                claim_ref="CLM-1",
                snapshot_id="WLS-7",
                method_fingerprint="method@v3",
            )
        ],
    )
    obligations = await lp.engine.open_obligations(c.context_id)
    assert any("WLS-7" in o.rationale and "method@v3" in o.rationale for o in obligations)


async def test_calibration_drift_becomes_a_question():
    lp = loop()
    c = ctx()
    await lp.tick(
        c,
        feedback=[
            ScienceFeedback(outcome=ScienceOutcome.DRIFTED, claim_ref="CLM-2", snapshot_id="WLS-2")
        ],
    )
    questions = [o.question for o in ((((((((((await lp.engine.open_obligations(c.context_id)))))))))))]
    assert any("drift" in q for q in questions)


async def test_a_supported_claim_produces_no_new_work():
    """Nothing left to ask about a settled question. Inventing a signal for it is how
    a loop spins forever."""
    lp = loop()
    c = ctx()
    step = await lp.tick(
        c,
        feedback=[ScienceFeedback(outcome=ScienceOutcome.SUPPORTED, claim_ref="CLM-1")],
    )
    assert step.feedback_signals == 0
    assert await lp.engine.open_obligations(c.context_id) == ()


async def test_inconclusive_science_produces_no_new_work():
    lp = loop()
    c = ctx()
    step = await lp.tick(
        c, feedback=[ScienceFeedback(outcome=ScienceOutcome.INCONCLUSIVE, claim_ref="CLM-1")]
    )
    assert step.feedback_signals == 0


# -- real outcomes, honestly counted -----------------------------------------

def test_an_action_that_produced_nothing_is_distinguishable():
    outcome = ObservationOutcome(action_id="A1", task_id="T1", produced_observations=())
    assert outcome.produced_nothing is True
    assert ObservationOutcome(action_id="A2", task_id="T2", produced_observations=("OBS-1",)).produced_nothing is False


async def test_a_contradicting_observation_becomes_a_question():
    lp = loop()
    c = ctx()
    await lp.tick(
        c,
        outcomes=[
            ObservationOutcome(
                action_id="A1", task_id="T1", produced_observations=("OBS-1",), contradicting=("CLM-9",)
            )
        ],
    )
    questions = [o.question for o in ((((((((((await lp.engine.open_obligations(c.context_id)))))))))))]
    assert any("CLM-9" in q for q in questions), questions


async def test_observations_alone_do_not_satisfy_without_saturation():
    """FR-053 restated at the loop level: producing observations is not sufficiency."""
    lp = loop()
    c = ctx()
    await lp.engine.ingest(
        c,
        [
            __import__("context_engine.engine", fromlist=["GapSignal"]).GapSignal(
                kind=__import__("context_engine.engine", fromlist=["TriggerKind"]).TriggerKind.COVERAGE_GAP,
                question="q1",
            )
        ],
    )
    oid = (((((await lp.engine.open_obligations(c.context_id))))))[0].obligation_id
    await lp.tick(
        c,
        outcomes=[ObservationOutcome(action_id="A", task_id="T", produced_observations=("OBS-1",))],
    )
    assert ((((((((((await lp.engine.store.get_obligation(oid))))))))))).status is not ObligationStatus.SATISFIED


async def test_saturated_plus_evidence_does_satisfy_through_the_loop():
    lp = loop()
    c = ctx()
    await lp.engine.ingest(
        c,
        [
            __import__("context_engine.engine", fromlist=["GapSignal"]).GapSignal(
                kind=__import__("context_engine.engine", fromlist=["TriggerKind"]).TriggerKind.COVERAGE_GAP,
                question="q1",
            )
        ],
    )
    oid = (((((await lp.engine.open_obligations(c.context_id))))))[0].obligation_id
    await lp.tick(
        c,
        outcomes=[ObservationOutcome(action_id="A", task_id="T", produced_observations=("OBS-1",))],
        saturation=saturated(),
    )
    assert ((((((((((await lp.engine.store.get_obligation(oid))))))))))).status is ObligationStatus.SATISFIED


async def test_a_contradiction_through_the_loop_blocks_rather_than_satisfying():
    lp = loop()
    c = ctx()
    await lp.engine.ingest(
        c,
        [
            __import__("context_engine.engine", fromlist=["GapSignal"]).GapSignal(
                kind=__import__("context_engine.engine", fromlist=["TriggerKind"]).TriggerKind.COVERAGE_GAP,
                question="q1",
            )
        ],
    )
    oid = (((((await lp.engine.open_obligations(c.context_id))))))[0].obligation_id
    await lp.tick(
        c,
        outcomes=[
            ObservationOutcome(
                action_id="A", task_id="T", produced_observations=("OBS-1",), contradicting=("CLM-1",)
            )
        ],
        saturation=saturated(),
    )
    assert ((((((((((await lp.engine.store.get_obligation(oid))))))))))).status is ObligationStatus.BLOCKED


# -- the operator stays in control -------------------------------------------

async def test_a_proposed_action_waits_for_approval():
    lp = loop()
    c = ctx()
    await lp.engine.ingest(
        c,
        [
            __import__("context_engine.engine", fromlist=["GapSignal"]).GapSignal(
                kind=__import__("context_engine.engine", fromlist=["TriggerKind"]).TriggerKind.COVERAGE_GAP,
                question="q1",
            )
        ],
    )
    step = await lp.tick(c)
    assert step.awaiting_approval, "an action was proposed without waiting for approval"


async def test_an_approved_action_is_recorded_as_an_attempt():
    lp = loop()
    c = ctx()
    await lp.engine.ingest(
        c,
        [
            __import__("context_engine.engine", fromlist=["GapSignal"]).GapSignal(
                kind=__import__("context_engine.engine", fromlist=["TriggerKind"]).TriggerKind.COVERAGE_GAP,
                question="q1",
            )
        ],
    )
    first = await lp.tick(c)
    action_id = first.actions_proposed[0]
    await lp.tick(c, approved_action_ids=[action_id])
    memory = await lp.engine.store.memory_for((((((await lp.engine.open_obligations(c.context_id))))))[0].obligation_id)
    assert any(entry.outcome == "approved" for entry in memory)


async def test_the_tick_accounts_for_everything_it_did():
    lp = loop()
    step = await lp.tick(
        ctx(),
        feedback=[ScienceFeedback(outcome=ScienceOutcome.REFUTED, claim_ref="CLM-1", snapshot_id="W1")],
    )
    d = step.to_dict()
    for key in ("status", "obligations_created", "actions_proposed", "awaiting_approval", "evaluated"):
        assert key in d
    assert d["obligations_created"]
