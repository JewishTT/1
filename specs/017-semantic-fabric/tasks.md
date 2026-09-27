# Tasks: Semantic Fabric (Ontologies as External Tools)

**Feature**: `017-semantic-fabric` · **Plan**: `plan.md`

Production work first. Each phase is ordered so the suite that is green today stays green;
the final phase is verification, not test-writing.

## Phase 0 — Contracts (blocking; everything else imports this)

- [ ] T001 `apps/shared/semantic/contracts.py` — `SemanticRef`, `RelationRef`, `TypeScope`
      (observed/inferred/mapped/context), `SemanticStatus` (observed/extracted/inferred/mapped/
      validated/resolved), `TypeAssertion`, `ValidationFinding`, `ValidationVerdict`
      (VALID/INVALID/UNKNOWN/UNSUPPORTED/CONFLICTING), `ValidationReport`. Immutable, frozen,
      content-addressed `content_key()` where identity demands it.
- [ ] T002 `apps/shared/semantic/__init__.py` — export **only** `SemanticRef`, `RelationRef`,
      `ValidationReport` (FR-005). No SKOS/SSSOM/SHACL/OAK/LinkML type escapes.

## Phase 1 — Open world (the load-bearing gate, US1)

- [ ] T003 Remove the closed-world gate at `apps/interpretation/extractors/registry.py:101,152`.
      An untyped/unknown-kind mention is **kept**, recorded with no semantic commitment — not
      dropped. `OntologyPack` may still be consulted for hints, never for permit/deny (FR-002).
- [ ] T004 Update `apps/acquisition/tests/test_pipeline.py:88` which constructs
      `ExtractorRegistry(ontology_pack=...)`; the parameter survives as a hint source.
- [ ] T005 Unknown entity type / unknown relation operator admitted end-to-end with no invented
      type (SC-1).

## Phase 2 — Layered typing (US2, FR-003/004/018)

- [ ] T006 `TypeAssertion` store: ORM models `type_assertions`, `semantic_profiles`,
      `semantic_mappings`, `validation_findings` in `apps/control-plane/db/schema.py`,
      tenant-scoped, provenance-bearing.
- [ ] T007 Forward-only alembic migration `018_semantic_fabric.py`.
- [ ] T008 Layer reads: one entity returns observed + inferred + mapped + context assertions
      simultaneously; no layer overwrites another (SC-2).
- [ ] T009 Monotonicity: `raw → surface → hypothesis → mapped → resolved` never deletes a prior
      state; the full history for any entity is reconstructable (FR-004, SC-2, US9).

## Phase 3 — Semantic profiles (US2, FR-007)

- [ ] T010 `apps/shared/semantic/profiles.py` — `SemanticProfile` (profile_id, parent_profile,
      version, types/relations/vocabularies/constraints/mappings, `applies_to` tags), cycle-safe
      inheritance resolution, multi-profile applicability to one entity.
- [ ] T011 Profile mismatch is never a rejection reason (FR-007).

## Phase 4 — Operators, closed world (US3, US4, FR-006/013)

- [ ] T012 `apps/shared/semantic/operators.py` — bind policy/strategy to the **existing**
      `RelationSchema`: arity, direction, roles, domain/range hints, temporal semantics, symmetry,
      inverse, transitivity, evidence requirements, extraction strategies, admission policy,
      validation policy, projection policy. No parallel semantic declaration (FR-006).
- [ ] T013 Default `domain_range` = `warn` (D1). Stricter policies are opt-in per operator.
- [ ] T014 Deterministic extraction binding: datatype contracts bind strictly (phone/email/URL/
      IPv4/UUID/date/currency/country code/language code); an unclassifiable token yields a
      mention with **no** type and does not abort the pass (US3).

## Phase 5 — Vocabularies and expansion (US6, FR-008/016)

- [ ] T015 `apps/shared/semantic/vocabularies.py` — SKOS `Concept`/`ConceptScheme`, `pref_label`,
      `alt_labels`, `broader`/`narrower`/`related`, and `exactMatch`/`closeMatch`/`broadMatch`/
      `narrowMatch`. No concept equality is ever encoded.
- [ ] T016 `apps/shared/semantic/expansion.py` — `broaderTransitive`/`narrowerTransitive` as an
      explicit per-operation opt-in; the choice is recorded, expansion is not a stored fact about
      the world (SC-6).
- [ ] T017 Candidate blocking narrowed by type hypothesis + relation affordance, reproducible,
      asserting nothing onto pruned candidates (FR-016, SC-10).

## Phase 6 — Mappings (US10, FR-009)

- [ ] T018 `apps/shared/semantic/mappings.py` — SSSOM-style `SemanticMapping`: predicate,
      mapping source, mapping version, justification, provenance; citable as evidence and
      re-evaluable. Replaces hardcoded external-type dicts (FR-009).

## Phase 7 — Validation (US4, US5, FR-011/012/014)

- [ ] T019 `apps/shared/semantic/validation.py` — layered structural → semantic → temporal →
      provenance → cross-source → graph-level, each returning a graded verdict, distinguishing
      `INVALID` from `UNKNOWN`/`UNSUPPORTED` (SC-9).
- [ ] T020 A failed check attaches a finding and never deletes or deprojects the assertion
      (SC-4, FR-012).
- [ ] T021 `EvidenceContext` extended with the semantic regime: active profile, profile version,
      ontology version, mapping set, validation profile. Its content-addressed identity semantics
      are unchanged (FR-014).
- [ ] T022 `apps/shared/semantic/shacl.py` — native graph → RDF validation view; `pyshacl`
      imported **lazily**; absent library ⇒ `UNSUPPORTED`, never a write-path failure, never a
      false `VALID` (FR-010, D4).
- [ ] T023 SHACL is off the write path and bounded (constitution VIII).

## Phase 8 — Pluggable access (US8, FR-015)

- [ ] T024 `apps/shared/semantic/registry.py` — `SemanticRegistry` exposing `resolve_term()`,
      `get_aliases()`, `parents()`, `children()`, `related()`, `mappings()`. Backend-agnostic;
      swapping the backend changes no calling code (SC-7).
- [ ] T025 An OAK-backed adapter behind the same interface, optional/lazy.

## Phase 9 — Contracts via LinkML (FR-017, P3)

- [ ] T026 LinkML used **only** for boundary contracts: `SourceLocator`,
      `ObservationEnvelope`, `AssertionEnvelope`, `RelationContract`, `ValidationReport`,
      `MaterializationManifest`. Optional/lazy; never enumerates permissible entity kinds.

## Phase 10 — Verification (last, not test-driven)

- [ ] T027 SC-0 non-regression: projection `189 passed, 1 skipped`; acquisition
      `126 passed, 10 skipped`; control-plane collects 343 with 0 errors, and the only failures
      are the 2 pre-existing `test_donor_api` plus the Postgres-unavailable parity test.
- [ ] T028 SC-3: `apps/shared/domain` has zero imports of SKOS/SSSOM/SHACL/OAK/LinkML.
- [ ] T029 SC-5: `OntologyPack.allows_type`/`allows_relation` unreachable from any admission path.
- [ ] T030 SC-1..SC-10 walked end-to-end against the acceptance scenarios in `spec.md`.

## Dependencies

T001 → T002 → all. T003–T005 independent of T006+ (can run in parallel). T006 → T010, T012, T018.
T019 → T022. T001 → T024.
