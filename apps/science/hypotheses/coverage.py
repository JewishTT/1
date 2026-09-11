"""Per-project hypothesis coverage (T105, US2; FR-005).

Produces a read-only coverage view for a project: how many hypotheses exist and
are alive, how many carry at least one evidence link, total/linked evidence
counts by direction, and (when the project declared requirements) which
requirements have at least one linked hypothesis. Used by reviewers so the
fabric never quietly stops collecting.
"""

from __future__ import annotations

from typing import Any

from claims.model import EvidenceDirection, Hypothesis
from hypotheses.model import is_alive
from store import ScienceStore


def _direction_counts(hypotheses: list[Hypothesis]) -> dict[str, int]:
    counts = {direction.value: 0 for direction in EvidenceDirection}
    for hypothesis in hypotheses:
        for link in hypothesis.evidence_links:
            counts[link.direction.value] += 1
    return counts


def project_coverage(
    hypotheses: list[Hypothesis] | None = None,
    *,
    project_id: str,
    store: ScienceStore | None = None,
) -> dict[str, Any]:
    """Coverage summary for a project's hypothesis population (FR-005)."""
    if store is not None:
        from hypotheses.gain import load_hypotheses

        hypotheses = load_hypotheses(store, project_id)
    hypotheses = hypotheses or []

    alive = [h for h in hypotheses if is_alive(h)]
    with_evidence = [h for h in hypotheses if h.evidence_links]
    total_links = sum(len(h.evidence_links) for h in hypotheses)
    requirements = {h.coverage.get("requirement") for h in hypotheses if h.coverage}

    return {
        "project_id": project_id,
        "hypotheses": len(hypotheses),
        "alive": len(alive),
        "dead": len(hypotheses) - len(alive),
        "with_evidence": len(with_evidence),
        "without_evidence": len(hypotheses) - len(with_evidence),
        "evidence_links": total_links,
        "direction_counts": _direction_counts(hypotheses),
        "requirements_covered": sorted(r for r in requirements if r),
    }