# Tasks: 021-entity-relation-extraction-finalization

**Input**: Design documents from `specs/021-entity-relation-extraction-finalization/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md` — all present
**Tests**: MANDATORY. §108 makes tests the only acceptable proof, so every phase below carries
test tasks and they are written before the implementation they cover.
**Authority**: `input.md` §110 fixes the development order. It **overrides** the usual
"group by user story" template — the brief's 12-phase order *is* the dependency graph, so the
phases are the sections and each task carries the `[USn]` stories it unblocks.

**Format**: `[ID] [P?] [USn] Description` — `[P]` = different files, no dependency.

---

## Phase 0: Baseline (blocking — nothing may start without it)

**Purpose**: Freeze the floor so "no regression" is measurable rather than asserted.

- [ ] T001 [P] Re-run and record the full baseline: `uv run --project apps/<app> pytest apps/<app>/tests -q` for shared, control-plane, interpretation, projection, admission, acquisition. Record exact pass/fail/skip counts in `specs/021-.../checklists/requirements.md`. Expected floor: control-plane 2 failed (`test_donor_api`), shared 14 failed. **If the numbers differ from research.md R-000, stop and report before touching code.**
- [ ] T002 [P] Confirm the Alembic head is `020_universal_relation_extraction` and that its `downgrade()` raises `NotImplementedError`. `020` must never be edited.
- [ ] T003 Record the parser baseline for R-001: capture a tree-construction digest per HTML fixture with `selectolax`, and pin it. A later diff must be a deliberate, visible change.
- [ ] T004 [P] Create `specs/021-.../checklists/requirements.md` from the Speckit requirements checklist, mapped to the 102 FRs, and mark each item's verification method.

**Checkpoint**: Baseline frozen and written down. No implementation may claim "no regression" without T001.

---

## Phase 1: Identity / domain cleanup (§110-1)

**Goal**: Make identity honest before anything new is built on top of it. Unblocks US1, US2, US8.
This phase exists because every later phase's determinism claim rests on it.

- [ ] T005 [US1] Canonicalise `signal_refs` on construction in `apps/shared/domain/relation_candidate.py`, matching `observation_refs`/`evidence_refs`. Add a test proving two candidates with the same signals in different input order get the same `candidate_id`. (FR-085)
- [ ] T006 [US2] Remove `relation_surface` from `_logical_material()`; key logical identity on the signature (T020) with a temporary fallback. Add the failing-then-passing test: active and passive realisations share one `logical_candidate_id`. (FR-005, FR-007)
- [ ] T007 [US8] Add `to_dict()`/`from_dict()` to `RelationCandidate`, covering all fields losslessly, with a build → store → read round-trip test asserting the field list, not a summary string. (FR-086)
- [ ] T008 [US8] Reconcile `verify_candidate_material_partition()`: either call it and make it correct, or delete it. Fix `CANDIDATE_LOGICAL_MATERIAL_FIELDS`, which declares `relation_type` where the code emits `relation_surface`. (FR-098)
- [ ] T009 [US2] Make `RelationClaim` re-derive and check its own carried `relation_id`, as candidates, materials and temporal observations already do. (FR-099)
- [ ] T010 [US2] Remove the dead `valid_from`/`valid_to` kwargs from `logical_material()`/`logical_relation_id()`, or make them load-bearing. Today they are declared, passed by both callers, and never read.

**Checkpoint**: Two processes deriving ids from the same inputs MUST agree, with no sort at the call site. Verified by T005.

---

## Phase 2: Foundational types (§110-2)

**Goal**: The new value types everything else imports. Unblocks US1, US7.
Depends on Phase 1 (a signature is an identity term, so it lands on honest identity).

- [ ] T011 [P] [US1] Create `apps/shared/domain/predicate_signature.py`: `PredicateSignature`, its `content_key()`, and normalisation rules N1–N6. One test per rule. (FR-020, data-model §1)
- [ ] T012 [P] [US7] Add `Polarity` (`ASSERTED`/`DENIED`/`UNCERTAIN`) in `apps/shared/domain/`. It replaces `SignalKind.NEGATION` and must exist before the signal is restructured. (FR-021)
- [ ] T013 [P] [US7] Add `RelationParticipant` (`mention_ref`, `role`, `argument_shape`) — the variadic participant unit. (FR-022)
- [ ] T014 [US7] Decide and record **Q4** (research.md): does N-ary identity use role bindings or positional arguments? `logical_material` currently ignores its `participants` argument for NARY. Record as an ADR per §100 decision K.
- [ ] T015 [US1] Extract the N5 synonym table into a versioned, sourced, reviewable artefact with provenance. If any entry cannot be justified from a source, drop it and let the predicate stay `AMBIGUOUS` rather than guessing. (FR-082)
- [ ] T016 [P] [US4] Create `apps/shared/semantic/type_vocabulary.py`: the bounded versioned `core:*` / `value:*` pack with hierarchy, answering **Q2** (research.md) as an ADR per §100 decision D/E. An unmapped type MUST yield `UNKNOWN`, never rejection. (FR-030, FR-033, FR-034a)

**Checkpoint**: `PredicateSignature` round-trips and its normaliser is individually tested. No producer or signal code touched yet.

---

## Phase 3: Type hypotheses and mention binding (§110-3)

**Goal**: A mention can be several things, and a producer cannot invent a mention. Unblocks US3, US4.
Depends on Phase 2 (`TypeHypothesis` needs the vocabulary; mention refs need the participant shape).

- [ ] T017 [US4] Extend `TypeHypothesis` in `apps/shared/semantic/blocking.py` to carry competing hypotheses with `CandidateResolutionState`, `vocabulary_version` and evidence refs. Test: "Apple" yields ≥3 retained hypotheses and selects none. (FR-029, FR-031)
- [ ] T018 [US4] Make `TypeAssertion` consume the competing hypotheses and record what it did *not* select. An ontology match MUST NOT become automatic truth. (FR-032)
- [ ] T019 [US3] Create `apps/interpretation/mention_index.py`: the pre-resolution binding seam and the **only** minter of `MN-…` ids. (FR-034, FR-103)
- [ ] T020 [US3] Wire the mention index into the extraction scope so a producer receives a resolver, and assert every `participant.mention_ref` resolves in it. (FR-103)
- [ ] T021 [US3] Record **Q3** (research.md) — the bounded-neighbourhood scope definition — and make `Neighbourhood` carry a real scope rather than a substring-tested `precision` string. (FR-070, FR-095)

**Checkpoint**: Every mention ref produced by Phase 4 onward resolves in the index. The §96 mutation (a synthetic `surface:person:john`) must fail the contract.

---

## Phase 4: Structural `RelationSignal` (§110-4)

**Goal**: Make the signal structurally honest — n-ary native, polarity real, kinds un-overloaded.
Unblocks US5, US6, US7. Depends on Phase 2 (participants, polarity) and Phase 3 (mention index).

- [ ] T022 [US7] Change `RelationSignal` in `apps/interpretation/extractors/signals/signal.py` to `participants: tuple[RelationParticipant, ...]`, variadic, arity ≥ 2. Remove the two hard-coded scalars. Test the §88 n-ary sale end to end. (FR-012, FR-013)
- [ ] T023 [US6] Remove `NEGATION`, `QUANTITY` and `COREFERENCE` from `SignalKind`, leaving observation channels plus `CO_OCCURRENCE`. Do NOT add a `TEMPORAL` member — the brief names one, the code never had it, and `stated_axes` already carries time. (FR-011)
- [ ] T024 [US6] Move negation to `Polarity.denied` on the signal, cardinality to `argument_shape` on the participant, coreference to a relation between mention refs. Test: a denial is evidence, not a drop. (FR-014, FR-015)
- [ ] T025 [US5] Replace `signal_asserts_nothing` with the honest rule: a `CO_OCCURRENCE` signal MAY have an empty surface and a `None` signature. Keep refusing only an empty surface + no signature + a kind that *does* assert a predicate. Update the regression test that currently locks in the wrong rule. (FR-006)
- [ ] T026 [US5] Add `predicate_signature`, `polarity`, declared `arity` and `role_names` to `RelationSignal._material()`. Keep `producer_ref` — that part is correct. Correct the three docstrings claiming two producers share a `signal_id`. (FR-089)
- [ ] T027 [US7] Test that two signals differing only in stated arity no longer collapse to one `signal_id`. (FR-089)

**Checkpoint**: n-ary is native, polarity is a field, and the §40 surface-required co-occurrence defect is gone.

---

## Phase 5: `PredicateSignature` and identity (§110-5)

**Goal**: Wire the signature into candidate identity. Unblocks US1, US2, US5, US6.
Depends on Phase 4 (the signal must be able to carry the signature) and Phase 1 (identity is honest).

- [ ] T028 [US1] Extend `PredicateHypothesis` in `apps/shared/domain/predicate_hypothesis.py` with a real `normalized_form` normaliser; `relation_ref=None` with a full signature MUST be legal and MUST be the norm. (FR-016, FR-017)
- [ ] T029 [US2] Wire `logical_candidate_id` to the signature. Prove `"John is the originator of Acme."` and `"Acme was originated by John."` collapse to one logical id with two revisions. (FR-005, data-model §3)
- [ ] T030 [US2] Confirm `relation_surface` is now revision/evidence material only, and that a surface change creates a `candidate_id` revision without changing the logical id. (FR-008)
- [ ] T031 [US5] Carry the signature from signal → candidate in `apps/control-plane/semantic_path/assembly.py`, preserving direction, polarity, arity, role names and all signal refs. (FR-025)
- [ ] T032 [US1] Test the §90 unknown case end to end: signal → candidate → preserved surface → normalised predicate → signature → `relation_ref=None` → `state=UNKNOWN` → no claim → no edge, with every piece of evidence still retrievable. (SC-002)

**Checkpoint**: The §84 and §90 mandatory tests pass. This is the constitutional heart of the feature.

---

## Phase 6: Producers (§110-6)

**Goal**: No producer may invent a mention, a key, or a count. Unblocks US3, US5.
Depends on Phase 3 (mention index) and Phase 4 (participant shape).

- [ ] T033 [P] [US3] Convert `links.py` to resolve real mention refs; delete the `anchor:*` / `href:*` fabrication and emit one signal per anchor with an honest independence identity. Fix `pairs_considered = scanned // 16`. (FR-093, FR-094)
- [ ] T034 [P] [US3] Convert `tables.py` to the DOM path. Delete the most-`<th>` heuristic as a *published* `precision="exact"`; keep the heuristic or drop it, but do not call it exact. Make `zip(..., strict=False)` strict so a `<dt>` term is never silently dropped; report a width-mismatched row instead of dropping it. (FR-095)
- [ ] T035 [P] [US3] Convert `metadata.py` to resolve real mention refs. Delete the `attribute:*` / `jsonld:*` **property-name subjects** — a field name is not a participant. Remove the `document:current` fallback in favour of a required `document_ref`, and replace 64-char truncation with a full content address. (FR-094)
- [ ] T036 [P] [US3] Convert `lexical.py` to resolve real mention refs; delete `surface:role:*`. Make the dead `MAX_PAIRS_CONSIDERED = 10_000` live or delete it — today it is compared against a hard-coded `0`. (FR-093)
- [ ] T037 [P] [US5] Add producers for the dissolved kinds: at minimum a `CO_OCCURRENCE` producer (surface-optional) and a coreference producer. Test: proximity with no predicate words is representable. (FR-006, FR-016)
- [ ] T038 [US3] Assert across all producers: zero synthetic `*_mention_ref` values remain in production producer code, and every `participant.mention_ref` resolves in the mention index. (FR-103, §96)

**Checkpoint**: The §96 mutation fails as required, and `grep` for the 12 fabrication prefixes in producer code returns nothing.

---

## Phase 7: Assembly (§110-7)

**Goal**: Grouping that reports disagreement instead of voting it away. Unblocks US2, US5, US6.
Depends on Phase 5 (candidates are signature-keyed).

- [ ] T039 [US2] Delete the majority vote and alphabetical tie-break from `_arity_of` in `assembly.py`; change its `-> Any` to `-> RelationArityMode`. (FR-090, §95)
- [ ] T040 [US2] A conflict over arity, direction, polarity or roles MUST yield `CandidateStatus.CONTRADICTED` with both readings preserved and MUST appear in `AssemblyReport` as a conflict. A declared NARY schema MUST NOT be downgraded to DIRECTED, and losing a vote MUST NOT silently drop role bindings. (FR-090, FR-026)
- [ ] T041 [US5] Group by structural participant configuration, preserving direction, polarity, signature, all signal refs and alternatives. Equal endpoints MUST NOT merge. (FR-025, FR-027)
- [ ] T042 [US5] Remove `RelationalReading.to_candidate()` from `apps/interpretation/extractors/relations.py`, or reduce it to a call into the assembler, so "how does a signal become a candidate" has exactly one answer in the code, not just in a docstring. (FR-091)
- [ ] T043 [US5] Test §43/§44: lexical, table and metadata producers over one participant configuration produce one logical candidate carrying many signals — and a *different* reading produces a different one. (FR-025)

**Checkpoint**: §95 mutation fails. A conflicting-arity case produces `CONFLICTING`, never a silent majority.

---

## Phase 8: Lifecycle (§110-8)

**Goal**: Separate observation, hypothesis, validation, admission and projection — and gate the store write on the decision. Unblocks US8, US9.
Depends on Phase 7.

- [ ] T044 [US8] Split `_claim_step` in `semantic_path/execution.py` so materialisation, validation and admission are separately observable, and retain the `ValidationReport` that gated admission instead of discarding it as a local. (FR-092)
- [ ] T045 [US8] Remove the post-admission re-validation, or justify it. Today the claim is validated twice — once as material before it exists, once as claim after `admit` committed it. (FR-057, FR-058)
- [ ] T046 [US8] Make the admission decision actually gate the store write. Today `_store_step` writes unconditionally and `decision.materialisable` is never branched on. (FR-059)
- [ ] T047 [US8] Stop doubling production writes to demonstrate idempotency. (FR-092)
- [ ] T048 [P] [US8] Fix the docstrings that say "thirteen steps" — there are fourteen. (Record as an ADR per §100 decision K.)
- [ ] T049 [US8] Record **Q5** (research.md): the producer ↔ lifecycle import direction, as an ADR. `run_producer` is in interpretation, `run_until` in control-plane, and `interpret_warc_capture` would call both.
- [ ] T050 [US9] Populate `ExecutionRequest.producers` — declared, never assigned by anyone, so `run_producer` currently iterates zero times on every run. (FR-100)

**Checkpoint**: The lifecycle is observable phase by phase, and the admission decision is load-bearing.

---

## Phase 9: Persistence (§110-9)

**Goal**: Store everything observed, read back exactly, replay identically. Unblocks US8.
Largest single block. Depends on Phase 5 (signature), Phase 1 (serialisation).

- [ ] T051 [US8] Create migration `021` on top of the forward-only `020`. Add the `predicate_signature` column set to `relation_signal` and `relation_candidate`. Never edit `020`. (FR-097, FR-087)
- [ ] T052 [US8] Add `signal_refs`, `direction`, `polarity`, `confidence` to `relation_candidate`, and `candidate_id` to `relation_claim`, in both the migration and the ORM, keeping parity test-enforced. (FR-088)
- [ ] T053 [US8] Add structured columns for `PredicateHypothesis.alternative_refs` and `mapping_evidence_refs`. A digest may identify data but MUST NOT be the only copy. (FR-087, FR-060)
- [ ] T054 [US8] Create `apps/control-plane/db/relation_signal_store.py` — a repository, writer and reader for `relation_signal`, `relation_candidate` and `source_temporal_observation`. **None of the three has any writer today; no INSERT exists anywhere.**
- [ ] T055 [US8] Resolve `SqlRelationClaimStore`: give the validation verdict a home or accept that the store stays unusable. Its `record_validation`/`non_valid` raise `NotImplementedError` and it has zero importers. Record which way this went.
- [ ] T056 [US8] Wire `capture_with_observations()` into `StreamRegistry.capture()`/`captures()`, and consume the `to_temporal_observations` output the SEC EDGAR and Common Crawl adapters already implement. Today the probe is `getattr`-ed and never invoked, so `source_temporal_observation` is unreachable. (FR-096, §61)
- [ ] T057 [US8] Build → store → read round-trip tests for every new type, asserting the full field list. Report DB verification as `verified only offline` while live PostgreSQL is unreachable. (FR-060, FR-084)

**Checkpoint**: No field that participates in an id is absent from its row. Verified by inspection of both the migration and the ORM.

---

## Phase 10: Projection (§110-10)

**Goal**: The graph shows admitted claims, and is rebuildable from the stores. Unblocks US9.
Depends on Phase 9 (a rebuild needs a store to rebuild from).

- [ ] T058 [US9] Keep `GraphProjectionBridge` typed `claim: RelationClaim` with no overload — a candidate or signal must remain unprojectable even by mistake. Add a test that tries and fails.
- [ ] T059 [US9] Add `direction` and `polarity` to `properties`. Assertion and derivation metadata goes in properties and MUST NOT enter edge identity. (FR-079)
- [ ] T060 [US9] Prove rebuildability: write claims → project → rebuild via `RebuildableGraphStore` → compare. Today it has zero production callers, so "the graph is a projection" is unproven. (Constitution III)
- [ ] T061 [P] [US9] Wire `GraphProjectionBridge` and the relation store into the live path. Both are implemented and unused. Explicitly OUT of scope: switching the default from `InMemoryGraphStore` to `Neo4jGraphStore` (research R-006).
- [ ] T062 [US9] Add the §78–§81 tests: graph equals a projection of claims; graph is rebuildable; edge metadata is not edge identity; unknown remains unknown and the graph does not invent a type.

**Checkpoint**: An edge can only come from an admitted claim, and the graph can be thrown away and rebuilt from the stores.

---

## Phase 11: Corpus and mutations (§110-11)

**Goal**: The 8 golden end-to-end HTML cases and the 17 mutations from §84–§101. Unblocks every story's proof.
Depends on all implementation phases.

- [ ] T063 [P] [US1] Golden relation corpus over the six end-to-end HTML cases of §70: cue phrase, passive, hyperlink, table, `Founder:` attribute, n-ary sale. Plus the text, event, structural, unknown, ambiguous and conflicting sets of §83.
- [ ] T064 [P] [US4] Golden entity-type corpus over the §82 surfaces including the ambiguous names, testing raw mention, type hypotheses, mapped type, unknown types and alternative types.
- [ ] T065 [P] [US8] Replay harness: the same input MUST produce the same `signal_id`, `candidate_id` and `relation_id` in a second process. (Constitution VI)
- [ ] T066 [US5] Mutation tests for §94–§101, each of which MUST fail: surface restored into logical identity (§94); majority-vote arity/direction (§95); synthetic `surface:person:john` (§96); `if core pack does not know type: continue` (§97); `if relation_ref is None: return ()` (§98); a producer importing or constructing `GraphEdge` (§99).
- [ ] T067 [P] [US8] Boundedness and coverage report per §106: input size, signals produced, pairs considered, structural nodes considered, time. After the work does not make the work bounded — report it.

**Checkpoint**: 18+ golden cases and 17 mutations, all mutations failing for the right reason.

---

## Phase 12: Benchmark, regression and wiring (§110-12)

**Goal**: Prove it in production, prove nothing regressed, and report honestly. Depends on all.

- [ ] T068 [US9] Wire the whole lifecycle into `services/capture_interpretation.py::interpret_warc_capture`, which both live production branches already funnel through. Prove a real `POST /api/v1/entities` produces signals, candidates, claims and edges — with real mention ids, not `document:current`. (FR-100)
- [ ] T069 [US9] Prove `lexical_signals` actually runs. It has never been called by anything in the repository, not even the corpus.
- [ ] T070 Re-run the full T001 baseline. No suite may exceed its Phase 0 failure count. Classify every failure as baseline, new, fixed or flaky, and forbid reporting "green" while a new failure hides among known ones. (FR-081)
- [ ] T071 [P] Record benchmarks: signal throughput per document, candidate assembly time, projection time, and the locality-window cost — proving no O(N²) mention sweep. (FR-047)
- [ ] T072 [P] Run `uvx ruff check` on all changed paths.
- [ ] T073 [P] Write `specs/021-.../contracts/` and the §100 ADRs A–K, and update `quickstart.md` with the commands that actually work.
- [ ] T074 [US8] Write the completion report, distinguishing `implemented` / `verified` / `verified only offline` / `known limitation` / `deferred`. "Feature complete" requires the §101 architecture to be present in **production** code, not only in the corpus harness. (FR-084, §114)

**Checkpoint**: The gate is re-run and reported honestly, and the live path demonstrably executes the new substrate.

---

## Dependencies & execution order

```
Phase 0  Baseline                      (blocks everything)
   |
Phase 1  Identity/domain cleanup       (blocks 5, 7, 9)
   |
Phase 2  Foundational types            (blocks 3, 4, 5)
   |
Phase 3  Type hypotheses + binding     (blocks 6)
   |
Phase 4  Structural RelationSignal     (blocks 5, 6)
   |
Phase 5  PredicateSignature + identity (blocks 7, 8, 9)
   |
Phase 6  Producers                     (blocks 7)
   |
Phase 7  Assembly                      (blocks 8)
   |
Phase 8  Lifecycle                     (blocks 9, 10)
   |
Phase 9  Persistence                   (blocks 10)
   |
Phase 10 Projection
   |
Phase 11 Corpus + mutations
   |
Phase 12 Benchmark, regression, wiring
```

Phases 6 and 7 may overlap: producers (6) do not depend on each other, and assembly (7) can
be written against the T031 signature contract while producers are still converting. Phases 2
and 3 are likewise partly parallel — T016 (`type_vocabulary.py`) and T017 (`TypeHypothesis`) are
different files, and T012/T013 are independent of both.

## MVP

The smallest defensible increment is **Phases 0 → 1 → 2 → 5**, which delivers User Story 1
alone: a relation nobody has a name for survives intact, with a preserved surface, a normalised
predicate, a signature, `UNKNOWN`, and no fabricated claim. It is worth building and stopping
there, because it is the constitutional heart and it is the only story whose absence makes the
rest of the substrate wrong rather than merely incomplete.

## Open questions blocking specific tasks

| Q | Blocks | Default if unanswered |
|---|---|---|
| Q1 normalisation rule set | T011, T015, T028 | N1–N4 only; N5 entries dropped, predicates stay `AMBIGUOUS` |
| Q2 controlled vocabulary | T016 | Bounded versioned vocabulary, used as a mapping instrument only |
| Q3 neighbourhood scope | T021 | Per-producer stated scope, no cross-producer claim |
| Q4 n-ary identity shape | T014 | Role bindings (`logical_material`'s current NARY path) |
| Q5 import direction | T009f | `interpret_warc_capture` calls producers, then the assembler |
| Q6 `Layer0Pipeline` vs `capture_interpretation` | T013a | `capture_interpretation` — it is the live path |
| Q7 temporal-observation repository | T010d, T010f | Yes, in 021, since §61 names it |

## Notes

- Tests are written FIRST in each phase and MUST fail before the implementation exists.
- Commit after each task or logical group; never bundle a phase boundary.
- Stop at any checkpoint to validate independently.
- If a task turns out to need a new ontology, a mapping decision, or a guess — stop and report
  `UNKNOWN` / `AMBIGUOUS` / `CONFLICTING` / `UNSUPPORTED` per FR-082. Do not widen the
  vocabulary to make a test pass.
- Known-failure discipline: the 16 baseline failures (2 control-plane donor, 14 shared) are not
  to be fixed, hidden, or counted as progress.
