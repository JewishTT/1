"""S1: a type hypothesis with a **cited basis**, and no free-floating number.

Feature 021 brief §16 (how do you know?), §25 (a producer below mention extraction);
constitution IV (fail-closed) and VI (determinism, Domain Invariant 12).

**What this stage is.** It turns ``this payload states ``$["registrant"]["email"]`` = ``a@b.c``
at bytes 41..46`` into *candidate type hypotheses*, and it is the first stage in the chain allowed
to make a judgement — which is exactly why it is the stage most able to lie. The two protections
here are structural rather than procedural:

* **Every hypothesis carries a citation.** :class:`CitedHypothesis` pairs a
  :class:`semantic.blocking.TypeHypothesis` with a :class:`HypothesisCitation` naming the key path
  segment that suggested it, the table row, the table version, and **which epistemic level**
  proposed it (:class:`~extractors.payload.keytable.BasisOrigin.KEY_SPELLING` for a whole key
  segment equalling a word, ``DECLARED_SCHEMA`` for a whole key path bound by a schema the source
  published). A hypothesis whose basis is not in the record is not constructible, because
  :class:`CitedHypothesis` has no way to hold one without one.
* **No hypothesis is emitted with an inherited confidence.**
  :attr:`semantic.blocking.TypeHypothesis.confidence` defaults to ``1.0`` — the very number whose
  inheritance this chain exists to remove — so the single construction site here names it
  explicitly, from a row of the versioned table that :mod:`extractors.payload.keytable` refuses to
  let declare ``1.0``. A mutation that drops the argument is caught by a test that compares every
  emitted confidence against the row its own citation names.

**A record with no hypothesis is a named refusal, never a silence.** Six codes, all of them
statements a caller can histogram:

===============================  =================================================
``key_rule_absent``              no row governs this whole key segment — the
                                 ambiguity answer for ``user_email``, and for every
                                 key nobody has written a rule for
``key_rule_value_type_mismatch`` a row governs it and the observed value type is
                                 not one the row admits (``{"email": 5}``)
``numeric_semantics_require_declared_schema``
                                 the value is a number and **nothing declares what it
                                 means**. This is the answer to "the bytes are a
                                 number, so what?", and it is a refusal rather than a
                                 default type
``member_is_array_indexed``      the record is an element of an array; an index is a
                                 position, not a name
``document_root_has_no_key``     the record is the payload's root
``key_path_unreadable``          the record's ``field`` is not in the parser's path
                                 grammar, so its last segment cannot be read without
                                 guessing — and a key containing ``[`` makes every
                                 convenient split wrong for a payload the platform
                                 really will see
===============================  =================================================

**Refusals may stack, and that is the point for numbers.** ``{"email_count": 4}`` produces two, and
both are true for two different reasons: no spelling row governs the segment, and no schema
declares the number. Collapsing them to one would lose a fact a caller needs — "nobody has a rule
for this key" and "nobody has said what this number means" are different gaps, and the second is
the one that would have produced a count, a port or a latitude.

**The path is parsed, not sliced.** :func:`path_tokens` reads a key path with
:func:`json.JSONDecoder.raw_decode`, in the grammar :func:`parsers.payload.structured.child_path`
writes. The last token is the key segment, and a terminal ``[0]`` is an index rather than a name.
String surgery is what would break: ``$["a[b"]["c"]`` is a real path, and ``rfind("[")`` on it
finds the bracket inside the key.

**Determinism is structural.** Records are read in document order, refusals are emitted in a fixed
per-record order, hypotheses come back in the table's own declaration order, and nothing here reads
a clock, a random source or a ``set``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from semantic.blocking import TypeHypothesis

from extractors.payload.keytable import (
    DEFAULT_DECLARED_SCHEMAS,
    KEY_TYPE_TABLE_VERSION,
    BasisOrigin,
    DeclaredSchema,
    KeyTypeRule,
    matching_rules,
)
from parsers.payload import ObservedField, ValueType

#: The number of tokens a key path segment may carry, published so "the payload is a label, the key
#: or the index and nothing else" is checkable against a number. A fourth kind of segment added
#: later and forgotten here would be read back as one of these three.
PATH_TOKEN_COUNT = 2

#: The kinds of token a key path is made of. Closed, and closed for the reason
#: :class:`extractors.payload.keytable.BasisOrigin` is: a token kind nobody can enumerate is a token
#: kind nobody can audit, and this one decides what a record is even *named*.
PATH_TOKEN_KINDS: tuple[str, ...] = ("key", "index")

#: The shared decoder, built once. :func:`json.JSONDecoder.raw_decode` is the platform's own JSON
#: grammar rather than a hand-rolled splitter, and a second implementation of how a quoted key reads
#: would be a second answer to "what is the last segment of this path".
_DECODER = json.JSONDecoder()

_ROOT_TOKEN = "$"


class HypothesisRefusalCode(StrEnum):
    """Every way this stage declines to propose a type, as a closed vocabulary.

    Each member names a record that **exists**. None of them is a silent drop, because a record
    that vanishes is a field the caller cannot tell was ever read — which is the same property
    :mod:`parsers.payload.records` and :mod:`parsers.payload.binding` each maintain at their own
    seam, carried forward here.
    """

    KEY_RULE_ABSENT = "key_rule_absent"
    KEY_RULE_VALUE_TYPE_MISMATCH = "key_rule_value_type_mismatch"
    NUMERIC_SEMANTICS_REQUIRE_DECLARED_SCHEMA = "numeric_semantics_require_declared_schema"
    MEMBER_IS_ARRAY_INDEXED = "member_is_array_indexed"
    DOCUMENT_ROOT_HAS_NO_KEY = "document_root_has_no_key"
    KEY_PATH_UNREADABLE = "key_path_unreadable"


#: The vocabulary as strings, for callers that switch on the token rather than the member.
HYPOTHESIS_REFUSAL_CODES: tuple[str, ...] = tuple(code.value for code in HypothesisRefusalCode)


def path_tokens(key_path: str) -> tuple[tuple[str, str], ...] | None:
    """The key path's ``(kind, text)`` tokens in the parser's grammar, or ``None`` if unreadable.

    ``$`` is the empty tuple; ``$["registrant"]["email"]`` is ``(("key", "registrant"), ("key",
    "email"))``; ``$["rows"][0]`` is ``(("key", "rows"), ("index", "0"))``. ``None`` means the
    string is not a path this grammar can read, and the caller records
    :attr:`HypothesisRefusalCode.KEY_PATH_UNREADABLE` rather than guessing a split.

    Parsed with :func:`json.JSONDecoder.raw_decode` because object keys in this grammar are
    ``json.dumps`` output, so a quoted key reads as itself and an index reads as a bare integer.
    The two are distinguished by the token itself rather than by a lookahead, which means a key
    spelled ``"0"`` is a key and ``[0]`` is an index, both correctly.
    """
    text = str(key_path or "")
    if not text.startswith(_ROOT_TOKEN):
        return None
    cursor = len(_ROOT_TOKEN)
    tokens: list[tuple[str, str]] = []
    while cursor < len(text):
        if text[cursor] != "[":
            return None
        try:
            value, end = _DECODER.raw_decode(text, cursor + 1)
        except ValueError:
            return None
        if end >= len(text) or text[end] != "]":
            return None
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            return None
        tokens.append(("key" if isinstance(value, str) else "index", str(value)))
        cursor = end + 1
    return tuple(tokens)


def last_key_segment(key_path: str) -> tuple[str | None, str]:
    """The record's own name — its last **key** token — and a code when there is not one.

    Returns ``(segment, code)`` with exactly one of the two non-empty:

    * ``(segment, "")`` — the record is a named member and ``segment`` is its key.
    * ``("", HypothesisRefusalCode.DOCUMENT_ROOT_HAS_NO_KEY)`` — the record is the root.
    * ``("", HypothesisRefusalCode.MEMBER_IS_ARRAY_INDEXED)`` — the record is an element.
    * ``("", HypothesisRefusalCode.KEY_PATH_UNREADABLE)`` — the path is not in this grammar.

    An element and a member are different questions, so they are different codes: a record with
    no key because it is at position 0 of an array is a fact about the payload's shape, and a
    record with no key because the caller handed over a path this stage cannot read is a defect in
    the caller. Reporting both as "unkeyed" would make the second invisible.
    """
    tokens = path_tokens(key_path)
    if tokens is None:
        return "", HypothesisRefusalCode.KEY_PATH_UNREADABLE.value
    if not tokens:
        return "", HypothesisRefusalCode.DOCUMENT_ROOT_HAS_NO_KEY.value
    kind, text = tokens[-1]
    if kind == "index":
        return "", HypothesisRefusalCode.MEMBER_IS_ARRAY_INDEXED.value
    return text, ""


@dataclass(frozen=True, slots=True)
class HypothesisCitation:
    """Why a hypothesis was proposed: the place, the segment, the row, the level, the table.

    This is the whole of S1's "a hypothesis must carry why it was proposed", and every field is
    load-bearing:

    ``key_path`` / ``segment``
        the **place** in the payload and the **word** that named it. Both, because they are
        different evidence: a schema binds the place, a spelling binds the word, and a citation
        that carried only one of them could not say which level had produced the hypothesis.
    ``origin``
        the epistemic level, as a member of a closed two-member vocabulary. It survives into the
        output because "the platform read a name" and "the source published a schema" are claims a
        reader weighs very differently, and a single ``basis: str`` would have flattened them.
    ``rule_id`` / ``table_version``
        the row and the table that contained it, so a stored citation can be checked against the
        rules that were in force and a retraction can be reasoned about after the fact.
    ``schema_ref``
        the published document, non-empty exactly when :attr:`origin` is
        :attr:`~extractors.payload.keytable.BasisOrigin.DECLARED_SCHEMA`. It is somebody else's
        document and a reader must be able to fetch it.
    """

    key_path: str
    segment: str
    origin: BasisOrigin
    rule_id: str
    table_version: str = KEY_TYPE_TABLE_VERSION
    schema_ref: str = ""
    value_type: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "key_path", str(self.key_path or ""))
        object.__setattr__(self, "segment", str(self.segment or ""))
        object.__setattr__(self, "origin", BasisOrigin(self.origin))
        object.__setattr__(self, "rule_id", str(self.rule_id or ""))
        object.__setattr__(self, "table_version", str(self.table_version or ""))
        object.__setattr__(self, "schema_ref", str(self.schema_ref or ""))
        object.__setattr__(self, "value_type", str(self.value_type or ""))
        object.__setattr__(self, "note", str(self.note or ""))
        if not self.key_path:
            raise HypothesisContractError(
                "citation_key_path_required",
                "a citation names the place in the payload that suggested the type, and '' names "
                "no place. A hypothesis that cannot say where it came from is a claim with no "
                "evidence attached",
            )
        if not self.segment:
            raise HypothesisContractError(
                "citation_segment_required",
                f"the citation for {self.key_path!r} names no key segment. A place and a word are "
                "different evidence - a schema binds the place, a spelling binds the word - so a "
                "citation carrying only one of them cannot say which level produced the hypothesis",
            )
        if not self.rule_id:
            raise HypothesisContractError(
                "citation_rule_id_required",
                f"the citation for {self.key_path!r} names no table row, so it cannot be checked "
                "against the rules that were in force when it was written",
            )
        if self.origin is BasisOrigin.DECLARED_SCHEMA and not self.schema_ref:
            raise HypothesisContractError(
                "citation_schema_ref_required",
                f"the citation for {self.key_path!r} claims a declared schema and names no "
                "document. A level of evidence with nothing behind it is not a level of evidence",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "key_path": self.key_path,
            "segment": self.segment,
            "origin": str(self.origin),
            "rule_id": self.rule_id,
            "table_version": self.table_version,
            "schema_ref": self.schema_ref,
            "value_type": self.value_type,
            "note": self.note,
        }


class HypothesisContractError(ValueError):
    """A cited hypothesis is not coherent, refused with a stable code like the rest of the platform."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


@dataclass(frozen=True, slots=True)
class CitedHypothesis:
    """A :class:`TypeHypothesis` and the citation that says why it was proposed.

    The pair is the output rather than the bare hypothesis, for two reasons that both have teeth.
    :class:`semantic.blocking.TypeHypothesis` has three fields and none of them records *why* —
    ``internal:email_address`` at ``0.5`` and ``schema:email_address`` at ``0.9`` are the same
    object shape and entirely different claims, and a consumer holding only the hypothesis cannot
    tell them apart. And the wrapper is where the **explicit confidence** lives: there is exactly
    one construction site in this module and it names ``confidence=`` from the cited row, so a
    hypothesis cannot acquire :attr:`TypeHypothesis.confidence`'s ``1.0`` default by being
    constructed in a hurry.

    No seventh field is added to :class:`~domain.relation_participant.RelationParticipant` or to
    any other shared type to make this work; the citation is a new value type in this package
    because the thing being carried did not previously exist anywhere in the model.
    """

    hypothesis: TypeHypothesis
    citation: HypothesisCitation

    def __post_init__(self) -> None:
        if not isinstance(self.hypothesis, TypeHypothesis):
            raise HypothesisContractError(
                "cited_hypothesis_type",
                f"a cited hypothesis holds a semantic.blocking.TypeHypothesis or nothing; got "
                f"{type(self.hypothesis).__name__}",
            )
        if not isinstance(self.citation, HypothesisCitation):
            raise HypothesisContractError(
                "cited_hypothesis_citation_type",
                f"a cited hypothesis holds a HypothesisCitation or nothing; got "
                f"{type(self.citation).__name__}",
            )

    @property
    def key_path(self) -> str:
        """The place in the payload, so a caller can join hypotheses to records and signals."""
        return self.citation.key_path

    @property
    def origin(self) -> BasisOrigin:
        """The epistemic level, readable without unpacking the citation."""
        return self.citation.origin

    def to_dict(self) -> dict[str, Any]:
        return {
            "type_ref": self.hypothesis.type_ref,
            "scheme": str(self.hypothesis.scheme),
            "confidence": self.hypothesis.confidence,
            "reference": self.hypothesis.reference(),
            "citation": self.citation.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class HypothesisRefusal:
    """One record this stage declined to type, with a code a caller histograms.

    ``key_path`` is the record, ``segment`` the word that was looked up (empty when the record has
    no name), ``value_type`` the observation about the bytes, and ``rule_id`` the row that was
    consulted when a row was. The detail says, in prose, what a reader needs to act: which key
    would have to be declared, or which schema.
    """

    code: str
    key_path: str
    segment: str = ""
    value_type: str = ""
    rule_id: str = ""
    detail: str = ""

    def __post_init__(self) -> None:
        code = str(self.code)
        if code not in HYPOTHESIS_REFUSAL_CODES:
            raise HypothesisContractError(
                "hypothesis_refusal_code_unknown",
                f"{code!r} is not a hypothesis refusal code. The vocabulary is closed and has "
                f"{len(HYPOTHESIS_REFUSAL_CODES)} members: {list(HYPOTHESIS_REFUSAL_CODES)}. A "
                "code nobody can enumerate is a code nobody can count, and a refusal nobody can "
                "count is a silent drop",
            )
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "key_path", str(self.key_path or ""))
        object.__setattr__(self, "segment", str(self.segment or ""))
        object.__setattr__(self, "value_type", str(self.value_type or ""))
        object.__setattr__(self, "rule_id", str(self.rule_id or ""))
        object.__setattr__(self, "detail", str(self.detail or ""))
        if not self.key_path:
            raise HypothesisContractError(
                "hypothesis_refusal_key_path_required",
                "a refusal names the record it is about, and '' names none. A refusal that cannot "
                "be attributed to a record is a gap somebody will rediscover as missing data",
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "key_path": self.key_path,
            "segment": self.segment,
            "value_type": self.value_type,
            "rule_id": self.rule_id,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class HypothesisReading:
    """What one record set proposed, what it refused, and against which table version.

    ``hypotheses`` and ``refusals`` are two views of one pass over the records, and the property
    worth asserting is not "there are some hypotheses" but "**every record is in one of them**":
    a record that is in neither was read and then silently discarded, which is the failure mode
    every layer of this chain exists to make impossible.
    """

    hypotheses: tuple[CitedHypothesis, ...] = ()
    refusals: tuple[HypothesisRefusal, ...] = ()
    table_version: str = KEY_TYPE_TABLE_VERSION
    schema_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "hypotheses", tuple(self.hypotheses or ()))
        object.__setattr__(self, "refusals", tuple(self.refusals or ()))
        object.__setattr__(self, "table_version", str(self.table_version or ""))
        object.__setattr__(self, "schema_refs", tuple(self.schema_refs or ()))

    def for_path(self, key_path: str) -> tuple[CitedHypothesis, ...]:
        """The hypotheses proposed for one key path, in emission order — the join to the signals."""
        wanted = str(key_path or "")
        return tuple(cited for cited in self.hypotheses if cited.key_path == wanted)

    def refusals_for(self, key_path: str) -> tuple[HypothesisRefusal, ...]:
        """The refusals recorded for one key path, in emission order."""
        wanted = str(key_path or "")
        return tuple(refusal for refusal in self.refusals if refusal.key_path == wanted)

    @property
    def refusal_codes(self) -> tuple[str, ...]:
        """Every refusal code in order — the count a caller histograms, not a judgement call."""
        return tuple(refusal.code for refusal in self.refusals)

    @property
    def untyped_paths(self) -> tuple[str, ...]:
        """The records this stage proposed nothing for, in document order, without duplicates."""
        seen: dict[str, None] = {}
        for refusal in self.refusals:
            seen.setdefault(refusal.key_path, None)
        return tuple(seen)

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_version": self.table_version,
            "schema_refs": list(self.schema_refs),
            "hypotheses": [cited.to_dict() for cited in self.hypotheses],
            "refusals": [refusal.to_dict() for refusal in self.refusals],
        }

    def content_key(self) -> str:
        """Identity of this reading, through the shared canonical-JSON convention.

        Order-sensitive on purpose: the hypotheses come back in the records' document order and in
        the table's declaration order, and a reading whose order changed is a reading whose
        provenance changed too.
        """
        from semantic.contracts import content_key

        return content_key(self.to_dict())


def read_type_hypotheses(
    records: Iterable[ObservedField], *, schemas: Iterable[DeclaredSchema] = DEFAULT_DECLARED_SCHEMAS
) -> HypothesisReading:
    """Propose type hypotheses for every record, and refuse the rest **by name**.

    The whole of S1 and S2, in one pass in document order, and the pass is total: a record whose
    path is unreadable, a record with no key, a record no row governs, a record a row governs and
    the value disagrees with, and a number nothing declares the meaning of all come back as
    refusals rather than as nothing.

    The one construction site of a :class:`TypeHypothesis` is in :func:`_cite`, and it names
    ``confidence=`` from the cited row on purpose. :attr:`TypeHypothesis.confidence` defaults to
    ``1.0``; :mod:`extractors.payload.keytable` refuses a row that declares ``1.0``; and
    ``test_dropping_the_explicit_confidence_fails_the_guard`` puts the argument back into the
    repository and shows the guard noticing.

    Refusal order within one record is fixed so a diff between two runs means something: the
    naming refusal first if there is one, then the per-row mismatches in table order, then the
    numeric-semantics refusal. Two records never share a refusal, so the sequence is a total order
    on the records.
    """
    schema_list = tuple(schemas or ())
    hypotheses: list[CitedHypothesis] = []
    refusals: list[HypothesisRefusal] = []
    for record in records:
        segment, code = last_key_segment(record.field)
        if code:
            refusals.append(
                HypothesisRefusal(
                    code=code,
                    key_path=record.field,
                    value_type=str(record.value_type),
                    detail=_naming_detail(record, code),
                )
            )
            continue
        rules = matching_rules(key_path=record.field, segment=segment, schemas=schema_list)
        if not rules:
            refusals.append(
                HypothesisRefusal(
                    code=HypothesisRefusalCode.KEY_RULE_ABSENT.value,
                    key_path=record.field,
                    segment=segment,
                    value_type=str(record.value_type),
                    detail=(
                        f"no row of the key-type table (version {KEY_TYPE_TABLE_VERSION}) governs "
                        f"the whole key {segment!r} at {record.field!r}, and no declared schema "
                        f"binds that path. Matching is equality on the whole key segment, so "
                        f"{segment!r} is not a near miss for any other row and no row was applied "
                        "as a guess. To type this field, add a row for this exact key, or bind "
                        "this path in a schema the source publishes"
                    ),
                )
            )
        for rule in rules:
            if rule.admits(record.value_type):
                hypotheses.append(_cite(record, segment, rule))
                continue
            refusals.append(
                HypothesisRefusal(
                    code=HypothesisRefusalCode.KEY_RULE_VALUE_TYPE_MISMATCH.value,
                    key_path=record.field,
                    segment=segment,
                    value_type=str(record.value_type),
                    rule_id=rule.rule_id,
                    detail=(
                        f"row {rule.rule_id!r} governs {rule.key!r} and proposes "
                        f"{rule.type_ref!r}, but it admits only "
                        f"{[str(v) for v in rule.value_types]} and this record is a "
                        f"{record.value_type}. A rule that admitted every value type would turn a "
                        "number under an address key into an address hypothesis, which is worse "
                        "than no hypothesis at all"
                    ),
                )
            )
        if record.value_type is ValueType.NUMBER and not any(
            rule.origin is BasisOrigin.DECLARED_SCHEMA for rule in rules
        ):
            refusals.append(
                HypothesisRefusal(
                    code=HypothesisRefusalCode.NUMERIC_SEMANTICS_REQUIRE_DECLARED_SCHEMA.value,
                    key_path=record.field,
                    segment=segment,
                    value_type=str(record.value_type),
                    detail=(
                        f"{record.field!r} is a JSON number and no declared schema binds that "
                        "path to a meaning. A number is not a licence to call something a port, a "
                        "latitude or a count: value_type says what the bytes are and nothing about "
                        "what they are for, so a numeric hypothesis requires a schema the source "
                        "publishes"
                    ),
                )
            )
    return HypothesisReading(
        hypotheses=tuple(hypotheses),
        refusals=tuple(refusals),
        table_version=KEY_TYPE_TABLE_VERSION,
        schema_refs=tuple(schema.schema_ref for schema in schema_list),
    )


def _cite(record: ObservedField, segment: str, rule: KeyTypeRule) -> CitedHypothesis:
    """The one place a :class:`TypeHypothesis` is built, and it names its confidence.

    ``confidence=rule.confidence`` is the load-bearing line of this module. It is a keyword rather
    than a positional argument so a reader can see what it is without tracing the dataclass, and
    :mod:`extractors.payload.keytable` guarantees the value it can be — a row declaring ``1.0`` is
    refused at construction, so the inherited default on
    :attr:`~semantic.blocking.TypeHypothesis.confidence` can never coincide with a declared row.

    The wrapper is what carries the basis: a hypothesis is emitted **with its citation or not at
    all**, so "every hypothesis says why it was proposed" is a property of the type rather than a
    rule a caller has to remember.
    """
    return CitedHypothesis(
        hypothesis=TypeHypothesis(
            type_ref=rule.type_ref,
            scheme=rule.scheme,
            confidence=rule.confidence,
        ),
        citation=HypothesisCitation(
            key_path=record.field,
            segment=segment,
            origin=rule.origin,
            rule_id=rule.rule_id,
            table_version=KEY_TYPE_TABLE_VERSION,
            schema_ref=rule.schema_ref,
            value_type=str(record.value_type),
            note=rule.note,
        ),
    )


def _naming_detail(record: ObservedField, code: str) -> str:
    """Prose for a record this stage could not name, one sentence per code."""
    if code == HypothesisRefusalCode.DOCUMENT_ROOT_HAS_NO_KEY.value:
        return (
            f"{record.field!r} is the payload's root container. The root states that a document is "
            "here and names nothing inside it; a type hypothesis needs a name, and a document's "
            "own name is a separate question this stage does not answer"
        )
    if code == HypothesisRefusalCode.MEMBER_IS_ARRAY_INDEXED.value:
        return (
            f"{record.field!r} is an element of a JSON array, so its last path token is a "
            "position rather than a name. An index is not a word: the same key table would apply "
            "to every payload that used the same position, which is the substring match this "
            "layer exists to remove wearing an index. The array's own key, if it has one, is the "
            "member set the element belongs to and is a different record"
        )
    return (
        f"{record.field!r} is not a key path in the grammar "
        "parsers.payload.structured.child_path writes, so its last segment cannot be read without "
        "guessing where the path ends. A key may itself contain '[' - $[\"a[b\"] is a real path - "
        "and every convenient string split is wrong for one of them. This is a record the "
        "caller assembled by hand or a parser that does not share this grammar"
    )


def cited_paths(hypotheses: Sequence[CitedHypothesis]) -> tuple[str, ...]:
    """The distinct key paths that received at least one hypothesis, in first-seen order.

    Published because a caller assembling a report needs the join in one place and a
    ``set(...)`` would not be deterministic; this is an ordered dict's keys.
    """
    seen: dict[str, None] = {}
    for cited in hypotheses:
        seen.setdefault(cited.key_path, None)
    return tuple(seen)


__all__ = [
    "HYPOTHESIS_REFUSAL_CODES",
    "PATH_TOKEN_COUNT",
    "PATH_TOKEN_KINDS",
    "CitedHypothesis",
    "HypothesisCitation",
    "HypothesisContractError",
    "HypothesisReading",
    "HypothesisRefusal",
    "HypothesisRefusalCode",
    "cited_paths",
    "last_key_segment",
    "path_tokens",
    "read_type_hypotheses",
]
