---

description: "Task list for COGNITIVE Global Platform Upgrade — engineering execution programme (v1.0 blueprint)"
---

# Tasks: COGNITIVE Global Platform Upgrade — Engineering Execution Programme

**Input**: Design documents from `/specs/032-global-upgrade-execution/`

**Prerequisites**: [`plan.md`](./plan.md), [`spec.md`](./spec.md) (Appendix A = verbatim v1.0 blueprint), [`data-model.md`](./data-model.md), [`contracts/`](./contracts/), [`quickstart.md`](./quickstart.md)

**Tests**: INCLUDED — mandatory. The blueprint's §11.2 assertions and this feature's SC-001…SC-015 are only satisfied by a machine-verifiable test or a checkable operational artifact. A task marked `[x]` requires evidence: a `file:line` reference or a recorded command with its exit status.

**Organization**: Phases follow the blueprint's WP0→WP12 order, because FR-058 makes that order normative. Within each phase, tasks are grouped by the user story they deliver.

---

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel — different files, no dependency on an incomplete task
- **[Story]**: `[US1]`…`[US9]` map to the user stories in `spec.md`
- Exact repository paths in every description

### Status markers

| Marker | Meaning |
|---|---|
| `[ ]` | Not executed |
| `[~]` | Partial — works, incomplete |
| `[x]` | **Verified** — implemented, called from a live path, test passing, evidence recorded |
| `[!]` | **Blocked** — needs a named dependency, owner and next action |

`[x]` is never justified by "the code exists". `NOT_RUN` is a legitimate final status for a task whose precondition never arrived; silent omission is not.

---

## Path conventions

- Services: `apps/<service>/`
- Cross-layer contracts: `apps/shared/contracts/`
- Events, outbox and the Observation Gate: `apps/shared/events/`
- Canonical invariants: `apps/shared/domain/`
- Donors: `donors/` and `docs/architecture/donors/00–10`
- Tests: `tests/contract/`, `tests/integration/`, `tests/golden/`, `tests/security/`, `tests/replay/`
- Evidence records: `specs/032-global-upgrade-execution/benchmarks/`

---

# Phase 1: WP0 — Truthful baseline (US1) 🎯 GATE

**Purpose**: Prove what exists before changing anything. **No architecture-changing work starts before this gate is signed off** (§12, FR-058).

**Independent Test (US1)**: a capability with code and a passing unit test but no production caller is reported `unit-tested`, never `wired`; two writers of canonical observation state are both named with one designated owner.

- [ ] T001 Record the executing baseline in `specs/032-global-upgrade-execution/benchmarks/WP0-baseline.md`: `git rev-parse HEAD`, `git branch --show-current`, `git status --porcelain`, Python/Node/Rust toolchain versions, migration head, lockfile digests, and the environment envelope (FR-058, US1-AS3)
- [ ] T002 [P] [US1] Run the full baseline suite from the repository root and record the exact command, exit status, pass/fail/skip/error counts and the name of every pre-existing failure; label those failures *baseline*, not *regression* (US1-AS4)
- [ ] T003 [P] [US1] Run collection-only (`pytest --co -q`) and record the collected count and any collection errors, so a later `testpaths` regression is attributable (US1-AS1)
- [ ] T004 [P] [US1] Measure and record the data profile: source-catalogue entry count, capture and observation counts, claim and candidate counts, event volume, graph vertex/edge cardinality and degree distribution, tenant count, and storage footprint (§12 WP0; FR-057)
- [ ] T005 [US1] Build the capability matrix in `benchmarks/WP0-capability-matrix.md` with columns `Capability | Blueprint claim | Implementation | Production call sites | Store owner | Unit | Contract | Integration | E2E | Operational | Defects`. Every row cites a `file:line` or a test ID. Any function returning constant success, unused registry, ignored projection id, test-only consumer or unreachable service config is marked plainly (US1-AS1, SC-001)
- [ ] T006 [P] [US1] Trace one end-to-end investigation through **real calls** — API → context engine → acquisition → `artifact_sink.py` → `observation_gate.py` → interpretation → admission → `graph_invariant.py` → projection → finding — and record the actual state and event path. A grep hit is not a caller (US1-AS1)
- [ ] T007 [P] [US1] Build the authoritative-store ownership map in `benchmarks/WP0-owner-map.md`: exactly one owner per field and per event. List every competing writer and every competing identity scheme, each with a WP reference (US1-AS2, FR-006)
- [ ] T008 [P] [US1] Create `donors/registry.yaml` and reconcile the eleven catalogues in `docs/architecture/donors/00–10`, every vendored tree under `donors/`, and the installed dependency set. For each capability record the fields of §8.1 — for example `semantica-agi/semantica` for conflict/fusion, `scalytics/kafSIEM` for pack and analyst-workflow patterns, and `AEGiS` as `UNVERIFIED / URL_REQUIRED` (FR-038, FR-043, US7-AS4)
- [ ] T009 [P] [US1] Classify every donor registry entry into the §8.1 status vocabulary and record the licence separately for code, model weights, datasets, docs, sample assets and data sources; flag Common Crawl as data-terms-governed rather than generically open (§8.2, FR-041)
- [ ] T010 [P] [US1] Name one production owner per TDA, graph and temporal operation and record the Kafka-compatible broker truth and configuration; list every duplicate execution path found (§12 WP0, FR-007)
- [ ] T011 [US1] Resolve the donor ambiguity on `AEGiS` and the legacy `kafSIEM` CSS lineage before any code is copied; record the verdict and the pinned upstream for each (§8.3, §8.4, FR-042, FR-043)
- [ ] T012 [US1] Publish the WP0 sign-off record: every gate item marked PASS / BLOCKED / NOT_RUN with an owner and the next action. **WP1+ tasks stay blocked until this record exists** (§12, SC-015)

**Checkpoint**: a source-backed baseline exists and no architecture change has started.

---

# Phase 2: WP1–WP2 — Governance and typed contracts (US2, US3)

**Purpose**: the foundations every later work package depends on. An unversioned contract is how a second authority appears.

**Independent Test (US2/US3)**: a parser that changes output produces a new derived revision with a new fingerprint while the raw digest is unchanged; an executor cannot publish an observation without a persisted raw object.

## 2.1 Governance (WP1)

- [ ] T013 [P] [US1] Ratify `.specify/memory/constitution.md` as an engineering constitution — not an agent-behaviour document — and record the ratification date and version (§12 WP1)
- [ ] T014 [P] Write the ADRs the blueprint's WP1 names: ContextGraph authority, outbox transaction boundary, identity merge/split, bitemporal semantics, retrieval, canonical matcher, graph/TDA ownership, deterministic/adaptive policy, donor licensing, replay semantics, retention. Each states decision, context, alternatives, consequences, migration, rollback, owner, status and date (§12 WP1; the v2.0 document's §34 lists the full twenty)

## 2.2 Typed contracts (WP2)

- [ ] T015 [P] [US2] Implement `OperatorResult` in `apps/shared/contracts/operator_result.py` with status, typed outputs, warnings, partial coverage, input observation IDs and digests, spans, operator name/version, parameter and model fingerprints, output digest, determinism/replay mode, resource consumption and language/encoding/locale/format references (FR-014, contract `operator-result.md`)
- [ ] T016 [P] [US3] Implement `EvidenceSpanRef` in `apps/shared/contracts/evidence_span.py` with the eight span kinds, `observation_ref`, `blob_digest`, `selector_semantics_version` and a validator that refuses cross-version conversion without an explicit policy (FR-016, FR-017, contract `evidence-span.md`)
- [ ] T017 [P] [US2] Implement the typed stage outcome and error taxonomy in `apps/shared/contracts/stage_outcome.py`: `accepted`, `partial`, `no-result`, `unsupported`, `unavailable`, `failed`, `policy-denied`, plus the operator-level classes of §4.4 (FR-012, FR-022)
- [ ] T018 [P] [US2] Implement canonical serialisation and digest helpers in `apps/shared/contracts/canonical.py` — deterministic key ordering, encoding, and content-addressed reference construction used by every digest in the programme (FR-002, FR-004)
- [ ] T019 [P] [US2] Implement `ProjectionManifest` in `apps/shared/contracts/projection_manifest.py` with inputs/offsets/source cut, builder and operator version, output digest, staleness, status, kill switch and tested rebuild route (FR-006, contract `projection-manifest.md`)
- [ ] T020 [P] [US2] Implement the obligation, action and decision contracts in `apps/shared/contracts/obligation.py` and `apps/shared/contracts/decision.py`, including acceptance predicates, priority vector, attempts, marginal gain, stop/satisfaction rules and an append-only decision record (FR-048, contract `research-obligation.md`)
- [ ] T021 [P] [US2] Implement `AcquisitionTask` vNext in `apps/shared/contracts/acquisition_task.py` with every field of §3.2 and a validator that rejects embedded secrets (FR-008, FR-009, contract `acquisition-task.md`)
- [ ] T022 [P] [US2] Implement the context-revision contract in `apps/shared/contracts/context_revision.py` — revision, parent, delta class, digest, author and the reason for the revision (FR-046, FR-047)
- [ ] T023 [US2] Implement the `ContextDefinition` schema and the canonical-context-state contract in `apps/shared/contracts/context_definition.py`, covering objective, compiled intent AST, scope, time mode, source universe, ontology/reasoning profile, output requirements, budgets, access policy, freshness, quality and stop conditions (FR-046, contract `research-obligation.md`)
- [ ] T024 [US3] Write contract tests for every contract in `tests/contract/`: round-trip, unknown-field preservation, enum exhaustiveness, digest stability and refusal of invalid combinations (SC-005)
**Checkpoint**: contracts exist, are versioned and are covered by tests.

---

# Phase 3: WP3–WP5 — Evidence seam, spans, identity and admission (US2, US3, US5)

**Purpose**: the layer where an evidence system either becomes auditable or does not. WP3 precedes WP4 so that the identity and invariant consumers exist before the writers are collapsed.

## 3.1 Invariant and bitemporal determinism (WP3)

- [ ] T025 [US6] Repair the accumulated-stream reduction in `apps/shared/domain/graph_invariant.py`: revision increments only on a canonical digest change; `supersedes` and source event hashes preserved; cold fold and replay must produce the same digest (FR-036, US6-AS4)
- [ ] T026 [US6] Distinguish correction and retraction from redelivery in the reducer and its inputs, so a resend never creates a revision and a correction always does (FR-036, FR-005)
- [ ] T027 [US6] Implement the bitemporal semantics end to end — storage, query and API — for `source_published_at`, `source_valid_from`/`source_valid_until`, `source_observed_at`, `captured_at`, `recorded_at`/`known_at`, `processed_at` and `projected_at`, with `unknown` preserved and no `now()` substitution (FR-036, FR-037)
- [ ] T028 [US6] Implement the three query modes `CURRENT`, `AS_OF(known_time)` and `INTERVAL(valid_from, valid_until)` and prove that a late capture refines the current reconstruction without changing pre-capture `AS_OF` (FR-037, US6-AS2, SC-008)
- [ ] T029 [P] [US6] Write the late-data replay test in `tests/replay/test_bitemporal_as_of.py`, including a 2026 document asserting a 2020 valid-time fact (US6-AS2)

## 3.2 One Gate, durable identity, admission (WP4)

- [ ] T030 [US2] Route every executor family through `apps/acquisition/artifact_sink.py` and `apps/shared/events/observation_gate.py`; enumerate and remove every bypass publisher with a repository-wide reference sweep, not a sample (§3.3, FR-001, SC-002)
- [ ] T031 [US2] Enforce persist-before-publish in the sink: raw object → digest → content-addressed ref → capture/observation identity → outbox write, with a rejection test for an observation created without a persisted `raw_ref` (FR-002, US2-AS1)
- [ ] T032 [US2] Make capture + membership/placement + outbox consistent in one transaction seam and return acknowledged publication details from the sink (FR-003, FR-004)
- [ ] T033 [US2] Preserve failed and unplaced outcomes as durable results instead of exceptions or logs; implement reconciliation for an orphan artifact after a crash between raw write and outbox placement (FR-012, US2-AS3, US2-AS4)
- [ ] T034 [US2] Implement deterministic capture and observation identity under a declared identity-scheme version, with an idempotent replay path that provably does not inflate coverage, independence, cost learning or revisions (FR-002, FR-005, SC-004)
- [ ] T035 [US5] Implement blocking and candidate generation in `apps/admission/` with a recorded blocking trace per candidate, avoiding all-pairs comparison (FR-027, US5-AS1)
- [ ] T036 [US5] Implement `ResolutionCandidate`, `ResolutionDecision` (admit/defer/reject/merge/split/reopen), the append-only decision history and the alias/revision behaviour, with the admission path as the only committer (FR-026, FR-028, FR-034, contract `resolution-decision.md`)
- [ ] T037 [US5] Enforce the anti-transitive-merge rule: a similarity chain cannot commit a merge where A–C evidence is inconsistent; add the `A≈B`, `B≈C`, `A≠C` trap to the labelled corpus (FR-027, US5-AS2, SC-006)
- [ ] T038 [US5] Implement the false-merge correction path: prior source claims unchanged, current grouping changed, projections regenerated through explicit supersession (FR-028, US5-AS3)

## 3.3 Spans to findings (WP5)

- [ ] T039 [US3] Repair parser and segment offset semantics at the producers: typed spans instead of an untyped `offset`, with `selector_semantics_version` assigned at creation — never inferred at display time (FR-016, FR-018)
- [ ] T040 [US3] Propagate `EvidenceSpanRef` through mention, resolution candidate, relation/claim candidate and finding, for the character, table-cell, page-box and WARC-record kinds (FR-016, US3-AS1)
- [ ] T041 [US3] Mark unrecoverable spans partial/unresolved at the point of failure and prevent a synthetic offset anywhere in the chain (FR-018, US3-AS3, SC-003)
- [ ] T042 [US3] Implement derived-revision creation with `supersedes` on parser/extractor/normalizer version change, retaining the prior output and the prior operator fingerprint (FR-015, US3-AS2, SC-005)
- [ ] T043 [US3] Write the span corpus tests in `tests/integration/test_spans_to_findings.py`: PDF table, HTML article, JSON result, WARC record — each resolving to the exact stored bytes after restart and after a projection rebuild (FR-055, SC-003)

**Checkpoint**: one seam, deterministic identity, spans that survive, decisions that append. No donor work has started.

---

# Phase 4: WP6–WP7 — Operators and projections (US1, US2, US9)

**Purpose**: give every capability one envelope and give every projection a manifest and a rebuild.

- [ ] T044 [US2] Implement the capability/runtime registry in `apps/shared/contracts/capability.py` and its runtime resolver: capability ID, version, input/output schema, accepted and emitted types, constraints, quality gate, execution envelope, governance and observability (FR-040, FR-041; reused by 033's §20 contract)
- [ ] T045 [US2] Enforce the six permission classes `READ`, `DERIVE`, `PROPOSE`, `DECIDE`, `WRITE_EXTERNAL`, `ADMIN` at the registry boundary; an operator call carries no ambient write privilege (FR-040)
- [ ] T046 [US1] Add the resource envelope and failure taxonomy to every adapter: timeout, byte/record budget, retry policy, cost accounting and the closed failure vocabulary (FR-012, FR-014)
- [ ] T047 [US9] Implement projection manifests across `apps/projection/`: source cut and offsets, builder/operator version, output digest, staleness, status and kill switch (FR-006, contract `projection-manifest.md`)
- [ ] T048 [P] [US9] Implement a tested rebuild route for every production projection and assert digest parity after a delete-and-rebuild (FR-006, SC-009, US9-AS3)
- [ ] T049 [P] [US9] Make staleness visible to obligation evaluation so a stale projection cannot satisfy an obligation without a recorded staleness decision (FR-006, SC-009)
- [ ] T050 [US1] Choose one production owner for every graph, TDA and temporal operation and remove or quarantine the losing duplicate paths, preserving the removal record (FR-007, T010's findings)

**Checkpoint**: every capability has an envelope, every projection has a manifest and a rebuild.

---

# Phase 5: WP8 — Open world, conflicts, dynamic ontology (US4, US5)

**Purpose**: make contradiction and semantic evolution first-class rather than post-processing.

- [ ] T051 [US4] Implement `ConflictRecord` in `apps/shared/contracts/conflict_record.py` with the §6.3 fields, the closed status vocabulary and per-transition reasons including an explanatory `NOT_A_CONFLICT` (FR-031, contract `conflict-record.md`)
- [ ] T052 [US4] Implement the comparability pre-check before any conflict is declared: participants and identity revision, predicate mapping and ontology version, units/currency/period/jurisdiction, valid-time intersection, timestamp precision, source and capture/publication/event times, dependency root, and predicate exclusivity (FR-030, US4-AS1, US4-AS2)
- [ ] T053 [US4] Implement the eight conflict detectors — value, type, relation, temporal, logical/ontology, identity, provenance and scope/context — as separate operators emitting `OperatorResult` (FR-029, contract `conflict-record.md`)
- [ ] T054 [US4] Implement four-valued epistemic support with independent `support_positive[]` and `support_negative[]`, and prove it round-trips through storage, events, API and export without collapsing into a score (FR-032, SC-007)
- [ ] T055 [US4] Implement the seven resolver strategies as policy plug-ins emitting `ResolutionProposal`: authority-weighted, temporal applicability, independent corroboration over lineage roots, ontology/constraint, source-of-record, analyst adjudication, and abstain-with-discriminating-evidence (FR-033, US4-AS4)
- [ ] T056 [US4] Implement source dependency groups and syndicated-copy detection so voting counts lineage roots rather than republishing sites (FR-030, US4-AS3)
- [ ] T057 [US4] Implement `OntologyPackRevision` with the §5.1 contents, the `DRAFT → PROPOSED → VALIDATED → ACTIVE → RETIRED` lifecycle and binding to a context or operator without retroactive reinterpretation (FR-023, FR-024)
- [ ] T058 [US4] Implement ontology-gap monitoring, mapping proposals with retained alternatives, validation against frozen fixtures, approval and re-interpretation with revision lineage (FR-025)
- [ ] T059 [US4] Preserve unknown raw types and predicates through storage, events, API, export and UI with `mapping_status=unknown_predicate` (FR-021, FR-022, SC-003)
- [ ] T060 [P] [US4] Build the contradiction corpus in `tests/golden/conflict_corpus/`: value, type, relation, temporal, logical, identity, provenance and scope cases, plus syndicated duplicates, mismatched currencies and periods, and genuinely unresolved `BOTH` cases (FR-055, US4 independent test)

**Checkpoint**: contradiction is a state, not a score; the ontology can grow without rewriting history.

---

# Phase 6: WP9–WP10 — Retrieval economics and the closed loop (US8, US9)

**Purpose**: spend resources on evidence that changes a decision, and prove the loop advances.

- [ ] T061 [US8] Freeze the judged query set before any retrieval change and record it in `benchmarks/WP9-judged-set.json` with its relevance judgements (FR-057)
- [ ] T062 [US8] Measure BM25 as the baseline, then compare lexical, RRF and hybrid on the frozen set; a variant is adopted only on measured gain, with the comparison recorded (FR-057; Feature 033 §22.3)
- [ ] T063 [US8] Implement source-yield and reliability calibration by predicate and context, with a cost vector per action (FR-050, FR-053)
- [ ] T064 [US8] Implement repeat-action suppression with an explicit reopening condition, and prove a suppressed repeat does not re-enter the frontier (FR-050, US8-AS3)
- [ ] T065 [US8] Implement the component vector per eligible action — expected information gain, hypothesis discrimination, relevance, quality, independence gain, novelty, freshness, cost, latency, repeat penalty, failure rate, resource risk and policy penalty (FR-050)
- [ ] T066 [US8] Enforce hard access, scope, tenant and budget filters **before** utility ranking, with a test that a high-gain action violating a hard constraint is never selected (FR-051, US8-AS3)
- [ ] T067 [US8] Implement obligation evaluation against acceptance predicates and coverage assumptions: task completion does not close an obligation; an empty result cannot close one without evaluation (FR-048, FR-049, US8-AS1)
- [ ] T068 [US8] Implement the stop-condition set and the stop report with residual unknowns, uncovered scope, unavailable sources and non-executed tasks; an empty queue is explicitly not completion (FR-052, FR-053, US8-AS2, SC-011)
- [ ] T069 [US8] Prove two persisted iterations end to end — new observation → obligation evaluation → invariant revision → context revision → altered next action with an auditable reason — on a clean stack with no donor present (FR-050, US8-AS4, SC-012)

**Checkpoint**: the loop advances for a recorded reason and stops only for a stated one.

---

# Phase 7: WP11 — Donor verticals by measured value (US7)

**Purpose**: promote useful capability without importing a parallel platform.

- [ ] T070 [US7] Promote vertical A — discovery/source coverage — from `CANDIDATE`/`AUDITED` to `WIRED`/`LIVE_PROVEN`, satisfying all ten §8.7 conditions, and record the benchmark gain (FR-040, SC-010)
- [ ] T071 [US7] Promote vertical B — documents and archives — with page/table/WARC spans and licence/data-terms review recorded separately from code licence (FR-040, FR-041)
- [ ] T072 [US7] Promote vertical C — conflict/ontology/dedup — with Semantica adapted per the six-step order of §8.5 and `most_recent` rejected unless validity semantics replace capture ordering (FR-044, US7-AS5)
- [ ] T073 [US7] Promote vertical D — analyst graph and replay UI — with provenance drawers and the `kafSIEM` pack-contract patterns, and **no** `kafSIEM` store, entity types or broker schema (FR-042, US7-AS2)
- [ ] T074 [US7] Evaluate vertical E — temporal/spatial/TDA and optional vector — and record adoption or `DEFERRED` with the measured reason (FR-045)
- [ ] T075 [US7] Prove the disable/rollback route for every promoted vertical: disabling resumes the prior path without deleting raw or derived evidence (FR-040, US7-AS3, SC-010)
- [ ] T076 [US7] Publish the donor benchmark record per vertical in `benchmarks/WP11-<vertical>.md` with corpus, configuration, versions, exit status, runtime, resources and source count (FR-056, SC-013)

**Checkpoint**: each vertical is independently promotable, measurable and disableable.

---

# Phase 8: WP12 — Operations, security, release evidence (US9)

**Purpose**: make the proof reproducible, adversarial and honest.

- [ ] T077 [US9] Write and pass the ten golden end-to-end cases of §11.1 in `tests/golden/`, including the failure/restart/replay case and the donor disable/rollback case (FR-055, SC-012)
- [ ] T078 [P] [US9] Write and pass the security corpus in `tests/security/`: SSRF, redirect-to-private, DNS rebinding, archive bomb, oversized body, secret redaction, cross-tenant reference and access-denied path (SC-014)
- [ ] T079 [P] [US9] Write and pass the replay/idempotency suite in `tests/replay/`: redelivery, retry, cold rebuild parity, and no coverage or independence inflation (SC-004)
- [ ] T080 [P] [US9] Implement fetch-boundary hardening tests: scheme allowlist, DNS A/AAAA validation, per-hop redirect validation with address pinning, streaming size limits, decompression/archive-bomb limits and deadline enforcement (FR-010, FR-011)
- [ ] T081 [US9] Implement backpressure, scoped budgets, egress control, worker isolation, tenant controls, retention/erasure, DLQ/quarantine replay, observability and migrations/backfills/rollback (§12 WP12)
- [ ] T082 [US9] Produce the SBOM, licence and model/data asset inventory release artifact and attach it to the release record (FR-059, §13)
- [ ] T083 [US9] Produce the release validation report in `benchmarks/WP12-release-report.md`: every SC-001…SC-015 marked PASS / FAIL / BLOCKED / NOT-RUN with its evidence command and exit status; `NOT_RUN` is permitted and blocks the release gate (FR-056, SC-013)
- [ ] T084 [US9] Confirm the §13 anti-pattern sweep: no third graph authority, no closed schema for unknown concepts, no `latest value wins` default, no voting over mirrors, no transitive merge, no fact from centrality, no LLM output as evidence, no raw content in payloads, no donor writing canonical stores, no unbenchmarked store, no out-of-scope person data, no simulation promoted to fact (FR-059)

**Checkpoint**: the programme is either proven, or its unproven parts are named.

---

## Dependencies and execution order

```text
WP0 (T001–T012)  ── gate ────────────────────────────────────────────┐
   │                                                                │
   ├─> WP1 (T013–T014) ──> WP2 (T015–T024) ──> WP3 (T025–T029)      │
   │                                    │        │                  │
   │                                    │        v                  │
   │                                    └─> WP4 (T030–T038)        │
   │                                                 │               │
   │                                    ┌────────────┴──────┐        │
   │                                    v                   v        │
   │                             WP5 (T039–T043)      WP6 (T044–T046)│
   │                                    │                   │        │
   │                                    └────────┬──────────┘        │
   │                                             v                   │
   │                                      WP7 (T047–T050)            │
   │                                             │                   │
   │                              ┌──────────────┴─────────┐         │
   │                              v                        v         │
   │                       WP8 (T051–T060)           WP9 (T061–T064) │
   │                              │                        │         │
   │                              └──────────┬─────────────┘         │
   │                                         v                       │
   │                                  WP10 (T065–T069)               │
   │                                         │                       │
   │                                         v                       │
   │                                  WP11 (T070–T076)               │
   │                                         │                       │
   │                                         v                       │
   └──────────────────────────────────> WP12 (T077–T084)
```

**Hard rules**

1. No WP1+ task starts before T012's sign-off record exists (§12).
2. No donor promotion (WP11) before WP4, WP5 and WP8 are complete (§12: "No donor integration promotion before this gate").
3. No performance target is written before the WP0 and WP9 measurements exist (§11.3, FR-057).
4. A task whose precondition never arrives is marked `[!]` with the blocking dependency named — never silently dropped.

## Parallel opportunities

- T002, T003, T004, T005, T007–T011 are independent read-and-record tasks and can run together.
- T015–T022 are separate contract files and can be implemented in parallel; T024 depends on all of them.
- T039–T042 touch different producers and can proceed per producer, but T040 depends on T016.
- T051–T060 are separable by conflict kind, ontology concern and support layer, all depending on T016 and T023.
- T077–T080 are four independent suites.
- T070–T074 are five independent donor verticals — but only after the WP4/WP5/WP8 gate, and each one is promoted alone.

## Implementation strategy

**MVP (US1–US3)**: WP0 → WP1 → WP2 → WP3 → WP4 → WP5. This yields a truthful baseline, one evidence seam, deterministic identity and spans that survive to findings — the minimum on which any later claim can rest. US4–US6 follow, then US8's loop, then US7's donor promotion, then US9's proof.

**Deliberately not in the MVP**: retrieval economics, donor verticals and scale profiles. Each of them is worthless — or actively harmful — without the seam and the spans, and each is measured before it is adopted.
