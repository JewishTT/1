"""``PredicateSignature`` v2, ``RoleBinding`` v2, the one canonical participant
ordering, and the logical candidate identity rule.

The implementation contract is
``specs/021-entity-relation-extraction-finalization/data-model.md`` parts 1, 2,
4, 5 and 9, arbitrated by ``repair/ARBITRATION.md`` sections 1, 8, 10, 11 and 14
and ``repair/A2-identity-subsystem.md`` D1-D5 and D8. Every exclusion listed in
part 1.2 and part 5.2 is load-bearing and is enforced by a test, not by a
docstring.

The defect this module exists to remove is precise. At HEAD,
``RelationCandidate._logical_material`` (``relation_candidate.py:1131-1139``)
passes ``self.relation_surface`` into ``logical_material``'s ``relation_type``
parameter, so **the raw words the observation used are the predicate term of a
logical identity**. The consequences are not aesthetic: ``"works for"`` and
``"Works For"`` cannot meet, and a producer's spelling choice mints a new world
relation. A signature replaces that with a structural projection - language,
lemma, canonical frame, closed function-word markers, canonical argument slots
and the two rule-set versions - so two realisations of one reading produce one
projection and therefore one ``logical_candidate_id``.

Three properties constrain every choice below, and they are worth stating once
because they are what the rest of the design follows from:

* **The predicate term is derived, never mapped.** A signature is produced
  before ontology mapping and is never re-derived from one (part 1, R-002 point
  4). There is consequently no field, and no row type, in which a base lemma
  could be folded onto a *different* base lemma: ``owns``, ``controls`` and
  ``manages`` stay three lemmas, therefore three signatures, therefore three
  logical ids, forever. That is N5 retired rather than deferred (FR-004, brief
  section 20), and :data:`LEMMA_TABLE` is generated from morphology so the
  forbidden table is not merely discouraged - it is unrepresentable.
* **Voice is the one unification, and only voice** (part 3.2, P-CANON). A
  passive clause with an overt ``by``-agent and its active counterpart produce
  the same canonical argument assignment. Nothing else is unified: ``at`` is not
  ``for``, a relative clause does not collapse with its paraphrase, and a copula
  does not collapse with a bare appositive. The justification is directional:
  under-merging is visible as two candidates, over-merging is invisible as a
  wrong merge.
* **Where a rule would be a guess, the answer is a refusal with a named stop
  condition.** A construction outside the table, a function word outside the
  closed inventory, a lemma the morphology cannot determine, a one-argument
  reading, a participant set assembled across two normalisation versions - each
  raises a typed error carrying a stable ``code``. None of them is resolved by a
  nearest match, a retry, or a default.

Determinism is a constitutional requirement (Domain Invariant 12), so nothing
here reads a clock, a random source or a dict ordering: every collection that
reaches material is emitted in a canonical order derived from a rule, and every
tie-break is a total order over typed values.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Protocol

from domain.relation_identity import RelationArityMode, canonical_material, digest128

#: Version of the identity material's *shape*. Bumped when a key is added or
#: removed from the identity projection, never when a rule's content changes - a
#: rule change bumps that rule's own version field instead, so the two are
#: distinguishable in a stored record. Matches ``part 5.1``.
IDENTITY_SCHEMA_VERSION = "cand-logical-2"

#: The ``normalize_voice`` convention, part 2.4. A change to the slot-assignment
#: convention must bump this, be recorded in the signature's own columns, and
#: produce a different ``logical_candidate_id`` for readings re-derived under the
#: new convention.
VOICE_NORMALIZATION_VERSION = "vn-1"

#: The generated-artefact version (part 1.4/1.5): the lemma table and the
#: argument-marker inventory. Adding a row to either changes this version's
#: subject matter, which is why the lemma table carries its own committed digest
#: so a row addition is a visible diff rather than a silent corpus shift.
PREDICATE_NORMALIZATION_VERSION = "pn-1"

#: Prefix for "which hypothesis this is" (part 5.1). Mirrors
#: ``relation_candidate.LOGICAL_CANDIDATE_ID_PREFIX`` deliberately *without*
#: importing it: that module imports ``semantic.contracts.RelationRef``, and an
#: import edge from the identity path to the mapping vocabulary would be the
#: exact leak ``INV-IDENTITY`` forbids.
LOGICAL_CANDIDATE_ID_PREFIX = "CAND-"


class SignatureContractError(ValueError):
    """A signature, a binding or a reading is not coherent as stated.

    Carries a stable snake_case ``code`` so a caller can distinguish a missing
    parser capability from a violated invariant without parsing the message, and
    so a refusal can be *counted* by reason: brief section 30 requires a missing
    parser capability to mean "no syntactic signals", not a silent fallback and
    not a batch failure, which only holds if the reason is machine-readable.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class ArgumentSlot:
    """A canonical, structural argument position: ``A0``, ``A1``, ``A2``, ...

    NOT an ontology of reality (part 2.3). ``A0`` means "the first argument of
    the construction whose ``construction_frame`` is F" and has no meaning
    outside that signature: there is no global registry, no namespace, no
    hierarchy and no lookup table, and nothing enumerates the admissible values
    beyond ``{A_k : 0 <= k < arity}``. A type pack is a finite named set of
    claims; a slot set is a *formula*. Nothing can be resolved to a slot, so
    nothing can be blocked, expanded or queried by slot.

    Ordered by the wrapped integer, never by the token text: ``A10`` sorts after
    ``A2`` and a string sort inverts that. That is not cosmetic - it changes the
    canonical material.
    """

    index: int

    def __post_init__(self) -> None:
        if isinstance(self.index, bool) or not isinstance(self.index, int):
            raise SignatureContractError(
                "invalid_argument_slot_index",
                f"An argument slot is a position, so its index is an int; got "
                f"{type(self.index).__name__}",
            )
        if self.index < 0:
            raise SignatureContractError(
                "negative_argument_slot", f"index >= 0, got {self.index}"
            )

    @property
    def token(self) -> str:
        """The canonical token form. A **rendering**, and the only form identity uses."""
        return f"A{self.index}"

    def __lt__(self, other: ArgumentSlot) -> bool:
        return self.index < other.index

    def to_identity(self) -> str:
        """The exact value that enters the identity projection."""
        return self.token

    def to_dict(self) -> dict[str, int]:
        return {"index": self.index}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ArgumentSlot:
        return cls(index=int(payload["index"]))


class ConstructionFrame(StrEnum):
    """The construction a predicate was realised in, as a closed structural vocabulary.

    ``VERB_PASSIVE_AGENT`` is an OBSERVED frame. It is admissible on
    ``RelationSignal.observed_construction_frame`` and never admissible on a
    ``PredicateSignature.construction_frame``, because voice handling demotes it
    to ``VERB_ACTIVE_TRANSITIVE`` before the signature is built (part 3, step V1).
    Carrying the observed passive frame in the signature is precisely the defect
    that keeps an active and a passive realisation apart, which is why
    :func:`verify_canonical_frame` exists and why constructing a signature with
    it is a contract error rather than a warning.
    """

    # - the one demotion, per part 3 -
    VERB_PASSIVE_AGENT = "verb_passive_agent"  # observed only

    # - canonical frames: one per construction brief section 29 names, plus two
    #   sub-frames required to be total. No construction outside this enumeration
    #   is supported (part 3.5). -
    VERB_ACTIVE_TRANSITIVE = "verb_active_transitive"
    VERB_ACTIVE_INTRANSITIVE = "verb_active_intransitive"
    COPULA_PREDICATIVE = "copular_predicative"
    COPULA_PREDICATIVE_NOUN = "copular_predicative_noun"
    NOMINAL_OWNER_OF = "nominal_owner_of"
    NOMINAL_POSSESSIVE = "nominal_possessive"
    APPOSITIVE_ROLE = "appositive_role"
    PREP_PHRASE_HEAD = "prep_phrase_head"
    RELATIVE_CLAUSE = "relative_clause"

    @property
    def is_observed_only(self) -> bool:
        return self is ConstructionFrame.VERB_PASSIVE_AGENT


class ArgumentMarker(StrEnum):
    """The closed inventory of function words that mark an argument in a canonical frame.

    A CLOSED, VERSIONED INVENTORY, not a mapping. There is deliberately no alias
    table and no member is ever folded onto another: ``by`` is not ``with``,
    ``of`` is not ``for``. A preposition outside this inventory is
    ``UNSUPPORTED_MARKER`` (part 3, step V4), never ``NOMARK`` and never a guess.
    This is the only lawful form of FR-003's "preposition normalization" and
    "particle normalization": **form** normalisation (NFKC, casefold) over a
    closed set, never cross-word folding. A field that folded ``at`` to ``for``
    would be the forbidden synonym table under a different field name, and
    ``test_argument_marker_inventory_is_closed`` is what makes that impossible to
    do quietly.
    """

    NOMARK = ""  # structurally unmarked (a canonical-active subject, e.g.)
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


class Polarity(StrEnum):
    """Whether the assertion stands, is denied, or is held open.

    Lives on the *candidate*, not the signature (part 1.1): brief section 109
    case H requires ``predicate = acquire`` for "John did not acquire Acme", so
    the same predicate must exist under the opposite polarity. Polarity on the
    signature would make one predicate two.

    It still enters **logical** material (part 5.1), because "John did not acquire
    Acme" is a different hypothesis from "John acquired Acme" (FR-002, brief
    section 19).
    """

    ASSERTED = "asserted"
    DENIED = "denied"
    UNCERTAIN = "uncertain"


# --------------------------------------------------------------------------- #
# N5: the generated lemma table
# --------------------------------------------------------------------------- #

#: The enumerated derivation suffixes, as ``(suffix, rule)`` pairs, applied in this
#: fixed order (part 1.5). Derivation is *morphology*: a rule appends a suffix to a
#: lemma's stem and the table maps the resulting surface back to that same lemma.
#: There is no rule that maps one base lemma onto another, which is the whole of
#: the N5 removal in data form.
#:
#: Three of the seven carry ``no_rule``, and that is a decision rather than an
#: omission. ``-ion`` is not formable from a verb lemma by spelling: English
#: inserts a syllable ("acquire" -> "acquisition", not "acquirion"), and the rule
#: that would produce it has to know which of -ation/-ution/-ic- applies, which is
#: a lexical fact. The ``-ation`` rule below covers the one case the sources
#: exercise, and the closure grows with a committed digest when a real predicate
#: needs another. Inventing the rule would produce surfaces that lemmatise to the
#: wrong lemma, which is a silent merge - precisely what N5 exists to prevent.
DERIVATION_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("or", "attach"),
    ("er", "attach"),
    ("ion", "no_rule"),
    ("ment", "attach"),
    ("ation", "attach_ate"),
    ("ing", "attach"),
    ("ee", "attach"),
)


#: The closed lemma inventory the inflection rules are *generated from*. Not a
#: synonym table and not a mapping: each entry contributes only morphological
#: forms of itself, which is what ``test_lemma_table_has_no_cross_lemma_row``
#: proves. Generating surface forms from a pinned lemma inventory - rather than
#: guessing a lemma from an unseen surface - is the only construction in which
#: "acquired" resolves to ``acquire`` and "worked" to ``work`` with neither one
#: being a guess: the two past forms are spelled differently precisely because the
#: lemmas end differently, and that fact is in the inventory, not in a rule.
LEMMA_INVENTORY: tuple[str, ...] = (
    "acquire",
    "act",
    "appoint",
    "be",
    "become",
    "build",
    "control",
    "drive",
    "draw",
    "employ",
    "found",
    "give",
    "go",
    "grant",
    "hire",
    "hold",
    "invest",
    "know",
    "lead",
    "manage",
    "meet",
    "operate",
    "originate",
    "own",
    "pay",
    "produce",
    "provide",
    "remain",
    "report",
    "run",
    "say",
    "see",
    "sell",
    "send",
    "take",
    "tell",
    "use",
    "win",
    "work",
    "write",
)

#: Pinned irregular surfaces. Two jobs and no more: they supply forms the regular
#: rules cannot spell ("sold" from "sell", "was" from "be"), and they suppress the
#: regular rules for any lemma that appears here, so no invented form ("selld",
#: "beed") ever enters the table. Every pair is a *morphological* relation, which
#: the cross-lemma test re-checks rather than trusts.
PINNED_IRREGULAR_FORMS: Mapping[str, str] = MappingProxyType(
    {
        "bought": "buy",
        "sold": "sell",
        "made": "make",
        "met": "meet",
        "led": "lead",
        "held": "hold",
        "knew": "know",
        "took": "take",
        "paid": "pay",
        "said": "say",
        "saw": "see",
        "sent": "send",
        "told": "tell",
        "won": "win",
        "ran": "run",
        "went": "go",
        "gave": "give",
        "wrote": "write",
        "drew": "draw",
        "drove": "drive",
        "built": "build",
        "was": "be",
        "were": "be",
        "is": "be",
        "are": "be",
        "am": "be",
        "been": "be",
        "became": "become",
        "got": "get",
    }
)

_VOWELS = frozenset("aeiou")
_SIBILANT = ("s", "x", "z", "ch", "sh")


def _third_person(lemma: str) -> str:
    """The ``-s`` form, which English spells by rule for every lemma here."""
    if lemma.endswith(_SIBILANT):
        return f"{lemma}es"
    if len(lemma) > 1 and lemma.endswith("y") and lemma[-2] not in _VOWELS:
        return f"{lemma[:-1]}ies"
    return f"{lemma}s"


def _orthography_is_pinned(lemma: str) -> bool:
    """Whether this lemma's spelling is declared irregular rather than ruled.

    A pinned lemma contributes only its citation form, its third-person form and
    its pinned surfaces. That is why "sell" contributes no "selld" and "be" no
    "beed": the table's job is to be a *correct* lookup, and an absent form is an
    honest ``unsupported_lemma`` while a wrongly generated one would be a silent
    merge - a surface the rules invented could collapse two readings of two
    different words. The cost is a coverage gap on the past and gerund of an
    irregular verb, and it is paid deliberately.
    """
    return any(pinned == lemma for pinned in PINNED_IRREGULAR_FORMS.values())


def _inflection_forms(lemma: str) -> tuple[str, ...]:
    """Third person, past and gerund of ``lemma``, spelled by rule."""
    forms = [lemma, _third_person(lemma)]
    if _orthography_is_pinned(lemma):
        return tuple(forms)
    if lemma.endswith("e"):
        forms.extend((f"{lemma}d", f"{lemma[:-1]}ing"))
    else:
        forms.extend((f"{lemma}ed", f"{lemma}ing"))
    return tuple(dict.fromkeys(forms))


def _derivation_surface(lemma: str, suffix: str, rule: str) -> str | None:
    """The derived surface a lemma forms, or ``None`` when the rule declines.

    Every rule is *forward*: it appends a suffix to the lemma's own stem, so the
    table's row can only ever point back at the lemma it was generated from. There
    is no reverse mapping here at all, which is the mechanism behind
    ``test_lemma_table_has_no_cross_lemma_row`` rather than a hope about one.
    """
    if rule == "no_rule":
        return None
    if rule == "attach_ate":
        if not lemma.endswith("ate"):
            return None
        return f"{lemma[:-len('ate')]}ation"
    if rule == "attach":
        stem = lemma[:-1] if lemma.endswith("e") else lemma
        return f"{stem}{suffix}"
    raise SignatureContractError(  # pragma: no cover - the table is closed
        "unknown_derivation_rule", f"no derivation rule named {rule!r}"
    )



def _build_lemma_table() -> dict[str, str]:
    """Generate ``LEMMA_TABLE`` - surface form to lemma, morphology only.

    Built by generation rather than transcription so the no-cross-lemma-row
    property is true *by construction*: every row is a form produced from its own
    lemma by :func:`_inflection_forms`, :func:`_derivation_surface`, or a pinned
    morphological irregular. No code path here can emit a row whose surface is a
    form of some other lemma.
    """
    table: dict[str, str] = {}
    for lemma in LEMMA_INVENTORY:
        for form in _inflection_forms(lemma):
            table.setdefault(form, lemma)
        if _orthography_is_pinned(lemma):
            continue
        for suffix, rule in DERIVATION_SUFFIXES:
            surface = _derivation_surface(lemma, suffix, rule)
            if surface is not None:
                table.setdefault(surface, lemma)
    for surface, lemma in PINNED_IRREGULAR_FORMS.items():
        table[surface] = lemma
    return table


#: The generated lemma table. ``Mapping[str, str]`` is the whole of the type:
#: there is no row type that maps one base lemma onto a different base lemma.
LEMMA_TABLE: Mapping[str, str] = MappingProxyType(_build_lemma_table())

#: Committed digest over ``sorted(LEMMA_TABLE.items())``. A row addition is
#: therefore a diff against a golden value rather than a silent corpus shift
#: (part 1.5), and the test is the mechanism rather than the intention.
LEMMA_TABLE_DIGEST = "2eeb2914d2a907b52b8e142a0efb7c6e"

#: The closed AUX and COPULA sets (part 3.4). Grammar inventories, not semantic
#: vocabularies; ``become`` appears in both and is resolved by TB1's row order,
#: not by preference.
AUX_LEMMA_INVENTORY: frozenset[str] = frozenset({"be", "get", "become"})
COPULA_LEMMA_INVENTORY: frozenset[str] = frozenset({"be", "remain", "seem", "become"})


def morphological_forms_of(lemma: str) -> frozenset[str]:
    """Every surface the rules license for ``lemma``, for the cross-lemma test."""
    forms = set(_inflection_forms(lemma))
    for suffix, rule in DERIVATION_SUFFIXES:
        surface = _derivation_surface(lemma, suffix, rule)
        if surface is not None:
            forms.add(surface)
    return frozenset(forms)



def normalize_surface_for_fingerprint(surface: str) -> str:
    """N1 + N2: NFKC, casefold, whitespace collapsed, edge punctuation stripped.

    N1 and N2 only, and never the predicate rules: a participant's surface is not
    a predicate, and lemmatising it here would make the *participant*
    realisation-dependent while the whole point of the fingerprint is that it is
    not. ``'  "Works For" '`` -> ``'works for'``.
    """
    folded = unicodedata.normalize("NFKC", str(surface)).casefold()
    collapsed = " ".join(folded.split())
    start, end = 0, len(collapsed)
    while start < end and unicodedata.category(collapsed[start]).startswith("P"):
        start += 1
    while end > start and unicodedata.category(collapsed[end - 1]).startswith("P"):
        end -= 1
    return collapsed[start:end]


# --------------------------------------------------------------------------- #
# The signature
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class PredicateSignature:
    """The structural, language-normalised projection of ONE predicate realisation.

    Field order is the identity order: language, lemma, frame, markers, slots,
    then the two rule-set versions. Every field participates in identity except
    the last two, which participate by *pinning* the first five - a signature
    with an empty version string is a contract error, never a legacy row silently
    upgraded (part 2.4), because a guessed version assigns an id whose record
    cannot justify it.

    What is deliberately absent is the load-bearing part, and the list is total
    (part 1.2): raw words, spans, producer identity, reference collections,
    confidence, mapping and ontology material, referential identity, and
    temporal data. Two of those absences are worth the reader's attention.
    A *surface* inside the signature would make brief section 18's own requirement
    - two different surface strings producing one signature "while retaining two
    distinct surface observations: as evidence" - arithmetically impossible. And
    a *type* or *shape* datum would couple the type layer's reclassification to
    relational identity through a digest, so a mention retyped in the type layer
    would fork a relation.
    """

    language: str
    predicate_lemma: str
    construction_frame: ConstructionFrame
    argument_markers: tuple[ArgumentMarker, ...]
    canonical_argument_slots: tuple[ArgumentSlot, ...]
    voice_normalization_version: str
    predicate_normalization_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "language", str(self.language).strip().lower())
        object.__setattr__(self, "predicate_lemma", str(self.predicate_lemma))
        if not self.language:
            raise SignatureContractError(
                "empty_signature_language",
                "a signature is language-specific: a cross-lingual pair is two signatures, "
                "because merging them is a semantic claim that section 20 reserves to "
                "explicit mapping",
            )
        if not self.predicate_lemma:
            raise SignatureContractError(
                "empty_predicate_lemma",
                "the lemma is the sole predicate term in logical_candidate_id; a signature "
                "without one has no predicate to key on",
            )
        try:
            frame = ConstructionFrame(self.construction_frame)
        except ValueError as exc:
            raise SignatureContractError(
                "invalid_construction_frame",
                f"construction_frame must be one of the closed ConstructionFrame members; got "
                f"{self.construction_frame!r}",
            ) from exc
        object.__setattr__(self, "construction_frame", frame)
        markers = tuple(ArgumentMarker(str(marker)) for marker in self.argument_markers)
        slots = tuple(
            slot if isinstance(slot, ArgumentSlot) else ArgumentSlot(int(slot))
            for slot in self.canonical_argument_slots
        )
        object.__setattr__(self, "argument_markers", markers)
        object.__setattr__(self, "canonical_argument_slots", slots)
        for name, version in (
            ("voice_normalization_version", self.voice_normalization_version),
            ("predicate_normalization_version", self.predicate_normalization_version),
        ):
            if not str(version).strip():
                raise SignatureContractError(
                    "unversioned_signature",
                    f"{name} is empty. A signature or binding with no normalisation version "
                    "is quarantined, reported and replayable - never defaulted to the current "
                    "version and never migrated with a guess (part 2.4)",
                )
        verify_canonical_frame(self)
        verify_parallel_markers(self)
        if len(slots) < 2:
            raise SignatureContractError(
                "signature_arity_below_two",
                f"a relational configuration needs at least two canonical argument slots; got "
                f"{len(slots)}. A one-argument reading states a property, not a relation "
                "(part 3.7)",
            )
        expected = tuple(ArgumentSlot(index) for index in range(len(slots)))
        if tuple(sorted(slots)) != expected:
            raise SignatureContractError(
                "slot_gap",
                f"canonical_argument_slots must be contiguous from A0; got "
                f"{[slot.token for slot in slots]}",
            )

    @property
    def arity(self) -> int:
        """Derived, never carried. A carried arity can disagree with the slots, and
        that disagreement is a silent identity fork (part 1.1)."""
        return len(self.canonical_argument_slots)

    def identity_projection(self) -> dict[str, object]:
        """The exact dict that enters ``logical_candidate_material`` (part 5).

        Nothing else may: this is the whole of the predicate term, and every key
        is either structural or a version that pins a structural key.
        """
        return {
            "language": self.language,
            "predicate_lemma": self.predicate_lemma,
            "construction_frame": str(self.construction_frame),
            "argument_markers": [str(marker) for marker in self.argument_markers],
            "canonical_argument_slots": [
                slot.to_identity() for slot in self.canonical_argument_slots
            ],
            "voice_normalization_version": self.voice_normalization_version,
            "predicate_normalization_version": self.predicate_normalization_version,
        }

    def content_key(self) -> str:
        """Address for the projection alone - a structural key, not a candidate id."""
        return digest128(canonical_material(self.identity_projection()))

    def rendered_predicate(self) -> str:
        """A human-readable rendering. **NOT identity** - for the derived
        ``normalized_predicate`` / ``normalized_form`` reads and for logs.

        Form: ``<lemma>(<slot>:<marker>,...)`` with the marker omitted when
        ``NOMARK``. ``"John acquired Acme."`` -> ``"acquire(A0:,A1:)"``.
        """
        args = ",".join(
            f"{slot.token}:{'' if marker is ArgumentMarker.NOMARK else marker}"
            for slot, marker in zip(
                self.canonical_argument_slots, self.argument_markers, strict=True
            )
        )
        return f"{self.predicate_lemma}({args})"

    def to_dict(self) -> dict[str, object]:
        return {
            "language": self.language,
            "predicate_lemma": self.predicate_lemma,
            "construction_frame": str(self.construction_frame),
            "argument_markers": [str(marker) for marker in self.argument_markers],
            "canonical_argument_slots": [slot.to_dict() for slot in self.canonical_argument_slots],
            "voice_normalization_version": self.voice_normalization_version,
            "predicate_normalization_version": self.predicate_normalization_version,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PredicateSignature:
        return cls(
            language=str(payload["language"]),
            predicate_lemma=str(payload["predicate_lemma"]),
            construction_frame=ConstructionFrame(str(payload["construction_frame"])),
            argument_markers=tuple(ArgumentMarker(str(m)) for m in payload["argument_markers"]),
            canonical_argument_slots=tuple(
                _slot_from_payload(slot) for slot in payload["canonical_argument_slots"]
            ),
            voice_normalization_version=str(payload["voice_normalization_version"]),
            predicate_normalization_version=str(payload["predicate_normalization_version"]),
        )


def _slot_from_payload(raw: object) -> ArgumentSlot:
    """Coerce one serialised slot, accepting the object, the mapping and the token.

    The token form exists because ``to_dict`` of an ordering emits ``"A0"`` - the
    identity form - and a reader handed that record must be able to rebuild the slot
    without knowing which of the three shapes a given column holds.
    """
    if isinstance(raw, ArgumentSlot):
        return raw
    if isinstance(raw, Mapping):
        return ArgumentSlot.from_dict(raw)
    if isinstance(raw, int) and not isinstance(raw, bool):
        return ArgumentSlot(raw)
    return ArgumentSlot(int(str(raw)[1:]))



@dataclass(frozen=True, slots=True)
class RoleBinding:
    """One participant's placement in one canonical reading.

    Exactly one of these five fields reaches identity, and both text fields are
    evidence. ``canonical_argument_slot`` is the sole *role* datum the logical
    identity is allowed to read; the *participant* enters separately, through
    the realisation-invariant fingerprint.

    ``surface_role`` and ``role_hypothesis`` are kept verbatim and are never
    consulted by the normaliser or the ordering rule. That is not bookkeeping: it
    is what makes two producers guessing "seller" and "vendor" for the same ``A1``
    produce ONE logical candidate rather than two, which is brief section 43's
    "ONE logical candidate / MANY signals" made mechanical. A guess is a guess -
    a ``role_hypothesis`` is not a ``surface_role``, and neither is a slot - and
    the words survive as ``Text`` so a mapping re-evaluated later still has the
    evidence it needs.
    """

    surface_role: str
    role_hypothesis: str
    canonical_argument_slot: ArgumentSlot
    normalization_version: str
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        slot = self.canonical_argument_slot
        if not isinstance(slot, ArgumentSlot):
            try:
                slot = ArgumentSlot(int(slot))
            except (TypeError, ValueError) as exc:
                raise SignatureContractError(
                    "invalid_canonical_argument_slot",
                    "canonical_argument_slot must be a structural ArgumentSlot - the position "
                    "this participant occupies in the construction - and never a free-text role "
                    f"name; got {self.canonical_argument_slot!r}. 'purchaser' and 'buyer' are "
                    "the same A1 and a role name here would fork the logical id (FR-009).",
                ) from exc
        object.__setattr__(self, "canonical_argument_slot", slot)
        object.__setattr__(self, "surface_role", str(self.surface_role))
        object.__setattr__(self, "role_hypothesis", str(self.role_hypothesis))
        object.__setattr__(
            self, "evidence", tuple(sorted({str(ref) for ref in self.evidence if str(ref)}))
        )
        if not str(self.normalization_version).strip():
            raise SignatureContractError(
                "unversioned_role_binding",
                "normalization_version is empty. A binding assigned by an unnamed version of "
                "normalize_voice cannot be placed in a canonical ordering with one assigned by "
                "a named version, because 'A1' does not mean the same position under both "
                "(part 2.5). Quarantine, report, replay - never default.",
            )

    @property
    def slot(self) -> ArgumentSlot:
        """Read-only alias, so a reader never has to know which word is canonical."""
        return self.canonical_argument_slot

    def to_dict(self) -> dict[str, object]:
        return {
            "surface_role": self.surface_role,
            "role_hypothesis": self.role_hypothesis,
            "canonical_argument_slot": self.canonical_argument_slot.to_dict(),
            "normalization_version": self.normalization_version,
            "evidence": list(self.evidence),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RoleBinding:
        return cls(
            surface_role=str(payload["surface_role"]),
            role_hypothesis=str(payload["role_hypothesis"]),
            canonical_argument_slot=_slot_from_payload(payload["canonical_argument_slot"]),
            normalization_version=str(payload["normalization_version"]),
            evidence=tuple(str(ref) for ref in payload.get("evidence", ())),
        )



# --------------------------------------------------------------------------- #
# Agreement rules (part 2.5)
# --------------------------------------------------------------------------- #


def verify_canonical_frame(signature: PredicateSignature) -> None:
    """Refuse an observed passive frame on a signature.

    Its own function because the failure is the one a future contributor is most
    likely to reintroduce: putting ``observed_construction_frame`` on the
    signature "just for diagnostics" restores exactly the fork between an active
    and a passive realisation that this subsystem exists to remove.
    """
    if signature.construction_frame.is_observed_only:
        raise SignatureContractError(
            "observed_passive_frame_on_signature",
            f"construction_frame={signature.construction_frame.value!r} is the OBSERVED "
            "passive frame. Voice handling demotes it to verb_active_transitive at step V1 "
            "before the signature is built, so carrying it here keeps an active and a passive "
            "realisation apart. The observed frame belongs on the signal, as evidence.",
        )


def verify_parallel_markers(signature: PredicateSignature) -> None:
    """Markers are parallel to slots; a length mismatch is a truncated construction."""
    if len(signature.argument_markers) != len(signature.canonical_argument_slots):
        raise SignatureContractError(
            "markers_not_parallel_to_slots",
            f"{len(signature.argument_markers)} markers against "
            f"{len(signature.canonical_argument_slots)} slots: argument_markers is parallel to "
            "canonical_argument_slots, so a length mismatch is a truncated construction, not a "
            "relation",
        )


def verify_slot_version_agreement(
    signature: PredicateSignature, bindings: Sequence[RoleBinding]
) -> None:
    """Refuse a participant set assembled across two normalisation versions.

    A binding assigned by an older convention and one assigned by a newer
    convention cannot be placed in a single canonical ordering, because "A1" does
    not mean the same position under both. Assembling them would produce an order
    neither version would produce, and therefore an id neither version can
    re-derive.
    """
    versions = sorted({binding.normalization_version for binding in bindings})
    if len(versions) > 1:
        raise SignatureContractError(
            "mixed_normalization_versions",
            f"participants carry normalisation versions {versions} but the signature was "
            f"assigned by {signature.voice_normalization_version!r}. A1 does not mean the same "
            "position under two conventions, so this set cannot be ordered canonically",
        )
    for binding in bindings:
        if binding.normalization_version != signature.voice_normalization_version:
            raise SignatureContractError(
                "role_binding_version_must_match_signature",
                f"binding for {binding.canonical_argument_slot.token} was assigned by "
                f"{binding.normalization_version!r} but the signature declares "
                f"{signature.voice_normalization_version!r}",
            )


def verify_signature_shape(
    signature: PredicateSignature,
    bindings: Sequence[RoleBinding],
    commutative_slots: frozenset[ArgumentSlot] = frozenset(),
) -> None:
    """The four total checks that keep slot, frame and arity from drifting.

    1. markers parallel to slots; 2. the distinct occupied slots equal the
    signature's contiguous slot skeleton - the signature carries the skeleton and
    the bindings carry the occupants, and the two may not disagree; 3. no
    observed-only frame; 4. commutativity is declared only for occupied slots.
    """
    verify_canonical_frame(signature)
    verify_parallel_markers(signature)
    occupied = {binding.canonical_argument_slot for binding in bindings}
    declared = list(signature.canonical_argument_slots)
    if sorted(occupied) != declared:
        raise SignatureContractError(
            "signature_slots_disagree_with_bindings",
            f"the signature declares slots {[slot.token for slot in declared]} but the bindings "
            f"occupy {[slot.token for slot in sorted(occupied)]}; the skeleton and the "
            "occupants are one structural claim and may not disagree",
        )
    unoccupied = sorted(commutative_slots - occupied)
    if unoccupied:
        raise SignatureContractError(
            "empty_commutative_slot",
            f"commutative_slots declares {[slot.token for slot in unoccupied]}, which no "
            "participant occupies. A symmetry marker with no occupant describes a relation "
            "nobody asserted",
        )
    verify_slot_version_agreement(signature, bindings)


# --------------------------------------------------------------------------- #
# The participant fingerprint (part 4.3) and the ordering (part 4)
# --------------------------------------------------------------------------- #


class ResolvedMention(Protocol):
    """What ``stable_participant_fingerprint`` reads, structurally.

    Declared as a protocol rather than a concrete type because no mention record
    is owned by this subsystem, and a fingerprint that depended on one concrete
    record's fields would couple identity to that record's shape. The attribute
    set is exactly the digest input and nothing more.
    """

    kind: str
    surface: str
    capture_ref: str
    segment_ref: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class ParticipantBinding:
    """One participant's placement: the role binding plus the mention that fills it.

    Named here because part 4.1's ``canonical_participant_ordering(signature,
    commutative_slots, participants: Sequence[RoleBinding])`` cannot be satisfied
    by a bare ``RoleBinding``: the ordering emits a
    ``participant_fingerprint`` (part 4.1) and part 2.1's five fields are
    complete, all of them evidence or role data, with no place for the participant
    itself. Adding a mention field to ``RoleBinding`` was rejected because that
    would put a referential fact among the role fields and make the exclusion in
    part 2.1 unenforceable. So the pairing lives in its own type and both
    specified parts are honoured literally: the binding stays five fields, and
    the ordering takes bindings plus the mention each one places.
    """

    role: RoleBinding
    mention: ResolvedMention

    def __post_init__(self) -> None:
        if not isinstance(self.role, RoleBinding):
            raise SignatureContractError(
                "invalid_role_binding",
                f"role must be a domain.predicate_signature.RoleBinding; got "
                f"{type(self.role).__name__}",
            )


def stable_participant_fingerprint(mention: ResolvedMention) -> str:
    """32 lowercase hex over the mention's own identity material, and nothing else.

    MUST digest, key by key:

    * ``mention_kind`` - ``mention.kind``
    * ``normalized_surface`` - ``normalize_surface_for_fingerprint(mention.surface)``
    * ``capture_ref`` - ``mention.capture_ref``
    * ``segment_ref`` - ``mention.segment_ref``
    * ``start`` - ``mention.start``
    * ``end`` - ``mention.end``

    MUST NOT digest, each for a stated reason:

    * the ``mention_id`` *text* - a minting artefact. The material says "a
      participant", not "a string starting MN-"; digesting the id would make
      identity depend on the minter's format, and a re-mint would fork every
      candidate mentioning it.
    * ``producer_ref`` / ``producer_version`` / ``extractor_version`` - FR-001,
      FR-006. They would extend producer scope from the observation level to the
      hypothesis level and break US5 and SC-005.
    * ``trigger_span`` / ``supporting_spans`` / ``structural_path`` - FR-001: a
      surface or a span belongs to a revision, not to a logical id. Two
      realisations of one configuration in one document have two spans and one
      id.
    * ``evidence_refs`` / ``observation_refs`` / ``signal_refs`` - FR-001 and brief
      section 43: which observations back a hypothesis grows.
    * ``confidence`` - FR-001, and a re-scoring pass must not mint a new relation,
      or every ranking change forks the graph.
    * ``type_ref``, kind-as-a-type, any ``TypeHypothesis``, type state,
      ``vocabulary_version`` - INV-001, and it keeps the type layer structurally
      incapable of moving a relational identity. Load-bearing, not tidiness.
    * ``argument_shape`` - same reason: shape is a fact about a referent, so a
      shape reclassification must not re-key a relation (part 1.4 N6).
    * ``surface_role`` / ``role_hypothesis`` / ``normalization_version`` - part 2.1.
      Two producers guessing "seller" and "vendor" for one slot are one logical
      candidate.
    * the relation the mention participates in - the fingerprint is a fact about a
      mention, so the same mention in two relations gets the same fingerprint and
      is ordered by slot.
    * any timestamp or clock reading - SC-010: replay must be a fixed point.
    """
    return digest128(
        canonical_material(
            {
                "mention_kind": mention.kind,
                "normalized_surface": normalize_surface_for_fingerprint(mention.surface),
                "capture_ref": mention.capture_ref,
                "segment_ref": mention.segment_ref,
                "start": mention.start,
                "end": mention.end,
            }
        )
    )


@dataclass(frozen=True, slots=True)
class CanonicalParticipant:
    """One occupant in canonical order: its slot, its fingerprint, its symmetry."""

    slot: ArgumentSlot
    participant_fingerprint: str
    commutable: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "slot": self.slot.token,
            "participant_fingerprint": self.participant_fingerprint,
            "commutable": self.commutable,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CanonicalParticipant:
        return cls(
            slot=_slot_from_payload(payload["slot"]),
            participant_fingerprint=str(payload["participant_fingerprint"]),
            commutable=bool(payload["commutable"]),
        )



def canonical_participant_ordering(
    signature: PredicateSignature,
    commutative_slots: frozenset[ArgumentSlot],
    participants: Sequence[ParticipantBinding],
) -> tuple[CanonicalParticipant, ...]:
    """The ONLY ordering of participants admitted to logical material (part 4).

    Steps, exact:

    * **O1** ``verify_signature_shape`` (and the version-agreement rule). A
      refusal here aborts ordering; nothing downstream sees a partially ordered
      set, because a partial order is not a determinism guarantee.
    * **O2** Group bindings by ``canonical_argument_slot``, preserving
      multiplicity: ``list``, never ``set``. "Acme is co-owned by John and Mary"
      is a different configuration from "Acme is co-owned by John", and a ``set``
      deletes a participant.
    * **O3** Within one slot, sort occupants ascending by
      ``participant_fingerprint``, byte-wise over 32 lowercase hex. That is the
      *whole* tie-break, and it is total because distinct mentions produce
      distinct fingerprints.
    * **O4** Order slots ascending by ``ArgumentSlot.index`` - the wrapped
      integer, never the token text. ``A10`` follows ``A2``; a string sort
      inverts that deterministically and semantically.
    * **O5** Emit ``(slot, fingerprint, slot in commutative_slots)`` per occupant.

    A slot holding more than one occupant in a slot that is *not* declared
    commutative is a contract error (``slot_not_commutative_multiple_members``)
    and no order is emitted: ordering it anyway would be inventing a reading the
    structure does not license. Coordination is refused for the same reason and
    with a named stop condition - see A2 U5.

    Why a slot sort at all for a directed binary relation: because the slots *are*
    the direction. ``Company acquired Asset`` gives ``(A0:Company, A1:Asset)`` and
    ``Asset acquired Company`` gives ``(A0:Asset, A1:Company)``; two material
    values, therefore two logical ids, which is brief sections 44 and 52 and SC-007
    in one mechanism.
    """
    bindings = [participant.role for participant in participants]
    verify_signature_shape(signature, bindings, commutative_slots)

    fingerprints = [stable_participant_fingerprint(item.mention) for item in participants]
    repeated = sorted({value for value in fingerprints if fingerprints.count(value) > 1})
    if repeated:
        raise SignatureContractError(
            "duplicate_participant_fingerprint",
            f"participants share fingerprint(s) {repeated}. The tie-break is a total order "
            "only because distinct mentions produce distinct fingerprints, so a repeat means "
            "the same mention was bound to two roles",
        )

    grouped: dict[ArgumentSlot, list[tuple[str, RoleBinding]]] = {}
    for item, fingerprint in zip(participants, fingerprints, strict=True):
        grouped.setdefault(item.role.canonical_argument_slot, []).append(
            (fingerprint, item.role)
        )

    for slot, occupants in grouped.items():
        if len(occupants) > 1 and slot not in commutative_slots:
            raise SignatureContractError(
                "slot_not_commutative_multiple_members",
                f"slot {slot.token} holds {len(occupants)} participants but is not declared "
                "commutative, so no order is emitted. Two participants are commutable if and "
                "only if they share a slot AND that slot is declared in commutative_slots. "
                "Coordination ('John and Mary acquired Acme') is a named stop condition: it "
                "stays unsupported until a coordinated frame and a symmetry declaration both "
                "exist (brief section 29 lists no coordinated frame; A2 U5).",
            )

    ordered: list[CanonicalParticipant] = []
    for slot in sorted(grouped):
        for fingerprint, _role in sorted(grouped[slot], key=lambda pair: pair[0]):
            ordered.append(
                CanonicalParticipant(
                    slot=slot,
                    participant_fingerprint=fingerprint,
                    commutable=slot in commutative_slots,
                )
            )
    return tuple(ordered)


def derive_arity_mode(
    signature: PredicateSignature,
    commutative_slots: frozenset[ArgumentSlot],
    bindings: Sequence[RoleBinding],
) -> RelationArityMode:
    """``arity_mode`` is DERIVED, never independently asserted (part 2.5 check 4).

    ``commutative_slots == set(occupied slots)`` is exactly the condition under
    which ``RelationArityMode.UNDIRECTED`` is admissible; two occupied slots
    without it are ``DIRECTED``; anything else is ``NARY``, which is native rather
    than a binary pair with a payload. ``verify_signature_shape`` refuses a
    declared mode that disagrees, so the term in the material is a checked
    redundancy rather than a second source of truth.
    """
    occupied = {binding.canonical_argument_slot for binding in bindings}
    if commutative_slots == occupied:
        return RelationArityMode.UNDIRECTED
    if len(occupied) == 2:
        return RelationArityMode.DIRECTED
    return RelationArityMode.NARY


# --------------------------------------------------------------------------- #
# Part 5: the logical candidate identity rule
# --------------------------------------------------------------------------- #


def logical_candidate_material(
    signature: PredicateSignature | None,
    participants: Sequence[ParticipantBinding],
    *,
    tenant_id: str,
    polarity: Polarity = Polarity.ASSERTED,
    commutative_slots: frozenset[ArgumentSlot] = frozenset(),
    arity_mode: RelationArityMode | None = None,
) -> dict[str, Any]:
    """The material of "which hypothesis this is", per part 5.1, verbatim.

    A signature is **required**. A reading with ``predicate_signature is None``
    gets no identity at all rather than a surface-keyed fallback, because a
    surface-keyed fallback is FR-001's violation alive under a version tag, and
    because two code paths deriving ids is one more path to disagree (part 5.4).

    Excluded, and the list is total (part 5.2): every raw surface, span,
    producer, reference collection, confidence, mapping artefact, referential
    identity, type datum, temporal hypothesis and ``extra`` value. Every
    collection that *is* present is emitted in canonical order, so no caller's
    iteration order can reach the id - the defect that
    ``relation_candidate.py:1180-1205`` and ``assembly.py`` currently leave to a
    hand-sort at one call site.
    """
    if signature is None:
        raise SignatureContractError(
            "unaddressed_logical_identity",
            "logical_candidate_id requires a PredicateSignature. A candidate with no signature "
            "is addressable only by candidate_id, and verify_candidate_identity refuses to "
            "certify it - a surface-keyed fallback identity is forbidden (FR-001, part 5.4)",
        )
    ordering = canonical_participant_ordering(signature, commutative_slots, participants)
    bindings = [participant.role for participant in participants]
    derived = derive_arity_mode(signature, commutative_slots, bindings)
    if arity_mode is not None and RelationArityMode(arity_mode) is not derived:
        raise SignatureContractError(
            "arity_mode_disagrees_with_commutative_slots",
            f"declared arity_mode={RelationArityMode(arity_mode)} but the declared "
            f"commutative_slots and the occupied slots derive {derived}. arity_mode is a "
            "checked redundancy, never an independent assertion (part 2.5 check 4)",
        )
    return {
        "identity_schema": IDENTITY_SCHEMA_VERSION,
        "tenant_id": str(tenant_id),
        "arity_mode": str(derived),
        "commutative_slots": sorted(slot.token for slot in commutative_slots),
        "polarity": str(Polarity(polarity)),
        "predicate_signature": signature.identity_projection(),
        "participants": [participant.to_dict() for participant in ordering],
    }


def logical_candidate_id(
    signature: PredicateSignature | None,
    participants: Sequence[ParticipantBinding],
    *,
    tenant_id: str,
    polarity: Polarity = Polarity.ASSERTED,
    commutative_slots: frozenset[ArgumentSlot] = frozenset(),
    arity_mode: RelationArityMode | None = None,
) -> str:
    """``CAND-`` + 32 hex: which relational configuration this is.

    The four parameters are the whole input surface, and each is named for the
    brief's own list (part 5.1): ``tenant_id`` is brief section 19's tenant and
    constitution VII's isolation - omitting it would let two tenants' hypotheses
    bucket under one key, which constitution IV forbids; ``arity_mode`` and
    ``commutative_slots`` are the arity shape, the role shape and the
    directional configuration; ``polarity`` is section 19 verbatim; and the
    signature projection is section 18.

    There is no surface, span, producer, evidence, confidence, observation order,
    type or mapping parameter, and that is the mechanism rather than a promise:
    a datum that cannot be passed cannot reach the id.
    """
    material = logical_candidate_material(
        signature,
        participants,
        tenant_id=tenant_id,
        polarity=polarity,
        commutative_slots=commutative_slots,
        arity_mode=arity_mode,
    )
    return LOGICAL_CANDIDATE_ID_PREFIX + digest128(canonical_material(material))


def lemma_for(observed_form: str) -> str:
    """Look a surface up in the generated table after N1 + N2.

    Raises ``unsupported_lemma`` for anything the morphology does not determine.
    A guessed lemma would be a silent merge - the exact defect N5 was removed to
    prevent - so the honest answer is a refusal with a named stop condition.
    """
    normalised = normalize_surface_for_fingerprint(observed_form)
    if not normalised:
        raise SignatureContractError(
            "unsupported_lemma",
            "an empty predicate head has no lemma; the head must be an overt token",
        )
    lemma = LEMMA_TABLE.get(normalised)
    if lemma is None:
        raise SignatureContractError(
            "unsupported_lemma",
            f"{normalised!r} is not a morphological form of any lemma the generated table "
            "holds. The table is generated (inflection rules + pinned irregulars + enumerated "
            "derivations) and covers no other form; inventing a lemma here would merge two "
            "readings on a guess, which N5 exists to prevent. Either the predicate enters the "
            "closed inventory with a committed digest, or the reading stays unsignatured "
            "(FR-014 basis predicate_text).",
        )
    return lemma


__all__ = [
    "AUX_LEMMA_INVENTORY",
    "COPULA_LEMMA_INVENTORY",
    "DERIVATION_SUFFIXES",
    "IDENTITY_SCHEMA_VERSION",
    "LEMMA_INVENTORY",
    "LEMMA_TABLE",
    "LEMMA_TABLE_DIGEST",
    "LOGICAL_CANDIDATE_ID_PREFIX",
    "PINNED_IRREGULAR_FORMS",
    "PREDICATE_NORMALIZATION_VERSION",
    "VOICE_NORMALIZATION_VERSION",
    "ArgumentMarker",
    "ArgumentSlot",
    "CanonicalParticipant",
    "ConstructionFrame",
    "ParticipantBinding",
    "Polarity",
    "PredicateSignature",
    "ResolvedMention",
    "RoleBinding",
    "SignatureContractError",
    "canonical_participant_ordering",
    "derive_arity_mode",
    "lemma_for",
    "logical_candidate_id",
    "logical_candidate_material",
    "morphological_forms_of",
    "normalize_surface_for_fingerprint",
    "stable_participant_fingerprint",
    "verify_canonical_frame",
    "verify_parallel_markers",
    "verify_signature_shape",
    "verify_slot_version_agreement",
]
