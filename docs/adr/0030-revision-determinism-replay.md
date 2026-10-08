# ADR-0030 — Revision, determinism and replay contract

**Status**: Accepted (Wave 0, ADR-025-03)
**Feature**: `025-context-reality-approximation-engine`
**Baseline**: v2 §4, §4.1, §4.2, §6, §36, §39.4, Appendix G.2, Appendix H

## Context

Two facts collide.

First, the platform is a distributed event system: Redpanda, multiple workers, at-least-once
delivery. Per-context event order is therefore not a property of the transport.

Second, the constitutional requirement is byte-identical replay (§4). Byte-identity across
heterogeneous platforms is **not achievable** for floating-point-backed artifacts, and
pretending otherwise produces a contract that is violated silently and constantly. v2 already
split identity into three classes; what was still missing is the machinery that makes the
split enforceable.

A third issue is storage cost. A full state snapshot per revision does not scale to
thousands of revisions over a long investigation, and v2 introduced content-addressed
artifacts and manifests to solve it — which in turn introduces garbage collection, erasure and
concurrency questions.

## Decision

**1. One sequencer per branch.** Exactly one sequencer assigns a gapless `context_event_seq`.
Ties on arrival are broken by `(source_event_id)` lexicographic order and the resulting order
is persisted in the event log manifest. Events are partitioned by context partition key so
per-context total order survives Redpanda partitioning. Without this, "the" event order is a
function of scheduling and replay is undefined.

**2. Recorded batch boundaries.** Revisions are produced per `ChangeBatch` — a contiguous run
of sequenced events, closed by `max_events` or `max_logical_span`. Boundaries are **recorded**
in the log. Replay uses the recorded boundaries, never a wall-clock timer. One tick yields at
most one revision.

**3. Optimistic concurrency on commit.** `(context_id, branch_id, parent_revision)` is the
compare-and-swap key. A conflicting writer fails and re-proposes. The sequencer makes this
the exceptional path, not the common one. Pessimistic locking is rejected: a context is
written by one sequencer, so a lock would only add a failure mode.

**4. Determinism classes.** Identity is defined per artifact class, and every operator
declares `numeric_mode`:

| Class | Requirement |
|---|---|
| `EXACT` | byte-identical on any platform |
| `FIXED_POINT` | byte-identical on any platform, at declared scale |
| `FLOAT_QUANTIZED` | quantized-identical across platforms; byte-identical on same build+platform |

Floats are canonicalised to decimal strings at a declared significant-digit count *before*
hashing. NaN/Inf are forbidden in identity material.

**5. Canonical reduction order.** Floating-point reductions sort by stable id before
accumulating. Parallel execution partitions deterministically and merges in canonical order.
Two workers summing the same set get the same bits.

**6. Derived seeds, never ambient.** `seed = digest128(context_id, branch_id,
parent_revision, operator_id, run_ordinal)`, part of the parameter fingerprint. An operator
that wants randomness takes a seed argument. There is no ambient RNG in the reasoning path.

**7. Revisions are manifests.** A revision stores artifact digests, not rows. Unchanged
artifacts are shared with the parent. GC removes only artifacts unreachable from any
non-expired revision and not under legal hold.

**8. Replay is a run mode, not a state.** `REPLAYED` is not a revision status. Replay emits a
`ReplayReport` comparing artifact digests and never creates or mutates a revision. After
erasure it returns `REPLAY_DEGRADED` with the unreadable-input list; erased digests remain so
everything else stays verifiable.

## Consequences

**Positive**

- Replay stops depending on scheduling, worker count or wall clock.
- Byte-identity is claimed only where it is achievable, so the claim stays trustworthy.
- Revision storage is proportional to change, not to state size.

**Costs, accepted**

- One sequencer per branch is a throughput ceiling per context. Accepted: investigations are
  sequential in nature, and horizontal scale comes from partitioning contexts, not from
  parallelising one.
- Quantisation is lossy for `FLOAT_QUANTIZED` artifacts. Declared, versioned, and part of the
  fingerprint — a lossy value that is honestly labelled beats an exact claim that is false.

**Not changed**

- 024's existing `ContextRevision` shape is extended, not rewritten (ADR-0028). The additive
  fields are `state_hash`, `manifest_ref`, `batch_ref`, `branch_id`, `worldline_snapshot_ref`,
  `method_fingerprint`, `policy_fingerprint`.

## Verification

- [ ] Two concurrent writers on the same `(context, branch, parent)` → exactly one commits.
- [ ] Replay with recorded boundaries reproduces identical artifact digests at every boundary,
      per determinism class.
- [ ] Cross-platform check: `EXACT`/`FIXED_POINT` artifacts byte-identical on Linux and
      Windows; `FLOAT_QUANTIZED` quantized-identical.
- [ ] Parallel and serial execution of the same operator produce identical output.
- [ ] Same inputs twice under a disabled adaptive layer produce identical `state_hash`.
- [ ] `created_at` differing between two runs does not change `state_hash`.
- [ ] GC removes only unreachable, non-held artifacts; an erasure drill leaves integrity
      checkable and replay reports `REPLAY_DEGRADED`.