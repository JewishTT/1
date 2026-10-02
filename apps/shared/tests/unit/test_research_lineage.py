"""Feature 024 T161/T162 -- research lineage, the third lineage.

Fails against the pre-024 state: the word "research" does not appear in
``evidence_lineage.py`` and ``HopKind`` carries no obligation or action hop, so a
chain from intent to outcome was not traversable at all.
"""

from __future__ import annotations

import pytest

from domain.research_lineage import (
    RESEARCH_HOP_ORDER,
    ResearchHop,
    ResearchHopKind,
    ResearchLineage,
    ResearchTrace,
    build_trace,
)

pytestmark = pytest.mark.unit

CXI = "CXI-" + "a" * 32
OBL = "OBL-" + "b" * 32
ACT = "ACT-" + "c" * 32
TSK = "TASK-7"
RES = "OBS-" + "d" * 32
REV = "CXR-" + "e" * 32


def full(outcome: str = "answered") -> ResearchTrace:
    return build_trace(
        context_id=CXI,
        obligation_id=OBL,
        action_id=ACT,
        task_id=TSK,
        result_ref=RES,
        revision_ref=REV,
        outcome=outcome,
    )


# -- the chain itself ---------------------------------------------------------

def test_a_complete_chain_carries_all_six_hops():
    trace = full()
    assert [h.kind.value for h in trace.hops] == list(RESEARCH_HOP_ORDER)
    assert trace.complete is True


def test_the_chain_runs_from_intent_to_outcome():
    trace = full()
    assert trace.hops[0].ref == CXI
    assert trace.hops[-1].ref == REV


def test_hops_must_stay_in_order():
    with pytest.raises(ValueError, match="out of order"):
        ResearchTrace(
            context_id=CXI,
            hops=(
                ResearchHop(ResearchHopKind.ACTION, ACT),
                ResearchHop(ResearchHopKind.OBLIGATION, OBL),
            ),
        )


def test_a_hop_must_reference_something():
    with pytest.raises(ValueError):
        ResearchHop(ResearchHopKind.CONTEXT, "")


# -- incompleteness is reported, never truncated quietly ----------------------

def test_a_chain_that_stopped_short_is_not_complete():
    trace = build_trace(context_id=CXI, obligation_id=OBL)
    assert trace.complete is False
    assert trace.break_at == "action"


def test_a_broken_chain_names_exactly_where_it_stopped():
    trace = build_trace(context_id=CXI, obligation_id=OBL, action_id=ACT, task_id=TSK)
    assert trace.break_at == "result"


def test_an_unstarted_obligation_is_distinguishable_from_an_empty_result():
    """The research analogue of unknown-vs-empty: no action was taken, which is not
    the same as an action that produced nothing."""
    unstarted = build_trace(context_id=CXI, obligation_id=OBL)
    produced_nothing = build_trace(
        context_id=CXI,
        obligation_id=OBL,
        action_id=ACT,
        task_id=TSK,
        outcome="no_result",
    )
    assert unstarted.break_at == "action"
    assert produced_nothing.break_at == "result"


def test_an_incomplete_chain_cannot_claim_to_be_answered():
    trace = build_trace(context_id=CXI, obligation_id=OBL, outcome="answered")
    assert trace.outcome == "open"


# -- forward: what came of an obligation --------------------------------------

def test_forward_from_an_obligation_finds_its_chain():
    lineage = ResearchLineage([full()])
    assert lineage.for_obligation(OBL)[0].obligation_ids == (OBL,)


def test_forward_from_an_action_finds_its_chain():
    lineage = ResearchLineage([full()])
    assert lineage.for_action(ACT)[0].action_ids == (ACT,)


def test_a_context_lists_the_obligations_it_generated():
    lineage = ResearchLineage([full()])
    assert lineage.obligations_for(CXI) == (OBL,)


def test_an_unknown_obligation_returns_nothing_rather_than_inventing():
    assert ResearchLineage([full()]).for_obligation("OBL-nope") == ()


# -- backward: why was this result sought -------------------------------------

def test_backward_from_a_result_explains_the_obligation_that_sought_it():
    """The question neither other lineage can answer."""
    lineage = ResearchLineage([full()])
    trace = lineage.explain_result(RES)
    assert trace is not None
    assert trace.obligation_ids == (OBL,)
    assert trace.action_ids == (ACT,)


def test_backward_from_a_revision_reports_what_it_revised():
    lineage = ResearchLineage([full()])
    assert lineage.what_revised(REV).obligation_ids == (OBL,)


def test_an_unknown_result_explains_nothing():
    assert ResearchLineage([full()]).explain_result("OBS-nope") is None


# -- honesty ------------------------------------------------------------------

def test_obligations_without_a_result_are_reportable_as_unanswered():
    lineage = ResearchLineage(
        [
            full(),
            build_trace(
                context_id=CXI,
                obligation_id="OBL-" + "9" * 32,
                action_id="ACT-" + "8" * 32,
            ),
        ]
    )
    unanswered = lineage.unanswered(CXI)
    assert "OBL-" + "9" * 32 in unanswered
    assert OBL not in unanswered


def test_a_second_trace_for_the_same_result_is_indexed_once_per_result():
    lineage = ResearchLineage([full(), full()])
    assert len(lineage) == 2
    assert lineage.explain_result(RES).obligation_ids == (OBL,)


def test_traces_are_scoped_to_their_context():
    lineage = ResearchLineage([full()])
    assert lineage.context_traces("CXI-other") == ()
    assert lineage.obligations_for("CXI-other") == ()


def test_a_trace_round_trips():
    trace = full()
    restored = ResearchTrace(
        context_id=trace.context_id,
        hops=tuple(ResearchHop.from_dict(h.to_dict()) for h in trace.hops),
        outcome=trace.outcome,
        break_at=trace.break_at,
    )
    assert restored == trace