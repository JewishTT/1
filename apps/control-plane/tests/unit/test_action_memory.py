"""Phase 3 / User Story 1, T045 and T049: action memory, suppression, and its re-open.

FR-045 and FR-059. Two claims are pinned here, and they are easy to confuse with each
other:

1. **A repeated no-gain action is suppressed, with a reason and declared re-open
   conditions.** Not "we will not try that again" -- that is indistinguishable from a
   bug, and an operator handles both by abandoning the tool. So
   :class:`ActionSuppression` refuses to be constructed without a reason *and* without the
   conditions that would lift it.

2. **Failure and no-result are different memory states.** "The source was down" and
   "the source was searched and contains nothing" are separate rows with separate
   addresses. Collapsing them retires questions that were never asked, which is the most
   expensive mistake available to a research loop.

A suppression is lifted by a *declared* condition change -- operator version, scope,
parameters -- and by an explicit override that records why. Not by a retry counter, not
by a timer: the platform has to be able to say exactly which declared change re-admitted
the action.

Hermetic: in-memory store, no clock, no network, no database, no donor component.
"""

from __future__ import annotations

import pytest
from contracts.stage_outcome import CoverageStatement, ErrorClass
from domain.investigation_context import ContextEngineError, InvestigationContext, ObligationStatus

from context_engine.engine import (
    ActionProposer,
    CapabilityDescriptor,
    ContextEngine,
    GapSignal,
    TriggerKind,
)
from context_engine.obligations import (
    ActionMemoryEntry,
    ActionSuppression,
    MemoryState,
    ResearchAction,
    classify_attempt,
    condition_fingerprint,
)
from context_engine.store import InMemoryContextStore

QUESTION = "who owns the registry?"
RUNTIME = "registry.record.extract"

#: The declared conditions an attempt runs under. Changing one of them is the only thing
#: that re-admits a suppressed action.
CONDITIONS_A = {"operator_version": "1.2.0", "scope": "entity:ent-1"}
CONDITIONS_B = {"operator_version": "1.3.0", "scope": "entity:ent-1"}


def _context() -> InvestigationContext:
    return InvestigationContext(
        tenant_id="t-1",
        investigation_id="inv-1",
        title="registry ownership",
        scope_refs=("entity:ent-1",),
        question=QUESTION,
    )


async def _engine_with_one_open_obligation(**kwargs):
    store = InMemoryContextStore()
    engine = ContextEngine(
        store,
        proposer=ActionProposer(
            [
                CapabilityDescriptor(
                    runtime_ref=RUNTIME, capabilities=("entity.extract",), cost_class="cheap"
                )
            ]
        ),
        **kwargs,
    )
    context = _context()
    await store.put_context(context)
    await engine.ingest(
        context,
        (
            GapSignal(
                kind=TriggerKind.COVERAGE_GAP,
                question=QUESTION,
                rationale="no evidence yet",
                required_capabilities=("entity.extract",),
            ),
        ),
        event_ids=["evt-gap-1"],
    )
    return engine, context, (await engine.open_obligations(context.context_id))[0]


async def _attempt(engine, obligation, runtime_ref: str = RUNTIME) -> ResearchAction:
    """A real proposed action, so the attempt key matches what the proposer would use."""
    action = await engine.propose_action(obligation.obligation_id)
    assert action is not None
    assert action.runtime_ref == runtime_ref
    return action


# =============================================================================
# T049 -- memory is persisted, and failure is not no-result
# =============================================================================


async def test_an_attempt_is_persisted_through_the_context_store():
    """T049 names ``ContextStore.remember`` specifically: the memory must survive the call."""
    engine, _, obligation = await _engine_with_one_open_obligation()
    action = await _attempt(engine, obligation)

    await engine.record_attempt(action, outcome="succeeded", realised_gain=0.4)

    stored = await engine.store.memory_for(obligation.obligation_id)
    assert len(stored) == 1
    assert stored[0].obligation_id == obligation.obligation_id
    assert stored[0].attempt_key == f"{RUNTIME}|{QUESTION}"
    assert stored[0].realised_gain == pytest.approx(0.4)


async def test_a_failure_and_a_no_result_are_two_rows_not_one():
    engine, _, obligation = await _engine_with_one_open_obligation()
    action = await _attempt(engine, obligation)

    await engine.record_attempt(
        action, outcome="failed", error_class=ErrorClass.SOURCE_UNAVAILABLE
    )
    await engine.record_attempt(
        action,
        outcome="no_result",
        coverage=CoverageStatement(universe="registered filings", coverage="2020-2026"),
    )

    memory = await engine.action_memory(obligation.obligation_id)
    assert {e.state for e in memory} == {MemoryState.FAILED, MemoryState.NO_RESULT}
    assert len({e.entry_id for e in memory}) == 2


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        ("failed", MemoryState.FAILED),
        ("unsupported", MemoryState.FAILED),
        ("quarantined", MemoryState.FAILED),
        ("no_new_information", MemoryState.NO_GAIN),
        ("no_change", MemoryState.NO_GAIN),
        ("succeeded", MemoryState.GAINED),
        ("partial", MemoryState.GAINED),
        ("approved", MemoryState.PENDING),
    ],
)
def test_a_legacy_outcome_string_maps_to_a_declared_state(outcome: str, expected: MemoryState):
    assert classify_attempt(outcome) is expected


def test_an_outcome_nobody_can_classify_is_no_gain_and_never_a_gain():
    """Reading an unknown outcome as a gain would satisfy an obligation on noise."""
    assert classify_attempt("something-nobody-defined") is MemoryState.NO_GAIN


def test_only_gained_counts_as_evidence():
    assert MemoryState.GAINED.counts_as_evidence is True
    for state in MemoryState:
        if state is not MemoryState.GAINED:
            assert state.counts_as_evidence is False


# =============================================================================
# T045 -- suppression, its reason, and its re-open conditions
# =============================================================================


async def test_a_repeated_no_gain_action_is_suppressed_with_a_reason_and_reopen_conditions():
    engine, _, obligation = await _engine_with_one_open_obligation()
    action = await _attempt(engine, obligation)

    first = await engine.record_attempt(
        action, outcome="no_new_information", conditions=CONDITIONS_A
    )
    assert first.suppression is None, "one unproductive attempt is not yet a pattern"

    second = await engine.record_attempt(
        action, outcome="no_new_information", conditions=CONDITIONS_A
    )
    suppression = second.suppression

    assert suppression is not None
    assert suppression.reason
    assert "2 attempts" in suppression.reason
    assert suppression.attempts_without_gain == 2
    assert suppression.reopen_conditions
    assert any("operator_version" in condition for condition in suppression.reopen_conditions)
    assert suppression.condition_fingerprint == condition_fingerprint(CONDITIONS_A)


async def test_the_suppression_is_readable_after_the_fact():
    engine, _, obligation = await _engine_with_one_open_obligation()
    action = await _attempt(engine, obligation)
    attempt_key = f"{RUNTIME}|{QUESTION}"

    for _ in range(2):
        await engine.record_attempt(
            action, outcome="no_new_information", conditions=CONDITIONS_A
        )

    live = await engine.suppression_for(obligation.obligation_id, attempt_key, conditions=CONDITIONS_A)
    assert live is not None
    assert live.reason


async def test_a_declared_condition_change_lifts_the_suppression():
    engine, _, obligation = await _engine_with_one_open_obligation()
    action = await _attempt(engine, obligation)
    attempt_key = f"{RUNTIME}|{QUESTION}"
    for _ in range(2):
        await engine.record_attempt(
            action, outcome="no_new_information", conditions=CONDITIONS_A
        )

    still = await engine.suppression_for(obligation.obligation_id, attempt_key, conditions=CONDITIONS_A)
    assert still is not None

    lifted = await engine.suppression_for(
        obligation.obligation_id, attempt_key, conditions=CONDITIONS_B
    )
    assert lifted is None, "a declared operator version change did not re-admit the action"


async def test_the_suppressed_action_is_reproposed_only_once_the_conditions_move():
    """The suppression is observable, not merely recorded."""
    engine, _, obligation = await _engine_with_one_open_obligation()
    action = await _attempt(engine, obligation)
    for _ in range(2):
        await engine.record_attempt(
            action, outcome="no_new_information", conditions=CONDITIONS_A
        )

    # Same declared conditions: the memory still blocks it.
    assert await engine.propose_action(obligation.obligation_id, conditions=CONDITIONS_A) is None

    # A declared change: eligible again. The address is unchanged, which is correct --
    # it is the same logical action under new conditions, and FR-065 wants that to be
    # idempotent rather than to mint a second proposal row.
    reproposed = await engine.propose_action(obligation.obligation_id, conditions=CONDITIONS_B)
    assert reproposed is not None
    assert reproposed.action_id == action.action_id


async def test_an_override_must_state_a_reason():
    engine, _, obligation = await _engine_with_one_open_obligation()

    with pytest.raises(ContextEngineError) as caught:
        await engine.override_suppression(
            obligation.obligation_id, f"{RUNTIME}|{QUESTION}", reason="   "
        )
    assert caught.value.code == "override_reason_missing"


async def test_a_recorded_override_re_admits_the_action():
    engine, _, obligation = await _engine_with_one_open_obligation()
    action = await _attempt(engine, obligation)
    attempt_key = f"{RUNTIME}|{QUESTION}"
    for _ in range(2):
        await engine.record_attempt(
            action, outcome="no_new_information", conditions=CONDITIONS_A
        )

    entry = await engine.override_suppression(
        obligation.obligation_id,
        attempt_key,
        reason="the registry published a new schema; the parser has been updated",
        conditions=CONDITIONS_A,
    )
    await engine.store.remember(entry)

    assert await engine.suppression_for(
        obligation.obligation_id, attempt_key, conditions=CONDITIONS_A
    ) is None


@pytest.mark.parametrize("field", ["reason", "reopen_conditions"])
def test_a_suppression_missing_either_half_is_refused(field: str):
    fields = {
        "reason": "two attempts, no gain",
        "attempts_without_gain": 2,
        "condition_fingerprint": "fp",
        "reopen_conditions": ("operator_version changes",),
    }
    fields[field] = "" if field == "reason" else ()
    with pytest.raises(ContextEngineError) as caught:
        ActionSuppression(**fields)
    assert caught.value.code.startswith("suppression_")


def test_a_suppression_is_lifted_only_by_a_different_fingerprint():
    suppression = ActionSuppression(
        reason="two attempts, no gain",
        attempts_without_gain=2,
        condition_fingerprint="fp-a",
        reopen_conditions=("operator_version changes",),
    )
    assert suppression.lifted_by("fp-a") is False
    assert suppression.lifted_by("fp-b") is True


# =============================================================================
# what suppression deliberately does *not* cover
# =============================================================================


async def test_a_no_result_is_not_suppressed_by_default():
    """It is admissible evidence. Re-running against another universe is the right move,
    and the default policy refuses to call that a loop."""
    engine, _, obligation = await _engine_with_one_open_obligation()
    action = await _attempt(engine, obligation)
    attempt_key = f"{RUNTIME}|{QUESTION}"

    for year in ("2020", "2021", "2022"):
        await engine.record_attempt(
            action,
            outcome="no_result",
            coverage=CoverageStatement(universe="registered filings", coverage=year),
            conditions={"universe": year},
        )

    assert await engine.suppression_for(
        obligation.obligation_id, attempt_key, conditions={"universe": "2020"}
    ) is None


async def test_a_repeated_failure_is_suppressed_only_when_the_caller_declares_it():
    default_engine, _, default_obligation = await _engine_with_one_open_obligation()
    default_action = await _attempt(default_engine, default_obligation)
    for _ in range(3):
        await default_engine.record_attempt(
            default_action, outcome="failed", error_class=ErrorClass.SOURCE_UNAVAILABLE
        )
    assert await default_engine.suppression_for(
        default_obligation.obligation_id,
        f"{RUNTIME}|{QUESTION}",
        conditions=CONDITIONS_A,
    ) is None

    strict_engine, _, strict_obligation = await _engine_with_one_open_obligation(
        suppressible_states=(MemoryState.NO_GAIN, MemoryState.FAILED)
    )
    strict_action = await _attempt(strict_engine, strict_obligation)
    for _ in range(2):
        await strict_engine.record_attempt(
            strict_action,
            outcome="failed",
            error_class=ErrorClass.SOURCE_UNAVAILABLE,
            conditions=CONDITIONS_A,
        )
    suppression = await strict_engine.suppression_for(
        strict_obligation.obligation_id, f"{RUNTIME}|{QUESTION}", conditions=CONDITIONS_A
    )
    assert suppression is not None
    assert suppression.attempts_without_gain == 2


# =============================================================================
# the entry itself
# =============================================================================


def test_an_entry_round_trips_through_its_dict():
    entry = ActionMemoryEntry(
        obligation_id="OBL-1",
        attempt_key=f"{RUNTIME}|{QUESTION}",
        outcome="no_result",
        coverage=CoverageStatement(universe="filings", coverage="2020", detection_power=0.8),
        declared_conditions=tuple(sorted(CONDITIONS_A.items())),
        detail="the filings index returned nothing for this entity",
        suppression=ActionSuppression(
            reason="two attempts, no gain",
            attempts_without_gain=2,
            condition_fingerprint=condition_fingerprint(CONDITIONS_A),
            reopen_conditions=("operator_version changes",),
        ),
    )
    assert ActionMemoryEntry.from_dict(entry.to_dict()) == entry


def test_the_condition_fingerprint_is_one_definition_used_by_both_sides():
    """Two implementations here produced two fingerprints that never matched, so a
    suppression was lifted by a condition change that had not happened."""
    assert condition_fingerprint(CONDITIONS_A) == condition_fingerprint(
        dict(reversed(list(CONDITIONS_A.items())))
    )
    assert condition_fingerprint(CONDITIONS_A) != condition_fingerprint(CONDITIONS_B)
    assert condition_fingerprint(None) == "no-declared-conditions"


def test_declared_conditions_are_hashed_into_the_entry_address():
    """Same attempt key, different declared conditions, different rows."""
    a = ActionMemoryEntry(
        obligation_id="OBL-1",
        attempt_key="r|q",
        outcome="no_new_information",
        declared_conditions=tuple(sorted(CONDITIONS_A.items())),
    )
    b = ActionMemoryEntry(
        obligation_id="OBL-1",
        attempt_key="r|q",
        outcome="no_new_information",
        declared_conditions=tuple(sorted(CONDITIONS_B.items())),
    )
    assert a.entry_id != b.entry_id
    assert a.condition_fingerprint != b.condition_fingerprint


async def test_the_attempt_key_is_shared_by_the_proposer_and_the_memory():
    """They used to disagree, so the engine could propose work it had already run."""
    engine, _, obligation = await _engine_with_one_open_obligation()
    action = await _attempt(engine, obligation)
    entry = await engine.record_attempt(action, outcome="no_new_information")

    assert entry.attempt_key == f"{action.runtime_ref}|{obligation.question}"
    assert (await engine.store.get_obligation(obligation.obligation_id)).status is (
        ObligationStatus.OPEN
    )