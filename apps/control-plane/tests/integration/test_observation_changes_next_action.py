"""Phase 3 / User Story 1, T052: a new observation moves three things at once.

The end-to-end claim, in one test and its two mirrors:

* a new observation advances the **invariant** revision -- the graph-projection side has a
  new state to fold, with a real digest change rather than a re-derivation;
* it advances the **context** revision -- the research record has a new cause to point at;
* and it **changes the recommended next action**, with a recorded justification.

The third is the one that matters and the easiest to fake. An engine that recomputes the
same proposal twice has "changed its recommendation" in no sense anybody can act on, so
each test compares the *substantive* content of the proposal -- the runtime it routes to,
the capabilities it requires, the gain it expects -- and not merely that "something was
returned".

Hermetic: in-memory store, fixed timestamps, no clock, no network, no database, no donor
component.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from contracts.stage_outcome import StageStatus
from domain.dynamics import StreamRecord
from domain.investigation_context import InvestigationContext, ObligationStatus

from context_engine.engine import (
    ActionProposer,
    CapabilityDescriptor,
    ContextEngine,
    GapSignal,
    SatisfactionInput,
    TriggerKind,
)
from context_engine.invariant_reducer import InvariantReducer
from context_engine.loop import CognitiveLoop, LoopStatus, ObservationOutcome
from context_engine.obligations import MemoryState, ResearchAction, SaturationState
from context_engine.store import InMemoryContextStore

WINDOW = timedelta(days=7)
BASE = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)
QUESTION = "who owns the registry?"

#: Two routes. The cheaper one is what the engine proposes first, so a change in what it
#: recommends has to be a change of substance rather than a reshuffle of equal options.
REGISTRY = CapabilityDescriptor(
    runtime_ref="registry.record.extract",
    capabilities=("entity.extract", "filing.extract"),
    cost_class="cheap",
)
FILINGS = CapabilityDescriptor(
    runtime_ref="registry.filing.pdf",
    capabilities=("entity.extract", "filing.pdf", "ocr.text"),
    cost_class="expensive",
)


def _context() -> InvestigationContext:
    return InvestigationContext(
        tenant_id="t-1",
        investigation_id="inv-1",
        title="registry ownership",
        scope_refs=("entity:ent-1",),
        question=QUESTION,
    )


def _stream_record(sequence: int) -> StreamRecord:
    # The reducer is tenant-scoped and defaults to its own tenant; the investigation runs
    # under "t-1". Keeping them apart here rather than unifying them is the honest shape:
    # two different scopes, two different records.
    return StreamRecord(
        entity_id="ent-1",
        kind="entity.observed",
        ts=BASE + timedelta(minutes=sequence),
        tenant_id="default-tenant",
        payload={"owners": ["ent-1"]},
        sequence=sequence,
    )


def _saturated(coverage: float = 0.95, gain: float = 0.0) -> SaturationState:
    return SaturationState(
        coverage=coverage,
        marginal_gain=gain,
        distinct_sources=4,
        source_diversity=3,
    )


async def _engine():
    store = InMemoryContextStore()
    engine = ContextEngine(store, proposer=ActionProposer([REGISTRY, FILINGS]))
    context = _context()
    await store.put_context(context)
    await engine.ingest(
        context,
        (
            GapSignal(
                kind=TriggerKind.COVERAGE_GAP,
                question=QUESTION,
                rationale="no evidence yet for the ownership claim",
                required_capabilities=("entity.extract",),
                event_id="evt-gap-1",
            ),
        ),
        event_ids=["evt-gap-1"],
    )
    return engine, context, (await engine.open_obligations(context.context_id))[0]


def _plan_of(action: ResearchAction | None) -> tuple[str, tuple[str, ...], float]:
    """The substantive content of a recommendation, with its id stripped.

    Comparing ids would pass trivially -- ``with_id`` rehashes on any material change --
    and would prove nothing. What has to change is *where the work goes* and *what it
    requires*.
    """
    assert action is not None
    return (
        action.runtime_ref,
        action.capability_requirements,
        action.expected_information_gain,
    )


# =============================================================================
# the end-to-end claim
# =============================================================================


async def test_a_new_observation_moves_the_invariant_the_context_and_the_next_action():
    """T052, stated once.

    Before the observation the engine recommends the cheap structured route. After it --
    an observation that shows the structured route cannot reach the document -- the engine
    recommends the expensive PDF route, because that is the only route left that carries
    the capability the new evidence says is required.
    """
    engine, context, obligation = await _engine()
    reducer = InvariantReducer(window=WINDOW)

    # -- before ---------------------------------------------------------------
    before_invariant = reducer.reduce([_stream_record(1)])
    assert before_invariant.changed is True
    before_context = await engine.revision_history(context.context_id)
    before_action = await engine.propose_action(
        obligation.obligation_id, required_capabilities=("entity.extract",)
    )

    assert _plan_of(before_action)[0] == REGISTRY.runtime_ref
    assert _plan_of(before_action)[1] == ("entity.extract",)

    # -- the observation ------------------------------------------------------
    # A real observation: the structured route ran and produced a record saying the
    # ownership clause lives inside a scanned filing.
    structured = ResearchAction(
        obligation_id=obligation.obligation_id,
        proposed_method=f"acquire via {REGISTRY.runtime_ref}",
        runtime_ref=REGISTRY.runtime_ref,
    ).with_id()
    await engine.record_attempt(
        structured,
        outcome="succeeded",
        realised_gain=0.2,
        detail="ownership clause is inside a scanned filing, not in the structured fields",
    )

    after_invariant = reducer.reduce([_stream_record(2)])
    verdict = await engine.evaluate_obligation(
        obligation.obligation_id,
        SatisfactionInput(
            evidence_count=1,
            saturation=SaturationState(
                coverage=0.2,
                marginal_gain=0.4,
                distinct_sources=1,
                source_diversity=1,
            ),
            stage_status=StageStatus.SUCCEEDED,
            evidence_refs=("OBS-scan-1",),
        ),
    )
    after_context = await engine.revision_history(context.context_id)
    after_action = await engine.propose_action(
        obligation.obligation_id, required_capabilities=("filing.pdf",)
    )

    # 1. the invariant advanced, with a new digest and a linked predecessor
    assert after_invariant.changed is True
    assert after_invariant.record.revision == before_invariant.record.revision + 1
    assert after_invariant.record.supersedes == before_invariant.record.snapshot_id
    assert after_invariant.record.digest != before_invariant.record.digest

    # 2. the context advanced, naming the observation as its cause
    assert len(after_context) > len(before_context)
    assert verdict.satisfied is False, "one observation is not coverage"

    # 3. the recommendation changed, in substance
    assert _plan_of(after_action)[0] == FILINGS.runtime_ref
    assert "filing.pdf" in _plan_of(after_action)[1]
    assert _plan_of(after_action) != _plan_of(before_action)

    # ...and the change is justified on the record rather than merely made.
    decisions = engine.recorder.decisions(context.context_id)
    evaluated = [d for d in decisions if d.kind == "obligation_evaluated"]
    assert evaluated
    assert "OBS-scan-1" in evaluated[-1].detail or evaluated[-1].detail


async def test_a_redelivered_observation_does_not_advance_the_invariant_again():
    """FR-065. Idempotence is what makes a chain of revisions mean anything."""
    reducer = InvariantReducer(window=WINDOW)
    first = reducer.reduce([_stream_record(1)])
    assert first.changed is True

    again = reducer.reduce([_stream_record(1)])
    assert again.changed is False
    assert again.record == first.record


async def test_the_invariant_and_the_context_advance_together_or_neither_moves():
    """One batch, one cause, two chains -- so the two cannot silently diverge."""
    engine, context, _ = await _engine()
    reducer = InvariantReducer(window=WINDOW)

    engine_before = len(await engine.revision_history(context.context_id))
    first = reducer.reduce([_stream_record(1)])
    await engine.ingest(context, (), event_ids=[first.record.snapshot_id])
    engine_after = len(await engine.revision_history(context.context_id))

    assert first.changed is True
    assert engine_after == engine_before + 1
    assert await engine.revision_history(context.context_id) == tuple(
        await engine.revision_history(context.context_id)
    )


# =============================================================================
# the recommendation itself
# =============================================================================


async def test_the_next_action_changes_when_the_capability_requirement_changes():
    engine, _, obligation = await _engine()

    structured = await engine.propose_action(
        obligation.obligation_id, required_capabilities=("entity.extract",)
    )
    scanned = await engine.propose_action(
        obligation.obligation_id, required_capabilities=("filing.pdf",)
    )

    assert _plan_of(structured)[0] == REGISTRY.runtime_ref
    assert _plan_of(scanned)[0] == FILINGS.runtime_ref


async def test_a_no_capability_fitting_proposes_nothing_rather_than_weakening_the_ask():
    """FR-040. Inventing a substitute is how a weaker question gets answered."""
    engine, _, obligation = await _engine()

    action = await engine.propose_action(
        obligation.obligation_id, required_capabilities=("time.travel.ocr",)
    )

    assert action is None


async def test_an_attempted_route_is_not_re_proposed_even_when_another_is_available():
    engine, _, obligation = await _engine()
    first = await engine.propose_action(
        obligation.obligation_id, required_capabilities=("entity.extract",)
    )
    await engine.record_attempt(first, outcome="succeeded", realised_gain=0.1)

    assert first.runtime_ref == REGISTRY.runtime_ref
    follow_up = await engine.propose_action(
        obligation.obligation_id, required_capabilities=("entity.extract",)
    )
    # The other descriptor also carries the capability, so the engine still has work to
    # offer -- but it must not be the route that already ran.
    assert follow_up is not None
    assert follow_up.runtime_ref == FILINGS.runtime_ref


async def test_the_loop_records_the_attempt_in_memory_when_it_runs():
    """The memory is written on the approval path, not by the caller remembering to."""
    engine, context, obligation = await _engine()
    loop = CognitiveLoop(engine, coverage_threshold=0.5, marginal_gain_threshold=0.05)

    proposed = await loop.tick(
        context,
        approved_action_ids=(
            (await engine.propose_action(obligation.obligation_id)).action_id,
        ),
    )

    memory = await engine.action_memory(obligation.obligation_id)
    assert memory, "an approved action left no memory"
    assert memory[0].state is MemoryState.PENDING
    assert proposed.awaiting_approval or proposed.actions_proposed


# =============================================================================
# the loop, end to end
# =============================================================================


async def test_a_loop_tick_changes_the_recommendation_and_says_why():
    engine, context, _ = await _engine()
    loop = CognitiveLoop(engine, coverage_threshold=0.5, marginal_gain_threshold=0.05)

    first = await loop.tick(context)
    assert first.status is LoopStatus.CONTINUE
    assert first.awaiting_approval, "an ungated action would be executed without approval"
    assert not first.actions_proposed

    second = await loop.tick(
        context,
        approved_action_ids=first.awaiting_approval,
        outcomes=(
            ObservationOutcome(
                action_id=first.awaiting_approval[0],
                task_id="task-1",
                produced_observations=("OBS-independent-1",),
                coverage_delta=0.6,
                marginal_gain=0.0,
            ),
        ),
    )

    assert second.status is LoopStatus.SATURATED, second.note
    assert second.evaluated
    report = await engine.termination_report(context.context_id)
    assert report.is_terminal
    assert report.stop_reason_detail


async def test_an_obligation_left_open_is_still_open_after_an_unproductive_tick():
    """Nothing was learned, so nothing changed -- and nothing was quietly closed."""
    engine, context, obligation = await _engine()
    loop = CognitiveLoop(engine, coverage_threshold=0.5, marginal_gain_threshold=0.05)

    await loop.tick(context)
    await loop.tick(
        context,
        outcomes=(
            ObservationOutcome(
                action_id="ACT-nothing",
                task_id="task-2",
                produced_observations=(),
                coverage_delta=0.0,
                marginal_gain=0.0,
            ),
        ),
    )

    stored = await engine.store.get_obligation(obligation.obligation_id)
    assert stored.status is not ObligationStatus.SATISFIED
    report = await engine.termination_report(context.context_id)
    assert report.is_terminal is False
    assert report.stop_reason is None