"""A deterministic, pinned shallow parser: the syntactic producer's parser capability.

Feature 021, brief §29 and §30; spec FR-042, FR-043; ``data-model.md`` part 3;
``repair/A2-identity-subsystem.md`` D6.3 H5 and H6.

**Why this module exists at all, and what it is not.** Brief §30 says to inspect the
installed parser capabilities and prefer a deterministic, pinned parser. Inspected: this
repository declares no dependency parser. No spaCy, no NLTK, no Stanza, no benepar, no
udpipe, no CoreNLP - not in ``apps/interpretation/pyproject.toml``, not in ``uv.lock``, and
not importable in the project environment. So the pinned capability is a **shallow
surface-rule parser written here**: a closed tokenizer, a closed function-word inventory,
and an ordered, pinned set of construction rules. That is a legitimate ``FR-043`` parser
capability, and a real one rather than a stub: it determines the construction, the head
lemma and the argument observations, which is exactly the input
``domain.predicate_voice`` declares it consumes. What it is *not* is a full parser. It does
no constituency, no nominal annotation, and no general coreference; and it refuses every
reading whose construction it cannot name - loudly, with a code.

**Four pinned fields, and what makes determinism true rather than hoped for.**

* :data:`MODEL_REF` / :data:`MODEL_VERSION` name the *model* artefact. There is no
  downloaded model, and saying so is more honest than inventing a checkpoint id: a reader
  told ``"spacy/en_core_web_sm"`` and handed a regex will not check.
* :data:`PARSER_VERSION` is the parser's own version, and it is the value that goes on
  ``RelationSignal.producer_version`` - so two readings parsed by different code are two
  observations rather than one reading with two names.
* :data:`CONFIGURATION_HASH` is a digest over :func:`configuration_material`, which lists
  **every** table, inventory, ordering and rule name the parser reads, plus
  ``LEMMA_TABLE_DIGEST``. A rule change is therefore a visible diff against a committed
  golden value, not a silent corpus shift - the mechanism ``predicate_signature`` uses for
  its own lemma table, applied to the parser.

Determinism (constitution Domain Invariant 12) is structural, not incidental: no clock, no
random source, no ``uuid``, no set- or dict-ordering that reaches an output, and every
tie-break is a total order over typed values. :func:`parse` is a pure function of
``(text, language, channel)``.

**Declare the construction; never guess it.** Every rule below *declares* a
:class:`~domain.predicate_voice.SyntacticConstruction` from the surface and then hands the
declared parse to ``normalize_predicate``. A surface matching no rule produces **no reading
and no signal** and a :class:`Refusal` with a stable code - never a fallback construction,
never the nearest row, never a default. Leftover tokens are a refusal too: if a rule cannot
say what a constituent is, the reading is refused rather than reported with the
constituent quietly missing.

**The two gaps this module does not close, stated rather than filled.**

*Gap (a), the temporal complement.* ``domain.predicate_voice`` identifies a temporal
complement by the UD ``tmod`` family, and **no source states the test that identifies
one.** brief ``input.md`` states none either: §109 case D and §30 require a temporal
complement to stay recoverable on the candidate's ``TemporalHypothesis`` and neither says
how a producer recognises it. A function-word list is the obvious candidate and it is a
guess with a concrete cost - ``at`` and ``on`` are locatives as often as they are times,
and ``at`` is the marker of the prepositional construction brief §29 requires. So this
parser **labels no complement as temporal**, and every complement it declares is retained
as a slot: the visible direction, since an over-retained temporal argument is one extra
structural slot while a wrongly dropped one is a lost participant with no trace. The cost
is stated in :data:`PARSER_LIMITATIONS` rather than hidden: ``V2.drop_temporal`` never
fires from this producer, and ``John acquired Acme in 2020`` keeps ``in 2020`` as a slot.

*Gap (b), copular vs active.* The complement's **phrase category** decides this, and
:class:`PhraseCategory` is the producer's own inventory for it. The test is decidable
without a lexicon and without an invented function-word list: a complement whose
phrase-initial token is a member of the pinned preposition inventory is a ``PP``; one
introduced by a subordinator is a ``CP``; one introduced by a relative pronoun, a relative
adverb, an auxiliary form, or an ``-ed``-shaped token that is not a declared participle is
**undecidable** on closed surface evidence and is refused. Everything else is a bare
``NP``, which is row 2's own residual by row 2's own definition. This is what makes
``John is the CEO of Acme`` (bare NP, row 3) distinguishable from ``John is at Acme``
(a ``PP`` complement, which no row accepts).

**§19's open case, ``H6``, is recorded and never resolved.** ``is CEO of`` /
``became CEO of`` / ``was appointed CEO of`` produce three different outcomes and must
remain three: unifying ``be`` with ``become`` is a lexical-semantic claim §20 reserves to
explicit mapping, and unifying the agentless passive with the copular requires deciding
that the elided agent is the entity the surface puts in the complement, which is wrong in
general. So :data:`H6_STOP_CONDITION` is the named stop condition: the first two
realisations each yield their **own** signature, the third is **refused**, and every
reading in the family is recorded with code ``h6_open_case`` so the gap is a count rather
than a silence. No rule is invented here.

**Refusals are countable.** :func:`parse` returns readings *and* refusals, and
:class:`Refusal` carries a stable ``code`` and the ``stage`` that raised it. That is
brief §30's "no syntactic signals, never batch failure" made mechanical: a caller counts by
code and the batch continues. Every code in :class:`RefusalCode` is reachable from running
English; :data:`REFUSAL_REACHABILITY` says which and the tests assert each one.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from domain.mention_occurrence_index import mint_occurrence_address
from domain.predicate_signature import (
    AUX_LEMMA_INVENTORY,
    COPULA_LEMMA_INVENTORY,
    LEMMA_INVENTORY,
    LEMMA_TABLE,
    LEMMA_TABLE_DIGEST,
    VOICE_NORMALIZATION_VERSION,
    ArgumentMarker,
    ArgumentSlot,
    ConstructionFrame,
    ParticipantBinding,
    Polarity,
    PredicateSignature,
    ResolvedMention,
    RoleBinding,
    SignatureContractError,
    logical_candidate_id,
    morphological_forms_of,
    normalize_surface_for_fingerprint,
)
from domain.predicate_voice import (
    SHIPPED_LANGUAGES,
    ArgumentObservation,
    DependencyEdge,
    DependencyStructure,
    PredicateHead,
    SyntacticConstruction,
    SyntacticStructure,
    normalize_predicate,
)
from domain.relation_identity import canonical_material, digest128

# --------------------------------------------------------------------------- #
# The pinned capability (FR-043)
# --------------------------------------------------------------------------- #

#: What the model **is**. There is no downloaded checkpoint, and naming a rule set is
#: more honest than inventing a model id.
MODEL_REF: Final[str] = "interpretation.shallow.surface-rules"

#: The model version, bumped when the rule set's content changes in a way
#: :data:`CONFIGURATION_HASH` does not already pin. Kept separate from
#: :data:`PARSER_VERSION` so a rule-set change and a code change stay distinguishable in a
#: stored provenance record - the same distinction ``IDENTITY_SCHEMA_VERSION`` makes.
MODEL_VERSION: Final[str] = "1"

#: The parser's own version, bumped when this module's code changes.
PARSER_VERSION: Final[str] = "shallow-1"

#: The two gaps, as the limitations record states them. Quoted rather than paraphrased
#: where a source is being followed, so a reader can check the claim against
#: ``data-model.md`` and ``A2-identity-subsystem.md`` without trusting this module.
PARSER_LIMITATIONS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "temporal_complement": (
            "No source states the test that identifies a temporal complement, so this parser "
            "labels none. Every complement is RETAINED as a slot, V2.drop_temporal never "
            "fires from this producer, and 'John acquired Acme in 2020' keeps 'in 2020' as "
            "A1. Decided as 'undecidable', per brief input.md, and not resolved by a "
            "function-word list."
        ),
        "copular_versus_active": (
            "Decided from the complement's phrase category via PhraseCategory. A bare PP "
            "complement, a clausal complement and an AdvP complement are each refused with a "
            "named code, because no row of CONSTRUCTION_TABLE states a condition accepting "
            "them."
        ),
        "section_19_h6": (
            "'is CEO of' / 'became CEO of' / 'was appointed CEO of' are NOT unified. The first "
            "two yield distinct signatures; the third is refused as an agentless passive. "
            "Unification is available only through the mapping layer, by design (FR-004, "
            "section 20)."
        ),
        "copular_adjunct": (
            "A copular clause with a constituent after its complement is refused: rows 2 and "
            "3 carry exactly one complement, so a third argument would be dropped by the plan "
            "with no trace. 'John is CEO of Acme since 2019' therefore yields no reading."
        ),
        "reduced_relative": (
            "A relative clause with no overt subject of its own is refused with slot_gap. The "
            "matrix NP is not declared as the clause's subject, because that inference is true "
            "in the common case and false in the reduced and adjunct cases, and a rule that is "
            "usually right is a guess."
        ),
        "capitalisation": (
            "Capitalisation decides whether a token can start or continue a noun phrase, so a "
            "lower-case proper noun yields an unparseable sentence. A refusal, not a wrong "
            "reading, and the parser's largest honest weakness."
        ),
    }
)

#: §19's named stop condition, quoted from ``A2-identity-subsystem.md`` D6.3 H6 and
#: recorded on the reading rather than resolved. Kept as a module constant because a stop
#: condition that exists only in a docstring is not one a caller can cite.
H6_STOP_CONDITION: Final[str] = (
    "H6: section 19's three-way illustration is not unified by the identity layer; "
    "unification is available only through the mapping layer, by design (FR-004, section 20)."
)


class PhraseCategory(StrEnum):
    """The complement's phrase category - gap (b)'s decided half.

    A closed, pinned inventory, and the *only* thing this parser lets decide whether a
    clause is copular. A grammar inventory like ``AUX_LEMMA_INVENTORY``, not a lexicon:
    nothing here says what a word means, and nothing here can be extended by adding a word
    that means something.
    """

    NP = "np"
    PP = "pp"
    CP = "cp"
    ADV_P = "advp"
    UNDECIDABLE = "undecidable"


class RefusalStage(StrEnum):
    """Which layer refused, and therefore whether a signal was emitted for the clause.

    :attr:`Refusal.suppresses_signal` is *derived* from this rather than carried, so the
    answer to "did this refusal cost a signal" cannot disagree with the answer to "who
    refused".
    """

    #: The parser could not declare a construction, or declared nothing it can hand on.
    PARSE = "parse"
    #: ``normalize_predicate`` refused a declared reading. The parse itself was fine.
    NORMALIZE = "normalize"
    #: A reading was emitted and a *merge* was refused (section 19's ``H6``), or a mention
    #: binding was refused before a logical id could be computed.
    IDENTITY = "identity"


class RefusalCode(StrEnum):
    """Every reason this producer declines, as a stable countable code.

    Flat snake_case to match ``SignatureContractError``, and deliberately **overlapping**
    with that class's codes where the cause is the same condition - a reading the table
    cannot take is one gap whether the producer or the normaliser noticed - so a single
    histogram over producer and normaliser refusals answers "how much of this corpus has
    no structural reading" honestly.
    """

    #: Nothing to read: the input carried no clause at all.
    NO_CLAUSE = "no_clause"
    #: A sentence no construction rule matched. Not ``unsupported_construction``: the
    #: producer has no reading to hand the table, so the table is not what refused.
    UNCLASSIFIED_CONSTRUCTION = "unclassified_construction"
    #: A coordinating conjunction inside a clause. A named stop condition, not a gap to
    #: paper over with a sort: brief §29 lists no coordinated frame, and a coordinated
    #: frame without a declared symmetry marker would let the ordering invent a reading the
    #: structure does not license (A2 U5).
    COORDINATED_CLAUSE = "coordinated_clause"
    #: ``AUX`` + participle with no overt ``by``-agent. Deciding what an elided agent is
    #: would be a semantic inference, and an inference is a mapping.
    AGENTLESS_PASSIVE = "agentless_passive"
    #: The complement's phrase category is not determined by the closed surface evidence:
    #: a relative pronoun, a relative adverb, an auxiliary form, or an ``-ed``-shaped token
    #: that is not a declared participle. Genuinely undecidable, so genuinely refused.
    UNDECIDABLE_COMPLEMENT_CATEGORY = "undecidable_complement_category"
    #: The complement's phrase category *is* decided (``PP``, ``CP``, ``AdvP``) and no row
    #: of ``CONSTRUCTION_TABLE`` states a condition accepting it.
    UNSUPPORTED_COMPLEMENT_CATEGORY = "unsupported_complement_category"
    #: A declared reading the construction table cannot take, or a rule that consumed only
    #: part of the clause. Also the code ``normalize_predicate`` raises, for the same cause.
    UNSUPPORTED_CONSTRUCTION = "unsupported_construction"
    #: The morphology determines no lemma for the predicate head. A guessed lemma would be
    #: a silent merge - the exact defect N5 was removed to prevent.
    UNSUPPORTED_LEMMA = "unsupported_lemma"
    #: A language other than ``en`` ships. A cross-lingual pair is two readings, because
    #: merging them is a semantic claim.
    UNSUPPORTED_LANGUAGE = "unsupported_language"
    #: §19's three-way illustration, ``H6``. The unification was refused; a reading in the
    #: family is emitted with its own signature and recorded, or refused outright.
    H6_OPEN_CASE = "h6_open_case"
    #: The producer's argument-to-slot map disagrees with ``normalize_voice``. A guard, not
    #: an expectation: it means the two implementations of the documented V2 order have
    #: drifted, and the right answer is to emit nothing rather than a wrong logical id.
    SLOT_MAP_DISAGREES = "slot_map_disagrees_with_normalizer"
    #: A participant has no mention binding, so no ``logical_candidate_id`` can be computed.
    #: Fail-closed: a partially bound ordering is a silent identity fork.
    UNBOUND_PARTICIPANT = "unbound_participant"


#: Which of :class:`RefusalCode` a corpus of English prose actually reaches, and why. Read
#: by the tests, and by anyone deciding whether a code is a real gap or a hypothetical. Every
#: entry is asserted by a test; none is decorative.
REFUSAL_REACHABILITY: Final[Mapping[str, str]] = MappingProxyType(
    {
        RefusalCode.NO_CLAUSE: "a heading, a byline, a table row - text with no clause in it",
        RefusalCode.UNCLASSIFIED_CONSTRUCTION: (
            "a bare name in a list: 'Acme Holdings Limited' is an NP with no head, no "
            "genitive, no of-complement and no appositive, so no rule names it"
        ),
        RefusalCode.COORDINATED_CLAUSE: (
            "'John and Mary acquired Acme' - coordination in the subject position"
        ),
        RefusalCode.AGENTLESS_PASSIVE: (
            "'The report was published' - passive with no by-agent, and section 19's "
            "'John was appointed CEO of Acme'"
        ),
        RefusalCode.UNDECIDABLE_COMPLEMENT_CATEGORY: (
            "'John is elected' - the complement could be a passive participle or a "
            "predicative adjective and no closed surface evidence decides it"
        ),
        RefusalCode.UNSUPPORTED_COMPLEMENT_CATEGORY: (
            "'John is at Acme' (a bare PP complement) and 'John reported that Acme was sold' "
            "(a clausal complement)"
        ),
        RefusalCode.UNSUPPORTED_CONSTRUCTION: (
            "'Did John acquire the company?' is declared OTHER and reaches it; so is a "
            "clause carrying a constituent no row can take, such as 'John is CEO of Acme "
            "since 2019'"
        ),
        RefusalCode.UNSUPPORTED_LEMMA: (
            "'Globex manufactures widgets' - 'manufactures' is a form of no lemma the "
            "generated table holds, so the head is not decidable as a verb"
        ),
        RefusalCode.UNSUPPORTED_LANGUAGE: "any document whose declared language is not en",
        RefusalCode.H6_OPEN_CASE: (
            "section 19's 'is CEO of' / 'became CEO of' / 'was appointed CEO of'"
        ),
        RefusalCode.SLOT_MAP_DISAGREES: (
            "a guard rather than a corpus case: it fires only if the two implementations of "
            "the documented V2 order drift apart"
        ),
        RefusalCode.UNBOUND_PARTICIPANT: (
            "a caller that asks for a logical_candidate_id before the mention-binding stage "
            "has bound every participant of the reading"
        ),
    }
)


class ParserContractError(ValueError):
    """A refusal a caller asked for as an exception rather than as a record.

    Carries the same stable ``code`` as :class:`Refusal` and the same string shape as
    :class:`domain.predicate_signature.SignatureContractError`, so one caller can switch on
    any of them. :func:`parse` never raises it - it returns refusals - and it is raised only
    by the helpers that must *return* a value (:func:`assign_slots`,
    :func:`logical_candidate_id_of`), where returning ``None`` would be indistinguishable
    from a reading with no signature.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class Refusal:
    """One declined reading, with the code a caller counts by.

    :attr:`stage` is the load-bearing half: a :attr:`RefusalStage.PARSE` or
    :attr:`RefusalStage.NORMALIZE` refusal means **no signal was emitted for this clause**,
    and :attr:`suppresses_signal` derives that so the two cannot disagree. An
    :attr:`RefusalStage.IDENTITY` refusal is a refused *merge* - §19's ``H6`` - and the
    reading was emitted.
    """

    code: str
    stage: RefusalStage
    detail: str
    clause: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", str(self.code))
        object.__setattr__(self, "stage", RefusalStage(self.stage))
        object.__setattr__(self, "detail", str(self.detail))
        object.__setattr__(self, "clause", str(self.clause))

    @property
    def suppresses_signal(self) -> bool:
        """Whether this refusal cost a signal for its clause."""
        return self.stage in (RefusalStage.PARSE, RefusalStage.NORMALIZE)

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "stage": str(self.stage),
            "detail": self.detail,
            "clause": self.clause,
            "suppresses_signal": self.suppresses_signal,
        }


@dataclass(frozen=True, slots=True)
class DeclaredChannel:
    """What a non-sentence channel declares for a fragment, per ``CONSTRUCTION_TABLE`` row 9.

    Row 9's condition is "a PP with no ``nsubj`` whose governor is a document-structure
    producer slot", and its ``A1`` is "the subject the producing channel declares for the
    governing slot". A headless PP is therefore not readable from a sentence at all: it
    needs a declaration, and a declaration is a channel's job rather than a parser's. The
    shape of a real one is an attribute row whose key is the predicate and whose value is
    the phrase - a record slot reading ``Affiliation: at Acme``.

    Both fields default empty and both are honoured when present. A headless PP with no
    declaration reaches the table with one occupied slot and is refused there with
    ``slot_gap``, which is the honest answer: inventing the subject would be inventing a
    participant.
    """

    subject: str = ""
    head: str = ""
    label: str = ""


# --------------------------------------------------------------------------- #
# Pinned inventories
# --------------------------------------------------------------------------- #

#: Closed English function-word inventories. A **grammar** inventory, versioned inside
#: :data:`CONFIGURATION_HASH`, and not a semantic vocabulary: nothing here says what a word
#: means, and no two members are ever folded onto one another.
DETERMINERS: Final[frozenset[str]] = frozenset(
    {
        "the", "a", "an", "this", "these", "those", "each", "every", "some", "any",
        "no", "all", "both", "either", "neither", "another",
    }
)

#: ``that`` is a determiner here and *not* a subordinator. The cost is stated: "John said
#: that Acme was sold" therefore does not read as a clausal complement but as a
#: determiner-headed NP followed by a further constituent, which the leftover check
#: refuses anyway - a different code for the same sentence, and the one that keeps "John is
#: that person" readable.
DEMONSTRATIVE_DETERMINERS: Final[frozenset[str]] = frozenset({"that"})

POSSESSIVE_DETERMINERS: Final[frozenset[str]] = frozenset(
    {"his", "her", "their", "its", "our", "my", "your"}
)

#: Bare pronouns. An NP whose head is one of these carries no overt referent, so V2 consumes
#: it and the slot goes unoccupied - the design's point: slots are positions filled by
#: *overt* mentions, and a pronoun becomes a mention only after coreference, which is a
#: later stage this producer does not perform.
PRONOUNS: Final[frozenset[str]] = frozenset(
    {
        "i", "me", "my", "mine", "you", "your", "yours", "he", "him", "his", "she", "her",
        "hers", "it", "we", "us", "our", "ours", "they", "them", "theirs", "myself",
        "himself", "herself", "itself", "ourselves", "yourselves", "themselves", "one",
        "ones", "somebody", "someone", "something", "anybody", "anyone", "anything",
        "nobody", "nothing", "everyone", "everybody", "everything",
    }
)

RELATIVE_PRONOUNS: Final[frozenset[str]] = frozenset({"who", "whom", "which", "whose"})

RELATIVE_ADVERBS: Final[frozenset[str]] = frozenset({"where", "when", "why", "how"})

#: Subordinators. A complement introduced by one is a ``CP`` - a *decided* category and an
#: unsupported one, counted apart from the undecidable case.
SUBORDINATORS: Final[frozenset[str]] = frozenset(
    {
        "whether", "if", "because", "although", "though", "while", "whereas", "unless",
        "until", "since", "as",
    }
)

#: Negation adverbs and particles. A clause carrying one is **recorded as a denial**, not
#: refused, and the reason the refusal used to be here is the reason it is gone:
#: ``Polarity`` was a *candidate*-level datum (part 1.1) and the installed
#: ``RelationSignal`` had no polarity field, so emitting a denial would have put a false
#: assertion in the record. Phase 4A added
#: :attr:`~extractors.signals.signal.RelationSignal.polarity`, and Phase 4B reopened this
#: path, so ``John is not the CEO of Acme`` is now a reading whose polarity is
#: :attr:`~domain.predicate_signature.Polarity.DENIED` rather than a gap in the corpus.
#: Phase 4C then deleted :attr:`~extractors.signals.signal.SignalKind.NEGATION`, which had
#: been the kind-shaped way of saying the same thing, so the field above is now the **only**
#: place the denial is recorded (data-model 6.1, FR-011, FR-012).
#:
#: The inventory is unchanged, and that is deliberate: a negator is a closed English
#: function-word set, and a producer reading one more (or one fewer) would be a grammar
#: change with a different blast radius. What changed is that a *clause* carrying one is
#: read. A negator the parser does **not** understand still refuses, by
#: :data:`UNREAD_NEGATOR_CODE`, because "I did not find a negator" and "there is no negator
#: here" are different findings and only the second is a licence to assert.
NEGATORS: Final[frozenset[str]] = frozenset({"not", "never", "neither", "nor"})

#: The named refusal for a clause whose negation this parser cannot read. Reachable when a
#: negator-shaped word the inventory does not hold appears in operator position - ``John is
#: without Acme`` does not qualify, but a construction whose complement is a token ending
#: ``-n't`` does once the inventory is extended. The point of the code is that the parser
#: says *which* gap rather than reporting the clause as an assertion.
UNREAD_NEGATOR_CODE = "unread_negator"

COORDINATORS: Final[frozenset[str]] = frozenset({"and", "or"})

#: The syntactic preposition inventory, deliberately **wider** than
#: :class:`domain.predicate_signature.ArgumentMarker`. The gap is load-bearing: recognition
#: and canonical marking are different acts. "John works across Acme" is a well-formed
#: active clause, and the marker layer is the only place entitled to say that ``across`` is
#: not a canonical marker - which it refuses with ``unsupported_marker`` rather than
#: substituting ``NOMARK``. A parser whose preposition inventory *were* the marker inventory
#: could not distinguish "I do not recognise this word" from "I recognise it and decline to
#: normalise it", and those are different gaps.
SYNTAX_PREPOSITIONS: Final[frozenset[str]] = frozenset(
    {str(marker) for marker in ArgumentMarker if str(marker)}
    | {
        "across", "after", "against", "along", "among", "amongst", "around", "before",
        "behind", "below", "beneath", "beside", "besides", "beyond", "despite", "down",
        "during", "except", "inside", "near", "outside", "over", "past", "per", "through",
        "throughout", "toward", "towards", "under", "underneath", "until", "up", "upon",
        "via", "within", "without",
    }
)

#: Closed auxiliary, modal and perfect forms. A grammar inventory: whether a given surface is
#: finite, participial or neither is decided by morphology and this list, never by a guess
#: about the sentence's meaning.
CLAUSE_INITIAL_AUX: Final[frozenset[str]] = frozenset(
    {
        "do", "does", "did", "will", "would", "shall", "should", "can", "could", "may",
        "might", "must", "have", "has", "had", "is", "are", "am", "was", "were", "been",
        "being", "be",
    }
)

#: Auxiliary forms that may sit between the primary AUX and a passive's participle:
#: "is being reviewed", "was taken", "had been sold". Grammar forms, not a lexical rule.
PASSIVE_MIDDLES: Final[frozenset[str]] = frozenset({"being", "been", "get", "got"})

SENTENCE_TERMINATORS: Final[frozenset[str]] = frozenset({".", "!", "?", ";"})

#: The declared irregular English past participles, as ``surface -> lemma``.
#:
#: Generated where the regular ``-ed`` rule reaches, and pinned here where English does not
#: spell it that way. Restricted to surfaces the platform's generated lemma table actually
#: holds: ``taken``, ``seen``, ``written`` and their siblings are real participles and are
#: **absent** from ``PINNED_IRREGULAR_FORMS``, so declaring them here would make the parser
#: recognise a head whose lemma cannot be resolved - a capability that refuses one step
#: later for a reason that is really this list's. Not declaring them means the same sentence
#: is refused at recognition, with a code that says so. The closure grows with a rule and a
#: new digest, never by widening a test.
PINNED_PARTICIPLES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "been": "be",
        "bought": "buy",
        "built": "build",
        "got": "get",
        "held": "hold",
        "led": "lead",
        "made": "make",
        "met": "meet",
        "paid": "pay",
        "sent": "send",
        "sold": "sell",
        "told": "tell",
        "won": "win",
    }
)

#: The regular past-participle surfaces, generated from the same public morphology the
#: lemma table uses, so a lemma that gains a form gains its participle here too.
REGULAR_PARTICIPLES: Final[frozenset[str]] = frozenset(
    form
    for lemma in LEMMA_INVENTORY
    for form in morphological_forms_of(lemma)
    if form.endswith("ed")
)

#: The declared constructor sequence, in the exact order the dispatcher tries them. Named
#: because the order *is* the parser's tie-break: a surface that could satisfy two
#: constructors is resolved by which one is listed first, and that has to be a pinned,
#: reviewable fact rather than an accident of how the functions happen to be written down.
#:
#: ``passive`` covers **two** rows of the construction table - the one with an overt agent
#: and the agentless refusal - because the difference between them is not a different parse
#: but whether a participant was written down. ``unresolved_clause_shape`` declares nothing
#: and refuses; it is listed because its position in the order is what makes a
#: determiner-less clause shape distinguishable from an unclassifiable fragment.
CONSTRUCTOR_ORDER: Final[tuple[str, ...]] = (
    "clause_initial_auxiliary",
    "passive",
    "copular",
    "active_clause",
    "relative_clause",
    "genitive_np",
    "appositive_np",
    "headless_pp",
    "bare_nominal",
    "unresolved_clause_shape",
)

#: The constructors that *declare* a construction, as constructor name to construction.
#: Declared rather than derived by introspection so that a constructor which silently stopped
#: being reachable is a diff in this mapping.
DECLARABLE_CONSTRUCTIONS: Final[Mapping[str, SyntacticConstruction]] = MappingProxyType(
    {
        "clause_initial_auxiliary": SyntacticConstruction.OTHER,
        "passive": SyntacticConstruction.PASSIVE_WITH_AGENT,
        "copular": SyntacticConstruction.COPULAR,
        "active_clause": SyntacticConstruction.ACTIVE_CLAUSE,
        "relative_clause": SyntacticConstruction.RELATIVE_CLAUSE,
        "genitive_np": SyntacticConstruction.GENITIVE_NP,
        "appositive_np": SyntacticConstruction.APPOSITIVE_NP,
        "headless_pp": SyntacticConstruction.HEADLESS_PP,
        "bare_nominal": SyntacticConstruction.BARE_NOMINAL,
    }
)

#: The constructors that declare nothing and exist only to refuse. Listed separately so a
#: reader can see that a refusal-only rule is a rule, and so a test can assert the
#: partition is total over :data:`CONSTRUCTOR_ORDER`.
REFUSAL_ONLY_CONSTRUCTORS: Final[tuple[str, ...]] = ("unresolved_clause_shape",)

#: The constructors that declare a *clause* reading, and the observed passive frame. The
#: observed frame is evidence and never reaches a signature - ``normalize_voice`` demotes it
#: at V1, and re-declaring that here is what keeps an active and a passive realisation apart
#: on the signal while they meet on the identity.
OBSERVED_PASSIVE_FRAME: Final[ConstructionFrame] = ConstructionFrame.VERB_PASSIVE_AGENT

#: The pinned clause corpus, and the parse each surface must produce. A rule change that
#: moves any of these is a visible diff in :func:`fixture_digest` against a committed golden
#: value. Deliberately includes the surfaces the brief §29 names, including the two whose
#: head noun ("CEO") is outside the closed lemma inventory - so the corpus records the
#: refusals as fixtures rather than leaving them as folklore.
PINNED_CLAUSE_FIXTURES: Final[tuple[tuple[str, str, str], ...]] = (
    # (clause, declared construction or refusal code, expected rendered predicate or "")
    ("Company acquired Asset.", "active_clause", "acquire(A0:,A1:)"),
    ("Asset was acquired by Company.", "passive", "acquire(A0:,A1:)"),
    ("John is the CEO of Acme.", "copular", "be(A0:,A1:of)"),
    ("John became CEO of Acme.", "copular", "become(A0:,A1:of)"),
    ("John works at Acme.", "active_clause", "work(A0:,A1:at)"),
    ("John, CEO of Acme", "unsupported_lemma", ""),
    ("John Smith, CEO of Acme", "unsupported_lemma", ""),
    ("Acme's founder John Smith", "genitive_np", "found(A0:,A1:)"),
    ("owner of Acme from Globex", "bare_nominal", "own(A0:,A1:of)"),
    (
        "The report, which the committee wrote, was sent by Acme.",
        "relative_clause",
        "write(A0:,A1:)",
    ),
    ("John is at Acme.", "unsupported_complement_category", ""),
    ("John is elected.", "undecidable_complement_category", ""),
    ("John and Mary acquired Acme.", "coordinated_clause", ""),
    ("The asset was sold.", "agentless_passive", ""),
    ("Did John acquire the company?", "unsupported_construction", ""),
    ("Acme Holdings Limited", "unclassified_construction", ""),
)


# --------------------------------------------------------------------------- #
# Tokenisation
# --------------------------------------------------------------------------- #

#: One word, one punctuation mark. The grouped-number alternative comes **first** because
#: alternation is ordered: a plain word alternative would match the leading ``1`` of
#: ``1,200.50`` and the decimal would split a sentence at its thousands separator.
_TOKEN = re.compile(r"\d+(?:[.,]\d+)+|[^\W_]+(?:['’\-][^\W_]+)*|[^\w\s]", re.UNICODE)

#: A trailing genitive ``'s``, split off its stem so ``Acme's`` is two tokens. The cost is
#: stated rather than hidden: ``it's`` splits too. The parser refuses ``it's`` on other
#: grounds, so the imprecision is unreachable in any reading it accepts.
_GENITIVE = re.compile(r"^(?P<stem>[^\W_]+)['’]s$", re.UNICODE)


def tokenise(text: str) -> tuple[str, ...]:
    """The clause's tokens, in document order, with genitive markers split off.

    Order is load-bearing downstream: ``DependencyStructure.edges`` is built from it and
    V2's ``TB2`` tie-break reads the edge position, so a tokeniser that emitted a different
    order would produce a different signature for the same sentence.
    """
    out: list[str] = []
    for match in _TOKEN.finditer(text):
        token = match.group(0)
        genitive = _GENITIVE.match(token)
        if genitive is not None:
            out.append(genitive.group("stem"))
            out.append("'s")
        else:
            out.append(token)
    return tuple(out)


def _is_punct(token: str) -> bool:
    return not any(character.isalnum() for character in token)


def _is_genitive(token: str) -> bool:
    return token == "'s"


def _is_coord(token: str) -> bool:
    return token.casefold() in COORDINATORS


def _is_relative_pronoun(token: str) -> bool:
    return token.casefold() in RELATIVE_PRONOUNS


def _is_aux(token: str) -> bool:
    folded = token.casefold()
    return folded in CLAUSE_INITIAL_AUX or folded in PASSIVE_MIDDLES


def _is_participle(token: str) -> bool:
    folded = token.casefold()
    return folded in PINNED_PARTICIPLES or folded in REGULAR_PARTICIPLES


def _is_preposition(token: str) -> bool:
    return token.casefold() in SYNTAX_PREPOSITIONS


def _is_determiner(token: str) -> bool:
    folded = token.casefold()
    return (
        folded in DETERMINERS
        or folded in DEMONSTRATIVE_DETERMINERS
        or folded in POSSESSIVE_DETERMINERS
    )


def _is_pronominal(token: str) -> bool:
    return token.casefold() in PRONOUNS


def _looks_like_negator(token: str) -> bool:
    """Whether a token is shaped like a negator the closed inventory does not hold.

    A **guard**, and the narrowest one the parser has: it fires on a contraction's
    ``-n't`` and on nothing else, and its whole purpose is that a word this parser cannot
    read as a negation must not be read as an assertion. Every other unread word is a
    different failure - an unread noun phrase is a missing participant, an unread
    preposition is an unsupported marker - and neither of those turns a denial into an
    assertion, which is what a missed negator does.

    Kept to the ``-n't`` shape rather than a synonym list on purpose. ``unable``,
    ``without`` and ``fails to`` all deny, and this parser reads none of them; widening the
    test to catch them would be a claim about three more constructions that no row of
    :data:`CONSTRUCTION_TABLE` supports. The code it raises,
    :data:`UNREAD_NEGATOR_CODE`, names the gap so the inventory can be extended on purpose.
    """
    return token.casefold().endswith("n't")


def _is_np_start(token: str) -> bool:
    """Whether a token can *begin* a noun phrase.

    Capitalisation, a closed determiner, or a closed pronoun. Capitalisation is the parser's
    largest honest weakness and it is worth naming here: a lower-case proper noun - a
    heading set in small caps by a CSS ``text-transform``, a stylised brand - yields an
    unparseable sentence, which is a refusal rather than a wrong reading.
    """
    if _is_determiner(token) or _is_pronominal(token):
        return True
    if _is_punct(token) or _is_genitive(token) or _is_coord(token):
        return False
    return token[:1].isupper() or token[:1].isdigit()


def _continues_np(token: str) -> bool:
    """Whether a token can *continue* a noun phrase already under way.

    Capitalised, and not a function word, a coordinator, a genitive, a participle or
    punctuation. So ``John Smith`` and ``Acme Holdings`` are one NP each, while
    ``John acquired`` and ``Acme at`` are not.

    The past-participle exclusion is load-bearing rather than cosmetic: without it
    ``Acme acquired`` would read as one NP and the clause would have no head.
    """
    if _is_punct(token) or _is_genitive(token) or _is_coord(token) or _is_participle(token):
        return False
    if _is_determiner(token) or _is_relative_pronoun(token) or _is_preposition(token):
        return False
    if _is_verb_form(token):
        return False
    return token[:1].isupper() or token[:1].isdigit()


#: Nominal derivation suffixes, as a *shape* rule. The one place this parser decides a
#: question about morphology by spelling rather than by consulting a table, and it is a
#: deliberate choice with a stated reason: the question is only ever "does this token end an
#: NP or stop one", so a suffix list is the whole of the decision, and re-implementing the
#: lemma table's inflection rules to answer it would be a second answer to "what are the
#: finite forms of 'acquire'".
#:
#: ``-ee`` is deliberately **absent**, because ``see`` is an inventory lemma and excluding it
#: would make a verb unreadable as a head. The cost is the other direction and it is the
#: cheap one: ``employee`` and ``payee`` are real derivations the rule does not recognise, so
#: they read as verb forms, which only ever makes the parser stop an NP or claim a head
#: earlier. That direction produces refusals; the other direction would produce merges.
#: ``test_no_inventory_lemma_is_hidden_by_a_nominal_suffix`` is what keeps the first claim
#: true, and the second is argued here because it cannot be asserted.
NOMINAL_SUFFIXES: Final[tuple[str, ...]] = ("er", "ing", "ation", "ion", "ment", "or")


def _is_verb_form(token: str) -> bool:
    """Whether a surface is a *finite* form of a lemma the generated table holds.

    Derived from :data:`~domain.predicate_signature.LEMMA_TABLE`, so a lemma added to the
    inventory becomes a possible head without touching this module, and narrowed by
    :data:`NOMINAL_SUFFIXES` so ``acquisition`` and ``founder`` are nouns. A token that is
    neither is not a head, and the parser refuses rather than assuming.
    """
    folded = token.casefold()
    if LEMMA_TABLE.get(folded) is None:
        return False
    return not folded.endswith(NOMINAL_SUFFIXES)


def _is_copula_form(token: str) -> bool:
    """Whether a surface resolves to a lemma in the closed COPULA inventory.

    Resolved through ``LEMMA_TABLE`` rather than through the auxiliary list: "has" and
    "will" are auxiliary forms but are not copulas, and reading "John has Acme" as a
    copular clause would put a ``be``-relation where the sentence has a perfect.
    """
    return LEMMA_TABLE.get(token.casefold()) in COPULA_LEMMA_INVENTORY


def _lemma_of(token: str) -> str | None:
    """The lemma for a surface, or ``None`` when the morphology does not determine one.

    Delegates to the generated table rather than re-deriving it. ``None`` is a real answer
    and not an error: the caller decides whether an unresolvable head is a refusal, and the
    one place it is not a refusal is the *participant* head token, which travels as the
    token as tokenised and is never lemmatised at all.
    """
    folded = normalize_surface_for_fingerprint(token)
    if not folded:
        return None
    return LEMMA_TABLE.get(folded)


# --------------------------------------------------------------------------- #
# Scanning noun phrases and prepositional phrases
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class _Span:
    """A token range, inclusive of ``start`` and exclusive of ``end``."""

    start: int
    end: int

    def surface(self, tokens: Sequence[str]) -> str:
        return " ".join(tokens[self.start : self.end])


def _scan_np(tokens: Sequence[str], index: int) -> _Span | None:
    """The noun phrase beginning at ``index``, or ``None``.

    Three steps, in order: a run of determiners; one **unconditional** head token; then a
    run of continuing tokens, each of which may itself be followed by a genitive and its own
    head. The unconditional head is what makes "the red team" one NP when "red" is a
    determiner-less, lower-case, non-verbal token the parser has no lexicon for.

    Returns ``None`` rather than an empty span so "there is no NP here" is representable
    without a sentinel index.
    """
    length = len(tokens)
    cursor = index
    determiner_run = 0
    while cursor < length and _is_determiner(tokens[cursor]):
        cursor += 1
        determiner_run += 1
    if cursor >= length:
        return None
    head = tokens[cursor]
    if _is_punct(head) or _is_genitive(head) or _is_coord(head) or _is_preposition(head):
        return None
    # After a determiner the head is accepted **unconditionally**: the parser has no lexicon
    # and cannot tell "the red team" from "the run", and "the" alone is not a noun phrase. A
    # determiner-less constituent must start NP-like, which is what keeps a stray lowercase
    # word out of the object position.
    if determiner_run == 0 and not _is_pronominal(head) and not _is_np_start(head):
        return None
    cursor += 1
    while cursor < length and _continues_np(tokens[cursor]):
        cursor += 1
        if cursor < length and _is_genitive(tokens[cursor]):
            cursor += 1
            if cursor < length and not _is_punct(tokens[cursor]):
                cursor += 1
    return _Span(index, cursor)


def _scan_np_loose(tokens: Sequence[str], index: int) -> _Span | None:
    """A noun phrase for a **prepositional** object, which may be a bare numeral.

    "in 2020" has an object no closed NP test accepts, because a four-digit year is neither
    capitalised nor a closed function word. A PP must have an object, so the PP scanner is
    permitted to take a run of tokens where the NP scanner refuses; the NP scanner stays
    strict so a stray numeral cannot become a participant of its own accord.
    """
    length = len(tokens)
    if index >= length:
        return None
    cursor = index
    while cursor < length and _is_determiner(tokens[cursor]):
        cursor += 1
    if cursor >= length:
        return None
    cursor += 1
    while cursor < length and _continues_np(tokens[cursor]):
        cursor += 1
        if cursor < length and _is_genitive(tokens[cursor]):
            cursor += 1
            if cursor < length and not _is_punct(tokens[cursor]):
                cursor += 1
    return _Span(index, cursor)


def _scan_pp(tokens: Sequence[str], index: int) -> _Span | None:
    """The prepositional phrase beginning at ``index``, marker included, or ``None``."""
    if index >= len(tokens) or not _is_preposition(tokens[index]):
        return None
    object_span = _scan_np_loose(tokens, index + 1)
    if object_span is None:
        return None
    return _Span(index, object_span.end)


# --------------------------------------------------------------------------- #
# The reading the parser hands over
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ParsedArgument:
    """One argument as the parser observed it, with the surfaces a caller needs.

    :attr:`mention_ref` is a **deferred participant reference**, not a minted mention id.
    brief §25 forbids a producer inventing a mention identity from text, and §26 says the
    alternative is exactly this: record the structural raw slot and let an explicit
    mention-binding stage resolve it. The default form is derived from the position label
    and the normalised surface, so two producers reading one structure address the same
    thing; a channel that has real mention records passes them in.
    """

    position_label: str
    surface: str
    head_token: str
    mention_ref: str
    function_word: str | None = None
    pronominal: bool = False
    token_start: int = 0
    token_end: int = 0

    @property
    def normalized_surface(self) -> str:
        return normalize_surface_for_fingerprint(self.surface)

    def to_observation(self) -> ArgumentObservation:
        """The :class:`ArgumentObservation` ``normalize_voice`` consumes.

        :attr:`head_lemma_hint` is the head token **as tokenised** - V3 lemmatises the
        predicate head and nothing else, so lemmatising a participant here would be an
        undeclared normalisation.
        """
        return ArgumentObservation(
            position_label=self.position_label,
            head_lemma_hint=self.head_token,
            function_word=self.function_word,
            is_pronominal=self.pronominal,
        )


@dataclass(frozen=True, slots=True)
class SyntacticReading:
    """One declared reading of one clause, and the signature it normalises to.

    The signature is built by ``normalize_predicate``, never here, and the observed frame
    travels beside it as evidence: :attr:`observed_construction_frame` is what the surface
    showed and :attr:`signature` is what the identity layer may key on, and for the passive
    those are two different frames on purpose.
    """

    clause: str
    construction: SyntacticConstruction
    predicate: PredicateHead
    syntactic_structure: SyntacticStructure
    dependency_structure: DependencyStructure
    arguments: tuple[ParsedArgument, ...]
    signature: PredicateSignature
    constructor: str
    predicate_surface: str
    predicate_span: str
    observed_construction_frame: ConstructionFrame
    head_function_word: str | None = None
    channel_label: str = ""
    #: Whether this reading stands or is **denied**. Phase 4B: the field exists because
    #: ``RelationSignal.polarity`` exists (Phase 4A), so a negated clause no longer has to be
    #: refused - and a reading is the right place for it, because "John is not the CEO of
    #: Acme" and "John is the CEO of Acme" are **one frame and two polarities**, which is
    #: what ``Polarity`` on a signature would have got wrong by making one predicate two
    #: (part 1.1). Asserted rather than derived: a constructor that saw no negator says so.
    polarity: Polarity = Polarity.ASSERTED

    @property
    def rendered_predicate(self) -> str:
        return self.signature.rendered_predicate()

    @property
    def participants(self) -> tuple[ParsedArgument, ...]:
        """The arguments that occupy a canonical slot, in slot order.

        Pronominal arguments are excluded because V2 consumes them, so a pronoun is not a
        participant of the reading - it is a gap the mention-binding stage may yet fill.
        """
        return tuple(argument for argument in self.arguments if not argument.pronominal)

    def to_dict(self) -> dict[str, object]:
        return {
            "clause": self.clause,
            "construction": str(self.construction),
            "constructor": self.constructor,
            "predicate_surface": self.predicate_surface,
            "predicate_span": self.predicate_span,
            "head_function_word": self.head_function_word or "",
            "observed_construction_frame": str(self.observed_construction_frame),
            "polarity": str(self.polarity),
            "predicate_signature": self.signature.to_dict(),
            "channel_label": self.channel_label,
            "arguments": [
                {
                    "position_label": argument.position_label,
                    "surface": argument.surface,
                    "head_token": argument.head_token,
                    "mention_ref": argument.mention_ref,
                    "function_word": argument.function_word or "",
                    "pronominal": argument.pronominal,
                }
                for argument in self.arguments
            ],
        }


@dataclass(frozen=True, slots=True)
class SlotBinding:
    """One argument bound to the canonical slot it fills.

    Derived by the producer, and **checked against** ``normalize_voice`` by
    :func:`assign_slots` rather than trusted. The check is the mechanism: a
    :class:`~domain.predicate_voice.CanonicalArgumentAssignment` carries slots and markers
    but not the arguments that filled them, so a producer needs its own map - and the only
    honest way to have one is to derive it and then let the authority say whether it agrees.
    """

    argument: ParsedArgument
    slot: ArgumentSlot
    marker: ArgumentMarker


# --------------------------------------------------------------------------- #
# Sentence segmentation
# --------------------------------------------------------------------------- #


def _sentences(tokens: Sequence[str]) -> tuple[tuple[int, tuple[str, ...]], ...]:
    """``(start offset in the token stream, tokens)`` per sentence, in document order.

    The offset travels so a reading can be located in the original text, and the split is
    on the pinned terminator set - a total order over tokens, so the segmentation is a
    function of the text alone.
    """
    out: list[tuple[int, tuple[str, ...]]] = []
    start = 0
    for index, token in enumerate(tokens):
        if token in SENTENCE_TERMINATORS:
            chunk = tuple(tokens[start:index])
            if chunk:
                out.append((start, chunk))
            start = index + 1
    tail = tuple(tokens[start:])
    if tail:
        out.append((start, tail))
    return tuple(out)


def _leading_advunct_prefix(tokens: Sequence[str]) -> int:
    """Index at which the subject region begins, after any comma-delimited PP adjunct.

    "In March, Acme acquired Beta" is a perfectly ordinary clause whose adjunct precedes the
    subject. A parser that treated the adjunct as the subject would place the head wrongly,
    and one that treated it as an argument would invent a slot the predicate does not have -
    so the adjunct is dropped from the *subject search* and reported nowhere, which is a
    stated loss rather than a silent one.
    """
    if not tokens:
        return 0
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token == ",":
            segments.append([])
        else:
            segments[-1].append(token)
    offset = 0
    for segment in segments[:-1]:
        if segment and _is_preposition(segment[0]):
            offset += len(segment) + 1
            continue
        break
    return min(offset, len(tokens))


# --------------------------------------------------------------------------- #
# Reading assembly
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class _Attempt:
    """What a constructor produced, before the authority was asked to judge it.

    ``arguments`` is in document order, because ``DependencyStructure.edges`` must be and
    V2's ``TB2`` tie-break reads edge position. ``head_index`` is the token index of the
    predicate head and ``head_aux_index`` the index of its auxiliary when it has one, so
    the observed predicate span can be reported from the head outward.
    """

    constructor: str
    construction: SyntacticConstruction
    head_surface: str
    arguments: tuple[ParsedArgument, ...]
    head_index: int
    head_aux_index: int | None = None
    extra_refusals: tuple[Refusal, ...] = ()
    #: Stated by the constructor that saw a negator, and carried unchanged into
    #: :class:`SyntacticReading`. Added with the negator path in Phase 4B, and defaulted
    #: ``ASSERTED`` so every constructor that never looks for one is untouched by the change.
    polarity: Polarity = Polarity.ASSERTED


@dataclass(frozen=True, slots=True)
class _Outcome:
    """A constructor's answer: *not mine*, *mine and declared*, or *mine and refused*.

    The three are distinct and the distinction is the whole of brief §30's rule. A
    constructor that has **claimed** a surface answers, so a refusal is never retried as
    the next constructor: ``John is at Acme`` is refused as an unsupported complement
    category and is not re-read as an active clause, which is what "declare the
    construction; never guess it" requires in code rather than in a comment.
    """

    claimed: bool = False
    attempt: _Attempt | None = None
    refusals: tuple[Refusal, ...] = ()

    @classmethod
    def pass_through(cls) -> _Outcome:
        return cls()

    @classmethod
    def declare(cls, attempt: _Attempt) -> _Outcome:
        return cls(claimed=True, attempt=attempt)

    @classmethod
    def refuse(cls, *refusals: Refusal) -> _Outcome:
        return cls(claimed=True, refusals=tuple(refusals))


def _argument(
    label: str,
    span: _Span,
    tokens: Sequence[str],
    *,
    function_word: str | None = None,
    pronominal: bool | None = None,
    token_offset: int = 0,
) -> ParsedArgument:
    """One argument observation, addressed by position label and normalised surface.

    ``token_offset`` shifts the recorded token indices into a different token sequence than
    ``tokens``' own. It is needed exactly once - the subject a :class:`DeclaredChannel`
    declares for a headless PP, which was tokenised separately from the phrase it governs.

    **The address is written by the one minter, and the label goes in whole.** This used to build
    ``f"surface:{label}:{address}"`` here, and the labels are dependency arcs - several of which
    contain the separator (``nmod:of``, ``nsubj:pass``) - so ``surface:nmod:of:acme`` was minted and
    the grammar read it back as label ``nmod`` and surface ``of:acme``: a *different address from
    the one this line meant*, and one the mention index cannot find. Two inputs, one output is a
    non-injective encoding, and no amount of care about which separator is "less likely" removes
    the class. So the string is not written here at all: it comes from
    :func:`domain.mention_occurrence_index.mint_occurrence_address`, whose payload is
    self-delimiting, so a label may hold ``:``, ``|``, ``@``, a newline, a non-ASCII letter or
    nothing at all and is read back as itself.

    The address states the **normalised** surface, which is the string
    :meth:`ParsedArgument.normalized_surface` returns and the one the mint key digests, so the
    address and the key cannot disagree about what was read here. The unpositioned form is
    deliberate and is not a gap: these positions are clause-relative token indices rather than
    character offsets in a segment, so there is no character span to state, and stating a token
    index as if it were a character offset would be inventing a position.
    """
    surface = span.surface(tokens)
    head = tokens[span.end - 1]
    is_pronominal = _is_pronominal(head) if pronominal is None else pronominal
    address = normalize_surface_for_fingerprint(surface)
    return ParsedArgument(
        position_label=label,
        surface=surface,
        head_token=head,
        mention_ref=mint_occurrence_address(label=label, surface=address),
        function_word=function_word,
        pronominal=is_pronominal,
        token_start=span.start + token_offset,
        token_end=span.end + token_offset,
    )


def _pronominal_argument(
    label: str, surface: str, *, position: int
) -> ParsedArgument:
    """An argument the surface supplies only as a reference: a pronoun, a relative pronoun.

    Declared ``pronominal`` so V2 **consumes** it. A pronoun is not a mention until
    coreference has run, so a slot filled by one has no overt participant in it, and the
    honest outcome is an unoccupied slot - refused at ``slot_gap`` when the position is a
    required one, rather than numbered with a referent this producer cannot see.

    Addressed through the one minter, like every other argument here, so this is not a second
    way to build the string.
    """
    address = normalize_surface_for_fingerprint(surface)
    return ParsedArgument(
        position_label=label,
        surface=surface,
        head_token=surface,
        mention_ref=mint_occurrence_address(label=label, surface=address),
        pronominal=True,
        token_start=position,
        token_end=position + 1,
    )


def _finish(
    attempt: _Attempt,
    clause: str,
    tokens: Sequence[str],
    *,
    language: str,
    channel: DeclaredChannel,
) -> tuple[SyntacticReading | None, tuple[Refusal, ...]]:
    """Hand a declared reading to ``normalize_predicate`` and, if it survives, return it.

    The single point where a declared construction meets the authority. Everything before
    here is the parser's declaration; everything after is the normaliser's judgement. A
    refusal from either reaches the caller as a refusal - one code space, one batch, no
    exception - which is what makes ``unsupported_construction`` countable rather than
    merely described.
    """
    observations = tuple(argument.to_observation() for argument in attempt.arguments)
    auxiliary = (
        tokens[attempt.head_aux_index] if attempt.head_aux_index is not None else None
    )
    structure = SyntacticStructure(
        construction=attempt.construction,
        arguments=observations,
        head_function_word=auxiliary,
    )
    edges = tuple(
        DependencyEdge("root", f"arg{index}", argument.position_label)
        for index, argument in enumerate(attempt.arguments)
    )
    root = attempt.arguments[0].position_label if attempt.arguments else "root"
    dependencies = DependencyStructure(edges=edges, root=root)
    predicate = PredicateHead(observed_form=attempt.head_surface, language=language)
    try:
        signature = normalize_predicate(predicate, structure, dependencies)
    except SignatureContractError as error:
        return None, (
            Refusal(
                code=error.code,
                stage=RefusalStage.NORMALIZE,
                detail=error.message,
                clause=clause,
            ),
            *attempt.extra_refusals,
        )
    observed = (
        OBSERVED_PASSIVE_FRAME
        if attempt.construction is SyntacticConstruction.PASSIVE_WITH_AGENT
        else signature.construction_frame
    )
    reading = SyntacticReading(
        clause=clause,
        construction=attempt.construction,
        predicate=predicate,
        syntactic_structure=structure,
        dependency_structure=dependencies,
        arguments=attempt.arguments,
        signature=signature,
        constructor=attempt.constructor,
        predicate_surface=attempt.head_surface,
        predicate_span=_predicate_span(tokens, attempt),
        observed_construction_frame=observed,
        head_function_word=auxiliary,
        channel_label=channel.label,
        polarity=attempt.polarity,
    )
    return reading, attempt.extra_refusals


def _predicate_span(tokens: Sequence[str], attempt: _Attempt) -> str:
    """The clause's own predicate words: from the head (or its AUX) to the last argument.

    This is the observed relation surface a signal carries. For the active and the passive
    realisation of one reading these differ - "acquired Asset" against
    "was acquired by Company" - which is exactly §18's requirement that two realisations
    remain two surface observations while meeting on one signature. A reading with nothing
    after the head reports the head word alone, which is honest: there was nothing else in
    the clause's predicate.
    """
    start = attempt.head_index
    if attempt.head_aux_index is not None:
        start = min(start, attempt.head_aux_index)
    end = start + 1
    for argument in attempt.arguments:
        if argument.token_start >= start:
            end = max(end, argument.token_end)
    return " ".join(tokens[start:end])


# --------------------------------------------------------------------------- #
# Head finding
# --------------------------------------------------------------------------- #


def _subject_prefix(tokens: Sequence[str], head_index: int) -> _Span | None:
    """The subject region before ``head_index``, as a span, or ``None``.

    Leading comma-delimited PP adjuncts are dropped (see :func:`_leading_advunct_prefix`),
    and the region must then hold at least one non-determiner token, contain no comma, and end
    on something that can carry a subject. Every one of those conditions is load-bearing:
    without the first, "The report" would make ``report`` a head; without the second, "The"
    alone would not; and without the third, "John , who founded Acme" would read as an active
    clause whose subject was "John , who".
    """
    offset = _leading_advunct_prefix(tokens[:head_index])
    region = list(tokens[offset:head_index])
    while region and region[-1] == ",":
        region.pop()
    if not region or "," in region:
        return None
    if all(_is_determiner(token) for token in region):
        return None
    tail = region[-1]
    if (
        _is_preposition(tail)
        or _is_punct(tail)
        or _is_coord(tail)
        or _is_relative_pronoun(tail)
        or _is_genitive(tail)
    ):
        # A subject region must end on a **head**, not on a function word. The relative
        # pronoun case is the one that matters: "John who founded Acme" has no bracket, and
        # without this the parser would read it as a main clause whose subject was
        # "John who" - the relative clause silently promoted, which is exactly what row 10
        # exists to stop.
        return None
    return _Span(offset, head_index)


def _head_candidate(token: str) -> bool:
    return _is_copula_form(token) or _is_verb_form(token) or _is_aux(token)


def _find_head(tokens: Sequence[str], *, inclusive_start: bool = False) -> int | None:
    """The token index of the predicate head, or ``None``.

    The first token that is a copula, an auxiliary or a finite verb form and that has a
    subject region before it. "First" is a total order over positions, so the answer is a
    function of the tokens and never of how the scan was written down.

    ``inclusive_start`` lets index 0 be a head, which a **relative** clause needs:
    "which the committee wrote" has its verb at the start because the relative pronoun
    already filled the subject.
    """
    start = 0 if inclusive_start else 1
    for index in range(start, len(tokens)):
        if not _head_candidate(tokens[index]):
            continue
        if index == 0:
            # A relative clause's head can sit at index 0 with an implicit subject, because
            # the relative pronoun already filled it: "which the committee wrote" puts the
            # verb after its subject, "who founded Acme" before one.
            if _is_verb_form(tokens[0]):
                return 0
            continue
        if _subject_prefix(tokens, index) is not None:
            return index
    return None


def _passive_participle_index(tokens: Sequence[str], head_index: int) -> int | None:
    """The participle index of a passive headed at ``head_index``, or ``None``.

    ``AUX`` then, optionally, a middle auxiliary, then a participle: "was acquired",
    "is being reviewed". The middle is skipped rather than required, so a participle
    straight after an AUX is still a participle - the whole of the passive pattern, and not
    a lexical rule.
    """
    cursor = head_index + 1
    if cursor < len(tokens) and tokens[cursor].casefold() in PASSIVE_MIDDLES:
        cursor += 1
    if cursor < len(tokens) and _is_participle(tokens[cursor]):
        return cursor
    return None


def _by_agent_index(tokens: Sequence[str], participle_index: int) -> int | None:
    """The index of the ``by``-PP after a passive participle, or ``None``.

    The *first* ``by``-PP at or after the participle, which is a total order rather than a
    preference: "was sold by Acme to Globex" has one agent and one recipient, and taking
    the first ``by`` is the only reading that does not depend on how many there are.
    """
    for index in range(participle_index, len(tokens)):
        if tokens[index].casefold() == "by":
            return index if index + 1 < len(tokens) else None
    return None


def _object_span(tokens: Sequence[str], index: int) -> _Span | None:
    """A bare noun phrase at ``index``, or ``None`` - which includes "a PP starts here"."""
    if index >= len(tokens) or _is_preposition(tokens[index]) or tokens[index] == ",":
        return None
    return _scan_np(tokens, index)


def _pp_arguments(
    tokens: Sequence[str], index: int
) -> tuple[tuple[tuple[ParsedArgument, int], ...], int]:
    """Every prepositional phrase from ``index`` onward: ``(argument, next index)`` pairs.

    The whole complement region of an active or passive clause. A **bare** noun phrase in
    that region is not consumed: an unmarked second object is either a compound the parser
    cannot split or a coordination, and reporting it as a slot would invent a participant,
    so the leftover check refuses instead.
    """
    found: list[tuple[ParsedArgument, int]] = []
    cursor = index
    while cursor < len(tokens):
        if tokens[cursor] == ",":
            cursor += 1
            continue
        if not _is_preposition(tokens[cursor]):
            break
        span = _scan_pp(tokens, cursor)
        if span is None:
            break
        marker = tokens[cursor].casefold()
        found.append(
            (
                _argument(
                    f"nmod:{marker}",
                    _Span(cursor + 1, span.end),
                    tokens,
                    function_word=marker,
                ),
                span.end,
            )
        )
        cursor = span.end
    return tuple(found), cursor


def _leftover(tokens: Sequence[str], start: int, end: int, what: str) -> tuple[Refusal, ...]:
    consumed = " ".join(tokens[start:end])
    return (
        Refusal(
            code=RefusalCode.UNSUPPORTED_CONSTRUCTION,
            stage=RefusalStage.PARSE,
            detail=(
                f"the clause has {what} - {consumed!r} - and no row of the construction "
                "table states a condition carrying it. Consuming the clause and dropping "
                "the extra would be a lost participant with no trace, so the reading is "
                "refused instead"
            ),
            clause=" ".join(tokens),
        ),
    )


# --------------------------------------------------------------------------- #
# Constructor 1: an inverted or modal clause
# --------------------------------------------------------------------------- #


def _c_clause_initial_auxiliary(
    tokens: Sequence[str], head_index: int, channel: DeclaredChannel
) -> _Outcome:
    """A clause whose first token is an auxiliary or a modal: a question, or a modal clause.

    Declared ``OTHER``, which is :class:`SyntacticConstruction`'s honest "I could not
    classify this" and has no canonical frame, so ``normalize_predicate`` refuses it with
    ``unsupported_construction``. That is the right answer rather than a coverage gap: an
    interrogative's subject is *after* the auxiliary, so the subject-then-verb shape every
    other constructor relies on is absent, and reading one anyway would be reading a
    different sentence.
    """
    del head_index, channel
    if not tokens or tokens[0].casefold() not in CLAUSE_INITIAL_AUX:
        return _Outcome.pass_through()
    return _Outcome.declare(
        _Attempt(
            constructor="clause_initial_auxiliary",
            construction=SyntacticConstruction.OTHER,
            head_surface=tokens[0],
            arguments=(_argument("nsubj", _Span(0, 1), tokens),),
            head_index=0,
        )
    )


# --------------------------------------------------------------------------- #
# Constructors 2 and 3: passives
# --------------------------------------------------------------------------- #


def _c_passive(tokens: Sequence[str], head_index: int, channel: DeclaredChannel) -> _Outcome:
    """``NP`` + ``AUX`` + participle, with or without an overt ``by``-agent.

    One constructor for both rows, because the difference is not a different parse: it is
    whether an agent was written down. The one with an agent is row 1 and is demoted to
    ``VERB_ACTIVE_TRANSITIVE`` at V1 - the single unification in the platform. The one
    without is ``agentless_passive``: deciding what an elided agent is would be a semantic
    inference, and an inference is a mapping.
    """
    del channel
    participle_index = _passive_participle_index(tokens, head_index)
    if participle_index is None:
        return _Outcome.pass_through()
    if _lemma_of(tokens[head_index]) not in (AUX_LEMMA_INVENTORY | COPULA_LEMMA_INVENTORY):
        return _Outcome.pass_through()
    subject = _subject_prefix(tokens, head_index)
    if subject is None:
        return _Outcome.pass_through()
    by_index = _by_agent_index(tokens, participle_index)
    if by_index is None:
        return _Outcome.refuse(
            Refusal(
                code=RefusalCode.AGENTLESS_PASSIVE,
                stage=RefusalStage.PARSE,
                detail=(
                    f"AUX {tokens[head_index]!r} + participle {tokens[participle_index]!r} "
                    "with no overt by-agent. Row 1 of the construction table requires an "
                    "nmod:by, and the elided agent is not in the parse: deciding what it is "
                    "would be a semantic inference, so the reading is refused rather than "
                    "resolved"
                ),
                clause=" ".join(tokens),
            ),
            *_h6_refusals(tokens, participle_index, suppressed=True),
        )
    agent = _scan_pp(tokens, by_index)
    if agent is None:
        return _Outcome.refuse(
            Refusal(
                code=RefusalCode.AGENTLESS_PASSIVE,
                stage=RefusalStage.PARSE,
                detail=f"'by' at token {by_index} governs no noun phrase",
                clause=" ".join(tokens),
            )
        )
    arguments = [
        _argument("nsubj:pass", subject, tokens),
        _argument(
            "nmod:by", _Span(by_index + 1, agent.end), tokens, function_word="by"
        ),
    ]
    marked, cursor = _pp_arguments(tokens, agent.end)
    arguments.extend(argument for argument, _ in marked)
    if cursor < len(tokens):
        return _Outcome.refuse(
            *_leftover(tokens, cursor, len(tokens), "a constituent after the by-agent")
        )
    return _Outcome.declare(
        _Attempt(
            constructor="passive",
            construction=SyntacticConstruction.PASSIVE_WITH_AGENT,
            head_surface=tokens[participle_index],
            arguments=tuple(arguments),
            head_index=participle_index,
            head_aux_index=head_index,
        )
    )


# --------------------------------------------------------------------------- #
# Constructor 4: copular
# --------------------------------------------------------------------------- #


def _complement_category(tokens: Sequence[str], index: int) -> PhraseCategory:
    """The complement's phrase category - gap (b)'s decided half, in five answers.

    A total function over the closed inventories, with a residual, and the residual is
    row 2's own: a constituent that is not a PP, a CP, an adverbial predicate, an
    auxiliary or a participle **is** a bare NP, which is what row 2's stated condition
    calls the complement. Deciding it that way is applying the table's definition rather
    than extending it, which is the only reason it is not a guess.
    """
    if index >= len(tokens):
        return PhraseCategory.ADV_P
    token = tokens[index]
    folded = token.casefold()
    if _is_preposition(token):
        return PhraseCategory.PP
    if folded in SUBORDINATORS:
        return PhraseCategory.CP
    if _is_relative_pronoun(token) or folded in RELATIVE_ADVERBS:
        return PhraseCategory.ADV_P if folded in RELATIVE_ADVERBS else PhraseCategory.UNDECIDABLE
    if _is_aux(token) or _is_participle(token):
        return PhraseCategory.UNDECIDABLE
    if folded.endswith("ed") and not _is_np_start(token):
        return PhraseCategory.UNDECIDABLE
    return PhraseCategory.NP


def _c_copular(tokens: Sequence[str], head_index: int, channel: DeclaredChannel) -> _Outcome:
    """A copula with a complement, and the three ways that complement can go wrong.

    ``_complement_category`` decides the category and the constructor applies the table's
    conditions to it: a bare NP is row 2, a bare NP with an adjacent ``of``-PP is row 3, and
    a ``PP``, a ``CP``, an adverbial predicate or an undecidable one is **no row at all**.
    The last three are refusals with distinct codes, which is the whole of gap (b) decided
    rather than argued.
    """
    if not _is_copula_form(tokens[head_index]):
        return _Outcome.pass_through()
    del channel
    complement_index = head_index + 1
    subject = _subject_prefix(tokens, head_index)
    if subject is None:
        return _Outcome.pass_through()
    polarity = Polarity.ASSERTED
    if complement_index < len(tokens) and tokens[complement_index].casefold() in NEGATORS:
        # A negator in operator position. Phase 4A gave ``RelationSignal`` a ``polarity``
        # field, so this is no longer the case where a denial had nowhere to go and had to
        # be refused. The complement is scanned from *after* the negator and the reading
        # carries Polarity.DENIED, which the syntactic producer writes onto the signal.
        # Skipping the token rather than refusing the clause is what reopens the path: the
        # reading is "John is not the CEO of Acme", the frame is row 3, and the polarity
        # says the whole thing is denied. Refusing it left a real fact about a real
        # document unrepresented, and a platform that cannot represent "did not" reports
        # it as "did", which is worse than a gap.
        #
        # One negator at most: "John is not not the CEO of Acme" is not a double denial this
        # grammar can read, and treating it as one would assert something about a
        # construction nothing in the table supports.
        if (
            complement_index + 1 < len(tokens)
            and tokens[complement_index + 1].casefold() in NEGATORS
        ):
            return _Outcome.refuse(
                Refusal(
                    code=UNREAD_NEGATOR_CODE,
                    stage=RefusalStage.PARSE,
                    detail=(
                        "the complement carries two negators. One negation is a polarity on "
                        "the clause and two is a construction (double negation, a corrective "
                        "'not ... but ...'), and no row of the construction table states a "
                        "condition for either, so the reading is refused rather than "
                        "collapsed onto the single-negation case"
                    ),
                    clause=" ".join(tokens),
                )
            )
        complement_index += 1
        polarity = Polarity.DENIED
    elif complement_index < len(tokens) and _looks_like_negator(tokens[complement_index]):
        return _Outcome.refuse(
            Refusal(
                code=UNREAD_NEGATOR_CODE,
                stage=RefusalStage.PARSE,
                detail=(
                    f"the complement is {tokens[complement_index]!r}, which is shaped like a "
                    f"negator but is not in the closed inventory {sorted(NEGATORS)}. This "
                    "parser records a denial it has read and refuses one it has not, because "
                    "reporting the clause as an assertion would assert the opposite of what "
                    "it says"
                ),
                clause=" ".join(tokens),
            )
        )
    if complement_index >= len(tokens):
        return _Outcome.refuse(
            Refusal(
                code=RefusalCode.UNSUPPORTED_COMPLEMENT_CATEGORY,
                stage=RefusalStage.PARSE,
                detail=(
                    "the copula carries no complement at all. Declared as copular so the "
                    "table's own arity step answers it: a one-slot reading is a property, not "
                    "a relational configuration, and no_configuration is the honest code"
                ),
                clause=" ".join(tokens),
            )
        )
    category = _complement_category(tokens, complement_index)
    if category is PhraseCategory.UNDECIDABLE:
        return _Outcome.refuse(
            Refusal(
                code=RefusalCode.UNDECIDABLE_COMPLEMENT_CATEGORY,
                stage=RefusalStage.PARSE,
                detail=(
                    f"the complement begins with {tokens[complement_index]!r}, whose phrase "
                    "category the closed surface evidence does not decide: it could be a "
                    "participle or a predicative adjective, or a relative pronoun opening a "
                    "clause. Row 2 requires a bare NP and row 3 an of-PP, and choosing between "
                    "them here would be the guess the design forbids"
                ),
                clause=" ".join(tokens),
            )
        )
    if category is not PhraseCategory.NP:
        return _Outcome.refuse(
            Refusal(
                code=RefusalCode.UNSUPPORTED_COMPLEMENT_CATEGORY,
                stage=RefusalStage.PARSE,
                detail=(
                    f"the complement is a {category.value.upper()} beginning with "
                    f"{tokens[complement_index]!r}. No row of the construction table states a "
                    "condition accepting a non-nominal copular complement: row 2 requires a "
                    "bare NP and row 3 a nominal with an of-PP. This is the copular-versus-"
                    "active distinction the complement's phrase category decides, and it is "
                    "refused rather than defaulted to NOMARK or to the nearest row"
                ),
                clause=" ".join(tokens),
            )
        )
    complement = _scan_np(tokens, complement_index)
    if complement is None:
        return _Outcome.refuse(
            Refusal(
                code=RefusalCode.UNSUPPORTED_COMPLEMENT_CATEGORY,
                stage=RefusalStage.PARSE,
                detail=(
                    f"the complement begins with {tokens[complement_index]!r}, which no "
                    "closed noun-phrase test accepts"
                ),
                clause=" ".join(tokens),
            )
        )
    arguments = [
        _argument("nsubj", subject, tokens),
        _argument("obj", complement, tokens),
    ]
    cursor = complement.end
    construction = SyntacticConstruction.COPULAR
    if cursor < len(tokens) and _is_preposition(tokens[cursor]):
        pp = _scan_pp(tokens, cursor)
        if pp is not None and tokens[cursor].casefold() == "of":
            arguments.append(
                _argument(
                    "nmod:of",
                    _Span(cursor + 1, pp.end),
                    tokens,
                    function_word="of",
                )
            )
            construction = SyntacticConstruction.COPULAR_WITH_NOUN_COMPLEMENT
            cursor = pp.end
    if cursor < len(tokens):
        return _Outcome.refuse(
            *_leftover(
                tokens, cursor, len(tokens), "a constituent after the copular complement"
            )
        )
    return _Outcome.declare(
        _Attempt(
            constructor="copular",
            construction=construction,
            head_surface=tokens[head_index],
            arguments=tuple(arguments),
            head_index=head_index,
            extra_refusals=_h6_refusals(tokens, complement_index, suppressed=False),
            # Stated by the constructor that saw the negator, and read nowhere else. The
            # frame is unchanged by a negation - "is the CEO of" and "is not the CEO of" are
            # the same construction - so the only thing that differs is the polarity, and
            # the polarity is the only thing that may differ.
            polarity=polarity,
        )
    )


# --------------------------------------------------------------------------- #
# Constructor 5: an active clause
# --------------------------------------------------------------------------- #


def _c_active_clause(tokens: Sequence[str], head_index: int, channel: DeclaredChannel) -> _Outcome:
    """A finite non-copula head, an overt subject, and at most one bare object.

    Row 4. The object is optional because a clause with no further argument is row 5 and
    the table's own arity step answers it with ``no_configuration`` - a decision about a
    well-parsed reading, which is why it is a different code from every refusal here.

    A **second** bare noun phrase is not consumed. "John owns Acme shares" reads as one
    object because the NP scan continues; "John acquired Acme yesterday" does not, because
    the leftover is an adverbial the parser has no slot for, and reporting the reading
    without it would be reporting less than the sentence says.
    """
    del channel
    if not _is_verb_form(tokens[head_index]) or _is_copula_form(tokens[head_index]):
        return _Outcome.pass_through()
    subject = _subject_prefix(tokens, head_index)
    if subject is None:
        return _Outcome.pass_through()
    arguments = [_argument("nsubj", subject, tokens)]
    cursor = head_index + 1
    obj = _object_span(tokens, cursor)
    if obj is not None:
        arguments.append(_argument("obj", obj, tokens))
        cursor = obj.end
    marked, after = _pp_arguments(tokens, cursor)
    arguments.extend(argument for argument, _ in marked)
    cursor = after
    if cursor < len(tokens):
        return _Outcome.refuse(
            *_leftover(tokens, cursor, len(tokens), "a constituent no argument slot carries")
        )
    return _Outcome.declare(
        _Attempt(
            constructor="active_clause",
            construction=SyntacticConstruction.ACTIVE_CLAUSE,
            head_surface=tokens[head_index],
            arguments=tuple(arguments),
            head_index=head_index,
        )
    )


# --------------------------------------------------------------------------- #
# Constructor 6: a relative clause, read off its comma bracket
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class _RelativeBracket:
    """A comma-bracketed ``reld:cl``, and the three regions around it."""

    matrix: tuple[str, ...]
    pronoun: str
    inner: tuple[str, ...]
    tail: tuple[str, ...]


def _find_relative_bracket(tokens: Sequence[str]) -> _RelativeBracket | None:
    """The first comma-bracketed relative clause, or ``None``.

    The bracket is a *surface* fact - a comma, a relative pronoun, another comma - and
    bracketing on it is what lets the parser put the matrix NP outside the relative
    clause's own arguments, which is the guarantee ``data-model.md`` part 3.4 row 10
    relies on. A relative clause with no overt subject is declared with a pronominal
    subject and the matrix NP is **not** inferred into it; see
    :data:`PARSER_LIMITATIONS`.
    """
    for index in range(1, len(tokens)):
        if not _is_relative_pronoun(tokens[index]):
            continue
        if tokens[index - 1] != ",":
            continue
        for close in range(index + 2, len(tokens)):
            if tokens[close] != ",":
                continue
            inner = tuple(tokens[index + 1 : close])
            if not inner:
                continue
            return _RelativeBracket(
                matrix=tuple(tokens[: index - 1]),
                pronoun=tokens[index],
                inner=inner,
                tail=tuple(tokens[close + 1 :]),
            )
    return None


def _c_relative_clause(bracket: _RelativeBracket) -> _Outcome:
    """The relative clause's own arguments, and the antecedent as its object.

    Two decisions, both decided rather than inferred:

    * **The antecedent.** Taken as the matrix NP, which is where the comma bracket puts
      it, and only when the matrix region is exactly one noun phrase. Two candidate matrix
      NPs leave the antecedent undecidable and the reading is refused.
    * **The relative pronoun's role.** Decided by whether the inner clause has an overt
      subject. If it does, the pronoun is the object and the antecedent fills ``obj``. If it
      does not, the pronoun is the subject: the antecedent would have to be declared as
      that subject, which is the inference ``data-model.md`` part 3.4 calls "usually right
      and therefore a guess", so the subject is declared pronominal and the normaliser
      refuses the unoccupied required slot.
    """
    matrix = _scan_np(bracket.matrix, 0)
    if matrix is None or matrix.end != len(bracket.matrix):
        return _Outcome.refuse(
            Refusal(
                code=RefusalCode.UNSUPPORTED_CONSTRUCTION,
                stage=RefusalStage.PARSE,
                detail=(
                    f"the matrix region {' '.join(bracket.matrix)!r} is not exactly one noun "
                    "phrase, so the relative pronoun's antecedent is not decidable. A reading "
                    "that picked one of several candidates would be a guess about which entity "
                    "the document means"
                ),
                clause=" ".join(bracket.matrix),
            )
        )
    inner = bracket.inner
    head_index = _find_head(inner, inclusive_start=True)
    if head_index is None or not _is_verb_form(inner[head_index]):
        return _Outcome.pass_through()
    subject = _subject_prefix(inner, head_index)
    arguments: list[ParsedArgument] = []
    cursor = head_index + 1
    if subject is not None:
        arguments.append(_argument("nsubj", subject, inner))
    else:
        arguments.append(_pronominal_argument("nsubj", bracket.pronoun, position=0))
    obj = _object_span(inner, cursor)
    if obj is not None:
        arguments.append(_argument("obj", obj, inner))
        cursor = obj.end
    else:
        # No overt object, so the relative pronoun is the object and the antecedent fills
        # the slot. Its token indices are the matrix region's, which is why the observed
        # predicate span for this reading is the head word alone. The address is minted by
        # the one minter like every other argument's - it used to be spelled out here, which
        # is a second way to build the same string and the one the grammar's own history
        # records as having drifted.
        arguments.append(
            ParsedArgument(
                position_label="obj",
                surface=matrix.surface(bracket.matrix),
                head_token=bracket.matrix[matrix.end - 1],
                mention_ref=mint_occurrence_address(
                    label="obj",
                    surface=normalize_surface_for_fingerprint(
                        matrix.surface(bracket.matrix)
                    ),
                ),
                token_start=0,
                token_end=len(bracket.matrix),
            )
        )
    marked, after = _pp_arguments(inner, cursor)
    arguments.extend(argument for argument, _ in marked)
    if after < len(inner):
        return _Outcome.refuse(
            *_leftover(inner, after, len(inner), "a constituent no argument slot carries")
        )
    return _Outcome.declare(
        _Attempt(
            constructor="relative_clause",
            construction=SyntacticConstruction.RELATIVE_CLAUSE,
            head_surface=inner[head_index],
            arguments=tuple(arguments),
            head_index=head_index,
        )
    )


# --------------------------------------------------------------------------- #
# Constructors 7 to 10: the nominal readings
# --------------------------------------------------------------------------- #


def _c_genitive_np(tokens: Sequence[str], channel: DeclaredChannel) -> _Outcome:
    """``NP`` ``'s`` ``NOUN`` ``NP`` - row 7, whose reversal is the whole point.

    ``A0`` is the head NP the genitive modifies, which may be the surface-left or the
    surface-right one, and ``A1`` is the genitive itself: "Acme's founder John Smith" reads
    as ``(A0: John Smith, A1: Acme)``, because the signature normalises argument structure
    rather than word order. ``A0`` is optional on purpose - "Acme's founder" has no head NP
    on the possessed side, so one slot is occupied and the table's arity step answers
    ``no_configuration``, which is a decision rather than a malformed structure.
    """
    del channel
    genitive_index = next(
        (index for index, token in enumerate(tokens) if _is_genitive(token)), None
    )
    if genitive_index is None:
        return _Outcome.pass_through()
    if genitive_index == 0:
        return _Outcome.refuse(
            Refusal(
                code=RefusalCode.UNSUPPORTED_CONSTRUCTION,
                stage=RefusalStage.PARSE,
                detail=(
                    "the clause opens with a genitive marker, so the possessed side has no "
                    "head NP at all. Declared as a genitive NP so the table's own arity step "
                    "answers it with no_configuration rather than the producer guessing a head"
                ),
                clause=" ".join(tokens),
            )
        )
    genitive = _Span(0, genitive_index)
    head_index = genitive_index + 1
    while head_index < len(tokens) and _is_determiner(tokens[head_index]):
        head_index += 1
    if head_index >= len(tokens):
        return _Outcome.pass_through()
    head_surface = tokens[head_index]
    arguments = [
        _argument(
            "case:gen",
            genitive,
            tokens,
            # No function word: a genitive marker is structural, and the observed ``'s`` is
            # evidence, not a marker. Row 7's A1 is NOMARK for exactly this reason.
            function_word=None,
        )
    ]
    cursor = head_index + 1
    if cursor < len(tokens):
        possessed = _scan_np(tokens, cursor)
        if possessed is not None and possessed.end == len(tokens):
            arguments.append(_argument("nsubj", possessed, tokens))
            cursor = possessed.end
        else:
            return _Outcome.refuse(
                Refusal(
                    code=RefusalCode.UNSUPPORTED_CONSTRUCTION,
                    stage=RefusalStage.PARSE,
                    detail=(
                        f"{' '.join(tokens[cursor:])!r} follows the genitive head and is not one "
                        "noun phrase. Row 7 carries a genitive and at most one possessed-side "
                        "head NP, so anything more would be dropped by the plan"
                    ),
                    clause=" ".join(tokens),
                )
            )
    del cursor
    return _Outcome.declare(
        _Attempt(
            constructor="genitive_np",
            construction=SyntacticConstruction.GENITIVE_NP,
            head_surface=head_surface,
            arguments=tuple(arguments),
            head_index=head_index,
        )
    )


def _c_appositive_np(tokens: Sequence[str], channel: DeclaredChannel) -> _Outcome:
    """``NP , NP of NP`` - row 8, an appositive read as a role.

    Distinguishable from row 6 by the comma and nothing else: rows 6 and 8 have *identical*
    conditions in the table, so the whole difference between ``nominal_owner_of`` and
    ``appositive_role`` is the producer's declaration that the second NP is comma-delimited.
    That is a surface fact, and it is why the two frames never merge.
    """
    del channel
    comma = tokens.index(",") if "," in tokens else -1
    if comma < 0:
        return _Outcome.pass_through()
    matrix = _scan_np(tokens, 0)
    if matrix is None or matrix.end != comma:
        return _Outcome.refuse(
            Refusal(
                code=RefusalCode.UNSUPPORTED_CONSTRUCTION,
                stage=RefusalStage.PARSE,
                detail=(
                    "the region before the comma is not exactly one noun phrase, so the "
                    "appositive's matrix NP is not decidable. Row 8's A0 is the matrix head, "
                    "and inventing one would be inventing a participant"
                ),
                clause=" ".join(tokens),
            )
        )
    head_index = comma + 1
    while head_index < len(tokens) and _is_determiner(tokens[head_index]):
        head_index += 1
    if head_index >= len(tokens):
        return _Outcome.refuse(
            *_leftover(tokens, head_index, len(tokens), "an appositive with no head noun")
        )
    head_surface = tokens[head_index]
    cursor = head_index + 1
    arguments = [_argument("obj", matrix, tokens)]
    if cursor < len(tokens) and _is_preposition(tokens[cursor]):
        pp = _scan_pp(tokens, cursor)
        if pp is not None and tokens[cursor].casefold() == "of":
            arguments.append(
                _argument("nmod:of", _Span(cursor + 1, pp.end), tokens, function_word="of")
            )
            cursor = pp.end
    if cursor < len(tokens):
        return _Outcome.refuse(
            Refusal(
                code=RefusalCode.UNSUPPORTED_CONSTRUCTION,
                stage=RefusalStage.PARSE,
                detail=(
                    f"{' '.join(tokens[cursor:])!r} follows the appositive. Row 8 carries the "
                    "matrix NP and one of-complement, so the appositive's own arguments are "
                    "not slots and reporting them would drop a participant"
                ),
                clause=" ".join(tokens),
            )
        )
    return _Outcome.declare(
        _Attempt(
            constructor="appositive_np",
            construction=SyntacticConstruction.APPOSITIVE_NP,
            head_surface=head_surface,
            arguments=tuple(arguments),
            head_index=head_index,
        )
    )


def _c_headless_pp(tokens: Sequence[str], channel: DeclaredChannel) -> _Outcome:
    """A PP with no subject of its own, whose governor and subject a channel declares.

    Row 9. Neither the governor nor the subject is in the surface, so both come from
    :class:`DeclaredChannel` - a real document-structure case being an attribute row whose
    key is the predicate and whose value is the phrase. With no declared head there is
    nothing to hand ``normalize_predicate``, so the reading is refused; with a head and no
    declared subject the table's ``slot_gap`` answers it, because inventing the subject
    would be inventing a participant.
    """
    if not tokens or not _is_preposition(tokens[0]):
        return _Outcome.pass_through()
    pp = _scan_pp(tokens, 0)
    if pp is None:
        return _Outcome.pass_through()
    if not channel.head.strip():
        return _Outcome.refuse(
            Refusal(
                code=RefusalCode.UNCLASSIFIED_CONSTRUCTION,
                stage=RefusalStage.PARSE,
                detail=(
                    "a headless prepositional phrase with no declared governor. Row 9's head "
                    "is a document-structure producer slot, so the channel must name it; a "
                    "phrase with no predicate is a phrase, not a reading"
                ),
                clause=" ".join(tokens),
            )
        )
    arguments = [
        _argument("pobj", _Span(1, pp.end), tokens, function_word=tokens[0].casefold())
    ]
    if channel.subject.strip():
        subject_tokens = tokenise(channel.subject)
        if not subject_tokens:
            return _Outcome.refuse(
                Refusal(
                    code=RefusalCode.UNCLASSIFIED_CONSTRUCTION,
                    stage=RefusalStage.PARSE,
                    detail="the channel declared a subject that tokenises to nothing",
                    clause=" ".join(tokens),
                )
            )
        span = _scan_np(subject_tokens, 0)
        if span is None:
            return _Outcome.refuse(
                Refusal(
                    code=RefusalCode.UNCLASSIFIED_CONSTRUCTION,
                    stage=RefusalStage.PARSE,
                    detail=(
                        f"the channel's declared subject {channel.subject!r} is not a noun "
                        "phrase this parser can read, so the row 9 A1 would be unstated"
                    ),
                    clause=" ".join(tokens),
                )
            )
        arguments.append(
            _argument("nsubj", span, subject_tokens, token_offset=len(tokens))
        )
    return _Outcome.declare(
        _Attempt(
            constructor="headless_pp",
            construction=SyntacticConstruction.HEADLESS_PP,
            head_surface=channel.head.strip(),
            arguments=tuple(arguments),
            head_index=0,
        )
    )


def _c_bare_nominal(tokens: Sequence[str], channel: DeclaredChannel) -> _Outcome:
    """A nominal head with an ``of``-complement and one further argument - row 6.

    ``A0`` is the nominal's governor argument and ``A1`` its ``of``-complement, so a
    fragment needs **two** arguments to reach row 6's condition. "owner of Acme" alone has
    an unoccupied ``A0`` and is refused at ``slot_gap``; "owner by John" has no ``of`` at all
    and matches no row. A caption, a chart label and a transaction-log line are where this
    reading actually occurs, and the surface that reaches it is two prepositional phrases
    under one nominal head - "owner of Acme from Globex".
    """
    del channel
    if not tokens or _is_preposition(tokens[0]):
        return _Outcome.pass_through()
    if len(tokens) < 2 or not _is_preposition(tokens[1]):
        # Not a "nominal + prepositional phrase" shape, so not row 6. Claiming it anyway
        # would make every determiner-less fragment a bare nominal, and the leftover check
        # would then report a construction nobody declared.
        return _Outcome.pass_through()
    head_surface = tokens[0]
    arguments: list[ParsedArgument] = []
    cursor = 1
    of_seen = False
    other = 0
    while cursor < len(tokens):
        if tokens[cursor] == ",":
            cursor += 1
            continue
        if not _is_preposition(tokens[cursor]):
            return _Outcome.refuse(
                *_leftover(
                    tokens, cursor, len(tokens), "a constituent no argument slot carries"
                )
            )
        pp = _scan_pp(tokens, cursor)
        if pp is None:
            return _Outcome.refuse(
                Refusal(
                    code=RefusalCode.UNSUPPORTED_CONSTRUCTION,
                    stage=RefusalStage.PARSE,
                    detail=(
                        f"the preposition {tokens[cursor]!r} governs no noun phrase"
                    ),
                    clause=" ".join(tokens),
                )
            )
        marker = tokens[cursor].casefold()
        label = "nmod:of" if marker == "of" else f"nmod:{marker}"
        arguments.append(
            _argument(label, _Span(cursor + 1, pp.end), tokens, function_word=marker)
        )
        of_seen = of_seen or marker == "of"
        other += 0 if marker == "of" else 1
        cursor = pp.end
    if not of_seen or other < 1:
        return _Outcome.refuse(
            Refusal(
                code=RefusalCode.UNSUPPORTED_CONSTRUCTION,
                stage=RefusalStage.PARSE,
                detail=(
                    f"the nominal {head_surface!r} has an of-complement={of_seen} and "
                    f"further-arguments={other}. Row 6 requires both: A0 is the governor and "
                    "A1 the of-head, so one of the two absent is a slot the parse cannot fill"
                ),
                clause=" ".join(tokens),
            )
        )
    return _Outcome.declare(
        _Attempt(
            constructor="bare_nominal",
            construction=SyntacticConstruction.BARE_NOMINAL,
            head_surface=head_surface,
            arguments=tuple(arguments),
            head_index=0,
        )
    )


# --------------------------------------------------------------------------- #
# Constructor 11: a clause shape whose predicate head has no lemma
# --------------------------------------------------------------------------- #


def _c_unresolved_clause(tokens: Sequence[str], channel: DeclaredChannel) -> _Outcome:
    """``NP`` word ``NP`` - a clause shape whose middle word is not a decidable predicate.

    The shape is real and common; the predicate is not. "Globex manufactures widgets" has
    the subject-then-predicate-then-object shape every other constructor recognises, and
    ``manufactures`` is in no morphology the platform holds, so the head cannot be resolved
    and the reading cannot be normalised. Refused as ``unsupported_lemma`` - which is the
    table's own code for exactly this, and a *different* gap from
    ``unclassified_construction``, where there was no clause shape to begin with.
    """
    del channel
    first = _scan_np(tokens, 0)
    if first is None:
        return _Outcome.pass_through()
    middle = first.end
    if middle >= len(tokens) or _is_punct(tokens[middle]) or _is_genitive(tokens[middle]):
        return _Outcome.pass_through()
    tail = _scan_np(tokens, middle + 1)
    if tail is None or tail.end != len(tokens):
        return _Outcome.pass_through()
    return _Outcome.refuse(
        Refusal(
            code=RefusalCode.UNSUPPORTED_LEMMA,
            stage=RefusalStage.PARSE,
            detail=(
                f"the clause has a subject-predicate-object shape but {tokens[middle]!r} is a "
                "form of no lemma the generated table holds, so it is not decidable as the "
                "predicate head. Guessing one would merge two readings on a coin toss, which "
                "is the defect N5 exists to prevent"
            ),
            clause=" ".join(tokens),
        )
    )


# --------------------------------------------------------------------------- #
# The dispatcher
# --------------------------------------------------------------------------- #


def _h6_refusals(tokens: Sequence[str], index: int, *, suppressed: bool) -> tuple[Refusal, ...]:
    """The §19 record for a determiner-less nominal complement followed by an ``of``-PP.

    "is CEO of", "became CEO of" and "was appointed CEO of" are the surfaces §19 lists, and
    what makes them *one* case is a determiner-less nominal complement: "is **the** CEO of"
    is a different reading and is not recorded here. The record is the stop condition being
    honoured, not a rule: for the two copular members ``suppressed`` is ``False`` because a
    reading *was* emitted and the refusal is of the **merge**, and for the passive member it
    is ``True`` because the whole reading was already refused as agentless.
    """
    if index >= len(tokens) or _is_determiner(tokens[index]):
        return ()
    if not any(token.casefold() == "of" for token in tokens[index + 1 :]):
        return ()
    return (
        Refusal(
            code=RefusalCode.H6_OPEN_CASE,
            stage=(
                RefusalStage.PARSE if suppressed else RefusalStage.IDENTITY
            ),
            detail=(
                f"{H6_STOP_CONDITION} This clause realises the bare-nominal-complement member "
                "('is CEO of' / 'became CEO of' / 'was appointed CEO of'); its reading keeps its "
                "own signature and is not merged with any other realisation."
            ),
            clause=" ".join(tokens),
        ),
    )


def _read_simple(
    tokens: tuple[str, ...],
    *,
    language: str,
    channel: DeclaredChannel,
) -> tuple[tuple[SyntacticReading, ...], tuple[Refusal, ...]]:
    """One clause with no relative-clause bracket: run the constructors in pinned order."""
    clause = " ".join(tokens)
    if not tokens:
        return (), (
            Refusal(
                code=RefusalCode.NO_CLAUSE,
                stage=RefusalStage.PARSE,
                detail="the text carried no clause, only punctuation or whitespace",
                clause=clause,
            ),
        )
    if any(_is_coord(token) for token in tokens):
        return (), (
            Refusal(
                code=RefusalCode.COORDINATED_CLAUSE,
                stage=RefusalStage.PARSE,
                detail=(
                    "the clause contains a coordinating conjunction. Coordination is a named "
                    "stop condition rather than a gap to paper over with a sort: brief §29 "
                    "lists no coordinated frame, and a coordinated frame without a declared "
                    "symmetry marker would let the ordering invent a reading the structure "
                    "does not license (A2 U5). Splitting the conjuncts is deliberately NOT "
                    "done, because the coordination itself is a fact this producer has no slot "
                    "for and dropping it would report less than the sentence says"
                ),
                clause=clause,
            ),
        )
    head_index = _find_head(tokens)
    outcome: _Outcome
    if head_index is not None:
        outcome = _Outcome.pass_through()
        for constructor in (
            _c_clause_initial_auxiliary,
            _c_passive,
            _c_copular,
            _c_active_clause,
        ):
            outcome = constructor(tokens, head_index, channel)
            if outcome.claimed:
                break
    else:
        outcome = _Outcome.pass_through()
        for constructor in (
            _c_genitive_np,
            _c_appositive_np,
            _c_headless_pp,
            _c_bare_nominal,
            _c_unresolved_clause,
        ):
            outcome = constructor(tokens, channel)
            if outcome.claimed:
                break
    if not outcome.claimed:
        return (), (
            Refusal(
                code=RefusalCode.UNCLASSIFIED_CONSTRUCTION,
                stage=RefusalStage.PARSE,
                detail=(
                    "no constructor declared a construction for this clause. It is refused "
                    "rather than forced into the nearest row: an unknown construction is a "
                    "countable gap (brief §30), and a guessed one is a merge nobody can undo"
                ),
                clause=clause,
            ),
        )
    if outcome.attempt is None:
        return (), outcome.refusals
    reading, refusals = _finish(
        outcome.attempt, clause, tokens, language=language, channel=channel
    )
    if reading is None:
        return (), refusals
    return (reading,), refusals


def _read_clause(
    tokens: tuple[str, ...],
    *,
    language: str,
    channel: DeclaredChannel,
) -> tuple[tuple[SyntacticReading, ...], tuple[Refusal, ...]]:
    """One sentence, split at a relative-clause bracket when there is one.

    A bracket yields **two** readings - the relative clause's own, and the matrix clause's -
    because they are two clauses and two relational claims. Splitting is a syntactic
    operation on a surface bracket and invents nothing; what the bracket's structure *forbids*
    is putting the matrix NP inside the relative clause's arguments, and that is refused
    rather than inferred.
    """
    bracket = _find_relative_bracket(tokens)
    if bracket is None:
        return _read_simple(tokens, language=language, channel=channel)
    readings: list[SyntacticReading] = []
    refusals: list[Refusal] = []
    relative = _c_relative_clause(bracket)
    if relative.claimed and relative.attempt is not None:
        inner = " ".join(bracket.inner)
        reading, inner_refusals = _finish(
            relative.attempt, inner, bracket.inner, language=language, channel=channel
        )
        refusals.extend(inner_refusals)
        if reading is not None:
            readings.append(reading)
    elif not relative.claimed:
        refusals.append(
            Refusal(
                code=RefusalCode.UNCLASSIFIED_CONSTRUCTION,
                stage=RefusalStage.PARSE,
                detail=(
                    "a comma-bracketed relative pronoun is present but its inner clause has no "
                    "finite head this parser can declare, so the relative clause is refused and "
                    "the matrix clause is still read"
                ),
                clause=" ".join(tokens),
            )
        )
    else:
        refusals.extend(relative.refusals)
    remainder = bracket.matrix + bracket.tail
    if remainder:
        more, more_refusals = _read_clause(
            remainder, language=language, channel=channel
        )
        readings.extend(more)
        refusals.extend(more_refusals)
    return tuple(readings), tuple(refusals)


def parse(
    text: str,
    *,
    language: str = "en",
    channel: DeclaredChannel | None = None,
) -> tuple[tuple[SyntacticReading, ...], tuple[Refusal, ...]]:
    """Every reading ``text`` licenses, and every refusal, in document order.

    The single entry point, and the reason a caller can count. Returns readings *and*
    refusals rather than one or the other, because brief §30 requires a missing parser
    capability to mean "no syntactic signals" and *not* a batch failure - which only holds if
    the reason is machine-readable and the batch continues.

    ``channel`` is a **document-level** declaration and applies to every fragment the parser
    reads in ``text``. A caller whose declarations are per clause - a different governor for
    a different slot in the same document - should call this function once per clause rather
    than pass one channel for the whole text, and that is a limitation of this signature
    rather than a rule the parser applies.

    Never raises for bad input. An unsupported language, empty text, a tokeniser failure and
    a clause no rule matched all come back as refusals with codes, and the caller decides
    what to do with the count.
    """
    channel = channel if channel is not None else DeclaredChannel()
    folded = str(language or "").strip().lower()
    if folded not in SHIPPED_LANGUAGES:
        return (), (
            Refusal(
                code=RefusalCode.UNSUPPORTED_LANGUAGE,
                stage=RefusalStage.PARSE,
                detail=(
                    f"language={folded!r} is not shipped in feature 021. These rules are "
                    "English surface rules, so a non-English surface is not a reading this "
                    "parser is competent to make; a cross-lingual pair would be two readings, "
                    "and merging them is a semantic claim section 20 reserves to explicit "
                    "mapping"
                ),
                clause="",
            ),
        )
    if not str(text or "").strip():
        return (), (
            Refusal(
                code=RefusalCode.NO_CLAUSE,
                stage=RefusalStage.PARSE,
                detail="the input carried no text at all",
                clause="",
            ),
        )
    tokens = tokenise(text)
    readings: list[SyntacticReading] = []
    refusals: list[Refusal] = []
    for _offset, sentence in _sentences(tokens):
        more, more_refusals = _read_clause(
            sentence, language=folded, channel=channel
        )
        readings.extend(more)
        refusals.extend(more_refusals)
    if not readings and not refusals:
        refusals.append(
            Refusal(
                code=RefusalCode.NO_CLAUSE,
                stage=RefusalStage.PARSE,
                detail="the text tokenised to nothing a constructor could claim",
                clause="",
            )
        )
    return tuple(readings), tuple(refusals)


def refusal_counts(refusals: Sequence[Refusal]) -> dict[str, int]:
    """``{code: count}`` over refusals, keys sorted, so a caller can count by code.

    A module function rather than a method on a result type, because there is no result
    type here: :func:`parse` hands back two tuples, and the same counting works over
    refusals gathered from a whole batch of documents. Sorted keys make the result
    byte-identical across runs, which is what makes it usable as a stored measurement.
    """
    counts: dict[str, int] = {}
    for refusal in refusals:
        counts[refusal.code] = counts.get(refusal.code, 0) + 1
    return {code: counts[code] for code in sorted(counts)}


# --------------------------------------------------------------------------- #
# The argument-to-slot map, checked against the authority
# --------------------------------------------------------------------------- #


def _tb2(arguments: Sequence[ParsedArgument]) -> list[ParsedArgument]:
    """V2's ``TB2`` order: function word, then position label, then document order.

    Re-derived here from the same three keys ``domain.predicate_voice`` states, and then
    **checked** against the result by :func:`assign_slots`. The duplication is the point:
    an independent implementation that is never compared with the authority is a second
    answer, and a second answer to a slot assignment is a fork in logical identity. The
    check is the mechanism, and ``test_the_slot_map_agrees_with_normalize_voice_on_every_row``
    is what keeps it honest for all ten rows.
    """
    return sorted(
        arguments,
        key=lambda argument: (
            (argument.function_word or "").casefold(),
            argument.position_label,
            argument.token_start,
        ),
    )


def _plan_slots(reading: SyntacticReading) -> tuple[tuple[tuple[ParsedArgument, bool], ...], ...]:
    """``((argument, function-word-marked), ...)`` in canonical slot order, pronominals included.

    One clause per construction, mirroring the slot-source column of ``CONSTRUCTION_TABLE``
    part 3.4 row by row. The ``bool`` is the row's *markers* column: whether that position
    takes the argument's own function word as its marker, or is structurally unmarked.
    """
    construction = reading.construction
    arguments = reading.arguments

    def labelled(*labels: str) -> list[ParsedArgument]:
        return [item for item in arguments if item.position_label in labels]

    def others(*labels: str) -> list[ParsedArgument]:
        return [item for item in arguments if item.position_label not in labels]

    if construction is SyntacticConstruction.PASSIVE_WITH_AGENT:
        agent = labelled("nmod:by")
        patient = labelled("nsubj:pass")
        rest = _tb2(others("nmod:by", "nsubj:pass"))
        return tuple((item, False) for item in agent) + tuple(
            (item, True) for item in [*patient, *rest]
        )
    if construction in (
        SyntacticConstruction.COPULAR,
        SyntacticConstruction.COPULAR_WITH_NOUN_COMPLEMENT,
    ):
        subject = labelled("nsubj")
        complement = others("nsubj")
        through_of = [item for item in complement if item.position_label == "nmod:of"]
        second = through_of or complement[:1]
        return tuple((item, False) for item in subject) + tuple(
            (item, bool(through_of)) for item in second
        )
    if construction in (
        SyntacticConstruction.ACTIVE_CLAUSE,
        SyntacticConstruction.RELATIVE_CLAUSE,
    ):
        subject = labelled("nsubj")
        rest = _tb2(others("nsubj"))
        return tuple((item, False) for item in subject) + tuple((item, True) for item in rest)
    if construction in (
        SyntacticConstruction.BARE_NOMINAL,
        SyntacticConstruction.APPOSITIVE_NP,
    ):
        of_complement = labelled("nmod:of")
        governor = others("nmod:of")
        return tuple((item, False) for item in governor) + tuple(
            (item, True) for item in of_complement
        )
    if construction is SyntacticConstruction.GENITIVE_NP:
        genitive = labelled("case:gen", "case:genitive")
        possessed = [
            item
            for item in arguments
            if item.position_label not in ("case:gen", "case:genitive")
        ]
        return tuple((item, False) for item in possessed) + tuple(
            (item, False) for item in genitive
        )
    if construction is SyntacticConstruction.HEADLESS_PP:
        pobj = labelled("pobj")
        subject = others("pobj")
        return tuple((item, True) for item in pobj) + tuple((item, False) for item in subject)
    raise ParserContractError(
        RefusalCode.SLOT_MAP_DISAGREES,
        f"no slot plan is declared for construction {construction.value!r}. The parser "
        "declares no construction outside CONSTRUCTION_TABLE, so reaching this is a defect in "
        "the plan, not a corpus condition, and emitting nothing is the right answer",
    )


def assign_slots(reading: SyntacticReading) -> tuple[SlotBinding, ...]:
    """Bind every argument of ``reading`` to the canonical slot it fills.

    A :class:`~domain.predicate_voice.CanonicalArgumentAssignment` carries the slots and the
    markers but not the arguments that filled them, and a :class:`~domain.predicate_voice.RoleBinding`
    needs exactly that. So the producer derives the map from the documented V2 order and then
    **asks the authority whether it agrees**, on two counts: the arity, and the marker of
    every slot. A disagreement raises ``slot_map_disagrees_with_normalizer`` rather than
    returning a map, because a wrong map is a wrong ``logical_candidate_id`` and nothing
    downstream can tell.
    """
    from domain.predicate_voice import normalize_voice

    assignment = normalize_voice(
        reading.predicate, reading.syntactic_structure, reading.dependency_structure
    )
    survivors = [
        (argument, marked) for argument, marked in _plan_slots(reading) if not argument.pronominal
    ]
    if len(survivors) != assignment.arity:
        raise ParserContractError(
            RefusalCode.SLOT_MAP_DISAGREES,
            f"the producer's plan fills {len(survivors)} slot(s) and normalize_voice filled "
            f"{assignment.arity}. The two implementations of the documented V2 order have "
            "drifted, so no logical identity is minted for this reading",
        )
    bindings: list[SlotBinding] = []
    for position, ((argument, marked), slot, marker) in enumerate(
        zip(survivors, assignment.canonical_argument_slots, assignment.argument_markers,
            strict=True)
    ):
        expected = ArgumentMarker.NOMARK
        if marked and argument.function_word:
            folded = normalize_surface_for_fingerprint(argument.function_word)
            try:
                expected = ArgumentMarker(folded)
            except ValueError as exc:
                raise ParserContractError(
                    RefusalCode.SLOT_MAP_DISAGREES,
                    f"slot {slot.token} takes its marker from function word "
                    f"{argument.function_word!r}, which is outside the closed inventory - so "
                    "the reading should not have reached this point",
                ) from exc
        if expected is not marker:
            raise ParserContractError(
                RefusalCode.SLOT_MAP_DISAGREES,
                f"slot {slot.token} (position {position}, argument "
                f"{argument.surface!r}) should carry marker {expected.value!r} and "
                f"normalize_voice produced {marker.value!r}. The two implementations of the "
                "documented V2 order have drifted, so no logical identity is minted",
            )
        bindings.append(SlotBinding(argument=argument, slot=slot, marker=marker))
    return tuple(bindings)


def logical_candidate_id_of(
    reading: SyntacticReading,
    mentions: Mapping[str, ResolvedMention],
    *,
    tenant_id: str,
    polarity: Polarity = Polarity.ASSERTED,
) -> str:
    """``logical_candidate_id`` for one reading, from bound mentions.

    ``mentions`` is keyed by the **normalised participant surface** - the same key
    ``data-model.md`` §10.1 gives the mention-binding stage - because this producer sits
    below mention extraction and cannot mint mention ids (brief §25). Every participant must
    be bound or the call raises ``unbound_participant``: a partially bound ordering is a
    silent identity fork, and this is the one place in the layer where failing open would be
    undetectable downstream.

    Two realisations of one reading that bind to the **same** mention records therefore
    reach one id - which is §18's claim, end to end, over a real parser.
    """
    if not str(tenant_id).strip():
        raise ParserContractError(
            RefusalCode.UNBOUND_PARTICIPANT,
            "a logical candidate id requires a tenant; '' is not a tenant (constitution IV)",
        )
    participants: list[ParticipantBinding] = []
    for binding in assign_slots(reading):
        key = binding.argument.normalized_surface
        mention = mentions.get(key)
        if mention is None:
            raise ParserContractError(
                RefusalCode.UNBOUND_PARTICIPANT,
                f"participant {binding.argument.surface!r} at slot {binding.slot.token} has no "
                "mention binding, so the participant fingerprint cannot be computed. Binding "
                f"the {len(participants)} other(s) and dropping this one would mint an identity "
                "over fewer participants than the sentence has",
            )
        participants.append(
            ParticipantBinding(
                role=RoleBinding(
                    # The position label, not a role name. 'seller' and 'vendor' are the same
                    # A1, and a free-text role here would fork the logical id (FR-009).
                    surface_role=binding.argument.position_label,
                    role_hypothesis="",
                    canonical_argument_slot=binding.slot,
                    normalization_version=VOICE_NORMALIZATION_VERSION,
                    evidence=(reading.predicate_span,),
                ),
                mention=mention,
            )
        )
    return logical_candidate_id(
        reading.signature, participants, tenant_id=tenant_id, polarity=polarity
    )


# --------------------------------------------------------------------------- #
# The pinned configuration and its digest
# --------------------------------------------------------------------------- #


def configuration_material() -> dict[str, object]:
    """Every table, inventory, ordering and rule name the parser reads.

    The digest input, and deliberately *exhaustive*: a rule that is not named here is a rule
    whose change is invisible in provenance. The lemma table contributes its own committed
    digest rather than its rows, for the same reason ``predicate_signature`` carries
    ``LEMMA_TABLE_DIGEST`` - the table has its own drift test, and hashing thousands of rows
    here would put a second copy of that fact in a second place.

    Keys are emitted in sorted order so the material reads in the same order it hashes in;
    ``canonical_material`` sorts them anyway, and a material whose order a reader has to
    guess is one nobody reviews.
    """
    material: dict[str, object] = {
        "constructor_order": list(CONSTRUCTOR_ORDER),
        "declaring_constructors": {
            name: str(construction)
            for name, construction in sorted(DECLARABLE_CONSTRUCTIONS.items())
        },
        "refusal_only_constructors": sorted(REFUSAL_ONLY_CONSTRUCTORS),
        "refusal_codes": sorted(str(code) for code in RefusalCode),
        "phrase_categories": sorted(str(category) for category in PhraseCategory),
        "refusal_stages": sorted(str(stage) for stage in RefusalStage),
        "determiners": sorted(DETERMINERS),
        "demonstrative_determiners": sorted(DEMONSTRATIVE_DETERMINERS),
        "possessive_determiners": sorted(POSSESSIVE_DETERMINERS),
        "pronouns": sorted(PRONOUNS),
        "relative_pronouns": sorted(RELATIVE_PRONOUNS),
        "relative_adverbs": sorted(RELATIVE_ADVERBS),
        "subordinators": sorted(SUBORDINATORS),
        "coordinators": sorted(COORDINATORS),
        "negators": sorted(NEGATORS),
        "syntax_prepositions": sorted(SYNTAX_PREPOSITIONS),
        "clause_initial_aux": sorted(CLAUSE_INITIAL_AUX),
        "passive_middles": sorted(PASSIVE_MIDDLES),
        "sentence_terminators": sorted(SENTENCE_TERMINATORS),
        "pinned_participles": dict(sorted(PINNED_PARTICIPLES.items())),
        "nominal_suffixes": list(NOMINAL_SUFFIXES),
        "token_pattern": _TOKEN.pattern,
        "genitive_pattern": _GENITIVE.pattern,
        "aux_lemmas": sorted(AUX_LEMMA_INVENTORY),
        "copula_lemmas": sorted(COPULA_LEMMA_INVENTORY),
        "lemma_table_digest": LEMMA_TABLE_DIGEST,
        "shipped_languages": sorted(SHIPPED_LANGUAGES),
    }
    return {key: material[key] for key in sorted(material)}


def configuration_hash() -> str:
    """32 lowercase hex over :func:`configuration_material`, and a committed golden value.

    A rule change moves this, and the test pins it. That is the whole mechanism: not "we
    bumped the version somewhere", but a diff in a digest a reviewer reads.
    """
    return digest128(canonical_material(configuration_material()))


#: The committed digest. Read by ``test_the_pinned_configuration_hash_is_current``; a diff
#: here means a rule, an inventory or an ordering moved, and the diff is the review.
PINNED_CONFIGURATION_HASH: str = "1aafcd1ecd30d2f67e97cc2aae382343"

#: The committed digest over the pinned clause fixtures' actual parses. The digest a rule
#: change shows up in when it changes an *output* rather than a table.
PINNED_FIXTURE_DIGEST: str = "bae224319ef33c4c8da0e5520f2451a2"


def fixture_outcome(clause: str, *, channel: DeclaredChannel | None = None) -> tuple[str, str]:
    """``(outcome, rendered predicate)`` for one clause, as the fixture table records it.

    The outcome is the constructor that claimed the clause, or the refusal code when it was
    refused, and the predicate is the rendered signature or ``""``. Both are what a rule
    change moves, which is what makes :func:`fixture_digest` the *behavioural* pin beside
    :func:`configuration_hash`'s *structural* one.
    """
    readings, refusals = parse(clause, channel=channel)
    blocking = [refusal for refusal in refusals if refusal.suppresses_signal]
    if blocking:
        return blocking[0].code, ""
    if not readings:
        return RefusalCode.NO_CLAUSE, ""
    return readings[0].constructor, readings[0].rendered_predicate


def fixture_digest() -> str:
    """A digest over every :data:`PINNED_CLAUSE_FIXTURES` outcome, in fixture order."""
    return digest128(
        canonical_material(
            [fixture_outcome(clause) for clause, _expected, _predicate
             in PINNED_CLAUSE_FIXTURES]
        )
    )


@dataclass(frozen=True, slots=True)
class ParserCapability:
    """The four pinned fields of FR-043, as one value.

    :attr:`model_ref` names a rule set rather than a downloaded checkpoint, which is the
    honest answer in a repository with no dependency parser. :attr:`configuration_hash` is
    the part that matters operationally: it is a digest over every table the parser reads, so
    a stored reading's provenance says which rules produced it and a rule change is a diff
    rather than a silent corpus shift.

    Frozen, and validated on construction, because a capability whose fields may be blank is
    a provenance record that cannot justify anything.
    """

    model_ref: str = MODEL_REF
    model_version: str = MODEL_VERSION
    parser_version: str = PARSER_VERSION
    configuration_hash: str = ""

    def __post_init__(self) -> None:
        computed = configuration_hash()
        supplied = str(self.configuration_hash or "").strip()
        if not supplied:
            object.__setattr__(self, "configuration_hash", computed)
            return
        if supplied != computed:
            raise ParserContractError(
                RefusalCode.SLOT_MAP_DISAGREES,
                f"configuration_hash={supplied!r} but the rule tables in this module hash to "
                f"{computed!r}. A capability may not claim a configuration it does not have: "
                "that is a provenance record asserting something the code does not do",
            )
        object.__setattr__(self, "configuration_hash", supplied)
        for name in ("model_ref", "model_version", "parser_version"):
            if not str(getattr(self, name)).strip():
                raise ParserContractError(
                    RefusalCode.SLOT_MAP_DISAGREES,
                    f"{name} is empty. FR-043 requires all four fields, and a blank one is a "
                    "record that cannot say which parser produced a reading",
                )

    def to_dict(self) -> dict[str, str]:
        return {
            "model_ref": self.model_ref,
            "model_version": self.model_version,
            "parser_version": self.parser_version,
            "configuration_hash": self.configuration_hash,
        }


#: The one capability, built once at import. A function would rebuild it per call, and a
#: caller comparing two capabilities by value deserves the same object.
SHALLOW_CAPABILITY: ParserCapability = ParserCapability()

#: Raised nowhere; exported so a caller can import the *type* without constructing one.
NO_LLM_IN_CONSTITUTIONAL_PATH: Final[str] = (
    "This parser is regex and table lookups over a closed function-word inventory. It imports "
    "no model, no network client and no learned parameter, so no LLM is in the constitutional "
    "extraction path (FR-043)."
)


__all__ = [
    "CLAUSE_INITIAL_AUX",
    "CONSTRUCTOR_ORDER",
    "COORDINATORS",
    "DECLARABLE_CONSTRUCTIONS",
    "DEMONSTRATIVE_DETERMINERS",
    "DETERMINERS",
    "H6_STOP_CONDITION",
    "LEMMA_TABLE_DIGEST",
    "MODEL_REF",
    "MODEL_VERSION",
    "NOMINAL_SUFFIXES",
    "NO_LLM_IN_CONSTITUTIONAL_PATH",
    "PARSER_LIMITATIONS",
    "PARSER_VERSION",
    "PASSIVE_MIDDLES",
    "PINNED_CLAUSE_FIXTURES",
    "PINNED_CONFIGURATION_HASH",
    "PINNED_FIXTURE_DIGEST",
    "PINNED_PARTICIPLES",
    "POSSESSIVE_DETERMINERS",
    "PRONOUNS",
    "REFUSAL_ONLY_CONSTRUCTORS",
    "REFUSAL_REACHABILITY",
    "RELATIVE_ADVERBS",
    "RELATIVE_PRONOUNS",
    "SHALLOW_CAPABILITY",
    "SUBORDINATORS",
    "SYNTAX_PREPOSITIONS",
    "DeclaredChannel",
    "ParsedArgument",
    "ParserCapability",
    "ParserContractError",
    "PhraseCategory",
    "Refusal",
    "RefusalCode",
    "RefusalStage",
    "SlotBinding",
    "SyntacticReading",
    "assign_slots",
    "configuration_hash",
    "configuration_material",
    "fixture_digest",
    "fixture_outcome",
    "logical_candidate_id_of",
    "parse",
    "refusal_counts",
    "tokenise",
]








