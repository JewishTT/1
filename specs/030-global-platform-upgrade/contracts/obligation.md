# Contract 04 — Obligation, Action, Attempt, Decision, Memory

**Feature**: `030-global-platform-upgrade`
**Governs**: the research process state machine.
**Enforces**: FR-037…FR-046, P5, P8, P11.

---

## The five separated responsibilities [FR-037] / P8

**[MEASURED]** These already exist as separate classes in
`apps/control-plane/context_engine/engine.py` and the plan preserves rather than re-implements them:

| Responsibility | Class | Line |
|---|---|---|
| Obligation generation | `ObligationGenerator` | `engine.py:100` |
| Satisfaction evaluation | `SatisfactionEvaluator` | `engine.py:185` |
| Action proposing | `ActionProposer` | `engine.py:264` |
| Decision recording | `DecisionRecorder` | `engine.py:345` |
| Revision management | `RevisionManager` | `engine.py:407` |

A single object mixing all five is forbidden. `ContextEngine` (`engine.py:475`) composes them.

---

## ResearchObligation

```text
ResearchObligation
├── obligation_id, context_id, question_ref, scope_ref
├── trigger                        REQUIRED, immutable once written
│   ├── kind
│   ├── event_id
│   ├── rule_id, rule_version
│   ├── reason                     exact, human-readable, non-generic
│   └── evidence_refs[]
├── question / intent
├── parent_refs                    { gaps[], hypotheses[], contradictions[], claims[] }
├── required_outcome
│   ├── kind
│   ├── hypothesis_refs[]
│   └── acceptance_predicates[]    e.g. ["independent_source", "time_consistent"]
├── capabilities_required[], eligible_sources[] + justification_each
├── unknown_dependencies[], policy_requirements[]
├── priority_components            NULLABLE = not yet estimated
├── expected_gain, cost_range, success_estimate + semantics, uncertainty
├── status + transition_history[]  every transition with a reason
├── attempt_history[]              { action_ref, outcome, marginal_gain, cost, suppression_rule }
├── stop_rule, satisfaction_rule, scope_boundaries
└── rules_fingerprint
```

### Rules

**O1 — `required_outcome` is not the ranking signal.** Acceptance criteria and priority are separate
fields with separate owners. Merging them lets a high-priority action quietly redefine what counts as
answering the question.

**O2 — Unknown is `null`, never `0.0`.** An unestimated `expected_information_gain` is `null`. It is
not zero, and it is not a small positive number. Fabricating a number here is the exact failure the
source specification prohibits.

**O3 — An obligation is never deleted.** Superseded, withdrawn and deferred preserve history and
cause. A reopened obligation retains a link to its prior instance and the reason for reopening.

**O4 — Task completion never satisfies an obligation.** Satisfaction requires the declared
acceptance criteria plus evidence refs plus an evaluator version. Task count is not a criterion
(FR-040).

**O5 — A gap never vanishes silently.** It is satisfied against criteria, superseded by a new
formulation, explicitly blocked with a named blocker, or still open. A function returning `[]` and a
task ending are not resolutions (FR-039).

**O6 — `UNSATISFIED` ≠ false.** It means the executed evidence did not meet the criteria.

**O7 — `PARTIALLY_SATISFIED` produces residue.** When justified, it creates a child obligation or
residual gap.

---

## ResearchAction and ActionAttempt

**ResearchAction** — a proposed plan; immutable once scheduled except by supersession.

```text
ResearchAction
├── action_fingerprint            canonical: plan + scope + time range + params + operator version
├── obligation_refs[]             MANY-TO-MANY with obligations
├── capability_descriptor, payload, preconditions, source_selection
├── estimate                      cost vector + latency
├── policy_state, approval_state
├── ranking_feature_vector        contract 04 §Action utility
├── constraints_applied[]         which hard filters passed
├── expected_outcomes[]
└── idempotency_key, replay_key
```

**ActionAttempt** — one execution. **Multiple attempts never collapse into one action status.**

```text
ActionAttempt
├── attempt_id, action_ref, task_id
├── worker_version, operator_version, source_version
├── started_at, completed_at
├── actual_cost                   vector
├── observation_refs[]
├── status, error_code            contract 03
├── retries, failure_class
├── marginal_gain                 measured value, or EXPLICIT unknown
├── affected_obligation_refs[]
└── diagnostics                   redacted before leaving the operator boundary
```

---

## Action utility vector

**Fourteen components, each independently inspectable:**

```text
expected_information_gain · hypothesis_discrimination · relevance · source_quality
evidence_independence_gain  · novelty · temporal_freshness  · probability_of_success
estimated_cost · latency · repeat_penalty · source_failure_rate · resource_risk · policy_penalty
```

### Ranking pipeline — order is normative

1. **Hard filters** — scope, access, tenant, budget, capability, approval, safety, legal. Applied
   **first**. An excluded candidate is recorded with its exclusion reason; exclusion is never
   invisible (P11, FR-043).
2. **Redundancy/suppression** — drop or suppress candidates unless a declared condition changed.
3. **Feature vector** — compute the fourteen components.
4. **Deterministic ranking** — weighted / Pareto / policy-defined.
5. **Optional adaptive reordering** — a learned component may propose a reorder; the deterministic
   core validates hard constraints; the **applied policy version and its inputs are stored**.

### Rules

**U1 — No single scalar is the stored truth.** A composite may be produced by a **versioned**
policy; the component vector and the policy version are retained with it (P5).

**U2 — Hard constraints cannot be outweighed.** No amount of expected gain compensates for a policy
violation, budget overrun, missing capability or absent approval (FR-043).

**U3 — `probability_of_success` carries its semantics.** An uncalibrated heuristic is labelled
`uncalibrated_score`, not `0.73`. A number without semantics is a fabrication.

**U4 — The adaptive layer is disableable.** With it off, the system continues on the deterministic
baseline with an explicit degraded-quality status. An adaptive layer may prioritise; it may not
redefine whether an obligation exists, satisfy one, or reclassify knowledge truth (FR-044).

**U5 — Ranking explains itself.** Every selection carries the component breakdown that produced it.

**U6 — Cost is a vector.** See contract 01. Never a bare currency figure or a bare latency.

---

## ActionMemory

**Key**: canonical action fingerprint + scope + temporal range + parameters + operator version.

**Record**: outcome, actual cost, **measured marginal gain**, attempt count, suppression state,
re-open conditions.

### Rules

**M1 — Failure and no-result are different memory states.** A source that errored is broken. A source
that returned nothing is uninformative. Collapsing them means a broken source gets suppressed as
"unproductive" and a working source gets retried forever.

**M2 — Suppression carries re-open conditions.** See contract 03 §Suppression.

**M3 — `no_change` is progress-adjacent, not progress.** It updates utility estimates and suppression
without deleting the attempt.

---

## DecisionRecord

```text
DecisionRecord
├── decision_id, decision_type, actor / system_principal
├── context_id, definition_ref, revision_ref
├── target_ref, prior_state, resulting_state
├── trigger_event_id
├── rule_id / operator_id + version, parameters
├── evidence_refs[]
├── alternatives_considered[]      REQUIRED where materially meaningful
├── rationale
├── hard_constraints_applied[]
├── override_ref, review_ref
└── digest
```

### Rules

**D1 — Every state change has one.** Including action approval/rejection, closure, admission,
satisfaction, policy change and identity merge/split.

**D2 — Atomic with the state change.** In the same transaction as the revision it justifies. Not a
separate write, not an eventual trace (contract 05).

**D3 — Alternatives are visible.** "We chose lexical over vector" is recorded. A decision with no
recorded alternative cannot be reviewed later.

**D4 — No raw content.** Rationale references evidence refs, never inline raw text (FR-096).

---

## Stop decision

The loop terminates **only** for an explicit recorded reason:

| Reason | Condition |
|---|---|
| `completed` | All required obligations met their declared criteria |
| `completed_with_limitations` | Useful result exists, named limitations remain |
| `saturated` | Marginal expected gain below a declared threshold **under stated scope and source universe with declared detection power** |
| `blocked` | Required work cannot proceed — access, capability, policy, dependency, resource |
| `needs_review` | A human decision is required for a material identity, contradiction, policy or interpretation choice |
| `cancelled` | Explicit operator termination |

### Rules

**S1 — These are NOT stop reasons**: empty results, task completion, exhausted retries, low model
confidence, workflow expiry, an empty queue.

**S2 — Saturation is scoped, never universal.** It states the scope, the source universe and the
detection power it was computed under. It is not a claim of omniscience.

**S3 — Every stop reports residual unknowns and unexecuted scope.**

**S4 — `blocked` is not `closed`.** A blocked investigation is resumable.

---

## Validation

| Check | On failure |
|---|---|
| `trigger` complete and immutable | reject |
| Unestimated priority component ⇒ `null` | reject if `0.0` |
| `satisfied` ⇒ acceptance criteria + evidence refs + evaluator version | reject |
| Any transition without a recorded reason | reject |
| Ranking candidate excluded by a hard filter ⇒ exclusion recorded | reject |
| `probability_of_success` without semantics | reject |
| Suppression without re-open conditions | reject |
| `no_change` recorded as progress | reject |
| Stop without a reason from the table | reject |
| Stop with reason `saturated` lacking scope + detection power | reject |
| DecisionRecord absent for a state change | reject |