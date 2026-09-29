"""The generic structured-field extractor: walk a JSON payload, report what is written where.

Feature 021 brief §25 (a producer below mention extraction reports, and refuses); constitution
IV (fail-closed) and VI (determinism, Domain Invariant 12).

**What this is.** One walk, over any JSON payload, emitting one
:class:`~parsers.payload.records.ObservedField` per value the payload states:

    field | value | value_type | byte_span        (plus depth, label, and the deferred address)

That is the whole of it. There is no per-source parser here, and that is a decision rather than
a gap: 92 parser names are declared across the catalogue, upstream implements about five of them
honestly, and writing 92 bespoke extractors would mean writing down what each of 92 APIs
*probably* returns — a key-name heuristic and a default type per source, which is the exact
shape of the defect this layer replaces. A generic walk needs no hypothesis about any source:
the key paths are in the payload, and the payload's own grammar says what kind of bytes each
value is.

**Why the scanner is written here instead of ``json.loads``.** Three reasons, each load-bearing:

* **Byte spans.** ``json`` parses to Python objects and throws the positions away, and a
  mention address is a position (brief §25, §26). Recovering spans afterwards by searching for
  the value would be a guess about which occurrence the parser meant, and the platform's whole
  argument against upstream is that it guessed.
* **A node ceiling that means something.** ``json.loads`` materialises the entire document
  before a caller can look at it, so "bounded" could only mean "refuse the body", which is a
  refusal, not a bound. Here the walk counts nodes as it goes and *stops*, recording
  :class:`~parsers.payload.records.BoundHit`.
* **Depth that is a number.** The scan is recursive, bounded by
  :attr:`~parsers.payload.records.ParseBounds.max_depth` and by nothing else: a body nested
  thousands deep hits the depth ceiling at 64 and is reported, which is what makes "a deeply
  nested body returns a record set and raises nothing" true rather than lucky.

**Total by construction, and the two ways it can fail are two named refusals.** A payload that
is not JSON at all does not reach this walk — :func:`parse_structured_fields` refuses with
``payload_not_json`` when :attr:`~parsers.payload.detect.Detection.is_json` is false, so a
caller cannot obtain structured records from a body the transport declared to be text. Bytes
that are not UTF-8 are ``payload_not_utf8`` with the offset of the first offending byte; bytes
that are not JSON are ``payload_malformed_json`` with the offset where the walk stopped. In
both cases **no records are returned**: a half-read document presented as a whole one is a
structure the document does not have, and the honest answer to "what is in here" when the
document is broken is a refusal naming where it broke.

**A bound is different from a fault, and returns records.** When a ceiling fires, the records
read before it are kept and :attr:`~parsers.payload.records.ParsedPayload.bound_hit` says
which ceiling, at what limit, with what observed value. A walk that stopped at node 8192 and
said so is a measurement of a large payload; a walk that raised is a fault. Never the same
thing, never conflated.

**Determinism is structural.** Records are appended as the scanner walks left to right, so
record order is **document order** — no dict ordering, no ``set``, no sort by hash anywhere on
the path, and the same bytes produce the same records in the same order in a second process
(constitution VI, Domain Invariant 12). Duplicate object keys are emitted as two records, not
merged: choosing one of them would be a decision about which of two stated values is *the*
value.
"""

from __future__ import annotations

import json
from dataclasses import replace

from parsers.payload.detect import JSON_WHITESPACE, Detection
from parsers.payload.records import (
    DEFAULT_BOUNDS,
    BoundHit,
    ExtractorResult,
    ObservedField,
    ParseBounds,
    PayloadLabel,
    PayloadRefusal,
    ValueType,
    address_for,
)

#: The name this extractor registers under, and the producer stamped on every record it emits.
STRUCTURED_PRODUCER = "structured_fields"

_QUOTE = 0x22
_BACKSLASH = 0x5C
_OPEN_BRACE = 0x7B
_OPEN_BRACKET = 0x5B
_MINUS = 0x2D
_ZERO = 0x30
_NINE = 0x39


class _Malformed(Exception):
    """Internal: the payload is not the grammar this walk reads. Carries its own refusal code."""

    __slots__ = ("code", "detail", "offset")

    def __init__(self, code: str, offset: int, detail: str) -> None:
        self.code = code
        self.offset = offset
        self.detail = detail
        super().__init__(f"[{code}] byte {offset}: {detail}")


class _BoundReached(Exception):
    """Internal: a ceiling fired. Carries the :class:`BoundHit` that says which one."""

    __slots__ = ("hit",)

    def __init__(self, hit: BoundHit) -> None:
        self.hit = hit
        super().__init__(hit.bound)


class _Scanner:
    """The walk: recursive over containers, bounded by :class:`ParseBounds` at every step.

    Every emission takes the :class:`~parsers.payload.records.PayloadLabel` of the position it
    read, passed in by the caller that knows it: the document root is ``json_root``, an object
    member is ``json_field``, an array element is ``json_element``. Deriving the label from the
    path afterwards would be a second reading of the payload's shape, and a label that could
    disagree with the structure it came from is a label nobody can trust.
    """

    __slots__ = ("_bounds", "_counts", "_data", "_nodes", "_open", "_records")

    def __init__(self, data: bytes, bounds: ParseBounds) -> None:
        self._data = data
        self._bounds = bounds
        self._records: list[ObservedField] = []
        #: Indices of container records whose closing byte has not been read yet. A container
        #: is emitted at its **opening** byte so record order is document order, which means
        #: its span is unknown until it closes; an unclosed one is removed rather than emitted
        #: with the span of its first byte, which would be a claim about bytes.
        self._open: list[int] = []
        self._nodes = 0
        self._counts: dict[str, int] = {}

    # -- entry ------------------------------------------------------------- #

    def scan(self) -> ExtractorResult:
        try:
            end = self._value(self._skip_ws(0), "$", 0, PayloadLabel.JSON_ROOT)
            tail = self._skip_ws(end)
            if tail != len(self._data):
                raise _Malformed(
                    "payload_malformed_json", tail, "bytes follow the top-level value"
                )
        except _Malformed as exc:
            return ExtractorResult(
                records=(),
                refusals=(PayloadRefusal(exc.code, exc.detail, exc.offset),),
                bound_hit=None,
            )
        except _BoundReached as exc:
            self._discard_open()
            return ExtractorResult(records=tuple(self._records), refusals=(), bound_hit=exc.hit)
        return ExtractorResult(records=tuple(self._records), refusals=(), bound_hit=None)

    def _discard_open(self) -> None:
        """Drop the containers the walk never closed.

        Their extents are unknown because the walk stopped inside them, and a record whose span
        is a guess is exactly what this layer refuses to emit. The children read before the stop
        stay: they were observed whole, and dropping them would lose a fact the payload states.
        """
        for index in reversed(self._open):
            del self._records[index]
        self._open.clear()

    # -- bounds ------------------------------------------------------------ #

    def _count_node(self) -> None:
        self._nodes += 1
        if self._nodes > self._bounds.max_nodes:
            raise _BoundReached(BoundHit("nodes_visited", self._bounds.max_nodes, self._nodes))

    def _guard_type(self, value_type: ValueType) -> None:
        name = str(value_type)
        seen = self._counts.get(name, 0)
        if seen >= self._bounds.max_records_per_value_type:
            raise _BoundReached(
                BoundHit(
                    "records_of_value_type",
                    self._bounds.max_records_per_value_type,
                    seen,
                    name,
                )
            )
        self._counts[name] = seen + 1

    def _guard_depth(self, depth: int) -> None:
        if depth > self._bounds.max_depth:
            raise _BoundReached(BoundHit("depth", self._bounds.max_depth, depth))

    # -- emission ---------------------------------------------------------- #

    def _emit_scalar(
        self,
        path: str,
        value: str,
        value_type: ValueType,
        span: tuple[int, int],
        depth: int,
        label: PayloadLabel,
    ) -> None:
        self._guard_type(value_type)
        address, refusal = address_for(
            value=value, value_type=value_type, byte_span=span, label=label
        )
        self._records.append(
            ObservedField(
                field=path,
                value=value,
                value_type=value_type,
                byte_span=span,
                depth=depth,
                label=label,
                address=address,
                address_refusal=refusal,
            )
        )

    def _open_container(
        self, path: str, depth: int, label: PayloadLabel
    ) -> int:
        """Reserve the container's record at its opening byte; the span is patched on close."""
        self._guard_type(ValueType.NESTED)
        address, refusal = address_for(
            value="", value_type=ValueType.NESTED, byte_span=None, label=label
        )
        index = len(self._records)
        self._records.append(
            ObservedField(
                field=path,
                value="",
                value_type=ValueType.NESTED,
                byte_span=None,
                depth=depth,
                label=label,
                address=address,
                address_refusal=refusal,
            )
        )
        self._open.append(index)
        return index

    def _close_container(self, index: int, start: int, end: int) -> int:
        self._records[index] = replace(self._records[index], byte_span=(start, end))
        self._open.pop()
        return end

    # -- grammar ----------------------------------------------------------- #

    def _skip_ws(self, pos: int) -> int:
        data = self._data
        end = len(data)
        while pos < end and data[pos] in JSON_WHITESPACE:
            pos += 1
        return pos

    def _is_digit(self, pos: int) -> bool:
        return pos < len(self._data) and _ZERO <= self._data[pos] <= _NINE

    def _value(self, pos: int, path: str, depth: int, label: PayloadLabel) -> int:
        """Read one value at ``pos``, emit its record, return the offset just after it."""
        self._count_node()
        if pos >= len(self._data):
            raise _Malformed(
                "payload_malformed_json", pos, "the payload ended where a value was expected"
            )
        byte = self._data[pos]
        if byte == _OPEN_BRACE:
            return self._object(pos, path, depth, label)
        if byte == _OPEN_BRACKET:
            return self._array(pos, path, depth, label)
        if byte == _QUOTE:
            return self._string(pos, path, depth, label)
        if byte == 0x74:  # t
            return self._literal(pos, b"true", ValueType.BOOL, path, depth, label)
        if byte == 0x66:  # f
            return self._literal(pos, b"false", ValueType.BOOL, path, depth, label)
        if byte == 0x6E:  # n
            return self._literal(pos, b"null", ValueType.NULL, path, depth, label)
        if byte == _MINUS or _ZERO <= byte <= _NINE:
            return self._number(pos, path, depth, label)
        raise _Malformed(
            "payload_malformed_json", pos, f"byte {byte!r} where a JSON value was expected"
        )

    def _object(self, pos: int, path: str, depth: int, label: PayloadLabel) -> int:
        self._guard_depth(depth)
        index = self._open_container(path, depth, label)
        data = self._data
        cursor = self._skip_ws(pos + 1)
        if data[cursor : cursor + 1] == b"}":
            return self._close_container(index, pos, cursor + 1)
        while True:
            if data[cursor : cursor + 1] != b'"':
                raise _Malformed(
                    "payload_malformed_json", cursor, "an object key must be a quoted string"
                )
            cursor, key = self._read_string(cursor)
            cursor = self._skip_ws(cursor)
            if data[cursor : cursor + 1] != b":":
                raise _Malformed(
                    "payload_malformed_json", cursor, "expected ':' after an object key"
                )
            cursor = self._skip_ws(cursor + 1)
            cursor = self._value(
                cursor, child_path(path, key), depth + 1, PayloadLabel.JSON_FIELD
            )
            cursor = self._skip_ws(cursor)
            marker = data[cursor : cursor + 1]
            if marker == b",":
                cursor = self._skip_ws(cursor + 1)
                continue
            if marker == b"}":
                return self._close_container(index, pos, cursor + 1)
            raise _Malformed(
                "payload_malformed_json", cursor, "expected ',' or '}' in an object"
            )

    def _array(self, pos: int, path: str, depth: int, label: PayloadLabel) -> int:
        self._guard_depth(depth)
        index = self._open_container(path, depth, label)
        data = self._data
        cursor = self._skip_ws(pos + 1)
        if data[cursor : cursor + 1] == b"]":
            return self._close_container(index, pos, cursor + 1)
        element = 0
        while True:
            cursor = self._value(
                cursor, f"{path}[{element}]", depth + 1, PayloadLabel.JSON_ELEMENT
            )
            element += 1
            cursor = self._skip_ws(cursor)
            marker = data[cursor : cursor + 1]
            if marker == b",":
                cursor = self._skip_ws(cursor + 1)
                continue
            if marker == b"]":
                return self._close_container(index, pos, cursor + 1)
            raise _Malformed(
                "payload_malformed_json", cursor, "expected ',' or ']' in an array"
            )

    def _string(self, pos: int, path: str, depth: int, label: PayloadLabel) -> int:
        """Read the quoted string at ``pos`` and emit it, span being the quoted token itself.

        The span includes the delimiting quotes on purpose, and the rule is stated once here so
        a reader does not have to infer it: **a record's span is the token the payload wrote**,
        which is what makes :meth:`ParsedPayload.read_span` a witness rather than a
        reconstruction. For a string that means the quoted literal, so ``json.loads`` of the
        span is the record's value; for a number, a literal and a line, the span's bytes *are*
        the value. A span that stopped at the first quote would instead address a different
        region than the one the payload marked as a value.
        """
        end, text = self._read_string(pos)
        self._emit_scalar(path, text, ValueType.STRING, (pos, end), depth, label)
        return end

    def _read_string(self, pos: int) -> tuple[int, str]:
        """Read the quoted string at ``pos``; return ``(offset_after, decoded_text)``.

        Finding the closing quote is separate from decoding it, and the decode is
        :func:`json.loads` on the exact token rather than a hand-rolled unescaper: an unescaper
        is a second implementation of JSON's string grammar and would be a second answer to what
        these bytes say. Unpaired surrogate escapes are refused rather than carried, because a
        lone surrogate cannot be encoded into an address's material and a record that mints an
        address has to be encodable.
        """
        data = self._data
        total = len(data)
        cursor = pos + 1
        while True:
            if cursor >= total:
                raise _Malformed(
                    "payload_malformed_json", pos, "a string opened here and never closed"
                )
            byte = data[cursor]
            if byte == _QUOTE:
                return self._decode_string(pos, cursor + 1)
            if byte == _BACKSLASH:
                cursor += 2
                continue
            if byte < 0x20:
                raise _Malformed(
                    "payload_malformed_json",
                    cursor,
                    "a raw control character inside a string; JSON requires it escaped",
                )
            cursor += 1

    def _decode_string(self, start: int, end: int) -> tuple[int, str]:
        token = self._data[start:end]
        try:
            text = token.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise _Malformed(
                "payload_not_utf8",
                start + exc.start,
                "these bytes are not UTF-8, so the string they delimit cannot be read",
            ) from None
        try:
            value = json.loads(text)
        except ValueError:
            raise _Malformed(
                "payload_malformed_json", start, "this token is not a valid JSON string"
            ) from None
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise _Malformed(
                "payload_malformed_json",
                start,
                "this string carries an unpaired surrogate escape, which cannot be encoded "
                "into an occurrence address's material",
            )
        return end, value

    def _literal(
        self,
        pos: int,
        word: bytes,
        value_type: ValueType,
        path: str,
        depth: int,
        label: PayloadLabel,
    ) -> int:
        end = pos + len(word)
        if self._data[pos:end] != word:
            raise _Malformed(
                "payload_malformed_json", pos, f"expected the literal {word.decode('ascii')!r}"
            )
        self._emit_scalar(
            path, word.decode("ascii"), value_type, (pos, end), depth, label
        )
        return end

    def _number(self, pos: int, path: str, depth: int, label: PayloadLabel) -> int:
        """Read a JSON number literal, keeping its text verbatim.

        Never converted to ``int`` or ``float``: ``1e3`` and ``1000.0`` are different byte
        sequences in the payload, and a record that reports the number rather than the bytes has
        already begun transforming the source. It also sidesteps an overflow that would
        otherwise be a fault — ``1e400`` is a legal JSON number and an illegal Python float.
        The grammar is validated here (no leading ``+``, no leading zeros, no bare ``.5``)
        because accepting what Python accepts is a guess about what the payload said.
        """
        data = self._data
        cursor = pos
        if data[cursor : cursor + 1] == b"-":
            cursor += 1
        if not self._is_digit(cursor):
            raise _Malformed("payload_malformed_json", cursor, "a number needs at least one digit")
        if data[cursor] == _ZERO:
            cursor += 1
        else:
            while self._is_digit(cursor):
                cursor += 1
        if data[cursor : cursor + 1] == b".":
            cursor += 1
            if not self._is_digit(cursor):
                raise _Malformed(
                    "payload_malformed_json", cursor, "a decimal point needs a digit after it"
                )
            while self._is_digit(cursor):
                cursor += 1
        if data[cursor : cursor + 1] in (b"e", b"E"):
            cursor += 1
            if data[cursor : cursor + 1] in (b"+", b"-"):
                cursor += 1
            if not self._is_digit(cursor):
                raise _Malformed(
                    "payload_malformed_json", cursor, "an exponent needs a digit after its sign"
                )
            while self._is_digit(cursor):
                cursor += 1
        literal = data[pos:cursor].decode("ascii")
        self._emit_scalar(path, literal, ValueType.NUMBER, (pos, cursor), depth, label)
        return cursor


def child_path(path: str, key: str) -> str:
    """``$`` + ``["items"]`` — object keys JSON-quoted, so a path is injective for any payload.

    A dotted path would make ``{"a.b": 1}`` and ``{"a": {"b": 1}}`` the same string, and this
    record's whole use is being looked up by the path it carries.
    """
    return f"{path}[{json.dumps(key, ensure_ascii=False)}]"


def parse_structured_fields(
    body: bytes,
    *,
    detection: Detection,
    bounds: ParseBounds = DEFAULT_BOUNDS,
) -> ExtractorResult:
    """Walk a JSON payload and report every value it states. Total; raises nothing.

    **Refuses rather than sniffs.** ``payload_not_json`` when
    :attr:`~parsers.payload.detect.Detection.is_json` is false, whatever the bytes look like: the
    caller has to have gone through :func:`~parsers.payload.detect.detect_json_text` and been
    told this is JSON, so the routing decision cannot be made anywhere but in the detection
    seam.

    **Empty is a refusal, not an absence.** An empty body returns ``payload_empty`` rather than
    an empty record set, so "this source said nothing" and "this source said nothing we could
    read" stay different facts.
    """
    if not detection.is_json:
        return ExtractorResult(
            records=(),
            refusals=(
                PayloadRefusal(
                    "payload_not_json",
                    f"the declared content type is {detection.declared or '(none)'!r} and the "
                    f"rule that decided was {detection.rule}. Producing structured records from "
                    "this body would be parsing a document nobody declared to be JSON, so the "
                    "route is refused: read it as text, or re-run detection for a payload whose "
                    "content type is absent rather than one that says text/plain",
                ),
            ),
            bound_hit=None,
        )
    payload = bytes(body)
    if not payload:
        return ExtractorResult(
            records=(),
            refusals=(
                PayloadRefusal(
                    "payload_empty",
                    "the payload has no bytes. An empty body is a fact about the retrieval and "
                    "is reported as one, rather than as a record set that happens to be empty",
                    0,
                ),
            ),
            bound_hit=None,
        )
    return _Scanner(payload, bounds).scan()


__all__ = ["STRUCTURED_PRODUCER", "child_path", "parse_structured_fields"]
