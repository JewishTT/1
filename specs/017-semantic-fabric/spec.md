# Feature Specification: Semantic Fabric (Ontologies as External Tools)

**Feature Branch**: `017-semantic-fabric`

**Created**: 2026-09-26

**Status**: Draft

**Input**: User description: "Do not build the system *around* an ontology — build a system that can *use* ontologies as external semantic tools. Foundation stays Observation/Mention/Assertion/Relation/Entity/TemporalWorldline. Semantic resources (SKOS vocabularies, SSSOM mappings, OAK access, SHACL constraints, LinkML contracts) attach *beside* the graph, never as its mandatory language. World is open, operators are closed. Semantic commitment is monotonic and never destructive. Validation produces findings, never deletion."

## Problem Statement

Feature 016 built the relation/evidence/context fabric: `RelationClaim`, `RelationSchema`, content-addressed `EvidenceContext`, and a graded `ContextValidator`. What it did **not** build is the ability to consume *external* semantic resources without letting them capture the platform.

Three concrete defects exist today:

**D1 — An ontology is currently an admission gate, i.e. a closed world.** `apps/shared/events/ontology_pack.py` exposes `OntologyPack.allows_type()` / `allows_relation()` through `OntologyPackRegistry`. A type or relation absent from the active pack has no legal path into the graph. This inverts the intended architecture: the *world* becomes no larger than whatever vocabulary happened to be registered. A newly discovered entity class, a source-local category, or a relation no ontology has ever heard of is silently un-admittable — the exact "sterility" failure the platform must not have. Note this is a *different* object from `RelationSchema` (feature 016, T063), which is a per-operator contract and is correct; `OntologyPack` is the global allowlist and is what is wrong.

**D2 — There is no layered typing, so a single categorical type loses everything else.** `apps/shared/domain/entity.py` gives `Entity` a `schema_name` — one categorical name. The target model requires `observed_types` / `inferred_types` / `mapped_types` / `context_types` to coexist. The same entity must be able to be `core:Entity` + `web:WebProfile` + `local:Influencer` + `schema:Person` simultaneously, with per-type status and provenance. Today there is nowhere to put the last three.

**D3 — Semantic mappings are not evidence-bearing objects.** Cross-vocabulary alignment does not exist as data anywhere. The closest thing is a hardcoded `EXTERNAL_TYPE_MAP` dict scattered in code. Consequently a mapping carries no provenance, no justification, and no version, so a mapping decision cannot be audited, reversed, or re-derived, and it cannot be cited as evidence.

**D4 — Validation is not layered and cannot express "unknown".** `ContextValidator` (016) returns graded verdicts, which is a real foundation, but there is no structural / semantic / temporal / provenance / cross-source / graph-level staging, and no distinction between `INVALID` (contradicted) and `UNKNOWN` / `UNSUPPORTED` (cannot be checked). Without `UNKNOWN`, operators are forced to collapse "I could not evaluate this" into either pass or fail.

## Scope Guard — what this feature is NOT

This is load-bearing and must survive implementation pressure:

- NOT an ontology of reality. No OWL/OWL-RL reasoner in the core, no Jena. If a domain later needs OWL-RL, it is added *locally* behind an adapter.
- NOT a global taxonomy of permitted entity kinds. Unknown types and unknown relations are always admissible.
- NOT a gate on raw assertions. A failed semantic check is a **finding attached to the assertion**, never a reason to delete or reject it.
- NOT a replacement for internal identity. External ontology IRIs never replace internal IDs; they are one mapping among many.
- NOT a second source of truth for relation semantics — `RelationSchema` (016) remains the single declaration of what a relation operator means.

The one-line test: *ontology answers "which known concepts can we use to interpret this", never "what may exist in our reality".*

## Terms

**Open world / closed operations** — anything may be observed and admitted; every *operator* (`extract_phone`, `works_for`, `located_in`) declares a fixed, enforced contract.

**Semantic commitment ladder** — `raw → surface → hypothesis → mapped concept → resolved entity`. Commitment may only move *up*; the original uncertainty is never deleted.

**SemanticProfile** — a versioned, scoped bundle of types, relations, vocabularies, constraints and mappings. `parent_profile` enables inheritance. `applies_to` scopes it to a source, domain, extractor or investigation. Multiple profiles apply to one entity at once.

**RelationOperator** — the executable identity of a relation: arity, direction, roles, domain/range hints, temporal semantics, symmetry, inverse, transitivity, evidence requirements, extraction strategies, admission policy, validation policy, projection policy. `RelationSchema` (016) is its declarative declaration; this feature adds the policy and strategy bindings.

**SemanticAssertion** — a typing or mapping claim (`ENT-1 mapped_to schema:Person`) that carries mode (`observed`/`extracted`/`inferred`/`mapped`/`validated`), evidence, context and mapping reference. It is a first-class object, not a side effect of entity creation.

## User Scenarios

### US1 — A new entity class appears that no ontology knows (P1)
An extractor surfaces an object typed `local:shell_company_shell`. No active profile, no external vocabulary and no ontology declares it. The platform admits it as an entity with a first-class local type, records no mapping, and raises no error. Three weeks later a corporate profile defines the concept and a SSSOM mapping is attached retroactively. The entity's identity never changed and nothing was rewritten.

### US2 — One entity carries four simultaneous typings (P1)
The same `ENT-123` is `core:Entity` (observed), `web:WebProfile` (observed from a source profile), `local:Influencer` (a local investigation hypothesis) and `schema:Person` (a close match, mapped, unvalidated). Search, blocking and UI read whichever layer they need. None overwrites another, and each keeps its own status and evidence.

### US3 — Extraction is constrained where it should be (P1)
A deterministic extractor finds `+370...` and binds it to `PhoneNumber` with a strict datatype contract. The system accepts it. In the same pass it finds an unclassifiable token, binds nothing, and stores a mention with no type — without aborting the extraction, and without inventing a type.

### US4 — A relation operator enforces its own contract (P1)
The pipeline proposes `works_for` between a mention pair. The operator's contract says subject is person-like or account, object is organization-like, arity 2, directed, inverse `employs`, temporal mode interval, `domain_range: warn`, `minimum_evidence: [mention_pair, relation_pattern]`. The claim is admitted with a `role_assignment` candidate shape, and validation reports a *warning* — not a rejection — if the object is not organization-like.

### US5 — A failed validation survives as data (P1)
SHACL reports that the object of `works_for` should be an `Organization` but is a `Document`. The `Assertion` is unchanged: status `observed`, `semantic_validation = failed`, `findings = [SHACL violation]`, `evidence = [OBS-123]`. The finding is queryable, the assertion is not deleted, and no projection drops it.

### US6 — A vocabulary is a retrieval accelerator (P2)
An analyst queries `public_company`. SKOS `broaderTransitive` expands to `company` and `organization`, widening recall. A second query for an exact corporate form does not expand. Expansion is a per-operation decision, and a `PublicCompany` concept is never *asserted equal* to `Organization` — only related by a recorded mapping.

### US7 — Blocking is cheap (P2)
A mention resolves against a candidate universe. Type hypotheses narrow it: person-like mentions only block against person-like candidates, and relation affordances prune further. The comparison set drops by orders of magnitude. The internal identity model is unchanged and no type is asserted by the pruning.

### US8 — External vocabulary access is pluggable (P2)
A lookup needs `schema:Person` labels and aliases. It resolves through a `SemanticRegistry` that exposes `resolve_term()`, `get_aliases()`, `parents()`, `children()`, `related()`, `mappings()`. The caller cannot tell whether the answer came from a local SKOS file, an OBO import or a remote OAK backend. Swapping backends changes no calling code.

### US9 — Semantic commitments are auditable (P2)
Given any entity, the system can list every type and mapping ever asserted about it, with mode, evidence, context, profile and mapping justification. Nothing was overwritten, so the history is complete.

### US10 — An unaligned external term is mapped, not guessed (P2)
Common Crawl yields `Managing Director`; internal extraction has `role`. Instead of a hardcoded dict, an SSSOM mapping `closeMatch` is recorded with provenance, justification, mapping source and mapping version. The mapping is itself evidence-bearing and can be re-evaluated.

## Functional Requirements

### FR-001 — Open-world admission (P1)
The platform MUST admit an unknown entity type, an unknown local concept and an unknown relation operator into the graph without error, MUST persist it as a first-class local type or operator, and MUST NOT require prior declaration in any profile, pack or ontology.

### FR-002 — No ontology as admission gate (P1)
`OntologyPack.allows_type()` / `allows_relation()` (apps/shared/events/ontology_pack.py) MUST NOT be reachable from any admission path as a permit/deny decision. `OntologyPack` MUST be demoted to a *hint* surface (expansion, ranking, validation) and its call sites in the admission path MUST be removed or replaced with operator contracts.

### FR-003 — Layered typing (P1)
A type assignment MUST be a first-class `TypeAssertion` object with fields: `entity`, `type`, `scope`, `source`, `context`, `valid_from`, `valid_to`, `observed_at`, `status`, `mapping`, `evidence`, carrying mode in {observed, inferred, mapped, context}. An entity MUST be able to hold type assertions in all four layers simultaneously, and MUST NOT be limited to a single categorical `schema_name` for semantic purposes.

### FR-004 — Semantic commitment is monotonic (P1)
The system MUST retain the raw surface form, the hypothesis and the mapped concept for every semantic resolution. Moving up the ladder (`raw → surface → hypothesis → mapped concept → resolved entity`) MUST NOT delete, overwrite or downgrade any prior state, and the system MUST support reconstructing the full history for any entity or relation.

### FR-005 — SemanticRef contract boundary (P1)
`apps/shared/domain` MUST import only `SemanticRef`, `RelationRef` and `ValidationReport`. It MUST NOT import SKOS, SSSOM, SHACL, OAK or LinkML types, and no ontology class type may appear in a core domain signature.

### FR-006 — RelationOperator extends RelationSchema (P1)
The system MUST bind to the existing `RelationSchema` (016) an executable operator definition carrying: arity, direction, roles, domain/range hints, temporal semantics, symmetry, inverse, transitivity, evidence requirements, extraction strategies, admission policy, validation policy and projection policy. It MUST NOT create a second, parallel declaration of relation semantics.

### FR-007 — SemanticProfile (P1)
A `SemanticProfile` MUST be identified by `profile_id` + `parent_profile` + `version`, and MUST contain types, relations, vocabularies, constraints and mappings, scoped by `applies_to` (source, domain, extractor, investigation). Profile resolution MUST support inheritance chains, and more than one profile MUST be applicable to a single entity at the same time. A profile mismatch MUST NOT be a rejection reason.

### FR-008 — SKOS vocabularies and controlled terms (P2)
The system MUST support SKOS `ConceptScheme` with `broader`, `narrower`, `related`, and cross-vocabulary match predicates (`exactMatch`, `closeMatch`, `broadMatch`, `narrowMatch`). It MUST support surface form → concept resolution, and MUST support `broaderTransitive`/`narrowerTransitive` query expansion as an explicit per-operation choice. Expansion MUST NOT assert concept equality.

### FR-009 — SSSOM mappings as evidence-bearing objects (P2)
A mapping between an internal term and an external term MUST be persisted as a first-class object carrying predicate, mapping source, mapping version, justification and provenance, and MUST be citable as evidence and re-evaluable. Hardcoded external-type dicts MUST NOT be the mechanism.

### FR-010 — SHACL validation sidecar (P2)
The system MUST build an RDF validation view from the native graph, validate it with `pySHACL` (SHACL Core) and produce a `ValidationReport`. The native store MUST NOT be required to become an RDF database. The sidecar MUST be optional and non-blocking for the write path.

### FR-011 — Layered graded validation (P1)
Validation MUST be staged as structural → semantic → temporal → provenance → cross-source → graph-level. Every stage MUST return a graded verdict from {VALID, INVALID, UNKNOWN, UNSUPPORTED, CONFLICTING}, MUST distinguish "contradicted" from "cannot be evaluated", and MUST NOT reduce to a boolean.

### FR-012 — Validation produces findings, not deletion (P1)
A validation failure MUST attach findings to the assertion and MUST NOT delete, reject, or prevent projection of the underlying assertion. A failed assertion MUST remain queryable with its evidence intact and MUST remain resolvable in the graph.

### FR-013 — Closed operations, open world (P1)
Every operator MUST declare and enforce a fixed contract (roles, arity, direction, datatypes, evidence requirements) regardless of what the world contains. The admission of unknown *content* MUST NOT weaken an operator's own contract, and the operator contract MUST NOT be used to forbid content that is outside its scope.

### FR-014 — ContextFrame as semantic binding layer (P1)
`EvidenceContext` (016) MUST carry the semantic regime in which an assertion was interpreted: active semantic profile, profile version, ontology version, mapping set, validation profile, temporal frame, localization and language. An assertion MUST be storable without semantic commitment, with the context recording the regime it was interpreted under.

### FR-015 — Pluggable semantic access (P2)
External vocabulary/ontology access MUST be exposed only through `SemanticRegistry` with `resolve_term()`, `get_aliases()`, `parents()`, `children()`, `related()` and `mappings()`. Backends (local SKOS, OBO import, remote OAK) MUST be interchangeable behind this interface, and no calling code outside the registry may depend on a specific backend.

### FR-016 — Search-space reduction (P2)
Resolution MUST support using type hypotheses and relation affordances to narrow candidate sets, and MUST expose the reduction as a measurable outcome. Pruning MUST NOT assert a type onto a pruned candidate, and pruning MUST remain reproducible.

### FR-017 — LinkML limited to contracts (P3)
LinkML MUST be used only to describe boundary/domain contracts (`SourceLocator`, `ObservationEnvelope`, `AssertionEnvelope`, `RelationContract`, `ValidationReport`, `MaterializationManifest`) with schema generation and validation. LinkML MUST NOT be used to enumerate the kinds of entities that may exist.

### FR-018 — Monotonic status vocabulary (P2)
Semantic status MUST be represented as a non-destructive set of stages {observed, extracted, inferred, mapped, validated, resolved} such that a later stage never invalidates an earlier one, and the system MUST be able to answer "what did we believe about X at time T".

## Data Requirements

- `TypeAssertion` — FR-003, FR-018. Keyed by (entity, type, scope, status). `scope` ∈ {observed, inferred, mapped, context}; `status` ∈ {observed, extracted, inferred, mapped, validated, resolved}. `valid_from`/`valid_to` are temporal, not a substitute for `observed_at`. Retained permanently (FR-004).
- `SemanticProfile` — FR-007. Keyed by (profile_id, version). `parent_profile` nullable. Contains child collections of type refs, relation refs, vocabulary refs, constraint refs and mapping refs; `applies_to` is a set of {source, domain, extractor, investigation} tags.
- `RelationOperator` — FR-006. Bound 1:1 to an existing `RelationSchema` by (relation_type, schema_version). Carries strategy and policy bindings.
- `SemanticMapping` — FR-009. Keyed by (internal_ref, external_ref, predicate, mapping_set_version). Carries `mapping_source`, `mapping_version`, `justification`, `provenance`.
- `ValidationFinding` — FR-011, FR-012. Keyed by (assertion_ref, stage, code). Carries graded `verdict`, message, constraint ref, and MUST NOT carry authority to delete.
- `Concept` / `ConceptScheme` — FR-008. `Concept` has `concept_id`, `scheme_id`, `pref_label`, `alt_labels`, and typed links (`broader`, `narrower`, `related`, match predicates). MUST NOT encode equality between concepts.
- `SemanticExpansionRequest` — FR-008. Records whether expansion was requested, which transitive closure was used, and the resulting term set. Expansion is a query-time decision, not a stored fact about the world.

## Out of Scope

- OWL/OWL-RL reasoning, Apache Jena, a triplestore, or RDF as the canonical store — explicitly rejected for this feature (constitution: no second backbone).
- SHACL 1.2 advanced features (rules, inference, SPARQL constraints) beyond Core; Core is the stable base and new drafts are adopted selectively.
- A single global ontology or a canonical enumeration of all entity kinds.
- Modifying or replacing `RelationClaim`, `RelationSchema`, `EvidenceContext` or `ContextValidator` semantics from feature 016; this feature extends and binds them.
- Ontology reasoning that mutates the canonical graph.

## Success Criteria

- **SC-0 (non-regression):** The suites that are green today stay green: projection `189 passed, 1 skipped`; acquisition `126 passed, 10 skipped`; control-plane collects 343 with 0 errors and the only remaining failures are the 2 pre-existing `test_donor_api` contract failures plus the 1 Postgres-unavailable test.
- **SC-1:** An entity and a relation with types/operators declared in no profile, pack or ontology are admitted end-to-end with no error and no invented type.
- **SC-2:** An entity simultaneously carries observed, inferred, mapped and context type assertions, and the full history is reconstructable with evidence per assertion.
- **SC-3:** `apps/shared/domain` has no import of SKOS, SSSOM, SHACL, OAK or LinkML types (enforced by test, FR-005).
- **SC-4:** A SHACL violation on a materialized relation is retrievable as a `ValidationFinding` while the underlying `RelationClaim` and its evidence remain fully intact and resolvable (FR-012).
- **SC-5:** `OntologyPack.allows_type`/`allows_relation` is unreachable from any admission path (FR-002).
- **SC-6:** `query("public_company")` with expansion enabled reaches `company` and `organization`; with expansion disabled it does not; neither asserts `PublicCompany ≡ Organization` (FR-008).
- **SC-7:** `query_term()`, `get_aliases()`, `parents()`, `children()`, `related()`, `mappings()` all work against a local SKOS backend, and swapping the backend requires no change in calling code (FR-015).
- **SC-8:** A `works_for` proposal whose object is not organization-like yields a graded `warn` finding and a still-materialised claim, never a rejection (FR-006, FR-011).
- **SC-9:** Unknown-vs-contradicted is distinguishable: a check that cannot be evaluated returns `UNKNOWN` or `UNSUPPORTED`, never `VALID` or `INVALID` (FR-011).
- **SC-10:** Blocking with type hypotheses reduces a candidate set measurably and reproducibly, without asserting types onto pruned candidates (FR-016).

## Constitution Check

| Principle | Status |
|---|---|
| I — evidence before entity | PASS: every type, mapping and finding carries evidence; findings never delete. |
| II — no second backbone | PASS: SHACL runs as a sidecar over an RDF view; no triplestore, no Jena. |
| III — no auth/CAPTCHA/paywall circumvention | PASS: semantic access is a static local/remote vocabulary lookup only. |
| IV — tenant isolation fail-closed | PASS: profiles, vocabularies and mapping sets are tenant-scoped; cross-tenant reads are refused. |
| V — one time model | PASS: `observed_at` (learned) is distinct from `valid_from`/`valid_to` (true); temporal typing is a claim. |
| VI — LLM-free determinism | PASS: SKOS/SHACL/SSSOM evaluation is deterministic; OAK is a lookup interface, not a generator. |
| VII — event-sourced rebuild | PASS: profiles, mappings and vocabularies are versioned projections rebuildable from the event log. |
| VIII — bounded resources | PASS: SHACL runs opt-in, off the write path, with a bounded graph view. |

**Gate**: open-world admission (FR-001, FR-002) is the load-bearing requirement. Any implementation that reintroduces a global type/relation allowlist fails this spec, regardless of how well the semantic tooling performs.

## Open Questions

1. Should `TypeAssertion` be its own event-sourced aggregate, or a projection over `Observation`/`Inference` events with a materialised table? Trade-off: auditability vs write amplification.
2. Default `domain_range` policy per operator — `warn` or `deny`? The user text specifies `warn` for `works_for`; a general default must be declared rather than inherited implicitly.
3. Where does the SHACL graph view get its namespace strategy — a synthetic namespace or the internal ID space?
4. Is `OntologyPackRegistry` retained as a hint surface, or removed outright once FR-002 lands? Removal is cleaner but touches any remaining call sites.
