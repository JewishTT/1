# Feature Specification: Finalize Entity / Relation Extraction Substrate

**Feature Branch**: `021-entity-relation-extraction-finalization`
**Created**: 2026-09-27
**Status**: Draft
**Base**: HEAD `00566655828258485795d58d38b5ebcdafb5ee9a` (previous constitutional point `81d8107`)
**Predecessor**: `specs/019-universal-relation-extraction/`

**Input**: User description: "Finalize the entity and relation extraction substrate: bounded
foundational atomic type vocabulary, first-class type hypotheses, real mention binding,
structural n-ary `RelationSignal` contract, `PredicateSignature`, corrected candidate identity
independent of raw surface, no majority-vote assembly, real execution lifecycle, durable
persistence and replay, graph projection of admitted claims only, golden corpus and
constitutional mutation tests."

> **The complete, unabridged user brief is `input.md` in this directory (3411 lines, all
> 115 sections, reproduced verbatim).** This document is the engineering reading of it. Where
> this document appears to compress or interpret something, `input.md` governs — in
> particular §0 (working mode), §45 (no majority vote), §51–56 (projection is a
> projection), §72–75 (structural prohibitions) and §110 (development order).
>
> The brief asks five questions, and this feature must keep them answered by five different
> objects rather than collapsed into one (§112, §102): **what was observed** →
> `Observation`/`Mention`/`RelationSignal`; **what could it be** →
> `TypeHypothesis`/`PredicateHypothesis`/`RelationCandidate`; **what our regime calls it** →
> `TypeAssertion`/`RelationRef`/mapping; **what survived validation and admission** →
> `RelationClaim`; **what graph view do we project** → `GraphEdge`/`HyperEdge`. The
> recommended end-state flow is §101; the eight golden examples it must represent are §109,
> and they are enumerated as the corpus in FR-075/FR-076 and SC-001…SC-003.

---

## Context: what already exists, and what is actually wrong

Feature 019 is committed at HEAD and is real work, not a report. It delivered
`RelationSignal`, `PredicateHypothesis`, `RelationCandidate` with an optional `relation_ref`,
`SourceTemporalObservation`, five signal producers, an assembler, a bounded-neighbourhood
contract, a forward-only migration `020` and 51 constitutional tests.

Its known defects, each traceable to a specific section of `input.md`:

| Defect | Where it lives | Required by |
|---|---|---|
| `logical_candidate_id` is keyed on raw `relation_surface`, so an active and a passive realisation are two hypotheses | `relation_candidate._logical_material` → `relation_identity.logical_material(arity_mode, relation_surface, ...)` | §17, §19, §23, §84 |
| Producers address synthetic `*_mention_ref` values (`surface:role:john smith`, `document:current`, `meta:author:…`) | `extractors/signals/lexical.py::_mention_ref`, `metadata.py`, `links.py` | §25, §26, §96 |
| `RelationSignal` is structurally binary; n-ary only survives via an `extra` tuple of tuples | `extractors/signals/signal.py` | §13, §14, §39, §88 |
| `relation_surface != '' OR relation_ref IS NOT NULL` makes `CO_OCCURRENCE` with no words unrepresentable | `signal.py::signal_asserts_nothing`, `relation_candidate.py::candidate_id_mismatch`, `relation_claim_material.py`, migration 020 CHECKs | §16, §40 |
| `_arity_of()` resolves a producer disagreement by **majority vote** | `semantic_path/assembly.py` | §45, §95 |
| `SignalKind` mixes observation channel with polarity, cardinality and adjacency: its 13 members are `LEXICAL`, `LINK`, `REFERENCE`, `TABLE`, `LIST`, `METADATA`, `ATTRIBUTE`, `HIERARCHY`, `SCHEMA`, `CO_OCCURRENCE`, `COREFERENCE`, `QUANTITY`, `NEGATION`. There is no `TEMPORAL` member — the brief names one, the code does not have it, and temporal axes already live in `stated_axes` | `signal.py::SignalKind` | §15 |
| **4 of those 13 kinds have no producer at all** (`CO_OCCURRENCE`, `COREFERENCE`, `QUANTITY`, `NEGATION`) — including the two the kind docstrings call the honest output | `extractors/signals/{lexical,links,tables,metadata}.py` | §15, §40 |
| The executable path still runs candidate → build → validate → admit → claim, then validates the claim again | `semantic_path/execution.py` | §57, §58 |
| `PredicateHypothesis` is stored only as a 64-char digest inside candidate material; its parts are unrecoverable | `relation_candidate._revision_material` | §60 |
| `SourceTemporalObservation` is reachable only through a helper no production path calls | `acquisition/stream.py::capture_with_observations` | §61 |
| No foundational atomic type vocabulary exists; `TypedMention.kind: str` is the only type surface | `extractors/types.py` | §4, §6, §7, §63 |

The following were found by reading the code during the 021 audit, not from the brief, and
are equally blocking:

| Defect | Where it lives | Consequence |
|---|---|---|
| `signal_refs` is identity material (`_revision_material`) but is never sorted or deduped, unlike `observation_refs`/`evidence_refs` which are | `relation_candidate.py::recompute_candidate_identity` | `candidate_id` depends on caller iteration order, falsifying the module's own "two processes assembling the same signals derive the same `candidate_id`" claim. Determinism holds only because `assembly.py:338` sorts by hand at one call site |
| `RelationCandidate` has no `to_dict`/`from_dict`, unlike every sibling value type | `relation_candidate.py` | No serialisation contract, so no lossless persistence is possible at all |
| `relation_candidate` has no `signal_refs`, `direction` or `confidence` column, and `polarity` is not a column on any table — it is a derived local in `assembly.py` only | `db/schema.py` | `signal_refs` enters `candidate_id` but leaves no durable record; a negated candidate is indistinguishable from an asserting one after a round trip |
| `RelationClaim.candidate_id` exists on the type but has no column, and the store neither writes nor reads it | `db/schema.py`, `db/relation_claim_store.py` | The claim → candidate link is silently dropped at the persistence boundary |
| `PredicateHypothesis.alternative_refs` and `mapping_evidence_refs` are inside `candidate_id` material but have no column | `db/schema.py` | Two candidates differing only in their alternatives get different ids with no stored reason |
| `extra` is excluded from `RelationSignal._material()`, and `extra` is where arity and role bindings live | `signal.py::_material` | Two signals differing only in their stated arity collapse to one `signal_id` and dedupe away |
| The whole `semantic_path` lifecycle has no production caller — `run_until`/`run_golden_path` are reached only from the corpus harness and tests | `semantic_path/execution.py` | Nothing today connects acquisition → producer → graph in production, so "production code" claims must be checked, not assumed |
| `RelationalReading.to_candidate()` is a second, dead, fully-functional path that builds a `RelationCandidate` without the assembler, falsifying assembly's "one code path" invariant | `extractors/relations.py` | A live, importable bypass of signal refs, arity and predicate hypothesis |
| `pairs_considered` is fabricated by two producers (`scanned // 16`, `scanned // 32`) and is always `0` in the third, so `max_pairs_considered` is either policed against an invented number or dead | `links.py`, `metadata.py`, `lexical.py` | The boundedness guarantee is not measured, so §47's boundedness is asserted rather than enforced |
| `metadata.py` uses a *property name* as the signal subject (`attribute:<key>`, `jsonld:<key>`), and falls back to the literal `document:current` when `document_ref` is empty, plus 64-char truncation on object refs | `metadata.py` | Asserts a relation between a field name and a value; empty `document_ref` makes every document in a batch collide on one participant ref, and truncation collides distinct values |
| `TableExtractor` pairs header↔cell positionally and silently drops width-mismatched rows; `ListExtractor` uses `zip(..., strict=False)` and silently truncates `<dt>` terms | `tables.py` | Data loss with no signal and no note — the mirror of the "confident falsehood" the module argues against |
| `Neighbourhood.precision` is a substring-tested string, and a heuristic header-row choice is published as `precision="exact; header row chosen by most <th> cells…"`, so `is_exhaustive` reads `"exact"` | `signal.py::Neighbourhood.is_exhaustive` | Exhaustive scanning is claimed for a heuristic scan |
| `OntologyPack.allows_relation()` is never called anywhere and `relation_type` is free-form text at every layer | `events/ontology_pack.py`, `relation_claim.py` | The one relation vocabulary in the repo is inert; nothing reconciles a `relation_type` with any operator |
| `logical_material()`/`logical_relation_id()` declare `valid_from`/`valid_to` kwargs that `logical_material` never reads, and both callers pass them | `relation_identity.py` | A reader trusting the signature concludes the validity window is in identity |
| Migration `020` is the Alembic **head** and is forward-only (`downgrade` raises `NotImplementedError`) | `migrations/versions/020_universal_relation_extraction.py` | 021 must add migration `021` on top of `020`; `020` must not be edited |
| `verify_candidate_material_partition()` is exported, never called, and would raise if called: 3 declared identity fields are never emitted, while its own comment asserts they are | `relation_candidate.py` | A verifier that is disabled and wrong is worse than none, because the docstring says it runs |
| `RelationClaim` is the only content-addressed type that does not re-derive and check its own carried `relation_id` | `relation_claim.py` | Forged ids are undetectable on claims, though they are on candidates, materials and temporal observations |
| `HyperlinkExtractor` emits a `LINK` and a `REFERENCE` signal per anchor with identical participant refs and identical `relation_surface`, differing only in `kind` | `links.py` | One hyperlink is counted as two independent corroborating observations by FR-034 |

Two of these are **not** defects and must not be "fixed":

- `RelationSignal._material()` includes `producer_ref`, so two producers reading the same
  structure get different `signal_id`s. That is correct — FR-034's independence count needs
  it (§24). The misleading part is the *documentation*, not the behaviour.
- The name `RelationSignal` is right. §12's complaint is about its *meaning* being unclear,
  and §22 explicitly forbids adding a fourth epistemic level.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A relation nobody has a name for survives intact (Priority: P1)

An analyst runs the platform over a document containing *"John is the originator of Acme."*
The vocabulary has no operator for `originator of`. Today the sentence still produces a
candidate, but its identity is a function of the exact string *"originator of"*, so a
paraphrase three words over becomes a different relation, and the platform cannot tell a
reader that both are the same claim about the world.

**Why this priority**: It is the constitutional heart of the feature. CD-7 says semantic
incompleteness must not reduce structural observability. If a paraphrase fragments a
hypothesis, the substrate is losing the world to the shape of its own vocabulary — the exact
failure 019 existed to fix, one level up.

**Independent Test**: Assemble two declarations, `"is the originator of"` and
`"was the originator of"`, over the same mention pair, and assert one `logical_candidate_id`
with two `candidate_id`s. Then assert `relation_ref is None`, `resolution_state == UNKNOWN`,
no claim, no edge — and that every surface, signal and alternative is still readable.

**Acceptance Scenarios**:

1. **Given** a candidate with `relation_surface="is the originator of"`, **When** a second
   reading over the same participants carries `"was the originator of"`, **Then** both
   resolve to one `logical_candidate_id` and distinct `candidate_id`s, and the predicate
   remains `UNKNOWN` with no `RelationRef` invented.
2. **Given** the same declaration with `"founded"` instead, **When** assembly runs, **Then**
   it produces a **different** `logical_candidate_id` — surface variation must not itself
   force *inequality* either (§20).
3. **Given** an unknown predicate candidate, **When** the claim-material boundary runs,
   **Then** it refuses with a message naming `relation_surface` and `SemanticRegime`, and
   the candidate remains storable and retrievable.

---

### User Story 2 — Active and passive realisations are one relation (Priority: P1)

*"John acquired Acme."* and *"Acme was acquired by John."* say the same thing. Today they
are two `CAND-` values, because identity keys on the surface string.

**Why this priority**: §84 makes it a named mandatory test, and it is the one place where a
design shortcut is invisible: a test that hard-codes both fixtures to the same id would pass
while the derivation still could not produce it.

**Independent Test**: Drive the syntactic producer over both sentences, assemble, and assert
one logical candidate, two signal ids, two surfaces, and that the *derivation* — not a
fixture — produced the shared id.

**Acceptance Scenarios**:

1. **Given** both sentences over the same mention pair, **When** assembly groups them,
   **Then** one `logical_candidate_id`, two `signal_id`s, two distinct `relation_surface`s,
   two distinct `candidate_id`s.
2. **Given** a mutation that adds `relation_surface` back into logical material, **When** the
   constitutional suite runs, **Then** it fails (§94).
3. **Given** `"John owns Acme"` and `"John manages Acme"`, **When** assembly runs, **Then**
   they do **not** merge — a normalized signature is not semantic equivalence (§20).

---

### User Story 3 — A producer cannot invent a mention (Priority: P1)

A structural producer reads an HTML table and finds *"John Smith"* in a cell. Today it
writes `cell:table0:john smith` into a field named `object_mention_ref` — a fabricated
identity in a field whose name promises a real one. The mention layer cannot join to it, and
nothing notices, because the value is a `str` and a `str` is exactly what the field
declares.

**Why this priority**: §25/§26/§96. This is the last place in the pipeline where a producer
is trusted to have invented an identity, and it silently breaks the join between the
observation substrate and the relation substrate.

**Independent Test**: Run the table producer over a document whose mentions were extracted,
and assert every `participant.mention_ref` resolves in the mention index. Then run the §96
mutation and assert it fails.

**Acceptance Scenarios**:

1. **Given** a table cell whose value was extracted as a mention, **When** the table producer
   runs, **Then** the participant's `mention_ref` is the real `MENTION-…` id.
2. **Given** a cell value that was **not** extracted as a mention, **When** the producer runs,
   **Then** it records the structural slot and a **deferred** participant reference that the
   binding stage can resolve later, and it does not mint an id.
3. **Given** a producer, **When** it is scanned, **Then** it imports no graph, claim,
   admission or projection symbol, and contains no `ENT-` or `RES-` literal (§74, §75).

---

### User Story 4 — "Apple" is allowed to be three things (Priority: P2)

A document mentions *Apple* next to *iPhone*. The platform currently records a single
`kind: "org"`. That is a decision made by a name-shaped grammar, with no evidence recorded
and no way to revisit it.

**Why this priority**: P2 rather than P1 because it is additive — the relation substrate can
be finished without it — but §3 makes the single-`kind` endpoint a constitutional violation,
and a foundational type vocabulary is a precondition for the mapping surface the relation
regime needs.

**Independent Test**: Extract a mention and assert more than one `TypeHypothesis` survives
with distinct confidence, evidence and state, that none is silently selected, and that a type
the `core:` pack has never heard of is still retained.

**Acceptance Scenarios**:

1. **Given** a mention surface with no pack entry, **When** extraction runs, **Then** a
   `TypeHypothesis` with `hypothesis_state=UNKNOWN` is retained, not dropped (§97).
2. **Given** an external `schema:Person` structured statement, **When** it is ingested,
   **Then** it produces a `TypeSignal` with mapping candidates, and **not** a
   `TypeAssertion(core:Person)` — a mapping record is required to cross (§9, §64).
3. **Given** one entity with several types, **When** assertions are read, **Then** they are
   separate assertions with separate scopes and evidence, and a later `INFERRED` status is a
   new revision (§10).

---

### User Story 5 — Three producers, one hypothesis, no dedup (Priority: P2)

A cue phrase, a table header and a JSON-LD block all describe the same employment relation.
The platform must record **one** hypothesis backed by **three** observations, and must not
collapse the three into one observation.

**Why this priority**: §85 and §24. It is the test that keeps FR-034 honest, and the
opposite failure — global dedup by content — is the mistake 019's own docs invited.

**Independent Test**: Run three producers over one pair, assert one logical candidate, three
signal ids, and that independence is computed over `producer_ref`/`independence_family`
rather than over deduplicated signal content.

**Acceptance Scenarios**:

1. **Given** three producers on one pair, **When** assembly runs, **Then** one
   `logical_candidate_id` with three `signal_refs` and three distinct `signal_id`s.
2. **Given** the same producer reading the same structure twice, **When** assembly runs,
   **Then** the two signals share one `signal_id`.
3. **Given** `John works_for Acme`, `John founded Acme`, `John owns Acme`, **When** assembly
   runs, **Then** three logical hypotheses, not one with three signals (§44, §86).

---

### User Story 6 — A denial is evidence, not noise (Priority: P2)

*"Acme did not acquire Beta."* The verb is real, the configuration is real, and the
polarity is denied.

**Why this priority**: §41/§87. The failure modes are symmetric and both are bad: dropping
the sentence loses an observed fact, and recording the acquisition is a lie. It is also the
cheapest place to prove `SignalAspect` earns its existence.

**Independent Test**: Extract the sentence and assert `polarity == DENIED`, the predicate
signature still normalises to `acquire`, and no positive candidate or edge results.

**Acceptance Scenarios**:

1. **Given** a negated acquisition, **When** assembly runs, **Then** a `DENIED` candidate
   exists with its predicate signature intact and no positive counterpart.
2. **Given** an independent positive observation of the same configuration, **When**
   assembly runs, **Then** both survive as separate polarity readings of one configuration.

---

### User Story 7 — An n-ary event keeps its shape (Priority: P2)

*"John sold Acme to Microsoft in 2020."* Three participants, four roles, a date. The binary
decomposition the platform reaches for loses the buyer and the date.

**Why this priority**: §39/§88. It is the only case that proves "n-ary is native" rather than
"n-ary is tolerated through a side channel".

**Independent Test**: Extract the sentence, assemble, and assert `arity=NARY` with
`seller`/`asset`/`buyer` roles and temporal evidence; then assert any binary projection
references the source hyperrelation claim (§54).

**Acceptance Scenarios**:

1. **Given** the sale sentence, **When** the event producer runs, **Then** one n-ary
   candidate with three participants and four roles, and the temporal expression attached as
   evidence with its precision (§38).
2. **Given** an n-ary claim, **When** projected, **Then** a `HyperEdge` is produced, and any
   derived binary edge names the claim it came from.

---

### User Story 8 — Everything the platform observed can be stored, read back and replayed (Priority: P1)

Signals, candidates, predicate hypotheses and stated instants are produced in memory.
Today the durable path stores a candidate's identity material — which contains the predicate
hypothesis *only* as an opaque digest — so a reader cannot recover the alternatives, the
mapping evidence or the normalized form.

**Why this priority**: Constitution III and domain invariant 12. A substrate that cannot be
reconstructed cannot be rebuilt, and a projection built on it is not rebuildable either.

**Independent Test**: Write every substrate object to its store, read it back, and assert
field-for-field equality of the reconstructed domain value. Then run → log → replay → replay
and assert every id is identical.

**Acceptance Scenarios**:

1. **Given** a predicate hypothesis with alternatives and mapping evidence, **When** it is
   stored and read, **Then** every part is recoverable without re-deriving from a digest
   (§60).
2. **Given** an EDGAR row with `date_filed`, **When** it is acquired, **Then** a
   `SourceTemporalObservation` at **day** precision is persisted by the normal path, and
   Common Crawl's stays an **index observation** (§61).
3. **Given** a full run and its log, **When** it is replayed twice, **Then** signal, candidate,
   material, claim and edge ids are identical, with no clock, randomness or dict-order
   dependency (§92).

---

### User Story 9 — The graph shows the world, not the extraction (Priority: P1)

Every edge must trace back to a claim, and forward from a source. An analyst must be able to
ask "how does the platform know this?" and walk to the source, and "what else did this source
produce?" and walk to every edge it fed.

**Why this priority**: Constitution II and III. It is the requirement that makes the whole
pipeline auditable, and §56 forbids solving it by putting unadmitted hypotheses into
`GraphEdge` — which is the tempting shortcut.

**Independent Test**: For a produced edge, walk `edge → claim → candidate → signals →
observations → source`, then walk the reverse direction from that source, and assert the
round trip reaches every edge that source fed.

**Acceptance Scenarios**:

1. **Given** a directed claim, **When** projected, **Then** source and target are preserved
   and never canonicalised by `min`/`max` (§52).
2. **Given** an undirected claim whose contract does **not** declare symmetry, **When**
   projected, **Then** no endpoint reordering happens — an unknown direction is not a
   symmetric relation (§53).
3. **Given** unadmitted candidates and signals, **When** the platform needs to show them,
   **Then** a separate hypothesis/evidence view serves them and `GraphEdge` is not reused
   (§56).

---

### Edge Cases

- **A co-occurrence with no predicate words.** Two mentions in one sentence, no verb. Must be
  representable with an empty `relation_surface` and a stated observational basis (§16).
- **A value that is also a name.** `john@example.com` is a value hypothesis, not a person;
  `+370…` is not a phone *entity*. Entity/value ambiguity is a stop condition (§111).
- **A header that spans columns.** A `<th colspan=3>` caption is not a column name. The
  header-row heuristic must be declared on the signal, not implied.
- **A row that does not line up.** Fewer cells than headers. Skipped, never positionally
  guessed, and the choice recorded — mispairing is a falsehood about the document's structure
  that still looks like a table (§34).
- **Two regimes disagreeing about one surface.** Same pair, same words, `works_for` under one
  regime and `affiliation` under another: one hypothesis, two readings, state `AMBIGUOUS` or
  `CONFLICTING`, nothing overwritten (§49, Case G).
- **A producer that misreports its extent.** The ceiling is checked after the work is done,
  which is a real weakness and is stated rather than hidden (§47).
- **An ambiguous name.** *Apple*, *Amazon*, *Jordan*, *Washington*, *Mercury* — competing
  hypotheses retained, none selected (§82).
- **No parser available.** Syntactic producer yields no signals; the batch does not fail
  (§30).
- **A mapping that is not equivalence.** `schema:SoftwareApplication → core:Software` is a
  narrower-than mapping and must be recordable as such (§64, SSSOM).

---

## Requirements *(mandatory)*

### Functional Requirements

#### Constitutional invariants

- **INV-001**: `Mention`, `Candidate`, `Entity`, `TypeHypothesis`, `TypeAssertion`,
  `RelationCandidate`, `RelationClaim`, `GraphNode`, `GraphEdge` remain distinct types.
  `mention.kind == entity.type` is never an identity theorem; one mention is never one
  entity; one entity is never one type; one relation surface is never one relation type. (§3)
- **INV-002**: The type vocabulary is an interpretation instrument — naming, hierarchy,
  aliases, blocking, role hints, mapping surface, validation vocabulary. It is never the
  definition of what exists, a permit/deny gate, a completeness condition, the source of
  truth, or a mandatory relation universe. (§2)
- **INV-003**: No producer drops an observation because the semantic layer does not
  understand it. An ontology miss yields `UNKNOWN`, never rejection. (§76, §97)
- **INV-004**: `GraphEdge`/`HyperEdge` are projections of admitted `RelationClaim`s only —
  never of a `RelationSignal` or a `RelationCandidate`. (§51, §99)
- **INV-005**: Evidence lineage and derivation lineage stay separate. A candidate is
  derivation, never evidence. (§68, §69)

### Identity

- **FR-001**: `RelationCandidate.logical_candidate_id` MUST NOT depend on raw
  `relation_surface`, `producer_ref`, `producer_version`, `signal_refs`, `capture_ref`,
  `context_ref`, `semantic_regime_ref`, `confidence`, `candidate_status`,
  `observation_refs` or any observation timestamp. Those are revision/evidence material. (§19,
  §23)
- **FR-002**: Logical identity MUST depend on tenant, participant configuration, arity shape,
  role shape, directional configuration, polarity and predicate signature. (§19)
- **FR-003**: System MUST provide a deterministic `PredicateSignature` carrying at least
  language, normalized trigger, lemma, normalized frame, normalized argument roles,
  voice normalization, preposition normalization, particle normalization and event-class hint.
  It MUST NOT be a `RelationRef` and MUST NOT be a semantic ontology concept. (§18)
- **FR-004**: Normalization MUST be deterministic and MUST NOT unify semantically distinct
  relations. `owns`/`controls`/`manages` MUST remain distinct. Surface variation must not
  force inequality, and similarity must not force equivalence. (§20)
- **FR-005**: A surface-variant pair (`"John acquired Acme"` / `"Acme was acquired by John"`)
  MUST derive the same signature **through the derivation itself**, never through a hard-coded
  fixture. (§18, §84)
- **FR-006**: `RelationSignal.signal_id` MUST remain producer-specific: same producer plus
  same observed structure gives the same id; different producers give different ids.
  Independence MUST be computed over `producer_ref`/`independence_family`, never over
  deduplicated signal content. (§24)
- **FR-007**: The candidate partition MUST stay two-level — `CAND-` answers "which relational
  configuration", `CNDR-` answers "which reading". No fourth epistemic level. (§22, §23, §103)

### Relation signal

- **FR-008**: `RelationSignal` MUST carry a first-class `participants: tuple[RelationParticipant, ...]`
  as its canonical participant representation, supporting 2..N participants without a fake
  binary decomposition. `subject_mention_ref`/`object_mention_ref` MAY remain as derived
  compatibility accessors for binary signals. (§13)
- **FR-009**: `RelationParticipant` MUST carry `mention_ref`, `slot`, `role_hypothesis`,
  `ordinal` and `confidence`. (§13)
- **FR-010**: The signal contract MUST explicitly support `role_hypotheses`,
  `arity_hypothesis`, `direction_hypothesis`, `polarity`, `predicate_surface`,
  `normalized_predicate`, `predicate_signature`, `structural_path`, `temporal_evidence`,
  `observation_refs`, `evidence_refs`, `extraction_rule_id` and `signal_ordinal`, in addition
  to the fields 019 introduced. Load-bearing dimensions MUST be typed, not JSONB. `extra` is
  for producer-specific non-core metadata only. (§14)
- **FR-011**: `SignalKind` MUST contain at least `LEXICAL`, `SYNTACTIC`, `STRUCTURAL`,
  `METADATA`, `LINK`, `REFERENCE`, `TABLE`, `LIST`, `EVENT`, `TEMPORAL`, `ATTRIBUTE`,
  `CO_OCCURRENCE`, `SEMANTIC`. `COREFERENCE`, `SCHEMA`, `QUANTITY`, `NEGATION` MAY remain,
  but MUST NOT substitute for a mandatory channel. (§15)
- **FR-012**: `NEGATION`, `TEMPORAL`, `QUANTITY`, `COREFERENCE` and `UNCERTAINTY` SHOULD move
  to a separate `SignalAspect`, so that `SignalKind` names an observation channel and not an
  orthogonal aspect. Make the smallest coherent change that removes the ambiguity. (§15)
- **FR-013**: A signal MUST NOT require `relation_surface` to be non-empty. A `CO_OCCURRENCE`
  with an empty surface MUST be representable, and `signal_asserts_nothing` /
  `relation_surface <> '' OR relation_ref IS NOT NULL` MUST be replaced by a requirement that
  every signal state an explicit observational basis. (§16)
- **FR-014**: The observational basis MUST be one of: predicate text, DOM relation, table slot,
  hyperlink, citation, proximity, metadata field, event frame, attribute key. (§16)
- **FR-015**: `polarity` MUST be explicit on every signal and MUST be `ASSERTED` or `DENIED`.
  A denied relation preserves its predicate surface and signature, and MUST NOT be dropped nor
  converted into a positive reading. (§41)

### Mention binding

- **FR-016**: No producer may invent a mention identity from text after the mention stage.
  Every `participant.mention_ref` MUST resolve in a mention index. (§25)
- **FR-017**: A structural producer observing a value that is not yet a mention MUST record
  the structural raw slot and produce a typed, deferred participant reference, never a
  synthesised id. (§25)
- **FR-018**: The platform MUST provide a `MentionOccurrenceIndex` with deterministic lookup on
  capture, segment, offset/span, normalized surface and extractor occurrence, resolvable to
  a real `MENTION-…` without resolving to an entity. (§26)
- **FR-019**: Mention binding MUST remain distinct from entity resolution. Producers may use
  mention ids after binding and MUST NEVER use `ENT-` or `RES-` literals. (§26, §75)
- **FR-020**: Producers MUST import no graph, claim, admission or projection symbol, with
  `TYPE_CHECKING` as the only exception and never in executable code. (§74)

### Predicate and claim boundary

- **FR-021**: `PredicateHypothesis` MUST preserve `surface_form`, `normalized_form`,
  `predicate_signature`, `relation_ref`, `alternative_refs`, `resolution_state` and
  `mapping_evidence_refs`. States are `KNOWN`, `UNKNOWN`, `AMBIGUOUS`, `CONFLICTING`. No
  `UNKNOWN_RELATION` sentinel and no fabricated `RelationRef`. (§21)
- **FR-022**: A signal mapping to a known operator (`"works at"` → `works_for`) MUST become
  typed only through explicit semantic interpretation under a regime. (§66)
- **FR-023**: A signal whose predicate has no operator MUST survive as a candidate with
  `predicate_state=UNKNOWN`, and the platform MUST remain able to answer what participants
  were observed, what structure connected them, what words were used, which type was unknown,
  what alternatives existed, which source and extractor produced it, and what temporal
  evidence existed. (§67)
- **FR-024**: `RelationClaimMaterial` MUST be constructible only when the predicate is
  resolved sufficiently for the claim schema, participants are resolved, and the required
  role structure is known. An unknown predicate yields candidate ✅, material ❌, claim ❌,
  edge ❌. No local relation type may be invented to make it eligible. (§50)

### Assembly

- **FR-025**: Assembly MUST group by structural participant configuration and MUST preserve
  direction, polarity, predicate signature, all signal refs and alternative interpretations.
  It MUST detect conflicts, MUST NOT resolve entities, MUST NOT admit claims and MUST NOT
  create a `GraphEdge`. Where lexical, table and structured-metadata producers all support
  the same participant configuration, assembly MUST be capable of producing one logical
  candidate carrying many signals — but only when they describe the same relational
  configuration (§43, §44). (§48)
- **FR-026**: Assembly MUST NOT adjudicate semantics by majority vote. `_arity_of()`-style
  resolution MUST be removed. A disagreement yields competing candidates or one ambiguous
  candidate with explicit alternatives, depending on the nature of the disagreement. (§45)
- **FR-027**: Distinct predicates over the same endpoints MUST remain distinct hypotheses.
  Equal endpoints MUST NOT merge them. (§44)
- **FR-028**: Two signals agreeing on surface but carrying different `relation_ref`s MUST
  yield one logical hypothesis whose predicate is `AMBIGUOUS`, with neither interpretation
  overwritten; genuine disagreement yields `CONFLICTING` with both preserved. (§49)

### Types

- **FR-029**: A versioned foundational type pack MUST exist, exposing per type: `type_ref`,
  `label`, `alt_labels`, `broader_refs`, `narrower_refs`, `description`, `kind ∈ {entity,
  value}` and `version`. It MUST NOT encode relation semantics and MUST NOT encode truth; it
  MAY carry blocking hints. (§4, §63)
- **FR-030**: The pack MUST cover, at minimum, entity classes `core:Person`,
  `core:Organization`, `core:LegalEntity`, `core:Group`, `core:Agent`, `core:WebSite`,
  `core:WebPage`, `core:OnlineAccount`, `core:SocialProfile`, `core:Domain`,
  `core:DigitalResource`, `core:PhysicalPlace`, `core:Facility`, `core:Address`,
  `core:GeographicRegion`, `core:Country`, `core:StateOrProvince`, `core:City`,
  `core:Coordinate`, `core:Document`, `core:Dataset`, `core:CreativeWork`,
  `core:MediaResource`, `core:Software`, `core:Project`, `core:Product`, `core:Service`,
  `core:Asset`, `core:Vehicle`, `core:FinancialInstrument`, `core:Event`. (§4)
- **FR-031**: Value types MUST be conceptually separate from entity classes: `value:
  EmailAddress`, `value:PhoneNumber`, `value:URL`, `value:Handle`, `value:Identifier`,
  `value:IPAddress`, `value:Hash`, `value:CryptoAddress`, `value:Date`, `value:DateTime`,
  `value:Money`, `value:Quantity`, `value:Coordinate`. A value MUST NOT be forced into
  `Entity`. (§4)
- **FR-032**: `TypeHypothesis` MUST be a first-class type carrying at least `type_surface`,
  `normalized_surface`, `type_ref`, `scheme`, `hypothesis_state`, `confidence`, `source_ref`,
  `extractor_ref`, `extractor_version`, `evidence_refs`, `context_ref`, `semantic_regime_ref`
  and `mapping_candidates`, with states `UNKNOWN`, `OBSERVED`, `INFERRED`, `MAPPED`,
  `AMBIGUOUS`, `CONFLICTING`. It MUST be distinguishable from `TypeAssertion`, which is
  evidence-bearing. (§6)
- **FR-033**: A mention MUST be able to hold several competing `TypeHypothesis` values with
  distinct confidence, evidence and state, with none silently selected. `TypedMention.kind`
  MAY be retained as a coarse producer classification. (§7)
- **FR-034**: The type space MUST be extensible by hierarchy (`core:Organization` →
  `industry:Bank` → `industry:CommercialBank`), and `broader`/`narrower` relations MUST be
  usable for query expansion, blocking, ranking, validation and role matching — never as an
  extraction gate. Unknown remains unknown. (§5)
- **FR-034a**: Type and relation policy MUST be the one stated in §104 and §65: a bounded,
  modularly-extensible *type* space is desirable because it supplies coarse semantic
  affordances, blocking, typing, query expansion and interpretation; a finite mandatory
  *relation* list is forbidden because relations are too dependent on context, source
  vocabulary, language, document structure, task, semantic regime, temporal frame and event
  structure. The relational space begins as observed structure and only later becomes a known
  predicate when the semantic system earns that mapping.
- **FR-035**: External vocabularies (JSON-LD, schema.org, OpenGraph, RDFa, microdata, HTML
  metadata) MUST produce a `TypeSignal` with `source_vocab`, `surface` and
  `mapping_candidates`, and MUST NOT immediately produce a `TypeAssertion`. (§9)
- **FR-036**: A type mapping MUST retain subject type, object type, mapping predicate,
  mapping set, mapping version, confidence, creator/operator and evidence/provenance, and MUST
  NOT collapse `schema:Person` into `core:Person` without a mapping record. SSSOM-compatible
  semantics apply, and a non-equivalence match MUST be recordable as such. (§9, §64)
- **FR-037**: The type pipeline MUST run `Observation → Mention → TypeSignal →
  TypeHypothesis → SemanticRegime interpretation → TypeAssertion`, retaining all prior states.
  A later `INFERRED` status MUST be a new revision, not a destructive replacement. (§10)
- **FR-038**: Entity type extraction MAY use the `core:` vocabulary, external mappings and
  the hierarchy as aids, but an ontology miss MUST mean `unknown type`, never a rejected
  mention. (§76)
- **FR-039**: Type resolution SHOULD consume already-available context — document title,
  section heading, DOM parent, table heading, neighbour mentions, URL/domain, metadata,
  language — and MUST represent competing hypotheses with evidence rather than encoding a
  universal deterministic truth rule. (§77)
- **FR-039a**: A mention's type hypotheses and a relation signal's role hypotheses MUST be
  mutually consumable, so resolution and blocking can exploit both — e.g. a `works_for`
  operator hinting a `Person-like` subject and an `Organization-like` object. Those hints MUST
  remain hints and MUST NOT become truth. (§71)

### Producers

- **FR-040**: `LEXICAL`, `SYNTACTIC`, `STRUCTURAL`, `LINK`, `REFERENCE`, `TABLE`, `LIST`,
  `METADATA`, `ATTRIBUTE`, `EVENT`, `TEMPORAL`, `CO_OCCURRENCE` and `SEMANTIC` MUST all be
  implementable producer families writing to the identical downstream model. "Universal"
  means a common observation language, not 500 extractors. (§27)
- **FR-041**: The existing lexical producer MUST remain one producer and MUST be upgraded to
  emit raw predicate surface, normalized predicate, predicate signature, participant roles,
  direction hypothesis, arity and trigger/support evidence. `RELATION_CUES` MUST be retained
  as one lexical instrument and MUST NOT define the global relation vocabulary. (§28)
- **FR-042**: A syntactic producer MUST support at least active, passive, copular, nominal,
  appositive, possessive, prepositional and relative-clause realisations, emitting structural
  signatures and role hypotheses. It MUST NOT emit `works_for`/`founded`/`owner_of` unless the
  mapping layer says so. (§29)
- **FR-043**: A parser capability MUST be explicit and pinned: `model_ref`, `model_version`,
  `parser_version`, `configuration_hash` are part of interpretation provenance. No LLM in the
  constitutional extraction path. A missing parser MUST mean no syntactic signals, never
  batch failure. (§30)
- **FR-044**: A structural producer MUST represent `structural_path` — DOM parent/child,
  section membership, heading → content block, breadcrumb, caption → table, figure → caption,
  document → subsection, page → document — and MUST NOT flatten structure into a predicate
  such as `member_of_board`. (§31)
- **FR-045**: The link producer MUST preserve source mention, target/resource mention, href,
  anchor text, DOM path, link position, `rel` attribute and target metadata, and MUST assert
  only `A links to B` — never `cites`, `owns`, `hosts` or `employs` without a separate
  interpretation. `rel="author"` may strengthen a signal and is still only a candidate. (§32)
- **FR-046**: The reference/citation producer MUST support footnotes, references, citation
  markers, `see …`, `as described in …`, DOI/reference patterns and document ids, emitting
  `REFERENCE` signals and never `cites` automatically. (§33)
- **FR-047**: The table producer MUST preserve `table_ref`, `row_ref`, `column_ref`,
  `header_ref`, `cell_ref` and `participant_ref`, and MUST treat a row as structural evidence
  for an n-ary configuration. Malformed tables MUST be refused or skipped by explicit
  structural rules and MUST NEVER be positionally guessed. No ontology relation is required
  before emitting. (§34)
- **FR-048**: The list producer MUST handle term/item structure, producing structure, role
  hints and participant slots without creating semantic relations. (§35)
- **FR-049**: The metadata producer MUST cover author, publisher, creator, canonical URL,
  site, section, category, parent, path and domain, plus unrecognised metadata which MUST
  survive. `author` MUST NOT be mapped to `authored_by` automatically. (§36)
- **FR-050**: The attribute producer MUST represent `Key: value` observations, and MUST NOT
  turn a value into an entity. `entity → scalar value`, `entity → typed value` and
  `entity → entity` MUST be explicitly distinguished. (§37, §89)
- **FR-051**: The temporal producer MUST attach temporal expressions to a signal/hypothesis
  as evidence with surface, normalized interval, precision and evidence span, and MUST NOT
  promote an inferred interval to world truth. §38
- **FR-052**: The event producer MUST support n-ary event structures and MUST NOT reduce
  `"John sold Acme to Microsoft in 2020"` to two binary edges at the substrate level. Binary
  projection may derive selected edges under an explicit policy, and the original event
  structure MUST never be discarded. (§39, §88)
- **FR-053**: The co-occurrence producer MUST report A and B appearing in the same
  sentence/block/window, and MUST NEVER convert to `related_to`. It is usable for blocking,
  discovery, hypothesis generation, query expansion and contextual reconstruction. (§40)
- **FR-054**: The semantic producer MAY consume schema.org, JSON-LD, mapping systems, domain
  vocabularies and profile annotations, but only to create interpretation candidates, and
  MUST NEVER turn an ontology match into automatic truth. (§42)

### Lifecycle

- **FR-055**: The executable path MUST implement, in order and with each stage exposing the
  object it produced: `OBSERVATION`, `CONTEXT`, `MENTIONS`, `TYPE_SIGNALS`,
  `RELATION_SIGNALS`, `REGIME`, `RELATION_CANDIDATE`, `RESOLUTION`, `CLAIM_MATERIAL`,
  `VALIDATION`, `ADMISSION`, `STORE`, `EDGE`, `WORLDLINE`. (§57, §58)
- **FR-056**: The claim lifecycle MUST be `Candidate → ClaimMaterial → Validation →
  Admission → RelationClaim`, and `RelationClaim → Validation` MUST NOT be the primary
  lifecycle. No fake `SUPPORTED` technical gate. (§57)
- **FR-057**: `ExecutionResult` MUST expose `material` as a real stage product. A stage that
  is semantically material but silently validates or admits is not acceptable. (§58)
- **FR-058**: A `GraphEdge` or `HyperEdge` MUST exist only after a `RelationClaim`. (§108)

### Persistence

- **FR-059**: Durable store seams MUST exist for `RelationSignal`, `RelationCandidate` and
  `SourceTemporalObservation` with `write`, `get`, `by_tenant`, `by_logical_id`, `by_pair`,
  `by_signal` and checksum/replay support where architecturally appropriate. (§59)
- **FR-060**: Every store MUST reconstruct the exact domain object. A round trip MUST
  preserve ids, alternatives, signals, provenance, type hypotheses, predicate signature,
  temporal evidence, tenant, context and regime. A digest may identify data; a digest MUST
  NOT be the only copy required for reconstruction. Every new substrate object MUST have a
  build → store → read test asserting that list, not a summary string. (§59, §60, §91)
- **FR-061**: The normal acquisition path MUST persist `SourceTemporalObservation`:
  `adapter → Capture + SourceTemporalObservation → durable store`. The helper no production
  path calls MUST NOT be the only route. EDGAR `date_filed` MUST stay day-precision; Common
  Crawl `timestamp` MUST stay index-observation time; source publication time MUST NOT be
  stuffed into `Capture.fetched_at`. (§61)
- **FR-062**: A new forward-only migration MUST be created if required. Applied migrations
  MUST NOT be modified. It MUST preserve data, be tenant-scoped, add CHECKs only for
  constitutional invariants, keep ORM/migration parity, and never drop historical semantic
  observations. Migration parity tests, schema invariant tests and round-trip tests MUST be
  created. (§62)

### Projection

- **FR-063**: `DIRECTED` claims MUST project with direction preserved and MUST NOT
  canonicalise endpoints by `min`/`max`. (§52)
- **FR-064**: `UNDIRECTED` projection MAY canonicalise endpoint ordering **only** when the
  admitted relation contract declares symmetry. Symmetry MUST NOT be inferred from an
  extractor not knowing the direction. (§53)
- **FR-065**: `NARY` claims MUST project to `HyperEdge` or the existing native n-ary
  abstraction. Flattening to binary edges requires an explicit policy, the original
  hyperrelation remaining available, and each derived edge referencing its source claim. (§54)
- **FR-066**: Entity-to-value relations MUST be distinguishable from entity-to-entity
  relations in the claim and projection layer; `Person → email → EmailAddress` MUST NOT be
  forced into a normal entity graph. (§55)
- **FR-067**: An explicit hypothesis/evidence view MUST serve extracted-but-unadmitted
  relations. `GraphEdge` MUST NOT be reused for it. World graph, hypothesis graph and
  evidence graph are distinct projections. (§56)
- **FR-068**: For every edge the platform MUST be able to navigate to `RelationClaim`,
  `Candidate`, `Signals`, `Observations` and `Source`, and from a source back to every edge
  it fed, making the projection rebuildable. (§78)
- **FR-069**: Projection MUST preserve enough metadata to answer which claim, which relation
  revision, which logical relation, which predicate interpretation, which evidence, which
  temporal interval, which regime, which validation and which source independence produced
  the edge. This metadata MUST NOT go into edge identity. (§79)
- **FR-070**: RDF-compatible shape is permitted (subject/predicate/object for binary claims,
  statement-level annotation for provenance), but RDF MUST NOT become the internal model.
  SHACL remains an optional sidecar and the core architecture MUST NOT depend on
  draft-only SHACL 1.2 behaviour. (§80, §81)

### Boundedness and determinism

- **FR-071**: Candidate generation MUST follow generate-wide-within-bounded-neighbourhood →
  hard block → resolve → semantic interpretation → validate → admit. An all-mentions ×
  all-mentions sweep is forbidden. Required neighbourhood classes: same sentence, same
  segment, same paragraph/block, dependency-connected, DOM-local, table-local, list-local,
  metadata-local, event-participant, reference-local, explicit link. Every signal MUST state
  its actual neighbourhood. (§46)
- **FR-072**: Every producer MUST expose and report `characters_scanned`,
  `tokens_scanned` where meaningful, `candidate_pairs_considered`,
  `structural_nodes_considered` and `signals_emitted`. Hard per-document/per-segment ceilings
  MUST be explicit and the implementation itself MUST remain bounded — a counter checked
  after the work does not make the work bounded. (§47, §106)
- **FR-073**: Two independent runs MUST be identical. Producer order MUST NOT alter ids. No
  `uuid.uuid4()`, no `datetime.now()`, no dict-order-dependent output, no random tie-breaking.
  (§92, §108)
- **FR-074**: No hidden semantic gate: extraction MUST NOT call `OntologyPack.allows_type()`
  as a drop/deny decision, and relation extraction MUST NOT contain `if relation not in
  registry: continue` or equivalent. (§73)

### Verification

- **FR-075**: A deterministic golden entity-type corpus MUST cover the surfaces named in §82,
  including the ambiguous names, and each case MUST test raw mention, type hypotheses, mapped
  type, unknown types, alternative types and the absence of an entity-resolution assumption.
- **FR-076**: A deterministic golden relation corpus MUST cover the text, event, structural,
  unknown, ambiguous and conflicting cases named in §83, and MUST include the six end-to-end
  HTML cases of §70 (cue phrase, passive, hyperlink, table, `Founder:` attribute, n-ary
  sale) as the executable form of the eight golden examples in §109.
- **FR-077**: An active/passive identity test MUST exist in which the **derivation itself**
  produces the shared `logical_candidate_id`; hard-coding both fixtures to one id is forbidden.
  (§84)
- **FR-078**: A constitutional mutation harness MUST break entity-layer fields (`type_ref`,
  `entity_ref`, `tenant`, `evidence`, `mapping`, `status`), relation-layer fields
  (`predicate_signature`, `participants`, `roles`, `polarity`, producer identity, signal
  evidence, candidate identity, surface exclusion from logical identity) and projection fields
  (`direction`, `arity`, claim provenance, edge identity), and a **named** test MUST fail for
  each. (§93)
- **FR-079**: Four named mutations MUST exist and MUST fail their named tests: adding
  `relation_surface` to logical identity material (§94); majority-vote resolution of
  conflicting arity/direction (§95); synthetic `surface:person:john` instead of a real
  `MENTION-*` (§96); `if core pack does not know type: continue` (§97); `if relation_ref is
  None: return ()` (§98); and any producer importing or constructing `GraphEdge` (§99).
- **FR-080**: The extraction layer MUST remain linear or bounded-superlinear within named
  local structures, and every producer MUST report input size, signals produced, pairs
  considered, structural nodes considered and time. (§106)
- **FR-081**: No regression may be introduced into `projection`, `acquisition`, `interpretation`,
  `admission`, `control-plane` or `shared`. Existing known failures MUST remain unchanged
  unless directly affected, and baseline membership, new failures, fixed failures and new
  tests MUST all be tracked. Reporting "green" while new failures hide among known ones is
  forbidden. (§107)

### Verified 019 defects requiring substrate work

These come from reading the code, not from the brief. Each is a real defect found at HEAD.

- **FR-085**: `RelationCandidate.signal_refs` MUST be canonicalised on construction, exactly
  as `observation_refs`, `evidence_refs` and `supporting_spans` already are, so that
  `candidate_id` cannot depend on caller iteration order. Determinism MUST hold from the
  type, not from a sort at one call site. (§61, §102)
- **FR-086**: `RelationCandidate` MUST gain `to_dict()`/`from_dict()` and MUST round-trip
  every one of its 26 fields losslessly, including `signal_refs`, `direction`, `polarity`,
  `alternative_refs`, `mapping_evidence_refs` and `confidence`. (§59, §60, §91)
- **FR-087**: A `predicate_signature` MUST be persisted in its own columns on both
  `relation_signal` and `relation_candidate` — normalised form, arity, role names, argument
  shape, direction and polarity — so that candidate identity no longer depends on a raw
  surface string and `PredicateHypothesis` is not stored as an opaque digest. (§59, §60, §91)
- **FR-088**: `relation_candidate` MUST gain columns for `signal_refs`, `direction`, `polarity`
  and `confidence`; `relation_claim` MUST gain `candidate_id`; and the store MUST write and
  read all of them. No field that participates in an id may be absent from the row. (§60, §91)
- **FR-089**: `RelationSignal._material()` MUST include the declared arity mode and role
  bindings, so two signals differing only in their stated shape do not collapse into one
  `signal_id`. `producer_ref` MUST remain in the material — that part is correct — and the
  three docstrings claiming two producers reading one structure share a `signal_id` MUST be
  corrected. (§24, §61)
- **FR-090**: A conflict over arity, direction, polarity or role bindings MUST yield
  `CandidateStatus.CONTRADICTED` with both readings preserved, and MUST be reported in
  `AssemblyReport` as a conflict. Majority vote and alphabetical tie-break MUST be deleted
  from `_arity_of`, and its `-> Any` return annotation MUST become `RelationArityMode`. A
  declared `NARY` schema MUST NOT be downgraded to `DIRECTED` by a vote, and losing the vote
  MUST NOT silently drop the role bindings with it. (§45, §95)
- **FR-091**: `RelationalReading.to_candidate()` MUST be removed, or reduced to a call into the
  assembler, so that "how does a signal become a candidate" has exactly one answer in the
  codebase and not merely one documented answer. (§48, §57)
- **FR-092**: The lifecycle MUST be split so that materialisation, validation, admission and
  projection are separately observable, the `ValidationReport` that gated admission is
  retained and surfaced rather than discarded as a local, the post-admission re-validation is
  removed or justified, and the admission decision actually gates the store write instead of
  being computed and discarded. Production writes MUST NOT be doubled to demonstrate
  idempotency. (§57, §58)
- **FR-093**: `pairs_considered` MUST report something real. A producer that performs no pair
  enumeration MUST report `0` with a stated reason; a producer that does MUST report its
  actual count. Fabricated divisors (`scanned // 16`, `scanned // 32`) MUST be deleted, and
  `max_pairs_considered` MUST be a live ceiling that can be exceeded by a real violation.
  (§46, §47)
- **FR-094**: A producer MUST NOT use a field name, a property name, a document placeholder or
  a truncated string as a participant. The `document:current` fallback MUST be removed in
  favour of a required `document_ref`, the 64-char truncation MUST be replaced by a full
  content address, and `metadata.py` MUST stop asserting relations between a key and a value.
  (§25, §26, §96)
- **FR-095**: Structural data loss MUST be reported, not silent. `zip(..., strict=False)` in the
  list producer MUST become strict, a width-mismatched table row MUST emit a note or a signal
  rather than being dropped, and a heuristic header-row choice MUST NOT be published as
  `precision="exact"`, since `is_exhaustive` is a substring test on that string. (§46, §47)
- **FR-096**: `SourceTemporalObservation` MUST be reachable from the normal acquisition path.
  `capture_with_observations()` MUST be called by `capture()`/`captures()` or replaced by the
  equivalent, `source_temporal_observation` MUST gain a repository with a writer and a reader,
  and the two adapters that already implement `to_temporal_observations` MUST have their
  output actually consumed. (§61)
- **FR-097**: Migration `021` MUST be added on top of `020`, which is the current Alembic head
  and is forward-only. `020` MUST NOT be edited. `021` MUST add every column FR-087/FR-088
  require, and ORM/migration parity MUST stay test-enforced.
- **FR-098**: `verify_candidate_material_partition()` MUST either be called and made correct
  or be deleted. A disabled verifier whose comment asserts it passes is worse than no
  verifier, and the 3 identity fields it fails to see MUST be reconciled with the declared
  `CANDIDATE_LOGICAL_MATERIAL_FIELDS` naming `relation_type` where the code emits
  `relation_surface`.
- **FR-099**: `RelationClaim` MUST re-derive and check its own carried `relation_id`, as every
  other content-addressed type in the layer already does, so a forged id is detectable on a
  claim and not only on a candidate.
- **FR-100**: The semantic path MUST be wired into the live production path, not only into the
  corpus harness. The seam is already built: `POST /api/v1/entities` →
  `services/entity_pipeline.py::run_live_entity_pipeline` / `workflows/temporal_materialization.py::reconcile_and_publish`
  → `services/capture_interpretation.py::interpret_warc_capture`, which both existing
  production branches already funnel through. That function currently runs only the 007-era
  `RelationExtractor`; it MUST additionally run the 019 producers, assembly, admission and
  projection. `ExecutionRequest.producers` — declared, never assigned by anyone — MUST be
  populated with the real producers, which is what makes `run_producer` iterate at all
  (`lexical_signals` has never been called by anything in the repository). (§101, §108, §114)

### Production reachability, as measured

Read-only reachability findings. Each row was verified by searching non-test importers, and
each is a place where the feature could be built and still never run.

| Component | Non-test production importer | Consequence |
|---|---|---|
| `semantic_path.execution.run_until` | **none** — corpus + tests only | The whole 019 lifecycle is test-only |
| `ExecutionRequest.producers` | **never assigned** | `run_producer` has zero iterations on every run |
| `extractors.signals.lexical.lexical_signals` | **none** | The primary prose producer has never run |
| `semantic_path.assembly.assemble` | **none** | No candidate is ever assembled in production |
| `db/relation_claim_store.py::SqlRelationClaimStore` | **none** (558 lines) | Claim persistence is unwired, and its `record_validation`/`non_valid` raise `NotImplementedError` |
| `relation_signal` / `relation_candidate` / `source_temporal_observation` | **no repository, writer or reader at all** | The three tables 020 created are written by nothing |
| `projection/graph/relation_store.py::GraphProjectionBridge` | **none** outside the dead path | The claim→graph adapter is unused |
| `projection/graph/neo4j.py::Neo4jGraphStore` | **none**; and the module never imports `neo4j` | `neo4j>=5.21` is declared in `control-plane` but `projection`, which needs it, does not declare it; `neo4j_uri` in settings is read by nothing |
| `projection/graph/snapshot.py::RebuildableGraphStore` | **none** | There is no wired rebuild-from-store path |
| `interpretation/pipeline.py::InterpretationPipeline` | **none** — tests only | The documented composition root is unused |
| `services/layer0_pipeline.py::Layer0Pipeline` + its `InterpretHook` seam | **none** — tests only | The intended binding point for real interpretation is unwired |
| `workflows/investigation.py` (`InvestigationWorkflow`, `RecrawlWorkflow`) | **unregistered**; calls two activities that exist nowhere | Dead workflow surface |
| CI (`.github/`) | **does not exist** | Nothing enforces the gate; `docs/quickstart-validation.md` (2026-09-17) is the only recorded baseline and predates 016–021 |



- **FR-082**: Encountering a new ontology requirement, a relation-identity ambiguity, an
  external-vocabulary mapping ambiguity, an entity/value ambiguity, a parser capability that
  cannot be made deterministic, or a persistence representation that loses information MUST
  stop the work and be reported explicitly, using `UNKNOWN`, `AMBIGUOUS`, `CONFLICTING` or
  `UNSUPPORTED` rather than a guessed type or relation. (§111)

### Specification deliverables (§100)

- **FR-083**: This feature MUST ship `specs/021-entity-relation-extraction-finalization/`
  containing `spec.md`, `plan.md`, `tasks.md`, `data-model.md`, `research.md`,
  `checklists/requirements.md` and a `contracts/` directory, plus ADR-level records for
  decisions A–K: bounded foundational atomic vocabulary is allowed; entity/value type
  vocabulary is separate from relation vocabulary; relation extraction is open-world and
  signal-driven; raw relation surface is evidence, not logical identity; `PredicateSignature`
  is structural normalised identity before ontology mapping; unknown predicates are durable
  hypotheses; n-ary relations are native; `GraphEdge` is a projection of admitted claims
  only; mention binding is distinct from entity resolution; no majority-vote semantic
  assembly; producers remain observation instruments.
- **FR-084**: The completion report MUST distinguish `implemented`, `verified`,
  `verified only offline`, `known limitation` and `deferred`, and MUST NOT claim the feature
  complete merely because tests pass. "Feature complete" requires that the §101 architecture
  is actually represented in production code and that the golden and mutation corpora prove
  the constitutional properties. (§114, §108)

### Key Entities

- **RelationParticipant**: one end of an observed relational configuration — `mention_ref`
  (or a deferred reference), `slot`, `role_hypothesis`, `ordinal`, `confidence`.
- **PredicateSignature**: deterministic structural normalisation of a predicate realisation.
  Not a `RelationRef`; the bridge between linguistic realisation and relational
  configuration.
- **PredicateHypothesis**: the open-world reading of a predicate — surface, normalised form,
  signature, ref, alternatives, resolution state, mapping evidence.
- **TypeHypothesis**: an interpretation candidate for what a mention is. Distinct from
  `TypeAssertion`, which is evidence-bearing.
- **TypeSignal**: what a structured or lexical source stated about a type, with
  `source_vocab`, `surface` and mapping candidates.
- **TypeMapping**: an SSSOM-compatible record crossing two vocabularies, with match type,
  provenance and confidence.
- **CoreTypePack**: the versioned foundational `core:*` / `value:*` vocabulary.
- **RelationSignal**: "this producer observed a relational configuration between these
  participant slots". Not "this relation holds", not "this is type X", not "create an edge".
- **RelationCandidate**: the durable hypothesis. One relational configuration, many readings.
- **RelationEvidenceView**: a projection of unadmitted candidates and signals, distinct from
  the world graph.
- **MentionOccurrenceIndex**: deterministic surface-occurrence → `MENTION-…` lookup, distinct
  from entity resolution.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `"John acquired Acme."` and `"Acme was acquired by John."` produce **one**
  `logical_candidate_id`, two `signal_id`s, two distinct `relation_surface`s and two
  `candidate_id`s — derived by the identity function, not by a fixture.
- **SC-002**: `"John is the originator of Acme."` produces a signal, a candidate, a
  preserved surface, a normalised predicate, a signature, `relation_ref=None`,
  `state=UNKNOWN`, **no** claim and **no** edge, with every piece of evidence still
  retrievable — the §90 unknown test, end to end.
- **SC-003**: `"John sold Acme to Microsoft in 2020."` produces one `NARY` candidate with
  `seller`/`asset`/`buyer` roles and year-precision temporal evidence, with no information
  lost to a binary collapse.
- **SC-004**: Every `participant.mention_ref` emitted by any producer resolves in the
  mention index; zero synthetic `*_mention_ref` values remain in production producer code.
- **SC-005**: Three producers over one pair yield one logical candidate with three signal
  ids; the same producer reading the same structure twice yields one signal id.
- **SC-006**: Conflicting arity/direction signals produce competing candidates or one
  explicitly ambiguous candidate — never a majority-vote winner. A mutation reinstating
  majority vote fails its named test.
- **SC-007**: `John works_for Acme`, `John founded Acme`, `John owns Acme` produce three
  logical hypotheses.
- **SC-008**: A predicate hypothesis with alternatives and mapping evidence round-trips
  through its store with every part recoverable, not merely a matching digest.
- **SC-009**: An EDGAR row yields a persisted `SourceTemporalObservation` at day precision and
  a Common Crawl row yields an index-observation one; neither reaches `Capture.fetched_at`.
- **SC-010**: Run → log → replay → replay yields identical signal, candidate, material, claim
  and edge ids, with no clock, randomness or dict-order dependency.
- **SC-011**: Zero producers import a graph, claim, admission or projection symbol, and zero
  contain an `ENT-` or `RES-` literal; each is a named mutation test.
- **SC-012**: A co-occurrence signal with an empty `relation_surface` is constructible,
  persistable and assemblable.
- **SC-013**: For every projected edge, the round trip `edge → claim → candidate → signals
  → observations → source` and back reaches every edge that source fed.
- **SC-014**: A `DIRECTED` edge never has its endpoints reordered; an `UNDIRECTED` edge is
  reordered only when the admitted contract declares symmetry.
- **SC-015**: The constitutional mutation harness breaks ≥ 20 distinct invariants across
  entity, relation and projection layers, and a **named** test fails for each.
- **SC-016**: All six 019 suites hold their baseline membership exactly, with no new failures.

### Constitutional non-goals

- The platform MUST NOT require that every relation be one of a finite operator list before
  preserving it. (§1B, §65)
- The platform MUST NOT make schema.org, Wikidata, DBpedia or GeoNames the canonical internal
  world model. They are external semantic sources and mapping targets. (§2, §105)
- The platform MUST NOT create a fourth epistemic level between signal and claim. (§103)
- The platform MUST NOT optimise toward "find all edges" — see `input.md` §113 for the
  governing statement.

---

## Assumptions

- The 019 work at HEAD is a starting point, not verified correctness. Every claim this
  document makes about existing behaviour is to be re-checked against the code before being
  relied on, and the previous agent's report is explicitly **not** evidence (§0).
- `core:*` is a *new* vocabulary owned by this platform. It is not a rename of any existing
  type space; existing `TypedMention.kind` values are a coarse producer classification and
  coexist with it (§7).
- The relation operator registry keeps its known operators (`works_for`, `owns`, `controls`,
  `founded`, `located_in`, `reports_to`, `created`, `published`, `employs`) for interpretation,
  validation, role hints, blocking and projection contracts — **not** as an enumeration of
  reality (§65).
- No parser dependency is assumed. §30 requires that a missing parser degrade to "no
  syntactic signals" rather than failing a batch, so the baseline must work without one and
  improve if one is added.
- Migration numbering is independent of feature numbering. 020 is taken; the next revision
  number is chosen at implementation time and applied migrations are never edited.
- PostgreSQL may be unreachable in the working environment, as it was for 019. ORM/migration
  parity and DDL invariants are provable offline; live round-trip is not. Anything verified
  only offline MUST be reported as such, distinctly from "verified" (§114).
