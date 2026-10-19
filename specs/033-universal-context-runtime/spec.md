# Feature Specification: COGNITIVE Universal Context Runtime — v2.0 Architecture Specification

**Feature Branch**: `033-universal-context-runtime`

**Created**: 2026-10-19

**Status**: Draft

**Input**: Owner-supplied normative document `COGNITIVE_Global_Upgrade_Blueprint (1).md` (v2.0, dated 19 October 2026), reproduced verbatim in [Appendix A](#appendix-a--normative-source-verbatim). Repository: https://github.com/JewishTT/1.

**Source digest**: `sha256:7B645578F210454CA3FE6FC96D2A18D5699E0D5CC1A1A609E3AB08BBE9BD32C6` · 167 121 bytes · 1 979 lines.

**Relationship to the programme**: this is the **v2.0** blueprint. Sections 0–14 are the v1.0 body that Feature `032-global-upgrade-execution` specifies in operational detail; sections 15–36 are the v2.0 extension that defines the *Universal Context Runtime*. This feature is the specification for that extension and for the conformance regime that governs both. Feature 032 remains the execution contract for sections 0–14; where the two features touch the same obligation, the stricter requirement governs and no second authority is created.

---

## Scope Statement

The v2.0 document makes one claim that the v1.0 document did not: COGNITIVE is not only an
evidence-processing platform, it is a **context runtime** — a system that accepts a context of any
subject matter, at any level of abstraction, without a closed ontology and without rewriting its core.

The document is deliberately precise about what that does *not* mean (§15.1, §35): it is not a promise
of magical understanding, not an all-knowing model, not a universal closed schema, and not an excuse
to attach dozens of agents or a database per data type. "Universal" is an **engineering property**:
a new kind of context can be admitted, described, linked, investigated, transformed and verified
without changing the core and without first entering a pre-approved list of ontological types.

That property rests on four principles — **open world**, **typed contracts**, **composable
operators**, **verifiable transformation history** — and on keeping five models distinct (§15.2):
evidence, world/knowledge, context/process, model/simulation space, and policy/decision. A hypothesis
in the process model does not become a fact in the knowledge model; a simulation does not become an
observation; permission to collect does not establish the truth of what was collected.

This feature specifies that runtime: the formal context model (§16), the abstraction ladder and its
loss accounting (§17), the context kernel (§18), the functional catalogue (§19), the capability
registry that replaces hard-coded tool names (§20), the analyst workbenches (§21), retrieval and
context assembly (§22), the reasoning-mode registry (§23), multimodal context (§24), memory layers
(§25), unknown/stopping semantics (§26), the API/event surface (§27), the model gateway (§28), the
security planes (§29), storage profiles (§30), the conformance suites and golden corpus (§32), the
A–H delivery programme (§33), the twenty mandatory ADRs (§34), and the Definition of Done (§35).

**Normative precedence.** Appendix A governs. Sections 0–14 of Appendix A are executed under Feature
032; this feature MUST NOT contradict it and MUST NOT create a second Context Engine. The document's
own §33 says exactly this: "Keep `specs/030-global-platform-upgrade` as the program-level workstream
and attach the universal-context runtime as a coherent extension of it. It should not become a
competing spec with independent source-of-truth."

**Explicit non-goal of this spec**: to claim the runtime exists, to enumerate a closed list of context
types, or to treat the functional catalogue of §19 as a statement of implemented capability. §19's own
preamble calls it "каталог планируемых возможностей, а не заявление, что они все уже реализованы".
Every catalogue row is `declared` until a conformance suite proves otherwise.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A new domain is admitted without touching the core (Priority: P1)

An analyst brings a subject matter the platform has never seen: a new scientific field, a regulatory
regime, a market structure, a codebase, a creative canon. They register a schema and a domain pack —
context kinds, element payload schemas, relation signatures, detectors, views, validators, output
contracts — and the system accepts, stores, links, retrieves and expands that content. No core enum
changes; no migration runs against canonical data; unknown terms are preserved rather than rejected.

**Why this priority**: this is the literal definition of "universal" in §15.1 and the first
Definition of Done bullet in §35. If every new domain requires a core change, the platform is a
closed product with an extensible façade.

**Independent Test**: register a synthetic domain pack for an invented field in a clean environment;
ingest one document and one structured record; assert they survive storage, events, API, export and
retrieval; assert that no table, enum or core schema changed; assert that the pack is disableable.

**Acceptance Scenarios**:

1. **Given** a new context kind with a registered schema, **When** an element of that kind is ingested, **Then** it round-trips through storage, events, API and export without a core code change.
2. **Given** an element whose `kind_uri` has no registered parser or schema, **When** it is ingested, **Then** it is stored as an opaque payload in quarantine with its decoding errors, not discarded (§16.3).
3. **Given** a domain pack that fails schema or contract validation, **When** it is installed, **Then** installation is refused with the failing validator, and no partial activation occurs.
4. **Given** a pack is disabled, **When** the platform continues, **Then** existing data remains readable and no canonical element is deleted.

---

### User Story 2 — The same object is understood at several abstraction levels, and every step is auditable (Priority: P1)

An analyst moves from bytes to span to signal to mention to claim to entity to structure to mechanism
to system to model to decision to meta-level, and back down. Each upward move is an operator with
declared inputs, assumptions and an `AbstractionManifest` that records what was omitted; each
manifest keeps a controlled drill-down path to the evidence. A summary or an embedding never
becomes the only surviving form of the material.

**Why this priority**: §17 is what makes "any level of abstraction" more than a slogan. Without loss
accounting, abstraction is indistinguishable from silent data destruction.

**Independent Test**: build a two-level summary of a document corpus; assert the manifest names the
included inputs, the excluded fields, the aggregation rule and the counterexamples; assert the
drill-down resolves to the original bytes after a rebuild.

**Acceptance Scenarios**:

1. **Given** a summarisation operator, **When** it emits a summary, **Then** an `AbstractionManifest` records inputs, rule, omissions, exceptions, applicability and staleness conditions (§17.3).
2. **Given** an abstraction with an excluded scope, **When** the analyst drills down, **Then** the excluded material is reachable and the omission is visible.
3. **Given** an operator that cannot perform the requested abstraction, **When** it runs, **Then** it returns `partial`, `unsupported` or `blocked` — never a plausible substitute (§17.2).
4. **Given** a `COUNTERFACTUAL` or `SIMULATE` result, **When** it is stored, **Then** it is labelled as a model/simulation artifact and cannot enter the observed-claim store (§15.2, §19.12).

---

### User Story 3 — A capability, not a tool name, is what the planner sees (Priority: P1)

Every operator is registered as a `CapabilityManifest` with input/output schemas, accepted and
emitted types, preconditions, determinism class, network access, quality gate, execution envelope,
governance owner, licence and observability metrics. The planner selects by semantic fit and
constraint first, then by provider. Replacing an implementation does not change the
`ContextDefinition`. A plugin receives only the permission class it needs — `READ`, `DERIVE`,
`PROPOSE`, `DECIDE`, `WRITE_EXTERNAL` or `ADMIN` — never all of them.

**Why this priority**: §20 is the mechanism that keeps universality from degenerating into an
uncontrolled agent swarm, and the permission classes are the only thing standing between a
`DERIVE` operator and a canonical write.

**Independent Test**: register two providers for `semantic.relation.extract`; swap them by manifest
alone and assert the context definition, the audit trail and the outputs' contract are unchanged;
assert that a plugin declared `DERIVE` is refused a canonical write and a `WRITE_EXTERNAL` action.

**Acceptance Scenarios**:

1. **Given** two providers of one capability, **When** the active provider is changed, **Then** no `ContextDefinition`, downstream contract or query changes.
2. **Given** a plugin with `DERIVE` permission, **When** it attempts a canonical write or an external action, **Then** the attempt is denied and recorded.
3. **Given** a capability whose quality gate is not met on the evaluation suite, **When** it is selected for production, **Then** selection is refused or flagged, and the gate result is visible.
4. **Given** a capability with `enabled_by_default: false`, **When** the platform starts, **Then** it is not invoked until explicitly enabled under policy.
5. **Given** no suitable capability exists, **When** the planner plans, **Then** it emits an explicit capability gap — a durable record with a required-contract description — rather than substituting a weaker tool silently.

---

### User Story 4 — The context compiler exposes ambiguity instead of resolving it silently (Priority: P1)

A natural-language request is compiled into a `ContextFrame` with purpose, scope, perspective, time
mode, epistemics, assumptions, questions, obligations, resources and access policy. Where a term is
ambiguous, the compiler records explicit hypotheses, offers branches, or asks — never silently fixing
one meaning that changes safety, cost or correctness.

**Why this priority**: §16.1 and §22.1. Silent disambiguation is the most common failure mode of
natural-language intelligence systems, and the v2.0 document forbids it in the strongest terms.

**Independent Test**: submit a request containing an ambiguous person name and an ambiguous time
range; assert the compile output contains at least two named interpretation hypotheses and that no
single interpretation is committed without a visible assumption or a branch.

**Acceptance Scenarios**:

1. **Given** a request with an ambiguous subject, **When** it is compiled, **Then** the ambiguity list is non-empty and visible in the frame, with the interpretation branches named (§16.1, §22.1).
2. **Given** a request whose scope would change policy or cost materially, **When** it is compiled, **Then** the compiler asks before committing, or emits explicit branches rather than one assumption.
3. **Given** a compiled frame, **When** the analyst revises intent, **Then** a new revision or an explicit branch is created with a parent link — the old revision is not rewritten (§16.1).
4. **Given** a frame whose `granularity` differs per question, **When** it is compiled, **Then** the typed scope model supports multiple granularities and does not collapse them into one field.

---

### User Story 5 — Context assembly is inspectable, so an answer can be explained (Priority: P1)

Every model, solver or operator receives a `ContextAssemblyManifest` — the question and output
schema, the included sources, claims and spans with the reason for inclusion, revisions and time cuts,
the excluded candidates with reason, summary-to-source links, the budget and pruning decisions,
unresolved conflicts that must not be dropped, privacy redactions, the assembly digest, and the
compiler version. This is how an analyst can tell whether the decisive contradiction was cut by
compaction.

**Why this priority**: §22.2. Without it, "the model said so" is the only available explanation for
any conclusion the platform produces.

**Independent Test**: assemble a context under a token budget that forces pruning while a decisive
conflict exists; assert the manifest records the pruning decision and that the conflict is either
included or explicitly marked as dropped-with-reason, and the answer cites the manifest.

**Acceptance Scenarios**:

1. **Given** a context assembly, **When** it is inspected, **Then** every included element carries a reason and every excluded one a reason category (§22.2).
2. **Given** a decisive conflict at risk of being pruned, **When** compaction runs, **Then** the conflict is preserved or the answer is explicitly marked as assembled without it (§22.2, §22.3).
3. **Given** an assembled context, **When** the answer is produced, **Then** the assembly digest and compiler version are recorded with the output.
4. **Given** a summary included in the assembly, **When** the answer relies on it, **Then** the summary-to-source links and the abstraction manifest travel with it.

---

### User Story 6 — Different reasoning modes are separate operators with separate limits (Priority: P2)

An analysis requests lexical retrieval, deterministic constraints, statistical estimation, causal
estimation under identification assumptions, graph structure, simulation and adversarial review as
distinct operators. The composition is a plan, each mode's output is labelled with its method and
limits, and a skipped step is explained in the manifest rather than disappearing.

**Why this priority**: §23. Collapsing every form of analysis into one undifferentiated "reasoning"
makes it impossible to state what an answer actually rests on.

**Independent Test**: run one analysis that legitimately requires exact lookup, lexical recall, a
deterministic constraint and a statistical estimate; assert four labelled outputs, one composed
explanation, and a manifest that names the method per component.

**Acceptance Scenarios**:

1. **Given** a causal question with no identification strategy, **When** the causal operator runs, **Then** it returns the non-identifiability as the result rather than an effect estimate (§19.12, §32.2).
2. **Given** a graph centrality result, **When** it is reported, **Then** it is labelled a structural measure and cannot create a fact or commit an identity (§13, §23).
3. **Given** a critical-review operator, **When** it reports, **Then** it is labelled as review, not as an independent evidence source (§23).
4. **Given** a composed analysis, **When** the result is delivered, **Then** each component carries its assumptions and its limit, and the composition itself is recorded.

---

### User Story 7 — Non-text material is a first-class citizen, not a model's caption (Priority: P2)

An image, an audio recording, a video and a chart are stored as immutable media with digests,
modality metadata, coordinate and time systems, a segmentation tree, transformation lineage, and
extracted text or measurements with exact source spans. A transcript phrase maps to an audio
interval; OCR text maps to an image box; a video frame maps to an event. The extracted form never
replaces the original, and alignment is itself an acceptance criterion.

**Why this priority**: §24. If only documents have a source of truth, the platform's "universal"
claim collapses at the first non-text artifact.

**Independent Test**: ingest a scanned table image and an audio recording; assert the OCR cell and the
transcript phrase each resolve to an exact box or time interval with tolerance tests, and that both
survive restart and rebuild.

**Acceptance Scenarios**:

1. **Given** an OCR extraction, **When** it is stored, **Then** it carries the image box, the coordinate system, the model version and the transformation lineage (§24).
2. **Given** a transcript, **When** it is queried, **Then** the phrase resolves to an exact audio interval with declared tolerance (§24, §32.1(16)).
3. **Given** a modality link, **When** it is created, **Then** it is a candidate mapping with confidence and verification, not an asserted identity.
4. **Given** a redacted media artifact, **When** it is served, **Then** the redaction and classification travel with it and the original is never served to an unauthorised viewer.

---

### User Story 8 — Memory is layered, scoped and correctable (Priority: P2)

Conversation state, working set, task memory, case memory, entity/worldline memory, procedural
memory, semantic/episodic indexes, preference memory and institutional memory each have their own
scope, retention, permissions, correction, expiry and replay rules. Nothing is remembered forever by
default, and a summary remembers what it omitted.

**Why this priority**: §25. A single "memory" is how a research platform turns into a system that
cannot explain, correct or forget.

**Independent Test**: write one item into each of the nine layers; assert each is retrievable only
within its declared scope and retention, that a preference never appears as evidence, and that a
summary carries links to what it compressed.

**Acceptance Scenarios**:

1. **Given** an item in preference memory, **When** an evidence query runs, **Then** the preference is not returned as evidence (§25.8).
2. **Given** an expired item under its layer's retention, **When** retention runs, **Then** the item is expired with a lineage impact record, not silently deleted.
3. **Given** a working-set compaction, **When** the analyst asks why a detail is missing, **Then** the compaction record names what was dropped and links to the full history (§25.2).

---

### User Story 9 — Unknown is a classified state and completion is a report (Priority: P1)

The platform distinguishes `UNKNOWN_NOT_INVESTIGATED`, `NO_OBSERVATIONS`, `SOURCE_UNAVAILABLE`,
`QUERY_UNSUPPORTED`, `SEARCHED_NO_RESULT`, `QUALIFIED_ABSENCE`, `POSITIVE_SUPPORT`,
`NEGATIVE_SUPPORT`, `BOTH`, `INCONCLUSIVE`, `BLOCKED_PARTIAL`, `HYPOTHESIS_REFUTED` and
`SATURATED_WITH_SCOPE`. Every terminal state emits a `CompletionReport` with residual obligations,
executed and unexecuted scope, sources attempted and unavailable, open conflicts and reopening
conditions. `COMPLETE_WITH_LIMITATIONS` is a valid and honest ending.

**Why this priority**: §26. This is where the v2.0 document is most explicit: no empty value,
exhausted retry, zero result or empty queue is a completion criterion.

**Independent Test**: force each of the fourteen result states; assert each is distinguishable across
storage, API and UI, and that a `CompletionReport` names the reason and the residual obligations.

**Acceptance Scenarios**:

1. **Given** a query that returned zero results from a source with undeclared detection power, **When** the result is classified, **Then** it is `SEARCHED_NO_RESULT`, not `QUALIFIED_ABSENCE` (§26.1).
2. **Given** a run that exhausted its budget, **When** it terminates, **Then** the state is `BLOCKED_PARTIAL` with the exhausted budget named, and the report lists the unexecuted scope (§26.2).
3. **Given** a completed context, **When** the report is produced, **Then** it names reopen conditions and next-best actions, and does not present open questions as resolved.
4. **Given** a hypothesis refuted inside a stated criterion and scope, **When** it is recorded, **Then** the scope boundary travels with the refutation.

---

### User Story 10 — The API, events and SDK are typed, versioned and honest about long work (Priority: P2)

Contexts, obligations, plans, actions, timelines, graphs, conflicts, resolutions, worldlines,
evidence, spans, ontology revisions, capabilities, queries, analyses, runs, traces, evaluations,
reports and audit are typed resources. Long work returns a durable run ID and events, never a
misleading success. Errors are typed `problem+json` with stable reason codes and an explicit
retriable flag. Events are published only after their canonical transaction commits, through the
approved outbox seam.

**Why this priority**: §27. An API that reports success for queued work, or publishes an event before
the write commits, breaks every downstream guarantee the rest of the platform is built on.

**Independent Test**: call a long-running analysis; assert the immediate response is an accepted run
ID, that polling reports real status, that the event appears only after commit, and that a failure is
a typed error rather than a 200.

**Acceptance Scenarios**:

1. **Given** a long analysis, **When** it is submitted, **Then** the response is a durable run ID with status, and no success is claimed before completion (§27.1).
2. **Given** an event published by a failing transaction, **When** recovery runs, **Then** no event exists that lacks a committed backing state (§27.2).
3. **Given** an error, **When** it is returned, **Then** it carries a stable reason code, a retriable flag and a remediation hint, and no secret or unrestricted stack trace (§27.1).
4. **Given** a query DSL request, **When** it runs, **Then** it declares scope, time, space, perspective, epistemic and provenance filters, execution mode and budget caps, and returns partial/unknown/conflict semantics explicitly (§27.3).

---

### User Story 11 — Security is five planes and confidence is not authorization (Priority: P1)

The data plane, context control plane, execution plane, governance plane and evidence/audit plane are
separated logically, with tenant and context isolation across queries, caches, vector indexes, logs and
exports. Untrusted content is data, never system instructions. A high-confidence identity match does
not authorise collection or disclosure; a public source does not authorise unlimited aggregation; a
technically executable action is not a permitted action. These separations are enforced in code and
tests, not left to analyst judgement.

**Why this priority**: §29.3 states the platform's central distinction explicitly, and the adversarial
conformance suite (§32.1(14), (18)) is the only proof that it holds.

**Independent Test**: construct a document containing prompt injection, a cross-tenant reference, an
external action requested by a model, and a high-confidence identity match against a protected
subject; assert all four are refused at the policy boundary and recorded, and that the injection text
did not alter system behaviour.

**Acceptance Scenarios**:

1. **Given** a document containing instructions aimed at the model, **When** it is processed, **Then** it is treated as data and cannot alter tool permissions or policy (§29.2).
2. **Given** a technically permitted request that violates purpose limitation, **When** it is issued, **Then** it is denied with the violated rule named (§29.2, §29.3).
3. **Given** a replay of an old run under current policy, **When** it is requested, **Then** the original policy is preserved as provenance and the replay is re-authorised under the current policy (§29.2).
4. **Given** an export or sensitive inference, **When** it occurs, **Then** it is audited with actor, purpose and classification label.

---

### User Story 12 — "Production-ready" is a demonstrated lifecycle, not an import (Priority: P2)

A capability moves through `DISCOVERED → LICENSE_REVIEWED → CONTRACTED → UNIT_TESTED →
CONTRACT_TESTED → BENCHMARKED → WIRED → E2E_PROVEN → OBSERVED_IN_OPERATION → APPROVED_FOR_SCOPE`,
with `BLOCKED`, `NOT_RUN` and `UNKNOWN` as first-class statuses. Eighteen conformance suites and a
golden corpus of fifteen fixtures must pass before the runtime is called complete.

**Why this priority**: §32 and §35. The document's closing rule is that the platform must expose
exactly what is evidenced, inferred, assumed, simulated, disputed or still unknown — which requires
a lifecycle that can say `NOT_RUN` out loud.

**Independent Test**: run the eighteen conformance suites against a clean stack and publish the
per-suite status, including `NOT_RUN` rows; assert that a capability marked `WIRED` without
`E2E_PROVEN` cannot be labelled `APPROVED_FOR_SCOPE`.

**Acceptance Scenarios**:

1. **Given** a capability that passes unit tests but has no end-to-end proof, **When** its status is requested, **Then** it is `UNIT_TESTED`, not `APPROVED_FOR_SCOPE` (§32).
2. **Given** a conformance suite that cannot run, **When** the report is published, **Then** the suite is `NOT_RUN` with a reason, and the release gate treats it as unmet (§32, §33 Phase H).
3. **Given** the Definition of Done, **When** any bullet is unmet, **Then** the runtime is not declared complete, and the unmet bullet is named (§35).
4. **Given** a proposed ADR conflict, **When** the ADR set is reviewed, **Then** the conflict is resolved before the architecture is treated as final (§34).

---

## Requirements *(mandatory)*

Requirement IDs are stable and are the traceability anchor for `plan.md` and `tasks.md`. Section
references (§n) point into Appendix A. Requirements marked **⟨inherited⟩** restate an obligation that
Feature 032 owns operationally; they are listed here because the v2.0 document binds them into the
universal runtime contract, and the stricter wording governs.

### Functional Requirements — Universal context model (§15–§16)

- **FR-001**: The platform MUST accept a new context kind through a schema-backed URI and registry entry without changing core enums or core tables (§15.1, §16.3).
- **FR-002**: The five models — evidence, world/knowledge, context/process, model/simulation, policy/decision — MUST remain semantically distinct and MUST be linked by reference and event, never merged; a hypothesis MUST NOT become a fact, a simulation MUST NOT become an observation, and permission to collect MUST NOT establish truth (§15.2).
- **FR-003**: `ContextFrame` MUST be a versioned snapshot carrying identity, revision and parent revision, tenant, purpose (goal, success criteria, deliverable contract), scope (inclusions, exclusions, granularity, scope revision), perspective (observer role, jurisdiction, ontology view), time (mode, valid interval, knowledge cutoff, timezone), epistemics (open-world flag, confidence policy, explicit-unknowns flag), assumptions, questions, hypotheses, obligations, resource budgets, access policy snapshot and classification, provenance, and a state digest (§16.1).
- **FR-004**: The context model MUST support a multi-dimensional description — content, semantics, abstraction level, time, space, causality, epistemics, modality, perspective, social structure, computational model, normative model, uncertainty, provenance and goal/value — with `unknown` and `not_applicable` as mandatory and distinct values in every dimension (§16.2).
- **FR-005**: Missing information in any dimension MUST be preserved as missing; the system MUST NOT substitute a convenient default (§16.2).
- **FR-006**: Every content item MUST be representable through a `ContextElement` envelope with an open `kind_uri`, schema ref and version, payload ref or small inline payload, raw-form ref, semantic refs, typed relations, time and space scope, epistemic status, provenance refs, abstraction-level ref, perspective refs, assumption refs, classification, lineage/supersedes and validation status (§16.3).
- **FR-007**: An invalid payload MUST go to quarantine with its decoding errors; an unknown type MUST be preserved as an opaque payload that can be investigated after a parser or schema is registered (§16.3).
- **FR-008**: Relations MUST support binary, n-ary and event-relations with participant roles; role-bearing relations MUST be reified as `RelationAssertion` or `EventFrame` and MAY be projected into graph edges (§16.4).
- **FR-009**: A `ContextDefinition` change MUST produce a new revision or branch with a parent link, never a silent rewrite (§16.1; ⟨inherited⟩ FR-047 of Feature 032).

### Functional Requirements — Abstraction and loss accounting (§17)

- **FR-010**: The platform MUST support at least the twelve abstraction levels of §17.1 as a branching, intersecting ladder, with typed relations `abstraction_relation`, `representation_of`, `derived_from`, `member_of`, `instantiates`, `models`, `contradicts` and equivalents, each carrying its own evidence (§17.1).
- **FR-011**: Every abstraction operation of §17.2 — `DECOMPOSE`, `AGGREGATE`, `ABSTRACT`, `INSTANTIATE`, `GENERALIZE`, `SPECIALIZE`, `PROJECT`, `LIFT_RELATION`, `COMPOSE`, `DECOMPOSE_CAUSALLY`, `ANALOGIZE`, `CONCRETIZE`, `TEMPORALIZE`, `SPATIALIZE`, `MODEL`, `SIMULATE`, `COUNTERFACTUAL`, `COMPARE`, `RECONCILE`, `EXPLAIN`, `REFUTE`, `BOUND` — MUST be a formal operator with declared inputs, outputs, assumptions, loss profile and test fixtures, and MUST record the mandatory field named for it in §17.2.
- **FR-012**: Every abstraction operator MUST emit at least `success`, `partial` and `unsupported/blocked`, plus the possibility of `no_change`; it MUST link its inputs and create a new derived artifact without rewriting the source object (§17.2).
- **FR-013**: Every abstraction MUST produce an `AbstractionManifest` recording input IDs and digests, included scope, aggregation rule or model, omitted fields and fragments, exception counts and classes, supporting and contradicting cases, applicability range, staleness conditions, and the drill-down path to source material (§17.3).
- **FR-014**: Summaries and embeddings MUST remain accelerating representations with a controlled path back to evidence; they MUST NOT replace the original context (§17.3).

### Functional Requirements — Context kernel (§18)

- **FR-015**: The core runtime MUST provide the twelve components of §18.1: context registry, context compiler, context resolver, context store, context delta engine, context graph store, obligation generator and evaluator, action planner, execution coordinator, context memory compiler, context revision manager, and stopping/completion engine (§18.1).
- **FR-016**: The context compiler MUST compile intent into a `ContextDefinition` with questions, scope and criteria, and MUST enumerate ambiguities (§18.1(2), §22.1).
- **FR-017**: The context delta engine MUST classify each change as new evidence, ontology change, policy change, user correction, projection drift or time advance (§18.1(5)).
- **FR-018**: The context memory compiler MUST select the minimum sufficient working set for an operation without hiding references to the full context (§18.1(10)).
- **FR-019**: The context revision manager MUST create revisions only on meaningful deltas and MUST prevent revision cycles (§18.1(11); §32.1(1)).
- **FR-020**: Context kinds MUST be an open, schema-backed catalogue; the starter registry MUST include the sixteen profiles of §18.2, and a user or donor domain pack MUST be able to register new kinds without core enum changes, subject to schema and contract validation (§18.2).
- **FR-021**: The existing `apps/control-plane/context_engine` MUST be refined and integrated, not duplicated; no competing engine and no separate "memory" system that becomes a source of truth may be created (§18.1).

### Functional Requirements — Functional catalogue (§19)

- **FR-022**: Every capability in the eighteen catalogues of §19 (acquisition, parsing, language, retrieval, identity, graph, ontology, claims, temporal, spatial, quantitative, causal, formal, planning, orchestration, reporting, collaboration, observability) MUST carry an ID, owner, input/output contract, policy requirements, determinism class, cost, tests, metrics and production status (§19 preamble).
- **FR-023**: LLM-generated content MUST remain a derived artifact carrying model, provider, prompt and tool versions, input refs and digests, output schema, known non-determinism, safety-policy version and validation outcome; model confidence MUST NOT be treated as evidence quality (§19.3).
- **FR-024**: A solver timeout or `unknown` MUST NOT be reported as proof of falsehood, and any code-execution capability MUST declare sandbox, filesystem, network, dependency and resource policies (§19.13).
- **FR-025**: Correlation MUST NOT be reported as causation, and a causal claim MUST state its identification assumptions; simulated outputs MUST remain scenario outputs (§19.11, §19.12).
- **FR-026**: Temporal capabilities MUST distinguish valid from knowledge time and support `CURRENT`, `AS_OF` and `INTERVAL` modes; spatial capabilities MUST be CRS-aware and carry positional accuracy; neither may infer a residential location without policy basis (§19.9, §19.10; ⟨inherited⟩ FR-036, FR-037 of Feature 032).
- **FR-027**: Collaboration and governance capabilities MUST provide role- and attribute-based access, branch/fork/merge of analytical context without silent canonical merge, conflict triage, approvals, purpose limitation, retention, audit and policy-as-code with denied-action explanation (§19.17).
- **FR-028**: Observability MUST correlate traces across context, action, operator, run and observation, publish digests rather than raw sensitive payloads, and treat telemetry as non-authoritative (§19.18).
- **FR-029**: Durable workflow ownership MUST remain with the existing Temporal integration; adopting another orchestration framework requires a written ADR and MUST NOT create a parallel authority (§19.15).

### Functional Requirements — Capability registry and permissions (§20)

- **FR-030**: Every tool MUST be registered as a `CapabilityManifest` carrying identity and version, input and output schemas, accepted and emitted types, preconditions, constraints (determinism, network access, payload limit, supported languages), quality gate, execution envelope, governance (owner, licence, model/data manifest, default-enabled flag) and observability metrics (§20.1).
- **FR-031**: The planner MUST select a capability by semantic fit and constraints before a concrete provider or runtime, and changing the provider MUST NOT change the `ContextDefinition` (§20.1).
- **FR-032**: Every operator MUST implement `describe`, `validate`, `execute` and `health`; `OperatorRequest` MUST carry typed input refs, context snapshot and revision, effective policy, budget and deadline, idempotency key and requested output contract; `OperatorResult` MUST carry status, typed outputs, provenance, input and output digests, operator/runtime/model versions, warnings, coverage, resource costs, emitted candidates and a continuation or checkpoint reference (§20.2).
- **FR-033**: An operator invocation MUST NOT carry ambient write privilege (§20.2).
- **FR-034**: Permissions MUST be classified as `READ`, `DERIVE`, `PROPOSE`, `DECIDE`, `WRITE_EXTERNAL` and `ADMIN`; a plugin MUST receive only the classes it needs; `WRITE_EXTERNAL` MUST be off by default, require explicit grant, confirmation and idempotency control; `ADMIN` MUST live in a separate high-privilege plane (§20.3).
- **FR-035**: External side effects MUST support dry-run, preview, idempotency, cancellation/compensation where possible, and an audit log (§20.3).
- **FR-036**: Tool selection MUST first apply hard policy and compatibility filters, then optimize cost and quality; an LLM score alone MUST NOT select a capability (§20.4).

### Functional Requirements — Analyst surfaces (§21)

- **FR-037**: The platform MUST provide the twenty workbenches of §21 — universal workbench, context explorer, evidence browser, entity/process workspace, research graph, knowledge graph, timeline studio, conflict desk, ontology studio, query/analysis studio, quant/model lab, workflow inspector, source registry, donor/capability registry, report builder, decision log, data-quality console, security/audit console, context diff and branches, and API/SDK studio (§21).
- **FR-038**: Each surface MUST be a view over the same state and the same references, not a local repository of truth; write controls MUST call the corresponding authority service (§21).
- **FR-039**: Each surface MUST expose staleness, unknown and conflict state rather than presenting a polished singular view (§8.2 operations row, §21).

### Functional Requirements — Retrieval and context assembly (§22)

- **FR-040**: The context compiler pipeline MUST run intent hypotheses and ambiguity, purpose/scope/time/perspective/constraints, questions/obligations/output contract, capability requirements, policy filtering, retrieval and acquisition plans, context assembly manifest, execution, and evidence-backed result with residual unknowns (§22.1).
- **FR-041**: An ambiguous term MUST produce an explicit visible assumption, multiple interpretation branches, or a question when ambiguity affects safety, cost or correctness; a single meaning MUST NOT be silently fixed (§22.1).
- **FR-042**: Every LLM, solver or operator MUST receive a `ContextAssemblyManifest` containing the question and output schema, included sources/claims/spans with inclusion reason, revisions, time cut, ontology and policy versions, excluded candidates with reason, summary-to-source links and abstraction manifests, token/byte/row budget and pruning decisions, unresolved conflicts and unknowns that must not be omitted, privacy filters and redactions, the assembly digest and the renderer/compiler version (§22.2).
- **FR-043**: The retrieval pipeline MUST implement the eight layers of §22.3 — candidate recall, grounding, semantic ranking, graph/context expansion, conflict-aware assembly, diversity and dependency collapse, budget-aware packing and coverage check — with BM25 as baseline and vector, graph and reranker components added only on measured gain (§22.3).
- **FR-044**: Vector similarity MUST be treated as a recall and ranking aid, never as proof or as an identity decision (§22.3).
- **FR-045**: The conflict-aware assembly layer MUST include competing claims and counter-evidence, not only top-positive results (§22.3(5)).

### Functional Requirements — Reasoning modes (§23)

- **FR-046**: Each reasoning mode of §23 — exact lookup, lexical and semantic retrieval, rule and logic, deduction, induction and statistics, Bayesian, abduction, causal, analogy, temporal, spatial, graph, simulation, optimization, critical adversarial review, human adjudication and meta-reasoning — MUST be a separate operator with its own output form and stated limit (§23).
- **FR-047**: A composed analysis MAY omit a reasoning step, but the omission MUST be explainable and recorded in the manifest (§23).
- **FR-048**: Human adjudication MUST produce a signed decision with rationale, authority and audit (§23).

### Functional Requirements — Multimodal context (§24)

- **FR-049**: Non-text material MUST be stored under a common contract covering the raw asset and digest, modality/codec/format metadata, time and spatial coordinate systems, a segmentation tree, transformation lineage, extracted text/measurements/entities with confidence and exact spans, model and runtime version with known failure modes, redaction/classification and retention, and source-open playback or zoom in the UI (§24).
- **FR-050**: Cross-modal links MUST be candidate mappings — transcript to audio interval, OCR to image box, frame to event, chart point to plot or table row — with alignment and temporal precision verified as an acceptance criterion (§24).
- **FR-051**: Extracted text MUST NOT replace the original material (§24).

### Functional Requirements — Memory layers (§25)

- **FR-052**: The platform MUST implement the nine memory layers of §25 — conversation state, working set, task/process, case/project, entity/worldline, procedural, semantic/episodic indexes, preference and institutional — each with its own scope, retention, permissions, correction, expiry and replay rules (§25).
- **FR-053**: A blanket "remember forever" policy MUST NOT be applied to all objects; summary memory MUST reference its source objects and record what was omitted (§25).
- **FR-054**: Preference memory MUST NOT be mixed with business evidence (§25.8).

### Functional Requirements — Unknown and completion semantics (§26)

- **FR-055**: The platform MUST distinguish the fourteen research result states of §26.1 and MUST NOT collapse any of them into another (§26.1).
- **FR-056**: No empty value, exhausted retry, zero-yield search or empty queue MAY be treated as a completion criterion (§26.1).
- **FR-057**: Every terminal state MUST emit a `CompletionReport` with context ID and final revision, completion status and reason code, satisfied and unsatisfied criteria, satisfied and residual obligations, executed/unexecuted/excluded scope, sources attempted and unavailable and unsupported capabilities, evidence coverage and known selection bias, open conflicts and unresolved hypotheses, budgets consumed and stop reason, reproducibility manifest and policy version, and reopen conditions with next-best actions (§26.2).
- **FR-058**: `COMPLETE_WITH_LIMITATIONS` MUST be a valid terminal state, and the system MUST NOT hide open questions to present one clean answer (§26.2).

### Functional Requirements — API, events and SDK (§27)

- **FR-059**: The platform MUST expose the typed resource APIs of §27.1, with naming reconciled against existing routers and contracts; no second API set may be created without a migration plan (§27.1).
- **FR-060**: Long-running work MUST return a durable run ID and events, never a misleading success response (§27.1).
- **FR-061**: Errors MUST be typed `problem+json`-style with stable reason codes, a retriable flag and a remediation hint, and MUST NOT expose secrets or unrestricted stack traces (§27.1).
- **FR-062**: Events MUST use a canonical envelope carrying schema version, event ID, occurred and recorded times, tenant, context and revision, actor/operator, correlation and causation, idempotency, provenance and payload refs, across the eleven event families of §27.2 (§27.2).
- **FR-063**: An event MUST be published only after its backing canonical transaction commits through the approved outbox seam; the event bus is delivery and replay, not authority (§27.2).
- **FR-064**: The platform MUST provide a versioned SDK and a typed JSON query DSL supporting subject/predicate/value or graph pattern, scope/time/space/perspective constraints, epistemic and source-quality filters, required provenance level, execution mode (`preview`, `execute`, `replay`, `explain`), cost/deadline/budget caps, accepted output schema, and partial/unknown/conflict semantics (§27.3).
- **FR-065**: Arbitrary unbounded code execution MUST NOT be exposed as the universal DSL; specialised SQL, SPARQL or graph languages MUST sit behind separate capability, validation and resource controls (§27.3).

### Functional Requirements — Model gateway (§28)

- **FR-066**: The model gateway MUST expose a common contract over LLM, embedding, reranker, OCR, ASR, VLM and specialist models carrying exact provider/model identity and immutable version, supported modality/language/task and context limits, input/output schema and cost, policy and region eligibility, timeout/retry/fallback and concurrency caps, prompt/template version and input manifest digest, output validator and schema-repair policy, structured refusal/error/partial semantics, evaluation results, retention and training/data-use terms, and a disable/rollback switch (§28).
- **FR-067**: Provider fallback MUST NOT silently change data jurisdiction, privacy characteristics or semantic behaviour (§28).
- **FR-068**: A deterministic output MUST NOT be served by an LLM call as if it were a deterministic parser or solver (§28).
- **FR-069**: Every LLM output MUST distinguish extracted quotation, normalized value, inferred claim, generated summary and speculation (§28).

### Functional Requirements — Security and governance (§29)

- **FR-070**: The five planes of §29.1 — data, context control, execution, governance, evidence/audit — MUST be logically separated with clear permissions, schemas and ownership even where infrastructure is shared (§29.1).
- **FR-071**: The mandatory protection rules of §29.2 MUST be enforced: tenant and context isolation across queries, caches, vector indexes, logs and exports; RBAC plus ABAC with purpose limitation; credential-vault references; encryption and rotation; classification propagation; controlled egress with SSRF and DNS/redirect checks; isolated workers for browser, code, archive and third-party tools; resource quotas; prompt-injection containment; output validation and tool allowlists; retention and authorised deletion with lineage impact; audit on access, sensitive inference, export, decision and external side effect; presentation and log redaction; SBOM, licence, model and dataset inventory; safe replay under current policy; approval for high-impact actions; and source terms and sensitivity controls (§29.2).
- **FR-072**: Untrusted content MUST be treated as data and never as system instructions (§29.2).
- **FR-073**: No model may grant itself privileges, and confidence MUST NOT be treated as authorisation for collection or disclosure (§29.2, §29.3).

### Functional Requirements — Storage and compute (§30)

- **FR-074**: Canonical data contracts MUST remain independent of physical index; SQL, graph, lexical, vector, columnar and time-series stores are execution targets and projections, and each query response MUST declare the data cut and projection freshness it used (§30.1).
- **FR-075**: The baseline profile MUST reuse existing components only where their production callers and ownership are proven, per §30.2; optional profiles — vector store, JanusGraph/ScyllaDB, specialised engines — MUST NOT become a second truth store (§30.2).
- **FR-076**: Optional backend adoption MUST be benchmarked on query quality, freshness, rebuild duration, operational burden, consistency, tenancy, ACL/ABAC enforcement, deletion propagation and failure recovery, not only traversal throughput (§30.2; ⟨inherited⟩ FR-045 of Feature 032).

### Functional Requirements — Conformance, programme and ADRs (§32–§36)

- **FR-077**: Capability status MUST follow the ten-step lifecycle of §32 and MUST keep `BLOCKED`, `NOT_RUN` and `UNKNOWN` as first-class visible statuses (§32).
- **FR-078**: The eighteen conformance suites of §32.1 MUST exist and pass before the runtime is called complete (§32.1).
- **FR-079**: The golden corpus of §32.2 MUST contain at least the fifteen fixtures listed, each with expected accepted, rejected, unresolved and unknown states, expected citations and spans, and explicitly allowed alternative interpretations (§32.2).
- **FR-080**: Delivery MUST follow Phases A–H of §33 in order, attaching to `specs/030-global-platform-upgrade` as an extension and reconciling section and task names against the live working tree before coding (§33).
- **FR-081**: The twenty ADRs of §34 MUST be approved and versioned, each stating decision, context, alternatives, consequences, migration plan, rollback plan, owner, status and date; the architecture MUST NOT be treated as final while ADRs conflict (§34).
- **FR-082**: The Definition of Done of §35 MUST be demonstrated item by item; naming a capability in the catalogue is not completion (§35).
- **FR-083**: External standards and reference implementations of §36 — SHACL, PROV-O, OpenTelemetry conventions, LangGraph, Semantica, kafSIEM, JanusGraph — MUST be treated as specification references or donor candidates, never as automatic production dependencies, and their advertised feature lists MUST NOT be taken as proof of suitability, correctness, scale or licence compatibility (§36).

### Key Entities *(include if feature involves data)*

- **ContextFrame / ContextDefinition / ContextRevision / ContextBranch**: the versioned snapshot, its immutable definition, its revision chain and its analytical branches (§16.1).
- **ContextElement**: the open-typed content envelope with payload schema, provenance, scope and epistemic status (§16.3).
- **RelationAssertion / EventFrame**: role-bearing, n-ary and event-relations that may be projected as edges but are not reducible to them (§16.4).
- **AbstractionManifest**: the loss record of every upward representational step (§17.3).
- **ContextAssemblyManifest**: the inspectable snapshot given to a model or solver, with inclusion and exclusion reasons (§22.2).
- **CapabilityManifest / OperatorRequest / OperatorResult / CapabilityHealth**: the registry and invocation contracts that replace hard-coded tool names (§20).
- **CompletionReport**: the terminal accounting of an investigation, including residual unknowns and reopen conditions (§26.2).
- **MemoryLayer**: the nine scoped memories with their retention, permissions and correction rules (§25).
- **ConformanceSuite / GoldenFixture / CapabilityLifecycleState**: the proof machinery of §32 and the status vocabulary that keeps `NOT_RUN` honest.
- **ADR**: the twenty decisions that must exist before the architecture is final (§34).

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001 (open extension)**: a new domain pack is registered, ingested, retrieved and disabled with zero changes to core enums, core tables or core migration count.
- **SC-002 (opaque preservation)**: 100 % of unknown kinds and unknown payloads survive storage, events, API, export and UI round-trip, or are quarantined with named decoding errors — zero silent drops.
- **SC-003 (abstraction accounting)**: 100 % of summaries, models and abstractions carry an `AbstractionManifest`, and 100 % of them support a drill-down that resolves to source bytes.
- **SC-004 (capability substitution)**: replacing a provider for any registered capability changes neither the `ContextDefinition` nor the downstream output contract in 100 % of swap tests.
- **SC-005 (permission containment)**: zero `DERIVE` or `PROPOSE` capability performs a canonical write or an external side effect in the adversarial test suite.
- **SC-006 (ambiguity exposure)**: 100 % of ambiguity that affects safety, cost or correctness is materialised as a named hypothesis, a branch or a question — zero silent disambiguation.
- **SC-007 (assembly explainability)**: 100 % of model and solver answers cite a `ContextAssemblyManifest`; in 100 % of forced-pruning cases the dropped conflict is either retained or explicitly recorded as excluded.
- **SC-008 (reasoning attribution)**: 100 % of composed analyses label each component with its mode, assumptions and limit; zero causal claims without stated identification assumptions; zero centrality or similarity results creating facts.
- **SC-009 (multimodal grounding)**: OCR and ASR outputs resolve to exact boxes and intervals within declared tolerance and survive rebuild in 100 % of the corpus cases.
- **SC-010 (memory scoping)**: nine layers are independently scoped, retained, correctable and expirable; zero preference records returned as evidence.
- **SC-011 (unknown fidelity)**: all fourteen result states of §26.1 are distinguishable across storage, API and UI; zero termination without a `CompletionReport`.
- **SC-012 (API honesty)**: zero long-running operations report success before completion; zero events exist without a committed backing transaction; zero errors leak secrets or stack traces.
- **SC-013 (security separation)**: the adversarial suite — prompt injection, cross-tenant reference, model-requested external action, protected-subject identity match, replay under changed policy — passes with zero bypasses.
- **SC-014 (conformance)**: all eighteen suites report a status; `NOT_RUN` is permitted but blocks the release gate; no capability reaches `APPROVED_FOR_SCOPE` without `E2E_PROVEN`.
- **SC-015 (golden corpus)**: the fifteen §32.2 fixtures exist with expected accepted, rejected, unresolved and unknown states, citations and allowed alternatives.
- **SC-016 (ADR completeness)**: the twenty §34 ADRs are approved with decision, alternatives, consequences, migration, rollback, owner, status and date; zero unresolved conflicts between them at release.
- **SC-017 (Definition of Done)**: every §35 bullet is demonstrated on a clean stack from API/UI through durable report, surviving process restart, with published test results, workload profile, quality metrics, costs and known limitations.

## Assumptions

- The v2.0 document is the owner's intended target state as of 2026-10-19; §19 is a planning catalogue and §35 is the completion test, not a status report.
- Feature `030-global-platform-upgrade` remains the program-level workstream, and Feature `032-global-upgrade-execution` remains the execution contract for v1.0 sections 0–14; this feature extends rather than replaces either (§33).
- `apps/control-plane/context_engine` exists and is the locus of the kernel; the work is contract refinement and integration, not a new engine (§18.1).
- The baseline infrastructure of §30.2 is present or explicitly reported absent; optional profiles are not assumed and must be benchmarked before adoption.
- The §36 external projects are references at unpinned revisions; no capability claim from their READMEs survives without an evaluation against the platform's own corpus.
- Owner sign-off exists for each ADR, each `APPROVED_FOR_SCOPE` capability and each release-gate decision; the platform does not self-authorise its own completion.

## Out of Scope Confirmation

- A second Context Engine, a second canonical store, or a parallel "memory" authority (§18.1, §30).
- A closed, exhaustive enumeration of context types; §18.2 is a starter registry, not a schema limit (§18.2).
- Treating the §19 catalogue as evidence of implemented capability (§19 preamble).
- Binding the runtime to one graph, vector or orchestration framework before measurement and an ADR (§19.15, §30.2, §34).
- Presenting simulation, causal narrative, abstraction or LLM output as observed fact (§15.2, §19.12, §28).
- Legal or professional judgement: policy and regulatory analysis supports an analyst and does not impersonate a licensed professional or decide a case (§31.6).
- Declaring the runtime complete on the strength of capability naming rather than the §35 demonstrations (§35).

---

## Appendix A — Normative source (verbatim)

The document below is the owner's v2.0 specification, reproduced **without modification**. It is the
governing text for this feature: where this spec's narrative, requirements or success criteria
conflict with it, this appendix prevails.

**Provenance**: `COGNITIVE_Global_Upgrade_Blueprint (1).md` · SHA-256 `7B645578F210454CA3FE6FC96D2A18D5699E0D5CC1A1A609E3AB08BBE9BD32C6` · 167 121 bytes · 1 979 lines · supplied 2026-10-19 · copied 2026-10-19.

**Integrity check**: the block between the two HTML comment markers below is byte-for-byte the source
file. Re-extract and hash it with:

```powershell
$raw  = Get-Content .\specs\033-universal-context-runtime\spec.md -Raw
$s    = $raw.IndexOf('<!-- BEGIN VERBATIM SOURCE -->
```markdown
# COGNITIVE — Global Platform Upgrade & Universal Context Runtime Specification

**Версия:** 2.0  
**Дата:** 19 октября 2026  
**Статус:** целевая архитектурная спецификация; проектные возможности не означают, что все компоненты уже реализованы или проверены в production.  
**Репозиторий:** https://github.com/JewishTT/1  
**Базовый workstream:** `specs/030-global-platform-upgrade/`

---

## 0. Резюме решения

COGNITIVE следует довести до единого замкнутого контура **контекст расследования → обязательства исследования → сбор → неизменяемые доказательства → извлечение → нормализация → кандидаты сущностей и отношений → разрешение конфликтов и identity → утверждения с provenance → динамические инварианты сущностей и worldlines → воспроизводимые проекции → выводы → новая исследовательская ревизия**.

Это не означает, что каждый компонент должен быть переписан или что платформе нужны новые БД на каждый вид данных. Репозиторий уже содержит существенные части этого основания: `apps/acquisition`, `apps/bulk-ingestion`, `apps/interpretation`, `apps/admission`, `apps/shared`, `apps/projection`, `apps/science` и `apps/control-plane/context_engine`. Главная задача — устранить конкурирующие пути исполнения и разные источники истины, а затем связать существующие примитивы доказуемой сквозной цепочкой.

### Непереговорные архитектурные решения

1. **Одно исходное доказательство и один канонический ingestion seam.** Все исполнители отдают артефакты через общий `ArtifactSink` / Observation Gate. Никакой runtime не создаёт собственную независимую версию canonical observation и не пишет напрямую в canonical entity/projection stores.
2. **Контекст — это исполняемый исследовательский процесс, а не строка поискового запроса.** Естественный язык компилируется в версионируемую `ContextDefinition`, scope, temporal mode, policy, source universe, obligations, acceptance criteria, budget и условия остановки.
3. **Неизвестность и противоречие — полноценное состояние данных.** Пустой результат, недоступный источник, неподдерживаемый запрос, отсутствие данных, квалифицированное отсутствие, положительное/отрицательное свидетельство, противоречие и насыщение под заданным scope не взаимозаменяемы.
4. **Факты не затираются «победившим» значением.** Все исходные утверждения сохраняются; разрешение конфликта создаёт версионируемое решение или provisional resolution, а не удаляет конкурирующие сведения.
5. **Identity — решение admission/resolution, не similarity score.** Entity IDs не вычисляются из одного атрибута; merge/split являются append-only решениями с историей и возможностью реконструировать прежнюю интерпретацию.
6. **Онтологии динамичны, но изменения управляемы.** Новые типы и предикаты не теряются, однако обнаруженный термин не становится автоматически активным правилом или новым типом истины.
7. **Entity Knowledge Graph и Context Graph — разные концептуальные графы.** Первый отражает claims/relations об объектах мира и их временных срезах; второй — ход расследования: вопросы, gaps, hypotheses, obligations, actions, contradictions и решения.
8. **Графовая БД и vector DB не меняются по принципу «масштабнее звучит».** Каноническая запись остаётся в текущих authoritative stores; альтернативные backend-ы допускаются как rebuildable serving/computation projections после benchmark-а на реальном workload.
9. **Донор интегрируется только как проверяемая capability.** Ни одна библиотека, сервис, модель или набор данных не становится частью production лишь потому, что в репозитории есть код, README или зелёный unit test.
10. **Весь сквозной путь должен быть доказан на clean stack.** Наличие отдельных тестов и live demos не заменяет proof от API расследования до долговечного finding с восстанавливаемым provenance и изменившимся следующим действием.

---

## 1. Целевая end-to-end архитектура

```text
Analyst UI / API
      |
      v
Natural-language Intent Compiler
  -> versioned ContextDefinition + explicit ambiguity list
      |
      v
Context Engine / Research Process Kernel
  -> gaps + obligations + hypotheses + contradictions + budgets
      |
      v
Acquisition Planner
  -> source universe + capability matching + task plan + expected outcomes
      |
      v
Durable Frontier (PostgreSQL) -> Dispatcher -> capability-specific Runtime/Adapter
      |                                           |
      |                                           v
      |                               HTTP / APIs / feeds / search / browser /
      |                               archives / WARC / documents / datasets /
      |                               authorized specialist tools
      |                                           |
      +-------------------------------------------+
                                                  v
                                     AcquisitionArtifact contract
                                                  |
                                                  v
                                 ONE ArtifactSink / Observation Gate
                                   -> immutable raw object in S3
                                   -> Capture + Observation + Locator
                                   -> transactional outbox / canonical event
                                                  |
                                                  v
                                        Interpretation Operators
                       parse -> typed segments -> mentions -> normalization
                       -> entity references -> relation/assertion candidates
                                                  |
                                                  v
                              Semantic / Dynamic Ontology Layer
                  raw predicate retention -> mapping -> typed validation
                  -> open-world handling -> temporal/property policy
                                                  |
                         +------------------------+-----------------------+
                         |                                                |
                         v                                                v
                  Entity Resolution                               Conflict Detection
                  blocking/pair/collective                         value/type/relation/
                  hypotheses; no implicit merge                    temporal/logical/schema
                         |                                                |
                         +------------------------+-----------------------+
                                                  v
                                    Admission / Resolution Decision
                          append-only decision, reasons, support/refutation,
                          calibration, policy and model fingerprints
                                                  |
                                                  v
                                     Canonical Claim / Event Stream
                                                  |
                                                  v
                               EntityInvariant + Worldline Reducer
                      current state / temporal slices / relation signatures /
                      lifecycle / identity reference / revision digest
                                                  |
                         +------------------------+-----------------------+
                         |                                                |
                         v                                                v
               Rebuildable query projections                   Context Graph / Revision
               search, graph, metrics, TDA                     reevaluate obligations,
               timeline, spatial, reports                      next action, termination
                         |                                                |
                         +------------------------+-----------------------+
                                                  v
                                   Analyst Workspace + Findings
                   source-openable claims, conflicts, timeline, gaps, coverage,
                         decision history, next action, cost and limitations
```

### Важная деталь: это не строго линейный pipeline

Discovery, interpretation, identity resolution, conflict resolution, ontology alignment и контекстный движок образуют обратные связи. Новое отношение может открыть новую сущность; новая сущность — новую obligation; конфликт — уточняющий запрос; новая версия онтологии — повторную интерпретацию прежних наблюдений. Обратные связи не должны напрямую мутировать сырой evidence или обходить policy/admission.

---

## 2. Обязанности и авторитетность подсистем

| Подсистема | Единственная ответственность | Что ей запрещено |
|---|---|---|
| `ContextDefinition` | Зафиксировать цель, scope, temporal mode, source universe, политики и критерии результата | Молча переписывать прошлые определения расследования |
| Context Engine | Управлять вопросами, gaps, obligations, actions, hypotheses, contradictions, revisions и stopping | Самому собирать в сети или записывать факты об объектах мира |
| Acquisition Planner | Превращать obligations в план работ по возможностям источников | Объявлять неизвестный source capability доступным без проверки |
| Frontier / Dispatcher | Durable scheduling, бюджеты, leases, cooldown/retry, capability routing, backpressure | Использовать event bus в качестве очереди истины; выдавать недоступную capability за успех |
| Runtime / Adapter | Получить артефакт в разрешённых границах и вернуть метаданные | Записывать canonical observation, entity, claim или projection напрямую |
| ArtifactSink / Observation Gate | Сохранить исходные bytes, адресовать capture/record, обеспечить идентичность и lifecycle, инициировать публикацию | Интерпретировать семантическую истинность данных |
| Parser / Extractor / Normalizer | Создать воспроизводимые derived artifacts, spans и candidates | Изменять исходные bytes или самостоятельно сливать сущности |
| Ontology Registry | Хранить версии semantic packs, signatures, constraints и mapping policy | Отбрасывать неизвестные термины или задним числом менять смысл старых утверждений |
| Entity Resolution | Выдвигать identity candidates и append-only decision proposals | Делать транзитивную склейку только по цепочке score-ов |
| Conflict Engine | Находить несовместимость утверждений и готовить resolution proposals | Удалять контрсвидетельства или подменять конфликт низкой confidence |
| Admission | Решать, какие candidates приняты, отложены, отклонены или помещены в карантин | Воспринимать similarity, recency или centrality как само-достаточное доказательство |
| Claim/Event Stream | Canonical append-only история утверждений и допустимых событий | Представлять производную проекцию как источник истины |
| EntityInvariant / Worldline | Детерминированно строить ревизии сущности из накопленного потока | Назначать identity или утверждать истинность факта |
| Projection Fabric | Строить rebuildable search/graph/analytics/timeline views | Незаметно удовлетворять obligation stale-проекцией |
| Donor Runtime | Предоставлять изолированный алгоритм/адаптер за общим контрактом | Писать в canonical stores или обходить security/policy gates |

### Хранение: переиспользовать, не плодить источники истины

- **S3/MinIO:** immutable raw artifacts, WARC, documents, structured captures, outputs of tools as bytes.
- **PostgreSQL:** authoritative operational state, frontier, capture/observation metadata, claim/decision/context revisions, identity decisions, outbox и relational canonical state в рамках принятого разделения ownership.
- **Kafka-compatible event backbone:** транспорт событий и replayable delivery, не authoritative queue.
- **OpenSearch/BM25:** базовый полнотекстовый retrieval projection.
- **ClickHouse:** метрики, временные ряды, расходы и агрегаты, где это соответствует назначению.
- **Neo4j:** только serving projection, если существующий `GraphProjection` contract/конфигурация действительно подключены; это не второй canonical graph store.
- **Redis:** только cache/lease acceleration там, где он реально используется; корректность должна восстанавливаться из PostgreSQL.
- **Temporal:** длительные investigation/rebuild/recrawl workflows, не hot-path обработки каждого сообщения.
- **Qdrant/pgvector:** optional retrieval profile после quality/cost benchmark-а, не предпосылка базовой архитектуры.
- **JanusGraph + Cassandra/Scylla:** экспериментальный distributed graph profile при доказанной потребности в соответствующих нагрузках; не миграция canonical truth по умолчанию.

Каждый объект должен иметь одного canonical owner, а каждая проекция — `ProjectionManifest` (inputs/offsets/source cut, builder/operator version, output digest, staleness, status, kill switch и tested rebuild route).

---

## 3. Layer-0 — универсальный, контролируемый сбор

### 3.1 Существующие основания

В репозитории уже есть каталог YAML-источников (аудит каталога указывает 146 определений), Python HTTP executor, Rust worker crates, dispatcher/frontier, source/connector registries, ArtifactSink, Observation Gate, `apps/bulk-ingestion`, Common Crawl/Wayback/WARC и runtime-интеграции (SearXNG, Airbyte, BBOT, external tools). Важнейший gap — не просто добавить ещё источники, а связать все поддерживаемые семейства с одним доказательным путём.

### 3.2 Канонический контракт задания

`AcquisitionTask` vNext должен ссылаться на:

- `tenant_id`, `investigation_id`, `context_id`, `context_revision_id`;
- `obligation_id`, `action_id`, `task_id`, `parent_work_id`, `seed_provenance`;
- `source_id`, `runtime_ref`, `capability_requirements`, `query_ref` и query parameters;
- `target_scope`, `access_mode`, `policy_snapshot_ref`, credential reference;
- temporal/geographic/scope filters и requested historical depth;
- `max_bytes`, `max_records`, timeout/deadline, request and compute budgets;
- retry/idempotency key, checkpoint/cursor reference, scheduled time, priority;
- ожидаемые виды результата и критерии acceptance.

Секреты никогда не входят в event payload, query log или donor manifest — только ссылки на управляемое хранилище секретов.

### 3.3 Семейства исполнителей

1. HTTP, RSS, sitemap и открытые API.
2. Federated search/discovery с хранением исходного ответа поиска и отдельными locator-ами результатов.
3. Common Crawl, Wayback, WARC, byte-range архивация и historical replay.
4. Structured connectors (включая Airbyte-подобные): RECORD отдельно от STATE/LOG/TRACE, checkpoint только после durable persist результатов, которые он покрывает.
5. Browser/document engines для публичного контента, недоступного простому HTTP-парсеру, с отдельным пулом и лимитами.
6. Bulk datasets, files, object stores, tabular feeds и локальные разрешённые коллекции.
7. Разрешённые специализированные источники инфраструктуры/CTI/реестров.
8. Внешние исследовательские инструменты в изолированном профиле; типизированный output stream, bounded stdout/stderr, pinned binary/container digest и run manifest.

### 3.4 Безопасность и надёжность fetch boundary

- URL schemes allowlist; DNS A/AAAA validation; отбрасывание loopback/private/link-local/metadata/reserved ranges по политике.
- Проверка каждого redirect-hop и защита от DNS rebinding (проверенный адрес должен совпадать с endpoint соединения).
- Streaming response reads с лимитом объёма до полной буферизации; decompression/archive bomb limits; connection/read/total deadlines.
- Rate policy per tenant/source/host, jittered retries, retry budgets, domain/source cool-down и backpressure.
- Явное соблюдение source access policy: не обходить логин, CAPTCHA, paywall, антибот-защиту или иные access controls; недоступность фиксировать как результат policy/source, не маскировать другим методом.
- Egress/network/process/fs isolation для браузеров и сторонних tools.
- Необходимы отдельные статусы: policy-denied, unsupported, unavailable, failed, partial, no-result, accepted.

### 3.5 Единый доказательный выход

Каждый executor возвращает `AcquisitionArtifact` (raw bytes + locator metadata + runtime/source/version). `ArtifactSink` должен:

1. Сохранить raw object до создания публикации.
2. Вычислить digest и content-addressed ref.
3. Создать deterministic capture/observation identity по утверждённой версии identity scheme.
4. Поддержать parent capture + несколько record observations, с locator вида JSON Pointer/table cell/WARC record/page span.
5. Сохранить metadata и контекст принадлежности/происхождения.
6. Записать outbox/event delivery atomically в предусмотренном transaction seam.
7. Возвращать acknowledged publication details, не ограничиваться логом.
8. Гарантировать idempotent replay: повтор не увеличивает coverage/evidence independence/cost learning и не порождает лишних semantic revisions.

**Запрет:** source-specific worker не вправе самостоятельно монтировать вторую схему observation event или самостоятельно создавать доказательство без реально сохранённого `raw_ref`.

---

## 4. Layer-1 — interpretation, normalization и candidate generation

### 4.1 Воспроизводимые операторы

Все parser/extractor/normalizer должны вызываться через общий `OperatorResult`, содержащий:

- статус выполнения, outputs, warnings/errors и partial-coverage information;
- input observation IDs, content digests и spans;
- operator name/version, parameters/config/model fingerprint;
- output digest, deterministic/replay mode и resource consumption;
- language/encoding/locale, data format и semantic version references.

Переобработка другим parser-ом не изменяет старый derived artifact: она создаёт новую ревизию с `supersedes` и сохранённым output.

### 4.2 EvidenceSpanRef — обязательное условие grounded output

Нельзя использовать одно поле `offset` для byte offset, character offset, segment index или page number. Каждый mention/claim/finding ссылается на типизированный span:

- character range + encoding;
- PDF/image page + coordinate system + bounding box;
- table reference + row + column + header path;
- JSON pointer/structured record locator;
- audio/video time range + track/frame;
- WARC offset + record digest;
- geometry reference;
- source locator/fragment.

Все spans включают `observation_ref`, `blob_digest` и `selector_semantics_version`. Несовместимые версии selector semantics нельзя суммировать или преобразовывать без явной conversion policy. Если исходный span не восстановить — finding маркируется partial/unresolved, а не получает синтетический offset.

### 4.3 Две модели сохранения

**Evidence layer:** immutable raw/source representation и извлечённые literal observations.  
**Interpretation layer:** normalized forms, translations/transliterations, parsed dates, alias candidates, entities/relations/events — с versions и lineage на source form.

Нормализация не переписывает оригинальную строку. Например, ФИО на нескольких языках, транслитерации и alternate scripts хранятся как наблюдавшиеся варианты с provenance и mappings; canonical representation — derived object, который можно пересчитать.

### 4.4 Ничего неизвестного не выбрасывать

`Mention`, `EntityReference`, `RelationCandidate`, `ClaimCandidate` должны хранить исходную формулировку даже при неизвестном типе/предикате. Типы результата оператора должны различать:

- unsupported format/operator;
- successful parse with no candidates;
- partial parse;
- malformed input;
- timeout/resource limit;
- quarantine/security refusal.

Неизвестный предикат — valid open-world record с `mapping_status=unknown_predicate`, не ошибка, требующая удалить запись.

---

## 5. Динамические онтологии и сущности-инварианты

### 5.1 Онтология как версионируемый контракт семантики

`OntologyPackRevision` описывает:

- entity-type signatures и property definitions;
- relation predicate, direction, arity, participant roles, domain/range hints;
- cardinality, exclusivity, symmetry/inverse/transitivity;
- temporal semantics, valid-time/known-time interpretation;
- unit/normalization/mapping rules;
- conflict compatibility rules, evidence requirements и admission policies;
- source-family mappings, aliases, vocabulary alignments;
- provenance, revision digest, validator/rule fingerprints.

Lifecycle: `DRAFT → PROPOSED → VALIDATED → ACTIVE → RETIRED` (с явными governance decisions). Активная ревизия онтологии привязывается к контексту/оператору и не переинтерпретирует прошлое задним числом.

### 5.2 Управляемое расширение онтологии

1. Входящие observation/claims приносят неизвестные raw types/predicates.
2. Ontology gap monitor группирует повторяющиеся неизвестные термины и их контексты.
3. Mapping proposer предлагает эквиваленты/подтипы/связанные предикаты, сохраняя альтернативы и доказательства.
4. Structural/temporal rules и constraints проверяются на frozen fixtures и конфликтных примерах.
5. Approved ontology revision становится active для заданного scope/version.
6. Re-interpretation создаёт новые derived claims/invariants; старые mapping/claims сохраняются, а новые связи помечаются revision lineage.

Similarity между словами не означает равенство понятий. Автоматический онтологический mining может предлагать, группировать и тестировать термины, но не должен без governance превращать предположение в активную истину.

### 5.3 EntityReference vs EntityInvariant

- **Mention:** участок источника, где сказано нечто.
- **EntityReference:** гипотеза о том, к кому/чему относится mention.
- **ResolutionCandidate:** кандидат объединения identity refs с blocking trace, component vector и противосвидетельствами.
- **ResolutionDecision:** append-only решение admit/defer/reject/merge/split/reopen, принятое по явной policy.
- **EntityInvariant:** стабильный `entity_id` плюс ревизируемая, выводимая из accepted stream реляционная структура, свойства, time slices, identity decision refs и integrity digest.
- **Worldline:** история утверждений/событий и смен состояния во времени, не уничтожающая прежние интерпретации.

`EntityInvariant` — не «одна строка, где лежит окончательная истина». Это versioned relational invariant over evidence and policy. Его `current`/history view может показывать спорные поля, temporal alternatives и unknowns; это не повод выбрать одно значение молча.

### 5.4 Entity identity и масштабное resolution

- Blocking/LSH/index-based candidate generation must avoid all-pairs O(N²), but every candidate retains trace of its blocking method.
- Pairwise score yields candidate ranking, not a merge decision.
- Collective/graph-aware methods may propose candidates and contradictions, but `A≈B`, `B≈C` is not automatically `A=C` if A–C evidence is inconsistent.
- Same domain/address/co-occurrence is contextual evidence, not universal identity proof.
- Merge/split decisions append revisions and aliases; existing claims store the resolution interpretation they were created under.
- Correcting a false merge must not rewrite prior source claims; it changes current entity grouping and regenerates projections through explicit supersession/rebuild.

---

## 6. Conflict Detection and Resolution — first-class subsystem

Это обязательный компонент fusion, а не постобработка перед показом графа.

### 6.1 Что такое contradiction

`Conflict` — обнаруженная несовместимость набора claims under a stated ontology, temporal frame, scope and compatibility policy. Он не равен `low_confidence` и не всегда означает, что один source ошибается.

Виды conflict detection:

1. **Value conflict:** одна сущность, одно свойство и перекрывающийся validity scope, несовместимые значения (например, разные одновременно заявленные величины).
2. **Type conflict:** взаимоисключающие candidate types или несовместимые property/type constraints.
3. **Relation conflict:** противоположные/несовместимые relation assertions при одной и той же роли и временном интервале.
4. **Temporal conflict:** несовместимые временные интервалы, порядок событий, timestamp semantics или interval constraints.
5. **Logical/ontology conflict:** нарушены ограничения совместимости, arity, role signatures, cardinality/exclusivity, declared rules.
6. **Identity conflict:** общая entity candidate имеет противоречивые идентификаторы или merge приводит к несовместимости attributes.
7. **Provenance conflict:** apparent corroboration с разных URLs оказывается одним syndicated/root source; source lineage не независим.
8. **Scope/context conflict:** утверждения относятся к разным jurisdiction, assets, roles, units, currencies, definitions or investigative scopes, хотя surface label похож.

### 6.2 Сначала проверить сопоставимость, потом объявлять конфликт

Перед конфликтным сравнением система обязана сравнить:

- resolved subject/participants and identity revision;
- predicate mapping + ontology version;
- unit, currency, period, jurisdiction and qualifier;
- valid-time intersection and timestamp precision;
- source type, capture time, publication time, claimed event time;
- dependency-group/root and whether claims are derived from the same upstream material;
- whether predicate pair is declared mutually exclusive or simply complementary.

Пример: «работал CTO в 2019–2021» и «стал VP Engineering в 2022» — это temporal transition, а не обязательно contradiction. Два разных текущих значения salary также нельзя объявить конфликтом, пока не сопоставлены currency, compensation period, base/total semantics и validity time.

### 6.3 Контракт ConflictRecord

```text
ConflictRecord
  conflict_id, tenant_id, context_id?, entity_or_candidate_refs[]
  conflict_kind, severity, status
  claim_refs_supporting_each_side[]
  ontology_pack_ref + compatibility_rule_id/version
  valid_time_overlap, known_time, scope_ref
  evidence_dependency_groups[]
  dimension_vectors: temporal / provenance / semantic / identity / source_quality
  detection_operator + version + parameter fingerprint
  resolution_criteria, opened_from_revision, current_revision
  resolution_proposal_refs[], decision_refs[], supersedes/refers_to
```

`status`: `OPEN`, `INVESTIGATING`, `PROVISIONALLY_RESOLVED`, `ADJUDICATED`, `REOPENED`, `NOT_A_CONFLICT` — каждый переход сохраняется с причиной. `NOT_A_CONFLICT` тоже объясняет, что выяснилось: temporal non-overlap, different scope, different units, non-exclusive predicates, duplicate/syndicated evidence etc.

### 6.4 Семантика поддержки

Каждый claim сохраняет независимые `support_positive[]` и `support_negative[]`. Производный эпистемический статус — четырёхзначный:

- `NEITHER`: нет ни положительной, ни отрицательной поддержки;
- `TRUE_ONLY`: есть положительная, но нет отрицательной поддержки;
- `FALSE_ONLY`: есть отрицательная, но нет положительной поддержки;
- `BOTH`: существуют и положительные, и отрицательные поддержки — реальное состояние contradiction.

`BOTH` не сводится к low confidence. Источник, который просто ничего не сообщил, не является отрицательным свидетельством.

### 6.5 ConflictResolver — стратегия предлагает решение, не удаляя данные

Поддерживаемые policy plug-ins:

- **Authority/credibility-weighted:** вес надёжности источника с явной областью применимости (source × predicate × jurisdiction × timeframe), калибровкой и версией профиля.
- **Temporal applicability / most recent:** сравнение именно заявленной validity/source time по правилам данного предиката, а не простая сортировка по `captured_at`.
- **Independent corroboration / voting:** голосование по lineage roots или evidence dependency groups, не по сырым числам сайтов, копирующих один источник.
- **Ontology/constraint-based:** проверка cardinality, exclusivity, temporal constraints, units, roles и допустимых преобразований.
- **Source-of-record precedence:** только если профиль предиката задаёт официальный/авторитетный source-of-record.
- **Analyst adjudication:** выбор/отказ с actor, rationale, conflict snapshot и expected context revision.
- **Abstain / request discriminating evidence:** сохраняет `BOTH` и открывает obligation, когда данные не позволяют честно разрешить конфликт.

Результат resolver — `ResolutionProposal` с competing alternatives, supporting/refuting evidence, strategy/version, component vector, assumptions, sensitivity, policy ref и uncertainty. После него admission создаёт append-only `ResolutionDecision`. Provisional winner не удаляет проигравшую сторону и не отменяет возможность повторного открытия.

### 6.6 Почему нельзя просто выбрать «most recent»

Последний capture — это время поступления в систему, а не время истинности. Поздно обнаруженный документ 2021 года может быть действительнее страницы 2026 года для вопроса о 2021 годе. Свежесть — отдельный компонент reliability/utility, не universal truth rule.

### 6.7 Семантика Semantica, которую нужно извлечь и проверить

Текущий GitHub README Semantica документирует `ConflictDetector`, `ConflictResolver`, `SourceTracker`, стратегии `credibility_weighted`, `most_recent`, `voting`, обнаружение value/type/relationship/temporal/logical conflicts, а также duplicate detection и merge history. Это отличная **кандидатная реализация для benchmark-а**: адаптировать detector как producer `OperatorResult` и resolver как generator `ResolutionProposal`. Нельзя позволять donor `EntityMerger` напрямую переписывать COGNITIVE identity authority. Прежде чем принять код, зафиксировать точную upstream revision, license/asset inventory, dependencies, actual test behavior, idempotency, temporal handling и lineage preservation.

Source: https://github.com/semantica-agi/semantica (README, conflict and deduplication sections).

---

## 7. Bitemporal lifecycle и вопросы «что было известно тогда?»

Все временные значения должны различать:

- `source_published_at` — когда источник, по его словам, опубликовал материал;
- `source_valid_from` / `source_valid_until` — период, на который claim претендует;
- `source_observed_at` — когда, по утверждению источника, наблюдалось событие;
- `captured_at` / `fetched_at` — когда платформа получила bytes;
- `recorded_at` / `known_at` — когда данные стали частью canonical knowledge state;
- `processed_at` — когда конкретный operator run их обработал;
- `projected_at` — когда projection догнала событие.

Нельзя подставлять `now()` вместо неизвестного времени. Нельзя приравнивать source time к capture time или делать causal claim только из temporal precedence.

Запросы принципиально различаются:

- `CURRENT`: текущая реконструкция под текущими доказательствами и активными политиками;
- `AS_OF(known_time)`: какое состояние knowledge system действительно держала на тот момент;
- `INTERVAL(valid_from, valid_until)`: какие claims считаются действующими в выбранном временном интервале.

Поздний capture может уточнить текущую реконструкцию прошлого `INTERVAL`, но не изменяет историю `AS_OF` на время до регистрации этого capture.

Life-cycle entity строится из датированных утверждений и событий; событие вроде рождения показывается только если существует пригодный source-backed claim. Система не синтезирует начальное жизненное событие, если источник не установил его.

---

## 8. Донорская программа: максимум полезной функциональности, минимум несовместимых систем

### 8.1 Главный принцип

**Максимизируем извлекаемые проверяемые capabilities, а не количество скопированных репозиториев.** Один mature donor может дать несколько adapters/operators, но не может становиться параллельной платформой с собственной canonical database, identity model и событийной схемой.

Обязателен `donors/registry.yaml`, который объединяет существующие 11 каталогов `docs/architecture/donors/00–10`, vendored trees, зависимости и новые кандидаты. Для каждой capability указать:

- canonical upstream URL, owner, pinned commit/tag/digest, дата проверки;
- license для кода отдельно от моделей, весов, datasets, docs, sample assets и data sources;
- какой файл/алгоритм переносится и что из donor не переносится;
- target layer + COGNITIVE contract/operator ID;
- input/output semantics, side effects and access needs;
- адаптер/путь вызова production;
- contract/unit/integration/live/e2e test IDs;
- benchmark baseline and measured quality/cost/latency;
- feature flag, kill switch, rollback, owner, update policy;
- status: `CANDIDATE`, `AUDITED`, `ADAPTED`, `TESTED`, `WIRED`, `LIVE_PROVEN`, `DEFERRED`, `REJECTED`, `METHODOLOGY_ONLY`.

### 8.2 Донорская матрица по функциональным вертикалям

| Вертикаль | Донорские примитивы | Где применить | Ограничение |
|---|---|---|---|
| Discovery / OSINT | SpiderFoot, Maigret, Sherlock, theHarvester, Sublist3r, domain/email/phone modules already catalogued | Capability-specific acquisition operators and source-query templates | Только допустимый режим работы и policy gate; результаты являются candidates, не identity truths |
| Search + open-web | SearXNG, current source providers, OpenAleph-type patterns | Search runtimes, result locators, source provenance, replay | Не переиспользовать donor-owned storage or event model |
| Archive/history | Common Crawl, Wayback CDX, WARC adapters, Browsertrix where approved | Historical fetch, replay, archive-aware temporal observations | Licensing/data terms reviewed separately; Common Crawl terms are not treated as generic open licence |
| Structured connectors | Airbyte protocol; RECORD/STATE/LOG/TRACE discipline | Cursor-based connector runtime with persist-before-checkpoint semantics | Only RECORD-derived evidence; STATE remains control metadata |
| Document understanding | Docling, GROBID, existing PDF/DOCX/XLSX parsers, OCR candidates | Document operators with page/table spans and typed outputs | Pin model/weights license; ungrounded layout locations are partial |
| Entity resolution | Existing resolution engine, Fellegi–Sunter/Splink as comparator, normalization libraries | Candidate generation and comparative evaluation on labelled pairs | External matcher cannot commit a merge; benchmark before promotion |
| Semantic fusion | Semantica conflict/normalization/dedup/ontology/provenance APIs | `ConflictDetector` operator + resolution proposals + mapping suggestions | Adapt to platform contracts; donor merger must not mutate canonical identities |
| Ontology pack / analyst UX | kafSIEM domain-pack approach, typed API, replay/provenance desk, graph/map UX | Versioned YAML semantic packs, detector/query/view/report declarations, UI patterns | Current kafSIEM repo may differ from legacy vendored CSS source; exact origin/revision must be pinned; SQLite remains donor-local |
| Epistemic review | AEGIS-like observation/evidence/assumption/judgment separation, dissent and Devil's Advocate workflow | Analyst review for high-impact conflicts and assumptions; structured alternative assessments | Methodology/review mechanism, not an automatic truth engine; verify exact intended AEGiS upstream |
| Temporal forensics | Timesketch-like timeline and event correlation patterns | Timeline investigation and time-window aggregation | Temporal order is not causality; carry timestamp type and source semantics |
| Spatial analysis | H3, DuckDB Spatial, geo extractors | Geometry-aware coverage, spatial joins, event maps | Optional, benchmarked and precision-aware; no inferred residential location without policy basis |
| Graph analytics/TDA | Current graph/TDA code, GUDHI, giotto-tda, Raphtory candidates | Topology/centrality/community features as derived artifacts | Must pick one production owner per operation; resolve AGPL/GPL deployment; features never perform identity merges |
| Retrieval/fusion | Existing BM25/bm25s + query planner; clean-room RRF comparison; optional Qdrant/pgvector | Retrieval of source-backed spans and related claims | Freeze judged query set before selecting default; vector service isn't mandatory baseline |
| Operations/coverage UX | kafSIEM flow/replay/provenance drawers, typed OpenAPI patterns, current COGNITIVE UI workbench | Source health, investigation trace, conflict triage, timeline, graph provenance | UI must show staleness/unknown/conflict, not just a polished singular graph |
| Science / economic / network simulation | existing `apps/science` and reviewed simulation donors | Explainable analytical features from source-backed inputs | Simulations are hypotheses/derived features, not source facts or evidence of intent |
| Spec-ops research tools | isolated-lab donors from existing donor catalogue | Scope-bound authorised testing/validation in a dedicated lab profile | Never mix exploit/pentest runtimes into routine public-source collection; strict scope + audit gate |

### 8.3 kafSIEM — what to take

The currently discoverable upstream `scalytics/kafSIEM` describes an evidence-linked entity graph, Kafka traffic/OSINT collector, YAML domain packs for drones/SCADA, typed OpenAPI, analyst topology/map/replay desk and provenance links to source records. This is a promising donor for **the pack contract and analyst workflows**: versioned declarative ontology/detector/query/view/map/report definitions, event-record provenance UX, replay studio interactions and typed API patterns.

What not to import as a second authority: its SQLite graph/store, collector process, independent entity types, and broker-specific event schemas. COGNITIVE already has its own durable frontier, canonical claims/context state, Observation Gate, event catalog and query/projection contracts. The current COGNITIVE frontend contains legacy kafSIEM CSS files sourced from a different URL (`nicoreed/kafSIEM`), so first resolve provenance and pin the exact upstream lineage before copying more code.

Sources: https://github.com/scalytics/kafSIEM and `apps/webapp/src/styles/donors/kafSIEM/` in COGNITIVE.

### 8.4 AEGiS — exact identity must be confirmed before code import

The name is ambiguous. COGNITIVE's existing donor catalogue includes `aegisceo/phone-osint-framework`, which is a phone-oriented OSINT module family and not a knowledge-conflict engine. A different public project, `ChristopherKahler/aegis`, describes epistemic review for code-audit findings: observation/evidence separation, dissenting review, assumption fragility and explicit response to disagreements; its README describes v0.1 as a specification set without runtime execution. That can inform review UX and conflict-governance methods but must not be represented as a validated data fusion library.

Until the intended upstream is pinned, record `AEGiS` as `UNVERIFIED / URL_REQUIRED` in donor registry. Do not select a project by name similarity. If the intended donor is the epistemic-governance project, begin with a methodology-only adapter specification and benchmarkable schemas for evidence-side comparison, not a claim that it can automatically adjudicate source truth.

Sources: https://github.com/aegisceo/phone-osint-framework ; https://github.com/ChristopherKahler/aegis.

### 8.5 Semantica — the main conflict/fusion candidate

The current Semantica README documents:

- `ConflictDetector` for value, type, relationship, temporal and logical conflicts;
- `ConflictResolver` strategies including credibility-weighted, most-recent and voting;
- `SourceTracker`, normalization, semantic deduplication, entity merge history;
- ontology generation/validation with OWL/SHACL/SKOS;
- provenance/lineage; context graph and graph analytics;
- pipeline stages covering ingestion, parsing, normalization, extraction, conflict detection, deduplication and graph building.

Recommended extraction order:

1. Benchmark the normalizers and conflict detector independently against COGNITIVE fixtures.
2. Wrap outputs in `OperatorResult`; retain input claim IDs, evidence spans, source dependency groups and policy fingerprints.
3. Adapt resolver strategies to produce `ResolutionProposal`; let COGNITIVE Admission / DecisionRecord commit outcomes.
4. Compare donor dedup against COGNITIVE blocking/pairwise/collective resolver on a frozen labelled corpus.
5. Extract ontology mapping/validation primitives behind `OntologyPackRevision` rather than importing a second ontology authority.
6. Preserve a COGNITIVE canonical stream and use the donor graph builder only as an optional derived representation/comparator.

A donor strategy such as `most_recent` must not be accepted without validity-time semantics; `voting` must count independent lineage roots, not syndicated document copies; a confidence score must never replace four-valued epistemic support. License, dependency assets and exact pinned revision are mandatory WP0/WP11 evidence, not assumed from package availability.

Source: https://github.com/semantica-agi/semantica (README, `semantica.conflicts`, `semantica.deduplication`, `semantica.ontology`, `semantica.provenance`).

### 8.6 MoranaLabs / JanusGraph / ScyllaDB — architecture pattern, not automatic migration

Treat the suggested JanusGraph + Cassandra/ScyllaDB architecture as a **candidate graph-serving/computation profile** for workloads that actually require distributed adjacency traversal at measured scale. Before adopting it:

- measure vertex/edge cardinality, degree skew, traversal fanout/depth, write/read/update mix, time-sliced edges, tenant and ABAC filtering cost;
- benchmark high-degree and adversarially skewed entities, not only uniform synthetic graphs;
- include index backend consistency/rebuild, graph mutations, tombstones, schema changes, backup/recovery, operational toil and total system complexity;
- run parity against the current graph/projection contract and include a kill switch;
- keep canonical evidence/claims and research state in their authoritative stores.

The JanusGraph ecosystem documents ScyllaDB as a storage-backend option, but that alone does not demonstrate superiority for COGNITIVE's graph queries. No graph-store migration before scale baselines and representative query benchmarks. Qdrant/pgvector likewise belongs to an optional retrieval profile, not a parallel truth store.

Source: https://docs.janusgraph.org/storage-backend/scylladb/.

### 8.7 Донорный promotion gate

A candidate moves to `LIVE_PROVEN` only if all are true:

1. upstream URL/commit/asset license manifest is complete;
2. `OperatorResult` adapter exists;
3. no direct writes to canonical state;
4. every output is linked to input observations and spans or labelled partial;
5. failure/empty/unsupported/partial/timeout are distinguishable;
6. contract + unit + integration + live/replay tests pass;
7. the feature appears in an actual production call path;
8. quality/cost/latency gain versus baseline is measured on representative data;
9. disabling it resumes the prior path without deleting evidence;
10. owner, upgrade policy, monitoring and rollback are documented.

---

## 9. Context Engine as the research process kernel

The platform must not be a crawler whose result is a pile of records. The Context Engine owns what the investigation is trying to establish and what the system should do next.

### 9.1 ContextDefinition versus live InvestigationContext

`ContextDefinition` is immutable/versioned: objective, compiled intent AST, target/scope, time mode, allowed source universe, ontology/reasoning profile, output requirements, budgets, access policy, freshness, quality and stop conditions.

`InvestigationContext` is the durable mutable-by-revision execution state: active revision, hypotheses, obligations, unknowns, contradictions, attempted actions, findings, cost, coverage, blockers and stop condition.

Changing intent or scope either pins the in-flight investigation to the existing definition version or emits an explicit rebase to a new version. Old revisions are never silently reinterpreted.

### 9.2 ResearchObligation is not an acquisition task

An obligation defines what knowledge is required and how sufficiency is evaluated. It contains trigger, parent gap/hypothesis/conflict, required outcome, acceptance predicates, source/capability requirements, unknown dependencies, priority vector, cost estimate, attempts, marginal gain and stop/satisfaction rules.

One obligation may generate many tasks; one captured observation may satisfy more than one obligation if it legitimately covers them. Completion of a task never automatically satisfies the obligation. Empty output never closes a gap without evaluation against its criteria and coverage assumptions.

### 9.3 Process-centric next action

After each outcome the kernel recomputes:

- which obligations remain open, satisfied, partial, blocked or superseded;
- which claims/hypotheses gained or lost support;
- new/open/reopened contradictions and unresolved identities;
- source coverage, independence and freshness;
- the actions that are eligible, suppressed, blocked or require approval;
- component vector for each action (expected information gain, hypothesis discrimination, relevance, quality, independence gain, novelty, freshness, probability semantics, cost, latency, repeat penalty, failure rate, resource risk, policy penalty);
- reason to continue, pause, become scoped-saturated or close.

Hard access/scope/tenant/budget constraints are filters before utility ranking; no high expected gain can override them. Any adaptive/LLM component may propose an ordering but cannot bypass deterministic policy. If there is no provider-evaluation substrate, start with the deterministic baseline and make LLM-assisted query expansion an optional evaluated capability later.

### 9.4 Stop conditions

Never stop because the queue is empty, retries are exhausted, a task completed, a score is low or an output list is empty. Permitted stop outcomes include explicit analyst closure, declared acceptance criteria met, policy/budget block, missing capability, or **saturated under stated scope/source universe** with measured marginal gain. The stop report lists residual unknowns, uncovered scope, unavailable sources and non-executed tasks.

---

## 10. Сквозной пример: source-backed dossier (только разрешённые данные)

Пример должен быть fixture/authorized case; он не предполагает массовое построение личных профилей по частным, чувствительным или закрытым данным. Публичные записи об имуществе, персональные контакты и семейные связи проходят отдельную policy/legal-basis gate, применяются minimization/redaction, и не расширяют scope автоматически.

1. Analyst в `Investigations` вводит естественный язык: «Подготовить проверяемое досье на публичного руководителя организации для due diligence; включить публичные профессиональные роли, официальные корпоративные связи, публикации/интервью и временную историю; не собирать частные контакты или нерелевантные чувствительные сведения».
2. Intent Compiler сохраняет исходную формулировку, строит AST: target candidates, scope, timeframe, permitted source families, output sections, evidence requirements, budget и stop rules. Неоднозначное ФИО породит несколько `EntityReference`/hypotheses с планом disambiguation, а не немедленный merge.
3. Context Engine создаёт obligations: resolve identity; fetch official bio and filings; collect public interviews/articles; build verified employment/board-role timeline; find and validate official company affiliations; identify uncovered source classes; detect contradictions.
4. Planner выбирает из Source Catalogue и capability registry: official registries / organization pages / search indexes / reputable publications / archives / permitted public APIs. Each task has context and obligation refs, limits and policy snapshot.
5. Frontier schedules, isolated runtimes collect. Every result reaches `ArtifactSink`; raw bytes are durable and content-addressed; page/result/document locators are reproducible. Failed and denied sources remain visible.
6. Parser creates segments and typed spans. Extractors create mentions and relation candidates (`Person — held_role — Role`, `Person — affiliated_with — Organization`, `Person — quoted_in — Publication`) with valid-time candidates and direct evidence spans.
7. Normalizer retains original scripts/aliases and normalized variants. Resolver proposes identity matches with comparison vector, negative evidence and calibration; only the admission decision assigns/extends stable entity identity.
8. Ontology aligns known predicates; unknown relation labels remain stored and become ontology-gap candidates. Incompatible relation signatures are flagged, not dropped.
9. Conflict Engine compares claims with time, jurisdiction, source dependence and role semantics. «Director in 2021» vs «Chair in 2024» is likely a timeline change; competing concurrent official roles may create a conflict. Both supports and source spans remain visible.
10. Accepted claims enter the canonical stream. EntityInvariant/Worldline produces current state and historical roles with revision digest; graph/search/timeline are rebuilt or incrementally updated as declared projections.
11. Context Graph advances revision; satisfied obligations close with evaluator evidence and new gaps/contradictions open. A new action may query an official registry or retrieve a dated publication that discriminates between competing claims.
12. UI presents timeline, relationship graph, source-backed findings, competing claims, policy warnings, unknowns and coverage. Every node/edge opens its proof. Analysts can inspect the previous knowledge state `AS_OF(t)` and current reconstruction separately.
13. If the birth date is unsupported, the timeline shows it as unknown; it never invents a birth event as a lifecycle start. A new connected entity (business partner, organization, publication) is added only through an evidence-backed relation candidate and identity/admission path.

---

## 11. Полномасштабная валидация: что означает «готово»

### 11.1 Golden end-to-end case suite

1. **Public/authorized dossier:** natural-language context -> source plan -> observed documents -> span-backed claims -> identity resolution -> lifecycle/timeline -> derived graph -> findings -> next action changes.
2. **Company/ownership investigation:** official registry and filing sources; entity/role/ownership claims, effective dates, source dependence, negative/unknown coverage; no unsupported beneficial-owner conclusion.
3. **Infrastructure intelligence (passive/authorized scope):** domain/IP/certificate/source facts; shared certificate is relation evidence, not automatic infrastructure-cluster identity; change histories are temporal.
4. **Document-intensive case:** PDF table, HTML article, JSON result and WARC record; every finding opens exact source span.
5. **Contradiction corpus:** value/type/relation/temporal/logical/identity conflicts, copied-source duplicates, mismatched currencies/periods, conflicting roles with disjoint intervals, invalid ontology constraints and genuinely unresolved `BOTH` cases.
6. **Ontology evolution:** unknown predicates round-trip; mapping proposal is reviewed/validated; new active revision produces new derived artifacts without mutating old claims.
7. **Late data / bitemporal:** acquire a 2026 document with valid-time 2020; assert `CURRENT`, `AS_OF(2025)` and `INTERVAL(2020)` differ correctly.
8. **Failure/restart/replay:** fail after raw write, after outbox placement, after broker ack and during downstream projection; recovery is idempotent, orphan artifacts are reconciled without invented placement.
9. **Tenant/safety boundary:** cross-tenant refs, SSRF, redirect-to-private, DNS rebinding, archive bomb, secret redaction, access-denied paths and approval-required actions.
10. **Donor disable/rollback:** run baseline, enable donor, compare outputs, disable donor; canonical evidence and prior derived revisions remain intact.

### 11.2 Mandatory assertions

- 100% of accepted claims/findings in the fixture suite resolve to content address + typed span, or are explicitly partial/unresolved.
- The same evidence replay does not create a second semantic result or inflate coverage, source independence, action-learning or revisions.
- A new parser/model/policy version emits a new derived revision; raw digest remains unchanged.
- A high identity score, centrality or graph proximity cannot commit a merge alone.
- Conflicting claims remain individually queryable even if a provisional value is selected for a particular view.
- `BOTH` is distinct from low confidence and from no result.
- No zero-result universal query becomes qualified absence unless source detection power and coverage conditions are declared and met.
- Every projection has a tested rebuild and staleness contract.
- Disabling a donor cannot delete raw/derived evidence.
- Every investigation terminal state carries stop reason, residual unknowns and unexecuted scope.
- Every benchmark prints exact input corpus, configuration, operator/model versions, exit status, runtime/resource figures and source count. No metric is fabricated; unavailable measures are `null` with a named reason.

### 11.3 Metrics to measure before setting performance targets

Acquire: successful durable artifact rate, source availability, error categories, retry inflation, byte/record throughput, capture-to-observation latency, raw storage cost, dedup ratio, source and tenant pressure.

Interpretation: parser success/partial/unsupported rates, resolvable span rate, operator throughput, reprocessing cost, normalized variant coverage, unknown-predicate rate.

Resolution/fusion: candidate recall, pairwise precision/recall, false merge/split rates, calibrated reliability, independent lineage-root count, contradiction precision/recall, analyst overturn rate and merge-split correction cost.

Graph/context: invariant digest reproducibility, context revisions per meaningful change, projection lag/rebuild duration, query latency by degree/fanout, temporal correctness, action marginal gain, repeated-work suppression, coverage attainment and costs by dimension.

Set p50/p95 and concurrency goals only after measurement on representative data. “100M edges” is a scale scenario to benchmark, not an existing measurement or a guarantee that any one store will scale linearly.

---

## 12. Execution programme and dependency order

Use `specs/030-global-platform-upgrade` as the program-level workstream; do not create a competing context engine or new architecture spec unless the owner deliberately versions the scope. The visible 030 task plan already proposes WP0–WP12 and correctly places donor vertical promotion after the evidence gate, spans, epistemic semantics and closed-loop baseline.

### WP0 — truthful baseline and capability matrix

- Record executing commit, dirty tree, migrations, configuration, full suite/collection/bench baselines and exact environment state.
- Trace production callers for every capability: declared / implemented / unit-tested / contract-tested / wired / live-proven / operational.
- Map authoritative store for every field and event; list all competing writers and identity schemes.
- Measure source catalogue, captures, claims, candidate count, event volume, graph cardinality, degree distribution and data/tenant profiles.
- Create `donors/registry.yaml`; reconcile all existing donor catalogues and actual vendored repositories; verify licenses, assets and upstream lineage.
- Resolve one owner per TDA/graph/temporal operation and record Kafka-compatible broker truth/config. No architecture-changing work starts before this gate.

### WP1 — governance and architecture decisions

- Ratify `.specify/memory/constitution.md` as an engineering constitution, not an agent-behaviour document.
- Write the planned ADRs covering ContextGraph authority, outbox transaction boundary, identity merge/split, bitemporal semantics, retrieval, canonical matcher, graph/TDA ownership, deterministic/adaptive policy, donor licensing, replay semantics and retention.
- Keep one canonical state owner per object and use outbox rather than introducing a second publication mechanism.

### WP2 — typed cross-layer contracts

Implement and test `OperatorResult`, `EvidenceSpanRef`, typed stage outcome/error taxonomy, canonical serialization/digests, projection manifests, obligation/action/decision and context revision contracts. Unknown-world enums/fields stay preservable; platform workflow states remain explicitly validated.

### WP3 — invariant/worldline determinism

Correct accumulated-stream reduction; increment revision only on canonical digest change; preserve `supersedes` and source event hashes; cold fold and replay must match recorded history; distinguish correction/retraction from redelivery. Fix bitemporal semantics across storage/query/API.

### WP4 — one Gate + durable identity + admission boundaries

Route every source/runtime through ArtifactSink and Observation Gate; remove bypass publishers; make Observation + membership/placement + outbox consistent; deterministic id identity versions; preserve failed/unplaced outcomes; enforce calibrated decision rules. No donor integration promotion before this gate.

### WP5 — evidence spans survive to findings

Fix parser/segment offset semantics at producers, preserve typed spans through mentions, resolution candidates, relation claims and findings. Verify table cells/page boxes/WARC records and unresolved spans.

### WP6 — canonical operator envelope and adapter registry

All internal and external providers run behind capability/runtime registry with explicit runtime resolution, output/result contracts, resource envelope, source policy and failure taxonomy. No adapter bypasses stores.

### WP7 — real projections

Choose one production owner for every graph/TDA/temporal operation. Add projection manifests, offsets/source cuts, freshness/staleness, output digest and tested rebuild. Keep PostgreSQL/canonical stream distinct from graph-serving projections.

### WP8 — open-world semantics + conflicts + dynamic ontologies

Make all epistemic states round-trip through storage/events/API/UI. Add ConflictRecord, conflict detector, resolution proposal/decision, source dependency groups and relation/property ontology rules. Preserve raw claims and unknown predicates. This is where Semantica and AEGiS-pattern donors begin behind benchmarks, not before the proof seam is sound.

### WP9 — retrieval/frontier economics

Use current lexical retrieval as baseline; freeze judged query set; compare BM25/RRF/hybrid and optional vector profile. Calibrate source yield/reliability by predicate/context, include cost vector and suppress no-gain repeat actions while preserving explicit reopening conditions.

### WP10 — Context Engine loop end-to-end

At least two persisted iterations: new observation → obligation evaluation → entity-invariant revision → context revision → altered next action for explicit reasons. Include explicit stop report and restart proof; the kernel needs no donor component for its base acceptance.

### WP11 — donor verticals by measured value

Promote one vertical at a time: (A) discovery/source coverage, (B) documents/archives, (C) conflict/ontology/dedup, (D) analyst graph/replay UI, (E) temporal/spatial/TDA and optional vector. Every vertical proves quality/cost and can be disabled. No “integrated” label without production call site and E2E proof.

### WP12 — operations, security, migration and release

Backpressure, scoped budgets, egress, isolation, tenant controls, retention/erasure, DLQ/quarantine replay, observability, migrations/backfills/rollback, SBOM/licence review, and full validation reports with PASS/FAIL/BLOCKED/NOT-RUN evidence.

### Suggested P0 work order within the programme

1. Build donor/capability inventory and real caller map.
2. Canonicalize Gate/sink/event identities and durable outbox path.
3. Fix evidence span semantics through to finding.
4. Fix deterministic entity invariant/worldline and bitemporal end-to-end.
5. Prove the context kernel loop without donors.
6. Add open-world/conflict/dynamic ontology semantics.
7. Prove the first three golden cases.
8. Start donor promotion on the frozen corpus.
9. Scale/graph backend experiments only with measured workloads.

---

## 13. Specific non-goals and anti-patterns

- No third graph authority. The research Context Graph does not replace the entity/claim stream and neither is a generic truth graph.
- No schema that forces every unknown world concept into a hard-coded closed list.
- No `latest value wins` as the default conflict policy.
- No majority voting over syndicated mirrors.
- No transitive entity merge based only on similarity chain.
- No graph centrality or link prediction directly creating facts or committing identity.
- No LLM output as source evidence; any model-derived result is a derived artifact with prompt/model/input fingerprints and a declared replay mode.
- No raw contents in event bus payloads, traces, exception messages or logs where a reference/digest is enough.
- No external donor directly writing canonical stores.
- No new graph/vector store without a quality/operational benchmark and rollback plan.
- No automatic person-data collection beyond explicitly permitted scope. Publicly visible content is not blanket authorization to aggregate sensitive personal data; high-risk fields and relationship inferences need purpose/access policy, minimization and audit.
- No simulation result or causal narrative is promoted to an observed fact without source evidence and stated assumptions.

---

## 14. Source documents and external donor references

### COGNITIVE repository

- Global Upgrade draft: https://github.com/JewishTT/1/tree/main/specs/030-global-platform-upgrade
- Latest audit document visible in repo: https://github.com/JewishTT/1/blob/main/specs/030-global-platform-upgrade/current-state-audit.md
- Donor catalogue index: https://github.com/JewishTT/1/blob/main/docs/architecture/donors/00-INDEX.md
- Donor integration matrix: https://github.com/JewishTT/1/blob/main/docs/architecture/donors/09-INTEGRATION-MATRIX.md
- Layer-0 acquisition: https://github.com/JewishTT/1/tree/main/apps/acquisition
- ArtifactSink: https://github.com/JewishTT/1/blob/main/apps/acquisition/artifact_sink.py
- Observation Gate: https://github.com/JewishTT/1/blob/main/apps/shared/events/observation_gate.py
- Context Engine: https://github.com/JewishTT/1/tree/main/apps/control-plane/context_engine
- Dynamic entity invariant: https://github.com/JewishTT/1/blob/main/apps/shared/domain/graph_invariant.py

### Donors / patterns to audit at pinned revision

- Semantica: https://github.com/semantica-agi/semantica
- kafSIEM (current discoverable repository): https://github.com/scalytics/kafSIEM
- AEGIS epistemic review candidate: https://github.com/ChristopherKahler/aegis (methodology candidate; not asserted to be the intended donor)
- Existing phone OSINT donor noted in COGNITIVE catalogue: https://github.com/aegisceo/phone-osint-framework
- JanusGraph ScyllaDB backend documentation: https://docs.janusgraph.org/storage-backend/scylladb/

**Important:** these references are audit starting points, not blanket endorsements. Recheck exact revision, license and bundled assets during WP0/WP11 before integrating any code.

---

# PART II — UNIVERSAL CONTEXT RUNTIME

## 15. Целевая способность: работать с контекстом любой сложности и уровня абстракции

### 15.1 Что именно означает «универсальный»

COGNITIVE не должен обещать магическое понимание любого содержания. Универсальность здесь — инженерное свойство системы: **новый тип контекста можно принять, описать, связать, исследовать, преобразовать и проверить без переписывания ядра и без обязательного внесения его в заранее закрытый перечень онтологических типов**.

Система должна уметь:

- принимать новые предметные области, словари, источники, форматы, понятия и отношения;
- представлять как структурированные данные, так и фрагменты естественного языка, мультимедиа, последовательности событий, модели, гипотезы и формальные системы;
- связывать материал при неполном, конфликтующем или неизвестном семантическом описании;
- работать с микро- и макроуровнями — от символа, ячейки таблицы и утверждения до процесса, организации, системы, модели, стратегии и теории;
- переключать перспективы и временные срезы, не смешивая то, что было известно системе в прошлом, с тем, что известно сейчас;
- выполнять анализы по разным формальным режимам: поиск, логический вывод, статистическая оценка, графовый анализ, причинный анализ, моделирование, оптимизация и объяснение;
- показывать происхождение результата и границы его применимости;
- останавливать исполнение, когда дальнейшее действие не оправдано бюджетом, политикой, ожидаемой ценностью или качеством доступных данных;
- признавать отсутствие способности: `unsupported` — легитимный ответ, который создаёт явный capability gap и маршрут расширения, а не подменяет обработку правдоподобным ответом.

Универсальность обеспечивается четырьмя принципами: **открытый мир**, **типизированные контракты**, **композиционные операторы** и **проверяемая история преобразований**. Она не обеспечивается бесконтрольным подключением десятков агентов или максимальным количеством баз данных.

### 15.2 Пять базовых моделей, которые не следует сводить в одну

1. **Evidence model** — какие наблюдаемые материалы реально поступили, где они находятся, как были получены и какие фрагменты поддерживают результат.
2. **World/knowledge model** — какие сущности, события, отношения и утверждения система предполагает относительно описываемого мира, с альтернативами и степенью подтверждения.
3. **Context/process model** — что пользователь пытается понять или сделать, какие вопросы открыты, какие задачи и решения уже были, что требуется для следующего шага.
4. **Model/simulation space** — какие формальные модели, допущения, сценарии и контрфактические варианты используются и в какой области действуют.
5. **Policy/decision model** — какие операции разрешены, кто может их инициировать, какие пороги доказательности нужны и какие действия требуют человеческого подтверждения.

Эти модели связаны ссылками и событиями, но имеют разные семантики и authority owners. Например, гипотеза в process model не становится фактом в knowledge model; симуляция из model space не становится наблюдением в evidence model; разрешение выполнить сбор не доказывает истинность полученного утверждения.

## 16. Формальная модель контекста

### 16.1 ContextFrame

`ContextFrame` — версионируемый снимок задачи понимания, а не просто prompt и не просто граф. Он ссылается на актуальные данные, не копируя в себя все объекты.

```yaml
context_frame:
  id: ctx_<stable-id>
  revision: 17
  parent_revision: 16
  tenant_id: tenant_<id>
  purpose:
    goal: "Понять динамику исследуемой системы и оценить гипотезы"
    success_criteria: [criterion_1, criterion_2]
    deliverable_contract: report_with_grounded_findings
  scope:
    inclusions: [subject_ref, time_range_ref, geography_ref]
    exclusions: [excluded_subject_ref]
    granularity: event_level
    scope_revision: scope_v3
  perspective:
    observer_role: analyst
    jurisdiction: configured_policy_ref
    ontology_view: ontology_pack_revision
  time:
    mode: bitemporal_as_of
    valid_interval: [start, end]
    knowledge_cutoff: timestamp
    timezone: Europe/Riga
  epistemics:
    open_world: true
    confidence_policy: policy_ref
    unknowns_are_explicit: true
  assumptions: [assumption_ref_a]
  questions: [question_ref_a, question_ref_b]
  hypotheses: [hypothesis_ref_a]
  obligations: [obligation_ref_a, obligation_ref_b]
  resources:
    cost_budget: budget_ref
    time_budget: deadline_ref
    compute_budget: budget_ref
  access:
    policy_snapshot: policy_snapshot_ref
    data_classification: classification_ref
  provenance:
    created_by: actor_ref
    created_at: timestamp
    source_request_digest: sha256:...
  state_digest: sha256:...
```

Поля в схеме illustrative. В production-контракте применяются стабильные typed IDs, schema version, canonical serialization, validation и compatibility policy. Поле `granularity` не заменяет типизированную модель scope: один контекст может содержать несколько гранулярностей для разных вопросов.

### 16.2 Контекст — многомерная структура

Любой контекст может быть описан в нескольких измерениях, причём `unknown` и `not_applicable` обязательны и различны:

| Измерение | Типичные значения / представления | Что нельзя терять |
|---|---|---|
| Содержание | текст, код, таблица, сигнал, изображение, видео, документ, события, граф, модель | исходную форму и точный locator |
| Семантика | понятие, тип, предикат, роль, единица, схема, онтология, свободный термин | исходный термин и версию mapping |
| Уровень абстракции | атом, признак, факт, объект, событие, процесс, система, модель, теория, цель | переход и правила агрегации |
| Время | event-time, valid-time, source-time, capture-time, knowledge-time, processing-time | точность времени, часовой пояс, unknown-time |
| Пространство | координаты, адресная сущность, регион, топология, виртуальное пространство | систему координат, погрешность, resolution |
| Причинность | ассоциация, механизм, причинная гипотеза, интервенция, контрфактуал | предпосылки и конфаундеры |
| Эпистемика | наблюдение, утверждение, вывод, гипотеза, опровержение, противоречие, отсутствие данных | тип обоснования и независимость источников |
| Модальность | реально заявлено, возможно, необходимо, разрешено, запрещено, сценарно | различие факта/возможности/нормы |
| Перспектива | источник, пользователь, организация, юрисдикция, модель или наблюдатель | кто, в каком смысле и с какими правами утверждает |
| Социальная структура | актор, роль, группа, полномочие, обязательство, договор, конфликт интересов | время действия роли и основание связи |
| Вычислительная модель | язык, типовая система, программа, состояние, зависимость, trace | точный runtime/model/config и воспроизводимость |
| Нормативная модель | правило, ограничение, разрешение, запрет, стандарт, договорная оговорка | версия и область применимости нормы |
| Неопределённость | интервальная, вероятностная, эпистемическая, aleatoric, модельная, конфликтная | разные источники неопределённости нельзя объединять одной confidence |
| Происхождение | непосредственный источник, производная цепочка, lineage-root, operator run | независимость подтверждений и повторяемость |
| Цель/ценность | вопрос, критерий, decision utility, риск, цена действия | чьи предпочтения и какие ограничения использованы |

В каждом измерении может быть частичная структура. Не требуется заполнять все измерения для каждого объекта. Требуется сохранять отсутствие информации и не подставлять ложные defaults.

### 16.3 Открытый тип ContextElement

Любое содержимое должно представляться через общий envelope, а содержательная часть — через versioned payload:

```text
ContextElement
  element_id
  kind_uri                 # open namespace; not a closed enum
  schema_ref + schema_version
  payload_ref | inline_small_payload
  raw_form_ref?             # exact observed form, if applicable
  semantic_refs[]           # zero or many mappings to concepts
  relations[]               # typed, directed, optionally n-ary
  time_scope                # valid-time + knowledge-time when meaningful
  space_scope?              # geometry/region/topology, with CRS
  epistemic_status
  provenance_refs[]
  abstraction_level_ref
  perspective_refs[]
  assumptions_refs[]
  sensitivity/classification
  lineage/supersedes
  validation_status
```

`kind_uri` и schema registry допускают расширение. Невалидный payload не выбрасывается: он направляется в quarantine с ошибками декодирования. Неизвестный тип сохраняется как opaque payload и может быть исследован позднее после регистрации парсера/схемы.

### 16.4 Relation — не всегда бинарное ребро

Модель должна поддерживать binary relations, n-ary relations и события-отношения. Например, контракт не сводится к `(person, signed, document)`: может требоваться роль подписанта, дата, организация, версия документа, полномочие, место и условие вступления в силу. Реляционные структуры по возможности reify-ятся в `RelationAssertion` / `EventFrame` с участниками и role labels. В проекцию они могут отображаться в обычные графовые рёбра.

Это необходимо, чтобы универсальность не зависела от способности одной graph DB хранить весь мир в тройках.

## 17. Уровни абстракции и операции перехода

### 17.1 Лестница абстракции

Система поддерживает как минимум следующие уровни, допускающие ветвление и пересечения:

0. **Байты и физический объект:** документ, response body, файл, изображение, аудио, сырые записи.
1. **Локатор и сегмент:** страница, абзац, ячейка, запись, token range, кадр, временной сегмент.
2. **Наблюдаемый сигнал:** строка, число, визуальный признак, acoustic event, измерение, структурированное поле.
3. **Лексическая/синтаксическая единица:** термин, фраза, имя, конструкция, AST-узел.
4. **Mention / candidate:** упоминание сущности, событие-кандидат, relation candidate, классификация-кандидат.
5. **Утверждение / событие:** кто, что утверждает или какое событие сообщено, с точным evidence link.
6. **Сущность / объект / процесс:** identity candidate, entity invariant, lifecycle, process instance.
7. **Межобъектная структура:** relation network, dependency graph, flow, ecosystem, hierarchy, spatial network.
8. **Паттерн / механизм:** агрегированный процесс, повторяющаяся последовательность, роль, причинная схема-кандидат.
9. **Система / организация / рынок / техническая архитектура:** подсистемы, потоки, границы, состояния и обратные связи.
10. **Формальная модель / теория / стратегия:** набор переменных, axioms/assumptions, механизмы, прогнозы и falsification conditions.
11. **Решение / действие / policy:** допустимые действия, цели, ограничения, expected utility, risk.
12. **Метауровень:** анализ того, как были получены знания, какая методология применена, где систематические слепые зоны.

Это не линейная онтология. Объект может одновременно быть элементом организации, участником события и переменной в модели. Система хранит `abstraction_relation`, `representation_of`, `derived_from`, `member_of`, `instantiates`, `models`, `contradicts` и другие отношения с собственными типами и доказательствами.

### 17.2 Операции абстракции

Каждая операция — оператор с формальными входами/выходами, assumptions, loss profile и test fixtures, а не произвольная просьба к LLM.

| Операция | Что делает | Обязательная запись |
|---|---|---|
| `DECOMPOSE` | Разлагает систему/понятие на части | критерий разложения, coverage, excluded parts |
| `AGGREGATE` | Сводит множество наблюдений к сводке/системе | aggregation window, denominator, weighting, omitted records |
| `ABSTRACT` | Выводит общий паттерн из частных случаев | commonality rule, counterexamples, abstraction loss |
| `INSTANTIATE` | Разворачивает абстракцию в ожидаемые частные признаки | assumptions, unverified instantiated slots |
| `GENERALIZE` | Предлагает правило, охватывающее наблюдения | population/scope, exceptions, validation set |
| `SPECIALIZE` | Ограничивает общий термин классом/условием | constraint and ontology revision |
| `PROJECT` | Выбирает представление для задачи | projection schema, omitted dimensions, freshness |
| `LIFT_RELATION` | Переносит отношение на более высокий уровень | mapping path, preservation conditions |
| `COMPOSE` | Собирает несколько процессов/моделей в композицию | interface compatibility, inter-model assumptions |
| `DECOMPOSE_CAUSALLY` | Раскладывает эффект по предполагаемым механизмам | causal graph version, identification limits |
| `ANALOGIZE` | Строит структурную аналогию | source/target mappings, matched invariants, mismatch set |
| `CONCRETIZE` | Превращает расплывчатое понятие в измеримые признаки | operational definition, measurement assumptions |
| `TEMPORALIZE` | Разворачивает сущность в состоявшуюся последовательность | clock semantics, event ordering policy |
| `SPATIALIZE` | Проецирует объекты/события в пространственную модель | CRS, precision, projection assumptions |
| `MODEL` | Строит формальную модель | variables, equations/rules, assumptions, validation evidence |
| `SIMULATE` | Получает сценарные trajectories | random seeds, versioned parameters, reproducibility mode |
| `COUNTERFACTUAL` | Меняет заданную предпосылку в модели | intervention variable, identification assumptions, affected outputs |
| `COMPARE` | Сопоставляет две системы/среза/гипотезы | alignment map and incomparable fields |
| `RECONCILE` | Согласует разные schema/ontology/units | mapping table, losses, conflicts, approval |
| `EXPLAIN` | Даёт цепочку вывода для результата | premises, rules/operators, evidence links, uncertainty |
| `REFUTE` | Проверяет, что опровергает гипотезу | falsification criteria, searched scope, disconfirming evidence |
| `BOUND` | Выводит нижнюю/верхнюю границу при неполных данных | assumptions, missingness model, validity conditions |

У каждой операции должны быть как минимум три outcome: `success`, `partial`, `unsupported/blocked`, а также возможность `no_change`. Она обязана сохранить ссылки на входы и создать новый derived artifact; исходный объект не переписывается.

### 17.3 Журнал потерь информации

Любой переход от детального уровня к абстрактному теряет информацию. `AbstractionManifest` фиксирует:

- входные ID/digests и включённый scope;
- правило/модель агрегации;
- поля и фрагменты, исключённые из представления;
- количество и классы исключений;
- поддерживающие/противоречащие случаи;
- диапазон применимости и моменты, при которых сводка становится stale;
- возможность drill-down до исходного материала.

Поэтому summary и embedding не заменяют исходный контекст. Это ускоряющие представления, которые всегда должны иметь controlled path back to evidence.

## 18. Контекстное ядро и набор служб

### 18.1 Core Runtime — обязательное основание

Core Runtime не принимает решения об истинности сам по себе. Он управляет типизированным контекстом, полномочиями и жизненным циклом вычислений. Минимальные компоненты:

1. `Context Registry` — ID, revisions, branches, ownership, lifecycle, access policy.
2. `Context Compiler` — превращает пользовательское намерение в `ContextDefinition`, вопросы, scope и criteria; обязан перечислять неоднозначности.
3. `Context Resolver` — разрешает указатели на предыдущие контексты, объекты, версии, ветки и внешние ссылки.
4. `Context Store` — authoritative state/revisions; не складывает туда все сырые объекты.
5. `Context Delta Engine` — классифицирует изменение: new evidence, ontology change, policy change, user correction, projection drift, time advance.
6. `Context Graph Store` — research/process relations: questions, obligations, hypotheses, actions, outputs and decisions.
7. `Obligation Generator/Evaluator` — переводит цель в проверяемые obligations и пересчитывает удовлетворение.
8. `Action Planner` — оценивает возможные действия и собирает допустимый план.
9. `Execution Coordinator` — запускает durable jobs, checkpoints, retries, approvals and compensations.
10. `Context Memory Compiler` — выбирает минимально достаточный working set для конкретной операции, не скрывая ссылки на полный контекст.
11. `Context Revision Manager` — создаёт revisions, находит meaningful deltas и предотвращает циклы.
12. `Stopping/Completion Engine` — выдаёт обоснованный termination report с residual unknowns и непроверенными scope.

В кодовой базе для части этих ответственностей уже существует `apps/control-plane/context_engine`. Предлагаемое решение — уточнить контракты и интеграцию имеющихся служб; не создавать конкурирующий engine или отдельную систему «памяти», которая сама становится источником истины.

### 18.2 Context types — открытый каталог

Context kind — schema-backed URI, а не обязательный enum из десятка заранее известного домена. В стартовый registry следует включить следующие базовые профили:

- `ResearchContext`: вопросы, гипотезы, obligations, источники, findings, gaps.
- `EntityContext`: отдельный объект, aliases, идентификаторы, claims, worldline.
- `EventContext`: акторы, time/place, sequence, event variants, chronology.
- `DocumentContext`: версии документа, структуры, цитаты и локаторы.
- `ConversationContext`: сообщения, участники, темы, ссылки, unresolved intents.
- `SystemContext`: компоненты, интерфейсы, зависимости, потоки, состояния.
- `CodeContext`: репозиторий, файлы, символы, call graph, tests, execution trace.
- `ScientificContext`: question, dataset, method, observations, model, replication.
- `DecisionContext`: options, criteria, constraints, scenario assumptions, decision log.
- `PolicyContext`: rule sources, applicability, hierarchy, conflicts, effective dates.
- `TemporalContext`: histories, interval semantics, change points, event ordering.
- `SpatialContext`: features, geometry, topology, coordinate systems, uncertainty.
- `CausalContext`: DAG/model, interventions, identification assumptions, counterfactuals.
- `OperationalContext`: incidents, dependencies, services, runbooks, telemetry.
- `Market/SystemDynamicsContext`: actors, incentives, flows, stocks, feedback, regimes.
- `Creative/ConceptualContext`: motifs, themes, constraints, conceptual relations, versions.

Это starter registry, а не исчерпывающий список возможных контекстов. Пользовательский или донорский domain pack регистрирует новые типы без изменения core enums при условии schema/contract validation.

## 19. Полный функциональный каталог платформы

Ниже — целевой функциональный каталог. Это каталог планируемых возможностей, а не заявление, что они все уже реализованы в COGNITIVE. Каждая capability получает ID, владельца, входной/выходной контракт, policy requirements, детерминированность, стоимость, тесты, метрики и production status.

### 19.1 Acquisition & discovery

- поиск по открытым индексам и federated search;
- HTTP/API/RSS/sitemap/feeds;
- веб-страницы и браузерное извлечение в разрешённом режиме;
- архивы и исторические snapshots (WARC/Common Crawl/Wayback и аналогичные источники при соблюдении условий доступа);
- официальные реестры и открытые документы;
- разрешённые файлы, папки, object storage, data lakes и bulk datasets;
- таблицы/CSV/TSV/Parquet/JSONL/NDJSON/XML/YAML;
- базы данных через read-only connectors;
- event/stream connectors, offsets и checkpoints;
- внутренние корпоративные источники с явными grants;
- научные публикации/datasets и версии материалов;
- разрешённые телеметрические и инфраструктурные feeds;
- source discovery by obligation, freshness recrawl и change detection;
- sampling, pagination, crawl frontier, backpressure, retry and resume;
- provenance capture, raw content storage, de-duplication и content-addressing;
- source coverage estimation с честными статусами partial/unknown.

### 19.2 Parsing & multimodal extraction

- HTML/DOM/readability, PDF, office documents, e-mail, text/markdown;
- images/OCR, charts, screenshots, layout and bounding boxes;
- audio transcription, speaker/time segmentation where appropriate;
- video scene/frame/time extraction;
- source code/parsers/ASTs, configs, logs and stack traces;
- SQL/schema/ERD extraction;
- structured tables, nested records, XML trees, JSON pointers;
- archive and message-pack readers;
- language, encoding and format detection;
- document segmentation and section hierarchy;
- table/header reconstruction, cross-page table continuation;
- entity, relation, event and claim candidate extraction;
- formula, unit, date, currency and measurement extraction;
- document lineage and version comparison;
- malformed-input recovery with explicit partial status;
- typed span calculation and source-openable anchors.

### 19.3 Language & semantic operations

- language identification and multilingual segmentation;
- lemmatization, canonical token forms, Unicode normalization;
- transliteration and script/alias mappings;
- synonym, acronym, expansion, abbreviation and glossary resolution;
- terminology extraction and candidate concept grouping;
- semantic-role and relation/event extraction;
- paraphrase clustering and semantic deduplication;
- translation with original + derived text side-by-side;
- terminology-aware translation and cross-lingual retrieval;
- semantic search and query expansion;
- intent compilation, ambiguity detection and clarification planning;
- definition extraction, term disambiguation and sense inventories;
- discourse, coreference, quote/speaker attribution and claim polarity;
- semantic schema/ontology alignment;
- contradiction and entailment candidates;
- grounded natural-language explanation and report generation.

LLM-generated content remains a derived artifact. It must carry model/provider/prompt/tool versions, input refs/digests, output schema, known non-determinism, safety-policy version and validation outcome. Model confidence alone is not evidence quality.

### 19.4 Retrieval & memory

- lexical search (BM25), fielded/Boolean search, phrase and proximity search;
- filters by source, time, provenance, tenant, schema, validity, status and access policy;
- graph traversal and path queries;
- relational/SQL and analytical retrieval;
- temporal “as-of” and interval queries;
- spatial and spatiotemporal queries;
- vector/semantic retrieval as an optional index;
- hybrid fusion (RRF or evaluated alternatives) and reranking;
- query decomposition and multi-hop search;
- evidence-first retrieval, quote/span exact match and source-open action;
- retrieval-set deduplication by evidence lineage;
- relevance evaluation over a frozen judged corpus;
- context assembly under token/memory budgets with evidence priorities;
- durable task memory and project/case memory by access scope;
- working memory compaction with reversible references to full history;
- persistent user preferences only where appropriate and consented;
- memory expiry, correction, provenance, permissions and versioning;
- cache invalidation and projection freshness checks;
- recall of unresolved obligations/decisions, not only similar text.

### 19.5 Entity, identity & resolution

- candidate generation/blocking;
- pairwise and collective entity resolution;
- multilingual aliases and identity references;
- attribute normalization and comparison;
- source-specific ID mapping;
- relationship-aware evidence and neighborhood comparison;
- uncertainty/conflict-aware scoring;
- explainable feature vectors and counterevidence;
- cluster consistency and anti-transitive-merge checks;
- duplicate detection at document/record/claim/entity layers;
- merge/split/reopen decisions with history;
- temporal identity and role changes;
- human adjudication queues and sampling;
- calibrated thresholds by domain and error cost;
- replay after algorithm/ontology revision.

### 19.6 Knowledge graph, event graph & structures

- typed directed/multi-edge and n-ary/event relations;
- temporal and provenance-bearing claims/edges;
- hyperedges and reified relationships where roles matter;
- graph projection and incremental rebuild;
- bounded traversal, path search and neighborhood summaries;
- connected components, community detection and clustering;
- centrality, influence-flow and structural-hole measures with caveats;
- graph diff, versioned subgraphs and before/after comparison;
- relationship pattern mining and motif detection;
- graph constraints/integrity and schema validation;
- graph embeddings and link prediction as candidate generation only;
- graph explanation and source-level edge provenance;
- dependency, call, supply, organizational, process and knowledge graphs;
- role/temporal relation views and graph slices;
- export/import through versioned interchange schemas.

### 19.7 Dynamic ontology & semantic governance

- ontology/terminology registry and package versioning;
- vocabulary, schema and predicate mapping;
- open-world unknown-term intake;
- type hierarchy and concept relationship proposals;
- property domain/range and role signatures;
- cardinality, exclusivity, inverse/symmetric/transitive declarations;
- unit, currency and value-space constraints;
- temporal and jurisdictional applicability;
- SHACL-like graph validation and custom validators;
- ontology difference reports and compatibility tests;
- migration/reinterpretation planning;
- conflicting schemas and multi-ontology views;
- domain packs with detectors, queries, validators, views, reports and UI configuration;
- governance workflows for draft/propose/validate/activate/retire;
- mapping confidence separately from truth confidence;
- replayable derivations after ontology changes.

### 19.8 Claims, epistemics, provenance & conflict

- positive/negative support tracking;
- four-valued epistemic states `NEITHER`, `TRUE_ONLY`, `FALSE_ONLY`, `BOTH`;
- explicit unknown/inapplicable/unsupported distinctions;
- source reliability profiles by claim type, jurisdiction and time;
- source independence and syndicated-copy detection;
- quote attribution and claim polarity;
- conflict kinds: value, type, relation, temporal, logical, identity, provenance, scope;
- contradiction candidates and discriminating evidence plans;
- resolution strategy registry and abstention;
- source-backed support/refutation graph;
- retraction/correction/supersession semantics;
- claim lineage and derived inference trace;
- confidence calibration and sensitivity analysis;
- provenance lineage to raw artifacts and exact spans;
- reproducibility record for each derived finding;
- explicit distinction between `no result`, `not searched`, `unavailable`, `not supported`, `qualified absence` and `saturated-with-scope`.

### 19.9 Temporal reasoning

- valid time vs knowledge/transaction time;
- publication, event, capture, processing and projection clocks;
- interval algebra and uncertain date ranges;
- date parsing by locale/time zone and precision;
- chronology construction and partial order;
- event sequence inference with alternatives;
- change point/regime detection;
- entity lifecycle and attribute history;
- `CURRENT`, `AS_OF(knowledge_time)`, `INTERVAL(valid_time)` query modes;
- late-arriving evidence and as-known-at-the-time replay;
- temporal consistency constraints and conflict generation;
- recurrence/periodicity and duration analysis;
- source-date conflicts and precision propagation;
- timeline projections at different scales;
- retraction/retroactive correction without erasing history.

### 19.10 Spatial & spatiotemporal reasoning

- address/geocode and geographic entity resolution through approved services/data;
- CRS-aware geometry storage and conversion;
- distance, containment, overlap, nearest-neighbor and topology queries;
- routes, movement and trajectories where permitted;
- spatial clustering/hotspot analysis;
- uncertainty radii and positional accuracy;
- place-name aliases, historical boundaries and toponym timelines;
- space-time co-occurrence with explicit time uncertainty;
- map/heatmap/flow/trajectory projections;
- spatial data provenance and source precision;
- geofencing and restriction checks under policy.

### 19.11 Quantitative, statistical & uncertainty tools

- descriptive statistics and robust summaries;
- distribution fitting and diagnostics;
- Bayesian updating and model comparison where assumptions are explicit;
- frequentist estimates, confidence intervals and hypothesis tests;
- resampling, bootstrap and permutation tests;
- missing data and selection-bias diagnostics;
- anomaly and change detection;
- forecasting and backtesting;
- sensitivity and uncertainty decomposition;
- Monte Carlo sampling and stochastic process models;
- dimensionality reduction and clustering;
- correlation with explicit non-causality warning;
- multiple-testing correction and leakage checks;
- calibration/reliability diagrams and proper scoring rules;
- statistical report generation with methods and limitations;
- reproducible notebooks/analysis environments with pinned dependencies.

### 19.12 Causal & systems reasoning

- causal question compiler and estimand definition;
- causal DAG editing/validation;
- confounder, mediator, collider and selection-bias analysis;
- identification-condition checks;
- causal effect estimation using appropriate observed data;
- structural causal models;
- intervention (`do`) and counterfactual queries when identified/assumed;
- system dynamics stocks/flows/feedback loops;
- agent-based models with explicit rules and seeds;
- discrete-event and queue simulations;
- scenario and stress testing;
- Bayesian networks and probabilistic graphical models;
- dependency/fault-tree/reliability analysis;
- game-theoretic/decision models when justified;
- regime shifts and stability analysis;
- model verification/validation, calibration and falsification;
- causal narrative generator that labels measured, inferred, assumed and simulated components separately.

No model should produce causal claims solely from observational association without stating identification assumptions. Simulated outputs remain scenario outputs, never raw observations.

### 19.13 Formal, symbolic & computational reasoning

- deterministic rule engine and forward/backward chaining;
- constraint solving/SAT/SMT for supported structured domains;
- type and schema checking;
- symbolic algebra or theorem-prover adapters as optional providers;
- program parsing, static analysis, dependency and call graph;
- test discovery and execution under isolation;
- code navigation, semantic diff and blame/lineage;
- data lineage and query plan analysis;
- expression evaluation in bounded sandbox;
- workflow/model checking for finite state machines;
- invariant checking and property-based tests;
- formal specification to test-case derivation;
- proof/explanation artifact retention;
- solver timeout and `unknown/timeout` semantics.

A timeout or solver `unknown` is not a proof of falsehood. Any code execution tool requires explicit sandbox, filesystem, network, dependency and resource policies.

### 19.14 Planning, optimization & resource economics

- goal and success-criteria decomposition;
- obligation and gap generation;
- action candidate enumeration;
- precondition/effect/cost/risk modeling;
- expected information gain / marginal coverage estimation;
- cost-sensitive source ordering;
- constrained scheduling and resource allocation;
- multi-objective optimization (quality, cost, time, risk, freshness);
- dependency-aware topological planning;
- branch-and-bound/heuristic planning where appropriate;
- plan simulation and dry runs;
- retry/cooldown and duplicate-action suppression;
- budget allocation per tenant/context/source/host/runtime/model;
- dynamic replanning on new evidence or changed policy;
- explicit human approval steps and cancellation/compensation;
- stopping decision with residual-unknown ledger.

### 19.15 Agent & workflow orchestration

- deterministic workflows, bounded agent loops and hybrid DAG/state-machine execution;
- tool capability discovery and policy-aware tool selection;
- specialist-role decomposition without granting broad ambient permissions;
- subtask isolation and typed handoff contracts;
- persistent checkpoint, resume and idempotent retry;
- human-in-the-loop review, interrupt, reject, amend and approve;
- step budget, token budget, wall-clock budget and tool-call limit;
- cycle/deadlock/stagnation detection;
- branch and compare alternative plans;
- trace/replay of tool inputs/outputs and decision points;
- evaluation of agent trajectories against known tasks;
- provider/model fallback with versioned policy;
- explicit distinction between planner recommendation and authorized external action.

Temporal is already present in the platform plan as the durable-workflow candidate. Do not add a second framework as a parallel authority without a written ADR. A library such as LangGraph is a pattern/candidate for agent-state orchestration; its adoption must be compared with the existing engine and bounded to a clear role.

### 19.16 Reports, explanations & communication

- concise answer, detailed report and technical dossier;
- chronology, entity profile, relationship graph and comparison matrix;
- executive summaries with drill-down;
- provenance-aware quote/citation insertion;
- evidence table with supports/refutes/unresolved fields;
- confidence and limitations view;
- source bibliography and archived artifact pointers;
- data tables and reproducible charts;
- decision memo, incident report, research log and technical specification;
- multiple audiences/languages without changing underlying claims;
- export formats (Markdown, JSON, CSV, Parquet, PDF/HTML/DOCX via adapters);
- report template versions and rendering fingerprints;
- redaction and audience-based disclosure;
- annotations and reviewer comments linked to exact claim/span/revision.

### 19.17 Collaboration & governance

- shared context with explicit role-based and attribute-based access;
- branch/fork/merge of analytical context (not silent merge of canonical truth);
- comments, annotations, review requests and sign-off;
- conflict ownership/triage queues;
- approvals for ontology, identity, policy and external actions;
- case-level purpose limitation and retention;
- audit history of view/export/decision/action;
- information barriers and cross-tenant separation;
- redaction, legal hold, retention and authorised erasure workflows;
- classification labels and downstream propagation;
- policy-as-code testing and denied-action explanation;
- access review and break-glass workflows with post-hoc review.

### 19.18 Observability, reliability & evaluation

- distributed traces across context/action/operator/run/observation;
- metrics and structured logs with stable correlation IDs;
- input/output digests without leaking secrets or raw sensitive payloads;
- queue lag, age, retries, dead letters and backpressure;
- latency, throughput, per-stage cost and resource consumption;
- capability health and source-health state;
- operator quality and regression tracking;
- data-quality, provenance completeness and span resolvability metrics;
- context-loop progress and obligation churn metrics;
- model/provider change monitoring;
- golden datasets, adversarial cases, property-based tests and replay tests;
- canary, shadow comparison, kill switch and rollback;
- incident timeline and reproducible run manifests.

OpenTelemetry conventions are a reasonable common vocabulary for traces/metrics/log correlation; the project must pin the version and define its own domain attributes without making telemetry a source of business truth.

## 20. Universal Tool Registry: как функции становятся доступными системе

### 20.1 Capability вместо hard-coded tool names

Каждый инструмент регистрируется как `CapabilityManifest`. Контекстный планировщик выбирает сначала capability по смыслу и ограничениям, а затем конкретный provider/runtime. Это позволяет заменить реализацию без изменения `ContextDefinition`.

```yaml
capability:
  id: semantic.relation.extract
  version: 2.1.0
  input_schema: relation_extract_input_v3
  output_schema: operator_result_v2
  accepts: [observation_ref, evidence_span_ref, language_hint]
  emits: [relation_candidate, evidence_span_ref, provenance_ref]
  preconditions:
    - evidence_is_available
    - tenant_policy_allows_processing
  constraints:
    deterministic: partially
    network_access: none
    max_payload_bytes: configured_limit
    supported_languages: provider_declared
  quality:
    eval_suite: relation_extraction_golden_v4
    minimum_gate: configured_threshold
  execution:
    runtime: python_worker_pool
    timeout: configured_limit
    retry_policy: idempotent_retry_v2
  governance:
    owner: semantic-platform
    license_ref: license_manifest
    model_data_manifest: optional_manifest
    enabled_by_default: false
  observability:
    metrics: [latency, partial_rate, span_grounding_rate]
```

В реальном manifest конкретные значения обязательных полей задаются схемой, а не перечисленными placeholder-строками.

### 20.2 Обязательный интерфейс Tool/Operator

```python
class Operator(Protocol):
    def describe(self) -> CapabilityManifest: ...
    def validate(self, request: OperatorRequest) -> ValidationResult: ...
    async def execute(self, request: OperatorRequest) -> OperatorResult: ...
    async def health(self) -> CapabilityHealth: ...
```

`OperatorRequest` включает typed input refs, context snapshot/revision, effective policy, budget/deadline, idempotency key и requested output contract. `OperatorResult` включает status, typed outputs, provenance, input/output digests, operator/runtime/model version, warnings, coverage, resource costs, emitted facts/claims candidates и continuation/checkpoint reference. Вызов не имеет ambient write privilege.

### 20.3 Классы инструментов и режимы прав

- `READ`: извлекает данные в пределах разрешённых scope.
- `DERIVE`: создаёт новый производный артефакт, не изменяя входы.
- `PROPOSE`: предлагает identity/conflict/policy/ontology/plan decision.
- `DECIDE`: фиксирует утверждённое решение только у владельца соответствующего authority.
- `WRITE_EXTERNAL`: производит внешнее действие; по умолчанию выключено, нуждается в явном capability grant, подтверждении и idempotency control.
- `ADMIN`: меняет runtime, доступы, миграции или policy; отдельный высокопривилегированный plane.

Один и тот же plugin не должен получать все режимы только потому, что ему нужен один из них. Действия с внешними side effects должны поддерживать dry-run, preview, idempotency, cancellation/compensation там, где возможно, и audit log.

### 20.4 Политика tool selection

При выборе инструмента оцениваются:

1. semantic fit и output schema compatibility;
2. достаточность доказательств и входной контекст;
3. permission/purpose/scope eligibility;
4. ожидаемый прирост информации или покрытия;
5. стоимость, задержка, нагрузка и quota;
6. качество, калибровка и ограничения источника/provider;
7. свежесть и риск stale result;
8. воспроизводимость и возможность replay;
9. наличие альтернативы без внешних side effects;
10. риск чувствительной обработки и необходимости review.

Нельзя выбирать capability только по score LLM. Сначала применяется жёсткая policy/compatibility фильтрация, затем cost/quality optimization.

## 21. Каталог пользовательских инструментов и рабочих поверхностей

Для пользователя платформа должна предоставлять не одну «чат-консоль», а набор общих рабочих пространств, использующих общий `ContextFrame`:

1. **Universal Workbench:** естественно-языковой ввод, явное отображение интерпретации запроса, scope, вопросов и прогресса.
2. **Context Explorer:** древовидный/графовый просмотр уровней абстракции с переходом raw → span → claim → entity/event → model/finding.
3. **Evidence Browser:** исходный документ, точный span, metadata, capture time, lineage, связанные claims и открытие исходника.
4. **Entity/Process Workspace:** identity timeline, attributes, relations, worldline, conflict history, merge/split controls для уполномоченных ролей.
5. **Research Graph:** questions, hypotheses, obligations, actions, gaps, dependencies, findings и decision history.
6. **Knowledge Graph:** serving projection отношений мира с source-backed edges, filters, temporal slice и bounded traversals.
7. **Timeline Studio:** multi-source chronology, uncertain intervals, alternative orderings, event-time vs known-time switch.
8. **Conflict Desk:** группировка спорных claims, why-conflict view, source dependence, resolution proposals и adjudication.
9. **Ontology Studio:** glossary, predicates, schema mappings, unknown concepts, constraints, diff, validation, approve/retire.
10. **Query/Analysis Studio:** lexical/semantic/SQL/graph/time/space retrieval с сохранением query definition и результата.
11. **Quant/Model Lab:** notebook/sandbox, datasets, model assumptions, reproducible runs, scenarios and sensitivity.
12. **Workflow Inspector:** задачи, retries, checkpoints, capabilities, resource use, dead letters и trace/replay.
13. **Source Registry:** источники, лицензии/terms, access mode, capabilities, reliability, health, coverage and known limitations.
14. **Donor/Capability Registry:** upstream URL/commit, SBOM/license/model assets, adapter contract, evaluation results, owner and kill switch.
15. **Report Builder:** grounded narratives, evidence tables, charts, citations, redaction and exports.
16. **Decision Log:** goals, alternatives, assumptions, policies, approved actions and outcomes.
17. **Data Quality Console:** schema errors, unsupported formats, missing spans, duplicate lineage, unresolved identities and drift.
18. **Security/Audit Console:** permissions, action approvals, access/export logs, retention, isolation and policy decisions.
19. **Context Diff & Branches:** сравнить revisions, объяснить изменения, выбрать две ветви гипотез и объединить только совместимые процессные записи.
20. **API/SDK Studio:** generated schemas, examples, auth scopes, idempotency documentation and sandbox calls.

Каждый экран — разный view того же состояния и тех же ссылок, а не собственная локальная база истины. Write controls должны вызывать соответствующий authority service.

## 22. Универсальный retrieval и сборка рабочего контекста

### 22.1 Context compiler pipeline

```text
Natural language / API request
  -> intent hypotheses + ambiguity set
  -> purpose, scope, time, perspective, constraints
  -> questions / obligations / output contract
  -> capability requirements
  -> policy filtering
  -> retrieval plan + acquisition plan
  -> context assembly manifest
  -> execution
  -> evidence-backed result + residual unknowns
```

Запрос с неопределённым термином не должен молча зафиксировать один смысл. Compiler либо делает явную гипотезу с видимой assumption, либо создаёт несколько ветвей интерпретации, либо задаёт вопрос, когда неоднозначность влияет на безопасность, стоимость или корректность.

### 22.2 Context Assembly Manifest

Любой LLM/solver/operator работает не со «всем контекстом», а с конкретным snapshot:

- вопрос и output schema;
- список включённых источников/claims/spans с причиной включения;
- используемые revisions, time cut, ontology and policy versions;
- excluded candidates и reason (irrelevant, duplicate, inaccessible, over budget, stale);
- summary-to-source links и abstraction manifests;
- token/byte/row budget и pruning decisions;
- unresolved conflicts/unknowns, которые нельзя опустить;
- privacy filters and redactions;
- digest сборки контекста и renderer/compiler version.

Это позволяет проверить, почему агент ответил именно так и не был ли ключевой конфликт отрезан компактизацией.

### 22.3 Слои Retrieval

1. **Candidate recall:** дешёвое извлечение широкого набора вариантов через lexical indexes, filters и connectors.
2. **Grounding:** поиск точных записей и byte/char/page/row/time spans.
3. **Semantic ranking:** BM25/hybrid/ontology filters/vector/learned reranker в соответствии с evaluation corpus.
4. **Graph/context expansion:** расширение по ограниченным relation paths, lineage, chronology и obligation dependencies.
5. **Conflict-aware assembly:** включение конкурирующих утверждений и контрсвидетельств, а не только top-positive results.
6. **Diversity/dependency collapse:** устранение дублирующих mirrors без удаления самостоятельных независимых свидетельств.
7. **Budget-aware packing:** отбор фрагментов по expected utility, novelty, provenance quality и cost.
8. **Coverage check:** вычисление не закрытых вопросов и bias/selection limitations.

BM25 — baseline; vector retrieval, graph retrieval and reranking подключаются только по измеренной добавочной пользе. Vector similarity — recall/ranking aid, не доказательство и не identity decision.

## 23. Режимы рассуждения и правила их компоновки

COGNITIVE должен поддерживать разные режимы анализа как отдельные операторы, а не выдавать все за одно недифференцированное «мышление».

| Режим | Что решает хорошо | Типичный выход | Критический предел |
|---|---|---|---|
| Exact lookup | Точные совпадения, IDs, конкретные параметры | source result / record | зависит от полноты индекса/источника |
| Lexical retrieval | Поиск формулировок/терминов | ranked document spans | слаб на перефразировании и языковой вариативности |
| Semantic retrieval | Похожие по смыслу фрагменты | candidates with score | similarity не доказывает тождество/истинность |
| Rule/logic | Явные правила и constraints | pass/fail/derived proposition | только в рамках формализованных premises |
| Deductive | Следствия из заданных premises | derived claim/proof trace | корректность зависит от корректности premises/rules |
| Inductive/statistical | Обобщение/оценка закономерности | estimate/model + uncertainty | риск selection bias, confounding, overfit |
| Bayesian | Обновление вероятности по evidence | posterior with assumptions | prior/likelihood specification matters |
| Abductive | Лучшие доступные объяснения | ranked hypothesis set | лучшая из рассмотренных не значит истинная |
| Causal | Эффекты и механизмы при условиях идентификации | causal estimate/scenario | correlation alone insufficient |
| Analogical | Перенос структурных гипотез | mapping + mismatch | структурная похожесть не подтверждает факты |
| Temporal | Порядок, интервалы, lifecycle | timelines and order constraints | неполные/ошибочные timestamps |
| Spatial | Геометрия и spatial relations | spatial relations/metrics | CRS/precision and selection effects |
| Graph | Связность, пути, структуры | graph measures/path | projection bias, hubs, missing edges |
| Simulation | Что будет при заданных правилах | scenario trajectories | результаты верны только относительно модели |
| Optimization | Выбор под ограничения | candidate plan + trade-offs | objective/constraints encode preferences |
| Critical/adversarial review | Контрпримеры, альтернативы, слепые зоны | refutation/gap report | критик не является независимым evidence source |
| Human adjudication | Контекстная интерпретация и нормативное решение | signed decision + rationale | нужны полномочия, объяснение и audit |
| Meta-reasoning | Выбор метода/проверка слабых мест | method plan / confidence limits | не заменяет domain validation |

Планировщик может составлять ансамбль режимов: exact lookup → lexical/hybrid recall → source grounding → deterministic constraints → statistical/causal analysis → adversarial review → explanation. Пропуск шага допустим, но должен быть объясним и отражаться в manifest.

## 24. Мультимодальный контекст как равноправная часть ядра

Универсальность сломается, если source-of-truth для документов существует, а для изображения/аудио/видео остаются только подписи, сгенерированные моделью. Общий контракт должен покрывать:

- raw media asset и immutable digest;
- modality/codec/format metadata;
- time and spatial coordinate systems;
- segmentation tree (page, region, crop, frame, audio interval, scene);
- transformations (rendering, OCR, ASR, compression, crop) со своей lineage;
- extracted text/measurements/entities with confidence and exact source spans;
- model/runtime version and known failure modes;
- redaction/classification and retention policy;
- source-open and playback/zoom capability in UI.

Связь между modalities выполняется как candidate mapping: transcript phrase ↔ audio interval, OCR text ↔ image box, video frame ↔ event, chart point ↔ rendered plot/table row. Проверка alignment и временной точности — отдельный acceptance criterion. Извлечённый текст не заменяет оригинал.

## 25. Memory: не одна память, а управляемые слои

1. **Conversation state:** текущий turn/conversation pointers and user-visible commitments.
2. **Working set:** короткий контекст конкретного шага; пересобирается из snapshot manifest.
3. **Task/process memory:** выполненные действия, outputs, retries, unresolved obligations, plans.
4. **Case/project memory:** claims, decisions, ontology/scope versions and findings в соответствующем доступе.
5. **Entity/worldline memory:** воспроизводимая история accepted claims/events and identity decisions.
6. **Procedural memory:** проверенные workflow recipes, capability docs and evaluated prompts/operators.
7. **Semantic/episodic indexes:** rebuildable projections для retrieval; не самостоятельный canonical truth.
8. **Preference memory:** только уместные, контролируемые пользователем настройки; не смешивать с деловым evidence.
9. **Institutional memory:** утверждённые методики, standards, decisions and lessons learned с владельцем и сроком актуальности.

У каждого слоя свои правила scope, retention, permissions, correction, expiry and replay. Нельзя применять общую политику «запомнить навсегда» ко всем объектам. Summary memory всегда содержит ссылки на исходные объекты и отметку, что было опущено.

## 26. Работа с неизвестностью и stopping semantics

### 26.1 Классификация результата исследования

Система должна различать, по крайней мере:

- `UNKNOWN_NOT_INVESTIGATED` — вопрос ещё не рассматривался;
- `NO_OBSERVATIONS` — нет наблюдений в доступном canonical stream;
- `SOURCE_UNAVAILABLE` — источник или средство доступа недоступно;
- `QUERY_UNSUPPORTED` — текущий оператор не может задать/выполнить этот запрос;
- `SEARCHED_NO_RESULT` — выполненный поиск не вернул подходящих результатов в указанном scope;
- `QUALIFIED_ABSENCE` — есть методологически достаточное основание утверждать отсутствие в явно ограниченном scope;
- `POSITIVE_SUPPORT` / `NEGATIVE_SUPPORT` — поддержка соответствующей стороны;
- `BOTH` — положительная и отрицательная поддержка сосуществуют;
- `INCONCLUSIVE` — evidence недостаточно для требуемого решения;
- `BLOCKED_PARTIAL` — часть работы не выполнена из-за политики/ресурсов/ошибки;
- `HYPOTHESIS_REFUTED` — гипотеза опровергнута в заданном критерии и scope;
- `SATURATED_WITH_SCOPE` — достигнута заданная насыщенность при названном охвате, не абсолютная полнота мира.

Ни одно пустое значение, exhausted retry, нулевая выдача или пустая очередь не являются автоматически критерием завершённости.

### 26.2 CompletionReport

Каждый terminal state включает:

```text
CompletionReport
  context_id + final_revision
  completion_status + reason_code
  criteria_satisfied[] / criteria_not_satisfied[]
  obligations_satisfied[] / residual_obligations[]
  executed_scope / unexecuted_scope / excluded_scope
  sources_attempted / sources_unavailable / unsupported_capabilities
  evidence_coverage_and_known_selection_bias
  conflicts_open / hypotheses_unresolved
  budgets_consumed / reason_for_stopping
  reproducibility_manifest / policy_version
  reopen_conditions / next_best_actions[]
```

`COMPLETE_WITH_LIMITATIONS` — нормальный валидный финал. Система не должна скрывать незакрытые вопросы, чтобы представить красивый единый ответ.

## 27. API, SDK и события

### 27.1 Основные resource APIs

Названия — проектная рекомендация; финальное naming следует согласовать с текущими router/contracts и не создавать второй набор API без миграционного плана.

- `POST /v1/contexts` — создать контекст из natural language или typed definition.
- `GET /v1/contexts/{id}` — получить текущую revision/status/summary.
- `GET /v1/contexts/{id}/revisions` — история и diffs.
- `POST /v1/contexts/{id}/branches` — создать branch для альтернативной интерпретации.
- `POST /v1/contexts/{id}/questions` — добавить вопрос/гипотезу.
- `GET /v1/contexts/{id}/obligations` — gaps, status, dependencies and acceptance.
- `POST /v1/contexts/{id}/actions:plan` — спланировать разрешённые действия без исполнения.
- `POST /v1/contexts/{id}/actions:execute` — выполнить утверждённый план/пакет actions.
- `POST /v1/contexts/{id}/actions/{action_id}:cancel` — отмена с ограничениями compensation.
- `GET /v1/contexts/{id}/timeline` — timeline по explicit temporal query mode.
- `GET /v1/contexts/{id}/graph` — bounded graph projection query.
- `GET /v1/contexts/{id}/conflicts` — открыть текущие и исторические конфликтные записи.
- `POST /v1/conflicts/{id}/resolution-proposals` — создать proposal, не коммитить canonical decision.
- `POST /v1/resolutions/{id}:adjudicate` — уполномоченное решение с actor/rationale.
- `GET /v1/entities/{id}/worldline` — entity history and current/temporal slices.
- `GET /v1/evidence/{id}` — metadata, provenance and object/span pointers.
- `GET /v1/evidence/{id}/spans/{span_id}` — получить/рендерить grounded region.
- `GET /v1/ontologies/{id}/revisions` / `POST ...:propose` / `POST ...:validate` / `POST ...:activate`.
- `GET /v1/capabilities` — capability discovery, version/health/constraints.
- `POST /v1/queries` — typed retrieval/query plan.
- `POST /v1/analyses` — statistical/causal/graph/spatial analysis request with explicit method and dataset scope.
- `GET /v1/runs/{id}` — run status, logs/metrics refs, outputs and costs.
- `GET /v1/runs/{id}/trace` — structured trace and operator lineage with redaction.
- `POST /v1/evaluations` — run evaluation against declared golden suite, when authorised.
- `GET /v1/reports/{id}` — report status/version/export refs.
- `GET /v1/audit/events` — policy-filtered audit stream.

API returns typed `problem+json`-style errors with stable reason codes, retriable flag and remediation hint, never raw secrets or unrestricted stack traces. Long jobs return durable run IDs and events; not a misleading success response.

### 27.2 Event taxonomy

Use canonical event envelopes with schema version, event id, occurred/recorded times, tenant, context/revision, actor/operator, correlation/causation, idempotency, provenance and payload refs. Event families:

- context: created, revised, branched, merged, archived;
- obligation: opened, evaluated, satisfied, blocked, superseded;
- action: proposed, approved, dispatched, checkpointed, retried, completed, failed, cancelled;
- acquisition: requested, artifact-stored, observation-published, source-unavailable, partial;
- interpretation: operator-started, artifact-derived, candidate-emitted, unsupported;
- identity: candidate-created, decision-proposed, merge/split-committed, reopened;
- conflict: detected, grouped, proposed, adjudicated, reopened, classified-not-conflict;
- ontology: term-unknown, mapping-proposed, revision-validated/activated/retired;
- projection: build-started, checkpoint-advanced, stale, rebuilt, failed;
- report: prepared, validated, exported, redacted;
- governance: access-granted/denied, policy-changed, retention-applied, review-approved;
- system: capability-health-changed, budget-exhausted, queue-backpressure, replay-started/completed.

Event bus — доставка и replay, а не независимый authority. Событие должно быть published only after its backing canonical transaction is committed (through the approved outbox seam).

### 27.3 SDK and query DSL

Provide one versioned SDK per supported language family and a typed JSON query DSL with:

- subject/predicate/value or graph pattern;
- scope/time/space/perspective constraints;
- epistemic and source-quality filters;
- required provenance/span level;
- execution mode (`preview`, `execute`, `replay`, `explain`);
- cost/deadline/budget caps;
- accepted output schema;
- partial/unknown/conflict semantics.

Do not expose arbitrary unbounded code execution as the universal DSL. Specialized SQL/SPARQL/graph languages may be provided behind separate capability, validation and resource controls.

## 28. Интеграция моделей и внешних движков

Model gateway предоставляет общий контракт для LLM, embeddings, rerankers, OCR/ASR/VLM and specialist models:

- provider/model exact identifier and immutable version/snapshot when available;
- supported modality/language/task and known context limits;
- input/output schema and token/compute costs;
- policy/region/data residency eligibility;
- timeout, retry, fallback and concurrency caps;
- prompt/template version and input manifest digest;
- output validator and schema-repair policy;
- structured refusal/error/partial semantics;
- quality evaluation results and benchmark set;
- retention/training/data-use terms tracked in provider manifest;
- disable/rollback switch and fallback provider semantics.

Provider fallback cannot silently change data jurisdiction, privacy characteristics or semantic behavior. If a deterministic output is required, an LLM call is not automatically a valid substitute for a deterministic parser/solver. Every LLM output must distinguish extracted quotation, normalized value, inferred claim, generated summary and speculation.

## 29. Security, governance and trust boundaries

### 29.1 Five planes

1. **Data plane:** acquisition, immutable evidence, interpretation and projections.
2. **Context control plane:** context definitions/revisions, obligations, action plans and completion.
3. **Execution plane:** operators, workflows, models, worker pools and sandboxing.
4. **Governance plane:** identities, authorization, purposes, policy, approvals, classification and retention.
5. **Evidence/audit plane:** provenance, decision records, access traces, manifests and reproducibility.

The planes are logical boundaries; deployment can reuse infrastructure if permissions, schemas and ownership remain clear.

### 29.2 Mandatory protection rules

- strong tenant and context isolation for queries, caches, vector indexes, logs and exports;
- RBAC + ABAC, purpose limitation and resource/action scopes;
- credential vault references instead of embedded secrets;
- encryption in transit/at rest and rotation;
- classification and downstream label propagation;
- controlled egress, SSRF mitigation and DNS/redirect checks;
- isolated workers for browser/code/archive/third-party tools;
- time, byte, record, memory, CPU and token quotas;
- untrusted content is data, never system instructions (prompt-injection containment);
- output validation and tool allowlists; no model may grant itself privileges;
- retention and authorised deletion/erasure with lineage impact record;
- audit on access, sensitive inference, export, decision and external side effect;
- redaction at presentation and log pipelines;
- dependency/SBOM/license/model and dataset inventory;
- safe replay only under current policy; original run policy is preserved as provenance, but does not automatically authorise a new replay;
- approval rules for high-impact decisions/actions;
- source terms/access constraints and public-data sensitivity controls.

### 29.3 Confidence is not authorization

A high-confidence identity match does not authorize collection or disclosure. A public source does not mean unlimited aggregation is permitted. A technically executable action is not equivalent to a permitted action. This separation must be enforced in policy code and tests, not left to analyst judgement alone.

## 30. Storage & compute profiles

### 30.1 Canonical data vs serving compute

The canonical data contracts must remain independent of physical index. Relational SQL, graph stores, lexical indexes, vector indexes, columnar stores and time-series systems are execution targets and projections. Each query response declares which data cut and projection freshness it used.

### 30.2 Baseline profile

Use existing platform components where their real production callers and ownership can be proven:

- PostgreSQL for authoritative relational state, control plane and durable frontier;
- MinIO/S3 for raw/derived artifacts and large payloads;
- Kafka-compatible broker plus transactional outbox for event delivery;
- OpenSearch/BM25 for lexical retrieval;
- ClickHouse for large analytical aggregates when justified;
- Redis for non-authoritative cache/lease acceleration;
- Temporal for durable long-running workflows if current integration is validated;
- Neo4j or another graph store only for specified rebuildable graph serving projections where needed.

Optional profiles:

- vector store (`pgvector`, Qdrant or benchmarked equivalent);
- graph scale-out (`JanusGraph` with a supported storage backend such as ScyllaDB/Cassandra), only after degree/fanout/update/failure workload benchmarks;
- specialized temporal, spatial or analytical engines when a specific operator proves value.

No optional backend becomes a second truth store. Benchmark includes query quality, freshness, rebuild duration, operational burden, consistency, tenancy, ACL/ABAC enforcement, deletion propagation and failure recovery — not only raw traversal throughput.

## 31. End-to-end examples of universal context work

### 31.1 Public-source investigation

Request → disambiguate subject/scope/period → context revision → research obligations → authorized source plan → capture with immutable raw evidence → interpretation with spans → entity and event candidates → conflict/identity decisions → worldline/timeline → findings → remaining unknowns → next actions or completion report.

### 31.2 Technical architecture understanding

Repository/docs/logs → parse code and docs → build file/symbol/interface/dependency graph → infer system components and data flows with evidence links → identify mismatched contracts and missing callers → generate hypotheses and validation tests → run sandboxed checks → compare current vs target architecture → build traceable remediation backlog. Model-derived architectural claims remain linked to code locations and test output.

### 31.3 Scientific analysis

Question and estimand → protocol/assumptions → dataset registry/version → provenance and data-quality review → descriptive/statistical/causal methods chosen by fit → sensitivity/negative controls → reproducible outputs → conflicting results and limitations → report with code/model/dataset digests.

### 31.4 Operations incident

Alert → telemetry/logs/traces → dependency context → timeline with clock semantics → candidate causal paths → validate against metrics and changes → safe, approved diagnostic action → incident report + open questions → runbook update proposed but not autonomously activated.

### 31.5 Strategic or conceptual modelling

Define system boundary and purpose → distinguish observations from premises → select abstraction level → represent actors/stocks/flows/feedback/constraints → generate alternative models → compare explanatory coverage and counterexamples → parameterize scenarios from cited data → sensitivity and model risk → conclusions labeled empirical/inferred/assumed/simulated.

### 31.6 Policy or regulatory analysis

Pin jurisdiction and effective date → load authoritative texts/version history → parse rule hierarchy and definitions → model applicability/exception/precedence → compare cases to criteria → surface ambiguous/conflicting rules → produce issue matrix with citations and review flags. Platform outputs support analysis; they do not impersonate a licensed professional or automatically decide a legal case.

These examples use the same context primitives but distinct domain packs, operators, evidence policies and output contracts. That's the practical meaning of universality.

## 32. Conformance and quality gates

A capability is not marked `production-ready` solely because code imports or unit tests pass. Required statuses:

`DISCOVERED → LICENSE_REVIEWED → CONTRACTED → UNIT_TESTED → CONTRACT_TESTED → BENCHMARKED → WIRED → E2E_PROVEN → OBSERVED_IN_OPERATION → APPROVED_FOR_SCOPE`.

Failure at any stage must be visible; `BLOCKED`, `NOT_RUN`, `UNKNOWN` are first-class statuses.

### 32.1 Core conformance suites

1. **Context revision:** identical inputs don't produce meaningless revisions; material policy/evidence/ontology change does.
2. **Open-world round trip:** unknown type/predicate survives storage, events, APIs, exports and UI.
3. **Evidence grounding:** finding opens exact source span and raw artifact after restart/rebuild.
4. **Temporal correctness:** as-of query returns what was known then; late evidence alters current historical reconstruction without rewriting past knowledge state.
5. **Epistemic correctness:** `NEITHER/TRUE_ONLY/FALSE_ONLY/BOTH` survive storage/API/UI; no observation is not negative evidence.
6. **Identity safety:** similarity and A≈B/B≈C chain alone never commits a merge; conflicting attributes require adjudication or explicit policy.
7. **Conflict correctness:** unit/scope/time mismatch is not labelled factual conflict; independent evidence is separated from syndicated copies.
8. **Abstraction accounting:** every summary/model can drill back to evidence and declares omitted scope/caveats.
9. **Tool permission:** capability denied when purpose/scope/tenant/egress requirements fail; model cannot override gate.
10. **Replay/idempotency:** redelivery/retry doesn't inflate evidence, coverage or lineage; cold rebuild matches canonical digest.
11. **Budget correctness:** tasks can't exceed per-tenant/context/source/host/token/resource budgets due to default-allow gaps.
12. **Completion correctness:** exhausted queue/retries never equals done; residual unknowns and skipped scope appear in report.
13. **Projection recovery:** delete/rebuild projection from canonical cut yields correct digest and freshness manifest.
14. **Security corpus:** SSRF, redirect, DNS rebinding, decompression bombs, oversized body, prompt injection, secret leakage and cross-tenant queries.
15. **Model/provider drift:** changes are benchmarked; prior outputs retain old fingerprints and remain inspectable.
16. **Multimodal alignment:** OCR/ASR/frames/structured extracts link back to accurate location/time, with tolerance tests.
17. **Branch semantics:** analytical context branches don't silently mutate canonical facts; merge conflicts are explicit.
18. **Adversarial epistemic suite:** false corroboration, deceptive timestamps, misleading entity names, circular citation and selective evidence.

### 32.2 Golden corpus

Build a versioned corpus with at minimum:

- one entity with multilingual aliases and a false-positive near-match;
- two contradictory values with valid-time non-overlap;
- two sources sharing the same upstream origin;
- late evidence about an earlier event;
- an empty/unavailable/unsupported source distinction;
- unknown ontology term recurring across sources;
- nested JSON/table/PDF/WARC span preservation;
- a document/image/audio example with exact span locator;
- entity merge followed by evidence-driven split;
- one hypothetical/simulation result that must not enter the observed-claim store;
- policy-denied acquisition with an informative, durable outcome;
- partial run/restart/replay under changed policy;
- two context branches reaching different plausible conclusions;
- causal question with non-identifiable treatment effect;
- budget exhausted before complete scope.

Each fixture has expected accepted, rejected, unresolved and unknown states; expected citations/spans; and explicitly allowed alternative interpretations.

## 33. Delivery programme for the universal runtime

Keep `specs/030-global-platform-upgrade` as the program-level workstream and attach the universal-context runtime as a coherent extension of it. It should not become a competing spec with independent source-of-truth. Before coding, reconcile section/task names against the live working tree.

### Phase A — Measure and freeze baseline

- record commit, working tree, migration state, config and resource envelope;
- rerun full tests and distinguish baseline failures from regressions;
- produce per-capability maturity/caller matrix;
- identify canonical owner and every writer for all critical entities/events;
- inventory donors with pinned upstream URL, commit, license, assets and use cases;
- measure source/capture/observation/claim/entity/graph/event cardinality and skew;
- create golden corpus and baseline quality/cost report.

### Phase B — Trustworthy evidence substrate

- one ArtifactSink + Observation Gate across all acquisition profiles;
- canonical event envelope/outbox/idempotency;
- typed EvidenceSpanRef preserved end-to-end;
- SSRF/redirect/DNS/body-size/archive isolation controls;
- durable frontier and actual budget enforcement;
- source policy and access modes in capability registry.

### Phase C — Canonical semantics

- entity references/resolution decisions/merge-split history;
- claim and event schemas with positive/negative support;
- four-valued epistemics and open-world unknown preservation;
- typed time/space/scope/perspective dimensions;
- bitemporal queries and reproducible worldline reducers;
- conflict records, dependency roots and abstain semantics;
- ontology package lifecycle and compatibility checks.

### Phase D — Universal Context Kernel

- ContextFrame/Definition/Revision/Branch contracts;
- obligation lifecycle and satisfaction evaluator;
- capability planner, context assembly manifest and action budget;
- stopping/completion report and residual-unknown ledger;
- durable execution/checkpoints/restart;
- first E2E case without optional donors.

### Phase E — Analysis and abstraction operators

- lexical retrieval, exact span search, graph/time/space query interfaces;
- deterministic rule/constraint validation;
- abstraction manifests and reversible summary drill-down;
- statistical and causal operator contracts;
- multimodal extraction contracts;
- output schemas, reports and explanation paths.

### Phase F — UI/SDK and collaboration

- universal workbench/context explorer/evidence browser;
- conflict desk/ontology studio/timeline/report builder;
- capability and source registries;
- API/SDK with durable run/status/trace endpoints;
- audit, redaction, retention and multi-tenant validation.

### Phase G — Measured donor promotion and scale profiles

- evaluate Semantica conflict/ontology/dedup tools as non-authoritative operators;
- extract useful `kafSIEM` domain-pack, typed API and provenance UI patterns without promoting its SQLite store to canonical truth;
- pin intended AEGiS repository and classify it as method/tooling before import;
- benchmark optional vector and distributed graph backends against real task sets;
- each adopted tool must pass the full lifecycle to `APPROVED_FOR_SCOPE` and prove a disable/rollback route.

### Phase H — Operational hardening

- load/concurrency/recovery/restore and long-run tests;
- source/capability/operator health models;
- cost/SLOs based on measured distributions;
- policy-change replay controls and access review;
- migration/runbook/rollback, incident response and security review;
- release gate requiring live end-to-end evidence, not merely documented intent.

## 34. Architecture decision records that must exist

At minimum, approve and version these ADRs:

- ADR-001: canonical authority map and graph separation;
- ADR-002: context model, revisions and branch semantics;
- ADR-003: ArtifactSink/Observation Gate/outbox transaction seam;
- ADR-004: evidence spans and selector semantics;
- ADR-005: claim/event schema, epistemic algebra and absence semantics;
- ADR-006: identity resolution, merge/split and admission;
- ADR-007: bitemporal time model and query semantics;
- ADR-008: ontology-pack lifecycle and open-world extension;
- ADR-009: conflict detection, source dependency and resolution authority;
- ADR-010: capability/plugin execution contract and permission classes;
- ADR-011: durable workflow engine ownership and agent loop boundaries;
- ADR-012: retrieval quality, indexes and context packing;
- ADR-013: abstraction manifests, summaries and loss accounting;
- ADR-014: model/provider versioning, privacy and fallback;
- ADR-015: projection manifests, rebuild and freshness guarantees;
- ADR-016: data classification, retention, deletion and replay policy;
- ADR-017: donor licensing/SBOM/model/data assets;
- ADR-018: universal API/event schema versioning;
- ADR-019: evaluation corpus, benchmark ownership and release thresholds;
- ADR-020: graph/vector/backend choice after workload-specific benchmarking.

Each ADR states decision, context, alternatives, consequences, migration plan, rollback plan, owner, status and date. A proposed architecture is not final until conflicts between ADRs are resolved.

## 35. Definition of Done for «Universal Context Runtime»

The runtime is not considered complete merely because all catalogued capabilities have names. It reaches baseline completion when the following are demonstrated:

- a new domain context can be registered via schema/domain pack without changing core enums;
- a user request becomes a versioned context with scope, assumptions, output contract and obligations;
- the system distinguishes evidence, interpretation, hypothesis, model and policy;
- source-backed text, table, PDF and at least one non-text modality survive to findings with resolvable spans;
- unknown terms, contradictions, no-results, unavailable sources and blocked actions remain explicit;
- at least two durable context iterations alter the next action for auditable reasons;
- time-aware entity/event views can be replayed as of a historical knowledge cutoff;
- abstraction/summarization supports drill-down and loss/counterexample inspection;
- an analysis combines at least two reasoning modes but keeps assumptions/methods separately attributed;
- tools are discovered by typed capability and policy, not hard-coded prompt naming;
- failed work can resume, replay or be disabled without duplicate facts;
- all conclusions have evidence/provenance or are explicitly labelled as inference/assumption/simulation;
- completion exposes residual unknowns and excluded/unexecuted scope;
- security/tenant/budget/egress controls are tested adversarially;
- a new optional donor can be introduced, evaluated, enabled, disabled and rolled back without breaking canonical state;
- the full target profile works from clean start through API/UI to durable report and survives process restart;
- test results, workload profile, quality metrics, resource costs and known limitations are published.

### The governing rule

**COGNITIVE is a context runtime and evidence-processing system, not an all-knowing model and not a universal closed schema.** Its universality is the ability to preserve unfamiliar data, compose explicit transformations across abstraction levels, use the appropriate reasoning and retrieval tools, and expose exactly what is evidenced, inferred, assumed, simulated, disputed or still unknown.

---

## 36. Additional standards and reference implementations

Use these as specification references or donor candidates, not automatic production dependencies:

- [W3C SHACL](https://www.w3.org/TR/shacl/) — graph/data-shape validation patterns; useful for ontology pack validation and structured constraint reports.
- [W3C PROV-O](https://www.w3.org/TR/prov-o/) — provenance concepts for entities, activities and agents; adapt to COGNITIVE's typed evidence/derivation model rather than blindly replacing it.
- [OpenTelemetry semantic conventions](https://opentelemetry.io/docs/specs/semconv/) — common telemetry attributes; observability should correlate runs/operators/events without becoming business truth.
- [LangGraph overview](https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/overview.mdx) — agent orchestration patterns such as durable state, mixed deterministic/model-driven steps and human-in-the-loop; compare to existing Temporal ownership before adoption.
- [Semantica conflict-resolution guide](https://github.com/semantica-agi/semantica/blob/main/docs/guides/conflict-resolution.md) — candidate conflict/dedup/ontology capabilities; benchmark on the platform's own golden corpus.
- [kafSIEM repository](https://github.com/scalytics/kafSIEM) — useful domain-pack, provenance graph and operator UI patterns; its local SQLite graph should not become a competing canonical source.
- [JanusGraph ScyllaDB backend](https://docs.janusgraph.org/storage-backend/scylladb/) — optional distributed graph profile reference; benchmark before committing to it.

A framework's feature list or README is evidence of advertised capability, not proof of suitability, correctness, scale or license compatibility for this workload.

```
<!-- END VERBATIM SOURCE -->')
$body = $raw.Substring($s, $e - $s).Trim("`r","`n")
$text = ($body -replace '(?s)^```markdown\r?\n', '') -replace '\r?\n```$', ''
$sha  = [Security.Cryptography.SHA256]::Create()
$hash = $sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($text))
([BitConverter]::ToString($hash) -replace '-', '')
```

The published value must be `7B645578F210454CA3FE6FC96D2A18D5699E0D5CC1A1A609E3AB08BBE9BD32C6`.

<!-- BEGIN VERBATIM SOURCE -->
```markdown
```
<!-- END VERBATIM SOURCE -->
