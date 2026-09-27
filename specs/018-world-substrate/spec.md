# Feature Specification: World Substrate Closure

**Feature Branch**: `018-world-substrate`

**Created**: 2026-09-27

**Status**: Draft

**Input**: User description: "Resolution *logic* is closed; resolution *lifecycle and provenance* are not. Before any Context Engine, close four P0s: durable resolution anchor (a resolver may be stateless, but state must be durable identity), Capture + acquisition lineage with the temporal axes kept separate, a real build/validate/admit split so a validator examines a hypothesis rather than an already-admitted claim, and an actually-executed SemanticRegime instead of a permanent UNEVALUATED. Then P1: a relation-aware extractor and a committed deterministic corpus with replay and benchmark. Contextual modeling is out of scope and must not start until the substrate can reconstruct, for any entity and any relation, exactly why it was accepted."

## Decisions taken (2026-09-27)

Three open questions were answered before planning, and all three changed this specification.

**D-A — `entity_identity` is a separate table, shaped for the layers above.** Optimising for the efficiency of everything computed downstream is the governing constraint. Bolt-on columns on `entities` would allow a partial write leaving an entity with no anchor, and the next layer up would read that as a valid entity. A separate table buys three things at once: the anchor can be write-once by construction, `entities.entity_type` stays a projection instead of becoming a second truth, and the table can carry exactly the two indexes the layers above actually read — anchor-by-mention, which is the hot path during resolution, and history-by-entity, which is the hot path during reconstruction. Read-path shaping decides the schema here, not entity tidiness.

**D-B — Absent fetch time is a named basis, not a null.** Where a source genuinely carries no fetch time — a crawl index carries the *index* timestamp, which answers a different question — `Capture` records a `CaptureTimeBasis` naming where the timestamp came from. A nullable column would leave `fetched_at` indistinguishable from "not yet populated", and the distinction between "we do not know" and "we have not written it" is exactly the distinction this substrate exists to keep.

**D-C — The corpus is functionality, not a test suite.** The requirement inverts: the deliverable is working code running over real input, and the corpus exists to *record* what that code produced so the recording can be compared. A suite of tests asserting that a path works is a weaker artefact than the path itself, and would re-create the exact gap D7 describes. This also settles where the corpus lives: beside the code it exercises, as data plus a runner — not in a test directory.

**D-D — Acquisition becomes stream-agnostic now, because Common Crawl is only the first module.** The global shape of data-stream temporality has to be settled before more streams are attached to it, or every module will invent its own time semantics. `Capture` is the common acquisition fact; each stream becomes a module that produces it, and the time axes are fixed once, centrally. Concrete non-API stream modules follow this feature through the seam established here, and the seam is a deliverable in its own right — a seam nobody has exercised is not a seam.

## Problem Statement

Feature 017 built the semantic fabric and 018's predecessor made it executable: a 13-stage deterministic path carries one sentence from `Observation` to a projected graph edge and a worldline event, and `Mention → Entity` resolution is a real machine rather than a stub. That part works.

What does not work is everything about **persistence, provenance and provability**. The logic is stateless and correct; the state it depends on lives only in whatever the caller happened to hold, and none of it is reconstructable. Six concrete defects:

**D1 — The resolution anchor is a caller obligation, not a durable invariant.** `MentionResolver` is stateless by design and takes its anchor from a `ResolutionScope` that the *caller* must persist:

```text
ResolutionBatch.scope  ->  anchor state
```

If a caller drops the scope, the next batch mints a new anchor and the same entity gets a new `ENT-`. Identity determinism therefore depends on external call discipline — the exact class of dependency this platform keeps trying to eliminate. The `entities` table makes it concrete: it holds `entity_id`, `entity_type`, `canonical_name` and **no anchor and no reference to any resolution that produced it**. Nothing in durable state can answer "which mention introduced this entity", and nothing prevents an anchor from silently moving.

**D2 — The resolution decision is not durable at all.** `RES-` is a content address of a decision that lives in memory for the length of one batch. `merged_mentions`, `surviving` candidates, the per-candidate compatibility reasons, the corroboration, the collective outcome and the verdict — the entire reasoning behind an identity — are unrecorded. Re-running resolution next week produces a new `RES-` with no way to tell whether it reasoned the same way or differently.

**D3 — `Capture` exists but acquisition cannot produce one.** `apps/shared/domain/capture.py` requires `fetched_at`, `content_digest` and a `target_uri`/`locator`. `apps/acquisition/cc_extract.py::CaptureObservation` supplies `url` and `digest` and a `warc_filename@offset,length` locator, but its timestamp is `observed_at` — derived from the **crawl index**, not from the fetch. There is no `fetched_at` anywhere in acquisition. So the bottom of the chain is still open:

```text
WORLD  ->  ???  ->  Observation  ->  Segment  ->  ...
```

and the orchestrator still fabricates a capture id from `(source_id, observation_id)` because it has no honest one.

**D4 — The acquisition time axis is conflated.** `Capture` is a fact of *acquisition*; `Observation` is a fact of *having observed content*. Six distinct axes exist across the codebase — `fetched_at`, `observed_at`, `published_at`, `valid_from`, `valid_to`, `known_from`/`known_until` — and `CaptureObservation.observed_at` is currently a crawl-index timestamp standing in for a fetch time. For temporal reconstruction this is not a naming preference: "when did we learn of this" and "when was it true" and "when did we fetch it" answer different questions, and a crawl index answers none of them for a given document.

**D5 — `build`, `validate` and `admit` are one operation.** `RelationCandidate.to_claim(...)` both constructs the claim and admits it, and refuses unless the candidate is already `SUPPORTED`. So the sequence in the running path is `CLAIM → VALIDATION → ADMISSION`, and `LayeredValidator` inspects an already-admitted object. "Claim" currently means a potential assertion, an immutable object and an admitted assertion at once. A validator that can only ever see admitted claims cannot examine a hypothesis, which is precisely what a task-scoped consumer will need to do later.

**D6 — The SemanticRegime is structurally present and permanently unevaluated.** `regime_id` is written in memory by `semantic_path/execution.py` and **persisted in no table** — not in `candidates`, not in `relation_claim`, not in `type_assertions`. Every compatibility check against a candidate's regime therefore returns `UNEVALUATED`, and it does so on the golden path, on every run. The semantic fabric executes structurally (objects, contracts, registry, operator, validator) while a real input is missing. This is the "no new semantic infrastructure until the existing layer actually runs" debt, and hiding it as `UNEVALUATED` was correct — the fix is to supply the input, not to stop reporting the absence.

**D7 — The relation-aware extractor is a shim, and the corpus is uncommitted.** The golden sentence only resolves because a cue-keyed org rule was added inside the orchestrator, not in the extraction package: `extractors.orgs` requires a legal-form suffix, so "CEO of Acme" yields no organisation mention at all. And nothing is committed: the 12 resolution behaviours and the determinism proofs exist only in a throwaway script under `%TEMP%`, which no CI run will ever execute.

## Scope Guard — what this feature is NOT

- **NOT contextual modelling.** No `TaskSpec`, `TaskPlan`, `Obligations`, `ContextFrontier`, `ContextDecision` or `ContextSnapshot`. Context must consume a mature world model, not compensate for a missing one; building it now guarantees it will become a god object asked to answer "what is an object", "what is a relation" and "what is relevant" at once.
- **NOT a new resolution algorithm.** The logic is closed. This feature persists it, separates its lifecycle, and makes it replayable. No reimplementation of blocking, compatibility or collective resolution.
- **NOT a second world model.** `entities.entity_type` is a single categorical type — the model `TypeAssertion` was built to replace. It is not rewritten here, but the relationship between it and the type layers must become explicit rather than left as two disagreeing truths.
- **NOT more semantic infrastructure.** No new adapters, no new vocabularies, no new profiles. The substrate must stop growing before the stack above it starts.

The one-line test: *after this feature, any entity and any relation in the graph can be traced back to the capture that fetched the bytes, and any identity can be shown to have been decided once and not since.*

## Terms

**Entity identity vs resolution state** — `ENT-` is which entity this is, anchored to a recorded mention; `RES-` is a particular reasoning that concluded so. They are different facts with different lifetimes.

**Resolution anchor** — the mention that introduced an entity, recorded at creation and immutable thereafter. Growth of later knowledge adds decisions; it never re-elects an anchor.

**Acquisition fact vs observation fact** — a `Capture` records that bytes were fetched (with `fetched_at`); an `Observation` records that content was seen (with `observed_at`); validity (`valid_from`/`valid_to`) and knowledge (`known_from`/`known_until`) are further axes and are never substituted for one another.

**Claim material** — the candidate-plus-resolution content a validator can examine before anything is admitted. One material, three lifecycle states, three operations: `build`, `validate`, `admit`.

## User Scenarios

### US1 — An entity's identity survives a lost caller scope (P0)
A batch resolves "Acme" to a new entity. The caller crashes and never persists its `ResolutionScope`. A later batch sees another mention of Acme. The entity id is unchanged, because the anchor is read from durable state rather than from the caller's memory. The loss is a missed optimisation, not an identity change.

### US2 — Why is this entity this entity? (P0)
Given any `ENT-`, the system returns the anchor mention, the observation it came from, the capture that fetched those bytes, the source, and every resolution decision ever made about it in order — including the ones that concluded `AMBIGUOUS` and therefore named no entity. The reasoning is reconstructable, not merely the outcome.

### US3 — A resolution decision is a durable record (P0)
A `RES-` decision survives the process. Re-running resolution on identical input reproduces the same `RES-`; changing an input changes the `RES-` and the previous one remains readable. A decision is never edited, only superseded.

### US4 — The bottom of the chain closes (P0)
Given a graph edge, the lineage resolves `Edge → Claim → Candidate → TypeAssertion → Mention → Segment → Observation → Capture → Source`, and the `Capture` is a real acquisition record with a real `fetched_at`, not a derived string. Fetch time, observation time, publication time and validity are four separately readable values.

### US5 — A hypothesis is validated before it is a claim (P0)
A candidate is built into claim *material*. The validator examines the material and returns a graded report. Only then does admission decide, and only `SUPPORTED` material becomes a committed claim. A material that validates badly can still be examined, quoted and reported — it simply is not in the graph. Nothing in the validate step requires that the object already be admitted.

### US6 — The regime is real, not UNEVALUATED (P0)
A candidate carries a persisted `regime_id`, and the compatibility comparison resolves it against a stored regime rather than reporting `UNEVALUATED`. If a regime genuinely cannot be resolved, the verdict is `UNRESOLVED` for a stated reason — but that is an exceptional path with a count, not the default on every run.

### US7 — Extraction produces relations, not just entities (P1)
From "John Smith became CEO of Acme in 2020" the extraction layer yields two mentions **and** a relational reading: a trigger span covering "CEO of", a candidate whose `relation_ref` names the operator, a role assignment, and an explicit temporal hypothesis. The organisation mention exists because the relational context implies an organisation role, not because a legal-form suffix appeared. Extraction reports evidence; it does not decide admission.

### US8 — The corpus is committed (P1)
A committed corpus of cases each record the input, expected mentions, expected resolution identities, expected decisions, expected claims, expected validation verdicts, expected lineage and expected materialisation. `run(input, versions, policy) == run(input, versions, policy)`, compared across identity outputs, decision hashes, claim hashes, context references and edge materialisation — not only the final graph, because a bug can hide behind an accidentally equal graph.

### US9 — Replay reproduces the world (P1)
Replaying the recorded event log into an empty store reproduces the same graph, the same ids and the same lineage as the original run. This is the first claim the platform can make about its own determinism, and it is the precondition for any benchmark meaning anything.

## Functional Requirements

### Durable identity and resolution (FR-001…FR-005)

- **FR-001 (P0) — Durable entity identity.** An `EntityIdentity` MUST be persisted holding at least `entity_id`, `anchor_mention_id`, `anchor_observation_id` and `created_by_resolution`. The anchor MUST be written once at creation and MUST be immutable; a later resolution MUST NOT re-elect it. Identity derivation MUST NOT depend on any caller-held value.
- **FR-002 (P0) — Stateless resolver, durable state.** `MentionResolver` MUST remain stateless, and the durable substrate MUST supply its anchor. Losing caller state MUST degrade to re-reading durable state, never to minting a new identity.
- **FR-003 (P0) — Durable resolution decisions.** A `ResolutionDecisionRecord` MUST be persisted with the same fields the in-memory decision carries (verdict, surviving candidates, per-candidate compatibility reasons, corroboration, collective outcome, confidence, notes), content-addressed `RES-` as primary key, tenant-scoped. Decisions are append-only; a re-decision supersedes rather than overwrites.
- **FR-004 (P0) — Resolution is reconstructable.** Given an `ENT-`, the system MUST return the anchor, the ordered history of `RES-` decisions, the mentions merged, and the terminal verdict. Given a `RES-`, the full reasoning MUST be recoverable. Ambiguous and unresolved decisions MUST be persisted too — a decision that named no entity is still a decision.
- **FR-005 (P0) — Cross-tenant refusal.** Anchor reads, decision writes and reconstruction MUST be tenant-scoped and fail-closed. A decision from tenant A MUST NOT be readable while reconstructing tenant B's entity.

### Capture and acquisition lineage (FR-006…FR-009)

- **FR-006 (P0) — Acquisition emits a real `Capture`.** Acquisition MUST emit `fetched_at`, `content_digest` and a `target_uri`/`locator` sufficient to construct a `Capture`. Where a genuine fetch time is unavailable (a crawl index carries the index timestamp, not the fetch time), that MUST be represented as absence with a stated reason — never substituted with the index timestamp.
- **FR-007 (P0) — Time axes stay separate.** `fetched_at`, `observed_at`, `published_at`, `valid_from`, `valid_to` and `known_from` MUST each be a distinct field with a distinct meaning. NO axis may be defaulted from another. Specifically: an index timestamp MUST NOT become `fetched_at`, and `observed_at` MUST NOT become `valid_from`.
- **FR-008 (P0) — The chain is closed end to end.** `Source → Capture → Observation → Segment → Mention → Assertion → RelationCandidate → RelationClaim → GraphProjection` MUST be traversable in both directions, and the orchestrator MUST stop fabricating a capture id.
- **FR-009 (P0) — Capture is deduplicable.** The same content captured in different batches MUST share content identity while remaining distinct acquisition events. Batch identity MUST NOT be conflated with content identity.

### Claim lifecycle (FR-010…FR-013)

- **FR-010 (P0) — build / validate / admit are distinct.** The API MUST expose `build(candidate) -> material`, `validate(material, context, regime) -> ValidationReport` and `admit(material, report) -> committed claim` as separate operations. `RelationCandidate.to_claim()` MUST NOT remain the single fused operation.
- **FR-011 (P0) — The validator examines material, not a committed claim.** `LayeredValidator` MUST accept claim *material* — an unadmitted, self-consistent value carrying its own derived ids — and MUST NOT require admission status. A material that would never be admitted MUST remain validatable.
- **FR-012 (P0) — One material, three states.** There need not be three tables, but the three lifecycle states MUST be distinguishable in the API and MUST NOT share one name. "Claim" MUST NOT simultaneously mean potential assertion, immutable object and admitted assertion.
- **FR-013 (P0) — Admission is the only committing step.** Only `admit` produces a committed claim. A finding, a `MaterialisationDecision` or an operator-scoped exclusion MAY inform admission and MUST NOT itself create, delete or rewrite one.

### Real semantic regime (FR-014…FR-016)

- **FR-014 (P0) — `regime_id` is persisted.** A `semantic_regime` record MUST be stored, and every candidate, type assertion and admitted claim MUST reference it. The reference MUST be tenant-scoped.
- **FR-015 (P0) — Regime comparison resolves.** With a stored regime on both sides, the compatibility layer MUST resolve it and MUST NOT report `regime_unevaluated` on the ordinary path. An unresolvable regime MUST be a stated `UNRESOLVED` with a reason and MUST be counted, not absorbed into the default.
- **FR-016 (P0) — No silent substitution.** Where a regime cannot be resolved, the system MUST NOT substitute an empty or default regime and proceed as though it matched.

### Relation-aware extraction (FR-017…FR-019)

- **FR-017 (P1) — Extraction yields relational evidence.** The extraction package MUST be able to produce a relational reading — trigger span, supporting spans, role assignment, `relation_ref`, temporal hypothesis, extraction method — alongside mentions, from a cue-phrase context. The organisation in "CEO of Acme" MUST be recoverable because the relation implies an organisation role, not only because a legal-form suffix appeared.
- **FR-018 (P1) — The cue rule moves out of the orchestrator.** The cue-keyed organisation rule currently living in the semantic path MUST live in the extraction package. The orchestrator MUST NOT hold extraction rules.
- **FR-019 (P1) — Extraction does not admit.** Extraction reports evidence and produces a candidate; admission remains a separate decision. No extractor may mark a reading `SUPPORTED` on its own authority.

### Corpus, replay, benchmark (FR-020…FR-023)

- **FR-020 (P1) — A committed deterministic corpus.** Cases MUST be committed with expected mentions, resolution identities, decisions, claims, validation verdicts, lineage and materialisation — not left in a throwaway script.
- **FR-021 (P1) — Invariance is compared in depth.** Determinism MUST be asserted over identity outputs, decision hashes, claim hashes, context references and edge materialisation. Comparing only the final graph is insufficient, because a defect can hide behind an accidentally equal graph.
- **FR-022 (P1) — Replay reproduces the world.** Replaying the recorded event log into an empty store MUST reproduce the same graph, ids and lineage as the original run. Replay MUST be a fixed point: replaying the replay is identical.
- **FR-023 (P1) — The corpus exercises the graded paths.** Cases MUST cover at least: ambiguity, unresolvable, cross-tenant refusal, open-world unknown type, a validation finding that does not stop materialisation, non-convergent collective, temporal conflict, and independence groups reaching the claim.

### Stream-agnostic acquisition (FR-024…FR-027)

- **FR-024 (P0) — `Capture` is the single acquisition fact.** Every data stream MUST yield `Capture` records through one contract. A stream-specific representation of "we fetched something" is forbidden, because that is how each module ends up with its own idea of when the fetch happened.
- **FR-025 (P0) — A stream module declares its time basis.** A stream adapter MUST state, per record, where each timestamp came from — and MUST declare that it cannot supply a fetch time rather than substituting the nearest thing it has. Common Crawl's index timestamp is the worked example: it is honest as an *index* observation and is not a fetch time.
- **FR-026 (P0) — The time axes are fixed once, centrally.** No stream module may introduce a new temporal field or reinterpret an existing one. Adding a stream is a matter of mapping its data onto the six existing axes, not of extending the model.
- **FR-027 (P1) — The seam is exercised, not merely declared.** At least one non-Common-Crawl non-API stream MUST be attached through the shared contract in this feature, with its temporality mapped onto the same axes. A seam with one implementation is untested architecture.

## Data Requirements

- `entity_identity` — FR-001. `entity_id` PK, `tenant_id`, `anchor_mention_id`, `anchor_observation_id`, `anchor_capture_id`, `created_by_resolution`, `created_at`. Anchor columns are write-once; a constraint or guard MUST make a second write impossible rather than merely discouraged.
- `resolution_decision` — FR-003. `resolution_decision_id` PK (`RES-`), `tenant_id`, `mention_id`, `entity_ref`, `verdict`, `confidence`, `merged_mentions` JSONB, `surviving` JSONB, `reasons` JSONB, `corroboration`, `collective` JSONB, `blocking` JSONB, `supersedes`, `decided_at`. Append-only.
- `captures` — FR-006. `capture_id` PK (`CAP-`), `tenant_id`, `source_id`, `source_family`, `target_uri`, `locator`, `content_digest`, `content_length`, `media_type`, `fetched_at`, `transport`, `ingest_batch_id`, `ingest_attempt`, `recorded_by`, `capture_fingerprint`.
- `semantic_regime` — FR-014. `regime_id` PK, `tenant_id`, `context_ref`, `profile_ref`, `profile_version`, `ontology_version`, `mapping_set_id`, `mapping_set_version`, `validation_profile`, `commitment`, `instruments` JSONB, `recorded_at`.
- `ingest_batches` — FR-009. `batch_id` PK, `tenant_id`, `source_id`, `opened_at`, `closed_at`, `record_count`, `state`. Distinct from content identity by construction.
- `capture_time_basis` — FR-006/D-B. A named basis recorded on each capture (`fetch`, `index_observation`, `publication`, `derived`, `absent`) so an absent fetch time is distinguishable from an unwritten one. Carried on the capture record rather than inferred from a null.
- `data_stream` — FR-024/FR-026. The stream registry: `stream_id`, `kind`, `temporality` (how the stream expresses time), `time_axes_supplied`, `adapter_ref`. A stream that cannot state its axes is not registrable.
- Relationship to existing tables: `entities.entity_type` remains and MUST be documented as a projection of the `type_assertions` observed layer rather than a second independent truth (out of scope to rewrite).

## Out of Scope

- Contextual modelling: `TaskSpec`, `TaskPlan`, `Obligations`, `ContextFrontier`, `ContextDecision`, `ContextSnapshot` (deferred until this feature's success criteria hold).
- Rewriting `entities.entity_type` into the layered model.
- New semantic adapters, vocabularies, profiles or ontology backends.
- Changing the resolution algorithm: blocking, compatibility layers, collective propagation and the decision verdict are closed.
- Live infrastructure: Kafka, Neo4j, MinIO and PostgreSQL remain unavailable in the dev environment; this feature is proven with in-memory implementations plus ORM/migration parity.
- A throughput benchmark against a million observations. FR-022 establishes that replay is a fixed point; a scale claim is a later, separate exercise and this feature must not assert one.

## Success Criteria

- **SC-0 (non-regression):** the suites green today stay green — projection `189 passed, 1 skipped`; acquisition `126 passed, 10 skipped`; interpretation `185 passed`; admission `96 passed`; control-plane `332 passed` with only the 2 pre-existing `test_donor_api` contract failures; shared's 14 failures remain the same known set (`test_infra_connectivity`, `test_evidence_context`, `test_evidence_lineage`, `test_websearch`).
- **SC-1:** An entity's `ENT-` is unchanged when a caller discards its `ResolutionScope` entirely; the anchor is recovered from durable state (FR-001, FR-002, US1).
- **SC-2:** Given any `ENT-`, the anchor, the ordered `RES-` history and the terminal verdict are all returned; ambiguous and unresolved decisions are present in that history (FR-004, US2).
- **SC-3:** A `RES-` decision survives the process; identical input reproduces it, changed input yields a new one, and the old one remains readable (FR-003, US3).
- **SC-4:** `Capture → Observation` resolves with four separately readable time values, and `fetched_at` is never populated from an index timestamp (FR-007, FR-008, US4).
- **SC-5:** The orchestrator no longer fabricates a capture id, and `Source → … → GraphProjection` is traversable in both directions (FR-008).
- **SC-6:** A candidate is validated as unadmitted material, and a material that would never be admitted is still validatable (FR-010, FR-011, US5).
- **SC-7:** `build`, `validate`, `admit` are three distinct operations and no single name denotes all three states (FR-012).
- **SC-8:** On the golden path, regime comparison resolves from storage and `regime_unevaluated` does not occur; any unresolvable regime is a counted, stated `UNRESOLVED` (FR-014, FR-015, FR-016, US6).
- **SC-9:** "CEO of Acme" yields an organisation mention and a relational reading from the extraction package, with no cue rule remaining in the orchestrator (FR-017, FR-018, US7).
- **SC-10:** No extractor can mark a reading `SUPPORTED` (FR-019).
- **SC-11:** The committed corpus runs in CI, and `run(input, versions, policy)` is byte-identical across separate processes over identities, decision hashes, claim hashes, context references and edge materialisation (FR-020, FR-021, US8).
- **SC-12:** Replaying the event log into an empty store reproduces the same graph, ids and lineage; replaying the replay is identical (FR-022, US9).
- **SC-13:** The corpus contains cases for ambiguity, unresolvable, cross-tenant refusal, unknown type, non-blocking validation finding, non-convergent collective, temporal conflict and independence groups (FR-023).
- **SC-14 (the standing acceptance criterion):** For any entity and any relation in the graph, the system can reconstruct *why it was accepted* —
  `Entity → Resolution decision → Mentions → Observations → Captures → Sources`
  and
  `RelationClaim → RelationCandidate → Assertion → Mentions → Evidence`.
  If either chain has a hole, this feature has not succeeded, whatever else it has delivered.
- **SC-15:** Two independent data streams — Common Crawl and at least one non-API, non-Common-Crawl stream — produce `Capture` records through the same contract, with the same six time axes, and no stream-specific acquisition representation exists (FR-024, FR-026, FR-027).
- **SC-16:** A stream that cannot supply a fetch time records a named basis and an `absent` fetch time; a nullable column is not how absence is represented, and no stream substitutes the nearest timestamp it has (FR-025).
- **SC-17:** Anchor lookup by mention and history lookup by entity are both single indexed reads, verified by the index definitions rather than asserted (D-A).

## Constitution Check

| Principle | Status |
|---|---|
| I — evidence before entity | PASS: identity carries a recorded anchor and an ordered decision history; decisions that named no entity are persisted too. |
| II — no second backbone | PASS: new records are Postgres rows in the existing store; replay uses the in-memory implementations already present. |
| III — no auth/CAPTCHA/paywall circumvention | PASS: extraction changes are about reading text that was lawfully fetched. |
| IV — tenant isolation fail-closed | PASS: every new record is tenant-scoped; anchor reads and reconstruction refuse cross-tenant access. |
| V — one time model | PASS: six time axes stay distinct; an index timestamp is never promoted to a fetch time (FR-007). |
| VI — LLM-free determinism | PASS: no generation; replay is asserted to be a fixed point. |
| VII — event-sourced rebuild | PASS: this feature is the durability layer that replay depends on, and SC-012 is the proof. |
| VIII — bounded resources | PASS: resolution already proves termination by a decreasing potential; no unbounded replay is introduced. |

**Gate:** FR-001 and SC-1 are the load-bearing requirement. If an entity's identity can still be changed by a caller forgetting to hold a value, the substrate is not durable and nothing above it is safe.

## Open Questions

1. Should `entity_identity` be a new table or columns on `entities`? A separate table keeps the identity substrate legible and lets `entities.entity_type` stay a projection; columns risk a partial write leaving an entity with no anchor.
2. When a crawl index genuinely carries no fetch time, is the correct representation a nullable `fetched_at` with a stated reason, or a `CaptureTimeBasis` value naming the source of the timestamp? The second is more honest and costs a column.
3. Does `admit` need to be idempotent on `(material, report)` — returning the existing committed claim rather than a second one — or is superseding by content address sufficient?
4. The corpus needs a stable case id scheme and a versioned expected-output format. Should expectations be stored as full expected ids (strict, brittle) or as structural assertions over ids (looser, weaker)? Full ids make the corpus a real regression detector; they also make every intentional change a corpus edit.
5. Corpus placement: committed tests, or a data corpus plus a runner? The user has previously asked not to write tests, so this needs an explicit decision — the current state is that a throwaway script proves behaviour no CI run will execute.
