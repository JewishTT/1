# Service Contracts: Relation & Evidence Graph Fabric

**Feature**: [016-relation-evidence-graph-fabric](../spec.md) | **Date**: 2026-09-26

Interface-level contracts for the components introduced or changed by this feature. These
are the boundaries constitution V (Plugability by contract) requires: no vendor-specific
type crosses into domain logic, and every contract is independently testable against an
in-memory implementation. Every write path upholds I-11 (idempotency) and I-12
(provenance enforced) without exception.

The value types these contracts exchange are defined in
[data-model.md](../data-model.md) and are not restated here beyond what a signature needs.
Two value types are defined in `apps/shared/domain/relation_identity.py` and re-exported
from `apps/shared/domain/relation_claim.py` (rather than the reverse) so that identity
derivation never imports the claim type: `RelationArityMode`, `RelationRoleBinding`,
`RelationContractError`.

---

## Contract inventory

| Contract | Kind | Module | Reference implementation | Primary obligations |
| --- | --- | --- | --- | --- |
| `RelationClaimService` | protocol | `domain.relation_claim` | `RelationClaimService` (in-memory) | sole minter of `logical_relation_id` / `relation_id`; refuses empty `context_ref` (I-12) |
| `RelationStore` | protocol | `graph.relation_store` | `InMemoryRelationStore` | provenance on every write (I-12), idempotent on `relation_id` (I-11), no status is ever deleted (I-3) |
| `ContextRegistry` | protocol | `domain.evidence_context` | `InMemoryContextResolver` | idempotent on `context_id`; `None` on unknown; no default substitution |
| `ContextValidator` | protocol + pure function | `domain.context_validation` | `validate()` | seven layers always reported, graded verdict, never a bool, never mutates inputs |
| `RelationSchemaRegistry` | class | `domain.relation_schema` | `RelationSchemaRegistry` | single read path for the relation vocabulary (FR-028) |
| `EvidenceLineageProvider` | protocol | `domain.evidence_lineage` | `EvidenceGraph` | bidirectional lineage, explicit incompleteness (FR-033) |
| `IndependenceResolver` | protocol + function | `domain.evidence_lineage` | `IndependenceResolver` / `independence_groups()` | copied sources collapse; publication count never substituted (constitution IV) |
| `GraphProjectionBridge` | protocol | `graph.relation_store` | `InMemoryGraphProjectionBridge` | adapts claims to `GraphNode`/`GraphEdge`/`HyperEdge`; graph stays a projection (I-4) |

Direction of dependency is strictly one way: `RelationClaimService` → `RelationStore`,
`ContextValidator` → `ValidationWorld` → (`RelationSchemaRegistry`, `ContextRegistry`),
`GraphProjectionBridge` → (`RelationStore`, `GraphStore`). No contract below calls back
upward, and no domain module imports anything from `apps/projection`.

---

## `RelationClaimService`

**Purpose.** The only entry point permitted to mint a `logical_relation_id` or a
`relation_id`. It takes participants, an arity mode, a context reference and evidence
references, derives both identity levels, and returns a fully validated frozen
`RelationClaim`. No other component may construct a `relation_id` (FR-003, FR-004, FR-005).

```python
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from domain.relation_identity import (
    RelationArityMode, RelationRoleBinding, logical_relation_id, relation_id,
)
from domain.relation_claim import DEFAULT_CONFIDENCE, RelationClaim


class RelationClaimService(Protocol):
    def claim(
        self,
        *,
        tenant_id: str,
        relation_type: str,
        arity_mode: RelationArityMode,
        participants: Sequence[str],
        context_ref: str,
        role_bindings: Sequence[RelationRoleBinding] = (),
        evidence_refs: Sequence[str] = (),
        observation_refs: Sequence[str] = (),
        assertion_refs: Sequence[str] = (),
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
        observed_at: datetime | None = None,
        published_at: datetime | None = None,
        known_from: datetime | None = None,
        known_until: datetime | None = None,
        source_independence_groups: Sequence[Sequence[str]] = (),
        extraction_version: str = "",
        normalization_version: str = "",
        ontology_version: str = "",
        schema_version: str = "",
        confidence: float = DEFAULT_CONFIDENCE,
        created_by: str = "",
        supersedes: str = "",
        contradicts: Sequence[str] = (),
    ) -> RelationClaim: ...

    def next_revision(
        self,
        prior: RelationClaim,
        *,
        supersedes: str | None = None,
        **changes: object,
    ) -> RelationClaim: ...
```

`claim` is pure: no I/O, no clock read, no store access. Determinism is total — the same
arguments always yield the same `relation_id`. `next_revision(prior, **changes)` re-derives
identity for changed content, sets `revision_number = prior.revision_number + 1`,
`supersedes = supersedes or prior.relation_id`, and preserves `logical_relation_id`,
`tenant_id` and `investigation_id` from `prior`.

**Invariants**

| # | Invariant | Tag |
| --- | --- | --- |
| 1 | The service is the sole producer of `logical_relation_id` and `relation_id`; a caller cannot supply either. | FR-003, FR-004 |
| 2 | `context_ref == ""` is refused; no claim is ever minted without a context reference. | I-12, FR-007 |
| 3 | Participant canonicalisation follows the arity mode: `UNDIRECTED` sorts, `DIRECTED` preserves order, `NARY` sorts by `(role, member)`, `TEMPORAL` preserves order and folds the window in. | FR-004, FR-008, FR-009 |
| 4 | A self-loop (`subject_ref == object_ref`) is refused; an `NARY` relation with fewer than two distinct members, or with a repeated member, is refused. | FR-002 |
| 5 | `DIRECTED` with non-empty `role_bindings` is refused; arity mode is part of the identity material, so the same participants under a different mode yield a different id. | FR-002, FR-004 |
| 6 | Two claims with identical material are byte-identical, including both ids (this is what makes the store idempotent structurally). | I-11, FR-005 |
| 7 | A revised claim shares `logical_relation_id` with its predecessor and receives a distinct `relation_id`; the predecessor is never mutated, only superseded. | I-4, FR-003, FR-006 |
| 8 | `content_hash` is a `digest128` over the full serialised field set; `publication_count` (`len(observation_refs)`) and `independent_source_count` (`len(source_independence_groups)`) are computed and exposed separately, never collapsed into one number. | constitution IV, FR-025, FR-034 |
| 9 | Nothing is written to any store by this contract; persistence is a separate decision by the caller. | I-4, constitution III |

**Failure modes**

| Condition | Exception / reason code | State changed |
| --- | --- | --- |
| `context_ref` empty or whitespace | `RelationContractError("context_ref_required")` | no — no id minted |
| `relation_type` empty | `RelationContractError("relation_type_required")` | no |
| `subject_ref == object_ref` | `RelationContractError("self_loop_relation")` | no |
| `arity_mode is NARY` and `len(role_bindings) < 2` | `RelationContractError("nary_too_few_members")` | no |
| `arity_mode is NARY` and a member repeats across roles | `RelationContractError("nary_duplicate_member")` naming the role | no |
| `arity_mode is DIRECTED` and `role_bindings` non-empty | `RelationContractError("directed_role_binding_forbidden")` | no |
| `participants` empty or contains an empty string | `RelationContractError("participant_ref_required")` | no |
| `valid_to < valid_from` | `RelationContractError("temporal_interval_inverted")` | no |
| `confidence` outside `[0.0, 1.0]` | `RelationContractError("confidence_out_of_range")` | no |
| `next_revision` given `supersedes` equal to the new `relation_id` | `RelationContractError("self_supersession")` | no |

Every refusal is a `ValueError` subclass and happens **before** any identifier is derived,
so a failed call cannot leave a partially-minted identity behind.

**Reference implementation**: `apps/shared/domain/relation_claim.py` (identity derivation
in `apps/shared/domain/relation_identity.py`).

---

## `RelationStore`

**Purpose.** Owns the durable, tenant-scoped set of relation revisions. Enforces provenance
on every write and idempotency on `relation_id`; never invents an identifier and never
deletes a claim.

```python
from datetime import datetime
from typing import Any, Mapping, Protocol

from domain.relation_claim import RelationClaim


class RelationStore(Protocol):
    def write(self, claim: RelationClaim, *, provenance: Mapping[str, Any]) -> str: ...
    def get(self, relation_id: str) -> RelationClaim | None: ...
    def revisions(self, logical_relation_id: str) -> tuple[RelationClaim, ...]: ...
    def by_type(self, relation_type: str, *, active_at: datetime | None = None) -> list[RelationClaim]: ...
    def participants(self, ref: str) -> list[RelationClaim]: ...
    def checksum(self) -> str: ...
```

**The store never mints an id.** `claim.relation_id` is supplied by the caller (in practice
by `RelationClaimService`) and is the sole key. A store that cannot resolve the id is a bug,
not a condition to be repaired by generating a fallback. This mirrors the existing
`GraphEdge.edge_id` decision in [data-model.md](../data-model.md) §9.1 and the
`HyperGraph.upsert` precedent in `apps/shared/domain/hypergraph.py`.

| Member | Contract |
| --- | --- |
| `write` | returns the `relation_id` it stored; a second write of the same claim returns the same id and leaves the count unchanged (I-11) |
| `get` | returns the claim, or `None`; a cross-tenant id returns `None`, never another tenant's row |
| `revisions` | every revision of one logical relation, ordered by `revision_number` ascending; the last element is current |
| `by_type` | filtered on `relation_type`, optionally on `is_active_at(active_at)`; deterministic order |
| `participants` | directional: for `DIRECTED`/`TEMPORAL` only `ref == subject_ref` matches; for `UNDIRECTED`/`NARY` either endpoint matches |
| `checksum` | order-independent: claims sorted by `relation_id`, then `digest128` over the joined `content_hash` list |

**Invariants**

| # | Invariant | Tag |
| --- | --- | --- |
| 1 | `write` refuses any call whose `provenance` lacks the required fields, delegating to `domain.enforce_projection_provenance`; the store is unchanged on refusal. | I-12, FR-007 |
| 2 | `write` is idempotent on `relation_id`: identical content re-written leaves the relation count and `checksum()` unchanged. | I-11, FR-005, FR-036, SC-012 |
| 3 | The store never invents, mutates or re-derives `relation_id` or `logical_relation_id`; a mismatch between a claim's own fields and its recomputed identity is refused, not corrected. | FR-003, FR-004 |
| 4 | A `SUPERSEDED`, `RETRACTED` or `CONTRADICTED` claim remains readable through `get` and `revisions` forever; there is no `delete`. | I-3, FR-006 |
| 5 | A write whose `relation_id` is already present with a **different** `content_hash` is refused as an identity collision and surfaced, never merged into one row. | FR-011 |
| 6 | `revisions` returns every revision including non-`ACTIVE` ones, so "all versions of this relation" is always answerable. | I-3, I-4 |
| 7 | Every read is tenant-scoped; a foreign identifier resolves to nothing, with no differing status, count or error text. | FR-048, constitution VII |
| 8 | `checksum()` is stable under insertion order and under property reordering, because it keys on `relation_id` and `content_hash` only. | FR-040, SC-011 |

**Failure modes**

| Condition | Exception / reason code | State changed |
| --- | --- | --- |
| `provenance` missing/empty | `ProjectionRebuildableError` (I-12) | no |
| `provenance` missing `event_id` or `observation_id` | `ProjectionRebuildableError` naming the missing fields | no |
| `claim.context_ref` empty | `RelationContractError("context_ref_required")` | no |
| existing `relation_id` with a different `content_hash` | `IdentityCollisionError` (subclass of `RelationContractError`), carrying both claims | no — the existing row is preserved untouched |
| existing `relation_id` with an identical `content_hash` | none — idempotent success, returns the same id | no |
| claim recomputes to a different `relation_id` | `RelationContractError("identity_revision_mismatch")` | no |
| cross-tenant `get` / `by_type` | none — `None` / empty list | no |

**Reference implementation**: `apps/projection/graph/relation_store.py`
(`InMemoryRelationStore`; production backends implement the same protocol against
PostgreSQL). Precedent for the upsert/idempotency shape:
`apps/shared/domain/hypergraph.py` → `HyperGraph.upsert`.

---

## `ContextRegistry`

**Purpose.** The frame store. Registers immutable content-addressed `EvidenceContext`
frames and resolves a claim's `context_ref` back to its frame, or to nothing at all.

```python
from typing import Protocol

from domain.evidence_context import EvidenceContext


class ContextRegistry(Protocol):
    def register(self, frame: EvidenceContext) -> str: ...
    def resolve(self, context_id: str) -> EvidenceContext | None: ...
    def parent_chain(self, context_id: str) -> tuple[EvidenceContext, ...]: ...
    def detect_cycle(self, frame: EvidenceContext) -> tuple[str, ...]: ...
```

Naming reconciliation with [data-model.md](../data-model.md) §5: the narrow two-member
`ContextResolver` protocol is the read side consumed by `ValidationWorld.contexts`. Every
`ContextRegistry` conforms to it, so a registry is passed to the validator unchanged; the
registry additionally exposes the parent-chain and cycle-detection members the validator
needs for `provenance_context_parent_missing` and `context_parent_cycle`.

**Invariants**

| # | Invariant | Tag |
| --- | --- | --- |
| 1 | `register` is idempotent on `context_id` and returns that id; re-registering an identical frame changes nothing. | I-11, FR-014 |
| 2 | `resolve` returns `None` for an unknown id. A caller that receives `None` **must** surface `context_unresolved` and quarantine; substituting a default frame is forbidden. | FR-016, I-12 |
| 3 | Frames are stored and shared by reference; no consumer may embed a mutable copy of a frame in a claim. | FR-018 |
| 4 | The stored frame is never mutated. `EvidenceContext` is frozen, and the registry holds it as-is. | FR-015, I-1 |
| 5 | Cycle detection lives here, not in the frame: `detect_cycle` returns the offending `context_id` path, and the frame itself remains storable even when its parent is missing. | FR-017 |
| 6 | `parent_chain` is ordered from the frame outward to its root and terminates on a cycle rather than looping. | FR-017 |

**Failure modes**

| Condition | Exception / reason code | State changed |
| --- | --- | --- |
| `resolve` on an unknown `context_id` | returns `None` (caller raises `context_unresolved`) | no |
| `register` of a frame with a `parent_context_id` that does not exist | accepted; frame storable, `parent_chain` stops and validation reports `provenance_context_parent_missing` | yes — the frame is stored (it is evidence, not a verdict) |
| `register` of a frame that closes a parent cycle | accepted into the registry; `detect_cycle` returns the cycle path and the validator reports `context_parent_cycle` | yes — stored, flagged |
| `register` of a frame with `valid_to < valid_from` | `RelationContractError("temporal_interval_inverted")` at construction | no |
| `register` attempted on a frame whose `context_id` is already present with different content | refused — the id is a content address, so different content cannot share it | no |

**Reference implementation**: `apps/shared/domain/evidence_context.py`
(`InMemoryContextResolver`).

---

## `ContextValidator`

**Purpose.** A pure, total function over `(context, claim, world)` that evaluates exactly
seven layers, always reports all seven outcomes, and returns one graded verdict with
structured reasons. It is not a boolean and it does no I/O.

```python
from typing import Protocol

from domain.context_validation import ValidationResult, ValidationWorld
from domain.evidence_context import EvidenceContext
from domain.relation_claim import RelationClaim


class ContextValidator(Protocol):
    def validate(
        self,
        context: EvidenceContext | None,
        claim: RelationClaim,
        world: ValidationWorld,
    ) -> ValidationResult: ...


def validate(
    context: EvidenceContext | None,
    claim: RelationClaim,
    world: ValidationWorld,
) -> ValidationResult: ...
```

The module-level `validate()` is the canonical reference implementation; any object
exposing the same three-argument `validate` conforms, and the two must be asserted
equivalent by test.

```python
@dataclass(frozen=True)
class ValidationWorld:
    schemas: RelationSchemaRegistry
    contexts: ContextResolver
    admitted_entity_ids: frozenset[str] = frozenset()
    known_entity_ids: frozenset[str] = frozenset()
    active_ontology_versions: frozenset[str] = frozenset()
    known_ontology_versions: frozenset[str] = frozenset()
    sibling_claims: tuple[RelationClaim, ...] = ()
```

`ValidationWorld` is the **injection point** that makes the validator pure. Everything
external is pre-resolved into the world: the schema registry, the context resolver, the
admitted/known entity id sets, the active/known ontology version sets, and the sibling
claims used for interval-conflict detection. A layer therefore never opens a socket, a
session or a clock, and the two expensive layers (`cross_source`, `graph_constraints`)
consume sets and pre-computed groups rather than traversing anything.

`context=None` short-circuits to `INVALID / provenance_context_missing` with **all seven
layers still reported**, so a caller never has to distinguish "short-circuited" from
"fully evaluated" by inspecting the layer count.

**Invariants**

| # | Invariant | Tag |
| --- | --- | --- |
| 1 | Exactly seven layers are evaluated, in order: `structural`, `semantic`, `temporal`, `provenance`, `identity`, `cross_source`, `graph_constraints`. All seven appear in `result.layers` regardless of an earlier failure. | FR-019, SC-004 |
| 2 | The return value is a `ValidationResult`; there is no `bool`-returning overload, and no reason code is communicated out of band. A non-`VALID` verdict always carries a non-empty `reasons` tuple. | FR-020, FR-021, SC-004 |
| 3 | Neither the claim nor the context is mutated. A test asserts the inputs' `content_hash` and `context_id` are unchanged across a call. | FR-021 |
| 4 | No I/O: the validator is a pure function of its three arguments. | I-4, plan performance goal |
| 5 | An unregistered relation type yields `UNDERDETERMINED / schema_unregistered` and the claim is preserved; an unknown relation is not a false one. | FR-023, SC-008 |
| 6 | Publication before observation is reported as `temporal_publication_before_observation` without rejecting (archive backfill is legitimate); disjoint sibling intervals record `temporal_non_overlap` and stay `VALID`. | FR-024, spec edge cases |
| 7 | Cross-tenant evidence yields `INVALID / provenance_tenant_mismatch`; it is never silently accepted. | FR-022, SC-007 |
| 8 | `grade_components` stores `independent_source_count`, `publication_count`, `completeness`, `trust_state` and `confidence` as **separate** entries. No single score is computed from them. | constitution IV, FR-025 |
| 9 | Layer short-circuiting affects only the collapsed verdict; every layer's own outcome is still computed and reported. | FR-019 |
| 10 | An inverted interval is refused at construction and *also* reported by the temporal layer for claims arriving from persistence, where construction has already run. | SC-005, [data-model.md](../data-model.md) §4.2 |

**Verdict precedence** (first match wins): `INVALID > CONFLICTING > STALE > INCOMPLETE >
UNDERDETERMINED > VALID`. The precedence is a fixed total order, not "any failure is
invalid" — collapsing staleness and incompleteness into falsehood is what the constitution
forbids (I-3).

**Failure modes**

| Condition | Exception / reason code | State changed |
| --- | --- | --- |
| never throws for a domain defect | the defect becomes a `ValidationReason` with a stable `code`, its `layer`, a `detail` and `evidence` refs | no |
| `claim.relation_type` not registered | reason `schema_unregistered`, layer `semantic`, outcome `INDETERMINATE`, verdict `UNDERDETERMINED` | no |
| `context_ref` does not resolve | reason `context_unresolved`, layer `provenance`, verdict `INVALID` | no |
| `context` argument is `None` | reason `provenance_context_missing`, all seven layers reported, verdict `INVALID` | no |
| world missing a required pre-computed input for an expensive layer | that layer is `INDETERMINATE` with its own reason; it is never silently `PASSED` | no |
| claim recomputes to a different identity | `identity_logical_mismatch` / `identity_revision_mismatch`, layer `identity`, verdict `INVALID` | no |

**Reference implementation**: `apps/shared/domain/context_validation.py`.

---

## `RelationSchemaRegistry`

**Purpose.** The single read path for the relation vocabulary: which relation types exist,
what classes and roles they admit, what temporal semantics they require, which admission
rule applies, and at which schema version.

```python
from domain.relation_identity import RelationArityMode
from domain.relation_schema import RelationSchema


class RelationSchemaRegistry:
    def register(self, schema: RelationSchema) -> RelationSchema: ...
    def get(self, relation_type: str) -> RelationSchema | None: ...
    def vocabulary(self) -> tuple[RelationSchema, ...]: ...
    def arity_of(self, relation_type: str) -> RelationArityMode | None: ...
```

| Member | Contract |
| --- | --- |
| `register` | returns the stored schema; rejects a shape that contradicts its declared arity; rejects a same-`schema_version` redefinition with different content; accepts a **new** `schema_version` for the same type |
| `get` | the current schema for a type, or `None` — never a default schema |
| `vocabulary` | the whole vocabulary in deterministic order (sorted by `relation_type`) |
| `arity_of` | the declared arity mode, or `None`; the validator uses it to check that a claim's declared arity matches the schema |

**Invariants**

| # | Invariant | Tag |
| --- | --- | --- |
| 1 | **The registry is the only place the relation list exists.** No extractor, validator, admission rule, API route, UI constant or test fixture may embed its own copy of the relation vocabulary. Any consumer that needs the list calls `vocabulary()`. | FR-028 |
| 2 | `vocabulary()` is deterministically ordered, so two calls with the same contents enumerate identically. | FR-028 |
| 3 | Registration rejects `DIRECTED` with role bindings, and `NARY` with fewer than two role bindings. | FR-012 |
| 4 | A claim records the `schema_version` in force when it was produced, and the validator compares it against the registered version rather than assuming the current one. | FR-029 |
| 5 | `temporal_semantics` is one of `POINT`, `REQUIRED_INTERVAL`, `OPTIONAL_INTERVAL`, `OPEN_ENDED`, and the temporal layer enforces it. | FR-027 |
| 6 | `get` returns `None` for an unknown type, and `None` is the only signal; the validator converts it to `UNDERDETERMINED / schema_unregistered`. It never invents a permissive default. | FR-023 |
| 7 | The registry holds declarations only. It never reads or writes claims, observations or contexts, so it cannot become a second source of truth. | constitution IV, I-4 |

**Failure modes**

| Condition | Exception / reason code | State changed |
| --- | --- | --- |
| `relation_type` empty | `RelationContractError("relation_type_required")` | no |
| `DIRECTED` schema with role bindings | `RelationContractError("arity_shape_conflict")` | no |
| `NARY` schema with fewer than two role bindings | `RelationContractError("arity_shape_conflict")` | no |
| same `relation_type` + same `schema_version`, different content | `SchemaVersionConflictError` | no |
| same `relation_type`, new `schema_version` | accepted; `get` returns the newest | yes — a new version is added |
| `get` on an unregistered type | returns `None` | no |

**Reference implementation**: `apps/shared/domain/relation_schema.py`.

---

## `EvidenceLineageProvider`

**Purpose.** Answers "why do you believe this?" in both directions over the chain
`Source → Capture → Observation → Segment → Mention → Candidate → Assertion → Relation →
Entity`, and reports incompleteness explicitly instead of truncating.

```python
from typing import Protocol

from domain.evidence_lineage import EvidenceHop, LineageTrace


class EvidenceLineageProvider(Protocol):
    def backward(self, node_id: str) -> LineageTrace: ...
    def forward(self, node_id: str) -> LineageTrace: ...
```

The reference implementation `EvidenceGraph` additionally carries the construction side
used by the projector:

```python
class EvidenceGraph:
    def add_hop(self, hop: EvidenceHop, *, forward: str, backward: str) -> None: ...
    def backward(self, node_id: str) -> LineageTrace: ...
    def forward(self, node_id: str) -> LineageTrace: ...
```

`add_hop(hop, forward=..., backward=...)` declares that this hop is derived **from**
`forward` and derives `backward`. Backward canonical order is
`RELATION → ASSERTION → MENTION → SEGMENT → OBSERVATION → CAPTURE → SOURCE`; forward order
is the reverse.

| Member | Contract |
| --- | --- |
| `backward` | every hop from a relation up to its source, each labelled with its `HopKind`; a hop with a `relation_id` set is carried through so forward traces show which assertion grounds a derived relation |
| `forward` | every relation derived from a node, each with the assertion that grounds it |
| `add_hop` | append-only; re-adding an identical hop is a no-op |

**Invariants**

| # | Invariant | Tag |
| --- | --- | --- |
| 1 | Traversal stops at the **first** missing hop and returns `complete=False` with `first_unresolved_hop` and `unresolved_node_id` set. It never returns a silently truncated list, and an empty list is never the representation of "cannot reach". | FR-033, SC-003 |
| 2 | A complete chain resolves from a relation id to a source id in the canonical order, with every hop present. | FR-031, SC-003 |
| 3 | Forward traversal from a source returns each derived relation with its grounding assertion. | FR-032 |
| 4 | Lineage is tenant-scoped; a hop whose `tenant_id` differs from the subject's is not traversed. | FR-048, constitution VII |
| 5 | Lineage is derived, never authoritative. The `RelationClaim` and the `EvidenceContext` remain the durable objects; a lineage trace can be dropped and recomputed. | constitution III, I-4, I-12 |
| 6 | A hop is a `(kind, node_id, relation_id, tenant_id)` value and carries no raw content. | constitution I, I-5 |

**Failure modes**

| Condition | Exception / reason code | State changed |
| --- | --- | --- |
| `backward` on an unknown node id | `LineageTrace(complete=False, first_unresolved_hop=RELATION, unresolved_node_id=node_id, hops=())` | no |
| a hop in the middle of the chain is absent | `complete=False`, `first_unresolved_hop` = the missing kind, `unresolved_node_id` = the dangling id | no |
| cycle in the adjacency (a hop reachable from itself) | traversal is depth-limited by the canonical chain order; the trace is marked `complete=False` at the repeated hop rather than recursing | no |
| cross-tenant hop encountered | the hop is not traversed; the trace is `complete=False` at that hop | no |

**Reference implementation**: `apps/shared/domain/evidence_lineage.py`.

---

## `IndependenceResolver`

**Purpose.** Collapses copied and derived sources into a single independent-origin group,
so that ten republications of one wire story count as one independent source — and stores
the publication count separately, never substituting one for the other.

```python
from collections.abc import Mapping, Sequence
from typing import Protocol


class IndependenceResolver(Protocol):
    def groups(
        self,
        observation_refs: Sequence[str],
        source_family_of: Mapping[str, str],
    ) -> tuple[tuple[str, ...], ...]: ...


def independence_groups(
    observation_refs: Sequence[str],
    source_family_of: Mapping[str, str],
) -> tuple[tuple[str, ...], ...]: ...
```

`IndependenceResolver.groups(...)` and the free function `independence_groups(...)` are the
same computation; the two are pinned equal by test so callers may use either. Output is
deterministic: groups are tuples of refs sorted ascending, and the group sequence is sorted
by its first member.

| Member | Contract |
| --- | --- |
| `groups` | one group per distinct resolved `source_family`; two captures of one family or one publisher land in a single group |

**Invariants**

| # | Invariant | Tag |
| --- | --- | --- |
| 1 | Two observations whose `source_family` resolves to the same value produce exactly one group, and the claim's `independent_source_count` is `1`, not `2`. | FR-034, US-6 scenario 4 |
| 2 | `publication_count` (`len(observation_refs)`) and `independent_source_count` (`len(groups)`) are stored and reported as **separate** fields. No code path may substitute one for the other, and no aggregate "confidence" is derived from them. | constitution IV, FR-025, FR-034 |
| 3 | A ref with no resolvable family forms its own singleton group and is reported, rather than being merged into another group's family by guesswork. | spec edge cases |
| 4 | One ref appearing under two different `source_family` values is **not** collapsed; the discrepancy is surfaced (`cross_source_family_conflict`) for the validator to report. | spec edge cases, FR-022 |
| 5 | `groups` is a pure function of its arguments — no I/O, no ordering dependence on the input sequence. | I-4 |

**Failure modes**

| Condition | Exception / reason code | State changed |
| --- | --- | --- |
| `observation_refs` empty | returns `()`; the validator reports `evidence_refs_empty` as `NOTED` | no |
| more than one observation and no group declared at all | returns singletons; the validator reports `independence_group_undeclared` as `INDETERMINATE` | no |
| a ref appears under two families | returned un-collapsed; `cross_source_family_conflict` is raised as a `ValidationReason` by the `cross_source` layer, not by this contract | no |
| `publication_count > independent_source_count` | not an error; `publication_count_exceeds_independent_count` is recorded as `NOTED` | no |

**Reference implementation**: `apps/shared/domain/evidence_lineage.py`.

---

## `GraphProjectionBridge`

**Purpose.** Adapts a stored `RelationClaim` (and its context and evidence hops) into the
**existing** `GraphStore` protocol as a `GraphNode`, `GraphEdge` or `HyperEdge`, so the
plain-edge and N-ary paths gain identity, context and version without a second graph API.

```python
from dataclasses import dataclass
from typing import Any, Mapping, Protocol, Literal

from domain.evidence_context import EvidenceContext
from domain.evidence_lineage import EvidenceHop
from domain.relation_claim import RelationClaim


@dataclass(frozen=True)
class ProjectionReceipt:
    relation_id: str
    kind: Literal["edge", "hyperedge", "node", "hop"]
    edge_id: str
    node_ids: tuple[str, ...]
    written: bool          # False when the write was an idempotent no-op


class GraphProjectionBridge(Protocol):
    def project_claim(
        self, claim: RelationClaim, *, provenance: Mapping[str, Any]
    ) -> ProjectionReceipt: ...

    def project_batch(
        self, claims: Sequence[RelationClaim], *, provenance: Mapping[str, Any]
    ) -> tuple[ProjectionReceipt, ...]: ...

    def project_context(
        self, frame: EvidenceContext, *, provenance: Mapping[str, Any]
    ) -> ProjectionReceipt: ...

    def project_hop(
        self, hop: EvidenceHop, *, provenance: Mapping[str, Any]
    ) -> ProjectionReceipt: ...
```

| Claim arity | Projected as | Identity |
| --- | --- | --- |
| `UNDIRECTED`, `DIRECTED`, `TEMPORAL` | `GraphEdge(edge_id=claim.relation_id, edge_type=claim.relation_type, source=claim.subject_ref, target=claim.object_ref, properties=…)` | `claim.relation_id` |
| `NARY` | `HyperEdge(edge_type=…, source=tuple(member refs), properties=…)` | `claim.relation_id` supplied via `properties["relation_id"]`; the existing `HyperEdge.edge_id` derivation is retained and both ids are carried |

`properties` always carries `relation_id`, `logical_relation_id`, `revision_number`,
`context_ref`, `evidence_grade`, `status`, `tenant_id`, `investigation_id` and the version
triple, so a projected edge can answer "why does this exist?" without a join back to the
durable store.

**Invariants**

| # | Invariant | Tag |
| --- | --- | --- |
| 1 | **The graph is a projection, not the source of truth.** No read path may answer a claim, context or verdict question from a graph store alone; every such answer is served from `RelationStore` / the durable event log. The bridge is one-way: claims flow out, nothing flows back. | I-4, constitution III, I-12 |
| 2 | Every projected write carries provenance and passes `enforce_projection_provenance`; a projection write without `event_id`/`observation_id` is refused and the graph is unchanged. | I-12 |
| 3 | Projection is idempotent: projecting the same claim twice leaves the edge count unchanged, on the pairwise **and** the N-ary path. The N-ary guard is fixed to key on `edge.edge_id`, because the current `if edge in self._hyperedges` compares a `HyperEdge` against `str` keys and never fires. | I-11, FR-037, SC-012 |
| 4 | `GraphEdge` carries `edge_id`; `__hash__`/`__eq__` key on `(edge_id,)` so two edges with identical endpoints but different ids are distinct entries, and idempotency is by id rather than by triple. | FR-035 |
| 5 | Direction is preserved on write and honoured on read: `neighbors(node, edge_type, direction)` supports `{"in","out","both"}`, defaulting to `out` for `DIRECTED`/`TEMPORAL` and `both` for `UNDIRECTED`/`NARY`. The current implementation adds every directed edge to both endpoints' adjacency and returns the union, which destroys direction on read; that is fixed, not preserved. | FR-010, US-2 scenario 5 |
| 6 | The N-ary form is the authoritative projection. Any pairwise expansion is an explicitly derived, lossy view (`HyperGraph.clique_projection`) and is never the only representation. | FR-045, FR-035 |
| 7 | The bridge imports no vendor driver. `Neo4jGraphStore` remains the only module importing `neo4j`, and it now `MERGE`s on the relation id and sets the full property payload. | constitution V, FR-038, SC-013 |
| 8 | Dropping the whole graph loses no knowledge: claims, contexts and lineage live in the durable substrate, and `rebuild(projection_id, from_offset=0)` reproduces the projection from the durable log alone. | constitution III, I-12, FR-040, FR-041 |

**Failure modes**

| Condition | Exception / reason code | State changed |
| --- | --- | --- |
| `provenance` missing required fields | `ProjectionRebuildableError` (I-12) | no |
| a participant node is absent from the graph store | `ValueError("Edge endpoints must exist: …")` | no — the claim remains in `RelationStore`, unresolved |
| `claim.context_ref` empty | `RelationContractError("context_ref_required")` | no |
| an `NARY` claim whose members collapse to fewer than two distinct nodes | `ValueError("hyperedge requires >= 2 members")` | no |
| re-projection of an unchanged claim | none — idempotent, `ProjectionReceipt(written=False)` | no |
| `neighbors(..., direction=...)` with an unrecognised direction | `ValueError` naming the permitted set | no |

**Reference implementation**: `apps/projection/graph/relation_store.py`
(`InMemoryGraphProjectionBridge`). It depends on the existing
`apps/projection/graph/abstraction.py` (`GraphNode`, `GraphEdge`, `HyperEdge`,
`GraphStore`, `InMemoryGraphStore`) and `apps/projection/graph/snapshot.py`
(`RebuildableGraphStore`, `GraphSnapshot`). If the adapter outgrows the module, it moves
to `apps/projection/graph/relation_bridge.py`; that is a rename recorded in
[tasks.md](../tasks.md), not a new contract.

---

## Cross-cutting contracts

| Concern | Contract | Requirement |
| --- | --- | --- |
| Identifier supply | Only `RelationClaimService` derives `logical_relation_id` / `relation_id`. `RelationStore`, `GraphStore` and `GraphProjectionBridge` all take the id as an input and never generate one. | FR-003, FR-004, FR-035 |
| Provenance | Every projection or store write goes through `domain.enforce_projection_provenance` (`event_id` + `observation_id`). A refused write leaves state byte-identical. | I-12, FR-036 |
| Idempotency | Content-addressed identity plus a content hash gives idempotency structurally; no caller-supplied dedup flag exists. | I-11, FR-005 |
| Preservation | `SUPERSEDED`, `RETRACTED` and `CONTRADICTED` claims stay queryable. No contract in this document exposes a delete. | I-3, FR-006 |
| Grading | `evidence_grade` and `grade_components` are stored as components, never as a single collapsed score. | constitution IV, FR-025 |
| Tenant scoping | Every read and every registry lookup is tenant-scoped; a foreign id resolves to nothing, with no differing error surface. | FR-048, constitution VII |
| Substitution refusal | An unresolved `context_ref` and an unregistered `relation_type` are both reported (`context_unresolved`, `schema_unregistered`); neither ever falls back to a default frame or a default schema. | FR-016, FR-023 |
| Event emission | Claim creation, revision, supersession, contradiction and context registration emit events so projections rebuild from the durable log. | FR-049, I-12 |

---

## Contract tests

Every contract below is pinned by a test that must exist. Paths follow the repository's
existing layout: domain tests live under `apps/shared/tests/unit/domain/` (as
`test_temporal_worldline.py` and its siblings do) rather than the flat path named in
[plan.md](../plan.md); that refinement is recorded here so implementation and plan do not
diverge silently.

| Contract | Test file | Property pinned |
| --- | --- | --- |
| `RelationClaimService` (identity minting) | `apps/shared/tests/unit/domain/test_relation_identity.py` | `logical_relation_id` of `(A, works_for, B)` differs from `(B, works_for, A)`; `(A, co_occurs_with, B)` equals `(B, co_occurs_with, A)` (SC-001). `digest128` is 32 hex chars (FR-004). 1,000,000 deterministically generated claims yield 1,000,000 distinct ids (SC-002). N-ary member order does not change the id while role permutation does (FR-009). |
| `RelationClaimService` (construction guards) | `apps/shared/tests/unit/domain/test_relation_claim.py` | Empty `context_ref` raises and mints nothing (I-12). Self-loop, `NARY` with < 2 members, `NARY` duplicate member and `DIRECTED` with roles all raise. Two identical constructions are byte-equal including both ids (I-11). `to_dict()`/`from_dict()` round-trips the identity fields byte-exactly. `publication_count != independent_source_count` is observable on the claim. |
| `RelationClaimService` (revision) | `apps/shared/tests/unit/domain/test_relation_claim.py` | `next_revision` preserves `logical_relation_id`, changes `relation_id`, sets `revision_number + 1` and `supersedes`; the prior claim is unchanged and still readable. `to_dict()`/`from_dict()` round-trips the identity fields byte-exactly. |
| `RelationStore` | `apps/projection/tests/unit/test_relation_store.py` | Writing the same claim twice leaves the relation count and `checksum()` unchanged (I-11, SC-012). A write with provenance missing `event_id` raises `ProjectionRebuildableError` and the store is unchanged (I-12). A colliding `relation_id` with a different `content_hash` raises and preserves the existing row (FR-011). `revisions()` returns non-`ACTIVE` revisions (I-3). `participants()` is directional. `checksum()` is invariant under insertion order. |
| `ContextRegistry` | `apps/shared/tests/unit/domain/test_evidence_context.py` | Two independently constructed identical frames yield a byte-identical `context_id` (SC-009). `register` is idempotent and returns the id. Mutating a frozen frame raises (FR-015). `resolve` returns `None` for an unknown id and no default frame is substituted (FR-016). A frame with a missing parent is storable and `detect_cycle` reports the cycle path (FR-017). |
| `ContextValidator` | `apps/shared/tests/unit/domain/test_context_validation.py` | A fixture matrix with one row per layer asserts the expected verdict and reason code. `len(result.layers) == 7` for every row, including the short-circuited `context=None` case (FR-019, SC-004). Inverted interval → `INVALID/temporal_interval_inverted` with `structural` reported `PASSED` (SC-005). `DOCUMENT --works_for--> PERSON` → `INVALID/schema_subject_class_not_allowed` citing both the offending class and the allowed set (SC-006). Cross-tenant evidence → `INVALID/provenance_tenant_mismatch` (SC-007). Unregistered type → `UNDERDETERMINED/schema_unregistered`, claim preserved (SC-008). Missing extractor version → `UNDERDETERMINED`. Inputs' `content_hash`/`context_id` unchanged after the call (FR-021). `grade_components` has five separate keys and no aggregate key (constitution IV). |
| `RelationSchemaRegistry` | `apps/shared/tests/unit/domain/test_relation_schema.py` | `vocabulary()` is deterministically ordered. `DIRECTED` with roles and `NARY` with < 2 roles are refused (FR-012). Same version + different content is refused; a new `schema_version` is accepted (FR-029). `get` returns `None` for an unknown type and the validator maps it to `UNDERDETERMINED` (FR-023). A repository scan asserts no module outside `domain/relation_schema.py` carries a hard-coded relation-type list (FR-028). |
| `EvidenceLineageProvider` | `apps/shared/tests/unit/domain/test_evidence_lineage.py` | A complete chain yields backward lineage to the source in canonical order (FR-031, SC-003). Removing the segment hop yields `complete=False` with `first_unresolved_hop == SEGMENT`, not an empty list (FR-033). Forward lineage from a source returns each relation with its grounding assertion (FR-032). Cross-tenant hops are not traversed (FR-048). |
| `IndependenceResolver` | `apps/shared/tests/unit/domain/test_evidence_lineage.py` | Two observations of one `source_family` produce exactly one group and `independent_source_count == 1` while `publication_count == 2` (FR-034, constitution IV). A ref under two families is not collapsed. `groups()` equals the free function `independence_groups()` on a shared fixture. |
| `GraphProjectionBridge` | `apps/projection/tests/unit/test_relation_projection_bridge.py` | A projected `GraphEdge.edge_id` equals `claim.relation_id` and its `properties` carry `context_ref` and the version triple. Projecting the same claim twice leaves the edge count unchanged (I-11). A claim without provenance raises and the graph is unchanged (I-12). A `NARY` claim projects as one `HyperEdge`, not a clique (FR-045). |
| `GraphStore` changes | `apps/projection/tests/unit/test_graph_store_semantics.py` | `neighbors(node, type, "out")` returns only outgoing neighbours when both directions exist (FR-010). Two edges with equal endpoints but different `edge_id` are distinct (FR-035). `write_hyperedge` twice leaves the hyperedge count unchanged — the current no-op guard is fixed (FR-037, SC-012). |
| Neo4j adapter | `apps/projection/tests/unit/test_neo4j_relation_payload.py` | The emitted write contains the relation id and the full property payload, and re-writes `MERGE` on the relation id (FR-038, SC-013). Non-ASCII relation types are rejected by label sanitisation. No domain module imports `neo4j` (constitution V). |
| Rebuild and snapshot | `apps/projection/tests/unit/test_graph_snapshot_rebuild.py` | Rebuild then compare `checksum()`: the rebuilt store's checksum equals the source's (FR-040, SC-011). Two snapshots over an unchanged store yield an equal checksum and a stable `projection_id` (FR-041). `_checksum` is stable under property reordering. `rebuild(projection_id, from_offset=k)` honours `k`. |
| Migration | `apps/control-plane/tests/unit/test_migration_016_forward_only.py` | Fresh install and 015-upgrade reach an identical schema by programmatic comparison (FR-042, SC-010); the revision graph has one root and one head; `016_relation_evidence_graph` is a child of `015_worldline_reconstruction`. |
| Released-revision immutability | `apps/control-plane/tests/unit/test_migration_forward_only.py` | Revision 015's SHA-256 matches the pinned digest; any edit fails loudly (FR-042). |
| Frontend alignment | `apps/webapp/src/lib/edgeFormation.test.ts` | A directed pair yields two oriented edges, a reversed undirected pair yields one, an N-ary observation stays one record (FR-043, SC-014). The `fnv1a` golden-vector test still passes, proving the hash helper was retired for identity only (FR-046, SC-015). |
| No regression | per-app suites | No new failures against the recorded baseline in [quickstart.md](../quickstart.md) §9 (SC-016, SC-017). |
