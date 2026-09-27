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

> **The complete, unabridged user brief is `input.md` in this directory (4898 lines, of which
> 3411 are non-blank, and all 115 sections, reproduced verbatim).** This document is the
> engineering reading of it. Where
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

**Why this priority**: It is the constitutional heart of the feature. `INV-003` says semantic
incompleteness must not reduce structural observability. If a paraphrase fragments a
hypothesis, the substrate is losing the world to the shape of its own vocabulary — the exact
failure 019 existed to fix, one level up. (§76, §97)

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

> **Reserved number space — stated once, here, so that absence reads as a decision and not as an
> oversight.** Two ranges of the `FR-` namespace are **deliberately empty and reserved**, and no
> requirement in this document occupies either of them: numbers **101–109** and **116–129**.
> `101` and `102` are void because two repair agents minted them for different subjects;
> `103` is a live phantom — a brief section number presented as an FR, and still cited as one by
> `research.md` and `tasks.md` — so it MUST remain unused until the checker reports it clean; and
> `104`–`109` were never allocated. `116`–`129` is reserved outright so a later wave has room
> without colliding.
>
> The bands that **are** occupied are `110`–`115` (already-applied appends), `130`–`137` (mapping
> layer), `140`–`149` (type vocabulary and the §8 extraction families), `150`–`160` (migration
> `021` and schema), `161`–`173` (constitution, lifecycle and provenance), `174`–`178` (identity
> subsystem) and `179`–`180` (the §8 producer obligation and the prohibition-coverage meta-rule).
> `repair/ARBITRATION.md` §14 is the authority for that whole allocation and supersedes §1's
> withdrawn instruction; §14 rule 1 is the rule that keeps a number unrepeatable.
>
> **These two ranges are written here as a reservation, not as a citation.** No artefact may name a
> number inside them as a live requirement target, and nothing in this document does so.

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
  never of a `RelationSignal` or a `RelationCandidate`, and a `GraphEdge` or `HyperEdge` MUST
  NOT exist before a `RelationClaim` exists. (§51, §99, §108)
- **INV-005**: Evidence lineage and derivation lineage stay separate. A candidate is
  derivation, never evidence. (§68, §69)

### Identity

- **FR-001**: `RelationCandidate.logical_candidate_id` MUST NOT depend on raw
  `relation_surface`, `producer_ref`, `producer_version`, `signal_refs`, `capture_ref`,
  `context_ref`, `semantic_regime_ref`, `confidence`, `candidate_status`,
  `observation_refs` or any observation timestamp. Those are revision/evidence material. (§19,
  §23)
- **FR-002**: `logical_candidate_id` MUST be derived from exactly: tenant, the **canonically
  ordered** participant configuration, arity shape, role shape, directional configuration,
  polarity, and the predicate signature. Participants MUST be canonically ordered before they
  enter identity material: for a `DIRECTED` reading, subject before object; for `NARY`, by the
  signature's normalised role name then by participant ordinal; for `UNDIRECTED`, by the
  signature's canonical subject/object slots — never by input order, and never by `min`/`max` of
  a raw ref. The derivation MUST produce the identity; a fixture MUST NOT. Canonicalisation MUST
  be implemented in the identity function, not at a call site. *(§19, §23, §84, §101)*
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

#### Identity subsystem *(A2 band, `FR-174`…`FR-178`)*

Applied verbatim from `repair/A2-identity-subsystem.md` §D8 under `repair/ARBITRATION.md` §14
rule 2, which renumbers A2's own five authored requirements into this band. The one internal
cross-reference is renumbered with them; nothing else is touched.

- **FR-174**: `PredicateSignature` field set and exclusions. System MUST provide a deterministic
  frozen `PredicateSignature` carrying exactly `language`, `predicate_lemma`,
  `construction_frame` (a member of the closed `ConstructionFrame` enumeration),
  `argument_markers` (parallel to the slots, each a member of the closed `ArgumentMarker`
  enumeration), `canonical_argument_slots` (contiguous from `A0`, at least two),
  `voice_normalization_version` and `predicate_normalization_version`, and no other field. It MUST
  NOT carry `raw_surface`, `predicate_surface`, `relation_surface`, `trigger_span`,
  `supporting_spans`, `producer_ref`, `producer_version`, `extraction_rule_id`, `evidence`,
  `observation_refs`, `evidence_refs`, `signal_refs`, `confidence`, `relation_ref`,
  `relation_type`, `schema_version`, `alternative_refs`, `mapping_evidence_refs`,
  `resolution_state`, any normalized-predicate mapping, any normalized raw-surface synonym, any
  participant or entity reference, or any temporal datum. `arity` and `direction` MUST be derived
  properties and MUST NOT be fields. `PredicateHypothesis.normalized_form` and
  `RelationSignal.normalized_predicate` MUST be derived read-only views of `predicate_signature`
  and MUST NOT be constructor inputs, so that exactly one normaliser exists in the platform. It
  MUST NOT be a `RelationRef` and MUST NOT be a semantic ontology concept.

  **Test method**:
  `apps/shared/tests/unit/test_predicate_signature.py::test_signature_field_set_is_exhaustive_and_excludes_surface_mapping_and_participants`
  (asserts the exact field list via `dataclasses.fields`), and
  `::test_predicate_hypothesis_refuses_a_constructor_supplied_normalized_form`,
  `::test_normalized_predicate_is_a_derived_view_of_the_signature`,
  `::test_signature_without_a_normalization_version_is_a_contract_error`.
  **Independently testable because** it asserts a type's field list and two read-only
  properties, with no producer, parser, corpus or store. (§18, §19, §20, §21, §23; replaces
  FR-003.)

- **FR-175**: `normalize_voice` is a specified deterministic algorithm. System MUST provide
  `normalize_voice(predicate, syntactic_structure, dependency_structure) ->
  CanonicalArgumentAssignment` as the ONLY function assigning canonical argument slots, executing
  the ordered steps `V0.validate`, `V1.frame`, `V2.assign_slots`, `V3.lemmatise`, `V4.markers`,
  `V5.trace`, `V6.arity` against a versioned construction table, with first-match-wins row order as
  the tie-break and with the argument tie-break fixed as `(ArgumentMarker ascending, position_label
  ascending byte-wise)`. It MUST map `Company acquired Asset` and `Asset was acquired by Company`
  to the same canonical argument assignment: `A0 = Company`, `A1 = Asset`,
  `predicate_lemma = acquire`, `construction_frame = verb_active_transitive`,
  `argument_markers = ("", "")`. It MUST normalise the ARGUMENT STRUCTURE and not the sentence's
  textual form, and the observed frame, the observed `by`, the span and the surface MUST remain
  available as evidence. It MUST support the constructions `active`, `passive` (with an overt
  `by`-agent), `copular`, `nominal`, `appositional`, `possessive`, `prepositional` and `relative
  clause`, and no others; it MUST unify nothing except voice, because unification is a claim about
  equivalence that §20 reserves to explicit mapping. An unsupported construction MUST yield
  `UNSUPPORTED_CONSTRUCTION` and MUST NOT be guessed, defaulted, retried or approximated by any
  fallback frame. A reading occupying fewer than two canonical slots MUST yield
  `NO_CONFIGURATION` and MUST NOT be padded. No lemma table row may map a surface to a lemma of
  which it is not a morphological form, and the table MUST be a generated artefact with a committed
  digest.

  **Test method**:
  `apps/shared/tests/unit/test_predicate_signature.py::test_normalize_voice_collapses_active_and_passive`,
  `::test_normalize_voice_does_not_unify_anything_but_voice`,
  `::test_unsupported_construction_yields_no_signature`,
  `::test_unsupported_construction_is_never_guessed_into_a_frame`,
  `::test_intransitive_reading_yields_no_configuration`,
  `::test_lemma_table_has_no_cross_lemma_row`,
  `::test_lemma_table_matches_its_committed_digest`,
  `::test_normalize_voice_marks_a_ditransitive_recipient_with_to_and_drops_a_temporal_complement_with_a_trace`.
  **Independently testable because** it is a pure function of three declared data structures and
  a committed table, driven entirely by literal inputs. (§18, §20, §22, §29, §30, §84; unblocks
  SC-001.)

- **FR-176**: Canonical participant ordering is a specified deterministic algorithm. System MUST
  provide `canonical_participant_ordering(signature, commutative_slots, participants) ->
  tuple[CanonicalParticipant, ...]` as the ONLY participant ordering admitted to logical identity.
  Participants MUST be ordered by `canonical_argument_slot` ascending, comparing the wrapped
  integer index and never the token text, and participants sharing one slot MUST be ordered
  ascending by `stable_participant_fingerprint`, compared byte-wise, preserving multiplicity and
  never deduplicating. `stable_participant_fingerprint` MUST digest `mention_kind`,
  `normalized_surface`, `capture_ref`, `segment_ref`, `start` and `end`, and MUST NOT digest the
  mention id text, any producer, extractor, span, evidence ref, observation ref, confidence, type
  datum, `argument_shape`, `surface_role`, `role_hypothesis` or any timestamp. Two participants
  MUST be commutable if and only if they occupy the same `canonical_argument_slot` AND that slot
  is declared in `commutative_slots`; participants in different slots MUST NEVER be commutable. A
  slot that is not declared commutative and holds more than one participant MUST be refused as a
  contract error rather than ordered. `commutative_slots` MUST always be explicitly present on a
  candidate, MUST be derived from no other datum, and MUST NOT be inferred from a missing or
  unknown direction.

  **Test method**:
  `apps/shared/tests/unit/test_predicate_signature.py::test_binary_and_nary_ordering_is_by_slot_then_fingerprint`,
  `::test_participant_fingerprint_is_invariant_across_realisations`,
  `::test_participant_fingerprint_excludes_producer_span_type_and_confidence`,
  `::test_slot_occupants_are_ordered_by_fingerprint`,
  `::test_non_commutative_slot_with_two_members_is_a_contract_error`,
  `::test_undirected_ordering_uses_the_slot_marker_not_a_mention_id_sort`,
  `::test_symmetry_is_never_inferred_from_missing_direction`,
  `::test_arity_mode_is_derivable_from_commutative_slots`.
  **Independently testable because** it is a pure function of a signature, an explicit slot set
  and a list of bindings, with no store and no parser. (§19, §22, §23, §52, §53, §54, §103.)

- **FR-177**: The logical candidate identity rule.
  `RelationCandidate.logical_candidate_id` MUST equal
  `"CAND-" + digest128(canonical_material(material))` where `material` contains exactly
  `identity_schema`, `tenant_id`, `arity_mode`, `commutative_slots`, `polarity`,
  `predicate_signature` (its `identity_projection()`, which carries
  `canonical_argument_slots`, `construction_frame`, `argument_markers`, `predicate_lemma`,
  `language`, `voice_normalization_version` and `predicate_normalization_version`) and
  `participants` (each entry `{"slot", "participant_fingerprint", "commutable"}`, ordered by
  FR-176). It MUST NOT contain `relation_surface`, `predicate_surface`, `trigger_span`,
  `supporting_spans`, `structural_path`, `producer_ref`, `producer_version`, `extraction_method`,
  `extractor_version`, `extraction_rule_id`, `signal_refs`, `observation_refs`, `evidence_refs`,
  `context_ref`, `semantic_regime_ref`, `capture_ref`, `neighbourhood`, `signal_ordinal`,
  `confidence`, `candidate_status`, `observed_at`, `recorded_by`, `investigation_id`,
  `temporal_hypothesis`, `relation_ref`, `relation_type`, `schema_version`,
  `predicate_hypothesis`, `alternative_refs`, `mapping_evidence_refs`, `resolution_state`, any
  mention id text, any type datum, any `ENT-` or `RES-` literal, any `extra` value, or any caller
  collection order. Every collection present MUST be emitted in canonical order. A candidate with
  no `predicate_signature` MUST NOT be given a `logical_candidate_id`, and
  `verify_candidate_identity()` MUST refuse to certify one with `unaddressed_logical_identity`; a
  surface-keyed fallback identity term is FORBIDDEN.

  **Test method**:
  `apps/shared/tests/constitution/test_identity_subsystem_constitution.py::test_logical_material_key_set_is_exact`,
  `::test_no_caller_order_reaches_the_logical_id`,
  `::test_candidate_without_a_signature_has_no_logical_candidate_id`,
  `::test_verify_candidate_identity_refuses_an_unaddressed_logical_id`,
  and the §94 mutation `::test_mutation_relation_ref_in_logical_material_fails`.
  **Independently testable because** it asserts a literal key set on a pure function and a
  refusal condition on a dataclass, with no corpus. (§17, §19, §23, §94, §95; replaces FR-001
  and FR-002.)

- **FR-178**: The mapping-independence invariant. Changing the mapping vocabulary MUST NOT change
  the historical logical identity of an already-extracted relational observation. Every mapping
  artefact — the operator registry, the relation vocabulary, any synonym or equivalence file, any
  embedding index, any `SemanticRegime` configuration, the type pack and any `RelationRef`
  catalogue — MUST be a non-input to `normalize_voice`, to `canonical_participant_ordering` and to
  `logical_candidate_id`, and none of those modules may import a registry, regime or type-pack
  symbol in executable code. A change to the mapping layer MUST appear as a change to
  `candidate_id` and to `PredicateHypothesis.resolution_state`, and MUST appear as a set of
  `PredicateMappingCandidate` records keyed on `signature_fingerprint`, and MUST NOT appear as a
  change to any stored `logical_candidate_id`, to the number of distinct stored
  `logical_candidate_id`s, or to the partition of candidates by logical id. A `PredicateSignature`
  field computed from a registry — including an event-class or ontology-derived field — is
  FORBIDDEN.

  **Test method**:
  `apps/shared/tests/constitution/test_identity_subsystem_constitution.py::test_mapping_vocabulary_is_not_an_input_to_logical_identity`
  (static: no import edge from `predicate_signature.py` to any registry, regime or type-pack
  module, and `identity_projection()`'s key set disjoint from every mapping artefact's key set),
  `::test_normalize_voice_and_ordering_never_read_the_mapping_layer`,
  `::test_mapping_swap_leaves_every_stored_logical_id_unchanged` (store-level, D5.2 steps 1–5),
  `::test_mapping_change_moves_candidate_id_and_not_logical_candidate_id`.
  **Independently testable because** the first two are static import assertions and the last two
  require only a store and two mapping fixtures, not a parser or a corpus. (§20, §21, §49, §65,
  §66, §104; new — no existing FR states it.)

### Relation signal

- **FR-008**: `RelationSignal` MUST carry a first-class `participants: tuple[RelationParticipant, ...]`
  as its canonical participant representation, supporting 2..N participants without a fake
  binary decomposition. `subject_mention_ref`/`object_mention_ref` MAY remain as derived
  compatibility accessors for binary signals, computed from `participants[0]`/`participants[1]`;
  they are never a second source of truth. `participants` is a typed structured field and MUST
  be persisted as such: migration `021` adds `participants JSONB NOT NULL` to **both**
  `relation_signal` and `relation_candidate`, in the canonical serialisation defined by the
  identity subsystem's participant ordering (FR-002), so that a stored row round-trips to an
  identical in-memory object and re-derives an identical `signal_id` / `logical_candidate_id`.
  It is **not** `extra`, and it is **not** deferred to a later migration. (§13, §62)
- **FR-009**: `RelationParticipant` MUST carry `mention_ref`, `slot`, `role_hypothesis`,
  `ordinal` and `confidence`. (§13)
- **FR-010**: The signal contract MUST explicitly support `role_hypotheses`,
  `arity_hypothesis`, `direction_hypothesis`, `polarity`, `predicate_surface`,
  `normalized_predicate`, `predicate_signature`, `structural_path`, `temporal_evidence`,
  `observation_refs`, `evidence_refs`, `extraction_rule_id` and `signal_ordinal`, in addition
  to the fields 019 introduced. Load-bearing dimensions MUST be typed, not JSONB. `extra` is
  for producer-specific non-core metadata only. (§14)
- **FR-011**: `SignalKind` names an **observation channel** and nothing else. It MUST contain at
  least `LEXICAL`, `SYNTACTIC`, `STRUCTURAL`, `METADATA`, `LINK`, `REFERENCE`, `TABLE`, `LIST`,
  `EVENT`, `TEMPORAL`, `ATTRIBUTE`, `CO_OCCURRENCE`, `SEMANTIC`, and `SCHEMA` MAY remain. It
  MUST NOT contain a member naming an orthogonal aspect — `NEGATION`, `QUANTITY`, `COREFERENCE`
  or `UNCERTAINTY` — because a channel and an aspect are different questions. `TEMPORAL` **is**
  a member and **stays**: it states only *provenance channel* — "this signal is based on a
  temporal observation" — and carries no temporal payload and no time of its own. The temporal
  facts themselves live in `SourceTemporalObservation` (FR-051) and in the signal's
  `temporal_evidence`, so `TEMPORAL` is never a container of time. `ck_relation_signal_kind`'s
  whitelist in migration `021` therefore **includes** `TEMPORAL`; a pre-flight that would
  rewrite that whitelist to remove it is refused, not applied (Principle I). No artefact may cite
  §15 or this FR either to forbid or to require removing the member. *(§15, §27, §16)*
- **FR-012**: `NEGATION`, `QUANTITY`, `COREFERENCE` and `UNCERTAINTY` MUST be expressed as
  members of a separate `SignalAspect` value carried by `RelationSignal`, with the following
  field mapping and no other: `NEGATION → Polarity.denied`; `QUANTITY → RelationParticipant
  .argument_shape = "value"` plus a producer note; `COREFERENCE → a reference relation between
  two mention refs, not an observation channel`; `UNCERTAINTY → Polarity.uncertain` or
  `TypeHypothesis.hypothesis_state`, whichever the reading is about. A `SignalKind` member naming
  an aspect MUST fail a structural test. `TEMPORAL` is **not** in this list: it is a channel, so
  FR-011 keeps it, and this requirement does not move it. *(§15)*
- **FR-013**: A `RelationSignal` MUST NOT require `relation_surface` to be non-empty. A
  `CO_OCCURRENCE` signal with an empty `relation_surface` and a `None` `predicate_signature`
  MUST be constructible, persistable and assemblable, provided it states an explicit
  observational basis. Migration `021` MUST **drop** `ck_relation_signal_asserts_something` and
  `ck_relation_candidate_asserts_something`, which encode
  `relation_surface <> '' OR relation_ref IS NOT NULL`, and MUST update the
  `ck_relation_signal_kind` whitelist for every member removed by FR-011. The domain-side check
  MUST be a named module constant `SIGNAL_ASSERTS_NOTHING`, replacing the current `__post_init__`
  string error code; it is a value, not a function. *(§16, §62)*
- **FR-014**: `observational_basis` MUST be a required, typed field on every `RelationSignal`,
  drawn from a closed enumeration: predicate text, DOM relation, table slot, hyperlink, citation,
  proximity, metadata field, event frame, attribute key. A signal with no basis MUST fail
  construction. The enumeration is closed: a new basis is an explicit extension with a version
  bump, not a free string. *(§16)*
- **FR-015**: `polarity` MUST be an explicit, required, durable field on every `RelationSignal`
  and on every `RelationCandidate`. Its domain is **closed and is `Polarity.{ASSERTED, DENIED}`**
  — two members, not three. Uncertainty is not polarity: it is
  `TypeHypothesis.hypothesis_state` for types and `PredicateHypothesis.resolution_state` for
  predicates, and neither is a third polarity. A denied relation MUST preserve its predicate
  surface and its signature, MUST be storable and queryable, MUST NOT be dropped, and MUST NOT
  yield a positive candidate or an edge. `polarity` MUST be a column on `relation_signal` and
  `relation_candidate` — a derived local is not persistence. *(§41, §89)*

### Mention binding

- **FR-016**: No producer may invent a mention identity from text after the mention stage.
  Every `participant.mention_ref` MUST resolve in a mention index. (§25)
- **FR-017**: A structural producer observing a value that is not yet a mention MUST record
  the structural raw slot and produce a typed, deferred participant reference, never a
  synthesised id. (§25)
- **FR-018**: `MentionOccurrenceIndex` MUST exist with deterministic lookup on the full tuple
  **(capture, segment, offset/span, normalized surface, extractor occurrence)**; omitting
  `capture` is forbidden, because two captures of one segment MUST NOT collide onto one id. The
  index MUST be the **sole minter** of mention identifiers; no other component may construct
  one. Lookup MUST resolve to a mention, never to an entity.
  `[INTERFACE: the identifier prefix is currently `MENTION-…` in `spec.md` and `MN-…` in
  `data-model.md` §6 and `tasks.md` T019. The identity owner picks one; the checker (§6) will
  require spec and code to agree.]` *(§26)*
- **FR-019**: Mention binding MUST remain distinct from entity resolution. Producers may use
  mention ids after binding and MUST NEVER use `ENT-` or `RES-` literals. (§26, §75)
- **FR-020**: No producer module may **import or construct** any of: `GraphEdge`, `HyperEdge`,
  `GraphStore`, `RelationClaim`, the `admission` package, the `projection` package.
  `TYPE_CHECKING` is the only permitted reference and never in executable code. The check MUST
  be an AST/import-graph test over the producer package, not a grep, and it MUST cover
  construction as well as import. *(§74, §75)*

### Predicate and claim boundary

- **FR-021**: `PredicateHypothesis` MUST preserve `surface_form`, `normalized_form`,
  `predicate_signature`, `relation_ref`, `alternative_refs`, `resolution_state` and
  `mapping_evidence_refs`. States are `KNOWN`, `UNKNOWN`, `AMBIGUOUS`, `CONFLICTING`. No
  `UNKNOWN_RELATION` sentinel and no fabricated `RelationRef`. `PredicateHypothesis.relation_ref`
  is the **sole authority** for a candidate's relation reference: `RelationCandidate.relation_ref`
  is a **derived** compatibility property computed from it, never a second stored source of
  truth, so a candidate and its hypothesis can never disagree about the reference. (§21, §8)
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

#### Mapping layer *(A4b band, `FR-130`…`FR-137`)*

Applied verbatim from `repair/A4b-mapping-layer.md` §D7 under `repair/ARBITRATION.md` §14, which
keeps A4b's own numbering. Placed where §D7 asks for it — after *Predicate and claim boundary*,
before *Assembly*. **A known conflict, reported not resolved:** `FR-133` routes a **structural**
disagreement into `CandidateStatus.CONTRADICTED`, which `repair/ARBITRATION.md` §3 forbids; the
structural axis is `RelationCandidate.assembly_state = CONFLICTING`, as `FR-090` in this document
already states. The text is the owner's and is carried over unaltered; `EPISTEMIC-AXIS-CONFLATION`
is expected to report it against `spec.md` as well as against the repair document.

- **FR-130**: `PredicateMappingCandidate` MUST be a frozen value object carrying at least
  `source`, `target`, `match_type`, `target_relation_ref`, `confidence`, `provenance`,
  `mapping_version`, `created_by`, `evidence_refs`, `mapping_set_id`, `mapping_set_version`,
  `supersedes` and `mapping_candidate_ref`, with its own `content_key()`, `with_id()`,
  `to_dict()` and `from_dict()`. `source` MUST be a `PredicateSignature` content key and MUST
  NOT be a surface string. `target` MUST be non-empty. `match_type` MUST be one of
  `exact_match`, `close_match`, `narrow_match`, `broad_match`, `related_match` (SSSOM
  semantics, this repository's spelling), MUST be required, and MUST have **no default**, so
  that an unspecified match cannot be recorded as `close_match`. `confidence` MUST default to
  `0.0`, not `1.0`. It MUST carry no lifecycle stage, no `signal_id`, no `candidate_id` and no
  row of its own. (§2, §9, §64, §105; A4b D1)
- **FR-131**: No `PredicateMappingCandidate` field, no `RelationRef`, no `resolution_state`, no
  `alternative_refs`, no `mapping_evidence_refs`, no `match_type`, no `confidence`, no
  `mapping_version`, no `provenance`, no `created_by` and no external vocabulary reference may
  participate in `logical_candidate_id`. Changing any of them MUST change `candidate_id` and
  MUST NOT change `logical_candidate_id`. A change to `mapping_version` or to any other mapping
  field MUST supersede rather than edit: the prior candidate is preserved and named in
  `supersedes`, and it leaves the live candidate set rather than remaining an alternative,
  because a correction is a revision and not an ambiguity. A test MUST break
  `PredicateMappingCandidate.target` and assert `logical_candidate_id` is unchanged, and a
  second MUST break the signature and assert it changes. (§19, §22, §23, §104; A4b D2.3, D2.4)
- **FR-132**: Two signals whose `PredicateSignature`s agree and whose `PredicateMappingCandidate`s
  name different `target_relation_ref`s MUST yield **one** logical candidate carrying one
  `PredicateHypothesis` with `resolution_state=AMBIGUOUS`, at least two entries in
  `mapping_candidates`, a designated `relation_ref`, and both readings preserved. Two
  signatures is two candidates and MUST NOT be reported as `AMBIGUOUS`. Neither interpretation
  may be overwritten, dropped, or ranked into a winner, and `resolution_state` MUST be derived
  from the candidate set and MUST NOT be a caller-stated label. An `AMBIGUOUS` hypothesis MUST
  NOT yield `RelationClaimMaterial`. (§49, §48, §26, §50; A4b D3.2, D3.3, D3.4)
- **FR-133**: A hypothesis whose competing readings came from **disagreeing evidence** rather
  than from one evidence set read by two regimes MUST carry `resolution_state=CONFLICTING`,
  stated explicitly by the assembler and never inferred from the refs, with both readings
  preserved and with `mapping_evidence_refs` naming the `signal_id` on each side so a reader
  can reconstruct why the hypothesis stalled. Both readings MUST be preserved. A disagreement
  that is **structural** — arity, direction, polarity or role bindings over the same mentions —
  is not representable as one hypothesis and MUST yield `FR-090`'s
  `CandidateStatus.CONTRADICTED` candidates with both readings preserved. A `CONFLICTING`
  hypothesis MUST NOT yield `RelationClaimMaterial`. No count, confidence, insertion order or
  alphabetical tie-break may decide either state. (§45, §49, §83, §95; A4b D3.3, D3.4)
- **FR-134**: A structured or external-vocabulary statement (JSON-LD, schema.org, OpenGraph,
  RDFa, microdata, HTML metadata) MUST produce a `TypeSignal` carrying `source_vocab`,
  `surface` and `mapping_candidates` — the last of which MAY legitimately be empty — together
  with `mention_ref`, `structural_path`, `observation_refs`, `evidence_refs`, `producer_ref`
  and its own `signal_id`. A `TypeSignal` MUST NOT carry a `core:` reference and MUST NOT
  produce a `TypeAssertion`. The first moment a local type may appear on this path is
  `TypeHypothesis`, and reaching it MUST require a recorded `TypeMapping`. `signal_id` MUST be
  derived from `(tenant_id, producer_ref, mention_ref, source_vocab, surface, structural_path)`
  and MUST NOT include `mapping_candidates`, so that a later mapping change is a new reading of
  the same observation rather than a new observation. (§9, §10, §24, §37; A4b D5.2)
- **FR-135**: A type mapping MUST be the existing `semantic.mappings.SemanticMapping`, and
  `TypeMapping` is its documented name — no parallel dataclass. It MUST retain subject type,
  object type, mapping predicate, mapping set and set version, mapping version, confidence,
  creator/operator, justification and evidence/provenance, MUST be content-addressed,
  citable, tenant-scoped at the write, superseding rather than editing, and MUST surface
  `MappingConflict` rather than resolve it. It MUST NOT collapse `schema:Person` into
  `core:Person` without a mapping record, and it MUST NOT default `predicate`: every
  construction on the 021 path MUST pass `match_type` explicitly. `MatchPredicate` MUST gain
  `related_match` so that a correspondence which is neither broader nor narrower is
  recordable as such; `Concept` MUST NOT gain a matching field, because a concept declares its
  own links and a mapping process does not. (§9, §64, §105; A4b D1.2, D5.1)
- **FR-136**: The initial type mapping set MUST be exactly §64's seven —
  `schema:Person → core:Person`, `schema:Organization → core:Organization`,
  `schema:WebSite → core:WebSite`, `schema:WebPage → core:WebPage`,
  `schema:Event → core:Event`, `schema:Product → core:Product`,
  `schema:SoftwareApplication → core:Software` — and each MUST be an explicit `TypeMapping`
  record carrying its justification and provenance, never a silent collapse. Match types MUST
  be recorded as claimed and MUST NOT be assumed equivalent: `schema:Person → core:Person`,
  `schema:Organization → core:Organization`, `schema:Product → core:Product` and
  `schema:SoftwareApplication → core:Software` are `broad_match`; `schema:WebSite →
  core:WebSite`, `schema:WebPage → core:WebPage` and `schema:Event → core:Event` are
  `exact_match`, and an `exact_match` MUST still be read as a claim by a mapping process and
  MUST NOT license collapsing the two references. A mapping whose match type cannot be cited to
  a published definition of the term MUST be withheld, and the unmapped term MUST yield
  `UNKNOWN` and be retained. No further mapping may be added without a recorded decision. (§64,
  §38, §82; A4b D5.3, D5.4)
- **FR-137**: `apps/shared/events/ontology_pack.py` MUST NOT declare, publish or check a
  relation list. The `relations` field, `allows_relation()` and the `relations` key in
  `to_dict()` MUST be deleted, and no replacement relation allow-list may be introduced in the
  extraction path. `allows_type()` MUST remain, MUST remain advisory, and MUST NOT be used as
  a drop, deny, filter or reject decision by any code path: an ontology miss MUST mean
  `unknown type`, never a rejected mention, and a `core:*` reference the pack does not know
  MUST be retained with `hypothesis_state=UNKNOWN`. Because no relation symbol remains to lock
  against, FR-074's second clause MUST be enforced behaviourally: a source scan of
  `apps/interpretation/extractors/**` and `apps/shared/domain/**` MUST fail on
  `allows_relation`, on a hard-coded relation-name list, and on any `if … not in … relations`
  shape. The ORM class `control-plane.db.schema.OntologyPack` and its `ontology_packs`
  `relations` column MUST be removed by the migration owner, and migration `021` MUST NOT
  create the table. (§73, §104, §65, §38, §34a; A4b D6)

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
  overwritten; genuine disagreement yields `CONFLICTING` with both preserved. `AMBIGUOUS` and
  `CONFLICTING` are **mapping states on `PredicateHypothesis`**, not identity terms on
  `PredicateSignature`; the identity terms are exactly the ones FR-002 enumerates, and FR-004
  governs them. (§49)

### Types

- **FR-029**: A versioned foundational type pack MUST exist, exposing per type: `type_ref`,
  `label`, `alt_labels`, `broader_refs`, `narrower_refs`, `description`, `kind ∈ {entity,
  value}` and `version`. It MUST NOT encode relation semantics and MUST NOT encode truth; it
  MAY carry blocking hints. (§4, §63)
- **FR-030**: The pack MUST cover, at minimum, the following **31** entity classes:
  `core:Person`,
  `core:Organization`, `core:LegalEntity`, `core:Group`, `core:Agent`, `core:WebSite`,
  `core:WebPage`, `core:OnlineAccount`, `core:SocialProfile`, `core:Domain`,
  `core:DigitalResource`, `core:PhysicalPlace`, `core:Facility`, `core:Address`,
  `core:GeographicRegion`, `core:Country`, `core:StateOrProvince`, `core:City`,
  `core:Coordinate`, `core:Document`, `core:Dataset`, `core:CreativeWork`,
  `core:MediaResource`, `core:Software`, `core:Project`, `core:Product`, `core:Service`,
  `core:Asset`, `core:Vehicle`, `core:FinancialInstrument`, `core:Event`. (§4)
  This is a **fixture requirement on the pack's contents** and MUST NOT be read as a producer
  obligation: a type's presence here does not oblige the system to have a dedicated extractor for
  it (FR-155). `core:Coordinate` is an **entity** here; `value:Coordinate` in FR-031 is a
  **value** with the same local name, and the two are distinct references distinguished by
  `kind` (FR-153, FR-156).
- **FR-031**: Value types MUST be conceptually separate from entity classes, and the pack MUST
  cover exactly **13** value (`value:*`) types: `value:EmailAddress`, `value:PhoneNumber`,
  `value:URL`, `value:Handle`, `value:Identifier`, `value:IPAddress`, `value:Hash`,
  `value:CryptoAddress`, `value:Date`, `value:DateTime`, `value:Money`, `value:Quantity`,
  `value:Coordinate`. A value MUST NOT be forced into `Entity`. `core:Coordinate` (entity) and
  `value:Coordinate` (value) are two distinct refs in two namespaces, so `kind` is a required,
  non-defaulted discriminator read from the entry. *(§4)*
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
- **FR-035**: External vocabularies (JSON-LD, schema.org, OpenGraph, RDFa, microdata, HTML
  metadata) MUST produce a `TypeSignal` with `source_vocab`, `surface` and
  `mapping_candidates`, and MUST NOT immediately produce a `TypeAssertion`. Type and relation
  policy is the one stated in §104 and §65, and `INV-002` is its constitutional home: a bounded,
  modularly-extensible *type* space is desirable because it supplies coarse semantic
  affordances, blocking, typing, query expansion and interpretation; a finite mandatory
  *relation* list is forbidden because relations are too dependent on context, source vocabulary,
  language, document structure, task, semantic regime, temporal frame and event structure. The
  relational space begins as observed structure and only later becomes a known predicate when the
  semantic system earns that mapping. `source_vocab` is an **external vocabulary reference or
  `null`** — it answers *whose semantic system said this*, while `producer_ref` /
  `producer_version` independently answer *which instrument extracted it*; no synthetic
  vocabulary (`local`, `internal`, `regex`, `ner`) may be introduced to avoid a `null`. (§9,
  §64, §104, §65, §2)
  *Tombstone `FR-034a` — folded into this slot per `repair/ARBITRATION.md` §1 and §2, with
  `INV-002` as its surviving constitutional home. It carries no normative requirement and MUST
  NOT be cited as a live target.*
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

#### Foundational type pack and the §8 entity instruments *(A5 band, `FR-140`…`FR-149`; A6 §8
obligation, `FR-179`)*

`FR-140`…`FR-149` and `FR-179` are applied verbatim from `repair/A5-type-vocabulary.md` §D6 and
`repair/A6-fr-triage.md` §2.5 under `repair/ARBITRATION.md` §14, and are renumbered, not rewritten.
`FR-179` is the **producer obligation** for the vocabulary `FR-030`/`FR-031` define; per §14 rule 4
the two are different claims and a previous revision's folding of the obligation into `FR-030` is
unwound.

**The reported A5 gap.** A5 authored **twenty-one** requirements, §14 allocates it **ten** slots,
and **eleven are therefore unnumbered** — reported here rather than numbered, per §14 rule 1. Two of
the eleven are unnumbered for a second, stronger reason: their subjects are already carried by the
applied `FR-111` and `FR-112`, so §14 rule 3 makes those the survivors and forbids the duplicate.
The eleven are enumerated, in A5's own numbering, in `repair/A5-type-vocabulary.md` §D6 and its
§D6.5 cross-reference table; they are the six-state enumeration, the `semantic.types` layering rule,
the pack identity/version rule, the eight-field entry rule, the cross-pack hierarchy rule, the
vocabulary-is-not-an-extractor-obligation rule, the `TypeSignal` type rule, the pipeline-order rule,
the context/bounded-neighbourhood rule, and the type/role mutual-consumption rule.

- **FR-140**: The deterministic extraction layer MUST be completed by **adapting** the existing
  extractors and registry — zero new extraction frameworks. `extractors/registry.py`'s
  `ExtractorRegistry` remains the single fan-out; `TypedMention`, `SOURCE_ORDER` and
  `to_dict()`'s `_sorted_dict` determinism are retained. A new instrument MUST be reachable from
  `register_builtin()` / `register_deterministic_extractors()` and MUST emit
  `list[TypedMention]`. A parallel module that re-implements segmentation, normalisation or
  dispatch is a defect, not an extension. (§8 preamble)
  **Test**: `test_a5_fr140_adapt_not_duplicate_extraction_framework` — asserts the new
  instruments are reachable from the existing registry, that no module under `extractors/`
  defines a second dispatch type, and that `extract_deterministic` output is unchanged for the
  §107 baseline corpus.
- **FR-141**: The person instrument MUST cover Latin names, Cyrillic names, initials, multi-token
  names, titles, person-name contextual cues, aliases, transliteration, Unicode normalization,
  surname-first patterns and social/profile names where useful; it MUST be an adaptation of
  `persons.py` / `normalize.py` / `translit.py`, not a new implementation. It MUST NOT treat
  `name-shaped string == person` as a conclusion: a mention supported only by name shape yields a
  `TypeHypothesis` at `hypothesis_state=INFERRED` whose `extractor_ref` names a cue-bearing
  instrument or whose `confidence` is below the cue-bearing floor, and never a
  `TypeAssertion`. Every person result is a `TypeHypothesis` on a mention. (§8 A)
  **Test**: `test_a5_fr141_person_covers_eleven_capabilities` (§82 rows `John Smith`,
  `Иван Петров`, `J. Smith`, `Smith, John`, `Dr Ivan Petrov`, `@johnsmith`) and
  `test_a5_fr141_name_shaped_string_is_not_a_person_conclusion`.
- **FR-142**: The organization instrument MUST extend beyond legal-form-only detection and
  recognise legal-form patterns, corporate suffixes, institutional names, brands, agencies,
  universities, government bodies, media organizations, banks, companies, NGOs, and
  organizations inferred from strong contextual structures; it MUST be an adaptation of
  `orgs.py`. Each recognition yields a `core:Organization`-or-narrower `TypeHypothesis`; no
  producer may mint an `entity_ref` or record `entity = organization`. (§8 B)
  **Test**: `test_a5_fr142_organisation_recognisers_exceed_legal_form` (§82 rows `Acme
  Corporation`, `Acme`, `Apple Inc.`, `University of …`, plus one suffix-free, dictionary-free
  name that must still yield a hypothesis from a contextual-structure signal) and
  `test_a5_fr142_no_producer_mints_an_entity_ref`.
- **FR-143**: URL, domain, WebSite and WebPage extraction MUST be deterministic and MUST preserve
  the four as four distinct types: `https://example.com/a` is a `value:URL`; `example.com` is a
  `core:Domain`; `www.example.com` is a `core:Domain` with `www` recorded as a hint and not as a
  `subdomain` assertion; a retrieved page is a `core:WebPage`; a registrable host serving
  multiple pages is a `core:WebSite`. A URL string is a value, a WebPage and a WebSite are
  resources at different levels, and a domain is a namespace/network resource. The distinction
  MUST be recorded, never inferred away, and none of the four may produce a `TypeAssertion`
  directly. (§8 C)
  **Test**: `test_a5_fr143_url_domain_website_webpage_stay_four_types` — one input yields exactly
  the set above, the four refs are four distinct strings, and zero `TypeAssertion`s are emitted.
- **FR-144**: A table-driven, versioned profile-URL and handle instrument MUST recognise
  `github.com/<segment>`, `(twitter|x).com/<segment>`, `linkedin.com/in/<segment>`,
  `t.me/<segment>` and `youtube.com/@<segment>`, each as a `TypeSignal` naming its
  `extraction_rule_id` and `extractor_version`, yielding `value:Handle` and/or
  `core:OnlineAccount` / `core:SocialProfile` hypotheses with the site in `evidence_refs`. It
  MUST NOT infer account identity from a display name: a bare `@name` yields a `value:Handle`
  value hypothesis and no `core:OnlineAccount` hypothesis. (§8 D)
  **Test**: `test_a5_fr144_profile_urls_and_handles` and
  `test_a5_fr144_display_name_alone_yields_no_account_hypothesis`.
- **FR-145**: Indicator extraction MUST extend — not duplicate — the existing instruments to emit
  **value-type** hypotheses for `IP`, `hash`, `CVE`, `crypto address`, `file path` and
  `identifier`. A value with no dedicated `value:*` entry (today: `CVE`, `file path`) MUST be
  recorded as `value:Identifier` with the specific form preserved in `normalized_surface` and
  `extraction_rule_id`. No value may be coerced to `kind=ENTITY`. (§8 E)
  **Test**: `test_a5_fr145_indicators_become_value_hypotheses` (all six families, with a named
  rule id) and the mutation that coerces a value to an entity, which fails a named test.
- **FR-146**: Document instrumentation MUST detect and documentize URLs pointing to files,
  filenames, document IDs, report-like structures, PDFs/documents where source metadata provides
  them, citations, and document title/identifier structure. A filename's extension is evidence,
  not the type. Document **casing** and document **identifiers** are value hypotheses
  (`value:URL`, `value:Identifier`); the `REFERENCE` signal family for citations remains owned by
  the relation substrate, and no document detector may emit a `RelationSignal` or a `GraphEdge`.
  (§8 F)
  **Test**: `test_a5_fr146_seven_document_detectors` and
  `test_a5_fr146_no_document_detector_emits_a_relation` (a source scan of the new modules).
- **FR-147**: A recognised event word — `conference`, `meeting`, `acquisition`, `launch`,
  `publication`, `incident`, `transaction`, `election`, `appointment` — MUST produce a
  `TypeSignal` recording the lexical match and its span, and a
  `TypeHypothesis(type_ref="core:Event", hypothesis_state=OBSERVED)`. **An event word MUST NOT
  become a claim.** Specifically it MUST NOT produce a `RelationSignal`, a `RelationCandidate`, a
  participant-role `TypeAssertion`, a `RelationClaim` or a `GraphEdge`. A participant, date, place
  or organisation near an event word is a separate mention with its own hypotheses; co-presence
  is recorded as co-occurrence, never as event participation. (§8 G)
  **Test**: `test_a5_fr147_event_word_never_becomes_a_claim` (all nine words, alone and in
  `"Acme announced the acquisition of Contoso in March."`, asserting zero claims and zero edges)
  and the mutation *if the pack has `core:Event`, emit a claim*, which must fail.
- **FR-148**: `TypeHypothesis` MUST be exactly ONE interpretation candidate and MUST NOT be a
  container of candidates. It MUST be a frozen dataclass carrying the thirteen §6 fields
  `type_surface`, `normalized_surface`, `type_ref`, `scheme`, `hypothesis_state`, `confidence`,
  `source_ref`, `extractor_ref`, `extractor_version`, `evidence_refs`, `context_ref`,
  `semantic_regime_ref`, `mapping_candidates` — and no others. It MUST NOT carry `mention_ref`,
  a children collection, an `entity_ref`, a content-addressed id, or any resolution verdict. It
  MUST remain distinct from `TypeAssertion`, which is evidence-bearing and id-bearing. A
  hypothesis narrows a comparison and is discarded with it; durable typing lives on
  `TypeAssertion`'s existing two-level identity. (§6, §3, §103, INV-001)
  **Test**: `test_a5_fr148_type_hypothesis_is_one_hypothesis` — `dataclasses.fields()` equals the
  thirteen-name tuple exactly, the class is frozen, and constructing one with `mention_ref=` or
  `hypotheses=` raises `TypeError`.
- **FR-149**: The **set** of competing hypotheses MUST be owned by the mention, never by a
  hypothesis. `TypedMention` MUST gain `type_hypotheses: tuple[TypeHypothesis, ...] = ()` and
  `ResolutionMention` MUST gain `type_hypotheses: tuple[TypeHypothesis, ...] = ()`, beside
  `ResolutionMention.type_assertions`. `TypedMention.kind: str` MUST be retained unchanged as a
  coarse producer classification and MUST NOT be compared against the vocabulary. The set MUST be
  frozen, de-duplicated by `(type_ref, scheme, hypothesis_state)` keeping the highest-confidence
  occurrence, and ordered by `(-confidence, type_ref, scheme, hypothesis_state)`, reusing
  `semantic.blocking._ordered_hypotheses` rather than a second ordering implementation. No new
  container type may be introduced. (§7, §3, §103)
  **Test**: `test_a5_fr149_the_set_lives_on_the_mention` and
  `test_a5_fr149_hypothesis_set_order_is_arrival_independent`.
- **FR-179**: The deterministic entity extraction layer MUST be completed around the atomic type
  vocabulary, extending existing extractors rather than duplicating them into a second framework,
  and providing producers/readers for all seven classes of §8:
  **A. Person** — Latin, Cyrillic, initials, multi-token, titles, contextual cues, aliases,
  transliteration, Unicode normalisation, surname-first patterns; a name-shaped string MUST NOT
  imply person; every result is a hypothesis.
  **B. Organization** — legal forms, corporate suffixes, institutional names, brands, agencies,
  universities, government bodies, media, banks, companies, NGOs, strong contextual structures;
  hypothesis, never `entity = organization`.
  **C. WebSite / WebPage / Domain / URL** — deterministic extraction of `https://example.com`,
  `example.com`, `www.example.com`, with the four kept distinct; a URL string is a value, a WebPage
  a resource, a WebSite a higher-level resource, a domain a namespace.
  **D. OnlineAccount / SocialProfile** — structured profile URLs and handles
  (`github.com/user`, `twitter/x.com/user`, `linkedin.com/in/user`, `t.me/user`,
  `youtube.com/@channel`); account identity MUST NOT be inferred from a display name.
  **E. Digital identifiers** — IP, hash, CVE, crypto address, file path, identifier as value-type
  hypotheses.
  **F. Documents** — URLs pointing to files, filenames, document ids, report-like structures, PDFs
  where source metadata provides them, citations, title/identifier structure.
  **G. Event mentions** — conference, meeting, acquisition, launch, publication, incident,
  transaction, election, appointment; an event mention is not a relation and MUST NOT become a
  claim.
  **Phase ownership: §110-2 ("atomic entity type vocabulary").** Phase 2 is the only phase that owns
  this, and today it is occupied by work §110 places in Phase 5 — this is D15, and this FR is what
  makes the phase non-empty. *(§8, §110-2)*
  *Applied verbatim from `repair/A6-fr-triage.md` §2.5, which is the only place the §8 producer
  obligation appears; `repair/ARBITRATION.md` §14 allocates it to A6's band. The phrase "all seven
  classes" is the owner's wording and is carried over unaltered: §10 of that record requires the
  *vocabulary* to be "seven extraction families" and a rewrite is a finding, not an integrator's
  edit.*

### Producers

- **FR-040**: `LEXICAL`, `SYNTACTIC`, `STRUCTURAL`, `LINK`, `REFERENCE`, `TABLE`, `LIST`,
  `METADATA`, `ATTRIBUTE`, `EVENT`, `TEMPORAL`, `CO_OCCURRENCE` and `SEMANTIC` MUST all be
  implementable producer families writing to the identical downstream model. "Universal"
  means a common observation language, not 500 extractors. A family that is not implemented MUST
  carry an explicit `UNSUPPORTED` marker with a reason; silence is not an implementation and an
  unbacked channel is a FAIL, not a deferral. A mention's type hypotheses and a relation signal's
  role hypotheses MUST be mutually consumable, so resolution and blocking can exploit both — e.g.
  a `works_for` operator hinting a `Person-like` subject and an `Organization-like` object. Those
  hints MUST   remain hints and MUST NOT become truth, and no role hint may enter
  `logical_candidate_id` material as a free-text `role: str`. (§27, §71)
  *Tombstone `FR-039a` — folded into this slot per `repair/ARBITRATION.md` §1. It carries no
  normative requirement of its own and MUST NOT be cited as a live target.*
- **FR-041**: The existing lexical producer MUST remain one producer and MUST be upgraded to
  emit raw predicate surface, normalized predicate, predicate signature, participant roles,
  direction hypothesis, arity and trigger/support evidence. `RELATION_CUES` MUST be retained
  as one lexical instrument and MUST NOT define the global relation vocabulary. (§28)
- **FR-042**: A syntactic producer MUST support at least active, passive, copular, nominal,
  appositive, possessive, prepositional and relative-clause realisations, emitting structural
  signatures and role hypotheses. It MUST NOT emit `works_for`/`founded`/`owner_of` unless the
  mapping layer says so. (§29)
- **FR-043**: Parser capability MUST be explicit and pinned: `model_ref`, `model_version`,
  `parser_version` and `configuration_hash` are part of interpretation provenance. No LLM may
  appear in the constitutional extraction path. A missing parser MUST mean *no syntactic
  signals*, never batch failure. **A named test MUST run the full production batch with the
  parser capability unavailable and MUST assert: exit success, ≥1 non-empty lexical signal, and
  ≥1 candidate.** *(§30)*
- **FR-044**: A structural producer MUST represent `structural_path` — DOM parent/child,
  section membership, heading → content block, breadcrumb, caption → table, figure → caption,
  document → subsection, page → document — and MUST NOT flatten structure into a predicate
  such as `member_of_board`. (§31)
- **FR-045**: The link producer MUST preserve source mention, target/resource mention, href,
  anchor text, DOM path, link position, the `rel` attribute and target metadata, and MUST assert
  only "A links to B" — never `cites`, `owns`, `hosts` or `employs`. `rel="author"` MAY
  strengthen a signal and is still only a candidate. **One anchor MUST NOT yield two signals
  that count as independent corroboration**: two signals over one anchor that differ only in
  `kind` share a `producer_ref` and MUST count once. *(§32, §24, §85)*
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

- **FR-055**: The executable path MUST make the following precedence constraints hold, each
  stage exposing the object it produced: `OBSERVATION ≺ CONTEXT ≺ MENTIONS ≺ TYPE_SIGNALS`;
  `MENTIONS ≺ RELATION_SIGNALS`; `RELATION_SIGNALS ≺ RELATION_CANDIDATE ≺ RESOLUTION ≺
  CLAIM_MATERIAL ≺ VALIDATION ≺ ADMISSION ≺ STORE`; `STORE ≺ EDGE ≺ WORLDLINE`.
  The brief states `REGIME` in **three incompatible positions** (§57: before `RELATION SIGNALS`;
  §101: after `ENTITY RESOLUTION`; this FR previously: between them). This FR therefore fixes only
  the constraints above and records `REGIME`'s position as an **open decision for `plan.md`**, to
  be answered by an ADR before Phase 8. Until then no task may assert a total stage order and no
  test may assert one. *(§57, §58, §101)*
- **FR-056**: The claim lifecycle MUST be `Candidate → ClaimMaterial → Validation →
  Admission → RelationClaim`, and `RelationClaim → Validation` MUST NOT be the primary
  lifecycle. No fake `SUPPORTED` technical gate. (§57)
- **FR-057**: `ExecutionResult` MUST expose `material` as a real stage product. A stage that
  is semantically material but silently validates or admits is not acceptable. (§58)
- **FR-058**: *tombstone — merged into `INV-004`; see the deleted-ids table in
  `repair/A6-fr-triage.md`. The obligation now lives in `INV-004`. This slot carries no
  normative requirement and MUST NOT be cited as a live target.* (§108)

### Persistence

- **FR-059**: Durable store seams MUST exist for `RelationSignal`, `RelationCandidate` and
  `SourceTemporalObservation` with `write`, `get`, `by_tenant`, `by_logical_id`, `by_pair`,
  `by_signal` and checksum/replay support where architecturally appropriate. (§59)
- **FR-060**: Every store MUST reconstruct the exact domain object. A round trip MUST
  preserve ids, alternatives, signals, provenance, type hypotheses, predicate signature,
  temporal evidence, tenant, context and regime. A digest may identify data; a digest MUST
  NOT be the only copy required for reconstruction. Every new substrate object MUST have a
  build → store → read test asserting that list, not a summary string. (§59, §60, §91)
- **FR-061**: The **normal** acquisition path MUST persist `SourceTemporalObservation`:
  `adapter → Capture + SourceTemporalObservation → durable store`. The helper no production
  path calls MUST NOT be the only route. EDGAR `date_filed` MUST stay day-precision; Common
  Crawl `timestamp` MUST stay index-observation time; source publication time MUST NOT be
  stuffed into `Capture.fetched_at`.
  **Verification clause:** because live PostgreSQL is unreachable in the working environment,
  the enforcement test MUST assert that the normal path **issues a write** through the
  repository seam (a spy/recording repository is sufficient), and the live round trip MUST be
  reported `verified only offline` per FR-084. The write obligation is unconditional; only the
  live verification is conditional. *(§61, §114)*
- **FR-062**: A new forward-only migration MUST be created if required. Applied migrations
  MUST NOT be modified. It MUST preserve data, be tenant-scoped, add CHECKs only for
  constitutional invariants, keep ORM/migration parity, and never drop historical semantic
  observations. Create **migration parity tests** and **schema invariant tests**
  unconditionally, and **round-trip tests if PostgreSQL is available** — the conditional is
  restored from §62 and MUST NOT be hardened into an unconditional MUST. When PostgreSQL is
  unavailable the omission MUST be reported `verified only offline` with the reason, per
  FR-084. `021` MUST also drop the two `*_asserts_something` CHECKs and update the `SignalKind`
  whitelist per FR-013/FR-011. *(§62; the restoration is mandated by the brief's own
  conditional)*

#### Migration `021`, requirement by requirement *(A7 band, `FR-150`…`FR-158`)*

Applied verbatim from `repair/A7-migration-021.md` §D9 under `repair/ARBITRATION.md` §14, which
keeps A7's own numbering. **Two placement notes.** §D9 asks for these to sit after `FR-100` in the
*Verified 019 defects* section; they are placed here instead, in the section whose subject is
persistence. And **the band's last two slots are not requirements**: A7 authored nine migration
requirements and §14 allocates it eleven slots, so the two surplus numbers are **reported here, not
filled** — per §14 rule 1, a requirement with no authored content is reported rather than numbered,
and writing a placeholder bullet would mint a definition the checker would then treat as a live
requirement target.

- **FR-150**: `021` MUST drop `ck_relation_signal_asserts_something` and
  `ck_relation_candidate_asserts_something` and replace both. The replacement on
  `relation_signal` MUST be
  `observational_basis IS NOT NULL OR relation_surface <> '' OR relation_ref IS NOT NULL`,
  together with `ck_relation_signal_predicate_text_basis`
  (`observational_basis IS DISTINCT FROM 'predicate_text' OR relation_surface <> '' OR relation_ref IS NOT NULL`)
  and `ck_relation_signal_observational_basis` (a closed vocabulary of the nine bases named by
  §16). The replacement on `relation_candidate` MUST be
  `relation_surface <> '' OR relation_ref IS NOT NULL OR predicate_signature_key IS NOT NULL OR (signal_refs IS NOT NULL AND jsonb_array_length(signal_refs) > 0)`.
  The two rules MUST differ: a signal has an observation channel and a candidate has none, so
  no single predicate can serve both. Neither replacement MUST require a named predicate, and
  neither MUST contain the literal `co_occurrence`. Each replacement MUST be a strict superset
  of the constraint it replaces, so that no stored row can become invalid. (§16, §40, §13)
  *Tests:* `test_the_two_asserting_constraints_are_dropped_by_name`,
  `test_each_replacement_is_a_strict_superset_of_the_check_it_replaces`,
  `test_the_replacement_never_mentions_co_occurrence`,
  `test_the_replacement_never_requires_a_named_predicate`.
- **FR-151**: `021` MUST add `relation_signal.observational_basis String(24) NULL` and the
  domain type `SignalBasis` with exactly the nine members §16 names, and the signature
  components MUST be wholly present or wholly absent
  (`ck_relation_signal_signature_whole`, `ck_relation_candidate_signature_whole`), with
  `direction` exempt on the candidate side because it is already `NOT NULL`. A half-written
  signature MUST NOT be storable, because a signature present in part cannot yield the
  `logical_candidate_id` that claims to be derived from it. (§16, §18, §62)
  *Tests:* `test_the_observational_bases_are_exactly_the_live_signal_basis`,
  `test_a_half_written_signature_is_refused_by_the_recorded_check_text`.
- **FR-152**: `ck_relation_signal_kind` MUST be dropped and recreated over a whitelist of
  exactly fifteen members: `lexical`, `syntactic`, `structural`, `event`, `semantic`,
  `temporal`, `link`, `reference`, `table`, `list`, `metadata`, `attribute`, `hierarchy`,
  `schema`, `co_occurrence`. `coreference`, `quantity` and `negation` MUST be removed, and
  `020`'s list of thirteen MUST remain unchanged in `020`'s file. `SignalAspect`, moving
  `NEGATION`, `TEMPORAL`, `QUANTITY`, `COREFERENCE` and `UNCERTAINTY` out of `SignalKind`
  entirely, MAY be a later forward revision and MUST NOT be taken in `021`. Because the
  replacement narrows rather than widens, `021` MUST document a pre-flight `SELECT` that
  reports rows carrying a removed kind, MUST refuse rather than rewrite them, and MUST NOT
  issue an `UPDATE`, a `DELETE` or a transitional whitelist to make the constraint apply.
  (§15, §16, §62)
  *Tests:* `test_the_kind_constraint_is_dropped_and_recreated`,
  `test_the_whitelist_is_exactly_the_live_signal_kind`,
  `test_the_whitelist_lists_exactly_fifteen_members`,
  `test_020_still_lists_exactly_thirteen_and_021_lists_fifteen`,
  `test_the_migration_file_states_the_kind_narrowing_preflight`.
- **FR-153**: A durable home for a `ValidationResult` MUST exist, and it MUST be
  `relation_claim.validation_record JSONB NULL`. `SqlRelationClaimStore.record_validation` and
  `SqlRelationClaimStore.non_valid` MUST stop raising `NotImplementedError` as a consequence,
  and `CLAIM_JSONB_COLUMNS` MUST NOT gain the column, because it is the exclusion list the
  resolution scans against. `relation_claim` MUST NOT gain any other JSONB column while the
  resolution returns the first match in declaration order, or a verdict will be written into
  an unrelated column without a line of code changing. The column MUST be excluded from
  `RelationClaim._material()`, so that recording a verdict does not mint a new `relation_id`.
  One verdict per claim revision is declared sufficient, because the lifecycle validates once
  before admission; a second validation of the same `relation_id`, or the first non-test
  importer of the store, MUST trigger a forward revision adding an append-only
  `relation_claim_validation` table. (§59, §60, §62, §91)
  *Tests:* `test_the_verdict_home_resolves_without_a_database`,
  `test_relation_claim_carries_exactly_one_foreign_jsonb_column`,
  `test_the_verdict_column_is_not_identity_material`,
  `test_the_verdict_column_is_not_in_the_owned_jsonb_set`.
- **FR-154**: `021` MUST add `ix_relation_candidate_object`, `ix_relation_signal_object`,
  `ix_relation_claim_candidate`, `ix_relation_candidate_status`,
  `ix_relation_candidate_signature` and `ix_validation_finding_candidate`, and every index
  it creates MUST lead with `tenant_id`. `by_signal` on the candidate side MUST be served by a
  filter over the tenant's candidates and NOT by an index, because no plain btree serves JSONB
  containment and a tenant-prefixed GIN would require a `btree_gin` extension this repository
  does not declare; the resulting O(candidates in tenant) cost MUST be reported as a known
  limitation, not presented as a design win. (§59, §62)
  *Tests:* `test_every_index_021_adds_leads_with_tenant_id`,
  `test_the_index_names_and_column_lists_match_the_orm`,
  `test_no_index_021_adds_is_built_without_a_tenant_prefix`.
- **FR-155**: `021` MUST be tenant-scoped and MUST NOT drop a historical semantic observation.
  It MUST emit no `UPDATE`, `DELETE`, `TRUNCATE`, `drop_table` or `drop_column`; its only `DROP`
  operations MUST be `drop_constraint(..., type_="check")`, which removes a rule and not a row.
  Every column it adds MUST land on a table that already carries `tenant_id NOT NULL` with a
  `tenant_id <> ''` CHECK, and `021` MUST create no table, no global row and no nullable
  tenant. Every query in the new store MUST filter on an explicit `tenant_id`. `020` MUST be
  pinned by content digest so that "020 MUST NOT be edited" is enforced rather than asserted,
  and `relation_signal`, `relation_candidate` and `source_temporal_observation` MUST be added
  to the live `OWNED_TABLES` drift check, which today omits all three. (§62, constitution I and
  VII)
  *Tests:* `test_no_statement_would_edit_a_row`,
  `test_no_table_and_no_column_is_dropped`,
  `test_no_check_is_dropped_outside_the_three_named`,
  `test_every_added_column_lands_on_a_table_that_already_carries_a_fail_closed_tenant`,
  `test_no_new_table_is_created`,
  `test_no_query_in_the_new_store_omits_a_tenant_predicate`,
  `test_020_is_pinned_by_digest`.
- **FR-156**: `validation_findings` MUST gain `candidate_id String(64) NULL` and
  `ix_validation_finding_candidate (tenant_id, candidate_id)`, so that a finding about an
  unadmitted candidate has somewhere to attach, and a candidate-stage finding MUST NOT
  fabricate an `assertion_ref` to satisfy its `NOT NULL`. A finding about a **claim** MUST
  continue to attach through the existing `assertion_ref` plus
  `ix_validation_finding_assertion`, and that path MUST NOT be duplicated by a second column.
  (§56, §59, §62)
  *Tests:* `test_a_candidate_stage_finding_never_fabricates_an_assertion_ref`,
  `test_a_claim_stage_finding_attaches_through_assertion_ref`.
- **FR-157**: `021.downgrade()` MUST raise `NotImplementedError` **before emitting any
  operation**, and MUST NOT drop even the lossless indexes, because a downgrade that drops
  some objects and then refuses leaves a database matching no revision. The refusal MUST name
  `predicate_signature_key`, `predicate_normalized`, `relation_claim.candidate_id` and
  `validation_record` as the four things that cannot be reversed, on the grounds that
  `predicate_signature_key` is the term `logical_candidate_id` is derived from and
  `relation_claim.candidate_id` is inside `content_hash`, so dropping either leaves stored
  rows that still look intact while the material their identity came from is gone. Rolling back
  remains a forward operation. (§62)
  *Tests:* `test_downgrade_refuses_before_emitting_any_operation`,
  `test_the_refusal_names_what_would_be_lost`.
- **FR-158**: ORM/migration parity, schema invariant and round-trip tests MUST exist for `021`
  and MUST compare CHECK constraints **by text and not only by name**, because a vocabulary
  that changes on one install path and not the other leaves the constraint *names* identical
  and is therefore invisible to a name-only comparison. The parity test MUST compare each
  vocabulary literal against the **live value type** and not against a count. Offline
  verification MAY prove: the recorded operation stream, per-column agreement of name, type,
  nullability and server default, check text, index lists, the whitelist against the enum, the
  absence of any row-editing statement, the downgrade refusal, domain `to_dict`/`from_dict`
  round trips, the row-builder output, and that a verdict home resolves from ORM metadata
  alone. It MUST NOT be reported as verified, and MUST be reported separately, anything
  requiring a live PostgreSQL: that the DDL is accepted; that the narrowed kind whitelist
  applies to a database holding legacy removed kinds; that `jsonb_array_length` and
  `IS DISTINCT FROM` behave as assumed inside a CHECK; that `alembic upgrade head` reaches a
  single head; that the new indexes are used; and any real store round trip. `SC-012` MUST be
  reported clause by clause — constructible `verified`, assemblable `verified`, persistable
  `verified only offline` — and never as a single `verified`. (§62, §91, §114)
  *Tests:* `test_the_columns_agree_with_the_orm`,
  `test_the_check_constraints_agree_with_the_orm_by_text`,
  `test_the_signature_survives_a_domain_round_trip_field_by_field`,
  `test_a_candidate_assembled_only_from_co_occurrences_is_storable_by_the_row_builder`,
  `test_a_co_occurrence_signal_is_accepted_by_the_database` *(live; skipped without
  PostgreSQL)*.

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
- **FR-070**: *tombstone — removed as a permission from which no acceptance criterion is
  constructible; both surviving sentences are restated as constitutional non-goals below, and
  the reasoning is in `repair/A6-fr-triage.md` and `design-notes/rdf-interoperability.md`. This
  slot carries no normative requirement and MUST NOT be cited as a live target.* (§80, §81)

### Boundedness and determinism

- **FR-071**: Candidate generation MUST follow generate-wide-within-bounded-neighbourhood →
  hard block → resolve → semantic interpretation → validate → admit. An all-mentions ×
  all-mentions sweep is forbidden. Required neighbourhood classes: same sentence, same
  segment, same paragraph/block, dependency-connected, DOM-local, table-local, list-local,
  metadata-local, event-participant, reference-local, explicit link. Every signal MUST state
  its actual neighbourhood. (§46)
- **FR-072**: The extraction layer MUST remain linear, or bounded-superlinear within named
  local structures. Every producer MUST expose and report `characters_scanned`,
  `tokens_scanned` where meaningful, `candidate_pairs_considered`,
  `structural_nodes_considered`, `signals_emitted`, input size, signals produced and elapsed
  time. Hard per-document and per-segment ceilings MUST be explicit. The implementation itself
  MUST remain bounded — a counter checked after the work does not make the work bounded. **A
  named mutation test MUST fail on an all-mentions × all-mentions pair sweep in any extraction
  path.** *(§47, §106, §72)*
- **FR-073**: Two independent runs MUST be identical. Producer order MUST NOT alter ids. No
  `uuid.uuid4()`, no `datetime.now()`, no dict-order-dependent output, no random tie-breaking.
  (§92, §108)
- **FR-074**: No hidden semantic gate. No extraction path may call
  `OntologyPack.allows_type()` as a drop/deny decision, and no relation-extraction path may
  contain `if relation not in registry: continue` or an equivalent guard whose effect is to drop
  an unrecognised reading. The check MUST be an AST test over every extraction module that fails
  on a call to `allows_type()` used in a boolean-drop position and on any
  continue-on-unrecognised guard, and it MUST be a **named mutation test** — §97's
  `if core pack does not know type: continue` MUST fail it. *(§73, §76, §97)*
  Note: `apps/interpretation/extractors/registry.py:76` calls `pack.allows_type(name)` today, so
  the FR describes a state that is **not** true at HEAD.

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
- **FR-078**: A constitutional mutation harness MUST be manifest-driven. Its manifest is exactly
  the 18 fields enumerated in §93: **entity layer** `type_ref`, `entity_ref`, `tenant`,
  `evidence`, `mapping`, `status`; **relation layer** `predicate_signature`, `participants`,
  `roles`, `polarity`, producer identity, signal evidence, candidate identity, surface
  exclusion from logical identity; **projection layer** `direction`, `arity`, claim provenance,
  edge identity. Each manifest entry MUST have a **named** test that fails when that field is
  broken. The six §94–§99 mutations are manifest entries 7–12, named: raw surface in logical
  identity (§94), majority-vote arity/direction (§95), synthetic `surface:person:john` (§96),
  `if core pack does not know type: continue` (§97), `if relation_ref is None: return ()` (§98),
  a producer importing or constructing `GraphEdge` (§99). §100 is a deliverables section and §101
  is a domain-model section; **neither is a mutation source.** The count of manifest entries is
  **18**, and `SC-015`'s "≥ 20" is corrected to "every entry in the manifest".
- **FR-079**: *tombstone — merged into `FR-078`; see the deleted-ids table in
  `repair/A6-fr-triage.md`. The six section mutations of `input.md` §94, §95, §96, §97, §98 and
  §99 are manifest entries 7–12 of `FR-078`,
  not a separate apparatus, so the old "Four" / six contradiction is gone. This slot carries no
  normative requirement and MUST NOT be cited as a live target.*
- **FR-080**: *tombstone — merged into `FR-072`; see the deleted-ids table in
  `repair/A6-fr-triage.md`. It restated the same five metrics. This slot carries no normative
  requirement and MUST NOT be cited as a live target.* (§106)
- **FR-081**: No regression may be introduced into `projection`, `acquisition`, `interpretation`,
  `admission`, `control-plane` or `shared`. Existing known failures MUST remain unchanged
  unless directly affected, and baseline membership, new failures, fixed failures and new
  tests MUST all be tracked. Reporting "green" while new failures hide among known ones is
  forbidden. (§107)
- **FR-082**: Encountering a new ontology requirement, a relation-identity ambiguity, an
  external-vocabulary mapping ambiguity, an entity/value ambiguity, a parser capability that
  cannot be made deterministic, or a persistence representation that loses information MUST
  stop the work and be reported explicitly, using `UNKNOWN`, `AMBIGUOUS`, `CONFLICTING` or
  `UNSUPPORTED` rather than a guessed type or relation. (§111)
- **FR-180**: Every hard prohibition stated in the brief MUST have at least one named test that
  **fails** when the prohibition is violated, and that test MUST be reachable from a task in this
  plan. At minimum this covers §72's all-mentions × all-mentions pair sweep, §74's six-symbol
  producer import **and construction** ban, §30's parser-free useful baseline, §73's semantic
  gate, §75's `ENT-`/`RES-` ban, §45's majority vote, §16's mandatory surface, §103's fourth
  epistemic level, and §104's finite mandatory relation list. A prohibition with no enforcing test
  is a **non-requirement** and MUST NOT be counted toward feature completeness. The checker's job
  is to assert that this list and `spec.md` agree, so a new prohibition cannot be added without a
  test.
  *(§72, §74, §30, §73, §75, §45, §16, §103, §104)*
  *Applied verbatim from `repair/A6-fr-triage.md` §2.5, the second half of A6's band under
  `repair/ARBITRATION.md` §14. The first half, `FR-179`, is the §8 producer obligation and sits
  with the type vocabulary it obliges.*

### Specification deliverables (§100)

- **FR-083**: This feature MUST ship `specs/021-entity-relation-extraction-finalization/`
  containing `spec.md`, `plan.md`, `tasks.md`, `data-model.md`, `research.md`, `input.md`,
  `checklists/requirements.md` and `contracts/`, plus ADR-level records in
  `specs/021-.../adr/` for decisions **A–L**: **A** bounded foundational atomic vocabulary is
  allowed; **B** entity/value type vocabulary is separate from relation vocabulary; **C**
  relation extraction is open-world and signal-driven; **D** raw relation surface is evidence,
  not logical identity; **E** `PredicateSignature` is structural normalised identity before
  ontology mapping; **F** unknown predicates are durable hypotheses; **G** n-ary relations are
  native; **H** `GraphEdge` is a projection of admitted claims only; **I** mention binding is
  distinct from entity resolution; **J** no majority-vote semantic assembly; **K** producers
  remain observation instruments; **L** *the `PredicateSignature` normalisation rule set,
  including any synonym table, is versioned, sourced and reviewable* — added because governance
  requires an ADR for any entity-resolution-grade decision and A–K had no slot for the N5
  synonym table (K5).
- **FR-084**: The completion report MUST contain all 14 sections mandated by §114, in order,
  and MUST classify every claim in each as one of `implemented`, `verified`,
  `verified only offline`, `known limitation`, `deferred`: (1) changed-file manifest,
  (2) architecture summary, (3) domain model changes, (4) migration summary, (5) producer
  summary, (6) identity changes, (7) execution path before/after, (8) graph projection
  semantics, (9) corpus coverage, (10) mutation-test results, (11) replay/determinism results,
  (12) benchmark results, (13) complete test matrix, (14) explicit remaining debt. "Feature
  complete" requires that the §101 architecture is represented in **production** code and that
  the golden and mutation corpora prove the constitutional properties; passing tests alone is
  not sufficient. *(§114, §108)*

### Verified 019 defects requiring substrate work

These come from reading the code, not from the brief. Each is a real defect found at HEAD.

- **FR-085**: `RelationCandidate.signal_refs` MUST be canonicalised on construction, exactly
  as `observation_refs`, `evidence_refs` and `supporting_spans` already are, so that
  `candidate_id` cannot depend on caller iteration order. Determinism MUST hold from the
  type, not from a sort at one call site. (§61, §102)
- **FR-086**: `RelationCandidate` MUST gain `to_dict()`/`from_dict()` and MUST round-trip
  **every field the type declares at the time of the change, and every field added by
  FR-088**, losslessly — explicitly including `signal_refs` and `confidence`, and including
  `direction`, `polarity`, `alternative_refs` and `mapping_evidence_refs` **once FR-088 has
  added them**. The previous wording asserted those four as existing fields; they do not exist
  at HEAD. The round-trip test MUST assert the field list, not a summary string. *(§59, §60,
  §91)*
- **FR-087**: A `predicate_signature` MUST be persisted in its own columns on both
  `relation_signal` and `relation_candidate` — normalised form, arity, role names, argument
  shape, direction and polarity — so that candidate identity no longer depends on a raw
  surface string and `PredicateHypothesis` is not stored as an opaque digest. Migration `021`
  MUST also add `participants JSONB NOT NULL` to **both** `relation_signal` and
  `relation_candidate` — a typed structured field, not `extra`, not a later migration — holding
  the canonical serialisation defined by the identity subsystem's participant ordering
  (FR-002), so that a stored row round-trips to an identical in-memory object and re-derives an
  identical `signal_id` / `logical_candidate_id`. (§59, §60, §91, §62)
- **FR-088**: `relation_candidate` MUST gain columns for `signal_refs`, `direction`, `polarity`
  and `confidence`; `relation_claim` MUST gain `candidate_id`; and the store MUST write and
  read all of them. `subject_mention_ref` / `object_mention_ref` are **retained** as
  compatibility accessors for binary records and become derived from
  `participants[0]` / `participants[1]`; they are never a second source of truth. No field that
  participates in an id may be absent from the row. (§60, §91)
- **FR-089**: `RelationSignal._material()` MUST include the declared arity mode and role
  bindings, so two signals differing only in their stated shape do not collapse into one
  `signal_id`. `producer_ref` MUST remain in the material — that part is correct — and the
  three docstrings claiming two producers reading one structure share a `signal_id` MUST be
  corrected. (§24, §61)
- **FR-090**: A **structural** reading conflict — producers disagreeing on arity, direction,
  polarity or role bindings for one participant configuration — MUST yield
  `RelationCandidate.assembly_state = CandidateAssemblyState.CONFLICTING` with both readings
  preserved, and MUST be reported in `AssemblyReport` as a conflict. The three epistemic axes
  are never collapsed. Incompatible **semantic** readings of the same structure are
  `PredicateHypothesis.resolution_state = CONFLICTING`. Incompatible **structural** readings are
  `assembly_state` on the candidate. `CandidateStatus.CONTRADICTED` is reserved for a positive
  reading set against an explicit denial, and a structural disagreement MUST NOT be routed into
  it. `CandidateAssemblyState` is a separate enumeration with members `CONSISTENT`, `AMBIGUOUS`
  and `CONFLICTING`; it is distinct from `CandidateStatus`, and `CandidateStatus` MUST NOT
  become a dumping ground for the epistemic space. Majority vote and alphabetical tie-break
  MUST be deleted from `_arity_of`, and its `-> Any` return annotation MUST become
  `RelationArityMode`. A declared `NARY` schema MUST NOT be downgraded to `DIRECTED` by a vote,
  and losing the vote MUST NOT silently drop the role bindings with it. (§45, §95)
- **FR-091**: `RelationalReading.to_candidate()` MUST be removed, or reduced to a call into the
  assembler, so that "how does a signal become a candidate" has exactly one answer in the
  codebase and not merely one documented answer. (§48, §57)
- **FR-092**: The lifecycle MUST be split so that materialisation, validation, admission and
  projection are separately observable. The `ValidationReport` that gated admission MUST be
  retained and surfaced, not discarded as a local. **The post-admission re-validation MUST be
  deleted.** There is no "or justified" alternative: §57 forbids `RelationClaim → Validation` as
  the primary lifecycle unconditionally, and a justification is not a pass condition. If a
  second check is genuinely required it MUST be a distinct, differently-scoped check with a
  different name and a different pass criterion, and it MUST NOT be the same check run twice.
  The admission decision MUST actually gate the store write rather than being computed and
  discarded. Production writes MUST NOT be doubled to demonstrate idempotency. *(§57, §58)*
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
- **FR-095**: Structural data loss MUST be reported, not silent. `zip(..., strict=False)` in
  the list producer MUST become strict. A width-mismatched table row MUST emit a note or a
  signal rather than being dropped. A heuristic header-row choice MUST NOT be published as an
  exact precision string: `Neighbourhood.is_exhaustive` is a substring test on that string —
  **it tests for `"exhaustive"`, not `"exact"`** — so publishing a heuristic with the literal
  text `precision="exact; …"` happens not to trip it. The real defect is that a human-readable
  string is load-bearing for a machine decision; the fix is to make `is_exhaustive` read a
  typed field and to state the heuristic on the signal. *(§46, §47)*
- **FR-096**: `SourceTemporalObservation` MUST be reachable from the normal acquisition path.
  `capture_with_observations()` MUST be called by `capture()`/`captures()` or replaced by the
  equivalent, `source_temporal_observation` MUST gain a repository with a writer and a reader,
  and the two adapters that already implement `to_temporal_observations` MUST have their
  output actually consumed. (§61)
- **FR-097**: Migration `021` MUST be added on top of `020`, which is the current Alembic head
  and is forward-only. `020` MUST NOT be edited. `021` MUST add every column FR-087/FR-088
  require — including `participants JSONB NOT NULL` on **both** `relation_signal` and
  `relation_candidate`, with no deferral to any later migration and no reuse of `extra` — and
  ORM/migration parity MUST stay test-enforced.
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

### Constitutional requirements (Principle VI, II, VII; Governance)

*(A1 band, `FR-161`…`FR-173`)*

These requirements implement Constitution Principles VI (Process-Centric), II (Evidence-First)
and VII (Security-First), plus the Additional Constraints and the Governance clauses, none of
which any existing FR in this document covers. Authority order: the constitution supersedes
`input.md`, which supersedes this document. Worked examples are in
`repair/A1-constitution-investigation.md` §D2.4.

Applied verbatim from `repair/A1-constitution-investigation.md` §D6 under
`repair/ARBITRATION.md` §14 rule 2, which renumbers A1's own thirteen authored requirements into
this band, and placed where §D6 asks for it — after `FR-100`, before *Production reachability, as
measured*, so that the reachability table sits under the requirements that explain why it exists.

- **FR-161**: The `Investigation` MUST be the only production entry point for the extraction and
  projection substrate. A production module outside the investigation workflow MUST NOT call
  `interpret_warc_capture`, an extractor, an assembler, an admission engine, or a graph store.
  `services/entity_pipeline.py::run_live_entity_pipeline` MUST become a client that starts an
  `InvestigationWorkflow` and MUST NOT hold a projection itself.
  **Test**: `apps/control-plane/tests/constitution/test_vi_single_entry_point.py::test_no_production_caller_of_interpretation_outside_the_workflow`
  — scans every non-test module under `apps/` for the six forbidden callees and fails on any hit
  outside `workflows/investigation_lifecycle.py`.
  **Rationale**: Principle VI — "The user creates an Investigation — not a graph."

- **FR-162**: The direct `user → extractor → graph` path MUST be prohibited as a *class of
  defect*, not merely as a call site. An extraction request that does not name an
  `investigation_id` MUST be refused at the boundary, and the refusal MUST be a named error code,
  not a `None` return. Stage ordering MUST continue to be validated by
  `cp_domain.investigation._TRANSITIONS`; an out-of-order stage MUST raise
  `InvestigationInvalidTransition`.
  **Test**: `apps/control-plane/tests/constitution/test_vi_single_entry_point.py::test_a_request_without_an_investigation_id_is_refused_with_a_named_code`
  and `::test_stages_may_not_run_out_of_order`.
  **Rationale**: Principle VI; Additional Constraints "No MVP/mini-architecture" — eight planes,
  each of which needs a contract.

- **FR-163**: `InvestigationWorkflow` MUST be registered on the Temporal worker, on task queue
  `cognitive-investigations`, together with every activity it calls. A workflow or activity that is
  not registered MUST NOT be described in a spec, plan or docstring as available.
  **Test**: `apps/control-plane/tests/constitution/test_vi_single_entry_point.py::test_investigation_workflow_and_all_activities_are_registered`
  — imports `workflows.worker`, reads its `workflows=` / `activities=` lists and asserts membership;
  plus `::test_no_workflow_executes_an_activity_by_string_name`, which fails on any
  `workflow.execute_activity` whose first argument is a `str` literal.
  **Rationale**: Principle VI; Additional Constraints "No MVP/mini-architecture". The two string
  activity names at `workflows/investigation.py:213,288` are the reason.

- **FR-164**: The workflow's stages MUST be, in order: `acquire`, `bind_mentions`,
  `extract_type_signals`, `extract_relation_signals`, `assemble_candidates`, `validate_candidates`,
  `admit_claims`, `project`. Mention binding MUST be its own stage and MUST NOT be folded into
  signal extraction. The workflow MUST NOT reimplement
  `temporal_materialization.reconcile_and_publish`; it MUST delegate to it, and the number of call
  sites of `domain.temporal_materialization.materialize_history` and of the Common Crawl discovery
  block MUST NOT increase.
  **Test**: `apps/control-plane/tests/constitution/test_vi_single_entry_point.py::test_stage_order_is_the_declared_order`
  (asserts the recorded activity order from a hermetic `Worker` run) and
  `::test_materialize_history_call_sites_do_not_grow` (a fixed-count assertion, currently 3,
  documented as such).
  **Rationale**: Principle VI; and the four duplicated `StreamRecord` literals at
  `temporal_materialization.py:65,82,98,115`, each hard-coding `"confidence": 0.91`.

- **FR-165**: Every consumer in the investigation path MUST be idempotent on a key drawn from
  `event_id` / `task_id` / `observation_id` / projection offsets, and the key MUST be named in the
  consumer's signature. Specifically: `acquire` on `task_id`; `bind_mentions` on `observation_id`
  **including the capture** in the key, so two captures of one segment are two mentions;
  `extract_type_signals` and `extract_relation_signals` on `event_id`; `assemble_candidates` on
  the derived `candidate_id`; `validate_candidates` on the derived `relation_id`; `admit_claims` on
  an `admission_id` **re-derived** from `(candidate_id, policy_version, reason_codes,
  score_vector)` rather than `uuid.uuid4().hex[:12]`; `project` on a monotonic
  per-`(tenant_id, investigation_id)` `projection_offset` written on success only.
  **Test**: `apps/shared/tests/constitution/test_vi_idempotency_keys.py::test_every_activity_declares_an_idempotency_key`
  (introspects the eight activity signatures), `::test_admission_id_is_content_addressed` (two
  identical admissions derive one id; two differing `reason_codes` derive two), and
  `::test_replaying_a_completed_task_id_issues_no_network_call`.
  **Rationale**: Additional Constraints "Idempotency" — the clause quotes these four keys by name.
  Currently `admission.py:69` mints a fresh `uuid4` and
  `temporal_materialization.py:152-157` retries three times with no key at all.

- **FR-166**: The investigation lifecycle MUST run within a policy, budget and freshness gate
  before `acquire` performs any network call, and the gate MUST be tenant-scoped: a policy or
  budget that does not belong to the requesting tenant MUST be refused fail-closed, not defaulted.
  Budgets MUST exist at the `task`, `source`, `investigation` and `global` tiers. A missing
  downstream-lag reading MUST be treated as **maximum** lag, not as zero.
  **Test**: `apps/control-plane/tests/constitution/test_vii_policy_boundary.py::test_another_tenants_policy_is_refused`,
  `::test_four_budget_tiers_exist`, `::test_absent_lag_reading_is_treated_as_maximum_lag`,
  `::test_no_network_call_occurs_before_the_gate_passes`.
  **Rationale**: Principle VI's "its policy/budget/freshness constraints"; Principle VII's "tenant
  isolation at every level"; Additional Constraints "Backpressure" and "Retry budgets". Currently
  `dispatcher.py:86` passes `{"downstream_lag_s": 0.0}` and `policy_service.py:22-28` hard-codes
  one tenant.

- **FR-167**: A change to an architectural decision on the Governance list MUST ship an ADR before
  the change merges. For this feature that means, at minimum: `Temporal` (the investigation
  workflow), `provenance` (the evidence warrant chain), `entity resolution` (any synonym or
  equivalence table over a term of `logical_candidate_id`), and `recrawl` (any scheduling
  decision). `FR-083`'s A–K list is extended with the entries this feature actually decides. A
  synonym or equivalence table over `PredicateSignature.normalized_predicate` is **forbidden**:
  `owns`, `controls` and `manages` remain three logical hypotheses.
  **Test**: `apps/control-plane/tests/constitution/test_governance_adrs_exist.py::test_each_governance_decision_in_this_feature_has_an_adr`
  — asserts `docs/adr/0025`…`0028` exist, are non-empty and each contains a `## Decision`
  section; plus `::test_no_synonym_table_over_normalized_predicate`, which scans the 021 artefacts
  and `PredicateSignature` for any `owns`–`controls` equivalence.
  **Rationale**: Governance, verbatim: "Changes to architectural decisions require an ADR (e.g., …
  provenance, entity resolution, admission engine, frontier architecture …)".

- **FR-168**: Constitutional compliance MUST be verified automatically on every change, not by
  hand. If no CI is added, the completion report MUST carry a dated, named attestation of who ran
  the gate, on which commit, with the per-suite failure counts from the Phase 0 baseline — and
  `FR-084`'s "verified" MUST NOT be claimed for any check that was not run.
  **Test**: `apps/control-plane/tests/constitution/test_governance_adrs_exist.py::test_constitutional_suite_runs_unattended`
  — runs `pytest apps/shared/tests/constitution apps/control-plane/tests/constitution` in a
  subprocess with no network and asserts exit code 0; plus
  `::test_completion_report_distinguishes_implemented_verified_and_offline`, which greps the report
  for the five required words and fails on a bare "complete".
  **Rationale**: Governance, verbatim: "Compliance is verified on every PR/review." `.github/`
  does not exist.

- **FR-169**: A `SIGNAL` hop kind MUST exist and MUST be traversable in **both** directions, and a
  `candidate_id` MUST be reachable from any projected edge **without** `CANDIDATE` becoming a link
  in `EVIDENCE_BACKWARD_CHAIN`; the resolution is a second step, not a hop. A reference that cannot
  be resolved MUST be reported as an incomplete trace naming the gap, never as an empty hop list.
  **Test**: `apps/shared/tests/unit/test_evidence_lineage.py::test_a_signal_hop_is_traversable_backward_and_forward`,
  `::test_candidate_is_resolvable_from_a_relation_without_joining_the_warrant_chain` (asserts
  `EVIDENCE_BACKWARD_CHAIN` still excludes `CANDIDATE`), and
  `::test_an_unresolvable_reference_names_the_gap`.
  **Rationale**: Principle II — "Any knowledge must trace fully". `HopKind`
  (`evidence_lineage.py:50-65`) has no `SIGNAL` member, so `spec.md:897-898`'s
  `edge → claim → candidate → signals → observations → source` is unreachable in *either*
  direction. The `CANDIDATE` exclusion and its written argument at `:75-80` are preserved.

- **FR-170**: A rejected candidate MUST NOT be deleted by any production path, **including the
  path that handles its re-evaluation**. `POST /dlq/{record_id}/re-evaluate` MUST record the
  re-evaluation outcome **on** the preserved record and leave the payload byte-for-byte intact.
  `QuarantineStore.purge` MUST either be removed or be restricted to records whose payload has
  already been durably copied to the configured `sink`, and MUST be unreachable from any route.
  **Test**: `apps/control-plane/tests/integration/test_quarantine.py::test_re_evaluate_does_not_delete_the_record`,
  `::test_replay_after_re_evaluate_returns_the_original_payload_bytes`, and
  `::test_purge_is_unreachable_from_any_route` (introspects the FastAPI route table for a handler
  that reaches `QuarantineStore.purge`).
  **Rationale**: Additional Constraints, verbatim: "rejected candidates are never auto-deleted
  (replay/re-evaluation supported)"; Governance: "Rejected analysis outputs (admission rejections,
  TDA signals) are preserved with decision, reasons, score vectors, versions, and timestamps for
  replay." Currently `api/routes/quarantine.py:64` calls `_store.purge(record_id)`.

- **FR-171**: `services/audit.py::AuditLog` MUST write to the durable `AuditLog` table at
  `db/schema.py:596` and MUST NOT be satisfiable by an in-memory list alone. An `admit_claims`
  decision and a `project` write MUST each produce an audit record carrying the decision, the
  reason codes, the score vector, the policy version and the timestamp.
  **Test**: `apps/control-plane/tests/constitution/test_vii_audit_is_durable.py::test_an_admission_decision_is_persisted_and_survives_a_new_log_instance`
  and `::test_audit_records_carry_decision_reasons_score_vector_policy_version_and_timestamp`.
  **Rationale**: Principle VII's Mandatory list includes "audit logs". `audit.py:40` is
  `self._events: list[AuditEvent] = []`, `audit.py` has exactly one importer and it is a test, and
  the durable table that already exists has no writer.

- **FR-172**: `workflows/investigation.py` MUST be deleted and its lifecycle state machine
  relocated into `cp_domain/investigation.py`, so that exactly one investigation lifecycle exists.
  `services/layer0_pipeline.py`'s orchestrator MUST be deleted and its `InterpretHook`,
  `FabricHook`, `SearchHook` and `LakeHook` protocols retained on the investigation path.
  `services/acquisition_loop.py` MUST NOT be wired in any form: its fetch is
  `follow_redirects=True` with no egress policy, no DNS-rebinding protection and no host allowlist,
  which Principle VII forbids and which a live registration would turn from a dead violation into a
  live one.
  **Test**: `apps/control-plane/tests/constitution/test_vi_dead_surface_is_gone.py::test_workflows_investigation_py_does_not_exist`,
  `::test_exactly_one_investigation_lifecycle_module_exists` (searches for `class LifecycleState`
  and `class InvestigationState` and asserts one owner),
  `::test_layer0_orchestrator_is_gone_and_its_hooks_survive`, and
  `::test_acquisition_loop_is_not_imported_by_any_production_module`.
  **Rationale**: Principle VI (no single subject); Principle VII (egress). `workflows/worker.py:20-27`
  registers neither workflow and `investigation.py:213,288` name two activities that do not exist.

- **FR-173**: Every constitutional citation in code, tests, migrations and feature artefacts MUST
  name the correct numeral. Tenancy is **VII**, not IV. Determinism is **unnumbered** and MUST be
  cited to INV-12 or to the Additional Constraints' "Idempotency" clause, not to VI. A citation of
  the form "constitution N" MUST be accompanied, on the same line or in the adjacent comment, by
  the clause's title or text.
  **Test**: `apps/shared/tests/constitution/test_citation_numerals_are_correct.py::test_no_citation_attributes_tenancy_to_iv`
  and `::test_no_citation_attributes_determinism_to_vi` — a repository scan of all `.py` and `.md`
  files for the mis-cited patterns, which currently matches 20 sites for tenancy-as-IV and 6 for
  determinism-as-VI.
  **Rationale**: a gate that cites the wrong clause is not a gate. `plan.md:85` and `:86` are two
  of the sites, and `apps/shared/tests/constitution/test_iv_vi_tenancy_and_determinism.py` is a
  third — the constitution test suite's own filename.

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

### Appended requirements *(A8prep allocation, `FR-110`…`FR-115`)*

The reserved ranges are stated once, in the `### Functional Requirements` preamble above. Nothing
below reuses a void or reserved number, and nothing below is renumbered.

- **FR-110**: The foundational type vocabulary MUST be **complete and versioned**: the shipped
  manifest MUST match the registered artefact byte for byte, its `version` MUST be pinned and
  loadable, and a consumer MUST never receive a `value:*` ref where an `Entity` is required or
  an `Entity` where a value is required. `kind` MUST be read from the entry and MUST NOT be
  inferred from the ref, so `core:Coordinate` and `value:Coordinate` are two distinct refs in
  two namespaces. This is the normative parent of the type-vocabulary completeness and the
  value/entity separation criteria (SC-017, SC-018) and of the 31/13 counts in FR-030/FR-031.
  *(§4, §63, §8)*
- **FR-111**: A type the `core:` pack has never heard of MUST be retained end to end as a
  `TypeHypothesis` with `hypothesis_state=UNKNOWN` and MUST survive a store round trip, and
  **zero** mentions may be dropped for an ontology miss. A later `INFERRED` status MUST be a
  **new revision** under the same logical assertion id, and every prior state MUST remain
  retrievable; an `INFERRED` promotion is never a destructive replacement. This is the
  normative parent of SC-020, SC-022 and SC-027 and of `INV-003`. *(§10, §76, §97)*
- **FR-112**: Type resolution MUST consume the already-available context — document title,
  section heading, DOM parent, table heading, neighbour mentions, URL/domain, metadata and
  language — **by reference to a named, bounded structural neighbourhood**, never by a document
  sweep, and it MUST represent competing hypotheses with evidence rather than encoding a
  universal deterministic truth rule. A mention's type hypotheses and a relation signal's role
  hypotheses MUST be mutually consumable for resolution and blocking, and those hints MUST
  remain hints: no role hint may become truth or enter identity material. This is the normative
  parent of SC-028. *(§71, §77)*
- **FR-113**: Migration `021` MUST **drop** the obsolete CHECK constraints inherited from
  `020` — the two `*_asserts_something` constraints and the stale `ck_relation_signal_kind`
  whitelist — exactly as FR-013 enumerates them, and a constraint that survives solely because
  `020` created it MUST NOT survive `021`. `020` MUST NOT be edited to achieve this. A
  pre-flight that would narrow-with-refusal rather than drop the whitelist is reported, not
  applied (Principle I). *(§62, §80)*
- **FR-114**: ORM/migration parity tests and schema invariant tests MUST be extended to cover
  every **dropped** constraint as well as every added column: a constraint present in the ORM
  metadata but absent from the migration head, or vice versa, MUST fail parity. Round-trip
  tests remain conditional on PostgreSQL per FR-062, and the omission MUST be reported
  `verified only offline`. *(§62, §91)*
- **FR-115**: `repair/tools/reference_check.py` MUST run as a **gate**: it MUST execute in CI or
  the pre-commit chain, MUST exit non-zero on any failed assertion in the gate list, and MUST
  report every check id in its summary so that a check which silently stopped running cannot
  hide. A run with a single FAIL MUST NOT be describable as clean. *(§100, §108)*

### Key Entities

- **RelationParticipant**: one end of an observed relational configuration — `mention_ref`
  (or a deferred reference), `slot`, `role_hypothesis`, `ordinal`, `confidence`. The canonical
  variadic representation of a signal's participants, persisted as typed `participants`
  JSONB on both `relation_signal` and `relation_candidate` (FR-008, FR-087).
- **PredicateSignature**: deterministic structural normalisation of a predicate realisation.
  Not a `RelationRef`; the bridge between linguistic realisation and relational
  configuration.
- **PredicateHypothesis**: the open-world reading of a predicate — surface, normalised form,
  signature, ref, alternatives, resolution state, mapping evidence. Its `relation_ref` is the
  **sole authority** for the relation reference (FR-021).
- **TypeHypothesis**: an interpretation candidate for what a mention is. Distinct from
  `TypeAssertion`, which is evidence-bearing.
- **TypeSignal**: what a structured or lexical source stated about a type, with
  `source_vocab` (an external vocabulary reference or `null` — never a synthetic sentinel),
  `surface` and mapping candidates.
- **TypeMapping**: an SSSOM-compatible record crossing two vocabularies, with match type,
  provenance and confidence.
- **CoreTypePack**: the versioned foundational `core:*` / `value:*` vocabulary — 31 entity
  types and 13 value types, with the 7 §8 extraction families as its producer obligations.
- **RelationSignal**: "this producer observed a relational configuration between these
  participant slots". Not "this relation holds", not "this is type X", not "create an edge".
- **RelationCandidate**: the durable hypothesis. One relational configuration, many readings.
  Carries `assembly_state` (`CONSISTENT` / `AMBIGUOUS` / `CONFLICTING`) as a separate axis from
  `candidate_status`, and its `relation_ref` is a derived view of the hypothesis's.
- **CandidateAssemblyState**: the structural-consistency axis of a candidate —
  `CONSISTENT`, `AMBIGUOUS`, `CONFLICTING`. Distinct from `PredicateHypothesis.resolution_state`
  and from `CandidateStatus`, and never a substitute for either.
- **RelationEvidenceView**: a projection of unadmitted candidates and signals, distinct from
  the world graph.
- **MentionOccurrenceIndex**: deterministic surface-occurrence → `MENTION-…` lookup, distinct
  from entity resolution.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `"John acquired Acme."` and `"Acme was acquired by John."` produce **one**
  `logical_candidate_id`, two `signal_id`s, two distinct `relation_surface`s and two
  `candidate_id`s — derived by the identity function, not by a fixture. **Status: proven as an
  algorithm, not yet as a production path.** `normalize_voice()` → canonical argument slots →
  canonical participant ordering → one `logical_candidate_id` is computable today and has a
  named test. It is **not reachable end to end** because no syntactic producer exists. This
  criterion therefore carries an `xfail(strict=True)` marker with reason
  `syntactic_producer_absent`; strict is mandatory, so an accidental pass is an error rather
  than a silent success. A **named task owns the `xfail → green` transition** and it is the
  syntactic producer task (the construction coverage of §29 — active, passive, copular,
  nominal, appositional, possessive, prepositional and relative-clause realisations). No
  implementation wave may report this criterion as passing while the marker is still `xfail`.
  *(FR-002, FR-005, FR-077, §84, §29)*
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
- **SC-013**: Provenance round-trip over **two distinct hop vocabularies**, never one. For
  every projected edge, (a) the **evidence** walk `edge → claim → evidence → observation →
  capture/raw → source` returns a complete warrant path, and (b) the **derivation** walk
  `edge → claim → candidate → signal → observation` returns every reading that produced the
  edge. Walking back from the source reaches every edge that source fed. The candidate is
  *reachable* from an edge by reference resolution but is **never a member of the evidence
  chain**: `INV-005` stands, a candidate is derivation and never evidence, and a structural
  disagreement is `assembly_state`, not a warrant failure. The two chains MUST NOT share one
  `HopKind` vocabulary, and a hop kind nothing writes is a failure rather than a silent
  `complete=False`. *(FR-068, `INV-005`, §68, §69, §78)*
- **SC-014**: A `DIRECTED` edge never has its endpoints reordered; an `UNDIRECTED` edge is
  reordered only when the admitted contract declares symmetry.
- **SC-015**: **Every entry in the §93 mutation manifest is broken by a mutation and a named
  test fails for it** — all **18** entries: 6 entity-layer, 8 relation-layer, 4 projection-layer,
  of which the six section mutations of `input.md` §94, §95, §96, §97, §98 and §99 are entries
  7–12 (FR-078). The count is 18, not "≥ 20":
  §93 enumerates 18 and no section outside §93 is a mutation source. *(FR-078)*
- **SC-016**: All six 019 suites hold their baseline membership exactly, with no new failures,
  **and** the tests that never executed — the 14 that self-skip and the 8 that are blocked on an
  unreachable PostgreSQL — are enumerated and tracked, because a floor that counts only what ran
  is not a floor. *(FR-081)*
- **SC-017**: The registered type pack `core-atomic-types@1` exposes 31 entity-kind entries and
  13 value-kind entries, every one carrying all eight §63 fields (`type_ref`, `label`,
  `alt_labels`, `broader_refs`, `narrower_refs`, `description`, `kind`, `version`) plus
  `namespace` and `pack_ref`; `len(pack.entries) == 44`; and the registry rejects a second
  registration of `core-atomic-types@1` with `ValueError`. Test: `test_a5_sc017_…`.
  *(FR-029, FR-030, FR-031, FR-110)*
- **SC-018**: For every one of the 44 entries, `kind` is read from the entry and never inferred
  from the ref, and `core:Coordinate` and `value:Coordinate` are two distinct refs with opposite
  `kind`s; a consumer that receives `value:EmailAddress` never receives an `Entity`. Test:
  `test_a5_sc018_…` plus a mutation that flips a value entry's `kind` to `ENTITY`, which fails.
  *(FR-031, FR-110)*
- **SC-019**: `TypeHypothesis` is an importable frozen dataclass with exactly the thirteen §6
  fields and a `hypothesis_state` whose value set is exactly
  `{UNKNOWN, OBSERVED, INFERRED, MAPPED, AMBIGUOUS, CONFLICTING}`; constructing one with a
  seventh state raises; and `semantic.types` imports nothing from `apps.control-plane` and
  nothing from `db.schema`. Test: `test_a5_sc019_…` and a module-scan test for the forbidden
  imports. *(FR-032)*
- **SC-020**: A `TypeAssertion` written before a `TypeHypothesis` set changes is still
  byte-identical after, and a promotion to `SemanticStatus.INFERRED` yields a new
  `type_assertion_id` under the *same* `logical_type_assertion_id` — verified over a store
  round trip, not over a fixture. Test: `test_a5_sc020_…`. *(FR-037, FR-111)*
- **SC-021**: The surface `"Apple"` produces **at least three** retained `TypeHypothesis` values
  on one mention — `core:Person`, `core:Organization`, `core:Product` (§7, verbatim) — with
  distinct `confidence` values, non-empty `evidence_refs` on each, no hypothesis deleted by a
  later one, and no `TypedMention.kind` field that could silently select one. Test:
  `test_a5_sc021_…` (§7). *(FR-033)*
- **SC-022**: A mention whose `type_ref` is in no registered namespace is retained end to end as
  a `TypeHypothesis` with `hypothesis_state=UNKNOWN`, survives a store round trip, and the §97
  mutation `if core pack does not know type: continue` fails a named test. Test:
  `test_a5_sc022_unknown_type_dropped_mutation_…`. *(FR-038, FR-111, `INV-003`)*
- **SC-023**: Every cross-vocabulary type statement the corpus produces is a `TypeSignal` with a
  populated `source_vocab`, `surface` and `mapping_candidates`, followed by zero direct
  `TypeAssertion`s; and the seven §64 mappings exist as `SemanticMapping` records with
  `mapping_set_id` and `mapping_set_version` set and with `schema:SoftwareApplication →
  core:Software` recorded as **not** `EXACT_MATCH`. Test: `test_a5_sc023_…`. *(FR-035, FR-036)*
- **SC-024**: With a pack satisfying FR-030 and FR-031 in full, zero producers, resolvers,
  blockers, validators, mappers or projectors consult `TypePack` membership to decide whether a
  mention exists, is typed, or is retained; the pack is provably unreachable from every
  extraction path, and a corpus row with no pack entry passes identically to a corpus row with
  one. Test: `test_a5_sc024_ontology_never_gates_…` plus the §97 mutation. *(FR-074, `INV-003`)*
- **SC-025**: `Mention`, `TypeHypothesis`, `TypeAssertion` and `Entity` are four distinct Python
  types, `TypeHypothesis` is not a subclass or alias of any of the others, no producer mints an
  `entity_ref`, and no corpus row asserts that two mentions are one entity. Test:
  `test_a5_sc025_…`. *(`INV-001`, FR-019)*
- **SC-026**: The §82 entity-type corpus runs green with every one of the **7 §8 extraction
  families** covered — person, organization, URL/domain/WebSite/WebPage, profile-URL/handle,
  the six indicator families, the seven document detectors, and the event words — and every
  coverage row is cited by the test that asserts it. Test: `test_a5_sc026_…`. *(FR-030, §8, §82)*
- **SC-027**: The type pipeline executes `Observation → Mention → TypeSignal → TypeHypothesis →
  SemanticRegime interpretation → TypeAssertion` in that order with every stage exposing its
  product, and a re-read after a later `INFERRED` promotion shows **all** prior states still
  present. Test: `test_a5_sc027_…`. *(FR-037, FR-111)*
- **SC-028**: The type pipeline consumes the eight §77 context inputs *by reference only*, each
  naming the bounded neighbourhood it read, and produces **zero** claims from any of them; the
  `iPhone/MacBook/iOS` vs `red apple/fruit/nutrition` example yields a *strengthened* competing
  hypothesis set, not a single chosen type. Test: `test_a5_sc028_…`. *(FR-039, FR-112)*
- **SC-029**: Two regimes over one signature yield **one** candidate carrying alternatives with
  nothing overwritten; two differing signatures yield two candidates; and a structural
  disagreement over one participant configuration is reported as
  `assembly_state = CONFLICTING` with both readings kept, never as a `candidate_status`.
  *(FR-028, FR-090)*
- **SC-030**: `Candidate` exists before `ClaimMaterial`, which exists before `Validation`, which
  exists before `Admission`, which exists before `RelationClaim` — asserted by four ordered
  timestamps in one run, not by four separate tests. *(FR-056, FR-057, FR-092)*
- **SC-031**: No `GraphEdge`/`HyperEdge` exists for a non-claim; the bridge has no overload; §99's
  producer-constructs-`GraphEdge` mutation fails. *(`INV-004`, FR-020)*
- **SC-032**: `RelationSignal` and `RelationCandidate` each have a working `write` / `get` /
  `by_tenant` / `by_logical_id` round trip against a real (in-memory or live) seam, and a stored
  `participants` row round-trips to an identical in-memory variadic object. *(FR-008, FR-059,
  FR-060, FR-087)*
- **SC-033**: An entity→value relation is distinguishable from entity→entity in both the claim and
  the projection; `Person → email → EmailAddress` never becomes a normal entity edge. *(FR-066)*
- **SC-034**: Write claims → project → rebuild via `RebuildableGraphStore` → compare, over
  `InMemoryGraphStore`, with zero equality. *(FR-068)*
- **SC-035**: Removing producer order, the clock, randomness and dict iteration order
  **individually** leaves every signal, candidate, material, claim and edge id identical.
  *(FR-073, FR-085)*
- **SC-036**: §72's all-mentions × all-mentions mutation fails its named test in every extraction
  path. *(FR-072)*
- **SC-037**: Every signal states a neighbourhood class from §46's 11-item list, and the class is
  a typed field, not a substring in a `precision` string. *(FR-071)*
- **SC-038**: `max_pairs_considered` is a live ceiling that a real violation exceeds, and all five
  §47 metrics are reported by every producer. *(FR-072, FR-093)*
- **SC-039**: Every field named in FR-010 is present and typed; zero load-bearing dimensions are
  JSONB; `extra` carries only producer-specific metadata and never the participants or the arity.
  *(FR-008, FR-010, FR-089)*
- **SC-040**: Every channel in FR-040's list is either implemented or carries an explicit
  `UNSUPPORTED` marker with a reason; `SignalKind` contains no aspect-named member, and
  `TEMPORAL` **is** present as a channel while the temporal facts themselves live in
  `SourceTemporalObservation` and in `temporal_evidence`. *(FR-011, FR-012, FR-040, FR-051)*
- **SC-041**: `polarity` is a required field and a durable column on both `relation_signal` and
  `relation_candidate`; a denied acquisition yields a `DENIED` candidate with its signature
  intact and **zero** positive candidates. *(FR-015, FR-088)*
- **SC-042**: A `PredicateSignature` exists, is content-keyed, is not a `RelationRef`, and is
  stored in its own columns rather than as a digest; `normalize_voice()` maps
  `Company acquired Asset` and `Asset was acquired by Company` to the same canonical argument
  assignment, and an unsupported construction yields `UNSUPPORTED_CONSTRUCTION` rather than a
  guessed frame. *(FR-003, FR-087)*
- **SC-043**: Changing `relation_surface` alone changes `candidate_id` and **not**
  `logical_candidate_id`; changing a producer, a capture or a confidence changes neither; and
  `RelationCandidate.relation_ref` always equals the hypothesis's, so the two can never
  disagree. *(FR-001, FR-002, FR-021)*

### Constitutional non-goals

- The platform MUST NOT require that every relation be one of a finite operator list before
  preserving it. (§1, §65)
- The platform MUST NOT make schema.org, Wikidata, DBpedia or GeoNames the canonical internal
  world model. They are external semantic sources and mapping targets. (§2, §105)
- The platform MUST NOT create a fourth epistemic level between signal and claim. (§103)
- The platform MUST NOT make RDF the internal model, and MUST NOT depend on draft-only SHACL 1.2
  behaviour; RDF-compatible shape and an optional SHACL sidecar are permitted. (§80, §81)
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
