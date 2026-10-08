# ADR-0031 — Locality boundary: pair and triple coherence, honestly claimed

**Status**: Accepted (Wave 0, ADR-025-04)
**Feature**: `025-context-reality-approximation-engine`
**Baseline**: v2 §7, §8, §9, §10, Appendix I.1–I.3, N.6

## Context

"Gluing" is the operation that makes a large investigation tractable: compare bounded local
sections and combine the compatible ones. The temptation is pairwise comparison, because
that is what a graph join does.

Pairwise compatibility does not imply coherence. Three sections can each agree with the other
two on the shared overlap — through different chains — and still be jointly inconsistent. In
sheaf language, pairwise compatibility of sections is not local-global compatibility on
overlaps; the cocycle condition on triple overlaps is a separate requirement.

Reporting `GLUED` on pairwise evidence alone would be a false structural claim about the
world, which is precisely what §0.2 forbids in the epistemic register and what the platform
exists to avoid.

## Decision

**1. Operational vocabulary only.** "Section", "restriction", "obstruction", "gluing" are used
in an operational sense defined by this ADR and the baseline. The platform does **not** claim
a sheaf library, a topos, or a formal local-global theorem. Sheaf-inspired means: attachment
maps give a closed-form structural kernel (ADR-0033), restrictions are monotone, obstructions
are first-class and durable.

**2. Blocking is mandatory and bounded.** All-pairs comparison is forbidden. Blocking keys:
same investigation, same temporal bucket, scope intersection ≠ EMPTY, shared entity, shared
source lineage, same geospatial tile, semantic-profile compatibility. `max_bucket_size` is a
declared budget parameter.

**3. Overflow is an obstruction, not a silent skip.** A bucket exceeding `max_bucket_size`
produces `BUCKET_OVERFLOW`, is counted, and raises a `ResearchObligation` to broaden the
blocking strategy. The oversized bucket is not processed.

**4. Typed restriction with a loss profile.** A restriction may reduce scope and may reduce
precision. It must never fabricate information. Every restriction records what it lost:
entities removed, relations removed, temporal precision loss, semantic precision loss.

**5. Triple coherence is checked, under budget.** For every triangle of the overlap graph,
restrict to the triple overlap and verify the pairwise-compatible restrictions agree there.
Triples are enumerated in stable id order up to `max_triples`; unchecked triples are counted
in `triples_unchecked` with a truncation reason.

**6. The verdict is honest about what was checked.**

```text
GLUED           only when triples_unchecked == 0 and no conflicts/unknowns
PARTIALLY_GLUED conflicts, unknowns, or unchecked triples
BLOCKED         conflicts and the profile forbids partial gluing
```

`GLUED` may never be returned while `triples_unchecked > 0`. This is a code-level guard, not
a convention.

**7. `BLOCKED` is not `FALSE`.** It means current evidence is insufficient to produce a
coherent merged section. The distinction is preserved in every API field and every UI label.

**8. Claims are scoped to what was verified.** Documentation and UI say "pair- and
triple-coherent under budget". Higher-order (`k>3`) coherence is out of scope and is never
implied. A v1 defect was the phrase "global coherence"; that phrasing is banned.

## Consequences

**Positive**

- The structural claim matches the evidence actually gathered.
- Genuine local-global failures surface as actionable obligations instead of silent merges.
- Overflow in a pathological corpus becomes visible rather than quadratic.

**Costs, accepted**

- Triple enumeration is superlinear in the overlap graph; `max_triples` and reporting are the
  price of not lying.
- `PARTIALLY_GLUED` will be the common verdict, not `GLUED`. That is the correct outcome, not
  a defect.

**Not changed**

- Scope intersection stays typed `EMPTY | PARTIAL | EXACT | UNKNOWN` and is never inferred
  from string equality.
- Compatibility keeps its per-dimension verdict vector (ADR-0033); the single verdict remains
  profile-derived.

## Verification

- [ ] Cells pairwise compatible but jointly inconsistent → verdict `PARTIALLY_GLUED`,
      obstruction `TRIPLE_INCONSISTENCY`, never `GLUED` (corpus case N.6).
- [ ] Property test: no code path returns `GLUED` when `triples_unchecked > 0`.
- [ ] Bucket over `max_bucket_size` → `BUCKET_OVERFLOW` recorded, obligation raised, bucket
      not processed.
- [ ] Property test: restriction cannot fabricate evidence — projecting then re-expanding
      never yields a fact absent from the source.
- [ ] Compatibility work grows with blocked candidate sets, not with cell count squared.
- [ ] A conflicting merge preserves both contributions and both remain independently
      inspectable.
- [ ] No API field, UI label or document uses the phrase "globally coherent" for this path.