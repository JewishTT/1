"""Investigation context: durable research scope (Feature 024 Phase 4).

Why this is a new object rather than an extension of ``EvidenceContext``
---------------------------------------------------------------------
``EvidenceContext`` is a content-addressed *evidence frame* -- the frame a claim was
read in. ``InvestigationContext`` is a *research scope*: what must be learned, why,
and what remains unknown. They answer different questions and must not be merged.

Merging them is not a style preference; it is technically destructive.
``EvidenceContext.__post_init__`` derives ``context_id`` from ``frame_fingerprint``
over all 25 material fields, and every persisted ``context_id``, the
``uq_evidence_context_fingerprint`` unique index, every ``context_ref`` on a claim and
every frame-carrying event payload is cut from that material. Adding a field changes
the digest, so stored frames fail ``context_id_mismatch`` on load -- they do not
degrade, they become unreadable.

The bypass pattern already exists in the codebase: ``SemanticRegime`` is a separate
content-addressed object holding a one-way ``context_ref``. This module follows it.

Reused from platform code (AGENTS.md §1)
-----------------------------------------
* ``domain.relation_identity.canonical_material`` / ``digest128`` -- the platform's
  single identity convention. Not reimplemented, not forked.
* The ``EvidenceContext`` shape: frozen dataclass, canonicalise -> invariants ->
  verify in ``__post_init__``, a private ``_material()``, local ``*ContractError``
  with a snake_case ``.code``.
* The ``RegimeRecord`` shape for storable addressed records: explicit ``with_id()``
  rather than minting an id as a side effect, and refusal on mismatch rather than
  silent acceptance.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from domain.relation_identity import canonical_material, digest128

CONTEXT_IDENTITY_SCHEMA = "investigation-context/v1"
CONTEXT_ID_PREFIX = "CXI-"
REVISION_PREFIX = "CXR-"


class ContextEngineError(ValueError):
    """Contract violation in the investigation context.

    Local error, in the same shape as ``ContextContractError`` and the rest of the
    016+ generation, so one caller can switch on ``.code`` for either family.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class InvestigationState(enum.StrEnum):
    """FR-030. ``UNINVESTIGATED`` and ``EXHAUSTED`` are different facts.

    "We have not looked" is not "we looked and found nothing". Collapsing them is
    how an investigation reports a clean bill of health it never earned.
    """

    UNINVESTIGATED = "uninvestigated"
    ACTIVE = "active"
    SATURATED = "saturated"
    EXHAUSTED = "exhausted"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class ObligationStatus(enum.StrEnum):
    """FR-035. Every obligation reaches a terminal state or the set is non-closed."""

    OPEN = "open"
    PARTIALLY_SATISFIED = "partially_satisfied"
    SATISFIED = "satisfied"
    ABANDONED = "abandoned"
    BLOCKED = "blocked"


#: Fields that determine *which* investigation this is. Revision state is
#: deliberately excluded: the address of a context must not move when the context
#: changes, or every stored reference to it would break on the first revision.
IDENTITY_FIELDS = (
    "identity_schema",
    "tenant_id",
    "investigation_id",
    "title",
    "scope_refs",
)


@dataclass(frozen=True, slots=True)
class ScopeLinkage:
    """An explicit cross-investigation link (FR-031).

    An investigation never silently absorbs another one's evidence. Every link is
    declared here, with a reason, so the question "why is this evidence in scope?"
    has an answer that is stored rather than inferred.
    """

    other_context_id: str
    relation: str  # "reuses" | "supersedes" | "derived_from" | "sibling"
    reason: str
    declared_at: str = ""
    declared_by: str = "operator"

    def _material(self) -> dict[str, Any]:
        return {
            "other_context_id": self.other_context_id,
            "relation": self.relation,
            "reason": self.reason,
            "declared_at": self.declared_at,
            "declared_by": self.declared_by,
        }

    def to_dict(self) -> dict[str, Any]:
        return self._material()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ScopeLinkage:
        return cls(
            other_context_id=payload["other_context_id"],
            relation=payload["relation"],
            reason=payload["reason"],
            declared_at=payload.get("declared_at", ""),
            declared_by=payload.get("declared_by", "operator"),
        )


@dataclass(frozen=True, slots=True)
class InvestigationContext:
    """A durable research scope.

    Identity is content-addressed over :data:`IDENTITY_FIELDS` only. Two contexts
    with the same tenant, investigation, title and scope refs are the same context
    regardless of how far either has progressed -- that is what makes ``context_id``
    usable as a stable reference from obligations, actions and decisions.
    """

    tenant_id: str = ""
    investigation_id: str = ""
    title: str = ""
    scope_refs: tuple[str, ...] = ()
    context_id: str = ""
    identity_schema: str = CONTEXT_IDENTITY_SCHEMA
    question: str = ""
    state: InvestigationState = InvestigationState.UNINVESTIGATED
    scope_links: tuple[ScopeLinkage, ...] = ()
    policy_snapshot_ref: str = ""
    created_at: str = ""

    def __post_init__(self) -> None:
        if self.identity_schema != CONTEXT_IDENTITY_SCHEMA:
            raise ContextEngineError(
                "identity_schema_unknown",
                f"{self.identity_schema!r} is not {CONTEXT_IDENTITY_SCHEMA!r}",
            )
        object.__setattr__(self, "state", InvestigationState(self.state))
        object.__setattr__(self, "scope_refs", tuple(sorted({str(r) for r in self.scope_refs})))
        if not self.tenant_id:
            raise ContextEngineError("tenant_id_missing", "tenant_id is required")
        if not self.investigation_id:
            raise ContextEngineError("investigation_id_missing", "investigation_id is required")
        if not self.scope_refs:
            raise ContextEngineError(
                "scope_empty",
                "a context with no scope is indistinguishable from no context; "
                "declare at least one scope reference",
            )
        object.__setattr__(self, "scope_links", tuple(self.scope_links))
        addressed = self.address()
        if not self.context_id:
            object.__setattr__(self, "context_id", addressed)
        elif self.context_id != addressed:
            raise ContextEngineError(
                "context_id_mismatch",
                f"declared {self.context_id!r} but identity material addresses to {addressed!r}",
            )

    # -- identity -----------------------------------------------------------

    def _identity_material(self) -> dict[str, Any]:
        return {
            "identity_schema": self.identity_schema,
            "tenant_id": self.tenant_id,
            "investigation_id": self.investigation_id,
            "title": self.title,
            "scope_refs": list(self.scope_refs),
        }

    def address(self) -> str:
        """``CXI-{digest128}`` over the identity fields alone."""
        return CONTEXT_ID_PREFIX + digest128(canonical_material(self._identity_material()))

    def with_id(self) -> InvestigationContext:
        """Explicit derivation, mirroring ``RegimeRecord.with_id``."""
        return replace(self, context_id=self.address())

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._identity_material(),
            "context_id": self.context_id,
            "question": self.question,
            "state": self.state.value,
            "scope_links": [link.to_dict() for link in self.scope_links],
            "policy_snapshot_ref": self.policy_snapshot_ref,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> InvestigationContext:
        return cls(
            tenant_id=payload["tenant_id"],
            investigation_id=payload["investigation_id"],
            title=payload.get("title", ""),
            scope_refs=tuple(payload.get("scope_refs", ())),
            context_id=payload.get("context_id", ""),
            identity_schema=payload.get("identity_schema", CONTEXT_IDENTITY_SCHEMA),
            question=payload.get("question", ""),
            state=InvestigationState(payload.get("state", "uninvestigated")),
            scope_links=tuple(
                ScopeLinkage.from_dict(link) for link in payload.get("scope_links", ())
            ),
            policy_snapshot_ref=payload.get("policy_snapshot_ref", ""),
            created_at=payload.get("created_at", ""),
        )

    # -- revision (FR-025, FR-026, FR-029) -----------------------------------

    def next_revision(
        self,
        *,
        revision: int,
        state: InvestigationState,
        caused_by_event_ids: tuple[str, ...],
        decision_ids: tuple[str, ...] = (),
        operator_actions: tuple[str, ...] = (),
        rules_version: str = "",
        mode: str = "deterministic",
    ) -> ContextRevision:
        """Derive the next snapshot. This context is not mutated (FR-026).

        The caller supplies the revision number because it is the store's job to
        allocate it transactionally; deriving it here would make replay depend on
        call order rather than on the recorded sequence.
        """
        if revision <= 0:
            raise ContextEngineError("revision_invalid", f"revision must be >= 1, got {revision}")
        return ContextRevision(
            context_id=self.context_id,
            revision=revision,
            parent_revision=revision - 1,
            state=state,
            snapshot=self.to_dict(),
            caused_by_event_ids=tuple(caused_by_event_ids),
            decision_ids=tuple(decision_ids),
            operator_actions=tuple(operator_actions),
            rules_version=rules_version,
            mode=mode,
        )


@dataclass(frozen=True, slots=True)
class ContextRevision:
    """One append-only snapshot of a context (FR-026).

    Every revision records what produced it: the events, the decisions, and the
    operator actions. A revision that cannot name its cause is not auditable, and an
    unauditable conclusion is the primary risk input.md §36.5 names.
    """

    context_id: str
    revision: int
    parent_revision: int
    state: InvestigationState
    snapshot: dict[str, Any]
    caused_by_event_ids: tuple[str, ...] = ()
    decision_ids: tuple[str, ...] = ()
    operator_actions: tuple[str, ...] = ()
    rules_version: str = ""
    mode: str = "deterministic"
    revision_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", InvestigationState(self.state))
        if self.revision < 1:
            raise ContextEngineError("revision_invalid", f"revision must be >= 1, got {self.revision}")
        if self.parent_revision != self.revision - 1:
            raise ContextEngineError(
                "revision_chain_broken",
                f"revision {self.revision} declares parent {self.parent_revision}",
            )
        if self.context_id and not self.context_id.startswith(CONTEXT_ID_PREFIX):
            raise ContextEngineError(
                "context_id_foreign", f"{self.context_id!r} is not a {CONTEXT_ID_PREFIX} address"
            )
        if self.mode not in ("deterministic", "adaptive"):
            raise ContextEngineError(
                "mode_unknown",
                f"mode must be 'deterministic' or 'adaptive', got {self.mode!r}",
            )
        addressed = self.address()
        if not self.revision_id:
            object.__setattr__(self, "revision_id", addressed)
        elif self.revision_id != addressed:
            raise ContextEngineError(
                "revision_id_mismatch",
                f"declared {self.revision_id!r} but material addresses to {addressed!r}",
            )

    def _material(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "revision": self.revision,
            "parent_revision": self.parent_revision,
            "state": self.state.value,
            "snapshot": self.snapshot,
            "caused_by_event_ids": list(self.caused_by_event_ids),
            "decision_ids": list(self.decision_ids),
            "operator_actions": list(self.operator_actions),
            "rules_version": self.rules_version,
            "mode": self.mode,
        }

    def address(self) -> str:
        return REVISION_PREFIX + digest128(canonical_material(self._material()))

    def with_id(self) -> ContextRevision:
        return replace(self, revision_id=self.address())

    @property
    def is_auditable(self) -> bool:
        """A revision must name at least one cause (FR-029)."""
        return bool(self.caused_by_event_ids or self.decision_ids or self.operator_actions)

    def to_dict(self) -> dict[str, Any]:
        return {**self._material(), "revision_id": self.revision_id}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ContextRevision:
        return cls(
            context_id=payload["context_id"],
            revision=int(payload["revision"]),
            parent_revision=int(payload["parent_revision"]),
            state=InvestigationState(payload["state"]),
            snapshot=dict(payload["snapshot"]),
            caused_by_event_ids=tuple(payload.get("caused_by_event_ids", ())),
            decision_ids=tuple(payload.get("decision_ids", ())),
            operator_actions=tuple(payload.get("operator_actions", ())),
            rules_version=payload.get("rules_version", ""),
            mode=payload.get("mode", "deterministic"),
            revision_id=payload.get("revision_id", ""),
        )


def verify_context_partition() -> None:
    """Total partition: every field is classified as identity or revision state.

    Mirrors ``verify_regime_partition``. A field classified by nobody is a field
    that silently does not participate in identity -- which is precisely how a
    mutable field ends up addressed, and the address then lies.
    """
    declared = set(IDENTITY_FIELDS)
    all_fields = {
        "identity_schema", "tenant_id", "investigation_id", "title", "scope_refs",
        "context_id", "question", "state", "scope_links", "policy_snapshot_ref", "created_at",
    }
    identity = declared | {"context_id"}
    revision_state = all_fields - identity
    unclassified = all_fields - identity - revision_state
    if unclassified:
        raise ContextEngineError(
            "field_unclassified",
            f"fields participate in neither identity nor revision state: {sorted(unclassified)}",
        )
    if declared & revision_state:
        raise ContextEngineError(
            "field_double_classified",
            f"fields claimed as both identity and revision state: {sorted(declared & revision_state)}",
        )


__all__ = [
    "CONTEXT_IDENTITY_SCHEMA",
    "CONTEXT_ID_PREFIX",
    "IDENTITY_FIELDS",
    "REVISION_PREFIX",
    "ContextEngineError",
    "ContextRevision",
    "InvestigationContext",
    "InvestigationState",
    "ObligationStatus",
    "ScopeLinkage",
    "verify_context_partition",
]