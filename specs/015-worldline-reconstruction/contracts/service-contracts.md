# Service Contracts: Worldline Reconstruction

**Feature**: [015-worldline-reconstruction](../spec.md) | **Date**: 2026-09-25

Interface-level contracts for the components introduced or changed by this feature.
These are the boundaries the constitution requires (V. Plugability by contract): no
vendor-specific types cross into domain logic, and each contract is independently
testable against an in-memory implementation.

---

## `SourceQueryPlanner`

Derives an ordered, deduplicated, deterministic set of executable source queries from an
entity search surface. Pure: no network, no clock, no database.

```python
class SourceQueryPlanner(Protocol):
    def plan(
        self, *,
        tenant_id: str,
        entity_id: str,
        surface: EntitySearchSurface,
        providers: tuple[RouteProvider, ...],
    ) -> SourceQuerySet: ...
```

| Member | Type | Contract |
| --- | --- | --- |
| `entity_id` | `str` | owning entity |
| `queries` | `tuple[SourceQuery, ...]` | ordered by `ordinal`; ordinals are contiguous from 0 |
| `executable` | `tuple[SourceQuery, ...]` | subset with `executable is True` |
| `unsupported` | `tuple[SourceQuery, ...]` | subset with `executable is False`, each carrying `unsupported_reason` |
| `identity_fingerprint` | `str` | sha256 over the canonicalized identity |
| `is_complete` | `bool` | true when no route is unsupported |

**Guarantees**

- Deterministic: the same identity yields a byte-identical set regardless of the
  ordering of the identity mapping (FR-002).
- Total: every dimension of the surface is either executable or explicitly unsupported
  with a reason. No dimension is silently dropped (FR-004).
- Deduplicated: two dimensions normalizing to the same route value produce one
  `SourceQuery` whose `origin_refs` lists both (FR-003).
- An identity with no executable route yields an empty `executable` tuple rather than
  raising at plan time; the run fails later with `no_executable_query` (AS-008).

**Errors**: `NormalizationError` for a value that cannot be normalized at all; the
planner converts it into an unsupported query rather than propagating.

**Satisfies**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-006

---

## `FrontierStore`

Owns the durable, per-entity, run-independent set of unexhausted work.

```python
class FrontierStore(Protocol):
    async def ensure_entries(
        self, *, tenant_id: str, entity_id: str, query_set: SourceQuerySet,
        partitions: Sequence[str],
    ) -> int: ...  # number of newly created entries

    async def claim_batch(
        self, *, tenant_id: str, entity_id: str, budget: FrontierBudget, owner: str,
    ) -> tuple[FrontierEntry, ...]: ...

    async def mark_exhausted(self, entry: FrontierEntry, *, reason: ExhaustionReason) -> None: ...
    async def mark_no_progress(self, entry: FrontierEntry) -> None: ...
    async def mark_retryable(self, entry: FrontierEntry, reason: str) -> None: ...
    async def mark_failed(self, entry: FrontierEntry, reason: str) -> None: ...
    async def extend(self, *, tenant_id: str, entity_id: str, query_set: SourceQuerySet,
                     partitions: Sequence[str]) -> int: ...

    async def counts(self, *, tenant_id: str, entity_id: str) -> FrontierCounts: ...
    async def failing(self, *, tenant_id: str, entity_id: str) -> tuple[FrontierEntry, ...]: ...
    async def is_terminal(self, *, tenant_id: str, entity_id: str) -> bool: ...
```

`FrontierBudget` carries `max_partitions`, `max_pages` and `max_captures` for **one
invocation only**. It selects work; it never defines it.

**Guarantees**

- `ensure_entries` is idempotent and never re-opens a terminal entry (FR-013).
- `claim_batch` returns entries in a deterministic order and leaves unselected entries
  untouched and claimable (FR-008).
- Only `mark_exhausted(reason=confirmed_empty)` asserts that a partition was proven
  empty. `mark_no_progress` terminates the entry without that assertion (FR-009, FR-012).

---

## `ObservationWriter`

Writes the observation level. Always writes, including for captures that yield no
admitted claim.

```python
class ObservationWriter(Protocol):
    async def write(
        self, *, tenant_id: str, entity_id: str, capture: InterpretedCapture,
    ) -> WrittenObservation: ...
```

**Guarantees**

- Idempotent on `(tenant_id, observation_id)`; a replayed capture does not duplicate the
  observation (FR-016).
- Carries refs only; raw bytes are addressed by `evidence_ref` into the content-addressed
  store and never embedded in the payload (constitution I-5, FR-020).
- Records untrustworthy captures (revisit, truncated, digest mismatch) with explicit
  reasons rather than dropping them (AS-014).

**Satisfies**: FR-016, FR-019, FR-020

---

## `AssertionProjector`

Turns extraction output plus admission decisions into stream records, and gates what may
become a temporal event.

```python
class AssertionProjector(Protocol):
    def project(
        self, *, tenant_id: str, entity_id: str, capture: InterpretedCapture,
    ) -> ProjectionResult: ...

    def project_events(
        self, *, tenant_id: str, entity_id: str, assertions: Sequence[AssertionRecord],
        projection_generation: int,
    ) -> tuple[TemporalEvent, ...]: ...
```

`ProjectionResult` carries `observations`, `assertions`, `events` and
`admission_counts`.

**Guarantees**

- One `entity.assertion` row per extracted claim, **regardless of decision**, each
  carrying its decision, reason codes, score vector and policy version (FR-018).
- `events` contains only assertions whose decision is `ACCEPT_NEW` or `ACCEPT_EXISTING`.
  A rejected, deferred or quarantined claim yields no event, no relation and no state
  transition (FR-017, SC-005).
- `admission_counts` reports accepted, rejected, deferred and quarantined totals and is
  carried into publication (FR-024).
- An observation yielding zero accepted assertions produces an observation, zero events,
  and an explicitly empty worldline interval (FR-019).
- Output is order-independent: the same assertion set in any order yields identical
  events and fingerprints (FR-022).

**Satisfies**: FR-015, FR-016, FR-017, FR-018, FR-019, FR-021, FR-022, FR-023, FR-024

---

## `WorldlineBuilder`

Builds the assertion-level worldline and its relations.

```python
class WorldlineBuilder(Protocol):
    def build(
        self, *, tenant_id: str, entity_id: str, records: Sequence[StreamRecord],
        level: WorldlineLevel = WorldlineLevel.ASSERTION,
        require_evidence: bool = True,
        projection_generation: int | None = None,
        relation_budget: int | None = None,
    ) -> Worldline: ...
```

`WorldlineLevel` is `OBSERVATION`, `ASSERTION` or `BOTH`, and the built worldline labels
which level it represents (FR-021).

**Guarantees**

- Folds only `entity.assertion` records whose admission decision is accepted. A
  `cc.capture` record is never folded as an assertion-level event (FR-017, FR-021).
- Deterministic: input records are deduplicated and sorted by canonical order key before
  folding, so arrival order cannot change the result (FR-022, SC-006).
- Relations are derived by the indexed algorithm: a single sort yields
  `precedes`/`follows`, and a sweep line over interval starts yields `overlaps`
  (FR-034, FR-035).

---

## `ReconstructionRequestStore`

Owns the durable request that entity creation commits.

```python
class ReconstructionRequestStore(Protocol):
    async def enqueue(
        self, *, tenant_id: str, entity_id: str, identity: Mapping[str, str],
        workflow_id: str, run_id: str,
    ) -> ReconstructionRequest: ...

    async def claim(
        self, *, owner: str, limit: int, lease_seconds: int,
    ) -> tuple[ReconstructionRequest, ...]: ...

    async def mark_dispatched(self, request: ReconstructionRequest) -> None: ...
    async def mark_failed(self, request: ReconstructionRequest, reason: str, *,
                          backoff_seconds: int) -> None: ...
    async def get(self, *, tenant_id: str, entity_id: str) -> ReconstructionRequest | None: ...
```

**Guarantees**

- `enqueue` is idempotent per `(tenant_id, entity_id, identity_fingerprint)` for active
  states, enforced by a partial unique index rather than a check-then-insert
  (FR-017, FR-030).
- `claim` selects only rows with `available_at <= now()` plus rows whose `DISPATCHING`
  lease has expired, and stamps `lease_owner`/`lease_expires_at` (FR-027, FR-028).
- `mark_failed` schedules a future `available_at`; a later `claim` must not return the
  row before that instant (FR-028).
- Batch claiming returns per-row outcomes so a partial dispatch failure is never reported
  as a full success (FR-029).
- All operations are tenant-scoped (FR-039).

**Satisfies**: FR-026, FR-027, FR-028, FR-029, FR-030, FR-038, FR-039

---

## Cross-cutting contracts

| Concern | Contract | Requirement |
| --- | --- | --- |
| Sequence allocation | `EntityStreamRepository.append_many` allocates its sequence range via a single `INSERT ... ON CONFLICT DO UPDATE ... RETURNING` inside the append transaction. Clients never compute `max(sequence) + 1`. | FR-031, FR-032 |
| Crash recovery | Prepared output is committed to the run-scoped cursor before the append; a retry replays exactly that payload without re-fetching. | FR-011, FR-032 |
| Publication gate | Publication of a new generation requires `FrontierStore.is_terminal()`. Otherwise the run reports `partial`, names failing partitions, and the previous generation stays current with a staleness label. | FR-025, FR-040 |
| Entity creation | The entity row and the request row are written in one transaction. The request path performs no inline dispatch and spawns no in-process pipeline task. | FR-026 |
| Test/dev fallback | In-memory implementations exist for every store and are selected only by explicit configuration. They are never the production default. | FR-026 |

- Exceeding `relation_budget` produces explicit, labelled degradation naming what was not
  computed. It does not raise and does not silently truncate (FR-036).
- Handles at least 10,000 events without a size-related failure (FR-037, SC-007).

**Reference oracle**: the pre-existing pairwise derivation
(`derive_temporal_relations(..., max_events=...)`) is retained in the module and remains
callable. It is test-only surface: production never calls it, and equivalence against it
is asserted by test on shared inputs. It must not be deleted (FR-035).

**Errors**: `WorldlineError` only for genuinely invalid input (mismatched tenant, missing
required evidence when `require_evidence` is set). Size is no longer an error condition.

**Satisfies**: FR-015, FR-021, FR-022, FR-034, FR-035, FR-036, FR-037

- Every method is tenant-scoped; a cross-tenant identifier resolves to no rows (FR-039).
- `is_terminal` is the single authority for whether a run may publish (FR-025).

**Errors**: `ConcurrencyError` when a claimed entry is mutated by a non-owner.

**Satisfies**: FR-007, FR-008, FR-009, FR-010, FR-011, FR-012, FR-013, FR-014, FR-038, FR-039
