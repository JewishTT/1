# ADR-030-05 — The existing lexical path stays default; RRF is a clean-room comparison candidate; vector is an optional profile

- **Status**: Accepted
- **Date**: 2026-10-17
- **Feature**: `030-global-platform-upgrade`
- **Implements**: T020
- **Cites**: FR-061, FR-110, Constitution P5, P12, ADR-0034, ADR-0037
- **Recorded clean-room basis**: `specs/029-research-closed-loop-upgrade/donors/donor-matrix.md §1`

## Context

FR-061 requires that candidate discovery, candidate expansion, relevance scoring, rank fusion, action
utility and policy decision "remain distinct operations with distinct metrics and provenance; a single
untyped score MUST NOT represent all of them" (`spec.md:383-385`). So the retrieval pipeline has a
named fusion slot, and the design question is what fills it.

**[MEASURED]** The lexical baseline exists and is declared. `apps/projection/pyproject.toml:14`
declares `bm25s>=0.2` and `:16` `duckdb>=1.0`. `apps/projection/search/` contains `bm25s_backend.py`,
`index.py`, `indexer.py`, `mappings.py`, `projector.py`, `publisher.py`, `quickwit.py`,
`relevance.py`, `tantivy_backend.py`.

**[MEASURED] No vector or ANN dependency exists in any workspace member.** A search across every
member `pyproject.toml` plus the root and `bench` manifests for `pgvector`, `chromadb`, `faiss`,
`qdrant`, `annoy` and `hnswlib` returns **zero hits**. This is the fact `research.md §1.2` point 2
records and it is the reason the vector arm is an optional profile rather than a baseline arm.

**[MEASURED] RRF already exists in-tree and is already called.** `reciprocal_rank_fusion` is defined
at `apps/shared/scoring/fusion.py:189` and is called from two production sites:
`apps/control-plane/services/query_planner.py:303` and `apps/interpretation/retrieval/retriever.py:225`
(with the `merge="rrf_any"` entry point at `retriever.py:164` and the route default at
`api/routes/fabric.py:140`). `apps/interpretation/tests/test_retriever_fusion.py:1` records why it is
shared: *"The local RRF copy was three separate bugs; the shared contract forbids all three."*

That last fact changes what this ADR can honestly claim. `tasks.md` T095 describes implementing RRF
clean-room in `apps/shared/scoring/fusion/` as a new comparison candidate. Measured reality: the
function is implemented, live, in a **module** (`fusion.py`) rather than the **package** T095 names,
and it has already absorbed a consolidation. This ADR does not treat that as a green light for RRF as
*default*. It records that the candidate exists, is shared, and is still unbenchmarked against the
lexical path on a judged set.

**[MEASURED] The clean-room basis is verified.** `donor-matrix.md §1` records, verbatim: for
**ranknexus**, *"Only `kprabhu-github/landingpage` ("ranknexus lp", 0?, **no licence**). Not a
project."* For **fuse** (RRF / rank fusion): *"**No rank-fusion library named `fuse` exists.** 39
unrelated `fuse` repos: JS fuzzy search, Go filesystem, sensor fusion, ESB, functional language."*
Verdict for both, and for seven others: *"REJECT - not integrable on the name given."* The other seven
are QUANTA, IntelShed, worker-browser, Stablerank, OptLLM, lcc and nax.

So the fusion candidates named in the source specification **do not exist**. Nothing may be added as a
dependency under those names. The RRF in `apps/shared/scoring/fusion.py` was built from the published
algorithm, and it is labelled `clean-room-inspired` — it is **not** donor code, and calling it donor
reuse would be false.

## Decision

**D1 — The existing lexical path (BM25) stays the default.** It is declared, tested and measurable
today. A default is changed only after a frozen judged query set exists and the comparison is written
up, whatever the comparison says — including "current path retained" (`tasks.md` T097 makes the
recorded decision the deliverable, not a promotion).

**D2 — RRF is a comparison candidate, built clean-room, and is labelled as such.** It is not donor
code, because `ranknexus` and `fuse` were verified non-existent (§1 of the donor matrix). It is not
promoted to default on the strength of existing code. It stays labelled `clean-room-inspired` wherever
it appears, including in the benchmark write-up.

**D3 — No vector dependency is added, and vector retrieval is an optional profile.**
`research.md §2.5` rejects adding one now: *"That is new runtime, new dependency, new licence and new
operational burden before a baseline exists — forbidden by FR-110."* `plan.md §Complexity Tracking`
repeats it: *"a dependency in `pyproject.toml` is not an integration."* Measured support: no vector
dependency exists in any workspace member today. If one is added later it arrives as a profile behind a
switch, with its own licence entry, its own benchmark, and the lexical path still runnable.

**D4 — Fusion is a distinct operation with its own metric and provenance.** Per FR-061, the fused
ranking records which rankers contributed and how. A fused score that cannot be attributed to its
inputs is a violation, not a simplification.

**D5 — No untyped scalar crosses the fusion boundary.** The component vector is retained; a composite
carries its policy version (constitution P5). Fusion policy is versioned, so a ranking change is
attributable to a policy id rather than to a diff.

**D6 — The judged query set is frozen before any comparison is run.** T085 builds it; T094 measures the
current BM25 path first. T093 builds the harness. "Do not change retrieval before this number exists"
is a sequencing rule, not a preference.

## Why not the alternatives

**A — Make RRF the default fusion now.** Rejected. The specification explicitly forbids treating RRF as
a universal truth (`research.md §2.5`), and shipping a default before the frozen judged set exists is
the "no baseline, no claim" violation this programme exists to prevent. The existence of working RRF
code is not a measurement of whether it beats BM25 on our query classes.

**B — Add a vector/ANN stack now to make the benchmark complete.** Rejected: no vector dependency
exists in any member (measured), and adding one before a baseline violates FR-110 directly. The cost
is not the dependency, it is that a vector arm evaluated against no baseline produces a number nobody
can interpret.

**C — Adopt a rank-fusion donor (`ranknexus`, `fuse`).** Rejected: both were verified non-existent
(`donor-matrix.md §1`). There is nothing to adopt on the name given. This is a verified finding, not an
unresolved search.

**D — Keep the three separate RRF implementations and benchmark each.** Rejected, and this one is
already closed by history: `test_retriever_fusion.py:1` records that the local copy was *"three
separate bugs"* that the shared contract forbids. A shared implementation with one set of tests is the
correct end state and it exists.

**E — Delete RRF until the benchmark lands, to avoid it being mistaken for the default.** Rejected: it
is called from two production sites, and removing a live code path is a larger change than labelling
it honestly. The label is the cheap, correct fix.

**F — Write a second RRF in `apps/shared/scoring/fusion/` as T095 literally specifies, as a fresh
clean-room comparison candidate.** Rejected. The function is at
`apps/shared/scoring/fusion.py:189`, shared, and already the consolidation of prior copies. A second
implementation would reintroduce exactly the defect `test_retriever_fusion.py` documents. T095's path
should be corrected to `apps/shared/scoring/fusion.py` and its scope narrowed to *benchmark the
existing shared RRF*, not to reimplement it.

## Consequences

**Positive**

- The default is the thing that already works and can be measured, so the first benchmark has a real
  baseline instead of a notional one.
- The clean-room label is honest and traceable: anyone reading `fusion.py` can find the `donor-matrix`
  §1 rows that explain why no donor code exists behind it.
- D3 keeps the dependency surface frozen. No new licence, no new runtime, no new operational burden,
  and the lexical path stays runnable regardless of what anyone adds later.

**Costs, accepted**

- The retrieval arm is narrower than the source specification asked for. `plan.md §Complexity
  Tracking` records this as a deliberate, reversible narrowing: SC-011/SC-012 measure *the platform's*
  evidence yield, not a named library's presence.
- RRF stays unpromoted and unmeasured until T085/T093/T094/T097 complete, so a working capability sits
  idle. Accepted: an unmeasured promotion is the failure this ADR exists to prevent.
- The fusion provenance required by D4 is real storage work that buys nothing until the benchmark
  exists.

**Not changed**

- ADR-0034 (global search completeness) and ADR-0037 (ranking policy, no multiplicative utility)
  stand.
- The existing `apps/projection/search/` layout is untouched by this ADR.
- No dependency is added or removed by this ADR. It records that giotto-tda was removed elsewhere
  (see ADR-030-09).

## Verification

- [ ] The default retrieval path resolves to BM25 with no profile flag set.
- [ ] The RRF implementation is at `apps/shared/scoring/fusion.py:189` and is the only fusion
      implementation in the tree — one `def reciprocal_rank_fusion`, not two.
- [ ] Any document describing the RRF path states `clean-room-inspired` and names
      `donor-matrix.md §1` as the reason.
- [ ] No `pgvector`, `faiss`, `qdrant`, `chromadb`, `annoy` or `hnswlib` appears in any workspace
      member's `pyproject.toml`.
- [ ] A fused result records which rankers contributed and under which policy version (D4, D5).
- [ ] `benchmarks/retrieval-comparison.md` exists with an identical query set, budget and source
      universe on both arms, and records a decision **either way** (T097).
- [ ] No named donor from `donor-matrix.md §1` appears in any dependency manifest.

## Open

- **The judged query set and the BM25 baseline number do not exist.** T085 builds
  `bench/fixtures/global_upgrade/retrieval/`; T093 builds the harness; T094 measures the current path
  and states *"Do not change retrieval before this number exists"*; T097 writes the comparison.
  None has run. This ADR therefore decides the *default* on the basis of what is declared and callable
  today, and makes **no** claim about which arm performs better.
- **`benchmarks/retrieval-comparison.md` does not exist** — there is no `benchmarks/` directory in the
  tree at all.