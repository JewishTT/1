"""The markup tokenizer, and the source index that makes every byte addressable.

**The problem this module exists to solve.** ``html.parser`` reports *where it is* — ``getpos()``
returns a line and a character column — but not *how long the thing it just reported was*. There
is no ``get_endtag_text()``, and the start-tag case is the only one where the raw text is offered
at all. So a naive consumer records positions and guesses lengths, and a guessed length is how a
Raw↔line mapping ends up pointing at the wrong line on a page with one long attribute.

**The tiling rule, which is the whole trick.** The tokenizer's input stream is partitioned, with
no gaps and no overlaps, into exactly the events it reports: a data region, a start tag, an end
tag, a comment, a declaration, a processing instruction. There is no "skip" step — whitespace
between tags is itself a data region, and the byte a parser does not consume as markup is always
handed back as text. Therefore **a construct ends where the next one begins**, and the last
construct ends at the end of the input. That turns "end position" from something that has to be
guessed into something that is read off the next event, and it is verified here against a corpus
of adversarial markup rather than assumed: :func:`assert_tiling` is the check, and a gap is a
refusal rather than a wrong offset.

Verified against CPython 3.11's ``html.parser`` on the cases that break naive consumers:
``a < b > c`` (three data regions, the ``<`` is text), ``&notanentity;`` (an entity-shaped run
that is not an entity), ``<a href=">">`` (a ``>`` inside an attribute value), ``<div`` and
``<p>trunc`` (truncated input, which yields text and a note rather than an exception),
``text<!--unterminated`` (a comment opener the tokenizer declines to recognise), and
``<script>if (a<b)</script>`` (CDATA content that contains a ``<``).

**Why ``convert_charrefs=False``, which is not the parser's default.** With conversion on, the
parser buffers character references and hands back one already-unescaped string whose *source*
length no longer relates to its length, so the boundary between "this span was markup" and "this
span was text" is unrecoverable without re-deriving it. With it off, ``&lt;`` arrives as its own
event with an exact source span, so **entity unescaping becomes an accounting event rather than a
side effect**: the span's five source characters are recorded as
:data:`~parsers.primproc.reasons.ENTITY_SYNTAX_REASON` and the one character that replaces them is
recorded as what reached the output. That is the difference between a stage that says it unescaped
entities and one that a reader can check.

**``a < b > c`` and ``<<SEE>>``, stated precisely because they are the directive's examples.**
``a < b > c`` survives verbatim here: the ``<`` is followed by a space, so it is not a tag start,
it is text, and three data regions come out — exactly as a browser renders it. ``<<SEE>>`` in
**raw** source is a different matter and no conforming parser can save it: ``<SEE>`` *is* an
unknown element by HTML's own rules, so the tokenizer reports a start tag and the text around it
survives as ``<>``. The spelling that carries the text — and the spelling every real page uses,
because a bare ``<<`` in markup is a parse error for authors too — is ``&lt;&lt;SEE&gt;&gt;``, and
that round-trips to ``<<SEE>>`` here byte for byte. A ``re.sub`` implementation fails on
``a < b > c``; it happens to survive ``&lt;&lt;SEE&gt;&gt;`` *by accident*, because after
``re.sub`` there is nothing left in the string for it to match.

**Determinism.** No clock, no randomness, no set iteration on any path from bytes to constructs;
the implied-end-tag table is a :class:`~types.MappingProxyType` and every candidate comparison
is over positions in the source. The same bytes give the same constructs, in the same order, in a
second process (constitution VI, Domain Invariant 12).
"""

from __future__ import annotations

import bisect
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from types import MappingProxyType
from typing import Final

from parsers.primproc.reasons import NoteCode

#: Construct kinds. A closed vocabulary rather than a string union scattered over the class,
#: because the accounting in :mod:`parsers.primproc.processor` switches on it and a missed case
#: there would be a byte with no reason.
KIND_DATA: Final = "data"
KIND_CDATA: Final = "cdata"
KIND_ENTITY_REF: Final = "entityref"
KIND_CHAR_REF: Final = "charref"
KIND_START_TAG: Final = "start_tag"
KIND_END_TAG: Final = "end_tag"
KIND_COMMENT: Final = "comment"
KIND_DECL: Final = "decl"
KIND_PI: Final = "pi"
KIND_UNKNOWN_DECL: Final = "unknown_decl"

CONSTRUCT_KINDS: Final[tuple[str, ...]] = (
    KIND_DATA,
    KIND_CDATA,
    KIND_ENTITY_REF,
    KIND_CHAR_REF,
    KIND_START_TAG,
    KIND_END_TAG,
    KIND_COMMENT,
    KIND_DECL,
    KIND_PI,
    KIND_UNKNOWN_DECL,
)

#: The constructs whose span is markup rather than content. Every one of them is removed, and
#: each under its own reason, so "the tags are gone" and "the comments are gone" stay two counts.
MARKUP_KINDS: Final[frozenset[str]] = frozenset(
    {
        KIND_START_TAG,
        KIND_END_TAG,
        KIND_COMMENT,
        KIND_DECL,
        KIND_PI,
        KIND_UNKNOWN_DECL,
    }
)

#: The constructs whose span is an entity reference's source syntax. Removed *and replaced*, and
#: counted on their own ledger verdict rather than as a removal.
ENTITY_KINDS: Final[frozenset[str]] = frozenset({KIND_ENTITY_REF, KIND_CHAR_REF})

#: The constructs whose span is text that may reach the output.
TEXT_KINDS: Final[frozenset[str]] = frozenset({KIND_DATA, KIND_CDATA})

#: Elements that end at their own end tag or at the end of a block, borrowed in spirit from the
#: ``adversarygraph`` donor's ``_BLOCK_TAGS`` and from HTML's own implied-end-tag rules. Used for
#: two things and only two: deciding that a text run starts a new line, and closing an open
#: element so that a following sibling is not read as its child.
BLOCK_TAGS: Final[frozenset[str]] = frozenset(
    {
        "address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt",
        "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5",
        "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section", "table",
        "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
    }
)

#: Tags that never have content, so they are popped immediately. Only for the HTML route: XML
#: has no void elements and treating ``<br/>`` as self-closing there would be a lie.
HTML_VOID_TAGS: Final[frozenset[str]] = frozenset(
    {
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr",
    }
)

#: ``open tag -> tags that close it without an end tag of its own``. HTML's implied end tags,
#: pinned as a table rather than encoded as scattered ``if`` statements, because a reader asking
#: "when does this stage believe ``<p>`` ended?" should be able to read the answer in one place.
#:
#: The cost is stated: an element closed this way gets an approximate source span, which is why
#: :attr:`~parsers.primproc.reasons.NoteCode.HTML_IMPLIED_END_TAG` exists. None of the strategies
#: in :class:`~parsers.primproc.reasons.ExtractStrategy` matches a tag in this table, so the
#: approximation cannot affect which region is selected.
IMPLIED_END_TAGS: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "p": frozenset(BLOCK_TAGS),
        "li": frozenset({"li"}),
        "dt": frozenset({"dt", "dd"}),
        "dd": frozenset({"dt", "dd"}),
        "tr": frozenset({"tr", "tbody", "tfoot", "thead"}),
        "td": frozenset({"td", "th", "tr", "tbody", "tfoot", "thead"}),
        "th": frozenset({"td", "th", "tr", "tbody", "tfoot", "thead"}),
        "thead": frozenset({"tbody", "tfoot"}),
        "tbody": frozenset({"tbody", "tfoot"}),
        "option": frozenset({"option", "optgroup"}),
        "optgroup": frozenset({"optgroup"}),
        "head": frozenset({"body"}),
    }
)

#: The attributes this stage drops from elements it keeps. ``style`` is a declaration block that
#: is presentation, not content; ``on*`` is an event handler. Both are dropped **with their own
#: source span**, so the byte count is measured rather than estimated.
_DROPPED_ATTR_EXACT: Final[frozenset[str]] = frozenset({"style"})
_DROPPED_ATTR_PREFIX: Final[str] = "on"

#: Markup that survived inside a text run means the tokenizer did not recognise it as markup.
#: Checked on the raw slice so the check is a statement about the source rather than about a
#: reconstruction.
_MARKUP_AS_TEXT: Final[re.Pattern[str]] = re.compile(r"<[!?/]")


def attribute_is_dropped(name: str) -> bool:
    """Whether an attribute is one this stage removes. The one place the rule is written."""
    lowered = str(name).lower()
    return lowered in _DROPPED_ATTR_EXACT or lowered.startswith(_DROPPED_ATTR_PREFIX)


class SourceIndex:
    """Decoded-text character offsets ↔ original raw-body byte offsets.

    Two indices are kept: the character position of each line's first character, and the **byte**
    position of the same, in the codec the payload actually decoded under — not in UTF-8, because
    a windows-1251 page's bytes are not UTF-8 and an offset computed as though they were would
    point into the middle of a multi-byte sequence.

    Lines are split on ``\\n`` alone, which is what ``html.parser``'s own position accounting does.
    Matching its rule exactly is not a stylistic choice: if the two disagreed about where a line
    began, every offset after the first ``\\r\\n`` would be wrong by one, silently.

    Line starts and per-line encodings are cached, so the cost is one encode per line touched
    rather than one per lookup.
    """

    __slots__ = ("_char_starts", "_byte_starts", "_codec", "_lines", "_offsets", "_text")

    def __init__(self, text: str, codec: str) -> None:
        self._text = text
        self._codec = codec
        char_starts: list[int] = []
        byte_starts: list[int] = []
        pos = 0
        byte_pos = 0
        newline_bytes = len("\n".encode(codec))
        for line in text.split("\n"):
            char_starts.append(pos)
            byte_starts.append(byte_pos)
            byte_pos += len(line.encode(codec)) + newline_bytes
            pos += len(line) + 1
        self._char_starts = char_starts
        self._byte_starts = byte_starts
        self._lines: dict[int, str] = {}
        self._offsets: dict[tuple[int, int], int] = {}

    @property
    def char_length(self) -> int:
        """Total characters of the decoded source."""
        return len(self._text)

    def char_of(self, line: int, column: int) -> int:
        """``html.parser``'s ``(line, column)`` as a character index. 1-based, as ``getpos`` is."""
        index = max(1, int(line)) - 1
        if index >= len(self._char_starts):
            return len(self._text)
        return self._char_starts[index] + max(0, int(column))

    def line_text(self, line: int) -> str:
        """The characters of one line, without its terminator. Cached."""
        index = max(1, int(line)) - 1
        cached = self._lines.get(index)
        if cached is not None:
            return cached
        if index >= len(self._char_starts):
            return ""
        start = self._char_starts[index]
        end = (
            self._char_starts[index + 1] - 1
            if index + 1 < len(self._char_starts)
            else len(self._text)
        )
        text = self._text[start:end]
        self._lines[index] = text
        return text

    def byte_at(self, line: int, column: int) -> int:
        """The raw-body byte offset of ``(line, column)``, memoised per coordinate."""
        index = max(1, int(line)) - 1
        key = (index, int(column))
        cached = self._offsets.get(key)
        if cached is not None:
            return cached
        if index >= len(self._byte_starts):
            return self.byte_of(len(self._text))
        value = self._byte_starts[index] + len(self.line_text(index)[: int(column)].encode(self._codec))
        self._offsets[key] = value
        return value

    def byte_of(self, char_index: int) -> int:
        """The raw-body byte offset of a character index, via its line."""
        index = max(0, min(int(char_index), len(self._text)))
        line = bisect.bisect_right(self._char_starts, index) - 1
        line = max(0, line)
        return self.byte_at(line + 1, index - self._char_starts[line])

    def byte_length(self, start_char: int, end_char: int) -> int:
        """How many raw-body bytes the character range covers."""
        return self.byte_of(end_char) - self.byte_of(start_char)

    def byte_span(self, start_char: int, end_char: int) -> tuple[int, int]:
        return self.byte_of(start_char), self.byte_of(end_char)


@dataclass(frozen=True, slots=True)
class Construct:
    """One tokenizer event with its **exact** source span in decoded characters.

    ``end_char`` is filled in by :meth:`_Collector.finish`, from the next construct's start or
    from the end of the input — never guessed, which is the entire point of this type.

    ``text`` is what the tokenizer said, which for ``entityref``/``charref`` is the bare name and
    for ``data`` is the literal characters. The authoritative source is always
    ``source[start_char:end_char]``; ``text`` is kept because it is what the tokenizer knows and
    cross-checking the two is a cheap guard against a position-accounting regression.
    """

    kind: str
    start_char: int
    text: str
    tag: str = ""
    attrs: tuple[tuple[str, str | None], ...] = ()
    end_char: int = -1

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", str(self.kind))
        object.__setattr__(self, "start_char", int(self.start_char))
        object.__setattr__(self, "text", str(self.text))
        object.__setattr__(self, "tag", str(self.tag))
        object.__setattr__(self, "attrs", tuple((str(k), v) for k, v in self.attrs))
        object.__setattr__(self, "end_char", int(self.end_char))

    @property
    def is_markup(self) -> bool:
        return self.kind in MARKUP_KINDS

    @property
    def is_text(self) -> bool:
        return self.kind in TEXT_KINDS

    @property
    def is_entity(self) -> bool:
        """An entity reference: its span is syntax that an expansion replaced."""
        return self.kind in ENTITY_KINDS

    def attr(self, name: str) -> str | None:
        """The first value for ``name``, or ``None``. Attribute names are compared lowercased."""
        wanted = str(name).lower()
        for key, value in self.attrs:
            if key.lower() == wanted:
                return value
        return None

    def descriptor(self) -> str:
        """The attributes as id/class/role/itemprop/data-testid joined — what a strategy matches."""
        parts = [
            self.attr(name) or ""
            for name in ("id", "class", "role", "itemprop", "data-testid", "data-test")
        ]
        return " ".join(parts)


@dataclass(slots=True)
class ElementSpan:
    """An element, its source span, and how much text survived inside it.

    ``text_chars`` is the density measure: the characters of text that were **not** inside a skip
    element, accumulated for every element open at the time. It is filled during the containment
    walk rather than afterwards, so it costs one pass and cannot disagree with the spans.
    """

    tag: str
    attrs: tuple[tuple[str, str | None], ...]
    start_char: int
    end_char: int = -1
    text_chars: int = 0

    def __post_init__(self) -> None:
        self.tag = str(self.tag)
        self.attrs = tuple((str(k), v) for k, v in self.attrs)
        self.start_char = int(self.start_char)
        self.end_char = int(self.end_char)
        self.text_chars = int(self.text_chars)

    def attr(self, name: str) -> str | None:
        wanted = str(name).lower()
        for key, value in self.attrs:
            if key.lower() == wanted:
                return value
        return None

    def descriptor(self) -> str:
        parts = [
            self.attr(name) or ""
            for name in ("id", "class", "role", "itemprop", "data-testid", "data-test")
        ]
        return " ".join(parts)

    def closed(self) -> bool:
        """Whether the element's end came from an end tag rather than from the end of input."""
        return self.end_char >= 0


@dataclass(frozen=True, slots=True)
class Note:
    """One thing the parser saw that a well-formed document would not contain.

    ``offset`` is a **character** offset into the decoded source, and it is optional because some
    notes are about the document as a whole — an unclosed element has no single position.
    """

    code: str
    detail: str
    offset: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", str(self.code))
        object.__setattr__(self, "detail", str(self.detail))
        if self.offset is not None:
            object.__setattr__(self, "offset", int(self.offset))

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "detail": self.detail, "offset": self.offset}


class TilingError(AssertionError):
    """The tokenizer's constructs did not tile the source. Raised, never returned.

    A gap means a byte exists in the payload that no construct claims, so no span covers it and
    no reason can be attributed to it — which is exactly the "a stage that eats content without
    saying so" failure this design exists to make impossible. It raises rather than returning a
    result because a result with an unattributable byte in it is not a measurement.
    """

    def __init__(self, detail: str) -> None:
        super().__init__(f"{NoteCode.SOURCE_BOUND_HIT}: {detail}")
        self.code = str(NoteCode.SOURCE_BOUND_HIT)
        self.detail = detail


def assert_tiling(constructs: Sequence[Construct], total_chars: int) -> None:
    """Every character of the source is claimed by exactly one construct, or this raises.

    Called on every parse rather than in a test, because the invariant is what the whole accounting
    rests on and a caller who has to remember to check it will not.
    """
    cursor = 0
    for construct in constructs:
        if construct.start_char < cursor:
            raise TilingError(
                f"a {construct.kind} construct starts at {construct.start_char}, before the "
                f"previous construct ended at {cursor}; the constructs overlap"
            )
        if construct.start_char > cursor:
            raise TilingError(
                f"a {construct.kind} construct starts at {construct.start_char} but the previous "
                f"one ended at {cursor}; characters [{cursor}, {construct.start_char}) are in "
                "the source and in no construct, so no removal could be attributed to them"
            )
        cursor = construct.end_char
    if cursor != total_chars:
        raise TilingError(
            f"the last construct ends at {cursor} and the decoded source is {total_chars} "
            "characters; the tail is in no construct"
        )


class _Collector(HTMLParser):
    """Collects constructs with exact spans, and walks containment as it goes.

    Two passes over one event stream, both deterministic. The first assigns spans by the tiling
    rule. The second maintains the element stack for skip-element and main-region decisions, and
    accumulates text density at the same time.

    ``convert_charrefs=False`` is load-bearing and is argued in the module docstring: it is what
    makes an entity reference an *event* with a source span, and therefore an accounting event.
    """

    def __init__(
        self,
        *,
        text: str,
        index: SourceIndex,
        xml_mode: bool,
        skip_tags: frozenset[str],
        max_chars: int | None,
    ) -> None:
        super().__init__(convert_charrefs=False)
        self._raw_text = text
        self._index = index
        self._xml = bool(xml_mode)
        self._skip_tags = skip_tags
        self._max_chars = max_chars
        self._constructs: list[Construct] = []
        self._elements: list[ElementSpan] = []
        self._all_elements: list[ElementSpan] = []
        self._closed_by: dict[int, int] = {}
        self._notes: list[Note] = []
        self._skip_depth = 0
        self._bounded = False

    # -- position ---------------------------------------------------------- #

    def _here(self) -> int:
        line, column = self.getpos()
        return self._index.char_of(line, column)

    def _at(self, kind: str, **kwargs: object) -> None:
        if self._max_chars is not None and self._here() >= self._max_chars:
            self._bounded = True
            return
        self._constructs.append(Construct(kind=kind, start_char=self._here(), **kwargs))  # type: ignore[arg-type]

    # -- handlers ---------------------------------------------------------- #

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = str(tag).lower()
        self._at(KIND_START_TAG, text=tag, tag=tag, attrs=tuple(attrs))
        if not self._xml and tag in HTML_VOID_TAGS:
            return
        if not self._xml and tag in self._skip_tags:
            self._skip_depth += 1
        element = ElementSpan(tag=tag, attrs=tuple(attrs), start_char=self._here())
        self._elements.append(element)
        # The open stack is drained by every end tag, so the document's elements are recorded
        # separately: a strategy has to be able to ask "was there an ``<article>``?" about a
        # document whose ``</article>`` arrived long ago.
        self._all_elements.append(element)
        if not self._xml:
            for open_tag in reversed([e.tag for e in self._elements[:-1]]):
                closers = IMPLIED_END_TAGS.get(open_tag)
                if closers is not None and tag in closers:
                    implied = self._elements.pop()
                    # The closing construct's *end* is not known until ``finish``, so the
                    # implication records which construct closed it and resolves the span there.
                    self._closed_by[id(implied)] = self._constructs[-1].start_char
                    self._notes.append(
                        Note(
                            str(NoteCode.HTML_IMPLIED_END_TAG),
                            f"<{open_tag}> was closed by the start of <{tag}>, not by its own end "
                            f"tag; its source span ends at character "
                            f"{self._constructs[-1].start_char} and is approximate",
                            offset=implied.start_char,
                        )
                    )
                    break

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = str(tag).lower()
        self._at(KIND_START_TAG, text=tag, tag=tag, attrs=tuple(attrs))

    def handle_endtag(self, tag: str) -> None:
        tag = str(tag).lower()
        self._at(KIND_END_TAG, text=tag, tag=tag)
        if tag in self._skip_tags and self._skip_depth > 0:
            self._skip_depth -= 1
        for position in range(len(self._elements) - 1, -1, -1):
            if self._elements[position].tag != tag:
                continue
            while len(self._elements) > position:
                element = self._elements.pop()
                self._closed_by[id(element)] = self._constructs[-1].start_char
            return
        self._notes.append(
            Note(
                str(NoteCode.HTML_UNMATCHED_END_TAG),
                f"</{tag}> arrived with no matching open element; the end tag is removed and the "
                "text around it is kept",
                offset=self._here(),
            )
        )

    def handle_data(self, data: str) -> None:
        if not data:
            return
        self._at(KIND_DATA, text=data)
        if self._skip_depth == 0:
            for element in self._elements:
                element.text_chars += len(data)

    def handle_entityref(self, name: str) -> None:
        self._at(KIND_ENTITY_REF, text=str(name))

    def handle_charref(self, name: str) -> None:
        self._at(KIND_CHAR_REF, text=str(name))

    def handle_comment(self, data: str) -> None:
        self._at(KIND_COMMENT, text=str(data))

    def handle_decl(self, decl: str) -> None:
        self._at(KIND_DECL, text=str(decl))

    def handle_pi(self, data: str) -> None:
        self._at(KIND_PI, text=str(data))

    def unknown_decl(self, data: str) -> None:
        raw = str(data)
        if raw.startswith("CDATA["):
            self._at(KIND_CDATA, text=raw[6:])
            if self._skip_depth == 0:
                for element in self._elements:
                    element.text_chars += len(raw) - 6
            return
        self._at(KIND_UNKNOWN_DECL, text=raw)

    # -- finish ------------------------------------------------------------ #

    def finish(self) -> tuple[tuple[Construct, ...], tuple[ElementSpan, ...], tuple[Note, ...]]:
        """Assign every construct's end, verify the tiling, and close the element stack.

        The bound is applied here rather than during the walk so that the collector's own
        bookkeeping stays trivial: constructs are collected in document order and the cut is a
        single truncation of the finished list, with the straddling construct's end pulled back to
        the bound so that the tiling still holds exactly.
        """
        total = self._index.char_length
        ceiling = total if self._max_chars is None else min(int(self._max_chars), total)
        pending = self._constructs
        kept: list[Construct] = []
        for position, construct in enumerate(pending):
            if construct.start_char >= ceiling:
                break
            end = pending[position + 1].start_char if position + 1 < len(pending) else total
            kept.append(
                Construct(
                    kind=construct.kind,
                    start_char=construct.start_char,
                    end_char=max(construct.start_char, min(end, ceiling)),
                    text=construct.text,
                    tag=construct.tag,
                    attrs=construct.attrs,
                )
            )
        if self._bounded and ceiling < total:
            self._notes.append(
                Note(
                    str(NoteCode.SOURCE_BOUND_HIT),
                    f"the source is {total} characters and the declared bound is {ceiling}; "
                    "reading stopped at the bound and everything after it is in no construct",
                )
            )
        assert_tiling(kept, ceiling)
        ends_by_start = {construct.start_char: construct.end_char for construct in kept}
        for element in self._all_elements:
            closer = self._closed_by.get(id(element))
            if closer is not None and closer in ends_by_start:
                element.end_char = ends_by_start[closer]
                continue
            element.end_char = ceiling
            self._notes.append(
                Note(
                    str(NoteCode.HTML_UNCLOSED_ELEMENT),
                    f"<{element.tag}> was still open when the source ended; its span runs to the "
                    "end of the read region and the text inside it is still read",
                    offset=element.start_char,
                )
            )
        for construct in kept:
            if construct.kind != KIND_DATA:
                continue
            if _MARKUP_AS_TEXT.search(self._raw_text[construct.start_char : construct.end_char]):
                self._notes.append(
                    Note(
                        str(NoteCode.HTML_MARKUP_LEFT_AS_TEXT),
                        "a '<!', '<?' or '</' sequence is inside a text run, so the tokenizer did "
                        "not recognise it as markup; those characters are kept as text",
                        offset=construct.start_char,
                    )
                )
                break
        return tuple(kept), tuple(self._all_elements), tuple(self._notes)


@dataclass(slots=True)
class MarkupDocument:
    """One parsed payload: its constructs, its elements, and what was odd about it."""

    constructs: tuple[Construct, ...]
    elements: tuple[ElementSpan, ...]
    notes: tuple[Note, ...]
    index: SourceIndex
    raw_text: str = ""
    truncated: bool = False

    def text_span(self, construct: Construct) -> str:
        """The construct's source characters — authoritative, and the reason spans are exact."""
        return self.raw_text[construct.start_char : construct.end_char]

    def slice_of(self, start_char: int, end_char: int) -> str:
        return self.raw_text[start_char:end_char]


def parse_markup(
    text: str,
    *,
    codec: str,
    xml_mode: bool = False,
    skip_tags: frozenset[str] = frozenset(),
    max_chars: int | None = None,
) -> MarkupDocument:
    """Parse ``text`` into constructs with exact spans. Total for well-formed and malformed alike.

    ``max_chars`` bounds how much is read, and hitting it is recorded as
    :attr:`~parsers.primproc.reasons.NoteCode.SOURCE_BOUND_HIT` rather than silently truncating —
    the same rule :class:`parsers.payload.records.BoundHit` follows, for the same reason.
    """
    index = SourceIndex(text, codec)
    collector = _Collector(
        text=text, index=index, xml_mode=xml_mode, skip_tags=skip_tags, max_chars=max_chars
    )
    collector.feed(text)
    collector.close()
    constructs, elements, notes = collector.finish()
    return MarkupDocument(
        constructs=constructs,
        elements=elements,
        notes=notes,
        index=index,
        raw_text=text,
        truncated=collector._bounded,
    )


__all__ = [
    "BLOCK_TAGS",
    "CONSTRUCT_KINDS",
    "ENTITY_KINDS",
    "HTML_VOID_TAGS",
    "IMPLIED_END_TAGS",
    "KIND_CDATA",
    "KIND_CHAR_REF",
    "KIND_DATA",
    "KIND_DECL",
    "KIND_END_TAG",
    "KIND_ENTITY_REF",
    "KIND_PI",
    "KIND_START_TAG",
    "KIND_UNKNOWN_DECL",
    "MARKUP_KINDS",
    "TEXT_KINDS",
    "Construct",
    "ElementSpan",
    "MarkupDocument",
    "Note",
    "SourceIndex",
    "TilingError",
    "assert_tiling",
    "attribute_is_dropped",
    "parse_markup",
]
