# ADR-030-02 — Observation membership commits through the existing outbox; there is no second consistency mechanism

- **Status**: Accepted
- **Date**: 2026-10-17
- **Feature**: `030-global-platform-upgrade`
- **Implements**: T017
- **Cites**: FR-063, FR-062, Constitution P10, ADR-0027, ADR-0021
- **Interacts with**: ADR-030-12 (observation placement), which decides what `UNPLACED` *means*; this
  ADR decides the mechanism that persists it

## Context

FR-063 states the problem precisely and then forbids the easy answer:

> The platform MUST NOT report an observation as placed when its membership write failed; it MUST use
> a defensible consistency strategy (single transaction, or transactional outbox plus idempotent state
> machine with explicit pending placement and reconciliation) and MUST NOT assume a distributed atomic
> transaction across object storage, database and broker without a mechanism.
> — `spec.md:389-392`

The last clause is the whole difficulty. An observation is a raw blob in object storage. Its
membership is a row in PostgreSQL. Its availability is a broker publication. **No mechanism exists
that commits all three atomically**, and the ADR would be dishonest if it implied one did. So the
question is not "how do we make it atomic" but "given that we cannot, which of the two permitted
strategies is already half-built here".

**[MEASURED]** One of them is not merely available, it is already running:

- `apps/control-plane/db/materialization_outbox.py:14` — `class SqlMaterializationOutbox`, holding an
  `AsyncSession`. Its `enqueue()` (`:31`) is **idempotent by construction**: it selects on
  `(tenant_id, run_id)` first (`:34-39`) and returns the existing row if one is there
  (`:41`), so a retried enqueue cannot duplicate. `outbox_id()` (`:19`) is a deterministic
  `sha256(f"{tenant_id}\x00{run_id}")`, so the identity is stable across processes. `claim_ready()`
  (`:53`) selects on `status IN ("PENDING", "FAILED")` ordered by `available_at, created_at`, with
  `.with_for_update(skip_locked=True)` — a correct multi-worker claim, not a naive `SELECT`.
- `apps/control-plane/services/materialization_outbox_relay.py:10` —
  `relay_materialization_outbox(*, limit=20)`, and `:46` `run_outbox_relay_forever(*,
  interval_seconds=5.0)`. The drain loop exists.
- `apps/control-plane/services/temporal_materialization_dispatch.py` — the workflow side.
- A durable DLQ exists beside it: `apps/shared/events/dlq.py`, `dlq_durable.py`, surfaced at
  `apps/control-plane/api/routes/quarantine.py`.

So the outbox, the relay, the retry status, and the dead-letter surface are all real, tested paths.
`research.md §2.2` records that idempotent consumers already have coverage at
`apps/shared/tests/unit/test_idempotent_consumer.py`.

**[MEASURED]** What is missing is not the mechanism. It is the routing. Observation membership is not
yet written through the outbox that exists, and nothing today records the *pending placement* state
FR-063 requires between "membership intended" and "membership committed". `ADR-030-02` therefore
decides the destination; the wiring is T051 and the placement semantics are ADR-030-12.

## Decision

**D1 — The outbox is the only consistency mechanism.** Observation membership, obligation/action/
decision publication and the resulting context revision are committed through
`SqlMaterializationOutbox` and drained by `relay_materialization_outbox`. A second queue, a second
relay, or a second publication path for the same event is refused at review.

**D2 — Placement is a state machine with an explicit pending phase, not a boolean.** Membership moves
`PENDING_PLACEMENT → PLACED` or `PENDING_PLACEMENT → UNPLACED`. Both are durable, both are
queryable, and the transition is what the reconciliation job reads. There is no window in which an
observation is reported placed while its membership write is still outstanding.

**D3 — Reported placement is a read of committed state, never an acknowledgement of intent.** The API
answers "placed" only from a committed membership row. A caller may observe `PENDING_PLACEMENT` or
`UNPLACED`; it may never observe a hopeful answer. This is FR-063's first sentence and it is the
constraint the whole design exists to satisfy.

**D4 — Object storage, database and broker are never assumed to commit together.** The outbox gives
at-least-once delivery with idempotent consumption. Every consumer is keyed by `event_id` /
`task_id` / `observation_id` / projection offset (constitution, Additional Constraints → Idempotency).
A redelivery is a no-op, not a second placement.

**D5 — Exhausted retries land in the existing DLQ, not in a discard.** A failed placement is
replayable from `api/routes/quarantine.py`. A rejected candidate is never auto-deleted.

**D6 — The outbox's idempotency keys are reused, not re-derived.** `outbox_id(tenant_id, run_id)`
remains the row identity. This ADR does not introduce a second key scheme, because two key schemes
over one queue is how one event gets processed twice.

## Why not the alternatives

**A — Single transaction spanning object storage, PostgreSQL and the broker.** Rejected, and not on
preference: no such transaction exists across those three systems, and `research.md §2.2` states the
prohibition verbatim. Designing one would mean inventing distributed-transaction machinery for a
problem the outbox pattern already solves in this codebase.

**B — Build a second, observation-specific consistency mechanism.** Rejected. This is the specific
failure the task names. The gap is that membership is not routed through the mechanism that exists,
not that the mechanism is absent. A second path would make the platform's consistency story
unauditable — you could no longer answer "how many places can an observation be published from?"
without reading both implementations, which is precisely the question `research.md §2.2` says the
specification forbids assuming the answer to.

**C — Write membership directly, then publish.** Rejected. This is the lost-update window FR-063
names: a crash between the row write and the publication leaves a durable observation that no
consumer will ever hear about, and nothing records it as missing. That failure is invisible until
someone notices a coverage gap months later.

**D — Move observation membership into Temporal and let the workflow own it.** Rejected. Temporal
already dispatches *from* the outbox
(`services/temporal_materialization_dispatch.py`); putting the commit there as well would make the
workflow the source of truth for a row whose atomicity with the revision advance is already solved in
`SqlMaterializationOutbox`. It also trades a transaction you have for a retry semantics you would
have to build.

**E — Declare the existing outbox sufficient and close this ADR as a no-op.** Rejected. The existing
outbox carries *materialization launches*, keyed by `(tenant_id, run_id, entity_id, workflow_id)`. It
has no membership state and no pending-placement phase. Deciding that no decision is needed would
leave D2 unimplemented by silence.

## Consequences

**Positive**

- One audit surface for consistency. "How can an observation be placed or reported?" has one answer.
- `claim_ready(skip_locked=True)` plus the deterministic `outbox_id` means horizontal relay scaling
  needs no new locking design.
- D2 turns "we lost an observation" from an unrecoverable silent loss into a queryable state that
  the reconciliation pass can find.

**Costs, accepted**

- The pending phase is a real state that every consumer must learn to handle, including "report the
  pending state honestly" paths. This is work, not a free win.
- At-least-once means every new consumer of this outbox inherits the idempotency obligation. Accepted:
  that obligation is cheaper than the alternative, which is a distributed transaction nobody can
  deliver.
- The outbox's `enqueue()` commits inside its own session (`materialization_outbox.py:50`). It
  therefore does not, on its own, give atomicity with the caller's surrounding transaction. Membership
  must be enqueued **within** the caller's transaction for D2 to hold; this is a wiring obligation
  that lands with T051 and is a known sharp edge, recorded here rather than discovered later.

**Not changed**

- ADR-0027: PostgreSQL remains the single authority.
- The DLQ, quarantine route and idempotent-consumer pattern are untouched.
- ADR-0021's single-sequencer property is unaffected; the outbox does not assign event order.

## Verification

- [ ] An observation whose membership write fails is never reported as placed (FR-063).
- [ ] Membership is observable in `PENDING_PLACEMENT` before it is `PLACED`, from committed state.
- [ ] `relay_materialization_outbox` is the only drain path; a repository search finds no second
      relay for observation membership.
- [ ] Replaying a batch twice produces identical membership and exactly one revision.
- [ ] `outbox_id` is stable across processes for the same `(tenant_id, run_id)`.
- [ ] A permanently failed placement is replayable from `api/routes/quarantine.py` and deletes no
      candidate.
- [ ] Concurrent relays do not double-claim (`claim_ready` holds `FOR UPDATE SKIP LOCKED`).

## Open

- **The membership wiring does not exist yet.** `T051` owns routing obligation/action/decision
  publication through `apps/control-plane/db/materialization_outbox.py`, and T052 the end-to-end
  assertion. Neither is executed. This ADR fixes the destination and the state machine; it does not
  claim the path is built.