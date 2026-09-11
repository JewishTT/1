"""Evidence attachment (T102, US2; interface-contracts §3).

Evidence links are direction-tagged (``supports | refutes | discriminates``),
append-only (FR-015), and their weights come from the US1-calibrated claims
layer — never ad-hoc. ``derive_credence`` turns an evidence-weighted hypothesis
set into a normalized CredenceDistribution over hypothesis ids (US1 precedence:
weighted, not fabricated).
"""

from __future__ import annotations

from typing import Any

from _events import envelope as _emit
from claims.model import (
    CredenceDistribution,
    EvidenceDirection,
    EvidenceLink,
    Hypothesis,
)


def attach_evidence(
    hypothesis: Hypothesis,
    link: EvidenceLink,
    *,
    producer: Any = None,
    store: Any = None,
) -> None:
    """Append a direction-tagged evidence link (immutable, FR-015)."""
    if any(existing.link_id == link.link_id for existing in hypothesis.evidence_links):
        return
    hypothesis.evidence_links.append(link)
    env = _emit(
        event_type="science.hypothesis.evidence_attached",
        payload={
            "hypothesis_id": hypothesis.hypothesis_id,
            "link_id": link.link_id,
            "observation_id": link.observation_id,
            "direction": link.direction.value,
            "weight": link.weight,
        },
        producer=producer,
        key=link.link_id,
        investigation_id=hypothesis.project_id,
    )
    if store is not None:
        store.apply(env)


def derive_credence(
    hypotheses: list[Hypothesis],
    *,
    method: str = "evidence-weighted@1.0",
) -> CredenceDistribution:
    """Derive hypotheses credence from US1-calibrated link weights (no fabrication).

    Alive hypotheses score by net evidence weight (supports + discriminates
    minus refutes, floor at a small epsilon); normalized over the set. Duplicates
    are excluded so the distribution stays a valid probability vector.
    """
    seen: set[str] = set()
    scores: list[tuple[str, float]] = []
    for hypothesis in hypotheses:
        if hypothesis.hypothesis_id in seen:
            continue
        seen.add(hypothesis.hypothesis_id)
        net = 1e-6
        for link in hypothesis.evidence_links:
            if link.direction in {EvidenceDirection.SUPPORTS, EvidenceDirection.DISCRIMINATES}:
                net += max(link.weight, 0.0)
            elif link.direction == EvidenceDirection.REFUTES:
                net -= min(link.weight, 1.0)
                net = max(net, 1e-6)
        scores.append((hypothesis.hypothesis_id, max(net, 1e-6)))
    total = sum(weight for _hid, weight in scores)
    return CredenceDistribution(
        states=[hid for hid, _w in scores],
        labels=[f"{hid}" for hid, _w in scores],
        probs=[weight / total for _hid, weight in scores],
        method=method,
    )