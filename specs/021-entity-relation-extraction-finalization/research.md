# Phase 0 Research: 021-entity-relation-extraction-finalization

**Date**: 2026-09-27 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

Every finding below was read out of the repository at HEAD `0056665`, not assumed. Where a
decision is still open it says so and says who must decide it.

---

## R-000. Baseline, recorded before any change

Command form: `uv run --project apps/<app> pytest apps/<app>/tests -q`.

| Suite | Result at HEAD |
|---|---|
| `apps/projection` | 189 passed, 1 skipped |
| `apps/acquisition` | 126 passed, 10 skipped |
| `apps/interpretation` | 185 passed |
| `apps/admission` | 96 passed |
| `apps/control-plane` | 356 passed, **2 failed**, 9 skipped |
| `apps/shared` | 571 passed, **14 failed**, 8 skipped |

The 2 control-plane failures are `test_donor_api`. The 14 shared failures are the pre-existing
baseline. **These 16 failures are the floor.** No commit in this feature may increase that
number, and "green" is not a claim that may be made while a new failure hides among them
(FR-081).

There is **no CI** (`.github/` does not exist), no Makefile, no tox/nox. The only recorded
baseline in the repo is `docs/quickstart-validation.md`, dated 2026-09-17, which predates
specs 016–021. The gate is therefore manual and must be re-run and reported per phase.

---

## R-001. Parser capability and determinism (was an open question)

**Decision: keep the lexical layer on text, move the structural producers onto a real DOM.**

What is installed and available: `selectolax>=0.3.21` (declared by
`apps/interpretation/pyproject.toml`, installed — a Lexbor-based HTML5 parser),
`trafilatura>=1.12`, `extruct>=0.17` (metadata/JSON-LD), plus `lxml`, `html5lib`, `soupsieve`
and `bs4` present transitively in `.venv`. `apps/interpretation/parsers/html_full.py` exists.

The decisive finding is that the 019 producers **do not use a DOM at all**. They run regexes
over raw markup:

- `lexical.py` calls `extract_cue_sites(text)` on the text body.
- `links.py` uses `_ANCHOR`/`_HREF`/`_TAG` regexes and strips tags by substitution.
- `tables.py` distinguishes `<th>` from `<td>` by `cell.group(0).lower().startswith("<th")`
  and picks the header row by *counting the most `<th>` cells* — a labelled heuristic
  published as `precision="exact; header row chosen by most <th> cells (a heuristic)"`.
- `metadata.py` uses `_META`, `_ATTR`, `_BYLINE`, `_ATTRIBUTE`, `_LD_SCRIPT` regexes and a
  `json.loads` for JSON-LD.

So determinism is currently fine — regexes are deterministic — and the real cost is
*structural fidelity*. That produces the specific defects in the spec: the header heuristic,
the `zip(..., strict=False)` truncation, `precision="exact"` on a heuristic, and positional
header↔cell pairing that silently drops width-mismatched rows.

**Why the DOM is the right move anyway, and it is forced rather than chosen:** FR-094 and
FR-103 require every producer to cite a real mention id resolved in a mention index, and
require the `surface:`/`header:`/`cell:`/`attribute:` fabrications to be gone. Mentions need
stable character offsets into a text stream. Deriving those from a regex match inside raw
markup means re-deriving them differently per producer, which is precisely how the current
inconsistent ids were born. One DOM pass, one text stream, one offset space, resolved by one
mention index is the only construction in which all producers agree on what a mention is.

**Determinism requirement on the DOM:** `selectolax` is chosen over `lxml`/`html5lib`
because it is a single-pass spec-compliant HTML5 parser with a stable tree construction, and
because it is already a declared dependency of the app that owns the parsers. Whichever
parser is used, the corpus MUST record a tree-construction digest per fixture so a parser
change is a visible diff rather than a silent corpus shift.

**Stop condition still armed (FR-082):** if a fixture's tree construction cannot be made
deterministic, that fixture is reported `UNSUPPORTED` with the reason. It is not made
deterministic by seeding, retrying or ignoring the diff.

---

## R-002. `PredicateSignature` — the identity decision

**Decision: a signature is a structural, normalised projection of a reading, and it is the
sole predicate term in `logical_candidate_id`.**

`PredicateSignature` does not exist anywhere in the repository today (0 matches, whole repo,
including tests and migrations). The existing near-misses are not sufficient:

- `PredicateHypothesis.normalized_form` exists but is inert: `__post_init__` sets it to
  `str(self.normalized_form or self.surface_form or "")`, so it is a verbatim copy of the
  surface. There is no normalisation function in the module and none in `domain/` or
  `semantic/`.
- `PredicateHypothesis.content_key()` is a 32-hex-char digest of six fields. It is a *content
  address of one specific reading*, not a normalised form shared across realisations.

The signature therefore carries, and only carries: normalised predicate, normalised argument
shape, arity, role names, direction, polarity. It does **not** carry `relation_ref`, and it
does **not** carry the raw surface.

Consequences that must be honoured everywhere:

1. `relation_surface` leaves `_logical_material()` entirely and becomes revision/evidence
   material (FR-005, FR-007). An active and a passive realisation then share one
   `logical_candidate_id` (User Story 2), which is currently false.
2. The signature is **durable in its own columns**, not a digest (FR-087). A digest may
   identify data; it may not be the only copy required for reconstruction (FR-060).
3. An unrecognised predicate produces a signature with a normalised form and
   `resolution_state=UNKNOWN`, and `relation_ref=None`. It is a first-class hypothesis, not a
   gap. `material_requires_resolved_predicate` remains the correct CD-6 line: a candidate may
   be untyped, a material may not.
4. **The signature is derived before ontology mapping, not after.** Mapping to a known
   operator is a later, versioned step. This is what keeps an open relation space open.

**The tension to be aware of:** a normalised form that is too aggressive merges distinct
relations; too weak and it reproduces the surface-fragmentation defect in normalised clothing.
The rule set is therefore recorded in `data-model.md` and every rule is individually tested,
because the whole feature rests on this one function.

---

## R-003. Bounded type vocabulary, open relation space

**Decision: implement §104 exactly — bounded versioned *type* space, unbounded *relation*
space — with the vocabulary as a mapping instrument, never as an extraction gate.**

Verified state at HEAD:

- There is **no** `core:*` or `value:*` constant anywhere in `apps/`.
- There is **no** class named `*Vocabulary`, `*TypePack` or `*TypeCanonical` anywhere.
- The only `OntologyPack` in the repo is `apps/shared/events/ontology_pack.py`, and its
  `allows_relation()` is **never called anywhere**. Its `relations` default is
  `["works_at", "owns", "controls", "corresponds_to", "linked_to"]` — a fixed relation list,
  which is exactly what §104 forbids as a *requirement*. The pack is documented as advisory
  and is only used via `allows_type()` by `extractors/registry.py`.
- `RelationRef` explicitly disclaims ontology membership: there is deliberately no `domain`,
  `range` or `allowed_types` field (`semantic/contracts.py:404-412`).
- `relation_type` is free-form text at every layer; the only check is non-empty
  (`relation_claim.py:230`).
- `TypeHypothesis` today is thin (`semantic/blocking.py`) and `TypeAssertion` carries a single
  hypothesis, not competing ones.

**Therefore:** `OntologyPack.relations` is inert and stays inert; it is not the vocabulary.
The new bounded vocabulary governs *entity and value types* only, is versioned, is extensible
by hierarchy, and an unmapped type yields `UNKNOWN` — never rejection, never a drop
(FR-030…FR-034a). A non-empty, non-vocabulary `relation_type` continues to be legal; what
changes is that a claim is minted from a *signature*, and the signature records the mapping
state explicitly.

---

## R-004. Production wiring

**Decision: wire into `services/capture_interpretation.py::interpret_warc_capture` (FR-100).**

The audit found `run_until`/`run_golden_path` have no production caller. It also found the
seam is already built and already live:

```
POST /api/v1/entities
  -> services/entity_pipeline.py::run_live_entity_pipeline      (in-process branch)
  -> services/temporal_materialization_dispatch -> Temporal
     workflows/temporal_materialization.py::reconcile_and_publish
  -> services/capture_interpretation.py::interpret_warc_capture  <-- the single choke point
```

`capture_interpretation.py` today runs the 007-era `RelationExtractor` + `WarcIntake`. Both
production branches already funnel through it, so **one edit covers both**. The Temporal
worker is registered (`workflows/worker.py:20-25`, task queue
`cognitive-temporal-materialization`) and the route is confirmed live in `api-live.out.log`
(`POST /api/v1/entities HTTP/1.1" 202 Accepted`).

Two facts make this cheap and must be recorded:

- `ExecutionRequest.producers` is declared and **never assigned by anyone** — so
  `run_producer` currently iterates zero times on every run. Populating it is what makes the
  producers run at all.
- `lexical_signals` — the primary prose producer — **has never been called by anything in the
  repository**, not even the corpus.

`run_producer` is in the **interpretation** app, while `run_until` is in **control-plane** and
would sit in the same function. That is a cross-app import which the workspace permits
editable, but it is the *wrong* direction. Cleaner: producers run in
`interpret_warc_capture` and hand their signals to the assembler through the same seam, rather
than having interpretation import control-plane's lifecycle. Recorded here because it is a
layering decision the brief does not make and a reviewer will otherwise re-litigate it.

---

## R-005. Migration strategy

**Decision: migration `021`, forward-only, on top of `020`.**

`020_universal_relation_extraction` is the current **Alembic head** (`down_revision =
"019_world_substrate"`, 7 files in `versions/`, no successor) and its `downgrade()` raises
`NotImplementedError` by design. `020` MUST NOT be edited. There is already a test asserting
ORM/migration parity for it, so new columns must be added in both places.

`021` adds, per FR-087/FR-088/FR-096: `predicate_signature` columns on `relation_signal` and
`relation_candidate` (normalised form, arity, role names, argument shape, direction, polarity);
`signal_refs`, `direction`, `polarity`, `confidence` on `relation_candidate`; `candidate_id` on
`relation_claim`; structured columns for `PredicateHypothesis.alternative_refs` and
`mapping_evidence_refs`; and a repository/writer/reader for `relation_signal`,
`relation_candidate` and `source_temporal_observation`, which today have **no repository
class at all** — no `INSERT` for any of the three exists anywhere in `apps/`, `bench/` or
`tools/`.

`SqlRelationClaimStore` (558 lines) has zero importers and its `record_validation`/`non_valid`
raise `NotImplementedError` because migration 016 never created a JSONB home for a verdict.
`021` must either give the verdict a home or that store stays unusable — recorded as a real
decision, not an oversight.

**Live PostgreSQL is not reachable in this environment.** All DB verification is therefore
offline: ORM/DDL parity, in-memory round trip, and migration text assertions. Anything needing
a live round trip is reported `verified only offline` and never as `verified` (FR-084).

---

## R-006. Live graph backend

**Decision: out of scope to switch backends; in scope to make rebuild-from-store real.**

`neo4j>=5.21` is declared in `apps/control-plane/pyproject.toml` but `apps/projection`, which
contains `graph/neo4j.py`, does **not** declare it. `graph/neo4j.py` **never imports the
`neo4j` package** — it takes an already-built driver object. `neo4j_uri`/`neo4j_user`/
`neo4j_password` in `apps/shared/config/settings.py:59-61` are read by nothing. A compose
service runs `neo4j:5-community` and nothing connects to it. `Neo4jGraphStore` and
`RebuildableGraphStore` both have zero production callers; `InMemoryGraphStore` is the only
wired store, held by `SearchProjectionRegistry` in `services/search_backends.py:821`.

Constitution III makes projection-first a first-class principle, and "the graph is
rebuildable from the stores" is currently unproven because no store is written. The minimal
honest step for 021 is: write the stores (R-005), then make the rebuild path exercised by a
test that writes → projects → rebuilds → compares, against `InMemoryGraphStore`. Switching the
production default to Neo4j is a separate change and is **not** taken here; it would trade one
unwired integration for another without advancing the constitution.

---

## R-007. Open questions, and who must answer them

| # | Question | Why it is open | Answerable by |
|---|---|---|---|
| Q1 | Exact `PredicateSignature` normalisation rule set | The whole identity model rests on it; too aggressive merges distinct relations, too weak reproduces surface fragmentation | Phase 1 `data-model.md`, with one test per rule |
| Q2 | Controlled type-space vocabulary vs free-form strings | The brief allows both. A controlled vocabulary gives blocking/matching/validation; free strings never reject | Phase 1, recorded as an ADR (§100 decision D/E) |
| Q3 | Bounded-neighbourhood scope definition | Producers must report scope honestly; the current `Neighbourhood` carries a `precision` string that is substring-tested | Phase 1, per producer |
| Q4 | Whether `n-ary` identity uses role bindings or positional arguments | `logical_material` currently ignores the `participants` argument for NARY and uses sorted `["role","member"]` pairs | Phase 1, decided with the signature |
| Q5 | Producer ↔ lifecycle import direction | `run_producer` is in interpretation, `run_until` in control-plane (R-004) | Phase 1, as an ADR |
| Q6 | Whether the unused `Layer0Pipeline::InterpretHook` seam is the intended binding point instead of `capture_interpretation` | Both are plausible; `Layer0Pipeline` has zero production instantiations | Needs a decision before Phase 8; default is `capture_interpretation` |
| Q7 | Whether `source_temporal_observation` gets a repository in 021 or a later feature | FR-096 requires reachability, but the table has no writer at all today | Phase 9; default is yes, since `§61` names it |
