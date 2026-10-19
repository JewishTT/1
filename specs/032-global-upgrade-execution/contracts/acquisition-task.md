# Contract 02 — `AcquisitionTask` vNext

**Feature**: `032-global-upgrade-execution`
**Governs**: the durable unit of acquisition work.
**Enforces**: FR-008, FR-009; blueprint §3.2.

---

## Why this contract exists

An acquisition task is where authorisation, scope, budget and provenance meet. If any of those is
missing from the task, it has to be re-derived at execution time from ambient state — and ambient
state is how a task ends up fetching something no investigation asked for.

The blueprint's §3.2 lists the references a task must carry. The list is not decorative: each group
answers a question that would otherwise be answered by a default.

| Group | Question it answers | Failure if absent |
|---|---|---|
| tenant / investigation / context / revision | whose work is this, under which definition? | cross-context contamination |
| obligation / action / task / parent work / seed provenance | why does this exist? | unattributable collection |
| source / runtime / capability / query | what is being asked of whom? | capability silently downgraded |
| scope / access mode / policy snapshot / credential ref | is this permitted? | policy bypass |
| temporal / geographic / depth filters | what is in scope? | silent scope expansion |
| bytes / records / timeout / budgets | how much is enough? | runaway collection |
| retry / idempotency / checkpoint / schedule / priority | has this already happened? | duplicated coverage |
| expected result kinds / acceptance | what would count as success? | "no result" mistaken for success |

---

## Shape

```text
AcquisitionTask
├── identity
│   ├── task_id                    REQUIRED
│   ├── tenant_id                  REQUIRED
│   ├── investigation_id           REQUIRED
│   ├── context_id                 REQUIRED
│   └── context_revision_id        REQUIRED
├── research binding
│   ├── obligation_id              REQUIRED   the knowledge requirement this serves
│   ├── action_id                  REQUIRED   the planned action it executes
│   ├── parent_work_id             OPTIONAL   the work item that spawned it
│   └── seed_provenance            REQUIRED   why this seed exists (entity, locator, query)
├── capability binding
│   ├── source_id                  REQUIRED
│   ├── runtime_ref                REQUIRED   executor family + pinned version
│   ├── capability_requirements[]  REQUIRED   typed capability ids with version constraints
│   ├── query_ref                  REQUIRED   the query object, not a bare string
│   └── query_parameters           REQUIRED   typed, with units and defaults resolved
├── authorisation
│   ├── target_scope               REQUIRED   typed scope, not free text
│   ├── access_mode                REQUIRED   public | authorised | licensed | internal
│   ├── policy_snapshot_ref        REQUIRED   the policy version in force at plan time
│   └── credential_ref             OPTIONAL   a vault pointer; never the secret
├── scope filters
│   ├── temporal                   OPTIONAL   valid-time window + knowledge cutoff
│   ├── geographic                 OPTIONAL   CRS-aware
│   ├── requested_depth            OPTIONAL   historical depth, when meaningful
│   └── exclusion_refs[]           OPTIONAL   explicit exclusions
├── budget
│   ├── max_bytes                  REQUIRED
│   ├── max_records                REQUIRED
│   ├── deadline                   REQUIRED
│   ├── request_budget             REQUIRED   number of network/API requests
│   └── compute_budget             OPTIONAL   for heavy runtimes
├── execution
│   ├── retry_policy_ref           REQUIRED
│   ├── idempotency_key            REQUIRED
│   ├── checkpoint_ref             OPTIONAL   cursor / offset / continuation token
│   ├── scheduled_at               OPTIONAL
│   └── priority                   REQUIRED   from the action's component vector
└── acceptance
    ├── expected_result_kinds[]    REQUIRED   what would count as an answer
    └── acceptance_criteria[]      REQUIRED   predicates, not prose
```

---

## Normative rules

### R1 — No default consent

Every authorisation field is required. A missing `policy_snapshot_ref` is not filled from the
current policy: the task is rejected, because a plan made under policy A must not execute under
policy B without an explicit rebase.

### R2 — Secrets are references

`credential_ref` is a vault pointer. A secret in an event payload, a query log or a donor manifest is
a contract violation, and the check for it is mechanical: pattern-scan the serialised task at
enqueue time in tests.

### R3 — Scope is typed and round-trips

`target_scope` and the filters are structured objects with declared semantics — not "the string the
planner produced". A scope that cannot be compared against an observation's scope cannot be used to
decide coverage, and coverage is the whole point.

### R4 — Budgets are enforced, not advisory

The frontier and the dispatcher enforce every budget field. An action that would exceed a budget is
not dispatched; it is recorded as budget-blocked, which is a legitimate terminal outcome and appears
in the stop report.

### R5 — Idempotency is carried, not computed downstream

The key travels with the task from plan to publication. A recomputed key at the sink is a different
key, and the replay-inflation guarantee collapses.

### R6 — Acceptance criteria are predicates

`acceptance_criteria[]` are machine-evaluable predicates over the expected result kinds. Prose
cannot be evaluated, and an unevaluable criterion is how a task "completes" without answering
anything.

### R7 — Cancellation and supersession are explicit

A task may be cancelled or superseded. Both are recorded with a reason and an actor. Deleting a row
is not cancellation.

### R8 — One task, one authorisation envelope

A task that would need two different access modes or two different policy snapshots is two tasks.
Combining them makes the authorisation decision untraceable.

---

## Prohibitions

- A task whose `source_id` is resolved at execution time from configuration globals.
- A task carrying a raw credential, cookie or session token.
- A task with `max_bytes` or `deadline` set to "unlimited".
- A task whose acceptance criteria are empty ("we'll know it when we see it").
- Reusing a completed task id for a new fetch.

---

## Tests

| Test | Asserts |
|---|---|
| `tests/contract/test_acquisition_task.py::test_secret_rejected` | R2 |
| `tests/contract/test_acquisition_task.py::test_missing_policy_snapshot_rejected` | R1 |
| `tests/integration/test_budget_enforcement.py` | R4 |
| `tests/replay/test_idempotency_key_threading.py` | R5 |
| `tests/contract/test_acquisition_task.py::test_acceptance_is_predicate` | R6 |
