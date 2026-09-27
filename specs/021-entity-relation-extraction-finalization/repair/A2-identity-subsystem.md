# Repair A2+A3+A4a — The Identity Subsystem

**Job**: A2+A3+A4a | **Feature**: 021-entity-relation-extraction-finalization | **Date**: 2026-09-27
**Repo root**: `C:\Users\tim\Desktop\COGNITIVE\1` | **Replaces**: `data-model.md` §1, §3 (identity
rule), §5 (the signature-carrying parts) and the `FR-001…FR-010` block in `spec.md`
**Code read at**: `apps/shared/domain/relation_identity.py`, `apps/shared/domain/relation_candidate.py`,
`apps/shared/domain/predicate_hypothesis.py`, `apps/shared/domain/relation_claim.py`

---

## 0. Scope, and the three prohibitions this file is written under

`PredicateSignature`, voice normalisation and canonical participant ordering are **one subsystem**
and are specified here as one subsystem. They cannot be split, because the identity rule in D5 is a
composition of all three: if the slot convention (D2/D3) changes, or the ordering rule (D4) changes,
the logical id changes for every candidate, so a spec that fixes any one of the three and leaves the
other two open has not fixed identity.

**P1 — There is no synonym table, at any layer, in this file.** The previous attempt's N5
(`owns ≡ controls`) is deleted, not repaired. It is forbidden by FR-004, by `input.md` §20
("Do not do: owns / controls / manages → same relation just because they sound similar"), by US2
Acceptance 3, and by constitution Domain Invariant 3 (`Assertion != truth`). The replacement
mechanism is a **generated morphology table with a committed digest** (§ D3, step V3) whose only
admissible rows are (a) inflectional rules and (b) an explicitly enumerated list of derivational
suffixes. There is no row type that maps one base lemma onto a different base lemma, so the
forbidden mapping is not merely discouraged, it is unrepresentable in the data structure.

**P2 — No free text enters identity.** Not the surface, not the role string, not the frame
template, not the preposition. Every identity-bearing term is either a version string, a closed
enumeration member, a structural slot index, or a digest. `surface_role` is free text and is
**evidence only** (D2).

**P3 — `TypeHypothesis` is not touched.** Review finding E3 flagged the previous attempt for
redefining `TypeHypothesis` as a container of `TypeCandidate`s, which is another agent's job
(A5) and a new epistemic level. This file contains zero changes to `TypeHypothesis`, `TypeCandidate`
or `CandidateResolutionState`, and the participant fingerprint in D4 explicitly **excludes** type
material so that A5's work cannot fork a logical id.

---

## D1 — `PredicateSignature` v2

### D1.1 The dataclass, verbatim

```python
IDENTITY_SCHEMA_VERSION = "cand-logical-2"
"""Version of the identity material's shape. Bumped when a key is added or removed from
the identity projection, never when a rule's content changes — a rule change bumps the
rule's own version field instead (see D1.5)."""


@dataclass(frozen=True, slots=True)
class ArgumentSlot:
    """A canonical, structural argument position: ``A0``, ``A1``, ``A2``, …

    NOT an ontology of reality. See D2.2 for the six properties that make it a structural
    representation, and D2.3 for the versioning discipline. Ordered by the wrapped
    integer, never by the token text: ``A10`` sorts after ``A2``, and a string sort would
    place it before. That is not a cosmetic difference — it changes the canonical material.
    """

    index: int

    def __post_init__(self) -> None:
        if self.index < 0:
            raise SignatureContractError(
                "negative_argument_slot", f"argument slot index must be >= 0, got {self.index}"
            )

    @property
    def token(self) -> str:
        """``"A0"``, ``"A1"``, … — the serialised form used in canonical material."""
        return f"A{self.index}"

    def __lt__(self, other: "ArgumentSlot") -> bool:
        return self.index < other.index

    def to_identity(self) -> str:
        return self.token


class ConstructionFrame(StrEnum):
    """The construction a predicate was realised in, as a closed structural vocabulary.

    ``VERB_PASSIVE_AGENT`` is an OBSERVED frame. It is admissible on a
    ``RelationSignal.observed_construction_frame`` and is **never** admissible on a
    ``PredicateSignature.construction_frame``, because voice normalisation demotes it to
    ``VERB_ACTIVE_TRANSITIVE`` (D3 step V1). Carrying the observed passive frame in the
    signature is precisely the defect that keeps an active and a passive realisation apart,
    and ``verify_canonical_frame()`` exists to make that unmissable.
    """

    # — the one demotion, per D3 (P-CANON) —
    VERB_PASSIVE_AGENT = "verb_passive_agent"          # observed only

    # — canonical frames: one per construction brief §29 names, plus two sub-frames it
    #   requires to be total. No construction outside this enum is supported (D3.3). —
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

    A CLOSED, VERSIONED INVENTORY, not a mapping. There is deliberately no alias table and
    no member is ever normalised onto another: ``by`` is not ``with``, ``of`` is not
    ``for``. A preposition outside this inventory is ``UNSUPPORTED_CONSTRUCTION`` (D3.5),
    never ``NOMARK`` and never a guess. This is the only lawful form of FR-003's
    "preposition normalization" and "particle normalization": **form** normalisation
    (NFKC, casefold) over a closed set, never cross-word equivalence. A field that
    "normalised" ``at`` to ``for`` would be a synonym table with a different field name.
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

    This is the sole predicate term in ``logical_candidate_id`` (D5). It is derived BEFORE
    ontology mapping and is never re-derived from a mapping, a registry, an operator list
    or a learned model (D5.2, D7.3). It is not a ``RelationRef`` and not a semantic
    ontology concept (input.md §18, verbatim: "It is NOT a RelationRef. / It is NOT a
    semantic ontology concept. / It is a structural/language-normalized signature.").

    Field order is the identity order: language, lemma, frame, markers, slots, then the two
    rule-set versions. Every field participates in identity except the last two, which
    participate by *pinning* the first five — a signature with an empty version string is a
    contract error, never a legacy row silently upgraded (D2.3).
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
        """The exact dict that enters ``canonical_material`` in D5. Nothing else may."""
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
        ``normalized_predicate`` / ``normalized_form`` reads (D1.6) and for logs.

        Form: ``<lemma>(<slot>:<marker>,<slot>:<marker>,…)``, marker omitted when NOMARK.
        ``"John acquired Acme."`` → ``"acquire(A0:,A1:)"``.
        """
        args = ",".join(
            f"{slot.token}:{marker if marker is not ArgumentMarker.NOMARK else ''}"
            for slot, marker in zip(self.canonical_argument_slots, self.argument_markers, strict=True)
        )
        return f"{self.predicate_lemma}({args})"
```

### D1.2 The v1 fields removed, and why — each one

`data-model.md` §1 currently declares (verbatim, lines 23–31):

```python
class PredicateSignature:
    normalized_predicate: str          # NFKC, casefold, whitespace/punct-folded, verb-normalised
    arity: int                        # >= 2; n-ary is native
    role_names: tuple[str, ...]       # length == arity; positional when unnamed
    argument_shape: tuple[str, ...]   # per-argument shape code, e.g. "entity", "value", "literal"
    direction: DirectionHypothesis    # subject_to_object | object_to_subject | undirected | ambiguous
    polarity: Polarity                # asserted | denied | uncertain
    schema_version: str = "1"
```

| v1 field | Disposition in v2 | Reason, stated once |
|---|---|---|
| `normalized_predicate: str` | **REPLACED** by `predicate_lemma: str` | A "normalised predicate" that is a free string is a synonym table waiting for a contributor. Its only lawful normalised form is a lemma from the generated morphology table (D3 V3), and that is what `predicate_lemma` is. Two of the v1 field's jobs (NFKC/casefold, "verb-normalised") are the *procedure*, and a procedure belongs in a versioned rule set, not in a field. |
| `arity: int` | **DERIVED** as `len(canonical_argument_slots)` | Carrying both invites a state where they disagree, and the disagreement is a silent identity fork. A property cannot drift from its source. |
| `role_names: tuple[str, ...]` | **REPLACED** by `canonical_argument_slots: tuple[ArgumentSlot, …]` | This is review finding **E2**, verbatim: *"`role: str` free text inside `logical_candidate_id` — relocates the exact defect the feature exists to destroy. `purchaser` vs `buyer` forks the logical id."* Free-text role names are surface vocabulary. The slot is structural, closed and versioned (D2). |
| `argument_shape: tuple[str, ...]` | **MOVED OUT** to `RelationParticipant.argument_shape` (already `data-model.md` §2's field) and **excluded from identity** | Shape is a fact about a *referent*, not about the predicate. Worse, if it entered identity then A5's reclassification of a mention (a type-layer change) would fork a relational identity — two subsystems' changes coupled through a digest. The participant fingerprint in D4.3 therefore excludes it explicitly. |
| `direction: DirectionHypothesis` | **DERIVED** from `(canonical_argument_slots, commutative_slots)`; retained only as a read-only projection | It can disagree with the slot order, and a disagreement is an identity fork. The validator is `verify_direction_agrees_with_slots()` (D2.5). |
| `polarity: Polarity` | **MOVED OUT** to `RelationCandidate.polarity` | Polarity is the structure of the *assertion*, not of the *predicate*. §109 Case H requires `predicate = acquire` for "John did not acquire Acme", i.e. the same predicate under the opposite polarity — so polarity on the signature would make the same predicate two predicates. FR-002 and §19 both require polarity in logical identity, and it is there, on the candidate. |
| `schema_version: str = "1"` | **REMOVED** | `relation_candidate.py:510-512` states the rule verbatim: *"`schema_version` is absent on purpose: it is the *operator* version, so a hypothesis read under a newer operator contract is a new reading of the same hypothesis, not a new hypothesis."* Putting it on the signature would move the operator version into the identity term, which is the same defect as carrying `relation_ref` (D1.3). The signature's schema identity is the pair `(voice_normalization_version, predicate_normalization_version)`. |

### D1.3 What `PredicateSignature` MUST NOT carry, and why — each one

| Absent | Why, stated once |
|---|---|
| `raw_surface` / `predicate_surface` / `relation_surface` | Raw words are evidence, never identity (FR-001, input.md §17, §19, §23). §18's own worked requirement is that two *different* surface strings produce one signature while "retaining two distinct surface observations: as evidence". A surface inside the signature makes that arithmetically impossible. |
| `trigger_span` / `supporting_spans` | §14 places them on the **signal**, not the signature, and FR-001 places them in revision/evidence material. A span is a location in one document; one logical configuration observed in two documents has two spans and one id. |
| `producer_ref` / `producer_version` / `extraction_rule_id` / `extraction_method` | FR-001 and §23 exclude them. `signal_id` is *supposed* to be producer-specific (FR-006, §24, and the module docstring at `relation_candidate.py:626-649` which is right about this); putting the producer in the *candidate's* logical term would extend producer scope from the observation level to the hypothesis level, breaking US5 and SC-005. |
| `evidence` / `observation_refs` / `evidence_refs` / `signal_refs` | FR-001, §23. Corollary worth stating: the candidate *docstring* at `relation_candidate.py:626-649` argues that whether a relation is hypothesised is settled by the mentions and the predicate while which observations back it is a separate fact that grows. `signal_refs` in logical material would make the second producer mint a second hypothesis instead of a second reading — the opposite of §43's "ONE logical candidate / MANY signals". |
| `confidence` | FR-001. `relation_identity.py:289-292` states the general reason verbatim: *"a re-scoring pass must not mint a new relation, or every ranking change forks the graph."* |
| `relation_ref` (and therefore `relation_type`, `schema_version`, `alternative_refs`, `mapping_evidence_refs`, `resolution_state`) | Mapping to a known operator is a later, versioned step (R-002 point 4: "The signature is derived before ontology mapping, not after"). Keying on it would re-split one hypothesis into two the moment a regime recognised it — the exact failure `relation_candidate.py:1119-1126` documents, generalised. D5.2 makes this a constitutional invariant rather than a docstring. |
| any normalized-predicate **mapping** | §20: "Only unify when deterministic normalization or explicit semantic mapping establishes that configuration." A mapping inside the identity term means the identity *is* the mapping, so the mapping can no longer be revised, contradicted, or attributed. That is review finding **E1** in a new field name. Forbidden. |
| any normalized **raw-surface synonym** | Review finding **E1** verbatim: *"`owns ≡ controls` as the worked synonym example — forbidden by FR-004, by §20, by `US2` Acceptance 3, and by constitution INV-3. The signature's `normalized_predicate` is the predicate term of `logical_candidate_id`, so a synonym table is an identity authority."* Concretely: the v1 signature admits a row type ("a small, versioned, sourced synonym table") that is a *claim about equivalence*, keyed into identity, with no ADR (review **K5**: the constitution's Governance clause names "entity resolution" as requiring one, and a synonym table is entity-resolution-grade). Deleted. Replaced by the mapping layer (D7), where it is dated, attributed, evidence-bearing and revisable — i.e. where a *claim* belongs. |
| any entity id / mention ref | `Mention ≠ Entity` (constitution Invariant 2, spec.md INV-001). The signature describes the *shape* of a reading. Participants live on the binding and enter identity through the fingerprint (D4). |
| `temporal` markers / event time | Temporality is orthogonal to arity and to predicate structure — `relation_identity.py:26-37` states it verbatim: *"An earlier `RelationArityMode.TEMPORAL` conflated the two and has been removed."* §109 Case D's `time = 2020` is a `TemporalHypothesis` on the candidate and is revision material. A year inside the predicate would make "sold in 2020" and "sold in 2021" different predicates, which is a category error, not a normalisation. |

### D1.4 Reconciliation with FR-003's nine required fields

`spec.md:383-386` verbatim:

> - **FR-003**: System MUST provide a deterministic `PredicateSignature` carrying at least
>   language, normalized trigger, lemma, normalized frame, normalized argument roles,
>   voice normalization, preposition normalization, particle normalization and event-class hint.
>   It MUST NOT be a `RelationRef` and MUST NOT be a semantic ontology concept. (§18)

`input.md` §18 says **"It may contain"** — a list, not a mandate. FR-003 promoted it to "MUST … at
least". FR-003 therefore needs a correction, and the correction is one mapping per field:

| # | FR-003 field | v2 disposition | Field or type in v2 | Justification |
|---|---|---|---|---|
| 1 | `language` | **MAPPED** | `language: str` | Kept verbatim. A cross-lingual pair is two signatures, because cross-lingual unification is a semantic claim and §20 reserves that to explicit mapping. |
| 2 | `normalized_trigger` | **REMOVED** (as a field) → merged into #3 | — | The trigger is a surface token. Normalising it either (a) yields the lemma, in which case the field is redundant with #3, or (b) yields a function-word/preposition residue, in which case it is #7+#8 and carrying it twice doubles the surface for no structural gain. The *procedure* is retained, versioned, in `predicate_normalization_version`. |
| 3 | `lemma` | **MAPPED** | `predicate_lemma: str` | Kept, and promoted to the sole predicate term. |
| 4 | `normalized_frame` | **MAPPED, TYPE CHANGED** `str` → `ConstructionFrame` | `construction_frame` | A free-text frame template is free-text identity: two implementations would spell the same frame differently and fork every id. A closed enum makes the frame space enumerable, testable and diffable. The frame is also **canonical, not observed** (D1.1) — that is what makes active ≡ passive. |
| 5 | `normalized_argument_roles` | **MAPPED, TYPE CHANGED** `str` → `ArgumentSlot` | `canonical_argument_slots` | This is the one FR-003 field that is **forbidden** from being free text, and the type change is the enforcement. Review finding **E2** is a finding about this exact field. "Normalized" here means *structurally assigned*, not *lexically harmonised*: `purchaser` and `buyer` both become `A0` or `A1` or `A2` according to where they sit in the construction, and which one they become is decided by the parse, not by a vocabulary. |
| 6 | `voice_normalization` | **MAPPED, TYPE CHANGED** `bool`/`str` → `str` (a version) | `voice_normalization_version` | A boolean is not reproducible: two signatures differing only in whether normalisation ran are indistinguishable in the record, so the identity cannot be re-derived later. A version string is reproducible and is the same discipline `relation_identity.py:274` already applies to `normalization_version`. The *result* of voice normalisation is not a field because it is expressed by fields 4 and 5. |
| 7 | `preposition_normalization` | **MERGED with #8**, TYPE CHANGED `str` → `ArgumentMarker` | `argument_markers` | Prepositions and particles are the same class of thing — function words marking argument structure. Splitting them into two fields buys nothing. The lawful normalisation is form-only over a closed inventory. |
| 8 | `particle_normalization` | **MERGED with #7** | `argument_markers` | As above. |
| 9 | `event_class_hint` | **REMOVED** | — | An event class ("transfer", "control", "acquisition") is a semantic category, and a *hint* is a mapping. §18 forbids the signature from being "a semantic ontology concept" and §20 forbids unifying on anything but deterministic normalisation or explicit semantic mapping. A registry lookup in the identity term would also break the D5.2 invariant outright. FR-003 must lose this item; §109 Case D is still satisfied without it, because "John sold Acme to Microsoft" is carried by frame + markers + slots: `VERB_ACTIVE_TRANSITIVE`, markers `(NOMARK, NOMARK, to)`, slots `(A0, A1, A2)` → seller/asset/buyer with no binary collapse and no event class. |

**FR-003 replacement text** is given verbatim in D9.2.

### D1.5 The two version fields, and the generated-table discipline

`predicate_normalization_version` versions two artefacts, both **generated** and both with a
**committed digest**, so that adding a synonym row is a visible diff against a golden value rather
than a silent corpus shift (the same discipline R-001 requires of a parser change):

| Artefact | Generated from | Committed golden | Test |
|---|---|---|---|
| `LEMMA_TABLE: Mapping[str, str]` | the regular inflection rules + a pinned irregular-form list, then the enumerated `DERIVATION_SUFFIXES` | `LEMMA_TABLE_DIGEST` (a `digest128` over `canonical_material(sorted(LEMMA_TABLE.items()))`) | `test_lemma_table_matches_its_committed_digest` |
| `ArgumentMarker` inventory | hand-enumerated closed set (D1.1) | part of the same digest | `test_argument_marker_inventory_is_closed` |

`DERIVATION_SUFFIXES` is an explicitly enumerated list of `(suffix, rule)` pairs —
`("or", verbalise)`, `("er", verbalise)`, `("ion", verbalise)`, `("ment", verbalise)`,
`("ation", verbalise)`, `("ing", verbalise)`, `("ee", verbalise)` and their orthographic variants
(`-ator`, `-ation`→`-ate`) — applied in a fixed order. This is what lets `originator` lemmatise to
`originate` (so §109 Case C and SC-002 work) **without** a synonym table: derivation is morphology,
and morphology has no cross-lemma rows.

The enforceable statement, which is the whole of P1 in data form:

> **`lemma_table` contains no row `(surface, lemma)` in which `surface` is not a morphological
> form of `lemma`.** There is no row type in the structure that expresses "these two words mean the
> same relation", so the forbidden mapping cannot be added by a future contributor — only by
> replacing the generator, which changes the committed digest and fails
> `test_lemma_table_matches_its_committed_digest`.

Test: `test_lemma_table_has_no_cross_lemma_row` — for every pair of rows sharing a `lemma`, the
surfaces must differ only by an inflection or an enumerated derivation of that lemma.

### D1.6 Where the 019 `normalized_form` concern goes

R-002 states the defect verbatim:

> - `PredicateHypothesis.normalized_form` exists but is inert: `__post_init__` sets it to
>   `str(self.normalized_form or self.surface_form or "")`, so it is a verbatim copy of the
>   surface. There is no normalisation function in the module and none in `domain/` or
>   `semantic/`.

Confirmed at `predicate_hypothesis.py:152-154`. The concern goes in **two** places, because there
are **two** inert fields claiming to be the normalised predicate, and closing one leaves the other
as a new normaliser:

1. **`PredicateHypothesis.normalized_form`** — the field is **preserved** (FR-021 and §21 both
   require it by name) but becomes a **derived read-only property** over the signature:

   ```python
   @property
   def normalized_form(self) -> str:
       """Derived view of the one normaliser in the codebase. Never an input.

       Before 021 this field was a verbatim copy of ``surface_form`` set in
       ``__post_init__`` (predicate_hypothesis.py:152-154), i.e. an inert second normaliser
       that would have become an identity authority the moment anyone used it. It is now a
       read: ``predicate_signature.rendered_predicate()``, falling back to ``surface_form``
       when no signature is present. A ``normalized_form=`` constructor keyword is REFUSED,
       so a caller cannot smuggle a second normaliser back in through the front door.
       """
       if self.predicate_signature is None:
           return self.surface_form
       return self.predicate_signature.rendered_predicate()
   ```

   FR-021's "MUST preserve `normalized_form`" is satisfied by an observable field. It is **not**
   satisfied by a stored input, and `spec.md:448-451` must be reworded accordingly — flagged in
   D9.3 as outside my stated D9 range but mandatory with this change, because leaving the old
   wording invites a constructor kwarg back.

2. **`RelationSignal.normalized_predicate`** — §14 (`input.md:970`) lists it as a field the signal
   contract "should explicitly support". It is supported as a **derived property** over
   `predicate_signature`, and *not* as a second stored string:

   ```python
   @property
   def normalized_predicate(self) -> str:
       """Derived. ``""`` when no signature — which is the honest answer for an unsupported
       construction (D3.5), and is a materially different answer from a copy of the surface."""
       return "" if self.predicate_signature is None else self.predicate_signature.rendered_predicate()
   ```

Tests: `test_normalized_predicate_is_a_derived_view_of_the_signature`,
`test_predicate_hypothesis_normalized_form_no_longer_copies_the_surface`,
`test_predicate_hypothesis_refuses_a_constructor_supplied_normalized_form`,
`test_normalized_predicate_is_empty_when_there_is_no_signature`.

**The principled statement.** There is exactly **one** normaliser in the platform, it lives in
`apps/shared/domain/predicate_signature.py`, it is versioned, and neither the signal nor the
hypothesis may hold a normalised predicate of its own. The 019 concern is closed by *subordination*,
not by writing a normaliser into `predicate_hypothesis.py`.

### D1.7 A brief-internal inconsistency found while reconciling, and how it is read

`input.md` §109 Case A, lines 4451-4454, verbatim:

```text
relation signal:
    predicate_surface = "works for"
    predicate_signature = works_for(...)
    relation_ref = works_for
```

`works_for` is a registry operator (it is in the list at §65, and §66 is titled "RELATION SIGNAL →
KNOWN OPERATOR"). §18 says verbatim: *"It is NOT a RelationRef. / It is NOT a semantic ontology
concept."* So the third line is the mapping and the second line, read literally, is the same
operator appearing as the signature — a relation vocabulary leaking into the identity carrier, in
the brief's own golden example, in the exact place this feature exists to prevent.

**Reading taken**: `predicate_signature = work(A0:,A1:at)` (a structural projection) and
`relation_ref = works_for` (a mapping). `relation_ref` is the mapping layer's output (D7), never an
input to the signature. The `works_for(...)` text in §109 is treated as illustrative of *shape*
(lemma + parenthesised argument list), which is what `rendered_predicate()` produces.

**A second consequence of the same reading, and it matters**: §29 says `John works at Acme.` (marker
`at`) while §109 Case A says `predicate_surface = "works for"` (marker `for`). Under
`ArgumentMarker` these are different markers, hence different signatures, hence two logical ids. I
am **not** permitted to collapse them — deciding that `at` and `for` mark the same argument in
`work` is a lexical-semantic claim, and §20 reserves it to explicit mapping. So `works at` /
`works for` are **two** signatures and may be **proposed** to map to one operator (D7). Named test:
`test_works_at_and_works_for_are_distinct_signatures`. See D6.3 hole **H6**.

---

## D2 — `RoleBinding` v2

### D2.1 The dataclass, verbatim

```python
@dataclass(frozen=True, slots=True)
class RoleBinding:
    """One participant's placement in one canonical reading.

    Exactly two of these five fields may reach identity, and only one of those may be free
    text — and that one is evidence. ``canonical_argument_slot`` is the sole role datum the
    logical identity is allowed to read (D4.2).
    """

    surface_role: str
    """FREE TEXT. EVIDENCE ONLY. The words the observation used: "buyer", "purchaser",
    "the CEO of". Never enters ``logical_candidate_id``. This is the field a later regime
    reads to decide the same words a different way (``relation_candidate.py:604-611`` states
    why the surface must survive), and the field a reviewer reads to find out what an ``A2``
    slot was called. Retained verbatim as a durable ``Text`` column; a mapping that is
    re-evaluated later needs the words to still be there."""

    role_hypothesis: str
    """FREE TEXT. A producer's guess at the role, retained verbatim and never consulted by
    the normaliser or the ordering rule. Two producers guessing "seller" and "vendor" for
    the same A1 produce ONE logical candidate, which is §43's "ONE logical candidate /
    MANY signals" made mechanical. A guess is a guess: a ``role_hypothesis`` is not a
    ``surface_role``, and neither is a slot."""

    canonical_argument_slot: ArgumentSlot
    """STRUCTURAL, VERSIONED, and the only role datum admitted to identity. Assigned by
    ``normalize_voice`` (D3) from the parse, never from a vocabulary. See D2.2."""

    normalization_version: str
    """The ``voice_normalization_version`` that assigned ``canonical_argument_slot``. Not
    decoration: it is the per-binding half of the versioning discipline in D2.3, and it is
    what lets a store detect a mixed-version participant set instead of assembling one."""

    evidence: tuple[str, ...]
    """EVIDENCE ONLY. Sorted, canonicalised on construction like every other reference
    collection, and revision material. Never identity."""
```

### D2.2 Why `A0`/`A1`/… is a canonical *structural* representation and NOT an ontology of reality

This must be defensible against INV-001 (`mention.kind == entity.type` is never an identity
theorem), INV-002 (the vocabulary is an interpretation instrument, never "the definition of what
exists"), and Domain Invariant 3 (`Assertion != truth`). Six properties, each with a test:

| # | Property | Consequence | Test |
|---|---|---|---|
| 1 | **It is scoped to one signature.** `A0` means "the first argument of the construction whose `construction_frame` is F", and has no meaning outside that signature. There is no global registry, no namespace, no `core:` prefix, no hierarchy, no lookup table. | A slot cannot be resolved, blocked, expanded, or queried. There is nothing to resolve *to*. | `test_argument_slot_space_is_unbounded_and_unregistered` |
| 2 | **It is derived from position in a parse, not from a judgement about the referent.** In `Company acquired Asset`, `A0 = Company` because Company occupies the `nsubj` position — not because Company is judged to be an agent, an organisation, or a controller. | A slot states where something sat, which is observable. It states nothing about what the something is, which would be a claim. | `test_slot_assignment_reads_dependency_position_not_type` |
| 3 | **It is a total order over positions of one construction, and the space is unbounded in `k`.** The admissible values are `{A_k : 0 ≤ k < arity}`. Nothing enumerates them, so there is no "permitted values" list to mistake for an ontology. | A type pack has `core:Organization`, `core:Person` — a *finite* named set of claims. A slot set has a *formula*. | `test_argument_slot_space_is_unbounded_and_unregistered` |
| 4 | **The same mention may occupy different slots in different signatures.** In `Company acquired Asset` the mention for Company is `A0`; in `Asset was acquired by Company` it is also `A0` (voice normalisation); but in `Asset acquired Company` it is `A1`. | Slots are per-reading, not per-entity. An entity has no slot. This is the exact line INV-001 draws, and it is why `ArgumentSlot` is not on `Mention` and not on `TypeHypothesis`. | `test_same_mention_may_occupy_different_slots_in_different_signatures` |
| 5 | **A slot carries no type, no confidence, no truth and no provenance.** It is an `int` and a token. | Nothing can be inferred from a slot. A candidate in `A1` is not thereby a "thing of class 1". | `test_argument_slot_carries_no_type_confidence_or_truth_claim` |
| 6 | **Occupants of one slot need not share a type.** `John sold Acme to Microsoft` puts a person, an organisation and an organisation in three slots; `Acme and Zurich co-host the summit` may put two different organisations in one slot and a temporal value in another. | Slots and types are orthogonal, so A5's type work can proceed with no effect on relational identity (reinforced by D4.3's fingerprint exclusion). | `test_slot_occupants_need_not_share_a_type` |

The one-line answer to a reviewer's "isn't `A0` an ontology?": **`A0` is a position in a sentence's
argument structure. It is derived by reading a parse. It asserts nothing about the world, and no
vocabulary anywhere assigns meaning to it.**

### D2.3 How the slot assignment stays versioned when the convention changes

The convention is identified by `voice_normalization_version`, which is the version of
`normalize_voice` — the function that assigns slots (D3). The rule, verbatim:

> A change to the slot-assignment convention (for example: "for a ditransitive, `A1` is the theme
> and `A2` is the goal" becomes "…`A1` is the goal and `A2` is the theme") MUST
>
> 1. bump `voice_normalization_version`;
> 2. be recorded in the signature's own durable columns, so a stored signature is
>    self-describing and re-derivable from the record alone (FR-060: a digest may identify
>    data, it may not be the only copy required for reconstruction — R-002 point 2);
> 3. change `ArgumentSlot.__lt__`'s contract only if the *token* form changes, which requires a
>    major `IDENTITY_SCHEMA_VERSION` bump; and
> 4. produce a **different `logical_candidate_id`** for readings re-derived under the new
>    convention.

Point 4 is not a cost, it is the point. A reading whose slots were assigned under an old convention
is a *different structural claim* from one assigned under a new convention, and the platform must
not silently re-key history. The two coexist as two candidates, which is visible, rather than one
candidate whose id moved, which is not.

The corollary that makes the version load-bearing rather than decorative:

> A signature or binding whose `voice_normalization_version` is `""` is a **contract error**
> (`unversioned_signature` / `unversioned_role_binding`). It is **never** defaulted to "the
> current version" and **never** migrated with a guess.

Why no back-compatible default: a default is a guess, and a guessed version assigns an id whose
record cannot justify it. The constitution's "Additional Constraints" require a **quarantine** for
exactly this class of row ("rejected candidates are never auto-deleted (replay/re-evaluation
supported)"), so the outcome is: the row is quarantined, reported, and replayable. Tests:
`test_signature_without_a_normalization_version_is_a_contract_error`,
`test_role_binding_version_must_match_its_signature`,
`test_changing_the_slot_convention_bumps_the_version_and_changes_the_logical_id`.

### D2.4 The version-agreement rule

```python
def verify_slot_version_agreement(
    signature: PredicateSignature, bindings: Sequence[RoleBinding]
) -> None:
    """Refuse a participant set assembled across two normalisation versions.

    A binding assigned by an older version and one assigned by the newer one cannot be
    placed in a single canonical ordering, because "A1" does not mean the same position
    under both. Assembling them anyway would produce a canonical order that neither version
    would produce, and therefore an id neither version can re-derive. Refusing is the only
    answer that keeps the id derivable from the record.
    """
```

Test: `test_mixed_normalization_versions_are_refused`.

### D2.5 The agreement rules that keep slots, frame and arity from drifting

```python
def verify_signature_shape(
    signature: PredicateSignature,
    bindings: Sequence[RoleBinding],
    commutative_slots: frozenset[ArgumentSlot],
) -> None:
    """Four total checks. Each is one line and each has a named test.

    1. ``len(signature.canonical_argument_slots) == len(signature.argument_markers)``
       — the markers are parallel to the slots; a length mismatch is a truncated
       construction, not a relation.
    2. ``sorted(distinct slots of bindings) == list(signature.canonical_argument_slots)``
       and the slots are contiguous from ``A0`` — the signature carries the slot
       SKELETON, the bindings carry the occupants, and the two may not disagree.
    3. ``signature.construction_frame.is_observed_only is False``
       — an observed passive frame on a signature would fork active from passive, which
       is the whole defect this subsystem exists to remove.
    4. commutativity agrees with the declared shape: ``commutative_slots`` may only contain
       slots that are OCCUPIED; a declared commutative slot with one occupant is legal
       (a symmetric relation observed with one side elided) and a declared commutative
       slot with zero occupants is a contract error (``empty_commutative_slot``); and
       ``commutative_slots == set(occupied slots)`` is exactly the condition under which
       ``RelationArityMode.UNDIRECTED`` is admissible, so ``arity_mode`` is *derivable*
       and never independently asserted.
    """
```

Tests: `test_markers_must_be_parallel_to_slots`, `test_signature_slots_must_equal_the_bound_slots`,
`test_signature_may_not_carry_an_observed_passive_frame`,
`test_commutative_slots_must_be_occupied`, `test_arity_mode_is_derivable_from_commutative_slots`.

---

## D3 — `normalize_voice()` — the specified algorithm

### D3.0 A correction to the job brief, made because D3 asks for verification

The brief's construction list is at **`input.md` §29 `SYNTACTIC PRODUCER`** (lines 1677–1741), not
§22. §22 is `RELATION CANDIDATE = DURABLE HYPOTHESIS` (line 1377) and contains no construction
list. §29's eight, verbatim heading-for-heading: `### Active`, `### Passive`, `### Copular`,
`### Nominal`, `### Appositional`, `### Possessive`, `### Prepositional`, `### Relative clause`.
The table below supports exactly those eight, plus the two sub-frames D3.4 justifies, plus one
construction deliberately excluded (D3.5). §29's "Support at least" permits more; §20 forbids more
*unification*, so the extras are all **narrowing or structural**, never merging.

### D3.1 Signature, inputs and outputs

```python
class SyntacticConstruction(StrEnum):
    """The parse-level construction, as detected. This is the INPUT vocabulary and it is
    a superset of :class:`ConstructionFrame`; the mapping from one to the other is
    ``CANONICAL_FRAME_BY_CONSTRUCTION`` (D3.4), and the only entry that differs is the
    passive demotion."""
    ACTIVE_CLAUSE, PASSIVE_WITH_AGENT, PASSIVE_NO_AGENT, COPULAR, COPULAR_WITH_NOUN_COMPLEMENT,
    BARE_NOMINAL, GENITIVE_NP, APPOSITIVE_NP, HEADLESS_PP, RELATIVE_CLAUSE, OTHER


@dataclass(frozen=True, slots=True)
class ArgumentObservation:
    """One argument as the PARSE sees it. Note what is absent: no role, no type, no
    semantic judgement. ``position_label`` is a dependency label, not a role — the whole
    point of D2.2 property 2."""
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
    relation: str            # UD-style: "nsubj", "nsubj:pass", "nmod:by", "obj", "case:gen", "np:appos", "reld:cl", "pobj"


@dataclass(frozen=True, slots=True)
class DependencyStructure:
    edges: tuple[DependencyEdge, ...]             # in document order; the ORDER is load-bearing (V2) and pinned
    root: str                                    # the label of the head of the clause/NP that carries the reading


@dataclass(frozen=True, slots=True)
class PredicateHead:
    observed_form: str                           # "acquired", "acquire", "acquires"
    language: str                                # BCP-47 primary subtag; only "en" is shipped in 021


@dataclass(frozen=True, slots=True)
class CanonicalArgumentAssignment:
    """The output. Note what is NOT here: no commutativity, no polarity, no direction, no
    mention ref, no surface. See D3.6."""
    construction_frame: ConstructionFrame         # CANONICAL — never an observed-only frame
    canonical_argument_slots: tuple[ArgumentSlot, ...]
    argument_markers: tuple[ArgumentMarker, ...] # parallel to slots, strict=True
    normalization_trace: tuple[str, ...]         # ordered step ids; corpus-visible, not identity


def normalize_voice(
    predicate: PredicateHead,
    syntactic_structure: SyntacticStructure,
    dependency_structure: DependencyStructure,
) -> CanonicalArgumentAssignment:
    """The ONLY function in the platform that assigns canonical argument slots.
    See D3.3 (ordered steps), D3.4 (the construction table), D3.5 (unsupported)."""
```

**Two independent implementations agree** because there is no judgement in the function: it
consumes a *declared* construction and a *declared* argument list, applies six ordered steps, and
the only inputs it does not consume are things that would require a judgement. The parse is
produced elsewhere; the *frame detection* is a table lookup over the declared construction; the
lemma comes from a generated table. Nothing in the body of the function can differ between
implementations.

### D3.2 Scope declaration — the one and only unification

> **P-CANON (Principle of Canonical Voice).** `normalize_voice` performs **voice normalisation
> only**: a passive clause with an overt `by`-agent and its active counterpart produce the same
> canonical argument assignment, and nothing else is unified.

Every other §29 construction receives **its own** `construction_frame` value in the signature.
"John, who founded Acme" does not collapse with "John founded Acme". "John is the CEO of Acme"
does not collapse with "John, CEO of Acme". "John works at Acme" does not collapse with "John works
for Acme" (D1.7).

The justification is directional, and it is the whole design: **under-unification is visible as two
candidates; over-unification is invisible as a wrong merge.** §43 permits one candidate from many
signals "only when they describe the same relational configuration" — so an unproven equivalence
produces a merge that cannot be undone and is not visible in the data. §20 names the only lawful
unifier: "deterministic normalization **or explicit semantic mapping**". Voice demotion is
deterministic normalisation; a relative clause's equivalence to its matrix clause, a nominal's
equivalence to its clause, and a copula's equivalence to a bare nominal are all *claims about
equivalence*, and claims about equivalence are what the **mapping layer** (D7) is for, where they
are dated, attributed, evidence-bearing, revisable and able to be wrong in public.

Test enforcing the scope: `test_normalize_voice_does_not_unify_anything_but_voice` — feed one
input per §29 construction and assert the output frames are pairwise distinct except for the single
`PASSIVE_WITH_AGENT` / `ACTIVE_CLAUSE` pair.

### D3.3 The ordered steps — exact, in order

| Step | Id | Action | Failure |
|---|---|---|---|
| V0 | `V0.validate` | `language` must be a shipped language (`en` in 021). `syntactic_structure.arguments` must be non-empty. `dependency_structure.root` must label an argument. | `UNSUPPORTED_LANGUAGE` / `MALFORMED_STRUCTURE` |
| V1 | `V1.frame` | Look up `CANONICAL_FRAME_BY_CONSTRUCTION[syntactic_structure.construction]` (D3.4). For `PASSIVE_WITH_AGENT` the result is `VERB_ACTIVE_TRANSITIVE` — **the demotion happens here, at the frame, not later.** | `UNSUPPORTED_CONSTRUCTION` (D3.5) |
| V2 | `V2.assign_slots` | Take the slot sources from the table row, **in the order the row states them**, drop any source marked *consumed* (V1's demoted `nsubj:pass`), and number the survivors `A0, A1, …` contiguously. Multiplicity is preserved: two occupants of one source produce two slots with the same index, and the table row must say the slot is *coordinated*. | `SLOT_GAP` if numbering is not contiguous |
| V3 | `V3.lemmatise` | `predicate_lemma = LEMMA_TABLE.get(observed_form.casefold())`. Applied to the **predicate head only** — never to a participant, never to a function word, never to a second argument. An AUX (`be`, `get`, `become`) is **not** the predicate head when the clause has a participle; the participle is. | `UNSUPPORTED_LEMMA` |
| V4 | `V4.markers` | For each slot, in slot order, `argument_markers[i] = ArgumentMarker(head_function_word)` if the table row says that position is function-word-marked, else `NOMARK`. Any function word not in the closed inventory is a failure, **not** `NOMARK`. | `UNSUPPORTED_MARKER` |
| V5 | `V5.trace` | `normalization_trace` = the ordered step ids actually executed, e.g. `("V0.validate","V1.frame","V2.assign_slots","V3.lemmatise","V4.markers")`. Persisted, corpus-visible, **never identity**. | — |
| V6 | `V6.arity` | If fewer than 2 slots are occupied → `NO_CONFIGURATION` (D3.7). | `NO_CONFIGURATION` |

Two exact tie-breaks, because "two independent implementations must agree" means the ambiguous
cases are specified, not left to taste:

> **TB1 (copula vs active, for `become`).** V1's table is consulted in row order and the **first
> match wins**. `COPULAR` precedes `ACTIVE_CLAUSE`, so `John became a founder of Acme` is
> `COPULAR_PREDICATIVE_NOUN` and `John became famous` is `VERB_ACTIVE_INTRANSITIVE`. The
> disambiguating syntactic test is presence of an NP/ADJ/PP complement, and that test is the table's
> *condition*, not an afterthought: a row that cannot be tested syntactically may not be in the
> table.
>
> **TB2 (order of non-slot arguments).** V2 takes arguments in **`dependency_structure.edges`
> order**, which is pinned document order, and NOT in the order of
> `syntactic_structure.arguments`. Where a construction's argument list is ambiguous under document
> order — a ditransitive with two `nmod:` arguments, e.g. `John sold Acme to Microsoft in 2020` —
> the tie-break is **`ArgumentMarker` ascending, then `position_label` ascending, byte-wise.**
> `in` < `to`, so `in 2020` sorts before `to Microsoft` and the temporal complement is assigned
> before the recipient. The temporal argument is then **dropped** (D1.3: temporality is not
> predicate structure), and the trace records `"V2.drop_temporal"` so the drop is auditable rather
> than invisible.

The drop of a temporal complement is the one place V2 discards an argument, and it is recorded in
the trace because §109 Case D's `time = 2020` must remain recoverable — it is carried by the
candidate's `TemporalHypothesis`, and the trace says the signature layer saw it and did not put it
in the predicate.

### D3.4 The construction table, verbatim

`CANONICAL_FRAME_BY_CONSTRUCTION`, consulted in row order (TB1), versioned by
`voice_normalization_version`:

| Row | `SyntacticConstruction` | Syntactic condition | Canonical `construction_frame` | Slot sources, in order | Markers |
|---|---|---|---|---|---|
| 1 | `PASSIVE_WITH_AGENT` | head is a member of the closed AUX set `{be, get, become}`; a `nsubj:pass` dependent exists; a `nmod:by` dependent exists | **`VERB_ACTIVE_TRANSITIVE`** (demoted) | A0 = `nmod:by` head; A1… = the passive participle's remaining arguments in edges order. The `nsubj:pass` head is **consumed** and becomes A1 if it is the only remaining argument, else it is **re-emitted** as the first remaining argument. | A0 = `NOMARK` (canonical-active subject). Remaining slots take their own markers. The observed `by` is recorded in the trace and in evidence, **not** in the signature. |
| 2 | `COPULAR` | head is in the closed COPULA set `{be, remain, seem, become}`; no `nsubj:pass`; a `nsubj` and a predicate complement exist; the complement is a **bare NP** | `COPULA_PREDICATIVE` | A0 = `nsubj` head; A1 = the complement's own `nmod:of` head if the complement is an NP with an `of`-PP, else the complement head | A0 = `NOMARK`; A1 = `of` when the `of`-PP was followed, else `NOMARK` |
| 3 | `COPULAR_WITH_NOUN_COMPLEMENT` | as row 2 but the complement is a **derived nominal + adjacent `of`-PP** ("a founder of Acme") | `COPULA_PREDICATIVE_NOUN` | as row 2 | as row 2 |
| 4 | `ACTIVE_CLAUSE` | head is a non-AUX verb; a `nsubj` exists; ≥1 further argument exists | `VERB_ACTIVE_TRANSITIVE` | A0 = `nsubj`; A1… = remaining arguments in edges order, temporal complements dropped (TB2) | `NOMARK` for A0; each further slot takes its own `function_word` as an `ArgumentMarker` |
| 5 | `ACTIVE_CLAUSE` with no further argument | as row 4 with no further argument | `VERB_ACTIVE_INTRANSITIVE` | A0 only | `NOMARK` — **always yields `NO_CONFIGURATION` at V6** (§13 requires 2..N participants; a one-argument clause states a property, not a relational configuration) |
| 6 | `BARE_NOMINAL` | no finite head; the governor is an NP whose head noun has an `nmod:of` dependent | `NOMINAL_OWNER_OF` | A0 = the NP head; A1 = the `nmod:of` head | A0 = `NOMARK`; A1 = `of` |
| 7 | `GENITIVE_NP` | an NP with a `case:gen` dependent **and** a head NP on the possessed side ("Acme's founder John Smith") | `NOMINAL_POSSESSIVE` | **A0 = the head NP that the genitive modifies** (which may be the surface-left or surface-right NP); A1 = the genitive head. This reversal is the point: it normalises argument structure, not word order. | A0 = `NOMARK`; A1 = `NOMARK` (a genitive marker is structural, and the *observed* `'s` is evidence) |
| 8 | `APPOSITIVE_NP` | a comma-delimited `np:appos` dependent of a preceding NP, whose head noun has an `nmod:of` dependent | `APPOSITIVE_ROLE` | A0 = the matrix NP head; A1 = the `nmod:of` head | A0 = `NOMARK`; A1 = `of` |
| 9 | `HEADLESS_PP` | a PP with no `nsubj`, whose governor is a document-structure producer slot | `PREP_PHRASE_HEAD` | A0 = the `pobj`; A1 = the subject the producing channel declares for the governing slot | A0 = the `function_word`; A1 = `NOMARK` |
| 10 | `RELATIVE_CLAUSE` | a `reld:cl` dependent of an NP | `RELATIVE_CLAUSE` | the clause's own arguments, in rows 1/4 order, with the matrix NP **not** an argument | the clause's own markers |
| — | everything else | — | **`UNSUPPORTED_CONSTRUCTION`** | — | — |

Two rows are **added** beyond §29's eight, and each is added for a stated necessity, not for
convenience:

- **Row 3 `COPULAR_WITH_NOUN_COMPLEMENT`** is required for **row 2 to be total**. "John is the CEO
  of Acme" (row 2) and "John is a founder of Acme" (row 3) are different syntaxes, and row 2 as
  written would reject the second as unsupported. It is a *narrowing* change — it turns an
  `UNSUPPORTED_CONSTRUCTION` into a supported frame — and it does **not** merge rows 2 and 3 with
  each other (D3.2).
- **Row 10's matrix NP** is excluded from the slots because a relative clause's matrix NP is not an
  argument of the clause. That is why "John, who founded Acme" does not collapse with "John founded
  Acme": collapsing them requires the inference "the matrix NP is the relative clause's subject",
  which is true in the common case and false in the reduced-relative and adjunct cases, and a rule
  that is usually right is a guess (D3.2).

The closed AUX set and closed COPULA set are **grammar inventories**, not semantic vocabularies, and
their membership is versioned inside `voice_normalization_version`. `become` in both sets is
resolved by TB1, not by preference.

### D3.5 Unsupported constructions: named, counted, never guessed

> `UNSUPPORTED_CONSTRUCTION` produces **no** `PredicateSignature`. It is **never** resolved by a
> fallback frame, a nearest-match frame, a default frame, a retry, a lexical-identity shortcut, or a
> syntactic guess. The reason code is persisted on the signal so the corpus can count occurrences by
> construction, so the gap is a *number* rather than a silence.

This is §30's rule applied at the right altitude — verbatim, `input.md:1764-1778`: *"For
deterministic baseline, produce useful relation signals even when parser output is unavailable. /
A missing parser capability must mean: `no syntactic signals` — not: `batch failure` — unless the
contract explicitly says the parser is mandatory."*

Downstream, and stated precisely because it is where a defect would re-enter:

- The signal is legal with an explicit observational basis and `predicate_signature=None` (§16,
  FR-013, FR-014), because FR-014's basis vocabulary includes "predicate text" — the words were
  seen; the structure was not.
- The signal **cannot** be grouped with a signal that has a signature. FR-027: "Distinct predicates
  over the same endpoints MUST remain distinct hypotheses. Equal endpoints MUST NOT merge them." A
  reading with no signature and a reading with a signature are not known to be the same
  configuration, so they are separate candidates.
- The candidate survives with `predicate_state=UNKNOWN` (FR-023), the surface retained, and
  `logical_candidate_id` **not minted** (D6.3 hole H3).

Tests: `test_unsupported_construction_yields_no_signature`,
`test_unsupported_construction_is_never_guessed_into_a_frame`,
`test_unsignatured_and_signatured_readings_do_not_merge`.

### D3.6 What `normalize_voice` deliberately does NOT return, and why

| Not returned | Why |
|---|---|
| `commutative_slots` | No grammar-derived construction is symmetric. Symmetry is a property of the *relation*, declared by a semantic contract, and §53 says verbatim: *"Do not infer symmetry merely because the extractor did not know direction."* Returning it from a syntactic function would be exactly that inference. It comes from the candidate's declared marker (D4.5). |
| `polarity` | Assertion structure, not predicate structure (D1.2). |
| `direction` | Derivable from slots + commutativity; an independent return value is a fork (D2.5 check 4). |
| any mention ref or surface | The function is about the *predicate*; participants arrive separately and are bound by the assembler. |
| `observed_construction_frame` | It is the *observed* frame and belongs to the signal as evidence. Carrying it in the signature's identity projection is precisely what keeps active and passive apart. |

Test: `test_normalize_voice_output_carries_no_participant_no_surface_and_no_symmetry`.

### D3.7 `NO_CONFIGURATION` — the honest answer for a one-argument reading

Separate from `UNSUPPORTED_CONSTRUCTION`, because the parse was fine and the outcome is a
*decision*, not a gap. `"Acme's ownership"` parses as row 7 with no head NP on the possessed side,
so one slot is occupied, so there is no relational configuration. `arity >= 2` is required
(`data-model.md` §1's own constraint, FR-008's "2..N participants without a fake binary
decomposition", §13's "without inventing a fake binary decomposition").

> A reading occupying fewer than 2 canonical slots yields `NO_CONFIGURATION`. It is **not** padded
> to arity 2 with a placeholder, and **not** given a null participant. "Acme's ownership" is a
> property of Acme, not a relation between two mentions.

Tests: `test_intransitive_reading_yields_no_configuration`,
`test_no_configuration_is_distinct_from_unsupported_construction`.

### D3.8 The worked derivation required by D3

**Active — `Company acquired Asset.`**

| Step | Working | Result |
|---|---|---|
| V0 | `language=en`, 2 arguments, root labels the clause | pass |
| V1 | construction `ACTIVE_CLAUSE`, non-AUX head, `nsubj` + 1 further argument | row 4 → `VERB_ACTIVE_TRANSITIVE` |
| V2 | A0 = `nsubj` head = Company; A1 = the remaining argument = Asset. No temporal complement to drop. | slots `(A0, A1)` |
| V3 | `acquired` → `acquire` via the regular `-ed` inflection rule | `predicate_lemma="acquire"` |
| V4 | A0 = `NOMARK` (subject, structurally unmarked); A1 = `NOMARK` (no function word) | markers `(NOMARK, NOMARK)` |

**Passive — `Asset was acquired by Company.`**

| Step | Working | Result |
|---|---|---|
| V0 | `language=en`, root labels the clause | pass |
| V1 | construction `PASSIVE_WITH_AGENT`; row 1 | → `VERB_ACTIVE_TRANSITIVE` **(demoted at the frame)** |
| V2 | A0 = `nmod:by` head = Company. The `nsubj:pass` head (Asset) is the only remaining argument, so it is re-emitted as A1. | slots `(A0, A1)` |
| V3 | head is the participle `acquired`, **not** the AUX `was` → `acquire` | `predicate_lemma="acquire"` |
| V4 | A0 = `NOMARK` — the canonical-active subject is structurally unmarked. The **observed** `by` goes to the trace and to evidence, not to the signature. | markers `(NOMARK, NOMARK)` |

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

`rendered_predicate()` = `"acquire(A0:,A1:)"`. This is §18's `acquire(...)` in shape and content.

---

## D4 — `canonical_participant_ordering()` — the specified algorithm

### D4.1 Signature

```python
def canonical_participant_ordering(
    signature: PredicateSignature,
    commutative_slots: frozenset[ArgumentSlot],
    participants: Sequence[RoleBinding],
) -> tuple[CanonicalParticipant, ...]:
    """The ONLY ordering of participants admitted to logical material. D4.2 the order,
    D4.3 the fingerprint, D4.4 the tie-break, D4.5 commutativity."""


@dataclass(frozen=True, slots=True)
class CanonicalParticipant:
    slot: ArgumentSlot
    participant_fingerprint: str      # 32 lowercase hex
    commutable: bool
```

**Binary** (`arity == 2`): order by `canonical_argument_slot` alone. There is nothing else to order
by, and no tie is possible unless both occupants share one slot, which is a contract error (D4.4).
**n-ary** (`arity >= 3`): order by `(canonical_argument_slot.index, participant_fingerprint)`.

### D4.2 The ordering steps — exact

| Step | Action |
|---|---|
| O1 | `verify_signature_shape(signature, participants, commutative_slots)` (D2.5). A refusal here aborts ordering; nothing downstream sees a partially ordered set. |
| O2 | Group bindings by `canonical_argument_slot`. Preserve multiplicity: `list`, never `set` (`logical_material` at `relation_identity.py:182` uses `sorted({…})`, which **deduplicates** — see D4.7). |
| O3 | For each occupied slot, sort its occupants ascending by `participant_fingerprint`, comparing the 32 lowercase hex **byte-wise** (`str` comparison). |
| O4 | Order the slots ascending by `ArgumentSlot.index` — the wrapped integer, **never the token text**. `A10` follows `A2`; a `str` sort places `"A10"` before `"A2"` because `'1' < '2'`, which is deterministic and semantically wrong. |
| O5 | Emit `(slot, participant_fingerprint, slot in commutative_slots)` per occupant, in slot order, occupants in fingerprint order. |

**Why a slot sort at all for a directed binary relation.** Because the slots *are* the direction.
`Company acquired Asset` → `(A0:Company, A1:Asset)`; `Asset acquired Company` → `(A0:Asset,
A1:Company)`. Two different material values, therefore two different logical ids — which is §44
("Different relations must not merge"), §52 ("Never canonicalize `min(source,target)` /
`max(source,target)` for directed edges") and SC-007 all in one mechanism. The current
`logical_material` `DIRECTED` branch (`relation_identity.py:184-195`) achieves this with
order-preserving `participants`; the mechanism is preserved and made explicit by sorting on the slot
rather than on arrival order.

### D4.3 `stable_participant_fingerprint` — exactly what it digests

```python
def stable_participant_fingerprint(mention: ResolvedMention) -> str:
    """32 lowercase hex over the mention's own identity material, and nothing else.

    MUST digest:  mention_kind, normalized_surface, capture_ref, segment_ref, start, end
    MUST NOT digest, each for the stated reason:
      * the mention_id text  — it is a MINTING artefact. Digesting it would make the logical
        material depend on the minter's id format, and a re-mint of the same mention would
        silently fork every candidate that mentions it. The material says "a participant",
        not "a string starting MN-".
      * producer_ref / extractor / extractor_version — FR-001, FR-006. Would extend producer
        scope from the observation level to the hypothesis level and break US5 and SC-005.
      * the sentence, span, trigger, supporting spans — FR-001. Two realisations of one
        configuration in one document have two spans and one id.
      * evidence_refs, observation_refs, signal_refs — FR-001, §43.
      * confidence — FR-001, and relation_identity.py:289-292 verbatim: "a re-scoring pass
        must not mint a new relation, or every ranking change forks the graph".
      * type_ref, kind, TypeHypothesis, type state, vocabulary_version — INV-001, and to keep
        A5's type work structurally incapable of moving a relational identity. This exclusion
        is load-bearing, not tidiness.
      * argument_shape — same reason: shape is a referent fact, and a shape reclassification
        must not re-key a relation.
      * surface_role, role_hypothesis, normalization_version — P2 / D2.1. Two producers
        guessing "seller" and "vendor" for the same slot are one logical candidate (§43).
      * the relation this mention participates in, the segment's predicate, the document's
        reading — the fingerprint is a fact about a mention, so that the same mention in two
        different relations gets the same fingerprint and is ordered by slot, not by relation.
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

`normalize_surface_for_fingerprint` is N1+N2 only — NFKC, casefold, internal whitespace collapsed,
edge punctuation stripped — and **never** the predicate normalisation of D3 V3, because a
participant's surface is not a predicate.

Two tests carry this whole subsection:
`test_participant_fingerprint_is_invariant_across_realisations` (build the mention pair once, build
both observations, assert byte-equal fingerprints — this is the realisation-independence claim, and
it is the test that would fail if any sentence-level datum leaked in) and
`test_participant_fingerprint_excludes_producer_span_type_and_confidence` (mutate each excluded
datum in turn; the fingerprint must not move).

### D4.4 Multiple participants in one slot — the deterministic tie-break

> When a slot holds more than one participant, the occupants are ordered ascending by
> `participant_fingerprint`, byte-wise over the 32 lowercase hex. That is the **whole** tie-break
> and it is total, because the fingerprints are distinct by construction (two distinct mentions
> produce two distinct fingerprints; a repeat fingerprint is `duplicate_participant_fingerprint`).
>
> If the slot is **not** in `commutative_slots`, two occupants is a contract error
> (`slot_not_commutative_multiple_members`) and **no order is emitted**. Ordering it anyway would
> be inventing a reading the structure does not license. Coordination ("John and Mary acquired
> Acme") is **not** in §29's list, so it is `UNSUPPORTED_CONSTRUCTION` until the table gains a
> coordinated frame *and* a commutativity declaration for it. Named stop condition, not a gap to
> be papered over with a sort.

Tests: `test_slot_occupants_are_ordered_by_fingerprint`,
`test_non_commutative_slot_with_two_members_is_a_contract_error`,
`test_coordination_is_unsupported_until_a_frame_and_a_symmetry_marker_exist`.

### D4.5 When two participants are commutable, and how it is represented

> **Two participants are commutable if and only if they occupy the same `canonical_argument_slot`
> AND that slot is declared in `commutative_slots`. Nothing else makes two participants
> commutable.** Participants in *different* slots are never commutable, under any declaration.

The second sentence is §52 and SC-014 together: a `DIRECTED` edge's endpoints are never reordered.
`A0`/`A1` is the direction, and no declaration may swap it.

Representation:

| Aspect | Specification |
|---|---|
| Where the marker lives | `RelationCandidate.commutative_slots: frozenset[ArgumentSlot]`, **always explicitly present**, defaulting to `frozenset()`. Never inferred, never absent, never `None`. |
| How it enters material | `"commutative_slots": sorted(slot.token for slot in commutative_slots)` — a sorted list, `[]` in the ordinary case. |
| Who may set it | Only an explicit declared-symmetry contract. `normalize_voice` cannot (D3.6). §53 verbatim: *"projection may use canonical endpoint ordering. But only if the admitted relation contract declares symmetry. Do not infer symmetry merely because the extractor did not know direction."* |
| Relationship to `arity_mode` | **Derivable, never independently asserted** (D2.5 check 4): `arity_mode is UNDIRECTED` iff `commutative_slots == set(occupied slots)`. `verify_signature_shape` refuses a pair that disagrees. |
| Consequence of changing it | A different `canonical_participant_ordering` output, therefore a **different** `logical_candidate_id`. Correct: a symmetric reading and an asymmetric reading of one pair are different claims, and the store shows both. |
| Interaction with a later claim contract | A claim's declared symmetry lives on `RelationClaimMaterial` / `RelationSchema` and **does not re-key an existing candidate**. A symmetric and an asymmetric candidate over one pair both stand; admission picks. This is why the marker must exist on the candidate and not only on the claim. |

**This replaces the current `logical_material` `UNDIRECTED` branch**
(`relation_identity.py:178-183`), which is `{"members": sorted({str(p) for p in participants})}` —
a sort by mention id text, i.e. the "random sort by mention id" the job forbids, plus a `set`, i.e.
a silent deduplication (D4.7).

Tests: `test_undirected_ordering_uses_the_slot_marker_not_a_mention_id_sort`,
`test_symmetry_is_never_inferred_from_missing_direction`,
`test_symmetric_and_asymmetric_readings_get_different_logical_ids`.

### D4.6 Worked example — §109 Case D, `John sold Acme to Microsoft in 2020.`

| Step | Working | Result |
|---|---|---|
| V1 | `ACTIVE_CLAUSE`, ditransitive | `VERB_ACTIVE_TRANSITIVE` |
| V2 | A0 = `nsubj` = John. Remaining: `nmod:to` → Microsoft, `nmod:in` → 2020. TB2 orders by `ArgumentMarker` ascending: `in` < `to`, so 2020 is considered first, is a temporal complement, and is **dropped** with trace `"V2.drop_temporal"`. | slots `(A0, A1, A2)` |
| V3 | `sold` → `sell` | `predicate_lemma="sell"` |
| V4 | A0 = `NOMARK`; A1 = `NOMARK`; A2 = `to` | markers `(NOMARK, NOMARK, to)` |
| V5 | trace records the drop | corpus-visible |
| — | `time = 2020` is carried by `TemporalHypothesis` on the candidate, at year precision, as revision material | SC-003 satisfied, no binary collapse |

`identity_projection()`: `{"argument_markers":["","","to"], "canonical_argument_slots":["A0","A1","A2"], "construction_frame":"verb_active_transitive", "language":"en", "predicate_lemma":"sell", …}` → `rendered_predicate()` =
`"sell(A0:,A1:,A2:to)"`. A0/A1/A2 are `seller`/`asset`/`buyer` **structurally**; the names live in
`RoleBinding.surface_role` as evidence, and the mapping layer may later propose operators for them
(D7).

### D4.7 Two behaviour changes this ordering makes to the existing `logical_material`, flagged for the claim-layer owner

`apps/shared/domain/relation_identity.py` is **not** in this job's ownership, so these are recorded
as required follow-on edits, not applied:

| # | Today | After | Why the change is required |
|---|---|---|---|
| 1 | `UNDIRECTED` sorts `sorted({str(p) for p in participants})` — by **mention-id text** | slot + fingerprint ordering, gated on `commutative_slots` | §52: "Never canonicalize `min(source,target)`/`max(source,target)`" for directed; and a mention-id sort makes identity depend on the id minter's format (D4.3). |
| 2 | `sorted({…})` **deduplicates** | multiset, multiplicity preserved | "Acme is co-owned by John and Mary" is a different configuration from "Acme is co-owned by John". A `set` deletes a participant. |
| 3 | `DIRECTED` takes `participants` in **arrival order** | slot order | Arrival order is caller order, and determinism currently holds only because `assembly.py` sorts by hand at one call site. Slot order removes the reliance on a call site. |
| 4 | `NARY` uses `sorted([role, member])` with `role` a **free-text** `RoleBindingLike.role` | the slot is a structural `ArgumentSlot` | This is review finding **E2** at the claim layer: `purchaser` vs `buyer` forks the id. `RelationRoleBinding.role` (`relation_claim.py:102`) is free text today. |

Item 4 also means `RelationRoleBinding` needs the D2 field split at the claim layer too. Recorded
here so the identity subsystem is specified as **one** subsystem, as the job requires, even though
only the candidate half is mine to change.

---

## D5 — The corrected logical identity rule

### D5.1 The rule, verbatim

```
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
                            ordered exactly as D4.2 O5 says>,
}))
```

using the existing primitives unchanged (`relation_identity.py:97-117`): `canonical_material`
(`json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_normalise)`)
and `digest128` (SHA-256 truncated to 128 bits, 32 lowercase hex).

**Included, and why each is here:**

| Term | Why it must be here |
|---|---|
| `identity_schema` | The shape of the material is part of what the id addresses. Without it, a future key addition is undetectable in the record. |
| `tenant_id` | FR-002, §19 ("The logical candidate identity should approximately depend on: tenant …"). Constitution VII: tenant isolation at every level. `relation_candidate.py:1112-1117` states the considered divergence from `RL-` verbatim: *"omitting it would let two tenants' hypotheses bucket under one key, which constitution IV forbids."* |
| `arity_mode` | §19's "arity shape". And it is **derivable** (D2.5 check 4), so it is a redundancy that is checked rather than an independent assertion. |
| `commutative_slots` | The explicit structural marker (D4.5). Without it in the material, a symmetric and an asymmetric reading of one pair would be indistinguishable — and D4.5 says they are different claims. |
| `polarity` | §19 verbatim, FR-002, §41, §109 Case H. "John did not acquire Acme" is a different hypothesis from "John acquired Acme". |
| `predicate_signature.identity_projection()` | The whole of §18 and FR-005. The projection contains the slots, the frame, the lemma, the markers and **both** version strings, so the slots cannot be reinterpreted under a moved convention. |
| `participants` as `(slot, fingerprint, commutable)` | FR-002's "participant configuration" and "role shape", with the role shape expressed structurally (D2) and the participant expressed through a realisation-invariant fingerprint (D4.3). |

**Excluded, and the list is total.** Not in the material, ever:

`relation_surface` · `predicate_surface` · `trigger_span` · `supporting_spans` · `structural_path` ·
`producer_ref` · `producer_version` · `extraction_method` · `extractor_version` ·
`extraction_rule_id` · `signal_refs` · `observation_refs` · `evidence_refs` · `context_ref` ·
`semantic_regime_ref` · `capture_ref` · `neighbourhood` · `signal_ordinal` · `confidence` ·
`candidate_status` · `observed_at` · `recorded_by` · `investigation_id` · `temporal_hypothesis` ·
`relation_ref` · `relation_type` · `schema_version` · `predicate_hypothesis` · `alternative_refs` ·
`mapping_evidence_refs` · `resolution_state` · any observation **ordering** · `mention_id` text ·
any `ENT-`/`RES-` literal · any type datum · any `extra` (FR-010: "`extra` is for producer-specific
non-core metadata only").

Every collection that **is** present is emitted in canonical order (participants by D4.2 O5,
`commutative_slots` sorted, markers parallel to slots), so no caller iteration order can reach the
id — the defect `relation_candidate.py:1180-1205` and `assembly.py` currently leave to a hand-sort
at one call site.

**What changes versus HEAD, in one line**: today
`logical_material(self.arity_mode, self.relation_surface, self._participants, self.role_assignments)`
passes `relation_surface` into the `relation_type` parameter, so **the surface is the predicate
term** (`relation_candidate.py:1131-1139`). After: the predicate term is the signature, and
`relation_type` is out. `CANDIDATE_LOGICAL_MATERIAL_FIELDS` (`relation_candidate.py:513-523`) must
therefore lose `relation_type` and `role_assignments` and gain `predicate_signature`,
`commutative_slots` and `polarity`; it currently declares `relation_type` while the code emits
`relation_surface`, which is the field/emit mismatch `T008` names.

### D5.2 The key invariant

> **INV-IDENTITY: changing the mapping vocabulary does not change the historical logical identity of
> an already-extracted relational observation.**

**Why it is true, in one sentence**: every mapping artefact — the operator registry, the relation
vocabulary, a synonym or equivalence file, an embedding index, a `SemanticRegime` configuration, a
type pack, a `RelationRef` catalogue — is a **non-input** to `logical_candidate_id`, because the
function's inputs are exactly `tenant_id`, `arity_mode`, `commutative_slots`, `polarity`, the
signature projection, and the participant fingerprints, and none of those is derived from a mapping.

**How a store demonstrates it** — the demonstration is mechanical, not rhetorical:

| # | Step | Assertion |
|---|---|---|
| 1 | Extract and store a candidate normally. | `logical_candidate_id` = `X`, `verify_candidate_identity()` passes. |
| 2 | **Replace the entire mapping apparatus** with a different one — a different `RelationRef` set, a different `SemanticRegime` configuration, a different type pack, and a regime that maps `"originator of"` → `works_for` and `"acquire"` → a different operator than before. | the fixtures are different objects; nothing else changed. |
| 3 | Re-read the stored row **from its own columns** and re-derive the id with the *new* mapping apparatus installed. | derived `== X`. `verify_candidate_identity()` still passes. |
| 4 | Run the same re-derivation over the whole stored corpus. | **every** stored `logical_candidate_id` unchanged; the **count of distinct** `logical_candidate_id`s unchanged; the **partition** of candidates by logical id unchanged — same groups, same sizes. |
| 5 | Re-run the mapping layer and write the results. | `candidate_id` **changes** (the mapping is revision material, `relation_candidate.py:1159-1178`), and `PredicateHypothesis.resolution_state` changes. So the mapping was not lost — it was recorded as a new reading of the same hypothesis. |

Step 5 is what makes this a *demonstration* rather than a *disclaimer*. Identity is stable **and**
the mapping is not silently dropped: a recognition shows up as a new reading, which is the shape
`relation_candidate.py:1123-1126` argues for and which FR-028 and §49 then give somewhere to live.

**Enforcement, because a docstring is not a mechanism.** Two named tests and one mutation:

- `test_mapping_vocabulary_is_not_an_input_to_logical_identity` — a static check that
  `apps/shared/domain/predicate_signature.py` and the candidate's identity projection import no
  registry, no `RelationRef` catalogue, no type pack, no regime module, and that the key set of
  `identity_projection()` is disjoint from the union of every mapping artefact's keys. Precedent:
  §74's six-symbol import test, and `test_constitution_has_teeth.py`.
- `test_mapping_swap_leaves_every_stored_logical_id_unchanged` — steps 1–5 above against the real
  store.
- **Mutation (§94 sibling, new)**: add `relation_ref.relation_type` to the material. The
  constitutional suite MUST fail. Named `test_mutation_relation_ref_in_logical_material_fails`. §94
  verbatim: *"This is essential because otherwise someone will reintroduce the old FR-040 violation
  in six months."*

**The residual, stated rather than hidden.** The invariant holds because the mapping is not an
input. If anyone later adds a field to `PredicateSignature` that is computed *from* a registry — and
`event_class_hint` (D1.4 item 9) is exactly the shape such a field would take — the invariant breaks
silently. That is why item 9 is a removal and not a deferral, and why the mutation above exists.

---

## D6 — The `SC-001` proof chain

`spec.md:868-870` verbatim:

> - **SC-001**: `"John acquired Acme."` and `"Acme was acquired by John."` produce **one**
>   `logical_candidate_id`, two `signal_id`s, two distinct `relation_surface`s and two
>   `candidate_id`s — derived by the identity function, not by a fixture.

### D6.1 The derivation, mechanically

| Line | Active: `John acquired Acme.` | Passive: `Acme was acquired by John.` | Same? |
|---|---|---|---|
| 1 | `normalize_voice` → row 4 → `VERB_ACTIVE_TRANSITIVE` | `normalize_voice` → row 1 → **demoted** to `VERB_ACTIVE_TRANSITIVE` | yes |
| 2 | V3: `acquired` → `acquire` | V3: head is the participle `acquired` → `acquire` (the AUX `was` is not the head) | yes |
| 3 | V2: `(A0, A1)` | V2: A0 = `by`-agent, A1 = demoted `nsubj:pass` → `(A0, A1)` | yes |
| 4 | V4: `(NOMARK, NOMARK)` | V4: A0 = `NOMARK` (canonical-active subject); observed `by` → trace/evidence | yes |
| 5 | `identity_projection()` — see D3.8's JSON, verbatim | identical dict | yes |
| 6 | Both resolve the same two mentions → `MN-john`, `MN-acme` | same | yes |
| 7 | `stable_participant_fingerprint(MN-john)` = `p_j`; `(MN-acme)` = `p_a`. Independent of the sentence, span, producer, type and confidence (D4.3). | identical | yes |
| 8 | `canonical_participant_ordering`: A0 < A1 by index; one occupant per slot; no tie-break reached | identical | yes |
| 9 | Same `tenant_id`, same `arity_mode=directed`, same `commutative_slots=[]`, same `polarity=asserted`, same `identity_schema` | identical | yes |
| 10 | `canonical_material({…})` | byte-identical | yes |
| 11 | `digest128(…)` → `logical_candidate_id` = `CAND-` + 32 hex | **same 32 hex** | **one `logical_candidate_id`** |

### D6.2 Everything else stays different — as required

| Requirement | Mechanism | Test |
|---|---|---|
| **two `signal_id`s** | `signal_id` material keeps `producer_ref` (FR-006, §24, and the correct behaviour `relation_candidate.py:626-649` documents) and the **observed** frame, which differs (`verb_active_transitive` vs `verb_passive_agent`), plus the differing `predicate_surface`. | `test_sc001_produces_two_distinct_signal_ids` |
| **two distinct `relation_surface`s** | `relation_surface` is a durable `Text` column on both candidates and a key in `_revision_material` only (D5.1). | `test_sc001_preserves_two_distinct_surfaces` |
| **two `candidate_id`s** | `candidate_id` = `CNDR-` + digest over `_revision_material(logical_candidate_id)`, which contains `predicate_hypothesis.content_key()` (surface-derived), `signal_refs`, `trigger_span`, `extraction_rule_id`, `observed_at`. All differ. | `test_sc001_produces_two_distinct_candidate_ids` |
| **derived, not a fixture** | There is no code path in `normalize_voice`, `canonical_participant_ordering` or `digest128` that recognises a sentence, a fixture id, or a corpus entry. The derivation is a pure function of a declared structure. | `test_sc001_is_derived_and_a_fixture_cannot_produce_it` — a mutation that hard-codes the two sentences to one id MUST fail, and the corpus MUST run both sentences without either appearing in a mapping table, a lemma exception list or a fixture. |

### D6.3 Remaining holes — named, not papered over

**H1 — `SC-001` requires a declared syntactic structure, and at HEAD no producer can produce one.**
`extractors/signals/syntactic.py` does not exist. R-004 records that `lexical_signals` — the primary
prose producer — *"has never been called by anything in the repository, not even the corpus"*, and
R-001 records that the 019 producers run regexes over raw markup with no DOM and no dependency
parse. So the chain in D6.1 is a chain over an **input that no component currently supplies**.

- **What is now true**: `SC-001` is *computable* — a pure function of a declared
  `SyntacticStructure` / `DependencyStructure`, with a named test that needs no corpus, no parser
  and no producer: `test_normalize_voice_collapses_active_and_passive` asserts the two inputs yield
  one `identity_projection()`.
- **What is still not true**: `SC-001` is *not reachable* end to end until the syntactic producer
  and a pinned parser exist. Review finding **D6** is therefore **closed as a specification defect**
  (the rule exists, is deterministic, is testable, and no longer needs a fixture) and **open as an
  implementation gap** (no task in `tasks.md` creates the producer).
- **Stop condition**: the end-to-end test `test_sc001_end_to_end_over_the_syntactic_producer` is to
  be written **now** and marked `xfail(strict=True)` with reason `syntactic_producer_absent`, and
  to start passing — not being deleted or skipped — the day the producer lands. A test that is
  deleted when it starts passing is the same as a test that never existed.

**H2 — the lemma table is a dependency of the chain, and it does not exist.**
`acquired → acquire` must come from the generated `LEMMA_TABLE` (D1.5). With no parser and no
table, there is no lemma, so there is no signature, so there is no predicate term. Named test
`test_lemma_table_matches_its_committed_digest` gates the table's existence.

**H3 — an un-signatured candidate has no `logical_candidate_id`, and that is a migration
consequence.**

- **Decision**: the signature is **required** for a `logical_candidate_id`. A candidate with
  `predicate_signature is None` gets `logical_candidate_id = ""`, is addressable only by
  `candidate_id`, and `verify_candidate_identity()` refuses to certify it with
  `unaddressed_logical_identity`. Compare `verify_candidate_identity`'s existing
  `if not candidate.candidate_id and not candidate.logical_candidate_id: return` — an unaddressed
  candidate is simply not yet addressed; here the logical half is unaddressed while the revision
  half is not, and that asymmetry MUST be named rather than papered over with a fallback.
- **The alternative, and why I refuse it**: keep a surface-keyed fallback identity term, tagged as
  "degraded". That is FR-001's violation alive under a version tag, and FR-001 is the requirement
  the whole feature exists to satisfy. It would also make two code paths derive ids, and the second
  one would be the one that is wrong.
- **Migration consequence, for whoever owns migration `021`**: existing `relation_candidate` rows
  have no signature, so their `logical_candidate_id` is **not** back-filled. Their `candidate_id`s
  are unchanged. Rows gain `logical_candidate_id = ''` until re-extraction supplies a signature. This
  must be stated in the migration, not discovered in a query.
- **Stop condition**: if a product requirement exists for a surface-keyed logical id on
  un-signatured candidates, that requirement **conflicts with FR-001** and must be escalated as a
  spec conflict. It must not be implemented.

**H4 — polarity must be `asserted` on both realisations**, or line 9 of D6.1 fails. "Acme was
**not** acquired by John" is a denial and yields a *different* `logical_candidate_id` — correctly
(FR-002, §19, §109 Case H). `SC-001`'s fixture is positive; if a corpus builder writes a negated
variant into the same test, the test is wrong, not the rule.

**H5 — replay determinism (SC-010) requires a pinned parser.** If a parser change alters the
derived frame, slots or markers, the signature changes, and therefore so does the logical id — which
is *correct* (a differently-parsed reading is a different structural claim, and it is a **signal**,
so it is a different observation). For SC-010's "replay yields identical ids", the parser must be
pinned, and R-001 / T003 already require a committed tree-construction digest per fixture. This is
a **dependency to record**, not an identity defect.

**H6 — the preposition and copula cases are not unified, and §19's illustration is therefore only
partly met.** `input.md:1275-1284` illustrates the shape with verbatim:

```text
same logical relation
    ├── observation A: "is CEO of"
    ├── observation B: "became CEO of"
    └── observation C: "was appointed CEO of"
```

Under D3.2, these produce **three different** outcomes: `COPULAR_PREDICATIVE` with lemma `be`;
`COPULAR_PREDICATIVE` with lemma `become`; and `PASSIVE_NO_AGENT`, which is
`UNSUPPORTED_CONSTRUCTION` because there is no overt agent. **This repair does not meet §19's
illustration, and I am not going to pretend it does.**

- Unifying `be` with `become` is a *claim about equivalence* — a lexical-semantic one — and §20
  permits only "deterministic normalization or explicit semantic mapping" to establish it. Lemma
  merging is neither.
- Unifying "was appointed CEO of Acme" with "is the CEO of Acme" requires deciding that the elided
  passive agent is the entity the surface places in the complement — a semantic inference that is
  wrong in general.
- So both belong in the **mapping layer** (D7), where they become `PredicateMappingCandidate` rows
  against two distinct signature fingerprints, and the *platform* records "these are probably the
  same relation" without having *made* them the same relation. That is FR-028 / §49's `AMBIGUOUS`
  state doing its job.
- **Named stop condition**: `test_agentless_passive_is_unsupported_not_guessed`,
  `test_become_and_be_are_distinct_signatures`, and a `known limitation` entry in the completion
  report: *"§19's three-way illustration is not unified by the identity layer; unification is
  available only through the mapping layer, by design (FR-004, §20)."*

### D6.4 The direct answer

> **Is `SC-001` reachable?** **As a pure function, yes** — and it is now a named test that needs no
> corpus and no fixture. **End to end, not yet** — because no producer parses a sentence and no
> lemma table exists, and because the two sentences must be read by the *same* producer (`SC-001`'s
> "two `signal_id`s" presumes one producer's two observations, since `signal_id` is
> producer-specific by FR-006 and §24; that is a corpus-construction requirement, named in
> `test_sc001_corpus_pins_one_producer_for_both_realisations`).
>
> So: review finding **D6** is closed as a specification defect and open as an implementation gap,
> and this repair does **not** claim the end-to-end form. The failure mode to avoid here would be to
> declare `SC-001` satisfied because a dataclass exists. It is not satisfied because a dataclass
> exists.

---

## D7 — Where `owns` / `controls` / `possesses` now live

### D7.1 They CAN and MUST have different signatures

| Input | `predicate_lemma` | Everything else | `identity_projection()` differs? |
|---|---|---|---|
| `John owns Acme` | `own` | frame `verb_active_transitive`, markers `("", "")`, slots `("A0","A1")` | — |
| `John controls Acme` | `control` | identical | yes, in `predicate_lemma` |
| `John manages Acme` | `manage` | identical | yes, in `predicate_lemma` |
| `John possesses Acme` | `possess` | identical | yes, in `predicate_lemma` |

Three distinct `canonical_material` values → **three distinct `logical_candidate_id`s**. This
satisfies FR-004 verbatim (*"`owns`/`controls`/`manages` MUST remain distinct. Surface variation
must not force inequality, and similarity must not force equivalence."*), US2 Acceptance 3 verbatim
(*"'John owns Acme' and 'John manages Acme' … they do **not** merge"*), §20, §86 (*"three logical
hypotheses"*) and SC-007. Tests:
`test_owns_controls_manages_never_share_a_logical_candidate_id`,
`test_lemma_table_has_no_cross_lemma_row`,
`test_lemma_table_matches_its_committed_digest`.

Note what is *not* being claimed: `owns` in two different realisations (`"Acme's owner is John"` vs
`"John owns Acme"`) are also two candidates, because `NOMINAL_POSSESSIVE` /
`COPULA_PREDICATIVE` differ from `VERB_ACTIVE_TRANSITIVE` (D3.2). Under-unification is the accepted
cost and it is visible.

### D7.2 `PredicateMappingCandidate` — the interface (the layer itself is another agent's job)

```python
@dataclass(frozen=True, slots=True)
class PredicateMappingCandidate:
    """One PROPOSED reading of one signature as one known operator.

    A claim, made by a named actor, with evidence and a vocabulary version. Not identity,
    not truth, not a gate. FR-034a's "the relational space begins as observed structure and
    only later becomes a known predicate when the semantic system earns that mapping".
    """

    signature_fingerprint: str
    """digest128 of ``PredicateSignature.identity_projection()``. KEYED ON THE SIGNATURE —
    not on the lemma (a second normaliser) and not on the surface (the original defect)."""

    relation_ref: RelationRef
    """The operator being proposed: ``(relation_type, schema_version)``. Never a bare string
    (``predicate_hypothesis.py:126-135``: a bare string at the primary ref is refused)."""

    mapping_basis: MappingBasis
    """LEXICAL | STRUCTURAL | REGIME | EXTERNAL_VOCABULARY | HUMAN_REVIEW. Required, and no
    value of it may create a *default* proposal: a default is a guess."""

    mapping_state: MappingState
    """PROPOSED | ACCEPTED | REJECTED | AMBIGUOUS | CONFLICTING. §49 / FR-028: two signals
    agreeing on surface with different refs is one hypothesis, state ``AMBIGUOUS``, nothing
    overwritten; genuine disagreement is ``CONFLICTING`` with both preserved."""

    surface_observations: tuple[str, ...]
    """The ``relation_surface`` and ``RoleBinding.surface_role`` texts this proposal was read
    off, verbatim. Retained because a proposal nobody can audit is a proposal nobody can
    revoke."""

    mapping_vocabulary_ref: str
    """Which versioned artefact asserted this. Constitution Governance: "Changes to
    architectural decisions require an ADR (… entity resolution …)". A mapping table is
    entity-resolution-grade and therefore requires an ADR. Review finding **K5** is the
    consequence of not having one; naming the field makes the omission impossible."""

    evidence_refs: tuple[str, ...]
    confidence: float
    recorded_by: str
    recorded_at: datetime | None
```

### D7.3 The direction of the relationship, and its three one-way rules

```
        PredicateSignature  ──(signature_fingerprint)──►  PredicateMappingCandidate
                 ▲                                                    │
                 │                                                    │ ACCEPTED
                 │ one-way; never written back                        ▼
                 └──────── MUST NOT ◄──────────  PredicateHypothesis.relation_ref
                                                  PredicateHypothesis.alternative_refs
                                                  PredicateHypothesis.resolution_state
```

1. **`signature → mapping candidates → `relation_ref`.`** `relation_ref` is a *projection of the
   accepted mapping set*, never an input. `PredicateHypothesis.normalized_form` and
   `RelationSignal.normalized_predicate` are derived reads (D1.6); `relation_ref` is a derived
   projection. Nothing in the identity chain reads the mapping layer — enforced by
   `test_mapping_vocabulary_is_not_an_input_to_logical_identity` (D5.2) and, statically, by
   `test_normalize_voice_and_ordering_never_read_the_mapping_layer` (no import edge from
   `predicate_signature.py` to any registry, regime or type-pack module).
2. **`owns ≡ controls` is expressible here, and only here.** Three separate
   `PredicateMappingCandidate` rows — `(own → controls)`, `(control → controls)`,
   `(possess → controls)` — against **three distinct** `signature_fingerprint`s, each with
   `mapping_basis=HUMAN_REVIEW`, its own `evidence_refs`, its own `recorded_by`, its own
   `mapping_vocabulary_ref`, and `mapping_state=PROPOSED` or `ACCEPTED`. The three candidates stay
   three candidates. The platform can then *answer* "these are probably one relation" and *say who
   thinks so and on what evidence* — which is the difference between a mapping and a synonym table.
3. **A proposal does not unblock a claim by itself.** `RelationClaimMaterial` still requires a
   resolved predicate (FR-024, §50): an `AMBIGUOUS` mapping state yields material no, claim no,
   edge no, exactly as today. And INV-003 verbatim: *"No producer drops an observation because the
   semantic layer does not understand it. An ontology miss yields `UNKNOWN`, never rejection."*

---

## D8 — New FR text, verbatim

**Numbering.** `spec.md` currently ends at **FR-100** (verified: 102 unique `FR-*` definitions, the
highest `FR-100`). These five continue from there. **`FR-103` is deliberately skipped.** It is
already cited as a requirement by `tasks.md` (T019, T020), `data-model.md` §6, `research.md` and
`phase0-results.md`, where it is a **phantom**: review finding **D2** records it as *"cited by 4
places and does not exist — it is brief §103 'DO NOT CREATE A FOURTH EPISTEMIC LEVEL', misread as
an FR"*. Minting a real FR-103 with a different meaning would silently resolve those four citations
onto unrelated content, reproducing D2 in a new form. Retiring the phantom is a separate repair
(§103 belongs in the spec as a non-goal, and `spec.md:911` already carries it as one), so the
number is left vacant rather than reused.

> **Disambiguation, because D2 is a citation-conflation defect**: `FR-1xx` in this block are
> requirement numbers in `spec.md`. `§1xx` in this file are section numbers in `input.md`. They are
> different namespaces, and an `FR-` prefix is never used for a brief section.

---

**FR-101 — `PredicateSignature` field set and exclusions.**

System MUST provide a deterministic frozen `PredicateSignature` carrying exactly `language`,
`predicate_lemma`, `construction_frame` (a member of the closed `ConstructionFrame` enumeration),
`argument_markers` (parallel to the slots, each a member of the closed `ArgumentMarker` enumeration),
`canonical_argument_slots` (contiguous from `A0`, at least two), `voice_normalization_version` and
`predicate_normalization_version`, and no other field. It MUST NOT carry `raw_surface`,
`predicate_surface`, `relation_surface`, `trigger_span`, `supporting_spans`, `producer_ref`,
`producer_version`, `extraction_rule_id`, `evidence`, `observation_refs`, `evidence_refs`,
`signal_refs`, `confidence`, `relation_ref`, `relation_type`, `schema_version`, `alternative_refs`,
`mapping_evidence_refs`, `resolution_state`, any normalized-predicate mapping, any normalized
raw-surface synonym, any participant or entity reference, or any temporal datum. `arity` and
`direction` MUST be derived properties and MUST NOT be fields. `PredicateHypothesis.normalized_form`
and `RelationSignal.normalized_predicate` MUST be derived read-only views of `predicate_signature`
and MUST NOT be constructor inputs, so that exactly one normaliser exists in the platform. It MUST
NOT be a `RelationRef` and MUST NOT be a semantic ontology concept.

**Test method**: `apps/shared/tests/unit/test_predicate_signature.py::test_signature_field_set_is_exhaustive_and_excludes_surface_mapping_and_participants`
(asserts the exact field list via `dataclasses.fields`), and
`::test_predicate_hypothesis_refuses_a_constructor_supplied_normalized_form`,
`::test_normalized_predicate_is_a_derived_view_of_the_signature`,
`::test_signature_without_a_normalization_version_is_a_contract_error`.
**Independently testable because** it asserts a type's field list and two read-only properties, with
no producer, parser, corpus or store. (§18, §19, §20, §21, §23; replaces FR-003.)

**FR-102 — `normalize_voice` is a specified deterministic algorithm.**

System MUST provide `normalize_voice(predicate, syntactic_structure, dependency_structure) ->
CanonicalArgumentAssignment` as the ONLY function assigning canonical argument slots, executing the
ordered steps `V0.validate`, `V1.frame`, `V2.assign_slots`, `V3.lemmatise`, `V4.markers`, `V5.trace`,
`V6.arity` against a versioned construction table, with first-match-wins row order as the tie-break
and with the argument tie-break fixed as `(ArgumentMarker ascending, position_label ascending
byte-wise)`. It MUST map `Company acquired Asset` and `Asset was acquired by Company` to the same
canonical argument assignment: `A0 = Company`, `A1 = Asset`, `predicate_lemma = acquire`,
`construction_frame = verb_active_transitive`, `argument_markers = ("", "")`. It MUST normalise the
ARGUMENT STRUCTURE and not the sentence's textual form, and the observed frame, the observed `by`,
the span and the surface MUST remain available as evidence. It MUST support the constructions
`active`, `passive` (with an overt `by`-agent), `copular`, `nominal`, `appositional`, `possessive`,
`prepositional` and `relative clause`, and no others; it MUST unify nothing except voice, because
unification is a claim about equivalence that §20 reserves to explicit mapping. An unsupported
construction MUST yield `UNSUPPORTED_CONSTRUCTION` and MUST NOT be guessed, defaulted, retried or
approximated by any fallback frame. A reading occupying fewer than two canonical slots MUST yield
`NO_CONFIGURATION` and MUST NOT be padded. No lemma table row may map a surface to a lemma of which
it is not a morphological form, and the table MUST be a generated artefact with a committed digest.

**Test method**: `apps/shared/tests/unit/test_predicate_signature.py::test_normalize_voice_collapses_active_and_passive`,
`::test_normalize_voice_does_not_unify_anything_but_voice`,
`::test_unsupported_construction_yields_no_signature`,
`::test_unsupported_construction_is_never_guessed_into_a_frame`,
`::test_intransitive_reading_yields_no_configuration`,
`::test_lemma_table_has_no_cross_lemma_row`,
`::test_lemma_table_matches_its_committed_digest`,
`::test_normalize_voice_marks_a_ditransitive_recipient_with_to_and_drops_a_temporal_complement_with_a_trace`.
**Independently testable because** it is a pure function of three declared data structures and a
committed table, driven entirely by literal inputs. (§18, §20, §22, §29, §30, §84; unblocks SC-001.)

**FR-104 — Canonical participant ordering is a specified deterministic algorithm.**

System MUST provide `canonical_participant_ordering(signature, commutative_slots, participants) ->
tuple[CanonicalParticipant, ...]` as the ONLY participant ordering admitted to logical identity.
Participants MUST be ordered by `canonical_argument_slot` ascending, comparing the wrapped integer
index and never the token text, and participants sharing one slot MUST be ordered ascending by
`stable_participant_fingerprint`, compared byte-wise, preserving multiplicity and never
deduplicating. `stable_participant_fingerprint` MUST digest `mention_kind`, `normalized_surface`,
`capture_ref`, `segment_ref`, `start` and `end`, and MUST NOT digest the mention id text, any
producer, extractor, span, evidence ref, observation ref, confidence, type datum, `argument_shape`,
`surface_role`, `role_hypothesis` or any timestamp. Two participants MUST be commutable if and only
if they occupy the same `canonical_argument_slot` AND that slot is declared in
`commutative_slots`; participants in different slots MUST NEVER be commutable. A slot that is not
declared commutative and holds more than one participant MUST be refused as a contract error rather
than ordered. `commutative_slots` MUST always be explicitly present on a candidate, MUST be derived
from no other datum, and MUST NOT be inferred from a missing or unknown direction.

**Test method**: `apps/shared/tests/unit/test_predicate_signature.py::test_binary_and_nary_ordering_is_by_slot_then_fingerprint`,
`::test_participant_fingerprint_is_invariant_across_realisations`,
`::test_participant_fingerprint_excludes_producer_span_type_and_confidence`,
`::test_slot_occupants_are_ordered_by_fingerprint`,
`::test_non_commutative_slot_with_two_members_is_a_contract_error`,
`::test_undirected_ordering_uses_the_slot_marker_not_a_mention_id_sort`,
`::test_symmetry_is_never_inferred_from_missing_direction`,
`::test_arity_mode_is_derivable_from_commutative_slots`.
**Independently testable because** it is a pure function of a signature, an explicit slot set and a
list of bindings, with no store and no parser. (§19, §22, §23, §52, §53, §54, §103.)

**FR-105 — The logical candidate identity rule.**

`RelationCandidate.logical_candidate_id` MUST equal `"CAND-" + digest128(canonical_material(material))`
where `material` contains exactly `identity_schema`, `tenant_id`, `arity_mode`, `commutative_slots`,
`polarity`, `predicate_signature` (its `identity_projection()`, which carries
`canonical_argument_slots`, `construction_frame`, `argument_markers`, `predicate_lemma`, `language`,
`voice_normalization_version` and `predicate_normalization_version`) and `participants` (each entry
`{"slot", "participant_fingerprint", "commutable"}`, ordered by FR-104). It MUST NOT contain
`relation_surface`, `predicate_surface`, `trigger_span`, `supporting_spans`, `structural_path`,
`producer_ref`, `producer_version`, `extraction_method`, `extractor_version`, `extraction_rule_id`,
`signal_refs`, `observation_refs`, `evidence_refs`, `context_ref`, `semantic_regime_ref`,
`capture_ref`, `neighbourhood`, `signal_ordinal`, `confidence`, `candidate_status`, `observed_at`,
`recorded_by`, `investigation_id`, `temporal_hypothesis`, `relation_ref`, `relation_type`,
`schema_version`, `predicate_hypothesis`, `alternative_refs`, `mapping_evidence_refs`,
`resolution_state`, any mention id text, any type datum, any `ENT-` or `RES-` literal, any `extra`
value, or any caller collection order. Every collection present MUST be emitted in canonical order.
A candidate with no `predicate_signature` MUST NOT be given a `logical_candidate_id`, and
`verify_candidate_identity()` MUST refuse to certify one with
`unaddressed_logical_identity`; a surface-keyed fallback identity term is FORBIDDEN.

**Test method**: `apps/shared/tests/constitution/test_identity_subsystem_constitution.py::test_logical_material_key_set_is_exact`,
`::test_no_caller_order_reaches_the_logical_id`,
`::test_candidate_without_a_signature_has_no_logical_candidate_id`,
`::test_verify_candidate_identity_refuses_an_unaddressed_logical_id`,
and the §94 mutation `::test_mutation_relation_ref_in_logical_material_fails`.
**Independently testable because** it asserts a literal key set on a pure function and a refusal
condition on a dataclass, with no corpus. (§17, §19, §23, §94, §95; replaces FR-001 and FR-002.)

**FR-106 — The mapping-independence invariant.**

Changing the mapping vocabulary MUST NOT change the historical logical identity of an
already-extracted relational observation. Every mapping artefact — the operator registry, the
relation vocabulary, any synonym or equivalence file, any embedding index, any `SemanticRegime`
configuration, the type pack and any `RelationRef` catalogue — MUST be a non-input to
`normalize_voice`, to `canonical_participant_ordering` and to `logical_candidate_id`, and none of
those modules may import a registry, regime or type-pack symbol in executable code. A change to the
mapping layer MUST appear as a change to `candidate_id` and to
`PredicateHypothesis.resolution_state`, and MUST appear as a set of `PredicateMappingCandidate`
records keyed on `signature_fingerprint`, and MUST NOT appear as a change to any stored
`logical_candidate_id`, to the number of distinct stored `logical_candidate_id`s, or to the
partition of candidates by logical id. A `PredicateSignature` field computed from a registry —
including an event-class or ontology-derived field — is FORBIDDEN.

**Test method**: `apps/shared/tests/constitution/test_identity_subsystem_constitution.py::test_mapping_vocabulary_is_not_an_input_to_logical_identity`
(static: no import edge from `predicate_signature.py` to any registry, regime or type-pack module,
and `identity_projection()`'s key set disjoint from every mapping artefact's key set),
`::test_normalize_voice_and_ordering_never_read_the_mapping_layer`,
`::test_mapping_swap_leaves_every_stored_logical_id_unchanged` (store-level, D5.2 steps 1–5),
`::test_mapping_change_moves_candidate_id_and_not_logical_candidate_id`.
**Independently testable because** the first two are static import assertions and the last two
require only a store and two mapping fixtures, not a parser or a corpus. (§20, §21, §49, §65, §66,
§104; new — no existing FR states it.)

---

## D9 — Exact old text, exact new text, and the F-series closure

### D9.1 `data-model.md` — line ranges and replacements

#### D9.1.1 §1 `PredicateSignature`: **lines 15–62, replaced in full**

**OLD (lines 21–31, verbatim):**

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

**NEW:** the `PredicateSignature` declaration in D1.1, verbatim.

**OLD (lines 42–57, verbatim — the N-rules block):**

```
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
```

**NEW (verbatim):**

```
**Normalisation is one function, versioned, generated, and it is not a semantic layer.**

The predicate term of `logical_candidate_id` is `predicate_lemma`, and `lemma_table` is a
**generated** artefact: regular inflection rules plus an explicitly enumerated list of
derivation suffixes, with a committed `LEMMA_TABLE_DIGEST`. There is no row type that maps
one base lemma onto a different base lemma, so no synonym table is representable here, and
adding one changes the committed digest and fails
`test_lemma_table_matches_its_committed_digest`. N5 is deleted, not bounded: a synonym table
keyed into identity is an identity authority, which FR-004, §20, US2 Acceptance 3 and
constitution invariant 3 each forbid, and the constitution's Governance clause names entity
resolution as ADR-requiring. Equivalence between distinct lemmas is a **mapping-layer**
claim (`PredicateMappingCandidate`, keyed on the signature fingerprint), where it is dated,
attributed, evidence-bearing and revisable — and where it merges nothing.

| # | Rule | Where it now lives | Example |
|---|---|---|---|
| N1 | Unicode NFKC, then casefold | `normalize_surface_for_fingerprint` (participant side) and the casefold inside `LEMMA_TABLE` lookup | `Café` → `café` |
| N2 | Collapse internal whitespace, strip edge punctuation | as N1 | `  "Works For" ` → `works for` |
| N3 | **Voice normalisation only**: a passive clause with an overt `by`-agent maps to its active canonical frame, moving the *arguments* and not rewriting the sentence | `normalize_voice` V1 + V2 | `Asset was acquired by Company` → `acquire(A0:Company,A1:Asset)` |
| N4 | Function-word marking is recorded against a **closed inventory**; a word outside it is `UNSUPPORTED_CONSTRUCTION` | `ArgumentMarker` | `John works at Acme` → marker `at`; `by` is never normalised to `with` |
| N5 | **REMOVED — no synonym set, ever, at this layer** | — | `owns` and `controls` remain two lemmas and therefore two signatures |
| N6 | **REMOVED from the signature**: argument shape is a fact about a referent, lives on `RelationParticipant`, and is excluded from the participant fingerprint so a type reclassification cannot re-key a relation | `RelationParticipant.argument_shape` | `40%` → `entity`… no: `value`, recorded on the participant, never in identity |

**A passive with no overt agent is `UNSUPPORTED_CONSTRUCTION`, not a guess.** Unifying
"was appointed CEO of Acme" with "is the CEO of Acme" requires deciding what the elided
agent is, which is a semantic inference and is therefore a mapping, not a normalisation.
```

**OLD (lines 59–62, verbatim):**

```
Unknown predicates are first-class: `"John is the originator of Acme."` yields
`normalized_predicate="originator of"`, `arity=2`, `direction=subject_to_object`,
`polarity=asserted`, `relation_ref=None`, `resolution_state=UNKNOWN`. That is a complete,
durable hypothesis — the §90 unknown test, end to end.
```

**NEW (verbatim):**

```
Unknown predicates are first-class: `"John is the originator of Acme."` yields
`language="en"`, `predicate_lemma="originate"` (via the enumerated `-or` derivation rule),
`construction_frame=copular_predicative`, `argument_markers=("", "of")`,
`canonical_argument_slots=(A0, A1)`, plus both normalisation versions;
`relation_ref=None`, `resolution_state=UNKNOWN`. `rendered_predicate()` is
`"originate(A0:,A1:of)"`. That is a complete, durable hypothesis — the §90 unknown test,
end to end — and `polarity` and `direction` are on the **candidate**, not the signature, so
the predicate is identical under assertion and denial.
```

#### D9.1.2 §3 `RelationCandidate` identity rule: **lines 136–153, replaced**

**OLD (verbatim):**

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
```

**NEW (verbatim):** the D5.1 rule block, followed by

```
Consequences that the corpus MUST prove, each with the derivation named (D6):

- `"Company acquired Asset."` and `"Asset was acquired by Company."` → **one**
  `logical_candidate_id`, two `signal_id`s, two `relation_surface` values, two
  `candidate_id`s. Proven by `normalize_voice` demoting the passive frame at V1 and
  reassigning slots at V2 — never by a fixture.
- `"works for"` vs `"Works For"` → one logical id, by NFKC + casefold inside the lemma
  lookup. The *lemma* unifies them; the two words remain one predicate.
- `"works for"` vs `"works at"` → **two** logical ids. The preposition is a structural
  marker from a closed inventory, and unifying `at` with `for` is a claim about equivalence
  that §20 reserves to explicit mapping. The mapping layer may propose one operator for both;
  the identity layer may not merge them.
- `"owns"` vs `"controls"` vs `"possesses"` → **three** logical ids, always.
```

#### D9.1.3 §5: **lines 200–209, amended**

**OLD (verbatim):**

```
`DirectionHypothesis` is unchanged: `SUBJECT_TO_OBJECT`, `OBJECT_TO_SUBJECT`, `UNDIRECTED`,
`AMBIGUOUS` — already persisted on `relation_signal`, **absent from `relation_candidate`**, and
`polarity` is not a column on any table (it is a derived local in `assembly.py` only). A
negated candidate and an asserting candidate over the same pair are currently indistinguishable
after a round trip.
```

**NEW (verbatim):**

```
`DirectionHypothesis` is unchanged as an enumeration: `SUBJECT_TO_OBJECT`, `OBJECT_TO_SUBJECT`,
`UNDIRECTED`, `AMBIGUOUS`. It is **no longer a signature field**; it is a *derived, read-only
projection* of `(canonical_argument_slots, commutative_slots)`, checked by
`verify_signature_shape`, and it MUST NOT be a material input — a disagreement between a
declared direction and the slot order would be a silent identity fork. It is still absent from
`relation_candidate` and `polarity` is still not a column on any table, so a negated candidate
and an asserting candidate over the same pair are still indistinguishable after a round trip;
that is fixed by FR-087/FR-088 adding both as columns, and `polarity` now additionally enters
**logical** material (D5.1) as `asserted` or `denied`.
```

### D9.2 `spec.md` — `FR-001…FR-010`, lines 376–412, replacements

**OLD FR-001 / FR-002 (lines 376–382, verbatim):**

```
- **FR-001**: `RelationCandidate.logical_candidate_id` MUST NOT depend on raw
  `relation_surface`, `producer_ref`, `producer_version`, `signal_refs`, `capture_ref`,
  `context_ref`, `semantic_regime_ref`, `confidence`, `candidate_status`,
  `observation_refs` or any observation timestamp. Those are revision/evidence material. (§19,
  §23)
- **FR-002**: Logical identity MUST depend on tenant, participant configuration, arity shape,
  role shape, directional configuration, polarity and predicate signature. (§19)
```

**NEW (verbatim):** superseded by **FR-105** above. `FR-002`'s "directional configuration" is
replaced by "the explicit `commutative_slots` marker and the slot ordering", because a declared
`DirectionHypothesis` can disagree with the slot order and an identity term that can disagree with
itself is a defect.

**OLD FR-003 (lines 383–386, verbatim):**

```
- **FR-003**: System MUST provide a deterministic `PredicateSignature` carrying at least
  language, normalized trigger, lemma, normalized frame, normalized argument roles,
  voice normalization, preposition normalization, particle normalization and event-class hint.
  It MUST NOT be a `RelationRef` and MUST NOT be a semantic ontology concept. (§18)
```

**NEW (verbatim):** superseded by **FR-101** above, with the nine-field reconciliation of D1.4
attached as the change record.

**OLD FR-004 / FR-005 / FR-006 / FR-007 (lines 387–398, verbatim):**

```
- **FR-004**: Normalization MUST be deterministic and MUST NOT unify semantically distinct
  relations. `owns`/`controls`/`manages` MUST remain distinct. Surface variation must not
  force inequality, and similarity must not force equivalence. (§20)
- **FR-005**: A surface-variant pair (`"John acquired Acme"` / `"Acme was acquired by John"`)
  MUST derive the same signature **through the derivation itself**, never through a hard-coded
  fixture. (§18, §84)
- **FR-006**: `RelationSignal.signal_id` MUST remain producer-specific: same producer plus
  same observed structure gives the same id; different producers give different ids.
  Independence MUST be computed over `producer_ref`/`independence_family`, never over
  deduplicated signal content. (§24)
- **FR-007**: The candidate partition MUST stay two-level — `CAND-` answers "which relational
  configuration", `CNDR-` answers "which reading". No fourth epistemic level. (§22, §23, §103)
```

**NEW (verbatim):** `FR-004` and `FR-007` are **retained unchanged** and are now load-bearing and
directly testable (D7.1 and D5.1). `FR-005` is **retained unchanged** and is made computable by
**FR-102**. `FR-006` is **retained unchanged**. No edit is required to any of the four; the repair
adds FR-101, FR-102, FR-104, FR-105, FR-106 alongside them.

**OLD FR-008 / FR-009 / FR-010 (lines 402–412, verbatim):**

```
- **FR-008**: `RelationSignal` MUST carry a first-class `participants: tuple[RelationParticipant, ...]`
  as its canonical participant representation, supporting 2..N participants without a fake
  binary decomposition. `subject_mention_ref`/`object_mention_ref` MAY remain as derived
  compatibility accessors for binary signals. (§13)
- **FR-009**: `RelationParticipant` MUST carry `mention_ref`, `slot`, `role_hypothesis`,
  `ordinal` and `confidence`. (§13)
- **FR-010**: The signal contract MUST explicitly support `role_hypotheses`,
  `arity_hypothesis`, `direction_hypothesis`, `polarity`, `predicate_surface`,
  `normalized_predicate`, `predicate_signature`, `structural_path`, `temporal_evidence`,
  `observation_refs`, `evidence_refs`, `extraction_rule_id` and `signal_ordinal`, in addition
  to the fields 019 introduced. Load-bearing dimensions MUST be typed, not JSONB. `extra` is
  for producer-specific non-core metadata only. (§14)
```

**NEW (verbatim) — FR-008 retained; FR-009 amended; FR-010 amended:**

```
- **FR-008**: `RelationSignal` MUST carry a first-class `participants: tuple[RelationParticipant, ...]`
  as its canonical participant representation, supporting 2..N participants without a fake
  binary decomposition. `subject_mention_ref`/`object_mention_ref` MAY remain as derived
  compatibility accessors for binary signals. (§13)
- **FR-009**: `RelationParticipant` MUST carry `mention_ref`, `slot`, `role_hypothesis`,
  `ordinal` and `confidence`. Its `slot` MUST be a structural `ArgumentSlot` drawn from the
  reading's `canonical_argument_slots`, and MUST NOT be a free-text role name: `purchaser` and
  `buyer` MUST be the same slot. `role_hypothesis` MUST be retained as evidence and MUST NOT
  enter logical identity. (§13, §20)
- **FR-010**: The signal contract MUST explicitly support `role_hypotheses`,
  `arity_hypothesis`, `direction_hypothesis`, `polarity`, `predicate_surface`,
  `normalized_predicate`, `predicate_signature`, `structural_path`, `temporal_evidence`,
  `observation_refs`, `evidence_refs`, `extraction_rule_id` and `signal_ordinal`, in addition
  to the fields 019 introduced. `normalized_predicate` MUST be a derived read-only view of
  `predicate_signature` and MUST NOT be a stored input, so that exactly one normaliser exists.
  Load-bearing dimensions MUST be typed, not JSONB. `extra` is for producer-specific
  non-core metadata only. (§14)
```

### D9.3 Adjacent changes that are outside D9's stated range but are mandatory with this repair

| # | Location | Old, verbatim | New | Why it cannot wait |
|---|---|---|---|---|
| 1 | `spec.md:448-451`, FR-021 | `PredicateHypothesis` MUST preserve `surface_form`, `normalized_form`, `predicate_signature`, … | `PredicateHypothesis` MUST preserve `surface_form`, `predicate_signature`, `relation_ref`, `alternative_refs`, `resolution_state` and `mapping_evidence_refs`, and MUST expose `normalized_form` as a derived read-only view of `predicate_signature`; a constructor-supplied `normalized_form` MUST be refused. | Leaving "MUST preserve `normalized_form`" invites a constructor kwarg back, which is a second normaliser (D1.6). |
| 2 | `spec.md:386`, FR-003's `event-class hint` | see D9.2 | removed | D1.4 item 9. |
| 3 | `tasks.md:53`, **T015** | `Extract the N5 synonym table into a versioned, sourced, reviewable artefact with provenance. If any entry cannot be justified from a source, drop it and let the predicate stay `AMBIGUOUS` rather than guessing. (FR-082)` | **Delete this task.** It is the specification of the forbidden artefact. Its intent is met by the mapping layer (D7), which is a different agent's job. | A task that builds a synonym table will be executed, and it will be the identity authority. |
| 4 | `tasks.md:52`, **T014** (Q4) | `Decide and record **Q4** (research.md): does N-ary identity use role bindings or positional arguments?` | **Answered** by D2/D4: structural `canonical_argument_slot` ordering, with `commutative_slots` as the only commutation marker, and multiplicity preserved. T014 becomes an ADR *record* of that answer, not a decision to be made. | Q4 is the question this repair decides; leaving it open leaves the identity rule open. |
| 5 | `tasks.md:49`, **T011** | `normalisation rules N1–N6. One test per rule.` | Replace "N1–N6" with "D1's seven-field signature, D3's seven ordered steps and its construction table, and D1.5's generated-table digest discipline." | N5 no longer exists; the test-per-rule list changes shape. |
| 6 | `data-model.md:9-11` | `**The seven levels are never collapsed** (I-2):` followed by a **nine**-item list | correct the count or drop the count | Review finding **E4**: the document's own header says seven and lists nine. Not mine, but in the file I am replacing. |
| 7 | `data-model.md:53-57` and `data-model.md:13` | `which fails the constitution's determinism requirement (VI)` | there is no determinism principle in the constitution; VI is Process-Centric | Review finding **E13**; the line is deleted with N5 anyway. |

### D9.4 Which review findings this repair closes, and which remain

| Finding | Status | Evidence |
|---|---|---|
| **D6** — `SC-001` has no enabling requirement | **CLOSED as a specification defect; OPEN as an implementation gap** | FR-102 specifies `normalize_voice` as the enabling requirement; FR-104 specifies ordering; FR-105 specifies the material; FR-106 pins the invariant. `test_normalize_voice_collapses_active_and_passive` is computable today. The end-to-end form still needs a syntactic producer and a pinned parser, and `test_sc001_end_to_end_over_the_syntactic_producer` is `xfail(strict=True)` with reason `syntactic_producer_absent` (D6.3 H1). **I do not claim the end-to-end form.** |
| **E1** — `owns ≡ controls` as a worked example | **CLOSED** | N5 deleted (D9.1.1). The lemma table is generated with a committed digest and has no cross-lemma row type (D1.5). `owns`/`controls`/`manages`/`possesses` are four lemmas and therefore four logical ids (D7.1). Equivalence moves to `PredicateMappingCandidate`, keyed on the signature fingerprint, where it merges nothing (D7.3). |
| **E2** — `role: str` free text inside `logical_candidate_id` | **CLOSED** | `role_names` removed from the signature in favour of `ArgumentSlot` (D1.2); `surface_role` and `role_hypothesis` are evidence-only on `RoleBinding` (D2.1); the free-text role never enters the material (D5.1's exclusion list); the fingerprint explicitly excludes it (D4.3); the claim layer's `RelationRoleBinding.role` is flagged as a required follow-on (D4.7 item 4). |
| **E5** — the N5 fallback says two signatures = `AMBIGUOUS` | **CLOSED** | The fallback line is deleted with N5. `AMBIGUOUS` is now produced only by the mapping layer as **one** `PredicateHypothesis` with `alternative_refs` (FR-028, §49, D7.2), and `test_unsignatured_and_signatured_readings_do_not_merge` plus D3.2's under-unification rule guarantee that two signatures are two *candidates*, never one hypothesis with alternatives. |
| **D2** — the `FR-103` phantom | **NOT closed by me, but made safe** | I deliberately did **not** mint FR-103 (D8). Retiring the phantom requires editing `tasks.md` T019/T020, `data-model.md` §6, `research.md` and `phase0-results.md`, which are other jobs' or the reviewer's. Flagged, not fixed. |
| **D3**, **D4**, **D5**, **D7**–**D16**, **E3**, **E4**, **E6**–**E16**, **K1**–**K7** | **NOT mine, not closed** | E3 (`TypeHypothesis` as a container) is deliberately untouched (P3). E4 and the seven/nine count are noted in D9.3 item 6. The rest are other jobs. |

---

## 10. Things that are undecidable from the brief, and the stop condition for each

| # | Question | Why it is undecidable here | Stop condition — do **not** invent a rule |
|---|---|---|---|
| U1 | Should `is CEO of` / `became CEO of` / `was appointed CEO of` be one logical relation? | §19 illustrates it; §20 forbids establishing it by anything but deterministic normalisation or explicit semantic mapping; and unifying them needs either a lemma merge or an elided-agent inference, both semantic. | **Not decided here.** Unification is available only through the mapping layer, as `PredicateMappingCandidate` rows against distinct signature fingerprints. Recorded as a `known limitation` (D6.3 H6). |
| U2 | Should `works at` and `works for` be one logical relation? | Same: a preposition-merge is a lexical-semantic claim, and `ArgumentMarker` exists precisely so it cannot be made by accident. | **Not decided here.** Two signatures; the mapping layer may propose one operator for both (D1.7). |
| U3 | Should a relative clause collapse with its matrix-free paraphrase? | Requires the inference "the matrix NP is the relative clause's subject", true commonly and false for reduced relatives and adjuncts. A usually-right rule is a guess. | **Not decided here.** `RELATIVE_CLAUSE` is its own frame (D3.4 row 10). |
| U4 | Should a copular predicate collapse with a bare appositive? | Same class as U1, and §29 lists them as separate constructions. | **Not decided here.** Two frames (D3.2). |
| U5 | Is coordination (`John and Mary acquired Acme`) a commutative non-commutative slot? | Requires deciding whether coordination preserves argument structure — a linguistic question, and the frame is not in §29's list. | **Not decided here.** `UNSUPPORTED_CONSTRUCTION` until a coordinated frame *and* a symmetry marker exist (D4.4). Never ordered by guess. |
| U6 | What is the *ordering* between two mentions that resolve to the same entity? | Entity resolution is downstream of the candidate (`relation_candidate.py:570-577` is explicit: the candidate has resolved nothing). | **Out of scope by construction.** The material is over **mentions** (D4.3), so two mentions of one entity are two participants. This is the correct answer, not a gap. |
| U7 | Should `logical_candidate_id` be back-filled for existing rows? | Migration `021` is another job's, and the answer depends on whether re-extraction or back-fill is the plan. | **Decided by me, flagged for them** (D6.3 H3): no back-fill without a signature; `logical_candidate_id = ''` until one exists; the migration must say so. |
| U8 | Does the claim layer's `RelationArityMode.UNDIRECTED` sort get replaced in 021 or later? | `relation_identity.py` is not in this job's ownership. | **Recorded, not applied** (D4.7). The identity subsystem is specified as one unit precisely so the claim-layer half can be applied by its owner without re-deriving anything. |

---

## 11. Named test index — every test this repair requires, in one place

**`apps/shared/tests/unit/test_predicate_signature.py`** (new; no producer, no parser, no store)
`test_signature_field_set_is_exhaustive_and_excludes_surface_mapping_and_participants` ·
`test_predicate_hypothesis_refuses_a_constructor_supplied_normalized_form` ·
`test_normalized_predicate_is_a_derived_view_of_the_signature` ·
`test_normalized_predicate_is_empty_when_there_is_no_signature` ·
`test_predicate_hypothesis_normalized_form_no_longer_copies_the_surface` ·
`test_signature_without_a_normalization_version_is_a_contract_error` ·
`test_role_binding_version_must_match_its_signature` ·
`test_mixed_normalization_versions_are_refused` · `test_markers_must_be_parallel_to_slots` ·
`test_signature_slots_must_equal_the_bound_slots` ·
`test_signature_may_not_carry_an_observed_passive_frame` ·
`test_commutative_slots_must_be_occupied` · `test_arity_mode_is_derivable_from_commutative_slots` ·
`test_normalize_voice_collapses_active_and_passive` ·
`test_normalize_voice_does_not_unify_anything_but_voice` ·
`test_normalize_voice_output_carries_no_participant_no_surface_and_no_symmetry` ·
`test_unsupported_construction_yields_no_signature` ·
`test_unsupported_construction_is_never_guessed_into_a_frame` ·
`test_unsignatured_and_signatured_readings_do_not_merge` ·
`test_intransitive_reading_yields_no_configuration` ·
`test_no_configuration_is_distinct_from_unsupported_construction` ·
`test_lemma_table_has_no_cross_lemma_row` · `test_lemma_table_matches_its_committed_digest` ·
`test_argument_marker_inventory_is_closed` ·
`test_normalize_voice_marks_a_ditransitive_recipient_with_to_and_drops_a_temporal_complement_with_a_trace` ·
`test_binary_and_nary_ordering_is_by_slot_then_fingerprint` ·
`test_participant_fingerprint_is_invariant_across_realisations` ·
`test_participant_fingerprint_excludes_producer_span_type_and_confidence` ·
`test_slot_occupants_are_ordered_by_fingerprint` ·
`test_non_commutative_slot_with_two_members_is_a_contract_error` ·
`test_coordination_is_unsupported_until_a_frame_and_a_symmetry_marker_exist` ·
`test_undirected_ordering_uses_the_slot_marker_not_a_mention_id_sort` ·
`test_symmetry_is_never_inferred_from_missing_direction` ·
`test_symmetric_and_asymmetric_readings_get_different_logical_ids` ·
`test_argument_slot_space_is_unbounded_and_unregistered` ·
`test_slot_assignment_reads_dependency_position_not_type` ·
`test_same_mention_may_occupy_different_slots_in_different_signatures` ·
`test_argument_slot_carries_no_type_confidence_or_truth_claim` ·
`test_slot_occupants_need_not_share_a_type` ·
`test_owns_controls_manages_never_share_a_logical_candidate_id` ·
`test_works_at_and_works_for_are_distinct_signatures` ·
`test_become_and_be_are_distinct_signatures` ·
`test_agentless_passive_is_unsupported_not_guessed` ·
`test_changing_the_slot_convention_bumps_the_version_and_changes_the_logical_id`

**`apps/shared/tests/constitution/test_identity_subsystem_constitution.py`** (new)
`test_logical_material_key_set_is_exact` · `test_no_caller_order_reaches_the_logical_id` ·
`test_candidate_without_a_signature_has_no_logical_candidate_id` ·
`test_verify_candidate_identity_refuses_an_unaddressed_logical_id` ·
`test_mapping_vocabulary_is_not_an_input_to_logical_identity` ·
`test_normalize_voice_and_ordering_never_read_the_mapping_layer` ·
`test_mapping_swap_leaves_every_stored_logical_id_unchanged` ·
`test_mapping_change_moves_candidate_id_and_not_logical_candidate_id` ·
`test_mutation_relation_ref_in_logical_material_fails` (§94 sibling)

**Corpus / end-to-end** (requires the syntactic producer; see D6.3 H1)
`test_sc001_end_to_end_over_the_syntactic_producer` (`xfail(strict=True)`, reason
`syntactic_producer_absent`) · `test_sc001_produces_two_distinct_signal_ids` ·
`test_sc001_preserves_two_distinct_surfaces` · `test_sc001_produces_two_distinct_candidate_ids` ·
`test_sc001_is_derived_and_a_fixture_cannot_produce_it` ·
`test_sc001_corpus_pins_one_producer_for_both_realisations`

---

## 12. Boundary statements — what this file does not touch

- **`TypeHypothesis`, `TypeCandidate`, `CandidateResolutionState`** — A5's job. Untouched (P3). The
  fingerprint's type exclusion (D4.3) is the only coupling, and it is a decoupling.
- **`relation_claim.py`, `relation_identity.py`** — not this job's files. D4.7 records the four
  required follow-on edits; none is applied here.
- **`semantic/ontology_pack.py`, the type vocabulary, the mapping layer implementation** — D7
  specifies the *interface and the direction* only, as instructed.
- **Migration `021`, the stores, the producer rewrites, `tasks.md`, `spec.md`, `data-model.md`** —
  this file writes no existing file. D9 states the exact old and new text for the spec-repair
  agent to apply; D9.3 lists the seven adjacent edits their owner must make.
- **`predicate_hypothesis.py` `resolution_state` semantics** — unchanged. `PredicateResolutionState`
  keeps `KNOWN`, `UNKNOWN`, `AMBIGUOUS`, `CONFLICTING` verbatim (`predicate_hypothesis.py:95-98`),
  and §21's "`UNKNOWN_RELATION` sentinel" prohibition is honoured by D1.3's exclusion of
  `relation_ref` from the signature and by D7.2's `relation_ref: RelationRef` (never a bare string).

---

## 13. One-paragraph summary for the gate reviewer

`PredicateSignature` v2 carries seven fields and admits no surface, no mapping, no synonym, no
participant and no truth claim; `RoleBinding` v2 carries a structural `ArgumentSlot` and treats
every role word as evidence; `normalize_voice` is a seven-step, table-driven, tie-broken algorithm
whose only unification is passive-with-agent to active; `canonical_participant_ordering` is
slot-then-fingerprint, integer-compared, multiplicity-preserving, with commutativity as an explicit
declared marker that may never be inferred; and `logical_candidate_id` is a digest over tenant,
arity mode, that marker, polarity, the signature projection and the participant configuration, and
nothing else. The signature table is generated with a committed digest and has no cross-lemma row
type, so `owns ≡ controls` is not merely forbidden but unrepresentable; the equivalence moves to a
mapping layer where it is a dated, attributed, evidence-bearing claim that merges nothing.
`SC-001` becomes **computable** — one derivation, no fixture — and I say plainly that it does not
yet become **reachable end to end**, because no producer parses a sentence and no lemma table
exists; the end-to-end test is written now, marked `xfail(strict=True)`, and the reviewer of this
gate should treat the day it starts passing as the day D6 is fully closed. Review findings **D6**
(closed as a spec defect, open as an implementation gap), **E1**, **E2** and **E5** are closed by
this file; **D2** is made safe by not minting `FR-103`; nothing else in the review's F-series is
mine, and eight undecidable questions are listed with their stop conditions rather than answered
with an invented rule.

