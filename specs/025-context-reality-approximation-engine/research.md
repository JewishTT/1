# 025 Deep Research — Context & Dialectical Reality Approximation Engine

**Feature**: `025-context-reality-approximation-engine`
**Date**: 2026-10-04
**Purpose**: ground Specification 025 in (a) reusable prior art already inside this
repository, (b) external method literature, (c) an explicit register of design risk —
*before* any code is written, so that implementation reuses rather than reinvents.

**Status of this document**: research input to `/speckit.specify` → `/speckit.plan`.
It does not override the owner's specification. Where research contradicts the
specification, that is recorded as a **Risk** for the owner to decide, not silently
"fixed" here (§1.1 of `AGENTS.md`).

---

## 0. Method actually used, and its limits

Recorded honestly, because a research log that overstates its coverage is worse than
none.

| Channel | Status | Consequence |
|---|---|---|
| `websearch` (Exa MCP) | **HTTP 403 — provider refused every query** | No general web literature sweep was possible |
| arXiv API (`export.arxiv.org`) | Partially available, then **HTTP 429 rate-limited** | Only one literature thread completed (§2.1) |
| `webfetch` direct URL | Available | Used for the one successful arXiv query |
| **Donor mining inside the repo** | **Completed** | Primary method, and the repository's own doctrine (`AGENTS.md` §1) |

`AGENTS.md` §1 makes donor reuse the *default* method rather than a fallback. That the
only fully available channel happened to be the prescribed one is lucky, not a
substitute: §3 below is therefore a genuine inventory, while §2 is admittedly thin and
is marked as such.

**Consequence for planning**: §3 findings are binding inputs to the reuse analysis in
`plan.md`. §2 findings are indicative and must be re-validated with working search
before any decision that depends on the literature is finalised.

---

## 1. What 025 actually asks for, reduced to load-bearing questions

The specification is long because it enumerates objects. Stripped of enumeration, 025
makes **seven** load-bearing technical demands. Each is a place where a plausible
implementation can be quietly wrong, so each was researched.

| # | Load-bearing demand | Where it can go wrong | Researched in |
|---|---|---|---|
| Q1 | Local sections must combine into a coherent whole, or say precisely why not (§7–§10) | A "merge" that averages conflicts away, or a `BLOCKED` verdict misread as `FALSE` | §2.1, §3.1 |
| Q2 | Contradictions must persist without collapsing (§13, §23) | Four-valued state quietly degraded to boolean in one serialisation path | §2.2, §3.7 |
| Q3 | Explanations must compete and be ranked by declared complexity (§17) | "Highest score wins" — exactly the anti-pattern in §59 | §2.3, §3.2 |
| Q4 | Regime / change-point / causality must stay three separate claims (§25, §27) | One numeric metric promoted to a causal story | §3.6, §3.8 |
| Q5 | Structural/topological findings must not become identity or truth (§26) | TDA feature leak into the entity/truth path | §3.5 |
| Q6 | "Find all" must degrade honestly (§33, Appendix P) | Silent switch from exact to open-world | §3.3 |
| Q7 | Deterministic core with adaptive layer off, replayable (§4, §36, §48) | Nondeterminism entering through an unversioned dependency | §2.4 |

---

## 2. External literature (partial — see §0)

### 2.1 Sheaf formulations: what is actually reusable

Retrieved: **Hansen & Gebhart, "Sheaf Neural Networks", arXiv:2012.06333** (NeRips 2020
Workshop on TDA and Beyond), plus the surrounding sheaf-NN line (Bayesian sheaf NNs
arXiv:2410.09590; Gaussian sheaf NNs arXiv:2605.21435; order-equivariant generalisation
arXiv:2607.03798).

Two findings matter for 025, one positive and one cautionary.

**Positive — there is a deterministic kernel worth borrowing.** The sheaf Laplacian is a
generalisation of the graph Laplacian in which the attachment maps of a cellular sheaf
supply the relational structure. That gives a *closed-form, non-learned* structural
similarity between two local sections that is strictly more expressive than adjacency
counting: it handles relations that are non-constant across a domain, asymmetric, and
varying in dimension. That is precisely the operator class 025 §9.2 calls "structural
compatibility ... under declared tolerance", and §9.2's "provenance/causal" dimensions
have no comparable closed form.

**Cautionary — do not import the learned half.** In essentially all of this line the
stalk spaces and restriction maps are *learned* from data, and the Bayesian variant exists
precisely because the learned sheaf is sensitive and unstable under limited data. 025
P08 makes the adaptive layer subordinate and P09 requires rebuildability. A learned sheaf
therefore cannot be on the critical path of the deterministic core: it would make §36
replay impossible and would put a neural model in the structural-trust position that
§59 forbids.

**Concrete recommendation for `plan.md`**: implement structural compatibility as an
explicit, hand-specified sheaf-style operator over declared attachment maps
(`compatibility.operator.v1`, exactly as §9.1 names it), with the Laplacian as the
deterministic default and a declared-tolerance comparison; treat learned restriction maps
as an optional Tier-3 adapter behind the same operator contract (§30, §31).

This is *not* a claim that the platform has a sheaf library. §3.5 of the specification
explicitly forbids that claim, and nothing found here changes that.

### 2.2 Paraconsistency / four-valued support

Not retrieved — provider refused, then rate-limited. What §13 specifies
(`positive_support` / `negative_support`, with `(true,true) = BOTH`) is a faithful
operationalisation of Belnap-style paraconsistent truth, and 025's requirement that
`BOTH` coexist with a scalar `confidence` is the part most likely to be lost in
implementation. **Treat §13 as the authoritative internal specification**; no donor and no
retrieved paper may be used to "simplify" it.

### 2.3 Abduction, complexity, minimality

Not retrieved. §17.6 already gives the ranking formula and correctly refuses to equate
complexity preference with truth. The risk is implementation, not theory: a beam search
that returns near-duplicate explanations violates §17.7 and would look correct. Covered
as T025-059 and the §52.2 benchmark.

### 2.4 Determinism and replay

Not retrieved. §4 and §36 are self-contained and stricter than most published
reproducibility guidance (they demand byte-identical revision content with wall-clock
excluded from identity). Appendix G.2 enumerates the forbidden identity material. The
realistic failure mode is not philosophical but clerical: one operator reading
`datetime.now()` into a payload. Recommend an AST-level lint as part of the
documentation-sync work the owner already asked for.

---

## 3. Donor inventory (repository-internal, verified by file inspection)

Method: capability-keyword sweep over `donors/` and `tmp/` (Python, Markdown, notebooks,
Rust), then targeted per-donor inspection. Counts are **keyword hits in donor files**,
which establish *that a capability exists somewhere*, not that it is production-shaped.
Every row below is therefore a **candidate for engineering assessment**, and adopting one
still requires the reuse analysis `AGENTS.md` §1 demands before writing anything new.

### 3.1 Locality / gluing / hypergraph structure

| Donor | Evidence | Serves |
|---|---|---|
| `hypergraphx` (189 files) | `measures/s_centralities.py`, `measures/edge_similarity.py`, `measures/reducibility.py` | §8 structural compatibility over multi-relation sections; overlap similarity when a section is a hypergraph rather than a graph |
| `adversarygraph` | `anomaly_detection/docs-site/docs/statistical-anomaly-taxonomy.md`, `attack-statistical-anomaly-mapping.md` | §44 failure/uncertainty taxonomy; §26 anomaly vocabulary |

**Assessment**: no donor implements gluing-as-specified. §10 is genuinely new work. The
hypergraph similarity measures are reusable *primitives* for the pairwise comparison step
(T025-037), not for the gluing verdict (T025-040).

### 3.2 Belief dynamics, hypothesis competition, traces

| Donor | Evidence | Serves |
|---|---|---|
| `BeliefLandscapeFramework` (189 files) | `src/proposition/sliding_window.py` (heaviest hit file), `src/run_belief_extractor.py`, `src/core/trace_builder.py`, `docs/belief_field_theory_and_tests.md` | **Closest existing analogue to §15–§18.** Propositions over sliding windows → hypothesis lifecycle; `trace_builder` → §38 `DecisionTrace`; belief-field theory → §21 frontier dynamics |

**Assessment**: this is the highest-value donor for the epistemic half of 025 and should
be assessed *first* in `plan.md`, before T025-053..066 are estimated. Risk to check: a
belief-field model may be intrinsically scalar/aggregative, which would collide with
P05 (competing hypotheses must coexist) and with §13 (`BOTH` must be representable).
That is exactly the "donor defect that must be treated on transfer" case in `AGENTS.md` §2.

### 3.3 Identity, resolution, completeness

| Donor | Evidence | Serves |
|---|---|---|
| `estorides` (280 files) | `KNOWLEDGE_BASE.md` (largest single hit count in the sweep), `estorides_core/entity_resolution.py`, `estorides_core/intel_resolver.py` | §33 completeness semantics, §8/§23 identity dimension of compatibility, source-independence assessment |
| `adversarygraph` | `backend/app/services/outbox_engine.py`, `backend/alembic/versions/*` | §39 durable reasoning-run recording pattern |

**Assessment**: `estorides` was already mined by spec 022. Reuse conclusions from that
spec should be carried forward rather than re-derived — this is the third feature to
touch identity, and the owner has an explicit anti-goal against a second truth model
(P12, §59).

### 3.4 Semantics / ontology

| Donor | Evidence | Serves |
|---|---|---|
| `DIMA-OntoToolkit` (58 files) | `src/dima_otk/owl/owl_dima_converter.py`, `owl_influencemini_converter.py`, `data/4.1-domain_signature_classifier_bootstrap.py` | The 12 declared ontology types; §29 open-world semantics; `semantic_regime_ref` as a versioned object |

### 3.5 Topology / persistence

| Donor | Evidence | Serves |
|---|---|---|
| `Raphtory` (223 files) | `raphtory/src/python/graph/properties/temporal_props.rs`, extensive temporal filter tests | §24 temporal reasoning over graphs; window materialisation (T025-048) |
| `ABa-KiTo` | `004-topological_analyisis/*N3intervals*`, `*N4intervals*` graph-analysis notebooks | §26 TDA series on worldline snapshots |
| Platform's own `apps/projection/tda` + `apps/science/scitda` | already implemented and benchmarked | §26 is largely **done**; 025 consumes it (I.7/T025-081) |

**Assessment**: 025 §26 is the one section where the platform is *ahead* of the donor
landscape. The correct move is integration and boundary enforcement — proving TDA output
cannot reach identity or truth — not reimplementation.

### 3.6 Dynamics / regime / phase transition

| Donor | Evidence | Serves |
|---|---|---|
| `cognitive_phase_transitions` | `scripts/cognitive_phase_transition.py`, `README.md` | §25 order parameters, phase-transition *candidate* criteria |
| `ABa-KiTo` | `robustness_checkup.ipynb`, `state_space_exploration.ipynb`, ISOKANN-based simulations | §12 observation model / state estimation; Koopman-style operator discovery |
| `social-oscillation-model`, `Entropic-Dynamics-of-the-Universal-Equivalent`, `votranhabysscoremicro` | small but on-topic | Regime/oscillation descriptors |

**Assessment**: this is the second-highest-value donor cluster after
`BeliefLandscapeFramework`. §25's insistence that change point ≠ regime change ≠ phase
transition ≠ causal explanation maps onto exactly the distinctions these donors must
already make to be useful. Whether their code makes them *explicitly* is the question to
answer during assessment.

### 3.7 Contradiction handling

Keyword sweep across all donors for
`paraconsist|belnap|four-valued|truth maintenance` returned **zero** substantive hits.

**Assessment**: §13 and §23 are greenfield. This is the clearest case in 025 where the
platform has no prior art and must author the algebra itself — with the corresponding
obligation to test it against a truth table (Appendix U, Wave 1 exit gate), not against
a donor.

### 3.8 Causal inference

No donor offers identification/estimation/refutation staging. §27's three-stage split
(IDENTIFICATION → ESTIMATION → REFUTATION) and its refusal to hide a failed stage behind
a single confidence field has **no donor precedent** in this repository.

**Assessment**: greenfield, and the highest-risk section per unit of value — see R4.

### 3.9 Strategic / narrative

| Donor | Evidence | Serves |
|---|---|---|
| `NarrativeDiffusion` | `analysis/graphs_ic2s2.ipynb`, `small_world_analysis.ipynb`, daily/weekly correlation analyses | §28 narrative/strategic layer; source-diffusion lineage |
| `MicroWorld`, `io-coordinated-replies`, `SYNINT`, `YᴜLaN-OneSim` | simulation and signal corpora | §28 actor-configuration hypotheses; §52 benchmark fixtures |

### 3.10 Query / search surface

`spiderfoot` (706), `theHarvester` (267), `sherlock`, `maigret`, `coldreach`, `Sublist3r`
and the platform's own 145-source catalogue serve §32/§33 acquisition side. 025 does not
need a new collector; it needs the completeness *protocol* (Appendix P) wrapped around
what already exists.

---

## 4. Risk register — findings that need an owner decision or a plan mitigation

These are ordered by expected cost of being wrong.

**R1 — `asyncio_mode` class of bug, recurring at config scope.**
While preparing 025 I found that this repository has already shipped one instance of a
whole class of defect: behaviour that was correct in one invocation scope and wrong in
another, because configuration is resolved from the *common ancestor* of the arguments
rather than from the repository root. 025 introduces **seven new applications' worth of
paths** (§1.2 placement) and a large operator registry (§30). Any per-package pytest or
tool configuration added during implementation will reproduce the failure mode.
*Mitigation*: `plan.md` must require that every new package's tool configuration be
verified from the repository root, and the AST/lint work the owner already requested
should cover this class.

**R2 — the specification's own volume is the largest single risk.**
§56 enumerates 129 tasks and Appendix T enumerates 68 requirements, but §58.1 states 025
"must not redefine" 024's approved semantics for `InvestigationContext`,
`ContextRevision`, `ResearchObligation`, `ResearchAction`, `ContextFrontier`. Those
objects **already exist and are now async and durable** (verified: contract, in-memory
store, PostgreSQL store, engine, `CognitiveLoop`, and a working
investigation → context → question → obligations → frontier → replay path).
*Risk*: an implementer treats §56 as a greenfield build list and rebuilds what is
already correct, or worse, forks it.
*Mitigation*: `plan.md` must contain an explicit **adoption matrix** mapping each
existing 024 object to its 025 role, marking reuse / extend / forbidden-to-touch. Nothing
in §56 that already exists should be re-implemented.

**R3 — four-valued truth will leak.**
`BOTH` (§13) must survive serialisation, API, UI and projection paths. The cheapest
implementation drops it in exactly one of them, and the failure is invisible because the
system still returns numbers.
*Mitigation*: the §52/Appendix U Wave 1 truth-table gate is a **release gate**, not a
test; require a property test asserting no code path maps `(true,true)` to `true`.

**R4 — causal staging is the most likely source of a false claim.**
§27.3 requires `NOT_IDENTIFIED` rather than `causal_effect = 0`. There is no donor and no
retrieved literature to defer to. Combined with §59's explicit ban on "TDA → causality"
and "centrality → importance truth", this is where a plausible-looking number would do
the most damage.
*Mitigation*: implement §27 as three separately persisted evaluations from the start.
Do not add a convenience "causal score" field later; §27.2 forbids it.

**R5 — complexity ranking invites the "just take the top score" collapse.**
§17.6 gives a formula and §17.7 requires diversity. Beam search plus a scalar ranking
reproduces precisely anti-pattern V.5 ("Abduction = choose highest score"), which the
specification itself rejects.
*Mitigation*: make `rejected_candidates` and `truncation_reason` mandatory fields
(§17.4 already does) and require the §52.2 near-duplicate cases in the golden corpus.

**R6 — glossary collision with 024 and 017.**
025 uses "context", "cell", "restriction", "regime", "saturation", "frontier". 024
already owns `InvestigationContext`/`ContextFrontier`/`SaturationState`; 017 owns
semantic lookup. §55 Wave 0 exists precisely to freeze this and has **not** been done —
the seven ADRs it calls for are absent from `docs/adr/`.
*Mitigation*: Wave 0 is a real gate with a real exit criterion ("no unresolved
contradiction between 024 and 025 terminology"). Do not start Phase A before it closes.

**R7 — unversioned dependencies defeat §36 replay.**
Appendix Q.2 states a floating dependency is insufficient for a scientific fingerprint.
The repository has no lockstep pinning for donor-derived numeric stacks, and 025 will
pull in TDA/Koopman-style code where this bites.
*Mitigation*: `MethodFingerprint` (§Q) must resolve to concrete versions from the moment
the first operator is registered, not retrofitted.

**R8 — repository constitution is an unmodified template.**
`.specify/memory/constitution.md` still contains `[PROJECT_NAME]`, `[PRINCIPLE_1_NAME]`
and every other placeholder. The repository therefore has **no enforceable
spec-kit-level constitution**, while `AGENTS.md` carries the real doctrine in prose.
*Risk*: a `/speckit.constitution` run would overwrite or conflict with `AGENTS.md`.
*Mitigation*: decide explicitly whether the constitution is generated from `AGENTS.md`
before running further speckit governance commands.

---

## 5. Inputs this research hands to `/speckit.plan`

1. **Reuse-first task ordering.** Assess `BeliefLandscapeFramework` (§3.2) and the
   `cognitive_phase_transitions` + `ABa-KiTo` cluster (§3.6) before estimating T025-053
   through T025-066 and T025-049 through T025-052 respectively.
2. **Adoption matrix against 024 is mandatory** (R2).
3. **The genuinely greenfield, high-risk items** are: four-valued truth and contradiction
   lifecycle (§3.7), causal staging (R4), gluing/obstruction (§3.1), and the completeness
   protocol (§3.10). These deserve the largest estimates and the most review.
4. **Already-done territory**: TDA (§3.5). Integrate and fence; do not rebuild.
5. **Wave 0 is a gate, not a formality** (R6), and the ADRs it names do not yet exist.
6. **Configuration-scope verification is a standing review item** (R1).

---

## 6. Honest statement of coverage

- Repository donor inventory: **complete for the capability keywords searched**, but
  keyword presence is not fitness. Every §3 row still needs the reuse analysis.
- External literature: **1 of 4 planned threads completed.** `websearch` was unavailable
  (HTTP 403) and arXiv rate-limited (HTTP 429). §2.2–§2.4 are therefore reasoned from the
  specification, not from sources, and are labelled as such.
- Specification review: read in full. No arithmetic or structural defect was found in
  §0–§61; the identified risks are integration and discipline risks, not errors in the
  document.