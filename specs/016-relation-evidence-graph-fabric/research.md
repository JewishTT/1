# Research: Relation & Evidence Graph Fabric

**Feature**: 016-relation-evidence-graph-fabric
**Date**: 2026-09-26

## Decision 1 — Relation identity: 128-bit truncated SHA-256

### Context

Relation identity must be a deterministic function of the relation's *content*, computed
identically by the backend, by the frontend, and on replay, and it must not be able to
alias two different relations. The only live edge-identity path today is a 32-bit FNV-1a
digest implemented in TypeScript at `apps/webapp/src/lib/edgeFormation.ts:56-64`
(`fnv1a`) and consumed by `makeEdgeId` at `apps/webapp/src/lib/edgeFormation.ts:71-76`.
A second, unrelated FNV-1a implementation lives at `apps/webapp/src/lib/graphState.ts:22-23`
and `apps/webapp/src/lib/graphState.ts:64-71`, used for the topology fingerprint
(`entitiesKeyFor`, `graphState.ts:85-95`) and the export checksum
(`checksumOf`, `graphState.ts:184-186`).

Two golden vectors pin the current hash:

- `apps/webapp/src/lib/edgeFormation.test.ts:18` and `:138` —
  `expect(makeEdgeId("ENT-1", "ENT-2", "possible_match", "CE-1")).toBe("e:1d374e53")`.
  This is an **identity** vector.
- `apps/webapp/src/lib/graphState.test.ts:132` — `expect(fnv1a("")).toBe("811c9dc5")`.
  This is the canonical FNV-1a offset-basis vector for a **non-identity** use.

The identity vector is the one that must move. The offset-basis vector must not.

A third width already exists in the codebase: `hyperedge_id` in
`apps/shared/domain/hypergraph.py:29-50` truncates SHA-256 to **16 hex characters**
(64 bits, `hypergraph.py:50`), while `hyperedge_version_id` at
`apps/shared/domain/hypergraph.py:53-86` truncates to **32 hex characters** (128 bits,
`hypergraph.py:86`). So the repository currently carries three different identity widths
across four call sites (8, 16 and 32 hex), which is itself an argument for normalising.

### Decision

All relation identity is `PREFIX + digest128(canonical_material)`, where
`digest128(m) = hashlib.sha256(m.encode("utf-8")).hexdigest()[:32]` and `canonical_material`
is `json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
default=str)` — the exact primitive already implemented as `_digest` at
`apps/shared/domain/temporal_worldline.py:131-134` and `event_id_for` at
`apps/shared/domain/temporal_worldline.py:614-616`. Prefixes are `RL-` for
`logical_relation_id` and `RC-` for `relation_id`. Output is 32 lowercase hex characters
(128 bits), matching `hyperedge_version_id`'s width so the two-level scheme is not wider
than the existing precedent.

FNV-1a is **retired for identity only**. It remains in `edgeFormation.ts` for
`layoutSeed` (`edgeFormation.ts:91-95`) and in `graphState.ts` for `entitiesKeyFor` and
`checksumOf` (layout seeds, view-state fingerprints, export checksums). The
`811c9dc5` vector at `graphState.test.ts:132` therefore continues to pass unchanged; the
`e:1d374e53` vector at `edgeFormation.test.ts:18` and `:138` is replaced by a new pinned
128-bit vector. If the frontend cannot yet emit the backend's 128-bit identity, it is
marked as a derived local view and does not claim backend identity (FR-044) — it does not
silently reuse a 32-bit value under a backend-labelled name.

### Rationale

- **The 32-bit space is too small by five orders of magnitude.** FNV-1a yields 2^32
  distinct ids. The birthday bound for 50% collision probability is
  `sqrt(2 * N * ln 2) = sqrt(2 * 2^32 * ln 2) = 77163` relations. The platform is designed
  for 10^7 relations (`plan.md:59`), which is 130x past the 50% point — a *more likely than
  not* outcome, not a tail risk.
- **The 64-bit width is not free either.** `hyperedge_id` at
  `apps/shared/domain/hypergraph.py:50` gives 2^64 ids with a 50% point of
  `sqrt(2 * 2^64 * ln 2) = 5.06e9`. That is adequate for the current hypergraph volume,
  which is exactly why it has not failed yet; normalising to 128 bits removes the
  question rather than deferring it a second time.
- **128 bits moves the bound to 2.17e19.** `sqrt(2 * 2^128 * ln 2) = 2.1719e19`
  relations. This is ~2.2e12 times the 10^7 design target, so SC-002 (1,000,000 claims
  yield 1,000,000 distinct ids) holds with a margin no test can exhaust. Concretely: at
  2^128 the expected number of collisions among 10^7 relations is
  `C(10^7, 2) / 2^128 ≈ 4.65e15 / 3.40e38 ≈ 1.4e-23` — not "small", but unobservable.
- **SHA-256 over FNV-1a is a security-strength primitive for free.** FNV-1a is a
  non-cryptographic hash with trivially constructible collisions; SHA-256 truncation makes
  collision an infeasible offline exercise rather than a lucky birthday. FR-011 still
  requires collisions to be *surfaced*, not merely unlikely, because a collision is
  indistinguishable from an identity merge at read time.
- **UTF-8 bytes, not UTF-16 code units.** `edgeFormation.ts:59` uses `charCodeAt(i)`,
  which walks UTF-16 code units; a Cyrillic or astral-plane id therefore hashes a
  different byte sequence than `m.encode("utf-8")` on the Python side. Canonicalising to
  UTF-8 bytes first removes a cross-language identity skew that would otherwise surface as
  "the same relation has two ids", which is the exact failure FR-044 is meant to prevent.
- **`json.dumps(..., sort_keys=True, separators=(",", ":"))` is already the house style.**
  `hypergraph.py:41-49`, `hypergraph.py:73-85`, `temporal_worldline.py:131-134` and
  `temporal_worldline.py:137-149` all do it. Using it means the new identity is
  auditable against the same rules an operator already knows, and the audit trail for
  `worldline.py:588-616` (`event_identity_material` / `event_id_for`, which documents
  "The exact material an `event_id` is derived from") is the pattern to copy.

### Consequences

**Positive**
- Identity is a total, auditable function of documented material; `relation_identity_material`
  can be exported and recomputed by an operator without running the pipeline.
- Frontend and backend can agree on identity, which is the precondition for FR-044 and for
  the UI workspace to cite backend relation ids rather than local ones.
- `hyperedge_version_id` (`hypergraph.py:86`) already proves the 32-hex width is accepted
  downstream, so this introduces no new width into the persisted surface.

**Negative / trade-offs**
- 32 hex characters versus 8: 4x the key width on every edge. At 10^7 relations that is
  ~320 MB of key bytes before index overhead, on top of the existing key. Accepted in
  `spec.md:341`.
- Every previously written frontend edge id (`e:xxxxxxxx`) is invalidated. The W5
  persistence payloads pinned by `edgeFormation.test.ts:137-139` carry those ids, so the
  golden-vector test must be rewritten rather than left to fail.
- Two FNV-1a implementations (`edgeFormation.ts:56` and `graphState.ts:64`) remain, with
  the same offset and prime but different signatures (`number` vs `string`). Consolidating
  them is *not* in scope and is left as a follow-up so this feature does not touch
  view-state code.

**Follow-up**
- ADR `docs/adr/0023-relation-identity-and-arity.md` (already listed at `plan.md:223`)
  must record the retained-FNV-1a-for-layout-seeds carve-out explicitly, or the next
  reader will assume any `fnv1a` call is a bug.
- Add a collision-detector test over a generated corpus that asserts the *reporting*
  path (FR-011) works, not only that no collision occurs — otherwise the reporting code
  is as unexercised as `write_edge` (defect 9).

## Decision 2 — Arity modes and participant canonicalisation

### Context

Identity is only well defined once participant order is either preserved or erased
deliberately. Today the frontend erases it unconditionally:
`apps/webapp/src/lib/edgeFormation.ts:72-73` computes
`lo = nodeA < nodeB ? nodeA : nodeB` / `hi = nodeA < nodeB ? nodeB : nodeA` and hashes
`lo, hi` at `edgeFormation.ts:74`, for **all six** declared `EdgeKind` values
(`edgeFormation.ts:12-18`): `assertion`, `evidence`, `possible_match`, `relationship`,
`source_host`, `co_occurrence`. The docstring at `edgeFormation.ts:66-70` states this is
deliberate ("Order-invariant — a→b and b→a yield the same id — so undirected findings
never duplicate"), and the test at `edgeFormation.test.ts:22-27` pins it. The premise is
true for exactly one of the six kinds.

On the Python side direction is stored on write (`abstraction.py:131-132` uses
`edge.source` and `edge.target`) and destroyed on read
(`abstraction.py:179-184`, see defect 2). There is no vocabulary for arity at all: no
`UNDIRECTED` / `DIRECTED` / `NARY` / `TEMPORAL` enum exists, and the only distinction
between a pairwise edge and an N-ary structure is which method you call
(`write_edge` vs `write_hyperedge`, `abstraction.py:97-98`).

### Decision

Introduce `RelationArityMode` with four values and one canonicalisation rule per mode.
The arity mode is itself part of the identity material, so a relation cannot silently
change arity without changing identity.

| Mode | Participant canonicalisation | `logical_relation_id` material | Window in identity? | `neighbors` default |
|---|---|---|---|---|
| `UNDIRECTED` | sort members ascending, dedupe | `{"mode","type","members": sorted(set(...))}` | no | `both` |
| `DIRECTED` | preserve order: `(subject, object)` | `{"mode","type","subject","object"}` | no | `out` |
| `NARY` | sort `(role, member)` pairs by role | `{"mode","type","roles": [[role, member], ...] sorted}` | no | `both` |
| `TEMPORAL` | preserve order; window participates | `{"mode","type","members": ordered, "valid_from","valid_to"}` | **yes** | `out` |

This matches `plan.md:124-129` and `data-model.md:43-52` exactly. Registration rejects a
schema whose declared mode conflicts with its participant shape: `DIRECTED` with role
bindings, or `NARY` with fewer than two bindings (FR-012, `data-model.md:301-302`).

### Rationale

- **`min`/`max` is *correct* for `co_occurrence` and *wrong* for the other seven types,
  and the difference is semantic, not stylistic.** For `co_occurrence` the assertion is
  "these two were observed in the same observation", which is true if and only if the
  reverse is true; the relation is symmetric, so sorting *is* the correct canonical form
  and `edgeFormation.test.ts:105-115` correctly relies on it.
- **`works_for` and `employed_by` are inverses of each other and are both in the planned
  vocabulary.** A symmetric normaliser cannot distinguish "Ivan works for Acme" from
  "Acme works for Ivan", and cannot even represent the inverse type as a different
  relation. FR-008 requires `(A, works_for, B) != (B, works_for, A)`; a symmetric
  canonicalisation makes that unsatisfiable.
- **`located_in` is the clearest proof that sorting manufactures false claims.** Both
  `A located_in B` and `B located_in A` are well-formed and both are generally false. A
  canonicalisation that merges them does not merely lose information — it makes the
  surviving id *stand for a statement that was never made*, which is a direct I-3
  violation (`constitution.md:31`).
- **`owns` and `controls` are the same argument with a partial order.** `controls` is
  antisymmetric by definition; `A controls B` and `B controls A` cannot both hold. Merging
  them removes the possibility of the relation ever being expressed at all.
- **`founded` is directional and asymmetric in the same way as `works_for`**, and it is
  the type most likely to be extracted from a single sentence, so it is the type most
  likely to be ingested in both orientations by different extractor passes — exactly the
  case where a symmetric id silently deduplicates a correct pair of relations into one
  wrong one.
- **`reports_to` is direction-as-role, and the endpoint *classes* differ.** A symmetric
  canonicalisation of `reports_to` allows `ORGANIZATION reports_to PERSON` to occupy the
  same id as `PERSON reports_to ORGANIZATION`; the semantic layer (Decision 6) would then
  have to reject one of two claims that share an identity, which is incoherent.
- **N-ary needs roles, not just members.** `Employment{person=P1, organization=O1,
  role=CEO, location=HQ1}` must be order-insensitive over *pairs*, not over a flat member
  list, or `role=CEO` and `person=CEO` would be indistinguishable. Sorting `(role, member)`
  pairs achieves order-insensitivity while keeping the role assignment load-bearing
  (FR-009).
- **`TEMPORAL` is a separate mode, not a `DIRECTED` variant.** A temporal relation's
  identity must include the window, otherwise two disjoint employment intervals collapse
  into one relation and the worldline cannot express that the person held the role twice
  (which `temporal_worldline.py:995-1079` already models as distinct
  `PRECEDES`/`FOLLOWS` relations between distinct `WorldlineEvent`s). Folding the window
  into the directed material would make *every* directed relation revision-addressed,
  destroying the identity/revision split of Decision 3.
- **Arity in the material means `NARY{person=P1, org=O1}` and `DIRECTED{P1 -> O1}` get
  different ids** even for the same participants, which is what
  `spec.md:187` (edge case, last bullet) requires and what makes the declaration auditable.

### Consequences

**Positive**
- `(A, works_for, B)` and `(B, works_for, A)` diverge; `(A, co_occurs_with, B)` and
  `(B, co_occurs_with, A)` converge. Both are testable as SC-001.
- N-ary member order stops mattering while role permutation starts mattering, which is
  what FR-009 asks for and what no existing code expresses.
- `neighbors()` gains a `direction` parameter with a mode-derived default, so an undirected
  read and a directed read are distinguishable at the call site rather than by convention.

**Negative / trade-offs**
- Adding a field to `GraphEdge` (`data-model.md:498-506`) and changing `__eq__`/`__hash__`
  breaks every construction site. Verified call sites are
  `apps/projection/tests/test_projection.py:66` and `:77` only (defect 9), so the blast
  radius is small — but it is not zero, and the two in-repo constructions use the
  positional 3-argument form, so `edge_id` must be keyword or defaulted for them to keep
  working.
- `NARY` with exactly two members is legal (`spec.md:187`) and produces a *different* id
  from the same pair declared `DIRECTED`. Two consumers writing "the same" employment
  relation under different declarations now create two relations. That is the intended
  behaviour — the declarations genuinely differ — but it will surface as apparent
  duplication until the registry makes arity a first-class, queryable attribute.
- Four modes is one more concept than the current code, which has none. The cost is paid
  once, in the registry, rather than in every consumer.

**Follow-up**
- The relation-type registry must make arity queryable *before* any extractor emits
  relations, or extraction will guess a mode per call site and the identity space will
  fragment. This is a hard precondition for the deferred extraction feature.
- `apps/shared/events/ontology_pack.py:36-38` already lists `works_at`, `owns`, `controls`
  as flat strings. Those three need arity declarations registered before any of them is
  honoured (see Decision 6).

## Decision 3 — Identity vs revision: the two-level id scheme

### Context

The split already exists in the domain and does **not** exist in the projection, and the
projection's docstring misdescribes it.

`apps/shared/domain/hypergraph.py` implements it explicitly:

- `hyperedge_id(edge_type, members, *, tenant_id)` at `hypergraph.py:29-50` — "Stable LOGICAL
  identity of an N-ary relation across all its versions. The single dedup key shared by the
  domain and the graph projection (block G): (edge_type, members, tenant)."
- `hyperedge_version_id(..., valid_from, valid_until, weight, anchor_artifact_id,
  observation_id, provenance)` at `hypergraph.py:53-86` — "Content-addressed id of ONE
  temporal version (block H). Includes valid_until / weight / provenance so distinct content
  is a distinct version."
- `HyperEdge` carries both `logical_id` (`hypergraph.py:104`) and `edge_id`
  (`hypergraph.py:103`), with `logical_id` filled first at `hypergraph.py:132-137` and
  `edge_id` derived *from* it at `hypergraph.py:138-153`.
- `HyperGraph` keys `_versions: dict[logical_id -> {edge_id: edge}]` at
  `hypergraph.py:215` and `_version_order` at `hypergraph.py:216`, and exposes
  `versions(logical_id)` at `hypergraph.py:254-257` — "Every temporal version of one
  logical relation, insertion order." The class docstring at `hypergraph.py:204-208` states
  the intent: "content that differs on any versionable field ... is a NEW temporal version of
  the same `logical_id` — stored alongside, never rejected as 'immutable'."
- `HyperGraph.upsert` even *recomputes* the version id when provenance is attached after
  construction, at `hypergraph.py:228-243`, precisely because provenance is version material.

The projection-level mirror has the docstring/code mismatch. `apps/projection/graph/abstraction.py:46`
asserts:

> "Identity is deterministic on (edge_type, members, valid_from)"

The code at `abstraction.py:71-82` does not use `valid_from`. It returns
`hyperedge_id(self.edge_type, self.source, tenant_id=self.properties.get("tenant_id",
"default-tenant"))`, and `hyperedge_id` hashes `(edge_type, sorted(members), tenant_id)` per
`hypergraph.py:41-49`. So the real identity material is **`(edge_type, members, tenant_id)`**,
with no temporal component at all. The docstring is wrong on two counts: it names a field
that is not in the material, and it omits the field that is.

The plain-edge path has no split because `GraphEdge` (`abstraction.py:29-37`) has no
identifier whatsoever — four fields, `edge_type`, `source`, `target`, `properties`. There
is nothing for a second id to hang off.

### Decision

`RelationClaim` carries two ids with a strict derivation order, mirroring
`hypergraph.py`:

- `logical_relation_id` = `"RL-" + digest128(canonical(logical_material))`, where
  `logical_material` is arity-mode shaped and **excludes** the temporal window, evidence
  refs, context ref and revision number (`data-model.md:90-97`).
- `relation_id` = `"RC-" + digest128(canonical({logical_id, valid_from, valid_to,
  observed_at, published_at, context_ref, observation_refs, assertion_refs,
  revision_number}))` (`data-model.md:99-101`).

Rules:

1. All revisions of one relation share a `logical_relation_id` (FR-003).
2. Distinct content always produces a distinct `relation_id` (FR-003, FR-005).
3. Identical content always produces an identical `relation_id`; two claims with the same
   `relation_id` are byte-identical and the second write is a no-op (I-11, FR-005).
4. `revision_number` is caller-supplied and monotonic within a `logical_relation_id`;
   `supersedes` names the immediately preceding `relation_id`, and
   `supersedes == relation_id` is rejected at construction (`data-model.md:173`).
5. The stale docstring at `abstraction.py:46` is corrected to state the actual material
   `(edge_type, members, tenant_id)`, and — for the projection-level `HyperEdge` — the
   *store key* is changed to the **version** id, not the logical id.

### Rationale

- **The precedent is sound and should be reused rather than reinvented.** `hypergraph.py`
  demonstrates the two-level scheme survives contact with a real temporal store, and
  `HyperGraph.versions()` (`hypergraph.py:254-257`) already answers "all versions of this
  relation" — the exact query Decision 3 makes necessary. Reusing its conventions is
  cheaper than a parallel scheme and prevents the two from disagreeing about what a
  relation is.
- **The two widths are already asymmetric, and the new scheme normalises them.**
  `hyperedge_id` truncates to 16 hex (`hypergraph.py:50`), `hyperedge_version_id` to 32 hex
  (`hypergraph.py:86`). A logical id does not need the width a version id does, but
  having two widths makes every cross-module comparison width-dependent. Normalising both
  to 32 hex removes a class of bug at the cost of 16 bytes per logical id.
- **The docstring mismatch is not cosmetic — it changes what the store keys on.** Because
  `abstraction.py:71-82` returns the *logical* id, `write_hyperedge` at
  `abstraction.py:147` does `self._hyperedges[edge.edge_id] = edge`, so two temporal
  versions of the same N-ary relation **overwrite each other** in the projection store.
  The domain `HyperGraph` stores both (`hypergraph.py:247`); the projection keeps one. A
  reader trusting the docstring would believe the projection is versioned, and it is not.
- **The dead guard at `abstraction.py:145` hides this.** `if edge in self._hyperedges`
  tests a `HyperEdge` against a `dict[str, HyperEdge]`'s *keys*. `HyperEdge.__eq__`
  (`abstraction.py:87-92`) returns `False` for any non-`HyperEdge`, so the test is always
  `False`. The guard was evidently written to short-circuit a repeat write, but the code
  beneath it (`abstraction.py:147`) overwrites by key, so the store's *current*
  idempotency is incidental — it holds only because `edge_id` happens to be a pure function
  of the logical material. That accident is exactly what makes the version-overwrite
  invisible, and it is the mechanism by which a corrected hyperedge silently replaces a
  prior one.
- **The plain-edge path could not have the split without an id to start from.** Adding
  `edge_id` to `GraphEdge` (`data-model.md:498-506`, FR-035) is the enabling change; the
  two-level scheme is then available to the plain path for free. Keying `__hash__` and
  `__eq__` on `(edge_id,)` (`data-model.md:508-510`) makes idempotency a function of
  identity rather than of accidental field equality, which is what the current
  hash/eq asymmetry (defect 3) breaks.
- **Version material must include the evidence and context, not just the window.** If
  `relation_id` covered only `(logical_id, valid_from, valid_to)`, then re-asserting the
  same interval with a new observation would be a silent overwrite and the observation
  would be lost — the same class of loss the constitution forbids in Governance
  (`constitution.md:73`: "Rejected analysis outputs ... are preserved with decision,
  reasons, score vectors, versions, and timestamps for replay").

### Consequences

**Positive**
- "All revisions of this relation" becomes a single indexed lookup
  (`ix_relation_claim_logical` on `(tenant_id, logical_relation_id)`, `data-model.md:625-630`).
- A corrected employment window is a *revision* with `supersedes` set, not a second
  unrelated edge — the correction is itself auditable (FR-006, I-3).
- Identical content is structurally idempotent, so callers cannot get it wrong.
- The projection's hyperedge store finally agrees with the domain's on what a relation is.

**Negative / trade-offs**
- Two id columns plus a `revision_row_id` (`data-model.md:636`) plus a third table
  (`relation_claim_revision`) is more storage and more write amplification than a single id.
- `revision_number` is caller-supplied, so it is a coordination responsibility the model
  cannot verify without re-reading the store. A store-side allocator is deferred.
- Changing the projection store key from logical id to version id changes what
  `InMemoryGraphStore.hyperedge(edge_id)` (`abstraction.py:152-153`) means for existing
  callers. Verified callers: `apps/projection/tests/test_projection.py` does not call it;
  no production caller exists.
- Correcting the `abstraction.py:46` docstring is a source change in a file other features
  may be touching in parallel; it is sequenced into Phase 1 with the `edge_id` change.

**Follow-up**
- A legacy-id alias column or lookup shim is needed for relations written before this
  feature (`spec.md:340`). It is explicitly *not* in this feature's schema; the migration
  note is the deliverable.
- The domain `HyperEdge` and the projection `HyperEdge` remain two classes with the same
  name and different identity semantics. Merging them is a later cleanup; this feature only
  corrects the docstring and the store key.

## Decision 4 — Immutable content-addressed EvidenceContext

### Context

Today, the conditions under which an assertion may be interpreted are not an object.
`EvidenceRef` at `apps/shared/domain/temporal_worldline.py:321-347` carries
`source_record_id`, `record_hash`, `observation_id`, `dataset_id`, `extraction_version`,
`extractor` and `span` — but it is a per-record ref, not a frame, and it has no
`tenant_id`, no `investigation_id`, no ontology or normalisation version, no source family
and no completeness or trust state. Those travel as loose attributes on
`StreamRecord` (see `_RESERVED_PAYLOAD_KEYS`, `temporal_worldline.py:103-116`).
Nothing validates them together and nothing prevents a claim from being interpreted under
a context that does not license it.

Two constraints shape the design. First, constitution III (`constitution.md:12`): the
graph is a rebuildable artifact, so the frame must be reconstructible from durable state
and not be the only copy of anything. Second, I-5 (`constitution.md:71` / the
`enforce_no_blobs` guard at `apps/shared/domain/domain/__init__.py:71-76` equivalent, and
`ontology_pack.py:74-79` which rejects a descriptor over 4096 bytes as "carry refs, not
blobs"): the frame must be small. It is a frame, not a payload.

The frozen-dataclass-with-derived-id pattern already exists three times in the codebase
and is the precedent to copy: `hypergraph.py:131-153` (`object.__setattr__` inside
`__post_init__` to sort members and fill `logical_id` then `edge_id`),
`temporal_worldline.py:468-472` and `:742-748` (`object.__setattr__` to normalise fields
and fill a content-addressed `fingerprint` / `integrity_fingerprint`).

### Decision

`EvidenceContext` is a `@dataclass(frozen=True)` with the 23 fields of FR-013
(`data-model.md:210-242`). Rules:

1. **`context_id` is content-addressed**: `"CX-" + digest128(canonical(all fields except
   context_id))` (`data-model.md:248`). Two independently constructed frames with the
   same field values yield byte-identical ids (FR-014, SC-009).
2. **The frame is frozen** (FR-015). `__post_init__` uses `object.__setattr__` **only** to
   fill the derived `context_id` (and to reject an inverted `valid_to < valid_from`,
   `data-model.md:249`). No other field is ever written after construction. This mirrors
   `hypergraph.py:131-153` exactly and is deliberately narrower than
   `temporal_worldline.py:528-535`, which also rewrites `participants`, `evidence` and
   `attributes` in `__post_init__`.
3. **Reference, not copy** (FR-018, I-5): a `RelationClaim` holds `context_ref: str` and
   nothing else. There is no embedded frame, no denormalised copy, no snapshot of the
   frame on the claim.
4. **Resolution is loud**: `ContextResolver.resolve` returns `None` and the validator
   raises reason code `context_unresolved`; it never substitutes a default frame
   (`data-model.md:263-264`, FR-016).
5. **Cycle detection lives in the resolver, not the frame** (`data-model.md:251-252`),
   because a frame cannot see its siblings. `context_parent_cycle` is a *validation
   outcome*, and the frame is still storable — it is evidence, not a verdict.
6. **A frame is never a verdict.** A frame with a missing parent, a `PARTIAL`
   completeness, or a `DISPUTED` trust state is storable; only the *claim interpreted
   under it* acquires a degraded verdict (`spec.md:80-81`).

### Rationale

- **Immutability is the precondition for sharing.** If a frame can be edited after a
  claim references it, then the claim's `context_id` becomes a lie: the id no longer
  addresses the content that was actually in force. Freezing makes `context_id` a
  permanent, checkable statement. `temporal_worldline.py:518-535` applies the same
  reasoning to `WorldlineEvent`.
- **Content addressing makes the id a verification, not a label.** The claim stores
  `context_id`; the store stores the frame. Recomputing the digest over the stored frame
  detects a corrupted or hand-edited row, which a UUID would not.
- **Reference-not-copy follows directly from constitution III** (`constitution.md:12`) and
  from the existing blob guard. A copied frame is a second source of truth for the same
  facts; it can drift, and nothing in the system would notice. A referenced frame can be
  validated once and shared by every claim made under it.
- **`object.__setattr__` restricted to the derived field** keeps the frozen guarantee
  meaningful. The wider pattern in `temporal_worldline.py:528-535` is defensible for
  normalisation but would be a hazard here: silently rewriting caller-supplied frame
  fields would mean two callers passing semantically equal frames get different stored
  values and therefore different `context_id`s, defeating SC-009.
- **`investigation_id` as a first-class field** satisfies constitution VI
  (`constitution.md:21`, "The user creates an Investigation — not a graph") and makes
  process-scoping structural rather than a filter applied at query time.
- **Source family and independence group belong in the frame**, not only on the claim,
  because independence is a property of *how the source was obtained*, not of the
  relation. Two captures of the same wire story share a family; the frame is the only
  place that knows. This is what makes FR-034 implementable at all.
- **The frame is small by construction** — 23 scalar/JSON columns, no raw text — so it is
  compatible with the 4096-byte inline-descriptor discipline already enforced at
  `ontology_pack.py:74-79`.

### Consequences

**Positive**
- Every claim can be replayed under the exact conditions that produced it, by resolving
  one id.
- Two claims made from the same document segment under the same versions share one frame
  row, so the store grows with *contexts*, not with claims.
- Tenant isolation is checkable at the frame (`context.tenant_id == claim.tenant_id` →
  `INVALID/provenance_tenant_mismatch`, `spec.md:79`), which is what FR-048 needs.
- The 32-hex content address means a frame can be re-registered idempotently, so a replay
  of the durable log converges rather than duplicating.

**Negative / trade-offs**
- The claim is unqueryable without a join. Anything that wants "show me the extractor
  version" must resolve `context_ref`; there is no denormalised shortcut. This is the
  intended cost (FR-018) but it does add a hop to every read API.
- A garbage-collected frame leaves a dangling claim (`spec.md:184`,
  `context_unresolved`). The claim must be preserved, not reinterpreted, so operators see
  a loud failure rather than a plausible default.
- `parent_context_id` introduces a DAG over frames, and cycle detection lives outside the
  frame, so a cycle is only ever caught at validation time — never at write time.
- The frame is immutable, so "the context changed" is expressed by registering a *new*
  frame and issuing a new claim revision, not by editing. That is more rows and more
  revision numbers for what a mutable model would call an update.

**Follow-up**
- The `claim_context_lineage` table (`data-model.md:667-681`) stores the hop list, not the
  frame; a frame's `parent_context_id` chain and a lineage trace are different artefacts
  and must not be conflated.
- A retention policy for frames is out of scope. Until one exists, `context_unresolved` is a
  reachable state and the validator must handle it as a first-class verdict, not an
  exception.

## Decision 5 — Layered validation and verdict precedence

### Context

Validation is currently structural and boolean by construction. The graph layer's only
admission control is provenance presence:
`enforce_projection_provenance` at `apps/shared/domain/__init__.py:79-88` checks that
`event_id` and `observation_id` are *keys* and raises `ProjectionRebuildableError`
otherwise. It does not check tenant, versions, schema, intervals or endpoints. There is no
`validate` function anywhere in the projection or shared domain layers, and no notion of a
*reason* for a rejection.

The spec requires four materially different failure kinds to be distinguishable
(`spec.md:87-102`): a structurally sound claim with an inverted interval, a claim whose
participant classes are inadmissible under its relation type, a claim resting on another
tenant's observation, and a claim that is merely uninterpretable because it declares no
extractor version. A boolean makes the first three indistinguishable from the fourth, and
the fourth is not a rejection at all.

### Decision

`validate(context, claim, world) -> ValidationResult` runs exactly seven layers, in order,
and **always reports all seven outcomes**:

1. `structural`
2. `semantic`
3. `temporal`
4. `provenance`
5. `identity`
6. `cross_source`
7. `graph_constraints`

Each layer yields a `LayerOutcome` of `PASSED` / `FAILED` / `INDETERMINATE` / `NOTED` and
zero or more `ValidationReason` records, each with a stable snake_case `code`, the raising
`layer`, a `detail` string and optional `evidence` refs (`data-model.md:311-341`). The
result carries one graded verdict, chosen by fixed precedence:

```text
INVALID > CONFLICTING > STALE > INCOMPLETE > UNDERDETERMINED > VALID
```

The verdict is a total order so callers get one comparable answer; the per-layer map stays
visible so nothing is lost. **The function never returns `True`/`False`, never mutates
its inputs, and performs no I/O** — every external dependency is injected through
`ValidationWorld` (`data-model.md:376-386`): `schemas`, `contexts`,
`admitted_entity_ids`, `known_entity_ids`, `active_ontology_versions`,
`known_ontology_versions`, `sibling_claims`.

### Rationale

- **A boolean is forbidden by invariant I-3** (`constitution.md:31`, "Assertion != truth";
  also `AssertionNotTruthError` at `apps/shared/domain/__init__.py:34-38`). A bare
  `False` asserts one thing — "not acceptable" — which conflates *wrong* with
  *uninterpretable* with *stale* with *incomplete*. Collapsing those is precisely the
  conflation I-3 exists to prevent: a claim that is correct but was produced under a
  retired ontology version has not become false.
- **A boolean forces every caller to re-derive the reason.** Callers would have to
  re-inspect the claim to learn *why* validation failed, which reintroduces exactly the
  duplicated derivation logic across projection, API and UI that this feature exists to
  eliminate. With structured reasons the reason is produced once, at the point of
  judgement, and travels with the result.
- **All seven outcomes are always computed, even after an earlier layer fails.** The
  layers answer different questions, and "the temporal layer failed" is only meaningful if
  the reader can also see that the structural layer passed. `spec.md:95` (SC-005) makes
  this exact point: `valid_from > valid_to` must report `INVALID/temporal_interval_inverted`
  *and* `structural: PASSED`. Short-circuiting would make the verdict correct and the
  diagnosis unavailable. It also means a fix applied to one layer surfaces previously
  hidden failures in another, which is the point of a layered contract.
- **The validator is pure with an injected `ValidationWorld`.** Purity is what makes the
  result reproducible and replayable (FR-050) and what keeps validation from becoming a
  pipeline bottleneck (`spec.md:342`): the expensive layers (`cross_source`,
  `graph_constraints`) receive pre-computed sets rather than issuing queries. Precedent:
  `temporal_worldline.py:838-849` explicitly pushes the state machine out and takes
  `before_state` / `after_state` as caller-supplied inputs for the same reason.
- **Verdict precedence orders *severity of interpretation problem*, not severity of
  modelling error.** `INVALID` is highest because a claim that is affirmatively wrong must
  not be admitted under any other label. `CONFLICTING` is next because an unresolved
  contradiction is not admissible even if each individual claim is well-formed. `STALE`
  precedes `INCOMPLETE` precedes `UNDERDETERMINED` because "we knew this and it has aged"
  is more actionable than "part of this is missing", which is more actionable than "we
  cannot tell". `VALID` is the floor. Precedence is a *reporting* rule, not a *severity*
  claim: a `STALE` claim is not more false than an `UNDERDETERMINED` one.
- **A null context short-circuits to `INVALID/provenance_context_missing` with all seven
  layers still reported** (`data-model.md:388-389`) — the "always seven" rule holds even
  on the degenerate input.
- **`NOTED` is distinct from `PASSED`.** `temporal_non_overlap` (FR-024) and
  `publication_count_exceeds_independent_count` are facts about the claim, not defects.
  Recording them under `NOTED` means a caller can distinguish "checked and fine" from
  "not applicable", and means disjoint validity intervals for the same relation type stay
  `VALID` with a note rather than becoming a contradiction (`spec.md:101`).
- **`evidence_grade` stores components, never a sum** (FR-025, constitution IV at
  `constitution.md:15`): `independent_source_count`, `publication_count`, `completeness`,
  `trust_state` and `confidence` are persisted separately (`data-model.md:394-400`), and
  the grade is a lookup over them, never a weighted blend.

### Consequences

**Positive**
- Callers distinguish all four required failure kinds with no re-derivation
  (SC-004 through SC-008).
- Every rejection is preserved with its decision, reasons, components, versions and
  timestamps and is replayable (FR-050, constitution `constitution.md:73`).
- An unregistered relation type yields `UNDERDETERMINED/schema_unregistered` and the claim
  is preserved, so the vocabulary can grow without invalidating stored data (FR-023).
- Identity validation recomputes both ids from the claim's own material, so tampering is
  detected as a distinct layer from schema invalidity.

**Negative / trade-offs**
- Always computing seven layers costs more than short-circuiting. Mitigated by purity and
  injected pre-computed inputs, but it is a real constant factor on the hot path.
- The verdict precedence is a total order, which means it is arbitrary among verdicts that
  never co-occur in practice. It is nonetheless fixed and documented, because a
  *documented* arbitrary order beats an undocumented emergent one.
- Stable reason codes are now a public contract. Renaming `schema_subject_class_not_allowed`
  breaks consumers; the codes must be treated as API.
- `ValidationWorld` is a wide constructor argument. Growing it is cheap, but a layer that
  silently reaches for a global instead of an injected value would break purity and is not
  detectable by the type system.

**Follow-up**
- The 7-layer result is the input to contradiction *reasoning*, which is explicitly out of
  scope (`spec.md:322`). `sibling_claims` in `ValidationWorld` is the seam it plugs into.
- The read API must persist the `ValidationResult`, not recompute it on read: a verdict is
  a record of a judgement made under specific versions (`evaluated_versions`,
  `data-model.md:351`), and recomputing on read would silently change historical verdicts
  when a schema version is registered.

## Decision 6 — Relation schemas as a constraint system

### Context

Relation semantics are currently split across two places and expressed in neither.

- `apps/shared/events/ontology_pack.py` — note the path: there is **no**
  `apps/shared/domain/ontology_pack.py`. The registry lives under `events/`, is
  already persisted (`ontology_packs`, `apps/control-plane/db/schema.py:818`), and
  enforces a `DRAFT -> REGISTERED -> ACTIVE` lifecycle
  (`ontology_pack.py:17-20`, `68-84`, `86-93`) with a hard "never overwrite a version"
  rule at `ontology_pack.py:80-81`.
- But its relation vocabulary is a flat `list[str]`: `["works_at", "owns", "controls",
  "corresponds_to", "linked_to"]` (`ontology_pack.py:36-38`), checked only by membership
  in `allows_relation` (`ontology_pack.py:45-46`). There is **no** subject class, **no**
  object class, **no** arity, **no** role binding, **no** temporal semantics, **no**
  evidence pattern and **no** admission rule. `works_at` and `corresponds_to` are
  indistinguishable to the registry except by name.
- Meanwhile the actual admissible-relation knowledge lives in extractor code, spread
  across `apps/interpretation/extractors/`, where it cannot be reviewed as a set.

The ontology pack is therefore a *versioned name list*, not a constraint system. It gives
staleness detection (FR: `active_ontology_versions` / `known_ontology_versions` in
`data-model.md:384-385`, using `OntologyPackRegistry.active_for` at
`ontology_pack.py:95-98` and `versions()` at `ontology_pack.py:100-101`) but it cannot
constrain anything.

### Decision

Ship a separate `RelationSchema` registry (`data-model.md:277-306`) as the constraint
system, and do **not** fold it into the ontology pack in this feature.

`RelationSchema` declares `relation_type`, `arity_mode`, `allowed_subject_classes`,
`allowed_object_classes`, `allowed_role_bindings`, `allowed_role_classes`,
`admissible_evidence_patterns`, `temporal_semantics`, `admission_rule_id`,
`schema_version` and `allow_repeated_member` (FR-026, `data-model.md:278-291`).
`temporal_semantics` is one of `POINT`, `REQUIRED_INTERVAL`, `OPTIONAL_INTERVAL`,
`OPEN_ENDED` (FR-027). `RelationSchemaRegistry` exposes `register`, `get`,
`vocabulary()` (deterministically ordered, FR-028), `arity_of` (`data-model.md:294-299`).

Registry semantics, mirroring the ontology pack's immutability rule
(`ontology_pack.py:80-81`): re-registering a `relation_type` with a *different*
`schema_version` is a new version and is allowed; re-registering with the *same* version
and different content is rejected (`data-model.md:304-305`).

**Scope: this feature ships the registry, the persistence for its versions
(`relation_schema_version`, `data-model.md:650-665`), and the validator's consumption of
it. It does not rewire any extractor.**

### Rationale

- **Ontology-first would be a coupling mistake.** The ontology pack is the *entity* type
  system: `entity_types` at `ontology_pack.py:29-34` is `PERSON`, `ORG`, `LOCATION`,
  `EMAIL`, … Extending it into per-relation arity, roles, evidence patterns and admission
  rules turns one versioned name list into a heterogeneous document with two independent
  lifecycles (pack activation per tenant at `ontology_pack.py:86-93` versus schema
  versioning per relation type). Every ontology change would then force a relation-schema
  migration. Keeping them separate lets the ontology answer "is this class admissible"
  and the schema answer "is this relation admissible", and lets a relation type exist
  before its participants are fully ontologised.
- **The registry is the single reviewable statement of relation semantics.** Today adding
  a relation type is a code change in `apps/interpretation/extractors/*` in several places
  with no single place to review. A registry makes the vocabulary data, which is the stated
  precondition for a relation-type registry and for ontology versioning (`spec.md:109`).
- **Three consumers, one declaration** (FR-028): the relation-candidate proposer, the
  validator and the admission-rule evaluator all read `RelationSchemaRegistry.vocabulary()`
  and none embeds its own relation list. This is the same "no vendor type in domain
  logic" discipline as constitution V (`constitution.md:18`) applied to relation semantics.
- **Versioning is required for the validator to be honest.** A claim records the
  `schema_version` in force when it was produced (FR-029, `data-model.md:148`). Without a
  versioned registry, re-registering a schema silently changes the meaning of every
  previously validated claim.
- **Not rewiring extractors is a deliberate, bounded coupling.** The risk in `spec.md:343`
  is real: schema-driven extraction couples the extraction layer to the registry. Shipping
  the registry first makes the consumption contract versioned and testable
  (`spec.md:111`) so extraction can adopt it independently. The three known extractor
  defects (defects 10, 11, and the `_dedup` key) are fixable on their own terms and should
  not be blocked behind a schema migration.
- **The ontology pack is still load-bearing for staleness.** `ValidationWorld`'s
  `active_ontology_versions` / `known_ontology_versions` map onto
  `OntologyPackRegistry.active_for` and `.versions` (`ontology_pack.py:95-101`), giving
  FR's `STALE/ontology_version_stale` a lookup rather than an embedded version list
  (`spec.md:310`).

### Consequences

**Positive**
- A new relation type is a registry entry plus a row in `relation_schema_version`, not a
  code change in N extractors.
- `schema_unregistered` yields `UNDERDETERMINED`, so the vocabulary can grow without
  invalidating stored claims (FR-023, SC-008).
- `temporal_semantics=REQUIRED_INTERVAL` turns "no `valid_from`" into
  `UNDERDETERMINED/temporal_interval_required` rather than a silent acceptance
  (`spec.md:116`).
- Registration rejects arity/participant-shape conflicts (FR-012), so an incoherent
  declaration cannot enter the vocabulary.

**Negative / trade-offs**
- Two registries now exist. A reader must know that `ontology_packs` governs entity classes
  and `relation_schema_version` governs relation types. This is a real comprehension cost.
- The three ontology relation names (`works_at`, `owns`, `controls`) are already in
  production use as strings (`ontology_pack.py:36-38`) and have no schema. Until they are
  registered, claims of those types validate as `UNDERDETERMINED/schema_unregistered` —
  which is the correct honest answer, but it will surface as a new verdict class in
  existing data.
- Nothing consumes the registry for extraction in this feature, so the registry is
  initially read only by the validator. A registry with one reader is less valuable than a
  registry with three, and this feature does not change that.

**Follow-up**
- Register `works_at` / `owns` / `controls` with explicit arity and classes as the first
  migration step of the relation-candidate extraction feature, and reconcile `works_at`
  against the spec's `works_for` naming.
- Decide, in the ontology-versioning feature, whether the relation vocabulary moves into
  the pack or stays linked to it by `ontology_version` reference. This feature keeps them
  separate and says so.

## Decision 7 — Evidence lineage and explicit incompleteness

### Context

Constitution II (`constitution.md:9`) requires the full chain
`Finding -> ... -> Graph/Assertion -> Evidence -> Observation -> Raw Object -> Source`, and
the lineage `Source -> Capture -> Observation -> Segment -> Mention -> Candidate ->
Assertion -> Relation -> Entity` exists today only as a naming convention. There is no
object that walks backward from a relation and no object that walks forward from a source.
`GraphEdge` has no id to start a backward walk from (`abstraction.py:29-37`), and
`RelationClaim` would have the same problem without `relation_id`.

The existing code is, however, explicit about one thing: a derived pairwise view is *not*
the authority. `HyperGraph.clique_projection` at `hypergraph.py:285-308` is documented as
"Deterministic pairwise projection (derived, lossy — explicit)... N-ary structure is
forgotten by design, so native hyperedges remain the authoritative form." The same
discipline is stated for the projection at `abstraction.py:44-45` and for the Neo4j
reification at `neo4j.py:36-43`. Lineage must obey the same rule: a hop that is derived is
labelled as derived, never presented as the original.

### Decision

`EvidenceGraph` (`data-model.md:455-462`) is an adjacency structure over typed
`EvidenceHop` records (`kind`, `node_id`, `label`, `relation_id`, `tenant_id`; hop kinds
`SOURCE`, `CAPTURE`, `OBSERVATION`, `SEGMENT`, `MENTION`, `CANDIDATE`, `ASSERTION`,
`RELATION`, `ENTITY`). It exposes `backward(node_id)` and `forward(node_id)`, both
returning a `LineageTrace` (`subject_id`, `direction`, `hops`, `complete`,
`first_unresolved_hop`, `unresolved_node_id`; `data-model.md:437-444`).

The canonical backward chain order is fixed:

```text
RELATION -> ASSERTION -> MENTION -> SEGMENT -> OBSERVATION -> CAPTURE -> SOURCE
```

Forward traversal is the reverse: `SOURCE -> CAPTURE -> OBSERVATION -> SEGMENT ->
MENTION -> CANDIDATE -> ASSERTION -> RELATION -> ENTITY`.

**The incompleteness contract (FR-033):** traversal is depth-limited by the canonical
chain order and **stops at the first missing hop**, returning `complete=False` with
`first_unresolved_hop` naming the hop kind and `unresolved_node_id` naming the node it
tried to resolve. A traversal that cannot complete **never returns an empty list and never
returns a silently truncated trace**. An empty list and a truncated trace are
indistinguishable to a caller, and the difference between "there is no evidence" and "the
evidence chain is broken" is the whole point of the exercise.

`independent_source_count` is derived from `source_independence_groups` and is stored
**separately** from `publication_count` (FR-034, `data-model.md:177-179`); a `disputed`
trust state caps the grade at `weak` (`data-model.md:409`).

### Rationale

- **Explicit incompleteness is the constitutional requirement, not a nicety.** "Every
  analytical result must be reproducible from source observations/evidence"
  (`constitution.md:9`) is unsatisfiable if a broken chain looks like a complete one. A
  `complete=False` trace with a named first unresolved hop is *actionable*: an operator
  knows exactly which hop to repair. An empty list is not.
- **`first_unresolved_hop` names a *kind*, not a position.** The repair differs by kind —
  a missing `SEGMENT` is a segmentation failure, a missing `MENTION` is an extraction
  failure, a missing `CAPTURE` is an acquisition failure. A position index
  (`hops[3]`) would require the reader to re-derive the kind from the canonical order
  table; a kind is self-describing.
- **Traversal is depth-limited, not breadth-limited.** The chain is a fixed linear order
  by construction (`RELATION` to `SOURCE`). Allowing arbitrary edges would let a
  lineage walk wander and would need cycle handling; the linear order makes the traversal
  total, terminating, and order-independent.
- **A hop with `relation_id` set carries the assertion that grounds it** (FR-032), so a
  forward trace returns derived relations *with* their grounding assertion rather than
  requiring a second lookup.
- **Separating `publication_count` from `independent_source_count` is a constitution
  requirement in as many words**: "Source independence (copied/derived sources) is
  considered in evidence fusion; publication count is not treated as independent-source
  count" (`constitution.md:73`). `spec.md:135` makes it testable: two observations from
  one source family yield one group and `independent_source_count == 1`.
- **The direction asymmetry is intentional.** Backward goes relation-to-source; forward
  goes source-to-relation-*and*-entity. Including `ENTITY` only in the forward direction
  reflects that a relation is grounded in evidence, whereas an entity is *derived from*
  relations, not the other way round — the reverse edge would be a resolution claim, which
  is a different feature (multi-pass entity resolution, `spec.md:321`).
- **Lineage is the cheapest possible integration surface for the UI**
  (`spec.md:126`): one traversal API, and the evidence panel is a consumer of it.

### Consequences

**Positive**
- SC-003 is satisfiable as stated: 100% of relations produce either a trace to a source or
  a `complete=False` trace naming the first unresolved hop.
- A broken chain becomes an operational signal rather than an invisible gap.
- The independence contract is enforceable in one function
  (`independence_groups(observation_refs, source_family_of)`, `data-model.md:469-471`),
  which is where a copied-source bug will be caught.
- `claim_context_lineage` (`data-model.md:667-681`) makes the trace durable and
  content-addressed, so a trace can be compared across runs.

**Negative / trade-offs**
- The linear chain is a simplification. Real lineage can branch (one observation producing
  two mentions producing two candidates) and the `EvidenceGraph.add_hop(hop, *,
  forward, backward)` signature (`data-model.md:457-458`) permits it, but the traversal
  contract only describes the canonical spine. Branching traces will produce more than one
  path and the first-unresolved-hop rule is defined on the spine.
- Recording traces in a table means trace volume grows with claim volume. The
  `hops` column is JSONB and unbounded.
- `independent_source_count` requires resolving each observation ref to a source family,
  which is a join the validator cannot do itself (purity, Decision 5) — it must arrive
  pre-computed on the claim as `source_independence_groups`. If the claim's groups are
  wrong, the validator will faithfully report the wrong independence.

**Follow-up**
- The `mentions` / `candidates` / `assertions` tables already exist
  (`apps/control-plane/db/schema.py:230`, `:253`, `:314`), so the middle of the chain is
  joinable. `Capture` and `Segment` have no table in `schema.py`'s tablename list; the hop
  kinds exist ahead of their storage. This must be resolved before the lineage feature can
  promise a complete chain.
- Whether a `complete=False` trace blocks admission or only degrades the grade is a policy
  decision for the admission feature, not this one.

## Decision 8 — Persistence: five tables, forward-only migration

### Context

Persistence is PostgreSQL via Alembic, with the schema declared in
`apps/control-plane/db/schema.py` (39 existing tables, `schema.py:93` through
`schema.py:996`) and the version chain in
`apps/control-plane/db/migrations/versions/`. The chain is governed by two tests in
`apps/control-plane/tests/unit/test_migration_forward_only.py`:

- `test_released_revisions_are_not_edited` (`:66-76`) pins revision
  `014_temporal_materialization.py` by SHA-256 (`:29-33`) — a released revision is
  immutable.
- `test_revision_graph_is_linear_and_has_a_single_head` (`:79-101`) asserts exactly one
  root and exactly one head and no branching, so "upgrade head" is unambiguous.
- `test_worldline_revision_follows_temporal_materialization` (`:104-108`) pins
  `015_worldline_reconstruction` as a child of `014_temporal_materialization`.

And, critically, `test_worldline_migration_creates_new_tables_before_indexing_them`
(`:111-128`) asserts the **ordering constraint** inside `upgrade()`:
`add_column < backfill < index`. Its docstring explains why: "Creating
`uq_materialization_outbox_active` before the backfill would let NULL-fingerprinted rows
slip through, leaving exactly the pre-existing rows the index exists to constrain
unconstrained." The corresponding statements are at
`015_worldline_reconstruction.py:88` (add column), `:168` (backfill call) and `:223` (index
creation).

### Decision

One new revision, `016_relation_evidence_graph`, `down_revision = "015_worldline_reconstruction"`
(`data-model.md:691`). Revision 015 is immutable and is *not* edited. Five new tables:

1. **`evidence_context`** — the frame, keyed by `context_id` (`String(64)` PK), with
   `frame_fingerprint` and a unique index `uq_evidence_context_fingerprint` on
   `(tenant_id, frame_fingerprint)` for idempotent registration, plus
   `ix_evidence_context_tenant` / `_observation` / `_source` / `_investigation`
   (`data-model.md:552-586`).
2. **`relation_claim`** — keyed by `relation_id` (`String(64)` PK), carrying
   `logical_relation_id`, `revision_number`, arity mode, role bindings, the full temporal
   interpretation, evidence refs, `context_ref`, `source_independence_groups`, the three
   version fields plus `schema_version`, `status`, `confidence`, `evidence_grade`,
   `supersedes`, `contradicts` and `content_hash`; unique index `uq_relation_claim_content`
   on `(tenant_id, content_hash)` plus `ix_relation_claim_tenant` / `_logical` / `_type` /
   `_subject` / `_object` / `_context` (`data-model.md:588-630`).
3. **`relation_claim_revision`** — the append-only revision ledger, keyed by
   `revision_row_id` (`logical_id + "-r" + revision_number`), with a unique index on
   `(tenant_id, logical_relation_id, revision_number)` (`data-model.md:632-648`).
4. **`relation_schema_version`** — the versioned relation vocabulary, unique on
   `(tenant_id, relation_type, schema_version)` (`data-model.md:650-665`).
5. **`claim_context_lineage`** — durable `LineageTrace` records, content-addressed by
   `lineage_id`, indexed on `(tenant_id, relation_id, direction)`
   (`data-model.md:667-681`).

**Ordering constraint, generalised and asserted for 016:** create the five tables → add
columns → backfill → create indexes, including the unique ones, **only after any
backfill** (`data-model.md:684-689`). `downgrade()` runs in strict reverse: indexes, then
tables. 016 adds no columns to existing tables and requires no backfill; the backfill step
is recorded as an explicit no-op assertion so that the ordering invariant is *structurally*
enforced for this revision and mechanically checkable for the next one that does need one.

`test_migration_016_forward_only.py` proves both install paths reach the same schema: a
fresh install and an install with revision 015 already applied, compared programmatically
(not by digest — the existing test's own docstring at `:12-13` says "Digest values cover
file content only; they are not a substitute for verifying both install paths against a
live database").

### Rationale

- **The ordering constraint is a data-integrity constraint, not a style preference.** The
  015 test's reasoning generalises directly: a unique index created before its backfill
  admits exactly the NULL/partial rows it exists to constrain. For 016 the exposure is
  `uq_evidence_context_fingerprint` and `uq_relation_claim_content` — both of which feed
  idempotency, so a NULL slipping through would break I-11 structurally.
- **Forward-only is enforced by an existing test, so the cost is zero.** The linear,
  single-head, immutable-revision machinery already exists
  (`test_migration_forward_only.py:66-108`) and 016 merely extends it. Editing 015 to
  absorb these tables would fail `test_released_revisions_are_not_edited` for 014 and break
  the 015 pinning test — the guard rails are already in place.
- **`String(64)` for the id columns is deliberate headroom.** `context_id` is
  `"CX-" + 32 hex = 35` characters and `relation_id` is `"RC-" + 32 hex = 35`
  (`data-model.md:556`, `:592`); 64 leaves room for a future width increase without a
  migration.
- **The unique index on `(tenant_id, content_hash)` is what makes FR-005 structural.**
  Idempotency on identical content is a database constraint here, not application logic, so
  a buggy caller cannot produce a duplicate.
- **Tenant-scoped uniqueness is the constitution's requirement made structural.**
  `constitution.md:24` demands "tenant isolation at every level"; every unique index and
  every lookup index in these five tables is tenant-prefixed, so a cross-tenant read or
  write is not expressible as a single query.
- **A separate revision ledger table, not just a status column, is required by FR-006.**
  `SUPERSEDED`, `RETRACTED` and `CONTRADICTED` claims stay queryable and are never deleted
  (constitution I-3). The ledger makes the revision chain indexable without scanning
  `relation_claim`.
- **The lineage table is a projection, not a source of truth.** It is rebuildable from
  `relation_claim` + the hop tables, consistent with constitution III
  (`constitution.md:12`); storing it makes the UI's evidence panel a single query.

### Consequences

**Positive**
- Both install paths are provably equivalent (SC-010), so a fresh deployment and an
  upgraded one cannot diverge.
- Idempotency and tenant isolation are database constraints, not caller discipline.
- Revision history is queryable by `(tenant_id, logical_relation_id, revision_number)`
  without touching the claims table.
- Nothing in the migration touches an existing table, so rollback of 015 is unaffected and
  the previous feature's materialization tables are untouched.

**Negative / trade-offs**
- Five tables is a lot of new surface for one feature, and `relation_claim` has 30 columns
  (`data-model.md:592-623`). Most are nullable timestamps and JSONB columns.
- JSONB for `role_bindings`, `assertion_refs`, `observation_refs`,
  `source_independence_groups` and `contradicts` trades queryability for schema stability.
  The alternative — child tables per list — multiplies the table count well past five.
- `lineage_id` is content-addressed but its column width is `String(128)`
  (`data-model.md:671`), larger than needed; noted for consistency, not blocking.
- Proving both install paths requires a live PostgreSQL, which
  `test_migration_forward_only.py:12-13` explicitly notes a content digest cannot replace.
  That makes the test an integration test, not a unit test.

**Follow-up**
- Any backfill added by a *future* revision must be inserted between the column addition and
  the index creation, and must extend the `add_column < backfill < index` assertion rather
  than relying on a no-op placeholder.
- `test_migration_env_resolves_a_database_url` (`test_migration_forward_only.py:131-140`)
  must keep passing: the `env.py` DSN resolution added by the previous feature is the only
  way the migration path is exercisable at all.

## Defects found in the existing implementation

All locations verified by reading the referenced files. Numbering is stable and each entry
gives file:line, symptom, root cause and fix.

1. **`apps/projection/graph/abstraction.py:145` — the N-ary idempotency guard is dead
   code.** `write_hyperedge` tests `if edge in self._hyperedges:` where
   `self._hyperedges` is `dict[str, HyperEdge]` (`:110`). `in` on a dict tests *keys*, and
   `HyperEdge.__eq__` (`:87-92`) returns `False` for any non-`HyperEdge` operand, so the
   test is unconditionally `False`. The guard never fires, ever. *Root cause:* an object
   was tested against a mapping that was always keyed by that object's derived id, so the
   correct check was `edge.edge_id in self._hyperedges` all along. The same defect class is
   duplicated in `GraphEdge.__eq__`/`__hash__` (`:36-37`, `:87-92`), where `properties` is
   excluded from the hash but included in equality. *Fix:* `if edge.edge_id in
   self._hyperedges: return edge.edge_id` (`data-model.md:520`), and key
   `__hash__`/`__eq__` on `(edge_id,)`. Note the dead guard is not the only problem in this
   function: the statement beneath it, `self._hyperedges[edge.edge_id] = edge` (`:147`),
   keys the store by the *logical* id, so a corrected hyperedge silently replaces the
   previous one instead of coexisting with it. That second defect is item 4 below.

2. **`apps/projection/graph/abstraction.py:179-184` — `neighbors()` loses direction.**
   `write_edge` adds each edge to *both* endpoints' adjacency (`:131-132`:
   `self._adj.setdefault(edge.source, set()).add(edge)` and the same for `edge.target`).
   `neighbors` then reads `out.add(e.target if e.source == node_id else e.source)`
   (`:183`) — the union, undifferentiated. A `reports_to` edge is returned to a manager as
   a report and to a report as a manager, indistinguishably. There is no `direction`
   parameter. *Root cause:* the adjacency index was built undirected, so direction was
   destroyed on write even though it was present in the data, and the read could not
   recover it. The Neo4j adapter does not share the bug — `neo4j.py:76` uses
   `-[r]->`, i.e. outgoing only — so the two stores already disagree about what
   `neighbors` means. *Fix:* `neighbors(node_id, edge_type=None, direction="out")` with
   `direction in {"in","out","both"}` and a mode-derived default (`data-model.md:512-518`).

3. **`apps/projection/graph/abstraction.py:29-37` — `GraphEdge` has no `edge_id`, and its
   `__hash__`/`__eq__` disagree.** The dataclass is `(edge_type, source, target,
   properties)` with no identifier, so no other object can reference an edge. `__hash__`
   is `hash((self.edge_type, self.source, self.target))` (`:36-37`) — properties
   excluded — while the dataclass-generated `__eq__` compares all four fields, properties
   included. Two edges with the same triple and different properties are therefore
   **unequal but hash-equal**, i.e. *distinct members of the same set*
   (`self._edges: set[GraphEdge]`, `:108`). Writing the same relation twice with a changed
   property bag creates two adjacency entries and two set members, so I-11 idempotency
   fails exactly when the relation gains information. The same field/equality asymmetry
   applies to the `write_edge` guard at `:128`. *Root cause:* identity was inferred from
   the triple instead of being carried explicitly, and `properties` — an unbounded,
   un-ordered dict — was given a role in identity by default. *Fix:*
   add a required `edge_id` and key both `__hash__` and `__eq__` on `(edge_id,)`
   (`data-model.md:498-510`); `edge_id` is supplied by the relation layer, not invented by
   the store.

4. **`apps/projection/graph/abstraction.py:46` — the projection `HyperEdge` docstring
   misdescribes its own identity material.** The docstring says "Identity is deterministic
   on (edge_type, members, valid_from)". The code at `:71-82` returns
   `hyperedge_id(self.edge_type, self.source, tenant_id=self.properties.get("tenant_id",
   "default-tenant"))`, and `hypergraph.py:41-49` shows the material is
   `(edge_type, sorted(members), tenant_id)`. So the docstring names `valid_from`, which
   is not in the material, and omits `tenant_id`, which is. *Root cause:* the docstring
   predates the delegation to `hyperedge_id` and was never updated when the projection was
   bound to the domain helper at block G. The consequence is not cosmetic: because the
   returned id is the *logical* id, `write_hyperedge` at `:147` does
   `self._hyperedges[edge.edge_id] = edge`, so **two temporal versions of the same N-ary
   relation overwrite each other in the projection store**, while the domain `HyperGraph`
   stores both side by side (`hypergraph.py:247`). The projection is not versioned, and a
   reader of the docstring would believe it is. *Fix:* correct the docstring to
   `(edge_type, members, tenant_id)` and key the store by the *version* id
   (`hyperedge_version_id`, `hypergraph.py:53-86`), matching
   `HyperGraph._versions` (`hypergraph.py:215`).

5. **`apps/projection/graph/snapshot.py` — five distinct defects in a 99-line
   rebuildability module.**
   (a) **`:44-99`** — `RebuildableGraphStore` implements `write_node` (`:56`) and
   `write_edge` (`:62`) but **no `write_hyperedge`**, although `GraphStore` declares it
   (`abstraction.py:98`). N-ary structure written to the wrapped store is neither logged
   nor snapshotted, `_asset_edges` (`:91-94`) only reads `edges()`, and `rebuild` can never
   reproduce it. The N-ary form is silently dropped by the one component whose entire job
   is faithful reproduction.
   (b) **`:69` and `:37`** — `snapshot()` constructs `GraphSnapshot()` and
   `projection_id` has `field(default_factory=lambda: "PROJ-" + uuid.uuid4().hex[:12])`,
   so **every snapshot gets a fresh random projection id**. Two snapshots of an unchanged
   store have different projection ids, which is why FR-041 / SC-011 ("a stable projection
   id") cannot hold. The existing test passes `snap.projection_id` into `rebuild` at
   `apps/projection/tests/test_projection.py:80` and passes only because `rebuild` ignores
   it.
   (c) **`:77-86`** — `rebuild(projection_id)` **ignores its `projection_id` argument**
   entirely and always replays `sorted(self._log, key=...)` from offset 0 (`:80`). There is
   no `from_offset` parameter, so `last_offset` (`:73`) is recorded for no purpose and an
   incremental rebuild is impossible. `:79` also hardcodes `InMemoryGraphStore()`,
   ignoring the wrapped backend, so a "rebuild" of a Neo4j-backed projection silently
   produces a different store type.
   (d) **`:22-24`** — `_checksum` builds its joined material as
   `f"{e.edge_type}:{e.source}->{e.target}"`, which **excludes `properties` entirely**, so
   two edge sets that differ only in properties produce an **identical checksum**. FR-040
   and SC-011 ("a rebuild reproduces an identical checksum") therefore cannot detect
   property divergence. The sort key `sorted(edges, key=str)` sorts on the full dataclass
   `repr`, which *includes* the properties dict and, for arbitrary values, memory
   addresses — so the ordering is not stable across processes even though the joined
   material is. Fix: sort on `(edge_id,)` and include the content hash in the material
   (`data-model.md:543`, `:491-492`).
   (e) **`:91`** — the method is named `_asset_edges`, called at `:70`. The intended name is
   `_all_edges` (or `_assert_edges`); "asset" has no meaning in this module. A typo that
   survived because the method has no test asserting its name.

6. **`apps/projection/graph/neo4j.py` — the adapter cannot round-trip a `GraphEdge`, and
   subclasses a Protocol the other implementation does not.**
   (a) **`:63-72`** — `write_edge` emits
   `MERGE (a)-[r:REL]->(b)` with only `source` and `target` as parameters. `edge.properties`
   is **discarded entirely** and **no edge id is created**, so the projection cannot store
   a `relation_id`, a context ref, a confidence or any other property; a `GraphEdge` read
   back from Neo4j is not the edge that was written. Because the `MERGE` pattern is the
   full `(a)-[r:TYPE]->(b)` shape, Neo4j will also match *any* existing relationship of
   that type between the pair, so the projection can hold **at most one relation of a type
   between two nodes** — two employment intervals, or two different contexts, are
   structurally unrepresentable. Compare `write_hyperedge` (`:35-61`), which does
   `MERGE (h:HyperEdge {edge_id: $edge_id})` and sets properties correctly: the N-ary path
   was fixed and the pairwise path was not.
   (b) **`:18`** — `class Neo4jGraphStore(GraphStore)` explicitly subclasses the `GraphStore`
   `Protocol` (`abstraction.py:95-100`), while `class InMemoryGraphStore:`
   (`abstraction.py:103`) does not. Explicit Protocol subclassing is the documented
   anti-pattern: it inherits the `...`-bodied stub methods (which silently return `None`)
   and it defeats the structural check that is the only reason to use a `Protocol` at all.
   The two "implementations" of one contract are therefore not held to the same contract,
   and the adapter's conformance is asserted by inheritance rather than by inspection.
   *Fix:* drop the explicit base, emit `MERGE (a)-[r:TYPE {rel_id: $rel_id}]->(b) SET r +=
   $props` (`data-model.md:526-533`), and reject non-ASCII alphanumerics in `_sanitize`
   (`:94-107` uses `str.isalnum()`, which is `True` for Cyrillic, producing an invalid
   label).

7. **`apps/projection/graph/adjacency.py:104-130` — `adjacency_from_store` returns an empty
   view against a real store.** `store.nodes()` returns `list[GraphNode]`
   (`abstraction.py:189-190`), but line `:118` computes `sorted(str(n) for n in all_nodes)`
   — `str()` on the **object**, producing
   `"GraphNode(node_id='n1', node_type='Entity', properties={})"`. That string is then
   passed as a node id to `store.neighbors(str(node), edge_type)` at `:122`, which looks it
   up in `self._adj` and finds nothing. The function therefore returns an `AdjacencyView`
   with **zero nodes and zero edges** for any real store. It should be `str(n.node_id)`
   (or better, `n.node_id` with no `str()` at all). Secondary defects in the same function:
   the nested loop at `:121-129` is `O(N * deg log deg)` and re-derives adjacency from
   neighbour queries when `store.edges()` is available; and because direction is lost
   upstream (defect 2) *both* `(a, b)` and `(b, a)` are appended, and `build_adjacency`
   dedups on `(source, target, edge_type)` (`:89`) which treats them as distinct — so every
   edge is duplicated, silently doubling the edge count fed to
   `to_tda_input` (`:42-57`) and to `to_distance_matrix` (`:133-154`). Like
   `adjacency_from_store` itself, this function has **zero call sites and zero tests**
   (verified: the only importers of the module use `build_adjacency` directly, from
   `apps/control-plane/api/routes/network.py:93-96` and
   `apps/projection/tests/test_metrics.py:8`).

8. **`apps/webapp/src/lib/edgeFormation.ts` — five defects in the frontend identity path.**
   (a) **`:72-73`** — `min`/`max` normalisation collapses direction for **every** `EdgeKind`
   (`:12-18`), including `relationship`, `assertion`, `evidence`, `source_host` and
   `possible_match`. `A --works_for--> B` and `B --works_for--> A` receive one id. The
   docstring at `:66-70` asserts this is intentional; it is only correct for
   `co_occurrence`.
   (b) **`:56-64`, `:75`** — FNV-1a is 32-bit, so 2^32 ids with a 50% birthday point at
   77163 relations (Decision 1). The id is rendered as 8 hex characters
   (`digest.toString(16).padStart(8, "0")`, `:75`).
   (c) **`:59`** — `input.charCodeAt(i)` walks **UTF-16 code units**, not UTF-8 bytes, so
   the material hashed in TypeScript is not the material `m.encode("utf-8")` would hash in
   Python. A Cyrillic node id hashes differently in the two languages, and astral-plane
   characters (emoji, some CJK extensions) are consumed as surrogate pairs. Frontend and
   backend ids cannot agree for any non-ASCII identifier, which is the normal case for
   this data (Cyrillic names throughout `apps/interpretation/extractors/persons.py:21-22`).
   (d) **`:127-131`** — `formEdges` expands each N-ary observation into a full clique:
   `for i ... for j = i+1 ...` emits `n(n-1)/2` pairwise edges. The Python side calls the
   same construction "derived and lossy" and insists the native form stays primary
   (`hypergraph.py:3-8`, `:292-297`; `abstraction.py:44-45`), so the frontend is the *only*
   place where the lossy view is the sole representation.
   (e) **`:140`** — `formed.set(id, {...})` is last-writer-wins on the whole record,
   including `reason`. The **id** is order-invariant (`:22-27` in the test), but the
   **payload** is not: two seeds that hash to the same id but carry different `reason`
   values produce different `FormedEdge` arrays depending on input order. The docstring at
   `:1-10` claims "edge emission is order-invariant". The test at
   `edgeFormation.test.ts:92-103` asserts only `toHaveLength(1)`, so it cannot catch this.

9. **`write_edge` and `write_node` have zero production call sites.** A repository-wide
   search for `.write_edge(`, `.write_node(` and `.write_hyperedge(` across `apps/`
   returns matches in exactly two files: `apps/projection/tests/test_projection.py`
   (lines `:38`, `:39`, `:47`, `:54`, `:56`, `:64-66`, `:75-77`) and
   `apps/projection/graph/snapshot.py` itself (`:58`, `:64`, `:83`, `:85`). The entire
   pairwise edge layer is exercised only by its own wrapper and by one test. *Root
   cause:* the pipeline writes entities, candidates and assertions through the domain and
   control-plane paths; the `GraphStore` edge API was built to the protocol and never
   wired to a producer. *Consequence:* defects 1, 2, 3, 6, 7 and 8(a) have survived because
   nothing in the running system can observe them. A test that constructs two objects and
   asserts a count is not an integration test. This is the single most important finding in
   this section: **the edge layer is currently unexercised by the pipeline, and every
   other defect on this list is a consequence of that fact.** It also means the fixes
   cannot be validated by production behaviour, so each must carry an explicit regression
   test that fails against today's code.

10. **`apps/interpretation/extractors/persons.py:336-344` — `_dedup` keys on less than its
    docstring claims.** The docstring says "Deterministic dedup: keep first mention per
    `(offset, kind, value)`". The code sorts by `(x.offset, x.value, x.kind)` (`:339`) but
    keys on `key = (m.offset, m.kind)` (`:340`) — **`value` is absent from the key**. The
    sort by `value` therefore decides *which* mention wins, not whether both are kept: at a
    shared start offset, the mention with the lexicographically smaller `value` is retained
    and the other is dropped at `:341-342`, regardless of evidence tier. Since
    `_ru_validation` (`persons.py:134-154`) assigns `source="dictionary"` with confidence
    0.9, `"morph"` with 0.7 and `"pattern"` with 0.5-0.6, a lower-tier `pattern` mention
    can silently displace a `dictionary` mention that started at the same byte offset.
    *Root cause:* the key was narrowed (probably to reduce collisions between overlapping
    pattern passes) without updating the contract, and the retained item's `source` and
    `confidence` are taken from whichever mention sorted first rather than from the
    highest-evidence one. *Fix:* key on `(offset, kind, value)` as documented, and when two
    mentions share `(offset, kind)`, retain the highest evidence tier, breaking ties on
    `(confidence desc, value asc)` so the outcome is independent of input order.

11. **`apps/interpretation/extractors/normalize.py:129` — a dead guard makes the
    patronymic expansion order-biased.** The loop header is
    `for root in sorted(_names.RU_FIRST_NAMES if not patronymic_hits else []):`. A `for`
    statement evaluates its iterable expression **exactly once**, before the first
    iteration, so this conditional is not re-evaluated per iteration. At that moment
    `patronymic_hits` is `[]` (`:128`), so `not patronymic_hits` is `True` and the
    iterable is the full sorted first-name list — the `else []` branch is **unreachable
    dead code**. The loop's real termination is therefore solely
    `if len(patronymic_hits) >= 6: break` (`:139-140`), which fires after the **third**
    matching root (each match appends up to two forms at `:135-138`). The result: the
    patronymic hypotheses for an initials-only mention are the first three stems in
    *lexicographic order of the given-names dictionary*, not the six most plausible or most
    frequent ones. Two initial pairs sharing a prefix but differing in later letters can
    yield disjoint, arbitrarily truncated patronymic sets, and the truncation point moves
    whenever the dictionary is re-sorted. *Root cause:* the guard was written as though it
    were an in-loop condition, which suggests the intent was "stop as soon as any patronymic
    has been found" — but Python's `for` semantics make the guard inert, and the
    comprehension-like `else []` hides the mistake from the reader. *Fix:* hoist the
    candidate list out of the header, make the intent explicit, and bound the scan by
    coverage rather than by count — e.g. iterate `sorted(_names.RU_FIRST_NAMES)` and break
    on `len(patronymic_hits) >= 6` with the limit as a named module constant, or iterate a
    precomputed stem index so the truncation is dictionary-order-independent and testable.
    Add a test asserting the expansion is stable under dictionary re-sorting.

12. **Invariant numbering in `spec.md` and `plan.md` does not match the constitution.**
    `plan.md:54-55` cites "constitution invariants I-1 (observation immutable), I-3
    (assertion ≠ truth), I-4 (monotonic versions), I-11 (idempotent), I-12 (provenance
    enforced)", and `spec.md` cites "I-11 idempotency" (FR-005, FR-036) and "I-12
    provenance" (FR-007, FR-036). But the constitution's numbered Domain Invariants
    (`constitution.md:28-39`) are a different list: 3 is "Assertion != truth" (correctly
    cited), **4 is "Graph != source of truth"** (not "monotonic versions"), **11 is "The
    fastest request is the request correctly avoided"** (a performance invariant, not
    idempotency), and **12 is "All downstream projections must be rebuildable from durable
    evidence/events"** (rebuildability, not provenance). Idempotency and provenance
    enforcement are real requirements but they live *unnumbered* under Additional
    Constraints (`constitution.md:66`) and Governance (`constitution.md:73`). The code
    side is inconsistent too: `apps/shared/domain/__init__.py:48-54` uses `I-12` for
    rebuildability (matching the constitution) while `plan.md` uses `I-12` for provenance
    (matching neither). *Consequence:* two numbering schemes are in circulation for the
    same labels, so every FR citing "I-11" or "I-12" is untraceable, and a reviewer
    checking `spec.md:199` ("FR-007 ... rejected by the provenance guard (I-12)") against
    `constitution.md:39` finds a different invariant. *Fix:* pick one scheme. The
    constitution's numbered list is authoritative; cite idempotency as
    `constitution.md:66` and provenance enforcement as `constitution.md:73` (plus
    `I-12` where rebuildability is actually meant), and correct `plan.md:54-55` and the
    `spec.md` FR references accordingly.

13. **`apps/shared/domain/__init__.py:64-68` — the I-1 immutability guard is
    bypassable on the empty-store path.** `enforce_observation_immutable(existing, update)`
    raises only `if existing and mutable_keys`. When `existing` is falsy — a store that
    returns `{}` for an unknown observation id, or a caller that passes `{}` — the guard is
    a no-op and any `update` is accepted. The function is also incomplete: it permits
    updates to `status`, `duplicate` and `provenance` unconditionally, with no transition
    validation, so an observation can be marked `duplicate` and thereby disappear from
    downstream counts without any record of who did it. *Root cause:* the guard is
    expressed as "reject if we happen to have the old value" rather than "reject unless
    this is a registered observation", which inverts the direction of the check.
    *Consequence for this feature:* Decision 4 relies on immutability-plus-content-address
    as the model for `EvidenceContext`, so this is the precedent being copied and it needs
    to be correct. *Fix:* require a resolvable existing observation and raise when it is
    absent, and validate the allowed `status` transitions explicitly.

14. **The frontend has two divergent FNV-1a implementations.**
    `apps/webapp/src/lib/edgeFormation.ts:56-64` returns a `number` and prefixes ids as
    `e:${...}`; `apps/webapp/src/lib/graphState.ts:64-71` returns a zero-padded 8-hex
    `string` with the same offset (`0x811c9dc5`, `graphState.ts:22`) and the same prime
    (`0x01000193`, `graphState.ts:23`) but no `>>> 0` normalisation in the loop body
    (relied on implicitly by `hash >>> 0` at `:70`). They agree numerically today and will
    continue to, but they are separate implementations of the same primitive with different
    signatures and different callers, and the golden vector
    `expect(fnv1a("")).toBe("811c9dc5")` at `graphState.test.ts:132` only pins one of
    them. *Root cause:* the hash was re-implemented per module rather than shared.
    *Consequence:* Decision 1 keeps both alive for non-identity purposes, so the duplication
    becomes permanent unless addressed. *Fix (deferred):* extract one `fnv1aHex` helper
    into a shared module, keep the existing vectors passing, and mark the edge-identity
    call sites as the ones being removed.

## Rejected alternatives

### Keep 32-bit FNV-1a and widen the namespace with a prefix

**Rejected because**: FNV-1a over a prefixed string is still FNV-1a over a 32-bit state
(`edgeFormation.ts:56-64`: the accumulator is a JavaScript `Number` forced back into
unsigned 32 bits by `h >>> 0` at `:62`). A prefix raises the number of *distinct input
strings*, not the number of distinct *output values*, so the birthday bound is unchanged
at 77163 relations. Widening the digest also does not help: the state is 32 bits, so the
output is 32 bits, so there is nothing wider to truncate. The only variables that change
the bound are the *width of the output* and the *quality of the mixing function*; Decision
1 changes the first (32 → 128 bits) and the second (FNV-1a → SHA-256) simultaneously,
which is why the bound moves by twelve orders of magnitude rather than by a constant.

### UUIDv5 over a fixed namespace

**Rejected because**: UUIDv5 is SHA-1 truncated to 128 bits, so the width is right but the
hash is not — and SHA-1 collision resistance is broken (SHAttered, 2017). More
importantly, UUIDv5 requires a *namespace UUID* and a name, and the natural namespace for
this system is the relation type, which means a relation's identity would depend on a
UUID that is itself registered somewhere. That reintroduces the exact problem Decision 6
solves: identity would be resolvable only through a registry lookup, so a claim's id could
not be recomputed from the claim alone. The existing house style already computes the
digest inline over documented material — `hypergraph.py:41-50`,
`temporal_worldline.py:131-134` and `:614-616` — and `digest128` over a
`sort_keys=True` JSON material keeps that property: the material *is* the audit trail
(`temporal_worldline.py:600`, "The exact material an `event_id` is derived from
(auditable, I-11)"). UUIDv5 also obscures the mode prefix that the `RL-`/`RC-`/`CX-`
conventions give for free when reading an id in a log line.

### Mutate `GraphEdge` in place instead of adding `RelationClaim`

**Rejected because**: `GraphEdge` has no `edge_id` (`abstraction.py:29-37`), no arity mode,
no temporal interpretation, no context ref, no revision lineage and no source-independence
information. Adding those fields to the existing four-field dataclass would make it a
`RelationClaim` with a different name, but it would also break every construction site,
every store, the Neo4j adapter and the existing tests mid-feature — and the two objects
have genuinely different lifetimes. A `GraphEdge` is a *projection artefact*: it is
rebuildable, disposable, and its identity is a convenience. A `RelationClaim` is an
*admitted assertion*: it is durable, status-bearing, never deleted (FR-006), and its
identity is load-bearing for lineage. Conflating them would mean constitution III
(rebuildable projection) and invariant I-3 (assertion ≠ truth) pull in opposite directions
on a single class. `plan.md:85` records the same conclusion: "Mutating `GraphEdge` in
place would break every store, adapter and test that depends on its 4-field shape". The
only in-place change this feature makes to `GraphEdge` is *adding* `edge_id` and keying
equality on it (`data-model.md:498-510`) — additive, not a rewrite.

### Single-level edge id, with no logical/revision split

**Rejected because**: it makes correction unrepresentable. Correcting an employment
interval from `2017-2020` to `2017-2022` under a single id either overwrites the prior
assertion — destroying the record that the system once believed the narrower window, a
direct I-3 and `constitution.md:73` violation ("rejected analysis outputs ... are
preserved") — or produces a second, unrelated edge, in which case "all versions of this
relation" is unanswerable and supersession is a convention rather than a link. The
precedent already exists and works: `hyperedge_id` vs `hyperedge_version_id`
(`hypergraph.py:29-86`), with `HyperGraph._versions` keyed by logical id
(`hypergraph.py:215`) and `versions(logical_id)` at `:254-257`. The projection cannot
follow it *today* only because `abstraction.py:71-82` returns the logical id (defect 4);
that is a bug to fix, not a reason to abandon the split.

### Clique projection as the primary N-ary representation

**Rejected because**: the codebase has already ruled this out in its own words.
`hypergraph.py:3-8` states that pairwise projection is "*derived and lossy* (it forgets
co-participation) — so the native form stays primary; clique projections are explicit,
deterministic, and derived-only artifacts for consumers that cannot read the native form."
`clique_projection`'s own docstring (`hypergraph.py:292-297`) repeats it: "N-ary structure
is forgotten by design, so native hyperedges remain the authoritative form." The Neo4j
reification agrees (`neo4j.py:36-43`): participation edges are `PART_OF_<TYPE>` from
member to hyperedge node, and pairwise projections "remain derived, never authoritative."
Making the clique primary would be a regression against an explicit, three-times-repeated
architectural commitment — and the frontend already violates it
(`edgeFormation.ts:127-131`, defect 8d), which is precisely the inconsistency this feature
removes. The clique remains available as `clique_projection` for TDA and network
consumers that genuinely cannot read the N-ary form, and the frontend's pairwise view
becomes an explicitly derived projection (FR-045), not the record.

### A boolean validator

**Rejected because**: it violates invariant I-3 (`constitution.md:31`) in the specific
sense that it makes "we cannot interpret this" indistinguishable from "this is false", and
it forces every caller to re-derive the reason, which is the exact duplication of
derivation logic the feature exists to remove (`plan.md:84`). Concretely, `spec.md:87`
requires four outcomes to be distinguishable: structurally valid but temporally invalid;
ontology-invalid participant classes; provenance-invalid cross-tenant evidence; and
uninterpretable-because-undeclared-version. A boolean returns `False` for all four. Worse,
the fourth is not a rejection at all — the claim is preserved and its `extraction_version`
is simply missing — so a boolean would force the caller to decide, without information,
whether to delete, quarantine or re-interpret it. The graded verdict with per-layer
outcomes also makes the validator *diagnosable*: SC-005 requires reporting
`temporal_interval_inverted` while simultaneously reporting `structural: PASSED`, which is
impossible if the function returns `True`/`False`.

### Store an embedded mutable context copy on the claim

**Rejected because**: it makes the claim's context unfalsifiable. An embedded copy can
diverge from the registered frame, and nothing in the system can detect the divergence
because the id and the content are both on the claim and both move together. FR-018
forbids it explicitly, and the blob discipline behind it is enforced in code:
`ontology_pack.py:74-79` rejects any inline descriptor over 4096 bytes as "carry refs, not
blobs (I-5)". It also defeats content addressing: the whole point of `context_id` is that
resolving it is a *check* — a stored frame whose recomputed digest does not match its id is
a detectable corruption. With an embedded copy there is nothing to recompute against. And
it multiplies storage: a frame shared by 10,000 claims would be stored 10,000 times, each
copy free to drift.

### Derive ontology semantics directly from extractors

**Rejected because**: relation semantics would live in code spread across
`apps/interpretation/extractors/`, with no single place to review them, no version to pin
a claim against, and no way to enumerate the vocabulary. `spec.md:109` states the problem
exactly: "Today relation semantics live in extractor code, so a new relation type is a
code change in several places with no single place to review." Extractor code also cannot
be the *authority* for admissibility, because extraction is downstream of admission — an
extractor proposes, a validator adjudicates, and a proposer that also adjudicates its own
proposals has no independent check. Finally, extractors are the layer most likely to be
rewritten: every known extractor defect (defects 10, 11) is a semantics bug of exactly the
kind a registry would have made visible. `spec.md:319` confirms relation *candidate
extraction* is a separate feature; this feature defines the `RelationSchema` contract that
extraction will consume, and does not rewire it (`spec.md:343`).

### A single global "truth score" per relation

**Rejected because**: forbidden by constitution IV in as many words — "no single score
equates to truth: validity, relevance, novelty, resolution confidence, source quality,
evidence support, and structural significance are stored separately"
(`constitution.md:15`), reinforced in Governance at `constitution.md:73` and in the
Additional Constraints. It is also substantively wrong, not merely disfavoured. The
quantities have different units and different failure modes: `independent_source_count`
is an integer that collapses copied sources; `completeness` is an ordinal the producer
declares about itself; `trust_state` can be `DISPUTED` after the fact; `confidence` is a
producer's self-report. A weighted blend of these is dominated by whichever term has the
widest range, is not monotone under any of them, and cannot be inverted — "why is this 0.6?"
is unanswerable, which is the question the whole feature exists to answer. `ValidationResult`
therefore stores the five components separately (`data-model.md:394-400`) and derives
`evidence_grade` by *lookup* over a small table (`data-model.md:403-409`), never by
summation, and a `DISPUTED` trust state caps the grade at `weak` rather than being averaged
away. The same reasoning is why `publication_count` and `independent_source_count` are two
fields and not one (`data-model.md:177-179`).

## Open questions deferred to later features

- **Relation candidate extraction** — how free text becomes a `RelationClaim` proposal
  from a `RelationSchema`. This feature ships the `RelationSchema` contract
  (`data-model.md:277-306`) and the `admissible_evidence_patterns` field that extraction
  will read, but no extraction is rewired (`spec.md:319`, `plan.md:158`). Open: which
  spans are proposable for `REQUIRED_INTERVAL` types; whether the proposer emits
  `RelationClaim` directly or a lower-confidence candidate that admission promotes.
- **Normalization algebra and mention arbitration** — the `normalization_version` field is
  reserved on both `RelationClaim` (`data-model.md:146`) and `EvidenceContext`
  (`data-model.md:237`) but no algebra is defined. Open: what constitutes a normalisation
  version boundary; how a name hypothesis (`normalize.py:120-145`, `hypothesis=True`,
  `credence=None`) becomes admissible evidence; whether `_dedup`'s tier-selection rule
  (defect 10) belongs to the normaliser or the extractor.
- **Mention arbitration** — `Mention != Candidate != Entity` (constitution invariant 2,
  `constitution.md:29`) is currently enforced only by naming. Open: the promotion
  threshold, and whether arbitration failure is a validator verdict or a separate
  quarantined record.
- **Multi-pass entity resolution** — a relation's participants are `subject_ref` /
  `object_ref` strings today, with no cluster identity. Open: whether a relation belongs
  to an entity or to a mention-of-an-entity; how re-resolution invalidates or supersedes
  claims. Note the forward lineage includes `ENTITY` but the backward chain does not
  (`Decision 7`), because the reverse edge is a resolution claim, not a lineage hop.
- **Contradiction reasoning** — this feature persists `contradicts` and `supersedes`
  (`data-model.md:157-158`) and reports conflicting intervals as `CONFLICTING`, but does not
  rank which claim wins (`spec.md:322`). `ValidationWorld.sibling_claims`
  (`data-model.md:385`) is the injection seam. Open: the ranking function; whether a
  contradiction is a property of two claims or of a relation family.
- **Temporal consistency** — this feature validates one claim's own interval. Cross-entity
  worldline consistency (`constitution.md:9`) is separate (`spec.md:323`). The machinery
  exists: `EventInterval` (`temporal_worldline.py:205-246`), `overlaps_window`
  (`:249-257`), `PRECEDENCE_RANK` (`:70-79`) and `WorldlineEvent`
  (`:491-553`). Open: whether `RelationClaim` should carry an `EventInterval` directly or
  a ref into a worldline event; how `TimePrecision.UNKNOWN` interacts with interval
  overlap decisions.
- **UI workspaces (Entity Workspace / Evidence Inspector)** — out of scope
  (`spec.md:318`). This feature supplies the read API (FR-047), the lineage traversal
  (FR-030 to FR-033) and the corrected frontend edge semantics it will render. Open:
  which `LayerOutcome`/`ValidationReason` pairs are surfaced, and whether the UI shows
  `complete=False` traces inline or only on demand.
- **Pivot / discovery fabric** — the lineage chain deliberately stops at `ENTITY` in the
  forward direction; pivoting is the next traversal layer and depends on the relation
  vocabulary being queryable by arity and schema. Open: whether a pivot is a traversal,
  a stored edge, or a materialised finding.
- **Stream-first transport** — the durable event vocabulary for this feature is defined
  (`data-model.md:697-710`: `relation.claim.created`, `.revised`, `.superseded`,
  `.contradicted`, `context.registered`, `context.validation.recorded`), all carrying refs
  and versions, never blobs. Transport is unchanged (`plan.md:53`, `spec.md:325`). Open:
  partition and key strategy for `relation.claim.revised`, which is keyed by
  `logical_relation_id` while the other four are keyed by `relation_id` — two different
  keying strategies on one topic, and a rebalance or a split topic is a live question.
