"""T118: finding -> new-work feedback branch.

A FindingCandidate proposes new acquisition work. The branch scores it with the
adaptive UtilityScorer (utility = confidence-weighted expected gain); candidates
above a threshold create frontier work, below it are dropped (stopping signal),
never blindly dispatched.
"""

from __future__ import annotations

from dataclasses import dataclass

from scoring.scorer import HeuristicUtilityScorer, UtilityScore

from ..frontier import FeedbackCandidate, retrieval_key_uri

ENQUEUE_UTILITY = 0.25


@dataclass
class FindingCandidate:
    finding_id: str
    entity_id: str
    tenant_id: str
    confidence: float = 0.5
    novelty: float = 0.5
    estimated_utility: float | None = None  # overrides score when set
    category: str = "research"
    investigation_id: str | None = None
    source_id: str | None = None
    work_id: str | None = None
    worker_class: str | None = None


def _score_finding(scorer: HeuristicUtilityScorer, finding: FindingCandidate) -> UtilityScore:
    if finding.estimated_utility is not None:
        utility = max(0.0, min(1.0, finding.estimated_utility))
        return UtilityScore(
            utility=utility,
            priority=utility,
            expected_novelty=finding.novelty,
            expected_cost=0.1,
            reasons=["finding-estimated"],
        )
    task = {
        "task_id": f"F-{finding.finding_id}",
        "uri": retrieval_key_uri("hypothesis", f"{finding.entity_id}:{finding.finding_id}"),
        "expected_gain": finding.confidence,
        "relevance": 1.0,
        "novelty": finding.novelty,
        "freshness": 0.7,
        "discovery_potential": finding.confidence,
        "source_quality": 0.6,
        "network_cost": 0.1,
        "compute_cost": 0.1,
        "duplicate_risk": 0.2,
    }
    if finding.worker_class:
        task["worker_class"] = finding.worker_class
    return scorer.score(task, {})


def run_finding_feedback(
    scorer: HeuristicUtilityScorer,
    findings: list[FindingCandidate],
    *,
    threshold: float = ENQUEUE_UTILITY,
    emit=None,
) -> list[FeedbackCandidate]:
    """Score findings and turn the winners into frontier work."""
    candidates: list[FeedbackCandidate] = []
    for finding in findings:
        score = _score_finding(scorer, finding)
        if score.utility < threshold:
            if emit is not None:
                emit("feedback.defer", {"finding_id": finding.finding_id, "utility": score.utility})
            continue
        candidates.append(
            FeedbackCandidate(
                uri=retrieval_key_uri("hypothesis", f"{finding.entity_id}:{finding.finding_id}"),
                priority=min(1.0, score.utility),
                kind="hypothesis",
                tenant_id=finding.tenant_id,
                investigation_id=finding.investigation_id,
                source_id=finding.source_id,
                work_id=finding.work_id,
                reason="finding -> new work",
                payload={
                    "finding_id": finding.finding_id,
                    "category": finding.category,
                    "estimated_utility": score.utility,
                },
            )
        )
    return candidates
