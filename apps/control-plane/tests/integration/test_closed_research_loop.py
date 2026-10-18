"""WP-A: the research loop must be able to close, and say why.

Three of these tests would have failed before specs/028 WP-A and are the reason that
package exists. They are written against the *public* surface -- ``CognitiveLoop.tick``
and ``ContextEngine`` -- not against internals, because the claim being made is about
behaviour a caller observes.

The regression each one pins:

* ``test_an_obligation_reaches_a_terminal_state_from_evidence`` -- the loop's
  saturation basis used to be a literal ``SaturationState(marginal_gain=1.0)`` on the
  re-evaluation path. 1.0 exceeds every threshold the loop ships with, so
  ``is_saturated`` was constantly ``False`` and no obligation could ever be satisfied.
  The loop therefore had no reachable terminal state short of a human editing the
  context object.

* ``test_a_saturated_tick_carries_a_reason`` -- ``_status_after`` built the engine's
  termination report and discarded it, so ``LoopStep.note`` was populated only for
  suspension and closure. A SATURATED or BLOCKED tick returned an empty note.

* ``test_an_unmeasured_basis_cannot_satisfy`` -- the replacement for the constant must
  not simply invert into a default that decides the question. ``coverage_known=False``
  has to actually block.
"""

from __future__ import annotations

import pytest
from domain.investigation_context import InvestigationContext

from context_engine.engine import ContextEngine, GapSignal, TriggerKind
from context_engine.loop import (
    CognitiveLoop,
    LoopStatus,
    ObservationOutcome,
    _unknown_saturation,
)
from context_engine.obligations import KnowledgeType, SaturationState
from context_engine.store import InMemoryContextStore


def _context(question: str = "who owns the registry?") -> InvestigationContext:
    # ``scope_refs`` is mandatory: a context with no scope is refused by the domain
    # type, which is the right refusal -- "no scope" and "no context" must not be
    # indistinguishable. The fabric's root scope is derived from exactly this field.
    return InvestigationContext(
        tenant_id="t-1",
        investigation_id="inv-1",
        title="registry ownership",
        scope_refs=("entity:ent-1",),
        question=question,
    )


async def _engine_with_obligation(question: str = "who owns the registry?"):
    """An engine holding one open obligation, created through the real ingest path.

    Not a hand-built ``ResearchObligation``: a test that fabricates its own fixture can
    pass while the production path that creates obligations is broken. This goes
    through ``ContextEngine.ingest`` so the obligation is byte-identical to one a real
    gap signal would produce.
    """
    store = InMemoryContextStore()
    engine = ContextEngine(store)
    context = _context(question)
    await store.put_context(context)
    await engine.ingest(
        context,
        (
            GapSignal(
                kind=TriggerKind.COVERAGE_GAP,
                question=question,
                rationale="no evidence yet for the ownership claim",
                knowledge_type=KnowledgeType.ENTITY,
                priority=0.8,
            ),
        ),
    )
    return engine, context


def _outcome(action_id: str, *, observations: int, gain: float, coverage: float) -> ObservationOutcome:
    return ObservationOutcome(
        action_id=action_id,
        task_id=f"task-{action_id}",
        produced_observations=tuple(f"OBS-{action_id}-{index}" for index in range(observations)),
        coverage_delta=coverage,
        marginal_gain=gain,
    )


# ---------------------------------------------------------------------------
# FR-001, FR-002: the loop closes, and names the reason
# ---------------------------------------------------------------------------


async def test_an_obligation_reaches_a_terminal_state_from_evidence():
    """A productive, exhaustive pass settles the obligation instead of spinning.

    Both outcomes report coverage progress and *no remaining gain*: the frontier for
    this question has been drained, so another step of the same kind would teach
    nothing. Before WP-A the basis ignored that signal and hardcoded 1.0, so the loop
    could not distinguish "the last action still taught us something" from "nothing
    more is available" -- and could never choose the second.

    ``test_an_outcome_that_still_reports_gain_keeps_the_obligation_open`` is the
    mirror image, and together they pin the rule in both directions.
    """
    engine, context = await _engine_with_obligation()

    loop = CognitiveLoop(engine, coverage_threshold=0.5, marginal_gain_threshold=0.05)
    step = await loop.tick(
        context,
        outcomes=(
            _outcome("a1", observations=2, gain=0.0, coverage=0.3),
            _outcome("a2", observations=2, gain=0.0, coverage=0.3),
        ),
    )

    assert step.status is LoopStatus.SATURATED, (
        f"expected the loop to settle, got {step.status.value}: {step.note}"
    )

    report = await engine.termination_report(context.context_id)
    assert report.is_terminal
    assert step.evaluated, "the obligation was re-evaluated but nothing was touched"


async def test_a_saturated_tick_carries_a_reason():
    """FR-002: a terminal tick says which conditions it reached.

    An investigation that ends without a stated reason is indistinguishable from one
    that crashed, and an analyst cannot act on either.
    """
    engine, context = await _engine_with_obligation()
    loop = CognitiveLoop(engine, coverage_threshold=0.5, marginal_gain_threshold=0.05)

    step = await loop.tick(
        context,
        outcomes=(_outcome("a1", observations=3, gain=0.0, coverage=0.6),),
    )

    assert step.status is LoopStatus.SATURATED
    assert step.note.startswith("saturated:"), f"no reason attached: {step.note!r}"
    # The reason must name the evidence that was reached, not merely assert success.
    assert "coverage" in step.note
    assert "basis" in step.note


async def test_a_blocked_tick_names_the_stalled_obligations():
    """FR-002: a stop must say what is stuck, not merely that it is stuck."""
    store = InMemoryContextStore()
    engine = ContextEngine(store)
    context = _context()
    await store.put_context(context)
    _, created = await engine.ingest(
        context,
        (
            GapSignal(
                kind=TriggerKind.COVERAGE_GAP,
                question="which capability is missing?",
                rationale="the only source that could answer is unavailable",
                knowledge_type=KnowledgeType.BOUNDARY,
                priority=0.8,
            ),
        ),
    )
    obligation = created[0].obligation_id

    # No action is registered for the obligation, so the loop cannot make progress.
    loop = CognitiveLoop(engine)
    step = await loop.tick(context)

    assert step.status is LoopStatus.BLOCKED
    assert obligation in step.note, (
        f"the blocked note must name the obligation, got {step.note!r}"
    )
    assert "no capability" in step.note


async def test_a_contradiction_keeps_the_obligation_open():
    """User Story 1, scenario 3: disagreement is not a stop condition."""
    engine, context = await _engine_with_obligation()
    loop = CognitiveLoop(engine, coverage_threshold=0.5, marginal_gain_threshold=0.05)

    step = await loop.tick(
        context,
        outcomes=(
            ObservationOutcome(
                action_id="a1",
                task_id="task-a1",
                produced_observations=("OBS-a1-0",),
                contradicting=("claim-7",),
                coverage_delta=0.9,
                marginal_gain=0.0,
            ),
        ),
    )

    assert step.status is not LoopStatus.SATURATED, (
        "an unresolved contradiction must not settle the question"
    )


# ---------------------------------------------------------------------------
# FR-003: an absence must not read as a success
# ---------------------------------------------------------------------------


def test_an_unmeasured_basis_cannot_satisfy():
    """The replacement for the 1.0 constant refuses, and says which input is missing."""
    basis = _unknown_saturation(coverage_threshold=0.9, marginal_gain_threshold=0.05)

    assert basis.is_saturated is False
    assert "coverage_unmeasured" in basis.reason()
    assert "marginal_gain_unmeasured" in basis.reason()


def test_an_unmeasured_gain_blocks_even_at_full_coverage():
    """The dangerous case: perfect coverage, unknown gain.

    Reading "unknown" as 0.0 would satisfy ``0.0 <= 0.05`` and close the obligation on
    a measurement that was never taken. This is the exact failure the flag prevents.
    """
    basis = SaturationState(
        coverage=1.0,
        coverage_known=True,
        marginal_gain=0.0,
        marginal_gain_known=False,
        distinct_sources=99,
        source_diversity=99,
    )

    assert basis.is_saturated is False
    assert "marginal_gain_unmeasured" in basis.reason()


def test_a_declared_independence_requirement_is_honoured():
    """A caller that measured independence is held to it; one that did not, is not."""
    short = SaturationState(
        coverage=1.0,
        marginal_gain=0.0,
        distinct_sources=1,
        source_diversity=9,
        required_independent_sources=2,
    )
    met = SaturationState(
        coverage=1.0,
        marginal_gain=0.0,
        distinct_sources=3,
        source_diversity=2,
        required_independent_sources=2,
        required_source_families=2,
    )

    assert short.is_saturated is False
    assert "independent_sources=1<2" in short.reason()
    assert met.is_saturated is True


def test_legacy_constructions_are_unchanged():
    """Backward compatibility: the new fields default to the old semantics.

    Every pre-existing construction in the repo passes four positional arguments and
    no flags, and must keep behaving identically -- otherwise this is a silent
    behaviour change across 104 existing context tests.
    """
    legacy = SaturationState(
        coverage=0.95, marginal_gain=0.01, distinct_sources=4, source_diversity=3
    )

    assert legacy.coverage_known is True
    assert legacy.marginal_gain_known is True
    assert legacy.required_independent_sources == 0
    assert legacy.is_saturated is True


def test_saturation_round_trips_through_its_dict():
    """The added fields must survive persistence; a dropped flag silently re-opens a gate."""
    original = SaturationState(
        coverage=0.95,
        marginal_gain=0.01,
        distinct_sources=4,
        source_diversity=3,
        coverage_known=False,
        required_independent_sources=2,
        required_source_families=3,
    )

    restored = SaturationState.from_dict(original.to_dict())

    assert restored == original
    assert restored.coverage_known is False
    assert restored.required_source_families == 3
    assert restored.key() == original.key()


# ---------------------------------------------------------------------------
# The basis-selection rule
# ---------------------------------------------------------------------------


async def test_an_outcome_that_still_reports_gain_keeps_the_obligation_open():
    """One productive step must not be averaged away by several unproductive ones.

    The basis takes the maximum marginal gain across related outcomes rather than the
    mean, so an action that still taught us something keeps the question open even when
    other actions in the same tick taught us nothing.
    """
    engine, context = await _engine_with_obligation()
    loop = CognitiveLoop(engine, coverage_threshold=0.5, marginal_gain_threshold=0.05)

    step = await loop.tick(
        context,
        outcomes=(
            _outcome("a1", observations=1, gain=0.0, coverage=0.4),
            _outcome("a2", observations=1, gain=0.0, coverage=0.4),
            _outcome("a3", observations=1, gain=0.9, coverage=0.4),
        ),
    )

    assert step.status is not LoopStatus.SATURATED, (
        "an action still reporting gain means work remains"
    )


async def test_a_supplied_basis_wins_over_everything_else():
    """A caller that measured the basis is believed, including when it refuses."""
    engine, context = await _engine_with_obligation()
    loop = CognitiveLoop(engine, coverage_threshold=0.9, marginal_gain_threshold=0.05)

    step = await loop.tick(
        context,
        saturation=SaturationState(
            coverage=0.99, marginal_gain=0.9, distinct_sources=9, source_diversity=9
        ),
        outcomes=(_outcome("a1", observations=2, gain=0.0, coverage=1.0),),
    )

    assert step.status is not LoopStatus.SATURATED


async def test_a_tick_with_nothing_to_show_evaluates_nothing():
    """No outcomes means no re-evaluation -- and the stop reason must still be honest.

    A tick with nothing to show and an obligation with no proposed action ends
    ``BLOCKED``, not ``CONTINUE``: there is open work and no means to pursue it.
    Reporting ``CONTINUE`` there would be the platform claiming it is still making
    progress while doing nothing.
    """
    engine, context = await _engine_with_obligation()
    loop = CognitiveLoop(engine)

    step = await loop.tick(context)

    assert step.evaluated == (), "nothing was produced, so nothing may be re-evaluated"
    assert step.status is LoopStatus.BLOCKED
    assert step.note.startswith("blocked:"), f"no reason attached: {step.note!r}"


@pytest.mark.parametrize("threshold", [0.01, 0.05, 0.2])
async def test_no_threshold_setting_can_revive_the_old_placeholder(threshold: float):
    """The defect was structural, not a matter of misconfiguration.

    Sweeping the gain threshold across the range the loop ships with proves the old
    constant was unreachable for every legitimate configuration, rather than one that
    happened to be tuned wrongly.
    """
    engine, context = await _engine_with_obligation()
    loop = CognitiveLoop(engine, coverage_threshold=0.5, marginal_gain_threshold=threshold)

    step = await loop.tick(
        context,
        outcomes=(_outcome("a1", observations=1, gain=0.0, coverage=0.9),),
    )

    # With a real measurement the loop closes when it should...
    assert step.status is LoopStatus.SATURATED
    assert step.note

    # ...and the basis it used was the reported gain, not a placeholder.
    assert "outcomes:" in step.note