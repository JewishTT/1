"""The approval gate must gate, not merely advise (spec 030 FR-095, T164).

``CognitiveLoop._propose`` returned an action that requires operator approval in **both**
tuples: it landed in ``awaiting_approval`` *and* in ``proposed``. Since ``proposed`` becomes
``LoopStep.actions_proposed``, and that is what a scheduler consumes to decide what to run,
the gate was advisory. Anything reading the obvious field would execute an action nobody had
approved, and the only thing warning it was a second field listing the same id.

These use the real proposer rather than a stub: ``ActionProposer`` sets
``requires_operator_approval=True`` by default, which is exactly the case the loop was letting
through.
"""

from __future__ import annotations

import pytest
from domain.investigation_context import InvestigationContext

from context_engine.engine import (
    ActionProposer,
    CapabilityDescriptor,
    ContextEngine,
    GapSignal,
    TriggerKind,
)
from context_engine.loop import CognitiveLoop
from context_engine.store import InMemoryContextStore

pytestmark = pytest.mark.unit


def _signal() -> list[GapSignal]:
    return [GapSignal(kind=TriggerKind.COVERAGE_GAP, question="who owns acme?")]


def _ctx() -> InvestigationContext:
    return InvestigationContext(
        tenant_id="t1", investigation_id="INV-1", scope_refs=("acme.example",)
    )


def _loop() -> CognitiveLoop:
    return CognitiveLoop(
        ContextEngine(
            InMemoryContextStore(),
            proposer=ActionProposer(
                [CapabilityDescriptor(runtime_ref="searxng", capabilities=("search",))]
            ),
        )
    )


async def _seed(lp: CognitiveLoop) -> tuple[InvestigationContext, str]:
    """Open one obligation directly, so a tick afterwards has something to propose for."""
    c = _ctx()
    await lp.engine.store.put_context(c)
    _, created = await lp.engine.ingest(c, _signal())
    return c, created[0].obligation_id


async def _tick_with_one_obligation(lp: CognitiveLoop, **kw):
    c, _ = await _seed(lp)
    return await lp.tick(c, **kw)


class TestTheGateGates:
    async def test_the_real_proposer_does_require_approval(self):
        """Premise of every test below. If this stops holding, the file is testing nothing."""
        lp = _loop()
        c = _ctx()
        _, created = await lp.engine.ingest(c, _signal())
        action = await lp.engine.propose_action(created[0].obligation_id)
        assert action is not None
        assert action.requires_operator_approval is True

    async def test_an_unapproved_action_is_reported_as_awaiting(self):
        step = await _tick_with_one_obligation(_loop())
        assert step.awaiting_approval, "the loop proposed nothing and gated nothing"

    async def test_an_unapproved_action_is_not_in_actions_proposed(self):
        step = await _tick_with_one_obligation(_loop())
        assert set(step.actions_proposed) & set(step.awaiting_approval) == set()

    async def test_the_two_sets_do_not_overlap(self):
        """The overlap is the whole defect. Asserted directly so it cannot regress quietly."""
        step = await _tick_with_one_obligation(_loop())
        overlap = set(step.actions_proposed) & set(step.awaiting_approval)
        assert overlap == set(), f"an action was both runnable and awaiting approval: {overlap}"

    async def test_nothing_runnable_is_proposed_before_approval(self):
        step = await _tick_with_one_obligation(_loop())
        assert step.actions_proposed == ()


class TestApprovalClearsTheGate:
    async def test_an_approved_action_leaves_the_awaiting_set(self):
        lp = _loop()
        c, _ = await _seed(lp)
        gated = (await lp.tick(c)).awaiting_approval
        assert gated, "nothing was gated to approve in the first place"

        step = await lp.tick(c, approved_action_ids=list(gated))
        assert not (set(step.awaiting_approval) & set(gated))

    async def test_approving_a_different_id_does_not_clear_the_gate(self):
        lp = _loop()
        c, _ = await _seed(lp)
        step = await lp.tick(c, approved_action_ids=["ACT-someone-else"])
        assert set(step.actions_proposed) & set(step.awaiting_approval) == set()
        assert step.actions_proposed == ()