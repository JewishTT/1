"""Context store: the contract, and a hermetic reference implementation (T037).

Follows the ``RegimeStore`` pattern already in the repository (``ABC`` contract plus
``InMemory*`` reference) rather than inventing a fourth store style -- the repo
already has Protocol-based, ABC-based, and concrete stores, and the ABC form is the
one that was chosen when "the store is a contract, not an implementation detail" had
to be decided.

``InvestigationContext`` is core state and MUST survive a restart (FR-027), so this
contract is deliberately not satisfiable by memory alone: :meth:`ContextStore.durable`
says whether the implementation loses state. The engine asserts on it, so a
memory-backed store cannot be wired into production by accident.
"""

from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass

from domain.investigation_context import ContextRevision, InvestigationContext

from context_engine.obligations import (
    ActionMemoryEntry,
    ContextFrontier,
    ResearchAction,
    ResearchObligation,
)


class StoreDurability(enum.StrEnum):
    """Whether a store survives a restart."""

    MEMORY = "memory"
    DURABLE = "durable"


class ContextStore(ABC):
    """Durable home for context, revisions, obligations, actions, memory."""

    @abstractmethod
    def durability(self) -> StoreDurability: ...

    # -- contexts -----------------------------------------------------------

    @abstractmethod
    async def put_context(self, context: InvestigationContext) -> None: ...

    @abstractmethod
    async def get_context(self, context_id: str) -> InvestigationContext | None: ...

    @abstractmethod
    async def contexts(self) -> tuple[InvestigationContext, ...]: ...

    # -- revisions (append-only, FR-026) -------------------------------------

    @abstractmethod
    async def append_revision(self, revision: ContextRevision) -> None: ...

    @abstractmethod
    async def revisions(self, context_id: str) -> tuple[ContextRevision, ...]: ...

    @abstractmethod
    async def current_revision(self, context_id: str) -> ContextRevision | None: ...

    @abstractmethod
    async def next_revision_number(self, context_id: str) -> int: ...

    # -- obligations ---------------------------------------------------------

    @abstractmethod
    async def put_obligation(self, obligation: ResearchObligation) -> None: ...

    @abstractmethod
    async def get_obligation(self, obligation_id: str) -> ResearchObligation | None: ...

    @abstractmethod
    async def obligations(self, context_id: str) -> tuple[ResearchObligation, ...]: ...

    # -- actions -------------------------------------------------------------

    @abstractmethod
    async def put_action(self, action: ResearchAction) -> None: ...

    @abstractmethod
    async def actions(self, obligation_id: str) -> tuple[ResearchAction, ...]: ...

    # -- action memory (FR-059) ----------------------------------------------

    @abstractmethod
    async def remember(self, entry: ActionMemoryEntry) -> None: ...

    @abstractmethod
    async def memory_for(self, obligation_id: str) -> tuple[ActionMemoryEntry, ...]: ...

    # -- frontier ------------------------------------------------------------

    @abstractmethod
    async def put_frontier(self, frontier: ContextFrontier) -> None: ...

    @abstractmethod
    async def get_frontier(self, context_id: str) -> ContextFrontier | None: ...


class InMemoryContextStore(ContextStore):
    """Reference implementation. Correct within a process; loses everything on exit.

    Fine for tests and single-shot runs. :meth:`durability` reports ``MEMORY`` so the
    engine can refuse it where persistence is required.
    """

    def __init__(self) -> None:
        self._contexts: dict[str, InvestigationContext] = {}
        self._revisions: dict[str, list[ContextRevision]] = {}
        self._obligations: dict[str, ResearchObligation] = {}
        self._actions: dict[str, list[ResearchAction]] = {}
        self._memory: dict[str, list[ActionMemoryEntry]] = {}
        self._frontiers: dict[str, ContextFrontier] = {}

    def durability(self) -> StoreDurability:
        return StoreDurability.MEMORY

    async def put_context(self, context: InvestigationContext) -> None:
        self._contexts[context.context_id] = context

    async def get_context(self, context_id: str) -> InvestigationContext | None:
        return self._contexts.get(context_id)

    async def contexts(self) -> tuple[InvestigationContext, ...]:
        return tuple(sorted(self._contexts.values(), key=lambda c: c.context_id))

    async def append_revision(self, revision: ContextRevision) -> None:
        """Append-only: an existing revision number is refused, not overwritten."""
        chain = self._revisions.setdefault(revision.context_id, [])
        for existing in chain:
            if existing.revision == revision.revision:
                if existing.revision_id == revision.revision_id:
                    return  # idempotent re-append
                raise ValueError(
                    f"revision {revision.revision} already exists with a different address"
                )
        chain.append(revision)
        chain.sort(key=lambda r: r.revision)

    async def revisions(self, context_id: str) -> tuple[ContextRevision, ...]:
        return tuple(self._revisions.get(context_id, ()))

    async def current_revision(self, context_id: str) -> ContextRevision | None:
        chain = self._revisions.get(context_id)
        return chain[-1] if chain else None

    async def next_revision_number(self, context_id: str) -> int:
        chain = self._revisions.get(context_id)
        return (chain[-1].revision + 1) if chain else 1

    async def put_obligation(self, obligation: ResearchObligation) -> None:
        self._obligations[obligation.obligation_id] = obligation

    async def get_obligation(self, obligation_id: str) -> ResearchObligation | None:
        return self._obligations.get(obligation_id)

    async def obligations(self, context_id: str) -> tuple[ResearchObligation, ...]:
        return tuple(
            sorted(
                (o for o in self._obligations.values() if o.context_id == context_id),
                key=lambda o: o.obligation_id,
            )
        )

    async def put_action(self, action: ResearchAction) -> None:
        bucket = self._actions.setdefault(action.obligation_id, [])
        for existing in bucket:
            if existing.action_id == action.action_id:
                bucket[bucket.index(existing)] = action
                return
        bucket.append(action)

    async def actions(self, obligation_id: str) -> tuple[ResearchAction, ...]:
        return tuple(sorted(self._actions.get(obligation_id, ()), key=lambda a: a.action_id))

    async def remember(self, entry: ActionMemoryEntry) -> None:
        bucket = self._memory.setdefault(entry.obligation_id, [])
        for existing in bucket:
            if existing.entry_id == entry.entry_id:
                return
        bucket.append(entry)

    async def memory_for(self, obligation_id: str) -> tuple[ActionMemoryEntry, ...]:
        return tuple(sorted(self._memory.get(obligation_id, ()), key=lambda e: e.entry_id))

    async def put_frontier(self, frontier: ContextFrontier) -> None:
        self._frontiers[frontier.context_id] = frontier

    async def get_frontier(self, context_id: str) -> ContextFrontier | None:
        return self._frontiers.get(context_id)


@dataclass(frozen=True, slots=True)
class ReplayResult:
    """FR-028: what a replay produced, so a mismatch is describable."""

    context_id: str
    revisions: int
    obligations: int
    actions: int
    final_state: str

    def to_dict(self) -> dict[str, object]:
        return {
            "context_id": self.context_id,
            "revisions": self.revisions,
            "obligations": self.obligations,
            "actions": self.actions,
            "final_state": self.final_state,
        }


__all__ = [
    "ContextStore",
    "InMemoryContextStore",
    "ReplayResult",
    "StoreDurability",
]