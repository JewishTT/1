"""Research obligations, actions, saturation, and the frontier (Feature 024 Phase 4/5).

The vocabulary the Context Engine reasons over. Every object here is a frozen
dataclass with a deterministic address, following the platform's 016+ convention --
reused, not reinvented (see ``domain.investigation_context`` for the template).

The central distinction, and the reason this is not the frontier module that already
exists: ``ResearchObligation`` is **what must be learned**, while
``acquisition_tasks``/``frontier_items`` are **what has been queued**. Closing an
obligation requires saturation and coverage, never a task count (FR-053) -- a task
count measures effort, not sufficiency.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from domain.investigation_context import ContextEngineError, InvestigationState, ObligationStatus
from domain.relation_identity import canonical_material, digest128

OBLIGATION_ID_PREFIX = "OBL-"
ACTION_ID_PREFIX = "ACT-"
SATURATION_PREFIX = "SAT-"
MEMORY_PREFIX = "AM-"


class KnowledgeType(enum.StrEnum):
    """What kind of answer would settle an obligation (input.md §13.2)."""

    ENTITY = "entity"
    RELATION = "relation"
    EVENT = "event"
    ATTRIBUTE = "attribute"
    ABSENCE = "absence"
    CONTRADICTION = "contradiction"
    BOUNDARY = "boundary"


class Disposition(enum.StrEnum):
    """FR-035. A terminal disposition always carries a reason."""

    SATISFIED = "satisfied"
    ABANDONED = "abandoned"
    BLOCKED = "blocked"
    SUPERSEDED = "superseded"


@dataclass(frozen=True, slots=True)
class SaturationState:
    """FR-052/053. Sufficiency, never effort."""

    coverage: float
    marginal_gain: float
    distinct_sources: int
    source_diversity: int
    stopping_condition: str = ""
    coverage_threshold: float = 0.9
    marginal_gain_threshold: float = 0.05

    def __post_init__(self) -> None:
        for name in ("coverage", "marginal_gain", "source_diversity_factor", "source_diversity"):
            if name in ("source_diversity_factor",):
                continue
        if not 0.0 <= self.coverage <= 1.0:
            raise ContextEngineError("coverage_out_of_range", f"{self.coverage}")
        if self.marginal_gain < 0.0:
            raise ContextEngineError("marginal_gain_negative", f"{self.marginal_gain}")

    @property
    def is_saturated(self) -> bool:
        return (
            self.coverage >= self.coverage_threshold
            and self.marginal_gain <= self.marginal_gain_threshold
        )

    def reason(self) -> str:
        """FR-054: the system must be able to say *why* it considers this settled."""
        return (
            f"coverage={self.coverage:.2f}>={self.coverage_threshold} "
            f"marginal_gain={self.marginal_gain:.3f}<={self.marginal_gain_threshold} "
            f"distinct_sources={self.distinct_sources} diversity={self.source_diversity}"
            + (f" stopping={self.stopping_condition}" if self.stopping_condition else "")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "coverage": self.coverage,
            "marginal_gain": self.marginal_gain,
            "distinct_sources": self.distinct_sources,
            "source_diversity": self.source_diversity,
            "stopping_condition": self.stopping_condition,
            "coverage_threshold": self.coverage_threshold,
            "marginal_gain_threshold": self.marginal_gain_threshold,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> SaturationState:
        return cls(
            coverage=payload["coverage"],
            marginal_gain=payload["marginal_gain"],
            distinct_sources=payload["distinct_sources"],
            source_diversity=payload["source_diversity"],
            stopping_condition=payload.get("stopping_condition", ""),
            coverage_threshold=payload.get("coverage_threshold", 0.9),
            marginal_gain_threshold=payload.get("marginal_gain_threshold", 0.05),
        )

    def key(self) -> str:
        return SATURATION_PREFIX + digest128(canonical_material(self.to_dict()))


@dataclass(frozen=True, slots=True)
class ResearchObligation:
    """FR-033. What must be learned, why, and what would count as an answer."""

    context_id: str
    question: str
    rationale: str = ""
    target_knowledge_type: KnowledgeType = KnowledgeType.ENTITY
    priority: float = 0.5
    status: ObligationStatus = ObligationStatus.OPEN
    created_by: str = ""
    satisfaction_criteria: tuple[str, ...] = ()
    confidence: float = 0.0
    related_hypothesis_ids: tuple[str, ...] = ()
    blocking_dependencies: tuple[str, ...] = ()
    saturation: SaturationState | None = None
    disposition: Disposition | None = None
    disposition_reason: str = ""
    obligation_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", ObligationStatus(self.status))
        object.__setattr__(
            self, "target_knowledge_type", KnowledgeType(self.target_knowledge_type)
        )
        if self.disposition is not None:
            object.__setattr__(self, "disposition", Disposition(self.disposition))
        object.__setattr__(self, "satisfaction_criteria", tuple(self.satisfaction_criteria))
        object.__setattr__(self, "related_hypothesis_ids", tuple(self.related_hypothesis_ids))
        object.__setattr__(self, "blocking_dependencies", tuple(self.blocking_dependencies))
        if not self.context_id:
            raise ContextEngineError("obligation_context_missing", "obligation needs a context")
        if not self.question.strip():
            raise ContextEngineError("obligation_question_empty", "obligation needs a question")
        if not 0.0 <= self.priority <= 1.0:
            raise ContextEngineError("obligation_priority_out_of_range", f"{self.priority}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ContextEngineError("obligation_confidence_out_of_range", f"{self.confidence}")
        if self.status is ObligationStatus.SATISFIED and self.disposition is None:
            raise ContextEngineError(
                "obligation_satisfied_without_disposition",
                "a satisfied obligation must say it is satisfied",
            )
        addressed = self.address()
        if not self.obligation_id:
            object.__setattr__(self, "obligation_id", addressed)
        elif self.obligation_id != addressed:
            raise ContextEngineError(
                "obligation_id_mismatch",
                f"declared {self.obligation_id!r} but material addresses to {addressed!r}",
            )

    def _material(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "question": self.question,
            "rationale": self.rationale,
            "target_knowledge_type": self.target_knowledge_type.value,
            "priority": self.priority,
            "status": self.status.value,
            "created_by": self.created_by,
            "satisfaction_criteria": list(self.satisfaction_criteria),
            "confidence": self.confidence,
            "related_hypothesis_ids": list(self.related_hypothesis_ids),
            "blocking_dependencies": list(self.blocking_dependencies),
            "saturation": self.saturation.to_dict() if self.saturation else None,
            "disposition": self.disposition.value if self.disposition else None,
            "disposition_reason": self.disposition_reason,
        }

    def address(self) -> str:
        """Obligation identity covers *what is being asked*, not how far it has got.

        Progress lives in a new revision of the same obligation; if progress changed
        the address, action memory keyed by obligation could never match again.
        """
        return OBLIGATION_ID_PREFIX + digest128(
            canonical_material(
                {
                    "context_id": self.context_id,
                    "question": self.question,
                    "target_knowledge_type": self.target_knowledge_type.value,
                }
            )
        )

    def with_id(self) -> ResearchObligation:
        from dataclasses import replace

        return replace(self, obligation_id=self.address())

    def to_dict(self) -> dict[str, Any]:
        return {**self._material(), "obligation_id": self.obligation_id}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResearchObligation:
        sat = payload.get("saturation")
        disp = payload.get("disposition")
        return cls(
            context_id=payload["context_id"],
            question=payload["question"],
            rationale=payload.get("rationale", ""),
            target_knowledge_type=KnowledgeType(payload.get("target_knowledge_type", "entity")),
            priority=payload.get("priority", 0.5),
            status=ObligationStatus(payload.get("status", "open")),
            created_by=payload.get("created_by", ""),
            satisfaction_criteria=tuple(payload.get("satisfaction_criteria", ())),
            confidence=payload.get("confidence", 0.0),
            related_hypothesis_ids=tuple(payload.get("related_hypothesis_ids", ())),
            blocking_dependencies=tuple(payload.get("blocking_dependencies", ())),
            saturation=SaturationState.from_dict(sat) if sat else None,
            disposition=Disposition(disp) if disp else None,
            disposition_reason=payload.get("disposition_reason", ""),
            obligation_id=payload.get("obligation_id", ""),
        )


@dataclass(frozen=True, slots=True)
class ResearchAction:
    """FR-036. A candidate means of satisfying an obligation. Never executed here."""

    obligation_id: str
    proposed_method: str
    runtime_ref: str = ""
    expected_information_gain: float = 0.0
    estimated_cost: float = 0.0
    priority: float = 0.5
    capability_requirements: tuple[str, ...] = ()
    requires_operator_approval: bool = True
    status: str = "proposed"
    task_id: str = ""
    realised_gain: float | None = None
    action_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "capability_requirements", tuple(self.capability_requirements))
        if not self.obligation_id:
            raise ContextEngineError("action_obligation_missing", "action needs an obligation")
        if not self.proposed_method.strip():
            raise ContextEngineError("action_method_empty", "action needs a method")
        if not 0.0 <= self.expected_information_gain <= 1.0:
            raise ContextEngineError("action_gain_out_of_range", f"{self.expected_information_gain}")
        if not 0.0 <= self.estimated_cost <= 1.0:
            raise ContextEngineError("action_cost_out_of_range", f"{self.estimated_cost}")
        addressed = self.address()
        if not self.action_id:
            object.__setattr__(self, "action_id", addressed)
        elif self.action_id != addressed:
            raise ContextEngineError(
                "action_id_mismatch",
                f"declared {self.action_id!r} but material addresses to {addressed!r}",
            )

    def _material(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "proposed_method": self.proposed_method,
            "runtime_ref": self.runtime_ref,
            "expected_information_gain": self.expected_information_gain,
            "estimated_cost": self.estimated_cost,
            "priority": self.priority,
            "capability_requirements": list(self.capability_requirements),
            "requires_operator_approval": self.requires_operator_approval,
            "status": self.status,
            "task_id": self.task_id,
            "realised_gain": self.realised_gain,
        }

    def address(self) -> str:
        return ACTION_ID_PREFIX + digest128(canonical_material(self._material()))

    def with_id(self) -> ResearchAction:
        from dataclasses import replace

        return replace(self, action_id=self.address())

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ResearchAction:
        """Rebuild from :meth:`to_dict`.

        Added for the durable store. Every sibling in this module already had the pair,
        and an action that can be written but not read cannot survive a restart, so the
        asymmetry was a gap in the contract rather than a missing convenience.
        """
        return cls(
            action_id=str(data.get("action_id", "")),
            obligation_id=str(data.get("obligation_id", "")),
            proposed_method=str(data.get("proposed_method", "")),
            rationale=str(data.get("rationale", "")),
            expected_gain=float(data.get("expected_gain", 0.0)),
            capability_requirements=tuple(data.get("capability_requirements", ())),
            requires_operator_approval=bool(data.get("requires_operator_approval", True)),
            status=str(data.get("status", "proposed")),
            task_id=str(data.get("task_id", "")),
            realised_gain=data.get("realised_gain"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {**self._material(), "action_id": self.action_id}


@dataclass(frozen=True, slots=True)
class ActionMemoryEntry:
    """FR-059. What was already attempted for an obligation.

    Without this the engine re-proposes work it has already done, which looks like
    diligence and is actually a loop.
    """

    obligation_id: str
    attempt_key: str
    outcome: str
    realised_gain: float | None = None
    entry_id: str = ""

    def __post_init__(self) -> None:
        addressed = MEMORY_PREFIX + digest128(
            canonical_material(
                {
                    "obligation_id": self.obligation_id,
                    "attempt_key": self.attempt_key,
                    "outcome": self.outcome,
                }
            )
        )
        if not self.entry_id:
            object.__setattr__(self, "entry_id", addressed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "attempt_key": self.attempt_key,
            "outcome": self.outcome,
            "realised_gain": self.realised_gain,
            "entry_id": self.entry_id,
        }


@dataclass(frozen=True, slots=True)
class ContextFrontier:
    """FR-058. Open work, as a queryable object rather than operator memory."""

    context_id: str
    state: InvestigationState
    open_obligations: tuple[str, ...] = ()
    blocked_obligations: tuple[str, ...] = ()
    closed_obligations: tuple[str, ...] = ()
    next_actions: tuple[str, ...] = ()
    pending_approval: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ContextFrontier:
        """Rebuild from :meth:`to_dict`; see :meth:`ResearchAction.from_dict`."""
        return cls(
            context_id=str(data.get("context_id", "")),
            state=InvestigationState(str(data.get("state", InvestigationState.UNINVESTIGATED))),
            open_obligations=tuple(data.get("open_obligations", ())),
            blocked_obligations=tuple(data.get("blocked_obligations", ())),
            closed_obligations=tuple(data.get("closed_obligations", ())),
            next_actions=tuple(data.get("next_actions", ())),
            pending_approval=tuple(data.get("pending_approval", ())),
            notes=tuple(data.get("notes", ())),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "state": self.state.value,
            "open_obligations": list(self.open_obligations),
            "blocked_obligations": list(self.blocked_obligations),
            "closed_obligations": list(self.closed_obligations),
            "next_actions": list(self.next_actions),
            "pending_approval": list(self.pending_approval),
            "notes": list(self.notes),
        }


__all__ = [
    "ACTION_ID_PREFIX",
    "MEMORY_PREFIX",
    "OBLIGATION_ID_PREFIX",
    "SATURATION_PREFIX",
    "ActionMemoryEntry",
    "ContextFrontier",
    "Disposition",
    "KnowledgeType",
    "ResearchAction",
    "ResearchObligation",
    "SaturationState",
]