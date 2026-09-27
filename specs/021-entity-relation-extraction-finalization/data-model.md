# Phase 1 Data Model: 021-entity-relation-extraction-finalization

**Date**: 2026-09-27 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)
| **Authority**: [repair/ARBITRATION.md](./repair/ARBITRATION.md) — binding on this file — over
`repair/A2-identity-subsystem.md` (identity), `repair/A4b-mapping-layer.md` (mapping),
`repair/A5-type-vocabulary.md` (types), `repair/A6-fr-triage.md` (traceability),
`repair/A7-migration-021.md` (migration) and `repair/A8prep-ownership-and-dag.md` (ownership, DAG)

This document defines the entities, their fields, and the identity rules. Everything here is
derived from the code at HEAD `0056665` plus [research.md](./research.md); where it changes an
existing type, the change and its reason are both stated.

## 0. Conventions, and one number that is deliberately absent

**These types remain distinct** (INV-001, INV-002, INV-003, brief §3). The count is deliberately
**absent**: it was stated four different ways across the artefact set — 7 in this file's own former
header, 8 in INV-001, 9 in the chain that followed, 12 in the approved diagram (A8prep DM-8) — and
a number carried inside a structural invariant is a number that drifts. The count is carried once,
in the two chains below, and the chains are the assertion.

**The relation chain** (brief §101, §102, §103):

```text
Observation → Mention → RelationSignal → RelationCandidate → RelationClaim → GraphEdge/HyperEdge
```

**The entity chain** (brief §101, §102):

```text
Observation → TypeSignal → TypeAssertion
```

`TypeHypothesis`, `PredicateHypothesis` and `PredicateSignature` are **nested value objects, not
stages**. Brief §103 names `PredicateHypothesis`, `PredicateSignature`, `TemporalHypothesis` and
`RelationParticipant` in its nested/value-object list; `TypeHypothesis` is structurally the same
object as `PredicateHypothesis` and brief §3 already places it among the concepts that must stay
distinct. `PredicateSignature` is additionally a **field declared by** a `RelationSignal`, never a
stage the pipeline produces — the diagram's edge is *declared by, not produced as a separate stage*
(A8prep DM-4), which is why FR-087 stores it as columns on `relation_signal` and why no
signature-keyed store row exists.

### 0.1 Requirement numbering, and why this file cites the ids it does

**Two requirement numbers in the `FR-1xx` range are void.** `ARBITRATION.md`, section 1: the
first two of them, proposed independently by A2 and by A6, are **both void**; each proposal takes its
**A8prep-allocated** number instead. The allocation is a band per agent: A2 owns the identity band
and the `FR-085`…`FR-089` block; A5 owns the type band `FR-029`…`FR-039`; A4b owns the
predicate/claim band `FR-021`…`FR-028`, the producer band `FR-040`…`FR-054` and `FR-090`/`FR-091`;
A7 owns `FR-059`…`FR-062`, `FR-096`/`FR-097` and `FR-113`/`FR-114`. Those replacement requirements
are **not yet minted**, so this file cites the requirement each one *replaces* and names the band,
rather than citing a number that does not exist.

**A second phantom is also gone.** The number at brief §103 was read as a requirement id in four
places; it is a brief section number, not a requirement. `ARBITRATION.md`, section 1 — no agent may
claim that id until the checker reports it clean. This file therefore cites brief §103, never a
requirement id.

**A third id is a tombstone.** The letter-suffixed id in the type/relation band is absorbed into
`INV-002` and carries **zero normative references** (`ARBITRATION.md`, section 2); the
type/relation policy it carried survives as FR-038 plus the brief §104 statement in part 10.3 of
this file. It is named here only as history, never as a requirement target.

**Two namespaces, one rule.** A bare `§N` in this file is a numbered heading in `input.md`; a
reference to a part of *this* document is written **`part N`**, so the two can never be confused.
The `B. Relation interpretation` heading under section 1 of `input.md` is an **unnumbered**
subsection, so a citation that reads as a lettered subsection there is a phantom.

---

## 1. `PredicateSignature` (v2 — the identity carrier)

This is the single most load-bearing type in the feature: it is the sole predicate term in
`logical_candidate_id`. It is derived **before** ontology mapping and is never re-derived from a
mapping, a registry, an operator list or a learned model (§18, §19, §20).

```python
IDENTITY_SCHEMA_VERSION = "cand-logical-2"
"""Version of the identity material's shape. Bumped when a key is added or removed from the
identity projection, never when a rule's content changes — a rule change bumps the rule's own
version field instead."""


@dataclass(frozen=True, slots=True)
class ArgumentSlot:
    """A canonical, structural argument position: ``A0``, ``A1``, ``A2``, …

    NOT an ontology of reality — see part 2.3. Ordered by the wrapped integer, never by the token
    text: ``A10`` sorts after ``A2``, and a string sort places it before. That is not a cosmetic
    difference; it changes the canonical material.
    """

    index: int

    def __post_init__(self) -> None:
        if self.index < 0:
            raise SignatureContractError("negative_argument_slot", f"index >= 0, got {self.index}")

    @property
    def token(self) -> str:
        return f"A{self.index}"

    def __lt__(self, other: "ArgumentSlot") -> bool:
        return self.index < other.index

    def to_identity(self) -> str:
        return self.token


class ConstructionFrame(StrEnum):
    """The construction a predicate was realised in, as a closed structural vocabulary.

    ``VERB_PASSIVE_AGENT`` is an OBSERVED frame. It is admissible on
    ``RelationSignal.observed_construction_frame`` and is **never** admissible on a
    ``PredicateSignature.construction_frame``, because voice handling demotes it to
    ``VERB_ACTIVE_TRANSITIVE`` at step V1 (part 3). Carrying the observed passive frame in the
    signature is precisely the defect that keeps an active and a passive realisation apart, and
    ``verify_canonical_frame()`` exists to make that unmissable.
    """

    # — the one demotion, per part 3 —
    VERB_PASSIVE_AGENT = "verb_passive_agent"           # observed only

    # — canonical frames: one per construction brief §29 names, plus two sub-frames required to
    #   be total. No construction outside this enumeration is supported (part 3.5). —
    VERB_ACTIVE_TRANSITIVE = "verb_active_transitive"
    VERB_ACTIVE_INTRANSITIVE = "verb_active_intransitive"
    COPULA_PREDICATIVE = "copular_predicative"
    COPULA_PREDICATIVE_NOUN = "copular_predicative_noun"   # "is a founder of Acme"
    NOMINAL_OWNER_OF = "nominal_owner_of"                  # "John, CEO of Acme,"
    NOMINAL_POSSESSIVE = "nominal_possessive"              # "Acme's founder John Smith"
    APPOSITIVE_ROLE = "appositive_role"                    # "John Smith, CEO of Acme,"
    PREP_PHRASE_HEAD = "prep_phrase_head"                  # "John works at Acme."
    RELATIVE_CLAUSE = "relative_clause"                    # "John, who founded Acme,"

    @property
    def is_observed_only(self) -> bool:
        return self is ConstructionFrame.VERB_PASSIVE_AGENT


class ArgumentMarker(StrEnum):
    """The closed inventory of function words that mark an argument in a canonical frame.

    A CLOSED, VERSIONED INVENTORY, not a mapping. There is deliberately no alias table and no
    member is ever folded onto another: ``by`` is not ``with``, ``of`` is not ``for``. A
    preposition outside this inventory is ``UNSUPPORTED_CONSTRUCTION`` (part 3.5), never ``NOMARK``
    and never a guess. This is the only lawful form of FR-003's "preposition normalization" and
    "particle normalization": **form** normalisation (NFKC, casefold) over a closed set, never
    cross-word folding. A field that folded ``at`` to ``for`` would be the forbidden table under
    a different field name.
    """

    NOMARK = ""            # structurally unmarked (a canonical-active subject, e.g.)
    ABOUT = "about"
    AS = "as"
    AT = "at"
    BY = "by"
    FOR = "for"
    FROM = "from"
    IN = "in"
    INTO = "into"
    OF = "of"
    ON = "on"
    ONTO = "onto"
    TO = "to"
    WITH = "with"


@dataclass(frozen=True, slots=True)
class PredicateSignature:
    """The structural, language-normalised projection of ONE predicate realisation.

    Field order is the identity order: language, lemma, frame, markers, slots, then the two
    rule-set versions. Every field participates in identity except the last two, which participate
    by *pinning* the first five — a signature with an empty version string is a contract error,
    never a legacy row silently upgraded (part 2.4).
    """

    language: str
    predicate_lemma: str
    construction_frame: ConstructionFrame
    argument_markers: tuple[ArgumentMarker, ...]        # parallel to canonical_argument_slots
    canonical_argument_slots: tuple[ArgumentSlot, ...]  # contiguous from A0; len >= 2
    voice_normalization_version: str
    predicate_normalization_version: str

    # — methods, not fields —

    @property
    def arity(self) -> int:
        return len(self.canonical_argument_slots)

    def identity_projection(self) -> dict[str, object]:
        """The exact dict that enters ``canonical_material`` in part 5. Nothing else may."""
        return {
            "language": self.language,
            "predicate_lemma": self.predicate_lemma,
            "construction_frame": str(self.construction_frame),
            "argument_markers": [str(marker) for marker in self.argument_markers],
            "canonical_argument_slots": [slot.to_identity() for slot in self.canonical_argument_slots],
            "voice_normalization_version": self.voice_normalization_version,
            "predicate_normalization_version": self.predicate_normalization_version,
        }

    def content_key(self) -> str:
        return digest128(canonical_material(self.identity_projection()))

    def rendered_predicate(self) -> str:
        """A human-readable rendering. **NOT identity** — used for the derived
        ``normalized_predicate`` / ``normalized_form`` reads and for logs.

        Form: ``<lemma>(<slot>:<marker>,<slot>:<marker>,…)``, marker omitted when NOMARK.
        ``"John acquired Acme."`` → ``"acquire(A0:,A1:)"``.
        """
        args = ",".join(
            f"{slot.token}:{marker if marker is not ArgumentMarker.NOMARK else ''}"
            for slot, marker in zip(self.canonical_argument_slots, self.argument_markers, strict=True)
        )
        return f"{self.predicate_lemma}({args})"
```

### 1.1 The v1 fields, and where each one went

v1 (the previous part 1) declared seven fields. Every one is accounted for:

| v1 field | Disposition in v2 | Reason, stated once |
|---|---|---|
| `normalized_predicate: str` | **REPLACED** by `predicate_lemma: str` | A "normalised predicate" that is a free string is the forbidden table waiting for a contributor. Its only lawful normalised form is a lemma from the generated morphology table (part 1.5), and that is what `predicate_lemma` is. Two of the field's jobs (NFKC/casefold, "verb-normalised") are the *procedure*, and a procedure belongs in a versioned rule set, not in a field. |
| `arity: int` | **DERIVED** as `len(canonical_argument_slots)` | Carrying both invites a state where they disagree, and that disagreement is a silent identity fork. A property cannot drift from its source. |
| `role_names: tuple[str, ...]` | **REPLACED** by `canonical_argument_slots: tuple[ArgumentSlot, …]` | Free-text role names are surface vocabulary. `purchaser` vs `buyer` would fork the logical id — the exact defect the feature destroys. The slot is structural, closed and versioned (part 2). |
| `argument_shape: tuple[str, ...]` | **MOVED OUT** to `RelationParticipant.argument_shape` and **excluded from identity** | Shape is a fact about a *referent*, not about the predicate. If it entered identity, a reclassification of a mention in the type layer would fork a relational identity — two subsystems' changes coupled through a digest. The participant fingerprint (part 4.3) therefore excludes it explicitly. |
| `direction: DirectionHypothesis` | **DERIVED** from `(canonical_argument_slots, commutative_slots)`; retained only as a read-only projection | It can disagree with the slot order, and that disagreement is an identity fork. The validator is `verify_direction_agrees_with_slots()` (part 2.5). |
| `polarity: Polarity` | **MOVED OUT** to `RelationCandidate.polarity` | Polarity is the structure of the *assertion*, not of the *predicate*. Brief §109 Case H requires `predicate = acquire` for "John did not acquire Acme", i.e. the same predicate under the opposite polarity — so polarity on the signature would make the same predicate two predicates. FR-002 and §19 both require polarity in logical identity, and it is there, on the candidate. |
| `schema_version: str = "1"` | **REMOVED** | It is the *operator* version, so a hypothesis read under a newer operator contract is a new reading of the same hypothesis, not a new hypothesis (`relation_candidate.py:510-512`). Putting it on the signature would move the operator version into the identity term, which is the same defect as carrying `relation_ref`. The signature's schema identity is the pair `(voice_normalization_version, predicate_normalization_version)`. |

### 1.2 What a signature deliberately does NOT carry — the exclusion classes

Seven classes, each with the reason stated once. This list is **total** for the signature.

| Class | Absent members | Why |
|---|---|---|
| **1. Raw words** | `raw_surface`, `predicate_surface`, `relation_surface`, `trigger_span`, `supporting_spans` | Raw words are evidence, never identity (FR-001, §17, §19, §23). §18's own worked requirement is that two *different* surface strings produce one signature while "retaining two distinct surface observations: as evidence". A surface inside the signature makes that arithmetically impossible. A span is a location in one document; one logical configuration observed in two documents has two spans and one id. |
| **2. Producer identity** | `producer_ref`, `producer_version`, `extraction_rule_id`, `extraction_method` | FR-001 excludes `producer_ref` and `producer_version` outright, and §23 excludes the rest. `signal_id` is *supposed* to be producer-specific (FR-006, §24); putting the producer in the *candidate's* logical term would extend producer scope from the observation level to the hypothesis level, breaking US5 and SC-005. |
| **3. Reference collections** | `evidence`, `observation_refs`, `evidence_refs`, `signal_refs` | FR-001, §23. Which observations back a hypothesis is a separate fact that grows; putting it in the logical term would make a second producer mint a second hypothesis instead of a second reading — the opposite of §43's "ONE logical candidate / MANY signals". |
| **4. Scoring** | `confidence` | FR-001, which names `confidence` explicitly. A re-scoring pass must not mint a new relation, or every ranking change forks the graph (`relation_identity.py:289-292`). |
| **5. Mapping and ontology material** | `relation_ref`, `relation_type`, `alternative_refs`, `mapping_evidence_refs`, `resolution_state`, any normalised-predicate **mapping**, any normalised raw-surface **table of near-meaning words** | Mapping to a known operator is a later, versioned step (R-002 point 4: "The signature is derived before ontology mapping, not after"). Keying on it would re-split one hypothesis into two the moment a regime recognised it — the exact failure `relation_candidate.py:1119-1126` documents. A mapping inside the identity term means the identity *is* the mapping, so the mapping can no longer be revised, contradicted, or attributed. |
| **6. Referential identity** | any entity id, any mention ref, any `ENT-`/`RES-` literal | `Mention ≠ Entity` (INV-001). The signature describes the *shape* of a reading. Participants live on the binding and enter identity through the fingerprint (part 4). |
| **7. Temporal data** | `temporal` markers, event time | Temporality is orthogonal to arity and to predicate structure. §109 Case D's `time = 2020` is a `TemporalHypothesis` on the candidate and is revision material. A year inside the predicate would make "sold in 2020" and "sold in 2021" different predicates, which is a category error. |

### 1.3 Reconciliation with FR-003's nine required fields, one by one

`spec.md:383-386` verbatim: "**FR-003**: System MUST provide a deterministic `PredicateSignature`
carrying **at least** language, normalized trigger, lemma, normalized frame, normalized argument
roles, voice normalization, preposition normalization, particle normalization and event-class
hint. It MUST NOT be a `RelationRef` and MUST NOT be a semantic ontology concept. (§18)"

`input.md` §18 says **"It may contain"** — a list, not a mandate. FR-003 promoted a permissive list
to a floor, and two of its nine items cannot be carried at all without putting a semantic claim
into the identity term. FR-003 therefore needs correction, and the correction is one disposition
per field.

| # | FR-003 field | Disposition | v2 field or type | Justification |
|---|---|---|---|---|
| 1 | `language` | **MAPPED** | `language: str` | Kept verbatim. A cross-lingual pair is two signatures, because cross-lingual merging is a semantic claim and §20 reserves that to explicit mapping. |
| 2 | `normalized_trigger` | **REMOVED** as a field, merged into #3 | — | The trigger is a surface token. Normalising it either yields the lemma, in which case the field is redundant with #3, or yields a function-word residue, in which case it is #7 + #8 and carrying it twice doubles the surface for no structural gain. The *procedure* is retained and versioned in `predicate_normalization_version`. |
| 3 | `lemma` | **MAPPED** | `predicate_lemma: str` | Kept, and promoted to the sole predicate term. |
| 4 | `normalized_frame` | **MAPPED, TYPE CHANGED** `str` → `ConstructionFrame` | `construction_frame` | A free-text frame template is free-text identity: two implementations would spell the same frame differently and fork every id. A closed enumeration makes the frame space enumerable, testable and diffable. The frame is also **canonical, not observed** (part 1) — that is what makes the active and passive realisations meet. |
| 5 | `normalized_argument_roles` | **MAPPED, TYPE CHANGED** `str` → `ArgumentSlot` | `canonical_argument_slots` | This is the one `PredicateSignature` field FR-003 names that is **forbidden** from being free text, and the type change is the enforcement. "Normalized" here means *structurally assigned*, not *lexically harmonised*: `purchaser` and `buyer` both become `A0` / `A1` / `A2` according to where they sit in the construction, and which one they become is decided by the parse, not by a vocabulary. |
| 6 | `voice_normalization` | **MAPPED, TYPE CHANGED** `bool`/`str` → `str` (a version) | `voice_normalization_version` | A boolean is not reproducible: two signatures differing only in whether the rule ran are indistinguishable in the record, so the identity cannot be re-derived later. A version string is reproducible. The *result* of the rule is not a field because it is expressed by fields 4 and 5. |
| 7 | `preposition_normalization` | **MERGED with #8**, TYPE CHANGED `str` → `ArgumentMarker` | `argument_markers` | Prepositions and particles are the same class of thing — function words marking argument structure. Splitting them buys nothing. The lawful normalisation is form-only over a closed inventory. |
| 8 | `particle_normalization` | **MERGED with #7** | `argument_markers` | As above. |
| 9 | `event_class_hint` | **REMOVED** | — | An event class ("transfer", "control", "acquisition") is a semantic category, and a *hint* is a mapping. §18 forbids the signature from being a semantic ontology concept and §20 forbids merging on anything but deterministic normalisation or explicit semantic mapping. A registry lookup in the identity term would also break the invariant in part 5.3 outright. §109 Case D is still satisfied without it: "John sold Acme to Microsoft" is carried by frame + markers + slots — `VERB_ACTIVE_TRANSITIVE`, markers `("", "", to)`, slots `(A0, A1, A2)` → seller / asset / buyer with no binary collapse and no event class. |

**Reconciliation count, as the brief for this pass requires it to be shown: 4 mapped, 2 merged,
2 removed, and the type changes named.** Mapped without a type change: `language`,
`predicate_lemma`, `voice_normalization_version`, and `argument_markers` (the merged carrier).
Mapped **with** a type change: `ConstructionFrame` (for the frame), `ArgumentSlot` (for the
argument roles), `ArgumentMarker` (for the merged function-word field). **Merged:** #7 and #8 into
one `argument_markers` field. **Removed with no residue:** `normalized_trigger` (folded into the
lemma at #3) and `event_class_hint`. FR-003's replacement text is the `PredicateSignature`
field-set requirement, and it takes A2's
A8prep-allocated number in the `FR-001`–`FR-007` band (part 0.1); it is not yet minted, so this file
does not cite a number for it.

### 1.4 Normalisation is one function, versioned, generated

The predicate term of `logical_candidate_id` is `predicate_lemma`, and the lemma table is a
**generated** artefact: regular inflection rules plus an explicitly enumerated list of derivation
suffixes, with a committed `LEMMA_TABLE_DIGEST`. There is no row type that maps one base lemma
onto a different base lemma, so the forbidden table is not merely discouraged here — it is
**unrepresentable in the data structure**. Adding one changes the committed digest and fails
`test_lemma_table_matches_its_committed_digest`.

| # | Rule | Where it now lives | Example |
|---|---|---|---|
| N1 | Unicode NFKC, then casefold | `normalize_surface_for_fingerprint` (participant side) and the casefold inside the lemma lookup | `Café` → `café` |
| N2 | Collapse internal whitespace, strip edge punctuation | as N1 | `  "Works For" ` → `works for` |
| N3 | **Voice handling only**: a passive clause with an overt `by`-agent maps to its active canonical frame, moving the *arguments* and not rewriting the sentence | `normalize_voice` V1 + V2 (part 3) | `Asset was acquired by Company` → `acquire(A0:Company,A1:Asset)` |
| N4 | Function-word marking is recorded against a **closed inventory**; a word outside it is `UNSUPPORTED_CONSTRUCTION` | `ArgumentMarker` | `John works at Acme` → marker `at`; `by` is never folded to `with` |
| N5 | **RETIRED FROM THE IDENTITY PATH — no such table, at this layer, ever.** The rule number is retired, not reused, and N6 keeps its number so every existing citation keeps its target. | — | `owns` and `controls` remain two lemmas, therefore two signatures, therefore two logical ids, always |
| N6 | **REMOVED from the signature**: argument shape is a fact about a referent, lives on `RelationParticipant`, and is excluded from the participant fingerprint so a type reclassification cannot re-key a relation | `RelationParticipant.argument_shape` | `40%` → `value`, recorded on the participant, never in identity |

**Where N5's content went, and why that is the right layer.** A table asserting that two base
lemmas mean one relation is a *claim about a correspondence*, and such a claim is a **mapping**:
dated, reviewable, citable, superseded, and a *revision* of a hypothesis rather than
its identity. Keyed into the identity term it made the predicate term depend on an artefact of
interpretation — the same failure as a model artefact in this position, and worse, because a model
carries its own provenance and a table looks like data. FR-004, §20, US2 Acceptance 3 and
constitution Domain Invariant 3 each forbid it, and the constitution's Governance clause names
entity resolution as ADR-requiring. Part 12 is where such a claim lives, and it merges nothing there.

**A passive with no overt agent is `UNSUPPORTED_CONSTRUCTION`, not a guess** (part 3.5). Deciding what
an elided passive agent is would be a semantic inference, and therefore a mapping.

### 1.5 The generated-table discipline

`predicate_normalization_version` versions two artefacts, both **generated** and both with a
**committed digest**, so adding a row is a visible diff against a golden value rather than a
silent corpus shift — the same discipline R-001 requires of a parser change:

| Artefact | Generated from | Committed golden | Test |
|---|---|---|---|
| `LEMMA_TABLE: Mapping[str, str]` | the regular inflection rules + a pinned irregular-form list, then the enumerated `DERIVATION_SUFFIXES` | `LEMMA_TABLE_DIGEST` — a `digest128` over `canonical_material(sorted(LEMMA_TABLE.items()))` | `test_lemma_table_matches_its_committed_digest` |
| `ArgumentMarker` inventory | hand-enumerated closed set (part 1) | part of the same digest | `test_argument_marker_inventory_is_closed` |

`DERIVATION_SUFFIXES` is an explicitly enumerated list of `(suffix, rule)` pairs — `or`, `er`,
`ion`, `ment`, `ation`, `ing`, `ee` and their orthographic variants — applied in a fixed order.
That is what lets `originator` lemmatise to `originate`, so §109 Case C and SC-002 work, **without**
a table of cross-lemma rows: derivation is morphology, and morphology has no such row type.

> **The enforceable statement, which is the whole of the N5 removal in data form:** the lemma
> table contains no row `(surface, lemma)` in which `surface` is not a morphological form of
> `lemma`.

Test: `test_lemma_table_has_no_cross_lemma_row` — for every pair of rows sharing a `lemma`, the
surfaces must differ only by an inflection or an enumerated derivation of that lemma.

### 1.6 The two derived normalised-predicate reads

There is exactly **one** normaliser in the platform, it lives in
`apps/shared/domain/predicate_signature.py`, and it is versioned. Two existing fields are inert
today and both would become a second normaliser the moment anyone used them
(`predicate_hypothesis.py:152-154` sets `normalized_form` to a verbatim copy of the surface, and
there is no normalisation function in `domain/` or `semantic/`). Both therefore become **derived
read-only views**, and neither may be a constructor input:

```python
@property
def normalized_form(self) -> str:            # on PredicateHypothesis
    """Derived view of the one normaliser. Never an input.

    Falls back to ``surface_form`` when no signature is present. A ``normalized_form=``
    constructor keyword is REFUSED, so a caller cannot smuggle a second normaliser back in
    through the front door.
    """
    if self.predicate_signature is None:
        return self.surface_form
    return self.predicate_signature.rendered_predicate()


@property
def normalized_predicate(self) -> str:        # on RelationSignal
    """Derived. ``""`` when no signature — which is the honest answer for an unsupported
    construction (part 3.5), and is a materially different answer from a copy of the surface."""
    return "" if self.predicate_signature is None else self.predicate_signature.rendered_predicate()
```

Tests: `test_normalized_predicate_is_a_derived_view_of_the_signature`,
`test_predicate_hypothesis_normalized_form_no_longer_copies_the_surface`,
`test_predicate_hypothesis_refuses_a_constructor_supplied_normalized_form`,
`test_normalized_predicate_is_empty_when_there_is_no_signature`.

### 1.7 Unknown predicates are first-class

`"John is the originator of Acme."` yields `language="en"`, `predicate_lemma="originate"` (via the
enumerated `-or` derivation rule), `construction_frame=copular_predicative`,
`argument_markers=("", "of")`, `canonical_argument_slots=(A0, A1)`, plus both normalisation
versions; `relation_ref=None`, `resolution_state=UNKNOWN`. `rendered_predicate()` is
`"originate(A0:,A1:of)"`. That is a complete, durable hypothesis — the §90 unknown test, end to
end — and `polarity` and `direction` are on the **candidate**, not the signature, so the predicate
is the same under assertion and under denial.

---

## 2. `RoleBinding` v2 — the only role datum identity may read

### 2.1 The dataclass

```python
@dataclass(frozen=True, slots=True)
class RoleBinding:
    """One participant's placement in one canonical reading.

    Exactly one of these five fields reaches identity, and the two text fields are evidence.
    ``canonical_argument_slot`` is the sole role datum the logical identity is allowed to
    read (part 4.2).
    """

    surface_role: str
    """FREE TEXT. EVIDENCE ONLY. The words the observation used: "buyer", "purchaser",
    "the CEO of". Never enters ``logical_candidate_id``. This is the field a later regime reads
    to decide the same words a different way, and the field a reviewer reads to find out what an
    ``A2`` slot was called. Retained verbatim as a durable ``Text`` column; a mapping that is
    re-evaluated later needs the words to still be there."""

    role_hypothesis: str
    """FREE TEXT. A producer's guess at the role, retained verbatim and never consulted by the
    normaliser or the ordering rule. Two producers guessing "seller" and "vendor" for the same
    A1 produce ONE logical candidate, which is §43's "ONE logical candidate / MANY signals" made
    mechanical. A guess is a guess: a ``role_hypothesis`` is not a ``surface_role``, and neither
    is a slot."""

    canonical_argument_slot: ArgumentSlot
    """STRUCTURAL, VERSIONED, and the only role datum admitted to identity. Assigned by
    ``normalize_voice`` (part 3) from the parse, never from a vocabulary. See part 2.3."""

    normalization_version: str
    """The ``voice_normalization_version`` that assigned ``canonical_argument_slot``. Not
    decoration: it is the per-binding half of the versioning discipline in part 2.4, and it is what
    lets a store detect a mixed-version participant set instead of assembling one."""

    evidence: tuple[str, ...]
    """EVIDENCE ONLY. Sorted and canonicalised on construction like every other reference
    collection, and revision material. Never identity."""
```

### 2.2 The rejected design this replaces

v1 part 2 put a free-text `role: str` on the participant, which put free text inside
`logical_candidate_id` — relocating the exact defect the feature exists to destroy, because
`purchaser` vs `buyer` would fork the logical id. The replacement keeps every role word, as
evidence, and makes exactly one datum identity-bearing: a **versioned canonical argument slot**
(`A0`, `A1`, …). FR-009 is amended accordingly — its `slot` MUST be a structural `ArgumentSlot`
drawn from the reading's `canonical_argument_slots` and MUST NOT be a free-text role name, and
`role_hypothesis` MUST be retained as evidence and MUST NOT enter logical material.

### 2.3 Why `A0` / `A1` / … is a *formula*, not a named set

This has to be defensible against INV-001, INV-002 and Domain Invariant 3. Six properties, each
with a named test:

| # | Property | Consequence | Test |
|---|---|---|---|
| 1 | **Scoped to one signature.** `A0` means "the first argument of the construction whose `construction_frame` is F", and has no meaning outside that signature. There is no global registry, no namespace, no `core:` prefix, no hierarchy, no lookup table. | A slot cannot be resolved, blocked, expanded or queried. There is nothing to resolve *to*. | `test_argument_slot_space_is_unbounded_and_unregistered` |
| 2 | **Derived from a position in a parse, not from a judgement about the referent.** In `Company acquired Asset`, `A0 = Company` because Company occupies the `nsubj` position — not because Company is judged to be an agent, an organisation or a controller. | A slot states where something sat, which is observable. It states nothing about what the something is, which would be a claim. | `test_slot_assignment_reads_dependency_position_not_type` |
| 3 | **A total order over the positions of one construction, and the space is unbounded in `k`.** The admissible values are `{A_k : 0 ≤ k < arity}`. Nothing enumerates them, so there is no "permitted values" list to mistake for an ontology. | A type pack has `core:Organization`, `core:Person` — a *finite named set* of claims. A slot set has a **formula**. | `test_argument_slot_space_is_unbounded_and_unregistered` |
| 4 | **The same mention may occupy different slots in different signatures.** In `Company acquired Asset` the mention for Company is `A0`; in `Asset acquired Company` it is `A1`. | Slots are per-reading, not per-entity. An entity has no slot. This is the line INV-001 draws, and it is why `ArgumentSlot` is not on `Mention` and not on `TypeHypothesis`. | `test_same_mention_may_occupy_different_slots_in_different_signatures` |
| 5 | **A slot carries no type, no confidence, no truth and no provenance.** It is an `int` and a token. | Nothing can be inferred from a slot. A candidate in `A1` is not thereby a "thing of class 1". | `test_argument_slot_carries_no_type_confidence_or_truth_claim` |
| 6 | **Occupants of one slot need not share a type.** `John sold Acme to Microsoft` puts a person, an organisation and an organisation in three slots. | Slots and types are orthogonal, so the type layer's work proceeds with no effect on relational identity — reinforced by the fingerprint exclusion in part 4.3. | `test_slot_occupants_need_not_share_a_type` |

**The one-line answer to "isn't `A0` an ontology?":** `A0` is a position in a sentence's argument
structure. It is derived by reading a parse. It asserts nothing about the world, and no vocabulary
anywhere assigns meaning to it.

### 2.4 The versioning rule, verbatim

The convention is identified by `voice_normalization_version`, the version of `normalize_voice`,
which is what assigns the slots.

> A change to the slot-assignment convention (for example: "for a ditransitive, `A1` is the theme
> and `A2` is the goal" becoming "…`A1` is the goal and `A2` is the theme") MUST
>
> 1. bump `voice_normalization_version`;
> 2. be recorded in the signature's own durable columns, so a stored signature is
>    self-describing and re-derivable from the record alone (FR-060: a digest may identify data;
>    it may not be the only copy required for reconstruction);
> 3. change `ArgumentSlot.__lt__`'s contract only if the *token* form changes, which requires a
>    major `IDENTITY_SCHEMA_VERSION` bump; and
> 4. produce a **different `logical_candidate_id`** for readings re-derived under the new
>    convention.

Point 4 is not a cost, it is the point. A reading whose slots were assigned under an old
convention is a *different structural claim* from one assigned under a new convention, and the
platform must not silently re-key history. The two coexist as two candidates, which is visible,
rather than one candidate whose id moved, which is not.

The corollary that makes the version load-bearing rather than decorative:

> A signature or binding whose `voice_normalization_version` is `""` is a **contract error**
> (`unversioned_signature` / `unversioned_role_binding`). It is **never** defaulted to "the
> current version" and **never** migrated with a guess.

**Why there is no back-compatible default:** a default is a guess, and a guessed version assigns
an id whose record cannot justify it. The constitution's Additional Constraints require a
**quarantine** for exactly this class of row ("rejected candidates are never auto-deleted;
replay/re-evaluation supported"), so the outcome is: the row is **quarantined, reported and
replayable**. Tests: `test_signature_without_a_normalization_version_is_a_contract_error`,
`test_role_binding_version_must_match_its_signature`,
`test_changing_the_slot_convention_bumps_the_version_and_changes_the_logical_id`.

### 2.5 The agreement rules that keep slot, frame and arity from drifting

`verify_slot_version_agreement(signature, bindings)` **refuses a participant set assembled across
two normalisation versions**: a binding assigned by an older version and one assigned by a newer
one cannot be placed in a single canonical ordering, because "A1" does not mean the same position
under both. Assembling them would produce a canonical order that neither version would produce,
and therefore an id neither version can re-derive. Test: `test_mixed_normalization_versions_are_refused`.

`verify_signature_shape(signature, bindings, commutative_slots)` makes four total checks, each one
line and each with a named test:

1. `len(signature.canonical_argument_slots) == len(signature.argument_markers)` — the markers are
   parallel to the slots; a length mismatch is a truncated construction, not a relation.
2. `sorted(distinct slots of bindings) == list(signature.canonical_argument_slots)` and the slots
   are contiguous from `A0` — the signature carries the slot **skeleton**, the bindings carry the
   **occupants**, and the two may not disagree.
3. `signature.construction_frame.is_observed_only is False` — an observed passive frame on a
   signature would fork the active realisation from the passive one, which is the whole defect
   this subsystem exists to remove.
4. commutativity agrees with the declared shape: `commutative_slots` may only contain **occupied**
   slots; a declared commutative slot with one occupant is legal (a symmetric relation observed
   with one side elided); a declared commutative slot with zero occupants is a contract error
   (`empty_commutative_slot`); and `commutative_slots == set(occupied slots)` is exactly the
   condition under which `RelationArityMode.UNDIRECTED` is admissible — so `arity_mode` is
   *derivable* and never independently asserted.

---

## 3. `normalize_voice()` — the slot-assignment algorithm

**Source of the construction list: `input.md` §29 `SYNTACTIC PRODUCER`, not §22.** §22 is
`RELATION CANDIDATE = DURABLE HYPOTHESIS` and contains no construction list at all. §29's eight,
heading for heading: active, passive, copular, nominal, appositional, possessive, prepositional,
relative clause. The table below supports exactly those eight, plus the two sub-frames the
algorithm needs to be total, plus one construction deliberately excluded. §29's "Support at least"
permits more; §20 forbids more *merging*, so the extras are all **narrowing or structural**.

### 3.1 Signature, inputs and output

```python
class SyntacticConstruction(StrEnum):
    """The parse-level construction, as detected. This is the INPUT vocabulary and it is a
    superset of :class:`ConstructionFrame`; the mapping from one to the other is
    ``CANONICAL_FRAME_BY_CONSTRUCTION`` (part 3.4), and the only entry that differs is the passive
    demotion."""
    ACTIVE_CLAUSE, PASSIVE_WITH_AGENT, PASSIVE_NO_AGENT, COPULAR, COPULAR_WITH_NOUN_COMPLEMENT,
    BARE_NOMINAL, GENITIVE_NP, APPOSITIVE_NP, HEADLESS_PP, RELATIVE_CLAUSE, OTHER


@dataclass(frozen=True, slots=True)
class ArgumentObservation:
    """One argument as the PARSE sees it. Note what is absent: no role, no type, no semantic
    judgement. ``position_label`` is a dependency label, not a role."""
    position_label: str      # "nsubj" | "obj" | "nmod:by" | "nmod:of" | "nmod:to" | "case:gen" | …
    head_lemma_hint: str     # as tokenised, NOT lemmatised: V3 does the lemmatising
    function_word: str | None
    is_pronominal: bool      # True for an elided subject/object; V2 consumes it, never emits it


@dataclass(frozen=True, slots=True)
class SyntacticStructure:
    construction: SyntacticConstruction
    arguments: tuple[ArgumentObservation, ...]   # in UD child order
    head_function_word: str | None               # "was", "at", "of", None


@dataclass(frozen=True, slots=True)
class DependencyEdge:
    governor_label: str
    dependent_label: str
    relation: str            # UD-style: "nsubj", "nsubj:pass", "nmod:by", "obj", "case:gen", …


@dataclass(frozen=True, slots=True)
class DependencyStructure:
    edges: tuple[DependencyEdge, ...]             # in document order; the ORDER is load-bearing (V2)
    root: str                                    # the label of the head carrying the reading


@dataclass(frozen=True, slots=True)
class PredicateHead:
    observed_form: str                           # "acquired", "acquire", "acquires"
    language: str                                # BCP-47 primary subtag; only "en" ships in 021


@dataclass(frozen=True, slots=True)
class CanonicalArgumentAssignment:
    """The output. Note what is NOT here: no commutativity, no polarity, no direction, no
    mention ref, no surface. See part 3.6."""
    construction_frame: ConstructionFrame         # CANONICAL — never an observed-only frame
    canonical_argument_slots: tuple[ArgumentSlot, ...]
    argument_markers: tuple[ArgumentMarker, ...]  # parallel to slots, strict=True
    normalization_trace: tuple[str, ...]          # ordered step ids; corpus-visible, not identity


def normalize_voice(
    predicate: PredicateHead,
    syntactic_structure: SyntacticStructure,
    dependency_structure: DependencyStructure,
) -> CanonicalArgumentAssignment:
    """The ONLY function in the platform that assigns canonical argument slots."""
```

**Two independent implementations agree** because there is no judgement in the function: it
consumes a *declared* construction and a *declared* argument list, applies seven ordered steps,
and the only inputs it does not consume are things that would require a judgement. The parse is
produced elsewhere; the frame detection is a table lookup over the declared construction; the
lemma comes from a generated table.

### 3.2 Scope declaration — the one and only unification

> **P-CANON (Principle of Canonical Voice).** `normalize_voice` performs **voice handling only**: a
> passive clause with an overt `by`-agent and its active counterpart produce the same canonical
> argument assignment, and nothing else is unified.

Every other §29 construction receives **its own** `construction_frame` value in the signature.
"John, who founded Acme" does not collapse with "John founded Acme". "John is the CEO of Acme"
does not collapse with "John, CEO of Acme". "John works at Acme" does not collapse with "John works
for Acme" — `at` and `for` are different `ArgumentMarker`s, and deciding they mark the same
argument is a lexical-semantic claim that §20 reserves to explicit mapping. Named test:
`test_works_at_and_works_for_are_distinct_signatures`.

**Why the scope is this narrow.** The justification is directional: **under-merging is visible as
two candidates; over-merging is invisible as a wrong merge.** §43 permits one candidate from many
signals "only when they describe the same relational configuration", so an unproven equivalence
produces a merge that cannot be undone and is not visible in the data. Voice demotion is
deterministic normalisation; a relative clause's relation to its matrix clause, a nominal's
relation to its clause, and a copula's relation to a bare nominal are all *claims about
equivalence*, and claims about equivalence are what part 12 is for — dated, attributed,
evidence-bearing, revisable and able to be wrong in public. Test enforcing the scope:
`test_normalize_voice_does_not_unify_anything_but_voice`.

### 3.3 The ordered steps, exact and in order

| Step | Id | Action | Failure |
|---|---|---|---|
| V0 | `V0.validate` | `language` must be a shipped language (`en` in 021). `syntactic_structure.arguments` must be non-empty. `dependency_structure.root` must label an argument. | `UNSUPPORTED_LANGUAGE` / `MALFORMED_STRUCTURE` |
| V1 | `V1.frame` | Look up `CANONICAL_FRAME_BY_CONSTRUCTION[syntactic_structure.construction]` (part 3.4). For `PASSIVE_WITH_AGENT` the result is `VERB_ACTIVE_TRANSITIVE` — **the demotion happens here, at the frame, not later.** | `UNSUPPORTED_CONSTRUCTION` (part 3.5) |
| V2 | `V2.assign_slots` | Take the slot sources from the table row, **in the order the row states them**, drop any source marked *consumed* (V1's demoted `nsubj:pass`), and number the survivors `A0, A1, …` contiguously. Multiplicity is preserved: two occupants of one source produce two slots with the same index, and the table row must say the slot is *coordinated*. | `SLOT_GAP` if numbering is not contiguous |
| V3 | `V3.lemmatise` | `predicate_lemma = LEMMA_TABLE.get(observed_form.casefold())`. Applied to the **predicate head only** — never to a participant, never to a function word, never to a second argument. An AUX (`be`, `get`, `become`) is **not** the predicate head when the clause has a participle; the participle is. | `UNSUPPORTED_LEMMA` |
| V4 | `V4.markers` | For each slot, in slot order, `argument_markers[i] = ArgumentMarker(head_function_word)` if the table row says that position is function-word-marked, else `NOMARK`. Any function word not in the closed inventory is a failure, **not** `NOMARK`. | `UNSUPPORTED_MARKER` |
| V5 | `V5.trace` | `normalization_trace` = the ordered step ids actually executed, e.g. `("V0.validate","V1.frame","V2.assign_slots","V3.lemmatise","V4.markers")`. Persisted, corpus-visible, **never identity**. | — |
| V6 | `V6.arity` | If fewer than 2 slots are occupied → `NO_CONFIGURATION` (part 3.7). | `NO_CONFIGURATION` |

**Two exact tie-breaks**, because "two independent implementations must agree" means the ambiguous
cases are specified rather than left to taste:

> **TB1 (copula vs active, for `become`).** V1's table is consulted in row order and the **first
> match wins**. `COPULAR` precedes `ACTIVE_CLAUSE`, so `John became a founder of Acme` is
> `COPULA_PREDICATIVE_NOUN` and `John became famous` is `VERB_ACTIVE_INTRANSITIVE`. The
> disambiguating syntactic test is presence of an NP / ADJ / PP complement, and that test is the
> table's *condition*, not an afterthought: a row that cannot be tested syntactically may not be in
> the table.
>
> **TB2 (order of non-slot arguments).** V2 takes arguments in `dependency_structure.edges` order,
> which is pinned document order, and **not** in the order of `syntactic_structure.arguments`.
> Where a construction's argument list is ambiguous under document order — a ditransitive with two
> `nmod:` arguments, e.g. `John sold Acme to Microsoft in 2020` — the tie-break is **`ArgumentMarker`
> ascending, then `position_label` ascending, byte-wise.** `in` < `to`, so `in 2020` sorts before
> `to Microsoft` and the temporal complement is assigned before the recipient. The temporal
> argument is then **dropped** (part 1.2 class 7: temporality is not predicate structure), and the
> trace records `"V2.drop_temporal"` so the drop is auditable rather than invisible.

The drop of a temporal complement is the one place V2 discards an argument, and it is recorded in
the trace because §109 Case D's `time = 2020` must remain recoverable — it is carried by the
candidate's `TemporalHypothesis`, and the trace says the signature layer saw it and did not put it
in the predicate.

### 3.4 The construction table, verbatim

`CANONICAL_FRAME_BY_CONSTRUCTION`, consulted in row order (TB1), versioned by
`voice_normalization_version`:

| Row | `SyntacticConstruction` | Syntactic condition | Canonical `construction_frame` | Slot sources, in order | Markers |
|---|---|---|---|---|---|
| 1 | `PASSIVE_WITH_AGENT` | head is a member of the closed AUX set `{be, get, become}`; a `nsubj:pass` dependent exists; a `nmod:by` dependent exists | **`VERB_ACTIVE_TRANSITIVE`** (demoted) | A0 = `nmod:by` head; A1… = the passive participle's remaining arguments in edges order. The `nsubj:pass` head is **consumed** and becomes A1 if it is the only remaining argument, else it is **re-emitted** as the first remaining argument. | A0 = `NOMARK` (canonical-active subject). Remaining slots take their own markers. The observed `by` is recorded in the trace and in evidence, **not** in the signature. |
| 2 | `COPULAR` | head is in the closed COPULA set `{be, remain, seem, become}`; no `nsubj:pass`; a `nsubj` and a predicate complement exist; the complement is a **bare NP** | `COPULA_PREDICATIVE` | A0 = `nsubj` head; A1 = the complement's own `nmod:of` head if the complement is an NP with an `of`-PP, else the complement head | A0 = `NOMARK`; A1 = `of` when the `of`-PP was followed, else `NOMARK` |
| 3 | `COPULAR_WITH_NOUN_COMPLEMENT` | as row 2 but the complement is a **derived nominal + adjacent `of`-PP** ("a founder of Acme") | `COPULA_PREDICATIVE_NOUN` | as row 2 | as row 2 |
| 4 | `ACTIVE_CLAUSE` | head is a non-AUX verb; a `nsubj` exists; ≥1 further argument exists | `VERB_ACTIVE_TRANSITIVE` | A0 = `nsubj`; A1… = remaining arguments in edges order, temporal complements dropped (TB2) | `NOMARK` for A0; each further slot takes its own `function_word` as an `ArgumentMarker` |
| 5 | `ACTIVE_CLAUSE` with no further argument | as row 4 with no further argument | `VERB_ACTIVE_INTRANSITIVE` | A0 only | `NOMARK` — **always yields `NO_CONFIGURATION` at V6** (brief §13 requires 2..N participants; a one-argument clause states a property, not a relational configuration) |
| 6 | `BARE_NOMINAL` | no finite head; the governor is an NP whose head noun has an `nmod:of` dependent | `NOMINAL_OWNER_OF` | A0 = the NP head; A1 = the `nmod:of` head | A0 = `NOMARK`; A1 = `of` |
| 7 | `GENITIVE_NP` | an NP with a `case:gen` dependent **and** a head NP on the possessed side ("Acme's founder John Smith") | `NOMINAL_POSSESSIVE` | **A0 = the head NP that the genitive modifies** (which may be the surface-left or surface-right NP); A1 = the genitive head. This reversal is the point: it normalises argument structure, not word order. | A0 = `NOMARK`; A1 = `NOMARK` (a genitive marker is structural, and the observed `'s` is evidence) |
| 8 | `APPOSITIVE_NP` | a comma-delimited `np:appos` dependent of a preceding NP, whose head noun has an `nmod:of` dependent | `APPOSITIVE_ROLE` | A0 = the matrix NP head; A1 = the `nmod:of` head | A0 = `NOMARK`; A1 = `of` |
| 9 | `HEADLESS_PP` | a PP with no `nsubj`, whose governor is a document-structure producer slot | `PREP_PHRASE_HEAD` | A0 = the `pobj`; A1 = the subject the producing channel declares for the governing slot | A0 = the `function_word`; A1 = `NOMARK` |
| 10 | `RELATIVE_CLAUSE` | a `reld:cl` dependent of an NP | `RELATIVE_CLAUSE` | the clause's own arguments, in rows 1/4 order, with the matrix NP **not** an argument | the clause's own markers |
| — | everything else | — | **`UNSUPPORTED_CONSTRUCTION`** | — | — |

Two rows are **added** beyond §29's eight, and each is added for a stated necessity, not for
convenience:

- **Row 3 `COPULAR_WITH_NOUN_COMPLEMENT`** is required for **row 2 to be total**. "John is the CEO
  of Acme" (row 2) and "John is a founder of Acme" (row 3) are different syntaxes, and row 2 as
  written would reject the second as unsupported. It is a *narrowing* change and it does **not**
  merge rows 2 and 3 with each other (part 3.2).
- **Row 10's matrix NP** is excluded from the slots because a relative clause's matrix NP is not
  an argument of the clause. That is why "John, who founded Acme" does not collapse with "John
  founded Acme": collapsing them requires the inference "the matrix NP is the relative clause's
  subject", which is true in the common case and false in the reduced-relative and adjunct cases,
  and a rule that is usually right is a guess.

The closed AUX set and the closed COPULA set are **grammar inventories**, not semantic
vocabularies, and their membership is versioned inside `voice_normalization_version`. `become`
appearing in both is resolved by TB1, not by preference.

### 3.5 Unsupported constructions: named, counted, never guessed

> `UNSUPPORTED_CONSTRUCTION` produces **no** `PredicateSignature`. It is **never** resolved by a
> fallback frame, a nearest-match frame, a default frame, a retry, a lexical-identity shortcut, or
> a syntactic guess. The reason code is persisted on the signal so the corpus can count
> occurrences by construction, so the gap is a *number* rather than a silence.

This is brief §30's rule applied at the right altitude: "For deterministic baseline, produce
useful relation signals even when parser output is unavailable. / A missing parser capability must
mean: `no syntactic signals` — **not**: `batch failure` — unless the contract explicitly says the
parser is mandatory."

Downstream, stated precisely because it is where a defect would re-enter:

- The signal is legal with an explicit observational basis and `predicate_signature=None` (brief §16,
  FR-013, FR-014), because FR-014's basis vocabulary includes "predicate text" — the words were
  seen; the structure was not.
- The signal **cannot** be grouped with a signal that has a signature. FR-027: "Distinct predicates
  over the same endpoints MUST remain distinct hypotheses. Equal endpoints MUST NOT merge them."
- The candidate survives with `predicate_state=UNKNOWN` (FR-023), the surface retained, and
  `logical_candidate_id` **not minted** (part 5.4).

Tests: `test_unsupported_construction_yields_no_signature`,
`test_unsupported_construction_is_never_guessed_into_a_frame`,
`test_unsignatured_and_signatured_readings_do_not_merge`.

### 3.6 What `normalize_voice` deliberately does NOT return

| Not returned | Why |
|---|---|
| `commutative_slots` | No grammar-derived construction is symmetric. Symmetry is a property of the *relation*, declared by a semantic contract, and §53 says verbatim: "Do not infer symmetry merely because the extractor did not know direction." Returning it from a syntactic function would be exactly that inference. It comes from the candidate's declared marker (part 4.5). |
| `polarity` | Assertion structure, not predicate structure (part 1.1). |
| `direction` | Derivable from slots + commutativity; an independent return value is a fork (part 2.5 check 4). |
| any mention ref or surface | The function is about the *predicate*; participants arrive separately and are bound by the assembler. |
| `observed_construction_frame` | It is the *observed* frame and belongs to the signal as evidence. Carrying it in the signature's identity projection is precisely what keeps the two realisations apart. |

Test: `test_normalize_voice_output_carries_no_participant_no_surface_and_no_symmetry`.

### 3.7 `NO_CONFIGURATION` — the honest answer for a one-argument reading

Separate from `UNSUPPORTED_CONSTRUCTION`, because the parse was fine and the outcome is a
*decision*, not a gap. `"Acme's ownership"` parses as row 7 with no head NP on the possessed side,
so one slot is occupied, so there is no relational configuration.

> A reading occupying fewer than 2 canonical slots yields `NO_CONFIGURATION`. It is **not** padded
> to arity 2 with a placeholder, and **not** given a null participant. "Acme's ownership" is a
> property of Acme, not a relation between two mentions.

Tests: `test_intransitive_reading_yields_no_configuration`,
`test_no_configuration_is_distinct_from_unsupported_construction`.

### 3.8 The worked derivation that makes the `SC-001` claim computable

**Active — `Company acquired Asset.`** V0 pass (`language=en`, two arguments, root labels the
clause); V1 row 4 → `VERB_ACTIVE_TRANSITIVE`; V2 A0 = `nsubj` head = Company, A1 = the remaining
argument = Asset, no temporal complement to drop → slots `(A0, A1)`; V3 `acquired` → `acquire` via
the regular `-ed` inflection rule; V4 A0 = `NOMARK` (subject, structurally unmarked), A1 =
`NOMARK` (no function word) → markers `(NOMARK, NOMARK)`.

**Passive — `Asset was acquired by Company.`** V0 pass; V1 construction `PASSIVE_WITH_AGENT`, row 1
→ `VERB_ACTIVE_TRANSITIVE` **demoted at the frame**; V2 A0 = `nmod:by` head = Company, and the
`nsubj:pass` head (Asset) is the only remaining argument so it is re-emitted as A1 → slots
`(A0, A1)`; V3 the head is the participle `acquired`, **not** the AUX `was` → `acquire`; V4 A0 =
`NOMARK` because the canonical-active subject is structurally unmarked, and the **observed** `by`
goes to the trace and to evidence, not to the signature.

Both produce the identical `identity_projection()`:

```json
{"argument_markers":["",""],
 "canonical_argument_slots":["A0","A1"],
 "construction_frame":"verb_active_transitive",
 "language":"en",
 "predicate_lemma":"acquire",
 "predicate_normalization_version":"pn-1",
 "voice_normalization_version":"vn-1"}
```

`rendered_predicate()` is `"acquire(A0:,A1:)"` — §18's `acquire(...)` in shape and content.

**`SC-001` status, stated without inflation.** The identity function is **computable**: the two
realisations above reach one `identity_projection()` with no fixture and no table lookup, and
`test_normalize_voice_collapses_active_and_passive` needs no corpus, no parser and no producer.
`SC-001` is **not yet reachable end to end**, because no producer parses a sentence and no lemma
table exists, and because the two realisations must be read by the *same* producer
(`test_sc001_corpus_pins_one_producer_for_both_realisations`). The end-to-end test is therefore
written now and carries `xfail(strict=True)` with reason `syntactic_producer_absent`; strict is
mandatory, because it makes an accidental pass an error rather than a silent success, and a named
task owns the transition. **No implementation wave may report `SC-001` as passing while the marker
is still `xfail`.**

---

## 4. `canonical_participant_ordering()` — the only ordering in logical material

### 4.1 Signature

```python
def canonical_participant_ordering(
    signature: PredicateSignature,
    commutative_slots: frozenset[ArgumentSlot],
    participants: Sequence[RoleBinding],
) -> tuple[CanonicalParticipant, ...]:
    """The ONLY ordering of participants admitted to logical material."""


@dataclass(frozen=True, slots=True)
class CanonicalParticipant:
    slot: ArgumentSlot
    participant_fingerprint: str      # 32 lowercase hex
    commutable: bool
```

**Binary** (`arity == 2`): order by `canonical_argument_slot` alone. There is nothing else to
order by, and no tie is possible unless both occupants share one slot, which is a contract error
(part 4.4). **n-ary** (`arity >= 3`): order by `(canonical_argument_slot.index,
participant_fingerprint)`.

### 4.2 The ordering steps, exact

| Step | Action |
|---|---|
| O1 | `verify_signature_shape(signature, participants, commutative_slots)` (part 2.5). A refusal here aborts ordering; nothing downstream sees a partially ordered set. |
| O2 | Group bindings by `canonical_argument_slot`. Preserve multiplicity: `list`, never `set` — the existing `logical_material` at `relation_identity.py:182` uses `sorted({…})`, which **deduplicates** (part 4.7). |
| O3 | For each occupied slot, sort its occupants ascending by `participant_fingerprint`, comparing the 32 lowercase hex **byte-wise** (`str` comparison). |
| O4 | Order the slots ascending by `ArgumentSlot.index` — the wrapped **integer**, never the token text. `A10` follows `A2`; a `str` sort places `"A10"` before `"A2"` because `'1' < '2'`, which is deterministic and semantically wrong. |
| O5 | Emit `(slot, participant_fingerprint, slot in commutative_slots)` per occupant, in slot order, occupants in fingerprint order. |

**Why a slot sort at all for a directed binary relation.** Because the slots *are* the direction.
`Company acquired Asset` → `(A0:Company, A1:Asset)`; `Asset acquired Company` →
`(A0:Asset, A1:Company)`. Two different material values, therefore two different logical ids —
which is §44 ("Different relations must not merge"), §52 ("Never canonicalize
`min(source,target)` / `max(source,target)` for directed edges") and SC-007 in one mechanism.

### 4.3 `stable_participant_fingerprint` — exactly what it digests, key by key

```python
def stable_participant_fingerprint(mention: ResolvedMention) -> str:
    """32 lowercase hex over the mention's own identity material, and nothing else.

    MUST digest, key by key:
      * ``mention_kind``       -> mention.kind
      * ``normalized_surface`` -> normalize_surface_for_fingerprint(mention.surface)
      * ``capture_ref``        -> mention.capture_ref
      * ``segment_ref``        -> mention.segment_ref
      * ``start``              -> mention.start
      * ``end``                -> mention.end

    MUST NOT digest, each for the stated reason:
      * the mention_id text  — a MINTING artefact. Digesting it would make the logical material
        depend on the minter's id format, and a re-mint of the same mention would silently fork
        every candidate that mentions it. The material says "a participant", not "a string
        starting MN-".
      * producer_ref / producer_version / extractor_version — FR-001, FR-006. Would extend producer
        scope from the observation level to the hypothesis level and break US5 and SC-005.
      * trigger_span / supporting_spans / structural_path — FR-001 and §17: a `relation_surface`
        or a span belongs to a revision, not to a `logical_candidate_id`. Two realisations of one
        configuration in one document have two spans and one id.
      * evidence_refs / observation_refs / signal_refs — FR-001, §43.
      * confidence — FR-001, and `relation_identity.py:289-292` verbatim: "a re-scoring pass must
        not mint a new relation, or every ranking change forks the graph".
      * type_ref, kind, TypeHypothesis, type state, vocabulary_version — INV-001, and to keep the
        type layer structurally incapable of moving a relational identity. This exclusion is
        load-bearing, not tidiness.
      * argument_shape — same reason: shape is a referent fact, and a shape reclassification must
        not re-key a relation.
      * surface_role, role_hypothesis, normalization_version — part 2.1. Two producers guessing
        "seller" and "vendor" for the same slot are one logical candidate (§43).
      * the relation this mention participates in, the segment's predicate, the document's
        reading — the fingerprint is a fact about a mention, so the same mention in two different
        relations gets the same fingerprint and is ordered by slot, not by relation.
      * any timestamp, clock reading, or wall clock — SC-010 replay must be a fixed point
        (relation_identity.py:292-297 states the rule verbatim).
    """
    return digest128(canonical_material({
        "mention_kind": mention.kind,
        "normalized_surface": normalize_surface_for_fingerprint(mention.surface),
        "capture_ref": mention.capture_ref,
        "segment_ref": mention.segment_ref,
        "start": mention.start,
        "end": mention.end,
    }))
```

`normalize_surface_for_fingerprint` is N1 + N2 only — NFKC, casefold, internal whitespace
collapsed, edge punctuation stripped — and **never** the predicate rules of part 3 V3, because a
participant's surface is not a predicate.

Two tests carry this whole subsection: `test_participant_fingerprint_is_invariant_across_realisations`
(build the mention pair once, build both observations, assert byte-equal fingerprints — this is
the realisation-independence claim, and it is the test that would fail if any sentence-level datum
leaked in) and `test_participant_fingerprint_excludes_producer_span_type_and_confidence` (mutate
each excluded datum in turn; the fingerprint must not move).

### 4.4 Multiple participants in one slot — the deterministic tie-break

> When a slot holds more than one participant, the occupants are ordered ascending by
> `participant_fingerprint`, byte-wise over the 32 lowercase hex. That is the **whole**
> tie-break and it is total, because the fingerprints are distinct by construction (two distinct
> mentions produce two distinct fingerprints; a repeat fingerprint is
> `duplicate_participant_fingerprint`).
>
> If the slot is **not** in `commutative_slots`, two occupants is a contract error
> (`slot_not_commutative_multiple_members`) and **no order is emitted**. Ordering it anyway would
> be inventing a reading the structure does not license. Coordination ("John and Mary acquired
> Acme") is **not** in brief §29's list, so it is `UNSUPPORTED_CONSTRUCTION` until the table gains
> a coordinated frame *and* a commutativity declaration for it. A named stop condition, not a gap
> to be papered over with a sort.

Tests: `test_slot_occupants_are_ordered_by_fingerprint`,
`test_non_commutative_slot_with_two_members_is_a_contract_error`,
`test_coordination_is_unsupported_until_a_frame_and_a_symmetry_marker_exist`.

### 4.5 When two participants are commutable, and how it is represented

> **Two participants are commutable if and only if they occupy the same `canonical_argument_slot`
> AND that slot is declared in `commutative_slots`. Nothing else makes two participants
> commutable.** Participants in *different* slots are never commutable, under any declaration.

The second sentence is §52 and SC-014 together: a `DIRECTED` edge's endpoints are never
reordered. `A0` / `A1` is the direction, and no declaration may swap it.

| Aspect | Specification |
|---|---|
| Where the marker lives | `RelationCandidate.commutative_slots: frozenset[ArgumentSlot]`, **always explicitly present**, defaulting to `frozenset()`. Never inferred, never absent, never `None`. |
| How it enters material | `"commutative_slots": sorted(slot.token for slot in commutative_slots)` — a sorted list, `[]` in the ordinary case. |
| Who may set it | Only an explicit declared-symmetry contract. `normalize_voice` cannot (part 3.6). §53 verbatim: "projection may use canonical endpoint ordering. But only if the admitted relation contract declares symmetry. Do not infer symmetry merely because the extractor did not know direction." |
| Relationship to `arity_mode` | **Derivable, never independently asserted** (part 2.5 check 4): `arity_mode is UNDIRECTED` iff `commutative_slots == set(occupied slots)`. `verify_signature_shape` refuses a pair that disagrees. |
| Consequence of changing it | A different `canonical_participant_ordering` output, therefore a **different** `logical_candidate_id`. Correct: a symmetric reading and an asymmetric reading of one pair are different claims, and the store shows both. |
| Interaction with a later claim contract | A claim's declared symmetry lives on `RelationClaimMaterial` / `RelationSchema` and **does not re-key an existing candidate**. A symmetric and an asymmetric candidate over one pair both stand; admission picks. This is why the marker must exist on the candidate and not only on the claim. |

**This replaces the current `logical_material` `UNDIRECTED` branch** (`relation_identity.py:178-183`),
which is `{"members": sorted({str(p) for p in participants})}` — a sort by mention-id text, plus a
`set`, i.e. a silent deduplication. Tests: `test_undirected_ordering_uses_the_slot_marker_not_a_mention_id_sort`,
`test_symmetry_is_never_inferred_from_missing_direction`,
`test_symmetric_and_asymmetric_readings_get_different_logical_ids`.

### 4.6 Worked example — brief §109 Case D, `John sold Acme to Microsoft in 2020.`

V1 `ACTIVE_CLAUSE`, ditransitive → `VERB_ACTIVE_TRANSITIVE`. V2: A0 = `nsubj` = John; remaining
`nmod:to` → Microsoft, `nmod:in` → 2020; TB2 orders by `ArgumentMarker` ascending, `in` < `to`, so
2020 is considered first, is a temporal complement, and is **dropped** with trace
`"V2.drop_temporal"` → slots `(A0, A1, A2)`. V3 `sold` → `sell`. V4 A0 = `NOMARK`, A1 = `NOMARK`,
A2 = `to`. `identity_projection()` →
`{"argument_markers":["","","to"], "canonical_argument_slots":["A0","A1","A2"],
"construction_frame":"verb_active_transitive", "language":"en", "predicate_lemma":"sell", …}`, so
`rendered_predicate()` is `"sell(A0:,A1:,A2:to)"`. A0 / A1 / A2 are seller / asset / buyer
**structurally**; the names live in `RoleBinding.surface_role` as evidence, and part 12 may later
propose operators for them. `time = 2020` is carried by `TemporalHypothesis` on the candidate at
year precision, as revision material — SC-003 satisfied, no binary collapse.

### 4.7 Behaviour changes this ordering makes to the existing `logical_material`

`apps/shared/domain/relation_identity.py` is not this file's to change, so these are recorded as
required follow-on edits, not applied here:

| # | Today | After | Why the change is required |
|---|---|---|---|
| 1 | `UNDIRECTED` sorts `sorted({str(p) for p in participants})` — by **mention-id text** | slot + fingerprint ordering, gated on `commutative_slots` | §52 forbids `min`/`max` canonicalisation for directed edges; and a mention-id sort makes identity depend on the id minter's format (part 4.3). |
| 2 | `sorted({…})` **deduplicates** | multiset, multiplicity preserved | "Acme is co-owned by John and Mary" is a different configuration from "Acme is co-owned by John". A `set` deletes a participant. |
| 3 | `DIRECTED` takes `participants` in **arrival order** | slot order | Arrival order is caller order, and determinism currently holds only because `assembly.py` sorts by hand at one call site. Slot order removes the reliance on a call site. |
| 4 | `NARY` uses `sorted([role, member])` with `role` a **free-text** `RoleBindingLike.role` | the slot is a structural `ArgumentSlot` | `RelationRoleBinding.role` (`relation_claim.py:102`) is free text today, so `purchaser` vs `buyer` forks the id at the claim layer. That type needs the same field split as part 2.1. |

---

## 5. The logical candidate identity rule

### 5.1 The rule, verbatim

```text
logical_candidate_id = "CAND-" + digest128(canonical_material({
    "identity_schema":     IDENTITY_SCHEMA_VERSION,          # "cand-logical-2"
    "tenant_id":           <tenant>,
    "arity_mode":          <"directed" | "undirected" | "nary">,
    "commutative_slots":   <sorted slot tokens>,             # [] unless declared
    "polarity":            <"asserted" | "denied">,
    "predicate_signature": <PredicateSignature.identity_projection()>,
    "participants":        <canonical_participant_ordering(...) as a list of
                            {"slot": "A0",
                             "participant_fingerprint": <32 hex>,
                             "commutable": <bool>},
                            ordered exactly as part 4.2 O5 says>,
}))
```

using the existing primitives unchanged (`relation_identity.py:97-117`): `canonical_material`
(`json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_normalise)`)
and `digest128` (SHA-256 truncated to 128 bits, 32 lowercase hex).

### 5.2 The inclusion and exclusion tables

**Included, and why each term is here:**

| Term | Why it must be here |
|---|---|
| `identity_schema` | The shape of the material is part of what the id addresses. Without it, a future key addition is undetectable in the record. |
| `tenant_id` | FR-002, brief §19, and tenant isolation at every level — which is constitution **VII. Security-First**, and also the reading of **IV. No Single Store / Graph / Score** that `relation_candidate.py:1112-1117` gives verbatim: "omitting it would let two tenants' hypotheses bucket under one key, which constitution IV forbids." |
| `arity_mode` | §19's "arity shape". It is **derivable** (part 2.5 check 4), so it is a redundancy that is checked rather than an independent assertion. |
| `commutative_slots` | The explicit structural marker (part 4.5). Without it in the material, a symmetric and an asymmetric reading of one pair would be indistinguishable — and part 4.5 says they are different claims. |
| `polarity` | §19 verbatim, FR-002, FR-015, §41, §109 Case H. "John did not acquire Acme" is a different hypothesis from "John acquired Acme". |
| `predicate_signature.identity_projection()` | The whole of §18 and FR-001’s exclusion list applied to `logical_candidate_id`. The projection contains the slots, the frame, the lemma, the markers and **both** version strings, so the slots cannot be reinterpreted under a moved convention. |
| `participants` as `(slot, fingerprint, commutable)` | FR-002’s `logical_candidate_id` must be derived from exactly tenant, the canonically ordered `participants`, arity shape, role shape, directional configuration, `polarity` and the predicate signature; with the role shape expressed structurally (part 2) and the participant expressed through a realisation-invariant fingerprint (part 4.3). |

**Excluded, and the list is total.** Not in the material, ever:

```text
relation_surface · predicate_surface · trigger_span · supporting_spans · structural_path ·
producer_ref · producer_version · extraction_method · extractor_version · extraction_rule_id ·
signal_refs · observation_refs · evidence_refs · context_ref · semantic_regime_ref ·
capture_ref · neighbourhood · signal_ordinal · confidence · candidate_status · observed_at ·
recorded_by · investigation_id · temporal_hypothesis · relation_ref · relation_type ·
schema_version · predicate_hypothesis · alternative_refs · mapping_evidence_refs ·
resolution_state · assembly_state · any observation ORDERING · mention_id text ·
any ENT-/RES- literal · any type datum · any `extra` value
```

`extra` is excluded because FR-010 reserves it for "producer-specific non-core metadata only".
`assembly_state` is excluded because a structural disagreement between two readings of one
configuration is a fact about the readings, not about the configuration (part 7.2).

Every collection that **is** present is emitted in canonical order (participants by part 4.2 O5,
`commutative_slots` sorted, markers parallel to slots), so no caller iteration order can reach the
id — the defect `relation_candidate.py:1180-1205` and `assembly.py` currently leave to a hand-sort
at one call site.

**What changes versus HEAD, in one line.** Today
`logical_material(self.arity_mode, self.relation_surface, self._participants, self.role_assignments)`
passes `relation_surface` into the `relation_type` parameter, so **the surface is the predicate
term** (`relation_candidate.py:1131-1139`). After: the predicate term is the signature, and
`relation_type` is out. `CANDIDATE_LOGICAL_MATERIAL_FIELDS` (`relation_candidate.py:513-523`)
therefore loses `relation_type` and `role_assignments` and gains `predicate_signature`,
`commutative_slots` and `polarity`; it currently declares `relation_type` while the code emits
`relation_surface`, which is the field/emit mismatch brief §94's sibling mutation names.

### 5.3 `INV-IDENTITY`, and the store demonstration that proves it

> **INV-IDENTITY: changing the mapping vocabulary does not change the historical logical identity
> of an already-extracted relational observation.**\n

**Why it is true, in one sentence:** every mapping artefact — the operator registry, the relation
vocabulary, a table of near-meaning words, an embedding index, a `SemanticRegime` configuration, a
type pack, a `RelationRef` catalogue — is a **non-input** to `logical_candidate_id`, because the
function's inputs are exactly `tenant_id`, `arity_mode`, `commutative_slots`, `polarity`, the
signature projection and the participant fingerprints, and none of those is derived from a mapping.

**How a store demonstrates it** — the demonstration is mechanical, not rhetorical, and step 5 is
where the mapping layer moves `candidate_id`:

| # | Step | Assertion |
|---|---|---|
| 1 | Extract and store a candidate normally. | `logical_candidate_id` = `X`; `verify_candidate_identity()` passes. |
| 2 | **Replace the entire mapping apparatus** with a different one — a different `RelationRef` set, a different `SemanticRegime` configuration, a different type pack, and a regime that maps `"originator of"` to a different operator than before and `"acquire"` to another. | the fixtures are different objects; nothing else changed. |
| 3 | Re-read the stored row **from its own columns** and re-derive the id with the *new* mapping apparatus installed. | derived `== X`; `verify_candidate_identity()` still passes. |
| 4 | Run the same re-derivation over the whole stored corpus. | **every** stored `logical_candidate_id` unchanged; the count of distinct `logical_candidate_id`s unchanged; the **partition** of candidates by logical id unchanged — same groups, same sizes. |
| 5 | Re-run the mapping layer and write the results. | `candidate_id` **changes** — the mapping is revision material (`relation_candidate.py:1159-1178`) — and `PredicateHypothesis.resolution_state` changes. So the mapping was not lost; it was recorded as a new reading of the same hypothesis. |

Step 5 is what makes this a *demonstration* rather than a *disclaimer*. Identity is stable **and**
the mapping is not silently dropped: a recognition shows up as a new reading, which is the shape
`relation_candidate.py:1123-1126` argues for and which FR-028 and §49 then give somewhere to live.

**Enforcement, because a docstring is not a mechanism.** Named tests:

- `test_mapping_vocabulary_is_not_an_input_to_logical_identity` — a static check that
  `predicate_signature.py` and the candidate's identity projection import no registry, no
  `RelationRef` catalogue, no type pack and no regime module, and that the key set of
  `identity_projection()` is disjoint from the union of every mapping artefact's keys. Precedent:
  brief §74's six-symbol import test.
- `test_normalize_voice_and_ordering_never_read_the_mapping_layer` — no import edge from
  `predicate_signature.py` to any registry, regime or type-pack module.
- `test_mapping_swap_leaves_every_stored_logical_id_unchanged` — steps 1–5 against the real store.
- `test_mapping_change_moves_candidate_id_and_not_logical_candidate_id` — step 5 in isolation.
- **Mutation**: add `relation_ref.relation_type` to the material. The constitutional suite MUST
  fail. Named `test_mutation_relation_ref_in_logical_material_fails`, a sibling of brief §94.

**The residual, stated rather than hidden.** The invariant holds because the mapping is not an
input. If anyone later adds a field to `PredicateSignature` computed *from* a registry — and
`event_class_hint` (part 1.3 item 9) is exactly the shape such a field would take — the invariant
breaks silently. That is why item 9 is a removal and not a deferral, and why the mutation exists.

### 5.4 The un-signatured candidate, named rather than papered over

The signature is **required** for a `logical_candidate_id`. A candidate with
`predicate_signature is None` gets `logical_candidate_id = ""`, is addressable only by
`candidate_id`, and `verify_candidate_identity()` refuses to certify it with
`unaddressed_logical_identity`. A surface-keyed fallback identity term is **forbidden**: that is
FR-001's violation alive under a version tag, and it would make two code paths derive ids, the
second of which would be the one that is wrong.

**Migration consequence, which the migration must state rather than a query discover:** existing
`relation_candidate` rows have no signature, so their `logical_candidate_id` is **not back-filled**.
Their `candidate_id`s are unchanged. Rows gain `logical_candidate_id = ''` until re-extraction
supplies a signature. If a product requirement exists for a surface-keyed logical id on
un-signatured candidates, that requirement **conflicts with FR-001** and must be escalated as a
spec conflict rather than implemented.

---

## 6. `RelationSignal` (CHANGED — natively n-ary, real polarity, named basis)

Current state at HEAD `0056665`: `subject_mention_ref: str` + `object_mention_ref: str`, two
required distinct scalars (`signal.py:281-282`, validated `:326-338`). N-ary survives only as
opaque `extra` tuples, and `extra` is excluded from `_material()`.

```python
@dataclass(frozen=True)
class RelationParticipant:
    mention_ref: str        # MUST resolve in the mention index (FR-016, §25)
    slot: ArgumentSlot      # structural, from the reading's canonical_argument_slots (part 2)
    role_hypothesis: str = ""    # EVIDENCE ONLY; never logical material (part 2.1)
    ordinal: int = 0             # position as observed, not canonical
    confidence: float = 0.0      # a projection, never FR-001 identity material
    argument_shape: str = "entity"   # a referent fact; excluded from identity (part 1.2 class 6)

@dataclass(frozen=True)
class RelationSignal:
    participants: tuple[RelationParticipant, ...]   # variadic; arity >= 2
    kind: SignalKind                               # OBSERVATION CHANNEL ONLY after part 6.1 split
    relation_surface: str                          # raw observed words — evidence only
    predicate_signature: PredicateSignature | None # None only when the construction is unsupported
    observed_construction_frame: ConstructionFrame | None   # the OBSERVED frame; never in the signature
    polarity: Polarity                             # was overloaded onto SignalKind.NEGATION
    observational_basis: SignalBasis               # replaces the surface-required invariant (brief §16)
    neighbourhood: Neighbourhood
    signal_id: str = ""
    # … all 019 fields retained
```

### 6.1 `SignalKind` is split (FR-011), and `TEMPORAL` is kept

Today it has thirteen values mixing three different things. Thirteen minus three, plus five, is
fifteen; `ck_relation_signal_kind` is recreated over those fifteen literals in `021`, and the
removal is a narrowing the migration **refuses forward** rather than applying silently.

| Today | Becomes |
|---|---|
| `LEXICAL`, `LINK`, `REFERENCE`, `TABLE`, `LIST`, `METADATA`, `ATTRIBUTE`, `HIERARCHY`, `SCHEMA` | remain `SignalKind` — these are observation channels |
| `CO_OCCURRENCE` | remains a `SignalKind`; becomes constructible with an empty surface (FR-013, §40) |
| `NEGATION` | **removed** → `Polarity.denied` on the signal; `predicate_polarity` is where a denial belongs |
| `QUANTITY` | **removed** → `argument_shape="value"` on the participant + a `quantity` note |
| `COREFERENCE` | **removed** → a coreference relation between mention refs, not an observation channel |
| `SYNTAX`, `STRUCTURAL`, `EVENT`, `SEMANTIC` | **added** — FR-011 requires a channel for a parsed frame, a non-containment document structure, an event frame and an asserted controlled-vocabulary meaning, and no channel existed |
| `TEMPORAL` | **added and KEPT** (`ARBITRATION.md`, section 4, overriding the "must not be added" reading) |

**`TEMPORAL` is a channel, not a container of time**, and the distinction is load-bearing:

```text
SignalKind.TEMPORAL                              →  "based on a temporal observation"   (channel)
SourceTemporalObservation / temporal_evidence     →  the temporal facts                    (content)
```

`TEMPORAL` carries no temporal payload. It states the *provenance channel*; the facts live in
`SourceTemporalObservation`. That division is what keeps `SignalKind` from becoming an
unstructured dumping ground (brief §15) — it is the same discipline as the N1–N6 table, applied to a
different axis.

Note the four values that no producer emits today — `CO_OCCURRENCE`, `COREFERENCE`, `QUANTITY`,
`NEGATION` — are exactly the ones being dissolved into fields. A vocabulary that only names things
nobody produces, and names them wrongly, is the defect.

### 6.2 The observational basis replaces the surface-required invariant

`signal_asserts_nothing` and `relation_surface <> '' OR relation_ref IS NOT NULL` are replaced by
an explicit basis (brief §16; the basis MUST be one of predicate text, DOM relation, table slot, hyperlink, citation, proximity, metadata field, event frame, attribute key — FR-013, FR-014). The honest rule: a `CO_OCCURRENCE` signal **may** have an
empty `relation_surface` and a `None` signature. Adjacency that was seen and not named is a real
observation. What remains refused is a signal whose basis is `PREDICATE_TEXT` with an empty
surface, and a signal with no basis at all — that is an unrecorded gap, not a co-occurrence.

### 6.3 Identity (`_material`) changes (FR-089)

`_material()` adds `predicate_signature`, `polarity`, the declared `arity_mode` and the role
bindings. It removes nothing — `producer_ref` **stays**, because FR-006's independence count
requires producer identity. What stays wrong is the three docstrings that claim two producers
reading one structure share a `signal_id`; they get corrected, not the code.

---

## 7. `RelationCandidate` (CHANGED — signature-keyed identity, serialisable)

```python
@dataclass(frozen=True)
class RelationCandidate:
    participants: tuple[RelationParticipant, ...]   # was subject/object scalars
    predicate_signature: PredicateSignature | None
    predicate_hypothesis: PredicateHypothesis | None
    relation_surface: str                           # EVIDENCE / revision material
    assembly_state: CandidateAssemblyState = CandidateAssemblyState.CONSISTENT
    commutative_slots: frozenset[ArgumentSlot] = frozenset()   # always present; never inferred
    direction: DirectionHypothesis | None = None    # DERIVED read-only projection of the slots
    polarity: Polarity | None = None                # asserted | denied
    candidate_id: str = ""
    logical_candidate_id: str = ""                  # "" until a signature exists (part 5.4)
```

### 7.1 `relation_ref` has exactly one authority

`PredicateHypothesis.relation_ref` is **authoritative**. `RelationCandidate.relation_ref` becomes
a **derived** property, kept only for compatibility with the existing surface area. Two stored
sources of truth for one reference is precisely the semantic minefield that produces
`candidate.relation_ref = A` against `predicate_hypothesis.relation_ref = B` (`ARBITRATION.md`, section 8).

```python
@property
def relation_ref(self) -> RelationRef | None:
    """DERIVED. The authoritative value is ``predicate_hypothesis.relation_ref``."""
    return None if self.predicate_hypothesis is None else self.predicate_hypothesis.relation_ref

@property
def mapped_operator_refs(self) -> tuple[RelationRef, ...]:
    """Primary first, then every live alternative, canonicalised."""
    return () if self.predicate_hypothesis is None else self.predicate_hypothesis.all_refs

@property
def mapped_relation_type(self) -> str:
    """The operator this candidate was MAPPED TO. Not the relation's type.

    ``relation_type`` promised ontology authority — a reader would conclude the relation *is* a
    ``works_for`` — and §104 forbids requiring that all relations fit a finite global edge list.
    Empty means NO MAPPING WAS MADE. It does not mean the relation has no type, and it is not a
    signal that the platform understands the predicate. For a hypothesis with several defensible
    readings this returns the designated primary, which is a ranking default and NOT a verdict.
    """
    return "" if self.relation_ref is None else self.relation_ref.relation_type
```

`relation_type` is retained as a delegating deprecated alias. **And the claim boundary moves** from
"is the string empty" to "is the state `KNOWN`": `relation_claim_material.py:360` currently tests
`if not self.relation_type:` and is fed `candidate.relation_type` at `:734`, which returns the
primary whenever there is one — so today an `AMBIGUOUS` hypothesis with a primary **would produce
claim material and an edge**. That is §51's projection boundary crossed by an unresolved
predicate, and it is reachable today. The gate becomes
`if self.candidate.predicate_hypothesis.resolution_state is not PredicateResolutionState.KNOWN:`,
with a refusal message that names the state, so an ambiguous predicate's refusal says *ambiguous*
rather than *untyped*.

The `relation_candidate.py:691` `__post_init__` fallback
`surface_form=self.relation_surface or ("" if self.relation_ref is None else str(self.relation_ref.relation_type))`
is **deleted**: the hypothesis is built with `surface_form=self.relation_surface` and no synthetic
surface. A candidate with no surface and no signature is a candidate with no identity term, which
is the honest state and the §90 case. The docstring at `:1128-1129`, which calls the fallback
harmless because "no existing identity moves", must be corrected in the same commit — a comment
asserting a safety property the code no longer has is the defect class FR-098 names.

### 7.2 `CandidateAssemblyState` — the third epistemic axis (NEW)

```python
class CandidateAssemblyState(StrEnum):   # NEW, distinct from CandidateStatus
    CONSISTENT  = "consistent"
    AMBIGUOUS   = "ambiguous"
    CONFLICTING = "conflicting"
```

Three distinct things, never mixed (`ARBITRATION.md`, section 3), and the middle one is why this
enumeration exists at all:

| State | Lives on | Means | Trigger |
|---|---|---|---|
| `PredicateHypothesis.resolution_state = CONFLICTING` | the hypothesis | incompatible **semantic** readings of the same structure | two regimes or operators map one signature incompatibly |
| `RelationCandidate.assembly_state` (**NEW**) | the candidate | incompatible **structural** readings of one participant configuration | producers disagree on arity, direction, polarity or role slots |
| `CandidateStatus.CONTRADICTED` | the candidate | the **assertion itself is denied** | a positive reading versus an explicit denial or contradiction |

`CandidateStatus` must not become a dumping ground for the epistemic space again. A structural
conflict that is *not* a denial yields `assembly_state = CONFLICTING`; it never yields
`candidate_status = CONTRADICTED`. `assembly_state` is a **revision** field, so it participates in
`candidate_id` and not in `logical_candidate_id` (part 5.2) — the same configuration assembled two ways
is one structural identity read two ways, and the disagreement is a fact about the readings, not
about the configuration.

### 7.3 `signal_refs` is canonicalised on construction (FR-085)

Alongside the collections that already are (`observation_refs`, `evidence_refs`,
`supporting_spans`). At HEAD it is identity material that is never sorted, so `candidate_id`
depends on caller iteration order and determinism holds only because `assembly.py:338` sorts by
hand at one call site. Test: `test_no_caller_order_reaches_the_logical_id`.

### 7.4 `to_dict()` / `from_dict()` (FR-086)

Added, covering all fields losslessly, and `relation_surface` is guaranteed to survive the round
trip as text — it is evidence, and evidence stored only as a digest is evidence that is gone.

---

## 8. `PredicateHypothesis` (EXTENDED — mapping state separated from structure)

`PredicateResolutionState` stays exactly as it is: `KNOWN`, `UNKNOWN`, `AMBIGUOUS`, `CONFLICTING`.
It describes the **mapping** to a known operator, which is a different question from the structure.
The two are separate fields and are never merged.

```python
@dataclass(frozen=True)
class PredicateHypothesis:
    surface_form: str = ""
    normalized_form: str = ""                              # DERIVED read-only view (part 1.6)
    relation_ref: RelationRef | None = None                # the PRIMARY mapping result
    mapping_candidates: tuple[PredicateMappingCandidate, ...] = ()   # the full live set
    resolution_state: PredicateResolutionState | None = None
    mapping_evidence_refs: tuple[str, ...] = ()

    # ---- derived, read-only; no setter, no stored duplicate ----

    @property
    def alternative_refs(self) -> tuple[RelationRef, ...]:
        """Every live competing target, canonicalised, primary excluded.

        Derived from ``mapping_candidates`` so the set of alternatives and the set of candidates
        can never disagree. Order is by ``str(ref)``; collection order is not semantic and MUST
        NOT reach any digest (§108 Determinism).
        """
        out = {
            c.target_relation_ref
            for c in self.mapping_candidates
            if c.target_relation_ref is not None and c.target_relation_ref != self.relation_ref
        }
        return tuple(sorted(out, key=str))
```

| Field | Holds |
|---|---|
| `surface_form` | raw words, verbatim |
| `normalized_form` | **derived, read-only** view of `predicate_signature.rendered_predicate()`, falling back to `surface_form`. A constructor-supplied value is **refused** (part 1.6) |
| `relation_ref` | the **primary** mapping result, or `None`. A *ranking default*, never a verdict: an `AMBIGUOUS` or `CONFLICTING` hypothesis yields no claim material, so the primary decides nothing that survives |
| `mapping_candidates` | the full live set of `PredicateMappingCandidate` (part 12), each with its own `match_type`, `confidence`, `provenance`, `mapping_version`, `created_by` and `evidence_refs`. `>= 0`, canonically ordered, de-duplicated by content digest |
| `alternative_refs` | **derived, read-only**: every live `target_relation_ref` other than the primary. Keeps FR-021's field name and element type; stops being a stored tuple of bare refs |
| `resolution_state` | `UNKNOWN`/`AMBIGUOUS`/`CONFLICTING`/`KNOWN`. **Derived from the candidate set**, except an explicit `CONFLICTING`, which records something the refs cannot |
| `mapping_evidence_refs` | why the mapping was made — the `signal_id`s behind each reading, so a reader can tell which evidence produced which interpretation |

**`AMBIGUOUS` is one hypothesis with alternatives, never two hypotheses.** Two distinct
`PredicateSignature`s are two logical candidates — `owns`, `controls` and `manages` stay three (FR-004, brief §20) — and MUST NOT be reported as
`AMBIGUOUS`. `AMBIGUOUS` means one signature, one evidence set, two defensible readings.
`CONFLICTING` means the evidence itself disagrees. Both preserve every reading; neither is
resolved by count, confidence, order or vote (FR-026, §45).

| `resolution_state` | `relation_ref` | live candidates | meaning | claim materialisable |
|---|---|---|---|---|
| `UNKNOWN` | `None` | 0, or candidates with `target_relation_ref=None` | nobody has named this relation. Structure known, mapping unknown — the §90 case and the **norm** | no |
| `KNOWN` | present | 1 distinct target | one operator, no competitor | yes |
| `AMBIGUOUS` | present (designated, **not a winner**) | ≥2 distinct targets, agreeing evidence | two **regimes** were each offered the same observation and returned different operators. The observations do not disagree; the interpreters do (§83) | no |
| `CONFLICTING` | present (designated, **not a winner**) | ≥2 distinct targets, **disagreeing evidence** | the **observations** contradict each other over the same participant structure (§83) | no |

**The discriminator is which layer the disagreement lives in, and it is read off the *evidence*,
never off the outcome.** A `UNKNOWN` state beside a non-`None` `relation_ref` MUST be refused —
that refusal is what makes `relation_ref=None` mean *unknown* rather than *unspecified*, which is
the only reason "structure known, mapping unknown" is expressible at all (§21, §67, SC-002).

`PredicateSignature` is **not** stored inside `PredicateHypothesis`: the signature is the
*structure*, the hypothesis is the *mapping attempt*, and merging them is how a hypothesis ends up
unable to represent "structure known, mapping unknown". `relation_ref=None` with a full signature
is legal and is the norm.

**Persistence change (FR-087), which requires `predicate_signature` in its own columns on
`relation_candidate` rather than as a digest.** `mapping_candidates` and `mapping_evidence_refs`
get real columns. Today they sit inside `candidate_id` material with no column at all, so two candidates
differing only in their alternatives get different ids with no stored reason, and
`PredicateHypothesis` survives only as a 32-character digest. Verified at HEAD: `relation_candidate`
and `relation_signal` carry only `predicate_hypothesis String(64)` and `predicate_state String(16)`
(`db/schema.py:2293-2294`, `:2388-2389`; migration `020` lines 247-248, 307-308), so the column
exists to hold a digest and nothing else. `mapping_candidates` MUST be stored as **structure, not
as a digest** — a digest may identify the data and must not be the only copy — because §108 lists
"alternatives survive" as a mandatory acceptance criterion, and a digest cannot survive as
evidence. `resolution_state` is already a column with a CHECK constraint against
`PredicateResolutionState` (`db/schema.py:2354`, `:2444`), so the four states persist correctly
today; `AMBIGUOUS` and `CONFLICTING` are therefore already storable, and what is missing is the
readings that justify them.

---

## 9. `Polarity`, `SignalBasis`, `DirectionHypothesis`, `Arity`

```python
class Polarity(StrEnum):          # NEW — was overloaded onto SignalKind.NEGATION
    ASSERTED = "asserted"
    DENIED    = "denied"
    UNCERTAIN = "uncertain"


class SignalBasis(StrEnum):        # NEW — brief §16, verbatim; named by NO artefact before this file
    PREDICATE_TEXT = "predicate_text"
    DOM_RELATION   = "dom_relation"
    TABLE_SLOT     = "table_slot"
    HYPERLINK      = "hyperlink"
    CITATION       = "citation"
    PROXIMITY      = "proximity"
    METADATA_FIELD = "metadata_field"
    EVENT_FRAME    = "event_frame"
    ATTRIBUTE_KEY  = "attribute_key"
```

`SignalBasis` is the nine-name vocabulary brief §16 gives for the replacement of
`relation_surface != \"\" OR relation_ref != NULL`, and **no artefact named it before this file and
the migration repair** — which is why `021` that adds the column cannot be ordered before the value
type exists. Naming the basis is what obliges a surface: naming `PREDICATE_TEXT` requires one,
naming `PROXIMITY` permits its absence. A `relation_signal.observational_basis` that is `NOT NULL`
with no legacy branch is rejected, because it would refuse every row written before `021`; the
constraint narrows-with-refusal instead (constitution Principle I). The nine names are written out
in the migration (`_OBSERVATIONAL_BASES_021`) **and** a test asserts the two lists are equal.

`DirectionHypothesis` is unchanged as an enumeration: `SUBJECT_TO_OBJECT`, `OBJECT_TO_SUBJECT`,
`UNDIRECTED`, `AMBIGUOUS`. It is **no longer a signature field**; it is a *derived, read-only*
projection of `(canonical_argument_slots, commutative_slots)`, checked by
`verify_signature_shape`, and it MUST NOT be a material input — a disagreement between a declared
direction and the slot order would be a silent identity fork. It is still absent from
`relation_candidate` at HEAD and `polarity` is still not a column on any table, so a negated
candidate and an asserting candidate over the same pair are still indistinguishable after a round
trip; that is fixed in part 13, and `polarity` now additionally enters **logical** material (part 5.1) as
`asserted` or `denied`.

`RelationArityMode` is unchanged: `UNDIRECTED`, `DIRECTED`, `NARY`. **N-ary is native** — role
bindings, not a binary pair with an `extra` payload.

---

## 10. Mention binding and the type layer

### 10.1 `MentionOccurrenceIndex` (NEW) — the pre-resolution binding seam

One name per thing (`ARBITRATION.md`, section 8): the **stage** is `MENTION_BINDING`, the **structure** is
`MentionOccurrenceIndex`, the **id form** is `MN-…`. `MentionBinding` is not a third data-model
object; `MentionOccurrenceIndex` is canonical, and no agent may introduce a fourth spelling.

Maps a producer's observation to real `MN-…` ids minted once per
`(segment, kind, value, start, end, extractor)`, with deterministic lookup on capture, segment,
offset/span, normalized surface and extractor occurrence, resolvable to a real `MENTION-…` without
resolving to an entity (FR-018, §26). Producers cite resolved mention refs; the index is the only
thing that mints them. At HEAD there is **no** such index, no resolution code for the
`surface:`/`anchor:`/`href:`/`header:`/`cell:`/`document:`/`meta:`/`byline:`/`attribute:`/`value:`/
`jsonld:`/`jsonld-value:` prefixes, and 100% of producer `participant.mention_ref` values are fabricated, so none resolves in a mention index (FR-016,
§25). Mention binding stays distinct from entity resolution: a producer may use a mention id after
binding and MUST NEVER use an `ENT-` or `RES-` literal (FR-019, §26, §75).

### 10.2 `TypeHypothesis` is ONE hypothesis (FR-032)

Thirteen fields, six states, both verbatim from brief §6 (`input.md:465-492`). The previous part 6
of this document redefined the type as a *container* of `TypeCandidate`s with a three-value state — an
invented enumeration belonging to the control-plane ORM, imported into `shared`, which inverts the
layering (`shared` is imported **by** control-plane), a misspelled member, and a second container
for facts the codebase already carries in two places.

```python
class HypothesisState(StrEnum):
    """How one type hypothesis stands. Per §6 of the brief; closed at six."""
    UNKNOWN     = "unknown"
    OBSERVED    = "observed"
    INFERRED    = "inferred"
    MAPPED      = "mapped"
    AMBIGUOUS   = "ambiguous"
    CONFLICTING = "conflicting"
```

The five fields with no defaults, which in a frozen dataclass must precede the defaulted ones:

```python
@dataclass(frozen=True)
class TypeHypothesis:                   # = interpretation candidate (brief §6); never a set
    type_surface: str                   # brief §6: the words that triggered it, verbatim
    normalized_surface: str              # brief §6: NFKC + casefold + whitespace fold, for matching only
    type_ref: str                       # brief §6: the candidate, e.g. "core:Organization"
    scheme: SemanticRef                 # brief §6: how to treat the ref; never what it means
```

and the eight defaulted fields, on the same dataclass:

```python
    hypothesis_state: HypothesisState = HypothesisState.UNKNOWN   # brief §6: one of the six above
    confidence: float = 0.0            # a projection, never FR-001 identity material
    source_ref: str = ""                # brief §6: the observation this was read off
    extractor_ref: str = ""             # brief §6: which producer proposed it
    extractor_version: str = ""         # brief §6: pinned, so the proposal is re-derivable
    evidence_refs: tuple[str, ...] = () # brief §6: citable; sorted + de-duplicated on construction
    context_ref: str = ""               # brief §6: the CONTEXT product consumed (brief §77)
    semantic_regime_ref: str = ""       # brief §6: the regime that read the context, or ""
    mapping_candidates: tuple[TypeMappingCandidate, ...] = ()  # brief §6; never collapsed, never chosen
```

`normalized_surface` reuses the existing `vocabularies.normalize_surface_form`, whose own docstring
states the discipline this type needs: "It makes no judgement about what the form *means* — it is a
string normalisation, never a type inference." Do not write a second one. `mapping_candidates` is
`tuple[TypeMappingCandidate, …]` — the type-side twin of part 12's `PredicateMappingCandidate`, and
**proposals, not records**, deliberately: a hypothesis has reached no reviewed, sourced or recorded
mapping either, so it is in exactly the same position as the signal that suggested it.

**What it deliberately does NOT carry**, stated so a later reader does not add it back:

| Absent | Reason |
|---|---|
| `mention_ref` | A hypothesis is owned by a mention. Carrying the owner's id inside the owned value is the identity inversion part 1.2 forbids on the predicate side. part 11's `TypeSignal` **does** carry `mention_ref` and this is not a disagreement: a signal is an *observation about a specific occurrence* and must be de-duplicable per occurrence; a hypothesis is a *candidate owned by that occurrence*, so a back-pointer is redundant — and would make the hypothesis's content key a function of an id minted by a different layer. **The asymmetry is load-bearing.** |
| `hypotheses` / children | Brief §103. A level you cannot cite is not a level, and the counter-case is tested — see the three arguments below this table. |
| `state` as a *resolution verdict* | A hypothesis does not resolve anything. Resolution is `TypeAssertion`'s business and its ladder is `SemanticStatus` (`contracts.py:110-123`). Two different questions. |
| `entity_ref` | INV-001: "one mention is never one entity." A hypothesis is about a mention. |
| `signal_id` / any id / digest | It is discarded with the comparison it narrowed. If a hypothesis is ever given an id, the thing it was id'd *for* has changed and this section is wrong. |
| `vocabulary_version` | Legitimate information, but it belongs on the **pack**, and brief §6's own mechanism for it is `mapping_candidates` / `scheme`. Dropping it here loses nothing the brief asked for. |
| `type_ref` prefixed by this type | part 11: the first moment a local type may appear on the observation path is `TypeHypothesis`, so this field is where a local ref is legal. |

Durable typing is `TypeAssertion`, which already has the two-level identity brief §10 requires — "a later
`status=INFERRED` must be a new revision, not destructive replacement … This follows the existing
`TypeAssertion` two-level identity model" (brief §10, FR-037). `TypeHypothesis` is a nested value object
in exactly the sense of brief §103's list, and not a level. The three arguments: §103's own
enumeration puts `TypeHypothesis` in the same class as `PredicateHypothesis`; §101 draws
`TYPE HYPOTHESES` as a fan-out annotation on the mention occurrence, between `TYPE SIGNALS` and
`TYPE ASSERTIONS`, which is the position a value object occupies and not a rung; and the
counter-case is tested — a type that has its own identity, can be minted by something other than a
mention, can exist without a mention and can be projected without one. `TypeHypothesis` fails the
first of those four tests by design.

**Where the SET of hypotheses lives — on the mention, in the two places the codebase already has.**

- `extractors/types.py::TypedMention.type_hypotheses: tuple[TypeHypothesis, ...] = ()`, with
  `kind: str` **retained unchanged** as a coarse producer classification (brief §7, FR-033). The seven
  values in use today — `crypto`, `handle`, `ip`, `org`, `person`, `phone`, `place` — are producer
  classes, none of which is a vocabulary term. `kind` is not deprecated, not renamed, not given an
  enumeration, and is compared to nothing.
- `semantic/resolution.py::ResolutionMention.type_hypotheses: tuple[TypeHypothesis, ...] = ()`,
  **beside the `type_assertions` it already carries**, frozen in the same `__post_init__` that
  freezes `type_assertions`.

Both are sorted, de-duplicated and frozen on construction, by
`(-confidence, type_ref, str(scheme), str(hypothesis_state))`, with de-duplication by
`(type_ref, str(scheme), str(hypothesis_state))` keeping the highest-confidence occurrence. That
policy is **not new**: `semantic/blocking.py::_ordered_hypotheses` already implements exactly this
and explains why — "Ordering is total and value-based rather than insertion-based so that the
recorded hypothesis list — and therefore the result's content key — cannot depend on the order a
caller happened to build its hypotheses in." **Reuse that function; do not write a second one.**

**No third container.** `BlockingResult.type_hypotheses` and `BlockingOutcome.hypotheses` already
carry the set, consistently, in two places. A third carrier for the same facts is the defect, not
the cure.

**The id asymmetry, stated once, because it is the strongest evidence that this is not a level.**
The *signal* carries a `signal_id` (part 11); the *hypothesis* does not; the *assertion* carries two
(`TA-`/`TAR-`). Three types, three id policies, each matching what the type is for: an observation
must be citable and de-duplicable, a candidate must be discardable, an assertion must be revisable
without erasure. A type that carried an id at every level would be a level; three different id
policies is what "not a level" looks like in code.

### 10.3 The bounded type vocabulary (NEW) — a normative pack, not a set of extractors

Pack identity, verbatim from brief §4.1: **`core-atomic-types@1`** — the pack id and version as one
`@`-separated string (FR-029, §63).

**31 `core:*` entity classes** (`input.md:338-397`, identical to FR-030's enumeration — 31, not 32):

| Group | Types |
|---|---|
| Person / agent | `core:Person` `core:Organization` `core:LegalEntity` `core:Group` `core:Agent` |
| Web / digital | `core:WebSite` `core:WebPage` `core:OnlineAccount` `core:SocialProfile` `core:Domain` `core:DigitalResource` |
| Place / geography | `core:PhysicalPlace` `core:Facility` `core:Address` `core:GeographicRegion` `core:Country` `core:StateOrProvince` `core:City` `core:Coordinate` |
| Information | `core:Document` `core:Dataset` `core:CreativeWork` `core:MediaResource` `core:Software` `core:Project` |
| Commercial / physical objects | `core:Product` `core:Service` `core:Asset` `core:Vehicle` `core:FinancialInstrument` |
| Events | `core:Event` |

**13 `value:*` value types** (`input.md:403-416`, identical to FR-031): `value:EmailAddress`
`value:PhoneNumber` `value:URL` `value:Handle` `value:Identifier` `value:IPAddress` `value:Hash`
`value:CryptoAddress` `value:Date` `value:DateTime` `value:Money` `value:Quantity`
`value:Coordinate`. Brief §4: "Do not force every value into `Entity`."

**44 entries: 31 entity-kind + 13 value-kind.** That is the pack's floor — not its ceiling, and
**not its obligation on producers.**

```python
CORE_NAMESPACE  = "core"
VALUE_NAMESPACE = "value"


@dataclass(frozen=True)
class TypePackEntry:
    type_ref: str                 # "core:Organization" / "value:URL" / "industry:Bank"
    label: str
    kind: TypePackKind            # ENTITY | VALUE  <- brief §63's "kind = entity/value" (brief §63); REQUIRED,
                                  #   no default, and never inferred from the prefix
    alt_labels: tuple[str, ...] = ()
    broader_refs: tuple[str, ...] = ()
    narrower_refs: tuple[str, ...] = ()      # completed from other entries' broader, never trusted
    description: str = ""
    version: str = "1"            # per-entry version
    namespace: str = ""           # "core" | "value" | "industry" | <any tenant-registered ns>
    pack_ref: str = ""            # "core-atomic-types@1" — provenance of THIS entry
    blocking_hints: tuple[str, ...] = ()      # permitted by brief §63; never a deny list


@dataclass(frozen=True)
class TypePack:
    pack_id: str                  # "core-atomic-types"
    version: str                  # "1"
    namespace: str                # the namespace this pack OWNS
    entries: tuple[TypePackEntry, ...] = ()
    status: PackStatus            # DRAFT | REGISTERED | ACTIVE
```

- **`namespace` is the prefix of `type_ref`, and it is data, not a hard-coded set.**
  `type_ref == f"{namespace}:{local_name}"` is validated on construction, and a `type_ref` whose
  prefix is neither `core` nor `value` is **legal** — that is exactly how `industry:Bank` lives.
  There is no `if namespace == "core"` branch anywhere, so `core:Organization` →
  `industry:Bank` → `industry:CommercialBank` (FR-034, brief §5) is reachable by registering a **second
  pack** (`industry-types@1`, namespace `industry`) whose `core:Organization` entry declares
  `narrower_refs=("industry:Bank",)`. **`industry:Bank` therefore needs no code change.**
- **`pack_ref` is a string, not an import.** The foundational pack is data — a frozen tuple of
  entries, byte-identical across processes and hashable for replay. brief §63's "Do not encode massive
  relation semantics into the type pack" is a size bound as well as a semantic one.
- **Status and version reuse the existing discipline.** `events/ontology_pack.py::OntologyPackRegistry`
  already implements "DRAFT → REGISTERED → ACTIVE; never overwrite a version" and raises on a
  duplicate version. `TypePack` reuses that registry rather than growing a second one.
- **`kind` is a required, non-defaulted discriminator, and it is load-bearing.** `core:Coordinate`
  (a located place reference, an entity) and `value:Coordinate` (a geographic measurement as a
  value) are the same label in two namespaces. Both stay, and they never collide as references
  because the namespace prefix is part of the string — so a consumer that forgets to read `kind`
  gets two different *strings*, which is the safe failure. FR-030 and FR-031 each list one of them;
  the contradiction is resolved by `kind`, not by deleting an entry, because a deleted entry is a
  silent narrowing, which is the one thing INV-002 forbids.
- **The `relations` list on the existing `events/ontology_pack.py` is deleted, not left inert.**
  "Inert" was the wrong diagnosis: `allows_relation()` is indeed never called, but `to_dict()`
  publishes the list and `OntologyPackRegistry.register()` inlines it, so relation names ride in
  every pack payload whether or not anything reads them. A published fixed relation list is worse
  than an enforced one, and brief §104 forbids a finite mandatory relation universe. `allows_type()` stays
  **advisory**: its result annotates and never filters, which matters because the pack's default
  `entity_types` are uppercase bare names, so `allows_type("core:Person")` is `False` and every
  `core:*` type the feature mandates is unknown to the pack — harmless while the result is a flag, a
  rejection the moment anyone treats it as a gate. A named test asserts the deleted list has zero
  callers.

### 10.4 The extractor contract, verbatim — a type in the vocabulary ≠ an extractor obligation

> **A type existing in the foundational vocabulary does not mean the system must have a dedicated
> extractor for it.**
>
> **The absence of a type from the foundational vocabulary does not mean a mention of that kind is
> refused, dropped, quarantined or downgraded.**

Both halves are already the brief's position. `input.md:439-445`: "but the existence of
`core:Organization` must never imply: `everything unknown cannot be Organization` / Unknown remains
unknown." `input.md:455`: "They must not be used as an extraction gate." `input.md:4662-4664`
(brief §110): "Do not start by adding dozens of extraction rules. / First make the substrate correct."

**The consequence for the plan is concrete.** The 31 `core:*` entity classes and 13 `value:*` value
classes are a **vocabulary** deliverable. The number of instruments is a separate, much smaller
deliverable — brief §8's **seven extraction families** (its A–G sub-sections: person, organization,
website/webpage/domain/URL, online account/social profile, digital identifiers, documents, event
mentions). At HEAD there are 7 `kind` values and 14 extractor modules, and this feature adds **no
new extraction framework** and at most **four** new instrument modules (URL/domain, profile-URL,
document-structure, event-mention), all thin wrappers over the existing registry. "Seven classes"
is the wrong vocabulary for the 7 and is a miscount of the 31; the two numbers are unrelated
(`ARBITRATION.md`, section 10).

**The FR-030 / INV-002 tension, bound to its own layer.** "MUST cover at minimum" is a requirement
on the **pack**: a fixture requirement, with a test asserting the pack contains `core:Organization`
and its 30 siblings. "Never a completeness condition" is a requirement on **everything downstream**:
no producer, resolver, blocker, validator, mapper or projector may consult the pack in a way that
makes a mention's survival, its type, or its extraction depend on the pack containing a matching
entry. A `type_ref` outside every registered namespace is a first-class `TypeHypothesis` with
`type_ref="whatever:Thing"`, `scheme=SemanticRef.UNRESOLVED`, `hypothesis_state=UNKNOWN`; the
mention is retained; `UNKNOWN` is a recorded state, never a rejection (FR-038, INV-003, brief §97). Brief §97 is
the mutation that proves it:

```python
if core pack does not know type:
    continue
```

must fail.

### 10.5 What is deliberately undecided here

`core:Coordinate` may be intended, or may be a brief typo for `core:GeographicRegion`; the brief
lists it under "Place / geography" and again under "Values". **Stop condition: ship both entries as
decided in part 10.3 and record the question. Do not delete a vocabulary entry on a guess.** Raised as
`UNKNOWN` in the ADR.

---

## 11. `TypeSignal` (NEW — the entity-side observation record)

Per `ARBITRATION.md`, section 7. Owned and specified by `repair/A4b-mapping-layer.md` §D5.2 as
`semantic/type_signal.py`; it is the direct analogue of `RelationSignal`, subject to the identical
rule — a signal is Layer 1, "something type-shaped was observed" (§102). It carries **no
commitment**, resolves to nothing, and is never projectable.

```python
@dataclass(frozen=True)
class TypeSignal:
    """What a structured or lexical source STATED about a mention's type. Never a type.

    ``source_vocab`` is an EXTERNAL VOCABULARY REFERENCE OR ``None``. It answers *whose semantic
    system said this*. ``producer_ref`` / ``producer_version`` are INDEPENDENT coordinates
    answering *which instrument did we extract it with*.
    """

    surface: str                                   # verbatim, as the source stated it
    source_vocab: str | None = None                # "schema.org" | "opengraph" | "rdfa" | …
    mapping_candidates: tuple[TypeMappingCandidate, ...] = ()   # >= 0; may legitimately be 0
    mention_ref: str = ""                          # the mention this statement is about
    structural_path: tuple[str, ...] = ()          # where in the document it sat
    observation_refs: tuple[str, ...] = ()         # canonicalised
    evidence_refs: tuple[str, ...] = ()            # canonicalised
    producer_ref: str = ""                         # observation channel identity (FR-006)
    producer_version: str = ""                     # pinned; brief §30 requires model/parser provenance
    signal_id: str = ""
```

| Instrument | `source_vocab` | `producer_ref` | `producer_version` |
|---|---|---|---|
| JSON-LD / schema.org statement | `"schema.org"` | `"jsonld-parser"` | `1.8.2` |
| regex CVE detector | **`null`** | `"cve-detector"` | `3.1.0` |
| person-name NER pass | **`null`** | `"ner-persons"` | pinned model version |
| surface / document / markup / metadata producers | the external vocabulary verbatim, or **`null`** | the instrument | pinned |

**No synthetic vocabularies.** `local`, `internal`, `regex` and `ner` MUST NOT be introduced in
order to avoid a `null` (`ARBITRATION.md`, section 7). A detector that reads no external vocabulary has
`source_vocab = null`, and the families that legitimately have no vocabulary are legal *because* of
it. A withdrawn `TypeSignalSource` enumeration stays withdrawn: it duplicated `source_vocab` +
`producer_ref`, and a new enumeration over an existing axis is how one field ends up with two
meanings — the same defect FR-011 fixed on `RelationSignal.kind`. The six brief §8 producing families are
therefore expressed as a *producer convention* (each instrument registers and writes `producer_ref`
plus the `source_vocab` value it declares), not as a new field.

**The signal may not carry a `core:` reference.** The first moment a local type may appear on this
path is `TypeHypothesis`, and reaching it requires a recorded mapping, so `schema:Person` can only
become `core:Person` by crossing a recorded `SemanticMapping` (FR-036, brief §9: "Never collapse … without
a mapping record"). This is an entity-side analogue of `RelationSignal`; it is **not** a
`SignalKind`, and brief §15's relation vocabulary is untouched.

**`TypeSignal` identity**, stated because nobody had: `signal_id` is derived from
`(tenant_id, producer_ref, producer_version, mention_ref, source_vocab, surface, structural_path)`.
It MUST NOT include `mapping_candidates` — a later mapping change is a new reading of the same
observation, not a new observation — and it MUST NOT include `mention_ref` alone, because two
sources may state the same thing about the same mention and §24/FR-006 require those to remain two
signals.

---

## 12. The mapping layer

Everything above is identity or structure. This section is the **claim** layer, and it sits
strictly below both.

```text
surface predicate → PredicateSignature → logical candidate identity          (part 1, part 3, part 5)
PredicateSignature → PredicateMappingCandidate(s) → relation_ref            (this section)
```

The two chains share one node — `PredicateSignature` — and **no field**. A change to any
`PredicateMappingCandidate` field, or to any `RelationRef`, moves `candidate_id` and MUST NOT move
`logical_candidate_id` (part 5.3). A table asserting that two base lemmas mean one relation, a curated
equivalence list, a regime's confidence and a Wikidata property are all *claims*, and all four are
versioned, citable and superseding.

### 12.1 The code that already exists, and why it changes the answer

`apps/shared/semantic/mappings.py` (1174 lines) is a complete, SSSOM-oriented, provenance-bearing,
content-addressed mapping apparatus. Its module docstring already states the design constraint this
section is about, at line 10: **"A mapping is a claim, not an identity."** That is structural, not
a promise in a comment.

| Symbol | What it is |
|---|---|
| `SemanticMapping` | one recorded cross-vocabulary correspondence; `identity` = `(tenant, subject_ref, object_ref, predicate, mapping_set_id, mapping_set_version)`; `content_key()`, `with_id()`, `to_dict()`, `cite()`, `conflicts_with()`, `supersedes_ref()` |
| `MappingSet` | one versioned alignment effort; content-deduplicated, canonically ordered |
| `MappingRegistry` | `mappings_for()`, `cite()`, `conflicts()`; returns tuples and never collapses |
| `MappingJustification` | `LEXICAL` / `MANUAL` / `INFERENCE` / `STATED_IN_SOURCE` |
| `MatchPredicate` | four values today: `EXACT_MATCH` / `CLOSE_MATCH` / `BROAD_MATCH` / `NARROW_MATCH` |
| `SemanticMappingRow` | the `semantic_mappings` table (migration `018`) |

**`TypeMapping` IS `SemanticMapping`. It is not a new dataclass** and this document does not mint
one, and it names `schema:Person` and `core:Person` explicitly. FR-036's eight items are, one
for one, fields `SemanticMapping` already has — including
its refusal to collapse `schema:Person` into `core:Person` without a record:
`subject_type` → `subject_ref` (+ `subject_scheme`), `object_type` → `object_ref` (+
`object_scheme`), `mapping_predicate` → `predicate`, `mapping_set` → `mapping_set_id` +
`mapping_set_version`, `mapping_version` → `mapping_version`, `confidence` → `confidence`,
`creator/operator` → `mapping_source` (+ `justification`), `evidence/provenance` → `provenance`.
Eight for eight, `schema:Person` → `core:Person` included. FR-036 needs a **task and a test**,
not a dataclass. `TypeMapping` is documented
as the brief's name for `SemanticMapping` — an alias plus the crosswalk above, not a type. A second
mapping record type with identical semantics would leave no way to tell them apart in
`semantic_mappings` and no way to enforce FR-036's "MUST NOT collapse `schema:Person` into
`core:Person` without a mapping record" across both.

**`PredicateMappingCandidate` is the only genuinely new type on the predicate side**, and it is a
*proposal* beside a *record*. It is deliberately not a subclass of, alias for, or wrapper around
`SemanticMapping`: its `source` is a `PredicateSignature` content key (a predicate term) where
`SemanticMapping`'s is a type reference normalised by `normalize_type_ref`; its `target` is a
*relation* reference (`wikidata:P127`, `schema:worksFor`) where `SemanticMapping`'s is a type; and
it has no row of its own until a `MappingSet` holds it.

```python
class MappingMatchType(StrEnum):
    """How a mapping process characterised one cross-vocabulary correspondence.

    SSSOM semantics, in this repository's snake_case dialect. "SSSOM-compatible" is a claim about
    meaning, not about spelling: the lexical forms are ``exactMatch`` … ``relatedMatch`` upstream
    and ``exact_match`` … ``related_match`` here, because every other enum in the semantic layer is
    snake_case and a second dialect would make ``str()`` comparisons across the layer silently fail.

    Read with the direction pinned, because ``narrow``/``broad`` are meaningless without it. For a
    candidate with ``source`` S and ``target`` T:

    ``exact_match``   a process asserts S and T denote the same extension. It does NOT license
                      treating them as one, and it does NOT license collapsing ``schema:Person``
                      into ``core:Person``.
    ``close_match``   same extension modulo a NAMED difference, recorded in ``provenance``.
    ``narrow_match``  S's extension is a proper SUBSET of T's - S fires on fewer cases.
    ``broad_match``   S's extension is a proper SUPERSET of T's - S fires on more cases.
    ``related_match`` S and T correspond and neither is comparable to the other by containment.

    "Extension" is the set of instances for a type mapping and the set of realisations a reading
    fires on for a predicate mapping; the same word, the same meaning, both layers.

    There is deliberately no ``unmapped``/``no_match`` value: absence of a record is how "no
    mapping" is represented, and a ``no_match`` record would be indistinguishable from a signal
    that was never mapped. US4 Acceptance 1 requires a mention surface with no pack entry to yield
    a retained ``TypeHypothesis`` with ``hypothesis_state=UNKNOWN``, not a dropped one.
    """

    EXACT_MATCH   = "exact_match"
    CLOSE_MATCH   = "close_match"
    NARROW_MATCH  = "narrow_match"
    BROAD_MATCH   = "broad_match"
    RELATED_MATCH = "related_match"


#: Retained name. Same enum, so every existing annotation, import and ``is`` comparison keeps
#: working. The four shared member values are byte-identical, so ``semantic_mappings.predicate``
#: values and every ``content_key()`` derived from ``str(predicate)`` are unchanged - which is a
#: test obligation, not a promise.
MatchPredicate = MappingMatchType
```

`related_match` is **new** and is required by the predicate layer, demonstrably: brief §20 forbids
mapping by similarity, so the correct match type for a pair with no containment relation must be
expressible, or the platform must record a false containment. §20 verbatim: "owns / controls /
manages → same relation / **just because they sound similar.** / Only unify when deterministic
normalization or explicit semantic mapping establishes that configuration." For a pair like
`controls` ↔ `wikidata:P127` the two case-sets are *incomparable* — a 10% non-controlling stake
satisfies one and not the other, and contractual control satisfies the other and not the one — so
`narrow_match` and `broad_match` would each assert a containment that is false, and `exact_match`
would assert identity. `related_match` is the one member that is true. Adding it is **safe and
asymmetric by construction**: no reverse `_MATCH_FIELDS[...]` lookup exists, so nothing raises, and
a `related_match` recorded on a `SemanticMapping` simply cannot be projected onto a `Concept`. That
asymmetry is correct and is stated rather than closed: a `Concept` declares links the vocabulary
itself asserts; a `MappingSet` records claims a *process* made, and "these correspond and are not
comparable" is a claim a process can make that a vocabulary does not declare.

**Proof obligation, because this touches a persisted CHECK-constrained column:** a test MUST assert
that the four shared values are byte-identical and that the `content_key()` of a fixed
`SemanticMapping` fixture is byte-identical before and after. If either fails, the alias is
withdrawn and `related_match` becomes a separate enum with a conversion refused at the boundary
rather than coerced.

```python
@dataclass(frozen=True)
class PredicateMappingCandidate:
    """One PROPOSED reading of one signature as one known operator.

    A claim made by a named actor, with evidence and a vocabulary version. Not identity, not
    truth, not a gate. Every field is revision material; **no field is identity-bearing**.
    """

    source: str                                    # PredicateSignature content key, FROM
    target: str                                    # external ref, TO; required, non-empty
    match_type: MappingMatchType                   # REQUIRED, NO DEFAULT - see part 12.2
    target_relation_ref: RelationRef | None = None # internal operator, if one is earned
    confidence: float = 0.0
    provenance: tuple[str, ...] = ()               # canonicalised, de-duplicated, sorted
    mapping_version: str = "1"                     # version of THIS mapping claim
    created_by: str = ""                           # the regime/process that made the claim
    evidence_refs: tuple[str, ...] = ()            # canonicalised, de-duplicated, sorted
    mapping_set_id: str = "predicate-mappings"
    mapping_set_version: str = "1"
    supersedes: tuple[str, ...] = ()               # a correction adds; it never edits
    mapping_candidate_ref: str = ""                # own content address, "" until with_id()
```

### 12.2 Why `match_type` is required with no default, and `confidence` defaults to `0.0`

`SemanticMapping` defaults `predicate: MatchPredicate = MatchPredicate.CLOSE_MATCH`
(`mappings.py:246`, `:438`). A silent `close_match` default is the mirror image of the defect §64
forbids — verbatim: "Do not silently treat mappings as exact equivalence if they are not." A default
of `close_match` silently treats *unspecified* as *close*, which is a claim nobody made.
`PredicateMappingCandidate` therefore has no default, and a positional construction without one is a
`TypeError`.

`SemanticMapping`'s default is **not** changed, because changing it would change
`evaluation_material()` and therefore `content_key()` for every row in `semantic_mappings` and every
id ever minted from one — a silent move of a content-address space, which FR-073 and §92 forbid far
more plainly than a wrong default does. Instead: every `SemanticMapping` constructed on the 021
path MUST pass `predicate` explicitly, and a test asserts that no `SemanticMapping` in `apps/` is
constructed without one. **The defect is recorded, not inherited silently and not papered over.**

`confidence` defaults to `0.0`, not `1.0`. A mapping nobody has scored is not maximally confident;
it is unscored, and `0.0` makes "no confidence recorded" visible in a stored row instead of
indistinguishable from "a process asserted this with full conviction".

### 12.3 The direction of the relationship, and its three one-way rules

```text
        PredicateSignature  ──(source = signature content key)──►  PredicateMappingCandidate
                 ▲                                                          │
                 │                                                          │ ACCEPTED
                 │ one-way; never written back                              ▼
                 └──────── MUST NOT ◄──────────  PredicateHypothesis.relation_ref
                                                  PredicateHypothesis.alternative_refs
                                                  PredicateHypothesis.resolution_state
```

1. **`signature → mapping candidates → relation_ref`.** `relation_ref` is a *projection* of the
   accepted mapping set, never an input. Nothing in the identity chain reads the mapping layer.
2. **A table asserting `owns` and `controls` mean one relation is expressible here, and only here.**
   Three separate `PredicateMappingCandidate` rows — `(own → controls)`, `(control → controls)`,
   `(possess → controls)` — against **three distinct** signature content keys, each with its own
   `match_type`, `confidence`, `provenance`, `created_by` and `evidence_refs`, and its own
   `mapping_version` naming the versioned artefact that asserted it. **The three candidates stay
   three candidates.** The platform can then *answer* "these are probably one relation" and *say who
   thinks so and on what evidence* — which is the difference between a mapping and a table keyed
   into identity. Note the reverse direction holds too: one signature may carry two candidates
   against two different targets with **no change to its content key**, therefore no change to
   `logical_candidate_id`, therefore a new `candidate_id` only. The map is many-to-many in both
   directions and is a function in neither; a design in which the target determined the identity
   would be a design in which recognising a relation forked the hypothesis.
3. **A proposal does not unblock a claim by itself.** `RelationClaimMaterial` still requires a
   resolved predicate (FR-024, §50): an `AMBIGUOUS` mapping state yields material no, claim no,
   edge no, exactly as §50 intends. And INV-003 verbatim: "No producer drops an observation because
   the semantic layer does not understand it. An ontology miss yields `UNKNOWN`, never rejection."

### 12.4 The two candidate types, and why there are two

`TypeMappingCandidate` is the type-side twin of `PredicateMappingCandidate`, sharing
`MappingMatchType` and the "extension" definition, differing in exactly one respect: its `source` is
a reference in a *type* vocabulary, normalised by `normalize_type_ref` (which preserves case,
because `schema:Person` and `schema:person` are different references), whereas a predicate source
is a signature content key. One match vocabulary, one direction convention, one `content_key()`
convention — and two candidate types, because a single generic `MappingCandidate` would have to
accept both normalisers and both scheme vocabularies on every field, which is how
`RelationSignal.kind` came to mix thirteen meanings before FR-011 split it.

`TypeSignal.mapping_candidates` and `TypeHypothesis.mapping_candidates` are both
`tuple[TypeMappingCandidate, ...]` — the same type on both, so FR-035 and FR-032 cannot contradict
each other on the record.

### 12.5 `SemanticMapping` is itself unreachable, and that is recorded here

`MappingRegistry(` and `MappingSet(` are **never constructed in production code** — the only two
call sites are inside `mappings.py` itself (`:671`, `:1113`). There is no non-test importer. This
belongs in `spec.md`'s *Production reachability, as measured* table, alongside
`SqlRelationClaimStore` and `GraphProjectionBridge`, because FR-036 (`schema:Person` →
`core:Person`) and FR-037 (`TypeSignal` → `TypeHypothesis` → `TypeAssertion`) are
unbuildable-and-unverifiable without it.

---

## 13. Persistence mapping (migration `021`)

`020_universal_relation_extraction` is the current Alembic head and is forward-only
(`downgrade()` raises `NotImplementedError`). `020` is not edited.

### 13.1 `participants` is a typed structured field in `021`, not `extra`, not `022`

After the additive structural phase the canonical domain object is **n-ary**, and a persistence
layer that cannot hold it losslessly violates the feature's own `build → store → read → identical
object` obligation and breaks US7. `021` therefore adds, to **both** `relation_signal` and
`relation_candidate`:

```text
participants  JSONB NOT NULL      typed structured field, canonical serialisation
```

It is **not** `extra`. `extra` is an untyped escape hatch and reusing it would reproduce the defect
that made n-ary unrepresentable. The canonical serialisation is **defined by the identity
subsystem's participant ordering** (part 4.2 O1–O5), so a stored `participants` round-trips to an
identical in-memory object and re-derives an identical `signal_id` / `logical_candidate_id`. Load
bearing dimensions are typed, not a bag of JSON (brief §14, FR-010).

`subject_mention_ref` / `object_mention_ref` are **retained as compatibility accessors for binary
records** and become derived from `participants[0]` / `participants[1]`. They are never a second
source of truth. **There is no artificial feature split and no deferral to `022`.**

`020`'s `ck_relation_candidate_distinct` and `ix_relation_candidate_pair` are defined over the
binary shape, so widening *them* means rewriting rows that hold observations, which Principle I
forbids. The additive phase therefore introduces `participants` and `SignalBasis` **without**
removing the binary columns; retiring the binary constraints and indexes is a separate, later step
that moves them forward. `020` is not edited either way.

### 13.2 The four schema operations: three DROPs and one ADD

| # | Operation | Object | Old text / value | Replacement |
|---|---|---|---|---|
| 1 | **DROP** `ck_relation_signal_asserts_something` | `relation_signal` | `relation_surface <> '' OR relation_ref IS NOT NULL` | the observational-basis rule (brief §16) — a **strict superset** of what it replaces, so no stored row can become invalid |
| 2 | **DROP** `ck_relation_candidate_asserts_something` | `relation_candidate` | `relation_surface <> '' OR relation_ref IS NOT NULL` | the four-ground rule. **The two replacements differ**, because a signal has an observation channel and a candidate has none |
| 3 | **DROP** `ck_relation_signal_kind` | `relation_signal` | a whitelist of 13 literals | recreated over 15 literals (part 6.1). This one **narrows**, so a pre-flight `SELECT` for rows carrying a removed kind **refuses** rather than rewriting them: those rows are observations, and Principle I forbids editing one |
| 4 | **ADD** `observational_basis` | `relation_signal` | — | `String(24)`, nullable, the subject of replacement #1. Type `SignalBasis` (brief §16), whose nine values are exactly the nine names `input.md:1125-1137` gives, and which **no artefact named before this file and the migration repair** |

**Operation 4 is the fourth operation, and it is the one that was missing.** The three DROPs are
the visible half of the story. The ADD is invisible until you try to write the migration, and then
it is blocking: a column whose value domain is a new closed vocabulary cannot be declared by a
migration that reads a value type whose meaning can change underneath it, so the nine names are
written out in the migration (`_OBSERVATIONAL_BASES_021`) **and** a test asserts the two lists are
equal. `021` that adds columns no code writes reproduces the defect it was created to fix, so the
migration MUST be ordered after the value types it stores — `PredicateSignature`, `Polarity`,
`SignalBasis` — and after the domain fields it mirrors.

### 13.3 The added columns and tables

| Table | Added columns | Null | Class |
|---|---|---|---|
| `relation_signal` | `participants` (JSONB), `predicate_signature_key`, `predicate_normalized`, `predicate_arity`, `predicate_roles`, `predicate_argument_shapes`, `predicate_polarity`, `predicate_mappings` (JSONB, structured), `predicate_mapping_evidence`, `observational_basis` | all NULL except `participants`, no default | 7 identity-bearing, 2 revision material, 1 basis attestation |
| `relation_candidate` | `participants` (JSONB), `predicate_signature_key`, `predicate_normalized`, `predicate_arity`, `predicate_roles`, `predicate_argument_shapes`, `commutative_slots`, `polarity`, `direction`, `signal_refs`, `predicate_mappings` (JSONB, structured), `predicate_mapping_evidence`, `confidence` | all NULL except `participants` and `confidence` (NOT NULL, default `0.5`) | 8 identity-bearing, 3 revision material, 1 mutable projection |
| `relation_claim` | `candidate_id` (NOT NULL, default `''`), `validation_record` (JSONB, NULL) | — | `candidate_id` identity-bearing and **already inside `content_hash`**; `validation_record` decision metadata, **deliberately outside it** |
| `validation_findings` | `candidate_id` (NULL) | — | attachment for a candidate-stage finding |
| `type_signals` (**NEW TABLE**) | `signal_id`, `tenant_id`, `mention_ref`, `source_vocab` (nullable), `surface`, `structural_path`, `producer_ref`, `producer_version`, `observation_refs`, `evidence_refs`, `mappings` (JSONB, structured) | — | the entity-side observation record (part 11) |
| `type_mapping_candidates` (**NEW TABLE**) | one row per `TypeMappingCandidate`, mirroring `semantic_mappings`' columns | — | proposals, not records (part 12.4) |
| `semantic_mappings` | **no new columns** — `SemanticMapping` already persists subject/object, scheme, predicate, set id + version, source, version, justification, provenance, confidence, observed_at, supersedes (`db/schema.py:1477`, migration 018) | — | the recorded type mapping (part 12.1) |
| `source_temporal_observation` | none — a repository, writer and reader, which the table has **none** of today | — | FR-096 |

**Two columns the previous table listed are gone, deliberately.** `predicate_direction` is **not**
added to `relation_signal`, because `relation_signal.direction` already exists, is `NOT NULL`, and
already carries a closed-vocabulary CHECK: a second direction column is a second column that can
disagree with the first. On `relation_candidate` the signature's direction and polarity are added
**once each**, under the names FR-088 requires (`direction`, `polarity`).

`predicate_mappings` replaces the previous `predicate_alternatives` because it no longer holds
alternatives alone: it holds the **full live set** of mapping candidates, primary included, because
the primary is a designation rather than a winner and storing only the others would make the store
unable to reconstruct which reading was ranked first. `JSONB` is acceptable here and only here:
brief §14's "do not turn the entire thing into arbitrary JSONB" forbids *core, load-bearing dimensions*
going untyped, and each entry is a typed `PredicateMappingCandidate` with a lossless
`to_dict()`/`from_dict()`, not a bag.

ORM/migration parity is test-enforced for `020` and MUST stay enforced for `021` — **and the parity
test MUST compare CHECK constraints by text, not only by name**, because a vocabulary that changes
on one install path and not the other leaves the names identical.

### 13.4 Three tables are written by nothing, and that orders the work

**Today, three tables are written by nothing.** No `INSERT` for `relation_signal`,
`relation_candidate` or `source_temporal_observation` exists anywhere in `apps/`, `bench/` or
`tools/`. Persistence is therefore the largest single block of work in this feature — and **`021`
that adds columns no code writes reproduces the defect it was created to fix**, so the migration
MUST be ordered after the value types it stores and after the domain fields it mirrors.

`SqlRelationClaimStore` (558 lines) has zero importers. Its `record_validation`/`non_valid` raise
`NotImplementedError` because migration 016 never created a home for a verdict, and the store names
the column it wants in the error message itself. `021` creates that home forward
(`relation_claim.validation_record`); the store's own `_validation_column()` resolves it from ORM
metadata, so **the disappearance of `NotImplementedError` is provable without a database**. Leaving
it unfixed is not a stable state: the resolution scans for the first non-owned JSONB column, so the
day any other JSONB column lands on `relation_claim` the verdict is written into it with no code
change.

Persistence is the one area where "verified" and "verified only offline" differ, because live
PostgreSQL is not reachable in this environment. The completion report MUST say so clause by clause
rather than reporting the block as verified.

---

## 14. Graph projection

`GraphProjectionBridge` is already correct and must not change shape: it is typed
`claim: RelationClaim` with no overload, so **a candidate or a signal cannot be projected even
by mistake** — the constitution holds at the type level (INV-004). `to_edge` mints nothing
(`edge_id=claim.relation_id`); `to_hyperedge` refuses a non-NARY claim and builds members from
`role_bindings`. A `DIRECTED` claim projects with direction preserved and is never canonicalised by
`min`/`max` (FR-063, §52); an `UNDIRECTED` claim may canonicalise endpoint ordering **only** when
the admitted relation contract declares symmetry, and symmetry is never inferred from an extractor
not knowing the direction: `UNDIRECTED` ordering needs a declared contract (FR-064, brief §53) — which is why `commutative_slots` must exist on the
candidate and not only on the claim (part 4.5).

Two gaps to close: `properties` carries no `direction` or `polarity` (only `arity_mode`), and there
is no wired rebuild-from-store path. The projection change is therefore additive metadata plus a
rebuild test — not a re-architecture. Switching the production default from `InMemoryGraphStore` to
`Neo4jGraphStore` is explicitly **out of scope** (research R-006): the Neo4j store is unwired, does
not import the driver, and lives in a package that does not declare the dependency, so switching
would trade one unwired integration for another.

`WorldLine` is a third projection of an admitted claim (FR-055, §101) and is on the diagram; it has
no field list in this document and **silent omission is not permitted**, so it is recorded here as a
gap owned by the lifecycle band rather than left out of the list.

---

## 15. Evidence lineage is not derivation lineage (two hop vocabularies)

Fully separated, permanently. A candidate and a signal may be *connected to* the evidence graph,
but they **never become evidence** because derivation passes through them.

```text
EVIDENCE lineage      edge → claim → evidence → observation → capture/raw → source
DERIVATION lineage    edge → claim → candidate → signal → observation
```

**The measured defect that forces the split** (`ARBITRATION.md`, section 9). `HopKind`
(`apps/shared/domain/evidence_lineage.py:50-65`) has nine values today and **`SIGNAL` is not one
of them**:

```python
class HopKind(StrEnum):
    SOURCE = "source"
    CAPTURE = "capture"
    OBSERVATION = "observation"
    SEGMENT = "segment"
    MENTION = "mention"
    CANDIDATE = "candidate"
    ASSERTION = "assertion"
    RELATION = "relation"
    ENTITY = "entity"
```

`EVIDENCE_BACKWARD_CHAIN` is `RELATION, ASSERTION, MENTION, SEGMENT, OBSERVATION, CAPTURE, SOURCE`
and `DERIVATION_FORWARD_CHAIN` is `SOURCE, CAPTURE, OBSERVATION, SEGMENT, MENTION, CANDIDATE,
ASSERTION, RELATION, ENTITY`. So the `SC-013` round trip
`edge → claim → candidate → signals → observations → source` and back is **unreachable in both
directions** — and adding `CANDIDATE` to the backward chain would not fix it, because `SIGNAL` is
absent from *both* chains. This is a **type-vocabulary defect, not a chain-ordering defect**, and no
reordering of a tuple fixes it. Constitution **II. Evidence-First** names a required chain that includes a
signal-bearing level, and the repository's ladder has no value corresponding to it.

**The fix is two distinct hop vocabularies in `evidence_lineage.py`, not one `HopKind` used for
both.** A hop in the evidence chain answers "what is this evidence under?"; a hop in the derivation
chain answers "what produced this?". A candidate and a signal answer the second question, so they
are members of the derivation vocabulary only, and the evidence vocabulary is what Principle II is
satisfied by.

**Consequences, all binding:**

- `INV-005` stands: a candidate is derivation, never evidence. `SC-013` is **reformulated as a
  provenance round-trip**, not as an attempt to seat the candidate inside a constitutional warrant
  chain. The candidate is therefore *reachable* from an edge — SC-013 becomes satisfiable — while
  never being evidence.
- Constitution Principle II (Evidence-First) is satisfied by the *evidence* chain above and is not
  weakened by the candidate's absence from it.
- The `schema.py` comment defending `SignalKind.NEGATION` becomes **false** when part 6.1 drops that
  value, and must be rewritten in the same commit: a stale comment defending a value the CHECK no
  longer admits is a disabled verifier whose comment asserts it passes, which is the failure FR-098
  names.

---

## 16. Entity summary

| Entity | Status | Identity key | Notes |
|---|---|---|---|
| `PredicateSignature` | NEW (v2) | `IDENTITY_SCHEMA_VERSION` + content key | 7 fields. Structure only — no surface, no mapping, no table of near-meaning words, no entity id. `arity` and `direction` are derived |
| `ArgumentSlot` | NEW | — | `A0`, `A1`, … A formula over positions, not a named set. Integer-compared, never token-compared |
| `ConstructionFrame` | NEW | — | Closed structural vocabulary, 1 observed-only value + 10 canonical. Carries the passive demotion |
| `ArgumentMarker` | NEW | — | Closed inventory of 15 function-word values, no alias table, no cross-word folding |
| `RoleBinding` | NEW (v2) | `canonical_argument_slot` only | `surface_role` and `role_hypothesis` are evidence. Bump ⇒ new logical id; empty version ⇒ contract error + quarantine, no default |
| `Polarity` | NEW | — | Replaces `SignalKind.NEGATION`; enters **logical** material on the candidate |
| `SignalBasis` | NEW | — | The nine observational bases of brief §16. Named by no artefact before this file; the subject of the added `observational_basis` column |
| `RelationParticipant` | CHANGED | (slot, mention fingerprint) | Variadic; replaces the two scalars. Carries a structural `ArgumentSlot`, not `role: str` |
| `RelationSignal` | CHANGED | `SIG-` + digest over signature + participants + `producer_ref` | Natively n-ary. `normalized_predicate` is a derived read |
| `CandidateAssemblyState` | NEW | — | `CONSISTENT` / `AMBIGUOUS` / `CONFLICTING`. The structural axis; revision material, never logical |
| `RelationCandidate` | CHANGED | `CAND-` + digest over the part 5.1 material | `relation_surface` becomes evidence; `relation_ref` becomes a derived projection of the hypothesis |
| `PredicateHypothesis` | EXTENDED | — | Mapping state, separate from structure. `mapping_candidates` stored, `alternative_refs` derived, `normalized_form` derived |
| `MappingMatchType` | NEW | — | Five SSSOM values, snake_case, direction pinned; no `unmapped` value |
| `PredicateMappingCandidate` | NEW | — (none) | A proposed predicate mapping. **No field is identity-bearing**; all is revision material. Not a rung (§103) |
| `TypeMappingCandidate` | NEW | — (none) | A proposed type mapping; all revision material. Shares `MappingMatchType` |
| `TypeMapping` | ALIAS | `SemanticMapping`'s digest | **Not a new type.** FR-036's eight items are `SemanticMapping`'s eight fields, `schema:Person` → `core:Person` included |
| `TypeSignal` | NEW | `TSIG-` + digest | What a source *said* about a type. `source_vocab` is an external reference or `null`; carries no `core:` ref |
| `TypeHypothesis` | CHANGED (v2) | — (none) | **ONE** interpretation candidate: 13 fields, 6 states. A nested value object, not a level |
| `MentionOccurrenceIndex` | NEW | `MN-` + digest | The only minter of mention ids. The stage is `MENTION_BINDING`; the structure is this; the id form is `MN-…` |
| `TypePack` / `TypePackEntry` | NEW | `core-atomic-types@1` | 31 entity + 13 value = 44 entries. `namespace` + `pack_ref` per entry; `kind` required and non-defaulted; registered through the existing `OntologyPackRegistry`; never a gate, never a completeness condition |
| `MentionTypeSets` (field, not a type) | — | — | `type_hypotheses: tuple[TypeHypothesis, ...]` on `TypedMention` and `ResolutionMention`; the **set** lives here, not in a hypothesis |
| `RelationClaimMaterial` | unchanged | `RL-`/`RC-` | Boundary already correct: `relation_type` required here, not in the candidate. Gate moves from "is the string empty" to "is the state `KNOWN`" |
| `RelationClaim` | EXTENDED | `RL-`/`RC-` | Must self-verify its carried id (FR-099) |
| `GraphEdge`/`HyperEdge` | unchanged | derived from `relation_id` | Projection only, claims only |
| `WorldLine` | NEEDS-SPEC | — | A third projection of an admitted claim (FR-055, §101). No field list yet; listed so the omission is visible rather than silent |
| `ValidationReport` | NEEDS-SPEC | — | First-class in the approved diagram, absent from this document. Owned by the Phase-6 band; a `NEEDS-SPEC` row is a promise, not a specification |
| `AdmissionDecision` | NEEDS-SPEC | — | As above |
| `SourceTemporalObservation` | unchanged | `STO-` | Needs a repository to be reachable at all. `SignalKind.TEMPORAL` is the channel; this type is the content |

### 16.1 Open questions recorded here rather than decided

| # | Question | Why it is not decided in this document | Stop condition |
|---|---|---|---|
| U1 | Should `is CEO of` / `became CEO of` / `was appointed CEO of` be one logical relation? | §19 illustrates it; §20 forbids establishing it by anything but deterministic normalisation or explicit semantic mapping; and it needs either a lemma merge or an elided-agent inference, both semantic. | **Not decided.** Unification is available only through part 12, as `PredicateMappingCandidate` rows against distinct signature content keys. Tests: `test_agentless_passive_is_unsupported_not_guessed`, `test_become_and_be_are_distinct_signatures` |
| U2 | Should `works at` and `works for` be one logical relation? | Same: a preposition merge is a lexical-semantic claim, and `ArgumentMarker` exists precisely so it cannot be made by accident. | **Not decided.** Two signatures; part 12 may propose one operator for both. Test: `test_works_at_and_works_for_are_distinct_signatures` |
| U3 | Should a relative clause collapse with its matrix-free paraphrase? | Requires the inference "the matrix NP is the relative clause's subject", true commonly and false for reduced relatives and adjuncts. A usually-right rule is a guess. | **Not decided.** `RELATIVE_CLAUSE` is its own frame (part 3.4 row 10) |
| U4 | Should a copular predicate collapse with a bare appositive? | Same class as U1, and §29 lists them as separate constructions. | **Not decided.** Two frames (part 3.2) |
| U5 | Is coordination a commutative non-commutative slot? | Requires deciding whether coordination preserves argument structure — a linguistic question, and the frame is not in §29's list. | **Not decided.** `UNSUPPORTED_CONSTRUCTION` until a coordinated frame *and* a symmetry marker exist (part 4.4). Never ordered by guess |
| U6 | What is the ordering between two mentions that resolve to the same entity? | Entity resolution is downstream of the candidate. | **Out of scope by construction.** The material is over **mentions** (part 4.3), so two mentions of one entity are two participants. This is the correct answer, not a gap |
| U7 | Is `core:Coordinate` intended, or a typo for `core:GeographicRegion`? | The brief lists it in "Place / geography" and again under "Values". | **Not decided** (part 10.5). Ship both entries; record the question. Do not delete a vocabulary entry on a guess |
| U8 | Does the claim layer's `RelationArityMode.UNDIRECTED` sort get replaced in 021 or later? | `relation_identity.py` is not this file's to change. | **Recorded, not applied** (part 4.7). The identity subsystem is specified as one unit so the claim-layer half can be applied by its owner without re-deriving anything |
