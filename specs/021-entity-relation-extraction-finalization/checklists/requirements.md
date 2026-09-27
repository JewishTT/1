# Requirements checklist: 021-entity-relation-extraction-finalization

**Gate**: every row must read `verified`, `verified only offline`, `known limitation` or
`deferred` before the feature is called complete. A tick means *checked against the code or a
test*, never "read and believed".

**Schema**: `| # | FR | Requirement (one line) | Method | Task | State |`

| Column | Contract |
|---|---|
| `#` | Row id. `R` + three digits = the one row per FR, numbered by FR. `K` = baseline failure. `N` = never-executed test. `A` = constitutional. `W` = production-path proof. `Y` = prohibition / mutation. `M` = reporting. `G` = arbitration gate. |
| `FR` | **Every row cites at least one FR.** A non-FR gate row cites the *nearest governing* FR. `—` is permitted by the schema and is used by no row, because `RI-04c-ROW-FR` treats a row with no FR as a row that maps no requirement, which is the defect this file exists to close. |
| `Requirement` | One line, in the FR's own vocabulary, so a mis-citation is visible. |
| `Method` | `T` / `I` / `M` / `B` / `P` — see the key below. |
| `Task` | **At least one task id that exists in `tasks.md`, or the literal `UNASSIGNED`.** |
| `State` | `☐` until proven. |

| Code | Method | What a tick requires |
|---|---|---|
| `T` | automated test | a named test exists, runs, and fails when the requirement is violated |
| `I` | inspection of the actual file | a reader can re-run the inspection and get the same answer |
| `M` | mutation must fail | a named mutation breaks the requirement and a named test fails for the **right reason** |
| `B` | baseline comparison | a before/after run against the recorded baseline in §0 |
| `P` | production-path proof | exercised on the **live** path; a test harness does not satisfy it |

**Why this file was rebuilt.** As written it had no FR column, cited `FR-081` and `FR-082` in its
whole body, and carried five letter-suffixed task ids that exist nowhere — one of which was the
sole verification for the entire mutation apparatus, and a second of which was carrying the
graph-projection invariant. It could not detect the failure it exists to prevent. `T104` owns the
rebuild; this file is its output.

**Task-numbering note.** Task ids are `^T\d{3}$` with no letter suffix, and `tasks.md` defines
`T101`…`T194`. That grammar rule is what makes the letter-suffixed phantom class unrepresentable,
so every `Task` cell here resolves. A `T`-token absent from `tasks.md` is a phantom and a row
gated on it is a gate on nothing.

**FR-namespace note.** `spec.md` defines 153 FRs, in the `001`–`100` range plus seven allocated
bands. Two bands are void or reserved and are never cited here: a number in a void band is the
historical phantom class of defect, a citation that resolves to nothing. Four of the 153 are tombstones
(sub-section 2.15). The
governing count for the vocabulary is four separate numbers, never one: **31** `core:*` entity
types, **13** `value:*` value types, **7** §8 extraction families, roughly **4** new instrument
modules.

---

## 0. Baseline — measured, not inherited

Source: `phase0-results.md` §1, fresh runs at HEAD `0056665`, frozen by `T101` into
`repair/baseline-021.md`. This is what a later run is compared **against**, so it is recorded here
rather than in a report nobody diffs.

### 0.1 Suite totals

| Suite | Result | Note |
|---|---|---|
| `apps/shared` | 14 failed, 571 passed, 8 skipped | 593 collected |
| `apps/control-plane` | 2 failed, 356 passed, 9 skipped | both `test_donor_api` |
| `apps/interpretation` | 185 passed | — |
| `apps/projection` | 189 passed, 1 skipped | 190 collected; the skip is a whole module, see `N4` |
| `apps/admission` | 96 passed | — |
| `apps/acquisition` | 126 passed, 10 skipped | all skips `minio unavailable` |
| `apps/science` | 164 passed | — |
| `apps/zero` | 121 passed | — |
| `apps/feedback` | 18 passed, 2 skipped | skips `postgres unavailable` |
| `apps/bulk-ingestion` | 10 passed, 2 skipped | skips `minio unavailable` |
| `bench` | 23 passed | — |

### 0.2 The 16 failing tests, individually accounted for

Classification is mandatory: `baseline` (pre-existing — do not fix, do not hide, do not count as
progress), `new` (a regression this feature introduced — a gate failure), `fixed` (a known failure
this feature legitimately cleared), `flaky` (non-deterministic; must be shown flaky twice).

| # | FR | Requirement (one line) | Method | Task | State |
|---|---|---|---|---|---|
| K1 | FR-081 | baseline — `apps/control-plane` `test_donor_api.py::test_entity_timeline_carries_observed_at`: the timeline `observed_at` differs from a hard-coded literal; it fails in isolation while the sibling `test_entity_view_projects_identity_invariant` passes on the same literal | B | T101, T190 | ☐ |
| K2 | FR-081 | baseline — `apps/control-plane` `test_donor_api.py::test_entity_can_be_created_as_dynamic_invariant`: the endpoint now returns `202 Accepted`, the test still asserts `200` | B | T101, T190 | ☐ |
| K3 | FR-081 | environment — `apps/shared` `test_kafka_list_topics`: Docker is down, so the test fails rather than skips | B | T101, T190 | ☐ |
| K4 | FR-081 | environment — `apps/shared` `test_redpanda_list_topics`: Docker is down | B | T101, T190 | ☐ |
| K5 | FR-081 | environment — `apps/shared` `test_minio_put_get_delete_content_addressed_probe`: Docker is down | B | T101, T190 | ☐ |
| K6 | FR-081 | baseline — `apps/shared` `test_evidence_context.py` genuine code failure 1 of 8 | B | T101, T190 | ☐ |
| K7 | FR-081 | baseline — `apps/shared` `test_evidence_context.py` genuine code failure 2 of 8 | B | T101, T190 | ☐ |
| K8 | FR-081 | baseline — `apps/shared` `test_evidence_context.py` genuine code failure 3 of 8 | B | T101, T190 | ☐ |
| K9 | FR-081 | baseline — `apps/shared` `test_evidence_context.py` genuine code failure 4 of 8 | B | T101, T190 | ☐ |
| K10 | FR-081 | baseline — `apps/shared` `test_evidence_context.py` genuine code failure 5 of 8 | B | T101, T190 | ☐ |
| K11 | FR-081 | baseline — `apps/shared` `test_evidence_context.py` genuine code failure 6 of 8 | B | T101, T190 | ☐ |
| K12 | FR-081 | baseline — `apps/shared` `test_evidence_context.py` genuine code failure 7 of 8 | B | T101, T190 | ☐ |
| K13 | FR-081 | baseline — `apps/shared` `test_evidence_context.py` genuine code failure 8 of 8 | B | T101, T190 | ☐ |
| K14 | FR-081 | baseline — `apps/shared` `test_evidence_lineage.py::test_t062_the_api_path_is_reachable_in_both_directions`; this is the same defect as row `Y16`, so this feature may legitimately move it from `baseline` to `fixed` and must say so | B | T101, T179, T190 | ☐ |
| K15 | FR-081 | baseline — `apps/shared` `websearch/test_websearch.py` genuine code failure 1 of 2 | B | T101, T190 | ☐ |
| K16 | FR-081 | baseline — `apps/shared` `websearch/test_websearch.py` genuine code failure 2 of 2 | B | T101, T190 | ☐ |

### 0.3 The 22 tests that never executed

A green run proves a fraction of the suite, not the suite. These are tracked, never reported as
passes: 14 that self-skip and report a skip, and 8 that report nothing at all.

| # | FR | Requirement (one line) | Method | Task | State |
|---|---|---|---|---|---|
| N1 | FR-081 | 10 `apps/acquisition` tests never executed — MinIO is absent, so they self-skip | I | T101, T190 | ☐ |
| N2 | FR-062, FR-081 | 2 `apps/feedback` tests never executed — PostgreSQL is absent, so the live round trip is `verified only offline` rather than passed; that suite is not one of the six the requirement names, unlike `apps/shared` and `apps/control-plane` | I | T101, T190 | ☐ |
| N3 | FR-081 | 2 `apps/bulk-ingestion` tests never executed — MinIO is absent; that suite is not one of the six the requirement names — `apps/projection`, `apps/acquisition`, `apps/interpretation`, `apps/admission`, `apps/control-plane`, `apps/shared` — so its skips are tracked here instead | I | T101, T190 | ☐ |
| N4 | FR-062, FR-081 | the whole of `test_tantivy_backend.py` never executed — a module-level `importorskip` takes the file down, so its assertions about tenant isolation, idempotent writes and provenance enforcement never run, and the ORM/migration parity and schema-invariant tests that would have covered them never run either; the suite reports it as one skip, and `apps/projection` is one of the six the requirement names | I | T101, T173, T182 | ☐ |
| N5 | FR-062, FR-081 | 7 `apps/control-plane` tests need a live PostgreSQL/dev stack and are blocked | I | T101, T190 | ☐ |
| N6 | FR-081 | re-baseline condition: if Docker is ever started the `apps/shared` baseline moves to roughly 11 failed, 571 passed, 3 skipped, so every comparison in §0.1 and `K1`–`K16` must be recomputed before it is trusted | B | T101, T190 | ☐ |

### 0.4 What the baseline licenses

- Every DB-dependent verification in this feature is `verified only offline`. Only the *write*
  obligation is unconditional; only the live round trip is conditional.
- `11 failed, 571 passed, 3 skipped` is a **different** baseline, not a better one. Re-baseline
  before trusting any comparison against it.
- `K3`–`K5` are environment failures, not code defects, and are not progress.

---

## 1. Constitutional invariants

`INV-001`…`INV-005` are the invariants no implementation wave may weaken.

| # | FR | Requirement (one line) | Method | Task | State |
|---|---|---|---|---|---|
| A1 | FR-007, FR-098 | the named types stay distinct types; `CandidateStatus` never becomes a `rank()`, and the partition stays `CAND-` / `CNDR-` with no fourth epistemic level (`INV-001`, `SC-025`) | T | T107, T134 | ☐ |
| A2 | FR-034, FR-074, FR-137 | the type vocabulary is an interpretation instrument — naming, hierarchy, aliases, blocking, role hints, mapping surface, validation vocabulary — and is never a gate or a completeness condition; the ontology pack's relation list is deleted, not merely unused (`INV-002`, `SC-024`) | T | T111, T152 | ☐ |
| A3 | FR-038, FR-111 | no producer drops an observation because the semantic layer does not understand it; an ontology miss yields `UNKNOWN`, never rejection (`INV-003`) | M | T117, T184 | ☐ |
| A4 | FR-058 — tombstone, merged into `INV-004` | a `GraphEdge` or `HyperEdge` exists only after an admitted `RelationClaim`, enforced at the type level with no overload; see the deleted-ids table in `repair/A6-fr-triage.md` (`SC-031`) | T | T174, T184 | ☐ |
| A5 | FR-068, FR-169 | evidence lineage and derivation lineage stay separate over **two distinct hop vocabularies**, and a `SIGNAL` hop is traversable in both directions; a candidate is derivation, never evidence (`INV-005`, `SC-013`) | T | T179 | ☐ |
| A6 | FR-073, FR-085, FR-089 | determinism: ids are re-derived and never trusted, and depend on no producer order, dict iteration order, clock read or random tie-break (`SC-010`, `SC-035`) | T | T105, T129, T186 | ☐ |
| A7 | FR-019, FR-020 | no `ENT-`/`RES-` literal in producer code, and no `TYPE_CHECKING` outside a type position | I | T152 | ☐ |
| A8 | FR-068, FR-180 | the graph is a projection and is rebuildable from the stores: a stored `RelationClaim`, its `Candidate`, its `Signals`, their observations and the source are all recovered from an edge and back, which is what makes the prohibition-coverage sweep over `repair/A6-fr-triage.md` and `spec.md` checkable rather than aspirational (`SC-034`) | T | T180 | ☐ |
| A9 | FR-069, FR-084 | the graph shows the world, not the extraction: an unknown predicate stays unknown and the graph does not invent a type | T | T175, T194 | ☐ |
| A10 | FR-062, FR-155, FR-171 | tenancy: no cross-tenant write and no cross-tenant read, every ORM query carries a `tenant_id` predicate, `021` adds no new table and drops no `relation_candidate` / `relation_signal` / `relation_claim` column, and the live round trip stays `verified only offline`; an `admit_claims` decision and a `project` write are recorded in the durable `AuditLog` | T | T165, T169 | ☐ |
| A11 | FR-061, FR-096 | `capture_with_observations()` is reachable from the normal acquisition path, and is not merely a helper no production path calls | T | T171 | ☐ |
| A12 | FR-059, FR-169 | durable store seams exist for the three relation types with the named operations, and none of the three is left without a writer — today no INSERT exists for any of them | I | T169, T170 | ☐ |

---

## 2. Normative map — one row per FR in `spec.md`

153 rows, one per FR definition, grouped by subject. Sub-section 2.15 holds the four tombstones.

### 2.1 Identity, signature and derivation

| # | FR | Requirement (one line) | Method | Task | State |
|---|---|---|---|---|---|
| R001 | FR-001 | `logical_candidate_id` depends on no `relation_surface`, producer, capture, confidence, status or observation timestamp; the §94 mutation fails (`SC-035`, `SC-043`) | M | T133, T184 | ☐ |
| R002 | FR-002 | `logical_candidate_id` is derived from tenant, the **canonically ordered** participant configuration, arity, role shape, direction, polarity and the signature, and the identity function's dead `valid_from`/`valid_to` parameters are removed or made load-bearing | T | T109, T131 | ☐ |
| R003 | FR-003 | a deterministic `PredicateSignature` carries its named field set and its exclusions, with one named test per rule, is never a `RelationRef`, and is content-keyed and stored in its own columns rather than as a digest (`SC-042`) | T | T130 | ☐ |
| R004 | FR-004 | normalisation is deterministic and does not unify distinct relations; a synonym or equivalence table never enters identity material | T | T130 | ☐ |
| R005 | FR-005 | a surface-variant pair reaches the same signature **through the derivation itself**, never through a hard-coded fixture | T | T133 | ☐ |
| R006 | FR-006 | `signal_id` stays producer-specific, and independence is computed over `producer_ref` and `independence_family` | T | T152 | ☐ |
| R007 | FR-007 | the candidate partition stays two-level — `CAND-` answers which configuration, `CNDR-` which reading — and no fourth epistemic level appears | T | T134 | ☐ |
| R085 | FR-085 | `signal_refs` is canonicalised on construction, so `candidate_id` cannot depend on caller iteration order and no call-site sort is needed | T | T105 | ☐ |
| R086 | FR-086 | `RelationCandidate.to_dict()`/`from_dict()` round-trips every declared field losslessly, and the test asserts the field list rather than a summary string | T | T106 | ☐ |
| R089 | FR-089 | `RelationSignal._material()` carries declared arity mode and role bindings so arity alone changes the `signal_id`; `producer_ref` is retained | T | T129 | ☐ |
| R098 | FR-098 | `verify_candidate_material_partition()` is called and made correct, or deleted; `CANDIDATE_LOGICAL_MATERIAL_FIELDS` stops declaring `relation_type` where the code emits `relation_surface` | T | T107 | ☐ |
| R099 | FR-099 | `RelationClaim` re-derives and checks its own carried `relation_id`, so a forged id is refused on a claim and not only on a candidate | T | T108 | ☐ |
| R174 | FR-174 | `PredicateSignature` is a frozen value object with exactly its declared field set and its declared exclusions, and carries its own `content_key()` | T | T130 | ☐ |
| R175 | FR-175 | `normalize_voice(predicate, syntactic_structure, dependency_structure) -> CanonicalArgumentAssignment` is the only function that assigns voice, and it is deterministic and specified | T | T130, T131, T138 | ☐ |
| R176 | FR-176 | `canonical_participant_ordering(signature, commutative_slots, participants)` is a specified deterministic algorithm running **inside** the identity function, never at a call site | T | T131, T183 | ☐ |
| R177 | FR-177 | `logical_candidate_id` equals `"CAND-" + digest128(canonical_material(material))` over exactly its declared material, and the red identity-property test is written red and turned green by a named task | T | T110, T133, T183 | ☐ |
| R178 | FR-178 | changing the mapping vocabulary changes no historical `logical_candidate_id`; no mapping artefact, `RelationRef`, `resolution_state`, `alternative_refs`, `mapping_evidence_refs`, `match_type`, `confidence`, `mapping_version` or `provenance` participates in identity material | T | T131, T133 | ☐ |

### 2.2 Relation signal

| # | FR | Requirement (one line) | Method | Task | State |
|---|---|---|---|---|---|
| R008 | FR-008 | `participants: tuple[RelationParticipant, ...]` is the canonical participant representation supporting 2..N, with the two hard-coded scalars only as derived accessors and never a second source of truth | T | T123, T127 | ☐ |
| R009 | FR-009 | `RelationParticipant` carries `mention_ref`, `slot`, `role_hypothesis`, `ordinal` and `confidence` | T | T123 | ☐ |
| R010 | FR-010 | every field the signal contract names is present and typed; zero load-bearing dimensions are JSONB, and `extra` never carries participants or arity (`SC-039`) | T | T123, T129 | ☐ |
| R011 | FR-011 | `SignalKind` names an observation channel only, and `TEMPORAL` **is** present as a channel while the temporal facts live in `SourceTemporalObservation` (`SC-040`) | T | T125, T128 | ☐ |
| R012 | FR-012 | `NEGATION`, `QUANTITY`, `COREFERENCE` and `UNCERTAINTY` are members of a separate `SignalAspect`, with exactly the stated field mapping and no other | T | T125, T128 | ☐ |
| R013 | FR-013 | a `CO_OCCURRENCE` with an empty `relation_surface` and a `None` `predicate_signature` is constructible, persistable and assemblable, and `021` drops the two `*_asserts_something` CHECKs (`SC-012`) | M | T129, T165 | ☐ |
| R014 | FR-014 | `observational_basis` is a required, typed field drawn from the closed nine-member `SignalBasis` enumeration, and a signal with no basis fails construction | T | T126 | ☐ |
| R015 | FR-015 | `polarity` is explicit, required, durable and two-valued; a denial keeps its surface and signature and yields no positive candidate and no edge (`SC-041`) | T | T124, T166 | ☐ |

### 2.3 Mention binding

| # | FR | Requirement (one line) | Method | Task | State |
|---|---|---|---|---|---|
| R016 | FR-016 | no producer invents a mention identity from text after the mention stage, and every `participant.mention_ref` resolves in the index — asserted by iterating real producer output, not by inspection (`SC-004`) | T | T119 | ☐ |
| R017 | FR-017 | a structural producer observing a value that is not yet a mention records the structural raw slot and a typed deferred reference, and never a synthesised id | T | T119 | ☐ |
| R018 | FR-018 | `MentionOccurrenceIndex` looks up on the full tuple including `capture`, so two captures of one segment cannot collide, and it is the **sole minter** of mention identifiers | T | T118 | ☐ |
| R019 | FR-019 | mention binding stays distinct from entity resolution, and no `ENT-` or `RES-` literal appears in producer code | I | T152 | ☐ |
| R020 | FR-020 | no producer module **imports or constructs** `GraphEdge`, `HyperEdge`, `GraphStore`, `RelationClaim`, the `admission` package or the `projection` package; `TYPE_CHECKING` is the only permitted reference (`SC-011`) | M | T152, T184 | ☐ |

### 2.4 Predicate and claim boundary

| # | FR | Requirement (one line) | Method | Task | State |
|---|---|---|---|---|---|
| R021 | FR-021 | `PredicateHypothesis` preserves its declared field set and its four states, with no `UNKNOWN_RELATION` and no fabricated `RelationRef` | T | T132 | ☐ |
| R022 | FR-022 | a signal mapping to a known operator becomes typed only through explicit interpretation under a regime, never by string proximity | T | T132 | ☐ |
| R023 | FR-023 | a predicate with no operator survives as a candidate with `predicate_state=UNKNOWN` and the observable questions stay answerable; the §98 `return ()` path is gone | M | T135, T184 | ☐ |
| R024 | FR-024 | `RelationClaimMaterial` is constructible only when the predicate, the participants and the role structure are resolved; an unknown predicate yields a candidate, never a claim, with every evidence item still retrievable (`SC-002`) | T | T135 | ☐ |

### 2.5 Assembly and the mapping boundary

| # | FR | Requirement (one line) | Method | Task | State |
|---|---|---|---|---|---|
| R025 | FR-025 | assembly groups by structural participant configuration and preserves direction, polarity, signature, every signal ref and every alternative; it detects conflicts, resolves nothing and admits nothing (`SC-005`) | T | T136, T155, T157 | ☐ |
| R026 | FR-026 | no majority-vote semantic adjudication, and no `_arity_of()`-style resolution path exists (`SC-006`) | M | T153, T184 | ☐ |
| R027 | FR-027 | distinct predicates over the same endpoints stay distinct hypotheses; equal endpoints never merge them (`SC-007`) | T | T155 | ☐ |
| R028 | FR-028 | two signals whose signatures agree but whose readings differ yield **one** logical hypothesis with the mapped states, neither interpretation overwritten (`SC-029`) | T | T154 | ☐ |
| R090 | FR-090 | a structural reading conflict yields `assembly_state = CandidateAssemblyState.CONFLICTING` with both readings preserved — never `CandidateStatus.CONTRADICTED` | T | T153, T154 | ☐ |
| R091 | FR-091 | `RelationalReading.to_candidate()` is removed, or reduced to a call into the assembler, so signal-to-candidate has exactly one answer in the code and not merely one documented answer | I | T156 | ☐ |
| R130 | FR-130 | `PredicateMappingCandidate` is a frozen value object carrying its declared fields, and it is the only mapping carrier — no second mapping model | T | T154 | ☐ |
| R131 | FR-131 | no mapping field, `RelationRef`, `resolution_state`, `alternative_refs`, `mapping_evidence_refs`, `match_type`, `confidence`, `mapping_version` or `provenance` enters `logical_material`; a digest may identify mapping data but is never the only copy | T | T154, T168 | ☐ |
| R132 | FR-132 | two signals whose `PredicateSignature`s agree but whose `PredicateMappingCandidate`s name different `target_relation_ref`s yield **one** candidate carrying one `PredicateHypothesis`, with the disagreement explicit | T | T154 | ☐ |
| R133 | FR-133 | a hypothesis whose competing readings came from **disagreeing evidence** rather than from one evidence set read by two regimes carries `resolution_state=CONFLICTING`, stated explicitly by the assembler | T | T154, T168 | ☐ |

### 2.6 Types, the vocabulary and the §8 instruments

| # | FR | Requirement (one line) | Method | Task | State |
|---|---|---|---|---|---|
| R029 | FR-029 | a versioned foundational type pack exposes the eight per-type fields and encodes no relation semantics, so a pack match is never truth | T | T111 | ☐ |
| R030 | FR-030 | the pack covers exactly **31** foundational entity (`core:*`) types, and the shipped manifest matches the registered artefact byte for byte | T | T111 | ☐ |
| R031 | FR-031 | **13** value (`value:*`) types are conceptually separate from entity classes, and a consumer never receives a value ref where an entity was asked for (`SC-017`, `SC-018`) | T | T111 | ☐ |
| R032 | FR-032 | `TypeHypothesis` is a first-class type: an importable frozen dataclass with exactly its declared thirteen fields, and a `hypothesis_state` whose value set is exactly the six the requirement names (`SC-019`) | T | T116 | ☐ |
| R033 | FR-033 | a mention holds several competing `TypeHypothesis` values with distinct confidence, evidence and state, and none is silently selected; `"Apple"` retains at least three (`SC-021`) | T | T116 | ☐ |
| R034 | FR-034 | the type space is extensible by hierarchy, and `broader`/`narrower` serve expansion, blocking, ranking and validation but **never** gate anything | T | T111 | ☐ |
| R035 | FR-035 | an external vocabulary statement produces a `TypeSignal` and never an immediate `TypeAssertion` (`SC-023`) | T | T112, T122 | ☐ |
| R036 | FR-036 | a type mapping retains its provenance fields, is content-addressed, citable and tenant-scoped at the write, and supersedes rather than replaces; a hypothesis with alternatives and mapping evidence round-trips through its store with every part recoverable, not merely a matching digest (`SC-008`) | T | T113 | ☐ |
| R037 | FR-037 | the type pipeline runs in order, retains all prior states, and a later `INFERRED` is a **new revision** rather than a destructive replacement (`SC-020`, `SC-027`) | T | T117, T122 | ☐ |
| R038 | FR-038 | an ontology miss means `unknown type`, never a rejected mention; the §97 `continue` guard is gone (`SC-022`) | M | T117, T184 | ☐ |
| R039 | FR-039 | type resolution consumes the already-available context — title, section heading, DOM parent, table heading, neighbour mentions, URL and domain, metadata, language — and represents competing hypotheses with evidence | T | T120 | ☐ |
| R134 | FR-134 | a structured or external-vocabulary statement produces a `TypeSignal` carrying `source_vocab`, `surface` and `mapping_candidates` plus `mention_ref`, `structural_path`, `observation_refs`, `evidence_refs` and `producer_ref`; `source_vocab` is an external reference **or `null`**, and no synthetic vocabulary is introduced to avoid the null | T | T112 | ☐ |
| R135 | FR-135 | `TypeMapping` **is** the existing `semantic.mappings.SemanticMapping` — a documented name, not a parallel dataclass | T | T113 | ☐ |
| R136 | FR-136 | the initial type mapping set is exactly the seven the brief's §64 names, each an explicit record, and a non-equivalence match is recordable as such | T | T113 | ☐ |
| R137 | FR-137 | the ontology pack declares, publishes and checks no relation list: `relations`, `allows_relation()` and the `relations` key in `to_dict()` are deleted, while `allows_type()` remains and remains advisory | I | T111 | ☐ |
| R140 | FR-140 | the deterministic extraction layer is completed by **adapting** the existing extractors and registry — zero new extraction frameworks, and `ExtractorRegistry` remains the single registration point | I | T114 | ☐ |
| R141 | FR-141 | the person instrument covers Latin, Cyrillic, initials, multi-token, titles, contextual cues, aliases, transliteration, Unicode normalisation and surname-first patterns, where a name-shaped string never implies person | T | T114 | ☐ |
| R142 | FR-142 | the organization instrument recognises legal forms, corporate suffixes, institutional names, brands, agencies, universities, government bodies, media, banks, companies and NGOs, always as a hypothesis and never as `entity = organization` | T | T114 | ☐ |
| R143 | FR-143 | URL, domain, WebSite and WebPage extraction is deterministic and keeps the four as four distinct types: a URL string is a value, a WebPage a resource, a WebSite a higher-level resource, a domain a namespace | T | T114 | ☐ |
| R144 | FR-144 | a table-driven, versioned profile-URL and handle instrument recognises the named host patterns, and account identity is never inferred from a display name | T | T114 | ☐ |
| R145 | FR-145 | indicator extraction **extends** the existing instruments to emit value-type hypotheses for IP, hash, CVE, crypto address, file path and identifier, and a value with no domain type is retained | T | T114 | ☐ |
| R146 | FR-146 | document instrumentation detects URLs pointing to files, filenames, document ids, report-like structures, PDFs where source metadata provides them, citations and document title structure | T | T114 | ☐ |
| R147 | FR-147 | a recognised event word produces a `TypeSignal` recording the lexical match; an event mention is not a relation and never becomes a claim | T | T114 | ☐ |
| R148 | FR-148 | `TypeHypothesis` is exactly **one** interpretation candidate and never a container of candidates — a frozen dataclass with the declared thirteen fields | T | T116 | ☐ |
| R149 | FR-149 | the **set** of competing hypotheses is owned by the mention, never by a hypothesis | T | T116 | ☐ |
| R179 | FR-179 | the seven §8 extraction families are all covered by a producer that **adapts** the existing extractors, and the criterion is renamed: the counts are 31 `core:*` types, 13 `value:*` types, 7 extraction families and roughly 4 new instrument modules — "seven classes" is a misreading that would harden into a mandate covering `core:Person`, `core:Organization`, `core:OnlineAccount`, `core:WebSite`, `core:WebPage` and a `value:URL` (`SC-026`) | I | T114, T182 | ☐ |

### 2.7 Producers

| # | FR | Requirement (one line) | Method | Task | State |
|---|---|---|---|---|---|
| R040 | FR-040 | every channel the producer requirement names is implemented or carries an explicit `UNSUPPORTED` marker with a reason, and all of them write to the identical downstream model (`SC-040`) | T | T151 | ☐ |
| R041 | FR-041 | the lexical producer remains one producer and is upgraded to emit surface, normalised predicate, signature, participant roles, direction, declared arity and trigger/support evidence; `RELATION_CUES` is not the global vocabulary | T | T139 | ☐ |
| R042 | FR-042 | a syntactic producer covers the named realisations, emits frames that are pairwise distinct, and emits no operator the mapping layer did not state — never `works_for` or `owner_of` by pattern match | T | T138 | ☐ |
| R043 | FR-043 | parser capability is explicit and pinned, no LLM appears in the constitutional extraction path, and a missing parser means no syntactic signals rather than batch failure | T | T103, T137 | ☐ |
| R044 | FR-044 | a structural producer represents `structural_path` and never flattens structure into a predicate | T | T140 | ☐ |
| R045 | FR-045 | the link producer preserves its refs and asserts only "A links to B", and one anchor never yields two signals that count as independent corroboration | T | T141 | ☐ |
| R046 | FR-046 | the reference and citation producer covers the named forms and never emits `cites` | T | T142 | ☐ |
| R047 | FR-047 | the table producer preserves its refs, treats a row as structural evidence for an n-ary configuration, and refuses or skips a malformed table by explicit rule rather than a positional guess | T | T143 | ☐ |
| R048 | FR-048 | the list producer handles term and item structure and produces structure, role hints and participant slots without creating a semantic relation | T | T144 | ☐ |
| R049 | FR-049 | the metadata producer covers the named fields plus unrecognised metadata, which must survive; `author` is never mapped to `authored_by` automatically | T | T145 | ☐ |
| R050 | FR-050 | the attribute producer represents `Key: value`, never turns a value into an entity, and distinguishes the three arrow kinds | T | T146 | ☐ |
| R051 | FR-051 | the temporal producer attaches the expression as evidence with surface, normalised interval, precision and span, emits `SignalKind.TEMPORAL` as the **channel**, and never promotes an inferred interval to world truth | T | T147 | ☐ |
| R052 | FR-052 | the event producer supports n-ary structures and never reduces `"John sold Acme to Microsoft in 2020"` to two binary edges at substrate level (`SC-003`) | T | T148 | ☐ |
| R053 | FR-053 | the co-occurrence producer reports adjacency in a named window and never produces `related_to`; proximity with no predicate words stays representable | T | T149 | ☐ |
| R054 | FR-054 | the semantic producer creates interpretation candidates only, and an ontology match is never automatic truth | T | T150 | ☐ |
| R093 | FR-093 | `pairs_considered` reports a real count or a stated `0` with a reason; the fabricated divisors and the dead `MAX_PAIRS_CONSIDERED` are live or deleted | T | T139, T143 | ☐ |
| R094 | FR-094 | no field name, property name, document placeholder or truncated string is a participant; the `document:current` fallback and the 64-char truncation are gone in favour of a full content address | I | T145 | ☐ |
| R095 | FR-095 | structural data loss is reported, not silent: the row `zip` is strict, a width-mismatched row emits a note or a signal, and a heuristic header choice is not published as an exact precision string | T | T144 | ☐ |

### 2.8 Lifecycle

| # | FR | Requirement (one line) | Method | Task | State |
|---|---|---|---|---|---|
| R055 | FR-055 | the executable path's precedence constraints hold as a **partial** order with each stage exposing its product, and the contested `REGIME` position is recorded as an open decision answered by an ADR rather than asserted | T | T158, T164 | ☐ |
| R056 | FR-056 | the claim lifecycle is `Candidate → ClaimMaterial → Validation → Admission → RelationClaim`; `RelationClaim → Validation` is not the primary path and there is no fake `SUPPORTED` gate (`SC-030`) | T | T161 | ☐ |
| R057 | FR-057 | `ExecutionResult` exposes `material` as a real stage product; a stage that is materially semantic but silently validates or admits is not acceptable | T | T159 | ☐ |
| R092 | FR-092 | the lifecycle is split so materialisation, validation, admission and projection are separately observable; the `ValidationReport` that gated admission is retained and surfaced; the post-admission re-validation is deleted with no "or justified" escape; the admission decision actually gates the store write; production writes are not doubled | T | T160, T161, T162 | ☐ |

### 2.9 Production wiring and the constitutional workflow

| # | FR | Requirement (one line) | Method | Task | State |
|---|---|---|---|---|---|
| R100 | FR-100 | the semantic path is wired into the live production path, not only into the corpus harness: `ExecutionRequest.producers` is populated and a counter proves `run_producer` iterates more than zero times | P | T163, T188, T189 | ☐ |
| R161 | FR-161 | `Investigation` is the only production entry point for the extraction and projection substrate; no production module outside the investigation workflow calls the extraction path | P | T188 | ☐ |
| R162 | FR-162 | the direct `user → extractor → graph` path is prohibited as a *class of defect*: an extraction request that names no `investigation_id` is refused at the boundary | P | T188 | ☐ |
| R163 | FR-163 | `InvestigationWorkflow` is registered on the Temporal worker and on its task queue together with every activity it calls; an unregistered workflow is not reachable and not acceptable | P | T188 | ☐ |
| R164 | FR-164 | the workflow's stages are, in order: `acquire`, `bind_mentions`, `extract_type_signals`, `extract_relation_signals`, `assemble_candidates`, `validate_candidates`, `admit_claims`, `project` | P | T188 | ☐ |
| R165 | FR-165 | every consumer in the investigation path is idempotent on a key drawn from the event, task, observation or projection offset, and the key is named in the consumer's signature | T | T163, T188 | ☐ |
| R166 | FR-166 | the investigation lifecycle runs within a tenant-scoped policy, budget and freshness gate before `acquire` performs any network call | T | T188 | ☐ |
| R167 | FR-167 | a change to a decision on the Governance list ships an ADR **before** the change merges | I | T115, T164, T193 | ☐ |
| R168 | FR-168 | constitutional compliance is verified automatically on every change; absent CI, the completion report carries a dated, named attestation of who ran the gate, on which commit | I | T104, T190, T192 | ☐ |
| R169 | FR-169 | a `SIGNAL` hop kind exists and is traversable in **both** directions, and a `candidate_id` is reachable from any projected edge without `CANDIDATE` becoming a link in the evidence backward chain | T | T179 | ☐ |
| R170 | FR-170 | a rejected candidate is not deleted by any production path, **including** the re-evaluation path: the outcome is recorded **on** the record, and `purge` may not remove it | I | T160 | ☐ |
| R171 | FR-171 | `AuditLog` writes to the durable table, not to an in-memory list alone, and both an admission decision and a projection write are recorded there | T | T169 | ☐ |
| R172 | FR-172 | `workflows/investigation.py` is deleted and its lifecycle state machine relocated, so exactly one investigation lifecycle exists | I | T188 | ☐ |
| R173 | FR-173 | every constitutional citation in code, tests, migrations and feature artefacts names the correct numeral; tenancy is VII, not IV, and the unnumbered determinism principle is cited correctly | I | T104 | ☐ |

### 2.10 Persistence and migration `021`

| # | FR | Requirement (one line) | Method | Task | State |
|---|---|---|---|---|---|
| R059 | FR-059 | durable store seams exist for the three relation types with the named operations, each with a working round trip (`SC-032`) | T | T169, T170 | ☐ |
| R060 | FR-060 | every store reconstructs the exact domain object; a round trip preserves ids, alternatives, signals, provenance, type hypotheses, signature, temporal evidence, tenant, context and regime, and a digest is never the only copy | T | T168, T172 | ☐ |
| R061 | FR-061 | the **normal** acquisition path persists `SourceTemporalObservation`; the helper no production path calls is not the only route, EDGAR stays day-precision, and publication time never reaches `Capture.fetched_at` (`SC-009`) | T | T171 | ☐ |
| R062 | FR-062 | `021` is forward-only, `020` is never edited, parity and schema-invariant tests are unconditional, and the live round trip stays conditional and is reported `verified only offline` when PostgreSQL is unavailable | T | T165, T173 | ☐ |
| R087 | FR-087 | `predicate_signature` is persisted in its own columns on both tables, wholly present or wholly absent, with `observational_basis` a real column — so candidate identity no longer depends on a digest | T | T167 | ☐ |
| R088 | FR-088 | `relation_candidate` gains `signal_refs`, `direction`, `polarity` and `confidence`; `relation_claim` gains `candidate_id`; the store writes and reads all of them | T | T166 | ☐ |
| R096 | FR-096 | `SourceTemporalObservation` is reachable from the normal acquisition path and has a repository with a writer and a reader | T | T171 | ☐ |
| R097 | FR-097 | migration `021` is added on top of the forward-only `020`, `020` is unedited, and every column the identity and signature requirements need is added — including typed `participants JSONB NOT NULL` on both tables, not `extra` and not deferred | I | T102, T165 | ☐ |
| R150 | FR-150 | `021` drops `ck_relation_signal_asserts_something` and `ck_relation_candidate_asserts_something` and replaces both with a constraint whose predicate is the honest one | I | T165 | ☐ |
| R151 | FR-151 | `021` adds `relation_signal.observational_basis` and the domain type `SignalBasis` with exactly the nine members the signal requirement names | I | T126, T166, T167 | ☐ |
| R152 | FR-152 | `ck_relation_signal_kind` is dropped and recreated over a whitelist of exactly the fifteen kinds the requirement names | I | T165 | ☐ |
| R153 | FR-153 | a `ValidationResult` has a durable home, and `record_validation` / `non_valid` stop raising `NotImplementedError` | I | T170 | ☐ |
| R154 | FR-154 | `021` adds the named indexes, including the candidate and signal object indexes and the claim candidate index | I | T165, T166 | ☐ |
| R155 | FR-155 | `021` is tenant-scoped, drops no historical semantic observation, and emits no `UPDATE`, `DELETE`, `TRUNCATE`, `drop_table` or `drop_column`; its only drops are constraints and indexes | I | T165 | ☐ |
| R156 | FR-156 | `validation_findings` gains `candidate_id` and its index, so a finding about an unadmitted candidate has somewhere to attach | I | T166 | ☐ |
| R157 | FR-157 | `021.downgrade()` raises `NotImplementedError` **before emitting any operation**, and drops nothing — a partial downgrade leaves a database matching no revision | T | T102, T165 | ☐ |
| R158 | FR-158 | ORM/migration parity, schema-invariant and round-trip tests exist for `021` and compare CHECK constraints **by text and not only by name** | T | T173 | ☐ |

### 2.11 Projection

| # | FR | Requirement (one line) | Method | Task | State |
|---|---|---|---|---|---|
| R063 | FR-063 | a `DIRECTED` claim projects with direction preserved and never canonicalises endpoints by `min`/`max` (`SC-014`) | T | T175 | ☐ |
| R064 | FR-064 | an `UNDIRECTED` projection canonicalises endpoint ordering only when the admitted relation contract declares symmetry | T | T175 | ☐ |
| R065 | FR-065 | a `NARY` claim projects to `HyperEdge`; flattening needs an explicit policy, the original hyperrelation stays available, and each derived edge names its source claim | T | T176 | ☐ |
| R066 | FR-066 | an entity-to-value relation is distinguishable from an entity-to-entity relation in both the claim and the projection (`SC-033`) | T | T177 | ☐ |
| R067 | FR-067 | an explicit hypothesis and evidence view serves unadmitted relations, `GraphEdge` is not reused for it, and the view is reachable | I | T178 | ☐ |
| R068 | FR-068 | from every edge the platform navigates to claim, candidate, signals, observations and source, and from a source back to every edge it fed, over **two** hop vocabularies | T | T179, T180 | ☐ |
| R069 | FR-069 | projection preserves the named provenance facts, and that metadata never enters edge identity: two claims differing only in confidence produce one edge id | T | T175 | ☐ |

### 2.12 Boundedness and determinism

| # | FR | Requirement (one line) | Method | Task | State |
|---|---|---|---|---|---|
| R071 | FR-071 | candidate generation is generate-wide-within-bounded-neighbourhood → hard block → resolve → interpret, over a named DOM/structural scope, and every signal states its neighbourhood class as a typed field rather than a substring in a `precision` string (`SC-037`) | T | T137, T187 | ☐ |
| R072 | FR-072 | the extraction layer stays linear or bounded-superlinear, every producer reports its five metrics, the ceilings are live, and the **implementation** is bounded — a counter checked after the work does not make the work bounded (`SC-036`, `SC-038`) | M | T185, T187, T191 | ☐ |
| R073 | FR-073 | two independent runs in a second process are identical; no `uuid4`, no clock read, no dict-order dependence, no random tie-break | T | T186 | ☐ |
| R074 | FR-074 | no hidden semantic gate: no extraction path calls `allows_type()` in a drop/deny position, and no relation path contains a continue-on-unrecognised guard | M | T152, T184 | ☐ |

### 2.13 Verification, stop conditions and deliverables

| # | FR | Requirement (one line) | Method | Task | State |
|---|---|---|---|---|---|
| R075 | FR-075 | a deterministic golden entity-type corpus covers the surfaces the brief's §82 names including the ambiguous ones, and each case exercises mention, retained hypotheses, mapped type, unknown types and alternatives | T | T182 | ☐ |
| R076 | FR-076 | a deterministic golden relation corpus covers the brief's §83 text, event, structural and unknown sets plus the ambiguous and conflicting rules **and** the six executable end-to-end HTML cases of §70 | T | T181 | ☐ |
| R077 | FR-077 | an active/passive identity test exists in which the **derivation itself** produces the shared `logical_candidate_id`; pinning both fixtures to one id is forbidden | T | T183 | ☐ |
| R078 | FR-078 | a manifest-driven mutation harness covers exactly the eighteen field groups §93 enumerates, and **every** manifest entry has a named test that fails when that field is broken, with the six §94–§99 section mutations as manifest entries (`SC-015`) | M | T184 | ☐ |
| R081 | FR-081 | no regression into projection, acquisition, interpretation, admission, control-plane or shared; known failures stay unchanged unless directly affected, and baseline membership, new failures and the never-executed tests are all tracked (`SC-016`) | B | T101, T190 | ☐ |
| R082 | FR-082 | a new ontology requirement, an identity ambiguity, a mapping ambiguity, an entity/value ambiguity, a non-deterministic parser or an unrepresentable persistence shape is reported as `UNKNOWN`/`AMBIGUOUS`/`CONFLICTING`/`UNSUPPORTED` rather than guessed | I | T193, T194 | ☐ |
| R083 | FR-083 | the feature ships its full artefact set plus `contracts/` plus ADR-level records **A**–**L** | I | T104, T115, T193 | ☐ |
| R084 | FR-084 | the completion report carries all fourteen headings §114 mandates, in order, each claim classified `implemented` / `verified` / `verified only offline` / `known limitation` / `deferred`; passing tests alone are not sufficient | I | T194 | ☐ |
| R180 | FR-180 | every hard prohibition stated in the brief has at least one named test that **fails** when the prohibition is violated, and that test is reachable from a task in this plan | I | T184, T185 | ☐ |

### 2.14 Type-vocabulary completeness and the machine gate

| # | FR | Requirement (one line) | Method | Task | State |
|---|---|---|---|---|---|
| R110 | FR-110 | the foundational type vocabulary is complete and versioned, the shipped manifest matches the registered artefact, `version` is pinned and loadable, and `kind` is read from the entry and never inferred from the ref (`SC-017`, `SC-018`) | T | T111 | ☐ |
| R111 | FR-111 | a type the pack has never heard of is retained end to end as `UNKNOWN`, survives a store round trip, and zero mentions are dropped for an ontology miss | T | T117 | ☐ |
| R112 | FR-112 | type resolution consumes the context inputs by reference to a named bounded neighbourhood, names what it read, and produces zero claims from any of them (`SC-028`) | T | T120, T121 | ☐ |
| R113 | FR-113 | `021` drops the two `*_asserts_something` CHECK constraints and the stale `ck_relation_signal_kind` whitelist it inherited from `020` | I | T165 | ☐ |
| R114 | FR-114 | parity and schema-invariant tests cover every **dropped** constraint as well as every added column, in both directions, with no delta | T | T173 | ☐ |
| R115 | FR-115 | the reference checker runs as a **gate** — unattended, in CI or the pre-commit chain — exits non-zero on any failed assertion, and reports every check id in its summary so a check that silently stopped running cannot hide | I | T104, T192 | ☐ |

### 2.15 Tombstones

These four slots carry no normative requirement. The row exists to prove nothing cites them as a
live target, and to name where the obligation went.

| # | FR | Requirement (one line) | Method | Task | State |
|---|---|---|---|---|---|
| R058 | FR-058 — tombstone, merged into `INV-004` | the edge-after-claim obligation lives in `INV-004` and is enforced by row `A4`; see the deleted-ids table in `repair/A6-fr-triage.md`; no artefact may cite this slot as a live requirement target | I | T174 | ☐ |
| R070 | FR-070 — tombstone, removed to a design note and the constitutional non-goals | a permission plus two restatements of the non-goals constructs no acceptance criterion; both surviving sentences are restated as non-goals; see the deleted-ids table in `repair/A6-fr-triage.md` | I | T193 | ☐ |
| R079 | FR-079 — tombstone, merged into `FR-078` | the six section mutations are manifest entries of `FR-078`, not a separate apparatus, so the "four" that contradicted its own list of six is withdrawn; a manifest entry breaking `type_ref`, `predicate_signature`, `participants`, `polarity` or `edge` identity keeps a named test; see the deleted-ids table in `repair/A6-fr-triage.md` | I | T184 | ☐ |
| R080 | FR-080 — tombstone, merged into `FR-072` | it restated the same five metrics, so the bound and the counters both live in `FR-072`: `characters_scanned`, `tokens_scanned`, `candidate_pairs_considered`, `structural_nodes_considered` and `signals_emitted`; enforced by rows `R072` and `Y13`; see the deleted-ids table in `repair/A6-fr-triage.md` | I | T187 | ☐ |

---

## 3. Production-path proofs

`P` is not satisfiable by a test harness. A row here is ticked only by exercising the live path.
The old file's architecture-completeness row was a production-path proof wearing a corpus-harness
tick.

| # | FR | Requirement (one line) | Method | Task | State |
|---|---|---|---|---|---|
| W1 | FR-100 | a live `POST /api/v1/entities` produces signals → candidates → claims → edges with **real** mention ids, read from the response rather than from a log line | P | T188 | ☐ |
| W2 | FR-100 | `lexical_signals` has a non-test production importer; today nothing in the repository calls it, not even the corpus | P | T189 | ☐ |
| W3 | FR-165, FR-100 | every investigation-path consumer is re-run against the live queue and produces no duplicate effect from a redelivered key | P | T188 | ☐ |
| W4 | FR-161, FR-163 | the registered workflow is observed running end to end on the worker, with its activities registered alongside it | P | T188 | ☐ |
| W5 | FR-084, FR-100 | the brief's §101 architecture is present in **production** code, not only in the corpus harness; a completion claim resting on the harness alone is refused | P | T188, T194 | ☐ |
| W6 | FR-068 | `GraphProjectionBridge` and `RebuildableGraphStore` each have at least one non-test caller, the production default is still the in-memory store, and a real run recovers a `RelationClaim`, its `Candidate`, its `Signals`, the observations and the source from an edge | P | T180 | ☐ |
| W7 | FR-061 | the normal acquisition path **issues** the `SourceTemporalObservation` write through the repository seam; a recording repository proves the obligation, and only the live round trip is conditional | P | T171 | ☐ |
| W8 | FR-061 | EDGAR `date_filed` stays day-precision, a Common Crawl timestamp stays index-observation time, and neither reaches `Capture.fetched_at` | P | T103, T171 | ☐ |
| W9 | FR-062, FR-084 | every DB-dependent verification is labelled `verified only offline` with its reason recorded, while live PostgreSQL is unreachable | I | T172, T173 | ☐ |

---

## 4. Prohibition and mutation coverage

### 4.1 The §94–§99 mutation manifest

The six named mutations of §94–§99. Each MUST fail **for the right reason**: the assertion is on the
failure, not on the failure's existence. All six are re-homed onto a task that exists; previously
all six rode on a single letter-suffixed id that exists nowhere.

| # | FR | Requirement (one line) | Method | Task | State |
|---|---|---|---|---|---|
| Y1 | FR-001 | §94 — restoring raw `relation_surface` into logical identity material fails its named test | M | T184 | ☐ |
| Y2 | FR-026, FR-090 | §95 — reinstating majority-vote arity/direction resolution fails its named test | M | T184 | ☐ |
| Y3 | FR-016, FR-094 | §96 — a synthetic `surface:person:john` mention ref fails the contract | M | T184 | ☐ |
| Y4 | FR-038, FR-074 | §97 — `if core pack does not know type: continue` fails its named test | M | T184 | ☐ |
| Y5 | FR-023, FR-024 | §98 — `if relation_ref is None: return ()` fails its named test, because an unknown predicate must still leave a `predicate_state=UNKNOWN` candidate with its evidence retrievable | M | T184 | ☐ |
| Y6 | FR-020 | §99 — a producer importing **or constructing** `GraphEdge` fails its named test | M | T184 | ☐ |

### 4.2 Prohibitions that had a row but no enforcing test

Each is a hard prohibition whose behaviour is forbidden but whose *test* was never required. A
prohibition with no failing test is a non-requirement.

| # | FR | Requirement (one line) | Method | Task | State |
|---|---|---|---|---|---|
| Y7 | FR-071, FR-072 | the all-mentions × all-mentions pair sweep is forbidden, and a named mutation fails in **every** extraction path when it is reinstated | M | T184, T191 | ☐ |
| Y8 | FR-020 | the six-symbol producer ban covers **import and construction** of `GraphEdge`, `HyperEdge`, `GraphStore`, `RelationClaim`, `admission` and `projection`, as an AST and import-graph test and not a grep; the old mutation covered only the `GraphEdge` import | M | T152, T184 | ☐ |
| Y9 | FR-043 | §30 — with the parser capability unavailable the full production batch still exits successfully and yields at least one non-empty lexical signal and at least one candidate; the parser-free baseline is useful, not merely non-fatal | T | T137, T189 | ☐ |
| Y10 | FR-010, FR-089 | §14 — the four signal-contract fields the requirement dropped are restored as typed fields, not as `extra`: `predicate_hypothesis`, `trigger_span`, `supporting_spans` and `producer_confidence` | T | T123, T129 | ☐ |
| Y11 | FR-051, FR-061 | §38 — the temporal producer respects the existing `TypeHypothesis` and `SourceTemporalObservation` rather than introducing a third temporal container | T | T147, T171 | ☐ |
| Y12 | FR-069 | §52/§79 — the `edge_id = relation_id` assertion has no defined subject: `edge_id` appears nowhere in the spec, so the row cannot be ticked until the spec names the field it is talking about | I | T175 | ☐ |
| Y13 | FR-072, FR-093 | the five producer counters are reported by every producer and `max_pairs_considered` is a live ceiling a real violation can exceed; reporting a number is not bounding the work, so the bound itself is what is gated | T | T139, T187 | ☐ |
| Y14 | FR-084 | §114 — the completion report carries all fourteen mandated headings, not the five status categories the requirement kept; the status vocabulary classifies claims inside a section, it does not replace the sections | I | T194 | ☐ |
| Y15 | FR-170, FR-060 | `QuarantineStore.purge` deletes a rejected candidate through a live route, which violates "rejected candidates are never auto-deleted"; the re-evaluation path must record its outcome **on** the record, and a `by_tenant` `write` never removes one | I | T160, T169 | ☐ |
| Y16 | FR-169, FR-068 | `HopKind` has no `SIGNAL` member, so the provenance round-trip is unreachable in both directions; adding `CANDIDATE` to the backward chain would not fix it — it is a type-vocabulary defect needing two distinct hop vocabularies | T | T179 | ☐ |
| Y17 | FR-179, FR-030, FR-110 | `SC-026` and the test named for the entity-extractor coverage are renamed: the four numbers are 31 `core:*` types, 13 `value:*` types, 7 §8 extraction families and roughly 4 new instrument modules, and "seven classes" is a misreading that would otherwise harden into a mandate covering `core:Person`, `core:Organization`, `core:OnlineAccount`, `core:WebSite` and the rest | I | T114, T182 | ☐ |
| Y18 | FR-137, FR-140 | no new extraction framework and no second vocabulary list: `extractors/registry.py`'s `ExtractorRegistry` stays the single registration point and `register_deterministic_extractors` stays sorted, so nothing is registered twice; the ontology pack's relation list is deleted; `TypeMapping` is a name for the existing mapping type rather than a parallel dataclass | I | T111, T114 | ☐ |
| Y19 | FR-173 | every constitutional citation names the correct numeral — tenancy is VII, not IV — and the unnumbered determinism principle is cited to its own label | I | T104 | ☐ |
| Y20 | FR-180, FR-074 | the prohibition-coverage sweep is a test, not a review: the checker asserts that the brief's prohibition list and the named-test list agree, so a new prohibition cannot be added without a test | T | T184, T185 | ☐ |

---

## 5. Reporting discipline

| # | FR | Requirement (one line) | Method | Task | State |
|---|---|---|---|---|---|
| M1 | FR-084 | the completion report classifies every claim as `implemented`, `verified`, `verified only offline`, `known limitation` or `deferred`, and uses no other status word | I | T194 | ☐ |
| M2 | FR-084 | every `verified` claim names the test that proves it, and every offline-only claim says so and says why | I | T194 | ☐ |
| M3 | FR-083, FR-167 | `contracts/` (producer protocol, mention-index contract, store contract), the ADR set **A**–**L** with a file per letter, and a `quickstart.md` carrying the commands that actually work | I | T193 | ☐ |
| M4 | FR-081 | `ruff check` is clean on every changed path, and the changed paths include the `apps/shared` and `apps/control-plane` suites the requirement names | I | T192 | ☐ |
| M5 | FR-081 | every failure in `apps/projection`, `apps/acquisition`, `apps/interpretation`, `apps/admission`, `apps/control-plane` and `apps/shared` is classified `baseline` / `new` / `fixed` / `flaky`, and reporting "green" while a new failure hides among the known ones is forbidden | B | T190 | ☐ |
| M6 | FR-081 | the 22 tests that never executed are enumerated and tracked, so a green run is not reported as a full-suite pass | I | T101, T190 | ☐ |
| M7 | FR-082 | any stop condition triggered is listed as `deferred` with its reason, and is never silently resolved by widening the vocabulary, never resolved by casting a guess as a type, and never resolved by renaming the artefact that failed | I | T193, T194 | ☐ |
| M8 | FR-078, FR-084 | the mutation results are reported per manifest entry with the reason each mutation failed, not as a count of failures | I | T184, T194 | ☐ |
| M9 | FR-168 | absent CI, the completion report carries a dated, named attestation of who ran the constitutional gate and on which commit | I | T190, T192 | ☐ |

---

## 6. Arbitration gate conditions

From `repair/ARBITRATION.md` §12. All six must hold, and each must be machine-verifiable wherever
that is possible.

| # | FR | Requirement (one line) | Method | Task | State |
|---|---|---|---|---|---|
| G1 | FR-115, FR-173 | FR namespace collision is 0 — every id defined exactly once, the void and reserved bands left empty, and no artefact inventing a number | I | T104 | ☐ |
| G2 | FR-083, FR-078 | zero normative references to the tombstoned set: the four `spec.md` tombstones plus the two letter-suffixed ghosts the record folded into the surviving invariant and requirement | I | T104, T184 | ☐ |
| G3 | FR-011, FR-152, FR-055 | `TEMPORAL` is **kept** as a `SignalKind` channel, the recreated kind whitelist includes it, and the Phase-4 model has exactly one answer: `RELATION_SIGNALS ≺ RELATION_CANDIDATE ≺ RESOLUTION ≺ CLAIM_MATERIAL ≺ VALIDATION ≺ ADMISSION ≺ STORE ≺ EDGE ≺ WORLDLINE`, with `REGIME` recorded as an open decision | T | T125, T128, T158, T165 | ☐ |
| G4 | FR-008, FR-097 | n-ary `participants` has a lossless, typed persistence representation in `021` as `JSONB NOT NULL` on **both** tables — not `extra`, and not deferred to a later migration — and a stored row round-trips to an identical in-memory object re-deriving an identical `logical_candidate_id` | T | T123, T165, T172 | ☐ |
| G5 | FR-068, FR-169 | evidence lineage is not derivation lineage: two distinct hop vocabularies with a `SIGNAL` hop traversable both ways, and the round-trip is a provenance walk rather than a seat for the candidate inside a constitutional warrant chain | T | T179 | ☐ |
| G6 | FR-001, FR-077, FR-177 | `SC-001` carries an `xfail(strict=True)` marker whose reason is the absent syntactic producer; **T138** owns the marker and **T131** owns the turn to green, where the shared `logical_candidate_id` is derived from the `PredicateSignature` rather than pinned; no wave reports `SC-001` as passing while the marker stands | T | T110, T131, T138 | ☐ |

---

## 7. Placement gate (`repair/A8prep-ownership-and-dag.md` §O6)

The placement agent states 87 machine-checkable assertions, each with a sole owner, and 21 failing
against the revision as it stands. **Its own per-gate arithmetic sums to 82, not 87** — G1 6, G2
13, G3 13, G4 9, G5 10, G6 8, G7 7, G8 8, G9 8 — so the two numbers in §O6 disagree and the
authoritative one is not established. The rows above are what the feature-side assertions are
gated on; the rest are properties of the placement itself. A **fail (measured)** marker means the
assertion is already failing against the tree and is not a claim about this file.

| Assertion | Enforced by the rows | State |
|---|---|---|
| G1.1 | every line of the five files is covered by exactly one ownership range | fail (measured) |
| G1.2 | no two agents touched the same ownership range | fail (measured) |
| G1.3 | no patch edited a range marked unchanged, except the named carve-out lines | fail (measured) |
| G1.4 | every append landed at its declared anchor, in the reserved order | fail (measured) |
| G1.5 | all seven repair documents exist, are non-empty and are referenced from the revision | pass |
| G1.6 | `tasks.md` was written only by the placement agent | pass |
| G2.1 | FR ids are unique | pass |
| G2.2 | every FR id matches the three-digit form, with a deliberate suffix allowed | pass |
| G2.3 | each agent's band is contiguous in document order | **fail (measured)** — `FR-082` sits out of numeric order |
| G2.4 | `FR-082` sits numerically between `FR-081` and `FR-083` in document order | **fail (measured)** — owner A6 |
| G2.5 | every FR is cited by at least one of `tasks.md`, this checklist or `data-model.md` | **fail (measured)** — 57 orphans; this file now closes the checklist side of all of them |
| G2.6 | every FR carries at least one section reference into the brief | fail (measured) |
| G2.7 | every FR appears in the traceability matrix with an owning phase and a verifying task | pass — sub-section 2 of this file is that matrix |
| G2.8 | every success criterion is referenced by at least one task id that exists | pass — all 43 named |
| G2.9 | every invariant is traceable to at least one test and one section | pass — §1 |
| G2.10 | count claims agree across the six places that state them | **fail (measured)** — brief length and the mutation counts; owner A6 |
| G2.11 | the reserved bands remain unused | pass |
| G2.12 | every supersession note names the superseding FR, the deciding rule and the deciding agent | fail (measured) |
| G2.13 | `input.md` is byte-identical to the brief | pass |
| G3.1 | every task id in `tasks.md` is unique and in range | pass — 94 ids |
| G3.2 | every task token in the five files matches a defined task | **fail (measured)** — 9 phantoms; this file contributed 5 and now contributes 0 |
| G3.3 | no letter-suffixed task id exists anywhere | **fail (measured)** — the same 9; this file now contributes 0 |
| G3.4 | every task carries a `files:` line listing its exact write set | pass — every task now has one |
| G3.5 | no two parallel tasks in a phase share a write set, and none reads another's | pass — stated per phase in `tasks.md` |
| G3.6 | no task references a task in a later phase | pass — the one backwards edge is replaced by the declared `red→green:` edge |
| G3.7 | the phase graph is acyclic | pass |
| G3.8 | phases are present with no gap | pass — twelve phase headers |
| G3.9 | every phase states an entry and an exit condition, and every exit is a machine command or a named test | pass |
| G3.10 | the minimum viable increment is a prefix of the phase order and its story set matches its phases' story tags | **fail (measured)** — owner A8prep |
| G3.11 | the mandated phase structure covers all 12 brief phases | pass — 12 of 12 |
| G3.12 | every brief deviation is recorded with its authorising section | fail (measured) |
| G3.13 | every FR in a phase's closed list is in that phase owner's band | fail (measured) |
| G4.1 | every node name in the model diagram resolves through the legend to a code type or a stage | **fail (measured)** — 4 dangling; owner A6 |
| G4.2 | the level count agrees across the data model, the invariant and the diagram | **fail (measured)** — owner A1 + A6 |
| G4.3 | no concept has two names across the five files | **fail (measured)** — 3 collisions; owners A5, A6 |
| G4.4 | every key entity has a data-model summary row | **fail (measured)** — 2 missing; owners A5, A4b |
| G4.5 | exactly one type declares each duplicated field authoritative | **fail (measured)** — owner A4b |
| G4.6 | every summary row carries a valid status and every unspecified row is reported as deferred | fail (measured) |
| G4.7 | every data-model section and summary row agree on status and identity key | fail (measured) |
| G4.8 | no diagram edge contradicts a requirement | fail (measured) |
| G4.9 | every diagram node marked unspecified has a named owning phase | fail (measured) |
| G5.1 | every relative markdown link in the five files resolves | fail (measured) |
| G5.2 | every file path named in the five files exists or is declared new with an owning task | pass — `files:` on every task |
| G5.3 | every `path.py:NNN` reference points to an existing line that still says what is claimed | fail (measured) |
| G5.4 | no undefined requirement, criterion, invariant, task or ADR-letter reference anywhere | **fail (measured)** — this file is clean of its own share |
| G5.5 | every section reference into the brief resolves to a real section | pass — this file cites only real sections |
| G5.6 | every type name and enum member named in the five files exists, or is declared new with an owning task | **fail (measured)** — the `edge_id` of `Y12` is one instance |
| G5.7 | the synthetic ref prefix list matches the list the checker greps for | fail (measured) |
| G5.8 | ADR letters A–K each have a record | pass — superseded by the A–L set; the assertion itself is stale |
| G5.9 | `contracts/` exists and declares the producer, mention-index and store contracts | fail (measured) — rows `M3`, `R083` |
| G5.10 | the checker exits non-zero on a deliberately injected violation | pass |
| G6.1 | each invariant traces to at least one test and one section | pass — §1 |
| G6.2 | the constitution check table has a status and a re-check for every principle, and the supersession rule states which document wins | fail (measured) |
| G6.3 | `InvestigationWorkflow` has a recorded disposition and the reachability row agrees with it | pass — rows `R163`, `R172` |
| G6.4 | no requirement permits majority-vote resolution — every occurrence sits inside a prohibition | pass — rows `R026`, `Y2` |
| G6.5 | no requirement makes a vocabulary match a gate | pass — rows `A2`, `R074` |
| G6.6 | no requirement permits an edge not derived from an admitted claim | pass — rows `A4`, `R058` |
| G6.7 | no requirement permits a producer to import a graph/claim/admission/projection symbol, or to contain an entity literal | pass — rows `A7`, `R020`, `Y8` |
| G6.8 | the distinct-type invariant appears once, with one count | **fail (measured)** — owner A1 |
| G7.1 | every phase exit condition is satisfied by a named test that exists | fail (measured) |
| G7.2 | the mandated phase structure covers all 12 brief phases | pass — 12 of 12 |
| G7.3 | every brief deviation is recorded with its authorising section | fail (measured) |
| G7.4 | the identity phase is split so the first half is committable alone | pass — P1a / P1b with the declared `red→green:` edge |
| G7.5 | the persistence substrate is the projection phase's entry condition | fail (measured) — owner A8prep |
| G7.6 | every phase-exit assertion maps to at least one task | pass |
| G7.7 | the broken construction sites and enum references each have an owning task | pass — `T127` and `T128` |
| G8.1 | migration `020` is byte-identical to its committed state | pass |
| G8.2 | `021` exists, is forward-only, and its `downgrade()` raises | fail (measured) — rows `R062`, `R157` |
| G8.3 | `021` is the migration head | fail (measured) — the head is `020`; row `R097` |
| G8.4 | the parity test exists and is named in `tasks.md` | pass — `T173` |
| G8.5 | every column in `021` appears in the ORM and vice versa, with no delta | fail (measured) |
| G8.6 | the obsolete CHECK constraints are named in the spec **and** dropped by `021` | fail (measured) — rows `R013`, `R113`, `R150` |
| G8.7 | every column participating in an id has a column in its table | fail (measured) |
| G8.8 | no digest is the only copy of any field | fail (measured) — rows `R060`, `R131` |
| G9.1 | the baseline failures are itemised and unchanged, and no suite exceeds its count | pass — §0.2, rows `K1`–`K16` |
| G9.2 | the completion report uses only the permitted status words | pass in form — row `M1` is unverified, so this is not yet a pass |
| G9.3 | every verified claim names a test; every offline-only claim says so | pass in form — row `M2` is unverified |
| G9.4 | no completion claim rests on the corpus harness alone | pass in form — row `W5` is unverified |
| G9.5 | every row of the reachability table is re-measured at the revision's head | fail (measured) |
| G9.6 | the mutation floor in the criteria equals the number of manifest field groups, with a named test each | **fail (measured)** — the criteria state a floor of 20 against 18; owner A6 |
| G9.7 | every mutation fails for the right reason | fail (measured) — row `M8` |
| G9.8 | the baseline was re-run at the second phase's entry, not only at the first | pass — `T190` |

---

## 8. Sign-off conditions

The feature is complete only when every row above reads `verified` (or an explicitly justified
`verified only offline`, `known limitation` or `deferred`), **and** all of the following hold. A
tick is not a claim; it is a pointer to a run.

1. **No row is `UNASSIGNED`.** An `UNASSIGNED` row is a gate on nothing. Each must acquire a task id
   that exists in `tasks.md` before sign-off, or the requirement it gates must be withdrawn in
   writing. The count is stated in the change log, not estimated.
2. **No row points at a task that does not exist.** Every `Task` cell resolves against
   `tasks.md`, whose ids are `^T\d{3}$`. A letter-suffixed id is by definition outside that set, so
   it is a phantom waiting to happen; the five that used to be in this file are gone.
3. **The `P` rows cannot be ticked on a test harness.** `W1`–`W8` are production-path proofs. A
   corpus run, an in-memory store or a mocked repository satisfies none of them. `W7` is the one
   deliberate exception: its *write obligation* is proved with a recording repository, and the live
   round trip is reported `verified only offline` under `W9`.
4. **The 16 baseline failures are individually accounted for.** `K1`–`K16` each carry a
   classification of `baseline`, `new`, `fixed` or `flaky`. A `new` classification is a gate
   failure. `K14` is the one row this feature may legitimately move to `fixed`, and it must say so
   explicitly rather than let the count drift.
5. **The 22 never-executed tests are tracked, not assumed.** `N1`–`N5` are enumerated. If Docker is
   started, `N6` fires and the whole of §0 is recomputed before any comparison is believed.
6. **Any stop condition triggered is listed as `deferred` with its reason.** Never silently
   resolved by widening the vocabulary, never resolved by casting a guess as a type, and never
   resolved by renaming the artefact that failed. The record is in `M7` and in the report's
   remaining-debt section.
7. **Every tombstone has zero normative references.** `R058`, `R070`, `R079` and `R080` are cited
   only as tombstones; their obligations are verified through `INV-004` and row `A4`, the
   non-goals list, `R078` and `R072` respectively.
8. **The fourteen §114-mandated report headings are present**, not the five status categories the
   requirement kept. The status vocabulary classifies each claim inside a section; it does not
   replace the sections.
9. **The four §8 numbers are never conflated.** 31 `core:*` types, 13 `value:*` types, 7 §8
   extraction families, roughly 4 new instrument modules. `SC-026` and the test named for it are
   renamed before anything depends on the old name.
10. **The checker's own verdict is part of sign-off.** The traceability, orphan, tombstone and count
    checks must be clean for this file, and the full set of check ids must appear in the summary so
    a check that silently stopped running cannot hide.
