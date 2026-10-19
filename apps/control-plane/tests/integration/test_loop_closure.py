"""Phase 3 / User Story 1: an investigation closes for a reason, and the reason is checkable.

Spec 030 T041-T044, T046-T048, T050, T051. Written against the public surface --
``ContextEngine``, ``CognitiveLoop`` -- rather than internals, because the claim being
made is about behaviour a caller observes.

The tests here are mostly about refusals. Each one pins a thing the platform must *not*
be able to do:

* no obligation that is merely "absent" (T041). An unanswered question always yields an
  obligation carrying its trigger, its acceptance criteria and the capability it needs.
* no satisfaction from a source that could not look (T042). The single most expensive
  conflation in an investigation is "we could not see it" and "it is not there", and it
  is refused structurally: the obligation goes ``blocked`` and names the capability.
* no convergence from disagreement (T043). Two contradicting supports both persist, a
  contradiction opens, and the board does not become terminal.
* no terminal state without a reason from the allowed table (T044), and no stop reason
  drawn from the five things FR-046 forbids -- empty results, task count, exhausted
  retries, model confidence, workflow expiry.
* no satisfaction by a raw hit count (T048). A verdict is a function of the obligation's
  *declared acceptance criteria*; ``evidence_count`` bounds how much was looked at and
  never decides anything on its own.

Hermetic: in-memory store, no clock, no network, no database, no donor component.
"""

from __future__ import annotations

import inspect

import pytest
from contracts.stage_outcome import (
    CoverageStatement,
    ErrorClass,
    StageOutcomeError,
    StageStatus,
)
from domain.investigation_context import (
    ContextEngineError,
    InvestigationContext,
    ObligationStatus,
)

from context_engine.engine import (
    FORBIDDEN_STOP_REASONS,
    RULES_VERSION,
    ContextEngine,
    GapSignal,
    SatisfactionInput,
    SatisfactionVerdict,
    StopReason,
    TriggerKind,
    assert_components_are_separate,
    assert_publication_is_single,
    require_real_stop_reason,
)
from context_engine.loop import CognitiveLoop, LoopStatus, ObservationOutcome
from context_engine.obligations import (
    PRIORITY_COMPONENT_NAMES,
    Disposition,
    KnowledgeType,
    MemoryState,
    ObligationTrigger,
    PriorityComponents,
    SaturationState,
)
from context_engine.store import (
    ContextChange,
    InMemoryChangePublisher,
    InMemoryContextStore,
    SqlOutboxChangePublisher,
    outbox_enqueue_contract,
)

QUESTION = "who owns the registry?"


def _context(question: str = QUESTION) -> InvestigationContext:
    return InvestigationContext(
        tenant_id="t-1",
        investigation_id="inv-1",
        title="registry ownership",
        scope_refs=("entity:ent-1",),
        question=question,
    )


def _saturated(coverage: float = 0.95, gain: float = 0.01) -> SaturationState:
    return SaturationState(
        coverage=coverage,
        marginal_gain=gain,
        distinct_sources=4,
        source_diversity=3,
    )


async def _seeded(
    *,
    signals: tuple[GapSignal, ...] | None = None,
    publisher=None,
):
    """An engine holding one obligation, created through the real ingest path.

    Not a hand-built ``ResearchObligation``: a test that fabricates its own fixture can
    pass while the production path that creates obligations is broken.
    """
    store = InMemoryContextStore()
    engine = ContextEngine(store, publisher=publisher) if publisher else ContextEngine(store)
    context = _context()
    await store.put_context(context)
    await engine.ingest(
        context,
        signals
        or (
            GapSignal(
                kind=TriggerKind.COVERAGE_GAP,
                question=QUESTION,
                rationale="no evidence yet for the ownership claim",
                knowledge_type=KnowledgeType.ENTITY,
                required_capabilities=("registry.record.extract",),
                event_id="evt-gap-1",
                evidence_refs=("OBS-seed",),
            ),
        ),
        event_ids=["evt-gap-1"],
    )
    return engine, context


# =============================================================================
# T041 -- an unanswered question is an obligation, never an "absent" state
# =============================================================================


async def test_an_empty_question_emits_an_obligation_with_its_full_declaration():
    engine, context = await _seeded()
    obligations = await engine.store.obligations(context.context_id)

    assert len(obligations) == 1, "an unanswered question must leave work on the board"
    obligation = obligations[0]

    assert obligation.status is ObligationStatus.OPEN
    # trigger: kind, event id, rule id *and* version, exact reason, evidence refs
    trigger = obligation.trigger
    assert trigger is not None, "an obligation with no trigger is a gap nobody can justify"
    assert trigger.kind == TriggerKind.COVERAGE_GAP.value
    assert trigger.event_id == "evt-gap-1"
    assert trigger.rule_id == TriggerKind.COVERAGE_GAP.value
    assert trigger.rule_version == RULES_VERSION
    assert trigger.reason == "no evidence yet for the ownership claim"
    assert trigger.evidence_refs == ("OBS-seed",)
    # acceptance criteria: declared, nameable, and not an empty tuple
    assert obligation.acceptance_criteria
    for criterion in obligation.acceptance_criteria:
        assert criterion.criterion_id
        assert criterion.statement
    # required capability
    assert obligation.required_capabilities == ("registry.record.extract",)
    assert obligation.missing_capabilities == ("registry.record.extract",)


async def test_a_question_with_no_evidence_still_terminates_nothing():
    """FR-039: a gap does not disappear because nothing came back.

    This is the "absent" state being refused. A caller that searched and found nothing, a
    caller that never searched, and a caller whose function returned an empty list all
    arrive at the same place: an obligation that is still open and a report that is not
    terminal.
    """
    engine, context = await _seeded()
    report = await engine.termination_report(context.context_id)

    assert report.is_terminal is False
    assert report.stop_reason is None
    assert report.still_unknown == (QUESTION,)
    assert [scope.obligation_id for scope in report.unexecuted_scope] == [
        o.obligation_id for o in await engine.store.obligations(context.context_id)
    ]


async def test_an_empty_signal_list_does_not_retire_an_existing_obligation():
    """A generator that returns nothing this pass must not close last pass's work."""
    engine, context = await _seeded()
    await engine.ingest(context, (), event_ids=["evt-tick-2"])

    assert len(await engine.open_obligations(context.context_id)) == 1


async def test_the_declared_block_survives_a_dict_round_trip():
    """An obligation an analyst cannot read back is an assertion, not a record."""
    engine, context = await _seeded()
    original = (await engine.store.obligations(context.context_id))[0]
    restored = type(original).from_dict(original.to_dict())

    assert restored == original
    assert restored.trigger == original.trigger
    assert restored.acceptance_criteria == original.acceptance_criteria


# =============================================================================
# T046 -- the trigger block is complete, and its absence is refused
# =============================================================================


@pytest.mark.parametrize("missing", ["kind", "rule_id", "rule_version", "reason"])
def test_a_trigger_missing_any_required_part_is_refused(missing: str):
    fields = {
        "kind": "coverage_gap",
        "rule_id": "coverage_gap",
        "rule_version": RULES_VERSION,
        "reason": "nothing found",
    }
    fields[missing] = "   "
    with pytest.raises(ContextEngineError) as caught:
        ObligationTrigger(**fields)
    assert caught.value.code == "trigger_block_incomplete"


def test_an_operator_intent_trigger_declares_the_absence_of_an_event():
    """No prior event is a fact about the trigger's kind, not a forgotten field."""
    trigger = ObligationTrigger(
        kind=TriggerKind.OPERATOR_INTENT.value,
        rule_id="operator_intent",
        rule_version=RULES_VERSION,
        reason="the operator asked this directly",
    )
    assert trigger.event_id == ""
    assert trigger.to_dict()["event_id"] == ""


# =============================================================================
# T047 -- unestimated priority components are null, never 0.0
# =============================================================================


def test_an_unestimated_component_is_null_and_never_zero():
    components = PriorityComponents()

    assert components.estimated() == {}
    assert components.basis == "unestimated"
    for name, value in components.to_dict().items():
        assert value is None, f"{name} defaulted to {value!r} instead of staying unestimated"


def test_an_unestimated_component_vector_scores_to_null_not_zero():
    """The dangerous direction: a fabricated 0.0 ranks a promising action last."""
    assert PriorityComponents().score() is None
    # Every component explicitly unestimated is still "unestimated", not "measured as 0".
    assert PriorityComponents(**{name: None for name in PRIORITY_COMPONENT_NAMES}).score() is None


def test_estimating_one_component_does_not_drag_the_rest_to_zero():
    components = PriorityComponents(relevance=0.8)
    score = components.score()

    assert score == pytest.approx(0.8)
    assert components.to_dict()["novelty"] is None


async def test_the_generator_names_its_priority_basis_rather_than_inventing_a_zero():
    engine, context = await _seeded(
        signals=(
            GapSignal(
                kind=TriggerKind.COVERAGE_GAP,
                question=QUESTION,
                rationale="nobody has ranked this",
            ),
        )
    )
    obligation = (await engine.store.obligations(context.context_id))[0]

    assert obligation.priority_basis == "defaulted"
    assert obligation.priority_components.score() is None
    payload = obligation.to_dict()["priority_components"]
    assert set(payload.values()) == {None}


async def test_a_declared_priority_beats_a_derived_one():
    engine, context = await _seeded(
        signals=(
            GapSignal(
                kind=TriggerKind.COVERAGE_GAP,
                question=QUESTION,
                priority=0.11,
                priority_components=PriorityComponents(relevance=0.99),
            ),
        )
    )
    obligation = (await engine.store.obligations(context.context_id))[0]

    assert obligation.priority == pytest.approx(0.11)
    assert obligation.priority_basis == "declared"


async def test_a_component_vector_is_used_when_no_scalar_was_declared():
    engine, context = await _seeded(
        signals=(
            GapSignal(
                kind=TriggerKind.COVERAGE_GAP,
                question=QUESTION,
                priority_components=PriorityComponents(relevance=0.4, novelty=0.2),
            ),
        )
    )
    obligation = (await engine.store.obligations(context.context_id))[0]

    assert obligation.priority_basis.startswith("derived:")
    assert 0.0 < obligation.priority < 1.0


# =============================================================================
# T042 -- a source failure does not satisfy an obligation
# =============================================================================


async def test_a_source_failure_blocks_the_obligation_and_names_the_missing_capability():
    engine, context = await _seeded()
    obligation = (await engine.open_obligations(context.context_id))[0]

    verdict = await engine.evaluate_obligation(
        obligation.obligation_id,
        SatisfactionInput(
            evidence_count=0,
            # The most dangerous shape: full coverage and no residual gain, so a
            # system reading "no evidence" as "nothing there" would close it happily.
            saturation=_saturated(),
            stage_status=StageStatus.FAILED,
            error_class=ErrorClass.SOURCE_UNAVAILABLE,
            missing_capabilities=("registry.record.extract",),
        ),
    )
    blocked = await engine.store.get_obligation(obligation.obligation_id)

    assert verdict.satisfied is False
    assert blocked.status is ObligationStatus.BLOCKED
    assert blocked.disposition is Disposition.BLOCKED
    assert "registry.record.extract" in blocked.disposition_reason
    assert verdict.missing_capabilities == ("registry.record.extract",)


async def test_a_missing_capability_alone_blocks_even_at_full_coverage():
    engine, context = await _seeded()
    obligation = (await engine.open_obligations(context.context_id))[0]

    verdict = await engine.evaluate_obligation(
        obligation.obligation_id,
        SatisfactionInput(
            evidence_count=9,
            saturation=_saturated(),
            missing_capabilities=("registry.record.extract",),
        ),
    )

    assert verdict.satisfied is False
    assert any(b.names_a_capability for b in verdict.blockers)
    assert "could not look" in verdict.reason


async def test_a_no_result_with_a_coverage_statement_still_does_not_discharge():
    """Contract 03: a qualified absence is admissible evidence, not a discharge."""
    engine, context = await _seeded()
    obligation = (await engine.open_obligations(context.context_id))[0]

    verdict = await engine.evaluate_obligation(
        obligation.obligation_id,
        SatisfactionInput(
            evidence_count=0,
            saturation=_saturated(),
            stage_status=StageStatus.NO_RESULT,
            error_class=ErrorClass.EXPECTED_NO_RESULT,
            coverage=CoverageStatement(universe="registered filings", coverage="2020-2026"),
        ),
    )

    assert verdict.satisfied is False
    assert any(b.kind == "stage_status" for b in verdict.blockers)
    assert "no_result does not discharge" in verdict.reason


def test_a_no_result_without_a_coverage_statement_is_refused_at_construction():
    from contracts.stage_outcome import StageOutcome

    with pytest.raises(StageOutcomeError):
        StageOutcome(status=StageStatus.NO_RESULT, error_class=ErrorClass.EXPECTED_NO_RESULT)


async def test_failure_and_no_result_are_different_memory_states():
    """Invariant 8, made observable: the two never collapse into one another."""
    from context_engine.obligations import ResearchAction

    engine, context = await _seeded()
    obligation = (await engine.open_obligations(context.context_id))[0]

    action = ResearchAction(
        obligation_id=obligation.obligation_id,
        proposed_method="acquire via registry",
        runtime_ref="registry",
    ).with_id()

    failed = await engine.record_attempt(
        action, outcome="failed", error_class=ErrorClass.SOURCE_UNAVAILABLE
    )
    no_result = await engine.record_attempt(
        action,
        outcome="no_result",
        coverage=CoverageStatement(universe="registered filings", coverage="2020-2026"),
    )

    assert failed.state is MemoryState.FAILED
    assert no_result.state is MemoryState.NO_RESULT
    assert failed.entry_id != no_result.entry_id
    assert {e.state for e in await engine.action_memory(obligation.obligation_id)} == {
        MemoryState.FAILED,
        MemoryState.NO_RESULT,
    }


def test_a_failed_attempt_may_not_claim_a_coverage_statement():
    """It did not search, so a coverage statement would describe a search that never ran."""
    from context_engine.obligations import ActionMemoryEntry

    with pytest.raises(ContextEngineError) as caught:
        ActionMemoryEntry(
            obligation_id="OBL-1",
            attempt_key="registry|q",
            outcome="failed",
            state=MemoryState.FAILED,
            coverage=CoverageStatement(universe="filings", coverage="2020"),
        )
    assert caught.value.code == "failed_attempt_carries_a_coverage_statement"


# =============================================================================
# T043 -- disagreement is not convergence
# =============================================================================


async def test_two_sources_that_disagree_keep_both_supports_and_close_nothing():
    from context_engine.obligations import ResearchAction

    engine, context = await _seeded()
    obligation = (await engine.open_obligations(context.context_id))[0]

    # Both sources reported, both gained something, and they disagree.
    for runtime_ref in ("registry-a", "registry-b"):
        action = ResearchAction(
            obligation_id=obligation.obligation_id,
            proposed_method=f"acquire via {runtime_ref}",
            runtime_ref=runtime_ref,
        ).with_id()
        await engine.record_attempt(
            action, outcome="succeeded", realised_gain=0.3, detail=f"{runtime_ref} answered"
        )

    memory = await engine.action_memory(obligation.obligation_id)
    assert len(memory) == 2, "one source's support overwrote the other's"
    assert {e.attempt_key for e in memory} == {
        f"registry-a|{QUESTION}",
        f"registry-b|{QUESTION}",
    }
    assert all(e.state is MemoryState.GAINED for e in memory)

    # The disagreement itself is now a contradiction, raised through the production path.
    _, raised = await engine.ingest(
        context,
        (
            GapSignal(
                kind=TriggerKind.CONTRADICTION,
                question="explain contradiction on owner-of-registry",
                rationale="registry-a and registry-b name different registrants",
                knowledge_type=KnowledgeType.CONTRADICTION,
            ),
        ),
        event_ids=["evt-contradiction-1"],
    )
    assert len(raised) == 1, "a disagreement did not open a contradiction"

    verdict = await engine.evaluate_obligation(
        obligation.obligation_id,
        SatisfactionInput(
            evidence_count=2,
            saturation=_saturated(),
            contradicting_evidence=1,
            evidence_refs=("OBS-a", "OBS-b"),
        ),
    )
    report = await engine.termination_report(context.context_id)

    assert verdict.satisfied is False
    assert "contradicted" in verdict.reason
    assert report.is_terminal is False
    assert report.stop_reason is None, "disagreement produced a stop reason"
    assert obligation.question in report.still_unknown


async def test_a_contradiction_does_not_settle_the_question():
    engine, context = await _seeded()
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

    assert step.status is not LoopStatus.SATURATED
    assert step.note or step.status is LoopStatus.CONTINUE


# =============================================================================
# T044 -- a terminal state carries a reason from the allowed table
# =============================================================================


async def test_a_satisfied_board_terminates_as_completed_with_a_reason():
    engine, context = await _seeded()
    obligation = (await engine.open_obligations(context.context_id))[0]
    await engine.evaluate_obligation(
        obligation.obligation_id, SatisfactionInput(evidence_count=3, saturation=_saturated())
    )
    report = await engine.termination_report(context.context_id)

    assert report.is_terminal is True
    assert report.stop_reason is StopReason.COMPLETED
    assert report.has_a_reasoned_stop is True
    assert report.stop_reason_detail


async def test_an_abandoned_question_terminates_as_completed_with_limitations():
    engine, context = await _seeded()
    obligation = (await engine.open_obligations(context.context_id))[0]
    await engine.abandon_obligation(obligation.obligation_id, reason="no public record exists")
    report = await engine.termination_report(context.context_id)

    assert report.is_terminal is True
    assert report.stop_reason is StopReason.COMPLETED_WITH_LIMITATIONS
    assert "no public record exists" in report.stop_reason_detail
    assert "no public record exists" in str(report.reasons_by_status)


async def test_open_work_is_not_a_stop_reason():
    """Three obligations created and none of them answered is not a stopping point."""
    engine, context = await _seeded(
        signals=tuple(
            GapSignal(kind=TriggerKind.COVERAGE_GAP, question=f"question {i}")
            for i in range(3)
        )
    )
    report = await engine.termination_report(context.context_id)

    assert report.total_obligations == 3
    assert report.is_terminal is False
    assert report.stop_reason is None
    assert len(report.unexecuted_scope) == 3


@pytest.mark.parametrize("label", sorted(FORBIDDEN_STOP_REASONS))
def test_the_five_forbidden_stop_reasons_are_refused(label: str):
    """FR-046: each of these is a symptom. None of them ends an investigation."""
    with pytest.raises(ContextEngineError) as caught:
        require_real_stop_reason(label)
    assert caught.value.code == "stop_reason_forbidden"


@pytest.mark.parametrize(
    "label", ["empty_results", "no_results", "task_count", "retries_exhausted", "model_confidence"]
)
def test_the_forbidden_labels_are_refused_in_their_camel_and_spaced_forms(label: str):
    with pytest.raises(ContextEngineError):
        require_real_stop_reason(label.replace("_", " ").upper())


def test_an_empty_reason_means_not_stopped_rather_than_a_missing_reason():
    assert require_real_stop_reason("") is None
    assert require_real_stop_reason("   ") is None


def test_every_allowed_reason_parses_and_nothing_else_does():
    for reason in StopReason:
        assert require_real_stop_reason(reason.value) is reason
    with pytest.raises(ValueError):
        require_real_stop_reason("it felt finished")


# =============================================================================
# T048 -- satisfaction is against declared acceptance criteria only
# =============================================================================


async def test_a_raw_hit_count_never_satisfies_a_declared_criterion():
    engine, context = await _seeded(
        signals=(
            GapSignal(
                kind=TriggerKind.COVERAGE_GAP,
                question=QUESTION,
                acceptance_criteria=("the filing names a registered entity",),
            ),
        )
    )
    obligation = (await engine.open_obligations(context.context_id))[0]

    verdict = await engine.evaluate_obligation(
        obligation.obligation_id,
        # 999 hits and a perfect basis, and the declared criterion is still unmet.
        SatisfactionInput(evidence_count=999, saturation=_saturated()),
    )

    assert verdict.satisfied is False
    assert verdict.blockers
    assert verdict.blockers[0].kind == "criterion_unmet"
    assert verdict.blockers[0].criterion_id == obligation.acceptance_criteria[0].criterion_id
    assert "999" not in verdict.reason


async def test_citing_the_evidence_discharges_the_declared_criterion():
    engine, context = await _seeded(
        signals=(
            GapSignal(
                kind=TriggerKind.COVERAGE_GAP,
                question=QUESTION,
                acceptance_criteria=("the filing names a registered entity",),
            ),
        )
    )
    obligation = (await engine.open_obligations(context.context_id))[0]

    verdict = await engine.evaluate_obligation(
        obligation.obligation_id,
        SatisfactionInput(
            evidence_count=1,
            saturation=_saturated(),
            criterion_evidence={obligation.acceptance_criteria[0].criterion_id: ("OBS-filing-1",)},
            evidence_refs=("OBS-filing-1",),
        ),
    )

    assert verdict.satisfied is True
    assert verdict.satisfied_criterion_ids == (obligation.acceptance_criteria[0].criterion_id,)
    assert verdict.evidence_refs == ("OBS-filing-1",)


async def test_a_verdict_carries_reasons_refs_version_and_blockers():
    """FR-041: a verdict that says only "no" cannot be argued with."""
    engine, context = await _seeded()
    obligation = (await engine.open_obligations(context.context_id))[0]

    verdict = await engine.evaluate_obligation(
        obligation.obligation_id,
        SatisfactionInput(
            evidence_count=4,
            saturation=SaturationState(
                coverage=0.4, marginal_gain=0.4, distinct_sources=1, source_diversity=1
            ),
            evidence_refs=("OBS-1", "OBS-2"),
        ),
    )

    assert isinstance(verdict, SatisfactionVerdict)
    assert verdict.evaluator_version == RULES_VERSION
    assert verdict.evidence_refs == ("OBS-1", "OBS-2")
    assert verdict.reasons
    assert verdict.blockers and all(b.detail for b in verdict.blockers)
    assert verdict.criterion_ids and verdict.satisfied_criterion_ids == ()
    assert set(verdict.to_dict()) >= {
        "reasons",
        "evidence_refs",
        "evaluator_version",
        "blockers",
        "missing_capabilities",
    }


def test_the_evaluator_declares_its_fallback_when_no_criterion_was_stated():
    """Hand-built obligations must not be mistaken for fully declared ones."""
    from context_engine.engine import DEFAULT_ACCEPTANCE_CRITERION, SatisfactionEvaluator
    from context_engine.obligations import ResearchObligation

    obligation = ResearchObligation(context_id="CXI-x", question="q").with_id()
    verdict = SatisfactionEvaluator().evaluate(
        obligation, SatisfactionInput(evidence_count=1, saturation=_saturated())
    )

    assert verdict.satisfied is True
    assert DEFAULT_ACCEPTANCE_CRITERION.criterion_id in verdict.criterion_ids
    assert any("no acceptance criteria were declared" in r for r in verdict.reasons)


# =============================================================================
# T050 -- every stop carries a reason, residual unknowns and unexecuted scope
# =============================================================================


async def test_a_report_always_carries_residual_unknowns_and_unexecuted_scope():
    engine, context = await _seeded()
    obligation = (await engine.open_obligations(context.context_id))[0]
    report = await engine.termination_report(context.context_id)

    assert report.still_unknown == (obligation.question,)
    assert [s.question for s in report.unexecuted_scope] == [obligation.question]
    assert report.unexecuted_scope[0].missing_capabilities == ("registry.record.extract",)

    payload = report.to_dict()
    assert set(payload) >= {"stop_reason", "stop_reason_detail", "unexecuted_scope"}


async def test_an_unreasoned_closure_is_refused():
    engine, context = await _seeded()
    obligation = (await engine.open_obligations(context.context_id))[0]
    with pytest.raises(ContextEngineError) as caught:
        await engine.abandon_obligation(obligation.obligation_id, reason="   ")
    assert caught.value.code == "abandon_reason_missing"


async def test_reopening_records_its_reason_and_what_was_still_open():
    engine, context = await _seeded()
    obligation = (await engine.open_obligations(context.context_id))[0]
    await engine.evaluate_obligation(
        obligation.obligation_id, SatisfactionInput(evidence_count=3, saturation=_saturated())
    )
    closed = await engine.termination_report(context.context_id)
    before = len(await engine.revision_history(context.context_id))

    revision = await engine.reopen(
        context.context_id, reason="a later filing contradicts the registrant", event_ids=["evt-9"]
    )

    decisions = [d for d in engine.recorder.decisions(context.context_id) if d.kind == "context_reopened"]
    assert len(decisions) == 1
    assert decisions[0].detail == "a later filing contradicts the registrant"

    scope = [d for d in engine.recorder.decisions(context.context_id) if d.kind == "context_reopen_scope"]
    assert len(scope) == 1
    assert "residual unknowns" in scope[0].detail
    assert "unexecuted scope" in scope[0].detail

    # The closure is not erased: the chain grew instead.
    after = await engine.revision_history(context.context_id)
    assert len(after) == before + 1
    assert after[-1].revision_id == revision.revision_id
    assert closed.is_terminal is True


async def test_reopening_without_a_reason_is_refused():
    engine, context = await _seeded()
    with pytest.raises(ContextEngineError) as caught:
        await engine.reopen(context.context_id, reason="  ")
    assert caught.value.code == "reopen_reason_missing"


# =============================================================================
# T051 -- one publication path, and it is the existing outbox
# =============================================================================


class RecordingOutbox:
    """Stands in for ``SqlMaterializationOutbox`` -- same ``enqueue`` contract, no database."""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    async def enqueue(
        self, *, tenant_id: str, entity_id: str, run_id: str, workflow_id: str, identity: dict
    ):
        self.rows.append(
            {
                "tenant_id": tenant_id,
                "entity_id": entity_id,
                "run_id": run_id,
                "workflow_id": workflow_id,
                "identity": identity,
            }
        )
        return identity


async def test_changes_reach_the_existing_outbox_and_nowhere_else():
    outbox = RecordingOutbox()
    engine, context = await _seeded(publisher=SqlOutboxChangePublisher(outbox))
    obligation = (await engine.open_obligations(context.context_id))[0]
    await engine.evaluate_obligation(
        obligation.obligation_id, SatisfactionInput(evidence_count=3, saturation=_saturated())
    )

    workflows = {row["workflow_id"] for row in outbox.rows}
    assert "context-engine.obligation.created" in workflows
    assert "context-engine.obligation.transitioned" in workflows
    assert "context-engine.decision.recorded" in workflows
    assert all(row["tenant_id"] == "t-1" for row in outbox.rows)
    assert all(row["run_id"] for row in outbox.rows)


def test_the_outbox_binding_matches_the_real_enqueue_signature():
    """The durable path must be checked against the class it actually calls."""
    from db.materialization_outbox import SqlMaterializationOutbox

    assert (
        tuple(inspect.signature(SqlMaterializationOutbox.enqueue).parameters)
        == ("self", *outbox_enqueue_contract())
    )


def test_an_undeclared_change_kind_is_refused():
    with pytest.raises(ContextEngineError) as caught:
        ContextChange(
            kind="something.happened",
            tenant_id="t-1",
            context_id="CXI-1",
            subject_id="OBL-1",
        )
    assert caught.value.code == "change_kind_unknown"


def test_a_change_with_no_tenant_scope_is_refused():
    with pytest.raises(ContextEngineError) as caught:
        ContextChange(
            kind="decision.recorded", tenant_id="", context_id="CXI-1", subject_id="DEC-1"
        )
    assert caught.value.code == "change_scope_missing"


def test_a_non_enqueueable_object_cannot_be_bound_as_the_outbox():
    with pytest.raises(ContextEngineError) as caught:
        SqlOutboxChangePublisher(object())
    assert caught.value.code == "outbox_not_enqueueable"


async def test_the_publication_seam_is_single_and_the_outbox_contract_holds():
    assert_publication_is_single()
    assert_components_are_separate()


async def test_every_published_change_carries_its_causal_scope():
    publisher = InMemoryChangePublisher()
    _, context = await _seeded(publisher=publisher)

    assert publisher.published
    for change in publisher.published:
        assert change.context_id == context.context_id
        assert change.tenant_id == "t-1"
        assert change.subject_id


# =============================================================================
# the loop still closes end to end
# =============================================================================


async def test_one_obligation_reaches_a_terminal_state_from_one_independent_observation():
    """The User Story 1 independent test: obligation, evidence, revision, next action."""
    engine, context = await _seeded()
    revisions_before = await engine.revision_history(context.context_id)

    loop = CognitiveLoop(engine, coverage_threshold=0.5, marginal_gain_threshold=0.05)
    step = await loop.tick(
        context,
        outcomes=(
            ObservationOutcome(
                action_id="a1",
                task_id="task-a1",
                produced_observations=("OBS-independent-1",),
                coverage_delta=0.6,
                marginal_gain=0.0,
            ),
        ),
    )
    report = await engine.termination_report(context.context_id)

    assert step.status is LoopStatus.SATURATED, step.note
    assert report.is_terminal and report.stop_reason is StopReason.COMPLETED
    assert len(await engine.revision_history(context.context_id)) > len(revisions_before)
    assert step.note.startswith("saturated:")