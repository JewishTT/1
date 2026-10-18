# Contract 05 — ContextRevision, Atomicity, Replay, Concurrency

**Feature**: `030-global-platform-upgrade`
**Governs**: durable investigation state.
**Enforces**: FR-032, FR-033, FR-034, FR-065, §2.1, §2.10, P8, P10.

---

## ContextRevision

```text
ContextRevision
├── context_id
├── revision_number        monotonic, PER-CONTEXT
├── revision_id            content-derived
├── parent_revision_id / supersedes
├── input_fingerprint
│     = hash(prior_revision_id, event_ids[], pinned_heads[], rule_versions[], parameters[])
├── changeset + durable refs to full change records
├── state_heads            { obligations, hypotheses, contradictions, unknowns }
├── observed_heads         { projections[], invariants[], worldlines[] }
├── rule_bundle_fingerprint, operator_fingerprints[]
├── status, warnings[], degradation_reason
├── replay_manifest
└── integrity_digest       over canonical serialization
```

---

## Rules

### R1 — Revision sequence is per-context

A context's revision 12 and an entity invariant's revision 12 are unrelated numbers. Conflating them
is how a context silently "adopts" an identity revision.

### R2 — Content-derived ids are stable

The same canonical content yields the same `revision_id`. Arrival order and wall-clock do not enter
`integrity_digest` unless the timestamp is semantically part of the state. Operational `created_at` is
stored **separately**.

### R3 — A no-op does not mint a semantic revision

A genuinely no-op input MAY skip a new revision. Its delivery/processing record remains observable
whenever idempotency investigation requires it. Fabricating a revision to look busy is a defect.

### R4 — Revision + DecisionRecord are atomic [DECIDED §2.1]

> **[MEASURED]** `PostgresContextGraphStore.apply(tenant_id, transaction) → DecisionRecord`
> (`apps/control-plane/context_engine/context_graph_store.py:80`) already makes the decision record
> and the graph mutation one transaction. This contract adopts that as the required pattern.

If outbox publication is required, the outbox row is written **in the same transaction**. On
rollback, no partial revision is queryable as current.

### R5 — Optimistic concurrency

Every write command carries `expected_revision` (a compare-and-swap token). If state has advanced,
the write is **rejected for re-evaluation** — never last-write-wins. A branch merge records which
revision won and why.

### R6 — Durable mode cannot be faked

`ContextEngine(require_durable=True)` already refuses a memory store **[MEASURED, `engine.py:490`]**.
This is the required pattern: a volatile store MUST NOT be selectable in a mode declared durable
(FR-034).

---

## Replay

Two declared modes (contract 01 §R2):

| Boundary | Mode | Rule |
|---|---|---|
| Invariant reduction | `deterministic` | Incremental fold and full rebuild MUST agree on the canonical digest for the same stream |
| Context projection | `deterministic` | Same snapshot + same rule versions ⇒ same delta |
| Any model-hosted operator | `result_replay` | The exact result is preserved; recomputation is not claimed |

### R7 — Incremental and rebuild paths must agree

This is the single most important existing behaviour in the repository, and it must not regress.

> **[MEASURED]** `InvariantReducer` advances its revision counter **once per `reduce()` call**, not
> once per event. A three-event stream folded in one batch lands at revision 1; folded incrementally
> it reaches revision 3. Because the revision is inside the invariant identity, **the two produce
> different digests over identical evidence**.
>
> The mitigation is `restore(stream, history=)`, which rebuilds at the recorded position.
> `test_a_cold_fold_is_not_equivalent_to_a_restore` pins this deliberately rather than hiding it.

### R8 — Replay mismatch fails loudly

On mismatch, report **both** input and output fingerprints and stop. Never accept the newer output as
equivalent.

### R9 — Replay manifest

Every deterministic boundary records: input event ids and canonical order, source stream head,
operator/rule versions, deterministic parameters, semantic profiles, prior state revision, output
digest, affected object ids, and any known nondeterminism with its preserved artifact.

---

## Idempotency

### R10 — At-least-once delivery, once-only semantics

Every consumer deduplicates by event / observation / task id and checks the canonical digest before
mutating.

Duplicate delivery MUST NOT:

- increment a revision
- increment evidence independence
- increment coverage
- pollute cost-benefit learning
- duplicate a decision record

### R11 — New evidence supersedes; it never rewrites

A late event producing a different canonical digest creates a **new** revision. It does not mutate a
previously published one. Findings derived from an older snapshot stay retrievable and are marked
superseded or stale — never overwritten (FR-023).

---

## Outbox

> **[MEASURED]** An outbox already exists: `apps/control-plane/db/materialization_outbox.py`,
> `services/materialization_outbox_relay.py`, `services/temporal_materialization_dispatch.py`,
> with migrations `014_temporal_materialization.py` and `015_worldline_reconstruction.py`.
> A durable DLQ exists at `apps/shared/events/dlq.py` / `dlq_durable.py`.

### R12 — The transaction boundary

```text
1. Write the raw blob immutably  (or verify it exists by content digest)
2. In ONE database transaction:
     persist observation metadata
     persist source/observation identity
     persist membership placement state  (or explicit PENDING_PLACEMENT)
     persist the idempotency record
     persist the outbox event
3. Commit
4. Relay publishes at-least-once; consumers are idempotent
```

### R13 — Membership consistency

**A context MUST NOT report an observation as placed when its membership write did not commit**
(FR-063). Two permitted strategies:

- single transaction, where the same database holds both; or
- transactional outbox + idempotent state machine, with **explicit** pending/unplaced state and a
  reconciler.

**A raw blob written without a DB commit is an allowed orphan**, garbage-collectable under the
retention policy. **A context claiming a failed membership committed is prohibited.**

### R14 — The reconciler never invents a placement

It finds orphan blobs, pending observations and delayed outbox rows. It does not attach an
unplaced observation to a convenient neighbour. Unplaced observations stay visible, do not count
toward coverage, and open an explicit gap (FR-062).

### R15 — No assumed distributed transaction

Object storage + database + broker do **not** participate in one atomic transaction. Retries and a
reconciliation job are the mechanism. Pretending otherwise is prohibited.

---

## Validation

| Check | On failure |
|---|---|
| `parent_revision_id` exists and forms a chain | reject |
| `input_fingerprint` recomputes from its declared parts | reject |
| `integrity_digest` recomputes over canonical serialization | reject |
| State change without a same-transaction `DecisionRecord` | reject |
| Stale `expected_revision` on write | **reject** — never overwrite |
| Memory store selected under `require_durable=True` | refuse at construction |
| Incremental digest ≠ rebuild digest for the same stream | **fail loudly** with both fingerprints |
| Duplicate delivery incremented any counter | reject |
| `unplaced` observation counted toward coverage | reject |
| Replayed event rewrote a published revision | reject |