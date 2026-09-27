"""Relation store, claim minting and graph projection (feature 016, T025/T075).

Contracts: ``data-model.md`` section 9, ``contracts/service-contracts.md``
(``RelationStore``, ``RelationClaimService``, ``GraphProjectionBridge``).

Three boundaries, one direction. ``RelationClaimService`` is the *sole* minter of
``logical_relation_id`` / ``relation_id`` (FR-003, FR-004): the store and the
bridge take an id as an input and never generate one, because an id a store
invented could not be recomputed from the record it keys.

``InMemoryRelationStore`` is the reference implementation and the rebuild oracle:
provenance enforced on every write (I-12), idempotent on ``relation_id`` (I-11),
no delete (I-3), and a ``checksum`` that is order-independent so a rebuild is
compared by value rather than by "it ran" (FR-040, SC-011).

``GraphProjectionBridge`` adapts a claim onto the existing graph types. The graph
is a PROJECTION, not the source of truth (constitution III, I-4): claims flow out
and nothing flows back, so dropping the whole graph loses no knowledge.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from domain import enforce_projection_provenance
from domain.relation_claim import (
    DEFAULT_CONFIDENCE,
    RelationClaim,
    RelationContractError,
    RelationRoleBinding,
    RelationStatus,
)
from domain.relation_identity import (
    LOGICAL_ID_PREFIX,
    REVISION_ID_PREFIX,
    IdentityCollision,
    RelationArityMode,
    detect_identity_collisions,
    digest128,
    recompute_identity,
)

import path_shim  # noqa: F401 - ensure apps/shared precedes conflicting dirs

if TYPE_CHECKING:
    from graph.abstraction import GraphEdge, GraphNode, HyperEdge

#: Stand-in ids a claim carries for the one construction step before its identity
#: is derived. Prefixed like a real id so a leaked intermediate is recognisable,
#: and never a valid digest, so it cannot collide with a minted one.
_PENDING_LOGICAL = f"{LOGICAL_ID_PREFIX}pending"
_PENDING_REVISION = f"{REVISION_ID_PREFIX}pending"

#: Modes whose reverse is a *different* relation, so a lookup may only match the
#: subject: matching the object would answer "who is this person?" with the
#: inverse edge (FR-010). Only ``DIRECTED`` — a directed relation is directional
#: whether or not it also carries a validity window, because temporality is
#: ``TemporalSemantics``, not arity.
_DIRECTIONAL_MODES = (RelationArityMode.DIRECTED,)


def _all_participants(claim: RelationClaim) -> tuple[str, ...]:
    """Every participant of ``claim`` in declaration order, deduplicated."""
    refs = [claim.subject_ref, claim.object_ref]
    refs.extend(binding.member_ref for binding in claim.role_bindings)
    return tuple(dict.fromkeys(refs))


def _lookup_refs(claim: RelationClaim) -> tuple[str, ...]:
    """Refs from which ``claim`` is reachable through ``participants(ref)``.

    Directional: a ``DIRECTED`` claim is reachable from its subject only. An
    ``UNDIRECTED``/``NARY`` claim is symmetric, so either endpoint and every
    role member match.
    """
    if claim.arity_mode in _DIRECTIONAL_MODES:
        return (claim.subject_ref,)
    return _all_participants(claim)


@runtime_checkable
class RelationStore(Protocol):
    """Durable, tenant-scoped relation revisions (``data-model.md`` section 9)."""

    def write(self, claim: RelationClaim, *, provenance: Mapping[str, Any]) -> str: ...
    def get(self, relation_id: str) -> RelationClaim | None: ...
    def revisions(self, logical_relation_id: str) -> tuple[RelationClaim, ...]: ...
    def by_type(
        self, relation_type: str, *, active_at: datetime | None = None
    ) -> list[RelationClaim]: ...
    def participants(self, ref: str) -> list[RelationClaim]: ...
    def checksum(self) -> str: ...


@dataclass
class InMemoryRelationStore:
    """Reference ``RelationStore``: the test oracle and the rebuild oracle.

    The store NEVER invents, mutates or re-derives a ``relation_id``. The id is
    the caller's (in practice ``RelationClaimService``'s) and is the sole key: a
    store that cannot resolve an id is a bug, not a condition to be repaired by
    generating a fallback — the same decision ``HyperGraph.upsert`` and
    ``GraphEdge.edge_id`` make (FR-035).
    """

    def __post_init__(self) -> None:
        self._claims: dict[str, RelationClaim] = {}
        self._revision_ids: dict[str, list[str]] = {}  # logical id -> [relation_id]
        self._by_type: dict[str, set[str]] = {}
        self._by_participant: dict[str, set[str]] = {}

    def write(self, claim: RelationClaim, *, provenance: Mapping[str, Any]) -> str:
        """Store ``claim`` under its own id and return that id (I-11, I-12).

        Provenance is enforced *first*, so a refused write leaves the store
        byte-identical. Re-writing identical content is a no-op returning the
        existing id; the same id carrying different content is an identity
        collision and is refused with the stored row preserved (FR-011). No
        status is ever deleted — a superseded, retracted or contradicted claim
        stays readable forever (I-3).
        """
        enforce_projection_provenance(provenance)
        if not claim.context_ref:
            raise RelationContractError(
                "context_ref_required",
                "a claim is admitted only with an evidence context ref (I-12, FR-007)",
            )
        stored = self._claims.get(claim.relation_id)
        if stored is not None:
            if stored.content_hash != claim.content_hash:
                raise RelationContractError(
                    "identity_collision",
                    f"relation_id {claim.relation_id} is already stored with a different "
                    "content_hash; the stored row is preserved (FR-011)",
                )
            return claim.relation_id
        self._claims[claim.relation_id] = claim
        self._revision_ids.setdefault(claim.logical_relation_id, []).append(claim.relation_id)
        self._by_type.setdefault(claim.relation_type, set()).add(claim.relation_id)
        for ref in _lookup_refs(claim):
            self._by_participant.setdefault(ref, set()).add(claim.relation_id)
        return claim.relation_id

    def get(self, relation_id: str) -> RelationClaim | None:
        """The claim under this id, or ``None`` — never a default row (FR-016)."""
        return self._claims.get(relation_id)

    def revisions(self, logical_relation_id: str) -> tuple[RelationClaim, ...]:
        """Every revision of one logical relation, ordered by ``revision_number``.

        Non-``ACTIVE`` revisions are included, so "all versions of this relation"
        is always answerable (I-3, I-4). The last element is current.
        """
        claims = [self._claims[rid] for rid in self._revision_ids.get(logical_relation_id, [])]
        return tuple(sorted(claims, key=lambda claim: (claim.revision_number, claim.relation_id)))

    def by_type(
        self, relation_type: str, *, active_at: datetime | None = None
    ) -> list[RelationClaim]:
        """Claims of one type, ordered by ``relation_id``.

        ``active_at`` filters on ``is_active_at``, so a reader asking "what was
        true then" never has to re-implement the half-open window.
        """
        claims = [self._claims[rid] for rid in self._by_type.get(relation_type, set())]
        if active_at is not None:
            claims = [claim for claim in claims if claim.is_active_at(active_at)]
        return sorted(claims, key=lambda claim: claim.relation_id)

    def participants(self, ref: str) -> list[RelationClaim]:
        """Claims reachable from ``ref``, ordered by ``relation_id``.

        Directional, so a ``DIRECTED`` lookup from the object does not return
        the inverse relation (FR-010).
        """
        return sorted(
            (self._claims[rid] for rid in self._by_participant.get(ref, set())),
            key=lambda claim: claim.relation_id,
        )

    def checksum(self) -> str:
        """Order-independent digest over the claim set (FR-040, SC-011).

        Claims are sorted by ``relation_id`` and digested over their
        ``content_hash`` values only, so the checksum is stable under insertion
        order and under property reordering, and any change to any claim's
        content changes it.
        """
        material = "\n".join(claim.content_hash for claim in self._ordered())
        return digest128(material)

    def detect_collisions(self) -> tuple[IdentityCollision, ...]:
        """Every identity collision in the stored claim set (FR-011).

        Delegated to the domain detector: a collision is reported with the
        colliding id and the claims involved, never merged into one row.
        """
        return detect_identity_collisions(self._ordered())

    def _ordered(self) -> list[RelationClaim]:
        return [self._claims[relation_id] for relation_id in sorted(self._claims)]

    def __len__(self) -> int:
        return len(self._claims)


class RelationClaimService:
    """The only entry point permitted to mint a relation identity (FR-003).

    Both identity levels are derived here, so a caller can never hand in a
    forged id: the store, the validator and the projection all re-derive the
    same pair from the claim's own fields and must agree. Determinism is total —
    the same arguments always yield the same ``relation_id`` — which is what
    makes the store idempotent structurally rather than by a dedup flag (I-11).

    Minting performs no I/O: persistence is a separate, explicit decision by the
    caller (constitution III, I-4).
    """

    def __init__(
        self,
        *,
        tenant_id: str = "default-tenant",
        investigation_id: str = "",
        created_by: str = "",
        store: RelationStore | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.investigation_id = investigation_id
        self.created_by = created_by
        self.store = store
        self._revisions: dict[str, int] = {}

    def build(
        self,
        *,
        relation_type: str,
        arity_mode: RelationArityMode,
        subject_ref: str,
        object_ref: str,
        context_ref: str,
        role_bindings: tuple[RelationRoleBinding, ...] = (),
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
        observed_at: datetime | None = None,
        published_at: datetime | None = None,
        assertion_refs: tuple[str, ...] = (),
        observation_refs: tuple[str, ...] = (),
        source_independence_groups: tuple[tuple[str, ...], ...] = (),
        extraction_version: str = "",
        normalization_version: str = "",
        ontology_version: str = "",
        schema_version: str = "",
        confidence: float = DEFAULT_CONFIDENCE,
        supersedes: str = "",
        contradicts: tuple[str, ...] = (),
        revision_number: int = 1,
        status: RelationStatus = RelationStatus.ACTIVE,
    ) -> RelationClaim:
        """Mint one claim: ``logical_relation_id`` then ``relation_id``.

        Every refusal happens *before* an identifier is derived, so a failed call
        cannot leave a partially-minted identity behind. An empty or whitespace
        ``context_ref`` is refused: a claim is admitted only inside an evidence
        frame (I-12, FR-007).
        """
        if not context_ref or not str(context_ref).strip():
            raise RelationContractError(
                "context_ref_required",
                "a claim is admitted only with an evidence context ref (I-12, FR-007)",
            )
        mode = RelationArityMode(arity_mode)
        bindings = tuple(role_bindings)
        claim = RelationClaim(
            relation_id=_PENDING_REVISION,
            logical_relation_id=_PENDING_LOGICAL,
            revision_number=revision_number,
            relation_type=relation_type,
            arity_mode=mode,
            subject_ref=subject_ref,
            object_ref=object_ref,
            role_bindings=bindings,
            valid_from=valid_from,
            valid_to=valid_to,
            observed_at=observed_at,
            published_at=published_at,
            assertion_refs=tuple(assertion_refs),
            observation_refs=tuple(observation_refs),
            context_ref=context_ref,
            source_independence_groups=tuple(
                tuple(group) for group in source_independence_groups
            ),
            extraction_version=extraction_version,
            normalization_version=normalization_version,
            ontology_version=ontology_version,
            schema_version=schema_version,
            status=status,
            confidence=confidence,
            tenant_id=self.tenant_id,
            investigation_id=self.investigation_id,
            created_by=self.created_by,
            supersedes=supersedes,
            contradicts=tuple(contradicts),
        )
        # Derived from the claim, not from a hand-kept copy of the material: the
        # revision material is defined once, in ``domain.relation_identity``, and
        # a second transcription of it here is exactly how a field would come to
        # be silently missing from every minted id.
        logical, revision = recompute_identity(claim)
        claim = replace(claim, logical_relation_id=logical, relation_id=revision)
        if recompute_identity(claim) != (logical, revision):
            raise RelationContractError(
                "identity_mismatch",
                f"minted ids do not re-derive for relation {revision!r}; refusing (FR-004)",
            )
        self._revisions[logical] = max(self._revisions.get(logical, 0), revision_number)
        return claim

    def next_revision(self, logical_relation_id: str) -> int:
        """The next free revision number of one logical relation (FR-006)."""
        self._revisions[logical_relation_id] = self._revisions.get(logical_relation_id, 1) + 1
        return self._revisions[logical_relation_id]

    def register(
        self,
        claim: RelationClaim,
        *,
        provenance: Mapping[str, Any],
        store: RelationStore | None = None,
    ) -> str:
        """Push a minted claim into a store and return its id.

        Persistence is the caller's decision, so a store must be named here or
        bound on the service; with neither this refuses rather than silently
        dropping the claim. The bound store is read with ``is not None`` rather
        than truthiness: an empty store is falsey.
        """
        target = store if store is not None else self.store
        if target is None:
            raise RelationContractError(
                "no_store_bound",
                "register needs a RelationStore; minting never persists by itself (I-4)",
            )
        return target.write(claim, provenance=provenance)


class GraphProjectionBridge:
    """Map a stored claim onto the existing graph types (one way, no back-flow).

    The graph is a PROJECTION, not the source of truth (constitution III, I-4):
    no read path may answer a claim, context or verdict question from a graph
    store alone — every such answer is served from ``RelationStore`` and the
    durable event log. No identifier is generated here: ``edge_id`` is
    ``claim.relation_id``, supplied by the relation layer (FR-035). ``context_ref``
    travels as a REFERENCE (FR-018), never a copy of the frame, so one shared
    context cannot fork into per-edge duplicates.
    """

    def to_node(self, claim: RelationClaim, ref: str = "") -> GraphNode:
        """One participant of ``claim`` as a node; ``ref`` defaults to the subject.

        The node type is the role the participant fills, or ``Entity`` when it is
        a bare endpoint.
        """
        from graph.abstraction import GraphNode

        node_ref = ref or claim.subject_ref
        return GraphNode(
            node_id=node_ref,
            node_type=self._role_of(claim, node_ref) or "Entity",
            properties={
                "relation_id": claim.relation_id,
                "logical_relation_id": claim.logical_relation_id,
                "arity_mode": str(claim.arity_mode),
                "tenant_id": claim.tenant_id,
            },
        )

    def to_nodes(self, claim: RelationClaim) -> tuple[GraphNode, ...]:
        """Every participant of ``claim`` as a node, in declaration order.

        Both endpoints are emitted even for a directed claim, because the graph
        store refuses an edge whose endpoints do not exist.
        """
        return tuple(self.to_node(claim, ref) for ref in _all_participants(claim))

    def to_edge(self, claim: RelationClaim) -> GraphEdge:
        """The claim as a plain edge, direction preserved.

        Direction MUST survive the projection: a ``DIRECTED`` claim keeps
        ``subject -> object`` and is read back with ``direction="out"``,
        because symmetric adjacency is fixed on read (FR-010), never by flipping
        the endpoints here. The N-ary form stays authoritative; any pairwise
        expansion is an explicitly derived, lossy view (FR-045).
        """
        from graph.abstraction import GraphEdge

        return GraphEdge(
            edge_id=claim.relation_id,
            edge_type=claim.relation_type,
            source=claim.subject_ref,
            target=claim.object_ref,
            properties=self.properties(claim),
        )

    def to_hyperedge(self, claim: RelationClaim) -> HyperEdge:
        """The claim as ONE hyperedge over its role members (FR-045).

        Never a clique: the N-ary form is the authoritative projection, so a
        pairwise expansion is a derived, lossy view and never the only
        representation. Both identities travel in the properties — the
        ``relation_id`` plus the projection's own ``edge_id`` derivation.
        """
        from graph.abstraction import HyperEdge

        if claim.arity_mode is not RelationArityMode.NARY:
            raise ValueError(
                f"hyperedge projection requires an nary claim, got {claim.arity_mode}"
            )
        return HyperEdge(
            edge_type=claim.relation_type,
            source=tuple(binding.member_ref for binding in claim.role_bindings),
            properties={
                **self.properties(claim),
                "role_map": {
                    binding.role: binding.member_ref for binding in claim.role_bindings
                },
            },
        )

    def properties(self, claim: RelationClaim) -> dict[str, Any]:
        """The property payload both projections carry.

        Enough to answer "why does this edge exist?" without joining back to the
        durable store: both identity levels, the revision, the context reference,
        the window, the lifecycle, the evidence grade, the evidence refs and the
        version triple.
        """
        return {
            "relation_id": claim.relation_id,
            "logical_relation_id": claim.logical_relation_id,
            "revision_number": claim.revision_number,
            "arity_mode": str(claim.arity_mode),
            "context_ref": claim.context_ref,
            "valid_from": claim.valid_from.isoformat() if claim.valid_from else None,
            "valid_to": claim.valid_to.isoformat() if claim.valid_to else None,
            "status": str(claim.status),
            "evidence_grade": str(claim.evidence_grade),
            "observation_refs": list(claim.observation_refs),
            "assertion_refs": list(claim.assertion_refs),
            "tenant_id": claim.tenant_id,
            "investigation_id": claim.investigation_id,
            "extraction_version": claim.extraction_version,
            "normalization_version": claim.normalization_version,
            "ontology_version": claim.ontology_version,
            "schema_version": claim.schema_version,
        }

    @staticmethod
    def _role_of(claim: RelationClaim, ref: str) -> str:
        """The role ``ref`` fills in ``claim``, or ``""`` for a bare endpoint."""
        for binding in claim.role_bindings:
            if binding.member_ref == ref:
                return binding.role
        return ""


__all__ = [
    "GraphProjectionBridge",
    "InMemoryRelationStore",
    "RelationClaimService",
    "RelationStore",
]
