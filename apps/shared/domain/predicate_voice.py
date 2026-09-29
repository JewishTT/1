"""``normalize_voice()`` - the ONLY function in the platform that assigns
canonical argument slots.

The implementation contract is
``specs/021-entity-relation-extraction-finalization/data-model.md`` parts 3 and
2.5, arbitrated by ``repair/ARBITRATION.md`` section 11 and
``repair/A2-identity-subsystem.md`` D3.

**P-CANON, the scope, verbatim from part 3.2:** this function performs **voice
handling only**. A passive clause with an overt ``by``-agent and its active
counterpart produce the same canonical argument assignment, and nothing else is
unified. Every other construction brief section 29 names receives its own
``ConstructionFrame``, so "John, who founded Acme" does not collapse with "John
founded Acme", "John is the CEO of Acme" does not collapse with "John, CEO of
Acme", and "John works at Acme" does not collapse with "John works for Acme" -
``at`` and ``for`` are different ``ArgumentMarker`` members, and deciding they
mark the same argument is a lexical-semantic claim that brief section 20 reserves
to explicit mapping.

The scope is this narrow for a directional reason: **under-merging is visible as
two candidates; over-merging is invisible as a wrong merge.** Brief section 43
permits one candidate from many signals only when they describe the same
relational configuration, so an unproven equivalence produces a merge that cannot
be undone and leaves no trace in the data. Voice demotion is deterministic
normalisation; a relative clause's relation to its matrix clause, a nominal's
relation to its clause and a copula's relation to a bare nominal are all *claims
about equivalence*, and claims about equivalence belong to the mapping layer,
where they are dated, attributed, revisable and able to be wrong in public.

Seven ordered steps, no judgement inside any of them: the parse is declared
elsewhere, frame detection is a table lookup over the declared construction, and
the lemma comes from the generated table. The algorithm is a pure function of its
three inputs, which is what makes two independent implementations able to agree
- and agreement requires the ambiguous cases to be *specified*, which is what the
two tie-breaks below and the row conditions do.

**Where this module refuses, and on what condition.** Every entry is a case the
sources leave open, and every entry names what would be needed to decide it. None
of them is resolved by a guess, and each is a distinct ``code`` so a corpus can
count the gap instead of hiding it:

============================================  ==========================================
code                                          stop condition
============================================  ==========================================
``unsupported_language``                      a language other than ``en`` ships in 021
``malformed_structure``                       no arguments, or a root labelling none
``unsupported_construction``                  a declared construction the table does not
                                              cover - no fallback, nearest match or retry
``slot_gap``                                  a required slot source has no overt
                                              argument; slots are positions in a parse
``unsupported_lemma``                         the morphology determines no lemma for
                                              the head
``auxiliary_is_not_the_predicate_head``       a passive whose head is the AUX; which
                                              participle was meant is not in the parse
``unsupported_marker``                        a function word outside the closed inventory
``no_configuration``                          fewer than two occupied slots - a
                                              decision, not a gap, and never padding
============================================  ==========================================

One decision is *recorded* rather than made, and it is worth naming because the
temptation to resolve it is strong: **no source states the test that identifies a
temporal complement.** Part 3.3's TB2 fixes the drop and the ``V2.drop_temporal``
trace entry, and part 1.2 class 7 fixes that temporality is not predicate
structure, but the test is absent - and a function-word list is a guess with a
concrete cost, because ``at`` and ``on`` are locatives as often as they are times
and ``at`` is the marker of the headless-PP construction. What is used instead is
the label a parser already emits from the parse with no semantic judgement, the UD
temporal-modifier family, documented at
:data:`TEMPORAL_POSITION_LABELS`. A complement outside it is **retained as a slot**,
which is the visible direction: an over-retained temporal argument is one extra
structural slot, while a wrongly dropped one is a lost participant with no trace.
"""


from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from domain.predicate_signature import (
    AUX_LEMMA_INVENTORY,
    PREDICATE_NORMALIZATION_VERSION,
    VOICE_NORMALIZATION_VERSION,
    ArgumentMarker,
    ArgumentSlot,
    ConstructionFrame,
    PredicateSignature,
    SignatureContractError,
    lemma_for,
    normalize_surface_for_fingerprint,
)

#: Only English ships in feature 021 (part 3, step V0). A cross-lingual pair is two
#: signatures, because merging them is a semantic claim.
SHIPPED_LANGUAGES: frozenset[str] = frozenset({"en"})

#: The closed inventory of UD temporal-modifier labels.
#:
#: Part 3's TB2 fixes the *drop* and the ``"V2.drop_temporal"`` trace entry, and
#: part 1.2 class 7 fixes that temporality is not predicate structure - but no
#: source states the *test* that identifies a temporal complement, and this
#: module will not invent one. The obvious candidate is a function-word list
#: containing ``at`` and ``on``, and that list is a guess with a concrete cost:
#: "John works at Acme" would lose its argument, and ``at`` is the marker of the
#: headless-PP construction.
#:
#: What is used instead is the label a parser already emits from the parse with no
#: semantic judgement: the UD temporal-modifier family. It is a grammar
#: inventory, versioned inside ``voice_normalization_version``, not a vocabulary.
#: A complement whose label is outside it is **retained as a slot**, which is the
#: visible direction: an over-retained temporal argument is one extra structural
#: slot, while a wrongly dropped one is a lost participant with no trace.
TEMPORAL_POSITION_LABELS: frozenset[str] = frozenset(
    {"nmod:tmod", "obl:tmod", "advmod:tmod"}
)


class SyntacticConstruction(StrEnum):
    """The parse-level construction, as **detected**.

    This is the INPUT vocabulary and it is a superset of :class:`ConstructionFrame`:
    the mapping from one to the other is :data:`CANONICAL_FRAME_BY_CONSTRUCTION`,
    and the only entry that differs is the passive demotion. ``OTHER`` is the
    producer's honest "I could not classify this" and it has no canonical frame,
    which is what turns a missing parser capability into a countable
    ``unsupported_construction`` rather than a silent default.
    """

    ACTIVE_CLAUSE = "active_clause"
    PASSIVE_WITH_AGENT = "passive_with_agent"
    PASSIVE_NO_AGENT = "passive_no_agent"
    COPULAR = "copular"
    COPULAR_WITH_NOUN_COMPLEMENT = "copular_with_noun_complement"
    BARE_NOMINAL = "bare_nominal"
    GENITIVE_NP = "genitive_np"
    APPOSITIVE_NP = "appositive_np"
    HEADLESS_PP = "headless_pp"
    RELATIVE_CLAUSE = "relative_clause"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class ArgumentObservation:
    """One argument as the PARSE sees it.

    Note what is absent: no role, no type, no semantic judgement.
    ``position_label`` is a dependency label, not a role, and
    ``head_lemma_hint`` is the token **as tokenised** - step V3 lemmatises the
    predicate head and nothing else.
    """

    position_label: str
    head_lemma_hint: str = ""
    function_word: str | None = None
    is_pronominal: bool = False

    def __post_init__(self) -> None:
        if not str(self.position_label).strip():
            raise SignatureContractError(
                "malformed_structure",
                "an argument observation needs a dependency label; a slot is a position in a "
                "parse, and an unlabelled argument has no position",
            )
        object.__setattr__(self, "position_label", str(self.position_label).strip())

    @property
    def is_temporal_complement(self) -> bool:
        return self.position_label in TEMPORAL_POSITION_LABELS


@dataclass(frozen=True, slots=True)
class SyntacticStructure:
    """The construction the producer detected, and the arguments it found."""

    construction: SyntacticConstruction
    arguments: tuple[ArgumentObservation, ...] = ()
    head_function_word: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "construction", SyntacticConstruction(self.construction))
        object.__setattr__(self, "arguments", tuple(self.arguments))


@dataclass(frozen=True, slots=True)
class DependencyEdge:
    """One UD-style edge, in document order. The ORDER is load-bearing (V2)."""

    governor_label: str
    dependent_label: str
    relation: str


@dataclass(frozen=True, slots=True)
class DependencyStructure:
    """The edges the parse produced, plus the label of the head carrying the reading."""

    edges: tuple[DependencyEdge, ...] = ()
    root: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "edges", tuple(self.edges))
        object.__setattr__(self, "root", str(self.root))


@dataclass(frozen=True, slots=True)
class PredicateHead:
    """The predicate head as observed, and its language.

    ``observed_form`` is the head **token** - "acquired", "acquire", "acquires" -
    and it is the head, not the auxiliary: step V3 refuses rather than guessing
    when the head is an AUX that is functioning as the head.
    """

    observed_form: str
    language: str = "en"


@dataclass(frozen=True, slots=True)
class CanonicalArgumentAssignment:
    """The output of :func:`normalize_voice`.

    Note what is NOT here, each for a stated reason (part 3.6): no
    ``commutative_slots`` (no grammar-derived construction is symmetric, and
    section 53 says verbatim "Do not infer symmetry merely because the extractor
    did not know direction"), no ``polarity`` (assertion structure, not predicate
    structure), no ``direction`` (derivable from slots plus commutativity, and an
    independent return value is a fork), no mention ref and no surface (the
    function is about the predicate; participants arrive separately), and no
    ``observed_construction_frame`` (it is evidence, and carrying it is exactly
    what keeps the two realisations apart).
    """

    construction_frame: ConstructionFrame
    canonical_argument_slots: tuple[ArgumentSlot, ...]
    argument_markers: tuple[ArgumentMarker, ...]
    normalization_trace: tuple[str, ...]

    @property
    def arity(self) -> int:
        return len(self.canonical_argument_slots)

    def rendered_predicate(self, predicate_lemma: str) -> str:
        """The derived ``normalized_predicate`` read, given the resolved lemma."""
        args = ",".join(
            f"{slot.token}:{'' if marker is ArgumentMarker.NOMARK else marker}"
            for slot, marker in zip(
                self.canonical_argument_slots, self.argument_markers, strict=True
            )
        )
        return f"{predicate_lemma}({args})"

    def to_signature(
        self, predicate_lemma: str, language: str = "en"
    ) -> PredicateSignature:
        """Build the signature this assignment describes.

        The only path from an assignment to a signature, so a signature cannot
        acquire a field the assignment does not justify. An assignment is
        refused here rather than padded: the arity floor of two is enforced by
        step V6 before this point, and a caller reaching it with fewer slots is
        asking for the padding part 3.7 forbids.
        """
        if len(self.canonical_argument_slots) < 2:
            raise SignatureContractError(
                "no_configuration",
                "a reading occupying fewer than two canonical slots is not a relational "
                "configuration. It is not padded to arity 2 with a placeholder and not given "
                "a null participant: 'Acme's ownership' is a property of Acme, not a relation "
                "between two mentions (part 3.7).",
            )
        return PredicateSignature(
            language=language,
            predicate_lemma=predicate_lemma,
            construction_frame=self.construction_frame,
            argument_markers=self.argument_markers,
            canonical_argument_slots=self.canonical_argument_slots,
            voice_normalization_version=VOICE_NORMALIZATION_VERSION,
            predicate_normalization_version=PREDICATE_NORMALIZATION_VERSION,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "construction_frame": str(self.construction_frame),
            "canonical_argument_slots": [slot.to_dict() for slot in self.canonical_argument_slots],
            "argument_markers": [str(marker) for marker in self.argument_markers],
            "normalization_trace": list(self.normalization_trace),
        }


# --------------------------------------------------------------------------- #
# The reading the steps operate on
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class _Reading:
    """The declared arguments, each carrying its document-order position.

    Step V2 takes arguments in ``dependency_structure.edges`` order, *not* in
    ``syntactic_structure.arguments`` order, so the edge position is resolved
    once here. An argument whose label matches no edge keeps its declaration index
    as a deterministic last resort rather than being dropped: the trace makes the
    case auditable and the tie-break below is total without it.
    """

    indexed: tuple[tuple[int, int, ArgumentObservation], ...]

    @classmethod
    def build(
        cls, arguments: Sequence[ArgumentObservation], edges: Sequence[DependencyEdge]
    ) -> _Reading:
        indexed = []
        for declaration_index, argument in enumerate(arguments):
            edge = next(
                (
                    position
                    for position, edge in enumerate(edges)
                    if edge.relation == argument.position_label
                ),
                None,
            )
            order = edge if edge is not None else len(edges) + declaration_index
            indexed.append((order, declaration_index, argument))
        return cls(indexed=tuple(indexed))

    @property
    def arguments(self) -> tuple[ArgumentObservation, ...]:
        return tuple(argument for _order, _index, argument in self.indexed)

    def order_of(self, argument: ArgumentObservation) -> int:
        for order, _index, candidate in self.indexed:
            if candidate is argument:
                return order
        raise SignatureContractError(  # pragma: no cover - identity over a frozen value
            "malformed_structure", "an argument is not part of this reading"
        )

    def labelled(self, *labels: str) -> list[ArgumentObservation]:
        wanted = set(labels)
        return [
            argument
            for _order, _index, argument in self.indexed
            if argument.position_label in wanted
        ]

    def others(self, *exclude: str) -> list[ArgumentObservation]:
        unwanted = set(exclude)
        return [
            argument
            for _order, _index, argument in self.indexed
            if argument.position_label not in unwanted
        ]

    def besides(self, *excluded: ArgumentObservation) -> list[ArgumentObservation]:
        """Every argument that is not one of ``excluded`` (identity, not equality)."""
        dropped = {id(argument) for argument in excluded}
        return [
            argument
            for _order, _index, argument in self.indexed
            if id(argument) not in dropped
        ]

    def tb2_order(self, arguments: Sequence[ArgumentObservation]) -> list[ArgumentObservation]:
        """Total order for the arguments of one slot source.

        Primary key is the ``ArgumentMarker`` token ascending, so a structurally
        unmarked direct object precedes every marked complement and ``in`` (a
        temporal complement) precedes ``to`` (a recipient) - which is what makes
        "John sold Acme to Microsoft in 2020" assign the asset before the
        recipient. The secondary key is the position label and the third is the
        document-order position, so the order is total rather than a taste.
        """
        return sorted(
            arguments,
            key=lambda argument: (
                (argument.function_word or "").casefold(),
                argument.position_label,
                self.order_of(argument),
            ),
        )


@dataclass(frozen=True, slots=True)
class _SlotSource:
    """One canonical slot: the argument that fills it, and whether the construction
    marks that position with a function word.

    One source is one slot, so a source holding two arguments is not a multi-occupant
    slot - it is two arguments competing for one position, which is coordination and
    is refused. Multiplicity is preserved rather than deduplicated so that the refusal
    is possible: dropping the extra argument would silently delete a participant.
    """

    arguments: tuple[ArgumentObservation, ...]
    marked: bool
    required: bool = False
    label: str = ""


_SlotPlan = Callable[[_Reading], tuple[_SlotSource, ...]]


def _one_per_slot(
    arguments: Sequence[ArgumentObservation], marked: bool, label: str
) -> tuple[_SlotSource, ...]:
    """One slot per argument, in the order given.

    V2 numbers the survivors ``A0, A1, ...`` contiguously, so an ordered list of
    arguments is an ordered list of slots - and each argument keeps its own
    ``function_word`` as its own marker, which is what makes a ditransitive
    ``sell(A0:,A1:,A2:to)`` rather than one argument per row of the table.

    Two arguments carrying the **same dependency label** are coordination, and
    coordination is refused here rather than numbered as two slots. That is the
    difference between "Acme is co-owned by John and Mary" - which needs a
    coordinated frame and a symmetry marker, neither of which exists - and a
    genuine ditransitive, whose arguments carry different labels.
    """
    _reject_coordination(arguments, label)
    return tuple(
        _SlotSource((argument,), marked=marked, label=label) for argument in arguments
    )


def _reject_coordination(
    arguments: Sequence[ArgumentObservation], label: str
) -> None:
    """Refuse a coordinated argument list with its named stop condition."""
    seen: set[str] = set()
    repeated: list[str] = []
    for argument in arguments:
        if argument.position_label in seen and argument.position_label not in repeated:
            repeated.append(argument.position_label)
        seen.add(argument.position_label)
    if not repeated:
        return
    raise SignatureContractError(
        "unsupported_construction",
        f"{label or 'a slot source'} holds two arguments labelled {repeated} "
        f"({[argument.position_label for argument in arguments]}). Coordination is a named "
        "stop condition, not a gap to paper over with a sort: brief section 29 lists no "
        "coordinated frame, and a coordinated frame without a declared symmetry marker would "
        "let the ordering invent a reading the structure does not license. Numbering them as "
        "two slots would assert a ditransitive nobody parsed. V2 refuses (A2 U5, part 4.4).",
    )



# --------------------------------------------------------------------------- #
# Part 3.4: the construction table, verbatim, in row order
# --------------------------------------------------------------------------- #


def _plan_passive_with_agent(reading: _Reading) -> tuple[_SlotSource, ...]:
    """Row 1. The one demotion in the whole system.

    ``A0`` is the ``by``-agent, because the demotion happens **at the frame**: the
    observed passive is re-read as an active clause whose subject is the agent.
    The ``nsubj:pass`` dependent is *consumed* by that demotion and re-emitted as
    the first remaining argument, which is the ``A1`` patient. The observed ``by``
    is recorded in the trace and in evidence, never in the signature - which is
    precisely why the passive and the active reach one ``identity_projection()``.
    """
    agent = reading.labelled("nmod:by")
    patient = reading.labelled("nsubj:pass")
    remainder = [
        argument
        for argument in reading.tb2_order(reading.others("nmod:by", "nsubj:pass"))
        if not argument.is_temporal_complement
    ]
    return (
        _SlotSource(tuple(agent), marked=False, required=True, label="A0=nmod:by"),
        *_one_per_slot(
            patient + remainder,
            True,
            "A1..=nsubj:pass re-emitted, then the participle's remaining arguments",
        ),
    )


def _plan_copular(reading: _Reading) -> tuple[_SlotSource, ...]:
    """Rows 2 and 3. A complement that is an NP with an ``of``-PP is followed
    through that PP; otherwise the complement head itself is ``A1``."""
    subject = reading.labelled("nsubj")
    complement = reading.others("nsubj")
    through_of = [
        argument for argument in complement if argument.position_label == "nmod:of"
    ]
    second = through_of or complement[:1]
    return (
        _SlotSource(tuple(subject), marked=False, required=True, label="A0=nsubj"),
        _SlotSource(
            tuple(second),
            marked=bool(through_of),
            required=True,
            label="A1=complement's nmod:of head, else the complement head",
        ),
    )


def _plan_active_transitive(reading: _Reading) -> tuple[_SlotSource, ...]:
    """Rows 4 and 5 share one plan; only the frame differs.

    ``A0`` is the subject - a canonical-active subject is structurally unmarked,
    so its marker is ``NOMARK`` - and every further argument takes its own
    ``function_word``. Temporal complements are dropped here and recorded, so the
    drop is auditable rather than invisible: brief section 109 case D's
    ``time = 2020`` has to stay recoverable on the candidate's
    ``TemporalHypothesis``, and the trace is how the signature layer records that
    it saw the year and declined to make it part of the predicate.
    """
    subject = reading.labelled("nsubj")
    remainder = [
        argument
        for argument in reading.tb2_order(reading.others("nsubj"))
        if not argument.is_temporal_complement
    ]
    return (
        _SlotSource(tuple(subject), marked=False, required=True, label="A0=nsubj"),
        *_one_per_slot(remainder, True, "A1..=remaining, temporal complements dropped"),
    )


def _plan_bare_nominal(reading: _Reading) -> tuple[_SlotSource, ...]:
    """Row 6. ``A0`` is the governor NP head, ``A1`` the ``of`` complement."""
    governor = reading.others("nmod:of")
    of_complement = reading.labelled("nmod:of")
    return (
        _SlotSource(tuple(governor), marked=False, required=True, label="A0=the NP head"),
        _SlotSource(
            tuple(of_complement), marked=True, required=True, label="A1=nmod:of head"
        ),
    )


def _plan_genitive(reading: _Reading) -> tuple[_SlotSource, ...]:
    """Row 7. The reversal is the point: argument structure, not word order.

    ``A0`` is the head NP the genitive modifies - which may be the surface-left or
    the surface-right NP - and ``A1`` is the genitive itself. "Acme's founder John
    Smith" therefore reads as ``(A0: John Smith, A1: Acme)``: the founder is the
    subject of the claim and Acme the object of it.

    ``A0`` is optional on purpose. "Acme's ownership" has no head NP on the
    possessed side, so one slot is occupied and step V6 answers
    ``no_configuration`` - a decision about a well-parsed reading, not a gap. An
    unoccupied ``A0`` must not become a ``SLOT_GAP``, which would misreport a
    decision as a malformed structure.
    """
    genitive = reading.labelled("case:gen", "case:genitive")
    possessed = reading.besides(*genitive)
    return (
        _SlotSource(
            tuple(possessed), marked=False, required=False, label="A0=the possessed-side head NP"
        ),
        _SlotSource(tuple(genitive), marked=False, required=True, label="A1=the genitive head"),
    )


def _plan_appositive(reading: _Reading) -> tuple[_SlotSource, ...]:
    """Row 8. The matrix NP and the appositive's ``of`` complement."""
    matrix = reading.others("nmod:of")
    of_complement = reading.labelled("nmod:of")
    return (
        _SlotSource(tuple(matrix), marked=False, required=True, label="A0=the matrix NP head"),
        _SlotSource(tuple(of_complement), marked=True, required=True, label="A1=nmod:of head"),
    )


def _plan_headless_pp(reading: _Reading) -> tuple[_SlotSource, ...]:
    """Row 9. ``A0`` is the ``pobj`` and carries the preposition; ``A1`` is the
    subject the producing channel declares for the governing slot. A headless PP
    has no ``nsubj`` of its own, so the channel - not the grammar - supplies it,
    which is why the marker on ``A0`` is the whole of this row's evidence."""
    pobj = reading.labelled("pobj")
    subject = reading.others("pobj")
    return (
        _SlotSource(tuple(pobj), marked=True, required=True, label="A0=pobj"),
        _SlotSource(tuple(subject), marked=False, required=True, label="A1=declared subject"),
    )


def _plan_relative_clause(reading: _Reading) -> tuple[_SlotSource, ...]:
    """Row 10. The clause's own arguments, in row 4's order.

    The matrix NP is **not** an argument of the clause, and that exclusion is the
    whole reason "John, who founded Acme" does not collapse with "John founded
    Acme". Collapsing them needs the inference "the matrix NP is the relative
    clause's subject", which is true in the common case and false in the
    reduced-relative and adjunct cases - and a rule that is usually right is a
    guess. Here the guarantee is the producer's: the arguments of a relative
    clause are the clause's own, and the matrix NP is not among them. The frame is
    ``RELATIVE_CLAUSE`` regardless, so the two readings stay apart even when a
    producer declares the same arguments for both.
    """
    return _plan_active_transitive(reading)


@dataclass(frozen=True, slots=True)
class ConstructionRow:
    """One row of the construction table.

    A row may not be in the table unless it is testable syntactically (part 3.3,
    TB1): a row whose condition cannot be decided from the declared parse is a
    judgement dressed as a rule. ``condition`` is therefore a named predicate over
    the declared arguments, and a row with ``condition=None`` matches on the
    declared construction alone.

    ``drops_temporal_complements`` records whether the row's plan discards a
    temporal argument, so ``V2.drop_temporal`` enters the trace only when a
    complement was really dropped - a trace entry that appears unconditionally
    would be a claim the record cannot support.
    """

    number: int
    construction: SyntacticConstruction
    condition_name: str
    frame: ConstructionFrame
    plan: _SlotPlan
    condition: Callable[[_Reading], bool] | None = None
    drops_temporal_complements: bool = False
    note: str = ""

    def matches(self, reading: _Reading) -> bool:
        return self.condition is None or self.condition(reading)


def _has_subject(reading: _Reading) -> bool:
    return bool(reading.labelled("nsubj"))


def _has_further_argument(reading: _Reading) -> bool:
    return bool(reading.others("nsubj"))


def _has_of_complement(reading: _Reading) -> bool:
    return bool(reading.labelled("nmod:of"))


def _has_genitive(reading: _Reading) -> bool:
    return bool(reading.labelled("case:gen", "case:genitive"))


def _has_pobj(reading: _Reading) -> bool:
    return bool(reading.labelled("pobj"))


def _is_copular(reading: _Reading) -> bool:
    """Row 2's syntactic test: a subject and a predicate complement exist.

    The complement is a bare NP *as a constituent*; the row's plan still follows
    the complement's ``of``-PP when there is one, which is how "John is the CEO of
    Acme" becomes ``(A0: John, A1: Acme, of)`` while the head is the complement
    noun rather than the ``of``-PP's object.
    """
    return _has_subject(reading) and _has_further_argument(reading)


def _is_copular_noun_complement(reading: _Reading) -> bool:
    """Row 3's syntactic test: the complement is a nominal with an adjacent ``of``-PP
    ("a founder of Acme"), as opposed to row 2's bare NP.

    The test is structural - an ``of``-complement exists - and nothing more.
    Whether the complement noun is *derived* is not decidable from an
    :class:`ArgumentObservation` (its four fields are a dependency label, a token,
    a function word and a pronominal flag), so the narrower condition is the one
    applied. The frame still separates rows 2 and 3, so no merge is created by
    the narrowing.
    """
    return _has_subject(reading) and _has_further_argument(reading) and _has_of_complement(reading)


def _is_bare_nominal(reading: _Reading) -> bool:
    """Row 6: an NP head alongside an ``of`` complement."""
    return bool(reading.others("nmod:of")) and _has_of_complement(reading)


def _is_appositive(reading: _Reading) -> bool:
    """Row 8: a matrix NP alongside an appositive ``of`` complement."""
    return bool(reading.others("nmod:of")) and _has_of_complement(reading)


CONSTRUCTION_TABLE: tuple[ConstructionRow, ...] = (
    ConstructionRow(
        number=1,
        construction=SyntacticConstruction.PASSIVE_WITH_AGENT,
        condition_name="head is a member of the closed AUX set; a nsubj:pass and a nmod:by exist",
        frame=ConstructionFrame.VERB_ACTIVE_TRANSITIVE,
        plan=_plan_passive_with_agent,
        note="THE DEMOTION: an observed passive frame is never carried on the signature.",
    ),
    ConstructionRow(
        number=2,
        construction=SyntacticConstruction.COPULAR,
        condition_name="head is in the closed COPULA set; a nsubj and a bare-NP complement exist",
        frame=ConstructionFrame.COPULA_PREDICATIVE,
        plan=_plan_copular,
        condition=_is_copular,
    ),
    ConstructionRow(
        number=3,
        construction=SyntacticConstruction.COPULAR_WITH_NOUN_COMPLEMENT,
        condition_name="as row 2 but the complement is a nominal beside an of-PP",
        frame=ConstructionFrame.COPULA_PREDICATIVE_NOUN,
        plan=_plan_copular,
        condition=_is_copular_noun_complement,
    ),
    ConstructionRow(
        number=4,
        construction=SyntacticConstruction.ACTIVE_CLAUSE,
        condition_name="a non-AUX head; a nsubj exists; at least one further argument exists",
        frame=ConstructionFrame.VERB_ACTIVE_TRANSITIVE,
        plan=_plan_active_transitive,
        condition=_has_further_argument,
        drops_temporal_complements=True,
    ),
    ConstructionRow(
        number=5,
        construction=SyntacticConstruction.ACTIVE_CLAUSE,
        condition_name="as row 4 with no further argument",
        frame=ConstructionFrame.VERB_ACTIVE_INTRANSITIVE,
        plan=_plan_active_transitive,
        condition=lambda reading: not _has_further_argument(reading),
        drops_temporal_complements=True,
        note="Always yields no_configuration at V6: a one-argument clause states a property.",
    ),
    ConstructionRow(
        number=6,
        construction=SyntacticConstruction.BARE_NOMINAL,
        condition_name="no finite head; the governor is an NP whose head noun has an nmod:of",
        frame=ConstructionFrame.NOMINAL_OWNER_OF,
        plan=_plan_bare_nominal,
        condition=_is_bare_nominal,
    ),
    ConstructionRow(
        number=7,
        construction=SyntacticConstruction.GENITIVE_NP,
        condition_name="an NP with a case:gen dependent",
        frame=ConstructionFrame.NOMINAL_POSSESSIVE,
        plan=_plan_genitive,
        condition=_has_genitive,
    ),
    ConstructionRow(
        number=8,
        construction=SyntacticConstruction.APPOSITIVE_NP,
        condition_name="a comma-delimited np:appos dependent whose head noun has an nmod:of",
        frame=ConstructionFrame.APPOSITIVE_ROLE,
        plan=_plan_appositive,
        condition=_is_appositive,
    ),
    ConstructionRow(
        number=9,
        construction=SyntacticConstruction.HEADLESS_PP,
        condition_name="a PP with no nsubj whose governor declares a subject slot",
        frame=ConstructionFrame.PREP_PHRASE_HEAD,
        plan=_plan_headless_pp,
        condition=_has_pobj,
    ),
    ConstructionRow(
        number=10,
        construction=SyntacticConstruction.RELATIVE_CLAUSE,
        condition_name="a reld:cl dependent of an NP",
        frame=ConstructionFrame.RELATIVE_CLAUSE,
        plan=_plan_relative_clause,
        drops_temporal_complements=True,
    ),
)

#: The row-order index of :data:`CONSTRUCTION_TABLE`: declared construction to
#: canonical frame, first row winning (TB1). ``ACTIVE_CLAUSE`` indexes to row 4's
#: frame; the row-5 narrowing to ``VERB_ACTIVE_INTRANSITIVE`` is a *condition* the
#: row loop applies, not a second entry, which is why one map cannot hold it.
#:
#: The only entry that differs from the observed construction is the passive
#: demotion, and that difference is the whole of P-CANON.
CANONICAL_FRAME_BY_CONSTRUCTION: Mapping[SyntacticConstruction, ConstructionFrame] = (
    MappingProxyType(
        {row.construction: row.frame for row in sorted(CONSTRUCTION_TABLE, key=lambda r: r.number)}
    )
)


# --------------------------------------------------------------------------- #
# The algorithm
# --------------------------------------------------------------------------- #


def normalize_voice(
    predicate: PredicateHead,
    syntactic_structure: SyntacticStructure,
    dependency_structure: DependencyStructure,
) -> CanonicalArgumentAssignment:
    """The ONLY function in the platform that assigns canonical argument slots.

    Steps, exact and in order:

    * **V0 ``V0.validate``** - ``language`` must be a shipped language, the
      argument list must be non-empty, and ``root`` must label an argument.
      Failure: ``unsupported_language`` / ``malformed_structure``.
    * **V1 ``V1.frame``** - the row-order lookup over
      :data:`CONSTRUCTION_TABLE`. For ``PASSIVE_WITH_AGENT`` the result is
      ``VERB_ACTIVE_TRANSITIVE``: **the demotion happens here, at the frame, not
      later**. Failure: ``unsupported_construction``.
    * **V2 ``V2.assign_slots``** - take the row's slot sources **in the order the
      row states them**, drop every source the demotion consumed, and number the
      survivors ``A0, A1, ...`` contiguously. Failure: ``slot_gap``,
      ``unsupported_construction`` (coordination).
    * **V3 ``V3.lemmatise```` - resolve the lemma from the generated table.
      Applied to the **predicate head only**: never to a participant, never to a
      function word, never to a second argument. Failure: ``unsupported_lemma``.
    * **V4 ``V4.markers``** - one marker per slot, in slot order, from the row's
      marker column. A function word outside the closed inventory is a failure,
      **not** ``NOMARK``. Failure: ``unsupported_marker``.
    * **V5 ``V5.trace``** - the ordered step ids actually executed.
      Corpus-visible, **never identity**. V5 is not an element of its own output and V6
      adds none either: a step that only *checks* has not transformed anything, and a trace
      entry that appeared unconditionally would be a claim the record cannot support. The
      two conditional entries that DO appear - ``V2.drop_temporal`` and
      ``V2.observed_by`` - are there because something was actually dropped and something
      was actually observed.
    * **V6 ``V6.arity``** - fewer than two occupied slots is
      ``no_configuration``. Failure: ``no_configuration``.

    The two tie-breaks are specified rather than left to taste, because "two
    independent implementations must agree" is only achievable for the ambiguous
    cases:

    * **TB1** the table is consulted in row order and the first match wins, so
      ``COPULAR`` precedes ``ACTIVE_CLAUSE``. Within one declared construction the
      order is the whole of the decision; *which* construction a clause is is a
      parse-level fact the producer declares, and the ADJ-complement case that
      would make that a judgement is not decidable from the four fields of
      :class:`ArgumentObservation` - see the module report's refusal list.
    * **TB2** arguments are taken in ``dependency_structure.edges`` order (pinned
      document order), not in ``syntactic_structure.arguments`` order, and where
      that order is ambiguous under the marker the tie-break is ``ArgumentMarker``
      ascending then ``position_label`` ascending, byte-wise. ``in`` < ``to``, so
      ``in 2020`` is considered before ``to Microsoft``; the temporal complement
      is then dropped and the trace records ``V2.drop_temporal`` so the drop is
      auditable.
    """
    trace: list[str] = []
    reading = _Reading.build(syntactic_structure.arguments, dependency_structure.edges)

    # --- V0.validate ------------------------------------------------------- #
    trace.append("V0.validate")
    _validate(predicate, syntactic_structure, dependency_structure, reading)

    # --- V1.frame ---------------------------------------------------------- #
    trace.append("V1.frame")
    row = _resolve_row(syntactic_structure.construction, reading)
    frame = row.frame

    # --- V2.assign_slots --------------------------------------------------- #
    trace.append("V2.assign_slots")
    sources = row.plan(reading)
    if row.drops_temporal_complements and any(
        argument.is_temporal_complement for argument in reading.arguments
    ):
        trace.append("V2.drop_temporal")
    if row.number == 1:
        trace.extend(("V2.observed_by", "by"))
    slots, filled = _number_slots(sources)

    # --- V3.lemmatise ------------------------------------------------------ #
    # Resolved and discarded here: the lemma is the signature's, not the
    # assignment's (part 3.6 - no predicate datum is returned). Running the step
    # is not optional, though, because V3's refusals - an unsupported lemma, an AUX
    # posing as the head - are how a reading is prevented from reaching V4 with an
    # undeclared predicate. ``normalize_predicate`` below reads the same lemma for
    # the signature; ``_lemmatise`` is pure, so the two cannot disagree.
    trace.append("V3.lemmatise")
    _lemmatise(predicate, syntactic_structure)

    # --- V4.markers -------------------------------------------------------- #
    trace.append("V4.markers")
    markers = _markers(sources, filled)

    # --- V5.trace then V6.arity -------------------------------------------- #
    if len(slots) < 2:
        raise SignatureContractError(
            "no_configuration",
            f"the reading occupies {len(slots)} canonical slot(s) "
            f"({[slot.token for slot in slots]}) after construction "
            f"{row.construction.value!r} row {row.number}. A reading occupying fewer than 2 "
            "canonical slots yields no_configuration: it is not padded to arity 2 with a "
            "placeholder and not given a null participant. This is a decision about a "
            "well-parsed reading, which is why it is a different code from "
            "unsupported_construction (part 3.7).",
        )

    return CanonicalArgumentAssignment(
        construction_frame=frame,
        canonical_argument_slots=slots,
        argument_markers=markers,
        normalization_trace=tuple(trace),
    )


def normalize_predicate(
    predicate: PredicateHead,
    syntactic_structure: SyntacticStructure,
    dependency_structure: DependencyStructure,
) -> PredicateSignature:
    """``normalize_voice`` followed by the signature it describes.

    The one entry point a producer needs, and the one normaliser in the platform
    (part 1.6): there is no second place where a predicate is normalised, so the
    derived ``normalized_predicate`` / ``normalized_form`` reads have exactly one
    thing to be a view of. A signature is produced here and never re-derived from a
    mapping, a registry, an operator list or a learned model.
    """
    assignment = normalize_voice(predicate, syntactic_structure, dependency_structure)
    lemma = _lemmatise(predicate, syntactic_structure)
    return assignment.to_signature(lemma, language=predicate.language)


def _validate(
    predicate: PredicateHead,
    syntactic_structure: SyntacticStructure,
    dependency_structure: DependencyStructure,
    reading: _Reading,
) -> None:
    """V0. The parse must be usable before any of it is interpreted."""
    language = str(predicate.language or "").strip().lower()
    if language not in SHIPPED_LANGUAGES:
        raise SignatureContractError(
            "unsupported_language",
            f"language={language!r} is not shipped in feature 021. A cross-lingual pair is "
            "two signatures, because merging them is a semantic claim that section 20 "
            "reserves to explicit mapping",
        )
    if not syntactic_structure.arguments:
        raise SignatureContractError(
            "malformed_structure",
            "a reading with no arguments carries no relational configuration; the parse "
            "produced nothing to normalise",
        )
    if not any(
        argument.position_label == dependency_structure.root
        for argument in reading.arguments
    ):
        raise SignatureContractError(
            "malformed_structure",
            f"root={dependency_structure.root!r} labels no argument of this reading, so the "
            "head carrying the reading cannot be identified. V2 orders arguments by "
            "dependency edges and needs a root to anchor them",
        )


def _resolve_row(
    construction: SyntacticConstruction, reading: _Reading
) -> ConstructionRow:
    """V1. Row order, first match wins (TB1)."""
    for row in CONSTRUCTION_TABLE:
        if row.construction is not construction:
            continue
        if row.matches(reading):
            return row
    raise SignatureContractError(
        "unsupported_construction",
        f"construction={construction.value!r} matched no row of the construction table, and "
        "the table is total for the constructions it supports. NO signature is produced: this "
        "is never resolved by a fallback frame, a nearest-match frame, a default frame, a "
        "retry, a lexical-identity shortcut or a syntactic guess. The reason code is persisted "
        "on the signal so the corpus counts the gap by construction instead of hiding it "
        "(part 3.5, brief section 30).",
    )


def _number_slots(sources: Sequence[_SlotSource]) -> tuple[tuple[ArgumentSlot, ...], list[bool]]:
    """V2. Contiguous numbering, multiplicity preserved, coordination refused."""
    slots: list[ArgumentSlot] = []
    filled: list[bool] = []
    for source in sources:
        arguments = tuple(argument for argument in source.arguments if not argument.is_pronominal)
        if not arguments:
            if source.required:
                raise SignatureContractError(
                    "slot_gap",
                    f"{source.label or 'a declared slot source'} yielded no overt argument. "
                    "Slots are positions in a parse, so an absent or elided argument cannot be "
                    "numbered, and numbering around the hole would produce a material neither "
                    "convention can re-derive",
                )
            filled.append(False)
            continue
        if len(arguments) > 1:
            _reject_coordination(arguments, source.label)
        slots.append(ArgumentSlot(len(slots)))
        filled.append(True)
    return tuple(slots), filled


def _lemmatise(predicate: PredicateHead, syntactic_structure: SyntacticStructure) -> str:
    """V3. The predicate head only - never a participant, a function word or a
    second argument.

    An AUX posing as the predicate head is refused rather than resolved. The rule
    is "an AUX is not the predicate head when the clause has a participle; the
    participle is", and in a passive clause that is not a matter of taste: the AUX
    is the clause's head and the participle carries the reading, so naming the AUX
    would key the logical identity on a word that encodes nothing about the
    relation. Which participle was meant is not in the declared parse, so the
    reading is refused - ``normalized_predicate`` is ``""`` and the signal carries
    an explicit basis instead (part 3.5).
    """
    head = normalize_surface_for_fingerprint(predicate.observed_form)
    lemma = lemma_for(head)
    if (
        lemma in AUX_LEMMA_INVENTORY
        and syntactic_structure.construction is SyntacticConstruction.PASSIVE_WITH_AGENT
    ):
        raise SignatureContractError(
            "auxiliary_is_not_the_predicate_head",
            f"head={head!r} resolves to the auxiliary {lemma!r}, and a passive clause's "
            "predicate head is its participle - the AUX is the clause's head, not the "
            "relation's. V3 lemmatises the predicate head only, and which participle was meant "
            "is not in the declared parse, so the reading is refused rather than resolved. The "
            "producer must name the participle (part 3.3 V3).",
        )
    return lemma


def _markers(sources: Sequence[_SlotSource], filled: Sequence[bool]) -> tuple[ArgumentMarker, ...]:
    """V4. One marker per occupied slot, in slot order, from the row's column."""
    markers: list[ArgumentMarker] = []
    for source, occupied in zip(sources, filled, strict=True):
        if not occupied:
            continue
        argument = next(
            argument for argument in source.arguments if not argument.is_pronominal
        )
        if not source.marked or not argument.function_word:
            markers.append(ArgumentMarker.NOMARK)
            continue
        markers.append(_marker_for(argument.function_word))
    return tuple(markers)


def _marker_for(function_word: str) -> ArgumentMarker:
    """Form-normalise a function word, and refuse one outside the closed inventory."""
    normalised = normalize_surface_for_fingerprint(function_word)
    try:
        return ArgumentMarker(normalised)
    except ValueError as exc:
        raise SignatureContractError(
            "unsupported_marker",
            f"function word {function_word!r} is not a member of the closed ArgumentMarker "
            "inventory. The only lawful normalisation is FORM normalisation (NFKC, casefold) "
            "over a closed set, never cross-word folding: a field that folded 'at' to 'for' "
            "would be the forbidden synonym table under another name, and deciding they mark "
            "the same argument is a lexical-semantic claim that section 20 reserves to explicit "
            "mapping. No marker is invented and NOMARK is not a fallback (part 3.3 V4).",
        ) from exc


__all__ = [
    "CANONICAL_FRAME_BY_CONSTRUCTION",
    "CONSTRUCTION_TABLE",
    "SHIPPED_LANGUAGES",
    "TEMPORAL_POSITION_LABELS",
    "ArgumentObservation",
    "CanonicalArgumentAssignment",
    "ConstructionRow",
    "DependencyEdge",
    "DependencyStructure",
    "PredicateHead",
    "SyntacticConstruction",
    "SyntacticStructure",
    "normalize_predicate",
    "normalize_voice",
]
