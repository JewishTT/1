# Implementation Plan: Semantic Fabric (Ontologies as External Tools)

**Feature**: `017-semantic-fabric` · **Spec**: `spec.md` · **Status**: planned 2026-09-26

## Summary

Turn the platform from ontology-gated into ontology-using. The graph's foundation stays
Observation → Mention → Assertion → Relation → Entity → TemporalWorldline. Semantic resources
attach beside it as pluggable, versioned, evidence-bearing instruments. The world is open; every
*operator* is closed. Validation produces findings, never deletions.

Physical approach: a new pure-domain package `apps/shared/semantic/` (no I/O, deterministic, no
service, no new backbone) plus surgical removal of the two ontology-gate call sites in
`apps/interpretation/extractors/registry.py`.

## Technical Context

**Language/runtime**: Python 3.11+, `uv` workspaces per app.

**Existing code this feature binds, not duplicates**:
- `apps/shared/domain/relation_schema.py` — `RelationSchema`, `RelationSchemaRegistry`,
  `TemporalSemantics`, `arity_mode`, roles, `content_key`, `schema_version`. **This is the
  `RelationContract`; 017 only attaches policy/strategy bindings to it** (FR-006).
- `apps/shared/domain/relation_claim.py` — `RelationClaim`, the assertion under validation.
- `apps/shared/domain/evidence_context.py` — `EvidenceContext`, content-addressed. Extended with
  the semantic regime fields (FR-014); its identity/hash semantics are untouched.
- `apps/shared/events/ontology_pack.py` — `OntologyPack`, `OntologyPackRegistry`. **Demoted to a
  hint surface** (FR-002), not deleted.

**Dependency reality** (probed): `rdflib` is present. `pyshacl`, `sssom`, `linkml`, `oak` are
**not installed**. Therefore no new hard dependency is added. SHACL is an optional adapter that
imports `pyshacl` lazily inside the call and returns `UNSUPPORTED` when absent — which is exactly
the graded verdict FR-011 requires, so the "library missing" path is specified behaviour rather
than a gap. SSSOM/SKOS are implemented natively over plain data (they are simple enough that a
dependency would cost more than it saves); OAK is an *interface*, not a dependency.

**Storage**: Postgres ORM in `apps/control-plane/db/schema.py` + forward-only alembic migrations.
`TypeAssertion`, `SemanticMapping`, `SemanticProfile`, `ValidationFinding` are new tables.
Everything is tenant-scoped, fail-closed.

**The gate to remove** (verified, precise): `apps/interpretation/extractors/registry.py:101` and
`:152` call `self._ontology.allows_type(m.kind)` and drop mentions on the result. Callers at
`apps/acquisition/tests/test_pipeline.py:88` construct `ExtractorRegistry(ontology_pack=...)`.
No other `allows_*` call sites exist.

**`ContextValidator` from spec 016 was never implemented.** Layered validation in 017 is built
new in `apps/shared/semantic/validation.py`; there is nothing to migrate.

## Decisions

- **D1 — `domain_range` defaults to `warn`, never `deny`.** A `deny` default would make FR-012
  self-contradictory. Operators may declare stricter policies explicitly; the default never
  deletes. (Resolves open question 2.)
- **D2 — `OntologyPackRegistry` is retained as a hint surface, not removed.** It is genuinely
  useful for expansion/ranking, and removal churns call sites for no architectural gain. The
  requirement is that it is *unreachable as a permit/deny decision*, not that it disappears.
  (Resolves open question 4.)
- **D3 — `apps/shared/semantic/`, not `apps/semantic/`.** `apps/*` are services
  (acquisition, control-plane, projection…); a new service would imply a second backbone and a
  deployment unit. This feature is pure domain logic imported by admission and control-plane.
- **D4 — SHACL/RDF is an optional sidecar behind `SemanticRegistry`.** Never on the write path.
- **D5 — `Entity.schema_name` is preserved** as the `observed` layer of typing. 017 adds layers
  alongside; it does not migrate or rewrite existing entities (FR-004, monotonicity).

## Constitution Check

| Principle | Status | Notes |
|---|---|---|
| I — evidence before entity | PASS | Every type, mapping, finding carries evidence; findings never delete. |
| II — no second backbone | PASS | Pure-domain package; no service, no triplestore, no Jena. |
| III — no auth/CAPTCHA circumvention | PASS | Vocabulary access is static lookup only. |
| IV — tenant isolation fail-closed | PASS | All new stores tenant-scoped; cross-tenant read refused. |
| V — one time model | PASS | `observed_at` ≠ `valid_from`/`valid_to`; temporal typing is a claim. |
| VI — LLM-free determinism | PASS | SKOS/SHACL/SSSOM evaluation deterministic; no generation. |
| VII — event-sourced rebuild | PASS | Profiles/vocabularies/mappings versioned, rebuildable from event log. |
| VIII — bounded resources | PASS | SHACL opt-in, off write path, bounded view. |

**Re-checked after D1–D5**: no principle regressed. D1 is the load-bearing one — it is what keeps
FR-012 and FR-011 consistent.

## Project Structure

```
apps/shared/semantic/
├── __init__.py            # exports SemanticRef, RelationRef, ValidationReport only
├── contracts.py           # SemanticRef, RelationRef, TypeScope, SemanticStatus, TypeAssertion
├── profiles.py            # SemanticProfile, profile resolution/inheritance, applies_to
├── operators.py           # RelationOperator: policy/strategy bound to existing RelationSchema
├── vocabularies.py        # SKOS Concept/ConceptScheme, broader/narrower/related, match preds
├── expansion.py           # broaderTransitive/narrowerTransitive, explicit opt-in per operation
├── mappings.py            # SSSOM-style SemanticMapping, justification/provenance
├── validation.py          # layered graded validation + ValidationFinding, UNKNOWN/UNSUPPORTED
├── shacl.py               # native graph -> RDF view; lazy pyshacl; degrades to UNSUPPORTED
└── registry.py            # SemanticRegistry: resolve_term/get_aliases/parents/children/related/mappings
```

```
apps/control-plane/db/
├── schema.py                             # + type_assertions, semantic_mappings, semantic_profiles, validation_findings
└── migrations/versions/018_semantic_fabric.py
```

```
apps/interpretation/extractors/registry.py   # GATE REMOVED (lines 101, 152)
```

## Complexity Tracking

| Component | Risk | Mitigation |
|---|---|---|
| Removing the ontology gate | **High** — silently changes what enters the graph | Remove gate, keep mention + untyped status; SC-5 asserts unreachability by import-graph test |
| SHACL sidecar | Medium — `pyshacl` absent, RDF view namespacing | Lazy import, `UNSUPPORTED` verdict, no write-path coupling (SC-9) |
| Layered typing store | Medium — write amplification | `TypeAssertion` as projection over events + materialised table (OQ1) |
| Profile inheritance | Low | Pure function, memoised, no cycles |
| SSSOM mappings | Low | Flat records, no reasoning |
