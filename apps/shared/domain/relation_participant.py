"""One end of an observed relational configuration, as a first-class value type.

Feature 021, spec FR-008 and FR-009; ``data-model.md`` part 6; ``repair/A2-identity-subsystem.md``
D1.2 and D4.3; ``repair/ARBITRATION.md`` §6 and §14 rule 5.

**Why the type exists at all.** Before it, a participant was one of two string columns, which
meant the platform could only say a thing about a *pair* of mentions however many the sentence
had. ``John sold Acme to Microsoft in 2020`` has four ends, and a two-column record of it is
either lossy or a lie: it keeps two ends and drops two, with no trace that two were dropped, so
the next reader cannot tell a binary relation from a four-ary one whose ends went missing. A
tuple of these is the fix, and it is a *type* rather than a JSON blob because three of the six
fields are load-bearing and must not be optional, misspelled or JSONB-decoded into a string.

**The field list, and why it is six and not five.** Three artefacts disagree and
``ARBITRATION.md`` §14 rule 5 left the conflict undecided; this is the reconciliation, recorded
here because the choice is not recoverable from the code:

===============================  ==========================================================
Artefact                         Fields named
===============================  ==========================================================
``spec.md`` FR-009 / T013        ``mention_ref``, ``slot``, ``role_hypothesis``, ``ordinal``,
                                 ``confidence``  (5)
``data-model.md`` part 6         the same five **plus** ``argument_shape``  (6)
FR-012                           **requires** ``argument_shape`` (it is the target of
                                 ``QUANTITY → RelationParticipant.argument_shape = "value"``)
FR-050 / FR-066                  not expressible without it
===============================  ==========================================================

**Six, following ``data-model.md``, and the instruction that settles it.** FR-009 is not
contradicted so much as incomplete: it names the five fields that were known when it was
written, and every requirement added afterwards - FR-012's aspect mapping, FR-050's value
argument shapes, FR-066's deferred raw slots - reaches for the sixth. An enumeration that
omits a field three live requirements need is not a narrower reading, it is a contract that
cannot express them, and FR-012 in particular is a *mapping table* whose only destination for
``QUANTITY`` is this attribute. Had the answer been five, ``QUANTITY`` would have had nowhere
to go except back into ``SignalKind``, which is the exact defect FR-012 was written to remove.
So: the union is six, and ``argument_shape`` carries the default ``"entity"`` that
``data-model.md`` specifies, which means a producer that observed nothing about the shape
asserts the ordinary one rather than leaving a hole.

**What enters identity, and what is deliberately kept out.** :meth:`to_identity` digests
``mention_ref``, ``slot`` and ``ordinal`` and **nothing else**, and the three exclusions are
each load-bearing rather than tidy - a fourth field in this list would be a defect, not a
completion:

- :attr:`role_hypothesis` is **evidence only** (``data-model.md`` part 2.1). Two producers
  guessing "seller" and "vendor" for one slot must produce one logical candidate; a free-text
  role in identity would fork it on a spelling difference.
- :attr:`confidence` is **a projection, never identity material**. The reason is the platform's
  standing one: a re-scoring pass must not mint a new relation, or every ranking change forks
  the graph.
- :attr:`argument_shape` is **a fact about a referent, not about the predicate**, and is
  excluded for a sharper reason than tidiness: a type-layer reclassification (this participant
  is a ``value`` rather than an ``entity``) is another subsystem's change, and coupling two
  subsystems' edits through one digest means a type correction silently forks a relational
  identity (``A2`` D1.2, N6).

**A mention, never an entity.** :attr:`mention_ref` is a *deferred participant reference* into
the mention index (FR-016, brief §25), not a resolved entity and not a minted mention id. This
module has resolved nothing and cannot: resolution is a later decision with its own record.

**A mention, or a retrieval, and Phase 4C made the difference a field rather than a string.**
:attr:`mention_ref` addresses one of two namespaces and until 4C nothing on the participant said
which: a ``surface@…`` occurrence that the mention layer resolves to an ``MN-``, or a
``capture:<ref>`` retrieval that is *already* a durable ``CAP-`` and must not be given a second
identity. The decision, the rejected alternative and the reason are on
:class:`ParticipantEndKind`; the short version is that minting an ``MN-`` for a document would
put a second id on one fact and would have no position to be a mention at, because a retrieval is
the scope every position is measured against rather than something measured against one.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from domain.mention_occurrence_index import (
    DeferredCaptureAddress,
    parse_deferred_address,
)
from domain.predicate_signature import ArgumentSlot

#: The smallest relational configuration. Not a stylistic floor: a one-participant reading
#: states a *property* of one thing ("Acme's ownership"), not a relation between mentions, and
#: padding it to two would fabricate a participant. ``A2`` D3.7 names the refusal
#: ``NO_CONFIGURATION`` for exactly this, and the signal contract raises
#: ``signal_arity_below_two`` rather than widening this floor.
MIN_PARTICIPANTS = 2

#: The referent shapes :attr:`RelationParticipant.argument_shape` may take, in the vocabulary
#: :mod:`domain.predicate_signature` already uses for a participant's shape. Open on purpose -
#: a referent's shape is a type-layer fact that grows, and freezing it here would make every
#: new value type a migration. It is **excluded from identity** regardless, so a new shape can
#: never re-key a relation.
DEFAULT_ARGUMENT_SHAPE = "entity"


class ParticipantEndKind(StrEnum):
    """What kind of thing this end of a configuration is - Phase 4C, and the answer is two.

    A capture end is a **fetch event**, not a mention, and Phase 4C had to decide what to do
    about that. The decision is this enumeration, and the alternative it rejects is recorded
    because the alternative is the one that looks tidy:

    **Rejected: a first-class document mention.** Minting an ``MN-`` for the document a
    ``<meta name="author">`` tag belongs to would put a second identity on one fact. The
    capture already has one - :attr:`domain.capture.Capture.capture_id`, a real
    content-addressed durable id - and two ids for one fact is exactly the defect the
    occurrence/retrieval split exists to prevent. Worse, a "mention" of a whole document has no
    position: a mention is an occurrence *at a span in a segment*, and the retrieval is the
    scope every such span is measured against, so the document would be its own container and
    its own content. :meth:`domain.mention_occurrence_index.MentionOccurrenceIndex
    .require_occurrence` already refuses it by name - ``mention_capture_is_not_a_mention`` -
    with the stop condition in the message, and this enumeration is what makes the refusal
    unnecessary rather than routine.

    **Chosen: a distinct participant kind, not required to resolve to ``MN-``.** A
    :attr:`RETRIEVAL` end is addressable, is already durable, and is carried through a binding
    unchanged. :attr:`OCCURRENCE` is the ordinary end and is the one the mention layer resolves.
    Neither is a special case in the binder: it reads this field, and a record that lies about
    its own end kind is refused on construction.

    **    And it is inferred, not merely declared.** ``None`` - the default - means *read the
    address*, and the address grammar already distinguishes the two namespaces
    (``surface...`` versus ``capture:<ref>``). Inference rather than a required argument because
    the five producers that mint a capture address all build their participants without this
    field, and requiring them to say it would be requiring them to restate what their own
    address already says. An **explicit** value that contradicts the address is refused with
    ``participant_end_kind_mismatch``: a record that claims an occurrence and addresses a
    retrieval is a record that will fail later, somewhere that cannot say why.
    """

    OCCURRENCE = "occurrence"
    RETRIEVAL = "retrieval"


def end_kind_of(reference: str) -> ParticipantEndKind:
    """The end kind a reference addresses, from the address grammar and nothing else.

    ``None`` — an unreadable address — and any real mention id read as :attr:`OCCURRENCE`,
    because that is the end the mention layer is for and an address nobody can read is not
    evidence of anything else. A ``capture:`` address is the only :attr:`RETRIEVAL`, and it is
    recognised structurally (by the parsed address type) rather than by a string test, so a
    surface that happens to start with the word ``capture`` is not promoted to one.
    """
    parsed = parse_deferred_address(str(reference or ""))
    if isinstance(parsed, DeferredCaptureAddress):
        return ParticipantEndKind.RETRIEVAL
    return ParticipantEndKind.OCCURRENCE


class ParticipantContractError(ValueError):
    """A participant is not coherent as stated.

    A ``ValueError`` carrying a stable snake_case ``code``, matching
    :class:`domain.predicate_signature.SignatureContractError`,
    :class:`domain.relation_candidate.CandidateContractError` and the rest of the platform, so
    one caller can switch on any of them by ``.code`` rather than by type. The count matters as
    much as the code: a refusal nobody can count is a silent drop, and a silent drop of a
    participant is a lost end of a relation.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


@dataclass(frozen=True)
class RelationParticipant:
    """One observed end of a relational configuration (FR-009).

    Frozen and content-participating, not content-addressed: a participant has no id of its
    own, because what makes it a participant is its *position* in one signal's ``participants``
    tuple. A ``mention_ref`` alone is not a participant - the same mention fills different slots
    in different readings, and ``Acme`` the subject of one sentence and the object of another is
    two participants that share an end.

    :attr:`slot` is a structural :class:`~domain.predicate_signature.ArgumentSlot` (``A0``,
    ``A1``, ...) and **not** a role name. The distinction is the whole reason two producers can
    agree: the parser says "the ``nmod:by`` phrase", not "the buyer", and a free-text role in
    the identity term would make "seller" and "vendor" two different relations.
    """

    #: Which mention this end is. A deferred reference into the mention index, never an entity
    #: id and never a minted mention id (FR-016, FR-019, constitution Invariant 2).
    mention_ref: str
    #: Which canonical argument position this end fills in the reading.
    slot: ArgumentSlot
    #: A role hypothesis, **evidence only and never identity material** (``data-model.md``
    #: part 2.1). Free text on purpose: it is a producer's guess at a name, and it is kept
    #: because a reader may find the guess useful while no identity term may depend on it.
    role_hypothesis: str = ""
    #: Position as **observed**, not as canonicalised. Distinct from the tuple position, and
    #: deliberately so: two occupants of one slot are ordered by this (``A2`` D4.4), and a
    #: collection whose canonical order is a tie-break is one where the tie-break is the fact.
    ordinal: int = 0
    #: The producer's certainty about **its own reading** of this end. Not a probability that
    #: anything holds, and not identity material - see the module docstring.
    confidence: float = 0.0
    #: A fact about the *referent* - ``"entity""`` or ``"value"`` - and the target of FR-012's
    #: ``QUANTITY → argument_shape = "value"`` mapping. Excluded from identity so a
    #: type-layer reclassification cannot re-key a relation.
    argument_shape: str = DEFAULT_ARGUMENT_SHAPE
    #: Whether this end is an **occurrence** in the segment (and so resolves to an ``MN-``) or
    #: the **retrieval** the observation belongs to (and is already a durable ``CAP-``).
    #: ``None`` means *read it off the address*; see :class:`ParticipantEndKind` for why the
    #: inference exists and what happens when a stated value contradicts it. Excluded from
    #: :meth:`to_identity` because the address already says it, and a fourth key here for a
    #: fact the third one implies would be a value that can disagree with what it summarises.
    end_kind: ParticipantEndKind | None = None

    def __post_init__(self) -> None:
        if not str(self.mention_ref).strip():
            raise ParticipantContractError(
                "participant_mention_required",
                "a participant names the mention it is an end of, and '' names none. A "
                "producer that saw a phrase without being able to address it must record a "
                "deferred raw slot and resolve it later, not hand over an empty reference - "
                "an empty end is a missing participant with no trace (FR-017)",
            )
        object.__setattr__(self, "mention_ref", str(self.mention_ref))
        if not isinstance(self.slot, ArgumentSlot):
            raise ParticipantContractError(
                "participant_slot_type",
                f"a participant's slot is a structural ArgumentSlot (A0, A1, ...), not "
                f"{type(self.slot).__name__}. A free-text role would let two producers "
                "guessing 'seller' and 'vendor' for one slot fork the same reading into two "
                "relations, which is why slot is structural and role_hypothesis is evidence",
            )
        if isinstance(self.ordinal, bool) or not isinstance(self.ordinal, int):
            raise ParticipantContractError(
                "participant_ordinal_type",
                f"ordinal is a position a reader can check, so it is a whole number; got "
                f"{type(self.ordinal).__name__}",
            )
        if self.ordinal < 0:
            raise ParticipantContractError(
                "participant_ordinal_negative",
                f"ordinal is {self.ordinal}; a participant observed at no position was not "
                "observed, and a zero-width position is indistinguishable from a placeholder",
            )
        try:
            confidence = float(self.confidence)
        except (TypeError, ValueError) as exc:
            raise ParticipantContractError(
                "participant_confidence_type",
                f"confidence must be a number in [0, 1]; got "
                f"{type(self.confidence).__name__}",
            ) from exc
        if not 0.0 <= confidence <= 1.0:
            raise ParticipantContractError(
                "participant_confidence_range",
                f"confidence is {confidence}. It is a producer's certainty about its own "
                "reading of this end, not a probability that anything holds about the world, "
                "and it must be a number in [0, 1]",
            )
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "role_hypothesis", str(self.role_hypothesis or ""))
        shape = str(self.argument_shape or "").strip()
        if not shape:
            raise ParticipantContractError(
                "participant_argument_shape_required",
                "argument_shape is the referent's own shape and it must be stated, because "
                f"the default is a claim. {DEFAULT_ARGUMENT_SHAPE!r} asserts this end is an "
                "entity; a producer that saw a measurement asserts 'value' and says so, and "
                "a producer that saw neither has not read this end (FR-012)",
            )
        object.__setattr__(self, "argument_shape", shape)
        self._adopt_end_kind()

    def _adopt_end_kind(self) -> None:
        """Adopt :attr:`end_kind`, inferring it from the address when it was not stated.

        Inference because the address grammar already carries the answer and five producers
        that mint a capture address would otherwise have to restate it; **refusal** when a stated
        value contradicts the address, because a participant that says "this resolves to a
        mention" while addressing a retrieval is a record that will fail in the mention layer —
        where the error is ``mention_capture_is_not_a_mention`` and nothing says the record
        lied. Catching it here names the record and the contradiction.
        """
        addressed = end_kind_of(self.mention_ref)
        if self.end_kind is None:
            object.__setattr__(self, "end_kind", addressed)
            return
        try:
            declared = ParticipantEndKind(self.end_kind)
        except ValueError as exc:
            raise ParticipantContractError(
                "participant_end_kind_unknown",
                f"end_kind={self.end_kind!r} is not a participant end kind; the vocabulary is "
                f"{', '.join(kind.value for kind in ParticipantEndKind)}",
            ) from exc
        if declared is not addressed:
            raise ParticipantContractError(
                "participant_end_kind_mismatch",
                f"this participant says end_kind={declared.value!r} and addresses "
                f"{self.mention_ref!r}, which is a {addressed.value!r}. An end that is declared "
                "an occurrence is required to resolve to an MN- and will be refused by the "
                "mention layer if it is not one, and a retrieval is already a durable CAP- and "
                "must not be given a second identity. State the kind the address supports, or "
                "leave the field unset and let it be read (I-2)",
            )
        object.__setattr__(self, "end_kind", declared)

    def to_identity(self) -> dict[str, Any]:
        """The exact dict that enters a signal's identity material, and nothing else.

        Three keys, and the five fields that are **absent** are the interesting part. See the
        module docstring for why :attr:`role_hypothesis`, :attr:`confidence` and
        :attr:`argument_shape` are each excluded for a stated reason; :attr:`end_kind` is a
        fourth exclusion with a sharper one, and a fifth key added here without that reasoning
        is a defect.
        """
        return {
            "mention_ref": self.mention_ref,
            "slot": self.slot.to_identity(),
            "ordinal": self.ordinal,
        }

    def to_dict(self) -> dict[str, Any]:
        """Every field, for a stored or serialised record - the projection, not the identity."""
        return {
            "mention_ref": self.mention_ref,
            "slot": self.slot.to_dict(),
            "role_hypothesis": self.role_hypothesis,
            "ordinal": self.ordinal,
            "confidence": self.confidence,
            "argument_shape": self.argument_shape,
            "end_kind": str(self.end_kind),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> RelationParticipant:
        kind = payload.get("end_kind")
        return cls(
            mention_ref=str(payload["mention_ref"]),
            slot=_slot_of(payload.get("slot")),
            role_hypothesis=str(payload.get("role_hypothesis", "")),
            ordinal=int(payload.get("ordinal", 0)),
            confidence=float(payload.get("confidence", 0.0)),
            argument_shape=str(payload.get("argument_shape", DEFAULT_ARGUMENT_SHAPE)),
            end_kind=ParticipantEndKind(str(kind)) if kind else None,
        )

    @classmethod
    def coerce(cls, value: RelationParticipant | Mapping[str, Any] | str) -> RelationParticipant:
        """Accept the three shapes a caller may reasonably have, and refuse the rest.

        The dataclass (the normal case), a mapping (a producer reading a stored or declared
        record), and a bare mention-ref string for the binary path. A string is accepted
        **only** for the two-argument construction, and it is accepted into slot ``A0`` by this
        class rather than guessed at by the caller, because guessing would let a bare string
        silently land in the wrong slot and the error would surface three stages later as a
        wrong identity. :func:`binary_participants` is the named two-end spelling.
        """
        if isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            return cls.from_dict(value)
        if isinstance(value, str):
            return cls(mention_ref=value, slot=ArgumentSlot(0))
        raise ParticipantContractError(
            "participant_type",
            f"a participant is a RelationParticipant, a mapping, or a mention-ref string; got "
            f"{type(value).__name__}. Anything else would put an untyped value into an "
            "identity term, which is the defect this type exists to prevent",
        )


def binary_participants(
    subject_mention_ref: str, object_mention_ref: str
) -> tuple[RelationParticipant, ...]:
    """The two-end tuple a **binary** producer declares, in slots ``A0`` and ``A1``.

    **The one phase of grace is closed.** This function was written for the window in which
    ``subject_mention_ref=`` and ``object_mention_ref=`` were still accepted constructor
    parameters on :class:`~extractors.signals.signal.RelationSignal`: it was the *only*
    sanctioned way for a bare mention-ref string to become a participant, and it was named and
    in one place so that closing the window would be exactly one deletion rather than seven.
    Phase 4B migrated all seven production sites onto ``participants=`` and removed the
    parameters, so that deletion has happened and no production code calls this any more.

    It stays because **binary is a real shape and not a temporary one.** A cue producer reading
    ``"John became CEO of Acme"`` saw two things, and spelling that out as
    ``RelationParticipant(..., slot=ArgumentSlot(0)), RelationParticipant(...,
    slot=ArgumentSlot(1))`` at every call site would be the caller restating the tuple's
    ordering by hand. What is gone is the *reason* — the compatibility path — and that is
    recorded here rather than left in the docstring, because a docstring describing an active
    grace period that has ended is a premise a reader will act on.

    Both ends are required and the caller's blanks are **not** swallowed here: a
    :class:`~domain.relation_participant.RelationParticipant` raises
    ``participant_mention_required`` for a blank end, and a signal built from a tuple with one
    end is refused with ``signal_arity_below_two``, because "a signal connects two mentions and
    needs both" is a statement about the signal and not about one of its parts.
    """
    return (
        RelationParticipant(
            mention_ref=subject_mention_ref, slot=ArgumentSlot(0), ordinal=0
        ),
        RelationParticipant(
            mention_ref=object_mention_ref, slot=ArgumentSlot(1), ordinal=1
        ),
    )


def _slot_of(value: Any) -> ArgumentSlot:
    """An :class:`ArgumentSlot` from a token (``"A2"``), a mapping, or the object itself."""
    if isinstance(value, ArgumentSlot):
        return value
    if isinstance(value, Mapping):
        return ArgumentSlot.from_dict(value)
    text = str(value or "").strip()
    if text.startswith("A") and text[1:].isdigit():
        return ArgumentSlot(index=int(text[1:]))
    raise ParticipantContractError(
        "participant_slot_unreadable",
        f"a slot is an ArgumentSlot, {{'index': n}}, or its 'A<n>' token; got {value!r}. A "
        "slot that cannot be read is a position that cannot be ordered, and an unordered "
        "position silently collapses into the first argument",
    )


__all__ = [
    "DEFAULT_ARGUMENT_SHAPE",
    "MIN_PARTICIPANTS",
    "ParticipantContractError",
    "ParticipantEndKind",
    "RelationParticipant",
    "binary_participants",
    "end_kind_of",
]
