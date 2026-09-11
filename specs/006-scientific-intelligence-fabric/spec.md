---
description: "Specification for the Scientific Intelligence Fabric: calibrated probabilistic claims, hypothesis management with information gain, causal and temporal inference, network/spectral/higher-order analysis, null models, robustness and reproducible experiments surfaced through a scientific review UI"
---

# Feature Specification: Scientific Intelligence Fabric

**Feature Branch**: `006-scientific-intelligence-fabric`

**Created**: 2026-09-09

**Status**: Draft

**Input**: User description: "Scientific Intelligence Layer: probabilistic claims with calibrated uncertainty; information gain; causal inference with explicit confounder control; temporal dynamics; network/spectral/higher-order analysis; hypothesis management; calibration; null models; robustness; experiments and reproduction. Surface through a scientific peer-review-style UI (evidence ladder / confidence tiers). HARD BOUNDARY: the system must NOT mass-target or score real individuals by sensitive attributes (political affiliation, involvement in illegal activity, membership in marginalized groups). Outputs are scientific claims about structures and processes, not verdicts about named persons."

## User Scenarios & Testing

### User Story 1 - Probabilistic claims with honest calibration and provenance (Priority: P1)

Analysts see every claim as a probability distribution, not a verdict: a claim about a
network structure or process carries an explicit distribution over states, an epistemic
status, and a full trace back to observations (Claim → Credence → EvidenceLink →
Observation → Raw). No numeric confidence is ever invented: every probability derives
from observed evidence through a declared model; where evidence is missing the claim is
marked `UNCERTAIN` with the missing evidence enumerated, never defaulted to a guess.
Confidence values are periodically checked against reality (calibration curves) and
reported honestly (overconfidence is surfaced, not hidden).

**Why this priority**: This is the epistemic foundation everything else sits on. If
claims cannot carry calibrated, traceable, non-fabricated probability, then hypothesis
management, causal inference, temporal and network analyses all produce noise dressed as
intelligence. It directly enforces Constitution II (evidence-first) and the user's
hard boundary (no verdicts about individuals without a transparent, calibrated basis).

**Independent Test**: A small event corpus produces claims through at least two
different analysis paths; the platform returns for each claim a probability
distribution, a status, and a chain Claim → EvidenceLink → Observation → Raw; the
calibration report shows per-bucket observed-vs-expected frequencies; no claim carries
a probability that was not derived from evidence by a declared method.

**Acceptance Scenarios**:

1. **Given** an evidence corpus and an analysis module that emits a claim, **When** the claim is registered, **Then** it carries a probability distribution, an epistemic status (DRAFT|CONFIRMED|WEAKENED|DISCARDED|UNCERTAIN), a declared model identifier, and a trace from the claim to the raw observations that produced it.
2. **Given** a model producing probabilities for 100 test claims, **When** the calibration harness runs, **Then** it emits observed-vs-expected frequencies in decile buckets and a Brier score, and marks the model `OVERCONFIDENT` if ECE exceeds the threshold.
3. **Given** a claim whose supporting evidence is absent, **When** the claim is registered, **Then** the status is `UNCERTAIN`, the missing evidence is enumerated, and no probability is fabricated.

---

### User Story 2 - Hypothesis management with information-gain-driven collection (Priority: P1)

Analysts turn intelligence requirements into **hypotheses** that compete against each
other (not confirmation of a single story): each hypothesis links to supporting and
refuting evidence, holds a status (PROPOSED|ACTIVE|STRENGTHENED|WEAKENED|DISCARDED|
CONFIRMED|RESOLVED), and drives collection by **expected information gain** — the system
prioritizes which evidence to seek next because it discriminates most strongly between
the alive hypotheses. Coverage (which requirements are addressed) is reported per
project, no hypothesis is silently abandoned, and a hypothesis is only discarded via an
explicit recorded decision with reasons.

**Why this priority**: Second in the user's brief and the direct consumer of US1
calibrated claims. Information gain turns the platform from a passive search box into
an evidence-seeking analyst; hypothesis lifecycle with recorded decisions matches the
Constitution's observable-immutability rules.

**Independent Test**: Proposing two mutually exclusive hypotheses over a small corpus
produces a hypothesis register where both are alive, each evidence item attaches with
its direction, the collection planner returns a ranked "which evidence to seek next"
list based on expected information gain, and discarding a hypothesis produces a stored
decision; coverage per project is computable.

**Acceptance Scenarios**:

1. **Given** two competing hypotheses sharing a corpus, **When** an evidence item arrives, **Then** it is attached to the hypotheses it discriminates, updating each hypothesis's credence only through US1-calibrated precedence.
2. **Given** a hypothesis set and a budget for the next collection step, **When** the planner runs, **Then** it returns the evidence opportunity with the highest expected information gain and the hypotheses it would discriminate between.
3. **Given** a hypothesis that must be discarded, **When** the analyst records the decision, **Then** the hypothesis moves to `DISCARDED` with a stored decision (who/when/why) and its evidence links remain intact.

---

### User Story 3 - Causal inference with explicit confounder control (Priority: P2)

The system distinguishes correlation from causation. A causal claim is emitted only
through a declared causal structure (directed graph of candidate influences with stated
assumptions), confounders are explicitly named and controlled for, and claims about
individuals or about politically/illegally sensitive characteristics are **out of scope
by design** (the causal engine is scoped to structural, systemic, and mechanical
processes, not to scoring natural persons). Where the data only supports association,
the output is labeled `CORRELATIONAL` and never upgraded to causal without an explicit,
auditable model.

**Why this priority**: Causal confusion is the classic failure of intelligence-style
platforms and the riskiest area for the user's hard boundary. Doing it rigorously,
scoped to structures and processes, builds trust; doing it naively produces false
verdicts.

**Independent Test**: Two correlated series over a process graph produce an output
labeled `CORRELATIONAL` by default; registering a declared causal model with named
confounders upgrades eligible outputs to `CAUSAL` with an assumptions block; any request
whose target is a natural person's sensitive characteristic is refused with a scope error.

**Acceptance Scenarios**:

1. **Given** correlated observations without a declared model, **When** the causal engine classifies them, **Then** the output is labeled `CORRELATIONAL` with the possible confounders listed.
2. **Given** a declared causal model naming confounders C1..Cn, **When** the engine produces a causal conclusion, **Then** the conclusion carries the model id, the controlled confounders, and the stated assumptions.
3. **Given** a causal request whose outcome attribute is a person's political affinity or illegal-activity involvement, **When** the engine validates it, **Then** it returns a scope rejection referencing the boundary policy, and logs an audit event.

---

### User Story 4 - Temporal dynamics and change detection (Priority: P2)

Claims are treated as time-varying: states, strengths, and confidences evolve as
evidence changes. The system records the time validity of observations, detects change
points and discontinuity in time series, and renders temporal scenarios so an analyst
can see how a claim's support moved over time. Projection results already produced are
re-evaluated only through explicit re-computation rules (temporal scenarios feed
a comparison, not silent mutation of past results).

**Why this priority**: Intelligence questions are inherently temporal (before/after,
spread, cycles, lags). Without time awareness, all other analyses flatten history and
produce misleading confidence.

**Independent Test**: A one-dimensional time series with an injected regime change
produces a detected change point with a rationale; a claim fed daily evidence shows a
confidence curve; re-running a projection with changed inputs produces a new version
while the old one remains queryable.

**Acceptance Scenarios**:

1. **Given** a time series with an injected discontinuity, **When** the change detector runs, **Then** it reports the change point, confidence of the detection, and the segments before/after.
2. **Given** a claim observed over several time intervals, **When** its support is plotted, **Then** the UI shows the credence trajectory with the evidence events annotated.
3. **Given** a reprojection triggered by new data, **When** it completes, **Then** the prior projection remains available under its original version and the new result is recorded as `SUPERSEDES` (no silent mutation).

---

### User Story 5 - Network, spectral and higher-order analysis (Priority: P3)

For entity-relation structures, analysts can run structural analysis: graph/spectral
signals (centrality, spectral clustering, motif significance), and higher-order views
(temporal networks, hypergraph/simplicial interactions) — always bounded to tractable
scale (no accidental O(N²)) and always coupled to null models (a motif or cluster is
reported with its significance, not as an oracle). Outputs describe structures, never
verdicts about named individuals.

**Why this priority**: Structural analysis is a force multiplier for every other
capability, but it is the area most likely to be misread as "finding the bad guys". The
user explicitly refuses that; the value delivered here is descriptive structure with
honest significance, scoped to processes and relationships.

**Independent Test**: A small synthetic graph yields centrality/spectral outputs with
scores normalized to bounded range; a motif search reports motif counts with
permutation-based significance; a request to interpret a cluster as a hidden-criminal
network is refused or relabeled to a structural description; scale benchmark shows
sub-quadratic behavior on the projection graph.

**Acceptance Scenarios**:

1. **Given** an entity-relation graph, **When** spectral analysis runs, **Then** it returns normalized structural scores with a documented algorithm and a significance/null comparison.
2. **Given** a motif search on the graph, **When** significance is computed, **Then** it uses a permutation null model and reports a p-value/effect measure with the null's parameters.
3. **Given** a cluster result, **When** presented, **Then** it is described structurally (membership counts, internal/external density) with no attribution of illegal behavior to named persons.

---

### User Story 6 - Robustness, null models and reproducible experiments (Priority: P3)

Every scientific claim must survive scrutiny: results are stress-tested by perturbing
inputs (missing evidence, flipped labels, biased subsamples), by comparing against
null/permutation baselines, and by reproducibility rules (seeded randomness, frozen
dependency versions, recorded pipeline version for every result). An experiment
registry records runs with inputs, outputs, seeds, and versions so any claim can be
re-tested. Robustness reports and null comparisons are shown with the result, never
hidden.

**Why this priority**: The difference between a scientific platform and a dashboard is
that claims can be challenged and re-run. Robustness and reproducibility are what make
the calibration in US1 trustworthy and the hypotheses in US2 falsifiable.

**Independent Test**: A robustness run perturbs a fixed corpus across N conditions and
reports how the claim's conclusion changes (flip rate); a null-model run on shuffled
data returns baseline distributions the reported effect is compared against; re-running
an experiment with identical seeds and versions reproduces the recorded output;
perturbation and null data are stored and queryable.

**Acceptance Scenarios**:

1. **Given** a claim with fixed inputs, **When** robustness analysis perturbs the inputs (missing/flipped/subsampled), **Then** it reports the conclusion flip rate and the sensitivity summary, stored with the claim.
2. **Given** a reported effect, **When** the null-model run is requested, **Then** it produces a null distribution, the observed statistic, and a comparison (never a bare "significant" label without the null details).
3. **Given** a recorded experiment run, **When** the same seeds and dependency versions are re-applied, **Then** the output reproduces within tolerance and the re-run is logged with the same pipeline version.

---

### User Story 7 - Scientific review UI and evidence ladder (Priority: P3)

Analysts and reviewers work through a peer-review-style interface: claims and
hypotheses are laid out on an **evidence ladder** (tiered confidence from "observation"
to "calibrated, robust, confirmed claim"), each rung shows the evidence chain and
calibration/robustness context, and a claim cannot reach the top rung unless the
underlying checks (calibration, null model, robustness, reproducibility) are recorded.
The UI supports review comments, status transitions, and per-project coverage views.

**Why this priority**: The user's brief calls for the UI to express scientific rigor
rather than a flat tag cloud. The UI is the place where honest uncertainty becomes
legible to human reviewers, closing the loop on US1–US6.

**Independent Test**: Rendering a claim with full provenance shows the evidence-ladder
position; a claim with missing robustness/calibration context renders as
`REVIEW_PENDING`, blocked from the top rung; a reviewer comment and a status
transition are persisted and rendered.

**Acceptance Scenarios**:

1. **Given** a claim with complete provenance, **When** rendered in the science view, **Then** it shows the evidence ladder, calibration context, robustness summary, and full evidence chain.
2. **Given** a claim lacking calibration or robustness records, **When** rendered, **Then** it is shown as `REVIEW_PENDING` and cannot be marked top-rung.
3. **Given** a reviewer writing a comment and changing a status, **When** persisted, **Then** the review event (comment, actor, timestamp) is stored and visible on the claim.

---

### Edge Cases

- What happens when two competing hypotheses both gain evidence? Credence updates
  follow US1-calibrated distributions; both stay alive until a recorded decision
  discards one — no silent winner.
- How does the system handle a claim whose underlying model version changed? The claim
  records the model id+version; a new run produces a new versioned claim, the old one
  stays readable (Supersede, never mutate).
- What happens when perturbation flips a conclusion? The robustness report highlights
  the flip (noise region), and the claim is downgraded to `UNCERTAIN` until the
  fragility is resolved.
- How does the system handle "no signal"? Absence of evidence is reported as such: a
  null result is a stored positive result ("no detectable effect under these
  conditions"), never silently dropped.
- What happens when a scope-forbidden request arrives (person-level sensitive
  outcome)? Hard rejection with policy reference + audit event (Home rule, US3).
- What happens if the graph is too large for spectral decomposition? Bounded
  size-aware algorithms, sampling with declared sampling plans, or explicit
  "deferred" result — never a truncated guess.
- What happens when the evidence for a probability is thin? Status `UNCERTAIN` with
  enumerated missing evidence; the calibration harness still records the model's
  performance honestly.
- How does time-zone/time-scope ambiguity affect temporal claims? Timestamps are
  normalized to UTC with original values preserved and source precision labeled.
- What happens when null-model permutations are too few (tiny corpus)? The report
  states the permutation count and a warning that significance is unreliable at that
  count — no fabricated precision.
- What happens when a reviewer closes a claim with open comments? The claim is marked
  `RESOLVED` (or `DISCARDED`) with the decision link; comments remain queryable.

## Requirements

### Functional Requirements

- **FR-001**: System MUST register scientific claims that carry a probability
  distribution over states, an epistemic status, a model id+version, and a trace to the
  raw observations (Claim → Credence → EvidenceLink → Observation → Raw).
- **FR-002**: System MUST NOT fabricate probabilities: every numeric confidence must be
  derivable from evidence through a declared method, else status `UNCERTAIN`.
- **FR-003**: System MUST run calibration checks (observed-vs-expected per bucket,
  Brier, ECE) and label models `OVERCONFIDENT`/`CALIBRATED` accordingly.
- **FR-004**: System MUST manage hypotheses with status lifecycle
  (PROPOSED→ACTIVE→STRENGTHENED/WEAKENED→DISCARDED/CONFIRMED→RESOLVED), evidence links
  with direction, and recorded discard decisions.
- **FR-005**: System MUST prioritize collection by expected information gain across the
  alive hypotheses of a project and report coverage per project.
- **FR-006**: System MUST distinguish `CORRELATIONAL` from `CAUSAL` outputs; causal
  outputs require a declared causal model with named confounders and stated
  assumptions.
- **FR-007**: System MUST refuse causal/predictive requests whose outcome attribute is
  a natural person's political affiliation, illegal-activity involvement, or membership
  in a marginalized group, and MUST log a scope-rejection audit event (constant).
- **FR-008**: System MUST treat claims as time-variable: temporal validity of
  observations, change-point detection, credence trajectories, and versioned
  reprojection (Supersedes, never mutation).
- **FR-009**: System MUST support network/spectral/higher-order analysis that is
  bounded in complexity (no accidental O(N²)), normalized to bounded ranges, and
  reported together with null-model significance.
- **FR-010**: System MUST compare structural findings against permutation/randomization
  null models and report significance with null parameters.
- **FR-011**: System MUST run robustness analysis (missing/flipped/subsampled inputs)
  and report conclusion flip rates and sensitivity summaries.
- **FR-012**: System MUST keep an experiment/reproduction registry recording inputs,
  outputs, seeds, pipeline and dependency versions for every run.
- **FR-013**: System MUST present claims in a scientific review UI with an evidence
  ladder, calibration/robustness context, review comments, and status transitions;
  top-rung requires recorded calibration+null+robustness+reproducibility checks.
- **FR-014**: System MUST persist all events (claim, hypothesis, calibration, causal,
  temporal, structural, robustness, experiment, review) as immutable observable events.
- **FR-015**: System MUST keep all original observations, versions, and decisions
  queryable; supersedes/retraction/rejection are recorded as links, never deletions.
- **FR-016**: System MUST record scope-boundary violations (person-level sensitive
  outcomes) as audit events with policy reference.

*Needs clarifications resolved during planning (see `research.md`):* choice of
numerical/Bayesian stack, calibration libraries, graph/spectral libraries, null-model
iteration protocol, storage and event contracts — no open `NEEDS CLARIFICATION`
markers remain in this specification.

### Key Entities

- **ScientificClaim**: a probabilistic claim with distribution, status, model id+version,
  provenance chain, review state; relates to Observations, EvidenceLinks, Hypotheses.
- **Hypothesis**: a competing explanatory statement with status lifecycle, evidence
  links, information-gain priority, coverage and decisions.
- **EvidenceLink**: directed attachment of evidence to a claim/hypothesis with
  direction (supports|refutes|discriminates) and US1-calibrated weight.
- **CredenceDistribution**: the probability distribution over states a model assigns,
  with method and calibration metadata.
- **CalibrationReport**: observed-vs-expected buckets, Brier, ECE, verdict.
- **CausalModel**: declared directed structure with confounders and assumptions;
  scoped to structural/systemic processes.
- **TemporalSeries / ChangePoint**: time series of a variable with detected change
  points and rationale.
- **StructureAnalysisResult**: normalized spectral/network/higher-order outputs with
  algorithm and null significance.
- **NullModelResult**: null distribution, observed statistic, comparison, permutation
  count/warnings.
- **RobustnessReport**: perturbation conditions and conclusion flip rates.
- **ExperimentRun**: reproducible run with inputs, outputs, seeds, versions.
- **ReviewEvent**: reviewer comments and status transitions on a claim.

## Success Criteria

### Measurable Outcomes

- **SC-001**: 100% of registered claims carry a declared probability source: a claim
  with no declared method to derive its probability is rejected at registration.
- **SC-002**: >90% of models under test pass the calibration gate (ECE ≤ threshold)
  after their first calibration improvement cycle; all models are labeled
  `OVERCONFIDENT`/`CALIBRATED` with the evidence shown.
- **SC-003**: 100% of hypotheses track the full lifecycle with recorded decisions;
  discarding always stores who/when/why.
- **SC-004**: The collection planner returns an evidence opportunity ranked by expected
  information gain for every project with two or more alive hypotheses.
- **SC-005**: 100% of published causal outputs carry a declared model with named
  confounders; 100% of person-level sensitive-outcome requests are rejected with an
  audit event; no non-trivial redesign is needed to enforce the boundary (No-MVP rule).
- **SC-006**: Structural analyses complete within the complexity bound (documented
  benchmark, sub-quadratic on the projection graph) and 100% of reported motifs/clusters
  include null significance.
- **SC-007**: ≥99% of reproducibility checks reproduce recorded outputs within
  tolerance when seeds and dependency versions are held fixed.
- **SC-008**: The scientific UI renders the evidence ladder, calibration and robustness
  context for every claim; no claim can reach the top rung without recorded
  calibration+null+robustness+reproducibility checks.
- **SC-009**: All claims, hypotheses, calibration, causal, temporal, structural,
  robustness, experiment, and review events are stored as immutable, queryable events
  (Constitution I).

## Assumptions

- Rigorous "scientific" behavior means calibrated uncertainty and honest null/robustness
  reporting, NOT volume or speed of verdicts (user's hard boundary kept as invariant).
- The boundary is structural: person-level sensitive-outcome requests are refused
  regardless of apparent source quality — enforced at the analysis/API layer, not by
  post-hoc review.
- Numerical/statistical stack: Python with NumPy-family tooling already used by the
  platform; heavy graph kernels may be delegated to compiled extensions where
  performance requires (bounded by benchmark, not free reign).
- Storage and events: existing immutable event/observability infrastructure in
  `apps/shared/events` and control-plane is reused; scientific events follow the same
  envelope.
- The webapp is the delivery surface for the scientific UI (evidence ladder, review
  views), reusing existing theme/API-client conventions from prior tracks.
- Causal/temporal/structural engines are NEW first-party modules in the platform
  (`apps/science`), not ports of external donor code; donor libs are only consulted for
  best practices (Apache-2.0/MIT compatible; no copied proprietary UX).
- Real-world claim evaluation datasets will be scarce at first; calibration/null/robust
  verification uses synthetic + recorded-project corpora until real gold data accrues.
- `apps/science` becomes part of the uv workspace (`pyproject.toml` members) and its
  tests follow the root pytest marker conventions (`contract|integration|unit`).