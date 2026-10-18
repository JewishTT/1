# Feature Specification: COGNITIVE Global Platform Upgrade — Context Engine as Research Process Kernel

**Feature Branch**: `030-global-platform-upgrade`

**Created**: 2026-10-14

**Status**: Draft

**Input**: User description: "COGNITIVE — Глобальный апгрейд платформы: полное инженерное ТЗ (контекстный движок, интеграция кода доноров, evidence fabric, retrieval, аналитика и замкнутый цикл расследования) + Полномасштабное ТЗ на Context Engine (CE-001 — Context Engine as Research Process Kernel). Репозиторий: https://github.com/JewishTT/1"

---

## Scope Statement

This feature is the **program-level modernization of COGNITIVE**, governed by two normative
documents supplied by the owner:

1. **Global Platform Upgrade** — audit, contracts, invariant/worldline integrity, Context Kernel,
   donor code integration, retrieval/frontier economics, projection fabric, operations.
2. **CE-001 — Context Engine as Research Process Kernel** — the deep upgrade of the Context
   Engine, the cross-cutting investigation lifecycle, research state, and donor-backed verticals.

Both documents are **normative specifications**, not idea lists. This spec consolidates them into a
single testable contract. Where the two documents differ in vocabulary, the **semantics** of both are
preserved; where they overlap, the stricter obligation governs.

**Authority note**: the documents assert that a repository state exists at revision
`608c3ad8f4743e4e729807c903b0364ed571b311`. Every capability claim in this spec is treated as
**unverified until proven against the executing commit**. The audit (WP0 / CE-WP00) is a
prerequisite deliverable, not an optional exercise.

**Explicit non-goal of this spec**: to declare the upgrade complete. This spec defines what
"complete" means and what must be proven; the engineering report (§23) reports reality.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — The analyst asks; the platform works the problem and explains its next move (Priority: P1)

An analyst opens an investigation with a question, a time scope, an allowed source universe and a
budget. The platform holds a durable, revisioned research state, identifies what is not yet known,
opens explicit research obligations, proposes permitted actions with an inspectable
benefit/cost breakdown, executes the permitted ones, and — after every outcome — recomputes what is
known, what is contradicted, what remains unknown, and what to do next. It stops only for an
explicit, recorded reason.

**Why this priority**: the entire platform is worthless as an intelligence product if the research
process does not advance, terminate honestly, and justify its choices. Every other capability in
this feature is a candidate generator or an evaluator plugged into this loop.

**Independent Test**: start an investigation with one obligation; deliver one independently-sourced
observation; assert the obligation transitions to a declared terminal state, the stop report names
the reason, the durable revision chain advanced, and the proposed next action changed with a
recorded justification. This can be validated on a clean stack without any donor component present.

**Acceptance Scenarios**:
1. **Given** an investigation with one open obligation and no evidence, **When** the loop runs, **Then** it opens an obligation with a recorded trigger, acceptance criteria and required capability, and reports the state as *unknown / not searched* — never as *absent*.
2. **Given** an open obligation, **When** a permitted source returns independently-sourced evidence meeting the acceptance criteria, **Then** the obligation reaches a terminal state, a decision record captures why, and a new durable context revision is appended.
3. **Given** an open obligation requiring a capability the platform does not have, **When** the loop runs, **Then** it reports the obligation as *blocked*, naming the missing capability and the constraint that blocked it, and does not spin.
4. **Given** two sources asserting opposing claims, **When** the loop runs, **Then** both supports persist, a contradiction record is opened, the obligation remains open, and no stop reason is emitted.
5. **Given** repeated identical actions that produced no new independent evidence, **When** the loop runs again, **Then** the repeat is suppressed with a recorded reason and an explicit list of conditions that would re-open it.

---

### User Story 2 — Every conclusion opens its source, byte for byte (Priority: P1)

An analyst inspects any finding, claim, extracted relation or analytical feature and reaches the
exact stored bytes that grounded it: document, page, span or cell, capture time, retrieval mode,
parser/operator version and the chain of derivation that led to it. Findings whose provenance is
incomplete are labelled as such and are never presented as grounded.

**Why this priority**: evidence-first is the platform's first constitutional principle. An
ungroundable conclusion is not evidence, and a provenance chain that cannot be replayed cannot be
audited or defended.

**Independent Test**: a document containing a table and a paginated document; a finding derived from
a table cell resolves to that cell's byte range in the stored raw bytes, and a coordinate-bearing
document retains page and box. Re-running a parser at a new version produces a *new* derived
revision and does not alter the raw bytes or the previous interpretation.

**Acceptance Scenarios**:
1. **Given** an accepted claim, **When** its lineage is resolved, **Then** every hop resolves to a content address and a source span that still matches the stored raw bytes.
2. **Given** two producers disagree about the meaning of a positional field, **When** their outputs are compared, **Then** the system refuses to conflate the meanings and reports the ambiguity.
3. **Given** a parser upgrade that changes extracted output, **When** the same raw document is reprocessed, **Then** a new derived revision is created with a new operator fingerprint, and the prior interpretation remains retrievable.
4. **Given** a finding with an unresolvable or partial chain, **When** it is presented, **Then** it is explicitly marked partial / unsupported / hypothesis and is not rendered as a grounded fact.

---

### User Story 3 — The platform does not lie about ignorance (Priority: P1)

An analyst asks a universal question — "who are all the suppliers of X in 2020" — and receives an
honest answer about what was actually established: which sources were searched, what they could
detect, what was found, what was refuted, what contradicts, and what remains unknown because the
source universe could not support an exhaustive claim.

**Why this priority**: the difference between a research platform and a confident narrator is
whether it preserves the distinction between *not investigated*, *searched and found nothing*,
*source unavailable*, *unsupported query*, *qualified absence*, *contradiction* and *refuted*.
Collapsing these into a boolean destroys the value of everything else.

**Independent Test**: a corpus where (a) a source is unreachable, (b) a supported query returns zero
results from a source with declared and declared-undetectable coverage, (c) two sources disagree,
and (d) a predicate is unknown to the platform. Assert four distinct, non-collapsed outcomes across
storage, events, API and UI.

**Acceptance Scenarios**:
1. **Given** a universal ("all", "every", "nobody") question and a source universe whose detection power is unknown, **When** the query completes with zero results, **Then** the result is reported as *searched, no result, informational only* — not as qualified absence and not as refutation.
2. **Given** the same question and a declared source universe with declared detection power meeting the stated coverage threshold, **When** the query completes with zero results, **Then** the platform MAY record a *qualified absence* bounded by that coverage, and the coverage statement travels with the answer.
3. **Given** an unsupported query shape for an available source, **When** it is issued, **Then** the outcome is *unsupported*, distinct from *no result* and distinct from *failure*.
4. **Given** an unknown relation predicate extracted from a document, **When** it is stored, projected and presented, **Then** it survives the whole round trip with its raw label and source span, and is never dropped for lack of a registry entry.

---

### User Story 4 — Identity decisions are made deliberately, never by a score (Priority: P2)

An analyst reviews entity resolution decisions. The platform proposes candidate identity links with
the evidence that produced them, exposes the cost and confidence semantics, keeps competing
candidates visible, and requires an admission/resolution policy decision before any identity
change. A later correction supersedes the earlier decision without erasing it.

**Why this priority**: identity errors are among the most expensive and hardest-to-detect errors in
the platform; they silently corrupt every downstream projection. The constitution makes identity a
decision, not a similarity measurement.

**Independent Test**: a labeled pair corpus containing transliteration variants, shared addresses,
name changes, missing fields and true negatives. Assert measured false-merge and false-non-match
rates, score calibration, and that a model output, graph proximity or centrality score alone cannot
commit a merge.

**Acceptance Scenarios**:
1. **Given** two candidate records with a high match score, **When** no admission decision is recorded, **Then** no identity change is committed and the pair remains a visible candidate.
2. **Given** a false merge is discovered, **When** the split is applied, **Then** the prior interpretation of existing claims remains traceable to the identity state they were written under, and the split decision supersedes rather than deletes the merge decision.
3. **Given** two pairs A↔B and B↔C match while A↔C feature evidence is inconsistent, **When** clustering runs, **Then** the system does not automatically infer A = C.

---

### User Story 5 — The platform gets more independent knowledge per unit of cost (Priority: P2)

An operator with a fixed budget observes that the platform acquires more *independent, verifiable*
evidence per unit spend than before, spends it on discriminating actions rather than on repeats,
suppresses unproductive repetition, and reports the tradeoff honestly — including the sources it
could not reach and the capabilities it lacked.

**Why this priority**: cost-awareness is what makes a research platform sustainable at scale, and it
is the stated objective of the program. It is subordinate to safety, provenance and identity gates,
which are hard constraints.

**Independent Test**: run a fixed query set and budget against two configurations; compare unique
novel evidence, independent-source groups obtained, duplicate rate and total cost, and confirm the
ranking explanation for each selected action is available.

**Acceptance Scenarios**:
1. **Given** an action that produced no gain under unchanged conditions, **When** the same action becomes eligible again, **Then** it is suppressed with a recorded reason and explicit re-open conditions.
2. **Given** an action whose expected value is high but which violates an access, approval, budget or tenant constraint, **When** ranking runs, **Then** it is excluded regardless of its expected value, and the exclusion reason is recorded.
3. **Given** a result set spanning many syndicated copies of one original, **When** coverage is computed, **Then** the effective independent evidence count does not scale with the copy count, and the platform does not claim broad corroboration.

---

### User Story 6 — Third-party capability is integrated, not listed (Priority: P2)

An engineer integrates a mature external capability (document structure parsing, probabilistic record
linkage, retrieval fusion, temporal or topological analytics) only when it measurably helps. The
capability runs behind a single contract, preserves full evidence provenance, cannot write canonical
state directly, reports failure honestly, and is compared against the existing baseline on the
platform's own data before it is promoted.

**Why this priority**: reuse of proven capability is the specified default; but integration must not
create a second authority, and a dependency added to a manifest is not an integration.

**Independent Test**: run the baseline and the integrated capability on the same corpus, the same
labels, the same compute envelope and the same inputs; compare measured quality and total cost;
verify the rollback switch exists and that disabling the new path deletes nothing.

**Acceptance Scenarios**:
1. **Given** an external capability is integrated, **When** it is disabled, **Then** the previous path resumes, no evidence or candidate is deleted, and already-persisted derived artifacts remain retrievable as historical.
2. **Given** an external capability produced a result, **When** provenance is inspected, **Then** the result identifies its inputs, operator version, method fingerprint, and exact evidence spans — or is explicitly labelled partial.
3. **Given** an external capability returns empty, times out, or does not support the requested input, **When** the outcome is recorded, **Then** the status distinguishes unsupported from no-result from failed, and the caller is informed which occurred.

---

### User Story 7 — The analyst and the platform always agree on the current state (Priority: P3)

An analyst sees, in one place: the question and analysis profile version, what is known, unknown,
blocked, not searched, refuted or contradicted; the competing hypotheses with their support and
counterevidence; the proposed, deferred, suppressed and blocked actions with reasons and costs;
findings with their evidence chains and limitations; the timeline of valid-time and known-time;
projection freshness; budget consumption; and the reason the investigation continues or stops.
Reviewer decisions are recorded and reversible at the policy level.

**Why this priority**: without this, every epistemic guarantee is invisible and therefore unusable by
the people the platform exists to serve.

**Independent Test**: a scenario in which an observation arrives that changes the next recommended
action; the analyst sees the before/after with the cause, and their recorded approval or refusal is
visible and does not alter the original evidence.

**Acceptance Scenarios**:
1. **Given** a stale or failed projection, **When** a decision would depend on it, **Then** the system reports the staleness/blockage instead of silently using older data.
2. **Given** an analyst approves, rejects or defers an action, **When** the decision is recorded, **Then** it is stored with actor, time, rationale and the context revision it applied to, and rejection does not delete the underlying candidate.
3. **Given** two API calls race on the same investigation state, **When** the second arrives with a stale expected revision, **Then** it is rejected for re-evaluation rather than silently overwriting the first.

---

### Edge Cases

- **Late-arriving evidence**: a document valid in 2020 is acquired in 2026. The current
  reconstruction changes; what the system *knew* at an earlier known-time does not.
- **Observation without a home**: an acquisition result is captured but its membership in scope
  cannot be established. It persists as unplaced, does not count toward coverage, and opens an
  explicit gap — it is never attached to a convenient guess.
- **Crash mid-cycle**: the process dies between capture and placement. After restart the state
  resumes from persisted status without duplicating semantic effects, and the reconciler finds
  orphan blobs and pending placements without inventing placements.
- **Poison record**: a malformed message that repeatedly fails. It is quarantined with its failure
  class, retained for replay eligibility, and does not block the pipeline.
- **Denied action**: the highest-expected-value action requires approval that was refused. The
  obligation stays open with the refusal recorded as the reason.
- **Saturated but not omniscient**: marginal expected gain falls below a declared threshold under a
  stated scope and source universe. The platform reports *saturated under stated scope* — never
  "complete knowledge".
- **Duplicate delivery**: the same event, observation or action result arrives twice. Revisions,
  coverage, evidence independence and cost-benefit learning do not inflate.
- **Conflicting timestamps**: a source's own clock disagrees with retrieval time. Both are retained
  with explicit types; neither is overwritten by the other.
- **Cross-tenant access**: a request references another tenant's object. The platform refuses
  without confirming the object's existence through a distinguishable error.
- **Partial operator output**: a parser or model times out halfway. Partial output is stored with
  its partial status and coverage limits, not presented as a complete result.
- **Ambiguous natural-language question**: the request admits multiple readings. Multiple
  interpretations are preserved; a clarification is requested only when safe execution requires it.

---

## Requirements *(mandatory)*

Requirement IDs are stable references. Normative keywords MUST / MUST NOT / SHOULD / MAY are used as
defined in §0.2 of the source specification. Each requirement is machine-verifiable.

### Functional Requirements — Evidence and Provenance Foundation

- **FR-001**: The platform MUST preserve acquired raw source objects as immutable, content-addressed
  artifacts that no parser, model, donor component, projection or user interface can modify.
- **FR-002**: Every observation MUST record the source, the retrieval mode, the acquisition
  timestamp(s), the byte digest, the content type, the acquisition parameters and an immutable
  provenance chain.
- **FR-003**: The platform MUST NOT overwrite or delete previously published interpretations when a
  new parser, model or rule version produces a different result; it MUST append a new derived
  revision with an explicit supersession link.
- **FR-004**: Every accepted claim, assertion, analytical feature and finding MUST be traceable to
  its originating observation and to an addressable span within it (character range, page and box,
  table cell, structured path, timestamp/frame, geometry or archive record).
- **FR-005**: A result whose provenance is incomplete MUST be explicitly labelled partial,
  unsupported or hypothesis, and MUST NOT be presented as fully grounded.
- **FR-006**: Different producers MUST NOT share one ambiguous positional convention; where span
  semantics cannot be reconciled, the platform MUST refuse to conflate them and report the
  ambiguity rather than aggregating them.
- **FR-007**: All derived artifacts MUST carry the operator identity, operator version, method
  fingerprint, parameter fingerprint and output digest of the run that produced them.

### Functional Requirements — Epistemic Semantics

- **FR-010**: The platform MUST preserve as mutually distinguishable: unknown-not-investigated,
  no-observations, source-unavailable, query-unsupported, searched-no-result, qualified absence,
  positive support, negative support, both/contradiction, inconclusive, blocked/partial, refuted,
  and saturated-with-scope.
- **FR-011**: Positive and negative support MUST be stored and computed as independent dimensions;
  absence of positive support MUST NOT be treated as negative support, and conflict MUST NOT
  collapse to a boolean.
- **FR-012**: Contradictory claims and their supporting evidence MUST remain simultaneously
  available; contradiction state MUST NOT be resolved by recency, document count, a single high
  score, or last-write-wins.
- **FR-013**: Unknown entity types, relation predicates, attributes and source output kinds MUST be
  preserved with their original label and span; registry mismatch MUST produce an explicit
  unknown/conflict/unsupported marker rather than a silent drop.
- **FR-014**: For queries with universal quantification, the platform MUST compute an attainable
  completeness mode from the declared source universe, coverage, freshness, capability availability,
  budget and detection power; when the preconditions do not hold, the result MUST degrade to
  "candidates observed within the stated coverage" with an enumerated list of limitations.
- **FR-015**: Coverage and saturation MUST account for evidence dependency groups, syndication and
  shared upstream origin, maintaining effective independent evidence separately from raw counts.
- **FR-016**: Relevance, source reliability, claim support, identity match, novelty, independence,
  structural centrality, temporal freshness, uncertainty and action utility MUST remain separately
  recorded quantities; any composite MUST retain the component vector and the policy version that
  produced it.
- **FR-017**: Evidence must never be mutated by a model, a scoring function, a topological feature,
  or a graphical centrality measure; those may only produce candidates.

### Functional Requirements — Temporal Semantics

- **FR-020**: The platform MUST keep separately typed and separately defined: source-published time,
  source-valid-from/valid-until, source-observed time, captured/fetched time, recorded/known time,
  processed time and projected time — each with its timezone, null semantics and query usage.
- **FR-021**: Unknown source time MUST remain unknown and MUST NOT be defaulted to the current time.
- **FR-022**: `CURRENT`, `AS_OF(known-time)` and `INTERVAL(valid-time a, b)` MUST return
  semantically distinct results; `AS_OF` MUST NOT be overloaded to mean both what the system knew
  and what is true in the world.
- **FR-023**: Late-arriving evidence MUST change the current reconstruction of past valid time
  without altering what the system recorded as known at an earlier known-time.
- **FR-024**: Temporal precedence MUST NOT be presented as causality; causal claims MUST carry their
  assumptions, identification conditions, confounds and non-identifiability state.
- **FR-025**: Where temporal relation reasoning is enabled, the supported subset of interval
  relations MUST be declared, and imprecise intervals MUST be represented as disjunctive or unknown
  rather than forced into a single relation.

### Functional Requirements — Context Kernel and Research State

- **FR-030**: The analytical contract of an investigation (objective, semantic regime, temporal
  query mode, policy references, source/capability requirements, freshness/quality criteria, stop
  conditions, analysis profile) MUST be a separate, versioned, immutable definition distinct from
  the mutable operational investigation state; they MUST NOT share an identifier namespace.
- **FR-031**: A change to the analytical definition MUST leave a trace: the running investigation
  either continues against a pinned definition revision or transitions to a new one with an
  explicit rebase decision; historical revisions MUST NOT be silently reinterpreted.
- **FR-032**: Any material change to investigation state MUST append a new revision carrying its
  id, sequence, predecessor/supersession link, inputs, applied rules and operators, parameters,
  change set, warnings, decision references and an integrity digest; a no-op input MUST NOT
  fabricate a semantic revision.
- **FR-033**: Investigation state, obligations, action proposals and results, decisions, hypothesis
  lifecycles, contradictions, stop reasons and replay metadata MUST survive process restart.
- **FR-034**: A volatile in-memory state store MUST NOT be selectable in a mode declared durable.
- **FR-035**: Query interfaces MUST distinguish empty state, explicitly registered unknown state,
  and found evidence; "never asked" MUST NOT equal "asked and found nothing".
- **FR-036**: The context projection operator MUST be a pure, reproducible function of its declared
  inputs and versions; it MUST NOT perform network access, remote model calls, durable writes or
  identity mutation inside the deterministic core.
- **FR-037**: Five responsibilities MUST remain separately owned and separately testable:
  obligation generation, satisfaction evaluation, action proposing, decision recording and revision
  management.
- **FR-038**: Every research obligation MUST record: stable id, parent context/question/scope,
  immutable trigger (kind, event, rule and version, exact reason), parent gap/hypothesis/
  contradiction/claim references, required outcome and acceptance predicates, required and
  eligible capabilities with justification, unknown or unsupported dependencies, policy
  requirements, priority components, expected gain, cost range, success estimate and uncertainty,
  status with every transition and reason, attempted actions with results, marginal gain and
  retry/suppression rule, and stop/satisfaction rule with scope boundaries.
- **FR-039**: A gap MUST NOT disappear because a function returned an empty list or a task ended; it
  MUST be satisfied against its declared criteria, superseded by a new formulation, explicitly
  blocked, or remain open.
- **FR-040**: A research obligation is not a task: completing an execution task MUST NOT satisfy an
  obligation, and task count MUST NOT be a satisfaction criterion.
- **FR-041**: The satisfaction evaluator MUST compare evidence and coverage against the obligation's
  declared acceptance criteria and return a verdict with reasons, evidence references, evaluator
  version and explicit blockers; a raw hit count MUST NOT by itself establish satisfaction.
- **FR-042**: Every proposed action MUST carry an inspectable component vector (expected information
  gain, hypothesis discrimination, relevance, source quality, independence gain, novelty, temporal
  freshness, success probability with stated semantics, estimated cost, latency, repeat penalty,
  source failure rate, resource risk, policy penalty) plus hard constraint evaluation, and MUST
  explain why it was selected, deferred, suppressed or blocked.
- **FR-043**: Hard constraints — source policy, tenant scope, consent/access, safety, budget cap,
  capability availability, required approval and legal restrictions — MUST NOT be outweighed by higher
  expected value.
- **FR-044**: An adaptive or learned layer MAY influence candidate generation and ranking, and MUST
  be disableable with a deterministic fallback and an explicit degraded-status signal; it MUST NOT
  redefine whether an obligation exists, silently satisfy one, or reclassify knowledge truth.
- **FR-045**: The platform MUST maintain action memory keyed by canonical action identity, scope,
  time range, parameters and operator version, recording actual cost and measured marginal gain; a
  repeated no-gain action MUST be suppressed until a declared condition changes or an explicit
  override with a reason is recorded.
- **FR-046**: The investigation loop MUST terminate only for an explicit recorded reason —
  completed, completed with limitations, saturated under stated scope, blocked, needs review, or
  cancelled — and MUST report residual unknowns and unexecuted scope. Empty results, task
  completion, exhausted retries, low model confidence and workflow expiry MUST NOT by themselves
  constitute a stop reason.
- **FR-047**: Every stage outcome MUST be typed and MUST distinguish succeeded, partial, no-result,
  unsupported, blocked, failed, quarantined, abstained and no-change, with retryability, reason,
  operator version and causal identifiers.
- **FR-048**: A `Finding` MUST be a versioned output exposing proposition or structural observation,
  typed epistemic status, exact support and counter-evidence references, scope and valid-time
  interval, derivation path, independent-source groups, method and snapshot fingerprints,
  uncertainty, alternative explanations, unresolved questions, coverage limitations, review state
  and supersession link.
- **FR-049**: Analyst review actions (support, refute, uncertain, irrelevant, duplicate, identity
  merge, identity split, withdraw, approve action, reject action) MUST be immutable records with
  actor, time, target revision and rationale; feedback MAY update evaluation and ranking policies in a
  controlled, reversible, audited workflow and MUST NOT rewrite raw evidence.

### Functional Requirements — Closed Loop and Consistency

- **FR-060**: Questions/obligations MUST compile into typed query plans and then to
  capability-specific requests; merging semantically similar plans MUST preserve the union of terms
  and filters and a many-to-many link to every originating obligation.
- **FR-061**: Candidate discovery, candidate expansion, relevance scoring, rank fusion, action
  utility and policy decision MUST remain distinct operations with distinct metrics and provenance;
  a single untyped score MUST NOT represent all of them.
- **FR-062**: Every acquisition result entering investigation state MUST have explicit membership or
  scope resolution; when it cannot be established, the observation MUST persist as unplaced with a
  recorded gap and MUST NOT be attached by guess.
- **FR-063**: The platform MUST NOT report an observation as placed when its membership write failed;
  it MUST use a defensible consistency strategy (single transaction, or transactional outbox plus
  idempotent state machine with explicit pending placement and reconciliation) and MUST NOT assume a
  distributed atomic transaction across object storage, database and broker without a mechanism.
- **FR-064**: Invariant reduction MUST fold the accumulated append-only life stream — not only the
  current batch — with deterministic ordering and deduplication, mint a new revision only when the
  canonical digest changes, persist the supersession/head relationship and all source event hashes,
  and restore the head across restart.
- **FR-065**: Redelivery MUST be idempotent; duplicate observations, events or action results MUST
  NOT inflate evidence independence, revision counts, coverage or cost-benefit learning.
- **FR-066**: Scientific outcomes supplied to investigation state MUST be anchored to input
  observations, snapshot, time window, operator/method fingerprint, assumptions and uncertainty; an
  unanchored science result MUST NOT satisfy an obligation.
- **FR-067**: The platform MUST implement backlog-driven backpressure: downstream interpretation,
  admission or projection saturation MUST reduce new acquisition dispatch rather than accumulate an
  unbounded backlog.
- **FR-068**: Retry policy MUST distinguish transient failure, permanent unsupported capability,
  permission denial, throttling, parse failure, no-result and valid empty result, with bounded
  retries at task, source, investigation, tenant and global levels, backoff with jitter, circuit
  breaking and rate windows.
- **FR-069**: Quarantined and dead-lettered records MUST retain payload reference, schema version,
  failure class, attempt history, error code, replay eligibility and redaction policy, and replay
  MUST use the same logical idempotency semantics.

### Functional Requirements — Projections

- **FR-070**: Every projection MUST declare its purpose, upstream sources, source-of-data and
  tenant/scope keys, schema/code/model/parameter fingerprints, incremental offset/checkpoint, full
  rebuild path and cost, deletion/retention behaviour, staleness indicator, error/partial/degraded
  status, idempotency and replay behaviour, output derivation contract, and kill switch.
- **FR-071**: A projection id that is created but never used, and a `rebuild` that silently restarts
  from offset zero while presenting itself as incremental, MUST be corrected or explicitly documented
  as the chosen cost model.
- **FR-072**: Graph projections MUST preserve direction, arity, temporal interval, source evidence,
  derivation and identity-decision revision; asserted and derived edges MUST remain distinguishable,
  and every derived edge MUST carry its rule, derivation path, premises, interval semantics and
  invalidation behaviour.
- **FR-073**: N-ary co-occurrence facts MUST preserve their incidence structure; a pairwise view MUST
  be an opt-in projection with explicit derivation and a warning about semantic loss.
- **FR-074**: Graph traversal MUST enforce depth, fan-out, scope, time, tenant and budget limits and
  MUST return truncation metadata with the derivation path explaining why each candidate appeared.
- **FR-075**: Search projections MUST expose index revision, searched fields, applied filters,
  staleness and candidate-pool truncation; a search hit MUST remain a candidate pointer, not admitted
  knowledge; deleting an index document MUST NOT lose the evidence it pointed to.
- **FR-076**: Topological analytics MUST record input snapshot digest, node set including isolated
  nodes, edge type/direction/arity treatment, filtration scale and units, metric, complex constructor,
  time window, code and dependency fingerprint and parameters; it MUST refuse or separately stratify
  incomparable scales; it MUST NOT mutate identity or claim truth.
- **FR-077**: Spatial projections MUST retain original geometry, coordinate reference system,
  precision/accuracy estimate, validity/known time and collection footprint; an index cell MUST NOT
  imply precision finer than the source.
- **FR-078**: Analytical metrics MUST report estimator and version, sample scope, sample size,
  confidence interval/uncertainty and missingness; source-health metrics MUST be maintained
  separately from real-world anomaly candidates.
- **FR-079**: A failed or stale projection MUST NOT satisfy an obligation requiring current data;
  the caller may accept staleness only through an explicit profile or policy.

### Functional Requirements — Identity and Admission

- **FR-080**: Mention, candidate and entity MUST remain distinct; identity merge, split and
  reassignment MUST be admission/resolution decisions with retained competing candidates and audit
  trail.
- **FR-081**: No similarity probability, structural centrality, graph adjacency, topological feature
  or language-model output MUST by itself authorize an identity merge.
- **FR-082**: Resolution decisions MUST be append-only; a superseded decision MUST remain retrievable
  and claims written under a prior identity interpretation MUST remain traceable to it.
- **FR-083**: Candidate admission MUST validate source observation and span reachability, contract
  shape with unknown-field preservation, permitted processing purpose and tenant/scope permissions,
  separation of extraction status from identity status, evidence both ways, temporal compatibility,
  duplicate and source-dependency detection, method version, and human review where the ambiguity or
  risk threshold requires it.
- **FR-084**: Transitive cluster contamination MUST be prevented: pairwise matches MUST NOT imply
  cluster membership where feature evidence is inconsistent.

### Functional Requirements — Security, Tenancy, Access Control

- **FR-090**: Every durable read, write, event consumer, projection lookup, cache key and replay key
  MUST be tenant-scoped; cross-tenant references MUST be rejected or hidden per policy without
  confirming existence through distinguishable errors.
- **FR-091**: All externally supplied content and any instruction inside it MUST be treated as
  untrusted data; it MUST NOT authorize new capabilities, alter policy or budget, invoke tools,
  change investigation lifecycle, or suppress contradictory evidence.
- **FR-092**: Acquisition, browsing and parsing MUST enforce egress policy against private, loopback,
  link-local and metadata addresses, validate resolution before and after redirects, constrain
  schemes/ports/redirect counts, and handle DNS rebinding.
- **FR-093**: Every operator MUST declare network permissions, resource limits (CPU, memory, storage,
  file size, archive depth, timeout), concurrency and rate limits, data classes read and written,
  credential scope, whether it executes active content or loads models, failure/cleanup behaviour,
  the tenant/scope enforcement point, its untrusted-text strategy and its telemetry redaction policy.
- **FR-094**: The platform MUST NOT bypass authentication, CAPTCHA, paywalls or other access
  controls; acquisition MUST operate only within permitted public or authorized interfaces.
- **FR-095**: Actions requiring approval MUST be proposed but not executed until the required
  decision is recorded.
- **FR-096**: Secrets and raw sensitive payloads MUST NOT appear in logs, metrics, traces or
  decision records.

### Functional Requirements — Analytics Transparency and Honest Reporting

- **FR-100**: No interface, report or dashboard MUST surface an unmeasured or fabricated number; where
  instrumentation is absent the value MUST be reported as null/unknown with the missing
  instrumentation surfaced.
- **FR-101**: Metrics MUST include backlog and lag, operator runtime/timeout/error, retry cost,
  source success rate, observation yield, duplicate rate, partial-output rate, resolution and review
  rate, independence group size, projection staleness, context revision rate, unresolved obligation
  age, no-gain suppression count, and cost per useful grounded finding.
- **FR-102**: The platform MUST NOT present a single green completion percentage that conceals
  blocked tasks, unknown areas, unsupported queries or failed projections.
- **FR-103**: Every revision, action and operator outcome MUST log correlation identifiers,
  tenant-safe identifiers, input/output references, latencies, costs, retry count, queue/offset
  state, method fingerprints and outcome, and MUST be traceable end-to-end from obligation through
  action, task, capture, observation, claim, derivation, invariant revision and context revision to
  finding.

### Functional Requirements — Third-Party Capability Integration

- **FR-110**: A third-party capability MUST NOT be considered integrated until: exact upstream
  revision or package version is pinned; code license, dependency licenses, model/dataset terms and
  attribution requirements are recorded; a contract adapter is implemented; a real production call
  site uses it; provenance is preserved through the adapter; error, timeout, partial and unsupported
  outcomes are handled; unit, contract and integration tests pass; and the platform's own benchmark
  on representative data shows capability gain, quality improvement at acceptable cost, or material
  operational reduction.
- **FR-111**: An external capability MUST NOT write canonical evidence, identity, investigation
  state or projection stores directly; its output MUST enter through candidates and derived
  artifacts under the platform's contracts.
- **FR-112**: Every third-party integration MUST have a disable/kill switch, a defined rollback
  route, a recorded upgrade policy and an operational owner; disabling MUST NOT delete evidence,
  candidates or prior derived artifacts.
- **FR-113**: Code license, dependency license, model weights, datasets, training data, bundled
  binaries, documentation and sample assets MUST be inventoried separately; a repository's headline
  license MUST NOT be assumed to cover assets.
- **FR-114**: Where an external capability's identity, upstream source or license cannot be
  established, it MUST be recorded as unverified and MUST NOT be integrated on assumption.
- **FR-115**: Existing internal catalogued capabilities MUST be inventoried and assessed before adding
  a second implementation of the same capability; wiring or repairing existing useful capability is
  preferred over duplication.

### Key Entities *(include if feature involves data)*

- **Investigation**: the analyst-created research process; owns scope, budget, policy and lifecycle.
- **Analytical Definition (ContextDefinition)**: immutable, versioned analytical contract —
  objective, regime, temporal mode, source universe, policy references, quality and stop criteria.
- **Investigation Context (InvestigationContext)**: mutable-by-revision operational state — questions,
  obligation ledger, hypotheses, contradictions, known unknowns, action history, coverage, budget and
  stop reason.
- **Context Revision**: immutable append-only snapshot/delta with predecessor link, inputs, applied
  rules, change set, decision references and integrity digest.
- **Question / Scope**: the target question with its intent, answer criteria and required knowledge;
  the temporal, geographic, source and access boundaries that make it queryable.
- **Research Obligation**: what the investigation still needs to learn, with trigger, acceptance
  criteria, required capabilities, priority components and lifecycle.
- **Research Action / Action Attempt**: a proposed plan and each individual execution attempt with
  outcome, cost and measured gain.
- **Decision Record**: immutable rationale for a state-changing, approval, closure, admission or
  policy decision, including alternatives considered.
- **Gap / Unknown**: a derived deficiency against the question and profile; and a durable record of
  what is unobserved, what was attempted, and why it remains unknown.
- **Contradiction**: opposing claims with scope, temporal frame, dependency groups, resolution criteria
  and decision history.
- **Hypothesis**: a candidate explanation with assumptions, predictions, discriminating tests and
  lifecycle state.
- **Observation**: an immutable record of what the system retrieved from a source, under what access
  mode and at what times.
- **Derived Artifact**: a versioned parser, extraction or analysis output over one or more
  observations, with operator manifest and input/output digests.
- **Segment / Mention**: an addressable span of a source and an entity reference extracted from it.
- **Candidate / Claim / Relation Candidate**: unresolved, admitted or normalized semantic propositions
  with support structure and open predicate vocabulary.
- **Evidence Dependency Group**: the relationship between copied, syndicated or jointly sourced
  evidence, with an independence estimate.
- **Invariant Revision**: the versioned relational projection of the accumulated entity life stream
  for a given entity, with stream head, digest, lifecycle slices and supersession chain.
- **Projection Manifest**: the reproducible build record of a projection — offsets, snapshot digest,
  builder/version, parameters, output digest, status and staleness.
- **Analytical Feature**: a typed derived measurement (topological, temporal, spatial, centrality,
  drift) with scale/window, uncertainty and derivation references.
- **Finding**: a versioned, analyst-facing result with epistemic status, evidence chain, derivation,
  uncertainty, limitations and review state.
- **Analyst Feedback**: an immutable review decision on a finding, candidate or action.
- **Third-Party Integration Record**: pinned upstream revision, license and asset inventory, mode of
  use, target path, benchmark evidence, rollback route and current status.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

The numeric performance targets below are deliberately **unset at specification time**: per the
source specification, numeric thresholds are established only after a measured baseline exists, and
fabricating them is a release blocker. Each criterion is therefore expressed as a measurable,
technology-agnostic outcome with a defined measurement method, not an invented percentage.

- **SC-001 — Loop closure**: For a representative investigation on a clean stack, the research loop
  completes at least two full iterations, where a new observation causes the invariant revision and
  the investigation revision to advance and the recommended next action to change for a recorded
  reason. *Measured by*: an end-to-end scenario executed on a deployable stack with persisted state,
  revision chain and decision history.
- **SC-002 — Honest termination**: 100% of investigation terminations in the acceptance suite carry a
  machine-readable reason and a list of residual unknowns; zero terminations are attributed to empty
  results, task completion, exhausted retries or model confidence alone. *Measured by*: automated
  assertion over all terminal transitions in the acceptance suite.
- **SC-003 — Epistemic discrimination**: Across the epistemic fixture corpus, every case resolves to
  the intended distinct outcome (unknown / no-observations / unavailable / unsupported / searched-no-
  result / qualified absence / positive / negative / both / inconclusive / blocked / refuted /
  saturated-with-scope) through storage, events, API and user interface without collapse. *Measured
  by*: automated round-trip assertions per fixture.
- **SC-004 — Provenance completeness**: 100% of accepted claims and findings in the acceptance corpus
  resolve to a content address plus an addressable span within the stored raw bytes; results without
  a complete chain are labelled partial/unsupported and are never counted as grounded. *Measured by*:
  lineage resolution test over every accepted artifact.
- **SC-005 — Byte immutability**: Zero modifications to stored raw objects across parser upgrades,
  reprocessing, rollbacks and feature-flag disablement. *Measured by*: digest comparison of raw
  artifacts before and after each acceptance scenario.
- **SC-006 — Restart and replay fidelity**: Restarting the platform and replaying the durable event
  stream reproduces the recorded invariant head, revision chain and integrity digests exactly; no
  state is lost and no semantic effect is duplicated. *Measured by*: digest equality between
  incremental and full-rebuild paths on golden event streams.
- **SC-007 — Idempotency**: Replaying any recorded event, observation or action result produces zero
  additional revisions, zero additional evidence independence, and zero additional coverage or
  cost-benefit learning. *Measured by*: state-equality assertions across duplicate delivery runs.
- **SC-008 — Bitemporal correctness**: On late-evidence fixtures, `CURRENT`, `AS_OF(known-time)` and
  `INTERVAL(valid-time)` return the three semantically distinct correct answers, and prior known-time
  snapshots remain unaltered. *Measured by*: golden-fixture assertions.
- **SC-009 — Identity safety**: Zero identity merges are committed by a similarity score, graph
  proximity, centrality, topological feature or language-model output alone; every committed merge
  and split has a recorded, retrievable decision. *Measured by*: adversarial test suite plus decision
  ledger completeness check.
- **SC-010 — Membership consistency**: Zero states in which an observation is reported as placed while
  its membership write did not commit; orphan blobs and pending placements are found by
  reconciliation without fabricated membership. *Measured by*: injected-failure integration tests.
- **SC-011 — Loop improvement at fixed budget**: With an identical query set, budget and source
  universe, the post-change configuration yields a measured improvement in unique novel evidence and
  independent-source groups obtained per unit total cost versus the verified baseline, or an
  equivalent-quality result at lower total cost. *Measured by*: same-envelope benchmark comparison;
  the decision is recorded either way.
- **SC-012 — Retrieval discrimination**: Retrieval evaluation reports Recall@k, Precision@k, MRR/nDCG,
  unique and independent evidence yield, candidate novelty, duplicate rate and latency distribution,
  stratified by query class, and the chosen fusion/ranking strategy is justified by those results
  rather than by assumption. *Measured by*: a versioned benchmark report over a frozen judged query
  set.
- **SC-013 — Suppression correctness**: Every repeated no-gain action is suppressed with a recorded
  reason and an explicit list of re-open conditions, and no suppression is permanent across a
  declared condition change. *Measured by*: repetition scenario assertions.
- **SC-014 — Admission evidence**: Every accepted third-party capability in production has a pinned
  revision, complete license and asset inventory, a real production call site, passing contract tests,
  a comparative benchmark against the platform baseline, and a working kill switch; capabilities
  lacking any of these are reported with the corresponding reduced status, never as integrated.
  *Measured by*: integration-record completeness audit.
- **SC-015 — Truthful operations**: Zero fabricated metrics in user-facing interfaces, reports or
  dashboards; every unavailable measurement is surfaced as unknown with the missing instrumentation
  named. *Measured by*: source-level audit plus interface assertions.
- **SC-016 — Honest test reporting**: Every test outcome in the final report is classified as pass,
  fail, blocked or not-run; zero inaccessible external services are reported as tested. *Measured by*:
  report review against recorded command output and exit codes.
- **SC-017 — Truthful readiness declaration**: The final engineering report explicitly enumerates
  which goals are proven end-to-end and which remain unverified; zero capabilities that are only
  documented, stubbed or unit-tested are counted toward completion. *Measured by*: report review
  against the capability matrix.

---

## Assumptions

- **Target repository and starting point**: the work targets the COGNITIVE repository at
  `https://github.com/JewishTT/1`; the implementation branch state is whatever the executing commit
  provides. This specification makes no claim that any listed path or caller exists; the audit
  deliverable establishes that.
- **Spec numbering**: the feature is registered as `specs/030-global-platform-upgrade` because
  feature numbering is sequential and `001`–`029` are occupied.
- **Constitution**: `.specify/memory/constitution.md` currently contains unfilled template
  placeholders. It is treated as the governing document whose *semantics* are restated by the source
  specifications (evidence-first, process-centric, relation-centric, immutable evidence, separate
  scores, open-world semantics, epistemic discipline). Filling the constitution is a prerequisite
  task, not an assumption that it is already authoritative.
- **Governing documents**: the Global Platform Upgrade specification and CE-001 are normative. Where
  this spec is silent, they govern. Where CE-001 and the global spec use different names for the
  same concept, both names are retained as aliases rather than resolved by fiat.
- **Scope boundary — in**: verification audit; data and event contracts; invariant/worldline integrity
  and replay; the context kernel and closed loop; acquisition consistency; identity/admission safety;
  retrieval and frontier economics; projection manifests and rebuildability; third-party capability
  integration with benchmark gates; API, console, observability, security, migration and rollback.
- **Scope boundary — out**: rewriting the platform in another language; migrating all services to a
  new distributed architecture without measurement; adopting any single third-party full-stack
  application as the authoritative backend; converting model output, graph scores or topological
  features into truth; integrating candidates merely for list coverage; collection that circumvents
  access controls; use of third-party datasets or models without license review; and any claim of
  demonstrated total coverage without a formalized detection-power and scope model.
- **Third-party candidates** named in the source specifications (document parsers, probabilistic
  linkage libraries, retrieval/fusion components, temporal graph engines, online-ML drift detection,
  spatial indexing, Earth-observation stacks, LLM routing and evaluation tooling, timeline/CTI
  adapters, and several not-yet-resolved project names) are **candidates, not integrations**. Their
  identity, upstream source, license and API must be established before any code is transferred.
- **Legal stance**: copyleft licensing is not automatically disqualifying and process separation is
  not automatically sufficient; the actual network and distribution terms must be reviewed where
  material. Unknown or absent licensing blocks code copying until rights are established, and a
  methodology or clean-room path may be substituted.
- **Baseline dependency**: all quantitative comparison depends on a recorded baseline (test results,
  fixtures, retrieval and resolution corpora, cost model) captured before architecture-changing work
  begins. If the audit reveals that the baseline cannot be established, the affected criteria are
  reported as blocked with the concrete reason.
- **Existing prior specifications** (including `specs/024`, `specs/025`, `specs/026`, `specs/028` and
  `specs/029`) are reconciled against actual code rather than copied forward; historical claims that
  conflict with the executing commit are corrected with source references.
- **Deployment reality**: declared services, ports and environment configuration are assumed to be
  potentially divergent from reality; where a service is unavailable, dependent scenarios are
  reported as blocked, never as passing.

---

## Out of Scope Confirmation

This specification deliberately does **not** prescribe programming languages, frameworks, database
engines, message brokers, specific third-party packages, file layouts or code structure. Where the
source specifications name concrete technologies or paths, they are treated as *candidates and
starting points for the audit*, recorded in the audit and donor-matrix deliverables rather than as
binding design decisions. The binding content of this spec is the required **behaviour, semantics,
invariants, evidence standards and acceptance evidence**.