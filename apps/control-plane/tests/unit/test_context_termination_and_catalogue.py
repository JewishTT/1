"""Feature 024 Phase 5/6 -- termination, re-opening, autonomous proposal, D4 bridge.

The behaviours that were impossible before: an investigation that can say why it
stopped, a closed investigation that re-opens on contradiction without erasing the
record of its closure, and a planner that routes by ``runtime_ref`` while gating on
declarative capabilities from the Source/Tool Catalogue.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from domain.investigation_context import ContextEngineError, InvestigationContext

from context_engine.catalogue_bridge import SourceCatalogueBridge
from context_engine.engine import (
    ActionProposer,
    ContextEngine,
    GapSignal,
    SatisfactionInput,
    TriggerKind,
)
from context_engine.obligations import ObligationStatus, SaturationState
from context_engine.store import InMemoryContextStore

pytestmark = pytest.mark.unit


def ctx(**over) -> InvestigationContext:
    base = {"tenant_id": "t1", "investigation_id": "INV-1", "scope_refs": ("acme.example",)}
    base.update(over)
    return InvestigationContext(**base)


def engine(**kw) -> ContextEngine:
    return ContextEngine(InMemoryContextStore(), **kw)


def saturated() -> SaturationState:
    return SaturationState(coverage=0.95, marginal_gain=0.01, distinct_sources=6, source_diversity=4)


def seed_all_satisfied(e: ContextEngine, c: InvestigationContext) -> None:
    e.ingest(c, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question=f"q{i}") for i in range(3)])
    for o in e.open_obligations(c.context_id):
        e.evaluate_obligation(o.obligation_id, SatisfactionInput(evidence_count=4, saturation=saturated()))


# -- FR-057: termination is never silent --------------------------------------

def test_a_fully_resolved_context_is_terminal():
    e = engine()
    c = ctx()
    seed_all_satisfied(e, c)
    report = e.termination_report(c.context_id)
    assert report.is_terminal is True
    assert report.still_unknown == ()


def test_an_investigation_with_open_work_is_not_terminal():
    e = engine()
    c = ctx()
    e.ingest(c, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q")])
    assert e.termination_report(c.context_id).is_terminal is False


def test_the_report_states_what_remains_unknown():
    e = engine()
    c = ctx()
    e.ingest(c, [
        GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q1"),
        GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q2"),
    ])
    by_question = {o.question: o.obligation_id for o in e.open_obligations(c.context_id)}
    e.evaluate_obligation(by_question["q1"], SatisfactionInput(evidence_count=4, saturation=saturated()))
    report = e.termination_report(c.context_id)
    assert report.still_unknown == ("q2",)
    assert report.is_terminal is False


def test_every_closed_obligation_carries_its_reason_into_the_report():
    e = engine()
    c = ctx()
    seed_all_satisfied(e, c)
    report = e.termination_report(c.context_id)
    satisfied = report.reasons_by_status["satisfied"]
    assert len(satisfied) == 3
    assert all(r["reason"] for r in satisfied)
    assert all("coverage=0.95" in r["reason"] for r in satisfied)


def test_the_report_names_what_would_reopen_the_investigation():
    """FR-057: termination must record what would overturn it."""
    e = engine()
    c = ctx()
    seed_all_satisfied(e, c)
    report = e.termination_report(c.context_id)
    assert len(report.would_reopen_on) == 3
    assert all(r["trigger"] == "contradicting evidence" for r in report.would_reopen_on)


def test_a_blocked_obligation_keeps_the_investigation_open():
    e = engine()
    c = ctx()
    e.ingest(c, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q")])
    oid = e.open_obligations(c.context_id)[0].obligation_id
    e.evaluate_obligation(
        oid, SatisfactionInput(evidence_count=4, saturation=saturated(), contradicting_evidence=1)
    )
    assert e.termination_report(c.context_id).is_terminal is False


def test_termination_report_of_an_unknown_context_is_an_error():
    e = engine()
    with pytest.raises(ContextEngineError) as exc:
        e.termination_report("CXI-nope")
    assert exc.value.code == "context_unknown"


# -- FR-076: re-opening ------------------------------------------------------

def test_a_closed_investigation_reopens_on_contradiction():
    e = engine()
    c = ctx()
    seed_all_satisfied(e, c)
    assert e.termination_report(c.context_id).is_terminal is True

    revision = e.reopen(c.context_id, reason="new evidence contradicts the owner", event_ids=["evt-9"])
    assert revision.revision > 1
    assert e.store.get_context(c.context_id).state.value == "active"


def test_reopening_does_not_erase_the_closure_from_history():
    """The terminal state must survive in the chain. Flipping the state back would
    erase the fact that the investigation had been declared finished."""
    e = engine()
    c = ctx()
    seed_all_satisfied(e, c)
    before = len(e.revision_history(c.context_id))
    e.reopen(c.context_id, reason="contradiction", event_ids=["evt-9"])
    chain = e.revision_history(c.context_id)
    assert len(chain) == before + 1
    assert [r.revision for r in chain] == list(range(1, len(chain) + 1))


def test_reopening_is_recorded_as_an_explainable_decision():
    e = engine()
    c = ctx()
    seed_all_satisfied(e, c)
    e.reopen(c.context_id, reason="contradicted", event_ids=["evt-9"])
    decisions = [d for d in e.recorder.decisions(c.context_id) if d.kind == "context_reopened"]
    assert len(decisions) == 1
    assert decisions[0].prior_state == "uninvestigated"
    assert decisions[0].outcome == "active"
    assert decisions[0].detail == "contradicted"


def test_reopening_records_the_operator_action():
    e = engine()
    c = ctx()
    seed_all_satisfied(e, c)
    revision = e.reopen(c.context_id, reason="r", event_ids=["e1"])
    assert revision.operator_actions == ("reopen",)


# -- FR-060: autonomous proposal ---------------------------------------------

def test_a_contradicted_obligation_proposes_a_new_question():
    e = engine()
    c = ctx()
    e.ingest(c, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="who owns acme?")])
    oid = e.open_obligations(c.context_id)[0].obligation_id
    e.evaluate_obligation(
        oid, SatisfactionInput(evidence_count=4, saturation=saturated(), contradicting_evidence=2)
    )
    proposals = e.propose_hypotheses(c.context_id)
    assert any("contradiction" in p.question for p in proposals)


def test_an_open_obligation_proposes_a_coverage_gap():
    e = engine()
    c = ctx()
    e.ingest(c, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="who owns acme?")])
    proposals = e.propose_hypotheses(c.context_id)
    assert any(p.question == "who owns acme?" for p in proposals)


def test_low_confidence_produces_a_confidence_raising_question():
    """Targets a *settled* obligation resting on thin evidence.

    Reachable through abandonment: a satisfied obligation always carries
    ``confidence >= coverage_threshold`` (0.9) by construction, so "settled but
    shaky" can only arrive by closing a question without convincing evidence --
    which is precisely the loose end worth revisiting.
    """
    e = engine()
    c = ctx()
    e.ingest(c, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q", priority=0.1)])
    oid = e.open_obligations(c.context_id)[0].obligation_id
    e.abandon_obligation(oid, reason="source space exhausted without an answer")
    proposals = e.propose_hypotheses(c.context_id)
    assert any("raise confidence" in p.question for p in proposals)


def test_an_open_obligation_is_never_restated_as_a_confidence_question():
    """The two rules do not overlap: an open obligation proposes the gap, not a
    rewording of itself."""
    e = engine()
    c = ctx()
    e.ingest(c, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="who owns acme?")])
    questions = [p.question for p in e.propose_hypotheses(c.context_id)]
    assert "who owns acme?" in questions
    assert "raise confidence on: who owns acme?" not in questions


# -- FR-035: abandonment is a terminal state with a reason -------------------

def test_an_abandoned_obligation_records_its_reason():
    e = engine()
    c = ctx()
    e.ingest(c, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q")])
    oid = e.open_obligations(c.context_id)[0].obligation_id
    abandoned = e.abandon_obligation(oid, reason="source space exhausted")
    assert abandoned.status is ObligationStatus.ABANDONED
    assert abandoned.disposition_reason == "source space exhausted"


def test_an_abandonment_without_a_reason_is_refused():
    e = engine()
    c = ctx()
    e.ingest(c, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q")])
    oid = e.open_obligations(c.context_id)[0].obligation_id
    with pytest.raises(ContextEngineError) as exc:
        e.abandon_obligation(oid, reason="   ")
    assert exc.value.code == "abandon_reason_missing"


def test_an_abandoned_obligation_is_not_left_open():
    """FR-035: nothing is silently dropped. Abandonment closes the item and says why."""
    e = engine()
    c = ctx()
    e.ingest(c, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q")])
    oid = e.open_obligations(c.context_id)[0].obligation_id
    e.abandon_obligation(oid, reason="unanswerable from available sources")
    assert e.open_obligations(c.context_id) == ()
    report = e.termination_report(c.context_id)
    assert report.is_terminal is True
    assert "unanswerable from available sources" in str(report.reasons_by_status)


def test_a_settled_investigation_still_reports_its_abandoned_reasons():
    e = engine()
    c = ctx()
    e.ingest(c, [
        GapSignal(kind=TriggerKind.COVERAGE_GAP, question="answerable"),
        GapSignal(kind=TriggerKind.COVERAGE_GAP, question="unanswerable"),
    ])
    by_q = {o.question: o.obligation_id for o in e.open_obligations(c.context_id)}
    e.evaluate_obligation(
        by_q["answerable"], SatisfactionInput(evidence_count=4, saturation=saturated())
    )
    e.abandon_obligation(by_q["unanswerable"], reason="no public record exists")
    report = e.termination_report(c.context_id)
    assert report.is_terminal is True
    assert report.reasons_by_status["abandoned"][0]["reason"] == "no public record exists"


def test_proposal_order_is_by_priority_then_question():
    """A function of state, not of call order -- which is what makes it auditable."""
    e = engine()
    c = ctx()
    e.ingest(c, [
        GapSignal(kind=TriggerKind.COVERAGE_GAP, question="b", priority=0.9),
        GapSignal(kind=TriggerKind.COVERAGE_GAP, question="a", priority=0.9),
        GapSignal(kind=TriggerKind.COVERAGE_GAP, question="c", priority=0.2),
    ])
    first = [p.question for p in e.propose_hypotheses(c.context_id)]
    second = [p.question for p in e.propose_hypotheses(c.context_id)]
    assert first == second
    assert first.index("a") < first.index("b") < first.index("c")


def test_proposals_are_bounded():
    e = engine()
    c = ctx()
    e.ingest(c, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question=f"q{i}") for i in range(20)])
    assert len(e.propose_hypotheses(c.context_id, max_proposals=3)) == 3


def test_every_proposal_names_the_rule_that_produced_it():
    e = engine()
    c = ctx()
    e.ingest(c, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q")])
    for p in e.propose_hypotheses(c.context_id):
        assert p.created_by


# -- FR-040 + D4: the catalogue bridge ---------------------------------------

@dataclass
class FakeSourceDefinition:
    """Shape-mimics ``catalogue.SourceDefinition`` closely enough to be a real test."""

    source_id: str
    runtime_ref: str
    capabilities: tuple[str, ...] = ()
    applies_to: tuple[str, ...] = ()
    contact: str = ""
    cost_class: str = "cheap"
    active: bool = True


CATALOGUE = [
    FakeSourceDefinition("SRC-a", "searxng", capabilities=("search", "http"), applies_to=("domain",)),
    FakeSourceDefinition("SRC-b", "airbyte", capabilities=("structured", "streaming"), cost_class="expensive"),
    FakeSourceDefinition("SRC-c", "bbot", capabilities=("recon", "dns")),
]


def bridge() -> SourceCatalogueBridge:
    return SourceCatalogueBridge.from_source_definitions(CATALOGUE)


def test_the_bridge_reads_declarative_capabilities():
    index = bridge().capability_index()
    assert index["search"] == ("searxng",)
    assert index["structured"] == ("airbyte",)
    assert "applies:domain" in index


def test_capabilities_gate_but_never_choose_the_runtime():
    """D4/FR-067: routing identity is the runtime_ref. The bridge checks the runtime
    it was given; it never searches for a different one."""
    b = bridge()
    decision = b.check("searxng", ["search"])
    assert decision.runtime_ref == "searxng"
    assert decision.capability_match is True


def test_an_incompatible_runtime_is_refused_with_the_missing_capability():
    decision = bridge().check("searxng", ["search", "telepathy"])
    assert decision.capability_match is False
    assert "telepathy" in decision.reason


def test_an_unknown_runtime_is_refused_rather_than_searched_for():
    decision = bridge().check("nonexistent", ["search"])
    assert decision.capability_match is False
    assert "not in the catalogue" in decision.reason


def test_a_missing_capability_is_reported_as_a_stated_requirement():
    """FR-040: surface the gap, do not implement it."""
    report = bridge().missing_capability_report(["search", "telepathy"])
    assert report["search"] == ("searxng",)
    assert report["telepathy"] == ()


def test_a_definition_with_no_declared_capabilities_is_skipped():
    b = SourceCatalogueBridge.from_source_definitions([FakeSourceDefinition("SRC-x", "x")])
    assert b.descriptors() == ()


def test_the_bridge_feeds_the_action_proposer():
    """End to end: declarative capabilities become proposable actions."""
    b = bridge()
    proposer = ActionProposer(b.descriptors())
    e = ContextEngine(InMemoryContextStore(), proposer=proposer)
    c = ctx()
    e.ingest(c, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="who owns acme?")])
    oid = e.open_obligations(c.context_id)[0].obligation_id

    action = e.propose_action(oid, required_capabilities=["search"])
    assert action is not None
    assert action.runtime_ref == "searxng"
    assert action.capability_requirements == ("search",)

    assert b.check(action.runtime_ref, action.capability_requirements).capability_match is True


def test_the_bridge_refuses_an_action_it_cannot_verify():
    b = bridge()
    proposer = ActionProposer(b.descriptors())
    e = ContextEngine(InMemoryContextStore(), proposer=proposer)
    c = ctx()
    e.ingest(c, [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="q")])
    oid = e.open_obligations(c.context_id)[0].obligation_id
    assert e.propose_action(oid, required_capabilities=["telepathy"]) is None