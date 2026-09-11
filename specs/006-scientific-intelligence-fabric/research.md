# Research: Scientific Intelligence Fabric

**Date**: 2026-09-09 | **Feature**: [spec.md](spec.md)

Phase 0 artifacts resolving plan Technical Context unknowns and scientific-stack risks.

## 1. Numerical/Bayesian stack

- **Decision**: Use `numpy>=1.26` + `scipy>=1.13` for all numeric work in `apps/science`
  (probability math, information gain, change-point, spectral routines, permutation nulls).
  No new heavyweight dependency is introduced; a `pyproject.toml` for `apps/science`
  declares the same two deps already used by `admission` and `projection`.
- **Rationale**: Prior tracks already committed to NumPy/SciPy (`venue`d in admission +
  projection pyprojects); adding a threat of parallel numeric ecosystems (TensorFlow/JAX,
  statsmodels, PyMC) would blow up the uv lock and maintenance surface for no incremental
  scientific value at this scale. The domain is classical statistics — NumPy/SciPy covers
  it fully. The declared-method requirement (FR-002) is satisfied by citing a method id +
  version string in every claim, not by a specific library.
- **Alternatives considered**: PyMC/ArviZ for Bayesian inference — rejected: MCMC sampling is
  overkill for the hypothesis-credence updates targeted here (exact conjugate/analytical
  updates cover US2). statsmodels — rejected: regression/GLM conveniences are not needed by
  any US. A pure-stdlib `math` implementation — rejected: change-point and spectral kernels
  need vectorized linear algebra; stdlib would be slow and error-prone.

## 2. Calibration practice and honest overconfidence labeling

- **Decision**: Implement a compact calibration harness emitting per-decile
  observed-vs-expected frequencies, aggregate Brier score, and expected calibration error
  (ECE) with `m=10` bins; verdict `CALIBRATED` when `ECE ≤ ECE_THRESHOLD` and `OVERCONFIDENT`
  when mean confidence exceeds mean accuracy beyond a tolerance — otherwise `UNCALIBRATED`
  (status pending observation of enough predictions). All thresholds are configuration, not
  magic numbers.
- **Rationale**: ECE + Brier are the standard honest-uncertainty metrics; the label
  (`OVERCONFIDENT`/`CALIBRATED`) directly implements FR-003 and surfaces overconfidence
  rather than hiding it. The ADC (Correction) distinction between "measured well" and
  "corrected to well" is respected: the registry stores the model's raw performance and any
  recalibration as separate records (Constitution IV — no single score).
- **Alternatives considered**: netcal package — rejected: adds a dep for one binning scheme.
  In-hit-rate-only — rejected: fails to capture overconfidence (a model can be "right often"
  while consistently overstating its confidence). No calibration at all — rejected: contradicts
  US1's core value and SC-002.

## 3. Information-gain-driven collection planning

- **Decision**: Model each hypothesis's credible uncertainty as a distribution over the
  evidence space; for each candidate "next evidence opportunity" compute the **expected
  information gain** = expected divergence (KL) between the current posterior and the
  posterior after observing that evidence (mixture over possible outcomes). The planner ranks
  opportunities within a project budget and returns the ranked list plus the hypothesis pair
  each opportunity discriminates.
- **Rationale**: Expected-KL information gain is the canonical decision-theoretic ranking —
  it directly serves US2's "which evidence to seek next because it discriminates most" and is
  cheap to compute from distributions that the claims layer already emits. Conservation
  applies: gain is computed only across **alive** hypotheses, so dead hypotheses stop pulling
  collection resources.
- **Alternatives considered**: Uncertainty-sampling heuristics (entropy reduction) — similar
  but conflate informativeness with surprise; KL gain against the hypothesis set is closer to
  the user's "discriminates between hypotheses" wording. Random/budget-doubling selection —
  rejected: no discrimination value. Thompson-sampling-style randomized selection — deferred:
  the deterministic KL ranking is testable and sufficient; randomness is left to the
  reproduction seeds where needed.

## 4. Causal inference scope and confounder control

- **Decision**: Implement a **declared-model causal engine**: analysts register a `CausalModel`
  (directed graph of candidate influences, named confounders, stated assumptions, scope
  declaration). Without a declared model the engine labels outputs `CORRELATIONAL` (listing
  candidate confounders); with one it may label eligible outputs `CAUSAL` carrying the model
  id, controlled confounders, and assumptions. Scope enforcement: any output attribute that
  names a natural person's political affinity, illegal-activity involvement, or marginalized-group
  membership is rejected with a policy-reference audit event BEFORE any computation.
- **Rationale**: This implements FR-006/FR-007 with an auditable paper trail. Correlation vs
  causation is settled by the presence of a declared, inspectable model rather than by a
  black-box "score", which is both more honest (Constitution II — traceable) and the only way
  to keep the person-boundary machine-enforceable (reject by attribute Schema in the model,
  not by post-hoc review).
- **Alternatives considered**: Full SCM/do-calculus library (e.g., dowhy) — rejected: adds a
  heavy dep; the platform needs declared-structure honesty, not intervention automation.
  Free-text "causal tags" — rejected: unenforceable and un-inspectable. Post-hoc content
  review for the boundary — rejected: user explicitly requires the boundary to be structural,
  not a reviewer judgment.

## 5. Change-point detection for credence trajectories

- **Decision**: Use a windowed mean-shift / CUSUM-style detector on scalar credence series
  (module reference: `temporal/changedetect.py`), parameterized by a minimum segment length
  and a change-severity threshold; emit the change point, detection confidence, and
  pre/post-segment summaries. Series are built from per-observation credence samples, not
  from fitted curves.
- **Rationale**: Credence trajectories are short noisy scalar series; CUSUM is robust, cheap,
  explainable, and satisfiable within SciPy (no new deps), matching US4's "detect discontinuity
  and show a rationale". Config thresholds externalized for tuning via the calibration
  harness output. Time values normalize to UTC with original precision retained.
- **Alternatives considered**: ruptures/BOCPD libraries — rejected: added dep + heavier prior
  machinery than the series justify. A manually-fitted rolling mean — rejected: no principled
  discontinuity signal. Full Bayesian online change detection — deferred: CUSUM meets SC-005
  test criteria; BOCPD is a documented follow-up if series become dense.

## 6. Spectral and higher-order structure analysis with null significance

- **Decision**: Implement size-aware primitives in `apps/science/structure`: normalized
  centrality/spectral scores (bounded to `[0,1]` via documented normalization), spectral
  clustering on the connected components that fit the complexity budget, and motif counts
  with **permutation nulls** (degree-sequence-preserving shuffles — stub-and-edge swap) as the
  significance baseline. Any analysis exceeding the node/edge budget is refused with a
  `DEFERRED` result carrying the budget and a declared sampling plan — never a truncated guess.
- **Rationale**: FR-009/FR-010 demand bounded complexity and honest significance. Stub-swap
  rewiring is the standard motif-null; normalized bounded scores keep structural outputs
  comparable (SC-006) without any claim about identity — matching US5's "structures, never
  verdicts". Reusing the projection graph through the shared abstraction (Constitution V)
  keeps the kernel swappable.
- **Alternatives considered**: networkx for convenience — rejected: pulls a new dep; spectral
  centrality needs only NumPy/SciPy eigensolvers here. False-discovery-rate-free raw counts —
  rejected: raw counts are exactly the "oracle" reading the user refuses. Global (non-permuted)
  baseline — rejected: can't distinguish structural signal from degree-artifact.

## 7. Null models and robustness reporting protocol

- **Decision**: Null-model results carry the observed statistic, the null distribution
  (histogram + parameters: N permutations, shuffle type) and a comparison (effect + p-value
  WHERE reliable — p-value suppressed with a warning when permutation count yields an
  unreliable estimate). Robustness analyzer perturbs inputs in three declared families —
  missing fraction, label flips, biased subsample — over a declared grid, and reports
  conclusion **flip rates** plus a sensitivity summary per family. No bare "significant"
  labels; no hidden null.
- **Rationale**: This is the half-measure killer the user's brief demands: conclusions in
  US1–US6 are only trustworthy if they survive perturbation and are compared to baselines.
  Persisting nulls and robustness reports as queryable artifacts (FR-011/FR-016) means any
  claim can be challenged and re-run (SC-007).
- **Alternatives considered**: Only reporting effect sizes — rejected: hides fragility.
  Fixed default perturbation without declared families — rejected: must be auditable and
  configurable. Bootstrap-only — rejected: bootstrap estimates sampling variability, not
  evidence-robustness; the flip-rate perturbation is the load-bearing device for SC-008's
  gating.

## 8. Reproducibility: seeds and version pinning

- **Decision**: The experiment registry stores, for every run: input refs, output refs,
  seed(s), pipeline version, dependency freeze (from the uv lock), and a tolerance; a
  reproduction check re-runs with identical inputs/seeds/versions and compares outputs within
  tolerance. Every claim references its producing run/experiment where one exists.
- **Rationale**: SC-007 (≥99% reproduction within tolerance) requires recording, not hoping.
  The uv lock and repository state are already versioned, so the freeze is a label on the run;
  seeds discipline NumPy/SciPy stochastic kernels so re-runs are bit-repeatable.
- **Alternatives considered**: Byte-identical output hash — rejected: tolerance is the honest
  contract (platform version drift changes nothing silently but exact float equality is not
  the goal). Container image pinning — deferred: the repo ships a container per deploy already;
  the registry records versions, the deployment layer owns images.

## 9. Event mapping (`science.*` topics)

- **Decision**: Extend `apps/shared/events/topics.py` `EVENT_CATALOG` with:
  `science.claim.registered`, `science.claim.status_changed`, `science.claim.discarded`,
  `science.hypothesis.proposed`, `science.hypothesis.evidence_attached`,
  `science.hypothesis.status_changed`, `science.hypothesis.discarded`,
  `science.calibration.report`, `science.causal.classified`, `science.causal.scope_rejected`,
  `science.temporal.change_point`, `science.structure.analyzed`, `science.robustness.report`,
  `science.experiment.run`, `science.experiment.reproduction`, `science.review.commented`,
  `science.review.status_changed` — all refs-only JSON payloads (Constitution I-5 rule).
- **Rationale**: Immutable envelopes make every scientific artifact rebuildable (Constitution
  12) and let the webapp subscribe for live updates. Prior tracks already follow the
  `build_envelope` / `topic_for` pattern; adding keys is a mechanical, tested extension.
- **Alternatives considered**: One aggregate `science.event` topic — rejected: loses per-type
  schema value and stream-partitioning. Storing only state rows without envelopes —
  rejected: violates the observation-immutable substrate and rebuildability invariants.

## 10. Evidence-ladder UI gating

- **Decision**: The webapp renders claims on a 5-rung evidence ladder
  (OBSERVATION → LINKED → SCORED/STRUCTURED → CALIBRATED → CONFIRMED). The top rung
  (`CONFIRMED`) is reachable only when the claim record carries recorded
  calibration + null + robustness + reproducibility artifacts (FR-013); otherwise the claim
  renders `REVIEW_PENDING` with the missing gating checks enumerated. Review comments and
  status transitions are persisted as `science.review.*` events and rendered inline.
- **Rationale**: The ladder is the user-visible embodiment of SC-003/SC-008 rigor: reviewers
  see *why* a claim is (not) confirmable, and the gating is machine-checked, not stylistic.
  Reuses the webapp's existing theme/API-client conventions.
- **Alternatives considered**: Flat score badge — rejected: exactly the "single score"
  presentation the Constitution (IV) forbids. Reviewer-discretion-only top rung — rejected:
   gating must be structural. Custom-drawn ladder — rejected: reuse existing UI components
  with tiered badges.

## Cross-cutting decisions

- **Workspace**: add `apps/science` to `[tool.uv.workspace] members` in root
  `pyproject.toml` (src layout `apps/science/{claims,hypotheses,causal,temporal,structure,
  robustness,experiments,review,api}`).
- **API surface**: `science` router mounted on the control plane exposes
  claims/hypotheses/calibration/causal/temporal/structure/robustness/experiments/review
  endpoints; scope-boundary rejection surfaces as `422 scope_refused` with policy reference.
- **Attribution/license**: all `apps/science` modules are first-party; donor projects
  (Apache-2.0/MIT) consulted only for algorithmic best practices — headers note the basis for
  each derived method, never copied code (matches tracks 002–005 policy).
- **Synthetic-first evaluation**: calibration/null/robust/reproduction verification runs on
  synthetic corpora + recorded-project data until real gold datasets accrue; benchmark
  harness optional via `bench/science/` if scale gates (SC-006) become load-bearing.