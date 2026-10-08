# ADR-0035 — Temporal algebra: 13 Allen relations over disjunctive sets

**Status**: Accepted (Wave 0, ADR-025-08)
**Feature**: `025-context-reality-approximation-engine`
**Baseline**: v2 §24, §12.4, Appendix G.2, T025-140, T025-148

## Context

The platform has six authoritative time axes and an existing temporal materialisation
(spec 014). What it lacks is an **interval algebra** — and without one, "A happened before B"
is a string comparison rather than a reasoned relation.

v1 listed eight relations (BEFORE, AFTER, OVERLAPS, MEETS, DURING, STARTS, FINISHES, EQUAL,
UNKNOWN), which is not a coherent set: it mixes inverses inconsistently and omits
`MET_BY`, `OVERLAPPED_BY`, `STARTED_BY`, `CONTAINS`, `FINISHED_BY`. Worse, it treated a
relation as a single value, while real data with imprecise endpoints genuinely admits several
relations at once.

## Decision

**1. Allen's 13 basic relations, complete and closed under converse.**

```text
BEFORE      AFTER
MEETS       MET_BY
OVERLAPS    OVERLAPPED_BY
STARTS      STARTED_BY
DURING      CONTAINS
FINISHES    FINISHED_BY
EQUAL
```

**2. A relation value is a non-empty subset of the 13, not a single relation.**

```text
singleton        definite relation
multiple         disjunctive — several hold under admissible endpoint values
full set of 13   UNKNOWN
empty            INCOMPATIBLE on the temporal dimension
```

Imprecise endpoints (§24.5 precision) are the main source of multi-valued relations. Point
events are degenerate intervals. This is the honest representation: collapsing a set to one
member asserts more than the data supports.

**3. Three table-driven operations, all deterministic.**

```text
converse(r)          inverse of each member
intersection(a, b)   a ∩ b; empty ⇒ INCOMPATIBLE
composition(a, b)    Allen's composition table, used for path consistency
```

No heuristics, no learned component. The tables are finite and testable exhaustively.

**4. Path consistency over bounded temporal networks**, with declared bounds. Unbounded
network reasoning is not attempted.

**5. The six axes remain authoritative.** Every temporal verdict names the axis or axis pair it
was computed on. No seventh axis. Derived relations are relations *about* the axes, not new
axes.

**6. Provenance on every relation.** `OBSERVED | DECLARED | DERIVED | INFERRED | UNKNOWN` —
carried with the relation, so a consumer can tell a recorded ordering from an inferred one.

**7. Precision travels with the relation.** `EXACT | DAY | WEEK | MONTH | YEAR | INTERVAL |
ORDER_ONLY | UNKNOWN`. A relation derived from `ORDER_ONLY` evidence is stored as such.

**8. Late data never mutates the past.** A late event recomputes the affected dependency
subgraph and produces a new revision with a supersession record (ADR-0030).

**9. Baseline estimator is interval constraint propagation, not a Kalman filter.**
`T025-148`. Each state variable carries an interval or finite-set domain; unobserved starts
unbounded = `UNKNOWN`. Observations narrow by unit-aware, tolerance-aware intersection.
Declared constraints propagate to a fixed point in canonical constraint order. An empty domain
yields `INCONSISTENT` with a minimal conflicting set as residual — nothing is dropped.
Unbounded domains stay `UNKNOWN` and are never defaulted to zero.

This is deliberate. A filter implies a dynamical model the platform does not have; it would
produce confident numbers from a linear assumption nobody declared.

## Consequences

**Positive**

- "A before B" becomes a derived, inspectable relation with provenance.
- Imprecise data yields an honest relation set rather than a false singleton.
- Contradictory temporal constraints surface as `INCONSISTENT` plus a residual.

**Costs, accepted**

- Relation values are sets, so storage, indexing and comparison are heavier than an enum.
- Path consistency is bounded and will not always close a network; that is reported.

**Not changed**

- The six axes and the existing materialisation.
- Entity identity. Temporal reasoning reads worldline snapshots; it never rewrites identity.

## Verification

- [ ] Exhaustive: all 13 × 13 converse and composition table entries verified.
- [ ] Intersection of disjoint relations → `INCOMPATIBLE`; of a set with itself → itself.
- [ ] `converse(converse(r)) == r` for all 13 and for all 8191 subsets.
- [ ] Composition is consistent with converse (property test).
- [ ] Imprecise endpoints yield multi-valued relations, not a forced singleton.
- [ ] Every stored relation names its axis and its provenance class.
- [ ] Empty feasible set → `INCONSISTENT` with a non-empty minimal residual; nothing dropped.
- [ ] Unbounded variable stays `UNKNOWN` after propagation.
- [ ] A late event produces a new revision and a supersession record; the prior revision is
      byte-identical to before.