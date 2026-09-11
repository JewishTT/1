"""Causal classification (T110, US3; interface-contracts §5, FR-006).

``classify`` runs the shared scope guard first (FR-007) — nothing is computed
on a person-sensitive outcome. Without a declared model the conclusion is
CORRELATIONAL with a confounder list; with a model that owns the outcome and
controls the named confounders it is CAUSAL and carries the model's id,
confounders and assumptions. Classifications are emitted as
``science.causal.classified`` (refs-only, I-5).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

from _events import envelope as _emit
from causal.model import CausalConclusion, CausalLabel, CausalModel
from causal.scope import ensure_scoped
from claims.model import EvidenceLink


def _conclusion_id(evidence: Sequence[EvidenceLink], model_ref: str | None) -> str:
    digest = hashlib.sha256(
        f"{model_ref or 'correlational'}|{'|'.join(l.link_id for l in evidence)}".encode()
    ).hexdigest()[:12]
    return f"CS-{digest}"


def classify(
    evidence: Sequence[EvidenceLink],
    model: CausalModel | None,
    *,
    outcome_attribute: str | None = None,
    possible_confounders: list[str] | None = None,
    producer: Any = None,
    store: Any = None,
) -> CausalConclusion:
    """Classify evidence as CORRELATIONAL, or CAUSAL under a declared model.

    Invariants (interface-contracts §5): scope guard first; CAUSAL only when a
    declared model owns the outcome and the named confounders are controlled.
    """
    ensure_scoped(
        outcome_attribute or "",
        entry_point="causal.classify",
        actor=None,
        producer=producer,
    )

    if model is not None and outcome_attribute is not None and model.declares(outcome_attribute):
        conclusion = CausalConclusion(
            conclusion_id=_conclusion_id(evidence, model.model_id),
            label=CausalLabel.CAUSAL,
            model_ref=model.model_id,
            controlled_confounders=list(model.confounders),
            assumptions=list(model.assumptions),
            possible_confounders=[],
            evidence_links=list(evidence),
        )
    else:
        conclusion = CausalConclusion(
            conclusion_id=_conclusion_id(evidence, None),
            label=CausalLabel.CORRELATIONAL,
            model_ref=None,
            controlled_confounders=[],
            assumptions=[],
            possible_confounders=list(possible_confounders or []),
            evidence_links=list(evidence),
        )

    env = _emit(
        event_type="science.causal.classified",
        payload={
            "conclusion_id": conclusion.conclusion_id,
            "label": conclusion.label.value,
            "model_ref": conclusion.model_ref,
            "evidence_refs": [link.link_id for link in conclusion.evidence_links],
            "outcome_attribute": outcome_attribute,
        },
        producer=producer,
    )
    if store is not None:
        store.apply(env)
    return conclusion