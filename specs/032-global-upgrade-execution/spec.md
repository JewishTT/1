# Feature Specification: COGNITIVE Global Platform Upgrade — Engineering Execution Programme

**Feature Branch**: `032-global-upgrade-execution`

**Created**: 2026-10-19

**Status**: Draft

**Input**: Owner-supplied normative document `COGNITIVE_Global_Upgrade_Blueprint.md` (v1.0, dated 19 October 2026), reproduced verbatim in [Appendix A](#appendix-a--normative-source-verbatim). Repository: https://github.com/JewishTT/1.

**Source digest**: `sha256:CC62D760A40AC5DBB40A6527FA597F12AC60A0A1378A91AD3CFBD8F013BA4E25` · 74 836 bytes · 757 lines.

---

## Scope Statement

This feature turns the owner's v1.0 **Global Platform Upgrade Blueprint** into an executable
Spec Kit workstream. The blueprint is a *target engineering programme* — its own header states it is
"проектное решение, не заявление о том, что все компоненты уже реализованы" — so every capability
claim it makes about the existing repository is **unverified until proven against the executing
commit**.

The blueprint declares `specs/030-global-platform-upgrade/` as its base workstream and explicitly
forbids a competing context engine or a second architecture spec unless the owner deliberately
versions the scope (§12). This feature therefore does **not** restate the Context Engine design that
Feature 030 already owns. It is the **execution and authority contract** for that programme: the ten
non-negotiable architectural decisions (§0.1–§0.10), the single-owner map for every subsystem
(§2), the evidence seam every runtime must cross (§3.5), the conflict-and-identity authority (§5–§7),
the donor promotion gate (§8.7), the stop semantics of the research kernel (§9.4), the golden
acceptance suite (§11), and the WP0–WP12 dependency order with WP0 as a hard gate (§12).

**Normative precedence.** Where this spec and its Appendix A differ, Appendix A governs. Where this
spec and `030` overlap, the stricter obligation governs and the overlap is recorded in
`plan.md` §"Overlap with Feature 030". The blueprint's own language — Russian and English intermixed —
is preserved verbatim in Appendix A; this spec's narrative is in English because the rest of the
`specs/` tree is.

**Explicit non-goal of this spec**: to declare the upgrade complete, to assert that any named
subsystem already satisfies its contract, or to re-derive the Context Engine design. This spec
defines what "done" means and what must be proven; the WP0 audit and the §11 validation suite report
reality.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The programme starts from a truthful baseline, not from a hypothesis (Priority: P1)

An engineer takes the executing commit and produces a capability matrix: for every capability the
blueprint names, the matrix records *declared / implemented / unit-tested / contract-tested / wired /
live-proven / operational*, the production call sites that reach it, and the authoritative store that
owns each field and event. Competing writers and competing identity schemes are listed by name. No
architecture-changing work starts until this gate passes.

**Why this priority**: the blueprint's WP0 is a gate, not a step (§12: "No architecture-changing work
starts before this gate"). Eight of the ten non-negotiable decisions are about *eliminating competing
authorities*, which cannot be done by an engineer who has not first found them.

**Independent Test**: run the audit against a clean checkout; for one capability (e.g. ArtifactSink)
produce the full row with file paths, test IDs, call sites and store ownership; confirm that a
capability with no production caller is reported as `declared` or `unit-tested`, never `wired`.

**Acceptance Scenarios**:

1. **Given** a capability that has code and a passing unit test but no production call site, **When** the matrix is produced, **Then** its status is `unit-tested`, not `wired` and not `live-proven`.
2. **Given** two modules that both write canonical observation state, **When** the ownership map is produced, **Then** both are named, one canonical owner is designated, and the competing writer is recorded as a defect with a WP reference.
3. **Given** the audit is produced from a dirty tree, **When** it is published, **Then** the exact commit, the dirty-file list, the migration state and the environment envelope are part of the report.
4. **Given** a baseline test suite with pre-existing failures, **When** the baseline is recorded, **Then** those failures are labelled baseline and are not counted as regressions later.

---

### User Story 2 — Every collected byte crosses exactly one evidence seam (Priority: P1)

Every executor family — HTTP, federated search, Common Crawl/Wayback/WARC, structured connectors,
browser/document engines, bulk datasets, specialist registries, isolated external tools — returns its
artifact through one `ArtifactSink` / Observation Gate. Raw bytes are durable and content-addressed
before any publication exists. Capture and record observations carry deterministic identity,
typed locators, and an atomic outbox write.

**Why this priority**: this is decision §0.1 and the WP4 gate. Every downstream guarantee — span
grounding, replay idempotency, coverage accounting, conflict provenance — is unattainable while a
second publication path exists.

**Independent Test**: register a throwaway executor that emits a synthetic artifact; assert the raw
object exists in S3/MinIO, the digest matches, a capture and at least one record observation exist,
the outbox row and the canonical event are in one transaction, and no direct write to canonical
entity or projection stores is possible from the executor's process.

**Acceptance Scenarios**:

1. **Given** an executor that tries to create an observation without first persisting raw bytes, **When** it runs, **Then** the write is rejected and the attempt is recorded.
2. **Given** the same artifact delivered twice with the same idempotency key, **When** the second delivery is processed, **Then** no second semantic result, coverage increment or evidence-independence increment is produced.
3. **Given** a failure after raw write but before outbox placement, **When** recovery runs, **Then** the orphan artifact is reconciled with an explicit placement decision and no invented capture identity.
4. **Given** a source that refuses access, **When** the executor reports, **Then** the outcome is `policy-denied` or `unavailable` — distinct from `failed`, `no-result` and `partial` — and it persists as a durable result.
5. **Given** a redirect to a private address or a DNS-rebinding attempt, **When** the fetch proceeds, **Then** the connection is refused at the validated address, the hop is recorded, and the source outcome is a policy result rather than a transport failure.

---

### User Story 3 — A finding opens its exact source, and stays openable after a rebuild (Priority: P1)

Every mention, relation candidate, claim and finding references a **typed** span — character range
with encoding, page and bounding box, table cell with header path, JSON pointer, media time range,
WARC record offset — together with `observation_ref`, `blob_digest` and
`selector_semantics_version`. Reprocessing with a different parser creates a new derived revision
with `supersedes`; it never mutates the old one. An unrecoverable span is labelled partial/unresolved,
never given a synthetic offset.

**Why this priority**: decision §0.3 plus WP5. A single `offset` field that can mean bytes, characters,
segments or pages is the defect that silently corrupts every downstream citation.

**Independent Test**: a corpus of one PDF table, one HTML article, one JSON result and one WARC
record; each yields a finding that resolves to the exact stored bytes after a process restart and
after a projection rebuild.

**Acceptance Scenarios**:

1. **Given** a finding grounded in a table cell, **When** its span is resolved, **Then** the resolved bytes equal the stored cell contents and the header path is preserved.
2. **Given** a re-run of a parser at a new version, **When** the output changes, **Then** a new derived artifact is created with the new operator fingerprint, and the old artifact remains retrievable.
3. **Given** a span that cannot be reconstructed, **When** the finding is presented, **Then** it is marked partial/unresolved and is not rendered as grounded.
4. **Given** two selector-semantics versions, **When** their spans are compared or summed, **Then** the system refuses the operation without an explicit conversion policy.

---

### User Story 4 — Contradiction is a first-class state, never a low score (Priority: P1)

When claims are compared, the platform first establishes comparability — resolved participants,
predicate mapping and ontology version, units, currency, period, jurisdiction, valid-time
intersection, source dependency root — and only then declares a conflict. Each claim carries
independent positive and negative support, and the derived epistemic state is four-valued:
`NEITHER`, `TRUE_ONLY`, `FALSE_ONLY`, `BOTH`. A resolver proposes; admission decides; the losing side
is never deleted.

**Why this priority**: §0.4 and the WP8 gate. The blueprint is explicit that `BOTH` is not low
confidence, that a source that said nothing is not negative evidence, and that "most recent" is a
capture timestamp, not a truth rule.

**Independent Test**: the contradiction corpus of §11.1(5) — value, type, relation, temporal,
logical, identity, provenance and scope cases, plus syndicated duplicates and mismatched
currencies — produces the expected conflict kind, or `NOT_A_CONFLICT` with a stated reason.

**Acceptance Scenarios**:

1. **Given** "CTO 2019–2021" and "VP Engineering from 2022", **When** the comparator runs, **Then** the outcome is a temporal transition, not a contradiction.
2. **Given** two concurrent salary claims in different currencies and compensation periods, **When** compared, **Then** no conflict is declared until units and periods are matched.
3. **Given** three URLs that all republish one upstream wire story, **When** voting is applied, **Then** the vote counts one independent lineage root, not three sites.
4. **Given** genuinely incompatible claims with balanced support, **When** resolution runs, **Then** the resolver may abstain, keeps `BOTH`, opens a discriminating-evidence obligation, and the conflict status records the abstention with its reason.
5. **Given** an adjudicated conflict, **When** the decision is recorded, **Then** it is append-only with actor, rationale, conflict snapshot and expected context revision, and it remains re-openable.

---

### User Story 5 — Identity is an admission decision, not a similarity score (Priority: P2)

Blocking generates candidates at sub-quadratic cost with a recorded blocking trace. A pairwise score
ranks candidates; it never merges. Collective methods may propose clusters and contradictions, but
`A≈B` and `B≈C` do not imply `A=C` when `A–C` evidence is inconsistent. Merge and split are
append-only decisions with history, and correcting a false merge changes current grouping without
rewriting the source claims created under the earlier interpretation.

**Why this priority**: decision §0.5 and WP4. It is the single most consequential irreversible action
the platform takes about a real person.

**Independent Test**: a labelled pair corpus with a deliberate transitive-merge trap (`A≈B`, `B≈C`,
`A≠C`); assert no merge is committed, the contradiction is surfaced, and the correction of a
previously committed merge regenerates projections without mutating prior claims.

**Acceptance Scenarios**:

1. **Given** a candidate pair with a high similarity score and no negative evidence check, **When** admission runs, **Then** the score ranks the candidate but cannot commit the merge.
2. **Given** a similarity chain across three references, **When** collective resolution runs, **Then** the A–C inconsistency blocks the transitive merge and is recorded.
3. **Given** a committed false merge, **When** it is split, **Then** prior source claims remain unchanged, current grouping changes, and projections are regenerated through explicit supersession.
4. **Given** an entity whose canonical record is derived from the accepted stream, **When** a property is disputed, **Then** the invariant view shows alternatives and unknowns rather than silently selecting one value.

---

### User Story 6 — Time answers three different questions and never substitutes `now()` (Priority: P2)

The platform distinguishes publication, validity, observation, capture, knowledge, processing and
projection time, and answers `CURRENT`, `AS_OF(known_time)` and `INTERVAL(valid_from, valid_until)`
differently. A 2026 document about 2020 refines the current reconstruction of the past without
retroactively changing what the system knew in 2025.

**Why this priority**: §7 and WP3. Temporal shortcuts are the most common way an evidence system
silently fabricates history.

**Independent Test**: acquire a 2026 document asserting a 2020 valid-time fact; assert `CURRENT`,
`AS_OF(2025)` and `INTERVAL(2020)` each return the correct, distinct result, and that the `AS_OF`
answer does not change after the late capture.

**Acceptance Scenarios**:

1. **Given** a claim with unknown publication time, **When** it is stored, **Then** the time is recorded as unknown and `now()` is not substituted.
2. **Given** a late-arriving capture, **When** `AS_OF(t)` is queried for `t` before the capture, **Then** the answer is unchanged and the late capture is visible only in later knowledge states.
3. **Given** a birth date with no source-backed claim, **When** a lifecycle is rendered, **Then** no birth event is synthesised.
4. **Given** a cold fold and a replay of the same stream, **When** both reducers run, **Then** their revision digests match, and a redelivery does not produce a new revision.

---

### User Story 7 — A donor is a capability, promoted only against evidence (Priority: P2)

Every donor is recorded in `donors/registry.yaml` with pinned upstream revision, licence separated by
artifact class (code, model weights, datasets, docs, assets, data sources), the exact file or
algorithm transferred, the target contract, the adapter call path, test IDs, benchmark baseline,
feature flag, kill switch and owner. Promotion to `LIVE_PROVEN` requires all ten gate conditions of
§8.7, including a production call site and a measured quality/cost/latency gain.

**Why this priority**: §0.9 and WP11. The blueprint's central donor thesis is that useful capability
is maximised, not repository count — and that no donor may become a parallel platform.

**Independent Test**: take one donor vertical (e.g. Semantica conflict detection), run it behind an
`OperatorResult` adapter against the frozen corpus, promote it, then disable it; assert canonical
evidence and prior derived revisions are intact and the baseline path resumes.

**Acceptance Scenarios**:

1. **Given** a donor whose README claims a capability but whose licence for model weights is unresolved, **When** the registry is reviewed, **Then** the capability is `AUDITED` at most and cannot be promoted.
2. **Given** a donor adapter that writes to a canonical store, **When** it is wired, **Then** the write is rejected and promotion is blocked pending an adapter fix.
3. **Given** a promoted donor, **When** its flag is disabled, **Then** the prior path resumes without deleting raw or derived evidence.
4. **Given** the ambiguous donor name `AEGiS`, **When** it is registered, **Then** it is recorded as `UNVERIFIED / URL_REQUIRED` and is not selected by name similarity.
5. **Given** a donor strategy `most_recent`, **When** it is proposed for production, **Then** it is rejected unless validity-time semantics replace capture-time ordering.

---

### User Story 8 — The kernel stops only for a stated reason (Priority: P2)

The Context Engine owns what the investigation is trying to establish. It evaluates obligations
against explicit acceptance criteria, recomputes the next eligible action with a component vector,
and terminates only for analyst closure, met criteria, policy/budget block, missing capability, or
measured saturation under a stated scope. Every terminal state produces a stop report naming
residual unknowns, uncovered scope, unavailable sources and unexecuted tasks.

**Why this priority**: §9.4 and WP10. An empty queue is not completion; a completed task does not
satisfy an obligation; a low score is not evidence of absence.

**Independent Test**: run two persisted iterations where a new observation changes the next action
for a recorded reason, then force each stop condition and assert the report distinguishes them.

**Acceptance Scenarios**:

1. **Given** a completed task, **When** the obligation is evaluated, **Then** the obligation does not close unless its acceptance predicates and coverage assumptions are met.
2. **Given** an empty frontier, **When** the kernel evaluates, **Then** the state is not `complete`; the report names the residual obligations and the reason the queue is empty.
3. **Given** a high expected-gain action that violates a hard scope or budget constraint, **When** ranking runs, **Then** the action is filtered out before utility ranking and cannot override the constraint.
4. **Given** two persisted iterations, **When** the second runs, **Then** the next action changed with an auditable reason and a context revision was appended.

---

### User Story 9 — "Done" is a validated end-to-end proof on a clean stack (Priority: P3)

The platform demonstrates the ten golden cases of §11.1 and the mandatory assertions of §11.2 on a
clean stack: natural-language context to durable finding with re-openable provenance and a changed
next action. No metric is fabricated; an unavailable measure is `null` with a named reason.

**Why this priority**: decision §0.10 and WP12. Separate green tests and live demos are explicitly
not a substitute for one end-to-end proof.

**Independent Test**: clean database, clean object store, clean event backbone; run the public-source
dossier fixture from §10 and the failure/restart/replay fixture from §11.1(8) to completion.

**Acceptance Scenarios**:

1. **Given** the full fixture suite, **When** it runs, **Then** 100 % of accepted claims and findings resolve to a content address and a typed span, or are explicitly partial/unresolved.
2. **Given** a replay of identical evidence, **When** it is compared to the first run, **Then** no second semantic result, coverage inflation, independence inflation or extra revision appears.
3. **Given** a projection, **When** it is deleted and rebuilt from its declared source cut, **Then** the output digest matches and the manifest reports the rebuild.
4. **Given** a benchmark, **When** it is published, **Then** it prints the input corpus, configuration, operator/model versions, exit status, runtime, resource figures and source count, with `null` plus a reason where a measure is unavailable.

---

## Requirements *(mandatory)*

Requirement IDs are stable and are the traceability anchor for `plan.md` and `tasks.md`. Section
references (§n) point into Appendix A.

### Functional Requirements — Authority and the evidence seam (§0, §2, §3.5)

- **FR-001**: Every executor family MUST deliver artifacts through the single `ArtifactSink` / Observation Gate; no runtime MAY create an independent canonical observation or write directly to canonical entity or projection stores (§0.1).
- **FR-002**: `ArtifactSink` MUST persist raw bytes before publication, compute a digest and content-addressed reference, and create deterministic capture/observation identity under a declared identity-scheme version (§3.5.1–§3.5.3).
- **FR-003**: The sink MUST support one parent capture with multiple record observations and typed locators — JSON Pointer, table cell, WARC record, page span — preserving membership and provenance context (§3.5.4–§3.5.5).
- **FR-004**: Outbox/event delivery MUST be written atomically in the approved transaction seam, and the sink MUST return acknowledged publication details rather than only logging success (§3.5.6–§3.5.7).
- **FR-005**: Replay MUST be idempotent: repeating a delivery MUST NOT increase coverage, evidence independence, cost learning, or produce extra semantic revisions (§3.5.8).
- **FR-006**: Every object MUST have exactly one canonical owner, and every projection MUST carry a `ProjectionManifest` with inputs/offsets/source cut, builder and operator version, output digest, staleness, status, kill switch and a tested rebuild route (§2).
- **FR-007**: The assignment of a single authoritative store per data class MUST follow the blueprint's storage map: S3/MinIO for immutable raw, PostgreSQL for operational and relational canonical state, the Kafka-compatible backbone for transport only, OpenSearch/BM25 for lexical retrieval, ClickHouse for metrics, Neo4j strictly as a serving projection, Redis strictly as cache/lease acceleration, Temporal strictly for long-running workflows, and Qdrant/pgvector/JanusGraph only as benchmarked optional profiles (§2).
- **FR-008**: The `AcquisitionTask` vNext contract MUST carry tenant, investigation, context and context-revision identity; obligation, action, task and parent-work refs; source, runtime, capability and query refs; scope, access mode, policy snapshot and credential reference; temporal/geographic filters and requested depth; byte, record, timeout and compute budgets; retry/idempotency keys, checkpoint refs, schedule and priority; and expected result kinds with acceptance criteria (§3.2).
- **FR-009**: Secrets MUST NOT appear in event payloads, query logs or donor manifests; only references into a managed secret store are permitted (§3.2).
- **FR-010**: The fetch boundary MUST enforce URL-scheme allowlisting, DNS A/AAAA validation, rejection of loopback/private/link-local/metadata/reserved ranges, per-hop redirect validation with DNS-rebinding protection, streaming reads with size limits, decompression and archive-bomb limits, and connection/read/total deadlines (§3.4).
- **FR-011**: The fetch boundary MUST enforce per-tenant/source/host rate policy, jittered retries with budgets, cool-down and backpressure, and MUST NOT bypass login, CAPTCHA, paywall, anti-bot protection or other access controls (§3.4).
- **FR-012**: Executor outcomes MUST distinguish at least `policy-denied`, `unsupported`, `unavailable`, `failed`, `partial`, `no-result` and `accepted` (§3.4).
- **FR-013**: The eight executor families of §3.3 MUST each be reachable through the one seam, including structured connectors that keep RECORD separate from STATE/LOG/TRACE and checkpoint only after durable persistence.

### Functional Requirements — Interpretation and spans (§4)

- **FR-014**: Every parser, extractor and normalizer MUST be invoked through a common `OperatorResult` carrying status, outputs, warnings and partial coverage; input observation IDs, digests and spans; operator name/version, parameters, config and model fingerprint; output digest, determinism/replay mode and resource consumption; language, encoding, locale, format and semantic-version references (§4.1).
- **FR-015**: Reprocessing MUST NOT mutate an existing derived artifact; it MUST create a new revision with `supersedes` and retain the prior output (§4.1).
- **FR-016**: Every mention, claim and finding MUST reference a typed `EvidenceSpanRef` from the enumerated span kinds — character range with encoding, page with coordinate system and bounding box, table row/column/header path, JSON pointer or structured record locator, media time range with track/frame, WARC offset with record digest, geometry reference, source locator fragment (§4.2).
- **FR-017**: Every span MUST carry `observation_ref`, `blob_digest` and `selector_semantics_version`; incompatible selector-semantics versions MUST NOT be summed or converted without an explicit conversion policy (§4.2).
- **FR-018**: An unrecoverable span MUST produce a partial/unresolved finding, never a synthetic offset (§4.2).
- **FR-019**: The evidence layer (immutable raw and literal observation) and the interpretation layer (normalized forms, translations, parsed dates, aliases, entities, relations, events) MUST be stored as distinct models with versions and lineage to source form (§4.3).
- **FR-020**: Normalization MUST NOT rewrite the original string; observed variants with provenance and mappings are retained and the canonical form is a recomputable derived object (§4.3).
- **FR-021**: `Mention`, `EntityReference`, `RelationCandidate` and `ClaimCandidate` MUST retain the original wording even for unknown types or predicates; an unknown predicate is a valid open-world record with `mapping_status=unknown_predicate` (§4.4).
- **FR-022**: Operator result types MUST distinguish unsupported format/operator, successful parse with no candidates, partial parse, malformed input, timeout/resource limit, and quarantine/security refusal (§4.4).

### Functional Requirements — Ontology, identity and conflict (§5–§7)

- **FR-023**: `OntologyPackRevision` MUST describe entity-type signatures, property definitions, relation predicates with direction, arity, roles and domain/range hints, cardinality and exclusivity and symmetry/inverse/transitivity, temporal and validity semantics, unit and normalization rules, conflict-compatibility rules, evidence requirements, admission policy, source-family mappings and aliases, provenance, revision digest and validator fingerprints (§5.1).
- **FR-024**: Ontology lifecycle MUST be `DRAFT → PROPOSED → VALIDATED → ACTIVE → RETIRED` with explicit governance decisions; an active revision binds to a context or operator and MUST NOT reinterpret the past retroactively (§5.1).
- **FR-025**: Ontology extension MUST proceed through gap monitoring, mapping proposals that retain alternatives and evidence, validation against frozen fixtures and conflict examples, approval, and re-interpretation that creates new derived artifacts while preserving old mappings and claims with revision lineage (§5.2).
- **FR-026**: The model MUST distinguish `Mention`, `EntityReference`, `ResolutionCandidate`, `ResolutionDecision`, `EntityInvariant` and `Worldline` as defined in §5.3, and `EntityInvariant` MUST be a versioned relational invariant over evidence and policy — not a single row holding final truth (§5.3).
- **FR-027**: Candidate generation MUST avoid all-pairs comparison and MUST retain a trace of the blocking method; pairwise scores rank candidates and MUST NOT commit merges; collective methods MUST NOT transitively merge across inconsistent evidence; co-occurrence and shared address/domain are contextual evidence, not identity proof (§5.4).
- **FR-028**: Merge/split MUST append revisions and aliases; existing claims MUST retain the resolution interpretation under which they were created; a corrected false merge MUST NOT rewrite prior source claims (§5.4).
- **FR-029**: A `Conflict` MUST be detected under a stated ontology, temporal frame, scope and compatibility policy, and MUST be distinguishable from low confidence; the eight conflict kinds of §6.1 MUST each be representable (§6.1).
- **FR-030**: Before declaring a conflict the system MUST compare resolved participants and identity revision, predicate mapping and ontology version, units/currency/period/jurisdiction/qualifier, valid-time intersection and timestamp precision, source and capture/publication/event times, evidence dependency root, and whether the predicate pair is declared mutually exclusive (§6.2).
- **FR-031**: `ConflictRecord` MUST carry the fields of §6.3 and a status from `OPEN`, `INVESTIGATING`, `PROVISIONALLY_RESOLVED`, `ADJUDICATED`, `REOPENED`, `NOT_A_CONFLICT`, with every transition and its reason preserved; `NOT_A_CONFLICT` MUST state what was established (§6.3).
- **FR-032**: Every claim MUST retain independent `support_positive[]` and `support_negative[]`, and the derived epistemic status MUST be four-valued `NEITHER` / `TRUE_ONLY` / `FALSE_ONLY` / `BOTH`; `BOTH` MUST NOT be collapsed into low confidence; silence MUST NOT count as negative support (§6.4).
- **FR-033**: The resolver MUST support the seven policy plug-ins of §6.5 — authority/credibility-weighted, temporal applicability, independent corroboration over lineage roots, ontology/constraint-based, source-of-record precedence, analyst adjudication, and abstain-with-discriminating-evidence — and MUST emit a `ResolutionProposal`, never a deletion (§6.5).
- **FR-034**: Admission MUST create the append-only `ResolutionDecision`; a provisional winner MUST NOT delete the losing side and MUST remain re-openable (§6.5).
- **FR-035**: `most_recent` MUST NOT be the default policy and MUST NOT order by capture time where the predicate requires validity or source time (§6.6).
- **FR-036**: The temporal model MUST distinguish `source_published_at`, `source_valid_from`/`source_valid_until`, `source_observed_at`, `captured_at`/`fetched_at`, `recorded_at`/`known_at`, `processed_at` and `projected_at`, and MUST NOT substitute `now()` for an unknown time or infer causality from temporal precedence (§7).
- **FR-037**: Query modes `CURRENT`, `AS_OF(known_time)` and `INTERVAL(valid_from, valid_until)` MUST be distinct and correct; a late capture MAY refine the current reconstruction of a past interval but MUST NOT change `AS_OF` history before its registration (§7).

### Functional Requirements — Donors (§8)

- **FR-038**: `donors/registry.yaml` MUST reconcile the eleven existing donor catalogues (`docs/architecture/donors/00–10`), vendored trees, dependencies and new candidates, recording for each capability the fields enumerated in §8.1.
- **FR-039**: Donor status MUST be drawn from `CANDIDATE`, `AUDITED`, `ADAPTED`, `TESTED`, `WIRED`, `LIVE_PROVEN`, `DEFERRED`, `REJECTED`, `METHODOLOGY_ONLY` (§8.1).
- **FR-040**: A donor MAY become `LIVE_PROVEN` only when all ten conditions of §8.7 hold, including an `OperatorResult` adapter, no canonical writes, span-or-partial linkage, distinguishable failure classes, passing contract/unit/integration/live-replay tests, a production call path, measured gain, a disable route, and documented ownership (§8.7).
- **FR-041**: The donor matrix of §8.2 MUST be honoured per vertical, including its stated restrictions; in particular Common Crawl terms MUST NOT be treated as a generic open licence, only RECORD-derived data may become evidence for structured connectors, and spec-ops tooling MUST stay in a separate lab profile (§8.2).
- **FR-042**: `kafSIEM` may supply pack-contract and analyst-workflow patterns; its SQLite store, collector process, entity types and broker schemas MUST NOT become a second authority, and the legacy CSS lineage MUST be resolved before further code is copied (§8.3).
- **FR-043**: `AEGiS` MUST be recorded as `UNVERIFIED / URL_REQUIRED` until the intended upstream is pinned, and MUST NOT be selected by name similarity (§8.4).
- **FR-044**: `Semantica` extraction MUST follow the six-step order of §8.5 and MUST NOT accept `most_recent` without validity semantics, MUST count independent lineage roots for `voting`, and MUST NOT let a confidence score replace four-valued epistemic support.
- **FR-045**: JanusGraph/ScyllaDB MUST remain a candidate profile pending measurement of cardinality, degree skew, traversal fanout/depth, mix, tenancy filtering, index consistency, recovery and operational cost; no graph-store migration before benchmark (§8.6).

### Functional Requirements — Research kernel and stopping (§9)

- **FR-046**: `ContextDefinition` MUST be immutable and versioned over objective, compiled intent AST, target/scope, time mode, allowed source universe, ontology/reasoning profile, output requirements, budgets, access policy, freshness, quality and stop conditions; `InvestigationContext` MUST be the durable, revisioned execution state (§9.1).
- **FR-047**: Changing intent or scope MUST either pin the in-flight investigation to the existing definition version or emit an explicit rebase; old revisions MUST NOT be silently reinterpreted (§9.1).
- **FR-048**: `ResearchObligation` MUST NOT be an acquisition task; it MUST carry trigger, parent gap/hypothesis/conflict, required outcome, acceptance predicates, source/capability requirements, unknown dependencies, priority vector, cost estimate, attempts, marginal gain and stop/satisfaction rules (§9.2).
- **FR-049**: One obligation MAY generate many tasks and one observation MAY satisfy several obligations; task completion MUST NOT automatically satisfy an obligation; empty output MUST NOT close a gap without evaluation against its criteria and coverage assumptions (§9.2).
- **FR-050**: After each outcome the kernel MUST recompute open/satisfied/partial/blocked/superseded obligations, claim and hypothesis support changes, new or reopened conflicts, unresolved identities, source coverage and independence and freshness, eligible/blocked/approval-required actions with their component vector, and the reason to continue, pause, saturate or close (§9.3).
- **FR-051**: Hard access, scope, tenant and budget constraints MUST filter before utility ranking; no expected-gain score MAY override them; adaptive or LLM components MAY propose ordering but MUST NOT bypass deterministic policy (§9.3).
- **FR-052**: Termination MUST NOT be triggered by an empty queue, exhausted retries, a completed task, a low score or an empty result list; permitted outcomes are analyst closure, met acceptance criteria, policy/budget block, missing capability, or measured saturation under a stated scope and source universe (§9.4).
- **FR-053**: Every terminal state MUST produce a stop report naming residual unknowns, uncovered scope, unavailable sources and non-executed tasks (§9.4).

### Functional Requirements — Validation, programme and non-goals (§10–§13)

- **FR-054**: The end-to-end dossier scenario of §10 MUST be executable as a fixture against authorized data only, with separate policy/legal-basis gates for personal contacts and relationship inference, minimization and redaction (§10).
- **FR-055**: The ten golden cases of §11.1 MUST exist and pass on a clean stack (§11.1).
- **FR-056**: The mandatory assertions of §11.2 MUST hold, including 100 % span resolution or explicit partiality, replay non-inflation, new derived revisions on parser/model/policy change, no merge from score or centrality alone, individually queryable conflicting claims, `BOTH` distinct from low confidence, no qualified absence without declared detection power, tested projection rebuilds, donor-disable evidence preservation, terminal-state stop reports, and honest benchmark reporting (§11.2).
- **FR-057**: Performance targets MUST NOT be set before the §11.3 measurements exist; the blueprint's scale figures are scenarios to benchmark, not guarantees (§11.3).
- **FR-058**: Work MUST follow the WP0→WP12 order of §12 with WP0 as a hard gate, and the P0 work order of §12 (§12).
- **FR-059**: The non-goals and anti-patterns of §13 MUST be treated as prohibitions: no third graph authority, no closed schema for unknown concepts, no `latest value wins`, no voting over syndicated mirrors, no transitive merge on a similarity chain, no fact creation from centrality or link prediction, no LLM output as source evidence, no raw content in event payloads or logs where a reference suffices, no donor writing canonical stores, no new graph or vector store without benchmark and rollback, no automatic person-data collection beyond permitted scope, and no simulation promoted to observed fact (§13).

### Key Entities *(include if feature involves data)*

- **Artifact / Capture / Observation / Locator**: the immutable evidence unit, its deterministic identity, its record-level children and their typed positions in the stored bytes (§3.5).
- **AcquisitionTask**: the durable work order carrying context, obligation, capability, policy and budget binding (§3.2).
- **OperatorResult**: the universal interpreter envelope with status, spans, fingerprints and resource cost (§4.1).
- **EvidenceSpanRef**: the typed, versioned pointer from a derived statement into stored bytes (§4.2).
- **OntologyPackRevision**: the versioned semantic contract with lifecycle and governance (§5.1).
- **Mention / EntityReference / ResolutionCandidate / ResolutionDecision / EntityInvariant / Worldline**: the identity chain from textual occurrence to versioned relational invariant (§5.3).
- **ConflictRecord / ResolutionProposal / SupportSet**: the contradiction, its proposed resolution and the independent positive/negative support structure (§6).
- **ContextDefinition / InvestigationContext / ResearchObligation / Action / ContextRevisionPlan**: the research process state machine (§9).
- **ProjectionManifest / StopReport / CapabilityMatrix / DonorRegistryEntry**: the accounting surfaces that make the platform auditable (§2, §8, §9.4, §12).

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001 (baseline truth)**: the WP0 capability matrix covers 100 % of capabilities named in the blueprint, each with a status, call sites and store owner; zero capabilities are labelled `wired` or `live-proven` without a production call path.
- **SC-002 (one seam)**: 100 % of executor families deliver through `ArtifactSink`; the number of canonical-observation writers is exactly 1; a bypass attempt is rejected in test.
- **SC-003 (grounding)**: 100 % of accepted claims and findings in the fixture suite resolve to a content address and a typed span, or are explicitly marked partial/unresolved — zero synthetic offsets.
- **SC-004 (replay)**: a full replay of identical evidence produces zero additional semantic results, zero coverage inflation, zero independence inflation and zero extra revisions.
- **SC-005 (derived revisioning)**: 100 % of parser, model and policy version changes produce a new derived revision while the raw digest is unchanged.
- **SC-006 (identity safety)**: zero merges committed by score, centrality or transitive similarity alone in the adversarial corpus; every merge is traceable to a `ResolutionDecision`.
- **SC-007 (epistemic fidelity)**: `NEITHER`, `TRUE_ONLY`, `FALSE_ONLY` and `BOTH` survive storage, events, API, export and UI; zero cases of `BOTH` rendered as low confidence or of silence counted as negative support.
- **SC-008 (temporal fidelity)**: `CURRENT`, `AS_OF(t)` and `INTERVAL(a,b)` return distinct correct answers on the late-data fixture; zero substitutions of `now()` for unknown time.
- **SC-009 (projection integrity)**: every production projection has a tested rebuild that reproduces its declared digest; zero obligations satisfied by a stale projection without a recorded staleness decision.
- **SC-010 (donor governance)**: 100 % of promoted donors have a complete licence/asset manifest, an adapter, a production call site, a measured gain and a proven disable route; disabling any donor leaves canonical evidence intact.
- **SC-011 (stop honesty)**: 100 % of terminal investigations carry a stop reason; zero investigations closed on an empty queue, exhausted retries, low score or empty result alone.
- **SC-012 (end-to-end proof)**: the ten golden cases of §11.1 pass on a clean stack, including failure/restart/replay at each seam and the donor disable/rollback case.
- **SC-013 (honest measurement)**: 100 % of published benchmarks print corpus, configuration, versions, exit status, runtime, resources and source count; every unavailable measure is `null` with a named reason.
- **SC-014 (security boundary)**: the security corpus — SSRF, redirect-to-private, DNS rebinding, archive bomb, oversized body, secret redaction, cross-tenant reference, access-denied path — passes with zero bypasses.
- **SC-015 (programme order)**: WP0..WP12 are evidenced in order; no architecture-changing work is merged before the WP0 gate is signed off.

## Assumptions

- The executing repository is reachable at https://github.com/JewishTT/1 and its current head is the object of the WP0 audit; the blueprint's own capability claims are treated as unverified.
- Feature `030-global-platform-upgrade` remains the program-level workstream and is the authority for the Context Engine design; this feature supplies the execution contract, the authority map and the validation gate without creating a competing engine.
- The infrastructure listed in §2 (PostgreSQL, S3/MinIO, Kafka-compatible broker, OpenSearch, ClickHouse, Redis, Temporal, Neo4j) is either present or explicitly reported absent by WP0; no optional backend is assumed.
- `docs/architecture/donors/00–10` is the current donor catalogue and is reconcilable; where a catalogue entry and a vendored tree disagree, the vendored tree wins and the discrepancy is recorded.
- The blueprint's Russian-language sections are authoritative in their original wording; this spec's English rendering is a working translation and Appendix A resolves any dispute.
- Owner sign-off exists for the WP0 gate and for each `LIVE_PROVEN` donor promotion; the platform does not self-authorise scope.

## Out of Scope Confirmation

- Re-designing the Context Engine or creating a second architecture spec; that is Feature 030's and the owner's decision (§12).
- Declaring any component production-ready on the strength of code presence, a README or a green unit test (§0.9, §13).
- Migrating canonical truth to JanusGraph, Qdrant or any new store before a workload benchmark and rollback plan (§8.6, §13).
- Automatic collection of sensitive personal data beyond an explicitly permitted scope; publicly visible content is not blanket authorization (§10, §13).
- Treating simulation, causal narrative, graph centrality or LLM output as observed fact or source evidence (§13).
- Setting p50/p95 or concurrency targets before the §11.3 measurements exist (§11.3).
- Importing a donor as a parallel platform with its own database, identity model and event schema (§8.1).

---

## Appendix A — Normative source (verbatim)

The document below is the owner's v1.0 blueprint, reproduced **without modification**. It is the
governing text for this feature: where this spec's narrative, requirements or success criteria
conflict with it, this appendix prevails.

**Provenance**: `COGNITIVE_Global_Upgrade_Blueprint.md` · SHA-256 `CC62D760A40AC5DBB40A6527FA597F12AC60A0A1378A91AD3CFBD8F013BA4E25` · 74 836 bytes · 757 lines · supplied 2026-10-19 · copied 2026-10-19.

**Integrity check**: the block between the two HTML comment markers below is byte-for-byte the source
file. Re-extract and hash it with:

```powershell
$raw  = Get-Content .\specs\032-global-upgrade-execution\spec.md -Raw
$s    = $raw.IndexOf('<!-- BEGIN VERBATIM SOURCE -->
```markdown
# COGNITIVE — Global Platform Upgrade Blueprint

**Версия:** 1.0  
**Дата:** 19 октября 2026  
**Статус:** целевая инженерная программа; это проектное решение, не заявление о том, что все компоненты уже реализованы.  
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

```
<!-- END VERBATIM SOURCE -->')
$body = $raw.Substring($s, $e - $s).Trim("`r","`n")
$text = ($body -replace '(?s)^```markdown\r?\n', '') -replace '\r?\n```$', ''
$sha  = [Security.Cryptography.SHA256]::Create()
$hash = $sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($text))
([BitConverter]::ToString($hash) -replace '-', '')
```

The published value must be `CC62D760A40AC5DBB40A6527FA597F12AC60A0A1378A91AD3CFBD8F013BA4E25`.

<!-- BEGIN VERBATIM SOURCE -->
```markdown
```
<!-- END VERBATIM SOURCE -->
