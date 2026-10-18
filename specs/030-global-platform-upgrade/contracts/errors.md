# Contract 07 — Error Codes

**Feature**: `030-global-platform-upgrade`
**Governs**: every machine-readable failure surface — API, events, operator results, replay.
**Enforces**: FR-047, FR-090, FR-096, FR-100.

---

## Three categories, never conflated

| Category | Retry? | Client behaviour | Examples |
|---|---|---|---|
| **Expected negative** | No | Report the state; do not retry | `NO_RESULT`, `POLICY_BLOCKED`, `CAPABILITY_UNAVAILABLE`, `UNSUPPORTED_QUERY` |
| **Retryable infrastructure** | Yes, bounded | Backoff within budget | `SOURCE_UNAVAILABLE`, `TIMEOUT`, `TRANSIENT_INFRA`, `RESOURCE_CAP` |
| **Software defect** | No | Fail loudly; do not degrade silently | `REPLAY_MISMATCH`, `SCHEMA_MISMATCH`, `OPERATOR_OUTPUT_INVALID`, `STALE_CONTEXT_REVISION` |

**A degraded-but-valid answer is never returned where a defect occurred.** A missing dependency must
produce an explicit unsupported/degraded status, never silent success.

---

## Codes

### Context and revision

| Code | Meaning |
|---|---|
| `UNKNOWN_CONTEXT` | No such context in this tenant |
| `STALE_CONTEXT_REVISION` | `expected_revision` is behind the head — **re-evaluate, do not overwrite** |
| `REVISION_CONFLICT` | Concurrent write; recompute the proposal against current head |
| `REPLAY_MISMATCH` | Recomputed digest ≠ recorded digest — **fail loudly, both fingerprints** |
| `DECISION_RECORD_MISSING` | State change attempted without a decision |

### Policy, scope and budget

| Code | Meaning |
|---|---|
| `POLICY_BLOCKED` | Denied by source policy or scope |
| `SCOPE_VIOLATION` | Outside the investigation's scope |
| `BUDGET_EXHAUSTED` | A budget level is exhausted; the level is named |
| `APPROVAL_REQUIRED` | Proposing is permitted; executing is not until approved |
| `TENANT_SCOPE_VIOLATION` | Cross-tenant reference — **refused without confirming existence** |

### Capability and source

| Code | Meaning |
|---|---|
| `CAPABILITY_UNAVAILABLE` | No operator provides the required capability |
| `UNSUPPORTED_QUERY` | Not representable by this operator/source |
| `SOURCE_UNAVAILABLE` | Transport/source failure |
| `RATE_LIMITED` | Throttled; retry after backoff |
| `DETECTION_POWER_UNKNOWN` | Absence claims are **informational only** |

### Placement

| Code | Meaning |
|---|---|
| `NO_MEMBERSHIP` | Observation persisted but unplaced — **stays unplaced, opens a gap** |
| `NO_ANCHOR` | The model requires an anchor and none exists — **no nearest-neighbour guess** |
| `PLACEMENT_PENDING` | Membership resolution is asynchronous; not yet counted as placed |

### Projection and operator

| Code | Meaning |
|---|---|
| `PROJECTION_STALE` | Older than the caller's freshness contract |
| `PROJECTION_FAILED` | Build failed; source unaffected |
| `OPERATOR_TIMEOUT` | Exceeded its declared time budget |
| `OPERATOR_OUTPUT_INVALID` | Output failed contract validation |
| `SCHEMA_INCOMPATIBLE` | Wire schema version mismatch without a compatibility path |
| `CAPACITY_GAP` | Approximate capability used; `substitution_attempted` must be false in the gap record |

### Evidence and provenance

| Code | Meaning |
|---|---|
| `SPAN_UNRESOLVABLE` | A declared span does not resolve against the stored blob |
| `SPAN_SEMANTICS_MISMATCH` | Two spans with incompatible semantics versions — **refuse, do not convert** |
| `PROVENANCE_INCOMPLETE` | Result has no complete chain — **must render as partial/unsupported** |
| `IMMUTABLE_VIOLATION` | An attempt to modify a raw object — **release blocker** |

### Identity

| Code | Meaning |
|---|---|
| `RESOLUTION_DEFERRAL` | Ambiguous pair deferred to review |
| `RESOLUTION_REJECTED` | Gate refused the merge |
| `UNVERIFIED_DONOR` | Upstream identity or licence unestablished — **integration is refused** |
| `LICENCE_BLOCKED` | Licence terms forbid the intended use |

---

## Rules

### R1 — Clients parse codes, not strings

Every failure carries a code. Clients MUST NOT parse human-readable error text.

### R2 — No distinguishable cross-tenant signal

A cross-tenant reference returns the same response shape as a genuinely absent object. Confirmed
existence through a different error path is an information leak (FR-090).

### R3 — No secrets or raw content in errors

Errors carry identifiers, codes and reasons. Raw payloads, credentials and source text are never
included (FR-096).

### R4 — Absence is stated, not implied

An empty result set is never returned bare. The response states **status + coverage + provenance +
limitations** (spec §19.4). A bare `[]` does not distinguish: no candidates / provider unavailable /
query unsupported / budget truncated / policy blocked.

### R5 — `BLOCKED` names its blocker

Not "blocked". It names **which** capability, policy, approval or budget, so the obligation can be
re-opened when the condition clears.

---

## Validation

| Check | On failure |
|---|---|
| Every failure carries a code from this table | reject |
| Same response shape for cross-tenant and genuinely-absent | reject — leak |
| Raw content or secret in an error payload | **release blocker** |
| Bare `[]` returned without status/coverage/provenance/limitations | reject |
| `blocked` without a named blocker | reject |
| Expected-negative classified as retryable, or vice versa | reject |
| `DETECTION_POWER_UNKNOWN` response presented as absence | **release blocker** |
| `IMMUTABLE_VIOLATION` raised | **release blocker** |