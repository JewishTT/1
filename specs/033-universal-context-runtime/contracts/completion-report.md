# Contract 06 — `CompletionReport`

**Feature**: `033-universal-context-runtime`
**Governs**: the terminal accounting of an investigation.
**Enforces**: FR-055…FR-058; blueprint §26.

---

## Why this contract exists

§26.1 lists fourteen result states and forbids collapsing them. §26.2 then requires that every
terminal state carry a report. Together they define the platform's honesty: an investigation ends
with a statement of **what was established, what was not, and why it stopped**.

`COMPLETE_WITH_LIMITATIONS` is a normal ending. A clean-looking report with hidden gaps is the
failure this contract exists to prevent.

---

## The fourteen result states

| State | Means | Must not be confused with |
|---|---|---|
| `UNKNOWN_NOT_INVESTIGATED` | the question was never examined | `SEARCHED_NO_RESULT` |
| `NO_OBSERVATIONS` | nothing in the canonical stream | `SOURCE_UNAVAILABLE` |
| `SOURCE_UNAVAILABLE` | the source or access route is unavailable | `NO_OBSERVATIONS` |
| `QUERY_UNSUPPORTED` | no operator can express this query | `SEARCHED_NO_RESULT` |
| `SEARCHED_NO_RESULT` | a search ran and found nothing in scope | `QUALIFIED_ABSENCE` |
| `QUALIFIED_ABSENCE` | methodologically sufficient grounds to assert absence in a bounded scope | `SEARCHED_NO_RESULT` |
| `POSITIVE_SUPPORT` | evidence supports the proposition | `BOTH` |
| `NEGATIVE_SUPPORT` | evidence bears against the proposition | `NEITHER` |
| `BOTH` | positive and negative support coexist | a low confidence score |
| `INCONCLUSIVE` | evidence is insufficient for the required decision | `SEARCHED_NO_RESULT` |
| `BLOCKED_PARTIAL` | part of the work could not run | `COMPLETE_WITH_LIMITATIONS` |
| `HYPOTHESIS_REFUTED` | refuted within the stated criterion and scope | `NEGATIVE_SUPPORT` |
| `SATURATED_WITH_SCOPE` | saturation reached under declared coverage | "we looked everywhere" |
| `COMPLETE_WITH_LIMITATIONS` | the criteria are met, with named residuals | "complete" |

---

## Shape

```text
CompletionReport
├── context_id                REQUIRED
├── final_revision            REQUIRED
├── completion_status         REQUIRED   one of the fourteen
├── reason_code               REQUIRED   stable machine code
├── criteria
│   ├── satisfied[]           REQUIRED
│   └── not_satisfied[]       REQUIRED   may be empty
├── obligations
│   ├── satisfied[]           REQUIRED
│   └── residual[]            REQUIRED   may be empty
├── scope
│   ├── executed              REQUIRED
│   ├── unexecuted            REQUIRED
│   └── excluded              REQUIRED
├── sources
│   ├── attempted[]           REQUIRED
│   ├── unavailable[]         REQUIRED
│   └── unsupported_capabilities[] REQUIRED
├── coverage
│   ├── evidence_coverage     REQUIRED
│   └── known_selection_bias  REQUIRED
├── open
│   ├── conflicts_open[]      REQUIRED
│   └── hypotheses_unresolved[] REQUIRED
├── budgets
│   ├── consumed              REQUIRED
│   └── reason_for_stopping   REQUIRED
├── reproducibility
│   ├── manifest_ref          REQUIRED
│   └── policy_version        REQUIRED
└── forward
    ├── reopen_conditions[]   REQUIRED
    └── next_best_actions[]   REQUIRED
```

---

## Normative rules

### R1 — One report per terminal state

No investigation ends without one. A report is a durable object, not a log line or a UI toast.

### R2 — Residuals are first-class

`residual[]`, `unexecuted`, `unavailable`, `unsupported_capabilities`, `conflicts_open` and
`hypotheses_unresolved` are part of the status, not an appendix. An empty list is a claim that there
were none, and it must be true.

### R3 — The stop reason is from the closed set

Analyst closure, met criteria, policy/budget block, missing capability, or measured saturation. An
empty queue, exhausted retries, a low score or an empty result list are **not** stop reasons.

### R4 — Absence requires declared detection power

A `QUALIFIED_ABSENCE` status requires the source's detection power and coverage conditions to be
declared and met. Otherwise the status is `SEARCHED_NO_RESULT`.

### R5 — Refutation is scoped

`HYPOTHESIS_REFUTED` carries the criterion and scope in which the refutation holds. Outside them, the
hypothesis is not refuted.

### R6 — Saturation is bounded

`SATURATED_WITH_SCOPE` names the scope, the source universe and the measured marginal gain. It is
never an absolute claim about the world.

### R7 — Reopening is stated

`reopen_conditions[]` and `next_best_actions[]` say what new evidence or change would reopen the
investigation. A closed investigation that cannot be reopened is a dead end.

### R8 — The report is reproducible

`manifest_ref` and `policy_version` allow the report to be re-derived. A report whose inputs cannot
be named is an opinion.

---

## Prohibitions

- A terminal state without a report.
- `COMPLETE` used where `COMPLETE_WITH_LIMITATIONS` is the honest status.
- An absence claim without declared detection power.
- A refutation without its scope.
- A stop reason outside the closed set.
- Hiding open questions to present a single clean answer.

---

## Tests

| Test | Asserts |
|---|---|
| `tests/contract/test_completion_report.py::test_one_per_terminal_state` | R1 |
| `tests/golden/test_qualified_absence_requires_detection_power.py` | R4 |
| `tests/golden/test_saturation_is_bounded.py` | R6 |
| `tests/golden/test_refutation_scope.py` | R5 |
| `tests/integration/test_no_stop_on_empty_queue.py` | R3 |
