# Quickstart Validation: Worldline Reconstruction

**Feature**: `015-worldline-reconstruction`
**Status**: Post-plan validation/run guide. The test files, modules and endpoints named
below are the *required* implementation surface; this document validates them and does
not create them.

## Purpose

Prove the feature end to end without implementing it in this planning phase. The guide
turns every acceptance scenario and success criterion into a runnable check, separated by
what each check needs:

| Tier | Needs | Phases |
| --- | --- | --- |
| Offline | Python only. No network, no PostgreSQL, no archive. | 0 (static parts), 1, 2 |
| Infrastructure | Docker core stack (PostgreSQL, Redis, MinIO, Kafka, Temporal). | 0.4, 3, 4, 5, 7 |
| Live | Infrastructure **plus** real network reachability to the Common Crawl index and S3 origin. | 6 |

Phases 1, 2 and the static parts of Phase 0 must pass on a machine with no egress at all.
If they need the network, the determinism they claim is not actually being tested. Phase 6
is the only phase that requires the real archive, and it is marked live-only throughout.

Contract references:

- Requirement sources: [spec.md](./spec.md) - AS-001..AS-024, SC-001..SC-014, FR-001..FR-040
- Architecture, budget semantics and phase order: [plan.md](./plan.md)
- Test tiers, coverage matrix and oracle rules: [contracts/test-strategy.md](./contracts/test-strategy.md)

## Prerequisites

- Windows PowerShell 7+, Git, Python 3.11+, `uv`, Node.js 20+, `pnpm`, Docker Desktop.
- A clean checkout or isolated feature branch (`015-worldline-reconstruction`).
- Accepted ADRs for frontier storage, outbox leasing, sequence allocation and relation
  indexing, plus a new forward-only migration revision `015` - never an edit to the
  already-applied `014_temporal_materialization`.
- Local non-production credentials only; do not place real secrets in shell history or files.
- For Phase 6: a real target with genuine archived history (a domain that appears in
  Common Crawl across several crawls). A target present only in the newest crawl cannot
  demonstrate frontier exhaustion across partitions.
- For Phase 7: two tenant identities and viewer/analyst/admin roles.

Run all commands from the repository root unless a step says otherwise.

## Required test inventory

Every file below is new work owned by this feature unless marked *existing*.

| Test file | Tier | Proves |
| --- | --- | --- |
| `apps/acquisition/tests/unit/test_source_query_set.py` | offline | AS-006..AS-009, SC-001 |
| `apps/control-plane/tests/unit/test_reconstruction_frontier.py` | offline | AS-001..AS-005, AS-021, SC-002, SC-003, SC-004 |
| `apps/control-plane/tests/unit/test_assertion_materialization.py` | offline | AS-010..AS-014, SC-005, SC-006 |
| `apps/shared/tests/unit/domain/test_worldline_determinism.py` | offline | AS-013, SC-006 |
| `apps/shared/tests/unit/domain/test_worldline_relations_index.py` | offline | AS-022..AS-024, SC-007, SC-008 |
| `apps/control-plane/tests/integration/test_stream_sequence_concurrency.py` | PostgreSQL | SC-011, FR-031 |
| `apps/control-plane/tests/integration/test_cursor_replay_recovery.py` | PostgreSQL | FR-032, AS-005 |
| `apps/control-plane/tests/integration/test_outbox_lease_reclaim.py` | PostgreSQL | SC-010, FR-027, FR-028, FR-030 |
| `apps/control-plane/tests/integration/test_entity_request_transaction.py` | PostgreSQL | SC-009, FR-026, FR-029 |
| `apps/control-plane/tests/integration/test_worldline_tenant_isolation.py` | PostgreSQL | SC-013, FR-039 |
| `apps/control-plane/tests/integration/test_publication_staleness.py` | PostgreSQL | SC-014, AS-020, FR-040 |
| `apps/acquisition/tests/unit/test_entity_search.py` *(existing)* | offline | regression: single-plan path still inspectable (FR-005) |
| `apps/acquisition/tests/unit/test_cc_plan.py` *(existing)* | offline | regression: legacy `cc_plan` derivable (FR-005) |
| `apps/shared/tests/unit/domain/test_temporal_worldline.py` *(existing)* | offline | regression: 014 worldline contract preserved |
| `apps/control-plane/tests/unit/test_entity_stream_persistence.py` *(existing)* | offline | regression: stream repository contract preserved |

## Environment variables

| Variable | Meaning after this feature | Used in |
| --- | --- | --- |
| `CC_CRAWL` | Known-good crawl pinned first in the partition order. | 1, 6 |
| `CC_HISTORICAL_PARTITIONS` | `1` = enumerate the full archive index list instead of only `CC_CRAWL`. | 1, 6 |
| `CC_MAX_CRAWLS` | Per-invocation cap on partitions *processed*; unprocessed frontier entries stay `OPEN`. | 1, 6 |
| `CC_MAX_PAGES` | Per-invocation cap on pages per partition; remaining pages stay `OPEN`. | 1, 6 |
| `CC_PAGE_LIMIT` | Results per page. Unchanged, but paging now continues across invocations until the partition is confirmed exhausted. | 1, 6 |
| `COGNITIVE_DURABLE_SQL` | `1` = run the durable cursor/frontier path instead of the in-process fallback. | 1, 3, 4, 6 |
| `POSTGRES_*` | Points the repositories at the live database (`cognitive` for live runs, a disposable database for tests). | 0.4, 3, 4, 5, 7 |

The semantic change under test: exhausting `CC_MAX_CRAWLS` or `CC_MAX_PAGES` must produce
`complete: false` with a non-empty `remaining_work`, never a shorter history. Any test that
passes under the old "hard cap truncates history" behaviour is not testing this feature.

---

## Phase 0 - Preflight

**Purpose**: confirm the tree is clean, the existing verified vertical slice still passes,
and the new migration is forward-only with a single head and applies to a fresh database.

**Infrastructure**: steps 0.1-0.3 need nothing. Step 0.4 needs only PostgreSQL from the
core stack.

```powershell
# 0.1 Static gates - no infrastructure
uv run ruff check apps/shared apps/acquisition apps/control-plane
uv run ruff format --check apps/shared apps/acquisition apps/control-plane
uv run python -m compileall -q apps/shared apps/acquisition apps/control-plane
git diff --check
```

```powershell
# 0.2 Regression on existing suites - nothing already verified may regress
uv run --project apps/acquisition pytest apps/acquisition/tests/unit/test_entity_search.py apps/acquisition/tests/unit/test_cc_plan.py -q
uv run --project apps/shared pytest apps/shared/tests/unit/domain/test_temporal_worldline.py -q
uv run --project apps/control-plane pytest apps/control-plane/tests/unit/test_entity_stream_persistence.py -q
```

```powershell
# 0.3 Migration topology - no database needed for the revision graph itself
Push-Location apps/control-plane
uv run alembic heads
uv run alembic history
Pop-Location
```

```powershell
# 0.4 Fresh-install migration check - REQUIRES PostgreSQL
docker compose -f apps/deploy/docker-compose.yml --profile core up -d postgres
docker compose -f apps/deploy/docker-compose.yml --profile core exec -T postgres createdb -U cognitive cognitive_fresh_015
Push-Location apps/control-plane
$env:POSTGRES_DB = "cognitive_fresh_015"
uv run alembic upgrade head
uv run alembic current
uv run alembic upgrade head      # must be a no-op
Pop-Location
```

**Expected observable result**

- 0.1: zero lint findings, zero formatting drift, `compileall` silent, no whitespace errors.
- 0.2: all pre-existing tests pass unchanged. `test_cc_plan.py` still asserts the single
  plan is derivable, which is what keeps FR-005 (inspectable legacy behaviour) honest.
- 0.3: `alembic heads` prints exactly one head - `015_worldline_reconstruction` - whose
  `down_revision` is `014_temporal_materialization`. A second head means a branch and blocks
  the rest of the feature.
- 0.4: `alembic current` reports `015`; the second `upgrade head` creates no new revision
  row; the already-applied 014 file is untouched:

```powershell
git --no-pager diff --stat -- apps/control-plane/db/migrations/versions/
```


---

## Phase 1 - Offline deterministic tests (no network, no database)

**Purpose**: prove the semantics that must hold regardless of infrastructure.

**Infrastructure**: none. Do not start the Docker stack for this phase, and run it on a
host with egress blocked if you want to be certain.

### 1.1 Multi-route query set

```powershell
uv run --project apps/acquisition pytest apps/acquisition/tests/unit/test_source_query_set.py -q
```

What each test must prove:

- **One query per route.** An identity carrying `url`, `domain`, `name`, `alias`,
  `username` and `email` produces an independent query for each supported route, not one
  prioritized plan. Assert the route kinds explicitly, not just the count.
- **Order independence.** Building the query set from the same identity with the attribute
  map inserted in different orders yields byte-identical query sets. Compare `to_dict()`
  output, not equality of an unordered container.
- **Dedup with merged provenance.** Two attributes that normalize to the same route value
  (for example `https://acme.test` and `https://acme.test/`) produce one query carrying
  both provenance references; the merged reference list is sorted and contains both.
- **Unsupported routes are reported, not dropped.** A `phone` identity yields a query set
  whose `unsupported` list names `phone` with a reason code while the supported routes
  still execute. An identity with no executable route at all must raise the explicit
  no-executable-query reason - not return an empty set that reads like a negative finding.
- **Byte-range collision.** Two routes resolving to the same locator produce one observation
  identity carrying two route references (spec edge case).

**Proves**: AS-006, AS-007, AS-008, FR-001..FR-004.

### 1.2 Per-route budget

In the same file: with more routes than `CC_MAX_CRAWLS` allows, one run executes a
deterministic subset, records which route kinds remain, and a second run resumes with the
rest. Repeat the assertion after shuffling the input order to catch order-dependent
budgeting.

**Proves**: AS-009, FR-006, FR-008.

### 1.3 Frontier semantics

```powershell
$env:CC_CRAWL                 = "CC-MAIN-2025-30"
$env:CC_HISTORICAL_PARTITIONS = "1"
$env:CC_MAX_CRAWLS            = "2"
$env:CC_MAX_PAGES             = "1"
$env:CC_PAGE_LIMIT            = "50"
$env:COGNITIVE_DURABLE_SQL    = "1"
uv run --project apps/control-plane pytest apps/control-plane/tests/unit/test_reconstruction_frontier.py -q
```

The frontier store is exercised against an in-process fake store plus a scripted provider
(scripted pages, scripted failures). What each test must prove:

- **Budget defers instead of truncating.** With 5 partitions and `CC_MAX_CRAWLS=2`, one
  invocation processes 2 and leaves 3 `OPEN`. Repeated invocations with the same budget
  reach `EXHAUSTED` on all 5, and any result with work still open carries `complete: false`
  with a non-empty `remaining_work`. No partition is ever dropped from the frontier because
  a limit was reached, and no already-`EXHAUSTED` partition is re-opened.
- **New partitions extend coverage.** Add a partition to the advertised list between runs:
  the new one appears `OPEN` as additional work; previously `EXHAUSTED` entries stay
  `EXHAUSTED`.
- **Empty page is not exhaustion.** A page returning zero hits keeps the entry open unless
  the provider response itself confirms absence of further results. A partition confirmed
  empty by the provider becomes `EXHAUSTED` with zero fabricated observations.
- **Transient failure stays open.** A transport error and a `503` both leave the entry

### 1.4 Admission gating and observation/assertion level separation

```powershell
uv run --project apps/control-plane pytest apps/control-plane/tests/unit/test_assertion_materialization.py -q
```

What each test must prove:

- **One event per admitted assertion.** A single capture whose interpretation yields three
  accepted relations produces three temporal events, each carrying subject, predicate,
  object, interval, precision, an evidence reference, the admission decision and
  before/after state. It must not produce a single event for the capture.
- **Admission gating: rejected claims produce zero events.** A `REJECT`, `DEFER` or
  `QUARANTINE` claim yields no temporal event, no temporal relation and no entity state
  transition, while remaining retrievable with its decision, reason codes and score vector.
  Assert the event and relation counts, not merely the absence of an exception.
- **The observation survives rejection.** The observation for that capture is still written
  and independently resolvable, with retrieval locator, content hash and source record
  identifiers.
- **Level separation is explicit.** Reading at the observation level returns raw
  observations - including the one whose claims were all rejected - labelled `observation`.
  Reading at the assertion level returns only admitted assertions, labelled `assertion`.
  The two responses must be distinguishable without inspecting a version field.
- **Empty input.** A capture yielding no admitted assertion records the observation and
  represents the interval as explicitly yielding no change: an empty worldline for that
  interval, not an error and not a missing row.
- **Untrustworthy capture.** A truncated WARC record, a revisit record, or a failed payload
  digest is marked untrustworthy and cannot by itself produce an admitted assertion.
- **Over-budget page.** A capture yielding more claims than the per-page admission budget
  defers the remainder as explicit work rather than dropping it.

**Proves**: AS-010, AS-011, AS-012, AS-014, FR-015..FR-021, FR-023, SC-005.

### 1.5 Worldline determinism under input reordering

```powershell
uv run --project apps/shared pytest apps/shared/tests/unit/domain/test_worldline_determinism.py -q
```

Supply the identical accepted-assertion set in at least five different orders (seeded
shuffles, not hand-picked ones) and assert that the worldline document, the event ordering,
the state transitions and the canonical fingerprint are byte-identical across all of them.
Also assert that rebuilding from accepted assertions alone reproduces the same document as
the incremental path, and that a rejected assertion in the input changes nothing in the
output.

**Proves**: AS-013, FR-022, SC-006.

**Expected observable result for Phase 1**

- Every command exits `0` with no skips. A skipped offline test is a failing test.
- No test in these files opens a socket, a database session or an object-store client. If
  one does, it is a live test in the wrong tier and Phase 1's determinism claim is void.

**Proves overall**: FR-001..FR-022, AS-001..AS-014, SC-001..SC-006 - the entire
no-infrastructure surface of the feature.

---

## Phase 2 - Scale: 10,000-event worldline equivalence

**Purpose**: prove relation derivation no longer has a quadratic fundamental limit and is
semantically identical to the reference implementation. The pairwise implementation is
**retained as a test oracle**, not deleted.

**Infrastructure**: none. This phase is slow, not networked.

```powershell
uv run --project apps/shared pytest apps/shared/tests/unit/domain/test_worldline_relations_index.py -q -s
```

Build a deterministic 10,000-event history for one entity with a seeded mix of overlapping

---

## Phase 3 - Concurrency and durability on live PostgreSQL

**Purpose**: prove the guarantees only a real database under real concurrency can
establish - atomic sequence allocation, exact replay after a crash, and lease-based
reclaim of abandoned dispatch claims.

**Infrastructure REQUIRED**: the Docker core stack. Start it and confirm health first.

```powershell
docker compose -f apps/deploy/docker-compose.yml --profile core up -d
docker compose -f apps/deploy/docker-compose.yml --profile core ps
```

Expected: `postgres`, `redis`, `minio`, `kafka`, `schema-registry` and `temporal` all
report healthy/running, with PostgreSQL on `localhost:5432`, user and database `cognitive`
(matching `.env.example`).

Use a disposable database so a run cannot damage development data:

```powershell
docker compose -f apps/deploy/docker-compose.yml --profile core exec -T postgres createdb -U cognitive cognitive_test_015
Push-Location apps/control-plane
$env:POSTGRES_DB = "cognitive_test_015"
uv run alembic upgrade head
Pop-Location
$env:COGNITIVE_DURABLE_SQL = "1"
```

### 3.1 Concurrent stream sequence allocation (SC-011)

```powershell
uv run --project apps/control-plane pytest apps/control-plane/tests/integration/test_stream_sequence_concurrency.py -q
```

What it must prove:

- Launch N (>= 8) concurrent appenders against **one** `(tenant_id, entity_id)` pair, each
  appending M (>= 50) records through the real SQL repository over separate connections.
- Afterwards `count(*)`, `count(DISTINCT sequence)` and `count(DISTINCT record_hash)` on
  that entity's stream all equal `N*M`.
- `max(sequence) - min(sequence) + 1 == N*M` - no gaps, so no allocated sequence was lost.
- No duplicate `record_hash` and no rejected append silently swallowed.
- Repeat with two tenants using the **same** `entity_id` to prove sequences are scoped per
  `(tenant, entity)`, not per `entity_id` alone.

SQL confirmation:

```powershell
docker compose -f apps/deploy/docker-compose.yml --profile core exec -T postgres psql -U cognitive -d cognitive_test_015 -c "SELECT tenant_id, entity_id, count(*) AS rows, count(DISTINCT sequence) AS seqs, max(sequence) AS hi FROM entity_stream GROUP BY 1,2;"
```

**Proves**: SC-011, FR-031. Expected: one row per tenant/entity, `rows == seqs`, and
`seqs == hi` when sequences start at 1.

### 3.2 Crash between cursor prepare and append (FR-032)

```powershell
uv run --project apps/control-plane pytest apps/control-plane/tests/integration/test_cursor_replay_recovery.py -q
```

What it must prove:

- Prepare a page of work and commit it, then **abort before** the stream append (raise at
  the seam between cursor `prepare` and `append_many`).
- On retry the run replays *exactly* the prepared records: identical `record_hash` set,
  identical count, and **zero** additional archive fetches. Assert the provider call count
  did not increase on the retry path.
- The final state is indistinguishable from an uninterrupted run: same stream contents, same
  frontier entry status, same observation identities.
- Cover the inverse crash too - append committed, cursor `complete` not - and prove the
  retry does not duplicate records.

**Proves**: FR-032, AS-005, SC-003.

### 3.3 Outbox lease reclaim after a simulated relay crash (SC-010, FR-028)

```powershell
uv run --project apps/control-plane pytest apps/control-plane/tests/integration/test_outbox_lease_reclaim.py -q
```

What it must prove:

- **Lease reclaim.** A worker claims a request (`DISPATCHING`, lease set) and then "dies"
  without completing it. After the lease expires a second relay reclaims the row,
  transitions it back to dispatchable and increments `attempts`. No second entity is

---

## Phase 4 - Transactional boundary of entity creation

**Purpose**: prove entity creation is the durable transactional boundary of the
reconstruction request, and that a partial dispatch is never reported as a full success.

**Infrastructure REQUIRED**: the same disposable PostgreSQL from Phase 3.

### 4.1 Exactly one durable request with no worker running (SC-009)

```powershell
$env:COGNITIVE_DURABLE_SQL = "1"
uv run --project apps/control-plane pytest apps/control-plane/tests/integration/test_entity_request_transaction.py -q
```

What it must prove:

- With **no worker, relay or Temporal worker running**, create N (= 25) entities. For each,
  exactly **1** `PENDING` row exists in the durable request store for that entity, and
  exactly **1** entity row exists. The answer must come from inspecting durable state - not
  from an in-process fallback having happened to run.
- **Atomicity.** Inject a failure in the request insert and assert neither the entity nor
  the request survives: "a failure of either leaves neither" (AS-015).
- **Duplicate suppression.** Replay the identical creation request 3x: still exactly one
  active request per entity and per identity fingerprint (AS-017).
- **Orphan recovery.** Create an entity, kill the process immediately after commit, restart:
  a durable pending request exists and is picked up by the next relay run with no external
  trigger (AS-016).

SQL confirmation - this query must return **zero rows**:

```powershell
docker compose -f apps/deploy/docker-compose.yml --profile core exec -T postgres psql -U cognitive -d cognitive_test_015 -c "SELECT entity_id, count(*) AS active_requests FROM materialization_outbox WHERE status IN ('PENDING','DISPATCHING') GROUP BY 1 HAVING count(*) <> 1;"
```

**Proves**: SC-009, FR-026, AS-015, AS-016, AS-017.

### 4.2 Partial dispatch failure is not reported as full success (FR-029)

In the same file: dispatch a batch of 10 requests where 3 fail (workflow start throws).
Assert the relay's return value reports `dispatched=7, failed=3` with the failed ids, and is
**not** reported as a successful dispatch of the whole batch. Then assert the 3 failures are
still durable and claimable (not lost), that a subsequent relay run retries exactly those 3,
and that all 10 end `DISPATCHED` with `attempts` incremented only for rows actually
attempted.

**Proves**: FR-029, FR-030, AS-018.

---

## Phase 5 - Fresh install vs upgrade from revision 014

**Purpose**: prove both migration paths reach the **same** schema state. The 014 revision is
treated as already released and must not be edited.

**Infrastructure REQUIRED**: PostgreSQL. Two disposable databases are used so neither path
contaminates the other.

### 5.1 Path A - fresh install (all revisions from empty)

```powershell
docker compose -f apps/deploy/docker-compose.yml --profile core exec -T postgres createdb -U cognitive cognitive_fresh_015
Push-Location apps/control-plane
$env:POSTGRES_DB = "cognitive_fresh_015"
uv run alembic upgrade head
Pop-Location
```

### 5.2 Path B - upgrade from the released 014 revision

```powershell
docker compose -f apps/deploy/docker-compose.yml --profile core exec -T postgres createdb -U cognitive cognitive_upgrade_015
Push-Location apps/control-plane
$env:POSTGRES_DB = "cognitive_upgrade_015"
uv run alembic upgrade 014_temporal_materialization   # stop at the released revision
uv run alembic current                                # must report 014
uv run alembic upgrade head                           # 014 -> 015 only
Pop-Location
```

### 5.3 Compare the two schema states

```powershell
$fresh   = docker compose -f apps/deploy/docker-compose.yml --profile core exec -T postgres pg_dump -U cognitive -d cognitive_fresh_015   --schema-only --no-owner --no-privileges
$upgrade = docker compose -f apps/deploy/docker-compose.yml --profile core exec -T postgres pg_dump -U cognitive -d cognitive_upgrade_015 --schema-only --no-owner --no-privileges
Compare-Object $fresh $upgrade
```

Then verify the upgrade path preserved pre-existing 014 data. Insert a 014-era row *before*
the `upgrade head` in 5.2 and assert it survives:

```powershell
docker compose -f apps/deploy/docker-compose.yml --profile core exec -T postgres psql -U cognitive -d cognitive_upgrade_015 -c "SELECT version_num FROM alembic_version;" -c "SELECT count(*) FROM entity_stream;" -c "SELECT outbox_id, status, available_at, lease_expires_at FROM materialization_outbox LIMIT 5;"
```

**Expected observable result**

- 5.1 and 5.2 both succeed and both `alembic current` report `015_worldline_reconstruction`.
- `Compare-Object` returns **no differences**. Any difference means the two paths are not
  equivalent and SC-012 fails.
- Every new table (`reconstruction_frontier`, `source_query`, the observation and assertion
  tables, the per-entity sequence counter) and the new outbox columns (lease, availability)
  exist in **both** databases.
- 014-era rows in `entity_stream` and `materialization_outbox` are unchanged by the
  upgrade: no data loss, no rewrite, backfilled lease columns nullable or defaulted.
- Re-running `alembic upgrade head` on both databases is a no-op.

**Proves**: SC-012, FR-033. This phase is the gate for the ADR prerequisite recorded in
[plan.md](./plan.md); the feature does not proceed to live validation until it passes.

  created and no second published generation appears for that entity.
- **`available_at` is not claimed early (FR-028).** A `FAILED` row with
  `available_at = now + 60s` is **not** returned by a claim at `now`, and **is** returned
  once that time passes. This is a distinct assertion from the lease test: backoff-delayed
  work must not be claimed early, and the claim query must filter on `available_at <= now`.
- **Idempotent dispatch (FR-030).** Two relays run concurrently over the same claimable set:
  `SKIP LOCKED` semantics must yield each row to exactly one relay. The union of claimed ids
  has no duplicates and no row is claimed twice.

**Expected observable result for Phase 3**: all three files pass against real PostgreSQL
with 0 lost or duplicated records, 0 sequence collisions, and 100% of abandoned claims
reclaimed. A test that only uses a fake store does not satisfy this phase.

**Proves**: SC-010, SC-011, FR-027, FR-028, FR-030, FR-031, FR-032, AS-005, AS-016, AS-018.

and disjoint intervals, then assert:

- **No size-related failure (AS-022, SC-007).** The worldline and its relations are derived
  in a single call. No `max_events`-style guard trips, no exception is raised, and the
  event count is exactly 10,000.
- **Oracle equivalence (AS-023, SC-007, FR-035).** Run the retained reference pairwise
  derivation over the same events and compare the *full* relation set as a canonical sorted
  structure of `(kind, left_event_id, right_event_id, lag, derivation_basis)`. Compare sets
  rather than list order, and every field rather than just the count.
- **Batch-size invariance (AS-023).** Derive relations for the same events supplied as one
  batch, as 10 batches, and in reversed order. All three relation sets are identical.
- **Complexity (FR-034).** Time derivation at 1,000 / 5,000 / 10,000 events. Growth must be
  super-quadratic-free: `t(10k) / t(1k)` stays within a configured bound (order 100x for
  10x data, not ~10,000x). Print the measured numbers so a regression is visible in CI logs
  before it crosses the bound.
- **Timing budget (SC-008, FR-037).** Sample at least 20 worldline requests and 20 coverage
  queries over the 10,000-event entity and record wall-clock. Assert p95 worldline <= **3 s**
  and p95 coverage <= **1 s**. A single fast run is not evidence for a p95. Record machine
  shape, worker counts and policy/schema versions with the numbers; a slow CI runner that
  fails this must report the machine, not be silently excused.
- **Bounded, explained degradation (AS-024, FR-036).** Derive relations for a history that
  exceeds the configured relation budget. The request still succeeds, the response carries
  an explicit degradation label naming what was not computed and how many relations were
  omitted, and no partial result is presented as complete.

**Expected observable result**: the file passes and prints a measurement block - event
count, relation count, oracle match, per-scale timings, p95 worldline, p95 coverage, and
the degradation label text. No size-related exception anywhere in the output.

**Proves**: AS-022, AS-023, AS-024, SC-007, SC-008, FR-034..FR-037.

  `RETRYABLE` with the error recorded and `attempts` incremented, and the run is not
  reported complete. Exhausting the bounded retry budget moves the entry to a terminal
  failure state that still counts as remaining work - never as exhausted.
- **Identical-page no-progress guard.** A provider that ignores the offset and returns the
  identical page twice is detected, the partition is stopped and marked
  `EXHAUSTED_NO_PROGRESS`, and the run does not loop.
- **Resume without rework.** After an interruption mid-partition, the resumed run starts
  from the persisted page, re-fetches nothing already recorded, and produces no duplicate
  observation identity.

**Proves**: AS-001, AS-002, AS-003, AS-004, AS-005, AS-021, FR-007..FR-014, SC-002,
SC-003, SC-004.

Expected output: empty. Any change to `014_temporal_materialization.py` is a hard stop.

**Proves**: FR-033 (forward-only, single head), FR-005 (legacy path preserved), and the
no-regression clause of the 014 contract. SC-012 is completed in Phase 5, not here.




---

## Phase 6 - Live end-to-end against real Common Crawl

**LIVE-ONLY PHASE.** This phase requires real network egress to the Common Crawl index
(`index.commoncrawl.org`) and to the S3 origin (`data.commoncrawl.org`). It cannot be run
offline, in an air-gapped CI job, or against a mocked provider. A "pass" recorded without
real archive traffic proves nothing about AS-001..AS-005, and this phase's evidence is not
substitutable by any offline result.

**Infrastructure REQUIRED**: the full Docker core stack plus the control-plane API on
`:8000` and a Temporal worker.

```powershell
docker compose -f apps/deploy/docker-compose.yml --profile core up -d
docker compose -f apps/deploy/docker-compose.yml --profile core ps
```

Configure the run. A deliberately tiny budget is the point: it forces deferral so the
exhaustion behaviour is observable in minutes rather than days.

```powershell
$env:CC_CRAWL                 = "CC-MAIN-2025-30"  # known-good crawl pinned first
$env:CC_HISTORICAL_PARTITIONS = "1"                # enumerate the full archive index list
$env:CC_MAX_CRAWLS            = "1"                # ONE partition per invocation
$env:CC_MAX_PAGES             = "1"                # ONE page per partition per invocation
$env:CC_PAGE_LIMIT            = "25"               # small page -> paging is exercised
$env:COGNITIVE_DURABLE_SQL    = "1"                # durable frontier, no in-process fallback
$env:POSTGRES_DB              = "cognitive"
```

Start the API and the worker in two separate shells so both are running for the whole phase:

```powershell
# Shell 1 - API on :8000
Push-Location apps/control-plane
uv run uvicorn api.main:app --port 8000
Pop-Location
```

```powershell
# Shell 2 - worker
Push-Location apps/control-plane
uv run python -m services.worker
Pop-Location
```

Confirm the API answers before creating anything:

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/health"
```

### 6.1 Create the entity

```powershell
$body = @{
  canonical_identity = @{
    url      = "https://www.wikipedia.org"
    domain   = "wikipedia.org"
    name     = "Wikipedia"

### 6.2 Read back the executed query set (AS-006..AS-009, SC-001)

```powershell
$q = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/entities/$eid/source-queries"
$q.queries | Select-Object route_kind, normalized_value, status, provider
$q.unsupported | Select-Object route_kind, reason_code
```

**Expected**: at least four distinct supported `route_kind` values present, each with
`status` of `EXECUTED` or `PENDING`; every identity dimension appears in either `queries` or
`unsupported` with a reason. A dimension present in neither is an **SC-001 failure** (0
routes silently discarded). Read the endpoint twice and confirm the set is identical
(AS-007).

### 6.3 Poll run status and coverage (AS-002, AS-021)

```powershell
1..8 | ForEach-Object {
  $s = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/entities/$eid/materialization-status"
  $s | Select-Object run_id, status, complete
  $c = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/entities/$eid/coverage"
  "remaining=$($c.remaining_work.Count) complete=$($c.complete) last_progress=$($c.last_progress_at)"
  Start-Sleep -Seconds 20
}
```

**Expected**: partitions and pages listed with their individual states, `remaining_work`
non-zero while the budget is binding, `complete = $false`, and `last_progress_at` advancing
between cycles. The worldline must be labelled incomplete while `complete = $false`
(AS-002). A run reported `complete` while any frontier entry is `OPEN`, `RETRYABLE` or
`FAILED` is an **FR-025 / SC-004 failure**.

### 6.4 SQL verification of the real run

```powershell
docker compose -f apps/deploy/docker-compose.yml --profile core exec -T postgres psql -U cognitive -d cognitive -c "SELECT count(*) AS entries, count(*) FILTER (WHERE status='EXHAUSTED') AS exhausted, count(*) FILTER (WHERE status IN ('OPEN','RETRYABLE')) AS open, count(*) FILTER (WHERE status='EXHAUSTED_NO_PROGRESS') AS no_progress, max(attempts) AS max_attempts FROM reconstruction_frontier WHERE entity_id = '$eid';"
```

```powershell
docker compose -f apps/deploy/docker-compose.yml --profile core exec -T postgres psql -U cognitive -d cognitive -c "SELECT admission_decision, count(*) FROM entity_assertion WHERE entity_id='$eid' GROUP BY 1 ORDER BY 1;" -c "SELECT count(*) AS events, count(DISTINCT assertion_id) AS distinct_assertions FROM entity_temporal_event WHERE entity_id='$eid';"
```

```powershell
docker compose -f apps/deploy/docker-compose.yml --profile core exec -T postgres psql -U cognitive -d cognitive -c "SELECT count(*) AS observations, count(DISTINCT retrieval_locator) AS distinct_locators FROM cc_observation WHERE entity_id='$eid';" -c "SELECT retrieval_locator, content_hash, crawl FROM cc_observation WHERE entity_id='$eid' LIMIT 3;"
```

**Expected**

- The frontier shows real partitions and pages in mixed states, with `exhausted` strictly
  increasing across cycles and `max_attempts` bounded by the retry budget.
- Observations exist for real captures, each with a distinct `data.commoncrawl.org`
  retrieval locator and a content hash; `distinct_locators == observations` (dedup holds).
- Assertions carry a real distribution of admission decisions, including at least one
  non-accepted one.
- `events == distinct_assertions`: every temporal event corresponds to exactly one accepted
  assertion, and no rejected, deferred or quarantined claim produced an event, a relation
  or a state transition (SC-005).

### 6.5 Read the worldline and the observation behind an event (AS-010, AS-012)

```powershell
$wl = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/entities/$eid/worldline"
$wl.level
$wl.complete
$wl.events | Select-Object -First 3 event_id, assertion_id, subject, predicate, object, evidence_ref
$obs = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/entities/$eid/observations"
$obs.level
$obs.observations.Count
```

Then follow one event's evidence reference back to its source record:

```powershell
$ref = $wl.events[0].evidence_ref
$one = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/entities/$eid/observations/$ref"
$one | Select-Object observation_id, retrieval_locator, content_hash, observed_at, source_record_id
```

**Expected**: the worldline `level` is explicitly `assertion`; every event carries an
`evidence_ref` that resolves to a real locator, content hash and source record identifier.
The observation endpoint is labelled `observation` and returns raw observations, including
any whose claims were all rejected (AS-012, AS-014).

### 6.6 Repeated scheduler cycle proving exhaustive coverage (SC-002, AS-001)

Keep re-triggering the scheduler with the **same** small budget until the frontier reports no
remaining work, then confirm:

```powershell
$cov = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/entities/$eid/coverage"
$cov.complete
$cov.remaining_work.Count
```

```powershell
docker compose -f apps/deploy/docker-compose.yml --profile core exec -T postgres psql -U cognitive -d cognitive -c "SELECT count(*) AS never_processed FROM reconstruction_frontier WHERE entity_id='$eid' AND attempts=0;" -c "SELECT count(*) AS not_terminal FROM reconstruction_frontier WHERE entity_id='$eid' AND status NOT IN ('EXHAUSTED','EXHAUSTED_NO_PROGRESS','FAILED_TERMINAL');"
```

**Expected**: `complete = $true`, `remaining_work` empty, `never_processed = 0` and

---

## Phase 7 - Tenant isolation and staleness after failure

**Purpose**: prove isolation holds on every new read and write path, and that a failed run
never destroys or overstates a previously valid publication.

**Infrastructure REQUIRED**: PostgreSQL plus the API on `:8000` (still running from Phase 6,
or restarted with the same env). This phase does **not** need live Common Crawl access.

### 7.1 Cross-tenant probes (SC-013, FR-039)

```powershell
uv run --project apps/control-plane pytest apps/control-plane/tests/integration/test_worldline_tenant_isolation.py -q
```

The test creates the **same** `entity_id` in two tenants, each with its own frontier,
observations, assertions, events and worldline, then probes every new surface as the wrong
tenant.

**Expected**

- 100% of cross-tenant probes are denied. A foreign resource returns the same `404` shape as
  a resource that does not exist, with no differing status, count, age, timing, error text
  or existence signal.
- 0 cross-tenant rows returned by frontier, coverage, evidence, request or worldline reads -
  verified at the SQL layer, not only at the API layer:

```powershell
docker compose -f apps/deploy/docker-compose.yml --profile core exec -T postgres psql -U cognitive -d cognitive -c "SELECT tenant_id, count(*) FROM reconstruction_frontier GROUP BY 1;" -c "SELECT tenant_id, count(*) FROM entity_temporal_event GROUP BY 1;" -c "SELECT tenant_id, count(*) FROM materialization_outbox GROUP BY 1;"
```

**Proves**: SC-013, FR-039.

### 7.2 Staleness after a failed run (SC-014, AS-020, FR-040)

```powershell
uv run --project apps/control-plane pytest apps/control-plane/tests/integration/test_publication_staleness.py -q
```

Sequence: publish a valid worldline; force a subsequent run to fail (unreachable provider, or

---

## Phase 8 - Full regression gate

**Purpose**: the release gate. Run on the merge candidate after all previous phases pass.

**Infrastructure**: the core stack for the integration suites; Node 20+ and `pnpm` for the
frontend block. The frontend block is required only if `apps/webapp` files changed - check
first:

```powershell
git --no-pager diff --name-only origin/main...HEAD -- apps/webapp
```

An empty result means skip the frontend block and record in the evidence that it was
skipped and why.

```powershell
# 8.1 Full Python suites
uv run --project apps/shared pytest apps/shared/tests -q
uv run --project apps/acquisition pytest apps/acquisition/tests -q
uv run --project apps/control-plane pytest apps/control-plane/tests/unit -q
uv run --project apps/control-plane pytest apps/control-plane/tests/integration -q
uv run --project apps/interpretation pytest apps/interpretation/tests -q
uv run --project apps/admission pytest apps/admission/tests -q
uv run --project apps/projection pytest apps/projection/tests -q
```

```powershell
# 8.2 The new offline suites, run together as a single determinism check
uv run --project apps/acquisition pytest apps/acquisition/tests/unit/test_source_query_set.py -q
uv run --project apps/control-plane pytest apps/control-plane/tests/unit/test_reconstruction_frontier.py apps/control-plane/tests/unit/test_assertion_materialization.py -q
uv run --project apps/shared pytest apps/shared/tests/unit/domain/test_worldline_determinism.py apps/shared/tests/unit/domain/test_worldline_relations_index.py -q
```

```powershell
# 8.3 Static gates
uv run ruff check apps/shared apps/acquisition apps/control-plane apps/interpretation apps/admission apps/projection
uv run ruff format --check apps/shared apps/acquisition apps/control-plane apps/interpretation apps/admission apps/projection
uv run python -m compileall -q apps
git diff --check
```

```powershell
# 8.4 Frontend - ONLY if apps/webapp files changed
Push-Location apps/webapp
pnpm test
pnpm exec tsc -b
pnpm build
pnpm lint
Pop-Location
```

**Expected observable result**

- 8.1 and 8.2: zero failures, zero errors, no unexpected skips. A skip in a new test file is
  a failure until justified in writing.
- 8.3: zero lint findings, zero formatting drift, `compileall` silent.
- 8.4: `tsc -b` emits no type errors and `build` succeeds. If the feature touched
  `apps/webapp`, the console renders coverage, completeness, stream level and admission
  outcomes from server-authoritative fields only, with no browser-side fabrication of
  missing state, and a foreign or unauthorized resource renders the same not-found state as
  a nonexistent one.

Any unrelated baseline failure must be fixed or explicitly approved before release; it
cannot be hidden behind a "no new failures" rule.

**Proves**: the repository-wide no-regression clause.

---

## Release evidence checklist

- [ ] AS-001 through AS-024 pass with recorded evidence; AS-022..AS-024 are covered offline, AS-001..AS-021 additionally live.
- [ ] FR-001 through FR-040 each map to a passing test or an explicitly justified operator check.
- [ ] SC-001 through SC-014 meet their numeric thresholds with the measurement recorded, not just "passed".
- [ ] All new offline suites pass with PostgreSQL stopped and no network egress.
- [ ] Live Common Crawl evidence is real archive traffic (Phase 6), not a mocked provider.
- [ ] Frontier reaches `complete = true` under a deliberately small per-run budget, with cycle count and wall-clock recorded.
- [ ] The pairwise relation oracle is retained in the tree and used by the 10,000-event scale test.
- [ ] Fresh-install and upgrade-from-014 schema states are identical (`Compare-Object` returns nothing).
- [ ] The applied `014_temporal_materialization` migration file is unmodified.
- [ ] Cross-tenant probes denied at both the API and the SQL layer, with no existence or timing signal.
- [ ] Last valid publication retained and explicitly labelled stale after a failing run.
- [ ] The single-plan `cc_plan` path is still derivable and inspectable (FR-005 regression).
- [ ] Ruff, compileall, pytest and - if webapp files changed - tsc/vitest/build gates are clean.

## Known limits of this guide

- Phases 1, 2 and the static parts of Phase 0 are the only ones runnable in an air-gapped CI
  job. A green Phase 1 does not imply a working live reconstruction, and Phase 6 evidence
  cannot be replaced by an offline result.
- SC-008 timings are machine-dependent. Record the machine shape; do not relax the
  threshold to make a slow runner pass.
- Phase 6 needs a target with real historical presence in Common Crawl. A target present
  only in the newest crawl cannot demonstrate frontier exhaustion across partitions.
- The `services.worker` module path and the `/source-queries`, `/coverage` and
  `/observations` routes are the implementation surface this feature must expose. If they
  land under different paths, update this guide rather than the tests, and record the
  deviation.
- Where this guide names a table (`reconstruction_frontier`, `entity_assertion`,
  `entity_temporal_event`, `cc_observation`), it names the concept from
  [plan.md](./plan.md); align the SQL to the shipped schema and record any rename.

a frontier entry that cannot complete); then read the worldline again.

**Expected**

- The read returns the **last valid publication**, unchanged: same publication id, same
  generation, same events.
- The response carries an explicit staleness label (for example `stale: true` with
  `reflects_newest_evidence: false`), so a consumer cannot mistake it for current state.
- The failed run is reported as `partial` and names the failing partition with its reason
  (AS-019); no completed result is published as a final reconstruction (FR-023, FR-025).
- The previous valid publication remains readable throughout failure and recovery, and
  becomes current again only after a subsequent successful run.

API-level confirmation using the two-tenant token form (`resolve_tenant` reads the bearer
token as a JSON claim envelope in the current build):

```powershell
$tA = @{ tenant_id = "tenant-a"; user_id = "analyst-a"; roles = @("analyst") } | ConvertTo-Json -Compress
$tB = @{ tenant_id = "tenant-b"; user_id = "analyst-b"; roles = @("analyst") } | ConvertTo-Json -Compress
Invoke-RestMethod -Headers @{ Authorization = "Bearer $tA" } -Uri "http://localhost:8000/api/v1/entities/$eid/worldline" | Select-Object stale, complete
try { Invoke-RestMethod -Headers @{ Authorization = "Bearer $tB" } -Uri "http://localhost:8000/api/v1/entities/$eid/coverage" } catch { $_.Exception.Response.StatusCode }
```

Expected: the tenant-B call returns `NotFound` with the same body shape as a nonexistent
entity; the tenant-A worldline read carries the staleness label.

**Proves**: SC-014, AS-019, AS-020, FR-023, FR-025, FR-040.

`not_terminal = 0`. With `CC_MAX_CRAWLS=1` across the full advertised index list, this is
only reachable if every partition is eventually processed: **100% of frontier entries reach
a terminal state after repeated runs, and 0 partitions remain permanently unprocessed**
(SC-002, AS-001). Entries still at `attempts=0` after many cycles mean budgets are
truncating history, and the feature's central claim is broken.

Record the number of scheduler cycles and the wall-clock time to reach exhaustion as the
operational evidence for "eventually exhaustive", together with the observed partition count.

**Proves**: AS-001, AS-002, AS-003, AS-005, AS-006, AS-007, AS-010, AS-012, AS-021, SC-001,
SC-002, SC-005 - against a real archive, with real locators and real content hashes.


    username = "wikipedia"
    email    = "contact@wikipedia.org"
  }
  aliases = @("Wiki", "The Free Encyclopedia")
} | ConvertTo-Json -Depth 5

$r = Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/entities" -ContentType "application/json" -Body $body
$eid = $r.entity.entity_id
$eid
$r.materialization
```

The identity deliberately supplies five distinct route types (exact URL, URL prefix, domain,
name/alias, username-derived, email-derived) so the multi-route claim is genuinely testable.
Note the returned `materialization.run_id` and keep it for the status reads below.

