"""Feature 024 Phase 4/5 -- the Context Engine.

The behaviours asserted here are the ones that were impossible before this phase:
obligations that can be generated and closed with a stated reason, a distinction
between "saturated" and "tried hard", saturation as the closure criterion rather than
task counts, actions that are proposed but never executed, memory that stops the
engine repeating itself, and a revision chain that replays deterministically.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from domain.investigation_context import (
    ContextEngineError,
    InvestigationContext,
    InvestigationState,
    ObligationStatus,
)

from context_engine.engine import (
    RULES_VERSION,
    ActionProposer,
    CapabilityDescriptor,
    ContextEngine,
    GapSignal,
    ObligationGenerator,
    SatisfactionEvaluator,
    SatisfactionInput,
    TriggerKind,
    assert_components_are_separate,
)
from context_engine.obligations import (
    Disposition,
    ResearchObligation,
    SaturationState,
)
from context_engine.store import InMemoryContextStore, StoreDurability

pytestmark = pytest.mark.unit


def ctx(**over) -> InvestigationContext:
    base = {"tenant_id": "t1", "investigation_id": "INV-1", "scope_refs": ("acme.example",)}
    base.update(over)
    return InvestigationContext(**base)


def saturated() -> SaturationState:
    return SaturationState(
        coverage=0.95, marginal_gain=0.01, distinct_sources=7, source_diversity=5
    )


def unsaturated() -> SaturationState:
    return SaturationState(
        coverage=0.40, marginal_gain=0.30, distinct_sources=2, source_diversity=1
    )


def engine(**kw) -> ContextEngine:
    return ContextEngine(InMemoryContextStore(), **kw)


def seed(e: ContextEngine, signals) -> InvestigationContext:
    c = ctx()
    e.ingest(c, signals, event_ids=["evt-1"])
    return c


# -- FR-041: five components, not one -----------------------------------------

def test_the_five_components_are_genuinely_separate():
    assert_components_are_separate()


def test_the_engine_owns_one_of_each_component():
    e = engine()
    names = {type(c).__name__ for c in (e.generator, e.evaluator, e.proposer, e.recorder, e.revisions)}
    assert names == {
        "ObligationGenerator", "SatisfactionEvaluator", "ActionProposer",
        "DecisionRecorder", "RevisionManager",
    }


# -- FR-034: obligations are generated with a recorded, versioned reason -------

def test_a_gap_produces_an_obligation_that_names_its_rule():
    e = engine()
    c = seed(e, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="who owns acme?", rationale="no owner found")])
    obligations = e.open_obligations(c.context_id)
    assert len(obligations) == 1
    assert obligations[0].created_by.startswith(RULES_VERSION)
    assert obligations[0].created_by.endswith("#coverage_gap")
    assert obligations[0].rationale == "no owner found"


def test_generation_is_deterministic_regardless_of_signal_order():
    a = ObligationGenerator()
    c = ctx()
    s1 = GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q1")
    s2 = GapSignal(kind=TriggerKind.CONTRADICTION, question="q2")
    forward = [o.obligation_id for o, _ in a.generate(c, [s1, s2])]
    backward = [o.obligation_id for o, _ in a.generate(c, [s2, s1])]
    assert forward == backward


def test_the_same_gap_twice_is_not_new_work():
    e = engine()
    c = ctx()
    signal = GapSignal(kind=TriggerKind.COVERAGE_GAP, question="who owns acme?")
    e.ingest(c, [signal], event_ids=["evt-1"])
    _, created = e.ingest(c, [signal], event_ids=["evt-2"])
    assert created == []
    assert len(e.open_obligations(c.context_id)) == 1


def test_the_constitutional_core_takes_no_adaptive_input():
    """FR-045: the generator must be correct with the adaptive layer absent. Its
    only inputs are the context and the declared signals -- nothing optional, nothing
    learned, nothing score-derived."""
    import inspect

    params = set(inspect.signature(ObligationGenerator.generate).parameters)
    assert params == {"self", "context", "signals"}

    evaluator_params = set(inspect.signature(SatisfactionEvaluator.evaluate).parameters)
    assert evaluator_params == {"self", "obligation", "data"}


# -- FR-037: satisfaction is a pure function of declared inputs ---------------

def test_no_evidence_never_satisfies_even_with_high_coverage():
    """FR-053: effort is not sufficiency."""
    o = ResearchObligation(context_id="CXI-x", question="q").with_id()
    verdict = SatisfactionEvaluator().evaluate(
        o, SatisfactionInput(evidence_count=0, saturation=saturated())
    )
    assert verdict.satisfied is False
    assert "never satisfy" in verdict.reason


def test_saturated_with_evidence_satisfies_and_states_why():
    o = ResearchObligation(context_id="CXI-x", question="q").with_id()
    verdict = SatisfactionEvaluator().evaluate(
        o, SatisfactionInput(evidence_count=3, saturation=saturated())
    )
    assert verdict.satisfied is True
    assert "coverage=0.95" in verdict.reason
    assert "marginal_gain=0.010" in verdict.reason


def test_unsaturated_never_satisfies_however_much_evidence_accrues():
    o = ResearchObligation(context_id="CXI-x", question="q").with_id()
    verdict = SatisfactionEvaluator().evaluate(
        o, SatisfactionInput(evidence_count=999, saturation=unsaturated())
    )
    assert verdict.satisfied is False
    assert "not saturated" in verdict.reason


def test_a_contradiction_cannot_satisfy_an_obligation():
    """FR-038."""
    o = ResearchObligation(context_id="CXI-x", question="q").with_id()
    verdict = SatisfactionEvaluator().evaluate(
        o,
        SatisfactionInput(
            evidence_count=10, saturation=saturated(), contradicting_evidence=1
        ),
    )
    assert verdict.satisfied is False
    assert "contradicted" in verdict.reason


def test_an_unresolved_dependency_blocks():
    o = ResearchObligation(context_id="CXI-x", question="q").with_id()
    verdict = SatisfactionEvaluator().evaluate(
        o,
        SatisfactionInput(
            evidence_count=5,
            saturation=saturated(),
            unresolved_dependencies=("OBL-other",),
        ),
    )
    assert verdict.satisfied is False
    assert "blocked" in verdict.reason


def test_the_evaluator_is_a_pure_function_of_its_inputs():
    """Same inputs, same verdict, twice, on separate evaluator instances."""
    o = ResearchObligation(context_id="CXI-x", question="q").with_id()
    data = SatisfactionInput(evidence_count=2, saturation=saturated())
    a = SatisfactionEvaluator().evaluate(o, data)
    b = SatisfactionEvaluator().evaluate(o, data)
    assert a == b


def test_satisfaction_carries_its_rules_version():
    o = ResearchObligation(context_id="CXI-x", question="q").with_id()
    v = SatisfactionEvaluator().evaluate(o, SatisfactionInput(evidence_count=1, saturation=saturated()))
    assert v.rules_version == RULES_VERSION


# -- FR-035: terminal states carry a reason -----------------------------------

def test_a_satisfied_obligation_records_how_it_was_satisfied():
    e = engine()
    c = seed(e, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q")])
    oid = e.open_obligations(c.context_id)[0].obligation_id
    e.evaluate_obligation(oid, SatisfactionInput(evidence_count=3, saturation=saturated()))
    closed = e.store.get_obligation(oid)
    assert closed.status is ObligationStatus.SATISFIED
    assert closed.disposition is Disposition.SATISFIED
    assert closed.disposition_reason
    assert "coverage=0.95" in closed.disposition_reason


def test_an_obligation_cannot_be_marked_satisfied_without_saying_why():
    with pytest.raises(ContextEngineError) as exc:
        ResearchObligation(
            context_id="CXI-x", question="q", status=ObligationStatus.SATISFIED
        )
    assert exc.value.code == "obligation_satisfied_without_disposition"


def test_an_obligation_with_no_evidence_stays_open():
    e = engine()
    c = seed(e, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q")])
    oid = e.open_obligations(c.context_id)[0].obligation_id
    e.evaluate_obligation(oid, SatisfactionInput(evidence_count=0, saturation=saturated()))
    assert e.store.get_obligation(oid).status is ObligationStatus.OPEN


def test_a_contradiction_blocks_rather_than_closes():
    e = engine()
    c = seed(e, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q")])
    oid = e.open_obligations(c.context_id)[0].obligation_id
    e.evaluate_obligation(
        oid, SatisfactionInput(evidence_count=4, saturation=saturated(), contradicting_evidence=2)
    )
    blocked = e.store.get_obligation(oid)
    assert blocked.status is ObligationStatus.BLOCKED
    assert "contradicted by 2" in blocked.disposition_reason


def test_obligation_identity_survives_progress():
    """If progress moved the address, action memory keyed by obligation could never
    match again."""
    e = engine()
    c = seed(e, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q")])
    oid = e.open_obligations(c.context_id)[0].obligation_id
    e.evaluate_obligation(oid, SatisfactionInput(evidence_count=2, saturation=unsaturated()))
    assert e.store.get_obligation(oid).obligation_id == oid


# -- FR-036: actions are proposed, never executed -----------------------------

def catalogue():
    return [
        CapabilityDescriptor(runtime_ref="searxng", capabilities=("search", "http")),
        CapabilityDescriptor(runtime_ref="airbyte", capabilities=("structured",), cost_class="expensive"),
    ]


def test_an_action_is_proposed_but_not_executed():
    e = engine(proposer=ActionProposer(catalogue()))
    c = seed(e, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q")])
    oid = e.open_obligations(c.context_id)[0].obligation_id
    action = e.propose_action(oid, required_capabilities=["search"])
    assert action is not None
    assert action.runtime_ref == "searxng"
    assert action.status == "proposed"
    assert action.requires_operator_approval is True


def test_no_compatible_capability_proposes_nothing():
    """FR-040: surface the gap, do not invent the capability."""
    e = engine(proposer=ActionProposer(catalogue()))
    c = seed(e, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q")])
    oid = e.open_obligations(c.context_id)[0].obligation_id
    assert e.propose_action(oid, required_capabilities=["telepathy"]) is None


def test_capabilities_check_compatibility_and_never_choose_the_runtime():
    """D4: routing is by runtime_ref; capabilities gate, they do not select."""
    d = CapabilityDescriptor(runtime_ref="searxng", capabilities=("search", "http"))
    assert d.supports(["search"]) is True
    assert d.supports(["search", "ftp"]) is False
    assert d.runtime_ref == "searxng"


def test_the_cheaper_compatible_runtime_is_preferred():
    e = engine(proposer=ActionProposer(catalogue()))
    c = seed(e, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q")])
    oid = e.open_obligations(c.context_id)[0].obligation_id
    cheap = e.propose_action(oid, required_capabilities=[])
    assert cheap.runtime_ref == "searxng"


# -- FR-059: action memory ----------------------------------------------------

def test_the_engine_does_not_repropose_the_same_runtime():
    """FR-059. The invariant is "not again", not "nothing left": with several
    runtimes, moving to an unattempted one is correct, re-offering the attempted one
    is the loop action memory exists to prevent."""
    e = engine(proposer=ActionProposer(catalogue()))
    c = seed(e, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q")])
    oid = e.open_obligations(c.context_id)[0].obligation_id

    first = e.propose_action(oid, required_capabilities=[])
    assert first.runtime_ref == "searxng"
    e.record_attempt(first, outcome="no_new_information")

    second = e.propose_action(oid, required_capabilities=[])
    assert second is not None
    assert second.runtime_ref != "searxng", "the attempted runtime was proposed again"


def test_when_every_runtime_is_exhausted_nothing_is_proposed():
    """Only one runtime exists, so after it is attempted the proposer has nothing
    left and must return None rather than invent a capability (FR-040)."""
    only = [CapabilityDescriptor(runtime_ref="searxng", capabilities=("search",))]
    e = engine(proposer=ActionProposer(only))
    c = seed(e, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q")])
    oid = e.open_obligations(c.context_id)[0].obligation_id

    action = e.propose_action(oid, required_capabilities=[])
    assert action is not None
    e.record_attempt(action, outcome="no_new_information")
    assert e.propose_action(oid, required_capabilities=[]) is None


def test_a_proposal_that_never_ran_is_not_treated_as_an_attempt():
    """FR-059 keys on attempts, not proposals. Skipping merely-proposed work would
    starve the engine of options that were never exercised."""
    e = engine(proposer=ActionProposer(catalogue()))
    c = seed(e, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q")])
    oid = e.open_obligations(c.context_id)[0].obligation_id
    e.propose_action(oid, required_capabilities=[])
    again = e.propose_action(oid, required_capabilities=[])
    assert again is not None and again.runtime_ref == "searxng"


def test_action_memory_records_realised_gain():
    e = engine(proposer=ActionProposer(catalogue()))
    c = seed(e, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q")])
    oid = e.open_obligations(c.context_id)[0].obligation_id
    action = e.propose_action(oid, required_capabilities=[])
    e.record_attempt(action, outcome="partial", realised_gain=0.2)
    entries = e.store.memory_for(oid)
    assert entries[0].realised_gain == 0.2
    assert entries[0].outcome == "partial"


# -- FR-042/044: incremental, explainable revisions ---------------------------

def test_a_tick_commits_a_revision_that_names_its_cause():
    e = engine()
    c = ctx()
    revision, created = e.ingest(c, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q")], event_ids=["evt-1"])
    assert revision.revision == 1
    assert revision.caused_by_event_ids == ("evt-1",)
    assert revision.is_auditable
    assert revision.rules_version == RULES_VERSION


def test_a_tick_with_no_signals_still_commits_but_creates_nothing():
    e = engine()
    c = ctx()
    revision, created = e.ingest(c, [], event_ids=["evt-2"])
    assert created == []
    assert revision.revision == 1


def test_every_decision_is_explainable():
    e = engine()
    c = seed(e, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q", rationale="gap A")])
    decisions = e.recorder.decisions(c.context_id)
    assert decisions
    d = decisions[0]
    assert d.rule_id == RULES_VERSION
    assert d.prior_state == "uninvestigated"
    assert "gap A" in d.detail
    assert e.recorder.explain(d.decision_id) == d


def test_a_tick_touches_only_what_it_was_given():
    """FR-042: incremental. A tick with one signal must not disturb another
    obligation's state."""
    e = engine()
    e.ingest(ctx(), [
        GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q1"),
        GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q2"),
    ], event_ids=["evt-1"])
    c = ctx()
    before = {o.question: o for o in e.open_obligations(c.context_id)}
    e.ingest(c, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q3")], event_ids=["evt-2"])
    after = {o.question: o for o in e.open_obligations(c.context_id)}
    assert after["q1"] == before["q1"]
    assert after["q2"] == before["q2"]


def test_the_mode_is_recorded_on_the_revision():
    e = engine()
    c = ctx()
    det, _ = e.ingest(c, [], event_ids=["e1"], mode="deterministic")
    adaptive, _ = e.ingest(c, [], event_ids=["e2"], mode="adaptive")
    assert det.mode == "deterministic"
    assert adaptive.mode == "adaptive"


# -- FR-026/027: append-only revisions ---------------------------------------

def test_revisions_are_append_only_and_numbered():
    e = engine()
    c = ctx()
    for i in range(3):
        e.ingest(c, [], event_ids=[f"evt-{i}"])
    chain = e.revision_history(c.context_id)
    assert [r.revision for r in chain] == [1, 2, 3]
    assert [r.parent_revision for r in chain] == [0, 1, 2]


def test_re_appending_the_same_revision_is_idempotent():
    e = engine()
    c = ctx()
    _, _ = e.ingest(c, [], event_ids=["e1"])
    r = e.revision_history(c.context_id)[0]
    e.store.append_revision(r)
    assert len(e.revision_history(c.context_id)) == 1


def test_a_different_revision_at_the_same_number_is_refused():
    """Two revisions claiming the same number with different content is a fork in
    history, not a merge. Refused at construction by the address check."""
    e = engine()
    c = ctx()
    e.ingest(c, [], event_ids=["e1"])
    first = e.revision_history(c.context_id)[0]
    with pytest.raises(ValueError, match="revision_id_mismatch"):
        replace(first, snapshot={"tampered": True})


def test_a_tampered_snapshot_cannot_be_appended():
    """And the store refuses a colliding revision number independently of the
    object's own check."""
    store = InMemoryContextStore()
    e = ContextEngine(store)
    c = ctx()
    e.ingest(c, [], event_ids=["e1"])
    first = store.revisions(c.context_id)[0]
    impostor = replace(first)
    object.__setattr__(impostor, "revision_id", "CXR-" + "0" * 32)
    with pytest.raises(ValueError):
        store.append_revision(impostor)


# -- FR-028: replay -----------------------------------------------------------

def test_replay_is_deterministic():
    e = engine()
    c = ctx()
    for i in range(3):
        e.ingest(c, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question=f"q{i}")], event_ids=[f"evt-{i}"])
    first = e.replay(c.context_id)
    second = e.replay(c.context_id)
    assert first == second
    assert first.revisions == 3
    assert first.obligations == 3


def test_replay_of_an_unknown_context_is_an_error_not_an_empty_result():
    e = engine()
    with pytest.raises(ContextEngineError) as exc:
        e.replay("CXI-nonexistent")
    assert exc.value.code == "nothing_to_replay"


# -- FR-050: queries and the frontier -----------------------------------------

def test_the_frontier_is_queryable_and_separates_open_from_closed():
    e = engine()
    c = seed(e, [
        GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q1"),
        GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q2"),
    ])
    frontier = e.rebuild(c.context_id)
    assert len(frontier.open_obligations) == 2
    first = frontier.open_obligations[0]
    e.evaluate_obligation(first, SatisfactionInput(evidence_count=3, saturation=saturated()))
    after = e.rebuild(c.context_id)
    assert len(after.open_obligations) == 1
    assert len(after.closed_obligations) == 1


def test_queries_answer_which_are_open_satisfied_and_contradicted():
    e = engine()
    c = seed(e, [
        GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q1"),
        GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q2"),
        GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q3"),
    ])
    by_q = {o.question: o.obligation_id for o in e.open_obligations(c.context_id)}
    e.evaluate_obligation(by_q["q1"], SatisfactionInput(evidence_count=3, saturation=saturated()))
    e.evaluate_obligation(
        by_q["q2"],
        SatisfactionInput(evidence_count=3, saturation=saturated(), contradicting_evidence=1),
    )
    assert len(e.satisfied_obligations(c.context_id)) == 1
    assert len(e.contradicted_obligations(c.context_id)) == 1
    assert len(e.open_obligations(c.context_id)) == 1


# -- FR-027: durability is a declared property, not an assumption ------------

def test_a_memory_store_declares_itself_in_memory():
    assert InMemoryContextStore().durability() is StoreDurability.MEMORY


def test_production_refuses_a_memory_backed_context():
    """FR-027: context state must survive a restart. A memory store must not be
    wireable where that is required, rather than silently losing the investigation."""
    with pytest.raises(ContextEngineError) as exc:
        ContextEngine(InMemoryContextStore(), require_durable=True)
    assert exc.value.code == "store_not_durable"


# -- FR-097: honesty about unknown --------------------------------------------

def test_an_uninvestigated_context_and_a_closed_one_are_different_facts():
    assert ctx().state is InvestigationState.UNINVESTIGATED
    assert replace(ctx(), state=InvestigationState.CLOSED, context_id=ctx().address()).state is (
        InvestigationState.CLOSED
    )
    assert InvestigationState.UNINVESTIGATED != InvestigationState.EXHAUSTED


def test_saturation_reasons_are_machine_readable():
    s = saturated()
    assert "0.95" in s.reason() and "7" in s.reason()
    assert s.is_saturated is True


def test_saturation_is_not_a_bare_boolean():
    s = SaturationState(
        coverage=0.9, marginal_gain=0.05, distinct_sources=1, source_diversity=0
    )
    assert s.is_saturated is True  # thresholds met even though diversity is nil
    assert "diversity=0" in s.reason()  # ... and the weakness is still reported


# -- FR-035: no silent drops --------------------------------------------------

def test_obligations_with_no_evidence_are_still_reportable_as_open():
    e = engine()
    c = seed(e, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q")])
    assert len(e.open_obligations(c.context_id)) == 1