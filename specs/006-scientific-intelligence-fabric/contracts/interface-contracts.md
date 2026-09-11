# Interface Contracts: Scientific Intelligence Fabric

**Date**: 2026-09-09 | **Feature**: [spec.md](spec.md)

Authoritative in-repo contract docs referenced where they already exist
(`apps/shared/contracts/statement.md`, `graph.md`, `correlation-review.md`,
`resolution-admission.md`). The scientific layer introduces a new first-party package
`apps/science`; its public interfaces and event contracts are defined here.

## 1. Scientific Claim registration — `apps/science/claims/registry.py`

```python
def register_claim(*, project_id: str, statement: str,
                   distribution: CredenceDistribution,
                   provenance: list[EvidenceLink], producer_run: str | None = None,
                   tenant_id: str) -> ScientificClaim
```

- Invariant (FR-001): provenance MUST be non-empty and each EvidenceLink MUST trace to an
  immutable observation/raw — empty provenance → `ProvenanceRequiredError`.
- Invariant (FR-002): `distribution.method` MUST resolve to a declared model id+version —
  unknown → `UnknownModelError`. No probability is fabricated: the method is recorded and
  is re-derivable from evidence.
- Invariant (boundary, FR-007): if `statement` is a person-level sensitive outcome
  (political affiliation, illegal-activity involvement, marginalized-group membership),
  registration → `ScopeBoundaryError` and an audit event; nothing is computed.
- Event: `science.claim.registered` (refs/fields only, I-5).

## 2. Calibration harness — `apps/science/claims/calibration.py`

```python
def calibrate(model_id: str, predictions: Sequence[Prediction], *,
              thresholds: CalibrationThresholds) -> CalibrationReport
```

- Returns per-decile observed-vs-expected buckets, aggregate Brier, ECE (m=10), and verdict
  `CALIBRATED | OVERCONFIDENT | UNCALIBRATED`.
- Verdict: `ECE ≤ ece_threshold` AND `mean_confidence − mean_accuracy ≤ tol` → `CALIBRATED`;
  overconfident drift → `OVERCONFIDENT`; insufficient samples → `UNCALIBRATED`.
- Event: `science.calibration.report`. Reports immutable and referenced by claims.

## 3. Hypothesis lifecycle — `apps/science/hypotheses/model.py`

```python
def propose_hypothesis(*, project_id: str, text: str, tenant_id: str) -> Hypothesis
def attach_evidence(hypothesis_id: str, link: EvidenceLink) -> None           # direction-tagged
def discard_hypothesis(hypothesis_id: str, decision: DecisionRecord) -> None  # requires decision
```

- Invariant (SC-003): `discard_hypothesis` without a decision → `DecisionRequiredError`;
  discard stores who/when/why and keeps evidence links intact.
- Credence updates ONLY through US1-calibrated precedence (`claims` layer); no ad-hoc
  weighting. Events: `science.hypothesis.proposed`, `.evidence_attached`,
  `.status_changed`, `.discarded`.

## 4. Information-gain planner — `apps/science/hypotheses/gain.py`

```python
def plan_collection(project_id: str, opportunities: Sequence[EvidenceOpportunity],
                    budget: int) -> list[RankedOpportunity]
```

- Returns opportunities ranked by expected KL information gain across **alive** hypotheses
  (dead hypotheses excluded), each carrying the hypothesis pair it discriminates.
- Event (read-only, no write): no envelope; callers decide via hypothesis/project routes.

## 5. Causal engine + scope boundary — `apps/science/causal/*`

```python
def classify(evidence: Sequence[EvidenceLink],
             model: CausalModel | None) -> CausalConclusion
def ensure_scoped(outcome_attribute: str) -> None   # raises ScopeBoundaryError
```

- Without `model`: label `CORRELATIONAL` + possible_confounders list (FR-006).
- With `model`: label `CAUSAL` iff the model declares the outcome and controls the named
  confounders; conclusion carries model id, confounders, assumptions.
- `ensure_scoped` rejects person-sensitive outcome attributes BEFORE computation (FR-007);
  rejection emits `science.causal.scope_rejected` (audit). Person attribute classes are
  hard-excluded and cannot be declared as scope in `CausalModel` (validation).
- Events: `science.causal.classified`, `science.causal.scope_rejected`.

## 6. Temporal / change-point — `apps/science/temporal/*`

```python
def build_series(variable: str, samples: Sequence[ObservationSample]) -> TemporalSeries
def detect_change_points(series: TemporalSeries, params: ChangeDetectParams) -> list[ChangePoint]
```

- Time values normalized to UTC; original values preserved (I-1).
- Superseding a prior projection creates a new versioned result linked via
  `SUPERSEDES` — never mutation (FR-015).
- Event: `science.temporal.change_point`.

## 7. Structure analysis — `apps/science/structure/*`

```python
def analyze(graph_ref: str, *, budget: AnalysisBudget, kind: StructureKind,
            null_params: NullParams) -> StructureAnalysisResult
```

- Complexity bound enforced (no accidental O(N²)); budget exceeded → `DEFERRED` result with
  the budget and a declared sampling plan — never a truncated guess (SC-006).
- Scores normalized/bounded (`[0,1]` or documented range) with a declared algorithm id.
- Significance always present or explicitly `DEFERRED` (FR-010).
- Event: `science.structure.analyzed` (result ref + significance ref; structural only).
- Outputs describe structure (membership counts/density/motif counts), never person verdicts.

## 8. Robustness — `apps/science/robustness/*`

```python
def analyze_robustness(claim_id: str, perturbations: PerturbationGrid) -> RobustnessReport
```

- Runs the three declared families — missing-fraction, label-flip, biased-subsample — over
  the declared grid; reports conclusion flip rates + sensitivity summary + noise regions
  (FR-011).
- Event: `science.robustness.report`. Report referenced by the claim; claim downgraded to
  `UNCERTAIN` when a flip lands in the relevant region.

## 9. Experiments / reproduction — `apps/science/experiments/*`

```python
def record_run(*, input_refs, output_refs, seed, pipeline_version,
               dependency_freeze, tolerance) -> ExperimentRun
def reproduce(run_id: str) -> ReproductionResult       # retries seeds+versions; compares ≤ tolerance
```

- ≥99% reproduction within tolerance when seeds/versions held fixed (SC-007).
- Events: `science.experiment.run`, `science.experiment.reproduction`.

## 10. Scientific review (UI gating) — `apps/science/review/*`

```python
def ladder_position(claim: ScientificClaim, gates: LadderGates) -> int | None
def comment_on_claim(claim_id: str, actor: str, body: str) -> ReviewEvent
def change_status(claim_id: str, actor: str, to_status: ClaimStatus) -> ReviewEvent
```

- `ladder_position` machine-checks gates: top rung requires recorded calibration + null +
  robustness + reproduction artifacts (FR-013); otherwise `None` (= `REVIEW_PENDING`).
- Events: `science.review.commented`, `science.review.status_changed`.

## Cross-cutting

- **Envelope**: all events use `events.kafka.build_envelope` with refs/fields-only JSON
  payloads (no blobs; Constitution I-5). Topics registered in `apps/shared/events/topics.py`
  `EVENT_CATALOG` (research §9).
- **Persistence**: state rows mirror these records in the hermetic in-memory store
  (Control-plane pattern) so projections stay rebuildable from the event log (I-12).
- **Boundary**: scope checks run first in every entry point; all reads/writes pass through
  the same `ensure_scoped` guard (FR-007/SC-005).