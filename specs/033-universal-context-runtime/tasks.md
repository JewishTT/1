---

description: "Task list for COGNITIVE Universal Context Runtime — v2.0 architecture (phases A–H)"
---

# Tasks: COGNITIVE Universal Context Runtime — v2.0

**Input**: Design documents from `/specs/033-universal-context-runtime/`

**Prerequisites**: [`plan.md`](./plan.md), [`spec.md`](./spec.md) (Appendix A = verbatim v2.0 blueprint), [`data-model.md`](./data-model.md), [`contracts/`](./contracts/), [`quickstart.md`](./quickstart.md), [`adr/README.md`](./adr/README.md), [`conformance/suites.md`](./conformance/suites.md), [`corpus/golden-corpus.md`](./corpus/golden-corpus.md)

**Tests**: INCLUDED — mandatory. §32 makes the conformance suites the only admissible proof of a capability, and the Definition of Done is demonstrated rather than declared.

**Organization**: Phases follow the v2.0 blueprint's Phase A–H (§33), because FR-080 makes that order normative. Tasks carry the user story they deliver.

---

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel — different files, no dependency on an incomplete task
- **[Story]**: `[US1]`…`[US12]` map to the user stories in `spec.md`
- Exact repository paths in every description

### Status markers

| Marker | Meaning |
|---|---|
| `[ ]` | Not executed |
| `[~]` | Partial — works, incomplete |
| `[x]` | **Verified** — implemented, reachable, test passing, evidence recorded |
| `[!]` | **Blocked** — named dependency, owner and next action |
| `[-]` | **NOT_RUN** — deliberately not executed; the reason is recorded and it blocks the release gate |

`NOT_RUN` is a status, not an omission. It is admissible in a report and inadmissible as a silent gap.

---

# Phase A — Measure and freeze baseline (US12, US1)

**Purpose**: the runtime cannot be built on an unmeasured platform. Phase A is Feature 032's WP0 plus the universal-runtime inventory.

**Independent Test**: every baseline figure has a command, a date and an exit status; a capability with no production caller is reported below `WIRED`.

- [ ] T001 [US12] Record commit, working tree, migration state, configuration and resource envelope in `specs/033-universal-context-runtime/conformance/PhaseA-baseline.md`; distinguish pre-existing failures from regressions (§33 Phase A)
- [ ] T002 [P] [US12] Produce the per-capability maturity and caller matrix at the granularity of the §19 catalogues — 18 sections, each row with an ID, owner, contract, determinism, cost, tests, metrics and production status (§19, FR-022)
- [ ] T003 [P] [US1] Identify the canonical owner and every writer for each critical entity and event, and confirm the context-model gap: which of `ContextFrame`, `ContextElement`, `RelationAssertion`, `AbstractionManifest` already exist and in what shape (§16, FR-003, FR-006)
- [ ] T004 [P] [US12] Inventory donors with pinned URL, commit, licence, assets and use cases; cross-reference Feature 032's `donors/registry.yaml` rather than duplicating it (§33 Phase A, FR-083)
- [ ] T005 [P] [US12] Measure source, capture, observation, claim, entity, graph and event cardinality and skew; record every figure with its query and timestamp (§33 Phase A)
- [ ] T006 [US12] Create the golden corpus skeleton and baseline quality/cost report in `corpus/` and `conformance/`, with the fifteen §32.2 fixtures named even where their data does not yet exist (§32.2, FR-079)

**Checkpoint**: a measured baseline exists, and the context-model gap is known rather than assumed.

---

# Phase B — Trustworthy evidence substrate (US11, US1)

**Purpose**: Feature 032's WP4/WP5 gates, executed as the prerequisite for anything universal. The runtime inherits this substrate; it does not rebuild it.

**Independent Test**: every observation has a resolvable source span; no adapter can write canonical state; a replay inflates nothing.

- [ ] T007 [US1] Confirm the single ArtifactSink and Observation Gate cover all acquisition profiles, including the profiles Phase A found outside the seam; record each profile and its route (§33 Phase B; Feature 032 FR-001)
- [ ] T008 [US1] Confirm the canonical event envelope, outbox and idempotency key thread through every producer, including context-kernel-initiated actions (§33 Phase B; 032 FR-004, FR-005)
- [ ] T009 [US1] Confirm `EvidenceSpanRef` survives from the producer to the finding for every span kind the corpus exercises, and record any kind that does not (§33 Phase B; 032 FR-016…FR-018)
- [ ] T010 [US11] Implement and test the isolation controls: SSRF, redirect, DNS, body-size and archive isolation at the fetch boundary, plus prompt-injection containment for any content that reaches a model (§33 Phase B, §29.2, FR-072)
- [ ] T011 [US1] Confirm the durable frontier and real budget enforcement: byte, record, time and compute budgets are refused at dispatch, not logged after the fact (§33 Phase B, FR-071)
- [ ] T012 [US1] Register source policy and access modes in the capability registry so a planner cannot select a source whose policy has not been declared (§33 Phase B, FR-030)

**Checkpoint**: the substrate is trustworthy; the universal layer may now be built on it.

---

# Phase C — Canonical semantics (US2, US10)

**Purpose**: the semantic layer the context model needs — typed time, four-valued epistemics, open-world preservation, conflict and ontology lifecycle.

**Independent Test**: an unknown predicate round-trips through storage, events, API, export and UI; `BOTH` is distinguishable from low confidence everywhere; `AS_OF` answers the historical question.

- [ ] T013 [US2] Confirm entity references, resolution decisions and merge/split history are append-only and reachable from an element's lineage (§33 Phase C; Feature 032 FR-026…FR-028)
- [ ] T014 [US2] Implement the claim and event schemas with typed positive and negative support, and confirm the four-valued state `NEITHER`/`TRUE_ONLY`/`FALSE_ONLY`/`BOTH` round-trips through every surface (§33 Phase C, FR-055; 032 FR-032)
- [ ] T015 [US2] Implement typed time, space, scope and perspective dimensions on elements, with `unknown` and `not_applicable` distinct in each (§16.2, FR-004, FR-005)
- [ ] T016 [US2] Implement bitemporal queries and reproducible worldline reducers as the substrate for `AS_OF` and `INTERVAL` views (§33 Phase C; 032 FR-036, FR-037)
- [ ] T017 [US2] Confirm conflict records, dependency roots and abstain semantics are consumable by the context model without duplicating them (§33 Phase C; 032 FR-029…FR-034)
- [ ] T018 [US10] Implement the ontology package lifecycle and compatibility checks, including open-world unknown-term intake and replayable derivation after an ontology change (§33 Phase C, §19.7, FR-024)
- [ ] T019 [P] [US2] Write the open-world round-trip test: an unknown `kind_uri`, an unknown predicate and an unknown payload survive storage, events, API, export and UI (§32.1(2), SC-002)
- [ ] T020 [P] [US2] Write the epistemic round-trip test across all surfaces, including a case where `BOTH` must not be rendered as a low-confidence value (§32.1(5), SC-011)

**Checkpoint**: semantics are canonical, typed and preserved; the runtime can now carry a frame.

---

# Phase D — Universal Context Kernel (US1, US4, US5, US9)

**Purpose**: the kernel itself — frame compilation, elements, revision and branch management, obligation evaluation, assembly, and honest completion.

**Independent Test**: a new domain pack registers and ingests without a core change; an ambiguous request exposes its ambiguity; two persisted iterations change the next action for a recorded reason; every terminal state emits a `CompletionReport`.

## D.1 Context model

- [ ] T021 [US1] Implement `ContextFrame` per `contracts/context-frame.md`: identity, revision and parent, tenant, purpose, scope, perspective, time, epistemics, assumptions, questions, hypotheses, obligations, resources, access, provenance and state digest (§16.1, FR-003)
- [ ] T022 [US1] Implement the multi-dimensional context description with `unknown` and `not_applicable` as mandatory, distinct values in every dimension (§16.2, FR-004, FR-005)
- [ ] T023 [US1] Implement `ContextElement` per `contracts/context-element.md`: open `kind_uri`, schema ref and version, payload ref, raw-form ref, semantic refs, typed relations, time and space scope, epistemic status, provenance, abstraction level, perspective, assumptions, classification, lineage and validation status (§16.3, FR-006)
- [ ] T024 [US1] Implement quarantine for invalid payloads and opaque preservation for unknown types, with a retrieval path once a parser is registered (§16.3, FR-007, SC-002)
- [ ] T025 [US1] Implement `RelationAssertion` and `EventFrame` for binary, n-ary and event relations with participant roles, and their optional projection to graph edges (§16.4, FR-008)
- [ ] T026 [US1] Implement context kind registration through schema-backed URIs, with the sixteen starter profiles of §18.2 and no core enum requirement for a new kind (§18.2, FR-020, SC-001)
- [ ] T027 [P] [US1] Write the domain-pack registration test: install, ingest, retrieve, disable — with zero core changes asserted by a migration count and an enum diff (§18.2, SC-001)

## D.2 Kernel services

- [ ] T028 [US4] Implement the context compiler: intent hypotheses, ambiguity set, purpose/scope/time/perspective/constraints, questions/obligations/output contract, capability requirements, policy filter, retrieval and acquisition plans, assembly manifest and execution handoff (§22.1, FR-016, FR-040)
- [ ] T029 [US4] Implement ambiguity materialisation: a visible assumption, multiple branches, or a question when ambiguity affects safety, cost or correctness — never a silent single meaning (§22.1, FR-041, SC-006)
- [ ] T030 [US1] Implement the context registry, resolver, store, delta engine and revision manager: revisions only on meaningful deltas, no cycles, no silent rebase (§18.1, FR-015, FR-017, FR-019)
- [ ] T031 [US1] Implement branch creation and comparison, with parent links, and merge limited to compatible process records — never a silent canonical merge (§18.1, §21(19), FR-009)
- [ ] T032 [US5] Implement the context memory compiler: minimum sufficient working set per operation, with references to the full context always preserved (§18.1(10), FR-018)
- [ ] T033 [US5] Implement `ContextAssemblyManifest` per `contracts/context-assembly-manifest.md`: question and output schema, included elements with reasons, revisions and cuts, excluded candidates with reasons, summary links, budget and pruning, unresolved conflicts, redactions, digest and compiler version (§22.2, FR-042, SC-007)
- [ ] T034 [US5] Implement conflict-aware assembly: competing claims and counter-evidence are included, or their exclusion is recorded and surfaced on the answer (§22.3(5), FR-045, SC-007)
- [ ] T035 [US5] Implement the eight retrieval layers — recall, grounding, semantic ranking, graph expansion, conflict-aware assembly, dependency collapse, budget packing, coverage check — with BM25 as the baseline and every addition measured (§22.3, FR-043, FR-044)
- [ ] T036 [US9] Implement the objective evaluator against acceptance predicates and coverage assumptions, with task completion explicitly insufficient to close an obligation (§9.2, §26, FR-049, FR-055)
- [ ] T037 [US9] Implement the fourteen-state result classification and prove every state distinguishable across storage, API and UI (§26.1, FR-055, SC-011)
- [ ] T038 [US9] Implement `CompletionReport` per `contracts/completion-report.md`, including `COMPLETE_WITH_LIMITATIONS` and reopen conditions with next-best actions (§26.2, FR-057, FR-058)
- [ ] T039 [US9] Implement the stopping engine over the closed stop-condition set, and prove that an empty queue, exhausted retries, a low score and an empty list are not stop conditions (§26.1, FR-056)
- [ ] T040 [US1] Implement durable execution with checkpoints and restart for kernel actions, so a restart resumes without duplicating work (§18.1(9), §19.15; Feature 032 WP10)
- [ ] T041 [US1] Implement the first end-to-end case without any optional donor: a request becomes a frame, obligations, an authorised plan, evidence, an advancement and a completion report (§33 Phase D, FR-080)

**Checkpoint**: the kernel compiles, evaluates, assembles and stops honestly, and it needs no donor to do so.

---

# Phase E — Analysis and abstraction operators (US2, US3, US6, US7)

**Purpose**: the operators that make "any level of abstraction" and "different reasoning modes" real.

## E.1 Abstraction

- [ ] T042 [US2] Implement the abstraction ladder's typed relations — `abstraction_relation`, `representation_of`, `derived_from`, `member_of`, `instantiates`, `models`, `contradicts` — each carrying evidence (§17.1, FR-010)
- [ ] T043 [US2] Implement the twenty-two abstraction operators of §17.2 as formal operators with declared inputs, outputs, assumptions, loss profile and fixtures (§17.2, FR-011)
- [ ] T044 [US2] Implement `AbstractionManifest` per `contracts/abstraction-manifest.md`, with omissions, exception classes, applicability, staleness and drill-down (§17.3, FR-013, SC-003)
- [ ] T045 [US2] Enforce the three-plus-one outcome rule for every abstraction operator — `success`, `partial`, `unsupported/blocked`, `no_change` — and prove the input is never rewritten (§17.2, FR-012)
- [ ] T046 [US2] Implement summary and embedding drill-down to source bytes, and prove it survives a rebuild (§17.3, FR-014, SC-003)

## E.2 Reasoning modes

- [ ] T047 [US6] Implement the reasoning-mode registry: exact lookup, lexical and semantic retrieval, rule and logic, deduction, induction and statistics, Bayesian, abduction, causal, analogy, temporal, spatial, graph, simulation, optimization, critical review, human adjudication and meta-reasoning — each a separate operator with its output and limit (§23, FR-046)
- [ ] T048 [US6] Implement composed analyses with per-component attribution and a recorded reason for every omitted step (§23, FR-047, SC-008)
- [ ] T049 [US6] Implement the causal operator contract: estimand, identification assumptions, and a non-identifiability result instead of an estimate (§19.12, FR-025, SC-008)
- [ ] T050 [US6] Implement the statistical operator contract with methods, diagnostics and limitations recorded alongside the result (§19.11, FR-024)
- [ ] T051 [US6] Label graph structural results as measures that cannot create facts or commit identity, with a test that attempts both and is refused (§13, §23, SC-008)
- [ ] T052 [US7] Implement the multimodal contract: raw asset and digest, modality metadata, coordinate and time systems, segmentation tree, transformation lineage, extracted content with spans, model version, redaction and playback (§24, FR-049)
- [ ] T053 [US7] Implement cross-modal candidate mappings — transcript↔audio interval, OCR↔image box, frame↔event, chart point↔plot/table row — with alignment and temporal precision as a tested acceptance criterion (§24, FR-050, SC-009)
- [ ] T054 [US3] Implement capability manifests per `contracts/capability-manifest.md`, with schemas, accepted and emitted types, preconditions, constraints, quality gate, execution envelope, governance and observability (§20.1, FR-030)
- [ ] T055 [US3] Implement provider substitution through the registry alone, with a test that swapping a provider changes neither the `ContextDefinition` nor the downstream contract (§20.1, FR-031, SC-004)
- [ ] T056 [US3] Implement the `describe` / `validate` / `execute` / `health` operator interface and the request and result envelopes, with no ambient write privilege (§20.2, FR-032, FR-033)
- [ ] T057 [US3] Implement the six permission classes, least-privilege assignment, `WRITE_EXTERNAL` off by default and `ADMIN` in a separate plane (§20.3, FR-034, SC-005)
- [ ] T058 [US3] Implement the tool-selection policy: hard policy and compatibility filters first, then cost and quality; an LLM score alone cannot select a capability (§20.4, FR-036)
- [ ] T059 [P] [US3] Write the capability gap test: with no suitable capability, the planner emits a durable gap rather than substituting a weaker tool (§20.1, US3-AS5)

**Checkpoint**: abstraction is accountable, reasoning is attributed, and tools are capabilities.

---

# Phase F — UI/SDK and collaboration (US5, US8, US10)

**Purpose**: the analyst surfaces and the typed API. Each surface is a view over the same state.

- [ ] T060 [US8] Implement the twenty workbenches of §21 as views over shared state with write controls calling the authority service (§21, FR-037, FR-038)
- [ ] T061 [US8] Prove every surface exposes staleness, unknown and conflict rather than a polished singular view (§21, FR-039, SC-011)
- [ ] T062 [US8] Implement the nine memory layers with independent scope, retention, permissions, correction, expiry and replay; prove a preference is never returned as evidence (§25, FR-052, FR-054, SC-010)
- [ ] T063 [US8] Implement working-set compaction with a reversible record of what was dropped (§25.2, FR-053)
- [ ] T064 [US10] Reconcile the §27.1 resource APIs against the existing routers and implement the missing ones without creating a second API set (§27.1, FR-059)
- [ ] T065 [US10] Implement typed `problem+json` errors with stable reason codes, a retriable flag and a remediation hint, with no secrets or stack traces (§27.1, FR-061, SC-012)
- [ ] T066 [US10] Implement the canonical event envelope across the eleven event families, published only after the backing transaction commits (§27.2, FR-062, FR-063)
- [ ] T067 [US10] Implement the versioned SDK and the typed query DSL with scope, time, space, perspective, epistemic and provenance filters, execution modes and budget caps (§27.3, FR-064)
- [ ] T068 [US10] Prove arbitrary unbounded code execution is unavailable through the universal DSL, and that SQL/SPARQL/graph languages sit behind separate controls (§27.3, FR-065)
- [ ] T069 [P] [US10] Write the API-honesty test: a long analysis returns a durable run ID, a failure is a typed error, and no event exists without committed state (§27.1, §27.2, SC-012)

**Checkpoint**: the runtime is operable by an analyst and honest to a client.

---

# Phase G — Measured donor promotion and scale profiles (US11)

**Purpose**: optional capability, promoted by evidence and reversible.

- [ ] T070 [US11] Evaluate Semantica's conflict, ontology and dedup tools as non-authoritative operators against the frozen corpus; record the six-step order and the rejected strategies (§8.5, §33 Phase G, FR-083)
- [ ] T071 [US11] Extract `kafSIEM` pack-contract, typed-API and provenance-UI patterns without its SQLite store, collector, entity types or broker schema (§8.3, §33 Phase G)
- [ ] T072 [US11] Pin the intended AEGiS repository, classify it as methodology or tooling, and refuse selection by name similarity (§8.4, FR-043)
- [ ] T073 [US11] Benchmark optional vector and distributed graph backends against real task sets, including deletion propagation, tenancy filtering, rebuild duration and recovery (§30.2, FR-075, FR-076)
- [ ] T074 [US11] Drive every adopted tool through the lifecycle to `APPROVED_FOR_SCOPE` and prove its disable and rollback route (§32, §33 Phase G, FR-077)

**Checkpoint**: every optional component is measured, attributable and removable.

---

# Phase H — Operational hardening and release gate (US11, US12)

**Purpose**: the runtime survives load, failure, policy change and review — or its unproven parts are named.

- [ ] T075 [US11] Run load, concurrency, recovery, restore and long-run tests and publish the distributions rather than single figures (§33 Phase H)
- [ ] T076 [US11] Implement source, capability and operator health models with a declared state per capability (§19.18, §33 Phase H)
- [ ] T077 [US11] Set cost and SLOs from the measured distributions; any target without a measurement stays `null` with a reason (§33 Phase H, FR-076)
- [ ] T078 [US12] Implement policy-change replay controls and access review, including re-authorisation of a replay under current policy with the original policy preserved as provenance (§29.2, §33 Phase H)
- [ ] T079 [US12] Produce migration, runbook, rollback, incident-response and security-review artifacts, each with an owner and a tested step (§33 Phase H, FR-071)
- [ ] T080 [US12] Implement the eighteen conformance suites as runnable suites with a status each, including `NOT_RUN` with a reason (§32.1, FR-078, SC-014)
- [ ] T081 [US12] Build the fifteen-fixture golden corpus with expected accepted, rejected, unresolved and unknown states, expected citations and allowed alternative interpretations (§32.2, FR-079, SC-015)
- [ ] T082 [US12] Approve the twenty §34 ADRs with decision, context, alternatives, consequences, migration, rollback, owner, status and date; resolve every conflict between them (§34, FR-081, SC-016)
- [ ] T083 [US12] Demonstrate the §35 Definition of Done item by item, each with a command and an artifact; any unmet bullet blocks completion and is named (§35, FR-082, SC-017)
- [ ] T084 [US12] Publish the release report with every SC-001…SC-017 marked PASS / FAIL / BLOCKED / NOT_RUN, each with its command and exit status; `NOT_RUN` blocks the gate (§35, FR-082, SC-017)

**Checkpoint**: the runtime is either proven complete or its gaps are named in public.

---

## Dependencies and execution order

```text
Phase A ──> Phase B ──> Phase C ──> Phase D ──> Phase E ──> Phase F ──> Phase G ──> Phase H
              │            │           │            │                        │
              │            │           │            └──> T053 multimodal needs T052
              │            │           └──> T038/T039 need T036/T037
              │            └──> T015 needs T014's claim model
              └──> T012 needs T007's profile list
```

**Hard rules**

1. Phase B is not optional and cannot be skipped: the universal layer on an untrustworthy substrate is a larger claim with a weaker base (§33).
2. Phase D's first end-to-end case (T041) must pass **without any optional donor**; that is what proves the kernel is the platform, not a wrapper (§33 Phase D).
3. Phase G cannot start before Phase B's seam and Phase C's semantics exist — a donor promoted earlier becomes a second authority by default.
4. No conformance suite may be reported as passing if it was not run; `NOT_RUN` is explicit and blocks the release gate (T080, T084).

## Parallel opportunities

- T002–T006 are independent baseline measurements.
- T013–T018 are separable semantic concerns across storage, events, API and UI.
- T021–T027 can proceed per contract once T014's claim model is stable.
- T042–T046 (abstraction) and T047–T051 (reasoning modes) are independent operator families.
- T052–T053 (multimodal) are independent of T054–T059 (capability registry), though T053's operators are registered through it.
- T060–T063 are four independent analyst-surface families.
- T070–T073 are four independent donor evaluations.

## Implementation strategy

**First vertical (US1 + US4 + US5)**: Phase A → B → C → D. This delivers the open context model, a compiled frame with visible ambiguity, an inspectable assembly, and a completion report. It is the smallest slice that justifies the word "universal", because a new domain can already register and be investigated.

**Second (US2 + US6)**: abstraction accounting and reasoning-mode attribution. **Third (US3 + US10)**: the capability registry and the API surface. **Fourth (US7 + US8)**: multimodal and the workbenches. **Fifth (US9 + US12)**: unknown/stopping semantics and the conformance regime. **Last (US11)**: donors, measured and reversible.

The order is deliberate: nothing optional is acquired before the required is provable.
