"""The text route: report a payload's lines, claiming no structure the payload does not state.

Feature 021 brief §25; constitution IV (fail-closed) and VI (determinism, Domain Invariant 12).

**Who arrives here, and why that is a fact rather than a fallback.** 23 of the catalogue's 146
definitions declare a parser whose upstream implementation is the identity function — the
payload comes back unparsed — and :attr:`sources.catalogue.SourceDefinition.parser_is_identity`
is where that is recorded. Those definitions have a **declared parser that parses nothing**,
which is a different thing from a definition with no parser at all: the source says "here is
my payload" and stops. So there is no key path to report, no schema to honour, and nothing to
guess.

What the bytes do state is *lines*: a ``0x0A`` at a byte offset is a fact about the payload,
not an inference about its meaning. So this extractor emits one record per line, at the line's
byte span, with a label that says the position was a line and a field path that cannot be
mistaken for a JSON path (``$line[7]``). It claims exactly one thing: **this run of bytes is
between two line terminators, or between a terminator and the end of the payload.**

**What it deliberately does not do.** It does not split on whitespace, tabulate columns, strip
a trailing ``\\r``, or find "the first field of a CSV row" — each of those is a claim about what
a line *means*, and every one of them is a different claim for a different payload format. A
line is emitted exactly as the bytes hold it, so ``line.value`` and the payload's own bytes at
``line.byte_span`` are the same string (:meth:`~parsers.payload.records.ParsedPayload.read_span`
is how a caller checks that). A consumer that knows the format is a CSV can split the line; a
consumer that does not cannot, and neither of them has to trust this module to have guessed.

**The same bounds apply.** Lines are nodes: the node ceiling, the per-type ceiling and the
depth ceiling of :class:`~parsers.payload.records.ParseBounds` all apply, the depth ceiling is
never approached because a line is not nested, and a bound that fires is recorded as a
:class:`~parsers.payload.records.BoundHit` in the same vocabulary the JSON walk uses. A 10 MB
text body is bounded by the node ceiling rather than by being refused, and says which ceiling.

**Empty lines are emitted.** A blank line is a run of zero bytes that the payload states, and
suppressing it would be a filter: the caller could not then tell a payload with no blank lines
from one whose blank lines were dropped. It is emitted, it carries ``field_surface_empty``, and
it is a record like any other. The one exception is the empty segment *after* a final
``0x0A``: a terminator ends the last line, it does not begin another one, and an empty record
at the end of every text payload would be an artefact of the splitter rather than of the
source.
"""

from __future__ import annotations

from parsers.payload.detect import Detection
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
TEXT_PRODUCER = "text_lines"

#: The byte that ends a line: RFC 8259's ``0x0A`` reused deliberately, because it is the line
#: terminator in every text format this catalogue's raw sources speak and re-deriving a second
#: set of whitespace constants would be a second answer to "what ends a line".
LINE_TERMINATOR = 0x0A


def line_field(index: int) -> str:
    """``$line[0]``, ``$line[1]``, … — a path that cannot be read as a JSON key path.

    The bracket is kept (it is how a position is written) but the ``line`` token is not a key
    any JSON payload can produce at the root, so a text record and a structured record are never
    mistaken for one another by a consumer that sorts or groups on the path.
    """
    return f"$line[{int(index)}]"


def parse_text_lines(
    body: bytes,
    *,
    detection: Detection | None = None,
    bounds: ParseBounds = DEFAULT_BOUNDS,
) -> ExtractorResult:
    """Report the payload's lines as records. Total; raises nothing.

    ``detection`` is accepted and **not used to choose anything**: this route exists for
    payloads whose structure nobody declared, and re-deciding here whether they are JSON would
    put the routing decision in two places. The registry reads
    :attr:`~parsers.payload.detect.Detection.is_json` and picks a route; this function reports
    bytes.

    **Failure modes are two named refusals and no records.** ``payload_empty`` for a body with
    no bytes; ``payload_not_utf8`` for a line whose bytes are not UTF-8, with the offset of the
    first byte that is not — and in both cases **no records at all**, for the same reason the
    JSON walk returns none on a malformed document: half a payload presented as the whole of one
    is a structure the payload does not have. (Bytes are not readable as text *and* not
    readable as JSON is the honest answer for a binary body; it is not an empty payload, and
    the difference is countable.)
    """
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
    bounds_count = bounds.max_nodes
    per_type = bounds.max_records_per_value_type
    records: list[ObservedField] = []
    nodes = 0
    strings = 0
    start = 0
    total = len(payload)
    while start <= total:
        if nodes >= bounds_count:
            return ExtractorResult(
                records=tuple(records),
                refusals=(),
                bound_hit=BoundHit("nodes_visited", bounds_count, nodes),
            )
        if strings >= per_type:
            return ExtractorResult(
                records=tuple(records),
                refusals=(),
                bound_hit=BoundHit(
                    "records_of_value_type", per_type, strings, str(ValueType.STRING)
                ),
            )
        terminator = payload.find(LINE_TERMINATOR, start)
        end = total if terminator < 0 else terminator
        if end > start or start < total:
            try:
                text = payload[start:end].decode("utf-8")
            except UnicodeDecodeError as exc:
                return ExtractorResult(
                    records=(),
                    refusals=(
                        PayloadRefusal(
                            "payload_not_utf8",
                            "these bytes are not UTF-8, so the line they delimit cannot be "
                            "read as text. Reported rather than replaced: a replacement "
                            "character would be a value the payload does not contain",
                            start + exc.start,
                        ),
                    ),
                    bound_hit=None,
                )
            address, refusal = address_for(
                value=text,
                value_type=ValueType.STRING,
                byte_span=(start, end),
                label=PayloadLabel.TEXT_LINE,
            )
            records.append(
                ObservedField(
                    field=line_field(nodes),
                    value=text,
                    value_type=ValueType.STRING,
                    byte_span=(start, end),
                    depth=0,
                    label=PayloadLabel.TEXT_LINE,
                    address=address,
                    address_refusal=refusal,
                )
            )
            nodes += 1
            strings += 1
        if terminator < 0:
            break
        start = terminator + 1
    return ExtractorResult(records=tuple(records), refusals=(), bound_hit=None)


__all__ = ["LINE_TERMINATOR", "TEXT_PRODUCER", "line_field", "parse_text_lines"]
