"""Hypothesis lifecycle (T101, US2; interface-contracts §3).

The ``Hypothesis`` value object lives in ``claims.model`` (data-model §3); this
module owns its lifecycle: proposal, append-only status transitions, and the
alive/dead predicate that gates every downstream planner.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from _events import envelope as _emit
from claims.model import Hypothesis, HypothesisStatus


def _hypothesis_id(project_id: str, text: str) -> str:
    digest = hashlib.sha256(f"{project_id}|{text}".encode()).hexdigest()[:12]
    return f"HY-{digest}"


def _is_alive_status(status: HypothesisStatus) -> bool:
    return status not in {HypothesisStatus.DISCARDED, HypothesisStatus.RESOLVED}


def is_alive(hypothesis: Hypothesis) -> bool:
    """Dead (discarded/resolved) hypotheses are invisible to collection planners."""
    return _is_alive_status(hypothesis.status)


def propose_hypothesis(
    *,
    project_id: str,
    text: str,
    tenant_id: str = "default-tenant",
    producer: Any = None,
    store: Any = None,
) -> Hypothesis:
    """Register a competing explanatory hypothesis (FR-004)."""
    hypothesis = Hypothesis(
        hypothesis_id=_hypothesis_id(project_id, text),
        project_id=project_id,
        text=text,
        status=HypothesisStatus.PROPOSED,
    )
    env = _emit(
        event_type="science.hypothesis.proposed",
        payload={
            "hypothesis_id": hypothesis.hypothesis_id,
            "project_id": project_id,
            "text": text,
            "tenant_id": tenant_id,
        },
        producer=producer,
        investigation_id=project_id,
    )
    if store is not None:
        store.apply(env)
    return hypothesis


_TRANSITIONS: dict[HypothesisStatus, set[HypothesisStatus]] = {
    HypothesisStatus.PROPOSED: {HypothesisStatus.ACTIVE, HypothesisStatus.DISCARDED},
    HypothesisStatus.ACTIVE: {
        HypothesisStatus.STRENGTHENED,
        HypothesisStatus.WEAKENED,
        HypothesisStatus.CONFIRMED,
        HypothesisStatus.DISCARDED,
        HypothesisStatus.RESOLVED,
    },
    HypothesisStatus.STRENGTHENED: {
        HypothesisStatus.CONFIRMED,
        HypothesisStatus.WEAKENED,
        HypothesisStatus.DISCARDED,
    },
    HypothesisStatus.WEAKENED: {
        HypothesisStatus.STRENGTHENED,
        HypothesisStatus.DISCARDED,
        HypothesisStatus.CONFIRMED,
    },
    HypothesisStatus.CONFIRMED: {HypothesisStatus.RESOLVED, HypothesisStatus.WEAKENED},
    HypothesisStatus.RESOLVED: set(),
    HypothesisStatus.DISCARDED: set(),
}


def transition_hypothesis_status(
    hypothesis: Hypothesis,
    to_status: HypothesisStatus | str,
    *,
    actor: str = "system",
    producer: Any = None,
    store: Any = None,
) -> Hypothesis:
    """Transition a hypothesis, emitting an append-only event (FR-015)."""
    target = (
        to_status if isinstance(to_status, HypothesisStatus) else HypothesisStatus(to_status)
    )
    allowed = _TRANSITIONS.get(hypothesis.status, set())
    if target not in allowed:
        raise ValueError(
            f"illegal hypothesis transition {hypothesis.status.value} -> {target.value}"
        )
    env = _emit(
        event_type="science.hypothesis.status_changed",
        payload={
            "hypothesis_id": hypothesis.hypothesis_id,
            "from_status": hypothesis.status.value,
            "to_status": target.value,
            "actor": actor,
            "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        },
        producer=producer,
        investigation_id=hypothesis.project_id,
    )
    if store is not None:
        store.apply(env)
    hypothesis.status = target
    if not _is_alive_status(target):
        hypothesis.gain_priority = None
    return hypothesis