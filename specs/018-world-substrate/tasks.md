# Tasks: World Substrate Closure

**Feature**: `018-world-substrate` · **Plan**: `plan.md`

Ordered so the suite that is green today stays green. Production code first; the corpus is functionality,
not a test suite (D-C).

## Phase 0 — Durable identity and resolution (P0, FR-001…FR-005)

- [ ] T001 `apps/shared/domain/entity_identity.py` — `EntityIdentity` (entity_id, tenant_id,
      anchor_mention_id, anchor_observation_id, anchor_capture_id, created_by_resolution) with a
      write-once anchor. A second bind raises `AnchorConflict`; the anchor is never re-elected (FR-001).
- [ ] T002 `InMemoryEntityIdentityStore` — anchor lookup by mention (the resolution hot path) and
      ordered identity/history by entity. Fail-closed across tenants (FR-002, FR-005).
- [ ] T003 Decision serialisation: `ResolutionDecision` → durable record, `RES-` content-addressed,
      append-only, superseding rather than overwriting (FR-003). Include `AMBIGUOUS` and `UNRESOLVED`.
- [ ] T004 Reconstruction: given `ENT-`, return anchor + ordered `RES-` history + terminal verdict
      (FR-004, SC-2, SC-3).
- [ ] T005 ORM: `entity_identity`, `resolution_decision` in `db/schema.py`; UNIQUE on
      `(tenant_id, anchor_mention_id)`, index on `(tenant_id, entity_ref, decided_at)` (SC-17).
- [ ] T006 Migration `019_world_substrate.py`, forward-only, `downgrade()` raises, ORM parity proven
      offline exactly as 018 was.

## Phase 1 — Capture and acquisition lineage (P0, FR-006…FR-009, FR-024…FR-027)

- [ ] T007 `CaptureTimeBasis` enum on `domain/capture.py` (FETCH / INDEX_OBSERVATION / PUBLICATION /
      DERIVED / ABSENT) so an absent fetch time is distinguishable from an unwritten one (D-B, SC-16).
- [ ] T008 `apps/acquisition/stream.py` — `StreamAdapter` protocol, `DataStream` registry. A stream that
      cannot state which of the six time axes it supplies is refused at registration (FR-024, FR-026).
- [ ] T009 Common Crawl adapter: map `CaptureObservation` onto `Capture` with
      `CaptureTimeBasis.INDEX_OBSERVATION` and an `ABSENT` fetch time. **The index timestamp is never
      promoted to a fetch time** (FR-025). Adapt `cc_extract`, do not rewrite it.
- [ ] T010 A second non-API, non-Common-Crawl stream adapter through the same contract, to exercise the
      seam (FR-027, SC-15).
- [ ] T011 `captures` + `ingest_batches` + `data_stream` tables, migration parity (FR-009).
- [ ] T012 Orchestrator stops fabricating a capture id; the real `Capture` flows into lineage, and
      `Source → Capture → Observation → … → GraphProjection` is traversable both ways (FR-008, SC-4, SC-5).

## Phase 2 — Claim lifecycle (P0, FR-010…FR-013)

- [ ] T013 `apps/shared/domain/relation_claim_material.py` — `RelationClaimMaterial`: the unadmitted,
      self-consistent value carrying its own derived ids (D3).
- [ ] T014 `build(candidate) -> material` / `validate(material, context, regime) -> ValidationReport` /
      `admit(material, report) -> committed claim` as three distinct operations (FR-010, SC-7).
- [ ] T015 `LayeredValidator` accepts material, not only a committed claim; an unadmittable material is
      still validatable (FR-011, SC-6).
- [ ] T016 `to_claim()` retained as a deprecated composition of the three so the 016 and orchestrator
      suites stay green. Marked deprecated in the docstring, not silently kept.

## Phase 3 — Real semantic regime (P0, FR-014…FR-016)

- [ ] T017 `apps/shared/semantic/regime_store.py` — durable regime substrate.
- [ ] T018 `semantic_regime` table + `regime_id` on `candidates` and `relation_claim`; parity-checked.
- [ ] T019 Compatibility layer resolves the regime from storage. `regime_unevaluated` MUST NOT occur on
      the golden path; an unresolvable regime is a counted, stated `UNRESOLVED` (FR-015, SC-8).
- [ ] T020 No default/empty regime substitution (FR-016).

## Phase 4 — Relation-aware extraction (P1, FR-017…FR-019)

- [ ] T021 The cue-keyed organisation rule moves from `semantic_path/execution.py` into the extraction
      package (FR-018, SC-9).
- [ ] T022 The extraction package yields a relational reading — trigger span, supporting spans, role
      assignment, `relation_ref`, temporal hypothesis, method — from a cue context, so "CEO of Acme"
      resolves without a legal-form suffix (FR-017).
- [ ] T023 No extractor may mark a reading `SUPPORTED` (FR-019, SC-10).

## Phase 5 — Corpus and replay (P1, FR-020…FR-023)

- [ ] T024 `apps/control-plane/semantic_path/corpus.py` — committed cases with expected mentions,
      resolution identities, decisions, claims, validation verdicts, lineage and materialisation (D-C).
- [ ] T025 Invariance compared over identity outputs, decision hashes, claim hashes, context references
      and edge materialisation — not the final graph alone (FR-021, SC-11).
- [ ] T026 Replay into an empty store reproduces graph, ids and lineage; replaying the replay is
      identical (FR-022, SC-12).
- [ ] T027 Corpus covers ambiguity, unresolvable, cross-tenant refusal, unknown type, non-blocking
      validation finding, non-convergent collective, temporal conflict, independence groups (FR-023, SC-13).

## Phase 6 — Verification (SC-14 is the gate)

- [ ] T028 SC-0 non-regression: projection 189/1, acquisition 126/10, interpretation 185, admission 96,
      control-plane 332 with only the 2 pre-existing `test_donor_api` failures, shared's 14 known failures
      unchanged.
- [ ] T029 SC-1: `ENT-` unchanged when a caller discards its `ResolutionScope` entirely.
- [ ] T030 **SC-14 (gate):** both "why was this accepted" chains reconstruct with no hole —
      `Entity → Resolution decision → Mentions → Observations → Captures → Sources` and
      `RelationClaim → RelationCandidate → Assertion → Mentions → Evidence`.

## Dependencies

T001 → T002 → T003 → T004. T005 → T006 (ORM after the value types exist).
T007 → T008 → T009, T010. T009 + T010 → T012. T011 after T008.
T013 → T014 → T015 → T016.
T017 → T018 → T019 → T020.
T021 → T022 → T023.
T024 needs T003, T009, T014, T019. T025 → T026 → T027.
T012, T016, T019, T020, T023 → T024.
Everything → T030.

T001…T004, T013…T016, T017…T020, T024…T027 are mutually independent and parallelise.
T005…T012 (schema + migration) must be sequenced with each other but not with the value-type phases.
