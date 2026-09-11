"""Feedback engine (T044).

Consumes signals — new entities, new relations, new discoveries, topological
signals from TDA — and produces concrete feedback recommendations: recrawl
priorities, new discovery seeds, and budget adjustments. Emits
`feedback.generated` events for the control plane.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class FeedbackSignal:
    kind: str  # entity | relation | discovery | topological
    source_id: str
    weight: float = 1.0
    payload: dict = field(default_factory=dict)


@dataclass
class FeedbackAction:
    action: str  # recrawl | discover | budget
    target: str
    priority: float = 0.5
    reason: str = ""
    payload: dict = field(default_factory=dict)


@dataclass
class FeedbackRecommendation:
    recommendation_id: str = field(default_factory=lambda: "FB-" + uuid.uuid4().hex[:12])
    actions: list[FeedbackAction] = field(default_factory=list)
    source: str = ""


class FeedbackEngine:
    def __init__(self, emitter=None) -> None:
        self._emitter = emitter  # callable(event_type, payload)
        self.history: list[FeedbackRecommendation] = []

    def ingest(self, signal: FeedbackSignal) -> FeedbackRecommendation:
        actions: list[FeedbackAction] = []
        if signal.kind == "entity":
            actions.append(
                FeedbackAction(action="discover", target=f"entity:{signal.payload.get('entity_id', signal.source_id)}",
                               priority=0.4 + 0.1 * signal.weight, reason="new entity needs breadth")
            )
        elif signal.kind == "relation":
            actions.append(
                FeedbackAction(action="recrawl", target=f"relation:{signal.source_id}",
                               priority=0.5 + 0.1 * signal.weight, reason="new relation warrants revalidation")
            )
        elif signal.kind == "discovery":
            actions.append(
                FeedbackAction(action="discover", target=signal.source_id,
                               priority=0.3, reason="fresh discovery seed")
            )
        elif signal.kind == "topological":
            actions.append(
                FeedbackAction(action="budget", target=signal.source_id,
                               priority=min(1.0, 0.2 + signal.weight),
                               reason="topological signal suggests deepening source",
                               payload=signal.payload)
            )
        rec = FeedbackRecommendation(actions=actions, source=signal.kind)
        self.history.append(rec)
        if self._emitter:
            self._emitter("feedback.generated", {
                "recommendation_id": rec.recommendation_id,
                "actions": [a.__dict__ for a in actions],
            })
        return rec

    def latest(self) -> FeedbackRecommendation | None:
        return self.history[-1] if self.history else None