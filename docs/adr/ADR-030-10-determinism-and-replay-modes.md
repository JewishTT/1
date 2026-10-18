# ADR-030-10 — Two declared replay modes; `restore(stream, history=)` is the mitigation and must not regress

- **Status**: Accepted
- **Date**: 2026-10-17
- **Feature**: `030-global-platform-upgrade`
- **Implements**: T025
- **Cites**: FR-036, Constitution P10, ADR-0030, ADR-0021
- **Protects**: `apps/control-plane/context_engine/invariant_reducer.py:319` and
  `apps/control-plane/tests/unit/test_digest_gated_revision.py:160`

## Context

The platform is a distributed event system with at-least-once delivery, and ADR-0030 settled what
follows: one sequencer per branch, recorded batch boundaries, canonical reduction order, derived seeds,
and three determinism classes (`EXACT` / `FIXED_POINT` / `FLOAT_QUANTIZED`). FR-036 adds the constraint
that closes it: the context projection operator "MUST be a pure, reproducible function of its declared
inputs and versions; it MUST NOT perform network access, remote model calls, durable writes or identity
mutation inside the deterministic core" (`spec.md:324-326`).

Byte-identical replay across heterogeneous platforms is **not achievable** for float-backed artifacts,
and ADR-0030 already says so rather than promising it. What was missing is the machinery that makes
the limited claim enforceable. That is the two-mode declaration.

**[MEASURED]** There is a specific, documented, load-bearing property in the invariant reducer, and it
is the reason this ADR is mostly about *not breaking something*.

`InvariantReducer` advances its revision counter **once per `reduce()` call, not once per event**. The
consequence is recorded in `research.md §2.10`: *"a cold fold of a three-event stream lands at revision
1 while an incremental fold reaches revision 3, and because the revision is inside the invariant
identity **the two produce different digests over identical evidence**."* `research.md §2.10` then
states: *"This is the single most important existing behaviour in the repo and must not be regressed."*

**[MEASURED]** The mechanism that exists for exactly this is `restore`. `apps/control-plane/context_engine/invariant_reducer.py:319`
declares:

```python
@classmethod
def restore(
    cls,
    stream: Iterable[Any],
    *,
    history: Iterable[RevisionRecord] = (),
    ...
```

`restore` rebuilds **at the recorded position** rather than at 1. Its docstring at `:330-338` states
both halves of the contract: it *"rebuilds from a persisted `(stream, history)` pair and **verifies**"*
it, and *"a stream and a history that disagree mean a corrupt store"*. The verification is enforced,
not aspirational: `:343` raises on `history_not_gapless` (*"revision chain must be gapless from 1, got
{positions}"*) and `:370` raises when *"stream rebuilds to {invariant.content_id}, history head is
{head.snapshot_id}"*.

**[MEASURED]** And there is a test whose entire purpose is to stop someone "fixing" this. At
`apps/control-plane/tests/unit/test_digest_gated_revision.py:160`,
`test_a_cold_fold_is_not_equivalent_to_a_restore`, docstring at `:161-175`:

> *A property worth pinning, because it looks like a bug and is not. … A digest that has been warming
> up to revision 3 is therefore **not reproducible by a cold fold**, even over the identical stream.
> That is why `restore` exists and takes the history: it rebuilds at the recorded position rather than
> at 1. A caller that uses a cold fold to "rebuild from scratch" and compares the digest will report a
> false change, and then mint a revision for evidence that did not move. The test asserts the property
> rather than pretending it does not exist, so a future change to the revision semantics has to confront
> it.*

The test body confirms it: `warm` reaches revision 3, `cold = _reducer().reduce(records)` does not
match, and the positive case at `:156-157` asserts that
`restore(warm.stream, history=warm.history(), ...)` reproduces both `head.digest` and `head.revision`.

So the risk this ADR must manage is not theoretical. A plausible-looking refactor that makes the
revision counter advance per event would make the cold fold reproducible — and would silently change
every digest ever computed, because the revision is inside the invariant identity.

## Decision

**D1 — Two replay modes, declared per operator.**

| Mode | Meaning | Replay obligation |
|---|---|---|
| `deterministic` | a pure function of fingerprinted inputs and versions | replay **recomputes**; the output digest must match |
| `result_replay` | model-hosted or otherwise non-deterministic | the exact returned result is preserved with its inputs; the mode is **stated** |

There is no third mode and no implicit default for an operator that does not declare.

**D2 — The deterministic core is pure.** No network access, no remote model call, no durable write, no
identity mutation (FR-036). "Durable write" is the clause that does the work: an operator that writes
cannot be replayed, and a replay that mutates state is not a replay.

**D3 — `deterministic=true` implies `model_fingerprint=null`** (contract 01, `tasks.md` T035). A result
claiming to be deterministic while naming a model is self-contradictory and is refused at validation.

**D4 — The invariant reducer's per-`reduce()` revision semantics are preserved.**
`InvariantReducer.restore(stream, history=)` at `invariant_reducer.py:319` remains the rebuild path. A
change to how the revision counter advances is a **breaking change to every digest in the system** and
requires a migration and a new artifact identity scheme — not a bug fix. Its gapless-chain and
head-mismatch verification (`:343`, `:370`) stays or strengthens.

**D5 — `test_a_cold_fold_is_not_equivalent_to_a_restore` stays green and stays named.**
`test_digest_gated_revision.py:160`. A change that makes a cold fold equivalent to a restore is a
deliberate, separately-migrated decision, and the test is updated in the same change that performs the
migration — never before, and never silently.

**D6 — Canonical serialization for identity-critical hashes.** Stable key ordering; normalised
timestamps and timezones; no uncontrolled `repr()` and no memory-address stringification
(constitution P10; `tasks.md` T033).

**D7 — Replay is a mode, not a state.** `REPLAYED` is not a revision status (ADR-0030 §7). A replay run
emits a comparison and creates no revision.

**D8 — After erasure, replay degrades explicitly** (ADR-0030 §7, ADR-0039 §3): `REPLAY_DEGRADED` with
the list of unreadable inputs. Silent degradation is forbidden.

**D9 — No operator is promoted to `deterministic` on assertion.** It is demonstrated: a test replays
the operator and asserts the digest matches. An operator whose digest has never been reproduced under
replay is `result_replay`, regardless of what its metadata claims.

## Why not the alternatives

**A — Fix the revision counter to advance per event, making cold folds reproducible.** Rejected, and it
is the tempting one because the current behaviour looks like a bug. The test's own docstring explains
why it is not: the counter advancing per `reduce()` call is what makes a revision mean *"a fold
happened"*, which is the unit the event log can actually replay. Changing it changes the identity of
every invariant ever computed, so every stored digest, every manifest `output_digest`, and every
lineage reference built on them becomes unverifiable. The migration cost is the whole database.

**B — Drop the two modes and declare everything `result_replay`.** Rejected: it is honest but it gives
up the guarantee where the guarantee is achievable, which is most of the platform. FR-036 requires the
deterministic core to be pure; declaring it impure to avoid the purity obligation inverts the
requirement.

**C — Declare everything `deterministic` and fix discrepancies as they appear.** Rejected: ADR-0030
already established that byte-identity is not achievable across platforms for float-backed artifacts.
Claiming it universally produces a contract that is violated silently and constantly — the failure that
produced the three determinism classes in the first place.

**D — Record the replay mode only in logs, not in the result envelope.** Rejected: FR-036 and contract
01 make it part of the result. A mode that lives in a log is not queryable by the consumer deciding
whether to trust a digest, which is the only consumer that matters.

**E — Let `restore` fall back to a cold fold when history is empty.** Rejected: an empty history is
exactly the case where a cold fold produces revision 1 and a silently wrong digest. `restore`'s current
behaviour — `:343` refusing a non-gapless chain — is the correct response. A fallback would convert a
loud corruption error into a quiet identity change.

**F — Accept the property and document it, without the test.** Rejected: the test *is* the protection,
and its docstring says so explicitly. Documentation drifts; a red test does not.

## Consequences

**Positive**

- The claim is scoped to what is actually achievable, so it stays trustworthy. A `deterministic` digest
  match means something; a universal byte-identity claim would mean nothing.
- D4 plus D5 mean the repo's most fragile invariant cannot be removed by a well-meaning cleanup, because
  the test's docstring forces whoever breaks it to confront what they are doing.
- `restore`'s existing verification means a corrupt `(stream, history)` pair is detected at load, not
  discovered later as a digest mismatch.

**Costs, accepted**

- An operator that is genuinely `result_replay` must persist its exact output and its inputs, which is
  more storage than recomputation. Accepted: recomputation is not available for these operators, and
  pretending otherwise loses the result.
- D6's canonical serialization is a real constraint on how new artifacts are hashed, and getting it
  wrong produces digests that do not reproduce. This is the T033 work.
- D5 is a standing tax: the test encodes behaviour that a future engineer will find surprising, and
  that tax is the point.

**Not changed**

- ADR-0030 (revision, determinism and replay contract) stands in full, including the three
  determinism classes, canonical reduction order and derived seeds.
- ADR-0021 (atomic stream sequence) is unaffected; replay does not assign order.
- The revision counter's per-`reduce()` semantics are **unchanged** by this ADR.

## Verification

- [ ] Every operator result declares exactly one of `deterministic` / `result_replay`.
- [ ] `deterministic=true` ⇒ `model_fingerprint=null` (contract 01).
- [ ] Replaying a `deterministic` operator reproduces the recorded `output_digest` (T147).
- [ ] `InvariantReducer.restore(stream, history=)` at `invariant_reducer.py:319` rebuilds at the
      recorded revision, not at 1.
- [ ] `restore` refuses a non-gapless history chain (`invariant_reducer.py:343`) and a
      stream/history head mismatch (`:370`).
- [ ] `test_a_cold_fold_is_not_equivalent_to_a_restore`
      (`test_digest_gated_revision.py:160`) passes unmodified.
- [ ] A deterministic operator's core performs no network call, no remote model call, no durable write
      and no identity mutation (FR-036).
- [ ] Identity-critical digests are stable across key-insertion order and across equivalent timezone
      representations; no `repr()` or `id()` output appears in hashed material.
- [ ] A replay after erasure returns `REPLAY_DEGRADED` with the unreadable-input list (D8).

## Open

- **The replay-mode fields are not implemented.** Contract 01 (`apps/shared/contracts/
  operator_result.py`, T029) and its validation tests (T035) have not run. D1 and D3 are decided; the
  field that carries them does not exist yet. `apps/shared/contracts/` does contain
  `projection_manifest.py`, so contracts work is in flight elsewhere.
- **`InvariantReducer.restore` is verified by reading, not by running.** This ADR cites
  `invariant_reducer.py:319`, `:343`, `:370` and `test_digest_gated_revision.py:160` from source. The
  test's status in the current run has not been confirmed in this session; the last full-suite baseline
  recorded in `current-state-audit.md §1` was `22 failed, 4358 passed, 32 skipped`, with no indication
  that `test_digest_gated_revision.py` is among the failures, but a specific run of that file was not
  performed here and this ADR does not claim one.
- **No operator has been demonstrated as `deterministic` under replay.** D9 therefore currently leaves
  the whole platform on `result_replay` by default, which is the correct conservative state and is
  stated rather than papered over.