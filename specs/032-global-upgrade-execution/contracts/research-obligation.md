# Contract 07 — `ResearchObligation` (delta)

**Feature**: `032-global-upgrade-execution`
**Governs**: the knowledge requirement, as distinct from the acquisition task that serves it.
**Enforces**: FR-048, FR-049, FR-052, FR-053; blueprint §9.2, §9.4.

**Canonical definition**: `specs/030-global-platform-upgrade/contracts/obligation.md`. This file
records the distinctions Feature 032 enforces alongside it — the distinctions that prevent a queue
from masquerading as an investigation.

---

## Delta against 030

| # | Added obligation | Source | Why |
|---|---|---|---|
| D1 | `acceptance_predicates[]` are machine-evaluable and evaluated by the obligation, not by the task that happens to serve it | §9.2, FR-049 | task completion is not obligation satisfaction |
| D2 | `coverage_assumptions` are required for any absence claim | §9.2, §11.2 | a qualified absence without declared detection power is a guess |
| D3 | `residual_unknowns[]` are first-class members of the terminal state, not a report appendix | §9.4, FR-053 | closing with unknowns hidden is the failure this prevents |
| D4 | `stop_condition` is one of a closed set, and `queue_empty` is not a member | §9.4, FR-052 | exhausted work is not finished work |
| D5 | One observation may satisfy several obligations, and one obligation may generate many tasks, with the many-to-many recorded explicitly | §9.2, FR-049 | the relationship is not a foreign key in either direction |
| D6 | `marginal_gain` and `attempts` are recorded per evaluation so repeated no-gain work is visible | §9.2, §9.3 | suppression needs a history |

## The distinction, stated plainly

| | Obligation | Task |
|---|---|---|
| Question | what knowledge is required, and how would we know we have it? | what work can be attempted? |
| Satisfaction | acceptance predicates + coverage assumptions | a completed execution with an outcome |
| Cardinality | 1 obligation → N tasks | 1 task serves ≥ 0 obligations |
| Failure | blocked, partial, superseded — with the unknown named | failed, unavailable, policy-denied — with the cause named |
| Terminal state | satisfied / unsatisfied / blocked / superseded | completed / failed / cancelled |

An obligation that closes because its tasks finished has not been evaluated. It has been abandoned.

---

## Normative rules

### R1 — Task completion does not close an obligation

The evaluator runs the acceptance predicates against the collected evidence. If a predicate cannot
be satisfied, the obligation records why and returns to a non-terminal state.

### R2 — Empty output does not close a gap

A zero-result run is evaluated against `coverage_assumptions` and the source's declared detection
power. Without a declared power, the result is `SEARCHED_NO_RESULT`, never `QUALIFIED_ABSENCE`.

### R3 — A stop reason is from the closed set

Analyst closure, met acceptance criteria, policy/budget block, missing capability, or measured
saturation under a stated scope. Anything else is not a stop reason, and "the queue is empty" is
explicitly excluded.

### R4 — The terminal state carries the residuals

Every terminal state names residual unknowns, uncovered scope, unavailable sources and unexecuted
tasks. `COMPLETE_WITH_LIMITATIONS` is a normal outcome; a clean-looking report with hidden gaps is
not.

### R5 — Satisfaction is evidenced

Closing an obligation records the evaluator, its inputs, the predicate results and the evidence
that satisfied them. A closed obligation with no evaluator record is reopened on inspection.

### R6 — Reopening is allowed

New evidence, a policy change, an ontology change or an analyst decision may reopen a satisfied
obligation. Reopening appends a revision; it does not erase the prior satisfaction.

---

## Prohibitions

- An obligation with no acceptance predicates.
- A qualified-absence claim with no coverage assumption.
- A terminal state that omits its residual unknowns.
- A stop triggered by queue exhaustion, retry exhaustion, a low score or an empty result list.
- Deleting an obligation.

---

## Tests

| Test | Asserts |
|---|---|
| `tests/integration/test_obligation_not_satisfied_by_task_completion.py` | R1 |
| `tests/golden/test_empty_result_is_not_qualified_absence.py` | R2 |
| `tests/integration/test_stop_conditions.py` | R3 |
| `tests/integration/test_terminal_state_residuals.py` | R4 |
