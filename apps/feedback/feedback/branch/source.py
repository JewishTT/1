"""T116: source-independence feedback branch.

Observed (yield, cost, freshness, independence_yield) for a source fold into
the NEXT expected utility through the shared adaptive scorer (SourceState,
T111); the branch additionally recommends a concrete frontier policy
(deepen / keep / reduce / drop) so the loop closes into the frontier.
"""

from __future__ import annotations

from dataclasses import dataclass

from scoring.scorer import HeuristicUtilityScorer, SourceState, lifecycle_to_outcome

from ..frontier import FeedbackCandidate


@dataclass
class SourceOutcomeFeedback:
    source_id: str
    lifecycle: str
    tenant_id: str
    cost: float = 0.0
    independence_yield: float = 0.0
    changed: bool | None = None  # auto-derived from lifecycle when None
    fresh: bool = True
    investigation_id: str | None = None
    work_id: str | None = None


def _changed_from_lifecycle(lifecycle: str) -> bool:
    return lifecycle in ("created", "changed")


def recommend_source_policy(state: SourceState, emitter=None) -> tuple[str, float, str]:
    """Frontier policy for a source given its adaptive state."""
    if state.window_n >= 3 and state.error_rate > 0.5:
        action, priority, reason = "drop", 0.0, "source is erroring"
    elif state.independence_yield > 0.3:
        action, priority, reason = (
            "deepen",
            min(1.0, 0.5 + state.independence_yield * 0.4),
            "high independence yield",
        )
    elif state.window_n >= 2 and state.change_rate < 0.20:
        action, priority, reason = "reduce", 0.2, "stability lowers marginal signal"
    else:
        action, priority, reason = "keep", 0.4, "steady source"
    if emitter is not None:
        emitter(
            "feedback.source_policy",
            {
                "source_id": state.source_id,
                "action": action,
                "priority": priority,
                "reason": reason,
            },
        )
    return action, priority, reason


def run_source_feedback(
    scorer: HeuristicUtilityScorer,
    forms: list[SourceOutcomeFeedback],
    *,
    emit=None,
) -> list[FeedbackCandidate]:
    """Fold source outcomes into adaptive state and emit frontier candidates."""
    statuses: dict[str, str] = {}
    for form in forms:
        outcome = lifecycle_to_outcome(form.lifecycle)
        state = scorer.adjust_source(
            form.source_id,
            outcome,
            changed=form.changed
            if form.changed is not None
            else _changed_from_lifecycle(form.lifecycle),
            cost=form.cost,
            independence_yield=form.independence_yield,
            fresh=form.fresh,
        )
        statuses[form.source_id] = state
    candidates: list[FeedbackCandidate] = []
    seen: set[str] = set()
    for form in forms:
        if form.source_id in seen:
            continue
        seen.add(form.source_id)
        state = statuses[form.source_id]
        action, priority, reason = recommend_source_policy(state, emitter=emit)
        if action == "drop":
            continue
        candidates.append(
            FeedbackCandidate(
                uri=retrieval_for_source(form, action),
                priority=priority,
                kind="pivot",
                tenant_id=form.tenant_id,
                investigation_id=form.investigation_id,
                source_id=form.source_id,
                work_id=form.work_id,
                reason=reason,
                payload={"policy": action, "source_kind": "source-reading"},
            )
        )
    return candidates


def retrieval_for_source(form: SourceOutcomeFeedback, action: str) -> str:
    from ..frontier import retrieval_key_uri

    return retrieval_key_uri("pivot", f"source:{form.source_id}:{action}")
