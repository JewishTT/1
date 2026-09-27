# Feature Specification: Universal Relation Extraction

**Feature Branch**: `019-universal-relation-extraction`

**Created**: 2026-09-27

**Status**: Draft

**Input**: User description: "Do not build a system that knows in advance which relations exist. Build a system that can answer: what relational structure was observed, which participants took part, what surface or structural signal produced the link, which interpretations of that signal are possible, which entities correspond to the participants, which temporal semantics are possible, which evidence supports each interpretation, which semantic regime considers it, what passed validation, and what was admitted into the world projection — and which may be *stopped at* without losing information. This is not ontology-first; it is a process-centric evidence substrate where relations are stable relational invariants emerging from observation flows."

**Verified against `HEAD 81d8107`, not inherited from any prior report.** Every defect below was confirmed by reading the code. Where a defect required a more fundamental contract change than a local fix, it was recorded and then resolved as a **constitutional decision** below rather than papered over with a workaround.

## Problem Statement

The platform now has an executable thirteen-stage path and a durable substrate underneath it. What it does **not** have is a way to discover a relation that nobody anticipated. Six confirmed defects:

**D1 — The executable path still uses the fused, deprecated lifecycle.** `apps/control-plane/semantic_path/execution.py:2707` reads:

```python
supported = proposed.with_status(CandidateStatus.SUPPORTED)
```

and `:2747` then calls `step.supported.to_claim(...)`. So the running path is `candidate → with_status(SUPPORTED) → to_claim() → validation`, not `build → validate → admit`. `SUPPORTED` is a flag flipped by the orchestrator, not a finding from an assessment — which means the validator can never examine a hypothesis that extraction was unsure about, because the flag was already set. `RelationCandidateSet.supported` (`apps/shared/domain/relation_candidate.py:1423`) filters on the same flag, so the concept is load-bearing in the public API.

**D2 — `RelationCandidate` has no durable substrate.** Confirmed: no migration creates any `relation_candidate` table. The generic `candidates` table (`apps/control-plane/db/schema.py`) carries `candidate_id VARCHAR(36)`, `mention_ids JSONB`, `surface_form`, `normalized_form`, `type_hypothesis VARCHAR(32)`, `state`, `epistemic_status`. It has no logical/revision split, no `relation_ref`, no role assignments, no trigger or supporting spans, no temporal hypothesis, no extraction method/version/rule, no regime reference. It also **cannot hold the id**: `CAND-`/`CNDR-` are 5+32 = 37 characters against a `VARCHAR(36)` column. So the platform cannot answer *"which relation hypotheses did the system produce?"* — only *"which claims did it materialise?"* For a substrate that must survive without claims, that is the wrong record.

**D3 — Evidence lineage and derivation lineage are two different chains in one unmarked vocabulary.** `apps/shared/domain/evidence_lineage.py`:

```text
BACKWARD_CHAIN = RELATION → ASSERTION → MENTION → SEGMENT → OBSERVATION → CAPTURE → SOURCE
FORWARD_CHAIN  = SOURCE → CAPTURE → OBSERVATION → SEGMENT → MENTION → CANDIDATE → ASSERTION → RELATION → ENTITY
```

`CANDIDATE` appears in the forward chain and not the backward one, and nothing marks which chain is *evidence* and which is *derivation*. Source, observation, capture and segment are evidence substrate; candidate, resolution and type assertion are derived interpretations. A candidate is not evidence, and a future contextual reconstruction that treated the two chains as one would be reading an interpretation as though it were a source.

**D4 — The acquisition temporal envelope drops the source's own temporal facts.** `Capture` has `fetched_at` and `time_basis` and **no `published_at`** (confirmed field list). `EdgarFullIndexAdapter` declares `published_at` as `supplied=True, source_field="date filed"`, then constructs:

```python
fetched_at=None,
time_basis=CaptureTimeBasis.PUBLICATION,
```

The registrar's acceptance instant — the single temporal fact EDGAR actually supplies — is recorded **nowhere**. It appears in the axis report and is then annihilated. `Capture` correctly refuses to be an acquisition-plus-source-temporal container, and the source-side facts have no other home.

**D5 — Relation extraction is a cue table.** `apps/interpretation/extractors/relations.py` implements a genuine relation-first reader (cue → participants → candidate), and it works: `Acme` is found in `"CEO of Acme"` with no legal-form suffix because the cue affords an organisation. But `RELATION_CUES` is the only producer, and its presence is a *precondition* for any relation being found at all. There is no `RelationSignal`, no signal registry, no assembler, no syntactic/structural/link/table/metadata producer (confirmed absent). A sentence with no known cue yields mentions and no relation — which is correct as far as it goes and wrong as a stopping point, because the structure is still there.

**D6 — A relation must be able to have an unknown type, and today it cannot.** The current path always sets `relation_ref` from the cue row's known operator. There is no representation of "a relation was observed and we do not know what kind it is" — so the one thing this platform exists to preserve is the thing it cannot express.

## Scope Guard — what this feature is NOT

Recorded because each is a way this work has previously gone wrong:

- NOT a global ontology. NOT a relation-type registry as a mandatory reference of the world.
- NOT `extractor → GraphEdge`. `GraphEdge` is a projection of admitted world state and exists nowhere near an extractor.
- NOT `ontology miss → drop relation`.
- NOT one mention = one entity, anywhere. Extraction is mention-level; resolution is separate.
- NOT `SUPPORTED` as a technical flag in front of a claim.
- NOT all mentions × all mentions. Bounded neighbourhoods, then hard blocking.
- NOT 500 relation-specific branches in one extractor.
- NOT a generic `related_to` edge standing in for co-occurrence.
- NOT a context engine inside a relation extractor.
- NOT a new abstraction layer for terminological tidiness. Every new object must answer a separate question the system cannot currently answer.

The one-line test: *the system can stop at "we saw a structural signal" without pretending to know the relation type, the entities, or whether the claim is admissible — and losing nothing.*

## Terms

**RelationSignal** — an observable structural reason to hypothesize that a particular relational configuration holds between some mentions. Not a candidate, not a claim, not an edge.

**RelationHypothesis** — one candidate interpretation of one or more signals. Competing hypotheses are retained, not collapsed.

**Evidence lineage** — the chain from an admitted claim back to bytes and source: relation → assertion → mention → segment → observation → capture → source.

**Derivation lineage** — the chain of *interpretations* that produced a claim: observation → mention → signal → hypothesis → candidate → material → claim → edge.

**Acquisition fact vs source temporal fact** — a `Capture` records that the platform obtained bytes. A source-declared temporal fact records what time the source itself stated. They are different objects and neither substitutes for the other.

## User Scenarios

### US1 — A relation is examined before it is admitted (P0)
A candidate is built into material. The validator examines the material and returns a graded report. Admission decides. The orchestrator never flips a status flag to make the chain work; if a reader cannot tell from the trace whether something was admitted, that is a defect in the trace.

### US2 — A hypothesis outlives the absence of a claim (P0)
A system is queried about a document in which nothing was ever admitted. It can still list every relation hypothesis produced, with the signals that produced each, the regime that interpreted it, the participants, the temporal guess and the evidence. "Nothing was admitted" and "nothing was observed" are distinguishable.

### US3 — A relation nobody declared survives (P0)
A signal is observed whose predicate surface is `originator of` and which no vocabulary, profile or operator declares. The raw relational structure is preserved with its surface, its participants and its evidence, and its semantic status is `unknown`. It is not discarded, and it is not given an invented relation type.

### US4 — A hyperlink is a signal, not a guess (P0)
A page links to another. The extractor emits a `LINK` signal asserting an observable structural relation between the two documents. It does not decide whether that means `cites`, `references`, `hosts` or `mentions`.

### US5 — A table cell is a signal (P0)
A two-column table `Company | CEO` with a row `Acme | John Smith` produces a `TABLE` signal with `relation_surface="CEO"`. The extractor does not know that `CEO` implies `works_for`, and is not required to.

### US6 — Metadata relations use the same contract (P0)
An author, a publisher, a parent document, a URL path segment, a reply-to header. All reach the same downstream contract as a textual relation. There is no separate world of metadata edges.

### US7 — One event, one n-ary hypothesis (P0)
"John sold Acme to Foo in 2020" produces an event-shaped hypothesis with three participants and a temporal reading. It is not cut into three binary relations by force, and temporal remains orthogonal to arity.

### US8 — Competing interpretations coexist (P0)
A text says one thing and a table says another about the same participants. Both signals are recorded, both hypotheses exist, and neither overwrites the other. The disagreement is itself a storable fact.

### US9 — A value need not be an entity (P0)
`John — email — x@example.com`. The extractor reports an attribute signal. Whether the value is a literal, an identifier, an unresolved entity or an external entity is a later decision.

### US10 — Bounded, not quadratic (P0)
A document with ten thousand mentions does not produce fifty million candidate pairs. Every signal is justified by a named, bounded neighbourhood, and the corpus reports the bounds.

### US11 — Stopping early loses nothing (P0)
An operator can stop at "we saw a structural signal", at "we produced a hypothesis", at "we resolved participants", or at "we admitted a claim", and read everything known at that level without reading the levels below.

## Functional Requirements

### A. Lifecycle (P0)

- **FR-001 (P0)** — The executable path MUST traverse `build → validate → admit`. `with_status(CandidateStatus.SUPPORTED)` MUST NOT appear in the production execution path.
- **FR-002 (P0)** — `SUPPORTED` MUST NOT gate `to_claim()` and MUST NOT be a required lifecycle stage. See CD-1.
- **FR-003 (P0)** — The extraction layer MUST NOT be able to produce an admissible candidate status by construction.
- **FR-004 (P0)** — Deprecated fused entry points MAY remain for legacy callers only, MUST be marked as such, and MUST NOT be on the production path. `RelationCandidateSet.supported` becomes a compatibility projection, not a lifecycle gate.
- **FR-005 (P0)** — The validator MUST be able to examine a material whose extraction was unconfident, and admission MUST be the only step that commits a claim.

### B. Candidate durability (P0)

- **FR-006 (P0)** — A durable substrate MUST persist relation hypotheses independently of claims, with `logical_candidate_id` (`CAND-`) and `candidate_id` (`CNDR-`), plus every field needed to reconstruct the hypothesis.
- **FR-007 (P0)** — Persistence MUST answer "which relation hypotheses did the system produce?", including never-admitted and contradicted ones.
- **FR-008 (P0)** — Append-only: a superseding hypothesis MUST NOT overwrite what it supersedes. Ambiguous and rejected hypotheses persist like any other.
- **FR-009 (P0)** — The generic `candidates` table MUST NOT be treated as this substrate. The `VARCHAR(36)` width MUST change per CD-3.
- **FR-010 (P0)** — All new records tenant-scoped and fail-closed (constitution IV).

### C. Lineage separation (P0)

- **FR-011 (P0)** — Evidence lineage and derivation lineage MUST be distinguishable in the model, not by convention. See CD-4.
- **FR-012 (P0)** — `CANDIDATE` MUST NOT be added to the evidence chain for symmetry.
- **FR-013 (P0)** — A reader MUST be able to ask for either chain of one claim and get two different, correct answers.
- **FR-014 (P0)** — `forward()` MUST keep its documented behaviour for existing callers; the change is that it stops pretending to be an evidence traversal. A new `trace()` returns both dimensions.

### D. Acquisition temporal envelope (P0)

- **FR-015 (P0)** — A `Capture` MUST remain an acquisition fact and MUST NOT be widened to hold source-declared temporal facts.
- **FR-016 (P0)** — Source-declared temporal facts MUST have their own durable representation, linked to the capture without being absorbed by it. See CD-5.
- **FR-017 (P0)** — No new temporal axis may be introduced. The six existing axes are fixed centrally (FR-006 of 018).
- **FR-018 (P0)** — EDGAR's registrar acceptance instant MUST be retained and queryable. Its current loss MUST be observable as a defect if reintroduced.

### E. RelationSignal primitive (P0)

- **FR-019 (P0)** — A `RelationSignal` value MUST exist, carrying at minimum: signal id, signal kind, context ref, subject and object mention refs, participant refs, role hypotheses, relation surface, predicate surface, normalized predicate, relation ref *or* absence, direction hypothesis, arity hypothesis, trigger span, supporting spans, temporal evidence, observation refs, evidence refs, extractor id and version, extraction rule id, and confidence.
- **FR-020 (P0)** — A signal MUST NOT be a candidate, a claim or an edge, and the type MUST make that structurally evident rather than by naming.
- **FR-021 (P0)** — Signal kinds MUST be a fixed, extensible vocabulary covering at minimum lexical, syntactic, structural, metadata, link, reference, table, list, event, temporal, attribute, co-occurrence and semantic. Not every kind MUST be implemented; the architecture MUST let each attach identically.
- **FR-022 (P0)** — A `RelationSignalExtractor` protocol MUST exist with a single extraction contract returning signals, so producers compose rather than fork.
- **FR-023 (P0)** — The existing cue reader MUST become one lexical producer behind that protocol, not a precondition for a relation being found.
- **FR-024 (P0)** — A signal with no known relation type MUST be constructible and MUST survive to a hypothesis without being dropped. See CD-6.
- **FR-025 (P0)** — Every signal MUST be mention-level. No producer may require, infer or emit an entity id.

### F. Signal producers (P0)

- **FR-026 (P0)** — At least one producer beyond the lexical cue reader MUST exist, covering structural/link/table/metadata evidence, chosen so the shared contract is exercised by structurally different input rather than a second sentence template.
- **FR-027 (P0)** — A link or reference MUST produce an observable structural signal and MUST NOT assert `cites`/`references`/`hosts` from nothing.
- **FR-028 (P0)** — A table or list structure MUST produce a signal carrying the surface relation, without the producer knowing a semantic relation type.
- **FR-029 (P0)** — Metadata relations MUST reach the same contract as textual relations.
- **FR-030 (P0)** — An event-shaped reading MUST be representable as an n-ary hypothesis and MUST NOT be forced into binary relations.
- **FR-031 (P0)** — An attribute or value signal MUST be representable without asserting the value is an entity.

### G. Hypothesis assembly (P0)

- **FR-032 (P0)** — A `RelationSignalAssembler` MUST turn one or more signals into zero or more `RelationCandidate` values, preserving each signal's origin.
- **FR-033 (P0)** — Multiple signals describing one configuration MUST aggregate into one hypothesis rather than N independent ones, and aggregation MUST NOT discard any signal.
- **FR-034 (P0)** — Conflicting signals MUST produce competing hypotheses, all persisted. A signal MUST NOT overwrite another.
- **FR-035 (P0)** — Extractor confidence MUST remain confidence, never truth, and MUST NOT be promoted to a verdict in assembly.
- **FR-036 (P0)** — Assembly MUST NOT create claims, resolve entities, or project edges.

### H. Candidate identity (P0)

- **FR-037 (P0)** — Two identity levels only: `CAND-` logical, `CNDR-` revision. No third hierarchy without stated necessity.
- **FR-038 (P0)** — A change of extractor, regime, temporal hypothesis or evidence MUST NOT break logical identity without cause, and each MUST be visible on the revision.
- **FR-039 (P0)** — A different interpretation, structural shape, participant set or relation configuration MUST NOT collapse into one candidate revision.
- **FR-040 (P0)** — Surface grammatical form MUST NOT determine relation hypothesis identity. Active and passive realisations of one relation MUST be able to yield the same logical hypothesis with distinguishable surface evidence.

### I. Boundedness (P0)

- **FR-041 (P0)** — Relation generation MUST be bounded by named, deterministic neighbourhoods. Document-wide pairwise generation is forbidden.
- **FR-042 (P0)** — Minimum bound set: segment-local, sentence-local, document structural, dependency, DOM/table, metadata-local, event-participant.
- **FR-043 (P0)** — Every signal MUST record the neighbourhood that produced it, so a bound is auditable rather than asserted.
- **FR-044 (P0)** — Order is generate wide within bounds, then block hard, then resolve, then validate. Cost must be reported, not assumed.
- **FR-045 (P0)** — Co-occurrence MUST NOT become a blanket `related_to` edge.

### J. Boundaries (P0)

- **FR-046 (P0)** — No producer may create a `GraphEdge` or a `RelationClaim`. The projection boundary is machine-checkable.
- **FR-047 (P0)** — A relation-discovery or expansion hypothesis MUST NOT live inside relation extraction. It is a distinct future object.
- **FR-048 (P0)** — The semantic registry MAY supply possible relation types, role hints, inverse hints, domain/range hints, aliases, mapping candidates, query expansion and blocking keys. It MUST NOT decide the best relation, the best entity, truth, or canonical reality, and MUST NOT be a gate.

### K. Determinism and replay (P0)

- **FR-049 (P0)** — Two independent processes over identical input MUST produce identical signal ids, candidate ids, material identities and claim identities.
- **FR-050 (P0)** — `run → record log → replay → replay of replay` MUST be byte-identical.
- **FR-051 (P0)** — No signal, candidate or hypothesis may depend on a wall clock, a random source or dictionary iteration order.
- **FR-052 (P0)** — **Semantic incompleteness MUST NOT reduce structural observability.** Where the relation type is unknown, the hypothesis MUST still retain both participants, their roles, the direction hypothesis, the trigger or path, the structural context, the source, the observation, temporal clues, the signal provenance, and every alternative interpretation. See CD-7.

## Data Requirements

- `relation_candidate` (FR-006, CD-2) — `candidate_id` (`CNDR-`) PK, `logical_candidate_id` (`CAND-`), `tenant_id`, `investigation_id`, `subject_mention_ref`, `object_mention_ref`, `relation_ref` **nullable**, `relation_surface`, `predicate_surface`, `predicate_hypothesis` JSONB, `arity_mode`, `role_assignments` JSONB, `context_ref`, `semantic_regime_ref`, `trigger_span` JSONB, `supporting_spans` JSONB, `observation_refs` JSONB, `evidence_refs` JSONB, `temporal_hypothesis` JSONB, `extraction_method`, `extractor_version`, `extraction_rule_id`, `candidate_status`, `confidence`, `signal_ids` JSONB, `supersedes`, `observed_at`, `recorded_by`, `created_at`, `record_fingerprint`. Append-only; wall clocks excluded from every address.
- `relation_signal` (FR-019) — `signal_id` PK, `tenant_id`, `signal_kind`, `context_ref`, `observation_refs` JSONB, participant refs, `relation_surface`, `predicate_surface`, `normalized_predicate`, `relation_ref` **nullable**, `direction_hypothesis`, `arity_hypothesis`, `trigger_span` JSONB, `supporting_spans` JSONB, `temporal_evidence` JSONB, `evidence_refs` JSONB, `extractor_id`, `extractor_version`, `extraction_rule_id`, `confidence`, `neighbourhood`, `created_at`, `record_fingerprint`.
- `source_temporal_observation` (FR-016, CD-5) — `observation_id` PK, `tenant_id`, `source_ref`, `capture_ref`, `temporal_axis`, `stated_value`, `precision`, `basis` (`source_declared` / `derived` / `absent`), `evidence_location`, `recorded_at`, `schema_version`.
- Id column widths (CD-3) — durable id columns for this class at least `VARCHAR(64)`; the migration sweeps every reference, not only the overflowing one.
- `relation_candidate_revision` — only if the single append-only table cannot preserve the logical/revision distinction; CD-2 prefers one table and the choice must be argued.
- Existing `candidates` table: left alone with a comment saying it is not the relation-hypothesis substrate, and widened per CD-3. It MUST NOT be silently relied upon.

## Out of Scope

- A context engine, and any of `TaskSpec` / `TaskPlan` / `Obligations` / `ContextFrontier` / `ContextDecision` / `ContextSnapshot`. This feature must *enable* it by preserving unresolved and competing objects, not anticipate it.
- `ExpansionCandidate` / `SearchHypothesis` / `TraversalOpportunity` as concrete objects (FR-047 fixes the boundary; the object belongs to the context feature).
- New semantic adapters, ontology packs, vocabulary backends or UI.
- Neural or LLM extraction. Deterministic only.
- Resolving mentions to entities as part of extraction.

## Constitutional decisions (fixed 2026-09-27)

These are **not** open questions. Each is a change to a contract, decided because the
architecture's own philosophy forces it. They are recorded so implementation cannot quietly
undo them, and so a later reader knows which parts of 016 are deliberately gone.

### CD-1 — `SUPPORTED` leaves the candidate's semantic lifecycle

`CandidateStatus.SUPPORTED` MUST NOT gate `to_claim()` and MUST NOT be a required lifecycle
stage. The order is fixed:

```text
Candidate → ClaimMaterial → Validation → Admission → RelationClaim
```

not

```text
Candidate → SUPPORTED → to_claim() → RelationClaim → Validation
```

The second is fundamentally wrong: it turns a hypothesis into an assertion and *then* asks
whether it passed. `RelationCandidateSet.supported` is removed from the lifecycle API. Where a
legacy caller still reads it, it is retained as a **compatibility projection** computed by a
separate assessment, never as an input to an admission guard. `if status != SUPPORTED: raise`
is forbidden anywhere.

### CD-2 — Durable candidate substrate, two-level identity

A durable substrate is introduced with the same philosophy `RelationClaim` already has. One
naming correction, because the two are easy to swap and the swap silently inverts meaning:

```text
logical_candidate_id = CAND-…    which hypothesis this is
candidate_id         = CNDR-…    this concrete reading of it
```

A candidate is not a transient DTO. Without it, replay can reconstruct a claim and its
observation but loses *which interpretation* produced it — including the alternatives and the
rejected ones. That is precisely what this platform exists to keep.

### CD-3 — Durable id columns are sized for a class, not for today's encoding

`candidates.candidate_id VARCHAR(36)` cannot hold a 37-character `CNDR-` id, and
`VARCHAR(36)` is the wrong lesson rather than the wrong number. The governing principle:

> The schema must not know the length of a particular hash or id encoding precisely enough
> that a new identity form breaks persistence.

Durable id columns of the relevant class go to at least `VARCHAR(64)`, and the migration MUST
sweep every reference — other tables' `candidate_id` columns, foreign keys, indexes, unique
constraints, revision references — not just the one that overflows.

### CD-4 — Evidence lineage and derivation lineage are two different things

`CANDIDATE` is **not** added to the evidence chain. The split is made explicit:

```text
EVIDENCE_BACKWARD_CHAIN   relation → assertion → mention → segment → observation → capture → source
DERIVATION_FORWARD_CHAIN  observation → mention → signal → hypothesis → candidate → material → claim → edge
```

"Forward" is derivation, not the opposite of evidence, and the old naming conflated them.
`forward()` is **preserved** as the derivation-compatible API for existing callers; what
changes is that it stops pretending to be an evidence traversal. A new `trace()` returns both
dimensions for one artefact, so the question "why does this edge exist?" gets two answers:

```text
Derivation: observation → signal → candidate → claim → edge
Evidence:   edge → claim → mention → segment → observation → capture → source
```

### CD-5 — `SourceTemporalObservation` is its own durable object

`Capture` is not widened. A source-declared temporal fact and a platform acquisition event
have different semantics and must not share a container:

```text
Capture                    = when the platform obtained the bytes
SourceTemporalObservation  = what time the source itself stated
```

with `capture_ref` linking them without making the observation part of the capture. This makes
`known_when`, `captured_when`, `published_when`, `valid_when` and `observed_when` separately
answerable, and it is the same orthogonality the six fixed axes already assert.

### CD-6 — `RelationRef` is optional at the hypothesis layer, required from material onward

The registry sentinel `UNKNOWN_RELATION` is **rejected**: minting an ontology concept for "we
do not know" turns unknown semantics into known vocabulary, which is the exact inversion this
platform was built to prevent.

The contract is split by epistemic status:

| layer | `relation_ref` |
|---|---|
| `RelationSignal` | absent — a signal is structure, not semantics |
| `RelationHypothesis` | absent, one ref, or **several** competing refs |
| `RelationCandidate` | optional, via `PredicateHypothesis` |
| `RelationClaimMaterial` | **required** |
| `RelationClaim` | **required** |

A nullable field alone is not enough, so a `PredicateHypothesis` value carries
`surface_form`, `normalized_form`, `relation_ref`, `alternative_refs`, `resolution_state`
(known / unknown / ambiguous / conflicting) and `mapping_evidence_refs`. Four kinds of
hypothesis are then durably representable and lossy in none of them:

```text
known       "works for"                    → relation_ref = employment
unknown     "has commercial arrangement"   → relation_ref = None
ambiguous   "associated with"              → relation_ref ∈ {ownership, affiliation, partnership}
conflicting signal A → ownership, signal B → control
```

`RelationClaim.relation_ref is None` being impossible is not a weakness of the type system.
It is the boundary between an open-world hypothesis substrate and an admitted semantic
assertion, and it is where the two are supposed to meet.

### CD-7 — Semantic incompleteness MUST NOT reduce structural observability

Stronger than "an unknown relation must be preserved". If the system does not know what
`A ──?──> B` means, it must still retain everything that *was* observed:

```text
A, B · role of A · role of B · direction · trigger or path · structural context
source · observation · temporal clues · signal provenance · alternative interpretations
```

Loss of semantics MUST NOT mean loss of relational structure. This is the load-bearing
statement underneath universal extraction, and it is what makes "we saw a structural signal"
a legitimate stopping point rather than a gap.

## Success Criteria

- **SC-A (lifecycle)** — `candidate → material → validation → admission → claim` is the path the executor runs, and `with_status(SUPPORTED)` appears nowhere in it (FR-001…FR-005).
- **SC-B (durability)** — A candidate with no claim survives; `CAND-`, `CNDR-`, context, regime, evidence, temporal hypothesis and signals are recoverable from persistence (FR-006…FR-010).
- **SC-C (universality)** — One downstream contract accepts signals from lexical and at least one structurally different producer, with no separate graph model per kind (FR-019…FR-031).
- **SC-D (unknown preservation)** — A relation whose type no vocabulary declares survives to a hypothesis with its surface intact and no invented type (FR-024).
- **SC-E (alternatives)** — Two competing interpretations of one participant pair both persist and neither is overwritten (FR-033, FR-034).
- **SC-F (mention/entity separation)** — No producer requires or emits an entity id; a structural producer over mentions with no entity table at all still produces signals (FR-025).
- **SC-G (projection boundary)** — Machine-checkably, no extractor emits a `GraphEdge` or a `RelationClaim` (FR-046).
- **SC-H (determinism)** — Two independent processes yield identical signal ids, candidate ids, material identities and claim identities (FR-049).
- **SC-I (replay)** — `run → log → replay → replay of replay` is byte-identical (FR-050).
- **SC-J (boundedness)** — No document-wide pairwise generation; every signal names the bounded neighbourhood that produced it, and the real bounds and blocking reduction are reported (FR-041…FR-045).
- **SC-K (lineage)** — Evidence chain and derivation chain are separately queryable and separately correct for one claim (FR-011…FR-014).
- **SC-L (acquisition envelope)** — EDGAR's registrar acceptance instant is retained and queryable, and `Capture` remains an acquisition fact (FR-015…FR-018).
- **SC-M (non-regression)** — projection `189 passed, 1 skipped`; acquisition `126 passed, 10 skipped`; interpretation `185 passed`; admission `96 passed`; control-plane `332 passed, 2 failed` (the 2 pre-existing `test_donor_api`), 9 skipped; shared's 14 known failures unchanged; corpus `18 cases, 10 worldline, 8 named refusals, 0 committed differences, 5 layers identical, replay fixed point.
- **SC-N (structural observability, CD-7)** — For a relation whose type no vocabulary declares, every structural fact in FR-052 is recoverable from the candidate. What was lost is the type name, which was never known.
- **SC-O (gate: CD-6)** — `RelationCandidate.relation_ref is None` is constructible and `RelationClaim.relation_ref is None` is impossible. Both demonstrated, not asserted.

## Constitutional tests

Small and invariant-only. They exist to stop a regression physically, not to chase coverage:

- a candidate survives without a claim
- material is validatable before admission
- a candidate does not become admissible merely because execution reached the claim stage
- an unknown relation survives
- no producer emits a `GraphEdge` or a `RelationClaim`
- mention refs are not entity refs
- identical signals yield identical identity
- different signals stay distinguishable
- two independent source signals are not one publication count

## Constitution Check

| Principle | Status |
|---|---|
| I — evidence before entity | PASS: signals and hypotheses are evidence-bearing; a derived interpretation is never recorded as evidence (FR-011, FR-012). |
| II — no second backbone | PASS: new substrate is rows in the existing store; no new service. |
| III — no auth/CAPTCHA circumvention | PASS: producers read lawfully fetched content and metadata. |
| IV — tenant isolation fail-closed | PASS: every new record tenant-scoped; cross-tenant refusal preserved. |
| V — one time model | PASS: the six axes are fixed centrally; a new axis is forbidden (FR-017); CD-5 keeps source-declared time as a *fact about a source*, not a seventh axis. |
| VI — LLM-free determinism | PASS: no generation; bounded neighbourhoods are named and deterministic. |
| VII — event-sourced rebuild | PASS: signals and hypotheses are recorded, so replay can reproduce them (FR-050). |
| VIII — bounded resources | PASS: FR-041…FR-045 replace pairwise generation with bounded neighbourhoods and hard blocking. |

**Gate**: CD-6 / FR-024 / SC-O. If `RelationCandidate.relation_ref is None` is not constructible, the central invariant is not met and nothing built on the signal substrate is sound. This decision is now fixed, so the gate is a build obligation rather than an open question.

## Remaining open questions

Narrowed to what the decisions genuinely left open. None blocks BUILD.

1. Which structurally different producer lands first — link, table, or metadata? All are acceptable; picking one is a judgement about what most usefully exercises the shared contract first.
2. Do signals persist in their own table before candidates (two writes), or is the candidate the durable record with signals materialised into it? CD-2 implies the former; the write cost is the trade-off.
3. May assembly emit a hypothesis with *no* signals — a structural shape the producers found but could not yet signal, as in a table whose cells have not parsed? A signal is currently the unit of observability, and this asks whether shape-without-content is admissible.
