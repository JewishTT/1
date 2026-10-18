# ADR-030-06 — The existing matcher is canonical; Splink is benchmark-only behind the same contract

- **Status**: Accepted
- **Date**: 2026-10-17
- **Feature**: `030-global-platform-upgrade`
- **Implements**: T021
- **Cites**: FR-110, FR-081, Constitution P3, P13, ADR-0013, ADR-0014, ADR-030-03
- **Enforced in code by**: `apps/admission/resolution/splink_adapter.py:1-22`

## Context

Identity resolution has two engines in play and a donor matrix that says when the second may run.

**[MEASURED]** The canonical matcher is `apps/zero/zero/resolution/fellegi_sunter.py`, a
Fellegi-Sunter implementation with `ComparisonLevel` (`:32`), `ComparisonField` (`:42`), field
constructors — `name_field` (`:57`), `email_field` (`:70`), `phone_field` (`:86`), `text_field`
(`:102`) — `block_pairs` (`:122`), the `FellegiSunter` class (`:160`) and a `_tf_adjustment`
frequency-weighting helper (`:303`). `tasks.md` T084 names this exact file as the measurement target
for `benchmarks/er-baseline.md`.

**[MEASURED]** The second engine is already present, pinned and self-limiting.
`apps/admission/resolution/splink_adapter.py` opens with a header that states the rule in its own
terms: *"Splink as a linkage **proposer**, behind the platform's resolution contract."* It records
upstream `https://github.com/moj-analytical-services/splink`, revision **4.0.10 (pinned)**, licence
MIT, and `Mode: B — upstream package behind a COGNITIVE contract` (`:5-8`). Its stated purpose at
`:10-16`: *"Splink proposes; it does not decide… Nothing here writes identity, and nothing here is
wired to write identity."* And at `:18-21`, the gate condition, quoted: *"**Baseline this must beat**
(ADR-030-06): the existing Fellegi-Sunter implementation at
`apps/zero/zero/resolution/fellegi_sunter.py`. Until `benchmarks/er-baseline.md` records a comparison
on the same labelled pairs, this adapter stays benchmark-only and no production caller is wired to
it."*

**[MEASURED]** The gate and span defects T021 names are real and still open. `research.md §2.6`:
the donor matrix marks Splink *"DEFERRED — after contracts hold"*, with the verbatim reason *"All are
individually sound. None should receive data while the gate and identity defects stand."* The gate
defect (029 WP-C) is the admission threshold that could commit a merge from an uncalibrated profile;
the span defect (029 WP-F) is the `Segment.offset` conflation at
`apps/interpretation/extractors/lane.py`. `research.md §2.3` records the 029 WP-E closure as the reason
the gate defect is now bounded, but the span defect is independently confirmed as open in
`current-state-audit.md §2`.

**[MEASURED]** `benchmarks/er-baseline.md` does not exist — there is no `benchmarks/` directory.

So the decision is constrained from both sides: FR-110 forbids calling anything integrated without a
measured comparison, and the 029 donor matrix forbids sending data to a second engine while the gate
and span defects stand. Both point the same way, and the code already implements it.

## Decision

**D1 — `apps/zero/zero/resolution/fellegi_sunter.py` is the canonical matcher.** It is the production
matcher. No other engine writes or commits identity.

**D2 — Splink is benchmark-only, behind the same `ResolutionCandidate` contract.** It is permitted to
emit candidates on the frozen labelled pair corpus (T076) and nowhere else. It emits the same
candidate type the canonical matcher emits, with a comparison vector and a score whose semantics are
named. There is no second candidate schema and no second identity writer.

**D3 — No production caller is wired to the Splink adapter.** This is not a preference; it is stated in
the adapter's own header (`splink_adapter.py:18-21`) and is the gate condition of this ADR. The
promotion path is: `benchmarks/er-baseline.md` exists (T084) **and** the FR-083 gate defects and span
defects are closed **and** a recorded comparison exists (T105 consumes it).

**D4 — Promotion requires a measured win on our data, not a feature list.** Pair recall,
false-merge rate, false-non-match rate, candidate-pair reduction and calibration, all on the frozen
corpus, all reported. "Splink is better at entity resolution" is not a result.

**D5 — Rollback to the canonical matcher is a config change, and it deletes nothing.** Splink has
contributed candidates only; candidates and derived artifacts survive its removal (constitution P13).

**D6 — No data reaches Splink while the gate and span defects stand.** Until
`ResolutionMention` carries a span (T060) and the FR-083 checklist is enforced (T162), a pair corpus
of "candidates with evidence" is not available — there is nothing reviewable to show an analyst. The
deferral is the 029 matrix's own condition, not a new restriction.

## Why not the alternatives

**A — Adopt Splink as canonical now.** Rejected on FR-110 in one line: a dependency in
`pyproject.toml` is not an integration, and no benchmark exists. Rejected on the donor matrix's own
ordering second: *"None should receive data while the gate and identity defects stand."*

**B — Benchmark Splink on synthetic pairs now, while the corpus is being built.** Rejected: a synthetic
pair corpus measures the implementation, not the workload. Transliteration variants, company aliases,
name changes and shared addresses (T076) are precisely where a Fellegi-Sunter u-score and a Splink
EM fit diverge; synthetic data would hide exactly the disagreements that decide the question.

**C — Run both engines in production and pick per-workload.** Rejected: that creates two production
matchers, which is the dual-authority shape ADR-030-03 D8 forbids. "Canonical per workload profile"
is only coherent if the profile selects among *proposers*, not among *committers*.

**D — Replace the Fellegi-Sunter implementation with a cleaner rewrite.** Rejected: FR-115 says
existing internal capability is inventoried and assessed before a second implementation is added.
The matcher is live, tested, and is the baseline everything else must beat.

**E — Wait for `benchmarks/er-baseline.md` before writing this ADR.** Rejected. The baseline measures
the canonical matcher; it does not decide who is canonical. The decision is decidable now from FR-110
and the donor matrix, and the code already encodes it.

**F — Record Splink's status as "integrated, unpromoted".** Rejected: that word is load-bearing in this
platform. FR-110 lists eight conditions, of which at least two are unmet (benchmark, real production
call site). Calling it integrated would be the exact fabrication constitution P15 forbids.

## Consequences

**Positive**

- One identity writer. ADR-030-03 D8 holds with a single enforcement point.
- The benchmark comparison will be apples-to-apples: same contract, same candidate type, same corpus.
- The adapter's own header documents the constraint, so a future reader cannot mistake "present in the
  tree" for "in production" — the failure FR-114 and P15 both exist to prevent.

**Costs, accepted**

- A pinned, licensed, working capability sits idle. Accepted deliberately: the 029 matrix ordered it
  after the gate and span fixes, and reordering that on convenience grounds is how a second authority
  gets created.
- The canonical matcher's own quality is unmeasured. That is uncomfortable — the thing we are keeping
  as canonical has no recorded false-merge rate — and it is the reason T084 is not optional.

**Not changed**

- ADR-030-03 (append-only decisions) is independent of this one.
- The Fellegi-Sunter implementation is untouched by this ADR.
- `apps/admission/resolution/` gains no new file from this decision; the adapter already exists.

## Verification

- [ ] Exactly one engine commits identity; `splink_adapter.py` has no writer path.
- [ ] No production caller is imported for `SplinkAdapter` — it is reachable only from benchmark code.
- [ ] Both engines emit `ResolutionCandidate` from the same module
      (`apps/admission/resolution/candidate.py`); no second candidate schema exists.
- [ ] `benchmarks/er-baseline.md` exists and records pair recall, candidate-pair reduction,
      false-merge rate, false-non-match rate and calibration for
      `apps/zero/zero/resolution/fellegi_sunter.py`.
- [ ] The FR-083 admission checklist is enforced (T162) and `ResolutionMention` carries a span (T060)
      before any non-synthetic data reaches Splink.
- [ ] Removing the Splink adapter deletes no candidate, evidence or derived artifact.
- [ ] `SPLINK_VERSION_PINNED` is asserted by a test and a version bump fails that test.

## Open

- **`benchmarks/er-baseline.md` does not exist and `benchmarks/` does not exist as a directory.** T084
  owns it and its own text says *"**No numbers before this number exists**"* — more precisely, no
  numbers before the baseline exists. This ADR therefore records **no** false-merge rate, recall or
  calibration figure for the canonical matcher, and none may be quoted until T084 lands.
- **The gate and span defect closure is not recorded.** T060 (`ResolutionMention` span field) and T162
  (FR-083 checklist) have not run, so the D6 precondition is asserted from the donor matrix text, not
  from an observed state.
- **Splink's frozen-corpus consumption (T105) is not built.** The adapter exists and self-limits; the
  benchmark harness behind it does not.