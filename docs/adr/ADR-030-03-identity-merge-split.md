# ADR-030-03 — Identity is an append-only resolution decision; merge and split supersede, never rewrite

- **Status**: Accepted
- **Date**: 2026-10-17
- **Feature**: `030-global-platform-upgrade`
- **Implements**: T018
- **Cites**: FR-080–FR-084, Constitution P3, ADR-0013, ADR-0014
- **Related**: ADR-030-06 (which matcher is canonical), ADR-030-02 (append-only publication)

## Context

Four requirements constrain identity, and they pull against each other unless the storage model is
chosen carefully.

- **FR-081** — no similarity probability, structural centrality, graph adjacency, topological feature
  or model output may *by itself* authorise a merge.
- **FR-082** — resolution decisions MUST be append-only; a superseded decision MUST remain retrievable
  and claims written under a prior identity interpretation MUST remain traceable to it.
- **FR-083** — admission must validate a nine-item checklist including span reachability, purpose and
  tenant permissions, method version, and human review where ambiguity or risk requires it.
- **FR-084** — pairwise matches MUST NOT imply cluster membership where feature evidence is
  inconsistent.

FR-082 and FR-084 are in direct tension with the most natural schema. The obvious way to store
"these two mentions are the same entity" is to mutate an `entity_id` column, or to delete a losing
member when a split wins. Both are **rewrites**, and both destroy the thing FR-082 protects: the
record that the claim was written under an interpretation that has since been superseded. Once the
superseded interpretation is gone, the split cannot be audited — and an unauditable split is
indistinguishable from a silent correction.

There is a second, subtler pressure. FR-081's "by itself" is doing real work, and it is easy to
satisfy it formally while defeating it in practice. A matcher emits a score; the admission gate reads
the score and the matcher's calibration profile; the gate decides. If the profile says "uncalibrated"
and the gate still commits, FR-081 has been violated with a paper trail. `research.md §2.3` records
that feature 029 closed exactly this — "a merge can no longer be decided by a threshold whose own
profile declares itself uncalibrated, and corroboration counts lineage roots rather than hostnames,
with the measure used named on every decision." That closure is the evidence this ADR rests on.

**[MEASURED]** The proposer-only pattern is already enforced in code, and it says so explicitly.
`apps/admission/resolution/splink_adapter.py:1-22` opens: *"Splink proposes; it does not decide… The
one rule this module exists to enforce."* It pins Splink at revision 4.0.10, names the baseline it must
beat (`apps/zero/zero/resolution/fellegi_sunter.py`), and states that until
`benchmarks/er-baseline.md` records a comparison, *"this adapter stays benchmark-only and no
production caller is wired to it."*

**[MEASURED]** Supersession-as-append is already the established idiom in this codebase, which is
strong evidence it is the right shape here rather than a new invention:
`apps/admission/engine/temporal.py:60` declares `supersedes: str | None`, and `:113` sets
`repl.supersedes = old_id` on a replacement. `apps/admission/resolution/candidate.py:68` states the
invariant in prose — *"this record supersedes (reverse appends one). 'Latest record per pair' drives"* —
and `:219` repeats it: *"so it supersedes rather than erases."* `api/routes/resolutions.py:8` puts it
in the API contract: *"accept is expressed as a REJECT record for the same pair (supersedes, never
erases)."* `apps/admission/tests/test_admission.py:110` pins it as a test.

**[MEASURED]** `benchmarks/er-baseline.md` does not exist. There is no `benchmarks/` directory. T084
owns it. So the matcher comparison this decision depends on has not been produced.

## Decision

**D1 — `ResolutionDecision` is append-only.** A decision row is written and never updated. Merge and
split are both *new rows* that supersede prior ones by reference. A superseded row stays readable
forever and keeps its rule version, author, timestamp, evidence refs and stated measure.

**D2 — Identity is derived from the decision history, never from a mutable entity column.** The
current interpretation of a pair is the latest non-superseded decision. "Latest" is a query over the
append-only log, not an update. This is what makes a split a first-class event: a split is a new
`SPLIT` row, and the merge it contradicts remains retrievable.

**D3 — Every claim records the identity interpretation it was written under.** Each claim stores the
decision id (or "no decision yet") in force when it was admitted. Re-interpreting identity never
rewrites a claim; it produces a new reading of the same claim under a new decision. This is FR-082's
second clause and it is the one that is easy to lose.

**D4 — Nothing commits a merge alone.** A matcher emits candidates with a comparison vector and a
score whose *semantics* are named (`SplinkAdapter` does exactly this). The admission gate applies the
FR-083 checklist. A matcher whose own profile declares itself uncalibrated cannot commit a merge at
any threshold — the check is on the calibration declaration, not on the score's magnitude.

**D5 — Pairwise agreement is not cluster membership.** A↔B and B↔C matching does not entail A = C.
Cluster membership is a separate decision that must be supported by feature evidence across the whole
group; inconsistency across the group's features blocks it rather than being averaged away (FR-084).

**D6 — Corroboration counts lineage roots, and the measure is named on the decision.** Three
syndicated copies of one wire story are one source. The decision row records *which* measure was used,
so a later reviewer can disagree with the measure rather than guess at it.

**D7 — Mention, candidate and entity stay distinct types.** A mention is a located string in a blob. A
candidate is a proposed correspondence with its evidence. An entity is the output of admitted
decisions. No promotion happens implicitly (`Principle` domain invariant 2).

**D8 — A second identity writer is refused.** Splink and any future engine propose candidates
through the same `ResolutionCandidate` contract. Only the admission path writes decisions.

## Why not the alternatives

**A — Mutate `entity_id` on merge, delete the loser on split.** Rejected: it is the direct negation of
FR-082. It destroys the superseded interpretation, so the split cannot be audited and claims written
under the old reading become untraceable. It is also irreversible in a system whose constitution makes
replay a first-class mode.

**B — Soft-delete the superseded decision (set `revoked_at`).** Rejected, though it was the closest
call. It looks append-only because the row survives, but the *content* can still be edited behind the
flag, and a revoked row is easily omitted from "what did the system believe at time T" queries — which
is the query that matters. A true append keeps both facts visible without a flag the reader must
remember to check.

**C — Keep decisions mutable but log every mutation to an audit table.** Rejected: this is the same
history split across two stores, which creates exactly the dual authority T008 is chartered to find.
Worse, the audit table is a second writer for the same fact.

**D — Let a high-scoring matcher commit directly when it clears a threshold, with the gate only
handling the grey zone.** Rejected: FR-081 forbids it, and the 029 finding is that the threshold in
question belonged to a matcher that had declared itself uncalibrated. A grey-zone gate around a
confident core is the shape that produced that defect.

**E — Model splits as merges in the opposite direction (union-find with retractions).** Rejected for
now. Retraction-aware clustering is a legitimate design, but it makes cluster membership a derived
quantity that depends on the retraction algorithm's history, which is far harder to audit than an
explicit decision log. Revisit if decision-log volume becomes a measured problem.

**F — Defer this ADR until `benchmarks/er-baseline.md` exists (T084).** Rejected. The baseline measures
matcher *quality*; it does not decide the *storage model*. The append-only decision log is required by
FR-082 regardless of which matcher wins, and deferring it would mean the baseline lands against an
undetermined schema. The missing baseline is recorded in `## Open` instead.

## Consequences

**Positive**

- A split is auditable: the merge it contradicts is still there, with the evidence that justified it.
- Claims remain interpretable. "Why does this claim attach to that entity?" has an answer for any
  point in the history, not only the present one.
- Replay is consistent with constitution P10 — the decision log is a stream that can be folded, not
  mutable state that must be snapshotted.
- D4 is already implemented as a stated rule in `splink_adapter.py:1-22`; this ADR makes it binding
  rather than aspirational.

**Costs, accepted**

- The decision log grows without bound where a mutable column would not. Accepted: erasure and
  retention are handled by ADR-030-11 / ADR-0039's tombstone model, not by forgetting history.
- Every identity read becomes a query over history rather than a column read. This is a genuine
  latency cost on the hot path and is the main thing to measure.
- Analysts must learn that "the entity this mention belongs to" is a question with a date. Accepted:
  the alternative is a question with a date and no way to see it.

**Not changed**

- ADR-030-06's canonical matcher decision is independent of this one.
- The Felix-Sunter implementation at `apps/zero/zero/resolution/fellegi_sunter.py` is untouched by
  this ADR.
- Admission remains distinct from priority (domain invariant 7).

## Verification

- [ ] A high-score pair with no admission decision commits **zero** merges (FR-081).
- [ ] A split supersedes the merge without deleting it; both rows are retrievable (FR-082).
- [ ] A claim admitted under decision *D1* remains traceable to *D1* after *D2* supersedes it.
- [ ] A↔B and B↔C matching with inconsistent A↔C evidence does **not** yield a cluster (FR-084).
- [ ] A matcher whose profile declares itself uncalibrated commits a merge at no threshold value.
- [ ] Every decision row names the corroboration measure used, and that measure counts lineage roots.
- [ ] `apps/admission/tests/test_admission.py:110` still passes unchanged.
- [ ] No code path updates or deletes a `ResolutionDecision` row.

## Open

- **`benchmarks/er-baseline.md` does not exist.** T084 owns it and records pair recall, candidate-pair
  reduction, false-merge rate, false-non-match rate and calibration for the current matcher at
  `apps/zero/zero/resolution/fellegi_sunter.py`. Until it lands, no matcher quality claim may be
  made, and D4's "no threshold may commit" rule has no measured false-merge rate behind it. This ADR
  does not estimate any of those numbers.
- **`ResolutionDecision` append-only persistence is not implemented.** T082 (`apps/admission/
  resolution/`) and T083 (`decision_store.py`) own it. `apps/admission/resolution/decision_store.py`
  does not exist yet; the file list today is `__init__.py`, `blocking.py`, `candidate.py`,
  `collective.py`, `resolver.py`, `splink_adapter.py`. D1–D3 are decided, not built.