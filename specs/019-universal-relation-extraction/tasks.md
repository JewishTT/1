# Tasks: Universal Relation Extraction

**Feature**: `019-universal-relation-extraction` · **Plan**: `plan.md`

Contract-healing first, then the substrate. Production code first; the nine constitutional
tests land in their own package and assert invariants only.

## Phase 0 — CD-6: the predicate may be unknown (P0, gate)

The gate. Nothing downstream is sound until a candidate can carry an unresolved predicate.

- [x] T001 grep the repo for every reader of `RelationCandidate.relation_ref` and enumerate
      them before changing the type. The list belongs in the commit message.
      **10 sites in 3 files**: `relation_candidate.py` (589, 593, 623, 626, 697, 702, 1459),
      `semantic_path/corpus.py` (1452-1453), `extractors/relations.py` (677). All fixed in
      T003. `semantic/profiles.py` has an unrelated `relation_refs` and was left alone.
- [x] T002 `apps/shared/domain/predicate_hypothesis.py` — `PredicateHypothesis`
      (`surface_form`, `normalized_form`, `relation_ref: RelationRef | None`,
      `alternative_refs`, `resolution_state` in {known, unknown, ambiguous, conflicting},
      `mapping_evidence_refs`), content-addressed, frozen, self-verifying. Plus
      `PredicateResolutionState`.
- [x] T003 `relation_candidate.py` — `relation_ref` becomes `RelationRef | None`;
      add `predicate_hypothesis: PredicateHypothesis` and `relation_surface: str`. Identity
      material gains the *surface* of the predicate so an unknown predicate is still
      distinguishable (FR-039). The `missing_relation_type` gate is gone, and what replaced
      it is not a weaker rule but a different question: `PredicateHypothesis` refuses a
      candidate that asserts *no* predicate at all, which the old gate also ruled out.
- [x] T004 `RelationCandidate.to_claim` / `build` — an unresolvable predicate is refused at
      *material* construction, not at signal time. The refusal names the missing semantic
      resolution. `to_claim` routes through `build`, so the deprecated path inherits it.
- [x] T005 `relation_claim_material.py` — `relation_ref` required with **no field to put
      `None` in**. `build` from a candidate whose predicate is unknown MUST raise.
      `RelationClaim.relation_type` stays bare `str`, so the claim boundary cannot even be
      *written* with a None predicate; `missing_relation_type` still refuses both `None`
      and `""`.
- [x] T006 Verify: `RelationCandidate(relation_ref=None)` constructs; an untyped relation
      constructs; `build(...)` on it raises; `RelationClaim(relation_type=None)` is not
      constructible at all. (SC-O) — 17 tests in
      `apps/shared/tests/unit/test_cd6_unresolved_predicate.py`.

      **Wording resolved during T006.** The clause "`relation_ref="owner of"` as a raw
      surface constructs" was written before the ambiguity was confronted, and it is now
      refused instead — on purpose. `"owner of"` and `"works_for"` are both strings and
      nothing about their shape says which was meant, so accepting one as a type means
      fabricating an operator, which constitution 4 forbids outright. A bare string at the
      ref position is refused with a message naming both ways forward
      (`RelationRef('works_for')` for a type, `surface_form='owner of'` for an unresolved
      relation), and the untyped relation is constructed through `relation_surface` — the
      shape §16 specifies. A bare string at `alternative_refs` *is* accepted, because an
      alternative is a type already being offered and there is nothing to guess. Verified:
      refusal redirects; legacy provenance of unknown origin is read as a surface, in
      `from_candidate_field` only, which is the single place permitted to guess.


## Phase 1 — CD-1: `SUPPORTED` leaves the lifecycle (P0)

- [x] T007 `relation_candidate.py` — `with_status` deprecated in the docstring, retained for
      legacy callers, never an input to admission. Also `is_admissible` and
      `RelationCandidateSet.admissible`, which are the two other places a label was dressed
      up as an answer; both now say plainly that they report a *disposition* and that the
      real question is answered by `admit`.
- [x] T008 `RelationCandidateSet.supported` — the code spells it `admissible`; it is now a
      compatibility projection over `is_admissible`, documented as not a lifecycle gate, and
      `ADMISSIBLE_CANDIDATE_STATUSES` says what it is for.
- [x] T009 `execution.py:2707/2747` — replaced. `CandidateStep.supported` is **gone, not
      deprecated** (keeping it would keep inviting the use); the step produces one reading.
      `_claim_step` is now `build` → `validate` → `admit` against the *material*, which
      `LayeredValidator` was already widened to read. `grep with_status(|to_claim(|CandidateStatus.SUPPORTED`
      over the production path: zero hits (one docstring mention, describing the old path).
- [x] T010 Verify: 016's suites stay green; the executable path reaches `admit` without ever
      setting a status. (SC-A) — proven, not assumed: `admit` commits a `PROPOSE` reading;
      `admit` still refuses `rejected`/`contradicted`; `to_claim` still raises
      `CandidateNotAdmissible` for `PROPOSE` and still commits `SUPPORTED`.

      **Two things the old gate was hiding, found while removing it.** First, `to_claim`
      reached `admit` with `unvalidated_report` — so the report slot that exists to gate
      admission carried "nothing was checked", and the evidence was not weakly consulted,
      it was not consulted at all. Validating the material *before* admitting is what makes
      the guard real, and that ordering is only possible because CD-1 removed the label
      precondition. Second, the relabelled `supported` reading was the one committed, so
      what entered the graph was not the reading extraction produced. The corpus records
      `candidate_id`, so those ids change; re-recording is T040.


## Phase 2 — CD-4: two lineages, one vocabulary (P0)

- [x] T011 `evidence_lineage.py` — `EVIDENCE_BACKWARD_CHAIN` and `DERIVATION_FORWARD_CHAIN`
      are the definitions; `BACKWARD_CHAIN`/`FORWARD_CHAIN` are retained as *aliases* (the
      same tuple object, asserted with `is`), so no existing caller can drift onto a
      different sequence.
- [x] T012 `forward()` keeps its exact current sequence and now says why it always was the
      derivation walk. Byte-identical behaviour; nothing in it changed.
- [x] T013 `trace(node)` — returns a new `LineageTracePair` carrying both dimensions, with
      `complete` as a conjunction (an `or` would hide exactly the case the type exists to
      expose) and `gaps` naming the *kind* of each hole.
- [x] T014 `CANDIDATE` is not added to the evidence ladder. Verified by assertion, and the
      ladders differ by `candidate` and `entity` — entity being the apex the evidence walk
      has no rung above, which is correct and not a second discrepancy.

      **A pre-existing limitation found and fixed, because T013 needed it.** `backward()`
      hard-coded `EVIDENCE_BACKWARD_CHAIN[1:]`, which assumed every subject was a relation.
      True of the single caller, wrong of the method: asked about a mention it demanded an
      `ASSERTION` hop it could not reach and reported a gap that was an artefact of the
      assumption. It now derives its ladder from the subject's own kind, exactly as
      `forward` does, and takes the same `kind` override. Omitted for a relation, the answer
      is what it always was.

      **The finding worth keeping.** A graph registered with derivation links *only* cannot
      answer the evidence question past the mention — the walk stops naming `mention`,
      because between a mention and the assertion resting on it sits exactly one thing and
      the candidate is not in that ladder. That is CD-4 as a property of real data, not
      just of a constant, and it is why the evidence spine has to be registered separately
      rather than inferred.


## Phase 3 — CD-5: source temporal facts get a home (P0)

- [x] T015 `apps/shared/domain/temporal_observation.py` — new module.
      `SourceTemporalObservation` (`capture_ref`, `temporal_axis`, `stated_value`,
      `stated_value_end`, `raw_value`, `precision`, `basis`, `evidence_location`,
      tenant-scoped), frozen, content-addressed under `STO-`, plus `TemporalAxis`,
      `TemporalPrecision` and `observations_by_axis`. `Capture` is **not** widened —
      asserted, not assumed.
- [x] T016 `adapters/sec_edgar.py` — the acceptance instant is now returned. The gap was
      sharper than "nowhere to put it": the module already declared `published_at` supplied
      from `date filed`, already had `iso_utc_from_filed_date` written specifically to parse
      it, and already set `time_basis=PUBLICATION` on every capture — and then discarded the
      parsed value. A stream declared it could supply an axis and did not, which is the one
      thing a declaration exists to prevent.
- [x] T017 `adapters/common_crawl.py` — the same shape for the index observation, on
      `observed_at` with `basis=INDEX_OBSERVATION`.
- [x] T018 Verify: EDGAR's `date filed` is retrievable; `Capture` still has no
      `published_at`; no seventh axis exists. (SC-L, FR-018) — 27 assertions.

      **The axis vocabulary is now defined once.** `stream.TimeAxis` is a plain *alias* for
      `domain.temporal_observation.TemporalAxis`, not a copy and deliberately not a
      subclass: a subclass would make `TimeAxis.X is TemporalAxis.X` False and let
      `isinstance` answer according to which name a caller imported. One enum, two names,
      no way to be wrong.

      **The seam.** `StreamRegistry.capture_with_observations` builds the capture first and
      passes its id in, because a stated instant with no retrieval behind it cannot be
      checked against anything anybody fetched. The capability is *probed* rather than added
      to the protocol, because the adapters are structurally typed and a required method
      would either break them or force an inheritance they deliberately avoid. An adapter
      that states no temporal facts returns an empty tuple — the honest answer, not a skip.

      **Two streams, one axis, two precisions.** EDGAR's `date filed` is `day` and Common
      Crawl's CDX `timestamp` is `second`; neither is rounded to the other, the raw text is
      kept beside the parse so the day-granularity convention is checkable against the
      register, and `is_ordered_precision` tells a consumer the midnight was ours. An
      absent or malformed date yields *no* observation — the capture is still produced,
      because it exists whether or not the register stated a date.


## Phase 4 — Persistence: candidates, signals, temporal observations (P0)

- [x] T019 `db/schema.py` — `relation_candidate` (27 cols), `relation_signal` (24),
      `source_temporal_observation` (11), all tenant-scoped fail-closed, every id column
      `String(64)`. Closed vocabularies (status, arity, predicate state, signal kind,
      direction, temporal axis) are CHECK constraints imported from the value types, so
      adding an enum member adds the CHECK with it.
- [x] T020 CD-3 widening sweep: **enumerated and measured before writing anything**, which
      changed the shape of the job. `CAND-` and `CNDR-` are each 37 characters, so
      `VARCHAR(36)` cuts the last hex digit off every candidate id — but *nothing writes one
      there today*, because `candidates` belongs to feature 008's extraction path (it
      carries `mention_ids` and a `type_hypothesis` and has no operator identity at all).
      So `candidates.candidate_id` is **not** widened, and the two columns that would
      actually carry a semantic-layer reference — `evidence_links.candidate_id` and
      `admission_decisions.candidate_id` — are. A test fails if somebody "finishes the
      sweep" by touching the generic one, and another fails if the prefixes ever stop
      overflowing 36 and the widening becomes cargo cult.
- [x] T021 `020_universal_relation_extraction.py` — forward-only, `downgrade()` raises and
      names all three tables. Offline DDL parity proven against the ORM by
      `tests/unit/test_migration_020_universal_relation.py`.
- [x] T022 Verify: a candidate with no claim is storable; `CAND-`/`CNDR-`/context/regime/
      evidence/temporal-hypothesis/signals all recoverable. (SC-B) — 24 tests, and the
      parity test found two real defects while being written: the ORM was missing the
      closed-vocabulary CHECKs the migration had, and its `producer_confidence` default was
      the string `'0'` on a Float column where the migration had a numeric `0`. Both are
      the class of bug this check exists to catch, and neither would have shown up in
      application tests.

      **The ORM imports its vocabularies; the migration writes its own.** Application code
      should follow the value type — when the enum gains a member, a fresh install must gain
      the CHECK with it or the two install paths diverge. A migration must not import it,
      because a revision that reads a value type changes meaning when somebody edits that
      type, and an already-migrated database cannot be re-run. Deliberate duplication, with
      the parity test as the only thing keeping it honest.

- [x] T023 `extractors/signals/signal.py` — **done before T019, not after, and the order
      change is recorded here.** T019's DDL for `relation_signal` has to mirror the field
      set of the value type exactly, so writing the type after the DDL would mean writing
      the list of fields twice and letting the two copies drift. `RelationSignal` with the
      full FR-019 field set, `SignalKind` (13 kinds), `DirectionHypothesis`,
      `Neighbourhood`. `relation_ref` optional; `relation_surface` required.

      **`producer_confidence` is deliberately excluded from the signal's content address**,
      and that is the useful part: a producer that is slightly more sure of the same reading
      is not a second independent observation, so letting confidence into the address would
      let one producer's uncertainty manufacture corroboration. The identity of a signal is
      what was seen, not how sure the reader was.

      `Neighbourhood` is required and never defaulted, with `characters_scanned` and
      `pairs_considered` as numbers a reader can check against the document — an
      unfalsifiable claim of boundedness is not boundedness. `assert_bounded` refuses a
      producer over a stated ceiling, per signal rather than averaged over a batch, because
      the failure is a *producer* reaching too far.


## Phase 5 — RelationSignal (P0)

- [x] T023 `extractors/signals/signal.py` — `RelationSignal` with the full FR-019 field set,
      `SignalKind` (13 kinds), `DirectionHypothesis`, `Neighbourhood`. `relation_ref` optional.
      *(Done before T019; see the Phase 4 note above for why.)*
- [x] T024 `extractors/signals/protocol.py` — `RelationSignalExtractor` (structural, so a
      producer is not forced to inherit a base class or implement a method it has no use
      for), `ProducerDeclaration`, `ExtractionScope`, and `run_producer` as the single place
      a producer's output is checked.

      **The registry owns identity, the producer owns observation.** `run_producer`
      overwrites `producer_ref`, `producer_version`, `tenant_id`, `context_ref`,
      `semantic_regime_ref` and `capture_ref` with what the registry knows. A producer that
      could set its own `producer_ref` could name itself `independent-source-7` and
      manufacture corroboration — the same forgery as letting confidence into a signal's
      address. It also refuses a producer that emits a kind it never declared, because that
      is either two producers wearing one name (which corrupts FR-034) or a declaration
      nobody maintains.

      **A crashing producer propagates.** Silently dropping one producer's output would make
      "no relations here" and "this producer crashed" the same observation, and that is the
      one confusion a substrate for evidence cannot afford.
- [x] T025 `extractors/signals/lexical.py` — 018's cue reader wearing the substrate's
      contract. `RELATION_CUES` is now *this producer's private data*, which is a much
      smaller claim than "this is how the platform learns relations".

      `producer_confidence` is **1.0**, and the value is worth the explanation because it
      looks like overconfidence. This producer's uncertainty is not uniform and the halves
      are recorded in different places: that the phrase occurred between two surfaces is
      exact (a declared pattern either matched or did not), while that those surfaces are
      the implied participants is genuinely uncertain — a job title and a place name are
      both noun phrases in the same position. That half lives in
      `CueAffordance.subject_kinds`/`object_kinds`, which the assembler reads. A single
      number would have averaged a certainty against an uncertainty into a figure meaning
      nothing.

      `trigger_span` is `None` and the character offsets ride in `extra`, because a
      `SpanRef` indexes *into a segment* and this producer sits below the segmentation
      layer. A span with an invented `segment_ref` resolves against nothing, which is worse
      than no span; a cue dropped rather than deferred is a cue nobody can find again.
- [x] T026 Verify: `relations.py` no longer gates relation discovery; a signal with
      `relation_ref=None` is constructible and survives. (SC-D) — 27 assertions, including
      a table-header signal with no operator type going through the whole contract
      untouched, and refusals for every way the contract could be decorative: an
      undeclared kind, an unstated ceiling, a producer that will not say what it cannot
      read, a scope with no context frame.


## Phase 6 — Producers beyond lexical (P0)

- [x] T027 `links.py` — LINK/REFERENCE producer over hyperlink structure. Asserts the
      observable link, never `cites`/`hosts` from nothing (FR-027). `relation_ref` is always
      `None` and direction always `UNDIRECTED`: a hyperlink states a document structure, not
      a world relation, and the markup points one way while a reader traverses it both ways.
      This is CD-6's first real user. Two boundaries worth naming: an `<a name=...>` target
      and an in-page `#fragment` are **not** reported as outward links, and an uninformative
      anchor keeps *its own* text ("click here") rather than having a name recovered from
      the URL.
- [x] T028 `tables.py` — TABLE and LIST producers. Emits `relation_surface="CEO"` without
      knowing it means `works_for` (FR-028). The **header** is the surface and the cell is
      the participant, because the relation is about the column; putting the cell in the
      surface would give one signal per cell all carrying the same words and would make
      FR-034 count rows rather than observations.

      **Three defects the checks found, all of the same kind — a confident falsehood about
      the document's own structure, which is the cheapest kind to produce because the output
      still looks like a table.** The header row was itself emitted as data (11 signals
      where there were 8). A spanning caption was chosen as the column names. And a row
      whose cell count did not match the header's was paired positionally, attaching values
      to columns the markup never put them in. The third is now skipped rather than
      mispaired, and the first is why `_read_table` returns the header row's index.

      Header-row selection is "the row with the most `<th>` cells", which is a **heuristic
      and is declared as one on every signal's `precision`**: one spanning caption cell
      loses to three column names, and a table whose only header is a caption reports
      nothing rather than reporting the caption as a column.
- [x] T029 `metadata.py` — METADATA/HIERARCHY/ATTRIBUTE/SCHEMA producer over author,
      publisher, parent, path and domain, on the same contract as textual relations
      (FR-029). Reads **unrecognised** meta keys too and labels them `unrecognised`, because
      a platform that discards metadata it has no reading for is losing evidence (CD-7).

      A byline reports the field name `"by"`, never `authored_by`: a byline may be a person,
      a shared newsroom address, a robot or a CMS default, and the producer says so in its
      own notes. JSON-LD `@`-keywords are **not** emitted — `@type` describes the metadata
      block, not anything in the world, and emitting it would put the block in a relation
      with its own type name.
- [x] T030 Boundedness: every signal records its `neighbourhood`; no producer scans a
      document-wide pair space. (FR-041…FR-043, SC-J) — 36 assertions over all five
      producers, each asked the same three questions: what it declared, what it read, and
      whether that is smaller than the document.

      **`pairs_considered` had to be redefined to mean one thing.** The lexical producer was
      reporting its *window* count there, which made the field mean two different things
      depending on the producer and made that producer exceed its own declared ceiling on
      any document over 10,000 characters. It now reports **0**, which is literally true: a
      cue scan compares no mention pairs at all, and `characters_scanned` already records
      how much was read. A gate that fires on ordinary input teaches people to ignore gates.

      The check is per signal and never averaged — 200 signals at one pair each pass a
      ceiling of 16, and one signal at ten million pairs is caught regardless.


## Phase 7 — Assembly (P0)

- [x] T031 `semantic_path/assembly.py` — `RelationSignalAssembler`/`:func:`assemble`: signals
      → candidates, origin preserved, aggregation without signal loss, conflicts preserved
      as competing candidates. Creates no claim, resolves nothing, projects nothing
      (FR-032…FR-036). Verified on the module's own imports: no `RelationClaim`, no
      `GraphEdge`, no resolver, no `admit`.

      Grouping key is the **mention pair in signal order, not sorted** — direction is part of
      what a signal asserts, so sorting would merge a relation with its own inverse. The
      per-pair reading key is `(polarity, surface, ref, direction)`, and the producer is
      deliberately *not* in it: two producers reading the same phrase corroborate one
      reading, and putting the producer in the key would make corroboration arrive as a
      conflict. `ExtractionStrategy.ORCHESTRATED` was **added** — every existing member is a
      single-producer method, and recording `LEXICAL_PATTERN` on a candidate assembled from a
      table and a hyperlink would put a false account of how the reading was made into its
      *identity material*, so the falsehood would live in the content address.

      `RelationCandidate.signal_refs` was added as **revision** material: a relation
      corroborated by three sources is one hypothesis with three readings, which is the same
      shape as FR-039 and makes the address depend on the evidence, so replay is
      deterministic and a candidate cannot claim backing it does not have.
- [x] T032 OQ3 resolved and written into the module docstring, not only here: **the type may
      carry no signals; the assembler never produces one.** The type must allow it because a
      `SemanticRegime` producing a second reading of a surface it resolved itself has, by
      definition, no producer observation behind it — forbidding it would make predicate
      resolution inexpressible. The assembler may not do it, because a hypothesis assembled
      from nothing has no statable origin. `AssemblyReport.complete` makes the distinction
      checkable rather than conventional.
- [x] T033 Verify: two signals on one pair → one candidate carrying both; two conflicting
      signals → two candidates, neither overwritten. (SC-E) — 29 assertions.

      **A distinction the checks forced, and it is the useful one.** Two signals with
      *different* surfaces ("CEO of" and "founded") get two different `logical_candidate_id`
      values: they are two claims about the world, not two readings of one claim, and they
      appear in `groups_with_conflict` but not in `competing()`. Two signals with the *same*
      surface read two ways (both "CEO of", one typed `works_for` and one `affiliation`) get
      one logical id and two readings — that is FR-039 arriving through the substrate. A
      reader who conflated the two would report a disagreement about how one relation is
      named as though it were a disagreement about what relations hold.

      **A real bug the checks caught:** `assemble` was not calling `with_id()`, so every
      candidate came back with an empty `candidate_id` and `logical_candidate_id`. It also
      made an order-independence check pass falsely, because it was comparing `'' == ''`.
      Order independence is now verified on real addresses.


## Phase 8 — Execute the real path (P0)

- [x] T034 `execution.py` — signals and assembly inserted between the regime and the
      candidate. **The orchestrator no longer constructs a candidate by hand**: `_candidate_step`
      reads an assembled reading, refuses to run without one (`signals_step_missing`), and
      refuses if the declaration did not survive assembly (`declared_reading_missing`).
      `ExecutionStage` is now fourteen stages and `SIGNALS` sits **after** `REGIME`.

      **The declaration is a signal, and that is the load-bearing decision.** The caller's
      "this observation asserts A relates to B" used to be an *instruction* — a candidate was
      built field by field from the request, so the relation the caller asked about was never
      evidence for anything. It is now a `SignalKind.SCHEMA` signal over the real mention ids,
      assembled alongside whatever producers observed, so declaration and observation
      aggregate, corroborate or conflict through one code path.

      **The stage position was wrong first and the code said so.** SIGNALS was placed between
      MENTIONS and REGIME, which forced a placeholder `semantic_regime_ref` because the real
      regime did not exist yet. A placeholder that satisfies the type is indistinguishable
      from a real value in every downstream read, which is the opposite of what FR-014 wants
      — so the stage moved after REGIME and the placeholder properties were deleted. A
      request's `context_ref`/`semantic_regime_ref` are now read from the regime step's own
      output.

      Producers' surface addresses are **not** remapped to mention ids: a producer is below
      the mention layer, and remapping would be the orchestrator inventing mention identity
      from a string match — resolution with no `ResolutionDecisionRecord` behind it.
- [x] T035 Grammar-form independence (FR-040) — **the spec's wording is not satisfiable in
      this design, and the reason is worth more than the check would have been.**

      FR-040 asks that an active and a passive realisation of one relation yield the same
      logical candidate. They do not, and that is the design working: a candidate's logical
      identity is keyed on `relation_surface`, so "is the CEO of" and "The CEO of Acme is" are
      two different claims. They say the same thing in English and are different things in a
      substrate whose job is not to guess what English means. Unifying them is a later layer's
      work — an operator mapping or a `SemanticRegime` that reads both surfaces into one
      operator — and that layer has somewhere to record the decision. This is the same
      distinction T033 forced: same surface read two ways = one hypothesis, two readings;
      different surfaces = two hypotheses.

      The **achievable** form is verified: one mention pair, one relation surface, two
      producers reading it in two grammatical frames → one `logical_candidate_id`, two
      `candidate_id`s, each naming the producer that read it.
- [x] T036 Verify the full path reaches `worldline` over a **structural** producer, not only
      the lexical one, and that no producer ever emits a `GraphEdge`. (SC-F, SC-G) — the
      golden request reaches `worldline` with a claim and a worldline record *through* the
      signal step, and a request carrying a link and a table produces `link`, `reference` and
      `table` signals alongside the declaration, all attributed. SC-G is verified structurally:
      no producer names an edge type, none imports a projection module, `RelationSignal` has
      no field a projection could be built from, and the edge stage runs at rank 12 against
      the candidate stage's 7.

      **The structural-producer drive stops at SIGNALS, on purpose.** A request's
      `resolution_candidates` universe belongs to its own sentence; bolting markup onto the
      golden sentence makes the *resolver* refuse with `subject_end_unresolved`, which is that
      layer working correctly and has nothing to do with whether the producers ran. Driving
      to WORLDLINE with new prose would be testing the resolver with a request built for
      different prose.


## Phase 9 — Constitutional tests

- [x] T037 `apps/shared/tests/constitution/` — the invariants that outlive any feature, in
      their own package with no imports from any feature's code path. Three files:
      I-1/I-3 (immutability and preservation), IV/VI (tenancy and determinism), and
      constitution 4 with CD-7 (no fabrication, no loss of structure). 42 tests, 51 with the
      teeth file.
- [x] T038 Verify each names its own failure — **done by mutation, not by assertion.**
      `test_constitution_has_teeth.py` breaks each of eight invariants in a *copy* of the
      production packages and asserts that a specific named test notices. A test that cannot
      fail is not a test, and for a constitutional test it is worse than useless, because it
      gets cited as evidence of a guarantee nobody is keeping.

      **The harness found three real things, which is the point of running it.**

      1. **A constitutional property three types kept and one did not.** `RelationClaimMaterial`,
         `SemanticRegime` and `SourceTemporalObservation` all refused a carried address that
         disagreed with the derived one. `RelationCandidate` accepted a forged `candidate_id`
         silently — an id is only load-bearing if it is a function of the contents, and this
         one was adoptable. Fixed, so construction stays a plain value operation while a
         *carried* id is verified.
      2. **A type that let a row exist without a tenant.**
         `SourceTemporalObservation(tenant_id="")` constructed, although the schema has
         `ck_temporal_observation_tenant` and the other two types refused. Fixed.
      3. **A real property with no test at all.** Removing `producer_ref` from a signal's
         content address left the entire constitutional suite green — so the property that
         two producers reading one page are two observations (FR-034) was load-bearing and
         unguarded. Now tested, together with its mirror: confidence is *not* in the address,
         because a producer growing more sure of the same reading is not a second
         observation.

      Two harness bugs worth recording, because both produced *false passes*: the mutation
      copies have to include the test files (pytest puts the test file's rootdir at the front
      of `sys.path`, so running the original file imported the original `domain` and no
      mutation took effect), and this file has to be excluded from its own recursive
      "suite is green first" run or it never terminates.


## Phase 10 — Corpus and verification

- [x] T039 Expand coverage: active/passive realisations, n-ary event, unknown relation, link,
      table, metadata, conflicting text-vs-table, duplicate evidence across three producers,
      attribute value, document hierarchy. — **added as a second corpus**,
      `semantic_path/signal_corpus.py`, all ten scenarios.

      **A second corpus rather than ten more `CaseSpec`s, and the reason is mechanical.**
      Every case in :mod:`semantic_path.corpus` carries a resolution universe built for its
      own sentence, which is correct and also means a *producer that has not been resolved
      yet* cannot be covered there without inventing an entity per case. The signal layer
      runs **before** resolution, so it needs no universe at all — and testing it through
      the full path would have tested the resolver and reported a resolver failure. The two
      corpora cover disjoint layers and the boundary between them is the point.

      Two cases earned extra assertions because they found something:
      * ``nary_event`` states ``arity_mode`` **and** the role bindings, and the case asserts
        that the second without the first is **refused** with
        `role_assignment_on_directed`. A caller cannot hand over roles and have the platform
        guess the arity they imply — which is the mechanism working, so the case pins it.
      * ``attribute_value`` exposed that `SignalKind.ATTRIBUTE` was a declared kind **nothing
        produced**: a byline is a byline, not a key/value pair. A narrow visible `Key: value`
        reader was added to the metadata producer, and `by` is excluded from it so one fact
        is not reported twice (FR-034 counts signals).
- [x] T040 Re-record expectations and read the diff before writing —
      `semantic_path/signal_corpus_baseline.py`. Recorded digest
      `802e8ce88d7307bc…`, matching on re-run; all ten case digests distinct.

      **The diff that had to be read, and it is in the identity material.** Every golden-path
      `candidate_id` moved, because `extraction_method` is now `orchestrated` rather than
      `lexical_pattern`, `extraction_rule_id` is the producer list rather than one rule id,
      and `signal_refs` is new revision material. The old values described *one producer*,
      and the reading is now assembled — recording them would have put a false account of how
      the reading was made into the content address, so the lie would have been in the
      address rather than in a description. **`relation_id` values did not move**, which is
      the identity split doing its job: how a hypothesis was formed and what was concluded
      are separable.
- [x] T041 Invariance across two runs over signal, candidate, material and claim ids (SC-H);
      replay fixed point (SC-I). — golden corpus: 5 layers, **0 field differences**,
      `identical=True`; signal corpus: `identical=True`, 0 differences; two signal runs
      produce the same digest.
- [x] T042 Report the real bounds and blocking reduction (SC-J) — measured, on a 78 000- and
      94 000-character document:

      | producer | dense signals | sparse | dense/sparse |
      |---|---|---|---|
      | lexical | 2 000 | 0 | **45.6×** |
      | hyperlink | 0 | 0 | noise (no markup) |
      | table | 0 | 0 | noise (no markup) |
      | metadata | 0 | 0 | noise |

      All four are **linear**: ×4 characters gave ×4.13, ×0.87, ×1.88 and ×3.79 seconds. The
      lexical reduction is the meaningful number — a document that states nothing costs about
      0.2 % of one that states 2 000 relations, and the cost is in *building* the signals
      rather than in the sweep. Every producer claimed **0** pairs compared, which is the
      field that distinguishes a sweep from a reading.

      **A weakness, recorded rather than hidden:** `assert_bounded` runs on the signals a
      producer returned, so it catches a producer that misreported its extent and does not
      stop one that misreported it *while* doing unbounded work — the work is finished before
      the ceiling is consulted. The declaration is the only thing bounding a producer during
      its own run, which is why it is required and why its `cannot_read` field is required
      too.
- [x] T043 SC-M non-regression — **all five suites at baseline, plus the new work**:

      | suite | baseline | now |
      |---|---|---|
      | projection | 189 / 1 | **189 passed, 1 skipped** |
      | acquisition | 126 / 10 | **126 passed, 10 skipped** |
      | interpretation | 185 | **185 passed** |
      | admission | 96 | **96 passed** |
      | control-plane | 332 + 2 pre-existing | **332 passed, 2 failed (the same donor ones), 9 skipped** |
      | shared | 503 + 14 known | **571 passed, 14 failed (the same known ones), 8 skipped** |

      shared grew by 68: 17 CD-6 tests, 24 migration-parity tests, and 27 constitutional
      tests (42 invariant + 9 teeth). The 14 shared failures and 2 donor failures are the
      pre-existing sets, unchanged in membership.


## Dependencies

T001 → T002 → T003 → T004 → T005 → T006. The gate is first because `relation_ref` optional
changes the type everything else reads.

T007…T010 depend on T003 (the lifecycle reads the candidate's predicate).
T011…T014 independent of T001…T010.
T015…T018 independent of T001…T014.
T019…T022 depend on T003 (column shape) and T015 (temporal object); T020 additionally on the
T001 enumeration.
T023…T026 depend on T003 (signal's `relation_ref` optionality mirrors the candidate's).
T027…T030 depend on T023, T024.
T031…T033 depend on T023…T030.
T034…T036 depend on T031 and on T004/T005 (material now requires a resolved predicate).
T037…T038 depend on T004, T005, T034, FR-046.
T039…T043 depend on T034.

T011…T018 and T023…T030 are mutually independent and parallelise. T019…T022 is sequenced
internally because the widening sweep must precede the migration that carries it.
