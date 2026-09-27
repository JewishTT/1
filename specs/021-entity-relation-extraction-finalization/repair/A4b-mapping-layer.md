# A4b — THE MAPPING LAYER (spec repair)

**Job**: A4b. **Feature**: `021-entity-relation-extraction-finalization`.
**Repo root**: `C:\Users\tim\Desktop\COGNITIVE\1` (not the parent).
**Date**: 2026-09-27. **HEAD at review**: `0056665 fixing extraction`.
**Reads**: `spec.md`, `data-model.md`, `phase0-results.md`, `input.md`, and the code at the
paths cited. **Writes**: this file only. No existing file is edited.

## Scope — what this job owns

This job owns everything **below** identity. Identity itself — `PredicateSignature`, its
normaliser, voice normalisation, participant ordering, `logical_candidate_id` derivation — is
owned by **A2-identity-subsystem** and is treated here as a **given interface**:

```
surface predicate
   │
   ▼  (A2: N1–N4, N6 — deterministic, no synonym table)
PredicateSignature
   │
   ▼  (A2 owns the proof that this key is stable)
logical_candidate_id   "CAND-…"
```

Everything this document specifies starts one level *below* that arrow: how a signature is
turned into a `RelationRef`, what happens when two readings compete, what a mapping record
looks like, how external vocabularies cross, and what a fixed relation list may not be.

**Explicitly not specified here**: `PredicateSignature` fields, normalisation rules, voice
normalisation, participant canonicalisation, role-name normalisation, the derivation of
`logical_candidate_id`, and the `CNDR-`/`candidate_id` revision digest. Those are quoted
where they constrain me, and referenced as the given interface everywhere else.

### The single failure being corrected

`data-model.md` line 57 states:

> **If N5 cannot be justified from
> a source, the predicate stays as two signatures and the platform reports `AMBIGUOUS`.**

This is wrong in three separable ways, and each has a distinct owner:

| The claim | Why it is wrong | Owner |
|---|---|---|
| synonym knowledge belongs in identity at all | a synonym table is a *claim about equivalence*; making it identity is what phase0 finding **E1** calls an identity authority | **A2** (delete N5) |
| synonym knowledge belongs *below* identity | it belongs in the mapping layer, where a claim about equivalence is versioned, reviewable and citable | **A4b** (this document, D1/D2) |
| `AMBIGUOUS` means *two signatures* | two signatures are **two candidates**. `AMBIGUOUS` is **one** logical hypothesis carrying `alternatives = [...]`. Two candidates *destroys* the uncertainty the state exists to hold | **A4b** (this document, D3) |

`phase0-results.md` **E5** records the third row verbatim:

> | E5 | `data-model.md` N5 fallback | "`AMBIGUOUS`" = two signatures | FR-028 requires **one** logical hypothesis with alternatives. Two signatures = two candidates |

And the consequence that makes it more than a wording error: **nothing in the current task set
produces `AMBIGUOUS` or `CONFLICTING`**, so every uncertain predicate collapses to `UNKNOWN`,
and `input.md:4385` lists `* alternatives survive` as a mandatory acceptance criterion under
§108 *Relation substrate*. A state that no task can reach and that no test can observe is a
state the criterion is written about and the platform cannot satisfy.

---

## D0 — The code that already exists, and why it changes the answer

Before specifying anything, one measured finding, because the specification must be written
against the code and not against the assumption that the code is missing.

**The mapping layer is already built.** `apps/shared/semantic/mappings.py` (1174 lines)
contains a complete, SSSOM-oriented, provenance-bearing, content-addressed mapping apparatus:

| Symbol | Line | What it is |
|---|---|---|
| `SemanticMapping` | `mappings.py:216` | one recorded cross-vocabulary correspondence; `identity` = `(tenant, subject_ref, object_ref, predicate, mapping_set_id, mapping_set_version)`; `content_key()`, `with_id()`, `to_dict()`, `cite()`, `conflicts_with()`, `supersedes_ref()` |
| `MappingSet` | `mappings.py:603` | one versioned alignment effort; content-deduplicated, canonically ordered |
| `MappingRegistry` | `mappings.py:~780` | `mappings_for()` (`:892`), `cite()` (`:1012`), `conflicts()` (`:1032`); returns tuples and never collapses |
| `MappingCitation` | — | citable form of a mapping claim |
| `MappingConflict` | — | two mappings that disagree about the same pair, surfaced not resolved |
| `MappingJustification` | `mappings.py:97` | `LEXICAL` / `MANUAL` / `INFERENCE` / `STATED_IN_SOURCE` |
| `MatchPredicate` | `vocabularies.py` | `EXACT_MATCH` / `CLOSE_MATCH` / `BROAD_MATCH` / `NARROW_MATCH` — **four members** |
| `SemanticMappingRow` | `db/schema.py:1477` | the `semantic_mappings` table (migration 018), `predicate` column + both-direction indexes |

Its module docstring already states the design constraint this whole job is about:

> `apps/shared/semantic/mappings.py:10`
> **A mapping is a claim, not an identity.** This is the whole design constraint, and it is
> structural rather than a promise in a comment.

**Three consequences.**

1. **`TypeMapping` (FR-036) must not be minted as a new dataclass.** The seven fields §9
   requires are, one for one, fields `SemanticMapping` already has. See **D5**. Writing a
   parallel `TypeMapping` would be the defect this review exists to remove.
2. **`PredicateMappingCandidate` is the only genuinely new type on the predicate side**, and
   it is a *proposal*, not a *record* — a distinction `SemanticMapping` already makes between
   a claim made by a process and a claim recorded in a set. See **D1**.
3. **`SemanticMapping` is itself unreachable.** `MappingRegistry(` and `MappingSet(` are
   **never constructed in production code** — the only two call sites are inside
   `mappings.py` itself (`mappings.py:671`, `:1113`). There is no non-test importer. This
   belongs in `spec.md`'s *Production reachability, as measured* table (line 791), alongside
   `SqlRelationClaimStore` and `GraphProjectionBridge`, because FR-036/FR-037 are
   unbuildable-and-unverifiable without it and the reachability table is where a reader looks
   for exactly that. **New row requested.**

---

## D1 — `PredicateMappingCandidate`

### D1.1 Placement and rationale

New frozen dataclass in `apps/shared/domain/predicate_mapping.py`. One new value object on
the predicate side. It is a **proposal**: a claim that a mapping process made about one
`PredicateSignature`, before any `MappingSet` has recorded it and before any `RelationRef`
has been earned.

It is deliberately **not** a subclass of, alias for, or wrapper around `SemanticMapping`:

| | `PredicateMappingCandidate` (NEW) | `SemanticMapping` (existing) |
|---|---|---|
| what it is | a proposal produced during assembly | a claim recorded in a `MappingSet` |
| `source` is | a `PredicateSignature` content key (a predicate term) | a type reference, normalised by `semantic.vocabularies.normalize_type_ref` |
| `target` is | a predicate reference (`wikidata:P127`, `schema:worksFor`) — a **relation** | a type reference (`core:Person`) |
| confidence/provenance in identity? | **no** — all revision material | **no** — deliberately excluded from `SemanticMapping.identity` (`mappings.py:294-309`) |
| persistence | inside `PredicateHypothesis` | its own table, `semantic_mappings` |
| who cites it | `PredicateHypothesis.mapping_evidence_refs` | `MappingCitation` |

Reusing `SemanticMapping` for predicates would require `normalize_type_ref` (a *type*
vocabulary function) to accept a predicate term, and would put predicate mappings in
`semantic_mappings` alongside type mappings with nothing to tell them apart — the same
"one field, two meanings" defect as `RelationSignal.kind` before FR-011 split it.

### D1.2 `MappingMatchType` — the SSSOM member set, and which one is adopted

**What the brief actually says.** Checked as instructed:

- §2 (line 240): "SKOS is appropriate as inspiration for vocabulary/hierarchy/mapping
  semantics, and SSSOM is an appropriate provenance-oriented model for mappings between
  vocabularies." — *sanctions the model, enumerates nothing.*
- §9 (line 770): "Use a mapping structure compatible with the existing SSSOM-oriented
  architecture." — *points at the architecture in D0, not at a member list.*
- §64 (line 2890): "Use SSSOM-compatible semantics where practical." — *"where practical" is
  a licence to diverge, explicitly.*
- §65 — **contains no match-type vocabulary at all.** It is the relation-vocabulary policy
  section: it forbids a mandatory relation enum and lists nine known operators. So the
  instruction to "verify against brief §2/§65" resolves as follows: §2 supplies the model,
  §65 supplies the *reason a bounded match-type vocabulary is needed at all* (relations are
  too dependent on context to be enumerated), and **neither enumerates the members.** The
  five-member set is imported from SSSOM itself, which is an external-vocabulary import and
  must therefore be declared as one.

**Adopted**: a single enum, **`MappingMatchType(StrEnum)`**, with the **five** SSSOM members,
in the repository's existing snake_case dialect (not SSSOM's camelCase — `MatchPredicate` uses
`"exact_match"`, `PredicateResolutionState` uses `"unknown"`, `SignalKind` values are
snake_case; emitting `exactMatch` would fork the dialect in the *other* direction, and
"SSSOM-compatible" is a claim about semantics, not about spelling).

| `MappingMatchType` | SSSOM lexical form | `MatchPredicate` today | change |
|---|---|---|---|
| `exact_match` | `exactMatch` | `EXACT_MATCH = "exact_match"` | **value byte-identical** |
| `close_match` | `closeMatch` | `CLOSE_MATCH = "close_match"` | **value byte-identical** |
| `narrow_match` | `narrowMatch` | `NARROW_MATCH = "narrow_match"` | **value byte-identical** |
| `broad_match` | `broadMatch` | `BROAD_MATCH = "broad_match"` | **value byte-identical** |
| `related_match` | `relatedMatch` | **no member exists** | **new** |

**There is one vocabulary, not two, and the existing name is retired rather than duplicated.**
`MappingMatchType` is defined once, in `semantic/vocabularies.py` beside the existing enum;
`MatchPredicate = MappingMatchType` is retained as a **deprecated alias**, so every existing
annotation, import and `is` comparison keeps working; and `SemanticMapping.predicate`'s
annotation is updated to `MappingMatchType` (`mappings.py:246`, `:438`) while its *default*
stays for the reason in D1.4.

**Proof obligation, because this touches a persisted CHECK-constrained column.** The four
shared members have byte-identical string values, so no `semantic_mappings.predicate` value
changes and no `content_key()` derived from `str(predicate)` moves. That is checkable and MUST
be checked, not asserted: a test MUST (i) assert the four shared values are unchanged, and
(ii) assert the `content_key()` of a fixed `SemanticMapping` fixture is byte-identical before
and after. If either fails, the alias is withdrawn and `related_match` becomes a separate enum
with a conversion refused at the boundary rather than coerced.

**Direction convention — pinned, because the direction-sensitive pair is otherwise
ambiguous.** For a candidate with `source` S and `target` T:

| `match_type` | The claim |
|---|---|
| `exact_match` | a mapping process asserts S and T denote the same extension. It does **not** license treating them as one, and does **not** license collapsing `schema:Person` into `core:Person` (§9) |
| `close_match` | same extension modulo a **named** difference, recorded in `provenance`. "Close but I did not write down how" is not `close_match`; it is a guess |
| `narrow_match` | S's extension is a **proper subset** of T's — S fires on strictly fewer cases |
| `broad_match` | S's extension is a **proper superset** of T's — S fires on strictly more cases |
| `related_match` | S and T correspond and **neither is comparable to the other by containment** |

"Extension" is used for both layers deliberately: for types it is the set of instances, for
predicates it is the set of realisations/regimes the reading fires on. One definition, two
layers, and the direction convention then means the same thing in each.

**There is no `unmapped` / `no_match` member, and there must not be one.** Absence of a record
*is* the representation of "no mapping". This is forced, not chosen: `US4` Acceptance 1
(`spec.md:195-196`) requires that "a mention surface with no pack entry" yields a retained
`TypeHypothesis` with `hypothesis_state=UNKNOWN`, **not dropped**. A `no_match` record would be
a fifth thing to store, and a `TypeSignal` whose only candidate is `no_match` would be
indistinguishable from a `TypeSignal` that was never mapped. SSSOM 1.3.0 does not have such a
member either.

**Why five and not four, when `MatchPredicate` has four.** `related_match` is required by the
predicate layer, demonstrably, and §20 makes demonstration easy: it forbids mapping by
similarity, so the correct match type for a pair with no containment relation must be
expressible, or the platform must record a false containment. §20 verbatim:

> ```
> owns
> controls
> manages
> ```
>
> → same relation
>
> just because they sound similar.
>
> Only unify when deterministic normalization or explicit semantic mapping establishes that configuration.

There is no "unify" and no "narrower" available for a pair like `controls` ↔
`wikidata:P127` (see **D2.2**): the two sets of cases are *incomparable*, because a 10%
non-controlling stake satisfies one and not the other, and contractual control satisfies the
other and not the one. `narrow_match` would assert a containment that is false;
`close_match` asserts only that a difference exists but leaves it unnamed, which the
definition above forbids. `related_match` is the one member that is true. §64's permission to
diverge "where practical" therefore does not apply: the divergence would be a false claim.

**The consequence on `Concept`, stated precisely.** `MatchPredicate` is
consumed by `Concept.match_predicates()` (`vocabularies.py:267-274`), which iterates
`_MATCH_FIELDS.items()` and projects each predicate onto a *named field on `Concept`*
(`exact_match`, `close_match`, `broad_match`, `narrow_match` — `_LINK_FIELDS`,
`vocabularies.py:177-185`). Adding `RELATED_MATCH = "related_match"` to the enum is therefore
**safe and asymmetric by construction**: no reverse lookup `_MATCH_FIELDS[...]` exists anywhere
(verified by search), so nothing raises, and a `related_match` recorded on a `SemanticMapping`
simply cannot be projected onto a `Concept`. That asymmetry is *correct* and should be
documented rather than closed: a `Concept` declares links the vocabulary itself asserts; a
`MappingSet` records claims a *process* made, and "these correspond and are not comparable" is
a claim a process can make that a vocabulary does not declare. **`Concept` does not gain the
field**, and the asymmetry is stated in `_MATCH_FIELDS`' docstring so the next reader does not
"fix" it.

### D1.3 The dataclass, verbatim

```python
# apps/shared/semantic/vocabularies.py  — ONE vocabulary, defined once (D1.2)
# MatchPredicate = MappingMatchType      — retained as a deprecated alias
# apps/shared/domain/predicate_mapping.py

class MappingMatchType(StrEnum):
    """How a mapping process characterised one cross-vocabulary correspondence.

    SSSOM semantics, in this repository's snake_case dialect. SSSOM-compatible is a claim
    about meaning, not about spelling: the lexical forms are ``exactMatch`` ..
    ``relatedMatch`` upstream and ``exact_match`` .. ``related_match`` here, because every
    other enum in the semantic layer is snake_case and a second dialect would make ``str()``
    comparisons across the layer silently fail.

    Read with the direction pinned, because ``narrow``/``broad`` are meaningless without it.
    For a candidate with ``source`` S and ``target`` T:

    ``exact_match``   a process asserts S and T denote the same extension. It does NOT
                      license treating them as one, and it does NOT license collapsing
                      ``schema:Person`` into ``core:Person``.
    ``close_match``   same extension modulo a NAMED difference, recorded in ``provenance``.
    ``narrow_match``  S's extension is a proper SUBSET of T's - S fires on fewer cases.
    ``broad_match``   S's extension is a proper SUPERSET of T's - S fires on more cases.
    ``related_match`` S and T correspond and neither is comparable to the other by
                      containment. The only member that is true of an incomparable pair.

    "Extension" is the set of instances for a type mapping and the set of realisations a
    reading fires on for a predicate mapping; the same word, the same meaning, both layers.

    There is deliberately no ``unmapped``/``no_match`` member: absence of a record is how
    "no mapping" is represented, and a ``no_match`` record would be indistinguishable from a
    signal that was never mapped.
    """

    EXACT_MATCH = "exact_match"
    CLOSE_MATCH = "close_match"
    NARROW_MATCH = "narrow_match"
    BROAD_MATCH = "broad_match"
    RELATED_MATCH = "related_match"


#: Retained name. Same enum, so every existing annotation, import and ``is`` comparison in
#: ``semantic.vocabularies``, ``semantic.mappings`` and ``semantic.registry`` keeps working.
#: The four shared member values are byte-identical, so ``semantic_mappings.predicate`` values
#: and every ``content_key()`` derived from ``str(predicate)`` are unchanged - which is a
#: test obligation, not a promise (D1.2).
MatchPredicate = MappingMatchType


# apps/shared/domain/predicate_mapping.py
from __future__ import annotations

from dataclasses import dataclass, replace

from semantic.contracts import RelationRef, content_key
from semantic.vocabularies import MappingMatchType, normalize_type_ref


class PredicateMappingError(ValueError):
    """A predicate mapping candidate is not coherent as stated. Carries a stable ``code``."""


@dataclass(frozen=True)
class PredicateMappingCandidate:
    """One proposed mapping FROM a predicate signature TO a reference in some vocabulary.

    A *proposal*, not a record: this is what assembly produces from one observation before
    any MappingSet has accepted it and before the platform has earned a RelationRef for the
    target. It is the predicate-side counterpart of a SemanticMapping's claim - the claim a
    process made - and it is a value object with no lifecycle stage of its own (§103): no
    signal_id, no candidate_id, no row, no transition. It is a field of
    PredicateHypothesis exactly as TemporalHypothesis is a field of RelationCandidate.

    ``source`` is the key the mapping is FROM: a PredicateSignature content key, i.e. the
    identity term, never a surface string. Two candidates for two different signatures may
    name the same ``target``; one signature may carry several candidates against different
    targets. The relation is many-to-many in both directions and is not a function either way.

    ``target`` is a reference in another vocabulary - ``wikidata:P127``,
    ``schema:worksFor`` - and is REQUIRED and non-empty. A local operator with no external
    correspondence has no candidate at all; it is represented by the hypothesis's
    ``relation_ref`` alone, because that is an absence, not a mapping.

    ``target_relation_ref`` is the internal operator, present only when the platform HAS an
    operator for the target. Its absence is the ordinary case for an external property the
    platform has not typed, and it is not an error.

    EVERY field is revision material. None is identity-bearing. See FR-131.
    """

    source: str                                    # PredicateSignature content key, FROM
    target: str                                    # external ref, TO; required, non-empty
    match_type: MappingMatchType                   # REQUIRED, no default - see D1.4
    target_relation_ref: RelationRef | None = None  # internal operator, if one is earned

    confidence: float = 0.0
    provenance: tuple[str, ...] = ()               # canonicalised, de-duplicated, sorted
    mapping_version: str = "1"                     # version of THIS mapping claim; see D2.4
    created_by: str = ""                           # the regime/process that made the claim
    evidence_refs: tuple[str, ...] = ()            # canonicalised, de-duplicated, sorted

    mapping_set_id: str = "predicate-mappings"
    mapping_set_version: str = "1"
    supersedes: tuple[str, ...] = ()               # a correction adds; it never edits
    mapping_candidate_ref: str = ""                # own content address, "" until with_id()

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", str(self.source).strip())
        object.__setattr__(self, "target", normalize_type_ref(self.target))
        object.__setattr__(self, "match_type", MappingMatchType(self.match_type))
        object.__setattr__(self, "mapping_version", str(self.mapping_version).strip())
        object.__setattr__(self, "created_by", str(self.created_by).strip())
        object.__setattr__(self, "mapping_set_id", str(self.mapping_set_id).strip())
        object.__setattr__(self, "mapping_set_version", str(self.mapping_set_version).strip())
        object.__setattr__(self, "mapping_candidate_ref", str(self.mapping_candidate_ref).strip())
        object.__setattr__(self, "provenance", _canonical_refs(self.provenance))
        object.__setattr__(self, "evidence_refs", _canonical_refs(self.evidence_refs))
        object.__setattr__(self, "supersedes", _canonical_refs(self.supersedes))
        if not self.source:
            raise PredicateMappingError(
                "mapping_source_required",
                "a predicate mapping candidate must name the signature it maps FROM; an "
                "unanchored mapping cannot be re-evaluated and must not be offered",
            )
        if not self.target:
            raise PredicateMappingError(
                "mapping_target_required",
                "a predicate mapping candidate must name the reference it maps TO. A local "
                "operator with no external correspondence is the ABSENCE of a mapping and is "
                "represented by PredicateHypothesis.relation_ref alone; recording it as a "
                "mapping would make a non-event look like a record",
            )
        confidence = float(self.confidence)
        if not 0.0 <= confidence <= 1.0:
            raise PredicateMappingError(
                "mapping_confidence_range",
                f"confidence must be within 0.0..1.0, got {confidence}",
            )
        object.__setattr__(self, "confidence", confidence)

    def evaluation_material(self) -> dict[str, object]:
        """Everything needed to recompute this claim independently.

        Exactly the material :meth:`content_key` digests, so a re-evaluation process can be
        handed the claim and reach the same digest rather than trusting a stored id
        (mirrors ``SemanticMapping.evaluation_material``, ``mappings.py:325``).
        """
        return {
            "source": self.source,
            "target": self.target,
            "target_relation_ref": (
                None if self.target_relation_ref is None else str(self.target_relation_ref)
            ),
            "match_type": str(self.match_type),
            "mapping_set_id": self.mapping_set_id,
            "mapping_set_version": self.mapping_set_version,
            "mapping_version": self.mapping_version,
            "created_by": self.created_by,
            "confidence": self.confidence,
            "provenance": list(self.provenance),
            "evidence_refs": list(self.evidence_refs),
            "supersedes": list(self.supersedes),
        }

    def content_key(self) -> str:
        """Order-insensitive digest of the whole claim, for citable addressing only.

        This is NOT logical identity. It never enters ``logical_candidate_id``; it appears
        in ``PredicateHypothesis.content_key()`` and therefore in ``candidate_id`` (the
        revision), which is the whole point. See FR-131.
        """
        return content_key(self.evaluation_material())

    def with_id(self) -> PredicateMappingCandidate:
        """A copy carrying its own content address, or ``self`` if it has one."""
        return (
            replace(self, mapping_candidate_ref=self.content_key())
            if not self.mapping_candidate_ref
            else self
        )

    def to_dict(self) -> dict[str, object]:
        """Lossless form for the ``predicate_mappings`` column.

        A digest MAY identify this data and MUST NOT be the only copy
        (data-model §7; tasks.md T053).
        """
        material = self.evaluation_material()
        material["mapping_candidate_ref"] = self.mapping_candidate_ref
        return material

    @classmethod
    def from_dict(cls, value: object) -> PredicateMappingCandidate:
        """Rebuild exactly. A round trip MUST be lossless or SC-008 is unachievable."""
        if not isinstance(value, dict):
            raise PredicateMappingError(
                "mapping_from_dict", f"expected a mapping, got {type(value).__name__}"
            )
        known = {f for f in cls.__dataclass_fields__}
        unknown = set(value) - known
        if unknown:
            raise PredicateMappingError(
                "mapping_from_dict_unknown_field",
                f"mapping carries fields this type does not declare: {sorted(unknown)}",
            )
        return cls(**value)
```

### D1.4 Two deliberate asymmetries, and why

**1. `match_type` is REQUIRED, with no default.** `SemanticMapping` defaults it:

```python
predicate: MatchPredicate = MatchPredicate.CLOSE_MATCH      # mappings.py:246
predicate: MatchPredicate = MatchPredicate.CLOSE_MATCH      # mappings.py:438
```

A silent `close_match` default is the mirror image of the defect §64 forbids. §64 verbatim:

> Do not silently treat mappings as exact equivalence if they are not.

A default of `close_match` silently treats *unspecified* as *close*, which is a claim nobody
made. `PredicateMappingCandidate` therefore has no default and a positional construction
without one is a `TypeError`.

`SemanticMapping`'s default is **not** changed, because changing it would change
`evaluation_material()` and therefore `content_key()` for every row in `semantic_mappings` and
every id ever minted from one — a silent move of a content-address space, which FR-073 and §92
forbid far more plainly than a wrong default does. Instead: every `SemanticMapping`
constructed on the 021 path MUST pass `predicate` explicitly, and a test asserts that no
`SemanticMapping` in `apps/` is constructed without one. **The defect is recorded, not
inherited silently and not papered over.**

**2. `confidence` defaults to `0.0`, not `1.0`.** `SemanticMapping` defaults to `1.0`
(`mappings.py:256`). A mapping nobody has scored is not maximally confident; it is unscored.
`0.0` is the honest default and it makes "no confidence recorded" visible in a stored row
instead of indistinguishable from "a process asserted this with full conviction".

### D1.5 Which fields are identity-bearing: **none**

| Field | Identity-bearing? | Revision material? | Where it lands |
|---|---|---|---|
| `source` | **No** | Yes (evidence of what was mapped) | `candidate_id` via the hypothesis; it *is* the A2 identity term, but the candidate does not mint it |
| `target` | **No** | Yes | `candidate_id` |
| `match_type` | **No** | Yes | `candidate_id` |
| `target_relation_ref` | **No** | Yes | `candidate_id` |
| `confidence` | **No** | Yes | `candidate_id` |
| `provenance` | **No** | Yes | `candidate_id` |
| `mapping_version` | **No** | Yes | `candidate_id` |
| `created_by` | **No** | Yes | `candidate_id` |
| `evidence_refs` | **No** | Yes | `candidate_id` |
| `mapping_set_id`, `mapping_set_version` | **No** | Yes | `candidate_id` |
| `supersedes` | **No** | Yes | `candidate_id` |
| `mapping_candidate_ref` | **No** | **No** — it *is* the digest of the rest | nothing; it is the address |

The answer is **none**, and it is the answer that has to be right: `target`, `match_type` and
`mapping_version` are the three fields a mapping process is most tempted to put in identity,
because each of them is stable over time and each of them looks like a fact about the world
rather than a claim about a correspondence. All three are claims. All three are revision
material. This is not a new position — it is `SemanticMapping.identity` (`mappings.py:294-309`)
applied to the predicate side, and the code already argues it:

> `mappings.py:296-300`
> Deliberately *not* including source, confidence or provenance: two processes aligning the
> same pair the same way are making the same claim about the same pair, and they are two
> pieces of evidence for it rather than two claims. They are still both stored and both
> retrievable, because identity is not the same thing as what the store holds.

**A note on "identity" having two meanings here**, because the phrase "identity-bearing" is
ambiguous and the ambiguity is the defect. `SemanticMapping.identity` is a *deduplication key
for mapping records*. It is **not** logical candidate identity. FR-131 and FR-136 speak only
about the latter.

---

## D2 — Where `owns` / `controls` / `possesses` now live

### D2.1 The ordering, stated once

```
                surface predicate                      evidence, revision material
   "owns"  "has"  "is the owner of"                    ── revision material ──┐
        │                                                        │            │
        │  A2: N1–N4 (NFKC, casefold, whitespace/punct, voice,        │            │
        │       light delexicalisation) + N6 (argument shape)           │            │
        │  NO synonym table — N5 is deleted (see D8)                     │            │
        ▼                                                                │            │
   PredicateSignature  ────────── content_key() ──────────▶  logical_candidate_id    │
        │                                                          "CAND-…"           │
        │                                                                            │
        │   mapping is a SEPARATE, VERSIONED, PER-CANDIDATE step                       │
        ▼                                                                            │
   PredicateMappingCandidate  (one, or several)                     ── revision material ┘
        │  source = <signature content key>
        │  target = "wikidata:P127" | "schema:owns" | …
        │  match_type, confidence, provenance, mapping_version, created_by, evidence_refs
        ▼
   PredicateHypothesis
        ├── relation_ref              ──▶ RelationRef        (the MAPPING RESULT)
        ├── mapping_candidates        ──▶ tuple[PredicateMappingCandidate, ...]
        ├── alternative_refs          ──▶ DERIVED read-only property
        ├── resolution_state          ──▶ KNOWN | UNKNOWN | AMBIGUOUS | CONFLICTING
        └── mapping_evidence_refs     ──▶ tuple[str, ...]
                                    │
                                    ▼
        candidate_id  "CNDR-…"  (revision)      ← everything in the box above lands here
```

**Two arrows, two directions, and they do not meet.**

```
surface predicate → PredicateSignature → logical candidate identity
PredicateSignature → PredicateMappingCandidate(s) → relation_ref
```

The first arrow is A2's. The second is mine. They share exactly one node —
`PredicateSignature` — and share **no** field. A2's chain never reads a `target`; my chain
never reads a `role_names` or an `arity`. A test must exist that breaks
`PredicateMappingCandidate.target` and asserts `logical_candidate_id` is unchanged, and a
second that breaks the signature and asserts `logical_candidate_id` **does** change.

### D2.2 The worked example

Three surfaces. `owns` and `controls` are both in the §65 known-operator list; **`possesses`
is in neither §65 nor `OntologyPack.relations` nor any corpus in §83**, and that is the point
of including it — the third column is the one that proves the layer is open.

| | A. ownership | B. control | C. possession |
|---|---|---|---|
| surface | `"John owns Acme."` | `"Acme is controlled by John."` | `"John has possession of Acme."` |
| `PredicateSignature.normalized_predicate` | `owns` | `control` | `possess` |
| `logical_candidate_id` | `CAND-α` | `CAND-β` | `CAND-γ` |
| `mapping_candidates` | `(owns → wikidata:P127, exact_match, created_by=regime:ownership, conf=0.9)` | `(controls → wikidata:P127, close_match, created_by=regime:control, conf=0.7)` | `()` |
| `relation_ref` | `RelationRef("owns")` | `RelationRef("controls")` | **`None`** |
| `resolution_state` | `KNOWN` | `KNOWN` | `UNKNOWN` |
| claim materialisable? | yes | yes | **no** |

**The two facts this table is built to make visible.**

1. **Two `PredicateMappingCandidate`s point at `wikidata:P127`, and the two logical candidates
   stay two.** The *target* is shared. The *source* is not. Nothing in the mapping layer
   reads across from target to source, and nothing in the identity layer reads across from
   source to target. `CAND-α ≠ CAND-β` even though both mappings end at the same Wikidata
   property, and `FR-004` / §20 / `US2` Acceptance 3 are satisfied by the table, not by a
   fixture. `SC-007` (`spec.md:885-886`) is discharged by exactly this: "John works_for Acme,
   John founded Acme, John owns Acme produce three logical hypotheses."

2. **The converse also holds, and must be tested.** One `PredicateSignature` can carry two
   candidates against two *different* targets — `corresponds_to` is the live case — with **no
   change to its content key**, therefore no change to `logical_candidate_id`, therefore a new
   `candidate_id` only. The map is many-to-many in both directions and is a function in
   neither. A design in which the target determined the identity would be a design in which
   recognising a relation forked the hypothesis — the exact failure
   `relation_candidate.py:1119-1129` documents and FR-005 exists to prevent.

**Why `controls → wikidata:P127` is `close_match` and not `narrow`/`broad`.** A 10%
non-controlling share satisfies "owned by" and not "controlled by"; contractual control
satisfies "controlled by" and not "owned by". The two case-sets are **incomparable**, so
`narrow_match` and `broad_match` would each assert a containment that is false, and
`exact_match` would assert identity. `close_match` is the weakest true statement, and §20's
rule — "Only unify when deterministic normalization or explicit semantic mapping establishes
that configuration" — forbids the unification that `exact_match` would invite. The
`related_match` question for this specific pair is **D2.5 open question Q1**.

**Column C is the load-bearing one.** `possesses` is not an operator the platform has, so it
maps to nothing, carries no candidate, has `relation_ref=None` and `resolution_state=UNKNOWN`,
and is a **complete, durable hypothesis** — `input.md:3562-3569` and `SC-002`:

> ```
> John is the originator of Acme.
> ```
>
> with:
>
> ```
> relation_ref=None
> ```

It reaches `RelationCandidate` ✅, `ClaimMaterial` ❌, `RelationClaim` ❌, `GraphEdge` ❌
(§50), and every word of it is still retrievable. A mapping layer that could not say "nothing"
would be a gate.

### D2.3 The invariant

> **INV-MAP-1.** `logical_candidate_id` is a function of `(tenant_id, participants, arity
> shape, role shape, directional configuration, polarity, PredicateSignature.content_key())`
> and of **nothing else**. No `PredicateMappingCandidate` field, no `RelationRef`, no
> `resolution_state`, no `alternative_refs`, no `mapping_evidence_refs`, no `match_type`, no
> `confidence`, no `mapping_version`, no `provenance`, no `created_by`, and no external
> vocabulary reference of any kind participates. Changing any of them MUST change
> `candidate_id` and MUST NOT change `logical_candidate_id`.

**Boundary note.** A2 owns the *proof* that `PredicateSignature.content_key()` is stable and
that the identity partition is correct. A4b owns the *interface* — which fields exist on the
mapping side, and what the word "identity" is allowed to mean in them. The two meet at exactly
one sentence, and both must be able to state it without appealing to the other.

This invariant is already argued in the code, and quoting it is stronger than restating it:

> `relation_candidate.py:1119-1126`
> The predicate goes in as :attr:`relation_surface` rather than as the resolved
> operator type, and that choice is the whole of CD-6 at this level. *Which hypothesis
> this is* is settled by what the observation said, and not by what the vocabulary
> could make of it: keying on the resolved type would give "originator of" a different
> logical id the moment a regime recognised it, splitting one hypothesis into two and
> losing the record that they were ever the same claim.

> `relation_candidate.py:1151-1157`
> The predicate enters the same way, and for a sharper reason: it belongs to the
> revision rather than the logical key because a later ``SemanticRegime`` may resolve the
> *same* surface form to a different operator. That is a new reading of one hypothesis,
> not a new hypothesis — and if the predicate sat in the logical material, resolving it
> would silently mint a second candidate for one relation.

**And the one place in the code where it is violated today.** `relation_candidate.py:691`:

```python
surface_form=self.relation_surface
or ("" if self.relation_ref is None else str(self.relation_ref.relation_type)),
```

When a candidate is constructed with `predicate_hypothesis=None`, the surface is **derived
from the mapping target**. So a candidate with no surface is keyed on the resolved type —
which the docstring at `:1128-1129` admits is "keying on the type as before" and calls
harmless. It is not harmless, and it is the last code path that can fork a hypothesis by
recognising it:

> `relation_candidate.py:1128-1129`
> For a candidate that supplies no surface, the surface was derived from the ref, so
> this is keying on the type as before and no existing identity moves.

"No existing identity moves" is true only because nothing yet produces a surface-less
candidate. The moment a producer emits one, every future mapping change moves its
`logical_candidate_id`. **This fallback MUST be deleted** and replaced with the A2 signature;
a candidate with no signature is a candidate with no identity term, which is the honest state
and the §90 case. See **D8.5**.

### D2.4 `mapping_version` semantics — three version axes that must not collapse

The word "version" appears in five places in this stack and they answer five different
questions. Collapsing any two of them is a defect.

| Axis | Field | Question it answers | May it move `logical_candidate_id`? | Owner |
|---|---|---|---|---|
| 1 | `PredicateSignature.schema_version` | which version of the **normaliser** produced this signature | **Yes, deliberately** — it is one of the few permitted moves, and it must be a recorded, replay-visible change | A2 |
| 2 | `RelationRef.schema_version` | which version of the **operator** was in force | **No.** Not in the identity material | A2's exclusion; A4b's persistence |
| 3 | `PredicateMappingCandidate.mapping_version` | which iteration of **this mapping claim** | **No.** Not in the identity material | **A4b** |
| 4 | `mapping_set_id` + `mapping_set_version` | which **alignment effort** asserted it | **No.** Not in the identity material | **A4b** |
| 5 | `mapping_candidate_ref` | what is this claim's **content address** | **No.** It is the digest of the rest | **A4b** |

**The rule for axis 3, which is mine:**

> A change to `mapping_version` is a **revision**, never an amendment. The prior candidate is
> not edited and not deleted; it is superseded by a new `PredicateMappingCandidate` naming it
> in `supersedes`, exactly as `SemanticMapping.supersedes` works (`mappings.py:263`,
> `mappings.py:390-396`). Both stay readable.

**And the distinction that is easy to get wrong** — revision material is not the same as
revision-*only* material:

| | Where a superseded candidate goes |
|---|---|
| `relation_surface` | stays in the row forever, as evidence, **and** in every later `candidate_id`'s material |
| a **live competing reading** | in `PredicateHypothesis.mapping_candidates` — the *live* set |
| a **superseded** mapping candidate | **out of the live set**, into the revision history, reachable through `mapping_evidence_refs` → its `mapping_candidate_ref` |

So a *correction* must not leave the corrected candidate sitting in `mapping_candidates`,
because that would make `AMBIGUOUS` permanent and unresolvable by evidence. A correction is a
revision, not an ambiguity. This is FR-037's rule ("A later `INFERRED` status MUST be a new
revision, not a destructive replacement", §10) applied one level down, and it is the reason
`supersedes` exists on the type at all.

**Why `mapping_version` is not identity even though it looks like identity.** It is stable
over time, which is the property people mistake for identity. It is a counter maintained by a
process, and the process is a semantic regime, which is a *fallible* component. Putting a
fallible process's counter into a content key is the N5 defect one level down: it makes
identity depend on an artefact of interpretation rather than on structure. The same argument
`data-model.md` lines 53-56 makes for the synonym table applies verbatim here — and note that
that paragraph's *reasoning* is sound even though its *conclusion* is wrong. The reasoning
moves; the conclusion lands in a different layer.

### D2.5 Open question Q1 — `related_match` for incomparable pairs

**The question.** §20 forbids mapping by similarity, and the vocabulary offers five match
types. For an incomparable pair such as `controls` ↔ `wikidata:P127`, only `related_match` is
exactly true; `close_match` is weaker but true. Does the platform record the exactly-true
answer, admitting a fifth member to `MatchPredicate` and a field-less `Concept`, or the
weaker-but-portable one?

**What is decided provisionally, and why.** Record the exactly-true answer.
`related_match` is a member of SSSOM 1.3.0, "SSSOM-compatible semantics apply" (FR-036), and
choosing a *less* precise vocabulary in order to avoid a field on `Concept` is precisely the
"silently treat mappings as exact" failure of §64 with the sign flipped: it silently treats
mappings as comparable when they are not.

**Stop condition.** If the review concludes that `MatchPredicate` must not gain a member
because `Concept.match_predicates()` cannot project it, then `related_match` MUST NOT be
coerced to `close_match` on the way to a `MappingCitation` — a coercion is a silent rewrite
of a recorded claim. In that case the platform MUST record no candidate at all for an
incomparable pair and report the situation through `FR-082`'s stop path, and the coercion
prohibition becomes a named mutation. **Do not let this be discovered during implementation.**

---

## D3 — `AMBIGUOUS` and `CONFLICTING` as ONE hypothesis

### D3.1 What is being corrected

Three separate statements in the current artefacts are wrong or unimplemented:

1. `data-model.md:57` — "`AMBIGUOUS`" = two signatures. **Wrong** (phase0 **E5**).
2. `data-model.md:177` — "`alternative_refs` | competing mappings, **each with evidence**".
   **Unimplemented**: `alternative_refs: tuple[RelationRef, ...]` (`predicate_hypothesis.py:141`)
   is a tuple of bare refs with no per-alternative evidence, and `mapping_evidence_refs`
   (`:143`) is a flat set of strings that cannot say *which* alternative it justifies.
3. `data-model.md:179` — "`mapping_evidence_refs` | why the mapping was made". **Not
   persisted**: there is no `predicate_alternatives` and no `predicate_mapping_evidence`
   column on either table (verified against `db/schema.py:2293-2294`, `:2388-2389` and
   migration `020`: only `predicate_hypothesis String(64)` and `predicate_state String(16)`
   exist), so `PredicateHypothesis` survives only as a digest — which `data-model.md:186-189`
   itself calls out.

### D3.2 `PredicateHypothesis`, carrying alternatives

One new stored structure. `relation_ref` stays the stored primary (so no call site changes);
`mapping_candidates` becomes the stored full set; `alternative_refs` becomes a **derived
read-only property**. Two stored parallel lists would be two sources of truth, which is the
defect `OntologyPack.relations` (D6) and the `OntologyPack`/`OntologyPack(Base)` name
collision already are.

```python
@dataclass(frozen=True)
class PredicateHypothesis:
    surface_form: str = ""
    normalized_form: str = ""
    relation_ref: RelationRef | None = None                        # the PRIMARY mapping result
    mapping_candidates: tuple[PredicateMappingCandidate, ...] = ()  # NEW: the full set
    resolution_state: PredicateResolutionState | None = None
    mapping_evidence_refs: tuple[str, ...] = ()

    # ---- derived, read-only; no setter, no stored duplicate ----

    @property
    def alternative_refs(self) -> tuple[RelationRef, ...]:
        """Every live competing target, canonicalised, primary excluded.

        Derived from ``mapping_candidates`` so the set of alternatives and the set of
        candidates can never disagree. Order is by ``str(ref)``; collection order is not
        semantic and MUST NOT reach any digest (§108 Determinism: "order of producers does
        not alter IDs").
        """
        out = {
            c.target_relation_ref
            for c in self.mapping_candidates
            if c.target_relation_ref is not None and c.target_relation_ref != self.relation_ref
        }
        return tuple(sorted(out, key=str))
```

`alternative_refs` keeps its name so FR-021's field list stays true, keeps its element type so
every existing call site (`predicate_hypothesis.py:241`, `relation_candidate.py:701`,
`signal.py:390`, the unit tests) keeps compiling, and stops being a bare-ref tuple. **FR-021's
requirement that the field be *preserved* is met by preserving the name and the read; the FR
does not fix the element type, and the change is a widening, not a redefinition.**

`__post_init__` gains three checks, all of which are the *same* checks the code already makes,
now over the richer set:

| Check | Code | Why |
|---|---|---|
| canonicalise | `mapping_candidates` sorted by `(source, str(target_relation_ref or ""), str(match_type), mapping_set_id, mapping_version, created_by, content_key())`, de-duplicated by `content_key()` | the current `dict.fromkeys` on `alternative_refs` (`:158-166`) preserves **declaration order**, and `content_key()` (`:280`) hashes it in that order — so two assemblies collecting the same two competing readings in opposite producer order produce different `PredicateHypothesis.content_key()` values and therefore **different `candidate_id`s for the same evidence**. That violates FR-073 and §108's "order of producers does not alter IDs", and it is a defect in the mapping layer, so it is mine. |
| `mapping_ref_not_a_candidate` | `relation_ref` MUST equal the `target_relation_ref` of at least one candidate, and MUST NOT be a bare `RelationRef` with no candidate behind it when any candidate carries a target | replaces today's `predicate_ref_in_alternatives` (`:178-183`), which is the same check expressed over bare refs |
| `mapping_match_disagreement_kept` | two candidates with the same `(source, target)` and different `match_type` are **legal** and MUST both be kept | two processes disagreeing about how two things correspond is data, not an error — `MappingRegistry.conflicts()` exists for exactly this (`mappings.py:1032`) |

### D3.3 `resolution_state` in each case

| `resolution_state` | `relation_ref` | live candidates | what it means | claim materialisable |
|---|---|---|---|---|
| `UNKNOWN` | `None` | 0 (or candidates with `target_relation_ref=None`) | nobody has named this relation. Structure known, mapping unknown. This is the §90 case and the **norm** (data-model §4: "`relation_ref=None` with a full signature is legal and is the norm") | **no** |
| `KNOWN` | present | 1 distinct target | one operator, no competitor | yes |
| `AMBIGUOUS` | present (designated, **not a winner**) | ≥ 2 distinct targets, agreeing evidence | two **regimes** were each offered the same observation and returned different operators. The observations do not disagree; the interpreters do (§83: "Same surface mapped by two semantic regimes/operators") | **no** |
| `CONFLICTING` | present (designated, **not a winner**) | ≥ 2 distinct targets, **disagreeing evidence** | the **observations** contradict each other over the same participant structure (§83: "Two incompatible signals over same participant structure") | **no** |

**The discriminator is which layer the disagreement lives in, and it is read off the
*evidence*, never off the outcome.** No count, no confidence, no insertion order, no
alphabetical tie-break (FR-026, §45). The evidence is named in
`mapping_evidence_refs` → each `PredicateMappingCandidate.evidence_refs` → the `signal_id`s
that produced it, which is what makes "which evidence produced which reading" answerable
after the fact.

**The primary is a designation, not a decision, and the claim boundary is what makes that
safe.** This is the single most important sentence in D3:

> An `AMBIGUOUS` or `CONFLICTING` hypothesis MUST NOT yield `RelationClaimMaterial`.
> Neither interpretation is overwritten, neither is dropped, **and neither becomes a claim.**

§50 is the authority:

> ```
> RelationCandidate ✅
> ClaimMaterial      ❌ until resolved
> RelationClaim      ❌
> GraphEdge          ❌
> ```
>
> This is intentional.

Without that rule, "neither overwritten" is a promise about storage while `relation_ref` still
quietly decides the edge type, and the promise is false. With it, the primary exists only so
that `is_resolved`, the projection layer and the storage layer have something to read, and it
is refused everywhere it could decide anything. **The `relation_ref` field is therefore a
*ranking* default and MUST be documented as such**, because a reader who sees
`relation_ref="ownership"` beside `state=AMBIGUOUS` will otherwise conclude ownership won.

Today `RelationClaimMaterial` checks `if not self.relation_type:` (`relation_claim_material.py:360`)
and is fed `candidate.relation_type` at `:734`. `candidate.relation_type` returns the
`relation_ref` whenever there is one (`relation_candidate.py:847`) — so an `AMBIGUOUS`
hypothesis with a primary **would today produce claim material and an edge**. This is not a
theoretical risk; it is the current code path, and it is the concrete form of "two candidates
destroys the uncertainty" arriving through the back door. See **D4.2** and **D8.6**.

### D3.4 How assembly produces `AMBIGUOUS` from two producers that agree on surface and map differently

`input.md:2394-2418` is the authority, verbatim and in full:

> ```
> # 49. PREDICATE ALTERNATIVES
>
> Example:
>
> ```text
> signal A:
> surface = CEO of
> relation_ref = employment
>
> signal B:
> surface = CEO of
> relation_ref = organizational_role
> ```
>
> should be representable as:
>
> ```text
> PredicateHypothesis:
>     surface = CEO of
>     primary = ...
>     alternatives = [...]
>     state = AMBIGUOUS
> ```
>
> without overwriting either interpretation.
>
> If evidence genuinely disagrees:
>
> ```text
> state = CONFLICTING
> ```
>
> and preserve both.
> ```

**Note what §49's shape requires and what the code has.** §49's `alternatives` is a list of
*readings*, each with its own provenance, and the module docstring
(`predicate_hypothesis.py:30-31`) describes the same:

> ```text
> ambiguous   "associated with"            → ref = ownership, alternatives = 2 more
> conflicting signal A → ownership, signal B → control
> ```

Step by step:

| # | Step | Rule | Must not |
|---|---|---|---|
| 1 | group | both signals land in one logical candidate, because the **signatures agree** (A2's normalisation is deterministic and `CEO of` is one normalised predicate in both readings) | open two candidates |
| 2 | emit | signal A yields `PredicateMappingCandidate(source=<sig key>, target="semantic:employment", target_relation_ref=RelationRef("employment"), match_type=EXACT_MATCH, created_by="regime:employment", evidence_refs=("SIG-a1",))` | — |
| 3 | emit | signal B yields the same with `target="semantic:organizational_role"`, `RelationRef("organizational_role")`, `created_by="regime:org"`, `evidence_refs=("SIG-b1",)` | — |
| 4 | merge | `mapping_candidates` is the **union**, canonically ordered, **de-duplicated by `content_key()` only** | de-duplicate by `target` — two processes asserting the same target is corroboration, and `SemanticMapping.identity` (`mappings.py:294-309`) already argues exactly that; de-duplicating by target would discard the second process's evidence |
| 5 | designate | `relation_ref` = the candidate of the **regime with the highest `confidence`**, ties broken by `str(target)` for determinism | treat the designation as a decision. It is a ranking default; step 6 is what makes that safe |
| 6 | state | `resolution_state = AMBIGUOUS` because the **evidence agrees** (both signals attest the same surface and the same participant structure) while the **targets differ** | `KNOWN` because a primary exists; `CONFLICTING` because the targets differ |
| 7 | evidence | `mapping_evidence_refs = ("SIG-a1", "SIG-b1")` plus each candidate's own `mapping_candidate_ref` | store one flat list that cannot say which reading it supports |
| 8 | claim | `RelationClaimMaterial` **refuses**, citing `resolution_state ∈ {AMBIGUOUS, CONFLICTING}` | build material from `relation_ref` alone |

**And the same trace for `CONFLICTING`**, which differs in exactly one input:

| # | Step | `AMBIGUOUS` | `CONFLICTING` |
|---|---|---|---|
| 1 | group | one logical candidate | one logical candidate **if the signatures agree**; see below |
| 2 | what differs | only the **mapping**: two regimes, one evidence set | the **evidence**: the signals themselves assert incompatible things |
| 3 | concrete | A: `surface="CEO of"`, `relation_ref=employment`. B: `surface="CEO of"`, `relation_ref=organizational_role` | A: `surface="Acme is controlled by John"`, `relation_ref=controls`. B: `surface="John is not affiliated with Acme"`, `polarity=denied`, `relation_ref=affiliated` — over the **same two mentions** |
| 4 | state | `AMBIGUOUS` | `CONFLICTING`, via the existing and correct `with_conflict()` (`predicate_hypothesis.py:250-262`) |
| 5 | both preserved | yes — `mapping_candidates` holds both | yes — same, plus `mapping_evidence_refs` naming the `signal_id` on **each side** so a reader reconstructing why a hypothesis stalled can tell them apart (the existing `with_conflict` docstring already says this) |
| 6 | claim | refused | refused |

**Where the boundary runs, and it is not mine to draw.** If the two signals do not merely
*map* differently but assert **incompatible participant structures** over the same mention set
— arity 2 vs 3, `subject_to_object` vs `object_to_subject`, `asserted` vs `denied`, a mention
in two different slots — then the disagreement is **identity-bearing**, no single signature
describes both, and one logical hypothesis would be a lie. That case is `FR-090`'s
`CandidateStatus.CONTRADICTED` with both readings preserved, at the candidate layer, and it
belongs to A2. FR-028's "genuine disagreement yields `CONFLICTING` with both preserved" is
therefore read as: **`CONFLICTING` on the hypothesis records that the candidate's mapping was
reached from signals that contradict each other**; where the contradiction is structural, the
two *candidates* are contradictory instead and the hypothesis-level `CONFLICTING` is not
reached at all. Both readings are preserved either way. **A2 must state this split explicitly
so the two documents agree on which case produces which artefact.**

### D3.5 The `_resolve_state` asymmetry: does it survive?

**Yes — all of it — and it is the correct model. Three amendments are required, and one gap is
named rather than closed.**

The current rule, verbatim (`predicate_hypothesis.py:296-323`):

> ```python
> def _resolve_state(
>     stated: PredicateResolutionState | str | None,
>     relation_ref: RelationRef | None,
>     alternative_refs: tuple[RelationRef, ...],
> ) -> PredicateResolutionState:
>     """Derive the resolution state, honouring an explicit ``CONFLICTING`` and nothing else.
>     ...
>     """
>     if (
>         stated is not None
>         and PredicateResolutionState(stated) is PredicateResolutionState.CONFLICTING
>     ):
>         return PredicateResolutionState.CONFLICTING
>     if relation_ref is None:
>         return PredicateResolutionState.UNKNOWN
>     if alternative_refs:
>         return PredicateResolutionState.AMBIGUOUS
>     return PredicateResolutionState.KNOWN
> ```

**Amendment 1 — derive from the candidate set, not from a parallel ref tuple.** The signature
becomes `(stated, relation_ref, mapping_candidates)` and the last three branches read the
derived `alternative_refs`. Same three answers, one source of truth. No behavioural change.

**Amendment 2 — the overwrite stays, and here is the justification that does not rest on
preference.** A caller-stated `KNOWN` beside two alternatives is a *contradiction*, and the
refs are the evidence that resolves it. Deriving rather than demanding is what makes the
invariant **checkable from the type** rather than from a reviewer's reading: a hypothesis that
says `KNOWN` while carrying two targets cannot be constructed. The alternative — trusting the
stated value — makes the label an assertion the type cannot refute, and the platform has
already committed to the opposite principle at `relation_candidate.py:405-411`:

> ```python
> if self.signal_id and self.signal_id != derived:
>     raise SignalContractError(
>         "signal_id_mismatch",
>         f"signal carries {self.signal_id!r} but its own content addresses to "
>         f"{derived!r}; a content address is derived, never trusted",
>     )
> ```

"Derived, never trusted" is the house rule. The asymmetry is that rule applied to a field the
type *can* check.

**Amendment 3 — an explicit `CONFLICTING` is honoured, and this is the one piece of the
asymmetry that cannot be derived.** The docstring already gives the reason, and it is correct:
`CONFLICTING` records something the refs *cannot* — that the competing readings came from
**disagreeing observations** rather than from one observation with several defensible names.
Overwriting it would discard the only trace of the disagreement. Keep it, and keep it
**explicit**: an inferred `CONFLICTING` is forbidden, because "these two disagree" is a claim
about evidence that only the assembler can make.

**`UNKNOWN` + a non-`None` `relation_ref` stays refused. Do not relax it.** The code's reason
(`predicate_hypothesis.py:190-199`):

> ```python
> if (
>     self.resolution_state is PredicateResolutionState.UNKNOWN
>     and self.relation_ref is not None
> ):
>     raise PredicateContractError(
>         "predicate_unknown_with_ref",
>         f"resolution_state=unknown means nothing was resolved, but "
>         f"{self.relation_ref!r} is a resolved operator type; use ambiguous or "
>         "conflicting if the platform has candidates",
>     )
> ```

The refusal is load-bearing for the whole feature, and the reason is that `relation_ref=None`
must mean **unknown** rather than **unspecified**. The feature's single most important state
is "structure known, mapping unknown" (`data-model.md:181-184`, §21, §67). That state is
*only* distinguishable from "we did not bother to record a mapping" if the platform has no
way to write `UNKNOWN` next to a ref. Relax the refusal and `UNKNOWN` becomes ambiguous
between the two, and §90's unknown test (`SC-002`) becomes unassertable. It is also the
refusal that makes §98's mutation — `if relation_ref is None: return ()` — detectable at all.

**And one dead branch, which must be deleted or the decision is incoherent.**
`with_alternatives` (`predicate_hypothesis.py:241-248`):

> ```python
> state = self.resolution_state
> if state is PredicateResolutionState.UNKNOWN and self.relation_ref is not None:
>     state = PredicateResolutionState.AMBIGUOUS
> ```

Its own docstring claims:

> The promotion is the point: a signal set that first knew nothing and then
> accumulated a second reading is ``ambiguous``, not ``unknown``.

**The promotion can never fire.** `resolution_state is UNKNOWN` implies `relation_ref is None`
— that is precisely what `_resolve_state` returns, and `predicate_unknown_with_ref` then
*refuses* the combination. So `state is UNKNOWN and self.relation_ref is not None` is
unsatisfiable, the branch is dead, and a method whose documented purpose is a promotion that
cannot happen is worse than a method without the claim. Either delete the branch and the
claim, or implement the promotion the docstring describes. **Recommendation: delete both**,
because the promotion it describes is a *claim-path* transition and the claim path is
**refused** for `AMBIGUOUS` (D3.3) — promoting a `None`-ref hypothesis to `AMBIGUOUS` would
manufacture a primary out of nothing, which is the registry-sentinel mistake
`predicate_hypothesis.py:8-13` exists to prevent.

**The named gap — a primary-less multi-alternative hypothesis. Open question Q2.**

`PredicateHypothesis(surface_form="associated with").with_alternatives(RelationRef("ownership"), RelationRef("control"))`
constructs successfully today with `resolution_state=UNKNOWN`, `relation_ref=None`, and two
alternatives. Neither FR-028 nor §49 covers this: §49's example always has a `primary = ...`,
and the module docstring's `ambiguous` line also always has a ref. The state space has a
fourth point the four names do not cover.

| Option | Consequence |
|---|---|
| (a) leave it `UNKNOWN` | **contained**: `relation_ref=None` ⇒ `is_resolved` is False ⇒ the claim boundary already refuses it. Nothing unsafe happens. But the record is *misnamed* — a reader sees `UNKNOWN` on a hypothesis carrying two mappings, which is the same class of lie as the one FR-028 was written to kill |
| (b) promote to `AMBIGUOUS` when ≥ 2 targets exist even with no primary | makes the name honest, but requires relaxing `predicate_resolution_without_ref` (`predicate_hypothesis.py:184-189`), which is the check that makes `relation_ref` mean "a resolution exists". That check is doing real work |

**Decision: do not decide here.** Option (a) is chosen as the **containment** — no new
artefact, no relaxation, and the misnaming is recorded as a known limitation rather than fixed
by weakening a check whose value was just argued above. Option (b) is a real candidate and it
is **not mine to take**, because relaxing `predicate_resolution_without_ref` is a change to
what "resolved" means, which is a `PredicateHypothesis` contract question that A2 and the spec
owner share.

**Stop condition.** If the §83 *Ambiguous* corpus case is implemented as "two regimes, no
designated primary", option (a) produces a golden-corpus row whose name contradicts its state
and the test is unsatisfiable. At that point the work **stops** and reports the gap rather than
weakening `predicate_resolution_without_ref`. The corpus case must therefore be built with a
designated primary (per §49's own example, which has one), and the no-primary variant, if
wanted, is a separate recorded decision.

---

## D4 — `relation_ref` status

### D4.1 It is a mapping result, not identity

> **`relation_ref` is the output of the mapping step and the input to nothing on the identity
> side.** It is stored on `RelationCandidate` as revision material, it is hashed into
> `candidate_id`, and it MUST NOT appear in `logical_candidate_id`.

The code already holds this position and argues it in two places, quoted in D2.3. What the
code does **not** do is make the distinction *visible in the type*, which is the decision
below.

**Where `relation_ref` legitimately appears, and where it must not:**

| Position | Legal? | Reason |
|---|---|---|
| `RelationCandidate.relation_ref` | yes | it is a *field*, i.e. revision material — same class as `relation_surface` |
| `PredicateHypothesis.relation_ref` | yes | same |
| `logical_candidate_id` material | **no** | FR-005, FR-007, and the two code comments above |
| `RelationSignal._material()` | **no** | a signal is an observation, not a resolution; §14/§59 have the signal carry the *signature* |
| `RelationClaimMaterial.relation_type` | **only if** `resolution_state is KNOWN` | §50 and D3.3 — an `AMBIGUOUS`/`CONFLICTING` hypothesis must not become a claim |
| any `GraphEdge` | **only via a claim** | §51, FR-058 |

### D4.2 What must change in `RelationCandidate.relation_type` (`relation_candidate.py:838`)

Current property, verbatim:

> ```python
> @property
> def relation_type(self) -> str:
>     """The operator's relation type, read off the reference rather than restated.
>
>     Empty for an unresolved predicate, and empty is the honest answer: no operator was
>     named, so there is no type to report. Callers that need to know *why* it is empty
>     should read :attr:`predicate_hypothesis`, which distinguishes a surface nobody has
>     typed from a reading with several defensible types.
>     """
>     return "" if self.relation_ref is None else self.relation_ref.relation_type
> ```

**Two defects, one naming and one behavioural.**

**(1) The name claims to be a type of the relation; it is a property of a mapping.** A reader
who writes `candidate.relation_type == "works_for"` concludes the relation *is* a works_for.
That is §104's forbidden move — "all relations fit a finite global edge list" — re-entering from
the read side, through a field whose name promises exactly the ontology authority §2 forbids.
The field does not have domain/range (correct) but its **name** supplies the authority the
type withholds.

**Required**: rename to **`mapped_relation_type`**, and keep `relation_type` as a
deprecated-alias property delegating to it, so no call site breaks and no id moves. The
docstring MUST say it is *the operator this candidate was mapped to*, and MUST say that
`""`/absent is not "the relation has no type" but "no mapping has been made".

**(2) The empty string is doing three jobs and is indistinguishable across all of them.**

| `relation_type` today | what it actually means |
|---|---|
| `""` | no operator named — `UNKNOWN` |
| `""` | several defensible operators, none chosen — `AMBIGUOUS`/`CONFLICTING` (because the primary *is* returned when present, this case returns the primary, which is worse: see below) |
| `""` | `RelationRef("")` — **constructible and indistinguishable**, because `RelationRef.__post_init__` does `str(...)` and refuses nothing, so `RelationRef("").relation_type == ""` and `RelationRef(None)` is equally reachable |

And the sharpest problem is the third row of the *table* in D3.3: because the property returns
the primary whenever one exists, an **`AMBIGUOUS`** candidate reports a single confident type.
`relation_claim_material.py:734` (`relation_type=candidate.relation_type`) and `:360`
(`if not self.relation_type:`) then admit it. **Today, an ambiguous predicate produces a claim
and an edge, and nothing in the type says so.** The claim boundary must read
`resolution_state`, not the emptiness of a string.

**Required**, in the smallest coherent change:

| # | Change | Note |
|---|---|---|
| a | add `mapped_relation_type` (the renamed property) | name only; no behaviour change |
| b | keep `relation_type` delegating to it, marked deprecated | no call site changes; no id moves |
| c | add `mapped_operator_refs: tuple[RelationRef, ...]` — primary first, then `alternative_refs` — so a reader who *wants* the full reading set has one call | makes `AMBIGUOUS` visible in the type rather than only in a sibling object |
| d | `RelationClaimMaterial` MUST gate on `predicate_hypothesis.resolution_state is KNOWN` and MUST cite the state in its refusal message | the actual fix; see D8.6 |
| e | `RelationRef.__post_init__` MUST refuse an empty `relation_type` (`PredicateContractError("relation_ref_type_empty", …)`) | removes the third row of the table above. Additive refusal on an existing type; `RelationRef("")` has no non-test caller |

Deliberately **not** changed: the return type. `mapped_relation_type` stays `str` and keeps
returning `""` for the unmapped case, because `relation_claim_material.py:360` and
`relation_identity.py:410` both key on falsiness and widening the type would touch the identity
module — which is A2's, not mine. The distinction is carried by (d), not by the return type.

### D4.3 Does `RelationRef` keep its no-domain/no-range disclaimer?

**Yes. It keeps the disclaimer verbatim and gains no field.** The current text, quoted in full
because it is load-bearing and correct:

> ```python
> class RelationRef:
>     """A reference to a relation *operator*, never to a fixed relation ontology.
>
>     The operator identity is ``(relation_type, schema_version)`` and that pair is
>     all this type carries. There is deliberately no ``domain``, ``range`` or
>     ``allowed_types`` field here: those are the operator's *contract* (bound in
>     ``semantic.operators`` to the existing feature 016 ``RelationSchema``), and
>     putting them on the reference would let a relation look well-typed before any
>     contract was ever declared for it (FR-006).
>     """
> ```

Three reasons, in order of force.

1. **The contract already exists and already binds roles.** `semantic.operators` /
   `domain/relation_schema.py` enforce it — `relation_schema.py:252` ("directed relation
   `{…}` takes no role bindings"), `:266` ("role(s) `{…}` more than once"), `:300` (a schema
   with no `relation_type` is refused). A second copy on the ref would be a second source of
   truth for the same contract, which is the defect `OntologyPack.relations` is (D6) and the
   `OntologyPack` / `OntologyPack(Base)` duplicate-class-name defect already is.
2. **Widening `RelationRef` moves a content-address space.** `identity` is
   `(relation_type, schema_version)`; `str(relation_ref)` is hashed into
   `PredicateHypothesis.content_key()` (`predicate_hypothesis.py:279`). Adding a field changes
   `__str__`? No — but it changes the type's contract and invites a later `__str__` change, and
   every id derived from a hypothesis would move silently. FR-073/§92 forbid that.
3. **The hint is required somewhere, and the mapping layer is already the right place.**
   §65 states the relation registry's purpose as "semantic interpretation / validation
   contract / role hints / blocking / projection contract". "Role hints" belongs to the
   **registry**, i.e. `RelationSchema`. And §2's "a role/domain/range hint" is, on the mapping
   side, already carried by `MappingMatchType`: `narrow_match`/`broad_match` **are** the
   domain/range relation between the signature and the target operator, expressed once,
   direction-pinned, and citable. Adding `domain=`/`range=` to `RelationRef` would express the
   same fact in a second, un-pinnable dialect.

**One documentation change, and it is a real gap.** The `RelationRef` docstring says the
contract is "bound in ``semantic.operators``" and does not name the type, so a reader looking
for the hint cannot find it — and `relation_schema.py` is a 300-line file with no pointer back.
**Required**: append one sentence to the `RelationRef` docstring naming
`domain.relation_schema.RelationSchema` as where domain/range/role bindings live, and append
one sentence to `RelationSchema` pointing at `MappingMatchType` for the *mapping* direction of
the same relation. No code change. Two sentences, and the hint becomes findable without a
second source of truth.

---

## D5 — `TypeSignal` and `TypeMapping` (the orphan FRs FR-035 / FR-036)

### D5.1 `TypeMapping` is `SemanticMapping`. It must not be a new dataclass.

FR-036 requires (verbatim, `spec.md:524-527`):

> - **FR-036**: A type mapping MUST retain subject type, object type, mapping predicate,
>   mapping set, mapping version, confidence, creator/operator and evidence/provenance, and MUST
>   NOT collapse `schema:Person` into `core:Person` without a mapping record. SSSOM-compatible
>   semantics apply, and a non-equivalence match MUST be recordable as such. (§9, §64)

And §9 requires (verbatim, `input.md:772-783`):

> ```text
> subject_type
> object_type
> mapping_predicate
> mapping_set
> mapping_version
> confidence
> creator/operator
> evidence/provenance
> ```

**Field-by-field, the requirement is already satisfied:**

| §9 requirement | `SemanticMapping` field | Line |
|---|---|---|
| `subject_type` | `subject_ref` (+ `subject_scheme`) | `mappings.py:244`, `:260` |
| `object_type` | `object_ref` (+ `object_scheme`) | `mappings.py:245`, `:261` |
| `mapping_predicate` | `predicate: MatchPredicate` | `mappings.py:246` |
| `mapping_set` | `mapping_set_id` + `mapping_set_version` | `mappings.py:248-249` |
| `mapping_version` | `mapping_version` | `mappings.py:252` |
| `confidence` | `confidence` | `mappings.py:256` |
| `creator/operator` | `mapping_source` (+ `justification`) | `mappings.py:251`, `:253` |
| `evidence/provenance` | `provenance` | `mappings.py:254` |

Eight for eight. `SemanticMapping` is persisted (`SemanticMappingRow`, `db/schema.py:1477`,
migration `018`), it is content-addressed (`content_key()`, `mappings.py:350`), it is
re-evaluable (`evaluation_material()`, `:325`), it is citable (`cite()`, `:369`), it
supersedes rather than edits (`supersedes`, `:263`), and it surfaces conflicts rather than
resolving them (`conflicts_with()`, `:398`; `MappingRegistry.conflicts()`, `:1032`).

**Decision.** `TypeMapping` is **documented as the brief's name for `SemanticMapping`** —
a documented alias plus a crosswalk table in `data-model.md`, not a new type and not a new
field. FR-036 needs a **task and a test**, not a dataclass. A new `TypeMapping` would create
two mapping record types with identical semantics, no way to tell them apart in
`semantic_mappings`, and no way to enforce "MUST NOT collapse `schema:Person` into
`core:Person` without a mapping record" across both.

**The one real gap in `SemanticMapping` against FR-036**, and it is one line:

> `related_match` cannot be recorded, because `MatchPredicate` has no such member
> (`vocabularies.py`: `EXACT_MATCH`, `CLOSE_MATCH`, `BROAD_MATCH`, `NARROW_MATCH` only).

FR-036 says "a non-equivalence match MUST be recordable as such". The three non-equivalence
members are recordable; the fourth SSSOM non-equivalence member is not. Add
`RELATED_MATCH = "related_match"` — see D1.2 for why this is safe and why the resulting
asymmetry with `Concept` is correct rather than a gap.

**And the one real defect**, which is *not* a gap but a hazard, already stated in D1.4:
`predicate: MatchPredicate = MatchPredicate.CLOSE_MATCH` (`mappings.py:246`, `:438`). For
`TypeMapping` this means a mapping can be recorded with an invented match type. §64 forbids
exactly that. Fix = pass it explicitly on the 021 path + a test, **not** a default change,
because a default change moves `content_key()` for every existing row.

### D5.2 `TypeSignal`

§9, verbatim (`input.md:743-766`):

> A structured statement like:
>
> ```json
> {
>   "@type": "Person",
>   "name": "John Smith"
> }
> ```
>
> must produce:
>
> ```text
> TypeSignal(
>     source_vocab = schema.org,
>     surface = "Person",
>     mapping_candidates = [...]
> )
> ```
>
> not immediately:
>
> ```text
> TypeAssertion(core:Person)
> ```

```python
# apps/shared/semantic/type_signal.py
@dataclass(frozen=True)
class TypeSignal:
    """What a structured or lexical source STATED about a mention's type. Never a type.

    One TypeSignal is one thing one source said: ``source_vocab`` is the vocabulary that
    said it, ``surface`` is the term it said, verbatim. The signal does not know what the
    term means and MUST NOT carry a ``core:`` reference: the first moment a local type may
    appear on this path is TypeHypothesis, and reaching it requires a TypeMapping record, so
    ``schema:Person`` can only become ``core:Person`` by crossing a recorded mapping
    (FR-036, §9 "Never collapse ... without a mapping record").

    It is an observation-channel value object, not a hypothesis and not a rung (§103). It
    has a signal_id because it is an observation with a producer; it has no status, because
    it has reached no conclusion.
    """

    source_vocab: str                              # "schema.org" | "opengraph" | "rdfa" |
                                                  # "microdata" | "html-meta" | "jsonld"
    surface: str                                   # verbatim, as the source stated it
    mapping_candidates: tuple[TypeMappingCandidate, ...] = ()   # >= 0; may legitimately be 0

    mention_ref: str = ""                          # the mention this statement is about
    structural_path: tuple[str, ...] = ()          # where in the document it sat
    observation_refs: tuple[str, ...] = ()         # canonicalised
    evidence_refs: tuple[str, ...] = ()            # canonicalised
    producer_ref: str = ""                         # observation channel identity (FR-006)
    signal_id: str = ""
```

**`mapping_candidates` is `TypeMappingCandidate`, not `TypeMapping`.** Same proposal/record
split as the predicate side, and for the same reason: a `TypeSignal` produced by a JSON-LD
block has, at best, a *candidate* mapping — nothing has been reviewed, sourced, or recorded.
A `TypeMapping` exists only once a `MappingSet` holds it. A `TypeSignal` MAY legitimately
carry zero candidates, and that is the `US4` Acceptance 1 case:

> **Given** a mention surface with no pack entry, **When** extraction runs, **Then** a
> `TypeHypothesis` with `hypothesis_state=UNKNOWN` is retained, not dropped (§97).

```python
@dataclass(frozen=True)
class TypeMappingCandidate:
    """One proposed cross-vocabulary correspondence for a type term. Not yet a record.

    The type-side twin of PredicateMappingCandidate, sharing MappingMatchType and the
    "extension" definition, and differing in exactly one respect: ``source`` is a reference
    in a *type* vocabulary, normalised by ``semantic.vocabularies.normalize_type_ref``
    (which preserves case, because ``schema:Person`` and ``schema:person`` are different
    references), whereas a predicate source is a PredicateSignature content key. One
    normaliser per layer, one match vocabulary, one direction convention.
    """

    source: str                                    # e.g. "schema:Person"
    target: str                                    # e.g. "core:Person"; required, non-empty
    match_type: MappingMatchType                   # REQUIRED, no default
    subject_scheme: SemanticRef = SemanticRef.EXTERNAL
    object_scheme: SemanticRef = SemanticRef.INTERNAL

    confidence: float = 0.0
    provenance: tuple[str, ...] = ()
    mapping_version: str = "1"
    created_by: str = ""
    evidence_refs: tuple[str, ...] = ()
    mapping_set_id: str = "type-mappings"
    mapping_set_version: str = "1"
    supersedes: tuple[str, ...] = ()
    mapping_candidate_ref: str = ""

    # same __post_init__ refusals, same evaluation_material()/content_key()/with_id()/
    # to_dict()/from_dict() as PredicateMappingCandidate
```

**Why two candidate types rather than one generic `MappingCandidate`.** The `source` of each
is normalised by a different function — `normalize_type_ref` (type vocabulary, case-preserving)
versus a `PredicateSignature` content key — and the `subject_scheme`/`object_scheme` pair only
means something for a *type* reference. A single generic type would have to accept both
normalisers and both scheme vocabularies on every field, which is how `RelationSignal.kind`
ended up mixing thirteen meanings before FR-011 split it. **One `MappingMatchType`, one
`content_key()` convention (`semantic.contracts.content_key`), one `MappingMatchType`
direction convention, two candidate types.**

**`TypeSignal` identity** — the analogue of FR-089 for the type layer, and stated here because
nobody has: `signal_id` is derived from `(tenant_id, producer_ref, mention_ref, source_vocab,
surface, structural_path)`. It MUST NOT include `mapping_candidates`, for the reason
`relation_candidate.py:1151-1157` gives on the relation side: a later mapping change is a new
reading of the same observation, not a new observation. And it MUST NOT include `mention_ref`
alone, because two sources may state the same thing about the same mention and §24/FR-006
require those to remain two signals.

### D5.3 The seven initial mappings from §64

§64, verbatim and complete (`input.md:2872-2890`):

> ```
> # 64. TYPE MAPPINGS
>
> Add initial mappings for common external vocabularies where justified:
>
> ```text
> schema:Person → core:Person
> schema:Organization → core:Organization
> schema:WebSite → core:WebSite
> schema:WebPage → core:WebPage
> schema:Event → core:Event
> schema:Product → core:Product
> schema:SoftwareApplication → core:Software
> ```
>
> Treat these as explicit mappings.
>
> Do not silently treat mappings as exact equivalence if they are not.
>
> Use SSSOM-compatible semantics where practical.
> ```

**All seven targets exist in the mandated pack** — `core:Person`, `core:Organization`,
`core:WebSite`, `core:WebPage`, `core:Event`, `core:Product`, `core:Software` all appear in
`FR-030`'s list (`spec.md:488-495`). No target needs to be invented, which is worth stating
because it is checkable and it is the only reason this list is implementable in Phase 1.

**The match types, assigned honestly, with the justification each one needs.** §64 says
"where justified" and "Do not silently treat mappings as exact equivalence if they are not" —
so the assignment *is* the work, and the reasons are stated rather than assumed.

| # | mapping | `match_type` | justification |
|---|---|---|---|
| 1 | `schema:Person → core:Person` | **`broad_match`** | schema.org's own definition of `Person` is "A person (alive, dead, undead, or **fictional**)", which includes fictional characters. A fictional character is not an instance of a `core:Person` that denotes a real human. So S's extension is a proper **superset** of T's. `exact_match` would be exactly the silent equivalence §64 forbids. |
| 2 | `schema:Organization → core:Organization` | **`broad_match`** | schema.org's `Organization` is "A business or organization of any kind" and is the parent of `MusicGroup`, `SportsTeam`, `NGO` and others. `FR-030` splits `core:Organization` from `core:LegalEntity` and `core:Group`; schema.org's `Organization` does not make that split. S ⊋ T. |
| 3 | `schema:WebSite → core:WebSite` | **`exact_match`** | schema.org's `WebSite` is "A collection of related web pages" — the same granularity as `core:WebSite`, with no containment relation in either direction. A process asserted alignment, and per `MatchPredicate`'s own docstring that asserts *a claim by a process*, **not** that the platform may treat them as one type or collapse them. |
| 4 | `schema:WebPage → core:WebPage` | **`exact_match`** | as (3), one concept, one granularity, no containment relation. |
| 5 | `schema:Event → core:Event` | **`exact_match`** | schema.org's `Event` is a general event class at the same granularity as `core:Event`; neither is a subset of the other. The claim is alignment, not identity. |
| 6 | `schema:Product → core:Product` | **`broad_match`** | schema.org's `Product` is "A thing that can be bought or sold", which **includes services**. `FR-030` makes `core:Product` and `core:Service` **separate classes**. So `schema:Product` ⊋ {`core:Product`, `core:Service`}, and the residual does not map to `core:Product` at all. This is the clearest case in the list of a mapping that is real and partial. |
| 7 | `schema:SoftwareApplication → core:Software` | **`broad_match`** | schema.org's `SoftwareApplication` covers "web apps, web services, embedded software" — and a `WebApplication` is also a `WebSite`, which is not software in `FR-030`'s reading. S's extension is wider than `core:Software`, and the part of S that is `schema:WebSite`-as-application maps to nothing in the seven. |

**Tally: 2 `exact_match`, 5 `broad_match`, 0 `narrow_match`, 0 `close_match`, 0
`related_match`.** That lopsidedness is the finding, not a defect in the assignment: **five of
the brief's seven are not exact equivalences**, which is precisely what §64's warning predicts
and precisely what a mapping layer that defaulted to `exact_match` would have hidden. It also
gives `broad_match` a real workload — and `broad_match` already exists in `MatchPredicate`, so
the seven require **no** new match member. The `related_match` addition of D1.2 is needed by the
*predicate* layer, and I have said so rather than pretending the seven need it.

**The `exact_match` rows carry a mandatory note.** Rows 3, 4 and 5 assert alignment and must be
stored as claims, with `justification`, `created_by` and `mapping_version` set — never as a
silent collapse. The `MappingMatchType` docstring's own words apply:

> `MatchPredicate` docstring, `vocabularies.py`
> Read them with their provenance in mind. ``EXACT_MATCH`` says a mapping process claimed
> the two concepts align; it does **not** say the platform treats them as one type, and it
> certainly does not license collapsing them.

**Where the match types come from, stated as a source requirement.** Each justification above
cites schema.org's published definition of the term. That is the "where justified" of §64 and
it is the *minimum*: the justification MUST be recorded in the mapping's `provenance` and
`justification=MAPPING_JUSTIFICATION.MANUAL`, so that a later reviewer can re-derive the call.
An operator (human or process) who cannot cite a source for a match type **withholds the
mapping** rather than guessing one — this is `FR-082`'s stop path applied to a type mapping, and
it is the honest outcome for any term not on the list.

### D5.4 Open question Q3 — the mappings §64 omits

**The question.** §64 lists seven mappings and stops. Three gaps follow from the
justifications above, and none may be filled silently:

| Gap | Why it follows from the seven |
|---|---|
| `schema:Corporation → core:LegalEntity` | row 2 records that `core:LegalEntity` is a class `FR-030` mandates, and schema.org's `Corporation` is its closer counterpart than `Organization` is. The seven do not reach it. |
| `schema:Service → core:Service` | row 6 records that `core:Service` is a class `FR-030` mandates and that `schema:Product` is a superset of `{Product, Service}`. The seven leave half of the source unmapped. |
| `schema:WebApplication → core:WebSite` | row 7 records that part of `schema:SoftwareApplication` is a website. Without it, that part maps to nothing. |

**Decision: do not add them.** The brief says "Add initial mappings … **where justified**" and
enumerates seven. Adding three is a scope decision for the spec owner, not a repair, and the
gap is *recorded* rather than closed: an unmapped external type yields `UNKNOWN` and is
retained (FR-038), which is a correct, complete, non-rejecting outcome.

**Stop condition.** If the §82 entity-type corpus is built over surfaces that require one of
the three, the work **stops** and reports the missing mapping rather than inventing it. The
corpus then either uses only the seven, or the spec owner adds the mapping as a recorded
decision with a cited justification.

---

## D6 — Reconciling `OntologyPack`

### D6.1 What is actually there

`apps/shared/events/ontology_pack.py`, verbatim:

> ```python
>     relations: list[str] = field(
>         default_factory=lambda: ["works_at", "owns", "controls", "corresponds_to", "linked_to"]
>     )
> ```
> ```python
>     def allows_relation(self, relation: str) -> bool:
>         return relation in self.relations
> ```
> ```python
>             "relations": self.relations,
> ```

Four measured facts, each of which changes the decision:

1. **`allows_relation()` is called by nothing.** Verified across `apps/`, `bench/`, `tools/`.
2. **The list is not inert — it is *published*.** `to_dict()` (`:48-57`) emits it, and
   `OntologyPackRegistry.register()` (`:68-84`) measures that descriptor against a 4096-byte
   cap and inlines it. So five relation names travel in every pack payload whether or not
   anything reads them. `data-model.md:240-242`'s "is inert (`allows_relation()` is never
   called) and stays inert" is right about the *call* and wrong about the *consequence*: the
   field is a claim in a serialised payload, and the review's own `D8`-class findings
   (`phase0-results.md:136`) are about exactly this kind of unearned assertion.
3. **`allows_type()` IS called and IS advisory.** `apps/interpretation/extractors/registry.py:76`
   → `semantic_hint(pack, kind)` → `SemanticHint(recognized=bool(name) and bool(pack.allows_type(name)))`,
   written to `m.attrs["semantic_hint"]` (`:154-156`) and read by nothing that filters. The
   docstring already states the rule: *"A bound OntologyPack is advisory (FR-002): every
   mention an extractor reports is admitted … Kinds the pack does not know are kept, not
   filtered."* (`:110-112`) and *"Pack knowledge about `kind` for ranking/expansion; never a
   veto."* (`:121`).
4. **The pack's vocabulary and the mandated vocabulary are disjoint.** The default
   `entity_types` is `["PERSON","ORG","LOCATION","EMAIL","PHONE","DOMAIN","USERNAME",
   "DOCUMENT","URL","IPV4","CVE","CRYPTO_ADDRESS"]` (`:29-34`) — uppercase bare names. So
   `allows_type("core:Person")` compares `"CORE:PERSON"` against that set and returns
   `False`. **Every `core:*` type the feature mandates is, to the pack, unknown.** Today that
   is harmless because the result is a boolean flag nobody filters on. It becomes a rejection
   the moment anyone treats it as a gate — which is the concrete, live demonstration of why
   the "ontology miss must mean unknown, never rejection" rule needs a *test* and not just a
   sentence.

Plus, in `apps/control-plane/db/schema.py:888-906`, a **second** class named `OntologyPack`
over table `ontology_packs` with its own `relations: Mapped[list | None] = mapped_column(JSONB)`
(`:898`) — and **no migration creates `ontology_packs`**. The ORM/migration parity test
enforced for `020` has nothing to enforce here because the table does not exist.

### D6.2 Decision: **delete** the relation half. Keep `allows_type()` exactly as it is.

| Option | Verdict | Why |
|---|---|---|
| **wire** | **refused** | wiring `allows_relation()` makes a five-element list a gate. §104 forbids a finite mandatory relation list, §65 forbids enumerating reality, and FR-074 names the exact form: *"relation extraction MUST NOT contain `if relation not in registry: continue` or equivalent."* Wiring the thing is admitting the bug exists |
| **keep inert** | **refused** | "inert" is false. The list is serialised into every pack payload and size-checked. Keeping it means keeping a false claim about a tenant's relations in a durable artefact. §104 is about what the platform *declares*, not only about what it *checks*: the relational space "begins as observed structure" (`:4237-4247`) and a declared list pre-empts that |
| **delete** | **chosen** | the field is unread, unwritable-into-meaning, unversioned-by-anyone, and §104-forbidden in shape. Deleting it removes a `KeyError` waiting to happen, removes a §104 violation from the read surface, and removes a vocabulary that duplicates the one FR-034a actually wants (`core:*`/`value:*`, extensible by hierarchy) |

### D6.3 Exactly what to change

**In `apps/shared/events/ontology_pack.py`:**

| # | Change | Line |
|---|---|---|
| 1 | **delete** the `relations: list[str] = field(...)` declaration | `:36-38` |
| 2 | **delete** `def allows_relation(self, relation: str) -> bool` | `:45-46` |
| 3 | **delete** `"relations": self.relations,` from `to_dict()` | `:54` |
| 4 | keep `allows_type()` **byte-identical** | `:42-43` |
| 5 | add to the module docstring: a named statement of §104/§65 — a pack declares *entity* types; it does not declare relations, because relations are earned by mapping, and a pack that listed them would be a finite mandatory relation universe | `:1-6` |

**In `apps/control-plane/db/schema.py`** (recommendation to the migration/persistence owner;
`021` is forward-only and must **not** create `ontology_packs`): delete the
`OntologyPack(Base)` class (`:888-906`) and `OntologyPackStatusState` (`:761`) if it has no
other user. An ORM class for a table no migration creates is the same class of defect as
`verify_candidate_material_partition()` (FR-098): a verifier/table whose existence asserts
something no code path can exercise. **I do not execute this one** — it is a schema change and
A2/the migration owner holds `021`.

**In `specs/002-donor-code-integration/contracts/ontology-pack.md`**: the contract document
declares the `relations` field and will need the same deletion. Flagged, not edited (hard
rule: no existing file is edited by this job).

### D6.4 The rule that must survive: ontology miss means unknown, never rejection

Whatever the disposition, this must hold, and it must be **test-enforced** rather than
documented. The three enforcement points, all of which exist today and none of which is
guarded:

| # | Rule | Test that must exist |
|---|---|---|
| 1 | `allows_type()` is **advisory only**: no code path may use its result to drop, skip, filter or reject a mention | mutation: make `extract()` skip a mention whose `semantic_hint.flag == "unrecognized"`, and assert the §82 corpus is unchanged in mention count. This is §97's mutation and FR-079's fourth named one |
| 2 | a `core:*` ref the pack does not know yields `UNKNOWN` and is **retained** | assert `allows_type("core:Person") is False` **and** that the mention survives with `hypothesis_state=UNKNOWN` — the fact-4 demonstration of D6.1. An ontology miss and a fresh ontology must be indistinguishable in the output |
| 3 | no relation-allow-list may exist in the extraction path at all | source scan of `apps/interpretation/extractors/**` and `apps/shared/domain/**` for `allows_relation`, `if .* not in .*relations`, and a hard-coded relation name list. With `allows_relation` deleted, FR-074's second clause becomes un-codelockable by name, so the *behavioural* prohibition and this scan are the enforcement |

**FR-074 is quoted here because it is the FR most at risk from this job's own change**, and
because deleting `allows_relation()` must not be read as weakening it:

> - **FR-074**: No hidden semantic gate: extraction MUST NOT call `OntologyPack.allows_type()`
>   as a drop/deny decision, and relation extraction MUST NOT contain `if relation not in
>   registry: continue` or equivalent. (§73)

Both clauses survive. The first is *more* enforceable after my change, because `allows_type()`
is still named and can still be scanned for. The second becomes a scan rather than a symbol
lookup, which FR-137 specifies.

---

## D7 — New FR text, verbatim

**Numbering**: continues from the existing range and starts at **`FR-130`** to avoid collision
with A2 and the other repair jobs. The existing spec's last numbers are `FR-100` (line 781),
`FR-082`/`FR-083`/`FR-084` (lines 814-836), and `FR-034a` (line 514); `FR-101` does not exist
in the file. `FR-130`–`FR-137` are placed under a new `### Mapping layer` heading, after
`### Predicate and claim boundary` (line 446) and before `### Assembly` (line 464) — or, if
the section order is not to be disturbed, appended after `### Specification deliverables (§100)`
(line 820). **Placement is the spec owner's call; the text and the numbering are mine.**

Each FR cites the section of this document that carries its worked example, so the requirement
and its justification cannot drift apart.

---

- **FR-130**: `PredicateMappingCandidate` MUST be a frozen value object carrying at least
  `source`, `target`, `match_type`, `target_relation_ref`, `confidence`, `provenance`,
  `mapping_version`, `created_by`, `evidence_refs`, `mapping_set_id`, `mapping_set_version`,
  `supersedes` and `mapping_candidate_ref`, with its own `content_key()`, `with_id()`,
  `to_dict()` and `from_dict()`. `source` MUST be a `PredicateSignature` content key and MUST
  NOT be a surface string. `target` MUST be non-empty. `match_type` MUST be one of
  `exact_match`, `close_match`, `narrow_match`, `broad_match`, `related_match` (SSSOM
  semantics, this repository's spelling), MUST be required, and MUST have **no default**, so
  that an unspecified match cannot be recorded as `close_match`. `confidence` MUST default to
  `0.0`, not `1.0`. It MUST carry no lifecycle stage, no `signal_id`, no `candidate_id` and no
  row of its own. (§2, §9, §64, §105; A4b D1)

- **FR-131**: No `PredicateMappingCandidate` field, no `RelationRef`, no `resolution_state`, no
  `alternative_refs`, no `mapping_evidence_refs`, no `match_type`, no `confidence`, no
  `mapping_version`, no `provenance`, no `created_by` and no external vocabulary reference may
  participate in `logical_candidate_id`. Changing any of them MUST change `candidate_id` and
  MUST NOT change `logical_candidate_id`. A change to `mapping_version` or to any other mapping
  field MUST supersede rather than edit: the prior candidate is preserved and named in
  `supersedes`, and it leaves the live candidate set rather than remaining an alternative,
  because a correction is a revision and not an ambiguity. A test MUST break
  `PredicateMappingCandidate.target` and assert `logical_candidate_id` is unchanged, and a
  second MUST break the signature and assert it changes. (§19, §22, §23, §104; A4b D2.3, D2.4)

- **FR-132**: Two signals whose `PredicateSignature`s agree and whose `PredicateMappingCandidate`s
  name different `target_relation_ref`s MUST yield **one** logical candidate carrying one
  `PredicateHypothesis` with `resolution_state=AMBIGUOUS`, at least two entries in
  `mapping_candidates`, a designated `relation_ref`, and both readings preserved. Two
  signatures is two candidates and MUST NOT be reported as `AMBIGUOUS`. Neither interpretation
  may be overwritten, dropped, or ranked into a winner, and `resolution_state` MUST be derived
  from the candidate set and MUST NOT be a caller-stated label. An `AMBIGUOUS` hypothesis MUST
  NOT yield `RelationClaimMaterial`. (§49, §48, §26, §50; A4b D3.2, D3.3, D3.4)

- **FR-133**: A hypothesis whose competing readings came from **disagreeing evidence** rather
  than from one evidence set read by two regimes MUST carry `resolution_state=CONFLICTING`,
  stated explicitly by the assembler and never inferred from the refs, with both readings
  preserved and with `mapping_evidence_refs` naming the `signal_id` on each side so a reader
  can reconstruct why the hypothesis stalled. Both readings MUST be preserved. A disagreement
  that is **structural** — arity, direction, polarity or role bindings over the same mentions —
  is not representable as one hypothesis and MUST yield `FR-090`'s
  `CandidateStatus.CONTRADICTED` candidates with both readings preserved. A `CONFLICTING`
  hypothesis MUST NOT yield `RelationClaimMaterial`. No count, confidence, insertion order or
  alphabetical tie-break may decide either state. (§45, §49, §83, §95; A4b D3.3, D3.4)

- **FR-134**: A structured or external-vocabulary statement (JSON-LD, schema.org, OpenGraph,
  RDFa, microdata, HTML metadata) MUST produce a `TypeSignal` carrying `source_vocab`,
  `surface` and `mapping_candidates` — the last of which MAY legitimately be empty — together
  with `mention_ref`, `structural_path`, `observation_refs`, `evidence_refs`, `producer_ref`
  and its own `signal_id`. A `TypeSignal` MUST NOT carry a `core:` reference and MUST NOT
  produce a `TypeAssertion`. The first moment a local type may appear on this path is
  `TypeHypothesis`, and reaching it MUST require a recorded `TypeMapping`. `signal_id` MUST be
  derived from `(tenant_id, producer_ref, mention_ref, source_vocab, surface, structural_path)`
  and MUST NOT include `mapping_candidates`, so that a later mapping change is a new reading of
  the same observation rather than a new observation. (§9, §10, §24, §37; A4b D5.2)

- **FR-135**: A type mapping MUST be the existing `semantic.mappings.SemanticMapping`, and
  `TypeMapping` is its documented name — no parallel dataclass. It MUST retain subject type,
  object type, mapping predicate, mapping set and set version, mapping version, confidence,
  creator/operator, justification and evidence/provenance, MUST be content-addressed,
  citable, tenant-scoped at the write, superseding rather than editing, and MUST surface
  `MappingConflict` rather than resolve it. It MUST NOT collapse `schema:Person` into
  `core:Person` without a mapping record, and it MUST NOT default `predicate`: every
  construction on the 021 path MUST pass `match_type` explicitly. `MatchPredicate` MUST gain
  `related_match` so that a correspondence which is neither broader nor narrower is
  recordable as such; `Concept` MUST NOT gain a matching field, because a concept declares its
  own links and a mapping process does not. (§9, §64, §105; A4b D1.2, D5.1)

- **FR-136**: The initial type mapping set MUST be exactly §64's seven —
  `schema:Person → core:Person`, `schema:Organization → core:Organization`,
  `schema:WebSite → core:WebSite`, `schema:WebPage → core:WebPage`,
  `schema:Event → core:Event`, `schema:Product → core:Product`,
  `schema:SoftwareApplication → core:Software` — and each MUST be an explicit `TypeMapping`
  record carrying its justification and provenance, never a silent collapse. Match types MUST
  be recorded as claimed and MUST NOT be assumed equivalent: `schema:Person → core:Person`,
  `schema:Organization → core:Organization`, `schema:Product → core:Product` and
  `schema:SoftwareApplication → core:Software` are `broad_match`; `schema:WebSite →
  core:WebSite`, `schema:WebPage → core:WebPage` and `schema:Event → core:Event` are
  `exact_match`, and an `exact_match` MUST still be read as a claim by a mapping process and
  MUST NOT license collapsing the two references. A mapping whose match type cannot be cited to
  a published definition of the term MUST be withheld, and the unmapped term MUST yield
  `UNKNOWN` and be retained. No further mapping may be added without a recorded decision. (§64,
  §38, §82; A4b D5.3, D5.4)

- **FR-137**: `apps/shared/events/ontology_pack.py` MUST NOT declare, publish or check a
  relation list. The `relations` field, `allows_relation()` and the `relations` key in
  `to_dict()` MUST be deleted, and no replacement relation allow-list may be introduced in the
  extraction path. `allows_type()` MUST remain, MUST remain advisory, and MUST NOT be used as
  a drop, deny, filter or reject decision by any code path: an ontology miss MUST mean
  `unknown type`, never a rejected mention, and a `core:*` reference the pack does not know
  MUST be retained with `hypothesis_state=UNKNOWN`. Because no relation symbol remains to lock
  against, FR-074's second clause MUST be enforced behaviourally: a source scan of
  `apps/interpretation/extractors/**` and `apps/shared/domain/**` MUST fail on
  `allows_relation`, on a hard-coded relation-name list, and on any `if … not in … relations`
  shape. The ORM class `control-plane.db.schema.OntologyPack` and its `ontology_packs`
  `relations` column MUST be removed by the migration owner, and migration `021` MUST NOT
  create the table. (§73, §104, §65, §38, §34a; A4b D6)

---

## D8 — Exact old text, exact new text

Every quotation below is verbatim from the file and line range named. Nothing outside the
quoted ranges changes.

### D8.1 `data-model.md` §1 — the N5 row (line 50)

**Old** (line 50):

> ```
> | N5 | Synonym set membership for a *small, versioned, sourced* table — never open-ended | `owns` ≡ `controls` **only** if the table says so |
> ```

**New** (line 50):

> ```
> | N5 | **RETIRED — a synonym table is a claim about equivalence and belongs to the mapping layer, not to identity. Use `PredicateMappingCandidate`; see §10.** | ~~`owns` ≡ `controls`~~ |
> ```

**Notes.** The rule number is retired, **not reused**, and N6 keeps its number. Renumbering
would silently re-point every `N5`/`N6` citation — `tasks.md` T011 ("normalisation rules
N1-N6"), T015 (the whole task), T028, and `tasks.md:264`'s decision-table row — at a different
rule, which is the citation-integrity failure phase0 **D3** and **D10** already record twice.

### D8.2 `data-model.md` §1 — the N5 paragraph (lines 53-57)

**Old** (lines 53-57):

> ```
> N5 is the dangerous one and is bounded deliberately: a versioned, sourced synonym table is a
> *claim about equivalence*, so it is versioned, reviewable, and carries provenance. An
> unbounded embedding or a learned model here would make identity depend on a model artefact,
> which fails the constitution's determinism requirement (VI). **If N5 cannot be justified from
> a source, the predicate stays as two signatures and the platform reports `AMBIGUOUS`.**
> ```

**New** (lines 53-57):

> ```
> N5 is retired from identity, and the reasoning that retired it moves rather than disappears.
> A synonym table *is* a claim about equivalence, and a claim about equivalence is a mapping:
> it is versioned, reviewable, citable and superseded, and it is a **revision** of a
> hypothesis, never its identity. Putting it here made `normalized_predicate` — the predicate
> term of `logical_candidate_id` — depend on an artefact of interpretation, which is the same
> failure as a model artefact in this position and worse, because the model at least carries
> its own provenance and a synonym table looks like data.
>
> Three things are true at once, and the original sentence conflated all three:
>
> * `owns` and `controls` MUST remain distinct signatures (FR-004, §20, `US2` Acceptance 3).
>   Two distinct signatures are **two logical candidates**, never one `AMBIGUOUS` hypothesis.
> * Where a source justifies treating two surfaces as one predicate, that justification is
>   recorded as a `PredicateMappingCandidate` (§10) and MAY move a candidate from two readings
>   to one — as a **revision**, so the earlier reading stays readable.
> * Where no source justifies it, nothing is guessed. The candidate keeps its two readings and
>   the platform reports the state its evidence supports: `AMBIGUOUS` if one evidence set was
>   read two ways, `CONFLICTING` if the evidence disagrees, `UNKNOWN` if nothing was mapped.
>   **Unknown is a complete answer and is never a reason to fabricate one.**
>
> Determinism is unaffected: a mapping is data with a version and a source, and an unbounded
> embedding or a learned model in this position is still forbidden wherever it appears.

**Notes.** This is the single most important text change in the document. It closes phase0
**E1** (the `owns ≡ controls` example), **E5** (the `AMBIGUOUS`-means-two-signatures fallback),
**E13** (the false citation of "the constitution's determinism requirement (VI)" — phase0
records that "there is no Principle VI determinism requirement. VI is *Process-Centric*";
**E14** is the same error in `plan.md`'s Constitution Check and is not mine to fix), and **K5**
(the N5 table as entity-resolution-grade with no ADR slot).
It also corrects `data-model.md`'s own framing of N5 as the dangerous rule, which was accurate
about the *risk* and wrong about the *layer*.

### D8.3 `data-model.md` §4 — the field table (lines 172-179)

**Old** (lines 172-179):

> ```
> | Field | Holds |
> |---|---|
> | `surface_form` | raw words, verbatim |
> | `normalized_form` | normalised predicate - gains a real normaliser (N1-N6) instead of copying the surface |
> | `relation_ref` | mapping to a known operator, or `None` |
> | `alternative_refs` | competing mappings, each with evidence |
> | `resolution_state` | `UNKNOWN`/`AMBIGUOUS`/`CONFLICTING`/`KNOWN` |
> | `mapping_evidence_refs` | why the mapping was made |
> ```

**New** (lines 172-180):

> ```
> | Field | Holds |
> |---|---|
> | `surface_form` | raw words, verbatim |
> | `normalized_form` | normalised predicate - gains a real normaliser (N1-N4, N6) instead of copying the surface |
> | `relation_ref` | the **primary** mapping result, or `None`. A *ranking default*, never a verdict: an `AMBIGUOUS` or `CONFLICTING` hypothesis MUST NOT yield claim material, so the primary decides nothing that survives |
> | `mapping_candidates` | the full live set of `PredicateMappingCandidate` (§10), each with its own `match_type`, `confidence`, `provenance`, `mapping_version`, `created_by` and `evidence_refs`. **>= 0, canonically ordered, de-duplicated by content digest** |
> | `alternative_refs` | **derived, read-only**: every live `target_relation_ref` other than the primary, de-duplicated and sorted. Keeps FR-021's field name and its element type; stops being a tuple of bare refs |
> | `resolution_state` | `UNKNOWN`/`AMBIGUOUS`/`CONFLICTING`/`KNOWN`. **Derived from the candidate set**, except an explicit `CONFLICTING`, which records something the refs cannot |
> | `mapping_evidence_refs` | why the mapping was made - the `signal_id`s behind each reading, so a reader can tell which evidence produced which interpretation |
>
> **`AMBIGUOUS` is one hypothesis with alternatives, never two hypotheses.** Two distinct
> `PredicateSignature`s are two logical candidates (FR-004, §20) and MUST NOT be reported as
> `AMBIGUOUS`. `AMBIGUOUS` means one signature, one evidence set, two defensible readings.
> `CONFLICTING` means the evidence itself disagrees. Both preserve every reading; neither is
> resolved by count, confidence, order or vote (FR-026, §45).
>
> **A `UNKNOWN` state beside a non-`None` `relation_ref` MUST be refused.** That refusal is
> what makes `relation_ref=None` mean *unknown* rather than *unspecified*, which is the only
> reason "structure known, mapping unknown" is expressible at all (§21, §67, SC-002).
```

**Notes.** `N1-N6` → `N1-N4, N6` follows D8.1. The two bolded paragraphs are the operative
corrections and both are required: the first closes **E5**, the second forecloses the
relaxation of `predicate_unknown_with_ref` that D3.5 argues against.

### D8.4 `data-model.md` §4 — the persistence paragraph (lines 186-189)

**Old** (lines 186-189):

> ```
> **Persistence change** (FR-087): `alternative_refs` and `mapping_evidence_refs` get real
> columns. Today they sit inside `candidate_id` material and have no column at all, so two
> candidates differing only in their alternatives get different ids with no stored reason, and
> `PredicateHypothesis` survives only as a 32-char digest.
> ```

**New** (lines 186-192):

> ```
> **Persistence change** (FR-087): `mapping_candidates` and `mapping_evidence_refs` get real
> columns. Today they sit inside `candidate_id` material and have no column at all, so two
> candidates differing only in their alternatives get different ids with no stored reason, and
> `PredicateHypothesis` survives only as a 32-char digest.
>
> Verified at HEAD `0056665`: `relation_candidate` and `relation_signal` carry only
> `predicate_hypothesis String(64)` and `predicate_state String(16)`
> (`db/schema.py:2293-2294`, `:2388-2389`; migration `020` lines 247-248, 307-308), so the
> column exists to hold a digest and nothing else. `mapping_candidates` MUST be stored as
> **structure, not as a digest** — a digest MAY identify the data and MUST NOT be the only
> copy — because `input.md:4385` lists `* alternatives survive` as a mandatory §108 acceptance
> criterion, and a digest cannot survive as evidence. One alternative MUST be readable without
> re-running the regime that produced it.
>
> `resolution_state` is already a column with a CHECK constraint against
> `PredicateResolutionState` (`db/schema.py:2354`, `:2444`), so the four states persist
> correctly today. `AMBIGUOUS` and `CONFLICTING` are therefore already storable; what is
> missing is the readings that justify them.
```

**Notes.** "Verified at HEAD" and the file:line citations are new and are the point: the
original says alternatives "have no column at all", which is true, but the repair must say
*where the columns would go* and *what shape*, or `FR-087` stays as unimplementable as it is
today.

### D8.5 `data-model.md` §3 — `relation_ref` and the surface-from-ref fallback

**Old** (line 128, inside the §3 dataclass):

> ```
>     relation_ref: RelationRef | None                # mapping, NOT identity
> ```

**New** (line 128):

> ```
>     relation_ref: RelationRef | None                # mapping result, NOT identity; see §10
>     mapped_operator_refs: tuple[RelationRef, ...] = ()   # primary + live alternatives, so an
>                                                            # AMBIGUOUS reading is visible in the
>                                                            # type and not only in a sibling object
> ```

**Old** — and this is a **code** change, listed here because it is a data-model claim that
turns out to be false. `relation_candidate.py:691`, inside `__post_init__`:

> ```python
>                 object.__setattr__(
>                     self,
>                     "predicate_hypothesis",
>                     PredicateHypothesis(
>                         relation_ref=self.relation_ref,
>                         surface_form=self.relation_surface
>                         or ("" if self.relation_ref is None else str(self.relation_ref.relation_type)),
>                     ),
>                 )
> ```

**New**: the `or (...)` fallback is **deleted**; the hypothesis is built with
`surface_form=self.relation_surface` and no synthetic surface. A candidate with no surface and
no signature is a candidate with no identity term, which is the honest state and the §90 case.
If a caller needs a surface it must pass one.

**Notes.** `relation_candidate.py:1128-1129` claims this is harmless — *"no existing identity
moves"*. It is harmless **only** because no producer currently emits a surface-less candidate.
The first one that does inherits a logical identity keyed on the mapping target, and every
future mapping change then moves it. The docstring at `:1128-1129` MUST be corrected with the
deletion, or it becomes a comment asserting a safety property the code no longer has — the same
defect class as `verify_candidate_material_partition()` (FR-098) and the three `signal_id`
docstrings FR-089 already orders corrected.

### D8.6 `data-model.md` §3 — `relation_type` becomes a mapping result in the type

**Old** (`relation_candidate.py:838-847`):

> ```python
>     @property
>     def relation_type(self) -> str:
>         """The operator's relation type, read off the reference rather than restated.
>
>         Empty for an unresolved predicate, and empty is the honest answer: no operator was
>         named, so there is no type to report. Callers that need to know *why* it is empty
>         should read :attr:`predicate_hypothesis`, which distinguishes a surface nobody has
>         typed from a reading with several defensible types.
>         """
>         return "" if self.relation_ref is None else self.relation_ref.relation_type
> ```

**New**: renamed to `mapped_relation_type`, with `relation_type` retained as a delegating
deprecated alias, plus `mapped_operator_refs` and a `RelationRef` refusal on an empty
`relation_type`. And the claim boundary moves from "is the string empty" to "is the state
`KNOWN`":

> ```python
>     @property
>     def mapped_relation_type(self) -> str:
>         """The operator this candidate was MAPPED TO. Not the relation's type.
>
>         The name says which of the two this is. ``relation_type`` promised ontology
>         authority - a reader would conclude the relation *is* a works_for - and §104
>         forbids requiring that all relations fit a finite global edge list. The field does
>         not carry domain or range; ``relation_schema.RelationSchema`` binds those, and
>         ``MappingMatchType`` records the direction of the mapping itself.
>
>         Empty means NO MAPPING WAS MADE. It does not mean the relation has no type, and it
>         is not a signal that the platform understands the predicate. For a hypothesis with
>         several defensible readings this returns the designated primary, which is a ranking
>         default and NOT a verdict - read :attr:`mapped_operator_refs` and
>         :attr:`predicate_hypothesis` for the whole set.
>         """
>         return "" if self.relation_ref is None else self.relation_ref.relation_type
>
>     @property
>     def mapped_operator_refs(self) -> tuple[RelationRef, ...]:
>         """Primary first, then every live alternative, canonicalised."""
>         return self.predicate_hypothesis.all_refs
> ```

**And in `relation_claim_material.py`, the gate changes** (`:360`, fed from `:734`):

> Old: `if not self.relation_type:`
> New: `if self.candidate.predicate_hypothesis.resolution_state is not PredicateResolutionState.KNOWN:`
> — with a refusal message that names the state, so an ambiguous predicate's refusal says
> *ambiguous* rather than *untyped*.

**Notes.** This is the fix that makes "neither interpretation overwritten" true rather than
merely stored. Without it, `relation_candidate.py:847` returns the primary for an `AMBIGUOUS`
hypothesis, `relation_claim_material.py:360` sees a non-empty string, admits the material, and
an edge is projected for a predicate the platform admitted it does not understand. That is
§51's projection boundary crossed by an unresolved predicate, and it is reachable today.

### D8.7 `data-model.md` §6 — the `OntologyPack` sentence (lines 240-242)

**Old** (lines 240-242):

> ```
> unmapped type yields `UNKNOWN` and is retained; it is never a rejection. The `relations` list on
> the existing `apps/shared/events/ontology_pack.py` is inert (`allows_relation()` is never
> called) and stays inert - a fixed relation list is what §104 forbids.
> ```

**New** (lines 240-244):

> ```
> unmapped type yields `UNKNOWN` and is retained; it is never a rejection.
>
> The `relations` list on `apps/shared/events/ontology_pack.py` is **deleted, not kept inert**
> (FR-137). "Inert" was the wrong diagnosis: `allows_relation()` is indeed never called, but
> `to_dict()` publishes the list and `OntologyPackRegistry.register()` inlines it, so five
> relation names ride in every pack payload whether or not anything reads them. A fixed
> relation list is what §104 forbids, and a published one is worse than an enforced one -
> it is a durable claim about a tenant's relations that no one made.
>
> `allows_type()` stays exactly as it is, called exactly where it is called
> (`interpretation/extractors/registry.py:76`), and stays **advisory**: its result annotates
> and never filters. That matters more than it looks: the pack's default `entity_types` are
> uppercase bare names (`PERSON`, `ORG`, …), so `allows_type("core:Person")` is `False` and
> **every `core:*` type the feature mandates is unknown to the pack**. Harmless while the
> result is a flag; a rejection the moment anyone treats it as a gate. Hence FR-137's
> test-enforced "ontology miss means unknown, never rejection", and §97's mutation.
```

**Notes.** The two measured facts — `allows_type("core:Person") is False`, and the list is
published — are what turn this from a policy sentence into an implementable one.

### D8.8 `data-model.md` §7 — the persistence table (lines 253-254)

**Old** (lines 253-254):

> ```
> | `relation_signal` | `predicate_normalized`, `predicate_arity`, `predicate_roles`, `predicate_argument_shapes`, `predicate_direction`, `predicate_polarity`, `predicate_alternatives`, `predicate_mapping_evidence` | FR-087 |
> | `relation_candidate` | same signature set, plus `signal_refs`, `direction`, `polarity`, `confidence`, `predicate_alternatives`, `predicate_mapping_evidence` | FR-087, FR-088 |
> ```

**New** (lines 253-254):

> ```
> | `relation_signal` | `predicate_normalized`, `predicate_arity`, `predicate_roles`, `predicate_argument_shapes`, `predicate_direction`, `predicate_polarity`, `predicate_mappings` (JSONB, structured, one row per `PredicateMappingCandidate`), `predicate_mapping_evidence` | FR-087, FR-130 |
> | `relation_candidate` | same signature set, plus `signal_refs`, `direction`, `polarity`, `confidence`, `predicate_mappings` (JSONB, structured), `predicate_mapping_evidence` | FR-087, FR-088, FR-130 |
> | `semantic_mappings` | **no new columns** - `SemanticMapping` already persists subject/object, scheme, predicate, set id + version, source, version, justification, provenance, confidence, observed_at, supersedes (`db/schema.py:1477`, migration 018) | FR-135 |
> | `type_signals` (**NEW TABLE**) | `signal_id`, `tenant_id`, `mention_ref`, `source_vocab`, `surface`, `structural_path`, `producer_ref`, `observation_refs`, `evidence_refs`, `mappings` (JSONB, structured) | FR-134 |
> | `type_mapping_candidates` (**NEW TABLE**) | one row per `TypeMappingCandidate`, mirroring `semantic_mappings`' columns | FR-134, FR-135 |
>
> `predicate_alternatives` is renamed to `predicate_mappings` because it no longer holds
> alternatives alone: it holds the **full live set** of mapping candidates, primary included,
> because the primary is a designation rather than a winner and storing only the others would
> make the store unable to reconstruct which reading was ranked first. `JSONB` is
> acceptable here and only here: §14's "do not turn the entire thing into arbitrary JSONB"
> forbids *core, load-bearing dimensions* going untyped, and each entry is a typed
> `PredicateMappingCandidate` with a lossless `to_dict()`/`from_dict()`, not a bag.
>
> `021` is forward-only and MUST NOT create `ontology_packs` (FR-137).
```

**Notes.** `type_signals` and `type_mapping_candidates` are genuinely new tables and are a
real Phase-1 cost that no artefact currently records. The two FR-035/FR-036 orphans are
therefore not free: they are two tables, one enum member, one alias, seven mapping records and
one test — and that is the honest size of the work D1 of the review was measuring.

### D8.9 `data-model.md` §9 — the entity summary (lines 295, 299)

**Old** (line 295):

> ```
> | `PredicateHypothesis` | EXTENDED | — | Mapping state, separate from structure; real normaliser |
> ```

**New** (line 295):

> ```
> | `PredicateHypothesis` | EXTENDED | — | Mapping state, separate from structure; real normaliser; `mapping_candidates` stored, `alternative_refs` derived |
> ```

**Old** (line 299):

> ```
> | `TypeVocabulary` (`core:*`/`value:*`) | NEW | — | Versioned, bounded, never a gate |
> ```

**New** (lines 299-302, three rows added):

> ```
> | `TypeVocabulary` (`core:*`/`value:*`) | NEW | — | Versioned, bounded, never a gate |
> | `PredicateMappingCandidate` | NEW | — (none) | A proposed predicate mapping. **No field is identity-bearing**; all is revision material. Not a rung (§103) |
> | `TypeSignal` | NEW | `TSIG-` + digest | What a source *said* about a type. Carries no `core:` ref |
> | `TypeMappingCandidate` | NEW | — (none) | A proposed type mapping; all revision material |
> | `TypeMapping` | ALIAS | `SemanticMapping`'s digest | **Not a new type.** FR-036's eight fields are `SemanticMapping`'s eight fields |
> | `MappingMatchType` | NEW | — | Five SSSOM members, snake_case, direction pinned; no `unmapped` member |
> | `OntologyPack.relations` | **REMOVED** | — | A fixed relation list is what §104 forbids (FR-137) |
> ```

### D8.10 `data-model.md` — a new §10 (append after §9)

**New section**, so the mapping layer has a home in the document rather than being scattered
across §1, §3, §4 and §6:

> ```
> ---
>
> ## 10. The mapping layer (A4b)
>
> Everything above is identity or structure. This section is the claim layer, and it sits
> strictly below both.
>
> ```
> surface predicate → PredicateSignature → logical candidate identity      (A2)
> PredicateSignature → PredicateMappingCandidate(s) → relation_ref        (this section)
> ```
>
> The two chains share one node — `PredicateSignature` — and no field. A change to any
> `PredicateMappingCandidate` field, or to any `RelationRef`, moves `candidate_id` and MUST NOT
> move `logical_candidate_id`. A synonym table, a curated equivalence list, a regime's
> confidence and a Wikidata property are all *claims*, and all four are versioned, citable and
> superseding.
>
> | Type | Layer | Role |
> |---|---|---|
> | `PredicateMappingCandidate` | predicate | a **proposed** mapping, with `match_type`, confidence, provenance, version, creator, evidence. No field is identity-bearing |
> | `TypeMappingCandidate` | type | the same, with a type reference as `source` |
> | `MappingMatchType` | both | `exact_match`, `close_match`, `narrow_match`, `broad_match`, `related_match`. Direction pinned. No `unmapped` member: absence of a record is the representation |
> | `TypeMapping` = `SemanticMapping` | type | a **recorded** mapping, in `semantic_mappings` since 018. Content-addressed, citable, superseding, conflict-surfacing |
> | `PredicateHypothesis` | predicate | the live candidate set, the designated primary, the derived alternatives, and the state that distinguishes one reading from several from conflicting evidence |
>
> `AMBIGUOUS` is **one** hypothesis with `alternatives`. Two signatures are two candidates.
> Neither interpretation is overwritten, and neither becomes a claim.
> ```

### D8.11 `spec.md` FR-021 (lines 448-451)

**Old**:

> ```
> - **FR-021**: `PredicateHypothesis` MUST preserve `surface_form`, `normalized_form`,
>   `predicate_signature`, `relation_ref`, `alternative_refs`, `resolution_state` and
>   `mapping_evidence_refs`. States are `KNOWN`, `UNKNOWN`, `AMBIGUOUS`, `CONFLICTING`. No
>   `UNKNOWN_RELATION` sentinel and no fabricated `RelationRef`. (§21)
> ```

**New**:

> ```
> - **FR-021**: `PredicateHypothesis` MUST preserve `surface_form`, `normalized_form`,
>   `predicate_signature`, `relation_ref`, `mapping_candidates`, `alternative_refs`,
>   `resolution_state` and `mapping_evidence_refs`. `mapping_candidates` holds the full live
>   set of `PredicateMappingCandidate`, each with its own match type, confidence, provenance,
>   mapping version, creator and evidence, and MUST be stored as structure rather than as a
>   digest; `alternative_refs` is a **derived, read-only** view of it and is never a tuple of
>   bare refs. `resolution_state` is **derived from the candidate set**, except an explicit
>   `CONFLICTING`, which records something the refs cannot; a caller-stated `KNOWN` beside two
>   alternatives MUST be corrected to `AMBIGUOUS`, and a `UNKNOWN` beside a non-`None`
>   `relation_ref` MUST be refused, so that `relation_ref=None` means *unknown* and not
>   *unspecified*. States are `KNOWN`, `UNKNOWN`, `AMBIGUOUS`, `CONFLICTING`. No
>   `UNKNOWN_RELATION` sentinel and no fabricated `RelationRef`. (§21, §49, §67; FR-130, FR-132)
> ```

**Notes.** The field list gains one name, the two behaviours that made `AMBIGUOUS` and
`CONFLICTING` reachable are stated, and the two existing refusals are promoted from implicit
code to requirement. `US4` Acceptance 2's "a `TypeHypothesis` with mapping candidates, and
**not** a `TypeAssertion`" is the type-side twin and is FR-134.

### D8.12 `spec.md` FR-028 (lines 478-480)

**Old**:

> ```
> - **FR-028**: Two signals agreeing on surface but carrying different `relation_ref`s MUST
>   yield one logical hypothesis whose predicate is `AMBIGUOUS`, with neither interpretation
>   overwritten; genuine disagreement yields `CONFLICTING` with both preserved. (§49)
> ```

**New**:

> ```
> - **FR-028**: Two signals whose `PredicateSignature`s agree and whose `PredicateMappingCandidate`s
>   name different `target_relation_ref`s MUST yield **one** logical hypothesis whose predicate
>   is `AMBIGUOUS`, carrying at least two entries in `mapping_candidates`, a designated
>   `relation_ref`, and both interpretations preserved. **Two distinct signatures are two
>   logical candidates and MUST NOT be reported as `AMBIGUOUS`.** Agreement of the evidence
>   distinguishes the two states: readings that came from one evidence set read two ways are
>   `AMBIGUOUS`; readings whose evidence contradicts itself are an explicit `CONFLICTING`, with
>   both preserved and with the `signal_id` of each side recoverable. Neither state may be
>   decided by count, confidence, order or vote, and neither may yield `RelationClaimMaterial`.
>   (§49, §45, §26, §50, §83; FR-132, FR-133)
> ```

**Notes.** This is the FR that closes phase0 **E5** and D8's `input.md:4385` obligation. The
sentence that matters is the second: it says in the requirement itself that `AMBIGUOUS` is
*one* hypothesis, so no future reader can reinstate the two-candidate reading from a footnote.

### D8.13 `spec.md` FR-035 (lines 521-523)

**Old**:

> ```
> - **FR-035**: External vocabularies (JSON-LD, schema.org, OpenGraph, RDFa, microdata, HTML
>   metadata) MUST produce a `TypeSignal` with `source_vocab`, `surface` and
>   `mapping_candidates`, and MUST NOT immediately produce a `TypeAssertion`. (§9)
> ```

**New**:

> ```
> - **FR-035**: External vocabularies (JSON-LD, schema.org, OpenGraph, RDFa, microdata, HTML
>   metadata) MUST produce a `TypeSignal` with `source_vocab`, `surface` and `mapping_candidates`
>   — the last MAY legitimately be **empty**, which is the `US4` Acceptance 1 case and is
>   retained, never dropped — together with `mention_ref`, `structural_path`,
>   `observation_refs`, `evidence_refs`, `producer_ref` and its own `signal_id`, derived from
>   `(tenant_id, producer_ref, mention_ref, source_vocab, surface, structural_path)` and
>   **excluding** `mapping_candidates`, so that a later mapping is a new reading of the same
>   observation rather than a new observation. A `TypeSignal` MUST NOT carry a `core:`
>   reference and MUST NOT immediately produce a `TypeAssertion`; the first moment a local
>   type may appear on this path is `TypeHypothesis`, and reaching it MUST require a recorded
>   `TypeMapping`. (§9, §10, §24, §97; FR-134)
> ```

### D8.14 `spec.md` FR-036 (lines 524-527)

**Old**:

> ```
> - **FR-036**: A type mapping MUST retain subject type, object type, mapping predicate,
>   mapping set, mapping version, confidence, creator/operator and evidence/provenance, and MUST
>   NOT collapse `schema:Person` into `core:Person` without a mapping record. SSSOM-compatible
>   semantics apply, and a non-equivalence match MUST be recordable as such. (§9, §64)
> ```

**New**:

> ```
> - **FR-036**: A type mapping MUST be the existing `semantic.mappings.SemanticMapping`, whose
>   fields already are subject type, object type, mapping predicate, mapping set and set
>   version, mapping version, confidence, creator/operator, justification and
>   evidence/provenance; `TypeMapping` is its documented name and **no parallel dataclass may
>   be introduced**. It MUST be content-addressed, citable, tenant-scoped at the write,
>   superseding rather than editing, and MUST surface `MappingConflict` rather than resolve it.
>   It MUST NOT collapse `schema:Person` into `core:Person` without a mapping record, and it
>   MUST NOT default its match type, so that an unspecified correspondence is never recorded as
>   a claim. SSSOM-compatible semantics apply: match types are `exact_match`, `close_match`,
>   `narrow_match`, `broad_match` and `related_match`, an `exact_match` is a claim by a
>   mapping process and does not license collapsing the two references, and a non-equivalence
>   match MUST be recordable as such. `MatchPredicate` MUST gain `related_match`; `Concept`
>   MUST NOT gain a matching field. (§9, §64, §105; FR-135, FR-136)
> ```

**Notes.** The substantive change is *"MUST be the existing `SemanticMapping`"*. FR-036 has
had no implementing task for the whole life of the feature because it reads as a request for a
new type, and nobody built one. It is not a new type. Closing it is a crosswalk table, an enum
member, a test, and a decision about the seven.

### D8.15 `spec.md` — FR-003 and FR-004 are confirmed, not changed

Quoted for the record, because the mapping layer's whole argument rests on them and because
A4b must not appear to relax them:

> ```
> - **FR-003**: System MUST provide a deterministic `PredicateSignature` carrying at least
>   language, normalized trigger, lemma, normalized frame, normalized argument roles,
>   voice normalization, preposition normalization, particle normalization and event-class hint.
>   It MUST NOT be a `RelationRef` and MUST NOT be a semantic ontology concept. (§18)
> - **FR-004**: Normalization MUST be deterministic and MUST NOT unify semantically distinct
>   relations. `owns`/`controls`/`manages` MUST remain distinct. Surface variation must not
>   force inequality, and similarity must not force equivalence. (§20)
> ```

FR-003's "MUST NOT be a `RelationRef` and MUST NOT be a semantic ontology concept" is the
boundary D1 and D2 are drawn on, stated by the spec before this job started. FR-004's
"`owns`/`controls`/`manages` MUST remain distinct" is D2.2's worked example, verbatim. **No
change to either.** The synonym knowledge N5 proposed to inject is not deleted in full — it is
relocated to the layer that may hold a claim about equivalence, where FR-004 does not apply
because FR-004 governs *identity*, not *mapping*.

---

## Review findings closed by this document

### D1 of phase0-results.md §4.1 — "52 of 102 FRs have no implementing task and no checklist item"

**Two of the 52 are FR-035 and FR-036, and both are closed here — by naming existing code, not
by adding a type.**

| FR | Why it was orphaned | What closes it |
|---|---|---|
| **FR-035** | reads as "create a `TypeSignal` type", and no artefact says where it lives, what its identity is, or that `mapping_candidates` may be empty | FR-134 + D5.2: a frozen value object with a pinned 7-field identity digest that excludes `mapping_candidates`; **one new table** (`type_signals`) |
| **FR-036** | reads as "create a type mapping record", and nobody noticed that `semantic.mappings.SemanticMapping` already *is* one, with all eight required fields, persisted since migration 018 | FR-135 + D5.1: **no new dataclass**. An alias, a crosswalk table, one enum member (`related_match`), one default-removal rule, and a test |

The honest size of the work: one new value object, one new alias, one enum member, one extra
field on an existing one, **two new tables**, seven mapping records, one deleted relation
allow-list, and six test obligations. That is a Phase-1 task with a real cost, which is what
D1 was measuring.

### E5 of phase0-results.md §4.2 — "`AMBIGUOUS`" = two signatures

| Where | Change |
|---|---|
| `data-model.md:57` | D8.2 — the sentence is replaced; two signatures are two candidates, stated as such, with the three-way distinction (distinct candidates / `AMBIGUOUS` / `CONFLICTING` / `UNKNOWN`) spelled out |
| `data-model.md:172-180` | D8.3 — the field table gains `mapping_candidates`, demotes `alternative_refs` to derived, and states the `AMBIGUOUS`-is-one-hypothesis rule in the table itself |
| `data-model.md:186-192` | D8.4 — the alternatives MUST be stored as structure, with the verified evidence for why a digest is not enough |
| `spec.md:478-480` (FR-028) | D8.12 — the FR itself says "**one** logical hypothesis" and "two distinct signatures are two logical candidates and MUST NOT be reported as `AMBIGUOUS`" |
| `tasks.md:264` | the decision-table row "N1-N4 only; N5 entries dropped, predicates stay `AMBIGUOUS`" keeps the wrong half of the error and MUST change to "predicates stay as separate candidates; equivalence claims are `PredicateMappingCandidate`s". Not edited by this job; flagged for the tasks owner |
| code | D3.2–D3.5: `_resolve_state` derives from the candidate set; the `UNKNOWN`+ref refusal is kept and argued; the dead promotion in `with_alternatives` is deleted |

### D8 of phase0-results.md §4.1 — "29 of §108's 47 acceptance bullets have no success criterion"

**`input.md:4385` — `* alternatives survive` — now has a requirement, a type, a storage shape
and a success criterion.**

| Layer | Where |
|---|---|
| acceptance criterion | `input.md:4385`, `* alternatives survive` (read-only here) |
| requirement | **FR-132**, and FR-028 as amended |
| type | `PredicateHypothesis.mapping_candidates`, `PredicateMappingCandidate` (D1.3, D3.2) |
| storage | `predicate_mappings` JSONB, structured, one entry per candidate, **not** a digest (D8.8) |
| test | one candidate built from two regimes over one evidence set ⇒ one `logical_candidate_id`, two `mapping_candidates`, `state=AMBIGUOUS`, both `target`s readable after a round trip with no regime re-run, and `RelationClaimMaterial` **refused** |
| success criterion | extend **SC-008** (`spec.md:887-888`): "A predicate hypothesis with alternatives and mapping evidence round-trips through its store with every part recoverable, not merely a matching digest" — add the `AMBIGUOUS` construction and the claim refusal |

SC-008 already says "not merely a matching digest". That clause was written for this and could
not be satisfied, because the alternatives were not stored. It can now.

### Also closed, incidentally

| Finding | How |
|---|---|
| **E2** (`role: str` free text in `logical_candidate_id`) | A2's, but D2.1 pins that the mapping chain reads no `role_names` and no `arity`, so a role-name normalisation change cannot reach a mapping decision |
| **E10** (round-tripping four fields that do not exist on `RelationCandidate`) | D4.2(c) adds `mapped_operator_refs`, and D3.2's `mapping_candidates` are on `PredicateHypothesis`; FR-132 and D8.8 name which column each goes in, so T007/T053 stop inventing fields |
| **K6** (migration `021` specified to ADD columns only) | D8.8 records that `021` must also create `type_signals` and `type_mapping_candidates` and MUST NOT create `ontology_packs` |
| **D3** (18 of 50 FR citations point at an unrelated FR) | every new FR cites its brief section **and** its A4b section, and every new code claim in this document carries a `file:line` |

---

## Open questions, with stop conditions

Three are mine, one is shared, one belongs to a §103 reading I may be wrong about. All are
recorded rather than resolved by invention.

| # | Question | Provisional decision | Stop condition |
|---|---|---|---|
| **Q1** | `related_match` for incomparable pairs, and `MatchPredicate` gaining a member it cannot project onto `Concept` | adopt; add the member; leave `Concept` alone (D1.2) | if the review rules the member illegal, `related_match` MUST NOT be coerced to `close_match` on the way to a `MappingCitation`; record no candidate and use `FR-082`'s stop path. The coercion prohibition becomes a named mutation |
| **Q2** | a hypothesis with ≥ 2 alternatives and **no** primary: `UNKNOWN`, or `AMBIGUOUS` with `predicate_resolution_without_ref` relaxed? | contain it: leave `UNKNOWN`, refuse at the claim boundary, record the misnaming as a known limitation (D3.5) | if the §83 *Ambiguous* corpus case is built with no designated primary, **stop** and report. Do not relax `predicate_resolution_without_ref`; §49's own example has a primary, so build it that way |
| **Q3** | the three mappings §64 omits: `schema:Corporation → core:LegalEntity`, `schema:Service → core:Service`, `schema:WebApplication → core:WebSite` | do not add them; the brief enumerates seven and unmapped is a correct outcome (D5.4) | if the §82 entity-type corpus needs one, **stop** and report the missing mapping rather than inventing it |
| **Q4** (shared with A2) | which disagreements are hypothesis-level `CONFLICTING` and which are FR-090 candidate-level `CONTRADICTED`? | split on the layer: mapping disagreement ⇒ hypothesis; structural disagreement ⇒ candidate (D3.4) | **A2 must state this split in `A2-identity-subsystem.md`** or the two documents will disagree about which artefact a corpus case produces. This is the one item I cannot close alone |
| **Q5** | is §103's nested-value-object list (lines 4176-4185) exhaustive for the relation hierarchy? | read as illustrative: `PredicateMappingCandidate` is a value object with no lifecycle stage, no id of its own and no row, exactly as `TemporalHypothesis` is a field of `RelationCandidate` (D1.1) | if the list is exhaustive, `PredicateMappingCandidate` collapses into `relation_ref` + a flat `mapping_evidence_refs` entry, at the cost of `data-model.md:177`'s own "each with evidence" and of `input.md:4385`. **The fallback is written out above so it is a decision and not a discovery during implementation** |

**Q5 deserves one more sentence**, because phase0 **E3** is the finding that creates it. E3
reads §103's list as a whitelist and rejects a `TypeHypothesis` of containers on that basis.
The test I have applied instead: *does the type have a lifecycle stage and its own lifecycle
transition?* `PredicateMappingCandidate` has none — no `signal_id`, no `candidate_id`, no row,
no transition, and FR-130 forbids it from growing one. A *rung* would need all four. The
distinction is drawn, the drawing is stated, and the reading is recorded so that a reviewer who
prefers E3's reading has the alternative cost in front of them rather than having to re-derive
it.

---

## Handover — what A2 and the other agents need from this document

**For A2-identity-subsystem:**

1. **N5 is retired, not renumbered.** N6 keeps N6. A2 must not renumber, and must not cite
   "N5" for anything. `data-model.md` line 50 becomes a retirement marker (D8.1).
2. **The synonym knowledge is not deleted, it is relocated.** Where A2 deletes the N5 table, it
   should say *where it went* — `PredicateMappingCandidate` (§10) — so the feature does not
   appear to have lost the ability to record an equivalence claim. It did not; it gained a
   place to record one honestly.
3. **The identity/mapping boundary is one sentence** (D2.1) and A2 must be able to state it
   without appealing to this document: the two chains share `PredicateSignature` and no field.
4. **Q4 must be answered in both documents** — which disagreements are hypothesis-level
   `CONFLICTING` and which are `FR-090` candidate-level `CONTRADICTED`.
5. **`relation_candidate.py:691` is A2's to delete** (D8.5). It is a signature-identity issue
   (a surface synthesized from the mapping target) even though the offending value comes from
   the mapping layer. Flagged because it will otherwise be missed by both jobs.

**For the migration / persistence owner (not A4b, not A2):**

| Change | Where |
|---|---|
| add `predicate_mappings` (JSONB, structured) and `predicate_mapping_evidence` to `relation_candidate` and `relation_signal` | D8.8, FR-087 |
| rename `predicate_alternatives` → `predicate_mappings`, because it now holds the **full live set**, primary included | D8.8 |
| create `type_signals` and `type_mapping_candidates` | D8.8, FR-134 |
| `semantic_mappings` needs **no** new columns | D8.8, FR-135 |
| delete the `OntologyPack(Base)` ORM class and its `ontology_packs.relations` column; `021` MUST NOT create `ontology_packs` | D6.3, FR-137 |
| add a `FR-130`–`FR-137` row to the Phase-0→1 checklist, which currently maps **zero** of the 102 FRs (phase0 **D5**) | FR-130…FR-137 |

**For the spec owner:**

| Decision needed | Reference |
|---|---|
| the five open questions above, with their stop conditions | "Open questions" table |
| whether `MatchPredicate` gains `related_match` | Q1, D1.2 |
| whether the §83 *Ambiguous* corpus case has a designated primary | Q2, D3.5 |
| whether the three omitted §64 mappings are added | Q3, D5.4 |
| whether §103's value-object list is exhaustive | Q5, D1.1 |
| where `FR-130`–`FR-137` sit in the document | D7 header |
| `specs/002-donor-code-integration/contracts/ontology-pack.md` declares the deleted `relations` field | D6.3 |
| `tasks.md:264`'s "predicates stay `AMBIGUOUS`" keeps the wrong half of E5 | "Review findings closed", E5 row |

**New row requested in `spec.md`'s reachability table (line 791):**

| Component | Non-test production importer | Consequence |
|---|---|---|
| `semantic.mappings.MappingRegistry` / `MappingSet` / `SemanticMapping` | **none** — the only two constructions are inside `mappings.py` itself (`:671`, `:1113`) | FR-036 and FR-137's `TypeMapping` have a type and a table and **no caller**; the entire mapping layer is unreachable, exactly as `SqlRelationClaimStore` and `GraphProjectionBridge` are |

---

## Summary of the eight decisions

| # | Decision | One line |
|---|---|---|
| **D1** | `PredicateMappingCandidate`, frozen, `match_type` required with no default, five SSSOM members in snake_case with the direction pinned, **no field identity-bearing** | the claim about a correspondence, versioned and citable, and not one field of it is identity |
| **D2** | `owns` and `controls` carry different signatures and two candidates both point at `wikidata:P127`; `possesses` maps to nothing and is `UNKNOWN` | the map is many-to-many in both directions and a function in neither; `mapping_version` is one of five version axes, none of which is identity |
| **D3** | `mapping_candidates` stored, `alternative_refs` derived, `AMBIGUOUS` = one hypothesis with readings, `CONFLICTING` = evidence that disagrees, both refused at the claim boundary | the `_resolve_state` asymmetry **survives whole**, with three amendments, one dead branch deleted, and one gap named rather than closed |
| **D4** | `relation_ref` is a mapping result; `relation_type` → `mapped_relation_type` + `mapped_operator_refs`, the claim gate moves to `resolution_state is KNOWN`; `RelationRef` keeps its no-domain/no-range disclaimer and gains nothing | the distinction becomes visible in the type, and the §2 role/domain/range hint is met by `RelationSchema` plus `MappingMatchType` rather than by a second contract |
| **D5** | `TypeMapping` **is** `SemanticMapping` — no new dataclass; `TypeSignal` and `TypeMappingCandidate` are new; the seven §64 mappings are recorded with `broad_match` ×5 and `exact_match` ×2, five of seven not equivalences | two orphan FRs close on existing code, one enum member, two new tables, and seven justified records |
| **D6** | `OntologyPack.relations` and `allows_relation()` are **deleted**, not kept inert — the list is published in every pack payload; `allows_type()` stays and stays advisory | a published relation list is worse than an enforced one, and `allows_type("core:Person") is False` is the live proof that the miss-must-mean-unknown rule needs a test |
| **D7** | `FR-130`–`FR-137`, one per subject, each citing its brief section and its A4b section | no collision with A2 or the other repair jobs |
| **D8** | 15 exact old/new text pairs across `data-model.md` §1/§3/§4/§6/§7/§9, a new §10, `spec.md` FR-021/FR-028/FR-035/FR-036, and four code changes | E1, E5, E13, K5, D1, D5, D8, E2, E10 and K6 all close on quoted text |

**The one sentence to carry out of this document:** a synonym table, a curated equivalence
list, a regime's confidence and a Wikidata property are all **claims** — and all four are
versioned, citable, superseding, and revision material. Identity is what the observation
said. The mapping layer is where the platform's opinions about it live, which is exactly why
it must sit below identity and not inside it.





