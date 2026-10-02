"""The cleaning stage: raw bytes in, clean addressable content out, with the ledger between.

**What this stage is for.** Everything downstream — mention extraction, dictionaries, relations —
wants text. What arrives is a web page with scripts, styles, navigation, inline handlers, entity
syntax and a density of markup. The stage that sits between them is the one that has to decide
what is content, and its whole job is to make that decision **visible and traceable to the
original bytes**: the cleaned text is a separate, separately-addressable artefact with its own
digest, and every character of the original is either quoted in the output or accounted for under
exactly one reason.

**Three families of route, and the ones that do nothing are the point.**
:func:`~parsers.primproc.processor.PrimaryProcessor.process` picks a route from the declared media
type and hands the JSON question to :func:`parsers.payload.detect.detect_json_text` rather than
re-implementing it — that decision already has five named rules and a recorded probe offset, and a
sixth rule written here would be a second answer to a question the platform has already answered.
:attr:`~parsers.primproc.reasons.Route.JSON`,
:attr:`~parsers.primproc.reasons.Route.NDJSON`,
:attr:`~parsers.primproc.reasons.Route.TEXT` and
:attr:`~parsers.primproc.reasons.Route.PASSTHROUGH` return the **original bytes, untouched and
recorded as untouched**. A cleaner that rewrites a JSON payload has corrupted evidence: the payload
is what the source stated, and re-serialising it would replace the source's key order, its number
formatting and its spacing with this stage's opinions about all three — and re-encoding it to
UTF-8 would replace the source's encoding with ours. Only
:attr:`~parsers.primproc.reasons.Route.HTML` and
:attr:`~parsers.primproc.reasons.Route.XML` do work.

**The whitespace pass, and what it costs.** Non-breaking spaces are folded to ``U+0020``, runs of
spaces and tabs collapse to one, and a run containing a line terminator ends the line. The cost of
folding nbsp is stated rather than hidden: it destroys the distinction between "these two words may
not be split" and "these two words are one", which is a real distinction in the evidence. This
stage gives it up because the directive asks for it, and because the alternative — treating nbsp as
non-collapsible — makes "collapsed whitespace" mean two different things depending on which
codepoint arrived. Everything else is exact: the pass is character-driven, so the byte count of
every collapsed run is measured rather than estimated.

**Where the line breaks come from, and the one number with no source behind it.** A break is
produced by a block-level tag or by a whitespace run containing a terminator. The whitespace case
has source characters; the block-tag case does not — the tag was removed as
:attr:`~parsers.primproc.reasons.RemovalReason.ELEMENT_MARKUP` and the newline that follows it is
**synthesised**. So the ledger's output characters do not sum to ``len(text)``; they sum to
``len(text) - (len(lines) - 1)``, and :attr:`~parsers.primproc.result.PrimaryResult.lines` accounts
for the difference exactly. Reported rather than papered over, because a stage whose accounting is
off by a constant nobody can name is a stage whose accounting is not believed.

**Determinism (constitution VI, Domain Invariant 12).** No clock, no randomness, no network, no
set iteration on any path from bytes to result. Every comparison between candidate elements is
over their positions in the source, every table is a :class:`~types.MappingProxyType`, every
vocabulary is a tuple, and :meth:`PrimaryProcessor.process` is a pure function of
``(body, content_type)`` plus the configuration given at construction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from typing import Final

from parsers.payload.detect import Detection, detect_json_text, media_type_essence
from parsers.primproc.decode import DecodeDecision, decode_body
from parsers.primproc.markup import (
    BLOCK_TAGS,
    ENTITY_KINDS,
    KIND_CDATA,
    KIND_COMMENT,
    KIND_DECL,
    KIND_END_TAG,
    KIND_PI,
    KIND_START_TAG,
    KIND_UNKNOWN_DECL,
    MARKUP_KINDS,
    TEXT_KINDS,
    Construct,
    ElementSpan,
    MarkupDocument,
    Note,
    attribute_is_dropped,
    parse_markup,
)
from parsers.primproc.reasons import (
    CONTENT_CLASS_PATTERN,
    DONOR_IRRELEVANT_PATTERN,
    DONOR_IRRELEVANT_TAGS,
    ENTITY_SYNTAX_REASON,
    MIN_DENSITY_CHARS,
    PRIMARY_PROC_SCHEMA,
    PRIMARY_PROC_VERSION,
    REMOVAL_REASONS,
    SKIP_TAGS,
    ExtractStrategy,
    NoteCode,
    RemovalReason,
    Route,
    SpanVerdict,
)
from parsers.primproc.result import (
    OutputLine,
    PrimaryResult,
    SourceSpan,
    zero_removals,
)

#: Media types that route to HTML parsing. Checked before the ``+xml`` suffix test, because
#: ``application/xhtml+xml`` ends in ``+xml`` and is served as HTML by every consumer that has an
#: opinion about it. The order of these two tests is a decision; recording it means a reader asking
#: "why was this XHTML treated as HTML" finds the answer in one place.
HTML_MEDIA_TYPES: Final[frozenset[str]] = frozenset({"text/html", "application/xhtml+xml"})

#: Media types that route to XML parsing. ``text/xml`` is unregistered in the same spirit that keeps
#: ``text/json`` out of :mod:`parsers.payload.detect` — it is not what a source sends. It is listed
#: because refusing to read a payload whose source named a type everyone recognises would be
#: pedantry, and the refusal that matters (an undeclared charset) is unaffected.
XML_MEDIA_TYPES: Final[frozenset[str]] = frozenset(
    {"application/xml", "text/xml", "application/rss+xml", "application/atom+xml"}
)

#: Media types that route to the NDJSON passthrough. Checked **before** the JSON test,
#: because NDJSON is JSON per line and a JSON detector would call it JSON — true and
#: useless, since both routes are byte-identical and a caller counting structured payloads
#: wants them apart.
NDJSON_MEDIA_TYPES: Final[frozenset[str]] = frozenset(
    {"application/x-ndjson", "application/ndjson", "application/jsonlines", "application/x-jsonlines"}
)

#: Characters the collapse treats as whitespace. Pinned rather than inherited from ``str.isspace``,
#: because ``str.isspace`` includes ``U+001C``–``U+001F`` — **control** characters some sources emit
#: as padding — and treating them as layout silently hides a source's bug. Written as escapes so the
#: set is readable rather than a row of invisible glyphs.
WHITESPACE_CHARS: Final[frozenset[str]] = frozenset(
    {
        "\t",
        "\n",
        "\v",
        "\f",
        "\r",
        " ",
        "\u00a0",  # no-break space — folded to U+0020, a stated cost
        "\u2007",  # figure space
        "\u2009",  # thin space
        "\u200a",  # hair space
        "\u202f",  # narrow no-break space
    }
)

#: Whitespace characters that end a line rather than becoming a space. ``U+2028``/``U+2029`` are
#: included because they are line terminators to every consumer that matters, and a stage that
#: collapsed them into a space would join two lines a reader believes are two.
LINE_TERMINATORS: Final[frozenset[str]] = frozenset({"\n", "\r", "\u2028", "\u2029"})

_CONTENT_CLASS: Final[re.Pattern[str]] = re.compile(CONTENT_CLASS_PATTERN, re.IGNORECASE)
_IRRELEVANT: Final[re.Pattern[str]] = re.compile(DONOR_IRRELEVANT_PATTERN, re.IGNORECASE)

#: Elements that are never candidates for the density strategy. ``html``/``body`` would tie with
#: whatever they contain and win on document order, which would report "we chose the main content"
#: when in fact nothing was chosen — the whole reason
#: :attr:`~parsers.primproc.reasons.ExtractStrategy.WHOLE_DOCUMENT` exists is that this case has its
#: own honest answer.
_NEVER_DENSITY: Final[frozenset[str]] = frozenset({"html", "body", "head"})

_TAG_SPACE: Final[frozenset[str]] = frozenset(" \t\n\r\f\v")
_TAG_NAME_STOP: Final[frozenset[str]] = frozenset("/>")
_ATTR_NAME_STOP: Final[frozenset[str]] = frozenset("= \t\n\r\f\v/>")


@dataclass(frozen=True, slots=True)
class _AttrSpan:
    """One attribute's exact source span inside a raw start tag, with the name lowercased."""

    name: str
    start: int
    end: int


def scan_tag_attributes(raw: str) -> tuple[int, tuple[_AttrSpan, ...]] | None:
    """``(region_start, attributes)`` for a raw start tag, or ``None`` if the scan does not close.

    ``region_start`` is where the attributes begin — the character after the tag name — so a caller
    can partition the tag's span into name, attributes and tail with no gap between them.

    The leading whitespace of each attribute is **inside** that attribute's span. That is why
    ``<div style="x">`` reports six dropped bytes rather than four: the space that separated the
    name from the attribute left with it, and counting only ``style="x"`` would leave a byte the tag
    was not really removed by. For the same reason the whitespace before the tag's ``>`` belongs to
    the **tail** and is accounted as such: a live Wikipedia page has ``<div … title="Main menu" >``
    with a space before the ``>``, and a scan that stopped at the last attribute left that byte
    unclaimed — which is the one outcome this function exists to make impossible.

    So the scan is **total over well-formed tags**: every character of the tag is either the name
    region, inside an attribute, or in the tail, and the caller's three-way split is gapless. The
    ``None`` return is a guard against the alternative — a caller that partitions the tag and cannot
    account for a byte — and it is not reached for any tag in the corpus the tests run. The caller
    treats it as "count the whole tag as markup and record a note", which loses no byte and claims no
    split it could not justify.
    """
    length = len(raw)
    cursor = 1
    while cursor < length and raw[cursor] not in _TAG_NAME_STOP and raw[cursor] not in _TAG_SPACE:
        cursor += 1
    region_start = cursor
    found: list[_AttrSpan] = []
    covered = cursor
    while cursor < length:
        if raw[cursor] == ">":
            break
        if raw[cursor] == "/":
            cursor += 1
            covered = cursor
            continue
        attr_start = cursor
        while cursor < length and raw[cursor] in _TAG_SPACE:
            cursor += 1
        if cursor >= length:
            covered = cursor
            break
        if raw[cursor] in _TAG_NAME_STOP:
            covered = cursor
            continue
        name_start = cursor
        while cursor < length and raw[cursor] not in _ATTR_NAME_STOP:
            cursor += 1
        name = raw[name_start:cursor].lower()
        while cursor < length and raw[cursor] in _TAG_SPACE:
            cursor += 1
        if cursor < length and raw[cursor] == "=":
            cursor += 1
            while cursor < length and raw[cursor] in _TAG_SPACE:
                cursor += 1
            if cursor < length and raw[cursor] in "\"'":
                quote = raw[cursor]
                cursor += 1
                while cursor < length and raw[cursor] != quote:
                    cursor += 1
                cursor = min(cursor + 1, length)
            else:
                while cursor < length and raw[cursor] not in _TAG_SPACE and raw[cursor] != ">":
                    cursor += 1
        if cursor <= attr_start or attr_start != covered:
            return None
        found.append(_AttrSpan(name=name, start=attr_start, end=cursor))
        covered = cursor
    if covered != cursor:
        return None
    return region_start, tuple(found)


def _element_is_content_class(element: ElementSpan) -> bool:
    return bool(_CONTENT_CLASS.search(element.descriptor()))


def select_region(document: MarkupDocument) -> tuple[ExtractStrategy, int, int]:
    """``(strategy, start_char, end_char)`` — which rule chose the main content, and its span.

    Strategies are tried in :data:`~parsers.primproc.reasons.EXTRACT_STRATEGIES` order and the
    **first element in document order** wins inside each. Density is the exception, resolved by a
    strict ``>`` in document order, so a tie goes to the earlier element and no comparison depends
    on anything but positions in the source.

    Density also has a floor, :data:`~parsers.primproc.reasons.MIN_DENSITY_CHARS`. Without one, the
    container around a single character wins and the record says :attr:`ExtractStrategy.DENSITY`,
    which reads as a measurement of the page's main content when nothing was measured.

    ``(WHOLE_DOCUMENT, 0, len)`` is the answer when nothing matched, and it is returned rather than
    raised: a page with no ``<article>`` is not an error, it is a page whose whole body is the best
    available guess, and the guess is what the strategy field says it is.
    """
    for tag, strategy in (("article", ExtractStrategy.ARTICLE), ("main", ExtractStrategy.MAIN)):
        for element in document.elements:
            if element.tag == tag:
                return strategy, element.start_char, element.end_char
    for element in document.elements:
        if (element.attr("role") or "").strip().lower() == "main":
            return ExtractStrategy.ROLE_MAIN, element.start_char, element.end_char
    for element in document.elements:
        if _element_is_content_class(element):
            return ExtractStrategy.CONTENT_CLASS, element.start_char, element.end_char
    best: ElementSpan | None = None
    best_chars = 0
    for element in document.elements:
        if element.tag in _NEVER_DENSITY:
            continue
        if element.text_chars > best_chars:
            best = element
            best_chars = element.text_chars
    if best is not None and best_chars >= MIN_DENSITY_CHARS:
        return ExtractStrategy.DENSITY, best.start_char, best.end_char
    return ExtractStrategy.WHOLE_DOCUMENT, 0, document.index.char_length


@dataclass(slots=True)
class _LineBuilder:
    """Assembles output lines while remembering which source characters each came from.

    Holds the two pieces of state the whitespace rule needs and nothing else — whether the current
    line has content, and what the last emitted character was. Both exist to answer one question,
    "may this whitespace run contribute a space?", and both are derived from the source in order, so
    the same bytes always produce the same lines.
    """

    lines: list[OutputLine]
    pieces: list[str]
    first_byte: int
    last_byte: int
    has_content: bool
    last_emitted: str

    @classmethod
    def start(cls) -> _LineBuilder:
        return cls(
            lines=[], pieces=[], first_byte=0, last_byte=0, has_content=False, last_emitted=""
        )

    def emit(self, char: str, byte_start: int, byte_end: int) -> None:
        if not self.pieces:
            self.first_byte = byte_start
        self.pieces.append(char)
        self.last_byte = byte_end
        self.has_content = True
        self.last_emitted = char

    def flush(self) -> None:
        """Close the current line, if it has one. An empty line is never emitted.

        Which is how "three blank lines between two paragraphs" becomes zero blank lines: the
        terminator runs that produced them removed every character they had, so the builder has
        nothing to emit and no line appears. The removed characters are counted under
        :attr:`~parsers.primproc.reasons.RemovalReason.WHITESPACE` like any other collapse.
        """
        if not self.pieces:
            return
        text = "".join(self.pieces)
        previous = self.lines[-1] if self.lines else None
        char_start = 0 if previous is None else previous.output_char_end + 1
        self.lines.append(
            OutputLine(
                line_number=len(self.lines) + 1,
                text=text,
                output_char_start=char_start,
                output_char_end=char_start + len(text),
                output_byte_start=0,
                output_byte_end=len(text.encode("utf-8")),
                source_byte_start=self.first_byte,
                source_byte_end=self.last_byte,
            )
        )
        self.pieces = []
        self.has_content = False
        self.last_emitted = ""


class PrimaryProcessor:
    """Turns raw bytes into clean content, and says exactly what it did.

    Configuration is given at construction and never inferred from the payload, so two processors
    configured differently are two named things rather than one behaviour that depends on what has
    been through it. Every knob is off by default except the directive's own choices.
    """

    def __init__(
        self,
        *,
        probe_meta_charset: bool = False,
        skip_tags: frozenset[str] = SKIP_TAGS,
        opt_in_irrelevant_tags: bool = False,
        drop_attributes: bool = True,
        max_source_chars: int | None = None,
    ) -> None:
        self._probe_meta = bool(probe_meta_charset)
        self._drop_attributes = bool(drop_attributes)
        self._max_source_chars = max_source_chars
        tags = set(skip_tags)
        if opt_in_irrelevant_tags:
            tags |= DONOR_IRRELEVANT_TAGS
        self._skip_tags: frozenset[str] = frozenset(tags)
        self._irrelevant = bool(opt_in_irrelevant_tags)

    @property
    def version(self) -> str:
        return PRIMARY_PROC_VERSION

    @property
    def schema(self) -> str:
        return PRIMARY_PROC_SCHEMA

    @property
    def skip_tags(self) -> tuple[str, ...]:
        """The elements this processor removes whole. Sorted, so it is a reportable fact."""
        return tuple(sorted(self._skip_tags))

    def is_cleaning_route(self, content_type: str | None) -> bool:
        """Whether ``content_type`` names a route this stage does work on.

        The runtime wrapper asks this before spending anything on an artefact. A ``False`` means the
        artefact is left alone rather than refused — a payload this stage has no opinion about is not
        a failure, and refusing it would be the transport making a semantic decision about someone
        else's media type.
        """
        return self.route_for(content_type) in (Route.HTML, Route.XML)

    def route_for(self, content_type: str | None) -> Route:
        """The route ``content_type`` names, without a body. Same order as :meth:`process`.

        The JSON test runs **before** the text/passthrough split and not after it, which is the whole
        point of delegating to :func:`parsers.payload.detect.detect_json_text`: a source that declares
        ``application/ld+json`` is routed by the media type the platform already has five rules for,
        and an ``ld+json`` payload must not fall through to "unaddressed type" because this function
        happened to check the type prefix first.
        """
        essence = media_type_essence(content_type)
        if essence in HTML_MEDIA_TYPES:
            return Route.HTML
        if essence in XML_MEDIA_TYPES or essence.endswith("+xml"):
            return Route.XML
        if essence in NDJSON_MEDIA_TYPES:
            return Route.NDJSON
        detection = detect_json_text(
            content_type=content_type, body=b"", probe_when_undeclared=not essence
        )
        if detection.is_json:
            return Route.JSON
        if essence.startswith("text/") or not essence:
            return Route.TEXT
        return Route.PASSTHROUGH

    # -- the stage ---------------------------------------------------------- #

    def process(self, body: bytes, *, content_type: str | None = None) -> PrimaryResult:
        """Clean ``body``, and return the text with the ledger that accounts for it.

        Total in the sense that matters: no input raises for a reason the caller could not have
        anticipated. A decode that cannot be done is a **refused result** with ``ok=False`` and a
        code, not an exception; a page over the configured bound is a result with
        :attr:`~parsers.primproc.reasons.NoteCode.SOURCE_BOUND_HIT` in its notes. The one thing that
        does raise is the tokenizer's tiling check, and that is deliberate — it means a character
        exists that no rule claimed, and a result with an unattributable character in it is not a
        measurement.
        """
        decode = decode_body(
            body=body, content_type=content_type, probe_when_undeclared=self._probe_meta
        )
        essence = media_type_essence(content_type)
        route = self.route_for(content_type)
        detection = detect_json_text(
            content_type=content_type, body=body, probe_when_undeclared=not essence
        )
        if not decode.ok:
            return PrimaryResult(
                ok=False,
                route=route,
                strategy=ExtractStrategy.WHOLE_DOCUMENT,
                text="",
                input_bytes=len(body) if isinstance(body, bytes) else 0,
                output_bytes=0,
                decode=decode,
                removed_bytes_by_reason=zero_removals(),
                entity_expansion_bytes=0,
                ledger=(),
                lines=(),
                notes=(),
            )
        if route in (Route.JSON, Route.NDJSON, Route.TEXT, Route.PASSTHROUGH):
            return self._unchanged(route, body, decode)
        return self._clean(route, decode, detection)

    # -- passthrough -------------------------------------------------------- #

    def _unchanged(self, route: Route, body: bytes, decode: DecodeDecision) -> PrimaryResult:
        """A route that changes nothing: the original bytes, in and out.

        :attr:`~parsers.primproc.result.PrimaryResult.verbatim_body` carries them, which is the only
        way "unchanged" can be true of a payload that was not UTF-8. The ledger's one kept span and
        the full zeroed accounting are still present, so "this stage decided to change nothing" is a
        recorded decision with a version on it rather than the absence of a record, and
        ``input_bytes == output_bytes`` is its checkable form.
        """
        text = decode.text
        span = (
            SourceSpan(
                start_char=0,
                end_char=len(text),
                verdict=SpanVerdict.KEPT,
                reason="",
                output_chars=len(text),
                source_byte_start=0,
                source_byte_end=len(body),
                text=text,
            )
            if text
            else None
        )
        lines = (
            (
                OutputLine(
                    line_number=1,
                    text=text,
                    output_char_start=0,
                    output_char_end=len(text),
                    output_byte_start=0,
                    output_byte_end=len(body),
                    source_byte_start=0,
                    source_byte_end=len(body),
                ),
            )
            if text
            else ()
        )
        return PrimaryResult(
            ok=True,
            route=route,
            strategy=ExtractStrategy.WHOLE_DOCUMENT,
            text=text,
            input_bytes=len(body),
            output_bytes=len(body),
            decode=decode,
            removed_bytes_by_reason=zero_removals(),
            entity_expansion_bytes=0,
            ledger=() if span is None else (span,),
            lines=lines,
            notes=(),
            verbatim_body=body,
        )

    # -- the cleaning routes ------------------------------------------------ #

    def _clean(
        self, route: Route, decode: DecodeDecision, detection: Detection
    ) -> PrimaryResult:
        """HTML and XML: parse, remove, select, collapse, account."""
        document = parse_markup(
            decode.text,
            codec=decode.charset,
            xml_mode=route is Route.XML,
            skip_tags=self._skip_tags,
            max_chars=self._max_source_chars,
        )
        notes: list[Note] = list(document.notes)
        strategy, region_start, region_end = select_region(document)
        index = document.index
        ledger: list[SourceSpan] = []
        removals = zero_removals()
        entity_expansion_bytes = 0
        builder = _LineBuilder.start()
        skip_depth = 0
        pending_break = False
        notes_seen: set[str] = set()

        def add_note(code: str, detail: str, offset: int | None = None) -> None:
            if code in notes_seen:
                return
            notes_seen.add(code)
            notes.append(Note(code, detail, offset))

        def span(start: int, end: int, verdict: SpanVerdict, reason: str, out: int, text: str = ""):
            byte_start, byte_end = index.byte_span(start, end)
            ledger.append(
                SourceSpan(
                    start_char=start,
                    end_char=end,
                    verdict=verdict,
                    reason=reason,
                    output_chars=out,
                    source_byte_start=byte_start,
                    source_byte_end=byte_end,
                    text=text,
                )
            )

        def removed(start: int, end: int, reason: RemovalReason) -> None:
            byte_start, byte_end = index.byte_span(start, end)
            removals[str(reason)] += byte_end - byte_start
            span(start, end, SpanVerdict.REMOVED, str(reason), 0)

        def take_char(start: int, reason: RemovalReason) -> None:
            """One removed character, counted and recorded on its own."""
            byte_start, byte_end = index.byte_span(start, start + 1)
            removals[str(reason)] += byte_end - byte_start
            span(start, start + 1, SpanVerdict.REMOVED, str(reason), 0)

        def want_space() -> bool:
            """Whether a whitespace run may contribute the single space that survives collapse."""
            return builder.has_content and builder.last_emitted != " "

        for construct in document.constructs:
            is_start = construct.kind == KIND_START_TAG
            is_end = construct.kind == KIND_END_TAG
            if is_start and (
                construct.tag in self._skip_tags
                or (self._irrelevant and self._is_irrelevant(construct))
            ):
                skip_depth += 1
            # The state at this construct, **including** the one it just opened: a ``<script>``
            # start tag is inside the skip region as much as its content is, and an end tag
            # is measured before it closes the region rather than after. An earlier version
            # decremented on *every* end tag while the depth was positive, so
            # ``<head><title>t</title></head>`` popped the depth twice and the ``</head>`` was
            # counted as element markup rather than as part of the removed region. The ledger
            # is what made that visible: the byte total was right and one span's reason was
            # wrong, which is exactly the kind of error a summed count hides.
            in_skip = skip_depth > 0
            in_region = construct.start_char >= region_start and construct.end_char <= region_end

            if (is_start or is_end) and construct.tag in BLOCK_TAGS:
                pending_break = True

            if construct.kind in MARKUP_KINDS:
                if in_skip:
                    removed(construct.start_char, construct.end_char, RemovalReason.SKIP_ELEMENT)
                elif construct.kind == KIND_COMMENT:
                    removed(construct.start_char, construct.end_char, RemovalReason.HTML_COMMENT)
                elif construct.kind in (KIND_DECL, KIND_PI, KIND_UNKNOWN_DECL):
                    removed(
                        construct.start_char, construct.end_char, RemovalReason.MARKUP_DECLARATION
                    )
                elif is_start:
                    self._account_start_tag(construct, document, removed, add_note)
                else:
                    removed(construct.start_char, construct.end_char, RemovalReason.ELEMENT_MARKUP)
            elif construct.kind in ENTITY_KINDS:
                if in_skip:
                    removed(construct.start_char, construct.end_char, RemovalReason.SKIP_ELEMENT)
                elif not in_region:
                    removed(construct.start_char, construct.end_char, RemovalReason.OUTSIDE_MAIN)
                else:
                    if pending_break:
                        builder.flush()
                        pending_break = False
                    entity_expansion_bytes += self._emit_entity(
                        builder,
                        document,
                        construct,
                        index,
                        span,
                        removed,
                        keep_space=want_space,
                    )
            elif construct.kind in TEXT_KINDS:
                if construct.kind == KIND_CDATA:
                    add_note(
                        str(NoteCode.XML_CDATA_KEPT),
                        "a CDATA section was read as text rather than dropped",
                        construct.start_char,
                    )
                if in_skip:
                    removed(construct.start_char, construct.end_char, RemovalReason.SKIP_ELEMENT)
                elif not in_region:
                    removed(construct.start_char, construct.end_char, RemovalReason.OUTSIDE_MAIN)
                else:
                    if pending_break:
                        builder.flush()
                        pending_break = False
                    self._emit_text(
                        builder, document, construct, index, span, removed, take_char, want_space
                    )
            else:  # pragma: no cover - the construct vocabulary is closed
                removed(construct.start_char, construct.end_char, RemovalReason.ELEMENT_MARKUP)

            if is_end and construct.tag in self._skip_tags and skip_depth > 0:
                skip_depth -= 1

        builder.flush()
        ledger.sort(key=lambda item: (item.start_char, item.end_char))

        text = "\n".join(line.text for line in builder.lines)
        lines = tuple(
            OutputLine(
                line_number=line.line_number,
                text=line.text,
                output_char_start=line.output_char_start,
                output_char_end=line.output_char_end,
                output_byte_start=len(text[: line.output_char_start].encode("utf-8")),
                output_byte_end=len(text[: line.output_char_end].encode("utf-8")),
                source_byte_start=line.source_byte_start,
                source_byte_end=line.source_byte_end,
            )
            for line in builder.lines
        )
        return PrimaryResult(
            ok=True,
            route=route,
            strategy=strategy,
            text=text,
            input_bytes=index.byte_length(0, index.char_length),
            output_bytes=len(text.encode("utf-8")),
            decode=decode,
            removed_bytes_by_reason=removals,
            entity_expansion_bytes=entity_expansion_bytes,
            ledger=tuple(ledger),
            lines=lines,
            notes=tuple(notes),
        )

    # -- per-construct accounting ------------------------------------------- #

    def _is_irrelevant(self, construct: Construct) -> bool:
        """Whether an element is chrome by the donor's heuristics. Only consulted when opted in."""
        if construct.tag in DONOR_IRRELEVANT_TAGS:
            return True
        return bool(_IRRELEVANT.search(construct.descriptor()))

    def _account_start_tag(self, construct, document, removed, add_note) -> None:
        """Split a kept start tag into name, attributes and tail, and count what left.

        Attributes are located by :func:`scan_tag_attributes` over the tag's own source, so the
        dropped byte count is **measured**. When the scan does not close, or when the names it found
        disagree with the ones the tokenizer reported, the whole tag is counted as
        :attr:`~parsers.primproc.reasons.RemovalReason.ELEMENT_MARKUP` and a note is recorded: the
        bytes are still counted, just not split, and the reason a reader gets is "we could not say
        which attributes this tag had" rather than a guess.

        The disagreement check is a real guard and not paranoia. ``html.parser`` reports an attribute
        *list* — names and values, no positions — so it cannot be used to measure bytes; and if the
        two disagree about which attributes a tag carries, then one of them is wrong, and attributing
        bytes to the wrong one of them is worse than not splitting.
        """
        if not self._drop_attributes:
            removed(construct.start_char, construct.end_char, RemovalReason.ELEMENT_MARKUP)
            return
        raw = document.text_span(construct)
        scanned = scan_tag_attributes(raw)
        names_agree = scanned is not None and tuple(
            sorted(attribute.name for attribute in scanned[1])
        ) == tuple(sorted(name.lower() for name, _ in construct.attrs))
        if scanned is None or not names_agree:
            add_note(
                str(NoteCode.HTML_ATTRIBUTE_SCAN_INCOMPLETE),
                f"the attributes of the <{construct.tag}> tag at character "
                f"{construct.start_char} could not be located exactly, so the whole tag is counted "
                "as element markup rather than split. Every byte is still counted",
                construct.start_char,
            )
            removed(construct.start_char, construct.end_char, RemovalReason.ELEMENT_MARKUP)
            return
        region_start, attributes = scanned
        removed(
            construct.start_char,
            construct.start_char + region_start,
            RemovalReason.ELEMENT_MARKUP,
        )
        for attribute in attributes:
            reason = (
                RemovalReason.ATTRIBUTE
                if attribute_is_dropped(attribute.name)
                else RemovalReason.ELEMENT_MARKUP
            )
            removed(
                construct.start_char + attribute.start,
                construct.start_char + attribute.end,
                reason,
            )
        tail_start = construct.start_char + (
            attributes[-1].end if attributes else region_start
        )
        removed(tail_start, construct.end_char, RemovalReason.ELEMENT_MARKUP)

    def _emit_text(self, builder, document, construct, index, span, removed, take_char, want_space):
        """Walk one text run's characters, applying the whitespace rule and the ledger.

        A maximal run of non-whitespace is one :class:`~parsers.primproc.result.SourceSpan` over the
        whole run rather than one per character, so the ledger stays readable on a long paragraph;
        the emitted characters still carry their own byte spans onto the line, which is what the
        Raw↔line mapping needs. A whitespace run is handled one character at a time because its
        characters have three different fates and only the last of them is kept.
        """
        raw = document.text_span(construct)
        position = 0
        while position < len(raw):
            if raw[position] in WHITESPACE_CHARS:
                run_start = position
                while position < len(raw) and raw[position] in WHITESPACE_CHARS:
                    position += 1
                self._emit_whitespace_run(
                    builder,
                    construct,
                    raw,
                    run_start,
                    position,
                    index,
                    span,
                    removed,
                    take_char,
                    want_space,
                )
                continue
            run_start = position
            while position < len(raw) and raw[position] not in WHITESPACE_CHARS:
                position += 1
            chunk = raw[run_start:position]
            span(
                construct.start_char + run_start,
                construct.start_char + position,
                SpanVerdict.KEPT,
                "",
                len(chunk),
                chunk,
            )
            for offset, character in enumerate(chunk):
                char_start = construct.start_char + run_start + offset
                char_byte_start, char_byte_end = index.byte_span(char_start, char_start + 1)
                builder.emit(character, char_byte_start, char_byte_end)

    def _emit_whitespace_run(
        self, builder, construct, raw, run_start, run_end, index, span, removed, take_char,
        want_space,
    ):
        """One maximal whitespace run: it ends the line, or it collapses to one space, or it drops.

        Three outcomes, and why they are three:

        * it contains a line terminator → every character is removed and the line ends. The break is
          **synthesised** from the terminator, which is why the ledger's output characters sum to
          ``len(text) - (len(lines) - 1)`` rather than to ``len(text)``.
        * it would open a line, or would follow a space → every character is removed and nothing is
          emitted. A leading space is layout; keeping it would make every line start with a space
          and shift every column an analyst reads.
        * otherwise → all but the last character are removed and the last emits one space. Keeping
          the last rather than synthesising it is what lets the ledger be a partition *and* the
          accounting exact at once: the byte that survives is a byte that was counted.
        """
        chunk = raw[run_start:run_end]
        has_terminator = any(character in LINE_TERMINATORS for character in chunk)
        emit_at = None if (has_terminator or not want_space()) else len(chunk) - 1
        for offset in range(len(chunk)):
            char_start = construct.start_char + run_start + offset
            if offset == emit_at:
                byte_start, byte_end = index.byte_span(char_start, char_start + 1)
                span(char_start, char_start + 1, SpanVerdict.KEPT, "", 1, " ")
                builder.emit(" ", byte_start, byte_end)
            else:
                take_char(char_start, RemovalReason.WHITESPACE)
        if has_terminator:
            builder.flush()

    def _emit_entity(self, builder, document, construct, index, span, removed, keep_space):
        """An entity reference: unescape it, count the swap, and join the line.

        Returns the number of output characters the expansion actually contributed. A reference the
        entity table does not know (``&notanentity;``) comes back with ``expansion == raw`` and is
        treated as literal text — the source's own characters, kept verbatim, counted as kept, and
        **not** reported as unescaping. That distinction is the difference between "this stage
        unescaped entities" and "this stage saw an ``&``", and it is why the comparison is on the
        expansion rather than on the presence of an ``&``.

        The returned count is what the :attr:`~parsers.primproc.reasons.SpanVerdict.REPLACED` span
        declares, and it is measured rather than assumed because an expansion can contribute
        **nothing**: ``a&nbsp;&nbsp;b`` expands to three characters, two of which the collapse eats,
        so a span that declared ``len(expansion)`` would over-count the output by two and the
        ledger's sum would stop reconciling with the text.
        """
        raw = document.text_span(construct)
        expansion = unescape(raw)
        byte_start, byte_end = index.byte_span(construct.start_char, construct.end_char)
        if expansion == raw:
            for offset in range(len(raw)):
                char_start = construct.start_char + offset
                char_byte_start, char_byte_end = index.byte_span(char_start, char_start + 1)
                span(char_start, char_start + 1, SpanVerdict.KEPT, "", 1, raw[offset])
                builder.emit(raw[offset], char_byte_start, char_byte_end)
            return 0
        emitted = 0
        position = 0
        while position < len(expansion):
            character = expansion[position]
            if character in WHITESPACE_CHARS:
                run_end = position + 1
                while run_end < len(expansion) and expansion[run_end] in WHITESPACE_CHARS:
                    run_end += 1
                if keep_space():
                    builder.emit(" ", byte_start, byte_end)
                    emitted += 1
                position = run_end
                continue
            builder.emit(character, byte_start, byte_end)
            emitted += 1
            position += 1
        span(
            construct.start_char,
            construct.end_char,
            SpanVerdict.REPLACED,
            ENTITY_SYNTAX_REASON,
            emitted,
            raw,
        )
        return emitted


__all__ = [
    "HTML_MEDIA_TYPES",
    "LINE_TERMINATORS",
    "NDJSON_MEDIA_TYPES",
    "REMOVAL_REASONS",
    "WHITESPACE_CHARS",
    "XML_MEDIA_TYPES",
    "PrimaryProcessor",
    "scan_tag_attributes",
    "select_region",
]
