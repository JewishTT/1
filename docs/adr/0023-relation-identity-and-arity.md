# ADR-0023: Relation identity scheme and arity model

## Status

Accepted — 2026-09-26 — feature `016-relation-evidence-graph-fabric` (task T001).

## Context

Relation identity has three requirements that the current code does not meet. It must be a
deterministic function of the relation's *content*; it must be computed identically by the
backend, by the frontend, and on replay from the durable log; and it must not be able to
alias two different relations.

The only live edge-identity path is a 32-bit FNV-1a digest in
`apps/webapp/src/lib/edgeFormation.ts:56-64`, consumed by `makeEdgeId` at
`apps/webapp/src/lib/edgeFormation.ts:71-76`. A second, unrelated FNV-1a implementation
lives at `apps/webapp/src/lib/graphState.ts:22-23` and
`apps/webapp/src/lib/graphState.ts:64-71`, feeding the view-state fingerprint
(`entitiesKeyFor`, `graphState.ts:85-95`) and the export checksum (`checksumOf`,
`graphState.ts:184-186`). FNV-1a is a non-cryptographic hash with trivially constructible
collisions, over a 32-bit state.

Direction is not modelled and is actively destroyed. `makeEdgeId` normalises every pair
through `min`/`max` (`edgeFormation.ts:72-74`) for **all six** declared `EdgeKind` values
(`edgeFormation.ts:12-18`). On the Python side, `InMemoryGraphStore.neighbors()` adds each
directed edge to both endpoints' adjacency (`abstraction.py:131-132`) and then returns the
undifferentiated union (`abstraction.py:179-184`), so direction is stored on write and lost
on read. There is no vocabulary distinguishing undirected, directed, N-ary and temporal
relations at all; the only distinction between a pairwise edge and an N-ary structure is
which method you call (`abstraction.py:97-98`).

Identity also conflates content with version. The plain-edge path has no logical/revision
split, and it cannot have one, because `GraphEdge` (`abstraction.py:29-37`) has four fields
— `edge_type`, `source`, `target`, `properties` — and no identifier at all. The HyperEdge
split that does exist (`apps/shared/domain/hypergraph.py`) is not available to the plain-edge
path. The repository already carries three identity widths across four call sites: 8 hex
characters in `edgeFormation.ts`, 16 in `hyperedge_id` (`hypergraph.py:50`) and 32 in
`hyperedge_version_id` (`hypergraph.py:86`).

Two golden vectors pin the current hash and they are not the same kind of pin:

- `apps/webapp/src/lib/edgeFormation.test.ts:18` and `:138` —
  `expect(makeEdgeId("ENT-1", "ENT-2", "possible_match", "CE-1")).toBe("e:1d374e53")`.
  This is an **identity** vector and it is the one that must move.
- `apps/webapp/src/lib/graphState.test.ts:132` — `expect(fnv1a("")).toBe("811c9dc5")`.
  This is the FNV-1a offset-basis vector for a **non-identity** use and it must not.

## Decision

**All relation identity is a 128-bit truncated SHA-256 over documented canonical material.**
The single id-producing primitive is:

```python
def digest128(material: str) -> str:
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]
```

The material is serialised by the house canonical form:

```python
json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
```

Ids carry a mode prefix: `RL-` + 32 hex characters for `logical_relation_id`, `RC-` + 32
hex for `relation_id`. The output is 32 lowercase hex characters — the same width
`hyperedge_version_id` already writes, so the two-level scheme introduces no new key width
into the persisted surface. Only `hashlib` and `json` are used; no new runtime dependency.

**The 32-bit space is disqualified on arithmetic, not on preference.** 32-bit FNV-1a yields
2^32 ids, and the birthday bound for 50% collision probability is
`sqrt(2 * 2^32 * ln 2) ≈ 77163` relations. 128-bit truncated SHA-256 yields
`sqrt(2 * 2^128 * ln 2) ≈ 2.17e19` relations. The platform targets 10^7 relations, which is
about 130x past the 32-bit 50% point — a more likely than not outcome rather than a tail
risk. 32-bit identity is therefore rejected outright. (64-bit, as used by `hyperedge_id`, has
its 50% point at `sqrt(2 * 2^64 * ln 2) ≈ 5.06e9`; it is adequate for today's hypergraph
volume, which is exactly why it has not failed yet, and normalising to 128 bits removes the
question instead of deferring it a second time.)

**FNV-1a is retired for identity only, and retained elsewhere.** It stays in
`apps/webapp/src/lib/edgeFormation.ts` for the layout seed (`layoutSeed`,
`edgeFormation.ts:91-95`) and in `apps/webapp/src/lib/graphState.ts` for
`entitiesKeyFor` and `checksumOf`. Concretely:

- `811c9dc5` in `graphState.test.ts:132` **keeps passing unchanged**. It is a
  non-identity vector and the helper it exercises is retained.
- `e:1d374e53` in `edgeFormation.test.ts:18` and `:138` is **replaced** by a new pinned
  128-bit vector. It is an identity vector for the code path being retired.
- The two FNV-1a implementations are not consolidated in this change. Leaving them
  duplicated is a recorded follow-up, not an oversight, so that no view-state module is
  touched by an identity feature.

**Arity is a first-class part of identity, with one canonicalisation rule per mode.**
`RelationArityMode` has exactly four values:

| Mode | Participant canonicalisation | Identity material | Window in identity? | `neighbors` default |
|---|---|---|---|---|
| `UNDIRECTED` | sort members ascending, dedupe | `{"mode","type","members": sorted(set(participants))}` | no | `both` |
| `DIRECTED` | preserve order: `(subject, object)` | `{"mode","type","subject","object"}` | no | `out` |
| `NARY` | sort `(role, member)` pairs by role | `{"mode","type","roles": [[role, member], …] sorted by role}` | no | `both` |
| `TEMPORAL` | ordered members, window participates in identity | `{"mode","type","members": ordered, "valid_from","valid_to"}` | **yes** | `out` |

Registration rejects a declared arity that conflicts with the participant shape: a
`DIRECTED` type given role bindings, or an `NARY` type given fewer than two role bindings.

**`min`/`max` normalisation in `makeEdgeId` is correct for `co_occurrence` and wrong for
every other planned type.** For `co_occurrence` the assertion is "these two were observed in
the same observation", which is true if and only if its reverse is true, so sorting *is* the
correct canonical form. For `works_for`, `owns`, `located_in`, `founded`, `reports_to`,
`employed_by` and `controls` the reverse is either false, meaningless, or an
independently meaningful relation, and collapsing the pair makes the surviving id stand for
a statement nobody made. `located_in` is the sharpest case: both orientations are well-formed
and both are generally false. `controls` and `owns` are antisymmetric by definition, so
merging the orientations removes the possibility of expressing the relation at all.
`reports_to` also has differing endpoint classes, so a symmetric canonicalisation would let
`ORGANIZATION reports_to PERSON` and `PERSON reports_to ORGANIZATION` share one identity —
which would then force the semantic layer to reject one of two claims that are the same
relation.

**Arity mode is part of the identity material.** An `NARY`
`Employment{person=P1, org=O1}` and a `DIRECTED` `P1 employed_by O1` are **different
identities** even though the participants are the same, because the declarations genuinely
differ. A relation cannot silently change arity without changing identity, and the
declaration stays auditable from the id's material. `NARY` with exactly two members is legal
and yields a different id from the same pair declared `DIRECTED`.

**Identity is two-level, and identical content yields an identical id.**

- `logical_relation_id` answers *which relation this is*. Its material is the arity-mode
  shape above: arity mode, relation type, canonical participants, role bindings. It
  **excludes** the temporal window, evidence refs, context ref and revision number. All
  revisions of one relation share it.
- `relation_id` answers *this content*. Its material is the `logical_relation_id` plus the
  temporal window, observation and publication times, evidence refs, context ref and
  revision number. Distinct content always produces a distinct `relation_id`; identical
  content always produces an identical one, which makes idempotency structural rather than a
  caller discipline.

This follows the precedent already in the domain: `hyperedge_id()` (`hypergraph.py:29-50`)
for the logical identity shared by all versions, and `hyperedge_version_id()`
(`hypergraph.py:53-86`) for one content-distinct version. Reusing those conventions is
cheaper than a parallel scheme and prevents the two from disagreeing about what a relation is.

**A collision is recorded and surfaced, never treated as an identity merge.** Because a
128-bit collision is astronomically unlikely but not impossible, and because at read time a
collision is indistinguishable from a merge, any collision detected within a claim set must
be reported with the colliding ids and the claims involved, and an operator must be able to
see it. Suppressing it would turn an unobservable event into a silent data-integrity failure.

## Rationale

- **The birthday bound is the whole argument.** A 32-bit id is a routine collision waiting
  for the relation count to grow, and the platform is designed for millions to tens of
  millions of relations. At 2^128 the expected number of collisions among 10^7 relations is
  about 1.4e-23 — not merely "small", but unobservable.
- **Truncating a cryptographic hash changes the mixing quality, not just the width.** FNV-1a
  collisions are constructible offline; truncated SHA-256 collisions are an infeasible
  exercise. This is why the bound moves by twelve orders of magnitude rather than by a
  constant.
- **UTF-8 bytes, not UTF-16 code units.** `edgeFormation.ts:59` walks UTF-16 code units via
  `charCodeAt`, so a Cyrillic or astral-plane identifier hashes a different byte sequence
  than `material.encode("utf-8")` on the Python side. Canonicalising on UTF-8 bytes removes
  a cross-language identity skew that would otherwise surface as "one relation, two ids" —
  the exact failure the frontend identity contract exists to prevent.
- **The canonical form is already house style.** `sort_keys=True` with compact separators is
  used by `hypergraph.py:41-49` and `:73-85` and by `_digest` in
  `apps/shared/domain/temporal_worldline.py:131-134`, and `event_identity_material` /
  `event_id_for` (`temporal_worldline.py:588-616`) already document "the exact material an
  `event_id` is derived from". The material is therefore the audit trail: an operator can
  recompute any relation id without running the pipeline.
- **Arity-aware canonicalisation is what makes direction assertable.** A symmetric
  normaliser cannot represent `A works_for B` and `B works_for A` as distinct, and cannot
  represent the inverse type as a different relation at all. Sorting the members of an
  `NARY` relation is not sufficient either: role assignment must stay load-bearing, or
  `role=CEO` and `person=CEO` become indistinguishable. Sorting `(role, member)` pairs gives
  order-insensitivity over pairs while keeping roles meaningful.
- **`TEMPORAL` is a separate mode, not a `DIRECTED` variant.** A temporal relation's
  identity must include its window, otherwise two disjoint employment intervals collapse into
  one relation and the worldline cannot express that the person held the role twice — which
  `temporal_worldline.py:995-1079` already models as distinct `PRECEDES` / `FOLLOWS`
  relations between distinct `WorldlineEvent`s. Folding the window into every directed
  relation's material would make *all* directed relations revision-addressed and destroy the
  identity/revision split.
- **The two-level split makes correction a revision, not a second relation.** Correcting an
  employment interval from `2017-2020` to `2017-2022` is the same relation with new content:
  same `logical_relation_id`, new `relation_id`, `supersedes` set. Under a single id, the
  correction either overwrites the prior assertion or becomes an unrelated second relation, and
  in both cases "all versions of this relation" is unanswerable.
- **Including evidence and context in the version material prevents silent loss.** If
  `relation_id` covered only the window, re-asserting the same interval with a new
  observation would be an overwrite and the new observation would be discarded — the same
  class of loss the constitution forbids in Governance.
- **Identity must be total, not merely likely.** Determinism across backend, frontend and
  replay is what lets the read API cite backend relation ids, and it is only achievable if
  the material is documented and reconstructible from the record alone.

## Consequences

### Positive

- `(A, works_for, B)` and `(B, works_for, A)` diverge while `(A, co_occurs_with, B)` and
  `(B, co_occurs_with, A)` converge — the whole defect, pinned as a test.
- N-ary member order stops mattering and role permutation starts mattering, which no existing
  code expresses.
- Identity is an auditable function of documented material, and identical content is
  structurally idempotent, so callers cannot get it wrong.
- The key width matches `hyperedge_version_id`, so no new width enters the persisted surface.
- "All revisions of this relation" becomes a single indexed lookup rather than a scan.

### Negative

- 32 hex characters instead of 8: four times the key width on every relation. At 10^7
  relations that is roughly 320 MB of key bytes before index overhead. Accepted — the
  correctness win dominates.
- Every previously written frontend edge id of the form `e:xxxxxxxx` is invalidated, and the
  persistence payloads pinned around those ids in `edgeFormation.test.ts` must be rewritten.
- Two FNV-1a implementations with the same offset and prime but different signatures remain
  in the tree, and keeping them is what makes the retirement safe. A reader who does not know
  the carve-out will see a `fnv1a` call inside an identity module and assume a bug.
- Four arity modes is one more concept than the current code, which has none. The cost is paid
  once in the registry rather than in every consumer.
- An `NARY` relation with exactly two members and a `DIRECTED` relation over the same pair
  produce two relations. That is intended, but until arity is a queryable registry attribute
  it will surface as apparent duplication.

### Follow-up

- Consolidating the two FNV-1a implementations into one shared `fnv1aHex` helper, with
  `811c9dc5` still passing. Deliberately out of scope here so that no view-state module is
  touched by an identity change.
- A collision-detector test over a generated corpus that exercises the **reporting** path, not
  only the no-collision path. Without it the reporting code is as unexercised as `write_edge`.
- Arity must be registered and queryable before any extractor emits relations, or extraction
  will guess a mode per call site and the identity space will fragment. This is a hard
  precondition for the deferred extraction feature.
- `apps/shared/events/ontology_pack.py:36-38` already lists `works_at`, `owns` and `controls`
  as flat strings; each needs an explicit arity declaration before it is honoured.
- A legacy-id alias for relations written before this feature. It is not in this change's
  schema; the migration note is the deliverable.

## Alternatives considered

**Keep 32-bit FNV-1a, optionally widened with a prefix.** Rejected. FNV-1a over a prefixed
string is still FNV-1a over a 32-bit state, so a prefix raises the number of distinct input
strings, not the number of distinct output values; the 50% bound stays at 77163 relations.
Widening the rendered digest does not help either, because the state is 32 bits. The only
two variables that move the bound are the width of the output and the quality of the mixing
function, and this decision changes both at once.

**UUIDv5 over a fixed namespace.** Rejected. UUIDv5 is SHA-1 truncated to 128 bits, so the
width is right and the hash is not — SHA-1 collision resistance is broken. More importantly it
requires a namespace UUID, and the natural namespace here is the relation type, which means
identity would be resolvable only through a registry lookup and a claim's id could not be
recomputed from the claim alone. That reintroduces exactly the indirection the relation
schema registry exists to remove, and it loses the `RL-` / `RC-` prefixes that make an id
readable in a log line.

**A single-level edge id, with no logical/revision split.** Rejected because it makes
correction unrepresentable. Under one id a corrected interval either overwrites the prior
assertion — destroying the record that the system once believed the narrower window, in
direct violation of "assertion != truth" and of the governance requirement that rejected
outputs are preserved — or appends a second unrelated edge, leaving supersession a naming
convention rather than a link. The two-level precedent already exists and works
(`hypergraph.py:29-86`).

**Exclude arity mode from the identity material.** Rejected. If arity is not in the material,
the same participants under two declarations share one id, and the semantic layer would then
have to reject one of two claims that are the same identity — incoherent. It also makes a
silent arity change invisible: a relation could be reinterpreted as `NARY` and keep its id.
Putting the mode in the material is what makes the declaration auditable.

**A UUIDv7 time-ordered id.** Rejected. It is non-deterministic across replays: the same
content processed twice yields different ids, which breaks content-addressed idempotency and
makes "these two claims are byte-identical" unverifiable. It also entangles identity with
wall-clock time, so a re-materialisation from a different clock rewrites every id and the
rebuild path can no longer be checksummed against the original. Identity here must be a pure
function of content.

## References

- `specs/016-relation-evidence-graph-fabric/spec.md` — FR-004, FR-008, FR-009, FR-011,
  FR-012, FR-035, FR-043, FR-044, FR-046; SC-001, SC-002, SC-015; Risk: identity change
  breaks existing stored edges.
- `specs/016-relation-evidence-graph-fabric/plan.md` — canonicalisation table, Complexity
  Tracking, Structure Decision.
- `specs/016-relation-evidence-graph-fabric/data-model.md` — section 1 (digest primitives),
  section 2 (arity modes), section 4.1 (identity derivation), section 9.1 (`GraphEdge`).
- `specs/016-relation-evidence-graph-fabric/research.md` — Decision 1 (identity), Decision 2
  (arity and canonicalisation), Decision 3 (identity vs revision), defects 1, 3, 8, 14.
- `.specify/memory/constitution.md` — invariant 3 "Assertion != truth", invariant 12
  (rebuildable projections), Governance (preserved rejections, source independence).
- `apps/shared/domain/hypergraph.py:29-50` — `hyperedge_id`, the logical-identity precedent.
- `apps/shared/domain/hypergraph.py:53-86` — `hyperedge_version_id`, the 32-hex precedent.
- `apps/shared/domain/temporal_worldline.py:131-134`, `:588-616` — the existing digest
  primitive and the documented-material pattern.
- `apps/webapp/src/lib/edgeFormation.ts:12-18`, `:56-64`, `:71-76`, `:91-95` — `EdgeKind`,
  `fnv1a`, `makeEdgeId`, `layoutSeed`.
- `apps/webapp/src/lib/edgeFormation.test.ts:18`, `:138` — the replaced `e:1d374e53` vector.
- `apps/webapp/src/lib/graphState.ts:22-23`, `:64-71`, `:85-95`, `:184-186` — the retained
  non-identity uses.
- `apps/webapp/src/lib/graphState.test.ts:132` — the retained `811c9dc5` vector.
- `apps/projection/graph/abstraction.py:29-37`, `:97-98`, `:131-132`, `:179-184` —
  `GraphEdge`, the write/read methods, and the direction loss.
- ADR-0008 (graph abstraction layer), ADR-0011 (event schema), ADR-0012 (provenance),
  ADR-0022 (indexed worldline relations).
