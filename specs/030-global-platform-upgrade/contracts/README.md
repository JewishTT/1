# Contracts Index

**Feature**: `030-global-platform-upgrade`

Contracts are the **stable boundary** between anything that produces evidence-derived results and
anything that records it. They are what makes donor integration safe: a third-party component is
acceptable when it speaks one of these and cannot write past it.

| # | Contract | Governs | Primary requirements |
|---|---|---|---|
| 01 | [`operator-result.md`](./operator-result.md) | Every operator, parser, extractor, matcher, analytics runner and donor adapter | FR-007, FR-047, FR-111 |
| 02 | [`evidence-span.md`](./evidence-span.md) | How a result points at the exact source bytes | FR-004, FR-006, SC-004 |
| 03 | [`stage-outcome.md`](./stage-outcome.md) | The nine typed execution outcomes and what each forbids | FR-047, FR-068 |
| 04 | [`obligation.md`](./obligation.md) | Obligations, actions, attempts, action memory, utility vector | FR-038…FR-045 |
| 05 | [`context-revision.md`](./context-revision.md) | Revision atomicity, decision records, optimistic concurrency | FR-032, FR-033, §2.1 |
| 06 | [`projection-manifest.md`](./projection-manifest.md) | Every projection's reproducibility record | FR-070, FR-071 |
| 07 | [`errors.md`](./errors.md) | Stable machine-readable codes; expected-negative vs retryable | FR-047, FR-100 |
| 08 | [`README.md`](./README.md) | Index, versioning policy, adoption rules | — |

---

## Universal rules — every contract obeys these

1. **Tenant scope is part of every key.** No contract admits a durable object without `tenant_id`,
   and no contract permits a cross-tenant reference.
2. **Logical identity ≠ content digest ≠ event identity ≠ revision sequence.** Four separate
   fields, never overloaded.
3. **Content-derived ids are stable** for equivalent canonical content. Wall-clock time, arrival
   order and mutable worker diagnostics are not hashed into deterministic identity unless
   semantically part of the object.
4. **Unknown is `null`, not a default.** A missing numeric estimate is `null`, never `0.0`. A
   missing timestamp is `null`, never `now()`.
5. **Every enum is closed for *our* workflow states and open for the *world*.** Our lifecycle states
   are enumerated. Entity types, relation predicates, attributes and source output kinds are **not**
   — an unknown value is preserved with a status marker.
6. **No contract may be satisfied by a fabricated value.** An unmeasured metric is `null` with the
   missing instrumentation named.
7. **Every status is distinguishable from every other status.** No value may mean "empty" across
   several meanings.

---

## Versioning policy

- Contract `version` is `MAJOR.MINOR`.
- **MAJOR** — a breaking change: removing a field, narrowing a type, changing the meaning of an
  existing value, or making an optional field required.
- **MINOR** — additive: a new optional field, a new enum value that existing consumers can
  ignore, a new contract.
- Consumers MUST tolerate unknown fields and MUST treat an **unknown enum value as
  "unrecognised — preserve, do not reject"** unless they are the designated authority for that
  vocabulary. This is the open-world rule applied to our own schemas.
- Wire schemas carry their own `output_schema_version`. A schema change requires a compatibility
  check; a version bump without a compatibility check fails CI.

---

## Adoption rule

A third-party capability (see `donor-matrix.md`) is integrated only when it produces and consumes
these contracts. It MUST NOT write canonical evidence, identity, investigation state or projection
stores directly — it emits an `OperatorResult`, and the platform's own services do the writing.

A capability that cannot produce one of these is a **methodology donor at best**: its algorithm may
be reimplemented against these contracts, but its output is not accepted into the platform, and the
manifest says `methodology_only` or `clean_room`.

---

## Existing substrate this reuses rather than replaces

**[MEASURED] 2026-10-14** — these already exist and are extended, not duplicated:

| Existing | Path | Used for |
|---|---|---|
| Outbox | `apps/control-plane/db/materialization_outbox.py` + `services/materialization_outbox_relay.py` | transactional publication (§`context-revision.md`) |
| Durable DLQ | `apps/shared/events/dlq.py`, `dlq_durable.py` | `errors.md` quarantine semantics |
| Idempotent consumer | `apps/shared/tests/unit/test_idempotent_consumer.py` | FR-065 |
| Quarantine route | `apps/control-plane/api/routes/quarantine.py` | operator replay surface |
| Isolation control | `apps/shared/isolation.py` | operator sandbox declarations |
| Durable-guard | `ContextEngine(require_durable=…)` refuses memory stores | FR-034 |
| Graph-store transaction | `PostgresContextGraphStore.apply(tenant, tx) → DecisionRecord` | revision/decision atomicity |