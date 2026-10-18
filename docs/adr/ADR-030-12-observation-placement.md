# ADR-030-12 — No guessed placement: `UNPLACED` is a durable, visible state that does not count toward coverage

- **Status**: Accepted
- **Date**: 2026-10-17
- **Feature**: `030-global-platform-upgrade`
- **Implements**: T027
- **Cites**: FR-062, FR-063, Constitution P6, P15, ADR-030-02
- **Depends on**: ADR-030-02 for the transaction mechanism; this ADR decides the *semantics*

## Context

FR-062 is the requirement: every acquisition result entering investigation state MUST have explicit
membership or scope resolution; **when it cannot be established, the observation MUST persist as
unplaced with a recorded gap and MUST NOT be attached by guess** (`spec.md:386-388`).

The clause that matters is the last one. Not-attached and guessed-attached are different states, and
only one of them is honest. A guessed attachment is worse than a missing one: it looks like coverage,
it counts toward whatever the attachment implies, and nobody downstream can tell it was invented. The
failure mode is invisible precisely because it improves the numbers.

**[MEASURED] The detection function already exists and says the right thing.**
`apps/control-plane/context_engine/return_path.py:212` declares
`def unplaced(outcomes: Sequence[ObservationOutcome]) -> tuple[str, ...]:` and its docstring at
`:213-218` states the principle directly:

> *"Observations that arrived without membership, and so cannot be placed. **Reported rather than
> swallowed.** An unplaced observation is a coverage question the investigation has to answer, and the
> caller needs the list to raise it — a silently narrower context is the failure this whole direction
> exists to prevent."*

That last clause is the governing sentence of this ADR. "A silently narrower context" is what guessing
produces.

**[MEASURED] The detection logic is honest about what it checks.** `return_path.py:219-224` collects an
observation id only when `not outcome.entities.get(observation_id)` — that is, when the outcome carries
no entity mapping for it. The function returns a tuple and it does not mutate; it reports.

**[MEASURED] The state is already surfaced in the cycle report.**
`apps/control-plane/context_engine/query_cycle.py:39` and `:54` carry `unplaced` as a field
(`unplaced: tuple[str, ...] = ()`), and `:75` serialises it as `"unplaced": list(self.unplaced)` into
the cycle output. `query_cycle.py:186` computes `missing = unplaced(outcomes)` and `:195` passes
`unplaced=missing` into the result.

**[MEASURED] It reaches the service layer and the operator-facing report.**
`apps/control-plane/services/cycle_service.py:60` carries `unplaced: tuple[str, ...] = ()`, `:108`
serialises it, and `:201` writes it into a human-readable line: `f"{report.lattice['unplaced']} unplaced, "`.
`:497-500` imports and calls it: `from context_engine.return_path import newly_grounded, unplaced` and
`report.unplaced = unplaced(outcomes)`.

**[MEASURED] Tests already assert it is zero in the happy path.**
`apps/control-plane/tests/integration/test_platform_assembly.py:342` asserts
`report.gradient["unplaced_observations"] == 0` and `:365` asserts `report.lattice["unplaced"] == 0`.
So the positive assertion exists.

**[MEASURED]** What the measurements do **not** show is the negative guarantee: that a non-zero
`unplaced` count is *visible as a gap* rather than merely recorded. Recording it in a report field is not
the same as counting it against coverage, and FR-062 requires the stronger property. There is no
measurement anywhere in the tree that unplaced observations are excluded from a coverage figure, and no
measurement that a guessed attachment is impossible.

## Decision

**D1 — `UNPLACED` is a durable first-class state, not an error, not a discard, and not a transient.**
The observation persists. It is queryable. It carries the reason its membership could not be
established. It is never deleted because it could not be placed.

**D2 — No guessed placement, ever.** Membership is established by resolution or not established. There
is no heuristic tier, no nearest-scope fallback, no "attach to the most likely investigation" path. A
heuristic that improves attachment rate at the cost of D2 is rejected on sight, because its output is
indistinguishable from a real membership once stored.

**D3 — `UNPLACED` does not count toward coverage.** An unplaced observation contributes **nothing** to
any coverage, completeness or saturation figure. This is the operative half of FR-062 and the half most
likely to be got wrong. Coverage computed over placed observations only is a *true* number about a
*narrower* set — which is honest — whereas counting unplaced observations is a false number about a
wider set. The gap must be visible next to the number.

**D4 — The gap is reported, not merely stored.** Per `return_path.py:215-218`, the caller receives the
list so it can raise it. An unplaced observation that is recorded but never surfaced produces a silently
narrower context, which is the exact failure the function's docstring names.

**D5 — Placement is never reported before its membership write commits.** FR-063's first sentence.
`UNPLACED` and `PENDING_PLACEMENT` are both honest; "placed, pending commit" is not. The mechanism is
ADR-030-02 D2–D3.

**D6 — An unplaced observation is not a failed acquisition.** The three states — produced and placed,
produced and unplaced, not produced — are distinct, and none is a report of the others (constitution P6).

**D7 — Re-placement is additive.** Membership can be established later, by resolution, as a new
transition from `UNPLACED` → `PLACED`. This does not retroactively alter coverage figures already
computed and published; those remain true of the state at their time, and the change is visible as a
revision.

**D8 — The state is queryable without joining the cycle report.** `UNPLACED` must be answerable as a
question about a tenant's current gaps, not only as a field on one cycle's output.

## Why not the alternatives

**A — Drop observations that cannot be placed.** Rejected, and it is the tempting one because it keeps
every downstream count clean. It converts a visible coverage gap into an invisible data loss: the
evidence was acquired, paid for, stored, and then silently discarded, and nothing records that it
existed. The next coverage claim is then wrong with no trace of why.

**B — Guess membership to the best candidate scope.** Rejected by FR-062's final clause, and rejected on
mechanism: a guessed attachment is stored identically to a real one, so the error becomes invisible the
moment it is written. The only defence would be a flag, and a flag on a guess is a claim that the guess
is reviewable — which is what D2 forbids.

**C — Treat unplaced as a soft failure and retry indefinitely.** Rejected: it converts a coverage
question into an unbounded queue. `return_path.py:217` is right that an unplaced observation is *"a
coverage question the investigation has to answer"* — a question posed to a human or to policy, not one
retried by a loop that cannot answer it.

**D — Count unplaced observations toward coverage, flagged.** Rejected. A flagged false number is still
a false number, and every consumer of the coverage figure has to remember the flag. FR-062 requires the
gap to be recorded; D3 requires it to be *excluded*, not annotated.

**E — Let an adaptive or learned layer infer membership.** Rejected: this is ADR-030-08 D2's boundary
crossed. It is also the worst version of B, because the guess would be neither reproducible nor
attributable.

**F — Defer this ADR until ADR-030-02's outbox wiring (T051) lands.** Rejected: the semantics and the
mechanism are separable, and the semantics are the part that is easy to get wrong. Deciding them now
means the wiring lands against a specified target instead of an implied one.

## Consequences

**Positive**

- Coverage figures become defensible: each is true of a stated set, and the excluded set is named.
- The evidence is preserved. An unresolvable observation today can be placed tomorrow by a resolution
  improvement, and nothing was thrown away in the meantime.
- `return_path.py:212`'s existing function becomes a specification-checked contract rather than an
  incidental helper — the docstring already says what the ADR now requires.

**Costs, accepted**

- Coverage numbers will be lower than a guessing implementation would report. That is the correct
  direction and it will look like a regression to anyone reading the number without the gap beside it.
  D3 and D4 exist so the gap is never far from the number.
- Every coverage consumer needs updating to handle the excluded set. That is real work across the
  coverage and completeness modules (`apps/science/context/coverage.py`, `completeness.py`).
- D7's "coverage is not retroactively altered" means a published figure stays published. Correct, and
  it means the current gap count must also be queryable at all times (D8).

**Not changed**

- ADR-030-02 owns the transaction mechanism; this ADR does not specify a queue.
- `unplaced()` at `return_path.py:212` is not modified by this ADR.
- ADR-030-08 D2 stands: nothing reclassifies knowledge truth, and `UNPLACED` is a placement state, not
  an epistemic one.

## Verification

- [ ] An observation whose membership cannot be resolved persists as `UNPLACED` with a recorded reason
      and is not attached to any scope (FR-062).
- [ ] No code path attaches an observation to a scope without a resolution result; a repository search
      finds no fallback or nearest-scope assignment.
- [ ] Unplaced observations contribute zero to every coverage, completeness and saturation figure.
- [ ] Every coverage figure is accompanied by the count of unplaced observations excluded from it.
- [ ] An unplaced observation is visible as a gap without joining a cycle report (D8).
- [ ] `UNPLACED` and "not produced" are distinct states and neither is reported as the other.
- [ ] A membership write that failed is never reported as placed (FR-063);
      `test_platform_assembly.py:342,365` still assert the zero-gap happy path.
- [ ] Re-placing an observation later creates a new transition and does not alter previously published
      coverage figures.

## Open

- **The "excluded from coverage" half is unverified.** The measurement confirms `unplaced` is
  **recorded** (`query_cycle.py:75`, `cycle_service.py:108,201`) and **asserted zero** in the happy path
  (`test_platform_assembly.py:342,365`). It does not confirm the stronger property FR-062 requires —
  that a non-zero count is *excluded from* coverage rather than merely shown beside it. No measurement
  of that exists in the tree, and this ADR does not assert one. T073
  (`apps/science/context/completeness.py`, `coverage.py`) owns the coverage enforcement and should
  carry the test that closes it.
- **`UNPLACED` is currently a report field, not a persisted state machine.** The states
  `PENDING_PLACEMENT` / `PLACED` / `UNPLACED` that ADR-030-02 D2 defines are not implemented; what
  exists is a computed tuple. D1's "durable" therefore describes the required end state and the ADR is
  accepted as the specification of it, not as a description of shipped behaviour.
- **The `PENDING_PLACEMENT` phase has no carrier.** ADR-030-02's `## Open` records the same gap from the
  mechanism side; contract 01 (T029) and T051 own it.