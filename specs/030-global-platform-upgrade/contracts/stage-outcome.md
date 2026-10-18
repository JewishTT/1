# Contract 03 — Stage Outcomes and Failure Classification

**Feature**: `030-global-platform-upgrade`
**Governs**: every execution result of every stage.
**Enforces**: FR-047, FR-068, FR-069, FR-100.

---

## The nine outcomes

| Status | Meaning | Retryable | Counts as progress? | May satisfy an obligation? |
|---|---|---|---|---|
| `succeeded` | Completed fully | n/a | Only if it produced new independent evidence | **Only** if its acceptance criteria are met |
| `partial` | Completed on a bounded subset | **Yes**, resumable | Partially | **Only** for the criteria the partial output satisfies |
| `no_result` | Executed successfully, zero matches | No — it succeeded | **No** | Only as `QUALIFIED_ABSENCE` **with declared detection power** |
| `unsupported` | This operator/source cannot represent the request | **No** | No | No |
| `blocked` | Denied by policy, missing capability, approval or budget | **No**, until the blocker clears | No | No |
| `failed` | Transient or permanent operator error | Depends on `error_code` | No | No |
| `quarantined` | Poison or policy-held record, retained for replay eligibility | No, until replayed | No | No |
| `abstained` | A model/agent declined to answer | No | No | No |
| `no_change` | Executed, produced no state delta | n/a | **No — this is the suppression signal** | No |

---

## The distinctions that must never collapse

These five pairs are conflated constantly and each collapse is a correctness defect:

| These | Are not the same because |
|---|---|
| `no_result` ≠ `unsupported` | The query ran and matched nothing **vs** the system could not express the query |
| `no_result` ≠ `qualified_absence` | Absence requires a declared universe **and** declared detection power |
| `failed` ≠ `succeeded` with empty output | An error is not a document with zero content |
| `partial` ≠ `succeeded` | Partial omits scope; that scope must travel with the result |
| `no_change` ≠ `succeeded` | Zero delta is the trigger for action memory and suppression |

> A parser that cannot process a format returns `unsupported`. It does not return an empty document
> with `status = succeeded`.

---

## Failure classes — finer than `status`

`status` says what happened. `error_code` says **why**, and `error_code` is what drives retry.

| Class | Retry | Examples |
|---|---|---|
| `EXPECTED_NO_RESULT` | No | query matched nothing |
| `SOURCE_UNAVAILABLE` | Yes, bounded | transport failure, 5xx, DNS |
| `RATE_LIMITED` | Yes, after backoff | 429, politeness delay |
| `POLICY_BLOCKED` | **No** | scope, legal, consent, approval |
| `CAPABILITY_UNAVAILABLE` | **No** | no operator supports this |
| `UNSUPPORTED_QUERY` | **No** | query shape not representable here |
| `MALFORMED_INPUT` | **No** | corrupt document, bad encoding |
| `PARTIAL_OUTPUT` | Yes, resumable | budget/limit bound the run |
| `TIMEOUT` | Yes, bounded | — |
| `RESOURCE_CAP` | Yes, bounded | memory, CPU, file size, archive depth |
| `TRANSIENT_INFRA` | Yes | dependency down, broker unavailable |
| `PERMANENT_OPERATOR_ERROR` | **No** | — |
| `SCHEMA_MISMATCH` | **No** | output failed contract validation |
| `ADMISSION_REJECTED` | **No** | candidate failed the gate |
| `QUARANTINED` | Only via replay | poison record |
| `REPLAY_MISMATCH` | **No — fails loudly** | recomputed digest ≠ recorded digest |
| `HUMAN_REVIEW_REQUIRED` | **No** | above ambiguity threshold |

### Retry policy [FR-068]

Retry budgets exist at **five** levels: task, source, investigation, tenant, global. Backoff is
exponential **with jitter**. Circuit breaking opens per source on sustained failure. Rate windows
apply per source. Exhausting a budget yields `blocked` with the exhausted level named — **never** a
silent success and **never** a stop reason for the investigation.

---

## Quarantine envelope [FR-069]

```text
QuarantineRecord
├── record_ref                 payload pointer, never inline raw content
├── schema_version             + the expected version
├── failure_class              from the table above
├── error_code, first_attempt_at, last_attempt_at, attempt_count
├── replay_eligible            bool + reason when false
├── redaction_policy           what may be shown, to whom
└── retention                  per the retention class (data-model §2)
```

**Replay uses the same logical idempotency semantics** as the original path (FR-065). A quarantined
record is **retained for re-evaluation** unless the retention policy dictates otherwise — the
failure is preserved, not the attempt.

---

## Suppression [FR-045]

`no_change` is the signal that feeds action memory. A canonical action fingerprint
(+ scope, temporal range, parameters, operator version) that returns `no_change` is **suppressed**
until a **declared** condition changes:

- new evidence arrived
- source content changed
- the stale interval elapsed
- the source became available
- the parser or model version changed
- parameters changed
- an analyst overrode, with a reason
- a hypothesis test now requires it

Failure and no-result are **different memory states**. A source that errored three times is not
suppressed as unproductive — it is broken, and that is a different record.

---

## Rules

1. Every stage returns exactly one `status` and, when applicable, one `error_code`.
2. **`no_result` carries the coverage statement that produced it.** If detection power is unknown,
   the result serialises as `SEARCHED_NO_RESULT / INFORMATIONAL_ONLY`, which is a distinct
   epistemic state — not a flavour of `no_result` (FR-014).
3. `partial` carries what was processed, what was not, the binding limit, and whether it resumes.
4. A status never implies a progress delta. Progress is computed separately (§6 of the source spec).
5. A stage that returns `blocked` MUST name the blocker: which capability, which policy, which
   approval, which budget (FR-038).
6. `replay_mismatch` **fails loudly** with both fingerprints. It is never resolved by accepting the
   newer output.

---

## Validation

| Check | On failure |
|---|---|
| Exactly one status; status ∈ the nine values | reject |
| `error_code` ∈ the class table | reject |
| Retryable class + exhausted budget ⇒ `blocked` with the level named | reject |
| `partial` ⇒ `missingness` populated with the binding limit | reject |
| `no_result` ⇒ coverage/detection statement present | reject |
| `blocked` ⇒ `gap_reason` non-empty | reject |
| `unsupported` ⇒ `CapacityGap.substitution_attempted = false` | reject |