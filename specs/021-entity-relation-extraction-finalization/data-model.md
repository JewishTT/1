# Phase 1 Data Model: 021-entity-relation-extraction-finalization

**Date**: 2026-09-27 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)

This document defines the entities, their fields, and the identity rules. Everything here is
derived from the code at HEAD `0056665` plus [research.md](./research.md); where it changes an
existing type, the change and its reason are both stated.

**The seven levels are never collapsed** (I-2):
`Observation → Mention → TypeHypothesis → RelationSignal → PredicateSignature →
RelationCandidate → RelationClaimMaterial → RelationClaim → GraphEdge/HyperEdge`

---

## 1. `PredicateSignature` (NEW — the identity carrier)

Answers open question **Q1** from research.md. This is the single most load-bearing type in
the feature: it replaces the raw surface string as the predicate term in
`logical_candidate_id`.

```python
@dataclass(frozen=True)
class PredicateSignature:
    normalized_predicate: str          # NFKC, casefold, whitespace/punct-folded, verb-normalised
    arity: int                        # >= 2; n-ary is native
    role_names: tuple[str, ...]       # length == arity; positional when unnamed
    argument_shape: tuple[str, ...]   # per-argument shape code, e.g. "entity", "value", "literal"
    direction: DirectionHypothesis    # subject_to_object | object_to_subject | undirected | ambiguous
    polarity: Polarity                # asserted | denied | uncertain
    schema_version: str = "1"
```

**What a signature deliberately does NOT carry**, and why:

| Absent | Reason |
|---|---|
| `relation_surface` | Raw words are evidence, never identity (FR-005). A paraphrase must not fork the hypothesis. |
| `relation_ref` | Mapping to a known operator is a later, versioned step. Keying on it would re-split one hypothesis into two the moment a regime recognised it — the exact failure `relation_candidate.py:1119-1129` documents. |
| `confidence` | Confidence is a mutable projection field, never identity. |
| any entity id | `Mention ≠ Entity` (I-2). A signature describes structure, not referents. |

**Normalisation rules** — each is a separate, individually tested rule (Q1):

| # | Rule | Example |
|---|---|---|
| N1 | Unicode NFKC, then casefold | `Café` → `café` |
| N2 | Collapse internal whitespace, strip edge punctuation | `  "Works For" ` → `works for` |
| N3 | Voice normalisation: a passive/copular frame maps to its active predicate class | `is the originator of` → `originator of`; `was acquired by` → `acquire` |
| N4 | Light verb/delexicalisation for a *closed* function-word set only | `is a subsidiary of` → `subsidiary of` |
| N5 | Synonym set membership for a *small, versioned, sourced* table — never open-ended | `owns` ≡ `controls` **only** if the table says so |
| N6 | Argument-shape extraction from the parsed frame | `Acme Corp` → `entity`; `40%` → `value`; `2021` → `literal` |

N5 is the dangerous one and is bounded deliberately: a versioned, sourced synonym table is a
*claim about equivalence*, so it is versioned, reviewable, and carries provenance. An
unbounded embedding or a learned model here would make identity depend on a model artefact,
which fails the constitution's determinism requirement (VI). **If N5 cannot be justified from
a source, the predicate stays as two signatures and the platform reports `AMBIGUOUS`.**

Unknown predicates are first-class: `"John is the originator of Acme."` yields
`normalized_predicate="originator of"`, `arity=2`, `direction=subject_to_object`,
`polarity=asserted`, `relation_ref=None`, `resolution_state=UNKNOWN`. That is a complete,
durable hypothesis — the §90 unknown test, end to end.

---

## 2. `RelationSignal` (CHANGED — natively n-ary, real polarity)

Current state at HEAD: `subject_mention_ref: str` + `object_mention_ref: str`, two required
distinct scalars (`signal.py:281-282`, validated `:326-338`). N-ary survives only as opaque
`extra` tuples, and `extra` is excluded from `_material()`.

```python
@dataclass(frozen=True)
class RelationParticipant:
    mention_ref: str        # MUST resolve in the mention index (FR-103)
    role: str = ""          # "" when the document does not state one
    argument_shape: str = "entity"

@dataclass(frozen=True)
class RelationSignal:
    participants: tuple[RelationParticipant, ...]   # variadic; arity >= 2
    kind: SignalKind                              # OBSERVATION CHANNEL ONLY after §15 split
    relation_surface: str                         # raw observed words — evidence only
    predicate_signature: PredicateSignature | None # None only when surface-only co-occurrence
    polarity: Polarity                            # was overloaded onto SignalKind.NEGATION
    neighbourhood: Neighbourhood
    signal_id: str = ""
    # … all 019 fields retained
```

**`SignalKind` is split** (FR-011). Today it has 13 members mixing three different things:

| Today | Becomes |
|---|---|
| `LEXICAL`, `LINK`, `REFERENCE`, `TABLE`, `LIST`, `METADATA`, `ATTRIBUTE`, `HIERARCHY`, `SCHEMA` | remain `SignalKind` — these are observation channels |
| `CO_OCCURRENCE` | remains a `SignalKind`; becomes constructible with an empty surface (FR-006) |
| `NEGATION` | **removed** → `Polarity.denied` on the signal |
| `QUANTITY` | **removed** → `argument_shape="value"` on the participant + a `quantity` note |
| `COREFERENCE` | **removed** → a coreference relation between mention refs, not an observation channel |

There is no `TEMPORAL` member today; temporal information already lives in `stated_axes`
(`TemporalAxis`) and `SourceTemporalObservation`. The brief names one, the code does not have
it, and it must not be added as a kind.

Note the four kinds that no producer emits today — `CO_OCCURRENCE`, `COREFERENCE`, `QUANTITY`,
`NEGATION` — are exactly the ones being dissolved into fields. A vocabulary that only names
things nobody produces, and names them wrongly, is the defect.

**Identity (`_material`) changes** (FR-089): add `predicate_signature`, `polarity`, the
declared `arity` and `role_names`. Remove nothing — `producer_ref` **stays**, because FR-034's
independence count requires producer identity. What stays wrong is the three docstrings that
claim two producers reading one structure share a `signal_id`; they get corrected, not the code.

`signal_asserts_nothing` is replaced by the honest rule: a `CO_OCCURRENCE` signal **may** have
an empty `relation_surface` and a `None` signature. Adjacency that was seen and not named is a
real observation. What remains refused is a signal with an empty surface, no signature, and a
kind that *does* assert a predicate — that is an unrecorded gap, not a co-occurrence.

---

## 3. `RelationCandidate` (CHANGED — signature-keyed identity, serialisable)

```python
@dataclass(frozen=True)
class RelationCandidate:
    participants: tuple[RelationParticipant, ...]   # was subject/object scalars
    predicate_signature: PredicateSignature | None
    relation_ref: RelationRef | None                # mapping, NOT identity
    predicate_hypothesis: PredicateHypothesis | None
    relation_surface: str                           # EVIDENCE / revision material
    # … 019's remaining fields retained
    candidate_id: str = ""
    logical_candidate_id: str = ""
```

**Identity rule** (FR-005, FR-007) — this is the change the whole feature exists for:

```
logical_candidate_id = "CAND-" + digest128(canonical_material({
    "arity_mode":    <from signature>,
    "participants":  <sorted (role, mention_ref) pairs, or ordered subject/object when directed>,
    "signature":     <signature content key>,   # was: relation_surface
    "tenant_id":     <tenant>,
}))
```

Two consequences that the corpus MUST prove:

- `"John is the originator of Acme."` and `"Acme was originated by John."` → **one**
  `logical_candidate_id`, two `candidate_id` revisions, two `relation_surface` values. True in
  the corpus; false at HEAD.
- `"works for"` vs `"Works For"` → one logical id. False at HEAD (no normalisation exists at
  all on this path).

**`signal_refs` is canonicalised on construction** (FR-085), alongside the collections that
already are (`observation_refs`, `evidence_refs`, `supporting_spans`). At HEAD it is identity
material that is never sorted, so `candidate_id` depends on caller iteration order and
determinism holds only because `assembly.py:338` sorts by hand at one call site.

**`to_dict()`/`from_dict()` are added** (FR-086), covering all fields losslessly, and
`relation_surface` is guaranteed to survive the round trip as text — it is evidence, and
evidence that is only stored as a digest is evidence that is gone.

---

## 4. `PredicateHypothesis` (EXTENDED — mapping state separated from structure)

`PredicateResolutionState` stays exactly as it is: `KNOWN`, `UNKNOWN`, `AMBIGUOUS`,
`CONFLICTING`. It describes the **mapping** to a known operator, which is a different question
from the structure. The two are separate fields and are never merged.

| Field | Holds |
|---|---|
| `surface_form` | raw words, verbatim |
| `normalized_form` | normalised predicate — gains a real normaliser (N1–N6) instead of copying the surface |
| `relation_ref` | mapping to a known operator, or `None` |
| `alternative_refs` | competing mappings, each with evidence |
| `resolution_state` | `UNKNOWN`/`AMBIGUOUS`/`CONFLICTING`/`KNOWN` |
| `mapping_evidence_refs` | why the mapping was made |

`PredicateSignature` is **not** stored inside `PredicateHypothesis`: the signature is the
*structure*, the hypothesis is the *mapping attempt*, and merging them is how a hypothesis ends
up unable to represent "structure known, mapping unknown" — the single most important state in
the feature. `relation_ref=None` with a full signature is legal and is the norm.

**Persistence change** (FR-087): `alternative_refs` and `mapping_evidence_refs` get real
columns. Today they sit inside `candidate_id` material and have no column at all, so two
candidates differing only in their alternatives get different ids with no stored reason, and
`PredicateHypothesis` survives only as a 32-char digest.

---

## 5. `Polarity`, `DirectionHypothesis`, `Arity`

```python
class Polarity(StrEnum):          # NEW — was overloaded onto SignalKind.NEGATION
    ASSERTED = "asserted"
    DENIED    = "denied"
    UNCERTAIN = "uncertain"
```

`DirectionHypothesis` is unchanged: `SUBJECT_TO_OBJECT`, `OBJECT_TO_SUBJECT`, `UNDIRECTED`,
`AMBIGUOUS` — already persisted on `relation_signal`, **absent from `relation_candidate`**, and
`polarity` is not a column on any table (it is a derived local in `assembly.py` only). A
negated candidate and an asserting candidate over the same pair are currently indistinguishable
after a round trip.

`RelationArityMode` is unchanged: `UNDIRECTED`, `DIRECTED`, `NARY`. **N-ary is native** — role
bindings, not a binary pair with an `extra` payload.

---

## 6. Mention index and type layer

**`MentionIndex` (NEW)** — the pre-resolution binding seam (FR-034, FR-103). Maps a producer's
observation to real `MN-…` ids minted once per `(segment, kind, value, start, end, extractor)`.
Producers cite resolved mention refs; the index is the only thing that mints them. At HEAD there
is **no** such index, no resolution code for the `surface:`/`anchor:`/`href:`/`header:`/
`cell:`/`document:`/`meta:`/`byline:`/`attribute:`/`value:`/`jsonld:`/`jsonld-value:` prefixes,
and 100% of producer participant refs are fabricated.

**`TypedMention`** gains real type state (FR-029…FR-032):

```python
@dataclass(frozen=True)
class TypeHypothesis:            # competing, not singular
    mention_ref: str
    hypotheses: tuple[TypeCandidate, ...]   # >= 1
    state: CandidateResolutionState          # RESOLVED | AMBOUSSED | UNRESOLVED
    vocabulary_version: str
    evidence_refs: tuple[str, ...]
```

`TypeHypothesis` today is thin (`semantic/blocking.py`) and `TypeAssertion` carries a single
hypothesis, so "Apple" cannot be three things at once (User Story 4).

**Bounded type vocabulary (NEW)** — `core:*` for entities, `value:*` for value types, versioned,
extensible by hierarchy (`core:Organization` → `industry:Bank` → `industry:CommercialBank`).
Answering **Q2**: the vocabulary is a **mapping/blocking/validation instrument, not a gate**. An
unmapped type yields `UNKNOWN` and is retained; it is never a rejection. The `relations` list on
the existing `apps/shared/events/ontology_pack.py` is inert (`allows_relation()` is never
called) and stays inert — a fixed relation list is what §104 forbids.

---

## 7. Persistence mapping (migration `021`)

`020_universal_relation_extraction` is the current Alembic head and is forward-only
(`downgrade()` raises `NotImplementedError`). `020` is not edited. `021` adds:

| Table | Added columns | FR |
|---|---|---|
| `relation_signal` | `predicate_normalized`, `predicate_arity`, `predicate_roles`, `predicate_argument_shapes`, `predicate_direction`, `predicate_polarity`, `predicate_alternatives`, `predicate_mapping_evidence` | FR-087 |
| `relation_candidate` | same signature set, plus `signal_refs`, `direction`, `polarity`, `confidence`, `predicate_alternatives`, `predicate_mapping_evidence` | FR-087, FR-088 |
| `relation_claim` | `candidate_id` | FR-088 |
| `source_temporal_observation` | a repository, writer and reader — the table has **none** today | FR-096 |

ORM/migration parity is test-enforced for `020` and MUST stay enforced for `021`.

**Today, three tables are written by nothing.** No `INSERT` for `relation_signal`,
`relation_candidate` or `source_temporal_observation` exists anywhere in `apps/`, `bench/` or
`tools/`. `SqlRelationClaimStore` (558 lines) has zero importers, and its
`record_validation`/`non_valid` raise `NotImplementedError` because migration 016 never created
a home for a verdict. Persistence is the largest single block of work in this feature and the
one where "verified" and "verified only offline" will differ, because live PostgreSQL is not
reachable in this environment.

---

## 8. Graph projection

`GraphProjectionBridge` is already correct and must not change shape: it is typed
`claim: RelationClaim` with no overload, so **a candidate or a signal cannot be projected even
by mistake** — the constitution holds at the type level. `to_edge` mints nothing
(`edge_id=claim.relation_id`); `to_hyperedge` refuses a non-NARY claim and builds members from
`role_bindings`.

Two gaps to close: `properties` carries no `direction` or `polarity` (only `arity_mode`), and
there is no wired rebuild-from-store path. The projection change is therefore additive
metadata plus a rebuild test — not a re-architecture. Switching the production default from
`InMemoryGraphStore` to `Neo4jGraphStore` is explicitly **out of scope** (research R-006): the
Neo4j store is unwired, does not import the driver, and lives in a package that does not
declare the dependency, so switching would trade one unwired integration for another.

---

## 9. Entity summary

| Entity | Status | Identity key | Notes |
|---|---|---|---|
| `PredicateSignature` | NEW | content key | Structure only. No surface, no ref, no confidence, no entity id |
| `Polarity` | NEW | — | Replaces `SignalKind.NEGATION` |
| `RelationParticipant` | NEW | (role, mention_ref) | Variadic; replaces the two scalars |
| `RelationSignal` | CHANGED | `SIG-` + digest over signature + participants + `producer_ref` | Natively n-ary |
| `PredicateHypothesis` | EXTENDED | — | Mapping state, separate from structure; real normaliser |
| `RelationCandidate` | CHANGED | `CAND-` + digest over **signature** | `relation_surface` becomes evidence |
| `TypeHypothesis` | EXTENDED | — | Competing hypotheses, not singular |
| `MentionIndex` | NEW | `MN-` + digest | The only minter of mention ids |
| `TypeVocabulary` (`core:*`/`value:*`) | NEW | — | Versioned, bounded, never a gate |
| `RelationClaimMaterial` | unchanged | `RL-`/`RC-` | Boundary already correct: `relation_type` required here, not in the candidate |
| `RelationClaim` | EXTENDED | `RL-`/`RC-` | Must self-verify its carried id (FR-099) |
| `GraphEdge`/`HyperEdge` | unchanged | derived from `relation_id` | Projection only, claims only |
| `SourceTemporalObservation` | unchanged | `STO-` | Needs a repository to be reachable at all |
