# Feature Specification: Relation & Evidence Graph Fabric

**Feature Branch**: `016-relation-evidence-graph-fabric`

**Created**: 2026-09-26

**Status**: Draft

**Input**: User description: "Replace the thin graph edge abstraction with a first-class semantic relation model (RelationClaim), separate relation identity from relation version, make edge direction and arity explicit, replace 32-bit FNV-1a ids with 128-bit truncated SHA-256, introduce an immutable content-addressed EvidenceContext frame as the only legal context in which an assertion may be interpreted, add a multi-level ContextValidator that returns graded verdicts instead of booleans, express relation semantics as a declarative constraint system, and expose full bidirectional evidence lineage from any graph object back to the raw observation."

## Problem Statement

The platform has a closed topological pipeline (Investigation → Discovery → Frontier → Acquisition → Observation → Interpretation → Candidates/Assertions → Resolution/Admission → Graph/Search/Analytics/TDA → Findings → Feedback) and a working hypergraph. The problem is no longer missing subsystems — it is the **weakness of the semantic contracts between them**.

Concretely, five defects make the graph layer unable to answer, for any relation it holds:

> *Why does this edge exist? On which observation? When was it published? When was it considered true? When did the system learn it? Which extractor version produced it? Which ontology version permitted the relation? What alternatives existed? Which sources were independent?*

**D1 — The edge is a triple, not a claim.** `GraphEdge` is `(edge_type, source, target, properties)`. Provenance is passed separately at `write_edge()` time and is not part of edge identity, so a relation cannot be reasoned about as an assertion about a relation that has evidence, a temporal interpretation, a status and a version lineage. `GraphEdge` has no `edge_id` at all, so no other object can reference an edge.

**D2 — Direction is not modelled, and is actively destroyed.** `apps/webapp/src/lib/edgeFormation.ts` normalises every edge through `min(nodeA,nodeB)`/`max(nodeA,nodeB)`. That is correct for `co_occurrence` and wrong for `works_for`, `owns`, `located_in`, `founded`, `reports_to`, `employed_by`, `controls`: `A --works_for--> B` and `B --works_for--> A` collapse to one identity. On the Python side `InMemoryGraphStore.neighbors()` adds each directed edge to *both* endpoints' adjacency and then returns the union, so direction is lost on read even though it is stored on write. There is no vocabulary distinguishing `UNDIRECTED_EDGE` / `DIRECTED_EDGE` / `NARY_RELATION` / `TEMPORAL_RELATION`.

**D3 — Identity is weak and conflates content with version.** The only live edge-id path is a 32-bit FNV-1a digest, i.e. 2^32 ids: a birthday collision passes 50% at roughly 77k edges, and the platform is designed for millions to tens of millions of relations. Worse, there is no separation between *which relation this is* and *this version of the relation*. When an employment interval is corrected from `2017–2020` to `2017–2022`, the system cannot express "same relation, new revision" — it can only append a second, unrelated edge, and the HyperEdge `logical_id`/`edge_id` split that already exists in `apps/shared/domain/hypergraph.py` is not available to the plain edge path.

**D4 — Context is a mutable dict, so it cannot be validated.** `assertion` already exists as `subject → relation → object` with evidence refs and temporal fields, but **the context in which an assertion is permitted to be interpreted is not a first-class object**. Extractor version, normalisation version, ontology version, source independence group, observation/publication/event time, completeness and trust state travel as loose attributes. Nothing validates them together, and nothing prevents a claim from being interpreted under a context that does not license it.

**D5 — Provenance is one-directional and hand-assembled.** The correct substrate principle is already in force — raw bytes stay immutable in object storage and the graph holds refs, not bytes — but the lineage `Source → Capture → Observation → Segment → Mention → Candidate → Assertion → Relation → Entity` exists only as a convention. There is no object that can walk backward from an edge to the raw observation, and no object that can walk forward from a source to everything it produced.

This feature closes those five defects as **one horizontal fabric**, not five vertical features: every later source (Common Crawl, Wayback, a live stream, an enterprise registry) and every later consumer (UI, search, TDA, science) consumes the same relation/context contracts.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A Relation Is a Claim, Not a Triple (Priority: P1)

An analyst inspecting a relation in the graph asks what it actually asserts, on what basis, and when it was true. Today the answer is a triple plus a properties bag. After this feature the answer is a `RelationClaim` that carries its own identity, arity mode, subject/object refs, a full temporal interpretation, evidence refs, an evidence context reference, source-independence groups, the extractor/ontology/normalisation versions that produced it, a status, and links to the claim it supersedes and the claims it contradicts.

**Why this priority**: Everything else in the platform consumes relations. Until a relation is a claim with identity, version, context and lineage, no validation, no contradiction reasoning, no UI evidence panel and no temporal worldline can be correct.

**Independent Test**: Construct two `RelationClaim` values for the same subject/object/type with different evidence contexts and different temporal windows; assert the two share one `logical_relation_id`, carry distinct `relation_id` values, and that the first is reachable from the second's `supersedes` chain. Then serialize to dict and back and assert byte equality of the identity fields.

**Acceptance Scenarios**:

1. **Given** a directed relation `Ivan --works_for--> Acme` with `valid_from=2017-01-01`, **When** a second claim for the same triple is created with `valid_to=2022-12-31` and an extra observation ref, **Then** both claims report the same `logical_relation_id`, distinct `relation_id`, and `revision_number` 1 and 2 respectively.
2. **Given** a `RelationClaim` written to the graph store, **When** it is read back, **Then** its `relation_id`, `context_ref`, `evidence_refs` and version fields are all preserved, including in the Neo4j adapter.
3. **Given** a `RelationClaim` with no `context_ref`, **When** it is written to any `GraphStore`, **Then** the write is rejected by the provenance guard (I-12) and the store state is unchanged.
4. **Given** a claim with `status=SUPERSEDED`, **When** its status is read, **Then** it is still queryable and is never deleted (I-3: assertion ≠ truth; rejected/retracted knowledge is preserved).

---

### User Story 2 - Direction and Arity Are Explicit, and Identity Survives Scale (Priority: P1)

A graph engineer adds two relation types to the registry: an undirected one (`co_occurs_with`) and a directed one (`works_for`). Adding the directed one must not silently merge it with its inverse, and the identity function used must not be able to collide at production relation counts.

**Why this priority**: The current frontend collapses direction for *every* relation kind, which is a correctness bug already shipping in the UI. The 32-bit identity is an architectural ceiling that becomes a data-integrity failure as soon as the relation count grows. Both are cheaper to fix now than after a million edges are written.

**Independent Test**: Register `works_for` as `DIRECTED` and `co_occurs_with` as `UNDIRECTED`; assert `A→B` and `B→A` produce different ids for the directed type and the same id for the undirected type. Then assert the identity function's output width is 128 bits and that it is a truncated SHA-256 over a documented canonical material string.

**Acceptance Scenarios**:

1. **Given** relation types `works_for` (directed) and `co_occurs_with` (undirected), **When** identity is computed for `(A, B, type)` and `(B, A, type)`, **Then** the directed ids differ and the undirected ids are equal.
2. **Given** an N-ary relation `Employment(person=P1, organization=O1, role=CEO, location=HQ1)`, **When** identity is computed, **Then** member ordering does not change the id, but permuting a member between the `person` role and the `organization` role does.
3. **Given** a 4th-generation relation set of 1,000,000 claims built deterministically, **When** ids are computed, **Then** the number of distinct ids equals 1,000,000 and no id is shorter than 32 hex characters.
4. **Given** the frontend `formEdges` builder, **When** a directed `relationship` seed and its reverse are both supplied, **Then** two distinct edges are emitted with distinct ids and correct orientation; when an undirected `co_occurrence` pair is supplied twice in opposite order, one edge is emitted.
5. **Given** a `GraphStore.neighbors(node, edge_type, direction="out")` call, **When** the node has both an incoming and an outgoing edge of that type, **Then** only the outgoing neighbours are returned.

---

### User Story 3 - Evidence Context Is a First-Class Immutable Object (Priority: P1)

A reviewer must be able to open any claim and see the exact frame in which it was permitted to be interpreted: which observation, source, document and segment it came from; the source family and independence group; observed/published/event time; the extractor, normalisation and ontology versions in force; the completeness and trust state; and the parent context when one exists. The frame must be immutable, content-addressed, and shared by reference rather than copied.

**Why this priority**: This is the object the entire roadmap depends on. Deferring it means every subsequent assertion, edge, contradiction and UI panel is built against a context that cannot be validated, and the schema must be broken later.

**Independent Test**: Build two `EvidenceContext` frames with identical content from different construction paths; assert their `context_id` is equal and that mutating a frozen frame raises. Then assert that a claim referring to a context by `context_id` can be resolved to the frame and that the resolution fails loudly for an unknown id.

**Acceptance Scenarios**:

1. **Given** two independently constructed `EvidenceContext` frames with the same field values, **When** `context_id` is read from each, **Then** the values are byte-identical.
2. **Given** an `EvidenceContext` with `tenant_id=A` and a `RelationClaim` whose `tenant_id` is `B`, **When** the claim is validated, **Then** the result is `INVALID` with reason code `provenance_tenant_mismatch` — never silently accepted.
3. **Given** an `EvidenceContext` with `parent_context_id` set to a frame that does not exist, **When** the context is validated, **Then** the result is `INCOMPLETE` with reason code `context_parent_missing`, and the frame is still storable (it is evidence, not a verdict).
4. **Given** a frame with `completeness=PARTIAL`, **When** a claim is admitted under it, **Then** the claim's `evidence_grade` is recorded as degraded and the validator reports `INCOMPLETE` rather than `VALID` when the claim asserts more than the context can support.

---

### User Story 4 - Validation Is Layered and Graded, Not Boolean (Priority: P1)

An assertion `Ivan --CEO_OF--> Acme` with `valid_from=2025` and `valid_to=2020` is structurally valid and temporally invalid. A claim `A --works_for--> B` where `A` is a document and `B` is a person is ontology-invalid. A claim supported by an observation belonging to another tenant is provenance-invalid. The validator must distinguish all of these, and must never return a bare `True`/`False`.

**Why this priority**: A boolean validator forces callers to re-derive *why* something failed, which is exactly the re-derivation the platform is trying to eliminate. The graded verdict is also the input to contradiction reasoning and to honest UI.

**Independent Test**: Run the validator over a fixture matrix of claims — each row crafted to trip exactly one layer — and assert the returned `ValidationResult` carries the expected `verdict` and the expected reason code, with all seven layers evaluated and reported even when an earlier one fails.

**Acceptance Scenarios**:

1. **Given** a claim with `valid_from > valid_to`, **When** validated, **Then** verdict is `INVALID` with reason code `temporal_interval_inverted` and the structural layer is reported as `PASSED` while the temporal layer is `FAILED`.
2. **Given** a claim `DOCUMENT --works_for--> PERSON`, **When** validated against the relation schema, **Then** verdict is `INVALID` with reason code `schema_subject_class_not_allowed`, citing both the offending class and the allowed set.
3. **Given** a claim whose evidence observation belongs to a different tenant than the claim, **When** validated, **Then** verdict is `INVALID` with reason code `provenance_tenant_mismatch`.
4. **Given** a claim with no declared extractor version, **When** validated, **Then** verdict is `UNDERDETERMINED` with reason code `extraction_version_undeclared` — not `INVALID`, because the claim is not wrong, it is uninterpretable.
5. **Given** a claim whose context declares `ontology_version=A` while the active ontology pack is `B`, **When** validated, **Then** verdict is `STALE` with reason code `ontology_version_stale`, and the claim is preserved unchanged.
6. **Given** any validation run, **When** it completes, **Then** the result enumerates all seven layers with their individual outcomes, so a caller can see that e.g. identity validation passed even though cross-source validation failed.
7. **Given** two claims of the same relation type over the same subject/object whose validity intervals are disjoint in time, **When** validated together, **Then** the result is `VALID` for each and a `temporal_non_overlap` note is recorded — disjoint intervals are not a contradiction.

---

### User Story 5 - Relation Semantics Are a Constraint System, Not a Catalogue (Priority: P2)

A schema author registers a new relation type by declaring the allowed subject and object classes, the admissible evidence patterns, the temporal semantics and the admission rules. The extractor consumes the same declaration to know which spans can be proposed; the validator consumes it to know which claims are admissible; the admission engine consumes it to know what to do with a claim that is not.

**Why this priority**: Today relation semantics live in extractor code, so a new relation type is a code change in several places with no single place to review. A constraint system makes the relation vocabulary data, which is the precondition for a relation-type registry and for ontology versioning.

**Independent Test**: Register a new relation type at runtime, then assert that the same declaration is visible to the relation-candidate proposer, the validator, and the admission-rule evaluator, and that a claim violating only the new schema is rejected with the new schema's reason code.

**Acceptance Scenarios**:

1. **Given** a `RelationSchema` for `works_for` with allowed subject class `PERSON` and object class `ORGANIZATION`, **When** a claim `ORGANIZATION --works_for--> PERSON` is validated, **Then** it is rejected citing `schema_object_class_not_allowed`.
2. **Given** a relation schema declaring `temporal_semantics=REQUIRED_INTERVAL`, **When** a claim for that type is submitted with no `valid_from`, **Then** the validator reports `UNDERDETERMINED` with `temporal_interval_required`.
3. **Given** a registered schema set, **When** the relation vocabulary is enumerated, **Then** every declared type reports its arity mode, allowed classes, evidence patterns, temporal semantics and admission rule id, and the enumeration is deterministically ordered.
4. **Given** a claim whose `relation_type` has no registered schema, **When** validated, **Then** the verdict is `UNDERDETERMINED` with `schema_unregistered` and the claim is preserved — an unknown relation is not a false one.

---

### User Story 6 - Every Relation Answers "Why Do You Believe This?" (Priority: P2)

An investigator selects a relation in the graph. The system must walk backward: relation → assertion → mention → segment → observation → capture → source → raw object, and forward: source → capture → observation → segment → mention → candidate → assertion → relation → entity. The lineage must be complete or explicitly report the first missing hop, never silently truncate.

**Why this priority**: Evidence-first is a constitutional principle, and the UI's usefulness depends entirely on being able to answer this question for any node. It is also the cheapest possible integration surface for the new UI workspace, because it is a single traversal API.

**Independent Test**: Build a small in-memory evidence graph covering one source, one observation, one mention, one candidate, one assertion and one relation; then assert the backward lineage from the relation resolves to the source and the forward lineage from the source resolves to the relation, and that removing the segment hop causes the traversal to report the exact missing hop rather than returning an empty list.

**Acceptance Scenarios**:

1. **Given** a complete evidence chain, **When** backward lineage is requested from a relation id, **Then** every hop up to the source id is returned in order with its hop kind.
2. **Given** a chain missing the segment hop, **When** backward lineage is requested, **Then** the result carries `complete=False` and names `segment` as the first unresolved hop.
3. **Given** a source id, **When** forward lineage is requested, **Then** every derived relation reachable from that source is returned, each with the assertion that grounds it.
4. **Given** a relation whose claim cites two observations from the same source family, **When** its independence group is computed, **Then** the group contains exactly one member and the claim's `independent_source_count` is 1, not 2.

---

### User Story 7 - Store Parity and Rebuildability Are Provable (Priority: P2)

A projection must be rebuildable from durable events alone. The in-memory store, the Neo4j adapter and the rebuildable wrapper must accept the same relation semantics, and a rebuild must reproduce an identical relation set with an identical checksum.

**Why this priority**: The hypergraph's existing `logical_id`/`edge_id` split is sound, but the plain-edge path has three known defects — the `write_hyperedge` idempotency guard tests membership of a `dict` (always false), `neighbors()` discards direction, and the Neo4j adapter drops `properties` and creates no edge id. A projection that cannot round-trip its own relations is not a projection.

**Independent Test**: Write a relation set through the rebuildable wrapper, take a snapshot, rebuild into a fresh store, and assert the edge checksums are equal and every relation is present with all fields intact. Separately, assert the Neo4j adapter emits a `MERGE` carrying the relation id and the full property payload.

**Acceptance Scenarios**:

1. **Given** a set of relations written through `RebuildableGraphStore`, **When** `rebuild()` produces a fresh store, **Then** both stores' relation checksums are equal and no relation is missing.
2. **Given** the same relation written twice, **When** it is written through any store, **Then** the store reports the same count both times (idempotent, I-11).
3. **Given** a hyperedge written twice with identical content, **When** the second write occurs, **Then** the store's hyperedge count is unchanged — the current guard is a no-op and must be fixed.
4. **Given** the Neo4j adapter, **When** a relation is written, **Then** the emitted query contains the relation id and the full property payload, and a re-write is a `MERGE` on the relation id.
5. **Given** a snapshot, **When** it is taken twice over an unchanged store, **Then** the checksums are equal and the projection id is stable rather than freshly randomised.

---

### User Story 8 - The Frontend Stops Assuming Every Edge Is Undirected (Priority: P3)

A UI engineer adds a new relation kind to the graph. The edge builder must honour the declared arity of that kind instead of collapsing every pair through `min`/`max`, must produce ids that agree with the backend identity, and must stop pinning golden vectors to a 32-bit hash that is being replaced.

**Why this priority**: The UI is downstream of the semantics, but it is the surface where a collapsed `works_for` becomes a *wrong answer shown to an analyst*, so it cannot ship after the semantics without a visible inconsistency window.

**Independent Test**: Run the frontend edge-builder test suite; assert a directed pair yields two oriented edges, an undirected pair yields one, an N-ary observation is not expanded into a clique by default, and the layout seed remains stable for a given node set.

**Acceptance Scenarios**:

1. **Given** seeds `{a: A, b: B, kind: "relationship"}` and `{a: B, b: A, kind: "relationship"}`, **When** edges are formed, **Then** two edges are emitted with distinct ids and preserved orientation.
2. **Given** a co-occurrence observation over three nodes, **When** edges are formed, **Then** the N-ary relation is preserved as one hyperedge-shaped record rather than three pairwise edges, and the pairwise projection remains available only as an explicitly derived view.
3. **Given** an unchanged node set, **When** the layout seed is computed twice, **Then** the values are equal.
4. **Given** the FNV-1a helper, **When** it is no longer used for edge identity, **Then** it remains available for non-identity purposes (layout seeds, checksums) and its existing golden vector test still passes.

---

### Edge Cases

- A relation whose subject and object are the same entity (self-loop) — rejected at construction, never emitted.
- An N-ary relation with fewer than two distinct members — rejected; a relation with duplicate members after role canonicalisation — rejected with the offending role named.
- Two claims of the same relation with *overlapping* validity intervals and conflicting object values — reported as `CONFLICTING`, not silently merged, and both preserved.
- A context whose `parent_context_id` forms a cycle — detected and reported as `context_parent_cycle`; the frame is still storable.
- A source that appears under two different `source_family` values across captures — the independence group is not collapsed, and the discrepancy is reported.
- An observation whose `published_at` precedes its `observed_at` (clock skew, or an archive backfill) — reported as `UNDERDETERMINED` with `temporal_publication_before_observation`, not rejected, because archives legitimately backfill.
- A relation id collision after truncation to 128 bits — the collision is *recorded and surfaced* rather than treated as an identity merge, so an operator can see it.
- Extraction under a context whose `ontology_version` no longer exists in the ontology pack registry — `STALE` with the missing version named.
- A claim that references an `EvidenceContext` id that has been garbage-collected — resolution fails loudly with `context_unresolved`; the claim is never reinterpreted under a default context.
- An N-ary relation where a member is also the subject of a pairwise edge of the same type — the pairwise edge is derived and marked lossy; the N-ary form stays authoritative.
- A relation with `valid_from == valid_to` — a zero-width interval, treated as a point occurrence, valid.
- A relation type registered as `NARY` but supplied with exactly two members — valid, and its identity must equal the identity of the same pair declared `DIRECTED` *only if* the arity modes agree; otherwise the ids differ, because arity mode is part of the identity material.

## Requirements *(mandatory)*

### Relation Claim Semantics

- **FR-001**: The system MUST model a relation as a first-class `RelationClaim` carrying: `relation_id`, `logical_relation_id`, `revision_number`, `relation_type`, `subject_ref`, `object_ref`, `arity_mode`, `role_bindings`, `valid_from`, `valid_to`, `observed_at`, `published_at`, `known_from`, `known_until`, `assertion_refs`, `observation_refs`, `context_ref`, `source_independence_groups`, `extraction_version`, `normalization_version`, `ontology_version`, `status`, `confidence`, `evidence_grade`, `created_by`, `supersedes`, `contradicts`.
- **FR-002**: The system MUST distinguish `UNDIRECTED`, `DIRECTED`, `NARY` and `TEMPORAL` arity modes, and MUST reject a self-loop relation, an N-ary relation with fewer than two distinct members, and an N-ary relation with duplicate members after role canonicalisation.
- **FR-003**: The system MUST separate relation *identity* from relation *version*: all revisions of one relation MUST share a `logical_relation_id`, and each distinct content MUST produce a distinct `relation_id`.
- **FR-004**: Identity MUST be computed as a **128-bit truncated SHA-256** over a documented, deterministically serialised material string that includes arity mode, relation type, canonical participants (order-normalised for `UNDIRECTED` and `NARY`, order-preserving for `DIRECTED`), and role bindings. The output MUST be at least 32 hex characters.
- **FR-005**: The system MUST record a content hash of the claim so that any two claims with identical content are byte-identical and idempotent (I-11).
- **FR-006**: The system MUST preserve `SUPERSEDED`, `RETRACTED` and `CONTRADICTED` claims queryable and MUST NOT delete them (I-3).
- **FR-007**: The system MUST reject any relation write that lacks a resolvable evidence context (I-12).

### Direction, Arity and Identity Correctness

- **FR-008**: The system MUST compute `(A, B, directed_type)` and `(B, A, directed_type)` to different relation ids, and `(A, B, undirected_type)` and `(B, A, undirected_type)` to the same relation id.
- **FR-009**: For N-ary relations, member ordering MUST NOT affect identity, but permuting a member between two different roles MUST affect identity.
- **FR-010**: The system MUST support directional reads: `neighbors(node, edge_type, direction)` with `direction` in `{in, out, both}`, defaulting to `out` for directed arity and `both` for undirected arity.
- **FR-011**: The system MUST surface, not hide, any identity collision detected within a claim set, including the colliding ids and the claims involved.
- **FR-012**: The system MUST reject registration of a relation type whose arity mode conflicts with its participant shape, e.g. a `DIRECTED` type given three participants.

### Evidence Context

- **FR-013**: The system MUST provide an immutable `EvidenceContext` frame with: `context_id`, `tenant_id`, `investigation_id`, `entity_anchor`, `observation_id`, `source_id`, `document_id`, `segment_id`, `subject_candidate_ids`, `object_candidate_ids`, `observed_at`, `published_at`, `valid_from`, `valid_to`, `source_family`, `independence_group`, `extraction_version`, `normalization_version`, `ontology_version`, `completeness`, `trust_state`, `policy_snapshot_ref`, `parent_context_id`.
- **FR-014**: `context_id` MUST be a content address over the canonical frame content, so two independently constructed identical frames yield the same id.
- **FR-015**: An `EvidenceContext` MUST be frozen; mutation MUST raise rather than alter a stored frame.
- **FR-016**: The system MUST resolve a claim's `context_ref` to its frame, and MUST fail loudly with `context_unresolved` rather than substituting a default context.
- **FR-017**: The system MUST detect a parent-context cycle and report `context_parent_cycle`.
- **FR-018**: Frames MUST be shared by reference. A claim MUST NOT embed a mutable copy of its context.

### Layered Context Validation

- **FR-019**: The system MUST evaluate exactly seven validation layers, in order, and MUST report every layer's outcome even when an earlier layer fails: `structural`, `semantic`, `temporal`, `provenance`, `identity`, `cross_source`, `graph_constraints`.
- **FR-020**: `validate(context, claim)` MUST return a `ValidationResult` with a `verdict` in `{VALID, INVALID, UNDERDETERMINED, INCOMPLETE, CONFLICTING, STALE}` and a non-empty `reasons` list of `ValidationReason` records, each carrying a stable `code`, the failing `layer`, and a human-readable `detail`.
- **FR-021**: The validator MUST NOT return a bare boolean, and MUST NOT mutate the claim or the context.
- **FR-022**: Structural validation MUST reject missing required fields, inverted intervals and unresolvable refs. Semantic validation MUST reject claims whose subject or object class is not permitted by the relation schema. Temporal validation MUST reject intervals whose end precedes their start and MUST report, without rejecting, publication-before-observation. Provenance validation MUST reject cross-tenant evidence and MUST reject a missing or unresolved context. Identity validation MUST verify the claim's identity material recomputes to its own `relation_id` and `logical_relation_id`. Cross-source validation MUST compute independence groups and report publication count separately from independent source count. Graph-constraint validation MUST reject a relation whose endpoints are not admitted entities, and MUST report, without rejecting, a missing endpoint as `UNDERDETERMINED`.
- **FR-023**: A claim whose relation type has no registered schema MUST validate as `UNDERDETERMINED` with `schema_unregistered`, never `INVALID`.
- **FR-024**: Disjoint validity intervals for the same relation type and participant pair MUST validate as `VALID` and MUST record a `temporal_non_overlap` note.
- **FR-025**: The system MUST compute a claim's `evidence_grade` from its context's completeness, trust state, independent source count and declared confidence, storing the component values separately (constitution IV: no single score equals truth).

### Relation Schema Constraint System

- **FR-026**: A `RelationSchema` MUST declare: `relation_type`, `arity_mode`, `allowed_subject_classes`, `allowed_object_classes`, `allowed_role_bindings`, `admissible_evidence_patterns`, `temporal_semantics`, `admission_rule_id`, and `schema_version`.
- **FR-027**: `temporal_semantics` MUST be one of `POINT`, `REQUIRED_INTERVAL`, `OPTIONAL_INTERVAL`, `OPEN_ENDED`.
- **FR-028**: The relation vocabulary MUST be enumerable in deterministic order and MUST be readable by the relation-candidate proposer, the validator and the admission-rule evaluator without any of them embedding their own copy of the relation list.
- **FR-029**: Schemas MUST be versioned, and a claim MUST record the `schema_version` in force when it was produced.

### Evidence Graph and Lineage

- **FR-030**: The system MUST represent the evidence chain `Source → Capture → Observation → Segment → Mention → Candidate → Assertion → Relation → Entity` and MUST support traversal in both directions.
- **FR-031**: Backward lineage from any relation MUST return every hop to the source, each labelled with its hop kind.
- **FR-032**: Forward lineage from any source MUST return every derived relation, each with the assertion that grounds it.
- **FR-033**: A lineage traversal that cannot complete MUST return `complete=False` and name the first unresolved hop; it MUST NOT return a silently truncated result.
- **FR-034**: The system MUST compute `source_independence_groups` for a claim such that two captures from one source family or one publisher count as a single independent source, and MUST store `publication_count` separately from `independent_source_count`.

### Store Parity, Persistence and Rebuildability

- **FR-035**: `GraphNode`, `GraphEdge` and the N-ary relation MUST all carry a stable identifier, and every store MUST preserve it on write and read.
- **FR-036**: Every `GraphStore` implementation MUST accept the same relation semantics, MUST be idempotent on identical content (I-11), and MUST enforce provenance on every write (I-12).
- **FR-037**: The N-ary write path's idempotency guard MUST function; the current check tests membership of a string-keyed mapping and therefore never fires.
- **FR-038**: The Neo4j adapter MUST write the relation id and the full property payload, and MUST `MERGE` on the relation id so a re-write is idempotent.
- **FR-039**: `RebuildableGraphStore` MUST forward N-ary writes, MUST record the projection id it snapshots, and MUST honour a supplied snapshot offset rather than always replaying from zero.
- **FR-040**: A rebuild from the durable log MUST reproduce a relation set with an identical checksum.
- **FR-041**: A snapshot taken twice over an unchanged store MUST produce an equal checksum and a stable projection id.
- **FR-042**: The system MUST persist claims, contexts and independence groups in PostgreSQL via a forward-only Alembic migration that creates tables before columns, backfills before unique indexes, and is proven to reach the same schema from a fresh install and from an install that already has the previous revision applied.

### Frontend Alignment

- **FR-043**: The frontend edge builder MUST honour the declared arity of each relation kind: directed kinds preserve orientation, undirected kinds collapse reversed pairs.
- **FR-044**: Frontend edge ids MUST agree with the backend identity scheme, or the frontend MUST be explicitly marked as a derived local view that does not claim backend identity.
- **FR-045**: The frontend MUST NOT expand an N-ary observation into a pairwise clique as its only representation; the N-ary form MUST be preserved and the pairwise projection MUST be an explicitly derived view.
- **FR-046**: The 32-bit FNV-1a helper MUST remain available for non-identity purposes and its existing golden-vector test MUST continue to pass; it MUST NOT be used for relation identity.

### Observability and Access

- **FR-047**: The system MUST expose a read API for a claim, its context, its validation result, its lineage in both directions, and its revisions.
- **FR-048**: Every read MUST be tenant-scoped, and a cross-tenant read MUST be refused.
- **FR-049**: The system MUST emit an event when a claim is created, revised, superseded or contradicted, and when a context is registered, so projections rebuild from the durable log (I-12).
- **FR-050**: Every rejection MUST be preserved with its decision, reasons, score components, versions and timestamps, and MUST be replayable.

### Key Entities

- **RelationClaim**: A first-class assertion that a relation of a given type holds between participants, under a specific context and temporal interpretation, with evidence, versions, status and a supersession/contradiction lineage.
- **RelationIdentity**: The stable logical identity of one relation, shared by all of its revisions.
- **RelationRevision**: One content-distinct version of a relation, with its own relation id, evidence set, temporal window and revision number.
- **RelationArityMode**: `UNDIRECTED` | `DIRECTED` | `NARY` | `TEMPORAL` — how participants are ordered for identity and how neighbours are read.
- **RelationSchema**: A declarative constraint declaration for one relation type: allowed classes, role bindings, evidence patterns, temporal semantics, admission rule and schema version.
- **RelationRoleBinding**: A named participant slot in an N-ary relation.
- **EvidenceContext**: An immutable, content-addressed frame describing the exact conditions under which an interpretation was produced and under which a claim may be interpreted.
- **ContextValidationResult**: The graded verdict of validating a claim against its context, with per-layer outcomes and structured reasons.
- **ValidationReason**: A stable reason code, the layer that raised it, and a human-readable detail.
- **EvidenceHop**: One link in the evidence chain, with a hop kind and a node reference.
- **LineageTrace**: An ordered list of evidence hops with a `complete` flag and, when incomplete, the first unresolved hop.
- **IndependenceGroup**: A set of evidence refs attributable to one independent origin, used so copied or derived sources are not counted as independent support.
- **GraphProjection**: A rebuildable materialisation of relations and evidence hops into a graph backend, with a snapshot, checksum and offset.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `(A, works_for, B)` and `(B, works_for, A)` produce different relation ids; `(A, co_occurs_with, B)` and `(B, co_occurs_with, A)` produce the same relation id — verified as a pinned test.
- **SC-002**: One million deterministically generated claims yield exactly one million distinct relation ids, each at least 32 hex characters, with zero undetected collisions.
- **SC-003**: Any relation returned by the read API can produce a backward lineage trace to a source id, or a `complete=False` trace naming the first unresolved hop — 100% of cases, verified over a generated fixture corpus.
- **SC-004**: Given a claim, `validate()` returns all seven layer outcomes and a non-empty reason list whenever the verdict is not `VALID`; zero boolean-only validation results exist.
- **SC-005**: The validator classifies a `valid_from > valid_to` claim as `INVALID/temporal_interval_inverted` while reporting the structural layer as `PASSED`.
- **SC-006**: The validator classifies `DOCUMENT --works_for--> PERSON` as `INVALID/schema_subject_class_not_allowed`, citing both the offending class and the allowed set.
- **SC-007**: The validator classifies a claim whose evidence observation is in another tenant as `INVALID/provenance_tenant_mismatch`.
- **SC-008**: The validator classifies a claim with an unregistered relation type as `UNDERDETERMINED/schema_unregistered` and preserves it.
- **SC-009**: Two `EvidenceContext` frames constructed by different paths with identical content produce byte-identical `context_id` values.
- **SC-010**: A forward-only migration reaches an identical schema from a fresh install and from an install with the previous revision applied, asserted by programmatic schema comparison.
- **SC-011**: A rebuild from the durable log reproduces a relation set with an identical checksum, and a double snapshot yields an equal checksum and a stable projection id.
- **SC-012**: Writing the same relation twice through any store leaves the store's relation count unchanged, including the N-ary path whose idempotency guard currently never fires.
- **SC-013**: The Neo4j adapter's emitted write for a relation contains the relation id and the full property payload.
- **SC-014**: The frontend edge builder emits two oriented edges for a directed pair and one edge for a reversed undirected pair, and preserves an N-ary observation as one record.
- **SC-015**: The existing 32-bit FNV-1a golden-vector test still passes after the identity change, proving the hash helper was replaced for identity purposes only.
- **SC-016**: The full Python test suite for the touched apps shows no new failures relative to the recorded pre-feature baseline.
- **SC-017**: The frontend test suite and `tsc` typecheck pass with no new failures relative to the recorded pre-feature baseline.

## Assumptions

- The 128-bit truncated SHA-256 identity scheme will become the canonical backend relation identity; the 32-bit FNV-1a scheme is retired for identity but retained for layout seeds and UI checksums.
- PostgreSQL is available for the persistence layer, and Alembic runs through the async path already established by the previous feature's environment repair.
- The ontology pack registry already tracks registered versions, so schema staleness can be detected by lookup rather than by embedding a version list.
- The existing `HyperEdge` `logical_id` / `edge_id` split in `apps/shared/domain/hypergraph.py` is the precedent for the claim identity/revision split, and the new model reuses its conventions rather than inventing a parallel one.
- The existing N-ary `clique_projection` remains available as an explicitly derived, lossy view; nothing that treats it as authoritative is introduced.
- Frontend test infrastructure (Vitest + jsdom) and Python test infrastructure (pytest per app) remain as they are.
- Analyst-facing UI work is out of scope for this feature; this feature delivers the API and client primitives the UI will be built on, plus the frontend edge-identity correction that would otherwise show wrong answers.

## Out of Scope

- Entity Workspace / Evidence Inspector UI redesign (next feature; this feature supplies its API and the corrected edge semantics).
- Relation *candidate* extraction from free text (a separate extraction feature; this feature defines the `RelationSchema` contract that extraction will consume).
- Normalization algebra and mention arbitration (separate extraction feature).
- Multi-pass entity resolution (separate feature).
- Contradiction *reasoning* over the contradiction graph (separate feature; this feature persists `contradicts` and `supersedes` links and reports conflicting intervals, but does not rank which claim wins).
- Temporal consistency checking across an entity's whole worldline (separate feature; this feature validates a single claim's own interval).
- Pivot/discovery fabric and additional source connectors.
- Any change to the acquisition, streaming or transport layers.

## Dependencies

- `apps/shared/domain/hypergraph.py` — existing `hyperedge_id` / `hyperedge_version_id` identity conventions and the `HyperGraph` upsert pattern.
- `apps/shared/domain/temporal_worldline.py` — `EventInterval`, `TimePrecision`, `EvidenceRef` and interval-overlap semantics.
- `apps/shared/domain/statement.py` — the canonical `Statement` record that assertions already produce.
- `apps/projection/graph/abstraction.py` — `GraphNode`, `GraphEdge`, `GraphStore`, `InMemoryGraphStore`.
- `apps/projection/graph/neo4j.py` and `snapshot.py` — the vendor adapter and the rebuildable wrapper.
- `apps/shared/events/ontology_pack.py` — registered ontology versions for staleness detection.
- `apps/control-plane/db/schema.py` and the Alembic version chain — for the forward-only migration.
- `apps/webapp/src/lib/edgeFormation.ts` and its golden-vector tests — for the frontend identity correction.

## Risks

- **Risk: identity change breaks existing stored edges.** Mitigation: the new identity is introduced alongside the old one; `logical_relation_id` is derived from the new scheme while a legacy id may be retained as an alias for previously written relations. A migration note records that relations written before this feature keep their legacy id until re-materialised.
- **Risk: 128-bit ids increase storage and index size.** Accepted: 32 hex characters versus 8, against a birthday-collision threshold that moves from ~77k to ~10^19 relations. The correctness win dominates.
- **Risk: the layered validator becomes a bottleneck.** Mitigation: the validator is pure and stateless; layers short-circuit only for the verdict, all layer outcomes are still computed, and the expensive layers (cross-source, graph constraints) accept pre-computed inputs.
- **Risk: schema-driven extraction couples the extraction layer to the schema registry.** Mitigation: this feature ships the registry and the validator's consumption of it, but does not yet change extractors; the consumption contract is versioned so extraction can adopt it independently.
- **Risk: fixing the frontend edge identity changes rendered graph topology.** Accepted and intended: the current behaviour merges inverse directed relations. The change is a correctness fix, and the UI will show more edges, not fewer.
- **Risk: pre-existing test failures obscure regressions.** Mitigation: a baseline of pre-existing failures was recorded before implementation (shared: 3, projection: 3 plus 2 collection errors; admission: 96 passing; interpretation: 184 passing; webapp: 232 passing) and the exit gate is "no new failures", not "all green".
