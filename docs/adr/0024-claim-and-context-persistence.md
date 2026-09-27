# ADR-0024: Relation claim and evidence context persistence

## Status

Accepted — 2026-09-26 — feature `016-relation-evidence-graph-fabric` (task T002).

## Context

The graph layer cannot answer, for any relation it holds, *why this edge exists, on which
observation, when it was published, when it was considered true, when the system learned it,
which extractor version produced it, which ontology version permitted it, and which sources
were independent.* Five defects follow from that, and this ADR governs the ones that are
about **what a relation is, what context it may be read under, and where it is stored**.

`GraphEdge` in `apps/projection/graph/abstraction.py:29-37` is a four-field frozen
dataclass — `edge_type`, `source`, `target`, `properties` — and it cannot carry the required
semantics for three concrete reasons:

1. **It has no `edge_id` at all.** Nothing can reference an edge, so no claim, no assertion,
   no lineage trace and no context can point at one. A second id cannot be added either,
   because there is no first one to hang it off.
2. **`__hash__` and `__eq__` disagree about identity.** `__hash__` is
   `hash((edge_type, source, target))` (`abstraction.py:36-37`) — properties excluded — while
   the dataclass-generated `__eq__` compares all four fields, properties included. Two edges
   with the same triple and different properties are therefore *hash-equal but unequal*, i.e.
   distinct members of the same set (`self._edges: set[GraphEdge]`, `abstraction.py:108`).
   Writing the same relation twice with a changed property bag therefore creates two set
   members and two adjacency entries, so idempotency fails precisely when the relation gains
   information.
3. **There is nowhere to put a context ref, a temporal interpretation, a status, or a
   supersession link.** Provenance is passed separately at `write_edge()` time and is not
   part of edge identity, so a relation cannot be reasoned about as an assertion that has
   evidence, an interpretation, a version and a lineage.

That dataclass is also load-bearing far outside its own file. It is embedded in
`InMemoryGraphStore`, `Neo4jGraphStore`, `RebuildableGraphStore`, `apps/projection/graph/snapshot.py`
and `apps/projection/graph/adjacency.py`, and constructed in their tests.

Context, meanwhile, is not an object. Extractor version, normalisation version, ontology
version, source family, independence group, observation/publication/event time, completeness
and trust state travel as loose attributes. Nothing validates them together and nothing stops
a claim being interpreted under a context that does not license it. The only admission control
in the graph layer today is `enforce_projection_provenance`, which checks that `event_id` and
`observation_id` are *keys* and raises otherwise — it does not check tenant, versions, schema,
intervals or endpoints, and there is no notion of a *reason* for a rejection.

Constitution III requires the graph to remain a rebuildable artifact, and invariant 3
("Assertion != truth") requires that a claim which is correct but was produced under a retired
ontology version has not thereby become false. A boolean validator cannot honour the second
requirement, because it makes "wrong" indistinguishable from "uninterpretable" from "stale"
from "partially supported". Constitution IV forbids a single score equalling truth, and
requires publication count to be kept separate from independent-source count.

## Decision

### `RelationClaim` is a new first-class model that coexists with `GraphEdge`

`RelationClaim` is a frozen dataclass in `apps/shared/domain/relation_claim.py` carrying
identity, revision, arity mode, subject and object refs, role bindings, the full temporal
interpretation (`valid_from`, `valid_to`, `observed_at`, `published_at`, `known_from`,
`known_until`), evidence refs, a `context_ref`, source-independence groups, the extractor,
normalisation, ontology and schema versions in force, a status, confidence, evidence grade,
and `supersedes` / `contradicts` links.

It is **additive**. `GraphEdge` is not rewritten; it is *widened once, minimally*: it gains
a required `edge_id` supplied by the relation layer (not invented by the store), and both
`__hash__` and `__eq__` key on `(edge_id,)`, which makes idempotency a function of identity
rather than of accidental field equality. The two objects then coexist with different
lifetimes: a `GraphEdge` is a disposable projection artefact whose identity is a convenience;
a `RelationClaim` is a durable admitted assertion whose identity is load-bearing for lineage
and which is never deleted.

Widening `GraphEdge` in place *instead of* adding the model was rejected precisely because it
breaks `InMemoryGraphStore`, `Neo4jGraphStore`, `RebuildableGraphStore`, `snapshot.py`,
`adjacency.py` and their tests mid-feature. An additive model that the stores then adopt is
faster and lower risk, and it keeps constitution III (rebuildable projection) and invariant 3
(preserved assertion) from pulling in opposite directions on one class.

### `EvidenceContext` is frozen, content-addressed, and shared by reference

`EvidenceContext` is a frozen dataclass with the 23 fields of FR-013.
`context_id = "CX-" + digest128(canonical(all fields except context_id))`, so two
independently constructed frames with the same field values yield byte-identical ids, and
recomputing the digest over a stored frame detects a corrupted or hand-edited row.

- **The frame is frozen.** `__post_init__` uses `object.__setattr__` **only** to fill the
  derived `context_id` (and to reject an inverted `valid_to < valid_from`). No other field is
  ever written after construction; any other mutation raises. This is deliberately narrower
  than the wider `__post_init__` rewriting used at `temporal_worldline.py:528-535`, because
  silently rewriting caller-supplied frame fields would give two semantically equal frames
  different stored values and therefore different `context_id`s, defeating the whole point.
- **Frames are shared by reference, never embedded.** A claim holds `context_ref: str` and
  nothing else — no denormalised copy, no snapshot of the frame. A mutable copy could drift
  from the registered frame with nothing able to detect it, and it would multiply storage.
- **Resolution is loud.** A missing frame yields reason code `context_unresolved`; the
  validator never substitutes a default frame.
- **A frame is never a verdict.** A frame with a missing parent, `PARTIAL` completeness or
  `DISPUTED` trust state is storable. Only the claim interpreted under it acquires a degraded
  verdict. Parent-cycle detection lives in the resolver, not the frame, because a frame cannot
  see its siblings.

### Validation is seven layers, graded, and never boolean

`validate(context, claim, world) -> ValidationResult` runs exactly seven layers in order and
**always reports all seven outcomes**, even when an earlier layer fails:

1. `structural`
2. `semantic`
3. `temporal`
4. `provenance`
5. `identity`
6. `cross_source`
7. `graph_constraints`

Each layer yields `PASSED` / `FAILED` / `INDETERMINATE` / `NOTED` and zero or more
`ValidationReason` records, each carrying a stable snake_case `code`, the raising `layer`, a
human-readable `detail` and optional evidence refs. The seven outcomes collapse into one
graded verdict by a fixed precedence:

```text
INVALID > CONFLICTING > STALE > INCOMPLETE > UNDERDETERMINED > VALID
```

A boolean return is **forbidden**. Constitution invariant 3 ("Assertion != truth") means a
verdict must distinguish *false* from *uninterpretable* from *stale* from *partially
supported*; a single `True`/`False` forces every caller to re-derive the reason, and that
re-derivation is precisely the duplication of judgement logic this feature exists to remove.
An `UNDERDETERMINED` verdict (a claim with no declared extractor version, or a relation type
with no registered schema) is not a rejection at all, and a boolean would force the caller to
decide without information whether to delete, quarantine or re-interpret it.

All seven outcomes are computed even after an earlier layer fails because the layers answer
different questions: "the temporal layer failed" is only meaningful if the reader can also
see that the structural layer passed. Short-circuiting would make the verdict correct and the
diagnosis unavailable, and a fix applied to one layer would stay hidden behind another.

The validator is **pure with an injected `ValidationWorld`**: schemas, context resolver, known
and admitted entity ids, active and known ontology versions, and sibling claims. It performs
no I/O, never mutates its inputs, and the expensive layers receive pre-computed inputs rather
than issuing queries. Purity is what makes the result reproducible and replayable, and it is
what keeps validation from becoming a pipeline bottleneck. A `null` context short-circuits to
`INVALID/provenance_context_missing` with all seven layers still reported — the "always seven"
rule holds even on the degenerate input.

### `evidence_grade` stores its components, never a sum

The grade is a lookup over five separately stored components:
`independent_source_count`, `publication_count`, `completeness`, `trust_state` and
`confidence`. They are never collapsed into one number, because constitution IV forbids a
single score equalling truth — validity, relevance, resolution confidence, source quality and
evidence support are stored separately. The quantities also have different units and different
failure modes: the independent source count collapses copied sources, completeness is an
ordinal the producer declares about itself, trust state can become `DISPUTED` after the fact,
and confidence is a producer's self-report. A weighted blend is dominated by whichever term
has the widest range, is not monotone under any of them, and cannot be inverted — "why is this
0.6?" is unanswerable, which is the question the feature exists to answer.

`publication_count` and `independent_source_count` are **never substituted for one another**.
Two captures of one wire story are two publications and one independent source, and the
constitution requires publication count not to be treated as independent-source count. Two
fields and a unique independence group per source family make that structural; a `DISPUTED`
trust state caps the grade at `weak` rather than being averaged away.

### Persistence: five tables, one forward-only migration

Five new tables land in revision `016_relation_evidence_graph` with
`down_revision = "015_worldline_reconstruction"`:

1. `evidence_context` — the frame, keyed by `context_id`, with `frame_fingerprint` and a
   unique index on `(tenant_id, frame_fingerprint)` for idempotent registration.
2. `relation_claim` — keyed by `relation_id`, carrying the logical id, revision number, arity
   mode, role bindings, the full temporal interpretation, evidence refs, `context_ref`,
   independence groups, the version fields, status, grade, `supersedes`, `contradicts` and
   `content_hash`; unique on `(tenant_id, content_hash)`.
3. `relation_claim_revision` — the append-only revision ledger, unique on
   `(tenant_id, logical_relation_id, revision_number)`.
4. `relation_schema_version` — the versioned relation vocabulary, unique on
   `(tenant_id, relation_type, schema_version)`.
5. `claim_context_lineage` — durable `LineageTrace` records, indexed on
   `(tenant_id, relation_id, direction)`.

The migration order is enforced and asserted: **tables → columns → backfill → indexes**, with
the unique indexes created only after any backfill; `downgrade()` runs in strict reverse,
indexes then tables. 016 adds no columns to existing tables and needs no backfill, so the
backfill step is recorded as an explicit no-op assertion — the ordering invariant is then
structurally enforced for this revision and mechanically checkable for the next one that does
need a backfill. Creating a unique index before its backfill admits exactly the rows the
index exists to constrain.

**Revision 015 is immutable and is not edited.** It is pinned by SHA-256 in
`apps/control-plane/tests/unit/test_migration_forward_only.py`, alongside the single-root,
single-head assertions; editing it to absorb these tables would fail those guards. A
corrective change to this schema is therefore **revision 017**, never an edit.

**Both install paths must be proven equivalent.** The migration must reach an identical
schema from a fresh install applying every revision in order **and** from an install that
already has 015 applied, asserted by programmatic schema comparison. A content digest over
the migration file is not a substitute — it covers file content only, and a fresh deployment
and an upgraded one must not be able to diverge.

Every unique index and every lookup index in these five tables is tenant-prefixed, so
tenant isolation is structural: a cross-tenant read or write is not expressible as a single
query. `SUPERSEDED`, `RETRACTED` and `CONTRADICTED` claims stay queryable and are never
deleted, and every rejection is preserved with its decision, reasons, grade components,
versions and timestamps so it is replayable.

### Rebuildability: the substrate is durable, the graph is a projection

`RelationStore` is the substrate contract; the graph stores remain rebuildable projections of
it. A rebuild from the durable log must reproduce a relation set with an **identical
`checksum()`**, and a double snapshot must yield an equal checksum and a stable projection id.
Projection failure never destroys evidence: the graph can be dropped and rebuilt from
`relation_claim`, the context table and the event log. The idempotency guarantee is a
database constraint here rather than application logic, so a buggy caller cannot produce a
duplicate.

## Rationale

- **The defects in `GraphEdge` are structural, not cosmetic.** No id means nothing can point
  at a relation; a hash that excludes `properties` while equality includes it means the set
  admits two members for one relation the moment the relation gains information. Neither is
  repairable by adding fields to a properties bag, which is why the fix is an explicit
  identity rather than a wider payload.
- **The blast radius of an in-place widening is larger than the benefit.** `GraphEdge` is
  embedded in five stores, adapters and helpers plus their tests, and it is currently
  constructed positionally at existing call sites. Widening it into a `RelationClaim` with a
  different name would break all of them mid-feature while delivering nothing the additive
  model does not. The additive path also respects the real difference in lifetimes: a
  projection artefact is disposable, an admitted assertion is not.
- **Immutability is the precondition for sharing.** If a frame can be edited after a claim
  references it, `context_id` becomes a lie — it no longer addresses the content that was
  actually in force. Freezing makes the id a permanent, checkable statement, and content
  addressing turns resolution into a verification rather than a lookup.
- **Reference-not-copy follows directly from constitution III and from the existing blob
  discipline.** A copied frame is a second source of truth for the same facts; it can drift
  and nothing in the system would notice. A referenced frame is validated once and shared by
  every claim made under it, so the store grows with contexts rather than with claims.
- **A graded verdict is what makes validation diagnosable.** Reporting
  `temporal_interval_inverted` while simultaneously reporting `structural: PASSED` is
  impossible if the function returns `True`/`False`. The verdict is a *reporting* rule, not a
  severity claim: `STALE` is not more false than `UNDERDETERMINED`, it is more actionable.
  Precedence is fixed and documented because a documented arbitrary order beats an
  undocumented emergent one.
- **Purity is what makes verdicts replayable.** A verdict is a record of a judgement made
  under specific extractor, normalisation, ontology and schema versions, so recomputing it on
  read would silently rewrite historical verdicts the moment a schema version is registered.
  It must be persisted, and it can only be trusted as reproducible if the function is pure.
- **The ordering constraint is a data-integrity constraint.** The unique indexes on
  `(tenant_id, frame_fingerprint)` and `(tenant_id, content_hash)` both feed idempotency, so
  a NULL slipping in before the index is created would break the idempotency guarantee
  structurally — the failure mode the feature most needs to eliminate.
- **Immutability of 015 is free to enforce.** The linear, single-head, immutable-revision
  guards already exist and already pass; 016 merely extends them, so the cost of not editing a
  released revision is zero.
- **Substrate over graph.** Keeping durable state in PostgreSQL and treating the graph as a
  rebuildable projection is what makes "projection failure never destroys evidence" true by
  construction rather than by policy.

## Consequences

### Positive

- Every claim answers *why do you believe this*, and every rejection is preserved with its
  decision, reasons, grade components, versions and timestamps and is replayable.
- An unregistered relation type or an undeclared extractor version yields `UNDERDETERMINED`
  and the claim is preserved, so the vocabulary can grow without invalidating stored data.
- Identity validation recomputes both ids from the claim's own material, so tampering is a
  distinct layer from schema invalidity.
- Idempotency and tenant isolation become database constraints, not caller discipline.
- Both install paths are provably equivalent, so a fresh deployment and an upgraded one cannot
  diverge.
- Revision history is queryable by `(tenant_id, logical_relation_id, revision_number)` without
  scanning `relation_claim`.
- Nothing in the migration touches an existing table, so the previous feature's materialization
  tables are untouched and rollback of 015 is unaffected.

### Negative

- Five new tables is substantial surface for one feature, and `relation_claim` alone has about
  thirty columns, most of them nullable timestamps and JSONB columns. JSONB for
  `role_bindings`, `assertion_refs`, `observation_refs`, `source_independence_groups` and
  `contradicts` trades queryability for schema stability; child tables per list would multiply
  the table count well past five.
- A claim is unqueryable without a join: anything that wants "show me the extractor version"
  must resolve `context_ref`. That is the intended cost of reference-not-copy, but it adds a
  hop to every read API.
- A garbage-collected frame leaves a dangling claim. The claim is preserved and reported as
  `context_unresolved` rather than reinterpreted, which is the correct behaviour and is also
  a reachable state the read path must handle.
- Always computing seven layers costs more than short-circuiting. Purity and injected
  pre-computed inputs mitigate it, but it is a real constant factor on the hot path.
- Stable reason codes are now a public contract. Renaming `schema_subject_class_not_allowed`
  breaks consumers, so the codes must be treated as API.
- `ValidationWorld` is a wide constructor argument. Growing it is cheap, but a layer that
  silently reaches for a global instead of an injected value would break purity and is not
  detectable by the type system.
- Proving both install paths requires a live PostgreSQL, which makes that test an integration
  test rather than a unit test.
- The domain `HyperEdge` and the projection `HyperEdge` remain two classes with the same name
  and different identity semantics. This ADR does not merge them.

### Follow-up

- Persist the `ValidationResult` rather than recomputing it on read, and treat
  `sibling_claims` in `ValidationWorld` as the seam for the contradiction-reasoning feature
  that is explicitly out of scope here.
- Adopt `RelationClaim` into the graph stores incrementally, and retire the legacy `e:` edge
  id path once the frontend emits 128-bit ids.
- A frame retention policy. Until one exists, `context_unresolved` is a first-class reachable
  state and must never be handled as an exception.
- Decide whether `complete=False` lineage traces block admission or only degrade the grade —
  an admission-policy question, not a persistence one.
- Any future revision that needs a backfill must insert it between the column addition and the
  index creation and extend the `add_column < backfill < index` assertion rather than relying
  on the no-op placeholder.

## Alternatives considered

**Widen `GraphEdge` in place instead of adding `RelationClaim`.** Rejected. It breaks every
construction site, every store, the Neo4j adapter and the existing tests mid-feature, and the
two objects have genuinely different lifetimes: a `GraphEdge` is rebuildable and disposable, a
`RelationClaim` is durable, status-bearing and never deleted. Conflating them would make
constitution III and invariant 3 pull in opposite directions on a single class. The only
in-place change made to `GraphEdge` is additive — a required `edge_id` with equality keyed on
it.

**Store a mutable context dict on the claim.** Rejected. It makes the claim's context
unfalsifiable: an embedded copy can diverge from the registered frame, and nothing can detect
the divergence because the id and the content are both on the claim and both move together. It
also defeats content addressing, because there is nothing left to recompute a digest against,
and it multiplies storage — a frame shared by ten thousand claims would be stored ten thousand
times, each copy free to drift. The blob discipline behind this is already enforced in code:
an inline descriptor over 4096 bytes is rejected in favour of carrying refs.

**A single boolean `validate()`.** Rejected. It violates invariant 3 in the specific sense
that it makes "we cannot interpret this" indistinguishable from "this is false", and it forces
every caller to re-derive the reason — the exact duplicated judgement logic this feature
exists to remove. Four required outcomes (structurally valid but temporally invalid;
ontology-invalid participant classes; provenance-invalid cross-tenant evidence;
uninterpretable-because-undeclared-version) all return `False` under a boolean, and the fourth
is not a rejection at all.

**A single global truth score per relation.** Rejected. Forbidden by constitution IV in as
many words, and substantively wrong rather than merely disfavoured: the components have
different units and different failure modes, a blend is not monotone under any of them, and it
cannot be inverted. Components are stored separately and the grade is a lookup over a small
table, never a summation.

**Embed the graph as the source of truth for relations.** Rejected. It contradicts
constitution III and invariant 4, and it makes the graph the only copy of the evidence — so a
projection failure destroys the assertion rather than degrading a view. The existing
projection defects make the alternative worse, not better: the Neo4j adapter drops properties
and creates no edge id, the N-ary idempotency guard is a no-op, and `neighbors()` discards
direction.

**Store relations only in the graph backend, with no durable substrate.** Rejected for the
same reason plus a practical one. A store that cannot round-trip its own relations is not a
projection, it is a database with a graph API — and the current adapter cannot: it emits
`MERGE (a)-[r:TYPE]->(b)` with no id and no properties, so the projection can hold at most
one relation of a type between two nodes. Two employment intervals, or two contexts, would be
structurally unrepresentable, and the `relation_id`, `context_ref` and confidence the read API
must return could not be stored at all.

## References

- `specs/016-relation-evidence-graph-fabric/spec.md` — D1, D4, D5; FR-001, FR-005, FR-006,
  FR-007, FR-013 to FR-025, FR-034 to FR-042, FR-047 to FR-050; SC-004 to SC-012.
- `specs/016-relation-evidence-graph-fabric/plan.md` — Constitution Check, Complexity
  Tracking, Project Structure.
- `specs/016-relation-evidence-graph-fabric/data-model.md` — section 4.2 (`RelationClaim`),
  section 5 (`EvidenceContext`), section 7 (`ContextValidator`, layer contracts,
  `ValidationWorld`, grade computation), section 9.1 (`GraphEdge` changes), section 10
  (persistence and migration order).
- `specs/016-relation-evidence-graph-fabric/research.md` — Decision 3 (identity vs revision),
  Decision 4 (immutable content-addressed context), Decision 5 (layered validation and
  verdict precedence), Decision 8 (persistence), defects 1, 2, 3, 5, 6, 9.
- `.specify/memory/constitution.md` — II (evidence-first), III (projection-first), IV (no
  single store or score), VI (process-centric), VII (tenant isolation), invariants 3 and 12,
  Governance (preserved rejections, source independence).
- `apps/projection/graph/abstraction.py:29-37`, `:36-37`, `:87-92`, `:108`, `:128`, `:145-147`,
  `:179-184` — `GraphEdge`, the hash/equality asymmetry, the dead N-ary guard, the direction
  loss.
- `apps/projection/graph/neo4j.py:63-72` — the adapter that drops properties and creates no
  edge id.
- `apps/projection/graph/snapshot.py:22-24`, `:44-99` — rebuild and snapshot defects.
- `apps/shared/domain/hypergraph.py:29-50`, `:53-86`, `:204-216`, `:254-257` — the
  identity/revision split precedent and `HyperGraph.versions()`.
- `apps/shared/domain/temporal_worldline.py:131-134`, `:321-347`, `:468-472`, `:518-535` — the
  digest primitive, `EvidenceRef`, and the wider `__post_init__` pattern deliberately not
  copied.
- `apps/shared/domain/__init__.py:79-88` — `enforce_projection_provenance`, the only
  admission control today.
- `apps/shared/events/ontology_pack.py:36-38`, `:74-79`, `:80-81`, `:95-101` — relation
  vocabulary, the 4096-byte descriptor guard, the never-overwrite rule, version lookup.
- `apps/control-plane/db/migrations/versions/015_worldline_reconstruction.py` and
  `apps/control-plane/tests/unit/test_migration_forward_only.py:29-33`, `:66-76`, `:79-101`,
  `:104-108`, `:111-128` — the immutable-revision pin and the ordering guard.
- `apps/control-plane/db/schema.py` — existing table declarations the five new tables
  accompany.
- ADR-0003 (PostgreSQL role), ADR-0008 (graph abstraction layer), ADR-0009 (graph backend),
  ADR-0011 (event schema), ADR-0012 (provenance), ADR-0022 (indexed worldline relations).
