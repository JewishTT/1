"""S3–S5: relation signals from structure, resolved mentions, and truncation that propagates.

Feature 021 brief §16 (``SignalBasis`` answers "how do you know?"), §25 (a producer below mention
extraction), §26 (:mod:`domain.mention_occurrence_index` is the mention seam), §31 (structural
observation read *as structure*); spec FR-008 (``participants`` is canonical and variadic), FR-009
(``RelationParticipant``'s six fields), FR-014 (``basis``), FR-016/FR-018/FR-019 (mention binding),
FR-041…FR-043 (the neighbourhood); ``ARBITRATION`` §8; constitution IV (fail-closed) and VI
(determinism, Domain Invariant 12).

**Where this sits.** :mod:`parsers.payload` turns bytes into records of observed structure; this
module is the first stage above it allowed to make a judgement, and it makes exactly two: which
observed structures are *relations*, and which are *typed*. It sits below the 021 substrate: it
imports no graph, claim, admission, projection or resolution symbol, mints no entity id, and every
participant is a **mention** resolved through :class:`domain.mention_occurrence_index
.MentionOccurrenceIndex` — a real ``MN-``, not a deferred address this stage assumed.

**The two bases, and why the shapes differ.**

``ATTRIBUTE_KEY`` — a JSON **object** is binary
    ``{"registrant": {"email": "…"}}`` says the container at ``$["registrant"]`` states a member
    called ``email`` whose value is that string. Subject ``A0`` is the container's mention, object
    ``A1`` is the member's, and ``relation_ref`` is **unset**: a key is not an operator, and the
    key thing the relation's own docstring says about ``relation_ref`` is that it means *the
    producer knows the operator*. A table/field producer does not.

``DOM_RELATION`` — a JSON **array** is a member set
    An array is unnamed and ordered: it states that it holds these things in these positions. Each
    element is therefore **its own binary** signal — (array, element) — and the array is **not**
    filed as one n-ary signal. An n-ary reading would assert the elements participate in one
    relation, which a JSON array does not state: a list of strings says the source holds them under
    one key, and says nothing about how they relate to each other. Phase 4A made
    :attr:`~extractors.signals.signal.RelationSignal.participants` n-ary for *parsed event frames*;
    membership is not one, and minting a four-slot signal for a four-element array would
    manufacture a relation from a list.

**The array rule, stated for the two cases that make array code wrong.**

============================  ==========================================================
**empty** ``[]``              **zero signals**, and the set is **recorded**: its key path
                              appears in :attr:`StructuralReading.member_sets` with
                              :attr:`MemberSetKind.EMPTY`. An empty array is a fact the payload
                              states — a key whose value is a set with nothing in it — and
                              emitting nothing *silently* would make it indistinguishable from a
                              key that was never there
**singleton** ``["jane"]``    **one signal**, of exactly the shape the many-element case
                              produces, and the set is recorded as
                              :attr:`MemberSetKind.SINGLETON`. A one-element list is a set with
                              one member, not a scalar: collapsing it onto its element reports a
                              payload that stated a set as though it stated a value, and that is
                              unrecoverable afterwards
**many**                     one signal per element, in document order, the element's
                              **index** as its ``ordinal``
============================  ==========================================================

**``ordinal``, and why the payload's position wins.** :attr:`RelationParticipant.ordinal` is
documented as *position as observed, not as canonicalised*, so an array element carries the index
the payload states. A container is always end ``0``; an object member is end ``1`` because a JSON
object states no position for a member, only a key; an array element is the **index**, because a
JSON array does state one. ``RelationParticipant.to_identity`` includes ``ordinal``, so two
elements of one array are two signals and swapping two positions changes both ids — which a test
asserts by moving the ordinal and watching the address move.

**``relation_surface``, and why the key path is not an invented verb.** A JSON document contains no
verbs, and :attr:`RelationSignal.relation_surface` is required. The honest value is **the key path
the observation is about** — ``$["registrant"]["email"]`` — a real artifact of the payload's own
grammar, carrying every segment rather than the last word alone so two same-named fields under
different containers cannot share a surface. Filling the field with ``"has_attribute"`` or
``"member_of"`` would be a word this producer chose, attributed to the source, in the one field a
reader reaches for when asking what connects the ends. ``extra["relation_surface_kind"]`` names it
as a key path in the record, and the notes say so in prose. ``RelationSignal`` then builds an
unresolved :class:`~domain.predicate_hypothesis.PredicateHypothesis` over that surface with no
``relation_ref``, which is the contract's own representation of "words seen, operator unknown".

**``Neighbourhood``, for a producer that looks at nothing but structure.** Four numbers, none of
them invented:

``characters_scanned``
    the container's own byte length **plus** the member's. The container's text is read once per
    container and shared by every signal that names it, so this is an **upper bound** on what one
    signal cost, and the notes say so. It is a count of **bytes**; the field is named
    ``characters`` because the contract named it that, and a byte count is the conservative
    direction for a boundedness claim.
``pairs_considered``
    ``0``, stated. No pair of mentions is ever compared — this producer reads membership. A
    producer that reported a non-zero count here would be claiming a search it did not run, and
    :func:`~extractors.signals.signal.assert_bounded` would then have a real ceiling to check
    instead of a tautology.
``scope_read``
    the two byte ranges, the segment and the capture, and the sentence "no other document,
    container or pair of mentions was read".
``precision``
    :data:`PRECISION_WHOLE` or :data:`PRECISION_BOUNDED`, and **never** ``exhaustive``. The record
    set is not the document: a payload can be a partial body the source chose to send, and nothing
    on the path from bytes to records can tell that from a complete one, so absence is never
    claimed from these signals.

**Every end is resolved or the signal does not exist.** A participant's ``mention_ref`` is a real
``MN-`` from ``index.require_occurrence``, never a deferred address and never a guess:

* a record the **parser** refused an address for is excluded, with
  :attr:`SignalRefusalCode.VALUE_END_NOT_ADDRESSABLE` naming the record's own refusal code;
* an address the **index** refuses — the ``"…"`` case, where the surface normalises to nothing — is
  excluded with :attr:`SignalRefusalCode.END_NOT_RESOLVED` and the index's code in the detail;
* a **container** end is the container's own text at the container's own byte span, so
  :meth:`ParsedPayload.read_span` returns the mention's surface and a reader can check the claim by
  slicing. Over :data:`MAX_CONTAINER_SURFACE_BYTES` the end is refused by name rather than minting
  a mention of a quarter of a megabyte of JSON;
* the ids this stage mints are **cross-checked against the caller's own binding**, and a
  disagreement is :attr:`SignalRefusalCode.MENTION_ID_SCOPE_MISMATCH`. The check exists because
  ``MentionOccurrenceIndex`` mints from five keys and three are the scope: a ``BoundPayload``
  built with another ``extractor_ref`` is a set of mentions from another reading, every id is well
  formed, and nothing about them looks wrong.

**Truncation propagates, and it propagates into the address.** A bounded walk's records are a
prefix of the document, so this stage refuses to describe them as a whole. :attr:`StructuralReading
.truncated` is **derived** from the ``BoundHit`` rather than carried, so it cannot disagree with
it. Every signal records ``extra["payload_truncated"]``, and its ``precision`` becomes
:data:`PRECISION_BOUNDED` with the bound named in the notes — and because
:class:`~extractors.signals.signal.Neighbourhood` is part of a signal's identity material, a
bounded read and a whole read of the same structure **cannot share a ``signal_id``**. A container
the walk never closed is simply absent from the record set, so its members are orphans and are
refused ``container_record_absent`` rather than joined to a nearest surviving container.

**Nothing is dropped.** :attr:`StructuralReading.member_outcomes` carries **one outcome for every
record in the payload, in document order**, so ``len(member_outcomes) == len(payload.records)`` is
checkable and "nothing was lost" is not a claim. The parser's own refusals and the binding's own
refusals are carried verbatim in their own vocabularies rather than folded into this stage's, so
each list has exactly one owner.

**Determinism is structural.** One pass over ``payload.records`` in document order; a container
end resolved once per container and shared; every tuple built by appending in that order; no
``set`` iteration, no dict-order dependence, no clock, no randomness. ``signal_id`` is
content-addressed by :class:`~extractors.signals.signal.RelationSignal` itself, so two processes
handed one payload and one scope produce the same ids in the same order.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from domain.mention_occurrence_index import (
    MentionBindingError,
    MentionOccurrence,
    MentionOccurrenceIndex,
)
from domain.predicate_signature import ArgumentSlot, Polarity
from domain.relation_participant import RelationParticipant
from domain.signal_basis import SignalBasis
from semantic.contracts import content_key

from extractors.payload.hypotheses import HypothesisReading, read_type_hypotheses
from extractors.payload.keytable import DeclaredSchema
from extractors.signals.mentions import deferred_occurrence
from extractors.signals.protocol import (
    ExtractionScope,
    ProducerDeclaration,
    RelationSignalExtractor,
    run_producer,
)
from extractors.signals.signal import (
    DirectionHypothesis,
    Neighbourhood,
    RelationSignal,
    SignalContractError,
    SignalKind,
)
from parsers.payload import (
    BoundPayload,
    ObservedField,
    ParsedPayload,
    PayloadContractError,
    PayloadRefusal,
    ValueType,
)

#: The producer stamped on every signal, and the unit FR-034's independence count is computed over.
#: One name for this one reading, so a signal about a JSON container cannot be counted as
#: corroborating a signal about a hyperlink or a table slot.
PRODUCER_REF = "extractors/payload/structure"

#: Bumped when the structural rules change, not when the type table does: the signals below depend
#: on the payload's shape and not on :data:`~extractors.payload.keytable.KEY_TYPE_RULES`, so a
#: table revision must not re-key every structural signal in the store.
PRODUCER_VERSION = "payload-structure/1"

#: One family, so this producer and any future one reading the same JSON structure are one source.
INDEPENDENCE_FAMILY = "payload-structure"

#: This producer compares **no pair of mentions at all** — it reads membership, not proximity.
#: :data:`~extractors.signals.protocol.ProducerDeclaration` refuses a ceiling below 1, so 1 is the
#: smallest value the contract admits, and it exists so
#: :func:`~extractors.signals.signal.assert_bounded` has something to check rather than a
#: convention to assume.
MAX_PAIRS_CONSIDERED = 1

#: The most bytes of a container's own text this stage will mint a mention of.
#:
#: A container's mention **is** its own text at its own span — that is what makes it verifiable by
#: slicing the payload — so the extent of the read is the extent of the container. Past this
#: ceiling the stage declines rather than minting a mention of a quarter of a megabyte of JSON, and
#: the refusal is named and counted (``container_surface_too_large``) rather than applied silently.
#: It is this stage's bound and not the parser's, so it never sets
#: :attr:`StructuralReading.truncated`: a payload is not truncated because this producer declined.
MAX_CONTAINER_SURFACE_BYTES = 65_536

#: ``Neighbourhood.precision`` for a read of a payload whose walk completed.
PRECISION_WHOLE = "exact"

#: ``Neighbourhood.precision`` for a read of a payload whose walk stopped at a ceiling. **Not**
#: :data:`~extractors.signals.signal.PRECISION_EXHAUSTIVE`, and never it: these signals are not
#: absence claims about a document.
PRECISION_BOUNDED = "bounded"

#: The two byte characters that open a JSON object and a JSON array, and the two facts a container's
#: own text has to state before this stage will address it. A record whose opening byte is neither
#: is refused (``container_kind_unknown``) rather than guessed at from its children's labels, which
#: would be a second reading of the payload's shape.
_OBJECT_OPENER = 0x7B
_ARRAY_OPENER = 0x5B

#: The label stamped on a container end's occurrence, and a closed two-member vocabulary of this
#: producer's own. :class:`parsers.payload.records.PayloadLabel` is the parser's and is not
#: extended — a container's label is a *structural* name rather than a position in the payload's
#: grammar, and the parser's four members are exactly the four positions a *value* can be read at.
CONTAINER_OBJECT_LABEL = "json_object_container"
CONTAINER_ARRAY_LABEL = "json_array_container"


class ContainerKind(StrEnum):
    """Which container a nested record is: an object or an array. Read from its opening byte.

    Two members and a refusal for a third, because the alternative is inferring it from the
    children's labels, and a second reading of the payload's shape is a second answer to a question
    the first one already answered.
    """

    OBJECT = "object"
    ARRAY = "array"


class MemberSetKind(StrEnum):
    """How many members an array states, as a **closed three-member vocabulary**.

    Named rather than computed at each call site because the distinction is the answer: empty,
    singleton and many are three different facts about a payload and code that treats them alike is
    how a one-element list becomes a scalar and an empty list becomes silence.
    """

    EMPTY = "empty"
    SINGLETON = "singleton"
    MANY = "many"

    @classmethod
    def of(cls, size: int) -> MemberSetKind:
        if size <= 0:
            return cls.EMPTY
        if size == 1:
            return cls.SINGLETON
        return cls.MANY


class SignalRefusalCode(StrEnum):
    """Every way this stage declines to state a relation, as a closed vocabulary.

    Each member names something that **exists**: a record, a container or the payload. None of them
    is a silent drop, and each is a different operator's bug — a record whose container vanished
    because a ceiling fired is not the same defect as a container whose bytes are not in the body
    the caller supplied.
    """

    VALUE_END_NOT_ADDRESSABLE = "value_end_not_addressable"
    END_NOT_RESOLVED = "end_not_resolved"
    MENTION_ID_SCOPE_MISMATCH = "mention_id_scope_mismatch"
    CONTAINER_RECORD_ABSENT = "container_record_absent"
    CONTAINER_KIND_UNKNOWN = "container_kind_unknown"
    CONTAINER_TEXT_UNAVAILABLE = "container_text_unavailable"
    CONTAINER_SURFACE_TOO_LARGE = "container_surface_too_large"
    MEMBER_KIND_MISMATCH = "member_kind_mismatch"
    PAYLOAD_NOT_STRUCTURED = "payload_not_structured"


#: The vocabulary as strings, for callers that switch on the token rather than the member.
SIGNAL_REFUSAL_CODES: tuple[str, ...] = tuple(code.value for code in SignalRefusalCode)


class MemberOutcomeCode(StrEnum):
    """What became of one record: the accounting that makes "no record is dropped" checkable.

    A closed vocabulary because the claim is arithmetic — exactly one member of it for every record
    in the payload — and a code nobody can enumerate makes the count unreadable. Every member
    other than :attr:`SIGNAL_EMITTED` is a way the record was **kept and counted** without becoming
    a signal, which is the difference between an exclusion and a drop.
    """

    DOCUMENT_ROOT = "document_root"
    SIGNAL_EMITTED = "signal_emitted"
    CONTAINER_STATES_MEMBERS = "container_states_members"
    EMPTY_CONTAINER = "empty_container"
    VALUE_END_NOT_ADDRESSABLE = "value_end_not_addressable"
    END_NOT_RESOLVED = "end_not_resolved"
    MENTION_ID_SCOPE_MISMATCH = "mention_id_scope_mismatch"
    CONTAINER_RECORD_ABSENT = "container_record_absent"
    CONTAINER_KIND_UNKNOWN = "container_kind_unknown"
    CONTAINER_TEXT_UNAVAILABLE = "container_text_unavailable"
    CONTAINER_SURFACE_TOO_LARGE = "container_surface_too_large"
    MEMBER_KIND_MISMATCH = "member_kind_mismatch"
    PAYLOAD_NOT_STRUCTURED = "payload_not_structured"


class ReadingContractError(ValueError):
    """A :class:`PayloadReading` is not a coherent reading of one payload, refused with a code.

    A ``ValueError`` carrying snake_case ``.code``, matching the rest of the platform so a caller
    can switch on any of them by ``.code`` rather than by type. Every code is fail-closed: each one
    is a case where the reading would otherwise name a different capture, a different reading, or a
    different record set than the one its own parts describe.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


@dataclass(frozen=True, slots=True)
class PayloadReading:
    """One payload, the bytes it was read from, and a binding made under **one** three-key scope.

    **Why the scope is an input and not a constant.** ``MentionOccurrenceIndex`` mints from five
    keys and three of them are ``(capture_ref, segment_ref, extractor_ref)``. A mention id minted
    under one triple and a mention id minted under another are different mentions of the same
    bytes, and nothing in the id says which triple produced it. So the reading carries the triple
    and :meth:`__post_init__` **cross-checks it against the binding the caller already made** —
    a disagreement is refused at construction rather than surfacing later as a signal whose
    participants name a different reading.

    ``body`` is required and is not derivable from the records: a container's mention is its own
    text at its own span, and a span is a claim about bytes nobody in this package holds.

    ``bound`` is required rather than recomputed, because the caller's
    :func:`parsers.payload.binding.bind_records` is **the mention seam** and its refusals are facts
    this stage must carry rather than redo. The partition it maintains —
    ``len(bound.bound) + len(bound.refusals) == len(payload.records)`` — is checked here too, so a
    binding made for a different record set is refused before anything is emitted.
    """

    payload: ParsedPayload
    body: bytes
    bound: BoundPayload
    capture_ref: str
    segment_ref: str
    extractor_ref: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "body", bytes(self.body or b""))
        for name in ("capture_ref", "segment_ref", "extractor_ref"):
            value = str(getattr(self, name) or "").strip()
            if not value:
                raise ReadingContractError(
                    "reading_scope_required",
                    f"{name} is required and cannot be defaulted. The index's scope is three of "
                    "the five keys a mention id is minted from, and defaulting one would mint "
                    "addresses that cannot say which retrieval, which document or which instrument "
                    "produced them (FR-018)",
                )
            object.__setattr__(self, name, value)
        if (
            self.bound.capture_ref != self.capture_ref
            or self.bound.segment_ref != self.segment_ref
            or self.bound.extractor_ref != self.extractor_ref
        ):
            raise ReadingContractError(
                "reading_scope_disagrees_with_binding",
                f"this reading is scoped to ({self.capture_ref!r}, {self.segment_ref!r}, "
                f"{self.extractor_ref!r}) but its bound payload was minted under "
                f"({self.bound.capture_ref!r}, {self.bound.segment_ref!r}, "
                f"{self.bound.extractor_ref!r}). Three of the five keys a mention id is minted "
                "from are that scope, so the two sets of ids are different mentions of the same "
                "bytes and nothing in an id says which produced it. Bind the payload with the same "
                "three values, or read it under the scope it was bound in",
            )
        records = len(self.payload.records)
        if len(self.bound.bound) + len(self.bound.refusals) != records:
            raise ReadingContractError(
                "reading_binding_does_not_partition_records",
                f"the bound payload accounts for "
                f"{len(self.bound.bound) + len(self.bound.refusals)} record(s) and the payload has "
                f"{records}. The binding's own guarantee is that every record appears exactly "
                "once, so this reading was assembled from a binding made for a different record "
                "set",
            )

    @property
    def truncated(self) -> bool:
        """Whether a ceiling stopped the parse walk. Derived, so it cannot be set independently."""
        return self.payload.truncated

    @property
    def truncation_reason(self) -> str:
        """The name of the ceiling that stopped the walk, or ``""`` when none did."""
        return self.payload.truncation_reason

    def container_text(self, record: ObservedField) -> str:
        """The container's own bytes, decoded — the surface its mention will carry.

        Delegates to :meth:`ParsedPayload.read_span`, which is the payload's own witness, and
        converts its refusals into this stage's vocabulary so a span that points past the end of the
        body the caller supplied is a **named** refusal rather than an exception out of a
        producer. Reading the nearest bytes instead would address a position nobody read.
        """
        try:
            return self.payload.read_span(self.body, record)
        except PayloadContractError as exc:
            raise _ContainerTextUnavailable(exc.code, exc.message) from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "capture_ref": self.capture_ref,
            "segment_ref": self.segment_ref,
            "extractor_ref": self.extractor_ref,
            "byte_length": len(self.body),
            "truncated": self.payload.truncated,
            "truncation_reason": self.payload.truncation_reason,
            "declared_parser": self.payload.declared_parser,
            "parser_is_identity": self.payload.parser_is_identity,
            "routed_to": self.payload.routed_to,
        }


class _ContainerTextUnavailable(Exception):
    """Internal: a container's span is not inside the body the caller supplied."""

    __slots__ = ("code", "detail")

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True, slots=True)
class SignalRefusal:
    """One thing this stage declined to state, with the code a caller counts by.

    ``key_path`` is the record it is about, empty for a refusal about the payload as a whole. The
    detail names the record, the position and the underlying code where there is one, because a
    refusal a reader cannot act on is a gap they will rediscover as missing data.
    """

    code: str
    detail: str
    key_path: str = ""

    def __post_init__(self) -> None:
        code = str(self.code)
        if code not in SIGNAL_REFUSAL_CODES:
            raise ReadingContractError(
                "signal_refusal_code_unknown",
                f"{code!r} is not a signal refusal code. The vocabulary is closed and has "
                f"{len(SIGNAL_REFUSAL_CODES)} members: {list(SIGNAL_REFUSAL_CODES)}. A code "
                "nobody can enumerate is a code nobody can count",
            )
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "detail", str(self.detail or ""))
        object.__setattr__(self, "key_path", str(self.key_path or ""))

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "detail": self.detail, "key_path": self.key_path}


@dataclass(frozen=True, slots=True)
class MemberOutcome:
    """What became of exactly one record, and the arithmetic that no record is dropped."""

    key_path: str
    code: MemberOutcomeCode

    def __post_init__(self) -> None:
        object.__setattr__(self, "key_path", str(self.key_path or ""))
        object.__setattr__(self, "code", MemberOutcomeCode(self.code))

    def to_dict(self) -> dict[str, Any]:
        return {"key_path": self.key_path, "code": str(self.code)}


@dataclass(frozen=True, slots=True)
class MemberSetReading:
    """One JSON array, and exactly what it states: its path, its kind, and its elements.

    Recorded for **every** array, not only for empty and singleton ones, because the useful
    comparison is between a payload that stated a set of three and one that stated three scalars,
    and that comparison needs the set in the record. ``element_paths`` is the document order the
    walk emitted, so a reader can join it to :attr:`StructuralReading.signals` without re-walking.
    """

    key_path: str
    kind: MemberSetKind
    element_paths: tuple[str, ...] = ()
    byte_span: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "key_path", str(self.key_path or ""))
        object.__setattr__(self, "kind", MemberSetKind(self.kind))
        object.__setattr__(self, "element_paths", tuple(self.element_paths or ()))
        fixed = _expected_size(self.kind)
        if fixed is not None and len(self.element_paths) != fixed:
            raise ReadingContractError(
                "member_set_reading_incoherent",
                f"the member set at {self.key_path!r} is recorded as {self.kind.value!r} with "
                f"{len(self.element_paths)} element path(s). The kind is derived from the count, "
                "so a record that disagrees with itself cannot be counted",
            )

    @property
    def size(self) -> int:
        """How many members the array states. Derived, so it cannot drift from :attr:`kind`."""
        return len(self.element_paths)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key_path": self.key_path,
            "kind": str(self.kind),
            "size": self.size,
            "element_paths": list(self.element_paths),
            "byte_span": list(self.byte_span) if self.byte_span is not None else None,
        }


def _expected_size(kind: MemberSetKind) -> int | None:
    """The only element counts a :attr:`MemberSetKind` fixes, or ``None`` for the open one.

    ``EMPTY`` fixes zero and ``SINGLETON`` fixes one, and those two are the cases array code gets
    wrong. ``MANY`` is open, so it fixes nothing and this returns ``None`` — which is why the
    coherence check compares only when a count is fixed.
    """
    if kind is MemberSetKind.EMPTY:
        return 0
    if kind is MemberSetKind.SINGLETON:
        return 1
    return None


@dataclass(frozen=True, slots=True)
class _ContainerEnd:
    """One container's resolved subject end, or the named reason it has none.

    Resolved **once per container** and shared by every signal that names it: the address is
    content-addressed over ``(label, surface, start, end)``, so every member of one container
    resolves to the same ``MN-`` — which is correct, because it is one occurrence of one structure
    — and re-resolving it per member would be the same work N times.
    """

    mention_id: str
    kind: ContainerKind
    byte_span: tuple[int, int]
    surface_bytes: int

    @property
    def label(self) -> str:
        return (
            CONTAINER_OBJECT_LABEL
            if self.kind is ContainerKind.OBJECT
            else CONTAINER_ARRAY_LABEL
        )


@dataclass(frozen=True, slots=True)
class _SignalBuild:
    """The internal result of one pass: signals, outcomes, refusals and member sets."""

    signals: tuple[RelationSignal, ...] = ()
    outcomes: tuple[MemberOutcome, ...] = ()
    refusals: tuple[SignalRefusal, ...] = ()
    member_sets: tuple[MemberSetReading, ...] = ()


def payload_occurrence_index(reading: PayloadReading) -> MentionOccurrenceIndex:
    """The index this stage binds against, built once from the records **and** the containers.

    Two populations, both real occurrences in this reading, registered in a single document-order
    pass:

    * every **addressable record** — the value mentions, at the spans the parser read. These mint
      the same ids as the caller's :func:`parsers.payload.binding.bind_records`, and the reading
      cross-checks that rather than assuming it.
    * every **container** — at the container's own byte span, with the container's own text as the
      surface. A container has no value of its own (the parser says so, and declines to address
      it), so a subject end for it has to be built from something the payload states; the container's
      own text is that something, and it is checkable by slicing the payload.

    Published rather than kept private so a caller can verify every participant of every signal
    against the index that produced it, using the index's **own** inverse.
    """
    index = MentionOccurrenceIndex(
        capture_ref=reading.capture_ref,
        segment_ref=reading.segment_ref,
        extractor_ref=reading.extractor_ref,
    )
    for record in reading.payload.records:
        if record.addressable and record.byte_span is not None:
            try:
                index.bind(
                    MentionOccurrence(
                        kind=_OCCURRENCE_KIND,
                        surface=record.value,
                        start=record.byte_span[0],
                        end=record.byte_span[1],
                    )
                )
            except MentionBindingError:
                # A record the address survives and the index does not: ``"..."`` normalises to
                # nothing, so there is a well-formed address at a position with no nameable words.
                # :func:`parsers.payload.binding.bind_records` refuses the same record and records
                # it, and this stage carries that refusal verbatim, so skipping it here costs the
                # record nothing: the member path resolves it, fails, and is excluded and counted
                # as ``end_not_resolved``. Registering it would instead cost the whole payload its
                # index, which is the "silent drop" this layer exists to prevent.
                continue
            continue
        if record.value_type is not ValueType.NESTED:
            continue
        span = record.byte_span
        if span is None:
            continue
        try:
            text = reading.container_text(record)
        except _ContainerTextUnavailable:
            continue
        try:
            index.bind(
                MentionOccurrence(
                    kind=_OCCURRENCE_KIND,
                    surface=text,
                    start=span[0],
                    end=span[1],
                )
            )
        except MentionBindingError:
            # An **empty** container's own text is punctuation, and the shared normalisation reduces
            # it to nothing, so the index refuses it with ``mention_occurrence_surface_required``.
            # That is the right answer and it costs nothing: an empty container has no members, so
            # it can never be a subject end, and its emptiness is recorded as a member set and a
            # member outcome instead. Refusing here rather than propagating is what keeps one
            # unnameable container from costing the payload its whole index.
            continue
    return index


#: The ``kind`` every occurrence this stage registers carries, and the same constant
#: :mod:`parsers.payload.binding` uses, because the index *checks* it: two registrations of one
#: span under different kinds are refused with ``mention_kind_disagreement``. One kind for the whole
#: reading is what keeps a value occurrence and a container occurrence from contradicting each
#: other — the classification of a record is said by the record and by the signal that names it,
#: not by the index.
_OCCURRENCE_KIND = "payload-occurrence"


class PayloadStructureExtractor(RelationSignalExtractor):
    """A JSON payload's own structure, as relation signals over resolved mentions.

    **Declared as a :class:`~extractors.signals.protocol.RelationSignalExtractor` subclass rather
    than merely satisfying it.** The protocol is ``runtime_checkable``, so an in-test ``isinstance``
    would pass; inheriting from it makes the two methods a checked part of the class's surface, and
    the run-time protocol check stays available for a caller who wants one. It is driven through
    :func:`~extractors.signals.protocol.run_producer`, so its output is stamped with the registry's
    authority on who spoke, checked against its own declared pair ceiling, refused if its basis is
    one the registry cannot account for, and collapsed by content — the same path every other
    producer in this package takes.

    **The unit of work is one payload, so the build is done once** in :meth:`extract` and cached.
    The cache is derived from immutable inputs and cannot drift, and re-running returns the same
    signals; :attr:`build` exists so the caller can read the pass's outcomes and refusals without
    walking the payload a second time.
    """

    __slots__ = ("_build", "_reading")

    def __init__(self, reading: PayloadReading) -> None:
        self._reading = reading
        self._build: _SignalBuild | None = None

    @property
    def reading(self) -> PayloadReading:
        """The reading this extractor was built over. The one payload it reads."""
        return self._reading

    @property
    def build(self) -> _SignalBuild | None:
        """The last build, or ``None`` before :meth:`extract` has run.

        Exposed because :func:`read_payload_structure` needs the pass's outcomes and refusals as
        well as its signals, and running the pass twice to get them would be a second walk of a
        payload whose determinism is the thing this whole stage is arguing for.
        """
        return self._build

    def declares(self) -> ProducerDeclaration:
        return ProducerDeclaration(
            producer_ref=PRODUCER_REF,
            producer_version=PRODUCER_VERSION,
            kinds=(SignalKind.ATTRIBUTE, SignalKind.STRUCTURAL),
            reads=(
                "one captured JSON payload's own grammar: for every object, the container and each "
                "of its members as a key/value pair (basis attribute_key); for every array, the "
                "container and each of its elements as a membership (basis dom_relation). Reads "
                "containers as occurrences in their own byte spans, so a member's subject end is "
                "the bytes of the structure that states it. Emits nothing from a payload whose "
                "detection says it is not JSON, and refuses every end it cannot resolve by name"
            ),
            cannot_read=(
                "what any of it MEANS. It cannot tell an address from a handle, a person from a "
                "company, a hostname from a URL that happens to be one, or a count from a version. "
                "It reads no words and therefore no verb, because a JSON document contains none, so "
                "it cannot say what operator connects two mentions and declines to: relation_ref "
                "is always None. It cannot tell an empty array from an array whose members it "
                "failed to resolve. It is not n-ary: an array states that it holds some things, "
                "not that those things are in one relation with each other, so each element is its "
                "own binary signal and no unary reading is ever produced - one mention in two slots "
                "is refused upstream as signal_self_connection, and a one-argument reading is that "
                "refusal"
            ),
            max_pairs_considered=MAX_PAIRS_CONSIDERED,
            independence_family=INDEPENDENCE_FAMILY,
            notes=(
                "relation_surface is the payload's own key path and is labelled as such in "
                "extra['relation_surface_kind']. There is no verb in a JSON document, and writing "
                "one into that field would attribute a word this producer chose to the source in "
                "the field a reader reaches for first. relation_ref is always None for every "
                "signal this producer emits, for the same reason: it read a container's membership "
                "and no operator. Array membership is filed under SignalKind.STRUCTURAL rather "
                "than SignalKind.HIERARCHY; the two are near-synonyms at this revision and "
                "extractors.signals.signal's own docstring records the overlap as named, "
                "unresolved, and not this producer's to decide"
            ),
        )

    def extract(self, record: object, *, scope: ExtractionScope) -> tuple[RelationSignal, ...]:
        """Every structural signal in this reading, in document order.

        ``record`` is the payload the extractor was built over and is checked against the reading
        rather than used: the unit of work is one payload and its bytes, and a producer handed a
        different record would otherwise answer about the one it holds, which is the silent
        substitution :class:`~extractors.signals.protocol.ExtractionScope` exists to prevent.
        """
        if record is not self._reading.payload:
            raise SignalContractError(
                "payload_reading_record_mismatch",
                "this producer was built over one payload and was handed a different record. It "
                "reads the container's own bytes, which only that payload has, so answering with "
                "the other reading would state relations about a document nobody bound. Drive it "
                "with the reading's own payload, or build one extractor per payload",
            )
        if self._build is None:
            self._build = _build_signals(self._reading, scope)
        return self._build.signals


def _build_signals(reading: PayloadReading, scope: ExtractionScope) -> _SignalBuild:
    """The single pass: containers, members, signals, outcomes, refusals, member sets.

    Total by construction. Every branch that cannot state a relation appends a
    :class:`SignalRefusal` **and** a :class:`MemberOutcome` and moves on, so there is no path
    through this function that reads a record and produces neither a signal nor an accounting
    entry — which is the property ``len(member_outcomes) == len(records)`` asserts.
    """
    records = reading.payload.records
    outcomes: list[MemberOutcome] = []
    refusals: list[SignalRefusal] = []
    if not reading.payload.detection.is_json:
        for record in records:
            refusals.append(
                SignalRefusal(
                    code=SignalRefusalCode.PAYLOAD_NOT_STRUCTURED.value,
                    key_path=record.field,
                    detail=(
                        f"this payload's detection decided it is not JSON (rule "
                        f"{reading.payload.detection.rule}, declared "
                        f"{reading.payload.detection.declared or '(none)'!r}), so its records are "
                        f"lines and not key paths. A line is not a key, and a producer that read "
                        "one as a field would state relations a text payload never wrote"
                    ),
                )
            )
            outcomes.append(
                MemberOutcome(record.field, MemberOutcomeCode.PAYLOAD_NOT_STRUCTURED)
            )
        return _SignalBuild(outcomes=tuple(outcomes), refusals=tuple(refusals))

    index = payload_occurrence_index(reading)
    parents, children = _tree(records)
    bound_by_path = {entry.field: entry for entry in reading.bound.bound}
    container_ends: dict[int, _ContainerEnd | SignalRefusal] = {}
    member_sets: dict[int, MemberSetReading] = {}
    signals: list[RelationSignal] = []

    for position, record in enumerate(records):
        if record.depth == 0:
            outcomes.append(MemberOutcome(record.field, MemberOutcomeCode.DOCUMENT_ROOT))
            continue
        parent_position = parents[position]
        if parent_position is None:
            refusal = SignalRefusal(
                code=SignalRefusalCode.CONTAINER_RECORD_ABSENT.value,
                key_path=record.field,
                detail=(
                    f"{record.field!r} sits at depth {record.depth} and no container at depth "
                    f"{record.depth - 1} is in this record set. A bounded walk discards the "
                    "containers it did not close, so a truncated payload leaves members without a "
                    "parent. Joining them to the nearest surviving container would state a "
                    "relation the payload never wrote"
                ),
            )
            refusals.append(refusal)
            outcomes.append(
                MemberOutcome(record.field, MemberOutcomeCode.CONTAINER_RECORD_ABSENT)
            )
            continue
        parent = records[parent_position]

        if record.value_type is ValueType.NESTED:
            _read_member_set(
                reading=reading,
                position=position,
                record=record,
                parent=parent,
                children=children,
                member_sets=member_sets,
                refusals=refusals,
                outcomes=outcomes,
            )
            continue

        end = _container_end(reading, index, parent_position, parent, container_ends, refusals)
        if isinstance(end, SignalRefusal):
            outcomes.append(MemberOutcome(record.field, MemberOutcomeCode(end.code)))
            continue

        failure = _value_end_failure(
            record=record,
            end=end,
            parent=parent,
            parents=parents,
            records=records,
            index=index,
            bound_by_path=bound_by_path,
        )
        if failure is not None:
            refusal, code = failure
            refusals.append(refusal)
            outcomes.append(MemberOutcome(record.field, code))
            continue

        resolved = index.require_occurrence(record.address)
        expected = bound_by_path[record.field].mention_id
        assert resolved.mention_id == expected, "checked by _value_end_failure"
        signal = _signal(
            reading=reading,
            scope=scope,
            record=record,
            parent=parent,
            end=end,
            member_mention_id=resolved.mention_id,
            ordinal=len(signals),
            member_index=_element_index(record, parent, parents, records),
        )
        signals.append(signal)
        outcomes.append(MemberOutcome(record.field, MemberOutcomeCode.SIGNAL_EMITTED))

    _check_no_collisions(signals)
    return _SignalBuild(
        signals=tuple(signals),
        outcomes=tuple(outcomes),
        refusals=tuple(refusals),
        member_sets=tuple(member_sets[position] for position in sorted(member_sets)),
    )


def _tree(records: Sequence[ObservedField]) -> tuple[list[int | None], list[list[int]]]:
    """``(parents, children)`` by record position, from ``depth`` and document order.

    The walk emits a container record at its **opening byte**, so a container always precedes its
    members in document order and a stack keyed on ``depth`` is exactly the containment. Positions
    are used rather than key paths because a JSON document may state the same key twice — the
    parser emits both records rather than merging them — and a path-keyed map would silently
    collapse them into one container.
    """
    parents: list[int | None] = [None] * len(records)
    children: list[list[int]] = [[] for _ in records]
    open_at_depth: dict[int, int] = {}
    for position, record in enumerate(records):
        if record.depth == 0:
            open_at_depth = {0: position}
            continue
        parent_position = open_at_depth.get(record.depth - 1)
        parents[position] = parent_position
        if parent_position is not None:
            children[parent_position].append(position)
        if record.value_type is ValueType.NESTED:
            open_at_depth[record.depth] = position
    return parents, children


def _read_member_set(
    *,
    reading: PayloadReading,
    position: int,
    record: ObservedField,
    parent: ObservedField,
    children: list[list[int]],
    member_sets: dict[int, MemberSetReading],
    refusals: list[SignalRefusal],
    outcomes: list[MemberOutcome],
) -> None:
    """Record an array's membership, or an object's mere existence as a container of members.

    Only **arrays** are member sets, and the asymmetry is the answer rather than an omission: a
    JSON object states *named* members, and the name is the relation — that is
    :attr:`SignalBasis.ATTRIBUTE_KEY`. A JSON array states unnamed members, and there is nothing
    but the position, which is what :attr:`SignalBasis.DOM_RELATION` records.
    """
    kind = _container_kind(reading, record)
    elements = children[position]
    if kind is ContainerKind.ARRAY:
        member_sets[position] = MemberSetReading(
            key_path=record.field,
            kind=MemberSetKind.of(len(elements)),
            element_paths=tuple(records_path(reading, elements)),
            byte_span=record.byte_span,
        )
    code = (
        MemberOutcomeCode.CONTAINER_STATES_MEMBERS
        if elements
        else MemberOutcomeCode.EMPTY_CONTAINER
    )
    outcomes.append(MemberOutcome(record.field, code))


def records_path(reading: PayloadReading, positions: Iterable[int]) -> tuple[str, ...]:
    """The key paths of the records at these positions, in the order given."""
    return tuple(reading.payload.records[position].field for position in positions)


def _container_kind(reading: PayloadReading, record: ObservedField) -> ContainerKind | None:
    """``OBJECT`` or ``ARRAY`` from the record's own opening byte, or ``None`` if it is neither.

    Read from the byte rather than inferred from the children's labels: a label says where a
    *value* was read, and deriving a container's kind from it would be a second reading of the
    payload's shape — a second answer to a question the first byte already answered.
    """
    span = record.byte_span
    if span is None or span[0] >= len(reading.body):
        return None
    opener = reading.body[span[0]]
    if opener == _OBJECT_OPENER:
        return ContainerKind.OBJECT
    if opener == _ARRAY_OPENER:
        return ContainerKind.ARRAY
    return None


def _container_end(
    reading: PayloadReading,
    index: MentionOccurrenceIndex,
    position: int,
    record: ObservedField,
    cache: dict[int, _ContainerEnd | SignalRefusal],
    refusals: list[SignalRefusal],
) -> _ContainerEnd | SignalRefusal:
    """The container's resolved subject end, resolved once per container and then shared.

    Cached by record position rather than by key path, because a payload may state the same key
    twice and the two containers are two structures.
    """
    cached = cache.get(position)
    if cached is not None:
        return cached

    # Text first, and the order is the argument: a body the caller supplied that does not contain
    # the container's bytes is the *cause*, and reading the opening byte out of it reports a
    # symptom instead. "The container's own text is not in this reading" is the refusal an
    # operator can act on; "its opening byte opens neither a brace nor a bracket" is what that
    # looks like from inside.
    try:
        text = reading.container_text(record)
    except _ContainerTextUnavailable as exc:
        refusal = SignalRefusal(
            code=SignalRefusalCode.CONTAINER_TEXT_UNAVAILABLE.value,
            key_path=record.field,
            detail=(
                f"{record.field!r} spans {record.byte_span} and the body supplied to this reading "
                f"is {len(reading.body)} byte(s), so its own text cannot be read: [{exc.code}] "
                f"{exc.detail}. A container's mention is its own bytes, and addressing the nearest "
                "ones would state a position nobody read"
            ),
        )
        refusals.append(refusal)
        cache[position] = refusal
        return refusal

    kind = _container_kind(reading, record)
    if kind is None:
        refusal = SignalRefusal(
            code=SignalRefusalCode.CONTAINER_KIND_UNKNOWN.value,
            key_path=record.field,
            detail=(
                f"{record.field!r} is recorded as a container but the byte at "
                f"{record.byte_span[0] if record.byte_span else '(no span)'} opens neither a JSON "
                "object nor a JSON array. The kind of a container decides whether its members are "
                "key/value pairs or a member set, so an unreadable kind cannot be guessed at from "
                "the children's labels"
            ),
        )
        refusals.append(refusal)
        cache[position] = refusal
        return refusal

    surface_bytes = len(text.encode("utf-8"))
    if surface_bytes > MAX_CONTAINER_SURFACE_BYTES:
        refusal = SignalRefusal(
            code=SignalRefusalCode.CONTAINER_SURFACE_TOO_LARGE.value,
            key_path=record.field,
            detail=(
                f"{record.field!r} is {surface_bytes} byte(s) of its own text, over this stage's "
                f"ceiling of {MAX_CONTAINER_SURFACE_BYTES}. A container's mention IS its own text, "
                "so the extent of the read is the extent of the container, and this stage declines "
                "rather than mint a mention of that much JSON. Raise "
                "MAX_CONTAINER_SURFACE_BYTES deliberately, or read the payload's members under "
                "their own containers. This is a bound of the producer, not a truncation of the "
                "parse, and it is recorded here so the payload's silence is visible"
            ),
        )
        refusals.append(refusal)
        cache[position] = refusal
        return refusal

    span = record.byte_span
    address = deferred_occurrence(label=_container_label(kind), surface=text, start=span[0], end=span[1])
    try:
        resolved = index.require_occurrence(address)
    except (MentionBindingError, ValueError) as exc:
        code = getattr(exc, "code", "participant_surface_required")
        refusal = SignalRefusal(
            code=SignalRefusalCode.END_NOT_RESOLVED.value,
            key_path=record.field,
            detail=(
                f"the container {record.field!r} at bytes {list(record.byte_span or ())} addresses "
                f"{address!r} and the mention index refused it: [{code}] {exc}. A signal whose "
                "subject end does not resolve states a relation against a position nobody could "
                "name, which is worse than no signal"
            ),
        )
        refusals.append(refusal)
        cache[position] = refusal
        return refusal

    end = _ContainerEnd(
        mention_id=resolved.mention_id,
        kind=kind,
        byte_span=span,
        surface_bytes=surface_bytes,
    )
    cache[position] = end
    return end


def _container_label(kind: ContainerKind) -> str:
    return CONTAINER_OBJECT_LABEL if kind is ContainerKind.OBJECT else CONTAINER_ARRAY_LABEL


def _value_end_failure(
    *,
    record: ObservedField,
    end: _ContainerEnd,
    parent: ObservedField,
    parents: list[int | None],
    records: Sequence[ObservedField],
    index: MentionOccurrenceIndex,
    bound_by_path: dict[str, Any],
) -> tuple[SignalRefusal, MemberOutcomeCode] | None:
    """The reason this member cannot become a signal's object end, or ``None`` when it can.

    Three refusals, in the order they are tested, and each is a different operator's bug:

    1. the record carries no address at all — the **parser** refused it (``null``, a container, a
       surface with no characters, no span). ``address_refusal`` is a name and is carried into the
       detail rather than re-invented here.
    2. the record's path token says index where the container says object, or the reverse — a
       record set that disagrees with itself.
    3. the address does not resolve in this index, or resolves to an id other than the one the
       caller's binding minted. Both are S4's "a signal whose participants are not all resolved
       must not be constructed", and the second is a *scope* disagreement the ids cannot reveal.
    """
    if not record.addressable:
        refusal_code = record.address_refusal or "field_address_missing"
        return (
            SignalRefusal(
                code=SignalRefusalCode.VALUE_END_NOT_ADDRESSABLE.value,
                key_path=record.field,
                detail=(
                    f"{record.field!r} is a {record.value_type} and the parser gave it no deferred "
                    f"occurrence address: {refusal_code}. A record with no address is kept and "
                    "counted by this reading and by the binding, and it is not bound to whatever "
                    "was nearest - which for a null would be a mention of the word 'null', and for "
                    "a container would be a mention of a region with no words in it"
                ),
            ),
            MemberOutcomeCode.VALUE_END_NOT_ADDRESSABLE,
        )
    wanted_index = end.kind is ContainerKind.ARRAY
    actual_index = _last_token_is_index(record.field)
    if wanted_index != actual_index:
        return (
            SignalRefusal(
                code=SignalRefusalCode.MEMBER_KIND_MISMATCH.value,
                key_path=record.field,
                detail=(
                    f"{record.field!r} ends in {'an index' if actual_index else 'a key'} but its "
                    f"container {parent.field!r} is an "
                    f"{'array' if wanted_index else 'object'}. A record set that disagrees with "
                    "itself about shape cannot be read as structure, and guessing which of the two "
                    "is right would decide the basis of the relation from the disagreement"
                ),
            ),
            MemberOutcomeCode.MEMBER_KIND_MISMATCH,
        )
    try:
        resolved = index.require_occurrence(record.address)
    except MentionBindingError as exc:
        return (
            SignalRefusal(
                code=SignalRefusalCode.END_NOT_RESOLVED.value,
                key_path=record.field,
                detail=(
                    f"{record.field!r} addresses {record.address!r} and this reading's mention "
                    f"index refused it: [{exc.code}] {exc.message}. A signal with an unresolved "
                    "object end states a relation against a position nobody could name, which is a "
                    "wrong relation rather than a partial one"
                ),
            ),
            MemberOutcomeCode.END_NOT_RESOLVED,
        )
    bound = bound_by_path.get(record.field)
    if bound is None or bound.mention_id != resolved.mention_id:
        return (
            SignalRefusal(
                code=SignalRefusalCode.MENTION_ID_SCOPE_MISMATCH.value,
                key_path=record.field,
                detail=(
                    f"{record.field!r} resolves to {resolved.mention_id!r} under this reading's "
                    f"scope but the caller's binding says "
                    f"{getattr(bound, 'mention_id', '(unbound)')!r}. Three of the five keys a "
                    "mention id is minted from are the scope, so the two are different mentions of "
                    "the same bytes and nothing in an id says which produced it. This reading "
                    "refuses to state a relation whose object end is a different reading's mention"
                ),
            ),
            MemberOutcomeCode.MENTION_ID_SCOPE_MISMATCH,
        )
    return None


def _last_token_is_index(field: str) -> bool:
    from extractors.payload.hypotheses import path_tokens

    tokens = path_tokens(field)
    if not tokens:
        return False
    return tokens[-1][0] == "index"


def _element_index(
    record: ObservedField,
    parent: ObservedField,
    parents: list[int | None],
    records: Sequence[ObservedField],
) -> int:
    """The position the payload states for this member, or ``1`` for an object member.

    An array states a position for its elements and an object does not state one for its members,
    so an element's ``ordinal`` is its index and a member's is its place as the second end of the
    pair. The payload's position wins where the payload states one, because
    :attr:`RelationParticipant.ordinal` is documented as *position as observed* — and it is in
    the identity projection, so two elements of one array are two signals and swapping two
    positions changes both ids.
    """
    if parent.value_type is not ValueType.NESTED:
        return 1
    from extractors.payload.hypotheses import path_tokens

    tokens = path_tokens(record.field)
    if tokens and tokens[-1][0] == "index":
        return int(tokens[-1][1])
    return 1


def _signal(
    *,
    reading: PayloadReading,
    scope: ExtractionScope,
    record: ObservedField,
    parent: ObservedField,
    end: _ContainerEnd,
    member_mention_id: str,
    ordinal: int,
    member_index: int,
) -> RelationSignal:
    """One observed connection, with the basis, the surface and the neighbourhood that produced it.

    ``relation_ref`` is **unset** and this is the load-bearing omission: it means "the producer
    knows the operator", and this producer read a container's membership. ``relation_surface`` is
    the key path — a real artifact of the payload's grammar, and *not* a verb, because a JSON
    document contains none and writing one here would attribute a word this producer chose to the
    source in the field a reader reaches for first.

    ``producer_confidence`` and both participants' ``confidence`` are ``1.0``, and the sense is
    the narrow one the contract gives them: the producer is certain **of its own reading of the
    structure** — that this container states this member at these bytes — and says nothing at all
    about whether any relation holds in the world. :class:`~extractors.signals.signal.RelationSignal`
    has no field for the latter, and that absence is why ``producer_confidence`` is named
    separately in the first place.
    """
    structured = end.kind is ContainerKind.ARRAY
    kind = SignalKind.STRUCTURAL if structured else SignalKind.ATTRIBUTE
    basis = SignalBasis.DOM_RELATION if structured else SignalBasis.ATTRIBUTE_KEY
    relation_word = "member of" if structured else "key of"
    member_span = record.byte_span
    parent_span = end.byte_span
    member_bytes = 0 if member_span is None else member_span[1] - member_span[0]
    truncated = reading.payload.truncated
    notes = (
        f"relation_surface is the payload's own key path, not a verb and not a predicate name: "
        f"this producer read a {relation_word} a container states and declines to name the "
        f"operator, so relation_ref is unset. The container at bytes "
        f"{[parent_span[0], parent_span[1]]} is the subject end and is addressed at its own text; "
        "its own bytes were read once for the whole container and are counted against every signal "
        "naming it, so characters_scanned is an upper bound on what one signal cost"
    )
    if truncated:
        notes += (
            f". The parse walk stopped at the {reading.payload.truncation_reason!r} ceiling, so "
            f"these records are a prefix of the document and absence here is not absence in it"
        )
    return RelationSignal(
        participants=(
            RelationParticipant(
                mention_ref=end.mention_id,
                slot=ArgumentSlot(0),
                # "container" is the structural role, not a guess at a semantic one: the payload
                # states the relation and does not say what kind of thing the holder is.
                role_hypothesis="container",
                ordinal=0,
                confidence=1.0,
                # The subject is the structure itself rather than a value in the payload, so the
                # ordinary "this end is a thing" shape is the honest one. It is excluded from the
                # identity projection, so a later type-layer correction cannot re-key the relation.
                argument_shape="entity",
            ),
            RelationParticipant(
                mention_ref=member_mention_id,
                slot=ArgumentSlot(1),
                role_hypothesis="array_element" if structured else "field_value",
                ordinal=member_index,
                confidence=1.0,
                # A scalar the payload wrote at this position. ``ValueType.NUMBER`` and
                # ``ValueType.BOOL`` are the two FR-012 names directly, and a string is the same
                # case: the payload states a *literal*, not a resolved thing, and a hypothesis
                # about what the literal denotes is a different stage's question.
                argument_shape="value",
            ),
        ),
        kind=kind,
        # Stated per read path, and the two bases are not interchangeable: an object member is a
        # key/value pair and an array element is a containment. Omitting this does not leave it
        # unset — ``run_producer`` sees a signal whose producer declares two kinds, finds that
        # exactly one of them (``ATTRIBUTE``) implies a basis, and stamps ``ATTRIBUTE_KEY`` onto
        # every signal, so an array membership would be filed as a key/value pair. Passing it in
        # is what stops the registry's inference from becoming the answer.
        basis=basis,
        relation_surface=record.field,
        neighbourhood=Neighbourhood(
            characters_scanned=end.surface_bytes + member_bytes,
            # Stated, not computed. This producer reads membership and compares no pair of
            # mentions; a non-zero count here would be claiming a search it did not run.
            pairs_considered=0,
            scope_read=(
                f"one captured JSON payload: the {end.label} at bytes "
                f"[{parent_span[0]}, {parent_span[1]}) and its {relation_word} at bytes "
                f"[{member_span[0]}, {member_span[1]}) in segment {reading.segment_ref!r} of "
                f"capture {reading.capture_ref!r}. No other document, container, or pair of "
                "mentions was read"
            ),
            precision=PRECISION_BOUNDED if truncated else PRECISION_WHOLE,
            notes=notes,
        ),
        # Stated, not defaulted: a container stating a member asserts nothing to deny, and
        # Phase 4C deleted the member that used to be able to say otherwise.
        polarity=Polarity.ASSERTED,
        # The nesting orders the ends. A container states its members; a member does not state the
        # container, and the key that names the member is read off the container's own grammar.
        direction=DirectionHypothesis.SUBJECT_TO_OBJECT,
        # Unset, and the whole argument: this producer did not read an operator.
        relation_ref=None,
        producer_ref=PRODUCER_REF,
        producer_version=PRODUCER_VERSION,
        context_ref=scope.context_ref,
        semantic_regime_ref=scope.semantic_regime_ref,
        capture_ref=scope.document_ref,
        signal_ordinal=ordinal,
        tenant_id=scope.tenant_id,
        notes=notes,
        extra={
            "field_path": record.field,
            "container_path": parent.field,
            "container_kind": str(end.kind),
            "relation_surface_kind": "key_path",
            "element_index": member_index if end.kind is ContainerKind.ARRAY else None,
            "payload_truncated": truncated,
            "value_type": str(record.value_type),
        },
    )


def _check_no_collisions(signals: Sequence[RelationSignal]) -> None:
    """Refuse two distinct members arriving on one ``signal_id``.

    :func:`~extractors.signals.signal.dedupe_by_content` collapses one signal id that arrives
    twice, which is right for a producer reading one structure twice and **wrong** if two different
    members of a payload address to one id — that would be a collision in the five-key mint, and
    the record would then claim two members where the substrate has one. Fail-closed and named.
    """
    seen: dict[str, str] = {}
    for signal in signals:
        path = str(signal.extra.get("field_path", ""))
        previous = seen.setdefault(signal.signal_id, path)
        if previous != path:
            raise SignalContractError(
                "payload_signal_identity_collision",
                f"{previous!r} and {path!r} both address to {signal.signal_id!r}. The mint is over "
                "five keys and a position is one of them, so two members of one payload cannot "
                "collide unless something upstream read one of them wrongly. Refusing rather than "
                "collapsing, because dedupe would turn a collision into a silent loss",
            )


@dataclass(frozen=True, slots=True)
class StructuralReading:
    """Everything one payload's structure yielded, and the accounting that nothing was lost.

    Three refusal vocabularies, each with exactly one owner, and never folded together:

    ``parse_refusals``
        verbatim from :attr:`ParsedPayload.refusals` — the parser's own.
    ``mention_refusals``
        verbatim from :attr:`BoundPayload.refusals` — the binding's own.
    ``signal_refusals``
        this stage's, under :class:`SignalRefusalCode`. Every entry is also a
        :class:`MemberOutcome` on the record it concerns, so the outcome table and the refusal list
        cannot disagree about which record was excluded.

    ``truncated`` and ``truncation_reason`` are **derived** from ``bound_hit`` rather than
    carried, exactly as :class:`ParsedPayload` derives them, so a reading cannot report itself whole
    while its own bound hit says otherwise.
    """

    payload: ParsedPayload
    signals: tuple[RelationSignal, ...] = ()
    hypotheses: HypothesisReading = field(default_factory=HypothesisReading)
    member_outcomes: tuple[MemberOutcome, ...] = ()
    signal_refusals: tuple[SignalRefusal, ...] = ()
    parse_refusals: tuple[PayloadRefusal, ...] = ()
    mention_refusals: tuple[PayloadRefusal, ...] = ()
    member_sets: tuple[MemberSetReading, ...] = ()
    bound_hit: Any = None
    capture_ref: str = ""
    segment_ref: str = ""
    extractor_ref: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "signals", tuple(self.signals or ()))
        object.__setattr__(self, "member_outcomes", tuple(self.member_outcomes or ()))
        object.__setattr__(self, "signal_refusals", tuple(self.signal_refusals or ()))
        object.__setattr__(self, "parse_refusals", tuple(self.parse_refusals or ()))
        object.__setattr__(self, "mention_refusals", tuple(self.mention_refusals or ()))
        object.__setattr__(self, "member_sets", tuple(self.member_sets or ()))
        object.__setattr__(self, "capture_ref", str(self.capture_ref or ""))
        object.__setattr__(self, "segment_ref", str(self.segment_ref or ""))
        object.__setattr__(self, "extractor_ref", str(self.extractor_ref or ""))

    @property
    def truncated(self) -> bool:
        """Whether a ceiling stopped the parse walk. Derived from ``bound_hit``, never carried."""
        return self.bound_hit is not None

    @property
    def truncation_reason(self) -> str:
        """The name of the ceiling that stopped the walk, or ``""`` when none did."""
        return "" if self.bound_hit is None else str(self.bound_hit.bound)

    @property
    def record_count(self) -> int:
        """How many records the payload states — the denominator of the accounting."""
        return len(self.payload.records)

    @property
    def accounted(self) -> bool:
        """Whether every record got exactly one outcome. The checkable form of "nothing dropped"."""
        return len(self.member_outcomes) == len(self.payload.records)

    @property
    def unaccounted_paths(self) -> tuple[str, ...]:
        """The records with no outcome, in document order. Empty on any coherent reading."""
        seen = {outcome.key_path for outcome in self.member_outcomes}
        return tuple(
            record.field for record in self.payload.records if record.field not in seen
        )

    @property
    def refusal_codes(self) -> tuple[str, ...]:
        """Every refusal code, parser's then the binding's then this stage's, in that order.

        Three vocabularies concatenated rather than merged, so each list has one owner and a caller
        that histograms this one still knows which layer said what.
        """
        return (
            tuple(refusal.code for refusal in self.parse_refusals)
            + tuple(refusal.code for refusal in self.mention_refusals)
            + tuple(refusal.code for refusal in self.signal_refusals)
        )

    @property
    def refusal_details(self) -> str:
        """Every refusal detail, in the same order as :attr:`refusal_codes`.

        Published because a code names the shape of a failure and only the detail says which
        record, which bytes and which underlying code — and a caller triaging a payload needs the
        second without opening three types.
        """
        return "\n".join(
            [refusal.detail for refusal in self.parse_refusals]
            + [refusal.detail for refusal in self.mention_refusals]
            + [refusal.detail for refusal in self.signal_refusals]
        )

    def signals_for(self, key_path: str) -> tuple[RelationSignal, ...]:
        """The signals whose object end is this key path, in emission order."""
        wanted = str(key_path or "")
        return tuple(
            signal
            for signal in self.signals
            if str(signal.extra.get("field_path", "")) == wanted
        )

    def member_set_at(self, key_path: str) -> MemberSetReading | None:
        """The array this key path states, or ``None`` if it states no array."""
        wanted = str(key_path or "")
        return next((entry for entry in self.member_sets if entry.key_path == wanted), None)

    def to_dict(self) -> dict[str, Any]:
        """The whole reading, in declared field order — the form the determinism test digests."""
        return {
            "capture_ref": self.capture_ref,
            "segment_ref": self.segment_ref,
            "extractor_ref": self.extractor_ref,
            "declared_parser": self.payload.declared_parser,
            "parser_is_identity": self.payload.parser_is_identity,
            "routed_to": self.payload.routed_to,
            "truncated": self.truncated,
            "truncation_reason": self.truncation_reason,
            "bound_hit": None if self.bound_hit is None else self.bound_hit.to_dict(),
            "record_count": self.record_count,
            "accounted": self.accounted,
            "signals": [signal.to_dict() for signal in self.signals],
            "hypotheses": self.hypotheses.to_dict(),
            "member_outcomes": [outcome.to_dict() for outcome in self.member_outcomes],
            "member_sets": [entry.to_dict() for entry in self.member_sets],
            "signal_refusals": [refusal.to_dict() for refusal in self.signal_refusals],
            "parse_refusals": [refusal.to_dict() for refusal in self.parse_refusals],
            "mention_refusals": [refusal.to_dict() for refusal in self.mention_refusals],
        }

    def content_key(self) -> str:
        """Identity of this reading, through the shared canonical-JSON convention.

        Order-sensitive on purpose: the signals come back in document order and a reading whose
        order changed is a reading whose provenance changed.
        """
        return content_key(self.to_dict())


def read_payload_structure(
    reading: PayloadReading,
    *,
    scope: ExtractionScope,
    schemas: Iterable[DeclaredSchema] = (),
) -> StructuralReading:
    """One payload's structure, as signals and cited type hypotheses, in one pass.

    The type hypotheses run over the same records **regardless** of whether the payload was JSON:
    the two vocabularies answer two different questions, and a text payload's records genuinely
    have no key segment, which :mod:`extractors.payload.hypotheses` says under
    ``key_path_unreadable`` rather than leaving to inference.

    The signals are produced by driving this stage's own producer through
    :func:`~extractors.signals.protocol.run_producer`, so the registry stamps who spoke, checks the
    declared pair ceiling, refuses a signal whose basis it cannot account for, and collapses
    anything that arrives twice by content. The build's outcomes and refusals are read off the
    producer's single pass rather than re-walked, so the payload is walked once.

    **The capture cross-check.** ``scope.document_ref`` must be the reading's ``capture_ref``,
    because the registry overwrites every signal's ``capture_ref`` from the scope and
    ``capture_ref`` is in the identity material: a scope naming a different retrieval would
    re-address every signal this stage just resolved, and a blank one would produce signals that
    cannot be traced to any retrieval at all. Both are refused here with a code rather than
    tolerated.
    """
    if not str(scope.document_ref or "").strip():
        raise SignalContractError(
            "payload_reading_capture_required",
            "this producer describes ONE retrieved payload, and the scope names no document_ref to "
            "describe it by. Every signal it emits has capture_ref in its identity material, so a "
            "blank one mints signals that cannot say which fetch saw them, and a scope naming a "
            "different one would re-address mentions this stage resolved against a different "
            "reading (I-3, FR-018). Supply the capture id, or do not run the producer",
        )
    if str(scope.document_ref).strip() != reading.capture_ref:
        raise SignalContractError(
            "payload_reading_capture_mismatch",
            f"this reading is scoped to capture {reading.capture_ref!r} and the extraction scope "
            f"names {scope.document_ref!r}. The scope is stamped onto every signal and its "
            "capture_ref is part of the signal's address, so the two disagreeing would re-address "
            "every signal in place of the reading the mentions were resolved under",
        )
    producer = PayloadStructureExtractor(reading)
    signals = run_producer(producer, (reading.payload,), scope=scope)
    build = producer.build
    assert build is not None, "run_producer returned without calling extract"
    return StructuralReading(
        payload=reading.payload,
        signals=tuple(signals),
        hypotheses=read_type_hypotheses(reading.payload.records, schemas=schemas),
        member_outcomes=build.outcomes,
        signal_refusals=build.refusals,
        parse_refusals=reading.payload.refusals,
        mention_refusals=reading.bound.refusals,
        member_sets=build.member_sets,
        bound_hit=reading.payload.bound_hit,
        capture_ref=reading.capture_ref,
        segment_ref=reading.segment_ref,
        extractor_ref=reading.extractor_ref,
    )


def payload_structure_signals(
    payload: ParsedPayload,
    *,
    body: bytes,
    capture_ref: str,
    segment_ref: str,
    extractor_ref: str,
    scope: ExtractionScope,
) -> tuple[RelationSignal, ...]:
    """Bind ``payload`` under the given scope and return only its signals.

    A convenience for a caller that wants the observations and not the accounting, with the same
    guarantee: the binding is made here, under the same three values, so the mention ids it resolves
    are the ones a caller repeating the call would get. A caller that needs the refusals, the
    member sets or the hypotheses calls :func:`read_payload_structure` instead.
    """
    from parsers.payload import bind_records

    reading = PayloadReading(
        payload=payload,
        body=body,
        bound=bind_records(
            payload,
            capture_ref=capture_ref,
            segment_ref=segment_ref,
            extractor_ref=extractor_ref,
        ),
        capture_ref=capture_ref,
        segment_ref=segment_ref,
        extractor_ref=extractor_ref,
    )
    return read_payload_structure(reading, scope=scope).signals


__all__ = [
    "CONTAINER_ARRAY_LABEL",
    "CONTAINER_OBJECT_LABEL",
    "INDEPENDENCE_FAMILY",
    "MAX_CONTAINER_SURFACE_BYTES",
    "MAX_PAIRS_CONSIDERED",
    "PRECISION_BOUNDED",
    "PRECISION_WHOLE",
    "PRODUCER_REF",
    "PRODUCER_VERSION",
    "SIGNAL_REFUSAL_CODES",
    "ContainerKind",
    "MemberOutcome",
    "MemberOutcomeCode",
    "MemberSetKind",
    "MemberSetReading",
    "PayloadReading",
    "PayloadStructureExtractor",
    "ReadingContractError",
    "SignalRefusal",
    "SignalRefusalCode",
    "StructuralReading",
    "payload_occurrence_index",
    "payload_structure_signals",
    "read_payload_structure",
]
