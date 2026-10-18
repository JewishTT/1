# ADR-030-04 — Eight typed clocks; `CURRENT`, `AS_OF(known-time)` and `INTERVAL(valid-time)` are three dimensions

- **Status**: Proposed
- **Date**: 2026-10-17
- **Feature**: `030-global-platform-upgrade`
- **Implements**: T019
- **Cites**: FR-020–FR-025, Constitution P7, ADR-0022, ADR-0035
- **Depends on**: T037, which has not run — see `## Open`

## Context

Bitemporal storage is the mechanism that lets the platform say *"the world was in state X at time T"*
and *"we believed that at time K"* as two separate facts. It only works if the clocks are separately
typed and separately stored. Collapse them and one of two things happens, both of them bad: a claim
about the past silently changes because someone learned something new, or a claim about what we knew
becomes indistinguishable from a claim about the world.

FR-020 names the clocks: source-published time, source-valid-from/valid-until, source-observed time,
captured/fetched time, recorded/known time, processed time, projected time. FR-022 then separates the
query dimensions, and the separation is the requirement that has teeth — `AS_OF` "MUST NOT be
overloaded to mean both what the system knew and what is true in the world" (`spec.md:295-297`).

**[MEASURED]** The distinction already exists in the schema and in a migration, with the reasoning
written down rather than left implicit. `EntityFact` is declared at
`apps/control-plane/db/schema.py:2768`. Migration
`apps/control-plane/db/migrations/versions/023_derivation_enforcement.py` adds both columns —
`recorded_at` (`:102`) and again for the second table (`:130`) — and states the rule in the migration
comment at `:128`: *"`recorded_at` is when we learned it; `valid_from` is when it was true."* The
migration's own header (`:31`) separates the two questions explicitly. Related nullable time columns
exist across the ORM: `valid_from` at `schema.py:925`, `:1095`, `:1276`, `:1331`, `:1397`, `:1553`;
`observed_at` at `:1274`, `:1333`, `:1555`, `:1671`, `:1713`, `:2461`.

**[MEASURED]** The query side exists too. `TemporalMode` with `CURRENT` / `AS_OF` / `INTERVAL` lives
in `apps/science/context/query_ast.py`, defaulting at `:164` (`mode: TemporalMode =
TemporalMode.CURRENT`), and the validator enforces the dimensions at `:171-179`: `AS_OF` **raises**
`ValueError("AS_OF needs the timestamp it is as of")` without a timestamp, `INTERVAL` raises
`ValueError("INTERVAL needs at least one bound")` without one, and `CURRENT` takes its own branch.
Raising rather than defaulting is the correct shape — FR-021 says unknown source time must stay
unknown and must not be defaulted, and the same discipline applies to the query mode.

**[MEASURED]** `plan.md` and `research.md §1.4` both record Alembic's latest migration as
`015_worldline_reconstruction`. The tree now contains twelve migrations, `014` through `025`, with
`025_context_graph.py` latest. Any claim about "the latest migration" written before this feature
executed is stale.

**[MEASURED] The open question is U-03**, and it is still open. `research.md §8` records it:
*"Does `recorded_at` flow past migration into ORM and query?"* — *"Requires runtime verification, not
reading."* `plan.md §Post-design Check` carries P7 forward as *"**PASS — U-03 open**"*, and
`current-state-audit.md` does not record a T037 result. Static reading confirms the columns exist at
every layer named above; that is not the same as observing a write flow end to end.

## Decision

**D1 — Eight clocks, separately typed and separately defined.** Source-published; source-valid-from;
source-valid-until; source-observed; captured/fetched; recorded/known; processed; projected. Each
carries its own timezone and null semantics. Each answers exactly one question, and the name states
which. No clock is a derived default of another: **unknown source time stays null** and is never
defaulted to now (FR-021).

**D2 — Three query dimensions, not one.**

| Dimension | Question | Binds to |
|---|---|---|
| `CURRENT` | what is the current reconstruction of valid time | `valid_from` / `valid_until` |
| `AS_OF(k)` | what did the system *know* at known-time *k* | `recorded_at <= k` **and** valid time as of *k* |
| `INTERVAL(a, b)` | what was valid over the valid-time interval | `valid_from`/`valid_until`, overlap |
| — | | |

These may not be aliased onto one another. `AS_OF` never silently means valid-time-as-of rather than
known-time-as-of; if a caller wants that, they ask for it explicitly (FR-022).

**D3 — Late-arriving evidence rewrites the reconstruction, never the record.** New evidence about past
valid time changes what `CURRENT` returns today and what `AS_OF(today)` returns. It does **not** change
what `AS_OF(k)` returned for *k* before the evidence arrived. This is FR-023 and it is the entire
reason `recorded_at` is stored separately from `valid_from` (FR-082's sibling requirement for
identity, applied to time).

**D4 — Temporal precedence is never presented as causality.** A causal claim carries its assumptions,
identification conditions, confounds and its non-identifiability state (FR-024).

**D5 — Imprecise intervals are disjunctive or unknown, never forced.** Where temporal relation
reasoning is enabled, the supported interval-relation subset is declared, and an interval with fuzzy
bounds produces a disjunction or an explicit unknown rather than one convenient relation (FR-025).

**D6 — `TemporalMode` validation stays raising, not defaulting.** The `ValueError` behaviour at
`query_ast.py:171-179` is load-bearing and is not to be relaxed to fill in a default.

**D7 — A new column is not a new clock.** Adding a timestamp column requires naming which of the
eight it is, or stating that it is a ninth with its own semantics. Untyped timestamps are refused at
review.

## Why not the alternatives

**A — Four clocks (`published`, `valid_from`, `valid_until`, `ingested`).** Rejected. It collapses
source-observed, captured, processed and projected into one column, which makes "did we know this, or
had we merely received it?" unanswerable and makes processing lag indistinguishable from evidence
lag. The extra four columns cost nothing at write time and are unrecoverable once collapsed.

**B — One `timestamp` plus a `timestamp_kind` enum.** Rejected: a nullable discriminator column means
the type is never enforced by the schema, only by convention. A row can be written with the wrong
kind, and nothing catches it. Typed columns make the error a database-level failure.

**C — Reconstruct `valid_from`/`valid_until` from `recorded_at` at query time.** Rejected: it erases
the evidence-arrival signal that FR-023 depends on, and it makes a late-arriving correction
indistinguishable from a long-known fact.

**D — Accept this ADR and let T037 verify the flow afterwards.** Rejected for the Status field, adopted
for the content. The *decision* — eight clocks, three dimensions — is fully specified by FR-020–023
and does not depend on whether the existing implementation flows correctly. What depends on T037 is
whether this repository already satisfies it. Status is therefore **Proposed**, not Accepted: an ADR
that claims its decision is in force while the only evidence about its implementation is a column
definition is overstating itself.

**E — Wait for T037 and write nothing.** Rejected. T037 is a verification task, not a design input. The
design is settled by the specification; blocking on a runtime check would let a tooling task decide an
architecture question.

## Consequences

**Positive**

- The knowledge/valid distinction stops being folklore and becomes a schema constraint with a
  migration comment explaining it.
- `AS_OF(k)` becomes genuinely reproducible: it is a filter on `recorded_at`, and late-arriving
  evidence provably cannot change it.
- The raising behaviour in `query_ast.py:171-179` means a malformed temporal query fails at the
  boundary instead of silently answering a different question.

**Costs, accepted**

- Eight columns per temporal model is wide. Writers must populate the right ones; a writer that fills
  `recorded_at` but not `captured_at` produces a partial row. Accepted: a narrow schema hides the
  distinctions rather than removing them.
- Every temporal query must declare its mode. There is no implicit default for `AS_OF`/`INTERVAL` — a
  caller must say which question it is asking, which is the point.
- Retrofitting existing rows means an explicit backfill policy per column, and "unknown" has to be
  distinguishable from "not yet backfilled". T126 owns the tooling.

**Not changed**

- ADR-0022 (indexed worldline relations) and ADR-0035 (temporal algebra) stand.
- The `EntityFact` shape at `db/schema.py:2768` is not restructured by this ADR.
- No migration is authored here. T038 owns any schema change arising from these decisions.

## Verification

- [ ] Each of the eight clocks exists as its own typed column with documented null semantics.
- [ ] Unknown source time persists as null and never becomes `now()` (FR-021).
- [ ] `CURRENT`, `AS_OF(k)` and `INTERVAL(a, b)` return demonstrably different result sets over a
      fixture where all three are answerable.
- [ ] `AS_OF(k)` returns byte-identical results before and after late-arriving evidence about the
      same period (FR-023).
- [ ] `query_ast.py:171-179` still raises on `AS_OF` without a timestamp and on `INTERVAL` without a
      bound.
- [ ] A causal claim carries assumptions and a non-identifiability state (FR-024).
- [ ] A fuzzy interval yields a disjunction or unknown, never a forced single relation (FR-025).
- [ ] No column named `timestamp` exists on a temporal model without a documented clock identity (D7).

## Open

- **U-03 is unresolved and this ADR does not resolve it.** `research.md §8` defines U-03 as *"Does
  `recorded_at` flow past migration into ORM and query?"* and states it *"Requires runtime
  verification, not reading."* **T037 must land first**: it verifies the `recorded_at` flow from
  migration into ORM and query layer (`apps/control-plane/db/migrations/versions/`, latest
  `023_derivation_enforcement.py` by filename, against `apps/control-plane/db/schema.py:2768`), and it
  blocks SC-008. `current-state-audit.md` records no T037 result. Static reading confirms the columns
  exist; the end-to-end write path is unobserved and is **not** asserted here.
- **Note on the analyze finding.** `tasks.md` row A4 records *"U-03 resolved: `recorded_at` does flow
  past migration into ORM and the query layer"*, citing `EntityFact` at `db/schema.py:2768`, migration
  `023_derivation_enforcement.py`, and `TemporalMode` in `science/context/query_ast.py` with 125
  passing contract tests. That conclusion is consistent with what is visible statically, but the
  finding also says *"The real gap is a cross-layer E2E, not the model."* A cross-layer E2E is a test,
  and no such test is recorded. This ADR adopts the decision and leaves the verification to T037 rather
  than closing U-03 on the strength of a column definition.
- **Migration numbering is contested.** `plan.md §Technical Context` and `research.md §1.1` both state
  the latest migration is `015_worldline_reconstruction`. **[MEASURED]** `apps/control-plane/db/
  migrations/versions/` contains `014` through `025`, latest `025_context_graph.py`. The documents are
  stale; T037 should re-record the true head.