# Feature Specification: Context & Dialectical Reality Approximation Engine

**Feature Branch**: `025-context-reality-approximation-engine`

**Created**: 2026-10-04

**Status**: Approved — Design Baseline **v2** accepted; Q1=B, Q2=B (ADR-0028); 154 tasks, 88 FR, gates A–Q

**Input**: `input.md` (owner-supplied Specification 025 **v2**, verbatim),
`research.md` (deep research: donor inventory, literature, risk register R1–R8)

**Depends on**: `024-context-driven-continuous-intelligence` (024 wins on conflicts)

---

## Design baseline notice

This specification is written **against** the owner's Design Baseline in `input.md`, which
remains authoritative for every object schema, algorithm, state machine and data contract.
This file does not restate that content. It does three things the baseline deliberately
does not:

1. expresses the same commitments as prioritized, independently testable user journeys;
2. carries the owner's own `FR-025-001`–`FR-025-068` identifiers through as the
   requirement set, so design and implementation stay traceable to each other;
3. records the two decisions that the baseline leaves genuinely open and that change the
   shape of the work.

Per `/speckit.specify`, this file states **what** is required and **why**. The *how*
lives in the baseline and, from here on, in `plan.md` and `tasks.md`.

---

## User Scenarios & Testing

Each story is a standalone slice. Implementing only P1 yields a usable system; each later
story adds one epistemic capability without invalidating the earlier ones.

### User Story 1 - Durable, replayable context (Priority: P1)

An analyst opens an investigation. The system holds a scoped definition of what is being
investigated, and every change to the analyst's understanding of the subject produces a new
immutable revision rather than an edit. The analyst can return to any earlier revision and
see exactly what was known then. Restarting the platform does not lose the investigation.

**Why this priority**: it is the substrate every other capability stands on. Without a
durable, replayable revision there is nothing for hypotheses, contradictions or a research
frontier to refer to, and nothing to audit. It is also the layer that already exists in
024 and must be adopted rather than rebuilt (research R2).

**Independent Test**: create a context, revise it, restart the process, read revision *N*
back byte-for-byte, and confirm an earlier revision is still readable and unedited.

**Acceptance Scenarios**:

1. **Given** an existing context, **When** new evidence arrives, **Then** a new revision is
   committed, the previous revision remains readable and unedited, and the new revision
   names the events that caused it.
2. **Given** a committed context, **When** the process is restarted, **Then** the context,
   its revisions and its scope are returned unchanged.
3. **Given** the same inputs, rule set and parameters, **When** the transition is replayed,
   **Then** the resulting revision content is identical, and wall-clock time does not
   influence that identity.
4. **Given** a retry after a failed validation, **When** it is resubmitted, **Then** it is a
   new proposal and the rejected object is never reopened.

---

### User Story 2 - Local sections that combine, or explain why not (Priority: P2)

An analyst's investigation is too large to reason about as one whole. The system divides it
into bounded local sections, compares only sections that can plausibly interact, and merges
them where they agree. Where they disagree, the merge stops and states precisely which
dimension blocked it. A blocked merge is never presented as a negative finding.

**Why this priority**: it is what makes full-scale reconnaissance tractable, and it is where
a plausible implementation most easily destroys information by averaging conflicts away.

**Independent Test**: take two local sections that conflict on one dimension and agree on
the rest; assert the merge is partial, the conflict is preserved verbatim, and an
actionable obstruction is raised.

**Acceptance Scenarios**:

1. **Given** two compatible local sections, **When** they are combined, **Then** a coherent
   merged section is produced and both contributions remain individually inspectable.
2. **Given** two sections that conflict, **When** they are combined, **Then** the verdict is
   blocked or partial, both sides remain readable, and an obstruction naming the blocking
   dimension is persisted.
3. **Given** a large investigation, **When** sections are compared, **Then** the engine
   never compares all sections with all sections, and any overflow of a comparison bucket
   is reported rather than silently processed.
4. **Given** a restriction projecting a section onto a smaller scope, **When** it is
   applied, **Then** it may reduce scope or precision but never introduces information that
   was not present in the source.

---

### User Story 3 - Unknown is a real answer (Priority: P3)

Two credible sources disagree. The system does not pick a winner and move on. It records
that both sides have support, keeps both alive, and tells the analyst what evidence would
separate them. An unobserved thing is reported as unobserved, never as absent.

**Why this priority**: it is the feature's epistemic core and the requirement most likely to
erode silently. It is P3 only because it presupposes a durable substrate (P1) and a
locality model (P2) to attach contradictions to.

**Independent Test**: assert the truth lattice over all four support combinations, and
assert that a `both` state survives a full save → API → UI → projection round trip
unchanged (research R3).

**Acceptance Scenarios**:

1. **Given** evidence *X* and evidence *not-X*, **When** the state is recorded, **Then** the
   claim's support state is *both*, the contradiction is open, and both evidences remain
   queryable.
2. **Given** a hypothesis requiring a variable that no registered source can observe,
   **When** the system reports state, **Then** the variable is unknown, the hypothesis is not
   advanced by the absence, and the obligation is blocked on capability.
3. **Given** no evidence observed, **When** a result is produced, **Then** it is reported as
   unobserved and never as a negative finding.
4. **Given** the same press release syndicated across many sites, **When** independence is
   assessed, **Then** the captured count and the independence count differ, and the
   derivation lineage is explicit.

---

### User Story 4 - Competing explanations, with their assumptions visible (Priority: P4)

The analyst asks "what is actually going on here?". The system proposes several explanations
that fit the evidence, says what each one assumes, what would refute it, and what it
predicts that the others do not. When two explanations fit equally well, the simpler one is
ranked first — as a ranking rule, not as a claim to truth — and near-duplicates are not
presented as additional insight.

**Why this priority**: this is the capability that converts a platform of collected facts
into an analytical instrument. It depends on P3, because competition is only meaningful
when contradiction can be represented.

**Independent Test**: give the engine two explanations with equal evidential fit and
different complexity; assert the cheaper one ranks first, both are retained, and the
discarded candidate remains auditable with its rejection reason.

**Acceptance Scenarios**:

1. **Given** evidence compatible with several explanations, **When** hypotheses are
   generated, **Then** multiple live hypotheses exist, each naming its assumptions and its
   supporting and refuting evidence.
2. **Given** a search that hits its budget, **When** it returns, **Then** the partial result
   states what was processed, what was not, and why truncation was allowed.
3. **Given** near-duplicate candidate explanations, **When** the top set is selected,
   **Then** structural diversity is preserved rather than k paraphrases returned.
4. **Given** a hypothesis with no observable consequence, **When** it is reported,
   **Then** it may be described, but it is not presented as a testable model.

---

### User Story 5 - Structure, dynamics and cause kept apart (Priority: P5)

The analyst sees structural patterns, periods of stability, and periods of change. The
system reports a detected structural change as a structural result, a period of stability as
a regime, a boundary as a transition window, and a candidate cause as a *candidate* with its
assumptions — as four separate claims, never merged into one causal statement.

**Why this priority**: it is where the platform's scientific instruments meet its honesty
requirements, and where a single numeric metric is most likely to be promoted into a story
it cannot support (research R4).

**Independent Test**: feed a series with a change point; assert four distinct outputs with
distinct identifiers, and assert that no causal-identification field is populated when the
effect is not identified.

**Acceptance Scenarios**:

1. **Given** a series with a detected change point, **When** results are reported,
   **Then** change point, regime change, phase-transition candidacy and causal explanation
   are separate claims with separate identifiers.
2. **Given** a causal question whose effect is not identified, **When** it is evaluated,
   **Then** the result is *not identified* — never a zero effect.
3. **Given** structural/topological features derived from a worldline snapshot,
   **When** they are stored, **Then** they cannot change entity identity or any truth state.
4. **Given** evidence arriving out of order, **When** it is incorporated, **Then** it
   produces a new revision and supersession record, and does not rewrite past revisions.

---

### User Story 6 - The next action is chosen for what it would distinguish (Priority: P6)

The system proposes what to investigate next. Each proposal states which explanations it
would separate, what it is expected to reveal, what it costs, why that source is trusted,
and what its result would mean under each competing explanation. Repetition of an action
that already produced nothing is suppressed.

**Why this priority**: it closes the loop from understanding back to collection, and it is
where research effort is actually spent. Depends on P4.

**Independent Test**: given two candidate actions, assert the ranking exposes its
components rather than one opaque number, and that a repeated no-gain action is not
proposed again.

**Acceptance Scenarios**:

1. **Given** competing explanations with different predictions, **When** actions are ranked,
   **Then** the action whose outcome best separates them ranks first, and the ranking
   exposes urgency, expected gain, discrimination, quality, novelty, cost and penalties.
2. **Given** an action already attempted with no realised gain, **When** the frontier is
   rebuilt, **Then** it is not proposed again without a declared reason.
3. **Given** an action requiring capabilities that no registered source provides,
   **When** it is proposed, **Then** it is blocked on capability with that reason, not
   silently dropped.
4. **Given** a policy requiring approval, **When** an action is selected, **Then** it remains
   a proposal until approved, and rejection is recorded as a decision.

---

### User Story 7 - "Find all" answers honestly (Priority: P7)

An analyst asks for *all* crypto whales above a threshold. The system returns what it
observed, what it could not resolve, what it excluded and why, how much of the intended
universe it covered, how saturated the search was, and which blind spots remain. It does not
claim completeness it cannot support.

**Why this priority**: it protects every other guarantee from being over-read by the
analyst. Depends on P1–P6 to have anything meaningful to report.

**Independent Test**: run a universal-intent query against a partial catalogue; assert the
response declares open-world discovery, reports coverage and blind spots, and retains the
unresolved population as a first-class result set.

**Acceptance Scenarios**:

1. **Given** a query using a universal term, **When** the universe cannot be shown complete,
   **Then** the response declares its completeness mode, coverage, saturation and blind
   spots, and the unresolved population is preserved rather than dropped.
2. **Given** an explicitly enumerable universe that was fully scanned, **When** results are
   returned, **Then** exact enumeration is declared and is justified by the scan.
3. **Given** a natural-language request, **When** it is compiled, **Then** a deterministic
   parser path exists for the supported grammar, and any adaptive parser produces the same
   structure for the same input.
4. **Given** a query whose identity resolution is incomplete, **When** clusters are formed,
   **Then** unresolved clusters are preserved and reported, not merged away for a cleaner
   answer.

---

### User Story 8 - Every conclusion can be interrogated (Priority: P8)

The analyst selects any conclusion and is shown why the system believes it, what supports
it, what contradicts it, what it assumes, what would refute it, and which evidence led the
system to request the source it chose. This holds for a single fact as well as for a whole
investigation closure.

**Why this priority**: without it the honesty guarantees are unauditable, and the platform's
claims cannot be checked by anyone but its author. Depends on P1 and P3.

**Independent Test**: from a result item, traverse to evidence in one hop per documented
lineage dimension; a missing edge is a test failure.

**Acceptance Scenarios**:

1. **Given** an entity in a result, **When** the analyst asks why, **Then** the full
   evidence lineage back to raw bytes is traversable.
2. **Given** a hypothesis, **When** the analyst asks why the system believes it,
   **Then** the current revision, supporting and refuting evidence, assumptions, model and
   method fingerprint are shown.
3. **Given** a request for a source, **When** the analyst asks why, **Then** the chain from
   discriminating test through targeted explanations to capability and source is traversable.
4. **Given** an investigation that stopped, **When** the analyst asks why, **Then** the
   closure report names terminal obligations, saturation, coverage, budget and unresolved
   blind spots.

### User Story 9 - Evidence weighed by independence, not by volume (Priority: P9)

An analyst sees fifty articles about the same event. The system treats them as what they
are — one syndicated origin, possibly two after an independent translation — reports the
effective independent source count next to the raw count, and does not let a repeated press
release raise confidence. When something was searched for and not found, the system asks
whether it was actually in a position to find it, and reports a negative finding only when
coverage and detection power justify it.

**Why this priority**: without it every confidence number in the system is inflated by
exactly the factor that matters most in open-source intelligence. v2 moved it to the core.

**Independent Test**: feed a syndicated set plus a covered-but-empty search; assert `n_eff`
stays below the raw count, a duplicate never raises a posterior, and the empty search is
`INFORMATIONAL_ONLY` unless detection power is declared.

**Acceptance Scenarios**:

1. **Given** one origin syndicated across many sites, **When** evidence is aggregated,
   **Then** it forms one dependency group, `n_eff` is reported beside the raw count, and the
   posterior does not inflate.
2. **Given** a search with unknown detection power that found nothing, **When** results are
   produced, **Then** a coverage-qualified absence is stored as informational only and
   contributes no negative support.
3. **Given** a universal-negative query whose conditions are not met, **When** it is
   answered, **Then** the answer is "none observed under declared coverage", never "none
   exist".
4. **Given** a claim no registered source can observe, **When** the frontier is built,
   **Then** the obligation is blocked on capability and the variable stays unknown.

---

### User Story 10 - Hypotheses compete inside a declared space (Priority: P10)

The analyst asks what is going on. The system states which explanations it considered, which
of them it did not, how much probability mass is left for "none of the above", and refuses to
rank a heuristic score against a probability. A hypothesis that nobody could have falsified
is labelled as such rather than presented as a finding.

**Why this priority**: it is the difference between an analysis and a confident story. It
depends on P9, because residual mass only means something once independence is accounted for.

**Independent Test**: declare a non-exhaustive space and assert `H_OTHER` carries mass, the
listed posteriors sum to less than one, and a mixed-kind frontier is ordered by a declared
interleave rather than by comparing raw numbers.

**Acceptance Scenarios**:

1. **Given** a space declared non-exhaustive, **When** posteriors are computed, **Then** an
   explicit residual hypothesis carries declared mass and is never silently renormalised away.
2. **Given** a heuristic-scored and a probabilistic candidate in the same frontier,
   **When** they are ranked, **Then** the declared interleaving rule is used and raw values
   are never compared.
3. **Given** three pairwise-compatible sections that are jointly inconsistent, **When** they
   are glued, **Then** the verdict is partial with a triple-inconsistency obstruction, never
   "glued".
4. **Given** a competing explanation generated with less budget than the thesis, **When** the
   pair is resolved, **Then** the parity violation is recorded and resolution is refused.

---

### Edge Cases

- **Budget exhausted mid-run.** Return partial results with an explicit exhaustion state,
  never a silently truncated set presented as complete.
- **Operator unavailable or failed validation.** The result is quarantined, no world state
  mutates, the run is recorded as failed, and the input stays replayable.
- **A comparison bucket overflows its limit.** Report the overflow and raise an obligation
  to reconsider the blocking strategy; do not process the oversized bucket.
- **No source can observe a required variable.** The variable stays unknown and the
  obligation is blocked on capability; absence of evidence never becomes a negative finding.
- **Sources syndicate one origin.** Capture count and independence count diverge, with
  explicit derivation lineage.
- **Late or out-of-order evidence.** Produces a new revision plus a supersession record;
  past revisions are never rewritten.
- **Unknown relation type or unmapped semantic predicate.** The structural signal survives
  with its type recorded as unknown; it is not discarded and not coerced.
- **Evidence supports both sides of a claim.** Both sides persist; confidence may rank them
  while the support state remains *both*.
- **Causal effect not identified.** The result is *not identified*, not a zero.
- **Structural/topological anomaly coincides with a real-world event.** Both are recorded;
  no causal claim is generated.
- **Adaptive layer disabled.** The deterministic core produces identical output for
  identical input; no capability becomes unavailable as a result.
- **A requested search term implies universality.** Completeness analysis runs and the
  response states its mode.
- **Two overlapping sections agree on everything except one dimension.** Partial merge, that
  dimension named as blocking, both sides retained.
- **A hypothesis depends on an assumption that later fails.** The hypothesis weakens and the
  dependence is visible; earlier assessments remain readable.
- **Pairwise-compatible cells that are jointly inconsistent.** Gluing returns partial with a
  triple obstruction; `GLUED` is forbidden while triples are unchecked (§I.3).
- **A blocking bucket exceeds its limit.** Overflow is recorded and an obligation is raised;
  the bucket is not processed.
- **Evidence lineage is unknown.** Items are treated as one group and `INDEPENDENCE_UNKNOWN`
  is recorded — never assumed independent.
- **Analyst overrides model state.** Both are shown side by side; the model value is not
  replaced.
- **A counterfactual branch concludes something.** It stays on the branch; mainline has no
  corresponding finding.
- **Payloads erased under retention.** Replay reports `REPLAY_DEGRADED`; digests of erased
  inputs remain so everything else stays verifiable.
- **A cache key lacks `tenant_id`.** Forbidden at registration (§30.5).

---

## Requirements

### Constitutional invariants (non-negotiable, restated from the baseline)

- **INV-1 (§0.2)**: Observability is never destroyed because semantic certainty is
  unavailable. Unknown, unresolved, incomplete and unobserved are distinct states.
- **INV-2 (§0.3)**: The five epistemic levels L0–L4 are never collapsed into one generic
  result by any API, persistence model or UI component.
- **INV-3 (§4, §4.1)**: Identical inputs, rule set, parameters and seeds produce identical
  revision content **per determinism class** (`EXACT` / `FIXED_POINT` / `FLOAT_QUANTIZED`);
  wall-clock does not influence identity, batching or ordering.
- **INV-4 (§48)**: The deterministic core is the constitutional acceptance mode and runs
  with adaptive models disabled.
- **INV-5 (§49)**: The engine proposes research actions; it never executes external
  operations directly and always routes through the existing governance boundary.
- **INV-6 (§59)**: The eighteen permanent non-goals are architectural failures even when the
  code appears to work.
- **INV-7 (P13–P17, v2)**: Hypothesis spaces are explicit; evidence is counted by independence
  not volume; absence is evidence only under coverage; the analyst is a first-class actor with
  provenance; different kinds of numbers are never compared without a declared policy.
- **INV-8 (conflict rule)**: where 025 and 024 define the same lifecycle, **024 wins**; any
  divergence is resolved by amending 025, never by redefining 024.

### Functional Requirements

Идентификаторы — owner's, извлечены дословно из Appendix T (v2). Baseline §54, Appendix T
и Appendix U нормативны; §60 — производная сводка.

**Контекст и ревизия**

- **FR-025-001**: ContextDefinition is immutable.
- **FR-025-002**: Context identity excludes revision state.
- **FR-025-003**: ContextRevision is append-only.
- **FR-025-004**: ContextRevision is transactionally committed before visible.
- **FR-025-005**: Historical revisions remain queryable.
- **FR-025-006**: Context reconstruction is replayable.

**Локальность**

- **FR-025-007**: ContextCell is independently inspectable.
- **FR-025-008**: Scope intersection is typed.
- **FR-025-009**: Overlap generation is blocked and bounded.
- **FR-025-010**: Restriction cannot fabricate information.
- **FR-025-011**: Compatibility produces a dimensional verdict vector.
- **FR-025-012**: Gluing preserves conflicts.
- **FR-025-013**: Obstructions are durable.
- **FR-025-014**: Obstructions can generate obligations.

**Состояние и динамика**

- **FR-025-015**: StateVariable has explicit observability status.
- **FR-025-016**: Hidden state is not serialized as observed fact.
- **FR-025-017**: State estimation records residuals.
- **FR-025-018**: Six authoritative time axes remain unchanged.
- **FR-025-019**: Late events create new revisions.
- **FR-025-020**: Regime is separate from change point.
- **FR-025-021**: Transition is separate from causality.
- **FR-025-022**: TDA output remains structural.

**Гипотезы**

- **FR-025-023**: Hypotheses are first-class durable objects.
- **FR-025-024**: Hypothesis identity has logical/revision levels.
- **FR-025-025**: Support/refutation are separate vectors.
- **FR-025-026**: Assumptions are explicit.
- **FR-025-027**: Predictions are explicit.
- **FR-025-028**: Discriminating tests are explicit.
- **FR-025-029**: Competing hypotheses coexist.
- **FR-025-030**: Historical hypothesis assessments remain queryable.

**Абдукция и диалектика**

- **FR-025-031**: Abduction is bounded.
- **FR-025-032**: Candidate pruning is auditable.
- **FR-025-033**: Complexity penalties are declared.
- **FR-025-034**: Hypothesis diversity is preserved.
- **FR-025-035**: Active hypotheses can produce counter-hypotheses.
- **FR-025-036**: Differential predictions are persisted.
- **FR-025-037**: Dialectical resolution can remain inconclusive.

**Противоречия**

- **FR-025-038**: Contradictions are durable.
- **FR-025-039**: Source independence is assessed explicitly.
- **FR-025-040**: Contradictions do not delete either side.
- **FR-025-041**: Contradictions can create obligations.

**Фронтир**

- **FR-025-042**: Research actions remain proposals until governance permits execution.
- **FR-025-043**: Expected information gain is recorded.
- **FR-025-044**: Realized information gain is recorded.
- **FR-025-045**: Action utility is decomposable.
- **FR-025-046**: Action repetition is controlled by ActionMemory.
- **FR-025-047**: Saturation is multidimensional.
- **FR-025-048**: Closure requires explicit criteria.
- **FR-025-049**: Re-opening on contradiction is supported.

**Запрос и глобальный поиск**

- **FR-025-050**: Natural-language queries compile to a common AST.
- **FR-025-051**: Deterministic grammar exists for supported queries.
- **FR-025-052**: Optional LLM compilation is subordinate.
- **FR-025-053**: Universal terms trigger completeness analysis.
- **FR-025-054**: Open-world results expose coverage and blind spots.

**Исполнение**

- **FR-025-055**: Every operator has a registered contract.
- **FR-025-056**: Every operator has a method fingerprint.
- **FR-025-057**: Every operator declares complexity/resource requirements.
- **FR-025-058**: Every operator exposes an explanation trace.
- **FR-025-059**: Every operator supports deterministic replay or explicitly declares why not.
- **FR-025-060**: Adaptive operators are optional.

**Целостность**

- **FR-025-061**: No LLM owns admission.
- **FR-025-062**: No TDA result owns truth.
- **FR-025-063**: No source count is treated as source independence.
- **FR-025-064**: No unknown value is silently coerced to zero/false.
- **FR-025-065**: No derived object is visible before durable commit.
- **FR-025-066**: Every major derived result has reverse provenance.
- **FR-025-067**: Resource exhaustion is explicit.
- **FR-025-068**: Replay is fixed-point deterministic (per determinism class).

**Добавлено в v2**

- **FR-025-069**: Hypotheses live in an explicit HypothesisSpace; non-exhaustive spaces carry `H_OTHER` mass.
- **FR-025-070**: All aggregation consumes evidence dependency groups; `n_eff` is reported.
- **FR-025-071**: Negative findings exist only as coverage-qualified absences with declared detection power.
- **FR-025-072**: Predictions have statuses and persisted outcomes that feed hypotheses, gain and calibration.
- **FR-025-073**: Ranking is declared in the ReasoningProfile, non-multiplicative, tier-respecting, with exploration quota.
- **FR-025-074**: Gluing checks triple coherence under budget and reports unchecked triples.
- **FR-025-075**: Counter-hypotheses satisfy a reproducible material-difference test and steelman parity.
- **FR-025-076**: Branches are isolated from the mainline.
- **FR-025-077**: Analyst assertions/decisions are first-class, traced and visible beside model state.
- **FR-025-078**: Numeric modes, quantization and derived seeds govern determinism.
- **FR-025-079**: One sequencer per context; batch boundaries are recorded; replay uses them.
- **FR-025-080**: Revisions are manifests of content-addressed artifacts with optimistic concurrency.
- **FR-025-081**: Retention/erasure via crypto-shredding preserves integrity and yields explicit `REPLAY_DEGRADED`.
- **FR-025-082**: Sensitive inference classes are gated by InferencePolicy.
- **FR-025-083**: Operator caches are tenant-keyed and fail closed.
- **FR-025-084**: Quantitative targets (§47.4) are ratified, measured and reported.
- **FR-025-085**: Honesty-metric denominators are defined and implemented.
- **FR-025-086**: Baseline estimator is interval constraint propagation with explicit residuals.
- **FR-025-087**: Temporal relations use the full 13-relation disjunctive algebra.
- **FR-025-088**: Truth-state operations satisfy the Belnap lattice laws; `BOTH` implies a Contradiction.
### Key Entities

- **Context definition** — immutable scope and objective of an investigation's analytical
  universe: identity, tenant, parent investigation, objective, entity/event/source/
  geographic scope, temporal scope, semantic regime, analysis profile, policy.
- **Context revision** — immutable, append-only state snapshot with parent link, state
  hash, input event references, method and policy fingerprints, and lifecycle status.
- **Context cell** — independently inspectable bounded local section: kind, scope
  descriptor, temporal slice, observation/entity/relation references, completeness,
  trust state.
- **Context overlap** — declared intersection of two cells with its own typed compatibility
  status; the unit of comparison, never a string match.
- **Restriction map** — projection of a cell onto a smaller scope, with an explicit loss
  profile of what precision was surrendered.
- **Compatibility assessment** — per-dimension verdict vector across identity, temporal,
  spatial, semantic, structural, numeric, provenance and causal dimensions, plus supporting,
  contradicting and missing evidence.
- **Gluing result** — merged candidate section with verdict, preserved conflicts and
  durable obstructions. Blocked means insufficient evidence, never false.
- **Obstruction** — recorded, actionable reason a join cannot currently be made; may
  become a research obligation.
- **State variable / state estimate** — a measurable or inferred property, and a typed
  estimate of it whose epistemic status distinguishes observed, estimated, latent and
  unknown.
- **Observation model** — declared state variables, observed variables, transition and
  emission operators, assumptions and a parameter fingerprint.
- **Hypothesis** — versioned candidate explanation with logical identity, revision,
  assumptions, premises, supporting/refuting/missing evidence, four-way support state,
  epistemic status, typed score, predictions and discriminating tests.
- **Assumption** — explicit, sensitivity-bearing premise a hypothesis depends on.
- **Dialectical pair** — thesis/antithesis pair with shared and disputed premises,
  differential predictions, discriminating tests and a resolution state that may remain
  inconclusive.
- **Prediction** — observable consequence expected if a hypothesis holds, with
  falsifiability grade and derivation trace.
- **Discriminating test** — evidence request chosen because live hypotheses predict
  different outcomes, with expected information gain labelled as model-based or surrogate.
- **Contradiction** — durable record of two mutually exclusive statements, with kind,
  severity, independence assessment, both evidence sets and resolution state.
- **Regime / transition window** — interval of approximate descriptor stability, and a
  bounded period of change between regimes with candidate causes kept distinct from
  detection.
- **Topological feature** — structural feature derived from a durable worldline snapshot;
  never identity, truth or causality.
- **Causal model / evaluation** — variables, edges, confounders and interventions, with
  identification, estimation and refutation persisted as three separate stages.
- **Research obligation** — unresolved epistemic demand connectable to executable
  capability, with readiness, missing evidence and priority components.
- **Research action** — a proposal to acquire evidence, with utility components,
  governance state and realised gain.
- **Saturation state** — multidimensional coverage, source diversity, marginal gain,
  unexplored capability classes, contradiction and obstruction counts, budget remaining.
- **Reasoning run** — transactionally recorded operator invocation with input/output
  references, fingerprints, resource budget, status, failure code and truncation.
- **Completeness declaration** — completeness mode, coverage, saturation, blind spots and
  the unresolved population for any query implying universality.

---

## Success Criteria

Measurable and technology-agnostic, mapped to the owner's acceptance gates §54 A–M and
definition of done §60.

### Context and revision (gate A)

- **SC-001**: 100% of committed revisions survive a full process restart with identical
  content, verified by content hash comparison over the whole revision corpus.
- **SC-002**: 100% of revisions remain readable at every prior revision number after any
  number of subsequent revisions; zero revisions are edited or deleted after commit.
- **SC-003**: Replaying the same event log with the same rule set, operator versions and
  parameters reproduces identical content hashes at every declared artifact boundary —
  target: 100% of artifacts across the entire golden corpus, not only the final graph.

### Locality (gate B)

- **SC-004**: In the locality corpus, 100% of merges either succeed coherently or emit a
  persisted obstruction naming the blocking dimension; zero merges discard a conflicting
  contribution.
- **SC-005**: Comparison work grows with blocked candidate sets, not with the square of the
  cell count; a comparison bucket exceeding its limit is reported in 100% of cases and
  never silently processed.
- **SC-006**: 100% of restrictions pass the property test that restriction cannot
  fabricate evidence.

### Hypothesis and reasoning (gates C, D, E)

- **SC-007**: In the abduction corpus, every case with multiple compatible explanations
  retains at least two live hypotheses unless an explicit rule explains the collapse.
- **SC-008**: 100% of pruned candidates are recoverable from durable state with a
  dominance reason and the comparison set that justified pruning.
- **SC-009**: 100% of near-duplicate corpus cases return a top-*k* set with declared
  structural diversity; zero cases return *k* paraphrases of one explanation.
- **SC-010**: In the dialectical corpus, 100% of active hypotheses above the profile
  threshold either produce a counter-hypothesis or carry an explicit failure reason; and
  100% of unresolvable cases remain inconclusive rather than being resolved by fiat.

### Dynamics, causality, structural evidence (gates F, G, H)

- **SC-011**: 100% of change points in the dynamics corpus are reported as four distinct
  claims — change point, regime change, phase-transition candidacy, causal explanation —
  with independent identifiers and independent status.
- **SC-012**: 100% of non-identified causal evaluations report *not identified*; zero
  report a zero or default effect, and no single convenience causal score field exists.
- **SC-013**: 100% of topological features are traceable to a durable worldline snapshot,
  and the adversarial test suite demonstrates zero write paths from topological features to
  entity identity or truth state.

### Research loop and honesty (gates I, J, K)

- **SC-014**: 100% of contradictions and persistent obstructions that meet their declared
  conditions produce or update a research obligation; zero are dropped silently.
- **SC-015**: 100% of research actions expose decomposed utility — expected gain,
  discrimination, feasibility, source quality, cost, penalties — with no opaque scalar
  as the only output.
- **SC-016**: 100% of universal-intent queries declare a completeness mode, coverage,
  saturation and blind spots; zero present an open-world result as exhaustive.
- **SC-017**: The unresolved population is preserved as a first-class result set in 100% of
  identity-incomplete cases in the global-query corpus.

### Provenance, determinism, resources (gates K, L, M)

- **SC-018**: Every audit question in Appendix L is answered end-to-end from durable state
  in 100% of golden cases; a missing lineage edge is a test failure.
- **SC-019**: With the adaptive layer disabled, 100% of golden-corpus runs are
  byte-identical across repeats and across machines with pinned dependency versions.
- **SC-020**: 100% of runs that hit a declared limit return an explicit
  budget-exhaustion state naming what was and was not processed; zero truncate silently.
- **SC-021**: Zero cross-tenant reads succeed in the adversarial isolation suite; every
  tenant-scoped access path fails closed.
- **SC-022**: 100% of major derived results resolve to a method fingerprint naming concrete
  dependency versions; zero fingerprints reference a floating version range.

### v2 additions

- **SC-023**: Replay is fixed-point at every declared artifact boundary per determinism
  class; `EXACT` and `FIXED_POINT` artifacts are byte-identical across platforms.
- **SC-024**: Adding a duplicate of an existing evidence item raises neither `n_eff` nor any
  posterior — verified as a property test over the whole corpus.
- **SC-025**: 100% of universal-negative results are expressed as coverage-qualified absences
  meeting profile thresholds; zero are emitted as unconditional negatives.
- **SC-026**: `GLUED` is returned in 0% of runs where `triples_unchecked > 0`.
- **SC-027**: 100% of hypothesis spaces declared non-exhaustive carry a residual
  `H_OTHER` hypothesis with declared prior mass.
- **SC-028**: 0 ranking operations compare raw values across score kinds — enforced by
  property test.
- **SC-029**: Branch writes appear in mainline queries in 0 cases; verified by isolation suite.
- **SC-030**: 100% of analyst decisions carry a justification and appear beside
  model-derived state rather than instead of it.
- **SC-031**: Erasure drill passes: crypto-shredding removes payload, tombstone remains,
  integrity of all other artifacts stays verifiable, replay reports `REPLAY_DEGRADED`.
- **SC-032**: 0 cross-tenant cache reads succeed; every cache key carries `tenant_id`.
- **SC-033**: Slice-0 passes in dev-lite and dev-full with every intermediate artifact
  reproduced by replay.
- **SC-034**: Measured p95 tick latency, memory peak, replay time and corpus size meet or
  exceed the §47.4 targets ratified in Wave 0; misses are recorded as findings.

---

## Assumptions

- **024 objects are adopted, not rebuilt.** `InvestigationContext`, `ContextRevision`,
  `ResearchObligation`, `ResearchAction`, `ContextFrontier` and the Context Engine already
  exist, are async and durable, and are covered by passing tests. Baseline §58.1 forbids
  redefining their approved semantics. Task ordering must reflect this.
- **PostgreSQL remains authoritative.** No new graph authority is introduced; Neo4j stays a
  rebuildable serving projection (baseline §1.1).
- **The six existing time axes are authoritative.** 025 adds derived relations only, never a
  seventh axis.
- **TDA is already implemented and benchmarked** in `apps/projection/tda` and
  `apps/science/scitda`; 025 consumes it and enforces its boundary rather than rebuilding
  it.
- **The acquisition layer already exists** (145-source catalogue, Airbyte, BBOT, SearXNG
  integration). 025 wraps a completeness protocol around it; it does not build a new
  collector.
- **The world substrate remains the only entity truth.** No parallel context database with
  its own entity resolution is created (P12).
- **Adaptive components are optional and disabled by default**, and no correctness
  requirement depends on them.
- **The target environment is a 20 GB CPU-first developer machine**, so every operator must
  declare a memory class and no operator may assume GPU availability.
- **Research precedes new implementation** (`AGENTS.md` §1): the donor candidates identified
  in `research.md` §3 must be assessed before the corresponding tasks are estimated.
- **Wave 0 is a real gate.** The seven ADRs it requires do not yet exist in `docs/adr/`, and
  Phase A does not begin before they close.

---

## Out of scope

- A new application boundary. `apps/context-engine/` is forbidden.
- A new event backbone. The existing envelope contract is reused.
- A second graph authority or a second entity-resolution truth.
- Learning stalk spaces, restriction maps or attachment maps on the deterministic critical
  path.
- Building a new acquisition/collection stack.
- Rebuilding TDA.
- Any capability whose correctness depends on an adaptive model.

---

## Open decisions

Two decisions materially change the shape of the work. Neither has a defensible default,
so both are surfaced rather than assumed.

> **RESOLVED 2026-10-04 — owner decision: Q1 = B, Q2 = B.**
> Recorded in [`ADR-0028`](../../../docs/adr/0028-context-definition-identity-and-placement.md).
> Binding corrections carried into this spec:
>
> 1. **Split identifier namespaces.** `CXI-` = `InvestigationContext` (unchanged, 024
>    contract untouched). `CXD-` = `ContextDefinition` (new namespace; baseline §5 and
>    Appendix G.1 are amended on this point). One shared prefix across two objects would
>    make every reference, storage key and lineage edge ambiguous, so this correction is
>    **mandatory**, not optional refinement.
> 2. **Explicit link.** `InvestigationContext.definition_ref -> CXD-…`. The only change to
>    the 024 object is one additive, nullable foreign reference. Its identity derivation,
>    revision semantics and lifecycle are unchanged.
> 3. **Divergent semantics, not duplicate authorities.**
>    `ContextDefinition` = immutable analytical specification (objective, temporal scope,
>    semantic regime, analysis profile, policy). `InvestigationContext` = operational
>    revisioned state (revisions, obligations, frontier, decisions). One composes into the
>    other in one direction only.
> 4. **Placement deviation recorded.** `apps/control-plane/context_engine/` is the single
>    canonical implementation path. No `cp_domain/` package, no re-export or compatibility
>    shim, one import path per implementation. Baseline §1.2's path requirement is
>    superseded by verified repository topology.

<details>
<summary>Original decision text (superseded, retained for traceability)</summary>

### Q1 — Relationship between `ContextDefinition` (§5) and the existing `InvestigationContext` (024)

The baseline defines `ContextDefinition` with fields the existing object does not have
(`objective` structured text, `temporal_scope`, `semantic_regime_ref`,
`analysis_profile_ref`, `policy_ref`), while the existing object carries fields
`ContextDefinition` does not list (`question`, `scope_refs`, `current_revision`,
`revision_count`). Both mint the `CXI-` prefix. Baseline §58.1 says 025 must not redefine
024's approved semantics.

| Option | Answer | Implications |
|---|---|---|
| A | Extend the existing `InvestigationContext` in place, adding the 025 fields as first-class attributes | One object, one identity space, no migration. Cost: mutates a frozen 024 contract, so 024's approved semantics change by addition and must be re-approved |
| B | Keep `InvestigationContext` as-is; add `ContextDefinition` as a separate object that references it | Clean separation, 024 untouched. Cost: two context-shaped objects, a mapping layer, and analyst-facing ambiguity about which one a revision belongs to |
| C | New `ContextDefinition` becomes authoritative; existing `InvestigationContext` becomes a thin projection of it | Matches §58.1's intent best. Cost: largest migration, touching live API, storage and tests that currently pass |

**Your choice**: B (accepted 2026-10-04)

### Q2 — Placement of the control-plane layer

Baseline §1.2 requires `apps/control-plane/cp_domain/context_engine/`. The working
implementation of 024's Context Engine currently lives at `apps/control-plane/context_engine/`,
and `cp_domain/` does not exist anywhere in the repository.

| Option | Answer | Implications |
|---|---|---|
| A | Create `cp_domain/` and move the existing engine into it | Matches the baseline literally. Cost: moves passing, live-verified code; every import, test path and deployment reference changes |
| B | Keep `context_engine/` where it is and record a documented deviation from §1.2 | Zero disruption. Cost: permanent divergence from a placement rule the owner wrote deliberately, and a precedent for further divergence |
| C | Create `cp_domain/` as a thin package that re-exports the existing engine, new 025 code lands in `cp_domain/` | Incremental. Cost: two import paths for one engine, which is exactly the ambiguity that caused the earlier package-collision failures |

**Your choice**: B (accepted 2026-10-04)

</details>

---

## Readiness

Q1 and Q2 are **resolved and recorded** (ADR-0028). `/speckit.plan` is unblocked. The plan must carry forward the
risk register from `research.md`: R2 (adoption matrix for existing 024 objects), R3
(four-valued truth must not leak), R4 (causal staging has no donor precedent), R6 (Wave 0
gate is not yet satisfied), R1 (configuration-scope verification as a standing review item),
and R8 (repository constitution is still an unmodified template).