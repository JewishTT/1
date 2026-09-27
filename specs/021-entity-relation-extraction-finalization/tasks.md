# Tasks: 021-entity-relation-extraction-finalization

**Input**: Design documents from `specs/021-entity-relation-extraction-finalization/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md` — all present
**Tests**: MANDATORY. §108 makes tests the only acceptable proof, so every phase below carries
test tasks and they are written before the implementation they cover.

## Authority order for this file

1. `repair/ARBITRATION.md` — **binding**. §3 fixes the three epistemic axes, §4 fixes `TEMPORAL`,
   §5 fixes the phase DAG, §6 fixes n-ary persistence, §8 fixes the naming, §10 fixes the four
   count words, §11 fixes `SC-001`, §14 fixes the FR bands.
2. `repair/A6-fr-triage.md` §5, the renumbering plan — the task content: 94 tasks, `T101`…`T194`,
   every task with at least one FR.
3. `repair/A8prep-ownership-and-dag.md` §O3 — placement, entry/exit conditions, the `[P]` rule.
4. `repair/A1`, `A2`, `A4b`, `A5`, `A7` — the requirement bodies this file cites.

Where a lower-authority document disagrees, the higher one wins and the override is noted in place.

## Format

`- [ ] Tnnn [P]? [USn] (FR-…) description | needs: … | files: …`

- **Task id** is `T` plus three digits: no letter suffix, contiguous, ascending in document order.
  That grammar makes the letter-suffixed phantom class unrepresentable, and it is why no task here
  may be referenced by a sub-lettered id from any artefact. For the same reason this file does
  **not** cite the pre-repair task ids: they are no longer defined, and citing them would
  reintroduce the very phantom this grammar closes. Pre-repair tasks are named by what they did.
- **The FR list is on the first line of the bullet, immediately after the story tag**, because that
  is the unit the reference checker reads. A citation on a continuation line is invisible to it.
- **Phase** is a header, not a field in the id.
- **`[P]`** means *different files, no dependency*. Two rules make it falsifiable rather than
  decorative: at most one task per file per phase, and no `[P]` task's write set is read by another
  task in the same phase. A task that shares a file with another task in its phase is **ordered and
  not `[P]`**, and the task line says so.
- **`needs:`** is the edge list. Every edge points at the same or a lower phase. The one exception
  is the declared `red→green:` edge, and it is declared as such on both ends.
- **`files:`** is the exact write set. It is what makes `[P]` checkable.
- **FR** is `FR-` plus three digits, from the original `FR-001`…`FR-100` set (unchanged,
  ARBITRATION §1) or from one of the §14 bands. Nothing else is cited and no task invents a
  number: the two ranges that §1 left void and the one that §14 left deliberately reserved are named
  in prose and never written as a citation.

## Phase DAG

One notation only: `P4A` / `P4B` / `P4C`. The lowercase spelling never appears in this file.

```text
P0 → P1a → P1b → P2 → P3 → P4A → P4B → P4C → P5 → P6 → P7 → P8 → P9
```

`P1a` and `P1b` sit inside the single phase `P1`, so the file has twelve phase headers: `P0`, `P1`,
`P2`, `P3`, `P4A`, `P4B`, `P4C`, `P5`, `P6`, `P7`, `P8`, `P9`.

**Why Phase 4 is three-way.** A8prep measured Phase 4's real breakage as **two** breaking lines
(`assembly.py:219`, `signal.py:394`), not twelve enum references. So `P4A` is **additive only**: it
introduces the variadic `participants` field, `Polarity`, `SignalAspect` and `SignalBasis` *without*
removing the binary columns or any `SignalKind` member, and it is committable green on its own.
`P4B` migrates the seven `RelationSignal(` construction sites in one commit and carries §110-6's
producer corrections. `P4C` performs the deletions together with their call-site migrations. That
split is the whole reason the sequence is committable.

## Why the ids are renumbered

A6's renumbering plan gave every phase a contiguous id block, which only works if the phase order is
monotone in the id space. ARBITRATION §5's DAG is **not**: it merges the signature phase into P1,
ahead of the type-vocabulary and mention-binding phases that A6 numbered in between. Applying §5
literally to A6's id table would put the candidate-identity task on the page before the type pack.

The resolution is mechanical and lossless: **the 94 tasks and the `T101`…`T194` range are kept, and
the ids are re-assigned in execution order**, so document order is ascending and every `needs:` edge
points backwards. The alternative — publishing a file whose bullets run out of numeric order — is the
very defect the reference check exists to catch. Each task's content, its phase and its FR citations
are what A6 assigned; only the label moved. A6 owns task content; the numbering *grammar* is what
§5's phase order constrains.

---

## Phase P0 — Spec / constitution / traceability (gate; no production code)

**Entry**: all seven `repair/A*.md` files exist and are non-empty.
**Exit**: the baseline floor is frozen in a file of its own; the head migration is confirmed
forward-only; the parser digest is pinned; the gate checklist is rebuilt with an FR column and a
`Task` column naming only ids that exist in this file.
**Tasks**: 4. **§110**: an added phase, authorised by §107 and §108, which require the baseline and
the acceptance gate but enumerate no phase for them.
**File rule**: the baseline recorder writes `repair/baseline-021.md` and the checklist creator writes
`checklists/requirements.md`, so the two no longer share a file — the defect the old collision
carried. The latter three tasks each depend on the baseline, so none of them is `[P]`.

- [ ] T101 [P] [US1] (FR-081) Re-run and record the full baseline for the six suites into
  `repair/baseline-021.md`: `uv run --project apps/<app> pytest apps/<app>/tests -q` for shared,
  control-plane, interpretation, projection, admission and acquisition. Expected floor:
  control-plane 2 failed (`test_donor_api`), shared 14 failed. If the numbers differ from
  `research.md` R-000, stop and report before touching code.
  | needs: — | files: repair/baseline-021.md
- [ ] T102 [US8] (FR-097, FR-157) Confirm the Alembic head is `020_universal_relation_extraction`,
  that `020` is forward-only and never edited, and that a `downgrade()` raises
  `NotImplementedError` **before emitting any operation** — the same refusal shape `021` must use,
  because a downgrade that drops some objects and then refuses leaves a database matching no
  revision.
  | needs: T101 | files: tests/unit/test_migration_head_020.py
- [ ] T103 [US8] (FR-043) Pin the parser baseline for R-001: capture a tree-construction digest per
  HTML fixture with `selectolax` into `repair/parser-digest-021.md`, so a later diff is a
  deliberate, visible change rather than drift.
  | needs: T101 | files: repair/parser-digest-021.md
- [ ] T104 [US1] (FR-083, FR-115, FR-168, FR-173) Rebuild `checklists/requirements.md` from the
  repaired set: one primary row per requirement `spec.md` defines, a populated FR column, a `Task`
  column naming only ids that exist in this file, and the `Method` key expanded from its five
  letters. It reads the counts T101 froze. The gate itself must run unattended rather than depend
  on someone remembering, and every constitutional citation in the changed files must name the
  correct numeral.
  | needs: T101 | files: checklists/requirements.md

---

## Phase P1 — Identity + `PredicateSignature` + `RoleSignature`

**Entry**: P0 exit. **Exit**: the identity function's declared parameters are honest; the signature
exists with a specified `normalize_voice` and a specified canonical participant ordering; one
`logical_candidate_id` is **derived** for active and passive realisations.
**Tasks**: 10. **§110**: `§110-1` merged with `§110-5`.

**The 1a/1b commit split is mandatory, not optional.** §110 orders identity cleanup *before* the
signature, with phases 2, 3 and 4 in between; the mandated structure places them together. Both are
honoured only if the phase carries an internal commit boundary: **1a is `§110-1` and is committable
and green on its own**; **1b is `§110-5`**. The phase has one entry condition and one exit
condition. `T110`→`T112` is the declared `red→green:` edge, and it is the mechanism that replaces the
old backwards edge: a Phase-1 identity task used to depend on a Phase-3 mention-index task that had
not been written yet. The identity test is now written **red** in 1a and turned **green** in 1b, so
the edge is legitimate and the cycle is gone.

### P1a — identity / domain contract cleanup (§110-1)

- [ ] T105 [P] [US1] (FR-085) Canonicalise `signal_refs` on construction in
  `relation_candidate.py`, matching `observation_refs` and `evidence_refs`. Test: two candidates
  with the same signals in a different input order get the same `candidate_id`.
  | needs: — | files: apps/shared/domain/relation_candidate.py, tests/unit/test_candidate_id_order.py
- [ ] T106 [US8] (FR-086) Add `to_dict()` and `from_dict()` to `RelationCandidate`, round-tripping
  every field the type declares at the time of the change and every field the persistence columns
  add, asserted by field list and not by a summary string. It shares `relation_candidate.py` with
  T105, so it is ordered after T105 and is not `[P]`.
  | needs: T105 | files: apps/shared/domain/relation_candidate.py
- [ ] T107 [P] [US8] (FR-098) Reconcile `verify_candidate_material_partition()`: call it and make
  it correct, or delete it. `CANDIDATE_LOGICAL_MATERIAL_FIELDS` declares `relation_type` where the
  code emits `relation_surface`.
  | needs: — | files: apps/shared/domain/candidate_material_partition.py, tests/unit/test_material_partition_verifier.py
- [ ] T108 [P] [US2] (FR-099) Make `RelationClaim` re-derive and check its own carried
  `relation_id`, as candidates, materials and temporal observations already do; a forged id is
  refused.
  | needs: — | files: apps/shared/domain/relation_claim.py
- [ ] T109 [P] [US2] (FR-002) Remove the dead `valid_from` and `valid_to` kwargs from
  `logical_material()` and `logical_relation_id()`, or make them load-bearing. Today they are
  declared, passed by both callers and never read, which is what makes the identity function's
  declared parameters dishonest.
  | needs: — | files: apps/shared/domain/relation_identity.py
- [ ] T110 [US1] (FR-001, FR-177) **RED** identity-property test, written here and expected to fail:
  active and passive realisations of one relation share one `logical_candidate_id`, and nothing
  else moves it. The test carries an `xfail(strict=True)` marker whose reason is
  `syntactic_producer_absent`; the marker is owned by **T133**, and the unit-level turn to green
  happens at **T112**.
  | needs: — | red→green: T112 | files: tests/unit/test_identity_property_red.py

### P1b — signature, `RoleBinding` and candidate identity (§110-5)

- [ ] T111 [US1] (FR-003, FR-004, FR-174, FR-175) Create
  `apps/shared/domain/predicate_signature.py`: `PredicateSignature` with its seven-field set and its
  exclusions, its own `content_key()`, `normalize_voice()`, and the ordered steps `V0.validate` …
  `V6.arity` run against a versioned construction table whose rows are the eight constructions §29
  names plus two added rows, each added for a stated necessity. One named test per rule. A synonym
  or equivalence table never enters identity material.
  | needs: — | files: apps/shared/domain/predicate_signature.py (NEW)
- [ ] T112 [US2] (FR-002, FR-175, FR-176, FR-178) Key logical identity on the signature.
  `canonical_participant_ordering()` runs **inside** the identity function and never at a call
  site: subject before object for a `DIRECTED` reading, by the signature's normalised role name then
  participant ordinal for `NARY`, by the signature's canonical subject and object slots for
  `UNDIRECTED`, never by input order and never by `min` or `max` of a raw ref. `role_bindings` are
  part of the signature's identity contribution and are voice-normalised, so
  `"Acme was acquired by John"` reaches the same material without ontology mapping. No temporary
  fallback. **This task turns T110 green.**
  | needs: T111 | red→green: T110 | files: apps/shared/domain/predicate_signature.py, apps/shared/domain/relation_identity.py
- [ ] T113 [US1] (FR-001, FR-005, FR-177, FR-178) Derive `logical_candidate_id` from the normalised
  signature and the canonically ordered participant configuration, with no `relation_surface` term
  and no call-site sort, and with no mapping field, `RelationRef`, confidence, capture, producer or
  observation timestamp participating. A surface-variant pair must reach the same signature
  **through the derivation**, never through a fixture.
  | needs: T112 | files: apps/shared/domain/relation_identity.py
- [ ] T114 [US1] (FR-001, FR-007) Confirm a `relation_surface` change creates a `candidate_id`
  revision and never a new logical id, and that the candidate partition stays two-level (`CAND-` and
  `CNDR-`) with no fourth epistemic level.
  | needs: T113 | files: apps/shared/domain/relation_candidate.py

---

## Phase P2 — Type vocabulary + `TypeHypothesis` substrate

**Entry**: P1 exit. **Exit**: the shipped pack manifest matches the artefact byte for byte; an
unmapped type survives as `UNKNOWN` with zero mentions dropped; `Apple` retains three or more
hypotheses and selects none; an external structured statement yields a signal plus a mapping record
and never an assertion; the seven §8 extraction families have producers.
**Tasks**: 10. **§110**: `§110-2` plus the type-hypothesis half of `§110-3`.
**File rule**: `blocking.py` is written by T120, T121, T122 and T123, so "at most one task per file
per phase" makes those four ordered, and only T116 and T117 keep `[P]`.

- [ ] T115 [US4] (FR-029, FR-030, FR-031, FR-034, FR-110, FR-137) Create
  `apps/shared/semantic/type_vocabulary.py`: the versioned pack `core-atomic-types@1` with its
  **31** named entity types and its **13** named value types, loadable with a pinned `version`, and
  a shipped manifest matching the artefact byte for byte. `kind` is a required, non-defaulted
  discriminator read from the entry and never inferred from the ref, so `core:Coordinate` and
  `value:Coordinate` stay two distinct refs in two namespaces and a consumer never receives a value
  ref where an entity is required. The type space is extensible by hierarchy, and that expansion is
  never a gate. Dispose of the ontology pack's relation list at the same time: `relations`,
  `allows_relation()` and the `relations` key in `to_dict()` are deleted, while `allows_type()`
  remains and remains advisory.
  | needs: — | files: apps/shared/semantic/type_vocabulary.py (NEW)
- [ ] T116 [P] [US4] (FR-035, FR-134) Produce a `TypeSignal` — never a `TypeAssertion` — from every
  structured or external-vocabulary statement: JSON-LD, schema.org, OpenGraph, RDFa, microdata and
  HTML metadata, carrying `source_vocab`, `surface` and `mapping_candidates` (which may legitimately
  be empty) plus `mention_ref`, `structural_path`, `observation_refs`, `evidence_refs`,
  `producer_ref` and its own `signal_id`. `source_vocab` is an external vocabulary reference **or
  `null`**: no synthetic vocabularies are introduced to avoid a `null`, and a detector that reads no
  vocabulary is legal precisely because the field is nullable.
  | needs: T115 | files: apps/interpretation/extractors/types.py
- [ ] T117 [P] [US4] (FR-036, FR-135, FR-136) `TypeMapping` is the existing
  `semantic.mappings.SemanticMapping` — no parallel dataclass. Ship the initial mapping set §64
  names, each an explicit record carrying subject and object type, mapping predicate, mapping set
  and set version, mapping version, confidence, creator, justification and evidence provenance,
  content-addressed, citable, tenant-scoped at the write and superseding rather than replacing. A
  non-equivalence match is recordable as such, and no mapping collapses without a mapping record.
  | needs: T115 | files: apps/shared/semantic/mappings.py
- [ ] T118 [US4] (FR-140, FR-141, FR-142, FR-143, FR-144, FR-145, FR-146, FR-147, FR-179) Complete
  the deterministic entity extraction layer **by adapting the existing extractors** rather than
  duplicating them into a second framework, across the **seven §8 extraction families** and their
  subsections. **A.** person — Latin, Cyrillic, initials, multi-token, titles, contextual cues,
  aliases, transliteration, Unicode normalisation and surname-first patterns, where a name-shaped
  string never implies person. **B.** organization — legal forms, corporate suffixes, institutional
  names, brands, agencies, universities, government bodies, media, banks, companies and NGOs, always
  hypothesis and never `entity = organization`. **C.** WebSite / WebPage / Domain / URL —
  deterministic extraction of `https://example.com`, `example.com` and `www.example.com`, kept
  distinct, where a URL string is a value, a WebPage a resource, a WebSite a higher-level resource
  and a domain a namespace. **D.** OnlineAccount / SocialProfile — structured profile URLs and
  handles, where account identity is never inferred from a display name. **E.** digital identifiers
  — IP, hash, CVE, crypto address, file path and identifier, as value-type hypotheses. **F.**
  documents — URLs pointing to files, filenames, document ids, report-like structures, citations and
  title/identifier structure. **G.** event mentions — conference, meeting, acquisition, launch,
  publication, incident, transaction, election and appointment, where an event mention is not a
  relation and never becomes a claim. Every result is a hypothesis. The acceptance test is
  **renamed** to `test_entity_extractor_covers_all_seven_extraction_families`: "classes" is the
  wrong word, because there are 31 entity classes and 7 extraction families, and the wrong phrase
  becomes a 32-extractor mandate within two weeks.
  | needs: T117 | files: apps/interpretation/extractors/entity_instruments/ (NEW), tests/integration/test_entity_extraction_families.py
- [ ] T119 [US7] (FR-083, FR-167) Record ADR **B**
  (entity and value type vocabulary is separate from relation vocabulary) and ADR **L** (the
  `PredicateSignature` normalisation rule set, including any synonym table, is versioned, sourced
  and reviewable). ADR **L** exists because governance requires an ADR for any
  entity-resolution-grade decision and the earlier A–K set had no slot for the synonym table. An
  entry that cannot be justified from a source is dropped and the predicate stays `AMBIGUOUS` rather
  than guessing.
  | needs: T118 | files: specs/021-entity-relation-extraction-finalization/adr/adr-B.md, adr-L.md
- [ ] T120 [US4] (FR-032, FR-033, FR-148, FR-149) `TypeHypothesis` is exactly **one** interpretation
  candidate with its declared field set and its six states, and the **set** of competing hypotheses
  belongs to the mention, never to the hypothesis. Test: `Apple`, `Amazon`, `Jordan`,
  `Washington` and `Mercury` each retain three or more and none is silently selected.
  | needs: T115 | files: apps/shared/semantic/blocking.py
- [ ] T121 [US4] (FR-037, FR-038, FR-111) Run the type pipeline
  `Observation → Mention → TypeSignal → TypeHypothesis → SemanticRegime → TypeAssertion`; a later
  `INFERRED` is a **new revision** and every prior state stays retrievable, with the write reading
  back a `TypeHypothesis` in state `UNKNOWN` and surviving a store round trip. An ontology miss
  means *unknown type*, never a rejected mention, and zero mentions are dropped for it.
  | needs: T120 | files: apps/shared/semantic/blocking.py, apps/shared/semantic/type_assertion.py
- [ ] T122 [US4] (FR-039, FR-112) Consume the bounded structural neighbourhood for type resolution
  — document title, section heading, DOM parent, table heading, neighbour mentions, URL and domain,
  metadata and language — **by reference to a named, bounded neighbourhood**, never by a document
  sweep, and represent competing hypotheses with evidence rather than encoding a universal
  deterministic truth rule.
  | needs: T120 | files: apps/shared/semantic/blocking.py
- [ ] T123 [US4] (FR-112) Make a
  mention's type hypotheses and a relation signal's role hypotheses mutually consumable, for
  resolution and for blocking, and keep the hints hints: no role hint may become truth and no role
  hint may enter identity material.
  | needs: T120, T126 | files: apps/shared/semantic/blocking.py
- [ ] T124 [US4] (FR-035, FR-037) Contract test for the type pipeline: the declared order is
  enforced, an unmapped type is retained as `UNKNOWN`, and an external structured statement yields a
  signal plus a mapping record and never an assertion.
  | needs: T121, T126 | files: tests/unit/test_type_pipeline_contract.py (NEW)

---

## Phase P3 — Mention binding / occurrence index

**Entry**: P2 exit; may start alongside P2's last task, which touches a different file.
**Exit**: `MentionOccurrenceIndex` resolves deterministically on the full lookup tuple; it is the
sole minter; every `participant.mention_ref` a producer emits resolves; a non-mention value yields a
typed deferred reference and mints nothing; no synthetic mention-ref prefix survives in producer
code. **Tasks**: 2. **§110**: the mention-binding half of `§110-3`.

- [ ] T125 [US3] (FR-018) Create `apps/interpretation/mention_index.py`:
  `MentionOccurrenceIndex`, the **sole minter** of `MN-…` identifiers, with deterministic lookup on
  the full tuple — capture, segment, offset or span, normalised surface and extractor occurrence —
  because omitting `capture` makes two captures of one segment collide onto one id.
  `MENTION_BINDING` is the **stage**, `MentionOccurrenceIndex` is the **structure**, `MN-…` is the
  **id** form; there is no third data-model object and no fourth spelling. Lookup resolves to a
  mention, never to an entity.
  | needs: — | files: apps/interpretation/mention_index.py (NEW)
- [ ] T126 [US3] (FR-016, FR-017) Wire the index into the extraction scope so every producer
  receives a resolver, and assert — by iterating every producer's real output, not by inspection —
  that each `participant.mention_ref` resolves. A non-mention value yields the structural raw slot
  plus a typed **deferred** reference, never a synthesised id.
  | needs: T125 | files: apps/interpretation/extractors/signals/protocol.py, apps/control-plane/semantic_path/execution.py

---

## Phase P4A — additive structural contract

**Entry**: P1 exit. **Exit**: `RelationSignal` carries a variadic `participants` tuple with the
binary columns surviving as derived accessors, a closed two-member `Polarity`, a required typed
`observational_basis` over the nine-member `SignalBasis`, and a separate `SignalAspect`; **all
seven construction sites still run unchanged and nothing has been removed**. **Tasks**: 4.
**§110**: `§110-4`, additive half.

**This phase removes nothing.** That is the property that keeps the sequence committable, and it is
why every enum-member and constructor-parameter deletion lives in P4C together with its own
call-site migration. A breaking task may not have a dependent in a later phase.

- [ ] T127 [US7] (FR-008, FR-009, FR-010) `RelationSignal` gains
  `participants: tuple[RelationParticipant, …]`, variadic, 2..N, with the participant's
  `mention_ref`, `slot`, `role_hypothesis`, `ordinal` and `confidence` typed, and with every
  load-bearing dimension the signal contract names typed rather than JSONB. The two binary columns
  survive as **derived compatibility accessors** computed from `participants[0]` and
  `participants[1]`, and are still accepted as constructor parameters, deprecated, for one phase of
  grace. No fake binary decomposition. Additive only.
  | needs: — | files: apps/shared/domain/relation_participant.py (NEW), apps/shared/domain/relation_signal_parts.py (NEW)
- [ ] T128 [P] [US7] (FR-015) Add `Polarity` with the closed two-member domain
  `Polarity.{ASSERTED, DENIED}` as an explicit, required field on every signal and every candidate.
  Uncertainty is not a third polarity: it is `TypeHypothesis.hypothesis_state` for types and
  `PredicateHypothesis.resolution_state` for predicates. A denied relation keeps its predicate
  surface and its signature, is storable and queryable, and yields no positive candidate and no
  edge. Additive only.
  | needs: — | files: apps/shared/domain/polarity.py (NEW)
- [ ] T129 [US7] (FR-011, FR-012) Split the orthogonal aspects out of `SignalKind` into a separate
  `SignalAspect` value carried by `RelationSignal`, with exactly the field mapping the requirement
  names and no other, plus a structural test that fails on any `SignalKind` member naming an aspect.
  **Keep `TEMPORAL` as a `SignalKind` member**: it names the provenance channel — *this signal is
  based on a temporal observation* — and carries no temporal payload and no time of its own, because
  the temporal facts live in `SourceTemporalObservation` and in the signal's `temporal_evidence`.
  `SignalKind` is an observation channel, never a container of an aspect, and that
  channel-versus-content division is exactly what stops it becoming an unstructured dumping ground.
  Additive only: new members are added here and nothing is removed. It shares `signal.py` with
  T127, so it is ordered after T127 and is not `[P]`.
  | needs: T127 | files: apps/interpretation/extractors/signals/signal.py
- [ ] T130 [P] [US7] (FR-014, FR-151) Add `observational_basis` as a required, typed field on every
  `RelationSignal`, drawn from the closed nine-member `SignalBasis` enumeration. A signal with no
  basis fails construction, and a new basis is an explicit extension with a version bump, never a
  free string. Additive only.
  | needs: — | files: apps/shared/domain/signal_basis.py (NEW)

---

## Phase P4B — producer migration and producer corrections

**Entry**: P4A exit. **Exit**: the seven construction sites construct from `participants=` with
unchanged semantics; every producer family in §110-6's list is corrected; the completeness marker
resolves; the cross-producer bans hold as AST and import-graph tests. **Tasks**: 17.
**§110**: the `RelationSignal(` construction-site migration of `§110-4`, plus all of `§110-6`.

**The seven-site migration is one commit, and it is the first task of this phase.** That is the
whole content of "7 construction sites, one commit": the migration and its removal counterpart now
sit in the same phase, so the phase boundary is never crossed mid-break. The eight new producer
files keep `[P]`; the five migrated producer files do not, because T131 reads them in this same
phase.

- [ ] T131 [US3] (FR-008) Migrate the seven `RelationSignal(` construction sites —
  `signal_corpus.py:117`, `execution.py:2824`, `tables.py:165`, `tables.py:261`, `lexical.py:169`,
  `links.py:209` and `metadata.py:397` — to `participants=(…)` in **one commit**, changing no
  producer's semantics. Mention-ref resolution is deliberately not this task: it needs the index
  from T125 and T126 and belongs to the producer corrections below.
  | needs: T130 | files: extractors/signals/lexical.py, links.py, tables.py, metadata.py, semantic_path/execution.py, semantic_path/signal_corpus.py
- [ ] T132 [P] [US5] (FR-043, FR-071) Pin parser capability — `model_ref`, `model_version`,
  `parser_version` and `configuration_hash` — keep every LLM out of the constitutional extraction
  path, and make a missing parser mean *no syntactic signals*, never a batch failure. A named test
  runs the full production batch with the capability unavailable and asserts exit success, at least
  one non-empty lexical signal and at least one candidate. Every signal also states a real
  neighbourhood class as a typed field, never a substring inside a human-readable `precision`
  string.
  | needs: T131 | files: apps/interpretation/extractors/signals/neighbourhood.py (NEW), apps/interpretation/extractors/signals/parser_provenance.py (NEW)
- [ ] T133 [P] [US2] (FR-042, FR-175) The syntactic producer: every construction the table names
  emits a `PredicateSignature` carrying its own frame, the output frames are pairwise distinct except
  where the table says otherwise, and the producer emits no operator the mapping layer did not say.
  **This task owns the `xfail → green` transition for `SC-001`.** It removes the
  `xfail(strict=True)` marker whose reason is `syntactic_producer_absent`, and no wave may report
  `SC-001` as passing while that marker is still present.
  | needs: T132 | files: apps/interpretation/extractors/signals/syntactic.py (NEW)
- [ ] T134 [US5] (FR-041, FR-093) Upgrade the lexical producer to emit signature, roles, direction
  and declared arity; delete `surface:role:*`; make the dead `MAX_PAIRS_CONSIDERED` live or delete
  it; and report a real `candidate_pairs_considered` — the fabricated divisors `scanned // 16` and
  `scanned // 32` are gone, a producer that enumerates no pair reports `0` **with a stated
  reason**, and `max_pairs_considered` is a live ceiling a real violation can exceed.
  | needs: T132 | files: apps/interpretation/extractors/signals/lexical.py
- [ ] T135 [P] [US3] (FR-044) The structural producer represents `structural_path` and never
  flattens structure into a predicate.
  | needs: T132 | files: apps/interpretation/extractors/signals/structural.py (NEW)
- [ ] T136 [US3] (FR-045) The link producer preserves source mention, target mention, href, anchor
  text, DOM path, link position, the `rel` attribute and target metadata, and asserts only "A links
  to B" — never `cites`, `owns`, `hosts` or `employs`. One anchor yields one signal that counts
  once: two signals over one anchor that differ only in `kind` share a `producer_ref` and never
  count as two independent corroborations.
  | needs: T132 | files: apps/interpretation/extractors/signals/links.py
- [ ] T137 [P] [US3] (FR-046) The reference and citation producer covers the six forms §46 names and
  never emits `cites`.
  | needs: T132 | files: apps/interpretation/extractors/signals/reference.py (NEW)
- [ ] T138 [US3] (FR-047, FR-093) The table producer preserves `table_ref`, `row_ref`, `header_ref`,
  `cell_ref` and `participant_ref`, treats a row as structural evidence for an n-ary configuration,
  refuses or skips a malformed table by explicit structural rule and never guesses positionally, and
  reports a live ceiling for its pair count.
  | needs: T132 | files: apps/interpretation/extractors/signals/tables.py
- [ ] T139 [US3] (FR-048, FR-095) The list producer handles term and item structure without creating
  a semantic relation, makes the row `zip` strict so a `<dt>` term is never silently dropped, emits a
  note or a signal for a width-mismatched row, and makes `is_exhaustive` read a typed field rather
  than a substring of a `precision` string. `tables.py` holds both the table instrument and the list
  instrument, so T138 and T139 are ordered and neither is `[P]`.
  | needs: T138 | files: apps/interpretation/extractors/signals/tables.py
- [ ] T140 [US3] (FR-049, FR-094) The metadata producer resolves real mention refs: the `attribute:`
  and `jsonld:` property-name subjects are deleted, because a field name is not a participant; the
  `document:current` fallback becomes a required `document_ref`; 64-character truncation becomes a
  full content address; and unrecognised metadata survives.
  | needs: T132 | files: apps/interpretation/extractors/signals/metadata.py
- [ ] T141 [P] [US3] (FR-050) The attribute producer represents `Key: value` — a value is not an
  entity — and distinguishes the three arrow kinds.
  | needs: T132 | files: apps/interpretation/extractors/signals/attribute.py (NEW)
- [ ] T142 [P] [US6] (FR-051) The temporal producer attaches the temporal expression as evidence
  with its surface, interval, precision and span, and emits `SignalKind.TEMPORAL` as the **channel**
  while the facts themselves land in `SourceTemporalObservation` and `temporal_evidence`: a
  `TEMPORAL` kind states provenance and carries no time of its own.
  | needs: T132 | files: apps/interpretation/extractors/signals/temporal.py (NEW)
- [ ] T143 [P] [US7] (FR-052) The event producer supports n-ary and never reduces the sale sentence
  to two binary edges at substrate level.
  | needs: T132 | files: apps/interpretation/extractors/signals/event.py (NEW)
- [ ] T144 [P] [US5] (FR-053) The co-occurrence producer reports adjacency and never produces
  `related_to`; proximity with no predicate words is representable.
  | needs: T132 | files: apps/interpretation/extractors/signals/co_occurrence.py (NEW)
- [ ] T145 [P] [US5] (FR-054) The semantic producer creates interpretation candidates only; an
  ontology match is never automatic truth.
  | needs: T132 | files: apps/interpretation/extractors/signals/semantic.py (NEW)
- [ ] T146 [US5] (FR-040) The completeness marker: every channel the producer requirement names is
  either implemented or carries an explicit `UNSUPPORTED` marker with a reason. "Universal" means a
  common observation language, not an unbounded extractor count, and silence is never an
  implementation.
  | needs: T133, T135, T136, T137, T138, T140, T141, T142, T143, T144, T145 | files: apps/interpretation/extractors/registry.py
- [ ] T147 [US3] (FR-006, FR-019, FR-020, FR-074) The cross-producer bans, as AST and import-graph
  tests rather than greps: no producer imports **or constructs** `GraphEdge`, `HyperEdge`,
  `GraphStore`, `RelationClaim`, the `admission` package or the `projection` package, and
  `TYPE_CHECKING` is the only permitted reference and never appears in executable code; zero `ENT-`
  and `RES-` literals exist in producer code; the enumerated synthetic mention-ref prefixes return
  zero hits; no extraction path calls `allows_type()` in a drop or deny position, and no
  relation-extraction path guards on an unrecognised relation; `signal_id` stays producer-specific
  and its independence is measured over the producer family. It comes strictly after T132–T146,
  because it asserts across all of them, so it is ordered rather than `[P]`.
  | needs: T146, T126 | files: apps/interpretation/tests/integration/test_producer_bans.py

---

## Phase P4C — enum / lifecycle / corpus cleanup

**Entry**: P4B exit. **Exit**: the aspect-named members and the deprecated binary constructor
parameters are gone, the two breaking lines are migrated in the same commit as the deletion, the
n-ary sale passes end to end, and the empty-surface co-occurrence is constructible, persistable and
assemblable. **Tasks**: 2. **§110**: `§110-4`, deletion half.

**Where the CHECK-constraint drops go.** A domain `CHECK` cannot be dropped before the code that
writes its replacement column exists, and A7's ordering constraint puts `021` after
`PredicateSignature`, `Polarity` and `SignalBasis` do. So P4C makes the **domain** side honest and
the **DDL** side follows in T167, which executes as P8's entry gate. This phase therefore does not
touch the database, and the two `*_asserts_something` constraints and the stale
`ck_relation_signal_kind` whitelist are dropped by the migration, not here.

- [ ] T148 [US6] (FR-011, FR-012) Remove the aspect-named members from `SignalKind` and remove the
  deprecated binary constructor parameters, migrating the two breaking lines — `assembly.py:219`
  and `signal.py:394` — **in the same commit as the deletion**, together with the lifecycle and
  corpus call sites. `TEMPORAL` is **kept**: it is a channel, and its whitelist entry is recreated
  by migration `021`. A `SignalKind` member naming an aspect fails the structural test.
  | needs: T129, T131 | files: extractors/signals/signal.py, semantic_path/assembly.py, semantic_path/execution.py, semantic_path/signal_corpus.py
- [ ] T149 [US7] (FR-013, FR-089) The signal contract tests: the n-ary sale constructs, persists
  and assembles; a `CO_OCCURRENCE` with an empty `relation_surface` and a `None`
  `predicate_signature` is constructible, persistable and assemblable, while a kind that does assert
  a predicate is still refused — with the domain-side check as the named module constant
  `SIGNAL_ASSERTS_NOTHING`, a value and not a function; and a change in declared arity changes the
  `signal_id`, because `_material()` now carries `predicate_signature`, `polarity`, declared arity
  and role names while `producer_ref` stays.
  | needs: T127, T129, T131, T148 | files: apps/interpretation/tests/unit/test_signal_contract.py (NEW)

---

## Phase P5 — candidate assembly

**Entry**: P4C exit. **Exit**: there is no voting path; a structural disagreement lands on
`assembly_state`, a semantic disagreement on `resolution_state`, and never a structural one on
`CONTRADICTED`; grouping preserves direction, polarity, signature, signal refs and alternatives; and
one signal becomes a candidate by exactly one route. **Tasks**: 8. **§110**: `§110-7`.

**File rule**: `assembly.py` is written by T152, T153, T154 and T155, and `predicate_hypothesis.py`
by T150 and T154, so only T151 and T157 keep `[P]`.

- [ ] T150 [US1] (FR-021, FR-022) Give `PredicateHypothesis` a real `normalized_form` normaliser,
  its declared field set and its four states, with no `UNKNOWN_RELATION` and no fabricated
  `RelationRef`: `relation_ref = None` with a full signature is legal and is the norm. A signal that
  maps to a known operator becomes typed only through explicit regime interpretation.
  | needs: T111 | files: apps/shared/domain/predicate_hypothesis.py
- [ ] T151 [P] [US1] (FR-023, FR-024) The unknown-predicate case end to end: signal → candidate →
  preserved surface → normalised predicate → signature → `relation_ref = None` → `UNKNOWN` → no
  claim → no edge, with every evidence item still retrievable and all seven answerable questions
  still answerable.
  | needs: T150 | files: tests/integration/test_unknown_predicate_end_to_end.py (NEW)
- [ ] T152 [US5] (FR-025) Carry the signature from signal into candidate, preserving direction,
  polarity, declared arity, role names and every signal ref.
  | needs: T113 | files: apps/control-plane/semantic_path/assembly.py
- [ ] T153 [US2] (FR-026, FR-090) Delete the majority vote and the alphabetical tie-break from
  `_arity_of()` and change its `-> Any` to `-> RelationArityMode`. No voting path survives; a
  declared `NARY` schema is never downgraded to `DIRECTED`, and losing a vote never drops role
  bindings.
  | needs: T152 | files: apps/control-plane/semantic_path/assembly.py
- [ ] T154 [US7] (FR-028, FR-130, FR-132, FR-133) Two signals whose signatures agree but whose
  mapping candidates name different `target_relation_ref`s yield **one** candidate carrying one
  hypothesis with `resolution_state=AMBIGUOUS`, at least two entries in `mapping_candidates` and both
  readings preserved; a hypothesis whose competing readings came from **disagreeing evidence**
  carries `resolution_state=CONFLICTING` with `mapping_evidence_refs` naming the `signal_id` on
  each side; two differing signatures are two candidates, never one ambiguous hypothesis. A
  disagreement over arity, direction, polarity or role bindings for one participant configuration
  is a structural reading, so it yields
  `RelationCandidate.assembly_state = CandidateAssemblyState.CONFLICTING` with both readings kept,
  reported in `AssemblyReport`. `CandidateStatus.CONTRADICTED` is reserved for a positive reading
  set against an explicit denial, and it must never carry that structural reading.
  `PredicateMappingCandidate` is a frozen value object with its own `content_key()`, `with_id()` and
  lossless round trip.
  | needs: T153 | files: apps/shared/domain/predicate_hypothesis.py, apps/control-plane/semantic_path/assembly.py
- [ ] T155 [US5] (FR-025, FR-027) Group by structural participant configuration, preserving
  direction, polarity, signature, all signal refs and alternative interpretations; detect conflicts;
  resolve no entity, admit no claim and create no `GraphEdge`. Distinct predicates over the same
  endpoints stay distinct hypotheses, so equal endpoints never merge.
  | needs: T153 | files: apps/control-plane/semantic_path/assembly.py
- [ ] T156 [US5] (FR-091) Remove `RelationalReading.to_candidate()`, or reduce it to a call into the
  assembler, so "how does a signal become a candidate" has exactly one answer in the code and not
  only in a docstring.
  | needs: T155 | files: apps/interpretation/extractors/relations.py
- [ ] T157 [P] [US5] (FR-025) The assembly contract test: lexical, table and structured-metadata
  producers over one participant configuration produce one logical candidate carrying many signals,
  and a different reading produces a different one.
  | needs: T152, T155 | files: tests/integration/test_assembly_contract.py (NEW)

---

## Phase P6 — claim material / validation / admission

**Entry**: P5 exit. **Exit**: materialisation, validation, admission and projection are separately
observable; the `ValidationReport` that gated admission is retained and readable after the run; the
post-admission re-validation is gone; the admission decision gates the store write; and production
writes are not doubled. **Tasks**: 7. **§110**: the material, validation and admission half of
`§110-8`.

**File rule**: all seven tasks write `semantic_path/execution.py`, so "at most one task per file per
phase" makes them a strict chain and **none of them is `[P]`**. The old lifecycle-docstring
collision — one task correcting the docstrings that four sibling tasks were changing — is resolved by
ordering, not by a marker, and the docstring task is last.

- [ ] T158 [US8] (FR-055, FR-083) Assert the lifecycle as a **partial order** and record `REGIME`'s
  position as an open decision for `plan.md`, answered by an ADR before the projection phase. The
  brief places `REGIME` in three incompatible positions, so this task fixes only the precedence
  constraints all three agree on, and no test may assert a total stage order.
  | needs: — | files: apps/control-plane/semantic_path/execution.py
- [ ] T159 [US8] (FR-057) `ExecutionResult` exposes `material` as a real stage product, and every
  stage exposes the object it produced rather than validating or admitting silently.
  | needs: T158 | files: apps/control-plane/semantic_path/execution.py
- [ ] T160 [US8] (FR-092, FR-170) Make the admission decision actually gate the store write: a test
  forces `materialisable = False` and asserts no row is written, then forces `True` and asserts one
  row. The admission path is also the only path permitted to change candidate state, so the live
  `QuarantineStore.purge` route that deletes a rejected candidate as a side effect of
  re-evaluating it is removed rather than inherited: a rejected candidate is evidence and is never
  auto-deleted.
  | needs: T159 | files: apps/control-plane/semantic_path/execution.py, apps/control-plane/api/routes/quarantine.py
- [ ] T161 [US8] (FR-056, FR-092) Delete the post-admission re-validation. There is no "removed or
  justified" escape, because a justification is not a pass condition: a genuinely distinct second
  check must be differently scoped, differently named and must not be the same check run twice.
  | needs: T160 | files: apps/control-plane/semantic_path/execution.py
- [ ] T162 [US8] (FR-092) Stop doubling production writes to demonstrate idempotency.
  | needs: T161 | files: apps/control-plane/semantic_path/execution.py
- [ ] T163 [US9] (FR-100, FR-165) Populate `ExecutionRequest.producers`; it is declared and never
  assigned, so `run_producer` currently iterates zero times on every run, and a counter proves it.
  Give every consumer in the investigation path an idempotency key.
  | needs: T162 | files: apps/control-plane/semantic_path/execution.py
- [ ] T164 [US8] (FR-055, FR-083, FR-167) Correct the stage docstrings to their measured state
  rather than a remembered one. Measured scope: five "thirteen" sites in four files —
  `execution.py:16`, `execution.py:302` (which contradicts itself in the same file),
  `semantic_path/corpus.py:8`, `semantic_path/corpus_cases.py:5`, and the `020` migration comment
  at `:94`, which is a *different* thirteen, namely `SignalKind` members, which P4C changes for a
  different reason; twenty-eight step-numbered docstrings in two parallel fourteen-step ladders plus
  eleven prose cross-references; "Step 9" three times; ladder 2 has no "Step 10" at all; "Step 6b"
  twice and outside the integer sequence in both ladders; and ladder 1 out of declaration order,
  which falsifies its own `STAGE_ORDER` claim that the two cannot drift apart. Acceptance: the step
  numbers in both ladders are `1..14` in declaration order, asserted by a test so the defect cannot
  recur. The ADR for this decision belongs beside ADR **L**, not to a "decision K" that says
  something else.
  | needs: T163 | files: apps/control-plane/semantic_path/execution.py, semantic_path/corpus.py, semantic_path/corpus_cases.py, migrations/versions/020_universal_relation_extraction.py

---

## Phase P7 — `InvestigationWorkflow` production wiring

**Entry**: P6 exit. **Exit**: a live `POST /api/v1/entities` produces signals → candidates → claims
→ edges with real mention ids, asserted by a test that reads the ids and not by a log line;
`lexical_signals` has a non-test caller; and exactly one investigation lifecycle exists.
**Tasks**: 2. **§110**: the production-wiring half of `§110-8`, plus §101, §108 and §114. **This
phase has no `§110` counterpart of its own** and is recorded as a deviation authorised by those
three sections.

- [ ] T165 [US9] (FR-100, FR-161, FR-162, FR-163, FR-164, FR-166, FR-172) Wire the whole lifecycle
  into `services/capture_interpretation.py::interpret_warc_capture`, and prove a real
  `POST /api/v1/entities` produces signals → candidates → claims → edges with real mention ids
  rather than `document:current`. The `Investigation` becomes the only production entry point and
  the direct `user → extractor → graph` path is prohibited as a class; the new
  `InvestigationWorkflow` is **new and minimal**, not a resurrection of anything, and it is
  registered on the Temporal worker with its declared stage order inside a policy, budget and
  freshness gate. Two competing investigation lifecycles exist today with different transition
  tables and no arbiter; `cp_domain`'s is the one that survives, and `workflows/investigation.py` is
  deleted — its `workflow.signal(InvestigationWorkflow, …)` at line 286 addresses the workflow
  **class**, so that file is unrunnable as written rather than merely unwired, and its lifecycle
  types relocate first.
  | needs: T163 | files: apps/control-plane/services/capture_interpretation.py, apps/control-plane/workflows/investigation_lifecycle.py (NEW), apps/shared/cp_domain/investigation.py
- [ ] T166 [US9] (FR-100) Prove `lexical_signals` actually runs: it has never been called by
  anything in the repository, not even the corpus. A non-test importer must exist, and
  `ExecutionRequest.producers` must be non-empty on every run.
  | needs: T165 | files: apps/interpretation/extractors/signals/__init__.py, tests/integration/test_live_production_path.py

---

## Phase P8 — Graph projection

**Entry**: P7 exit **and** the persistence substrate complete. **Exit**: an edge can only come from
an admitted claim; direction and polarity live in properties and not in edge identity; an n-ary
claim projects to a `HyperEdge`; the unadmitted are served by a separate view; navigation reaches
every edge a source fed in both directions; and the graph can be thrown away and rebuilt from the
stores. **Tasks**: 16. **§110**: the persistence **substrate** of `§110-9` plus all of `§110-10`.

**Why persistence is this phase's entry gate.** §110 puts persistence at 9 and projection at 10; the
mandated order puts projection at 8 and its proof at 9. The mandated order is preserved and §110 is
satisfied by **splitting `§110-9`**: T167–T175 execute as P8's entry gate and belong to P8, and the
persistence *proof* — round trips, replay, corpora, mutations, regression and benchmark — is P9.
Nothing is reordered; a phase boundary is drawn inside one brief phase. A7's ordering constraint
also lands here: `021` comes after `PredicateSignature`, `Polarity` and `SignalBasis` exist, or it
adds columns no code writes.

**Entry gate — the persistence substrate (`§110-9`)**:

- [ ] T167 [US8] (FR-097, FR-113, FR-150, FR-152, FR-154, FR-155) Migration `021` on top of the
  forward-only `020`, which is never edited. Add the signature and structural columns; **drop**
  `ck_relation_signal_asserts_something` and `ck_relation_candidate_asserts_something` and replace
  both, since a constraint that survives only because `020` created it must not survive `021`; drop
  and recreate `ck_relation_signal_kind` over the fifteen-member whitelist including `temporal`;
  add the tenant-leading indexes; and stay tenant-scoped, emitting no `UPDATE`, `DELETE`, `TRUNCATE`,
  `drop_table` or `drop_column`, its only drops being check constraints. A pre-flight that would
  narrow-with-refusal rather than drop the whitelist is reported, not applied.
  | needs: — | files: apps/control-plane/db/migrations/versions/021_*.py (NEW), apps/control-plane/db/schema.py
- [ ] T168 [US8] (FR-088, FR-015, FR-151, FR-154, FR-156) Add `signal_refs`, `direction`, `polarity`
  and `confidence` to `relation_candidate` and `candidate_id` to `relation_claim`, and `candidate_id`
  with its index to `validation_findings`. `polarity` is a durable column, not a derived local, and
  no field that participates in an id is left without a column.
  | needs: T167 | files: apps/control-plane/db/schema.py, db/migrations/versions/021_*.py
- [ ] T169 [US8] (FR-087, FR-151) The `predicate_signature` column set on both tables, stored in its
  own columns rather than as a digest, wholly present or wholly absent, with `observational_basis` a
  real column that is read back.
  | needs: T167 | files: apps/control-plane/db/schema.py, db/migrations/versions/021_*.py
- [ ] T170 [P] [US8] (FR-060, FR-087, FR-131, FR-133) Structured columns for
  `PredicateHypothesis.alternative_refs` and `mapping_evidence_refs`. A digest may identify data but
  is never the only copy, and none of those fields participates in `logical_candidate_id` while a
  change in any of them changes `candidate_id`.
  | needs: — | files: apps/control-plane/db/schema.py, db/migrations/versions/021_*.py
- [ ] T171 [P] [US8] (FR-059, FR-171) Repository, writer and reader for `relation_signal`,
  `relation_candidate` and `source_temporal_observation`, covering the named operations; none of
  the three has any writer today and no `INSERT` exists anywhere. The audit log writes to its
  durable table instead of to a process-lifetime list, so an admission decision survives a new log
  instance.
  | needs: — | files: apps/control-plane/db/relation_signal_store.py (NEW), apps/shared/events/audit.py
- [ ] T172 [P] [US8] (FR-059, FR-153) Resolve `SqlRelationClaimStore`:
  `relation_claim.validation_record` is the durable home for a `ValidationResult`, so
  `record_validation` and `non_valid` stop raising `NotImplementedError` and the store becomes usable
  instead of decorative. The verdict is written after the claim exists and never enters identity
  material. Record which way this went.
  | needs: — | files: apps/control-plane/db/relation_claim_store.py
- [ ] T173 [P] [US8] (FR-061, FR-096) Persist `SourceTemporalObservation` on the **normal**
  acquisition path: wire `capture_with_observations()` into `StreamRegistry.capture()` and
  `captures()` and consume the `to_temporal_observations` output the SEC EDGAR and Common Crawl
  adapters already implement. The helper no production path calls is never the only route. EDGAR
  `date_filed` stays day-precision, Common Crawl `timestamp` stays index-observation time, and
  source publication time never enters `Capture.fetched_at`.
  | needs: — | files: apps/acquisition/adapters/sec_edgar.py, adapters/common_crawl.py, apps/control-plane/acquisition/stream_registry.py
- [ ] T174 [P] [US8] (FR-060) Build → store → read tests for every new substrate object, asserting
  the full field list rather than a summary string, and reconstructing the exact domain object.
  | needs: T171 | files: apps/control-plane/tests/integration/test_store_roundtrip.py (NEW)
- [ ] T175 [P] [US8] (FR-062, FR-114, FR-158) Migration parity and schema-invariant tests
  unconditionally — comparing each constraint **by text and not only by name**, because a vocabulary
  that changes on one install path and not the other leaves the constraint names identical — and the
  live round trip **conditionally**, on PostgreSQL, with the omission reported
  `verified only offline` and the reason named.
  | needs: T167 | files: apps/control-plane/tests/integration/test_migration_parity.py (NEW)

**Body — graph projection (`§110-10`)**:

- [ ] T176 [US9] (FR-067; `FR-058` tombstoned: merged into `INV-004`) Keep `GraphProjectionBridge`
  typed `claim: RelationClaim` with no overload, so a candidate and a signal remain unprojectable
  even by mistake; a named test attempts both and fails.
  | needs: T171 | files: apps/projection/graph_projection_bridge.py
- [ ] T177 [US9] (FR-063, FR-064, FR-069) Put `direction` and `polarity` in edge `properties`,
  where assertion and derivation metadata belongs, and never in edge identity: two claims differing
  only in confidence produce one edge id. A `DIRECTED` claim never has its endpoints reordered, and
  an `UNDIRECTED` claim canonicalises **only** when the admitted contract declares symmetry.
  | needs: T176 | files: apps/projection/graph_projection_bridge.py
- [ ] T178 [US7] (FR-065) Project a `NARY` claim to a `HyperEdge`, and make any derived binary edge
  name the claim it came from under an explicit flattening policy.
  | needs: T177 | files: apps/projection/hyper_edge_projection.py (NEW)
- [ ] T179 [US3] (FR-066) Make an entity-to-value relation distinguishable from an
  entity-to-entity relation in both the claim and the projection, so
  `Person → email → EmailAddress` never becomes a normal entity edge.
  | needs: T177 | files: apps/projection/value_relation_projection.py (NEW)
- [ ] T180 [US9] (FR-067) Serve unadmitted relations from a separate hypothesis and evidence view;
  `GraphEdge` is not reused for them, and the view is reachable.
  | needs: T177 | files: apps/projection/relation_evidence_view.py (NEW)
- [ ] T181 [US9] (FR-068, FR-169) Make navigation bidirectional —
  `edge → claim → candidate → signals → observations → source`, and from a source back to every
  edge it fed — over **two** distinct hop vocabularies: a `SIGNAL` hop kind exists and is
  traversable in both directions, and a candidate stays derivation, never evidence.
  | needs: T177 | files: apps/shared/events/evidence_lineage.py
- [ ] T182 [US9] (FR-068) Prove the graph is a projection: write claims → project → rebuild via
  `RebuildableGraphStore` → compare, with at least one non-test caller, because today that class has
  zero production callers and the claim is otherwise unproven.
  | needs: T181 | files: apps/control-plane/semantic_path/rebuild_path.py (NEW)

---

## Phase P9 — Replay / determinism / golden corpus

**Entry**: P8 exit and the P0 baseline re-read, because §110-12 makes the baseline a repeated
obligation and not a one-off. **Exit**: replay in a second process is identical; the golden corpora
are manifest-derived; every mutation fails for the right reason; every hard prohibition has a
failing named test; the boundedness ceilings are live; the regression floor holds; and the
completion report is honest. **Tasks**: 12. **§110**: the persistence **proof** of `§110-9`, plus
`§110-11` and `§110-12`.

- [ ] T183 [P] [US1] (FR-076) Golden relation corpus over the six executable end-to-end HTML cases
  §70 supplies and the §83 relation sets — text, event, structural, unknown, plus the ambiguous and
  the conflicting rule — recorded in a per-case manifest whose counts are asserted against the
  manifest rather than against prose, so the competing "18+", "17" and "eight cases" figures cannot
  survive.
  | needs: — | files: apps/interpretation/tests/corpus/test_golden_relations.py (NEW)
- [ ] T184 [P] [US4] (FR-075) Golden entity-type corpus over the §82 surfaces including the
  ambiguous names, testing raw mention, retained type hypotheses, mapped type, unknown types and
  alternative types.
  | needs: — | files: apps/interpretation/tests/corpus/test_golden_entity_types.py (NEW)
- [ ] T185 [P] [US2] (FR-077, FR-176, FR-177) The active/passive **derivation** test: the derivation
  itself produces the shared logical id, canonical participant ordering and voice normalisation
  included. A test that pins both fixtures to one id is itself a mutation and must fail.
  | needs: — | files: tests/integration/test_active_passive_derivation.py (NEW)
- [ ] T186 [US5] (FR-078, FR-180; `FR-079` tombstoned: merged into `FR-078`) The manifest-driven
  mutation harness: exactly the eighteen field groups §93 enumerates, each with a **named** test
  that fails when that field is broken, and the six §94–§99 cases as manifest entries seven through
  twelve, each failing for the right reason — the assertion is on the failure, not on the failure's
  existence.
  | needs: T149, T147, T153 | files: tests/mutation/test_constitutional_harness.py (NEW)
- [ ] T187 [US1] (FR-180, FR-072) The prohibition-coverage sweep: every hard prohibition has at
  least one named test that **fails** when the prohibition is violated and is reachable from a task
  in this plan — the all-mentions by all-mentions pair sweep, the six-symbol producer import **and
  construction** ban, the parser-free useful baseline, the semantic gate, the `ENT-` and `RES-` ban,
  the majority vote, the mandatory-surface rule, the fourth epistemic level, and the finite
  mandatory relation list. A prohibition with no enforcing test is a non-requirement and is not
  counted toward completeness.
  | needs: T186 | files: tests/mutation/test_prohibition_coverage.py (NEW)
- [ ] T188 [P] [US8] (FR-073) Replay determinism in a **second process**: identical `signal_id`,
  `candidate_id`, material, claim and edge ids, with no `uuid4`, no clock read, no random tie-break,
  no dict-iteration dependence and no call-site sort. Removing each of those in turn leaves every id
  identical.
  | needs: — | files: tests/replay/test_replay_determinism.py (NEW)
- [ ] T189 [US8] (FR-072, FR-071; `FR-080` tombstoned: merged into `FR-072`) Boundedness and
  coverage: every producer reports input size, characters scanned, candidate pairs considered,
  structural nodes considered, signals produced and elapsed time, with explicit per-document and
  per-segment ceilings that a real violation can exceed. The **implementation** stays bounded, not
  merely the counter that observes it.
  | needs: T132, T138, T140 | files: apps/interpretation/extractors/coverage_report.py (NEW)
- [ ] T190 [US8] (FR-081, FR-168) Re-run the T101 baseline. No suite may exceed its entry failure
  count; every failure is classified baseline, new, fixed or flaky; reporting "green" while a new
  failure hides among known ones is forbidden; and the tests that never executed are tracked
  explicitly, because a floor that ignores them is a lie. Constitutional compliance is verified on
  every change rather than depending on a person remembering to run the gate.
  | needs: T166 | files: repair/baseline-021-final.md
- [ ] T191 [US8] (FR-072) Benchmarks: signal throughput per document, candidate assembly time,
  projection time and the locality-window cost, proving there is no all-mentions by all-mentions
  sweep in any extraction path.
  | needs: T190 | files: bench/bench_021_boundedness.py (NEW)
- [ ] T192 [P] [US8] (FR-081, FR-168) `ruff check` clean on all changed paths, and the
  constitutional suite wired so it runs unattended. A8prep's finding D4 would remove `[P]` from the
  linter because it reads every other task's files; A6's `[P]`-collision table keeps it, and A6 is
  the higher authority on task content, so the marker stands and the ordering is carried by this
  line instead.
  | needs: T190 | files: .pre-commit-config.yaml
- [ ] T193 [US8] (FR-082, FR-083, FR-167; `FR-070` tombstoned: absorbed into the design note and
  the constitutional non-goals list) Write `contracts/` (producer protocol, mention-index contract,
  store contract), the ADR set **A**–**L** with a file per letter, and a `quickstart.md` carrying the
  commands that actually work. Every stop condition is reported as `UNKNOWN`, `AMBIGUOUS`,
  `CONFLICTING` or `UNSUPPORTED` rather than guessed, and the vocabulary is never widened to make a
  test pass.
  | needs: T191 | files: specs/021-entity-relation-extraction-finalization/contracts/ (NEW), adr/adr-A.md … adr-L.md
- [ ] T194 [US8] (FR-084) The completion report with all fourteen sections §114 mandates, in order,
  each claim classified as `implemented`, `verified`, `verified only offline`, `known limitation` or
  `deferred`. "Feature complete" requires the §101 architecture to be present in **production**
  code; passing tests alone are not sufficient.
  | needs: T193 | files: specs/021-entity-relation-extraction-finalization/completion-report.md (NEW)

---

## §110 coverage — all twelve brief phases mapped, none skipped

`input.md` §110 fixes twelve phases. Every one is mapped; three are split, none is dropped.

| §110 phase | Brief text | Lands in | How |
|---|---|---|---|
| `§110-1` | identity/domain contract cleanup | **P1a** | verbatim; committable and green alone |
| `§110-2` | atomic entity type vocabulary | **P2** | verbatim |
| `§110-3` | type hypothesis + mention binding | **P2** (type half) + **P3** (binding half) | split, because it names two subjects |
| `§110-4` | `RelationSignal` structural contract | **P4A** (additive) + **P4B** (the seven construction sites) + **P4C** (deletions) | split three ways so each part is green on its own |
| `§110-5` | predicate signature + candidate identity correction | **P1b** | merged into P1 with `§110-1`; see the mandatory 1a/1b split |
| `§110-6` | producer corrections | **P4B** | after the construction-site migration, because the migration must be one commit with its callers |
| `§110-7` | assembly / conflict semantics | **P5** | verbatim |
| `§110-8` | real execution lifecycle | **P6** (material, validation, admission) + **P7** (production wiring) | split; P7 is the deviation, authorised by §101, §108 and §114 |
| `§110-9` | durable persistence + replay | **P8** (substrate, as P8's entry gate) + **P9** (replay and round-trip proof) | split; see the inversion below |
| `§110-10` | graph projection verification | **P8** (body) | verbatim |
| `§110-11` | golden corpus + mutation tests | **P9** | merged into P9 with `§110-12`, whose subject is where regression and boundedness belong |
| `§110-12` | benchmark + regression | **P9** | merged; it also makes the P0 baseline a **repeated** obligation, re-read at P9's entry |

Added phases, each with its authorising section: **P0** (§107, §108 — a spec gate, no production
code) and **P7** (§101, §108, §114 — production wiring, which §110 does not enumerate).

**The two real inversions, handled without reordering anything.**

1. **§110-1 and §110-5 land in one phase.** §110 separates them by three phases; the mandated
   structure does not. Resolved by the mandatory **1a/1b commit split**: 1a is `§110-1` alone and is
   committable green on its own, 1b is `§110-5` and depends on 1a's exit. §110's ordering survives in
   the commit history, and the mandated single phase survives in the header. The phase has one entry
   condition and one exit condition.
2. **§110-10 (projection) would precede §110-9 (persistence).** The mandated order puts projection
   before persistence; §110 puts persistence first, and a rebuild needs a store to rebuild from.
   Resolved by **splitting §110-9**: the persistence *substrate* — migration `021`, ORM parity, and
   the three repositories with their writers and readers — is the **entry gate of P8** and belongs to
   P8; the persistence *proof* — build → store → read, replay, corpora, mutations, regression and
   benchmark — is P9. So persistence exists before projection is verified, and the mandated
   8-before-9 order is preserved. Nothing is reordered; a phase boundary is drawn inside one brief
   phase.

## MVP

```text
P0 → P1a → P1b → P2 → P3 → P4A → P4B → P4C
```

That is a **contiguous prefix** of the phase order with **no phase skipped**: every phase header
between `P0` and `P4C` appears. It delivers the A6 increment `0→1→2→3→4→5` — the baseline gate, the
honest identity function, the signature and candidate identity, the type vocabulary and
`TypeHypothesis`, the mention index, and the whole structural signal contract including its
deletions. It is the smallest increment whose absence makes the rest of the substrate *wrong* rather
than merely incomplete: without P1a the identity function lies about its parameters, without P1b no
producer can emit a signature, without P2 there is no vocabulary, without P3 there is no resolver,
and without P4A–P4C the signal cannot carry a participants tuple or a polarity at all.

**The old `0 → 1 → 2 → 5` MVP is abolished.** It traversed a phase it claimed not to need: the
predicate-signature phase keyed logical identity on the signature, which the Phase-4 signal contract
has to be able to carry. It was also inconsistent with its own story tags, claiming User Story 1
alone while carrying five.

## Reversals this file applies

**`TEMPORAL` — reversed, it stays.** The old SignalKind-removal task forbade a `TEMPORAL` member while
citing the requirement that mandates it, which is an inverted citation. `SignalKind.TEMPORAL` is
**kept** as an observation channel: it states *this signal is based on a temporal observation* and
carries no temporal payload and no time of its own. The temporal facts live in
`SourceTemporalObservation` and in the signal's `temporal_evidence`. `T129` adds the aspect split
without touching `TEMPORAL`, `T148` deletes the aspect-named members and explicitly keeps
`TEMPORAL`, `T142` emits the channel and puts the facts in the observation, and `T167` recreates the
`SignalKind` whitelist including `temporal`. Nothing in this file forbids adding it.

**`CONTRADICTED` — reversed, it must never be the structural-conflict target.** The old
assembly-conflict task sent an arity, direction, polarity or role-binding disagreement into
`CandidateStatus.CONTRADICTED`, and that is forbidden: it collapses the epistemic space. The three
axes are now separate — a **structural** disagreement yields
`RelationCandidate.assembly_state = CandidateAssemblyState.CONFLICTING`; a **semantic**
disagreement yields `PredicateHypothesis.resolution_state = CONFLICTING`; and
`CandidateStatus.CONTRADICTED` is reserved, and must never be widened, for a positive reading set
against an explicit denial.
**`T154` owns this** and says so.

**The named test is renamed.** `test_entity_extractor_covers_all_seven_classes` becomes
`test_entity_extractor_covers_all_seven_extraction_families` (`T118`). There are 31 foundational
entity types, 13 value types, 7 §8 extraction families and about 4 new instrument modules — four
numbers, four jobs. "Seven classes" is wrong vocabulary and would otherwise become a 32-extractor
mandate.

**`SC-001` is computable but not yet reachable.** The unit-level derivation is specified, and `T110`
writes the test **red** in P1a so that `T112` can turn it **green** in P1b. The criterion itself is
a different matter: it is unreachable end to end because no syntactic producer exists, so it carries
an `xfail(strict=True)` marker with reason `syntactic_producer_absent`, and **`T133` — the syntactic
producer — owns the `xfail → green` transition.** No wave may report `SC-001` as passing while that
marker is still present.

**n-ary is native and persisted in `021`.** `participants` is a typed structured field persisted in
`021` on both `relation_signal` and `relation_candidate`. It is not `extra`, which is an untyped
escape hatch, and it is not deferred to a later feature. The two binary columns survive as derived
accessors and are never a second source of truth.

## The `[P]` re-examination

The old file's `[P]` markers each claimed *different files, no dependency*, and each claim was false
for a different reason. The old groups are named by subject rather than by their retired numbers,
because those numbers are no longer defined and citing them would be a phantom citation — the exact
defect this table exists to close.

| Old group (by subject) | Verdict | What this file does |
|---|---|---|
| baseline recorder ↔ checklist creator | **real** — both wrote `checklists/requirements.md` | **T101** writes `repair/baseline-021.md`; **T104** writes `checklists/requirements.md` and reads T101's counts. Disjoint, and ordered. |
| step-docstring fixer ↔ the four lifecycle tasks | **real** — all five edited `execution.py` | **T158**→**T159**→**T160**→**T161**→**T162**→**T163**→**T164** is a strict chain on one file. None is `[P]`, and T164 is last because it corrects docstrings the others change. |
| `Polarity` module ↔ `RelationParticipant` module | **soft** — same directory, different new modules, and `[P]` was unfalsifiable because no path was given | **T127** owns `relation_participant.py` and `relation_signal_parts.py`; **T128** owns `polarity.py`; **T130** owns `signal_basis.py`. Each is a named new file, so `[P]` is now checkable. T129 shares `signal.py` with T127 and is therefore ordered after it. |
| the five producer-conversion tasks | **wrong as stated** — four of the five are distinct producer files | The real collision is that `tables.py` holds both the table instrument and the list instrument, so **T138** and **T139** are ordered and neither is `[P]`. The eight new-file producers keep `[P]`; the five migrated ones do not, because T131 reads them in the same phase. |
| replay harness, boundedness report, `ruff` gate | **weak** — separate phases, but shared read surfaces | **T188** (replay), **T189** (boundedness) and **T191** (benchmark) are ordered. **T192** keeps `[P]`: A8prep's D4 would remove it because a linter reads everything, A6's `[P]`-collision table keeps it, and A6 is the higher authority on task content. The disagreement is recorded in T192 rather than resolved silently. |
| not in the old list | **additional finding** | **T147** asserts across every producer, so it comes strictly after T132–T146 and is ordered, not `[P]`. **T110** and T147 both assert across the producer suite, and that is why T147 lands after the whole producer set. |

## Merged, removed and folded requirements

These ids are cited only with their replacement named, and never as a live normative target. The
`ARBITRATION.md` §2 rule is zero normative references to a tombstone; a citation that carries a
deprecation marker on the same line reads as history, which is why the owning task still names it.

| Id | Status | Replacement | Owning task |
|---|---|---|---|
| the sub-numbered type-space id folded into the mapping band | tombstoned, absorbed into `INV-002` | the type space stays desirable; a finite mandatory *relation* list stays forbidden | T115, T119 |
| `FR-058` | merged into `INV-004` | an edge exists only after an admitted claim | T176 |
| `FR-070` | removed, no longer normative | the design note and the constitutional non-goals list | T193 |
| `FR-079` | merged into `FR-078` | one manifest-driven harness, eighteen field groups | T186 |
| `FR-080` | merged into `FR-072` | the same five metrics plus the complexity bound | T189 |
| the sub-numbered type-hypothesis id folded into the `110` band | deprecated, folded into `FR-112` | the `110`-band number is the survivor | T123 |

The two folded sub-numbered ids are deliberately **not** written as citations anywhere in this file.
`spec.md` folded them into their allocated slots rather than keeping them as definitions, so a
citation would dangle; their content is carried by `FR-112` and by the mapping band respectively.
This also retires the letter-suffixed id grammar for good: no `FR-nnn<letter>` token appears below
except inside a deprecation marker.

## Open questions blocking specific tasks

Every id below is defined in this file. The old table pointed at four phantom ids.

| Q | Blocks | Default if unanswered |
|---|---|---|
| Q1 normalisation rule set | T111, T112, T150 | the seven-field signature and the versioned construction table; an unsourced entry is dropped and the predicate stays `AMBIGUOUS` rather than guessing |
| Q2 controlled vocabulary | T115 | the bounded versioned pack `core-atomic-types@1`, used as a mapping instrument only and never as a gate |
| Q3 neighbourhood scope | T132 | per-producer stated neighbourhood class as a typed field; no cross-producer sweep claim |
| Q4 n-ary identity shape | T112 | role bindings, canonically ordered, with a declared symmetry marker |
| Q5 producer ↔ lifecycle import direction | T158 | `interpret_warc_capture` calls producers, then the assembler; recorded as an ADR |
| Q6 `Layer0Pipeline` versus `capture_interpretation` | T165 | `capture_interpretation` — it is the live path, and it becomes an activity of the investigation workflow |
| Q7 temporal-observation repository | T171, T173 | yes, in `021`, because §61 names the table and the normal path must write it |

## Notes

- Tests are written **first** in each phase and must fail before the implementation exists. The one
  declared exception is `T110`, whose failure is the point until `T112` turns it green.
- Commit after each task or logical group. `P4A`, `P4B` and `P4C` are each committable green on their
  own, and a phase boundary is never bundled.
- Stop at any phase entry to validate independently.
- If a task turns out to need a new ontology, a mapping decision or a guess, stop and report
  `UNKNOWN`, `AMBIGUOUS`, `CONFLICTING` or `UNSUPPORTED`. Do not widen the vocabulary to make a test
  pass.
- Known-failure discipline: the entry baseline failures are not to be fixed, hidden or counted as
  progress, and the tests that never executed are reported rather than quietly excluded.
- If a task appears to need a change outside this file, it is reported, not made. This file owns
  `tasks.md` and nothing else.
