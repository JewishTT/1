"""Hypothesis discard (T103, US2; SC-003).

Discarding a hypothesis is a *decision*, not an implementation detail: it
requires a DecisionRecord (who/when/why), keeps all evidence links intact, and
emits an append-only ``science.hypothesis.discarded`` event. Without a decision
the discard is refused outright (``DecisionRequiredError``).
"""

from __future__ import annotations

from typing import Any

from _events import envelope as _emit
from claims.model import DecisionRecord, Hypothesis, HypothesisStatus
from errors import DecisionRequiredError
from hypotheses.model import transition_hypothesis_status


def discard_hypothesis(
    hypothesis: Hypothesis,
    decision: DecisionRecord | None,
    *,
    producer: Any = None,
    store: Any = None,
) -> None:
    """Discard a hypothesis; refuses (SC-003) without a recorded who/when/why."""
    if decision is None or not decision.actor or not decision.reason:
        raise DecisionRequiredError(hypothesis.hypothesis_id)
    transition_hypothesis_status(
        hypothesis,
        HypothesisStatus.DISCARDED,
        actor=decision.actor,
        producer=producer,
        store=store,
    )
    hypothesis.decisions.append(decision)
    env = _emit(
        event_type="science.hypothesis.discarded",
        payload={
            "hypothesis_id": hypothesis.hypothesis_id,
            "decision": {
                "actor": decision.actor,
                "reason": decision.reason,
                "at": decision.at.isoformat(),
            },
            "evidence_kept": len(hypothesis.evidence_links),
        },
        producer=producer,
        investigation_id=hypothesis.project_id,
    )
    if store is not None:
        store.apply(env)