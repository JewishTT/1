"""``EvidenceSpanRef`` -- the typed union that makes three meanings of one integer impossible.

Spec 030 contract 02 / FR-004, FR-005, FR-006 / tasks T028, T034.

**The defect this exists to prevent is measured, not hypothetical.** ``Segment.offset`` meant
**byte offset** in one parser, **segment index** in another and was always ``0`` in a third;
all three were then summed into one field at ``apps/interpretation/extractors/lane.py:82-86``.
Downstream, ``document_adapter.py:271-300`` consumed the span to mint an id and threw it away.
The consequence is exact: a span that grounds a mention was destroyed after use, and the one
field that survived meant three different things.

So this module refuses three things, structurally rather than by convention:

1. **A bare integer is not a span.** R1: a span is a typed union. ``selector=82`` raises
   :class:`SpanContractError` rather than being read as "an offset somewhere". There is no
   ``__int__``, no ``__index__`` and no coercion path, so a caller cannot pass one by accident
   without the failure landing on the line that did it.
2. **A selector carries its semantics version, and it has to be the right one.** R2: two spans
   whose ``selector_semantics_version`` differ MUST NOT be compared, summed or converted.
   :meth:`EvidenceSpanRef.require_comparable` raises :class:`SpanSemanticsMismatch` and names
   both versions. There is no conversion table anywhere in this file, because a best-effort
   merge of two unknown conventions manufactures wrong provenance.
3. **Zero is not "no position".** Every selector validates its own geometry, so an unset
   offset cannot be stored as ``0`` and later read as position zero.

**Relationship to ``OffsetSemantics`` in ``apps/interpretation/parsers/registry.py``.** That
class is the *runtime* owner of the offset-unit vocabulary and this module does not redeclare
it. ``char_span.units`` is validated against :data:`DOCUMENT_ABSOLUTE_UNITS`, which is exactly
the ``OffsetSemantics.REBASABLE`` subset -- ``document_char`` and ``document_byte`` -- and
which refuses ``unset`` and ``segment_index`` here. :func:`offset_vocabulary_agrees_with_runtime`
is the drift check that keeps the two from separating silently; it is lazy because ``shared`` is
the substrate layer and must not import upward into ``interpretation`` at module scope.

**R8: the blob is the identity, the span is a pointer.** :meth:`EvidenceSpanRef.check_blob`
compares the declared digest against the stored bytes and reports ``stale`` with both recorded.
It does not raise and it does not silently prefer the span.
"""

from __future__ import annotations

import dataclasses
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from contracts.canonical import digest_of

__all__ = [
    "CoordinateSystem",
    "CharSpan",
    "EvidenceSpanRef",
    "GeometrySpan",
    "JsonPathSpan",
    "PageBoxSpan",
    "SelectorKind",
    "SelectorSemanticsVersion",
    "SourceLocator",
    "SourceLocatorSpan",
    "SpanContractError",
    "SpanSelector",
    "SpanSemanticsMismatch",
    "StoredDocument",
    "TableCellSpan",
    "TimeRangeSpan",
    "WarcRecordSpan",
    "DOCUMENT_ABSOLUTE_UNITS",
    "ResolvedRegion",
    "offset_vocabulary_agrees_with_runtime",
]


class SpanContractError(ValueError):
    """A span does not satisfy the contract, and storing it would make it look like it does.

    Raised rather than defaulted. The default reading of a malformed span is "position zero"
    or "no position", and those two are exactly what contract 02 forbids confusing.
    """


class SpanSemanticsMismatch(SpanContractError):
    """Two spans name different producer conventions and cannot be compared.

    The refusal carries both versions, because "these are not comparable" is only actionable
    if the caller is told which two. It is never resolved by converting either one (R2).
    """


class SelectorKind(StrEnum):
    """The eight ways a span may address source bytes. The discriminator of the union.

    Closed, because a new way of addressing bytes is a new *contract*, not a new integer. An
    unrecognised kind is a producer that has not opted in, and it gets no span at all.
    """

    CHAR_SPAN = "char_span"
    PAGE_BOX = "page_box"
    TABLE_CELL = "table_cell"
    JSON_PATH = "json_path"
    TIME_RANGE = "time_range"
    GEOMETRY = "geometry"
    WARC_RECORD = "warc_record"
    SOURCE_LOCATOR = "source_locator"


#: Token set for what a positional selector's integers count. Same vocabulary as
#: ``OffsetSemantics`` in ``apps/interpretation/parsers/registry.py`` -- deliberately not a
#: second enum: one integer must have one unit and one declaration of it.
#:
#: Only the two document-absolute units appear. ``unset`` is excluded because a contract-02
#: span is by construction a position in a stored blob, and a producer with no position does
#: not emit a span (it emits no span, and the consumer renders the result ungrounded).
#: ``segment_index`` and ``segment_char`` are excluded because they address a producer's own
#: segment list, which nothing in the blob preserves.
DOCUMENT_ABSOLUTE_UNITS: frozenset[str] = frozenset({"document_char", "document_byte"})


def offset_vocabulary_agrees_with_runtime() -> bool | None:
    """Whether :data:`DOCUMENT_ABSOLUTE_UNITS` still matches the interpretation layer's.

    ``True`` when ``parsers.registry`` is importable and agrees, ``None`` when it is not on the
    path -- which is the normal case for the substrate's own test scope, because ``shared`` is
    below ``interpretation`` in the layer order and may not import upward. ``False`` is the
    answer that matters: the vocabulary has forked and one of the two is now lying.
    """
    try:
        from parsers.registry import OffsetSemantics
    except ImportError:
        return None
    return set(DOCUMENT_ABSOLUTE_UNITS) == set(OffsetSemantics.REBASABLE)


class CoordinateSystem(StrEnum):
    """R3: a coordinate is meaningless without the frame it was measured in.

    Closed on purpose. Adding a frame is a contract change, not a string a caller may invent
    at the call site -- an unrecognised frame means the numbers are being compared to numbers
    that were never in the same space.
    """

    PDF_POINTS = "pdf_points"
    PIXEL_TOP_LEFT = "pixel_top_left"
    PIXEL_TOP_RIGHT = "pixel_top_right"
    GEO_WGS84 = "geo_wgs84"
    SVG_USER_UNITS = "svg_user_units"
    IMAGE_PIXELS = "image_pixels"


@dataclass(frozen=True, slots=True)
class SelectorSemanticsVersion:
    """The producer convention a span was written under, as ``<kind>/<version>``.

    Parsing it into ``(kind, version)`` rather than keeping it as a string is what makes R2
    mechanical: the kind is checked against the selector actually present at construction, and
    two spans are comparable only when their parsed versions are equal. A bare ``"1"`` or
    ``"v2"`` is refused, because a version that does not name its kind is exactly the thing
    that let three conventions share one field.
    """

    kind: SelectorKind
    version: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", SelectorKind(self.kind))
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version < 1:
            raise SpanContractError(
                f"selector semantics version must be a positive integer, got {self.version!r}; "
                "0 is not a version, it is the absence of one"
            )

    @classmethod
    def parse(cls, raw: str) -> SelectorSemanticsVersion:
        """Read ``"<kind>/<version>"``, refusing anything that does not name a known kind."""
        if not isinstance(raw, str) or not raw.strip():
            raise SpanContractError(
                "selector_semantics_version is mandatory (contract 02 R2): without it a span "
                "is an integer with a shape, which is the defect this type replaces"
            )
        text = raw.strip()
        kind_text, separator, version_text = text.rpartition("/")
        if not separator or not kind_text or not version_text:
            raise SpanContractError(
                f"selector_semantics_version {raw!r} is not '<kind>/<version>'; a version that "
                "does not name its producer convention cannot make two conventions comparable"
            )
        try:
            kind = SelectorKind(kind_text.strip())
        except ValueError as exc:
            raise SpanContractError(
                f"selector_semantics_version names unknown selector kind {kind_text!r}; known "
                f"kinds are {', '.join(sorted(k.value for k in SelectorKind))}"
            ) from exc
        try:
            version = int(version_text.strip())
        except ValueError as exc:
            raise SpanContractError(
                f"selector_semantics_version {raw!r} has a non-integer version"
            ) from exc
        return cls(kind=kind, version=version)

    def __str__(self) -> str:
        return f"{self.kind.value}/{self.version}"

    def is_comparable_with(self, other: SelectorSemanticsVersion) -> bool:
        return self.kind is other.kind and self.version == other.version


@dataclass(frozen=True, slots=True)
class SourceLocator:
    """How to re-fetch the source. Required even when the bytes are already stored.

    R-fetch is a separate act from R-read: a span over a blob that has aged out of the store
    is still addressable if the locator survives, and a span with no locator is a span that
    dies with its blob.
    """

    uri: str
    fragment: str | None = None

    def __post_init__(self) -> None:
        uri = str(self.uri).strip()
        if not uri:
            raise SpanContractError(
                "source_locator.uri is required; a span that cannot be re-fetched cannot be "
                "re-grounded when the blob ages out (contract 02)"
            )
        object.__setattr__(self, "uri", uri)
        if self.fragment is not None:
            object.__setattr__(self, "fragment", str(self.fragment))

    def as_dict(self) -> dict[str, Any]:
        return {"uri": self.uri, "fragment": self.fragment}


@dataclass(frozen=True, slots=True)
class ResolvedRegion:
    """What a span resolved to, and how far that resolution can be trusted."""

    value: Any
    raw: bytes = b""
    is_pointer_only: bool = False
    detail: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StoredDocument:
    """The stored raw bytes, plus the indexes a structured selector needs to address into them.

    ``index`` is what a *producer* supplies alongside its span -- the page-region index a PDF
    layout parser built, the table model a spreadsheet reader built. It is not derived here:
    reconstructing a table from raw bytes is the producer's job and pretending otherwise is how
    a span comes to point at a cell the source never had.
    """

    data: bytes
    encoding: str = "utf-8"
    index: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", bytes(self.data))
        encoding = str(self.encoding).strip()
        if not encoding:
            raise SpanContractError("a stored document must declare the encoding its spans use")
        object.__setattr__(self, "encoding", encoding)
        object.__setattr__(self, "index", dict(self.index))

    @property
    def text(self) -> str:
        return self.data.decode(self.encoding)

    def blob_digest(self) -> str:
        """The content address of the bytes. The identity; a span is only a pointer (R8)."""
        return digest_of(self.data)

    def require(self, key: str) -> Any:
        if key not in self.index:
            raise SpanContractError(
                f"the stored document carries no {key!r} index, so no span of that kind can "
                "resolve against it; the producer's index is required, not reconstructed"
            )
        return self.index[key]


# ---------------------------------------------------------------------------
# The eight selector variants. Each validates its own geometry at construction,
# so an unset coordinate cannot be stored as 0 and read back as position 0.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CharSpan:
    """A character range in the decoded text, with the unit and encoding it was measured in.

    ``units`` is required for the reason ``OffsetSemantics`` exists: ``start``/``end`` over the
    same bytes are different numbers under ``document_char`` and ``document_byte``, and a
    producer that omits the unit has produced an integer of unknown provenance.
    """

    start: int
    end: int
    encoding: str = "utf-8"
    units: str = "document_char"

    kind: SelectorKind = field(default=SelectorKind.CHAR_SPAN, init=False, repr=False)

    def __post_init__(self) -> None:
        for name in ("start", "end"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise SpanContractError(
                    f"char_span.{name} must be an int, got {value!r} of type "
                    f"{type(value).__name__}; a float or a string offset is the conflation this "
                    "type exists to prevent"
                )
            if value < 0:
                raise SpanContractError(
                    f"char_span.{name} is {value}; -1 is 'not found', not a position, and "
                    "contract 02 forbids storing it as one (0 is a real position)"
                )
        if self.end <= self.start:
            raise SpanContractError(
                f"char_span.end ({self.end}) must exceed char_span.start ({self.start}); an "
                "empty or backwards range addresses nothing"
            )
        encoding = str(self.encoding).strip()
        if not encoding:
            raise SpanContractError("char_span.encoding is required; the round-trip contract "
                                    "is byte-identical *after the declared encoding*")
        object.__setattr__(self, "encoding", encoding)
        units = str(self.units).strip()
        if units not in DOCUMENT_ABSOLUTE_UNITS:
            raise SpanContractError(
                f"char_span.units {units!r} is not a document-absolute unit; accepted units are "
                f"{sorted(DOCUMENT_ABSOLUTE_UNITS)}. 'unset' means the producer never computed a "
                "position and 'segment_index' means it is an index into the producer's own "
                "list - neither addresses a stored blob (contract 02 R2)"
            )
        object.__setattr__(self, "units", units)

    def resolve(self, document: StoredDocument) -> ResolvedRegion:
        """Yield the exact substring that produced the derived text, byte-identical.

        No normalisation of any kind is applied here (R6): transliteration and Unicode
        normalisation produce *additional* candidate forms with their own lineage, and a
        normalised span written back over this one would destroy the byte-level grounding.
        """
        text = document.text
        if self.end > len(text):
            raise SpanContractError(
                f"char_span ({self.start}, {self.end}) runs past the end of a "
                f"{len(text)}-character document; mark it ungrounded, do not truncate"
            )
        fragment = text[self.start : self.end]
        if self.units == "document_byte":
            raw = document.data[self.start : self.end]
        else:
            raw = fragment.encode(self.encoding)
        return ResolvedRegion(
            value=fragment,
            raw=raw,
            detail={"units": self.units, "encoding": self.encoding},
        )


@dataclass(frozen=True, slots=True)
class PageBoxSpan:
    """A rectangle on a numbered page. R3: the frame is mandatory.

    The box is ``[x0, y0, x1, y1]`` with ``x0 < x1`` and ``y0 < y1``. A degenerate or inverted
    box is refused: some renderers emit one, and accepting it would store a region of zero
    area that resolves to nothing while still looking like an address.
    """

    page: int
    box: tuple[float, float, float, float]
    coordinate_system: CoordinateSystem

    kind: SelectorKind = field(default=SelectorKind.PAGE_BOX, init=False, repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.page, bool) or not isinstance(self.page, int) or self.page < 1:
            raise SpanContractError(
                f"page_box.page must be a 1-based int, got {self.page!r}; page 0 is not a page "
                "and a float page is not addressable"
            )
        box = self.box
        if not isinstance(box, tuple | list) or len(box) != 4:
            raise SpanContractError(
                f"page_box.box must be exactly four numbers [x0, y0, x1, y1], got {box!r}"
            )
        try:
            coords = tuple(float(value) for value in box)
        except (TypeError, ValueError) as exc:
            raise SpanContractError(f"page_box.box holds a non-numeric value: {box!r}") from exc
        if not all(math.isfinite(value) for value in coords):
            raise SpanContractError(
                f"page_box.box {box!r} holds a non-finite coordinate; NaN and Infinity are not "
                "positions"
            )
        x0, y0, x1, y1 = coords
        if x0 >= x1 or y0 >= y1:
            raise SpanContractError(
                f"page_box.box {box!r} is empty or inverted; a box needs x0 < x1 and y0 < y1 to "
                "address a region"
            )
        object.__setattr__(self, "box", coords)
        if not self.coordinate_system:
            raise SpanContractError(
                "page_box.coordinate_system is required (R3); a coordinate without its frame is "
                "not a location"
            )
        object.__setattr__(self, "coordinate_system", CoordinateSystem(self.coordinate_system))

    def area(self) -> float:
        x0, y0, x1, y1 = self.box
        return (x1 - x0) * (y1 - y0)

    def overlaps(self, other: PageBoxSpan) -> float:
        """Fraction of *this* box covered by ``other``. Zero means they do not meet.

        Requires the same frame. Comparing across coordinate systems is refused rather than
        approximated, because an approximate overlap of two different spaces is a fabricated
        overlap.
        """
        if self.coordinate_system is not other.coordinate_system:
            raise SpanSemanticsMismatch(
                f"page_box boxes in {self.coordinate_system.value} and "
                f"{other.coordinate_system.value} are in different frames; there is no "
                "conversion, so there is no overlap to report (R3)"
            )
        ax0, ay0, ax1, ay1 = self.box
        bx0, by0, bx1, by1 = other.box
        dx = max(0.0, min(ax1, bx1) - max(ax0, bx0))
        dy = max(0.0, min(ay1, by1) - max(ay0, by0))
        covered = dx * dy
        return covered / self.area() if self.area() > 0.0 else 0.0

    def resolve(self, document: StoredDocument) -> ResolvedRegion:
        """Look the box up in the producer's page-region index.

        The index is supplied, never reconstructed: turning raw PDF bytes back into page
        boxes is the producer's work, and a resolver that guessed at it would report a region
        the source does not contain.
        """
        pages = document.require("pages")
        candidates = pages.get(self.page)
        if not candidates:
            raise SpanContractError(
                f"page_box names page {self.page}, which the producer's index does not contain"
            )
        best: ResolvedRegion | None = None
        best_overlap = 0.0
        for box, payload in candidates:
            other = PageBoxSpan(
                page=self.page,
                box=tuple(box),
                coordinate_system=self.coordinate_system,
            )
            overlap = self.overlaps(other)
            if overlap > best_overlap:
                best_overlap = overlap
                best = ResolvedRegion(
                    value=payload.decode(document.encoding, errors="strict")
                    if isinstance(payload, bytes | bytearray)
                    else str(payload),
                    raw=bytes(payload) if isinstance(payload, bytes | bytearray) else b"",
                    detail={
                        "page": self.page,
                        "coordinate_system": self.coordinate_system.value,
                        "overlap": round(best_overlap, 6),
                    },
                )
        if best is None or best_overlap <= 0.0:
            raise SpanContractError(
                f"page_box {list(self.box)} on page {self.page} does not meet any region the "
                "producer indexed; mark the span ungrounded rather than dropping it"
            )
        return best


@dataclass(frozen=True, slots=True)
class TableCellSpan:
    """One cell, addressed by table, row, column **and** its header path.

    ``header_path`` is required, and the requirement is the interesting part: a bare
    ``(row, column)`` stops addressing the right cell the moment the table is filtered, and
    filtering a table is routine. A span that resolves only under one incidental filter is not
    a stable address.
    """

    table_ref: str
    row: int
    column: int
    header_path: tuple[str, ...]

    kind: SelectorKind = field(default=SelectorKind.TABLE_CELL, init=False, repr=False)

    def __post_init__(self) -> None:
        if not str(self.table_ref).strip():
            raise SpanContractError("table_cell.table_ref is required")
        object.__setattr__(self, "table_ref", str(self.table_ref).strip())
        for name in ("row", "column"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise SpanContractError(
                    f"table_cell.{name} must be a non-negative 0-based int, got {value!r}"
                )
        path = tuple(str(part) for part in self.header_path)
        if not path or not all(part.strip() for part in path):
            raise SpanContractError(
                "table_cell.header_path is required and must be non-empty; (row, column) alone "
                "addresses nothing once the table is filtered, and filtering is routine"
            )
        object.__setattr__(self, "header_path", path)

    def resolve(self, document: StoredDocument) -> ResolvedRegion:
        tables = document.require("tables")
        table = tables.get(self.table_ref)
        if table is None:
            raise SpanContractError(
                f"table_cell names table {self.table_ref!r}, which the producer's index does not "
                "contain"
            )
        header_index: dict[tuple[str, ...], int] = {
            tuple(part): index for index, part in enumerate(table.get("headers", ()))
        }
        declared = header_index.get(self.header_path)
        if declared is None:
            raise SpanContractError(
                f"table_cell.header_path {list(self.header_path)} is not a column path of "
                f"{self.table_ref!r}; a cell span whose declared path does not exist resolves "
                "to a neighbouring column, which is the filter-dependent address contract 02 "
                "forbids"
            )
        if declared != self.column:
            raise SpanSemanticsMismatch(
                f"table_cell declares column {self.column} but its header_path "
                f"{list(self.header_path)} is column {declared}; refusing to pick one (R2)"
            )
        rows = table.get("rows", ())
        if not 0 <= self.row < len(rows):
            raise SpanContractError(
                f"table_cell.row {self.row} is outside the {len(rows)} rows of {self.table_ref!r}"
            )
        cells = rows[self.row]
        if not 0 <= declared < len(cells):
            raise SpanContractError(
                f"table_cell.column {declared} is outside the {len(cells)} columns of row "
                f"{self.row}"
            )
        cell = cells[declared]
        return ResolvedRegion(
            value=str(cell),
            raw=str(cell).encode(document.encoding),
            detail={
                "table_ref": self.table_ref,
                "row": self.row,
                "column": declared,
                "header_path": list(self.header_path),
            },
        )


@dataclass(frozen=True, slots=True)
class JsonPathSpan:
    """An RFC 6901 JSON Pointer into the stored structure.

    Pointer syntax rather than a dotted path because it is the only one that addresses array
    indices unambiguously and survives a key containing a dot.
    """

    pointer: str

    kind: SelectorKind = field(default=SelectorKind.JSON_PATH, init=False, repr=False)

    def __post_init__(self) -> None:
        pointer = self.pointer
        if not isinstance(pointer, str):
            raise SpanContractError(
                f"json_path.pointer must be a str, got {type(pointer).__name__}"
            )
        if pointer == "":
            # Legal RFC 6901: the whole document. Explicit rather than accidental.
            object.__setattr__(self, "pointer", pointer)
            return
        if not pointer.startswith("/"):
            raise SpanContractError(
                f"json_path.pointer {pointer!r} must be an RFC 6901 pointer: start with '/' or "
                "be the empty pointer naming the whole document"
            )
        if pointer.endswith("/"):
            raise SpanContractError(
                f"json_path.pointer {pointer!r} ends with '/', which names an array's '-' key "
                "rather than an element"
            )

    def tokens(self) -> tuple[str, ...]:
        return tuple(
            token.replace("~1", "/").replace("~0", "~") for token in self.pointer.split("/")[1:]
        )

    def resolve(self, document: StoredDocument) -> ResolvedRegion:
        root = document.require("json")
        current: Any = root
        walked: list[str] = []
        for token in self.tokens():
            walked.append(token)
            if isinstance(current, Mapping):
                if token not in current:
                    raise SpanContractError(
                        f"json_path.pointer {self.pointer!r} does not resolve: no key {token!r} "
                        f"at {'/'.join(walked)}"
                    )
                current = current[token]
            elif isinstance(current, list):
                if not token.isdigit() or int(token) >= len(current):
                    raise SpanContractError(
                        f"json_path.pointer {self.pointer!r} does not resolve: {token!r} is not "
                        f"an element index of a {len(current)}-element array"
                    )
                current = current[int(token)]
            else:
                raise SpanContractError(
                    f"json_path.pointer {self.pointer!r} does not resolve: {token!r} is applied "
                    f"to a {type(current).__name__}"
                )
        return ResolvedRegion(
            value=current,
            raw=json.dumps(current, ensure_ascii=False, sort_keys=True).encode(document.encoding),
            detail={"pointer": self.pointer},
        )


@dataclass(frozen=True, slots=True)
class TimeRangeSpan:
    """A half-open interval on a source timeline, optionally pinned to a track and a frame."""

    start: float
    end: float
    track: str | None = None
    frame: int | None = None

    kind: SelectorKind = field(default=SelectorKind.TIME_RANGE, init=False, repr=False)

    def __post_init__(self) -> None:
        for name in ("start", "end"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise SpanContractError(
                    f"time_range.{name} must be a number of seconds, got {value!r}"
                )
            if not math.isfinite(float(value)):
                raise SpanContractError(f"time_range.{name} is {value!r}; not a finite instant")
        if float(self.end) <= float(self.start):
            raise SpanContractError(
                f"time_range.end ({self.end}) must exceed time_range.start ({self.start}); a "
                "half-open interval of zero length addresses no sample"
            )
        if self.frame is not None and (
            isinstance(self.frame, bool) or not isinstance(self.frame, int) or self.frame < 0
        ):
            raise SpanContractError(
                f"time_range.frame must be a non-negative int, got {self.frame!r}"
            )
        if self.track is not None:
            track = str(self.track).strip()
            if not track:
                raise SpanContractError("time_range.track, if given, must not be blank")
            object.__setattr__(self, "track", track)

    def overlaps(self, other: TimeRangeSpan) -> bool:
        """Whether two half-open intervals on the **same track** share an instant.

        A different track is a different timeline, so overlap across tracks is False rather
        than an error: two audio tracks running at the same wall-clock second are not the same
        evidence, and merging them would be the conflation contract 02 forbids.
        """
        if self.track != other.track:
            return False
        return float(self.start) < other.end and float(other.start) < self.end

    def resolve(self, document: StoredDocument) -> ResolvedRegion:
        """Find the overlapping segments on the requested track.

        ``track=None`` means "the single track in this document". A document with more than one
        track and no track named is ambiguous, and an ambiguous span resolves to nothing on
        purpose -- guessing which track was meant is the same defect as guessing an offset.
        """
        segments = document.require("time_ranges")
        matched = [
            segment
            for segment in segments
            if self.track in (None, segment.get("track"))
            and _interval_overlaps(
                self, float(segment["start"]), float(segment["end"]), segment.get("track")
            )
        ]
        if not matched:
            raise SpanContractError(
                f"time_range ({self.start}, {self.end}) on track {self.track!r} matches no "
                "segment the producer indexed"
            )
        matched.sort(
            key=lambda s: (float(s["start"]), str(s.get("track") or ""), int(s.get("frame") or 0))
        )
        text = "".join(str(segment.get("text", "")) for segment in matched)
        return ResolvedRegion(
            value=text,
            raw=text.encode(document.encoding),
            detail={
                "track": self.track,
                "matched": [
                    {
                        "start": segment["start"],
                        "end": segment["end"],
                        "frame": segment.get("frame"),
                    }
                    for segment in matched
                ],
            },
        )


def _interval_overlaps(span: TimeRangeSpan, start: float, end: float, track: str | None) -> bool:
    """Overlap test against a producer's raw segment record, not a typed span."""
    if span.track is not None and span.track != track:
        return False
    return float(span.start) < end and start < float(span.end)


@dataclass(frozen=True, slots=True)
class GeometrySpan:
    """A geometry identified by the feature it belongs to.

    R3's second half: where a coordinate was produced by a transform from source data, the
    span references the **original** representation. So both refs are required -- dropping
    ``feature_ref`` would leave a geometry whose relationship to the observation is unknown,
    and dropping ``geometry_ref`` would leave a feature with no addressable shape.
    """

    feature_ref: str
    geometry_ref: str

    kind: SelectorKind = field(default=SelectorKind.GEOMETRY, init=False, repr=False)

    def __post_init__(self) -> None:
        for name in ("feature_ref", "geometry_ref"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise SpanContractError(
                    f"geometry.{name} is required; a geometry without the feature it belongs to "
                    "cannot be shown against its observation (R3)"
                )
            object.__setattr__(self, name, value)

    def resolve(self, document: StoredDocument) -> ResolvedRegion:
        geometries = document.require("geometries")
        geometry = geometries.get(self.geometry_ref)
        if geometry is None:
            raise SpanContractError(
                f"geometry.geometry_ref {self.geometry_ref!r} is not in the producer's index"
            )
        owner = geometry.get("feature_ref")
        if owner != self.feature_ref:
            raise SpanSemanticsMismatch(
                f"geometry {self.geometry_ref!r} belongs to feature {owner!r}, not "
                f"{self.feature_ref!r}; refusing to reattribute it to the feature the caller "
                "asked for"
            )
        return ResolvedRegion(
            value=geometry.get("payload", geometry),
            detail={"feature_ref": self.feature_ref, "geometry_ref": self.geometry_ref},
        )


@dataclass(frozen=True, slots=True)
class WarcRecordSpan:
    """A record inside a WARC, addressed by byte offset **and** the record's own digest.

    The digest is what makes this safe. An offset into a container that has been rewritten --
    re-gzipped, re-chunked, concatenated in a different order -- points at a different record,
    and nothing about the offset would say so. The digest is the identity (R8); the offset is
    the fast path.
    """

    record_offset: int
    warc_digest: str
    record_length: int | None = None

    kind: SelectorKind = field(default=SelectorKind.WARC_RECORD, init=False, repr=False)

    def __post_init__(self) -> None:
        for name in ("record_offset", "record_length"):
            value = getattr(self, name)
            if value is None and name == "record_length":
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise SpanContractError(
                    f"warc_record.{name} must be a non-negative int, got {value!r}"
                )
        if not str(self.warc_digest).strip():
            raise SpanContractError(
                "warc_record.warc_digest is required; an offset into a rewritten container "
                "addresses a different record and nothing about the offset would say so (R8)"
            )
        object.__setattr__(self, "warc_digest", str(self.warc_digest).strip())

    def resolve(self, document: StoredDocument) -> ResolvedRegion:
        records = document.require("warc")
        record = records.get(self.warc_digest)
        if record is None:
            raise SpanContractError(
                f"warc_record names digest {self.warc_digest!r}, which this container does not "
                "hold; the container has been rewritten since the span was written"
            )
        offset = int(record["offset"])
        if offset != self.record_offset:
            raise SpanSemanticsMismatch(
                f"warc_record offset {self.record_offset} no longer addresses record "
                f"{self.warc_digest!r}, which now starts at {offset}; refusing to read whatever "
                "is at the old offset (R8: the blob wins)"
            )
        length = int(record["length"]) if self.record_length is None else self.record_length
        raw = document.data[offset : offset + length]
        if len(raw) != length:
            raise SpanContractError(
                f"warc_record claims {length} bytes at offset {offset} but only {len(raw)} are "
                "present; the container is truncated"
            )
        return ResolvedRegion(
            value=raw.decode(document.encoding, errors="replace"),
            raw=raw,
            detail={"record_offset": offset, "warc_digest": self.warc_digest},
        )


@dataclass(frozen=True, slots=True)
class SourceLocatorSpan:
    """The only pointer-only variant: the span names a location, and no bytes are claimed.

    Legal, and deliberately the weakest thing the union admits. It cannot support a grounded
    rendering -- there is no content behind it to compare against -- so ``resolve`` says so
    rather than returning an empty string that would read as "the region was empty".
    """

    locator: SourceLocator

    kind: SelectorKind = field(default=SelectorKind.SOURCE_LOCATOR, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.locator, SourceLocator):
            raise SpanContractError(
                "source_locator selector must carry a SourceLocator, got "
                f"{type(self.locator).__name__}"
            )

    def resolve(self, document: StoredDocument) -> ResolvedRegion:
        """Yield the locator, not bytes -- and say that is what happened.

        There is nothing behind this variant to compare against, so ``raw`` is empty and
        ``is_pointer_only`` is True. Returning an empty *string* here would have been the more
        natural-looking wrong answer: an empty string reads as "the region was empty", which is
        a claim about the source.
        """
        return ResolvedRegion(
            value=self.locator.uri,
            raw=b"",
            is_pointer_only=True,
            detail={
                "fragment": self.locator.fragment,
                "re_fetch_required": True,
                "note": "no bytes are claimed; the locator must be resolved against the source",
            },
        )


#: The union, as a runtime checkable tuple. ``isinstance(selector, SpanSelector)`` is the
#: single gate a bare integer fails.
SpanSelector = (
    CharSpan | PageBoxSpan | TableCellSpan | JsonPathSpan | TimeRangeSpan
    | GeometrySpan | WarcRecordSpan | SourceLocatorSpan
)


@dataclass(frozen=True, slots=True)
class EvidenceSpanRef:
    """A pointer from a derived result into the exact source bytes that produced it.

    Five fields, four of them required, and the one that looks optional -- ``selector`` -- is
    where the type does its work: it is a union member or the construction fails. There is no
    integer form, no default, and no coercion.

    ``selector_semantics_version`` is mandatory (R2) and is checked against the selector that
    is actually present, so ``table_cell/2`` on a ``page_box`` selector is refused at
    construction rather than at read time.
    """

    observation_ref: str
    blob_digest: str
    selector: SpanSelector
    source_locator: SourceLocator
    selector_semantics_version: str

    def __post_init__(self) -> None:
        observation_ref = str(self.observation_ref).strip()
        if not observation_ref:
            raise SpanContractError(
                "observation_ref is required; a span that names no observation cannot be "
                "traced back to the bytes it claims to address (FR-004)"
            )
        object.__setattr__(self, "observation_ref", observation_ref)

        blob_digest = str(self.blob_digest).strip()
        if not blob_digest:
            raise SpanContractError(
                "blob_digest is required; the digest is the identity of the raw object and the "
                "span is only a pointer into it (R8)"
            )
        object.__setattr__(self, "blob_digest", blob_digest)

        if not isinstance(self.selector, SpanSelector):
            # The measured defect, refused at the line that would have introduced it.
            raise SpanContractError(
                f"selector must be one of the eight typed variants "
                f"({', '.join(sorted(k.value for k in SelectorKind))}); got "
                f"{self.selector!r} of type {type(self.selector).__name__}. An int here is the "
                "conflation contract 02 exists to end: one offset field carried byte offset, "
                "segment index and unset-zero in three producers and all three were summed "
                "together (R1)"
            )
        if not isinstance(self.source_locator, SourceLocator):
            raise SpanContractError(
                f"source_locator must be a SourceLocator, got {type(self.source_locator).__name__}"
            )

        declared = SelectorSemanticsVersion.parse(self.selector_semantics_version)
        present = SelectorKind(self.selector.kind)
        if declared.kind is not present:
            raise SpanContractError(
                f"selector_semantics_version {declared} does not match the selector present, "
                f"which is a {present.value}; the version names the producer convention and a "
                "mismatch is a producer bug, not a version to convert (R2)"
            )
        object.__setattr__(
            self, "selector_semantics_version", str(declared)
        )

    # -- semantics compatibility -------------------------------------------

    @property
    def semantics(self) -> SelectorSemanticsVersion:
        return SelectorSemanticsVersion.parse(self.selector_semantics_version)

    def is_comparable_with(self, other: EvidenceSpanRef) -> bool:
        return self.semantics.is_comparable_with(other.semantics)

    def require_comparable_with(self, other: EvidenceSpanRef) -> None:
        """Raise unless the two spans were written under the same producer convention.

        This is the whole of FR-006. There is no conversion here and none may be added: two
        conventions with no published mapping have no best-effort merge, and a best-effort
        merge of two unknown conventions silently manufactures wrong provenance.
        """
        if not self.is_comparable_with(other):
            raise SpanSemanticsMismatch(
                f"span semantics {self.selector_semantics_version} and "
                f"{other.selector_semantics_version} are not comparable; the platform refuses to "
                "conflate them and reports the ambiguity instead of aggregating (FR-006, R2)"
            )

    # -- grounding ----------------------------------------------------------

    def resolve(self, document: StoredDocument) -> ResolvedRegion:
        return self.selector.resolve(document)

    def check_blob(self, document: StoredDocument) -> BlobCheck:
        """Compare the declared digest against the stored bytes (R8).

        Returns a record rather than raising. The blob wins when they disagree and the span is
        reported stale with both digests attached -- a stale span is a finding to surface, not
        an exception that takes the reader down with it.
        """
        stored = document.blob_digest()
        if stored == self.blob_digest:
            return BlobCheck(status="fresh", declared_digest=self.blob_digest, stored_digest=stored)
        return BlobCheck(
            status="stale",
            declared_digest=self.blob_digest,
            stored_digest=stored,
            detail="the stored blob is the identity (R8); this span was reported stale",
        )

    # -- identity -----------------------------------------------------------

    def content_key(self) -> str:
        """Content address of the span itself, for deduplication and lineage keys."""
        return digest_of(
            {
                "observation_ref": self.observation_ref,
                "blob_digest": self.blob_digest,
                "selector": _selector_form(self.selector),
                "source_locator": self.source_locator.as_dict(),
                "selector_semantics_version": self.selector_semantics_version,
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "observation_ref": self.observation_ref,
            "blob_digest": self.blob_digest,
            "selector": _selector_form(self.selector),
            "source_locator": self.source_locator.as_dict(),
            "selector_semantics_version": self.selector_semantics_version,
            "span_id": self.content_key(),
        }


@dataclass(frozen=True, slots=True)
class BlobCheck:
    """Whether a span's declared digest still matches the bytes it points into."""

    status: str
    declared_digest: str
    stored_digest: str
    detail: str = ""

    @property
    def is_stale(self) -> bool:
        return self.status == "stale"


def _selector_form(selector: SpanSelector) -> dict[str, Any]:
    """The wire form: one key, the variant name, its own fields. Never flattened."""
    name = SelectorKind(selector.kind).value
    payload: dict[str, Any] = {}
    for field_info in _selector_fields(selector):
        if field_info.name == "kind":
            continue
        value = getattr(selector, field_info.name)
        payload[field_info.name] = list(value) if isinstance(value, tuple) else value
    return {name: payload}


def _selector_fields(selector: Any) -> tuple[Any, ...]:
    return dataclasses.fields(selector)