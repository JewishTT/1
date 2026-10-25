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

from datetime import UTC, datetime

import json

import enum
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from domain.investigation_context import (
    ContextEngineError,
    ContextRevision,
    InvestigationContext,
    ObligationStatus,
)

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


#: The change kinds the context engine publishes. Closed, because an open-ended stream of
#: "context happened" is an event log nobody subscribes to.
CHANGE_KINDS: tuple[str, ...] = (
    "obligation.created",
    "obligation.transitioned",
    "action.proposed",
    "decision.recorded",
)


@dataclass(frozen=True, slots=True)
class ContextChange:
    """One obligation / action / decision change, on its way out of the engine (T051).

    Carries its own causal identifiers -- tenant, context, subject, revision -- because a
    downstream consumer that has to join against the context store to find out which
    investigation a change belongs to has already lost the ordering guarantee the
    outbox exists to provide.
    """

    kind: str
    tenant_id: str
    context_id: str
    subject_id: str
    revision_id: str = ""
    payload: Mapping[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.kind not in CHANGE_KINDS:
            raise ContextEngineError(
                "change_kind_unknown",
                f"{self.kind!r} is not one of {CHANGE_KINDS}; an undeclared change kind is a "
                "second publication vocabulary, and there is exactly one",
            )
        for name in ("tenant_id", "context_id", "subject_id"):
            if not str(getattr(self, name)).strip():
                raise ContextEngineError(
                    "change_scope_missing",
                    f"a context change must name its {name}; an unscoped change is "
                    "undeliverable and, worse, readable by the wrong tenant (FR-090)",
                )
        object.__setattr__(self, "payload", dict(self.payload or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "tenant_id": self.tenant_id,
            "context_id": self.context_id,
            "subject_id": self.subject_id,
            "revision_id": self.revision_id,
            "payload": dict(self.payload),
        }


class ChangePublisher(ABC):
    """The **single** publication seam for obligation / action / decision changes (T051).

    One interface, one implementation in production. The engine holds exactly one of
    these and routes every obligation, action and decision change through it; there is no
    second queue behind it, no fire-and-forget append, and no "log it in the decision
    recorder instead" fallback. :func:`context_engine.engine.assert_publication_is_single`
    checks that mechanically.

    Concrete implementations:

    * :class:`InMemoryChangePublisher` -- the reference, matching a memory-durability
      store. Correct within a process, loses everything on exit.
    * :class:`SqlOutboxChangePublisher` -- binds to the repository's existing
      ``db.materialization_outbox.SqlMaterializationOutbox``. Transactional-outbox
      semantics, already built and already reviewed; the context engine adds a binding,
      not a broker.
    """

    @abstractmethod
    async def publish(self, change: ContextChange) -> None: ...

    async def publish_all(self, changes: list[ContextChange] | tuple[ContextChange, ...]) -> None:
        for change in changes:
            await self.publish(change)


class InMemoryChangePublisher(ChangePublisher):
    """Reference publisher. Mirrors the store: right in-process, gone on exit."""

    def __init__(self) -> None:
        self.published: list[ContextChange] = []

    async def publish(self, change: ContextChange) -> None:
        self.published.append(change)

    def kinds(self) -> tuple[str, ...]:
        return tuple(change.kind for change in self.published)


class SqlOutboxChangePublisher(ChangePublisher):
    """Binds context changes to the **existing** ``materialization_outbox`` (T051).

    Not a new table and not a new queue. ``SqlMaterializationOutbox`` already provides the
    transactionally-safe hand-off, the ready-claim and the retry accounting; this class
    only maps a :class:`ContextChange` onto its ``enqueue`` call. Its idempotency key is
    ``(tenant_id, run_id)``, so the change is addressed by the revision that produced it
    and re-publishing the same revision is a no-op at the outbox rather than a duplicate
    delivery -- which is FR-065, enforced by the table's unique index rather than by
    anything written here.

    The outbox parameter is typed structurally so ``context_engine`` does not have to
    import ``db`` at module load. :func:`outbox_enqueue_contract` states the shape it
    needs and is asserted against the real class in the tests.
    """

    #: ``enqueue``'s keyword-only signature, restated so a mismatch is caught here rather
    #: than at the first publish.
    WORKFLOW_PREFIX = "context-engine"

    def __init__(self, outbox: Any, *, workflow_prefix: str = "") -> None:
        if not callable(getattr(outbox, "enqueue", None)):
            raise ContextEngineError(
                "outbox_not_enqueueable",
                "the change publisher binds to SqlMaterializationOutbox; the object "
                f"supplied has no enqueue() ({type(outbox).__name__}), so this would be a "
                "second publication path with a different name",
            )
        self.outbox = outbox
        self.workflow_prefix = workflow_prefix or self.WORKFLOW_PREFIX

    async def publish(self, change: ContextChange) -> None:
        await self.outbox.enqueue(
            tenant_id=change.tenant_id,
            entity_id=change.subject_id,
            run_id=change.revision_id or change.context_id,
            workflow_id=f"{self.workflow_prefix}.{change.kind}",
            identity={
                "kind": change.kind,
                "context_id": change.context_id,
                "subject_id": change.subject_id,
                "revision_id": change.revision_id,
                **dict(change.payload),
            },
        )


def outbox_enqueue_contract() -> tuple[str, ...]:
    """The parameter names ``SqlOutboxChangePublisher`` relies on.

    Returned rather than imported so the assertion can be made against the real
    ``SqlMaterializationOutbox`` from a test that has the database package on its path,
    while ``store.py`` itself stays free of it.
    """
    return ("tenant_id", "entity_id", "run_id", "workflow_id", "identity")


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

    # -- person-case metadata (Feature 034) ----------------------------------

    async def put_person_case_metadata(
        self,
        *,
        case_id: str,
        tenant_id: str,
        purpose_code: str,
        basis_ref: str,
        launch_profile: str,
        claim_families: list[str],
        allowed_source_ids: list[str],
        denied_claim_families: list[str],
        scope_digest: str,
        scope_revision: int,
        approved: bool,
        budget_ref: str | None,
        expires_at: str | None,
        valid_time: dict[str, Any],
        jurisdictions: list[str],
        subject_anchors: list[dict[str, str]] | None = None,
    ) -> None:
        """Persist the vertical metadata through the store's metadata contract.

        The reference store keeps this sidecar in memory. Durable store implementations
        must override this pair with a database-backed record. Do not mint a fake
        ResearchObligation to hold metadata: it pollutes the analyst's obligation list
        and loses the actual values after a process restart.
        """
        if not case_id or not tenant_id:
            raise ContextEngineError(
                "person_case_identity_missing",
                "case_id and tenant_id are required for case metadata",
            )
        self._person_case_meta_index: dict[str, dict[str, Any]] = getattr(
            self, "_person_case_meta_index", {}
        )
        previous = self._person_case_meta_index.get(case_id, {})
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        self._person_case_meta_index[case_id] = {
            "case_id": case_id,
            "created_at": previous.get("created_at", now),
            "updated_at": now,
            "tenant_id": tenant_id,
            "purpose_code": purpose_code,
            "basis_ref": basis_ref,
            "launch_profile": launch_profile,
            "claim_families": list(claim_families),
            "allowed_source_ids": list(allowed_source_ids),
            "denied_claim_families": list(denied_claim_families),
            "scope_digest": scope_digest,
            "scope_revision": int(scope_revision),
            "approved": bool(approved),
            "budget_ref": budget_ref,
            "expires_at": expires_at,
            "valid_time": dict(valid_time),
            "jurisdictions": list(jurisdictions),
            "subject_anchors": [dict(a) for a in (subject_anchors or [])],
        }

    async def get_person_case_metadata(self, case_id: str) -> dict[str, Any] | None:
        """Retrieve the complete case sidecar, or None if it is not stored."""
        index = getattr(self, "_person_case_meta_index", {})
        value = index.get(case_id)
        if value is None:
            return None
        # Return a detached representation so callers cannot mutate durable/reference
        # state without going through put_person_case_metadata.
        return json.loads(json.dumps(value))

    async def put_person_case_dispatch_intent(
        self,
        *,
        case_id: str,
        tenant_id: str,
        run_id: str,
        idempotency_key: str,
        approved_action_refs: list[str],
        scope_digest: str,
        policy_digest: str,
    ) -> dict[str, Any]:
        """Reference idempotency ledger; production uses the PostgreSQL override."""
        if not all((case_id, tenant_id, run_id, idempotency_key, scope_digest, policy_digest)):
            raise ContextEngineError("dispatch_intent_incomplete", "dispatch intent is missing identity or digest fields")
        key = (tenant_id, case_id, idempotency_key)
        proposed = {
            "case_id": case_id,
            "tenant_id": tenant_id,
            "run_id": run_id,
            "idempotency_key": idempotency_key,
            "approved_action_refs": sorted(set(approved_action_refs)),
            "scope_digest": scope_digest,
            "policy_digest": policy_digest,
            "state": "PREPARED",
            "outcome": None,
        }
        self._person_case_dispatch_index: dict[tuple[str, str, str], dict[str, Any]] = getattr(
            self, "_person_case_dispatch_index", {}
        )
        previous = self._person_case_dispatch_index.get(key)
        if previous is not None:
            for field in ("approved_action_refs", "scope_digest", "policy_digest"):
                if previous[field] != proposed[field]:
                    raise ContextEngineError(
                        "idempotency_key_reused",
                        f"idempotency key was reused with different {field}",
                    )
            return {**previous, "created": False}
        self._person_case_dispatch_index[key] = proposed
        return {**proposed, "created": True}

    async def mark_person_case_dispatch_intent(
        self,
        *,
        case_id: str,
        tenant_id: str,
        idempotency_key: str,
        state: str,
        outcome: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record the broker outcome without deleting the idempotency ledger."""
        if state not in {"PREPARED", "PUBLISHED", "PARTIAL", "FAILED"}:
            raise ContextEngineError("dispatch_state_invalid", f"unsupported dispatch state {state}")
        index = getattr(self, "_person_case_dispatch_index", {})
        key = (tenant_id, case_id, idempotency_key)
        current = index.get(key)
        if current is None:
            raise ContextEngineError("dispatch_intent_missing", "dispatch intent is not recorded")
        updated = {**current, "state": state, "outcome": dict(outcome or {})}
        index[key] = updated
        return {**updated, "created": False}



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
    "CASE_META_OBLIGATION_ID_PREFIX",
    "CHANGE_KINDS",
    "ContextChange",
    "ContextStore",
    "DISPATCH_INTENT_ACTION_ID_PREFIX",
    "InMemoryChangePublisher",
    "InMemoryContextStore",
    "ReplayResult",
    "SqlOutboxChangePublisher",
    "StoreDurability",
    "outbox_enqueue_contract",
]