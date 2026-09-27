
# Tasks: Relation & Evidence Graph Fabric
**Input**: Design documents from `specs/016-relation-evidence-graph-fabric/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`
**Tests**: Tests are included and are written first for each task group, per`docs/CONTRIBUTING.md`. Every test task states the property it pins.
**Organization**: Tasks are grouped by user story so each story can be implemented, testedand delivered as an independent increment. Phase 0 is a hard gate: no application code iswritten before the migration is proven on both installation paths.
## Format: `[ID] [P?] [Story] Description`
- **[P]**: can run in parallel (different files, no dependencies)
- **[Story]**: which user story the task belongs to
## Baseline (recorded before implementation)
Exit gate is **no new failures**, not "all green":
| suite | pre-existing state |
|---|---|
| `apps/shared` | 3 failed, 344 passed, 3 skipped |
| `apps/projection` | 3 failed, 102 passed, 1 skipped, plus 2 collection errors (`test_bm25s_backend.py`, `test_relevance.py` cannot import) |
| `apps/admission` | 96 passed |
| `apps/interpretation` | 184 passed |
| `apps/webapp` | 232 passed across 37 files |
| `ruff` on the scoped app dirs | pre-existing findings already present |
## Critical sequencing rules
1. Phase 0 completes before any application code. Editing revision `015` is forbidden.
2. Phase 1 (identity + claim + store) is the foundation; Phases 2, 4 and 5 all depend on it.
3. Phase 1 and Phase 0 may not overlap — the schema in Phase 1 mirrors the migration in Phase 0.
4. Phase 2 (context + validator) and Phase 5 (frontend identity) are mutually independent once   Phase 1 lands, and may run concurrently.
5. Phase 3 (schema registry + lineage) depends on Phase 1 for the claim type; its registry   half is independent of Phase 2.
6. Phase 6 (rebuildability) depends on the Phase 1 store but not on Phases 2-3.
---
## Phase 0: Setup and architectural gates (blocking)
**Purpose**: Accept the required ADRs and prove the forward-only migration on both
installation paths before any feature code is written.
- [x] T001 [P] Write ADR for the relation identity scheme (128-bit truncated SHA-256) and the four arity modes, covering why 32-bit FNV-1a is retired for identity and why it is retained for layout seeds and UI checksums. -> `docs/adr/0023-relation-identity-and-arity.md`
- [x] T002 [P] Write ADR for the claim/context persistence model: the two-level  `logical_relation_id` / `relation_id` split, the five new tables, and why  `RelationClaim` coexists with rather than replaces `GraphEdge`. ->  `docs/adr/0024-claim-and-context-persistence.md`
- [x] T003 Confirm revision `015_worldline_reconstruction.py` is unmodified relative to its applied state; treat it as immutable from here on.
- [x] T004 Add forward-only migration `016_relation_evidence_graph` creating  `evidence_context`, `relation_claim`, `relation_claim_revision`, `relation_schema_version`  and `claim_context_lineage` per `data-model.md` section 10, in tables -> indexes order. -> `apps/control-plane/db/migrations/versions/016_relation_evidence_graph.py`
- [x] T005 Add the five tables to the declarative schema so `create_all` and Alembic agree. -> `apps/control-plane/db/schema.py`
- [x] T006 [P] Add the both-paths proof: pin `015` by SHA-256, assert exactly one root and one head, assert no branching, and assert `016.down_revision == "015_worldline_reconstruction"`. -> `apps/control-plane/tests/unit/test_migration_016_forward_only.py`
- [x] T007 [P] Add the migration shape test asserting the ordering contract (tables before indexes, unique index present, `downgrade` in strict reverse order) in  `apps/control-plane/tests/unit/test_migration_016_forward_only.py`.
**Checkpoint**: ADRs accepted, migration proven on both paths. Proves FR-042, SC-010.
---
## Phase 1: User Stories 1 & 2 — Relation Claim, Direction, Arity, Identity (P1)
**Goal**: A relation is a first-class claim with a two-level identity, explicit arity, and a128-bit content-addressed id; the stores accept it, preserve it and read it directionally.
**Independent Test**: Two claims for the same triple with different evidence and windows share one `logical_relation_id` and differ in `relation_id`; `(A, works_for, B)` and`(B, works_for, A)` differ while `(A, co_occurs_with, B)` and its reverse are equal; onemillion generated claims yield one million distinct ids.
### Tests for User Stories 1 & 2
- [x] T008 [P] [US1] Test that a directed claim and its reverse produce different relation ids while an undirected claim and its reverse collide on one id. -> `apps/shared/tests/unit/test_relation_identity.py`
- [x] T009 [P] [US1] Test that every relation id is `RC-` + 32 lowercase hex characters and that `logical_relation_id` is `RL-` + 32 hex. -> `apps/shared/tests/unit/test_relation_identity.py`
- [x] T010 [P] [US1] Test that N-ary identity is invariant to member ordering but changes when a member moves between two roles. -> `apps/shared/tests/unit/test_relation_identity.py`
- [x] T011 [P] [US1] Test that a revised claim keeps its `logical_relation_id`, gets a new  `relation_id`, and increments `revision_number`. -> `apps/shared/tests/unit/test_relation_claim.py`
- [x] T012 [P] [US1] Test that identical claim content yields a byte-identical `content_hash`  and that `to_dict`/`from_dict` round-trips. -> `apps/shared/tests/unit/test_relation_claim.py`
- [x] T013 [P] [US1] Test each construction rejection: self-loop, empty relation type, empty  `context_ref`, N-ary with fewer than two members, N-ary with duplicate members, directed carrying role bindings, inverted interval, out-of-range confidence, `revision_number < 1`, self-supersession. -> `apps/shared/tests/unit/test_relation_claim.py`
- [x] T014 [P] [US1] Test that `publication_count` and `independent_source_count` are separate values and that two observations from one source family yield 1, not 2. -> `apps/shared/tests/unit/test_relation_claim.py`
- [x] T015 [P] [US2] Test the 1,000,000-claim distinctness property and that no collision is left unreported. -> `apps/shared/tests/unit/test_relation_identity.py`
- [x] T016 [P] [US2] Test that a claim with a recomputable identity mismatch is detectable — i.e. that tampering with a field is caught by re-derivation. -> `apps/shared/tests/unit/test_relation_claim.py`
- [x] T017 [P] [US2] Test that `InMemoryRelationStore.write` is idempotent on identical content, rejects a write with no provenance, and never invents a `relation_id`. -> `apps/projection/tests/unit/test_relation_store.py`
- [x] T018 [P] [US2] Test directional reads: `participants` distinguishes subject from object for a directed claim and matches either endpoint for an undirected one; `by_type(active_at=)`  filters correctly. -> `apps/projection/tests/unit/test_relation_store.py`
- [x] T019 [US2] Test that `InMemoryGraphStore.neighbors` honours `direction` and that the default resolves from the stored edge's arity mode. -> `apps/projection/tests/unit/test_graph_store_direction.py`
- [x] T020 [US2] Test that the N-ary idempotency guard fires: writing the same hyperedge twice leaves the hyperedge count unchanged. -> `apps/projection/tests/unit/test_graph_store_direction.py`
- [x] T021 [US2] Test that two `GraphEdge`s with the same triple but different `edge_id` are distinct entries and that rewriting the same `edge_id` is a no-op. -> `apps/projection/tests/unit/test_graph_store_direction.py`
- [x] T022 [US2] Test that the Neo4j adapter emits a `MERGE` keyed on the relation id and carries the full property payload. -> `apps/projection/tests/unit/test_neo4j_relation_write.py`
### Implementation for User Stories 1 & 2
- [x] T023 [P] [US1] Add `canonical_material`, `digest128`, `RelationArityMode`,  `logical_material`, `logical_relation_id` and `relation_id` in  `apps/shared/domain/relation_identity.py`, matching `data-model.md` sections 1-2.
- [x] T024 [P] [US1] Add `RelationRoleBinding`, `RelationStatus`, `EvidenceGrade`,  `RelationClaim`, `RelationRevision` and `RelationContractError` with all ten construction rejections, `content_hash`, `independent_source_count`, `publication_count`, `is_active_at`  and a stable `to_dict`/`from_dict` in `apps/shared/domain/relation_claim.py`  (depends on T023).
- [x] T025 [P] [US2] Add `RelationStore` protocol and `InMemoryRelationStore` with  `write`/`get`/`revisions`/`by_type`/`participants`/`checksum`, provenance enforcement and an order-independent checksum in `apps/projection/graph/relation_store.py` (depends on T024).
- [x] T026 [P] [US2] Add `edge_id` to `GraphEdge`, key `__hash__`/`__eq__` on it, fix the  `write_hyperedge` idempotency guard, and add the `direction` parameter to  `InMemoryGraphStore.neighbors` in `apps/projection/graph/abstraction.py` (depends on T025 for the arity lookup).
- [x] T027 [US2] Update `Neo4jGraphStore.write_edge` and `write_hyperedge` to `MERGE` on the relation id and set the full property payload; reject non-ASCII characters in label sanitisation in `apps/projection/graph/neo4j.py` (depends on T026).
- [x] T028 [US2] Fix `adjacency_from_store` to use `str(n.node_id)` instead of `str(node)`  and de-duplicate emitted pairs in `apps/projection/graph/adjacency.py` (depends on T026).
- [x] T029 [US2] Add the collision detector: group a claim set by `relation_id`, return every bucket of size > 1 with the ids and the claims involved, never merging them silently, in  `apps/shared/domain/relation_identity.py` (depends on T024).
- [x] T030 [US2] Add `SqlRelationClaimStore` with tenant-scoped persist, read, revision-chain read and a checksum query in `apps/control-plane/db/relation_claim_store.py` (depends on T005, T024).
**Checkpoint**: A relation is a claim with a two-level identity, explicit arity, and storesthat accept, preserve and read it directionally. Proves FR-001 to FR-012, FR-035 to FR-038,SC-001, SC-002, SC-012, SC-013.
---
## Phase 2: User Stories 3 & 4 — Evidence Context and Layered Validation (P1)
**Goal**: An immutable content-addressed frame records the conditions of interpretation, anda seven-layer validator returns a graded verdict with structured reasons.
**Independent Test**: Two independently constructed identical frames produce byte-identical`context_id`s; a fixture matrix with one row per layer failure returns the expected verdictand reason code while reporting all seven layer outcomes.
### Tests for User Stories 3 & 4
- [ ] T031 [P] [US3] Test that two frames built by different construction paths with the same field values produce byte-identical `context_id`s. -> `apps/shared/tests/unit/test_evidence_context.py`
- [ ] T032 [P] [US3] Test that a frame is frozen: attribute assignment raises. -> `apps/shared/tests/unit/test_evidence_context.py`
- [ ] T033 [P] [US3] Test that `InMemoryContextResolver.register` is idempotent on `context_id`  and that `resolve` of an unknown id returns `None`. -> `apps/shared/tests/unit/test_evidence_context.py`
- [ ] T034 [P] [US3] Test cycle detection: a parent chain that loops reports the cycle path. -> `apps/shared/tests/unit/test_evidence_context.py`
- [ ] T035 [P] [US3] Test that a frame with an inverted validity window is rejected at construction. -> `apps/shared/tests/unit/test_evidence_context.py`
- [ ] T036 [P] [US4] Test the per-layer matrix: structural, semantic, temporal, provenance, identity, cross-source and graph-constraint each fail with their exact reason code, and each result still enumerates all seven layer outcomes. -> `apps/shared/tests/unit/test_context_validation.py`
- [ ] T037 [P] [US4] Test the three headline cases: `valid_from > valid_to` is  `INVALID/temporal_interval_inverted` with `structural == passed`;  `DOCUMENT --works_for--> PERSON` is `INVALID/schema_subject_class_not_allowed` citing the offending class and the allowed set; a foreign-tenant observation is  `INVALID/provenance_tenant_mismatch`. -> `apps/shared/tests/unit/test_context_validation.py`
- [ ] T038 [P] [US4] Test that a claim with no declared extractor version is  `UNDERDETERMINED/extraction_version_undeclared`, not `INVALID`. -> `apps/shared/tests/unit/test_context_validation.py`
- [ ] T039 [P] [US4] Test that a context declaring an ontology version absent from the active pack set is `STALE/ontology_version_stale` and the claim is preserved unchanged. -> `apps/shared/tests/unit/test_context_validation.py`
- [ ] T040 [P] [US4] Test that a claim with no registered schema is  `UNDERDETERMINED/schema_unregistered` and is preserved. -> `apps/shared/tests/unit/test_context_validation.py`
- [ ] T041 [P] [US4] Test verdict precedence: a claim that is simultaneously inverted and stale resolves to `INVALID`. -> `apps/shared/tests/unit/test_context_validation.py`
- [ ] T042 [P] [US4] Test that disjoint validity intervals over the same type and participant pair are `VALID` with a `temporal_non_overlap` note, and that overlapping intervals with conflicting objects are `CONFLICTING` with both claims preserved. -> `apps/shared/tests/unit/test_context_validation.py`
- [ ] T043 [P] [US4] Test that `validate` never mutates the claim or the context, and never returns a bare boolean. -> `apps/shared/tests/unit/test_context_validation.py`
- [ ] T044 [P] [US4] Test every row of the evidence-grade table and that `grade_components`  stores the five components separately. -> `apps/shared/tests/unit/test_context_validation.py`
- [ ] T045 [P] [US4] Test that a `null` context short-circuits to  `INVALID/provenance_context_missing` with all seven layers still reported. -> `apps/shared/tests/unit/test_context_validation.py`
### Implementation for User Stories 3 & 4
- [ ] T046 [P] [US3] Add `ContextCompleteness`, `ContextTrustState`, `EvidenceContext`  (frozen, content-addressed) and `ContextContractError` in  `apps/shared/domain/evidence_context.py` (depends on T023).
- [ ] T047 [P] [US3] Add `ContextResolver` protocol, `InMemoryContextResolver` and  `detect_context_cycle` in `apps/shared/domain/evidence_context.py` (depends on T046).
- [ ] T048 [P] [US4] Add `ValidationLayer`, `ValidationVerdict`, `LayerOutcome`,  `ValidationReason`, `ValidationResult`, `ValidationWorld` and the evidence-grade table in  `apps/shared/domain/context_validation.py` (depends on T024).
- [ ] T049 [P] [US4] Implement the seven layer functions and the `validate` entry point with the fixed verdict precedence in `apps/shared/domain/context_validation.py` (depends on T046, T047, T048).
- [ ] T050 [P] [US4] Add `detect_identity_collisions` re-export surface and the  `recompute_identity` helper used by the identity layer in  `apps/shared/domain/relation_identity.py` (depends on T023, T024).
- [ ] T051 [US3] Add `SqlEvidenceContextStore` with tenant-scoped register, read and a cycle-detecting ancestor query in `apps/control-plane/db/evidence_context_store.py`  (depends on T005, T046).
- [ ] T052 [US3] Persist validation verdicts with decision, reasons, grade components, versions and timestamps so a rejected claim is replayable, and never delete a non-`VALID`  claim -> `apps/control-plane/db/relation_claim_store.py` (depends on T030, T049).
**Checkpoint**: Any claim can be interpreted only inside a registered, immutable context, andevery validation returns a graded verdict with structured reasons. Proves FR-013 to FR-025,SC-004 to SC-009.
---
## Phase 3: User Stories 5 & 6 — Schema Registry and Evidence Lineage (P2)
**Goal**: Relation semantics are a versioned constraint system readable by every consumer, andany relation answers "why do you believe this?" in both directions.
**Independent Test**: Register a schema at runtime and assert the proposer, validator andadmission evaluator all read it; build a complete evidence chain and assert backward lineage
reaches the source while removing the segment hop yields `complete=False` naming `segment`.
### Tests for User Stories 5 & 6
- [ ] T053 [P] [US5] Test that `RelationSchemaRegistry.vocabulary()` is deterministically ordered and reports arity mode, allowed classes, evidence patterns, temporal semantics and admission rule id for every declared type. -> `apps/shared/tests/unit/test_relation_schema.py`
- [ ] T054 [P] [US5] Test registration rejections: a `DIRECTED` schema carrying role bindings, a `NARY` schema with fewer than two role bindings, and a same-version redefinition with different content. -> `apps/shared/tests/unit/test_relation_schema.py`
- [ ] T055 [P] [US5] Test that a new schema version of an existing type registers while a conflicting same-version redefinition is rejected. -> `apps/shared/tests/unit/test_relation_schema.py`
- [ ] T056 [US5] Test that the validator consumes the registry rather than an embedded list: registering `works_for` at runtime flips an `UNDERDETERMINED/schema_unregistered` claim to  `INVALID/schema_subject_class_not_allowed`. -> `apps/shared/tests/unit/test_relation_schema.py`
- [ ] T057 [US5] Test each `temporal_semantics` value, including  `REQUIRED_INTERVAL` producing `UNDERDETERMINED/temporal_interval_required`. -> `apps/shared/tests/unit/test_relation_schema.py`
- [ ] T058 [P] [US6] Test that backward lineage over a complete chain returns every hop in canonical order with its hop kind. -> `apps/shared/tests/unit/test_evidence_lineage.py`
- [ ] T059 [P] [US6] Test that removing the segment hop yields `complete=False` naming  `segment` and never an empty `hops` list. -> `apps/shared/tests/unit/test_evidence_lineage.py`
- [ ] T060 [P] [US6] Test that forward lineage from a source returns every derived relation each carrying the asserting `relation_id`. -> `apps/shared/tests/unit/test_evidence_lineage.py`
- [ ] T061 [P] [US6] Test that `independence_groups` collapses two captures from one source family into one group. -> `apps/shared/tests/unit/test_evidence_lineage.py`
- [ ] T062 [US6] Test that a relation is reachable from its source by the API-level path  `relation → assertion → mention → segment → observation → capture → source`. -> `apps/shared/tests/unit/test_evidence_lineage.py`
### Implementation for User Stories 5 & 6
- [ ] T063 [P] [US5] Add `TemporalSemantics`, `RelationSchema` and `RelationSchemaRegistry`  with registration validation and deterministic vocabulary enumeration in  `apps/shared/domain/relation_schema.py` (depends on T023).
- [ ] T064 [P] [US6] Add `HopKind`, `EvidenceHop`, `LineageTrace`, `EvidenceGraph` with bidirectional traversal and explicit incompleteness, plus `independence_groups` in  `apps/shared/domain/evidence_lineage.py` (depends on T024).
- [ ] T065 [US5] Wire the semantic layer of the validator to read `RelationSchemaRegistry`  through `ValidationWorld` rather than any embedded list in  `apps/shared/domain/context_validation.py` (depends on T049, T063).
- [ ] T066 [P] [US5] Persist registered schema versions in `relation_schema_version` in  `apps/control-plane/db/relation_schema_store.py` (depends on T005, T063).
- [ ] T067 [US6] Persist lineage traces with their completeness and first-unresolved-hop fields in `apps/control-plane/db/evidence_lineage_store.py` (depends on T005, T064).
- [ ] T068 [US6] Add the relation read API: claim, revisions by logical id, filtered list, context, validate, lineage — tenant-scoped, with the documented error envelope, in  `apps/control-plane/api/relations.py` (depends on T030, T051, T052).
**Checkpoint**: Relation semantics are data, and any relation can be traced to its source inboth directions with incompleteness reported explicitly. Proves FR-026 to FR-034, FR-047,FR-048, SC-003, SC-008.
---
## Phase 4: User Story 7 — Store Parity and Rebuildability (P2)
**Goal**: In-memory, Neo4j and rebuildable stores accept the same relation semantics, and arebuild reproduces an identical relation set with an identical checksum.
**Independent Test**: Write a relation set through the rebuildable wrapper, snapshot, rebuildinto a fresh store and assert equal checksums and full field preservation.
### Tests for User Story 7
- [ ] T069 [P] [US7] Test that a rebuild reproduces a relation set with an identical checksum and loses no field. -> `apps/projection/tests/unit/test_relation_rebuild.py`
- [ ] T070 [P] [US7] Test that a double snapshot over an unchanged store yields an equal checksum and a stable projection id. -> `apps/projection/tests/unit/test_relation_rebuild.py`
- [ ] T071 [P] [US7] Test that `RebuildableGraphStore` forwards N-ary writes instead of dropping them. -> `apps/projection/tests/unit/test_relation_rebuild.py`
- [ ] T072 [P] [US7] Test that `rebuild(projection_id, from_offset=n)` honours the offset. -> `apps/projection/tests/unit/test_relation_rebuild.py`
- [ ] T073 [P] [US7] Test that the snapshot checksum is stable under property reordering in the stored edge. -> `apps/projection/tests/unit/test_relation_rebuild.py`
### Implementation for User Story 7
- [ ] T074 [US7] Fix `RebuildableGraphStore`: forward `write_hyperedge`, record the snapshotted  `projection_id`, honour `from_offset`, and make `_checksum` sort by `edge_id`; rename the  `_asset_edges` typo in `apps/projection/graph/snapshot.py` (depends on T026, T071).
- [ ] T075 [US7] Add `GraphProjectionBridge` mapping a `RelationClaim` onto  `GraphNode`/`GraphEdge`/`HyperEdge` with the correct arity-driven direction, in  `apps/projection/graph/relation_store.py` (depends on T025, T026).
- [x] T076 [US7] Correct the stale docstring on the projection-level `HyperEdge.edge_id` in  `apps/projection/graph/abstraction.py` so it matches the code's actual identity material (depends on T026).
- [x] T077 [US7] Make `InMemoryGraphStore` explicitly declare it satisfies `GraphStore`, and remove the Protocol subclassing from `Neo4jGraphStore` so the two agree. -> `apps/projection/graph/abstraction.py`, `apps/projection/graph/neo4j.py` (depends on T027, T077).
**Checkpoint**: Projections round-trip and rebuild provably. Proves FR-039 to FR-041,SC-011.
---
## Phase 5: User Story 8 — Frontend Identity Correction (P3)
**Goal**: The edge builder honours declared arity, stops collapsing inverse directed
relations, preserves N-ary observations, and keeps FNV-1a for non-identity purposes only.
**Independent Test**: A directed pair yields two oriented edges, a reversed undirected pairyields one, an N-ary observation survives as one record, and the existing FNV-1a golden vectortest still passes.
### Tests for User Story 8
- [ ] T078 [P] [US8] Test that a directed `relationship` seed and its reverse produce two distinct edges with preserved orientation. -> `apps/webapp/src/lib/edgeFormation.test.ts`
- [ ] T079 [P] [US8] Test that a reversed undirected `co_occurrence` pair produces one edge. -> `apps/webapp/src/lib/edgeFormation.test.ts`
- [ ] T080 [P] [US8] Test that an N-ary observation is preserved as one record and that the pairwise projection is an explicitly derived, opt-in view. -> `apps/webapp/src/lib/edgeFormation.test.ts`
- [ ] T081 [P] [US8] Test that the layout seed is stable across repeated calls for the same node set and that ordering invariance still holds. -> `apps/webapp/src/lib/edgeFormation.test.ts`
- [ ] T082 [US8] Test that the FNV-1a helper still satisfies its existing golden vector (`811c9dc5` for the empty string in `graphState.test.ts`), proving it was retired for identity only. -> `apps/webapp/src/lib/edgeFormation.test.ts`
### Implementation for User Story 8
- [ ] T083 [US8] Add an arity declaration per `EdgeKind` and make `makeEdgeId` order-sensitive for directed kinds and order-insensitive for undirected kinds in  `apps/webapp/src/lib/edgeFormation.ts` (depends on T078, T079).
- [ ] T084 [US8] Preserve N-ary observations in `formEdges` and move the clique expansion into an explicitly derived, opt-in projection in `apps/webapp/src/lib/edgeFormation.ts`  (depends on T080).
- [ ] T085 [US8] Update the two call sites `apps/webapp/src/lib/entityGraph.ts:45` and  `apps/webapp/src/lib/intelGraph.ts:247` for the new `formEdges` contract and remove the stale `e:1d374e53` identity golden vector. -> `apps/webapp/src/lib/edgeFormation.test.ts`  (depends on T083, T084).
- [ ] T086 [US8] Make the edge payload order-invariant so a duplicate id does not last-writer-win its `reason`. -> `apps/webapp/src/lib/edgeFormation.ts` (depends on T083).
**Checkpoint**: The UI no longer shows merged inverse directed relations. Proves FR-043 to
FR-046, SC-014, SC-015.
---
## Phase 6: Polish & Cross-Cutting Concerns
**Purpose**: Cross-cutting verification against the recorded baseline.
- [ ] T087 [P] Emit the new events (`relation.claim.*`, `context.*`) through the existing envelope using `build_envelope` / `topic_for`, with refs and versions only and no raw bytes. -> `apps/control-plane/services/relation_events.py`
- [ ] T088 [P] Add the observability counters and the identity-collision alert path listed in  `contracts/operations.md`. -> `apps/control-plane/services/relation_metrics.py`
- [ ] T089 [P] Audit-log cross-tenant read refusals, context registrations and claim supersessions. -> `apps/control-plane/api/relations.py` (depends on T068)
- [ ] T090 Verify no new failures against the recorded baseline: `apps/shared`,  `apps/projection`, `apps/admission`, `apps/interpretation`, `apps/control-plane`, and  `apps/webapp` (`npx vitest run` plus `npx tsc -b`).
- [ ] T091 [P] Run `uv run ruff check` on the touched app dirs and confirm no new findings beyond the pre-existing ones.
- [ ] T092 [P] Add `docs/architecture/relation-fabric.md` describing the four primitives, the identity scheme and how a new source plugs in.
- [ ] T093 Run the `quickstart.md` snippets end to end and confirm each one prints the documented result.
---
## Dependencies & Execution Order
### Phase Dependencies
- **Phase 0 (gates)**: no dependencies; BLOCKS everything.
- **Phase 1 (US1/US2)**: depends on Phase 0. BLOCKS Phases 2, 3, 4, 5.
- **Phase 2 (US3/US4)**: depends on Phase 1. Independent of Phases 3, 4, 5.
- **Phase 3 (US5/US6)**: depends on Phase 1. Its lineage half is independent of Phase 2;  its schema half is independent of Phase 2 entirely.
- **Phase 4 (US7)**: depends on Phase 1. Independent of Phases 2 and 3.
- **Phase 5 (US8)**: depends on Phase 1 only for the shared identity contract; the frontend  code change itself touches no Python file and can run concurrently with Phases 2-4.
- **Phase 6 (polish)**: depends on Phases 2-5.
### Parallelism within each phase- Phase 1: T008-T022 (tests) and T023-T030 (implementation) split cleanly — no two `[P]`  tasks in the same phase touch the same file.- Phase 2: T031-T037 and T046-T048 are fully parallel; T049, T051, T052 serialise after them.- Phase 3: T053, T054, T055, T058, T059, T060, T061 and T063, T064 are fully parallel.- Phase 4: T069-T073 and T074-T077 serialise as test-first then fix.- Phase 5: T078-T082 first, then T083-T086.
### Critical path
```text
Phase 0 → Phase 1 (T023→T024→T025→T026) → Phase 2 (T046→T047→T049) → Phase 6                          ↘ Phase 3 (T063/T064 → T068) ↗                          ↘ Phase 4 (T074)                  ↗                          ↘ Phase 5 (T083→T085)             ↗
```
---
## Implementation Strategy
### MVP first (Phase 0 + Phase 1)
1. Phase 0: ADRs + proven migration.
2. Phase 1: identity, claim, arity, store.
3. **STOP and VALIDATE**: `apps/shared` and `apps/projection` suites show no new failures and   SC-001, SC-002, SC-012, SC-013 are demonstrated.
### Incremental delivery

Each subsequent phase is an independently deployable, independently testable increment:
- Phase 2 adds the context gate and the validator — without it, claims are interpretable  anywhere.
- Phase 3 makes relation semantics data and makes lineage answerable.
- Phase 4 makes the projection provably rebuildable.
- Phase 5 corrects what the UI currently shows.
- Phase 6 closes the loop with observability and the regression gate.
### Parallel team strategy
- Agent A: Phase 2 (context + validator) — `apps/shared/domain/evidence_context.py`,  `apps/shared/domain/context_validation.py`, `apps/control-plane/db/evidence_context_store.py`.
- Agent B: Phase 3 (schema + lineage) — `apps/shared/domain/relation_schema.py`,  `apps/shared/domain/evidence_lineage.py`, `apps/control-plane/db/relation_schema_store.py`,  `apps/control-plane/db/evidence_lineage_store.py`.
- Agent C: Phase 4 (rebuild) — `apps/projection/graph/snapshot.py`,  `apps/projection/graph/relation_store.py`.
- Agent D: Phase 5 (frontend) — `apps/webapp/src/lib/edgeFormation.ts` and its test.

All four run concurrently once Phase 1 lands; they share no files.
---
## Notes
- [P] tasks = different files, no dependencies
- [Story] label maps each task to a user story for traceability
- Every test task states the invariant it pins, not just the module it lives in
- Write the test, see it fail, then implement — per `docs/CONTRIBUTING.md`
- Revision `015_worldline_reconstruction.py` is immutable; a corrective schema change is  revision `017`
- The exit gate is "no new failures against the recorded baseline", not "all green"