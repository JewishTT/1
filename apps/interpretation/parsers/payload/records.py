"""What a parser emits: **a record of observed structure, and nothing else**.

Feature 021 brief §25 (a producer sits below mention extraction), §16
(:class:`~domain.signal_basis.SignalBasis` answers "how do you know?"), and §26
(:mod:`domain.mention_occurrence_index` is the mention seam); ``ARBITRATION`` §8
(``MENTION_BINDING`` / ``MN-``); constitution IV (fail-closed) and VI (determinism,
Domain Invariant 12).

**Why this module exists, stated as the defect it closes.** A captured page arrives as
bytes (:class:`sources.executor.CapturePage` keeps them raw, which is right), and upstream
then collapsed six epistemic levels into one record: a regex hit, a key-name heuristic, a
type assertion, a mention and a resolution result all arrive as ``Entity(type, value,
source, context, confidence, attributes, sources)`` with ``confidence`` defaulted to ``1.0``.
A payload field named ``email`` therefore produced an *email entity at full confidence* from
a payload that only said the word "email" once. :class:`ObservedField` is the record that
replaces it: four facts the bytes actually state — where the value is, what it is, what kind
of bytes it is, and which of those bytes it occupies — plus the deferred address that lets a
mention layer resolve it later.

**The type in this record is a fact about the bytes, and that is the whole of what it is.**
:attr:`ObservedField.value_type` is one of :class:`ValueType`, which is exactly the JSON
scalar inventory plus ``nested``: ``string``, ``number``, ``bool``, ``null``, ``nested``. A
string is reported as a string because the payload wrote quotes around it. Nothing here says
*what a string is* — no ``email``, no ``ipv4``, no ``person`` — because deciding that is a
type hypothesis, it belongs to a later stage, and a parser that guesses is a parser whose
output cannot be audited against its input. The catalogue's ``entity_hints`` are a *hint a
definition declares about itself*, they are not observations of the bytes, and this module
reads neither them nor anything else about a definition except the two parser fields.

**What is deliberately absent, and each absence has a reason.**

``confidence``
    Upstream defaulted it to ``1.0``, which is a fabricated number: it asserted a level of
    certainty nobody measured. There is no confidence field here, and adding one later is a
    stage that has evidence to put in it — a source's declared contact level, a re-read of the
    same field by another instrument, a schema the source publishes. A record with no
    confidence is honest about being an observation; a record with ``1.0`` is a claim.
``type`` in the sense of "what this thing is"
    Only :attr:`ObservedField.value_type`, and only about the bytes. See above.
``entity_id`` / ``mention_id`` / ``resolution``
    The address is a *deferred occurrence*, minted by
    :func:`extractors.signals.mentions.deferred_occurrence` (which delegates to
    :func:`domain.mention_occurrence_index.mint_occurrence_address`), so a producer names a
    position and never an identity (brief §25, FR-019). Nothing here resolves anything, and
    there is no field for a resolution to be written into.
``parser`` deciding whether a record is *useful*
    A field called ``applies_to: [ipv4, ipv6]`` is a filtering decision, and a filtering
    decision at this layer is a silent drop: a source whose payload grew a field we did not
    anticipate would report as though it had said less than it did. The record set is a
    function of the bytes and the bounds only.

**Why every record carries either an address or a named refusal.** A record that is dropped
for want of an address is a record whose absence nobody can see: the caller cannot tell
"this payload had nothing there" from "this payload had a value the parser could not
address". So :attr:`ObservedField.address_refusal` is not diagnostic decoration — it is the
record's way of saying *there is a value here and it is not addressable*, with a code that
counts (:func:`ObservedField.require_address` is the fail-closed front door). The codes are
:data:`ADDRESS_REFUSAL_CODES` and the set is closed.

**Determinism is structural, not aspirational (constitution VI, Domain Invariant 12).** No
clock, no randomness, no ``set`` and no dict iteration order anywhere in the record order:
records arrive in **document order** because the scanner walks the payload left to right and
appends as it goes, and every ``to_dict`` is built in declared field order. The one thing
that makes that claim checkable rather than believed is :meth:`ObservedField.as_tuple`, whose
width is :data:`OBSERVED_FIELD_KEY_COUNT` — a sixth field added for convenience is then a
change to a number this module publishes, and two records of different shape cannot share a
comparison key by accident.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from extractors.signals.mentions import deferred_occurrence

#: The version of the record shape this module emits. It is in every payload's
#: :meth:`ParsedPayload.to_dict` because a record set read by a consumer written against a
#: different shape is a misread, and the cheapest guard is a string the consumer can compare.
PAYLOAD_RECORD_VERSION = "1"

#: The width of :meth:`ObservedField.as_tuple`, published so "a record is these facts and no
#: others" is checkable against a number. A field added later and forgotten here would be
#: read back as equal to a record that does not carry it.
OBSERVED_FIELD_KEY_COUNT = 6


class PayloadContractError(ValueError):
    """A parser-layer refusal a caller asked for as an exception rather than as a record.

    Carries the same stable snake_case ``code`` shape as
    :class:`extractors.signals.signal.SignalContractError`,
    :class:`domain.mention_occurrence_index.MentionBindingError` and
    :class:`parsers.shallow.ParserContractError`, so one caller can switch on any of them by
    ``.code`` rather than by type. Every code here is **fail-closed** (constitution IV): the
    alternative to a named refusal is a record that looks addressable and is not.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class ValueType(StrEnum):
    """What the bytes are, in the payload's own grammar — five members, no more.

    The inventory is JSON's scalar set plus one member for a container, and it is a
    **closed** enumeration for the same reason :class:`~domain.signal_basis.SignalBasis` is:
    a value type nobody can enumerate cannot be audited. Read each member as an answer to
    "what did the payload write here?", never to "what is this?":

    ``STRING``
        the payload wrote quotes. ``"jane@acme.example"`` is a string; whether it is an email
        address is a hypothesis and is not in this module.
    ``NUMBER``
        the payload wrote a JSON number literal. The literal text is preserved verbatim —
        ``1e3`` stays ``1e3`` and is never reformatted to ``1000.0``, because reformatting is
        a transformation of the source and this record reports the source.
    ``BOOL``
        the payload wrote ``true`` or ``false``. ``true`` is the two bytes of the word, and
        what they assert about the world is somebody else's question.
    ``NULL``
        the payload wrote ``null``, which is an observation about the *absence* of a value
        and therefore the one scalar that carries no surface worth addressing.
    ``NESTED``
        the payload wrote ``{`` or ``[``. The record states that a container is here and
        names its byte span; its children are separate records at their own paths.
    """

    STRING = "string"
    NUMBER = "number"
    BOOL = "bool"
    NULL = "null"
    NESTED = "nested"


#: Every value type, in declaration order. For serialisation and for the per-type ceiling,
#: which is keyed by these tokens — never by ``set`` iteration order.
VALUE_TYPES: tuple[ValueType, ...] = tuple(ValueType)

#: The types a deferred occurrence can be minted for, and the reason the other two are not.
#:
#: The exclusion is **not** a judgement about meaning: a number may well name something to a
#: later stage, and refusing it here would be that stage's decision made in advance. It is a
#: statement about what the payload presents *at that position*. ``null`` presents the
#: absence of a value — minting a mention of the word "null" would make a payload's silence
#: into a mention of a thing named null — and a container presents no value at its own span,
#: only at the spans of its children, which are their own records.
ADDRESSABLE_VALUE_TYPES: tuple[ValueType, ...] = (
    ValueType.STRING,
    ValueType.NUMBER,
    ValueType.BOOL,
)


class PayloadLabel(StrEnum):
    """Which named position of which structure an occurrence was read at.

    A **closed** vocabulary of four, and it is closed for the reason FR-009 gives for
    participant labels: two producers labelling one occurrence differently would address it
    as two participants and corroborate nothing. So a label here is never a word anybody
    chose — it is one of "the document root", "a key of a JSON object", "an element of a JSON
    array", "a line of a payload routed as text".

    The field *path* is deliberately **not** in the label. The path is a fact about the
    payload and it is carried on :attr:`ObservedField.field`, where a caller can read it; the
    address carries the label because the address is minted per occurrence and is content
    addressed, so putting a whole path in it would make two occurrences of the same value at
    the same position in differently shaped documents address two mentions of one thing.
    """

    JSON_ROOT = "json_root"
    JSON_FIELD = "json_field"
    JSON_ELEMENT = "json_element"
    TEXT_LINE = "text_line"


#: Every address refusal, as a closed vocabulary, so "how much of this payload was not
#: addressable" is a count over a list rather than a judgement over prose. Every code names a
#: record that **exists**: none of them is a silent drop.
ADDRESS_REFUSAL_CODES: tuple[str, ...] = (
    # The value is a container; its children are their own records.
    "field_value_is_nested",
    # The value is the literal ``null`` — the payload states there is no value here.
    "field_value_is_null",
    # The value is present but has no characters, so there is nothing to address.
    "field_surface_empty",
    # The producing parser could not state a position for the value.
    "field_has_no_byte_span",
    # The mint itself refused; the surface was not addressable after all.
    "occurrence_address_mint_refused",
    # Neither an address nor a refusal is carried: the record is malformed and is refused
    # here rather than read as unaddressable.
    "field_address_missing",
)


@dataclass(frozen=True, slots=True)
class PayloadRefusal:
    """One thing the parser declined to say, with the code a caller counts by.

    ``offset`` is a byte offset into the payload when the refusal has a position (a malformed
    token, an undecodable string, a bound that stopped the walk) and ``None`` when it does not
    (an empty payload, an unknown declared parser). It is optional **only** because some
    refusals are about the payload as a whole, and it is always ``int | None`` rather than a
    sentinel offset so "no position" cannot be confused with "position zero".
    """

    code: str
    detail: str
    offset: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", str(self.code))
        object.__setattr__(self, "detail", str(self.detail))
        if self.offset is not None and not isinstance(self.offset, int):
            object.__setattr__(self, "offset", None)

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "detail": self.detail, "offset": self.offset}


@dataclass(frozen=True, slots=True)
class ParseBounds:
    """The three ceilings a structured walk runs under, and the defaults it runs under.

    **Why bounds at all, when the platform's whole argument is that it does not lose facts.**
    Because an unbounded walk on a hostile payload does not lose facts quietly, it loses them
    *expensively*: a 10 MB JSON body is a few hundred thousand nodes, and a consumer that
    materialised all of them would be a consumer that could not answer for the ones it
    dropped. So the walk is bounded, and — this is the load-bearing half — **hitting a bound
    is a recorded fact** (:class:`BoundHit` on :attr:`ParsedPayload.bound_hit`), never a
    silent stop. A bounded parse that says "I stopped at node 8192" is a measurement; an
    unbounded parse that timed out somewhere downstream is a source that looks empty when it
    is not.

    ``max_nodes``
        node visits, counting every value the walk reaches: each scalar and each container.
        This is the ceiling that bounds a 10 MB body.
    ``max_records_per_value_type``
        records emitted **per** :class:`ValueType`. Separate from the node ceiling because the
        two bound different failure shapes: a payload with a million one-character strings
        hits the per-type ceiling long before the node ceiling, and a payload with a million
        containers never hits it at all.
    ``max_depth``
        container nesting. Bounds the recursion the scanner performs and the length of a field
        path; it is what makes a deeply nested body a measurement rather than a stack
        overflow. **It is the one bound with an environment underneath it**: the structured walk
        is recursive, so a ``max_depth`` set far above the interpreter's recursion limit will be
        met by a ``RecursionError`` before the ceiling is. That is caught by the registry and
        recorded as ``parser_raised`` rather than propagated (constitution IV), so the layer stays
        total — but a caller who wants the bound rather than the fault should keep it near the
        default, and a test pins that the default is nowhere near the interpreter's limit.

    All three are declared here, named here and published here, and
    :meth:`ParsedPayload.bound_hit` names which one fired, at what ceiling, and with what
    observed value.
    """

    max_nodes: int = 8192
    max_records_per_value_type: int = 4096
    max_depth: int = 64

    def __post_init__(self) -> None:
        for name in ("max_nodes", "max_records_per_value_type", "max_depth"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise PayloadContractError(
                    "parse_bounds_invalid",
                    f"{name}={value!r} is not a ceiling. A bound of zero or less is not a "
                    "bound, it is a parser that refuses everything while claiming to be "
                    "bounded, and a non-integer cannot be compared against a count. Pass a "
                    "positive int",
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_nodes": self.max_nodes,
            "max_records_per_value_type": self.max_records_per_value_type,
            "max_depth": self.max_depth,
        }


#: The ceilings a read runs under when a caller states none, as one named object.
#:
#: A module-level singleton rather than a ``ParseBounds()`` call in each signature for two
#: reasons: the defaults become **one value a caller can read, print and compare against** rather
#: than a number restated in five signatures, and :class:`ParseBounds` is frozen, so sharing one
#: instance is the same as constructing one each time — with the difference that the shared one
#: can be cited.
DEFAULT_BOUNDS: ParseBounds = ParseBounds()


@dataclass(frozen=True, slots=True)
class BoundHit:
    """One ceiling that stopped a walk, stated as a fact about the walk.

    ``bound`` is one of :data:`BOUND_NAMES`; ``ceiling`` is the limit in force and
    ``observed`` is what the walk had reached when it stopped — so a caller can see *how far
    past the edge* it was rather than only that it stopped. ``value_type`` is set only for
    ``records_of_value_type``, naming which type's ceiling fired, because "a per-type ceiling
    fired" without saying which type is half a measurement.
    """

    bound: str
    ceiling: int
    observed: int
    value_type: str = ""

    def __post_init__(self) -> None:
        name = str(self.bound)
        if name not in BOUND_NAMES:
            raise PayloadContractError(
                "bound_name_unknown",
                f"{name!r} is not a declared bound. The declared bounds are "
                f"{list(BOUND_NAMES)}, and a hit on anything else cannot be read by a "
                "caller that is counting hits",
            )
        object.__setattr__(self, "bound", name)
        object.__setattr__(self, "ceiling", int(self.ceiling))
        object.__setattr__(self, "observed", int(self.observed))
        object.__setattr__(self, "value_type", str(self.value_type or ""))

    def to_dict(self) -> dict[str, Any]:
        return {
            "bound": self.bound,
            "ceiling": self.ceiling,
            "observed": self.observed,
            "value_type": self.value_type,
        }


#: Every bound name, as a vocabulary. :class:`BoundHit` refuses anything outside it, so
#: "the walk stopped" is always one of three named things.
BOUND_NAMES: tuple[str, ...] = ("nodes_visited", "records_of_value_type", "depth")


def _value_type_of(value_type: object) -> ValueType:
    """The :class:`ValueType` for ``value_type``, refused by name rather than coerced.

    A record whose type is not one of the five is a record whose type cannot be read, and
    ``ValueType("email")`` failing with an enum's own ``ValueError`` would be a refusal with no
    code — a caller histograming refusals would have to catch the type as well as the code.
    """
    try:
        return ValueType(value_type)
    except ValueError:
        raise PayloadContractError(
            "field_value_type_unknown",
            f"{value_type!r} is not a value type. The closed inventory is "
            f"{[str(value) for value in VALUE_TYPES]}, and it is closed because a value type is "
            "an observation about bytes; 'email' and 'ipv4' are hypotheses and belong to the "
            "stage that makes them",
        ) from None


def _label_of(label: object) -> PayloadLabel:
    """The :class:`PayloadLabel` for ``label``, refused by name rather than coerced."""
    try:
        return PayloadLabel(label)
    except ValueError:
        raise PayloadContractError(
            "field_label_unknown",
            f"{label!r} is not a position label. The closed inventory is "
            f"{[str(member) for member in PayloadLabel]}; a label is structural — which named "
            "position of which structure the read came from — and never a word a producer chose",
        ) from None


@dataclass(frozen=True, slots=True)
class ObservedField:
    """One value the payload states, at one position, in the payload's own grammar.

    The record, field by field:

    ``field``
        the key path — ``$`` for the document root, ``$["items"][0]["name"]`` below it. Object
        keys are rendered JSON-quoted and array indices bare, so the path is **injective for
        every payload**: a key containing a dot or a bracket cannot be confused with nesting,
        which a dotted path would make it.
    ``value``
        the value as the payload states it: for a string, the decoded text; for a number, the
        literal token verbatim (``1e3`` stays ``1e3``); for ``bool`` and ``null``, the word;
        for a container, the empty string — a container has no value at its own span, only at
        the spans of its children, which are separate records.
    ``value_type``
        :class:`ValueType` — an observation about the bytes, never a hypothesis about the
        world.
    ``byte_span``
        ``(start, end)`` byte offsets into the payload body, or ``None`` when the producing
        parser could not state one. ``None`` is a legal, refused state (see
        :attr:`address_refusal`), not a default.
    ``depth``
        how many containers deep the value sits; ``0`` is the document root. Carried because
        "the payload said this at the top level" is an observation a later stage needs and
        would otherwise have to re-derive from the path.
    ``label``
        the :class:`PayloadLabel` for the position — structural, closed, never a chosen word.

    And the pair that makes it mentionable:

    ``address``
        a deferred occurrence address minted by
        :func:`extractors.signals.mentions.deferred_occurrence`, or the empty string.
    ``address_refusal``
        the code from :data:`ADDRESS_REFUSAL_CODES` saying why this record has no address, or
        the empty string. **Exactly one of the two is set**, and :meth:`require_address` is the
        fail-closed door that raises rather than returning an empty string to a caller who
        would bind it.
    """

    field: str
    value: str
    value_type: ValueType
    byte_span: tuple[int, int] | None
    depth: int
    label: PayloadLabel
    address: str = ""
    address_refusal: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "field", str(self.field))
        object.__setattr__(self, "value", str(self.value))
        object.__setattr__(self, "value_type", _value_type_of(self.value_type))
        object.__setattr__(self, "depth", int(self.depth))
        object.__setattr__(self, "label", _label_of(self.label))
        object.__setattr__(self, "address", str(self.address))
        object.__setattr__(self, "address_refusal", str(self.address_refusal))
        span = self.byte_span
        if span is not None:
            start, end = span
            if not isinstance(start, int) or not isinstance(end, int):
                raise PayloadContractError(
                    "field_byte_span_invalid",
                    f"byte_span={span!r} for {self.field!r} is not a pair of integer offsets. "
                    "A half-stated span is a position that cannot be looked up",
                )
            if start < 0 or end < start:
                raise PayloadContractError(
                    "field_byte_span_invalid",
                    f"byte_span={(start, end)} for {self.field!r} is not a forward range inside "
                    "the payload",
                )
            object.__setattr__(self, "byte_span", (int(start), int(end)))
        if self.address and self.address_refusal:
            raise PayloadContractError(
                "field_address_state_invalid",
                f"the record for {self.field!r} carries both an address and the refusal "
                f"{self.address_refusal!r}. A record is either addressable or it names the "
                "reason it is not; both at once means two answers to one question and the "
                "caller has no way to know which it read",
            )

    @property
    def addressable(self) -> bool:
        """Whether this record carries a deferred occurrence address."""
        return bool(self.address)

    def as_tuple(self) -> tuple[str, str, str, tuple[int, int] | None, int, str]:
        """The record's content, in :attr:`field` order, for comparison and for ordering."""
        return (
            self.field,
            self.value,
            str(self.value_type),
            self.byte_span,
            self.depth,
            self.address,
        )

    def require_address(self) -> str:
        """The deferred address, or a named refusal — never an empty string.

        The fail-closed front door, and the reason a record with no address is *refused with a
        name* rather than dropped: an empty string handed to a mention binder is an address
        that resolves to nothing and reports as though it had been bound, which is the failure
        mode constitution IV exists to prevent (a finding is a finding).
        """
        if self.address:
            return self.address
        raise PayloadContractError(
            self.address_refusal or ADDRESS_REFUSAL_CODES[-1],
            f"the record for {self.field!r} (value_type={self.value_type}) has no deferred "
            "occurrence address"
            + (
                f": {self.address_refusal}"
                if self.address_refusal
                else ", and carries no refusal code either, so it is a malformed record rather "
                "than an unaddressable one. A record must say which it is"
            )
            + f". byte_span={self.byte_span}. STOP: addressable means value_type in "
            f"{[str(v) for v in ADDRESSABLE_VALUE_TYPES]} with a non-empty surface and a "
            "stated byte span; do not mint an address from a record that does not have one, "
            "and do not drop the record",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "value": self.value,
            "value_type": str(self.value_type),
            "byte_span": list(self.byte_span) if self.byte_span is not None else None,
            "depth": self.depth,
            "label": str(self.label),
            "address": self.address,
            "address_refusal": self.address_refusal,
        }


def address_for(
    *,
    value: str,
    value_type: ValueType,
    byte_span: tuple[int, int] | None,
    label: PayloadLabel,
) -> tuple[str, str]:
    """``(address, refusal_code)`` for one value — exactly one of the two is non-empty.

    The single place a deferred occurrence is minted, so the rule cannot be re-implemented by
    a second producer and drift from the first. The rule, in the order it is applied:

    1. :attr:`ValueType.NESTED` → ``field_value_is_nested``. A container's span is a region
       containing other values; addressing it would give one mention to a document region and
       every one of its children would be unreachable. Checked **before** the span, because a
       container's span is filled in when its closing byte is read and a container caught
       mid-walk has none yet — reporting "no span" for a container would name a plumbing
       detail instead of the fact that a container is not a surface.
    2. :attr:`ValueType.NULL` → ``field_value_is_null``. See :data:`ADDRESSABLE_VALUE_TYPES`:
       the payload states there is no value here, and that statement is not a nameable thing.
    3. no ``byte_span`` → ``field_has_no_byte_span``. A value nobody can point at cannot be
       addressed, and pointing at the nearest bytes would be a position nobody read.
    4. a surface with no characters in it → ``field_surface_empty``. A mention needs words
       (FR-017); the refusal names the record rather than dropping it.
    5. otherwise the mint is attempted, and a mint that refuses anyway is recorded as
       ``occurrence_address_mint_refused`` rather than escaping as an exception — a record must
       not be able to fail the whole parse by existing.

    **The mint is deferred, and that is what keeps this layer below mention extraction**
    (brief §25, FR-019): it addresses a position, never an identity. No ``MN-`` is written
    here, and no field on this record can hold one.
    """
    if value_type is ValueType.NESTED:
        return "", "field_value_is_nested"
    if value_type is ValueType.NULL:
        return "", "field_value_is_null"
    if byte_span is None:
        return "", "field_has_no_byte_span"
    if not value.strip():
        return "", "field_surface_empty"
    try:
        return (
            deferred_occurrence(
                label=str(label),
                surface=value,
                start=int(byte_span[0]),
                end=int(byte_span[1]),
            ),
            "",
        )
    except ValueError:
        # ``SignalContractError`` is a ``ValueError`` and is read by ``.code``; this module
        # records the refusal under its own vocabulary rather than re-exporting the producer
        # contract's codes, so a caller counting parser-layer refusals counts one list.
        return "", "occurrence_address_mint_refused"


@dataclass(frozen=True, slots=True)
class ExtractorResult:
    """What one extractor read: its records, what it declined, and the ceiling that stopped it.

    The unit a registered parser returns, kept separate from :class:`ParsedPayload` because the
    **registry** owns the routing facts (which name was declared, whether the definition says
    the parser is the identity, which extractor ran) and the extractor owns only what it read.
    Splitting them is what lets the same two extractors be registered under any number of
    names, and what stops an extractor from deciding what a source *declared* — the one thing
    about a source it has no business deciding.
    """

    records: tuple[ObservedField, ...]
    refusals: tuple[PayloadRefusal, ...] = ()
    bound_hit: BoundHit | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(self, "refusals", tuple(self.refusals))


@dataclass(frozen=True, slots=True)
class ParsedPayload:
    """Everything one parser read out of one captured payload, and the facts about the read.

    ``declared_parser``
        the parser name the source definition declared, verbatim. It is recorded and never
        obeyed by guessing: an unregistered name is a :class:`PayloadRefusal`, not a licence
        to pick a parser.
    ``parser_is_identity``
        the definition's own flag, passed in rather than re-derived, so the catalogue stays
        the one place that decides what "identity parser" means. A name and a flag that
        disagree is a refusal (:func:`parsers.payload.registry`).
    ``routed_to``
        the registered parser that produced :attr:`records`. A caller can always see which
        instrument read the bytes and which name asked for it.
    ``detection``
        :class:`~parsers.payload.detect.Detection` — which rule decided whether this payload
        is JSON text, and what it decided.
    ``bounds`` / ``byte_length`` / ``records`` / ``refusals`` / ``bound_hit``
        the walk itself: the ceilings in force, how many bytes were read, the records in
        document order, everything the parser declined to say, and the ceiling that stopped it
        (``None`` when none did).

    **The properties are derived, not stored, so they cannot disagree with
    :attr:`bound_hit`.** :attr:`truncated` is ``bound_hit is not None`` and
    :attr:`truncation_reason` is its ``bound`` name; a caller cannot read a payload as
    truncated while its bound hit says otherwise, which is exactly the "silent truncation"
    this layer exists to make impossible.
    """

    declared_parser: str
    parser_is_identity: bool
    routed_to: str
    detection: Any
    bounds: ParseBounds
    byte_length: int
    records: tuple[ObservedField, ...]
    refusals: tuple[PayloadRefusal, ...] = ()
    bound_hit: BoundHit | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "declared_parser", str(self.declared_parser))
        object.__setattr__(self, "parser_is_identity", bool(self.parser_is_identity))
        object.__setattr__(self, "routed_to", str(self.routed_to))
        object.__setattr__(self, "byte_length", int(self.byte_length))
        object.__setattr__(self, "records", tuple(self.records))
        object.__setattr__(self, "refusals", tuple(self.refusals))

    @property
    def truncated(self) -> bool:
        """Whether a ceiling stopped the walk. Derived, so it cannot be set independently."""
        return self.bound_hit is not None

    @property
    def truncation_reason(self) -> str:
        """The name of the ceiling that stopped the walk, or ``""`` when none did."""
        return "" if self.bound_hit is None else self.bound_hit.bound

    @property
    def refusal_codes(self) -> tuple[str, ...]:
        """Every refusal code in order — the count a caller histograms, not a judgement call."""
        return tuple(refusal.code for refusal in self.refusals)

    def addressable(self) -> tuple[ObservedField, ...]:
        """The records that carry a deferred occurrence address, in document order."""
        return tuple(record for record in self.records if record.addressable)

    def unaddressable(self) -> tuple[ObservedField, ...]:
        """The records that do not, each with its refusal code — the ones that must not vanish."""
        return tuple(record for record in self.records if not record.addressable)

    def of_value_type(self, value_type: ValueType) -> tuple[ObservedField, ...]:
        """Records of one :class:`ValueType`, in document order."""
        wanted = ValueType(value_type)
        return tuple(record for record in self.records if record.value_type is wanted)

    def read_span(self, body: bytes, record: ObservedField) -> str:
        """The payload bytes this record's span covers, decoded — the span's own witness.

        A span is a claim about a byte range, and the cheapest way for a caller (and a test)
        to check the claim is to slice the payload. Refused by name rather than returned
        empty: a record with no span, or a span outside this body, is a defect in the record
        or in the pairing of record with payload, and both want a name.
        """
        span = record.byte_span
        if span is None:
            raise PayloadContractError(
                "field_has_no_byte_span",
                f"the record for {record.field!r} has no byte span, so there is nothing to "
                "read. Reading a nearest range instead would return bytes nobody said were "
                "there",
            )
        start, end = span
        if start > len(body) or end > len(body):
            raise PayloadContractError(
                "field_byte_span_outside_payload",
                f"the record for {record.field!r} claims bytes [{start}, {end}) of a "
                f"{len(body)}-byte payload. A span that points past the end is a record of "
                "bytes that do not exist",
            )
        return bytes(body[start:end]).decode("utf-8", errors="replace")

    def to_dict(self) -> dict[str, Any]:
        """The whole read, in declared field order — the form the determinism test digests."""
        return {
            "record_version": PAYLOAD_RECORD_VERSION,
            "declared_parser": self.declared_parser,
            "parser_is_identity": self.parser_is_identity,
            "routed_to": self.routed_to,
            "detection": self.detection.to_dict(),
            "bounds": self.bounds.to_dict(),
            "byte_length": self.byte_length,
            "truncated": self.truncated,
            "truncation_reason": self.truncation_reason,
            "bound_hit": None if self.bound_hit is None else self.bound_hit.to_dict(),
            "refusals": [refusal.to_dict() for refusal in self.refusals],
            "records": [record.to_dict() for record in self.records],
        }


__all__ = [
    "ADDRESSABLE_VALUE_TYPES",
    "ADDRESS_REFUSAL_CODES",
    "BOUND_NAMES",
    "DEFAULT_BOUNDS",
    "OBSERVED_FIELD_KEY_COUNT",
    "PAYLOAD_RECORD_VERSION",
    "VALUE_TYPES",
    "BoundHit",
    "ExtractorResult",
    "ObservedField",
    "ParseBounds",
    "ParsedPayload",
    "PayloadContractError",
    "PayloadLabel",
    "PayloadRefusal",
    "ValueType",
    "address_for",
]
