"""What primary processing returns: the text, and the ledger that accounts for it.

**The ledger is the feature.** :class:`SourceSpan` is a partition of the decoded source: the spans
tile ``[0, len(source))`` with no gap and no overlap, and each carries exactly one
:class:`~parsers.primproc.reasons.SpanVerdict` and, when that verdict is
:attr:`~parsers.primproc.reasons.SpanVerdict.REMOVED`, exactly one
:class:`~parsers.primproc.reasons.RemovalReason`. So "this stage did not quietly eat content" is
a property of the returned value that a caller can verify, not a promise in a docstring — and the
test verifies it by sorting the spans and checking that each one starts exactly where the
previous ended.

**Offsets are carried in four currencies, and every one of them is needed by somebody.**
``source_char_*`` addresses the decoded document (what the tokenizer walked),
``source_byte_*`` addresses the **original raw body** in the codec it declared (what a Raw viewer
holds), and ``output_char_*`` / ``output_byte_*`` address the cleaned text (what a consumer
parses). A single "offset" field could only ever be right for one of them, and the wrong one is
silently wrong: a byte offset computed as UTF-8 on a windows-1251 page points into the middle of a
multi-byte sequence, which is not an off-by-one but a different character.

**Why :class:`OutputLine` rather than "the surviving text runs".** The unit a downstream consumer
addresses is a **line**: ``apps/webapp/src/evidence/rawPayload.ts``'s ``buildLineIndex`` numbers
lines from the payload text and every locator in the UI resolves to a line span, and a mention
addressed into this stage's output has to land on one. So the mapping this module publishes is
line-for-line, and each :class:`OutputLine` names the raw-body byte range of the source characters
it came from — which is what lets a click on cleaned line 3 say "that is raw bytes 812–869 of
the capture you are looking at".

**What is deliberately absent.** No confidence, no type, no entity, no claim, no resolution. §3's
boundary is enforced by the shape: there is no field on this module that could hold one, so a
caller cannot read a semantic judgement out of a cleaning result even by accident.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from parsers.primproc.decode import DecodeDecision
from parsers.primproc.markup import Note
from parsers.primproc.reasons import (
    ENTITY_SYNTAX_REASON,
    PRIMARY_PROC_SCHEMA,
    PRIMARY_PROC_VERSION,
    REMOVAL_REASONS,
    DecodeRefusal,
    ExtractStrategy,
    NoteCode,
    RemovalReason,
    Route,
    SpanVerdict,
)


class PrimProcContractError(ValueError):
    """A refusal a caller asked for as an exception rather than as a record.

    Carries the same stable ``code`` shape as
    :class:`parsers.payload.records.PayloadContractError` and
    :class:`parsers.shallow.ParserContractError`, so one caller can switch on any of them by
    ``.code`` rather than by type. :meth:`PrimaryResult.require_text` is the only thing that
    raises it, and it exists so that a caller who would otherwise read an empty string as "this
    page had no text" cannot.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """One claim on one range of the decoded source.

    ``output_chars`` is what this span contributed to :attr:`PrimaryResult.text`: its length for a
    kept span, zero for a removed one, and **the expansion's length** for a replaced one. That one
    field is what makes the whole result checkable — ``sum(span.output_chars for span in ledger)``
    is the length of the output, so a reader can reconcile the output against the source without
    trusting either.
    """

    start_char: int
    end_char: int
    verdict: SpanVerdict
    reason: str
    output_chars: int
    source_byte_start: int
    source_byte_end: int
    text: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "start_char", int(self.start_char))
        object.__setattr__(self, "end_char", int(self.end_char))
        object.__setattr__(self, "verdict", SpanVerdict(self.verdict))
        object.__setattr__(self, "reason", str(self.reason))
        object.__setattr__(self, "output_chars", int(self.output_chars))
        object.__setattr__(self, "source_byte_start", int(self.source_byte_start))
        object.__setattr__(self, "source_byte_end", int(self.source_byte_end))
        object.__setattr__(self, "text", str(self.text))
        if self.end_char < self.start_char:
            raise PrimProcContractError(
                "source_span_reversed",
                f"a span claims [{self.start_char}, {self.end_char}), which is not a forward "
                "range inside the source",
            )
        if self.output_chars < 0:
            raise PrimProcContractError(
                "source_span_output_invalid",
                f"a span claims {self.output_chars} output characters; a span contributes zero "
                "or more and never a negative count",
            )

    @property
    def source_chars(self) -> int:
        return self.end_char - self.start_char

    @property
    def source_bytes(self) -> int:
        return self.source_byte_end - self.source_byte_start

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_char": self.start_char,
            "end_char": self.end_char,
            "verdict": str(self.verdict),
            "reason": self.reason,
            "output_chars": self.output_chars,
            "source_byte_start": self.source_byte_start,
            "source_byte_end": self.source_byte_end,
            "source_chars": self.source_chars,
            "source_bytes": self.source_bytes,
        }


@dataclass(frozen=True, slots=True)
class OutputLine:
    """One line of the cleaned text, and the raw-body bytes it came from.

    ``line_number`` is **1-based**, matching ``buildLineIndex`` in
    ``apps/webapp/src/evidence/rawPayload.ts`` — the frontend's line 1 is the first line, and a
    stage that numbered from zero would put every mention one line off with no symptom.

    ``source_byte_start`` / ``source_byte_end`` cover **every** source character the line drew
    from, so a line assembled from three runs names the span from the first to the last. For the
    overwhelmingly common case of a line drawn from one contiguous run, the span is that run's
    exactly and slicing the raw body reproduces it.
    """

    line_number: int
    text: str
    output_char_start: int
    output_char_end: int
    output_byte_start: int
    output_byte_end: int
    source_byte_start: int
    source_byte_end: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "line_number", int(self.line_number))
        object.__setattr__(self, "text", str(self.text))
        for name in (
            "output_char_start",
            "output_char_end",
            "output_byte_start",
            "output_byte_end",
            "source_byte_start",
            "source_byte_end",
        ):
            object.__setattr__(self, name, int(getattr(self, name)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "line_number": self.line_number,
            "text": self.text,
            "output_char_start": self.output_char_start,
            "output_char_end": self.output_char_end,
            "output_byte_start": self.output_byte_start,
            "output_byte_end": self.output_byte_end,
            "source_byte_start": self.source_byte_start,
            "source_byte_end": self.source_byte_end,
        }


@dataclass(frozen=True, slots=True)
class PrimaryResult:
    """One cleaned payload, and every fact about how it was cleaned.

    The fields that are not the text:

    ``ok``
        ``False`` when the decode refused. :attr:`text` is then the empty string — never a partial
        decode and never an ``errors="replace"`` page — so "this page had no text" and "this page
        could not be read" are different values of a boolean rather than the same empty string.
    ``route``
        Which per-type path ran. :attr:`~parsers.primproc.reasons.Route.JSON`,
        :attr:`~parsers.primproc.reasons.Route.NDJSON` and
        :attr:`~parsers.primproc.reasons.Route.TEXT` are **recorded as decisions to change
        nothing**: a cleaner that rewrites a JSON payload has corrupted evidence, and the record
        has to be able to say so.
    ``strategy``
        Which extraction rule chose the main content. ``WHOLE_DOCUMENT`` is a valid answer and a
        weak one, and it is carried so that "we picked ``article``" and "we guessed the densest
        div" cannot be confused downstream.
    ``removed_bytes_by_reason``
        Raw-body bytes, one closed key per :class:`~parsers.primproc.reasons.RemovalReason`,
        always all seven keys present so a caller can histogram without normalising first.
    ``verbatim_body``
        The **original** bytes, set only on the routes that changed nothing. It exists because
        "unchanged" has to mean the original bytes and not a re-encoding of the decoded text: a
        JSON payload declared as ``windows-1252`` re-encoded to UTF-8 is a *different* payload, and
        a stage that returned it while reporting ``output_bytes == input_bytes`` would be lying
        about the one thing it claimed. ``None`` on the cleaning routes, where the output really is
        the cleaned text and is UTF-8.
    ``ledger``
        The partition described in this module's docstring. Published in full.
    ``lines``
        The Raw↔line mapping: one entry per output line, each naming its raw-body byte range.
    """

    ok: bool
    route: Route
    strategy: ExtractStrategy
    text: str
    input_bytes: int
    output_bytes: int
    decode: DecodeDecision
    removed_bytes_by_reason: Mapping[str, int]
    entity_expansion_bytes: int
    ledger: tuple[SourceSpan, ...]
    lines: tuple[OutputLine, ...]
    notes: tuple[Note, ...]
    verbatim_body: bytes | None = None
    version: str = PRIMARY_PROC_VERSION
    schema: str = PRIMARY_PROC_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "ok", bool(self.ok))
        object.__setattr__(self, "route", Route(self.route))
        object.__setattr__(self, "strategy", ExtractStrategy(self.strategy))
        object.__setattr__(self, "text", str(self.text))
        object.__setattr__(self, "input_bytes", int(self.input_bytes))
        object.__setattr__(self, "output_bytes", int(self.output_bytes))
        object.__setattr__(self, "entity_expansion_bytes", int(self.entity_expansion_bytes))
        object.__setattr__(self, "ledger", tuple(self.ledger))
        object.__setattr__(self, "lines", tuple(self.lines))
        object.__setattr__(self, "notes", tuple(self.notes))
        if self.verbatim_body is not None:
            object.__setattr__(self, "verbatim_body", bytes(self.verbatim_body))
        object.__setattr__(self, "removed_bytes_by_reason", dict(self.removed_bytes_by_reason))

    def artifact_body(self) -> bytes:
        """The bytes a derived artefact carries: the original on a passthrough route, the cleaned
        UTF-8 text otherwise.

        One function, so "what does the supplement contain" has one answer and a caller cannot
        pick the wrong one of two nearly-identical fields.
        """
        if self.verbatim_body is not None:
            return self.verbatim_body
        return self.text.encode("utf-8")

    @property
    def removed_bytes_total(self) -> int:
        """Every source byte that did not reach the output, for any reason."""
        return sum(self.removed_bytes_by_reason.values())

    @property
    def source_bytes_kept(self) -> int:
        """Source bytes that reached output processing: the input minus every recorded removal."""
        return self.input_bytes - self.removed_bytes_total

    @property
    def note_codes(self) -> tuple[str, ...]:
        """Every note code in order — the count a caller histograms, not a judgement call."""
        return tuple(note.code for note in self.notes)

    @property
    def unescaped(self) -> bool:
        """Whether any entity reference was replaced. Whether the unescaping *happened*, as a fact."""
        return self.entity_expansion_bytes > 0 or any(
            span.reason == ENTITY_SYNTAX_REASON for span in self.ledger
        )

    @property
    def unchanged(self) -> bool:
        """Whether this route changed nothing. The recorded form of "we did not touch it"."""
        return self.verbatim_body is not None

    def require_text(self) -> str:
        """The cleaned text, or a named refusal — never an empty string standing in for one.

        The fail-closed front door, and the reason a refused decode is not merely ``text=""``: a
        caller that reads an empty cleaned page as "this page had nothing to say" has turned a
        decode failure into a finding about the world.
        """
        if self.ok:
            return self.text
        raise PrimProcContractError(
            self.decode.refusal or str(DecodeRefusal.CHARSET_UNDECLARED),
            f"primary processing refused this payload and produced no text: "
            f"{self.decode.refusal_detail}. decode.rule={self.decode.rule}, "
            f"content_type={self.decode.declared or '(none)'}",
        )

    def line_number_of_source_byte(self, source_byte: int) -> int | None:
        """The 1-based output line whose source range covers ``source_byte``, or ``None``.

        The inverse of what a raw viewer needs, and the function that makes the two views one
        object rather than two. ``None`` is a real answer — the byte belongs to a removed
        construct, or to no line at all — and is never rounded to the nearest line: §99's rule for
        the raw pane applies here too.
        """
        for line in self.lines:
            if line.source_byte_start <= source_byte < line.source_byte_end:
                return line.line_number
        return None

    def to_dict(self) -> dict[str, Any]:
        """The whole record, in declared field order — the form a determinism test digests."""
        return {
            "schema": self.schema,
            "version": self.version,
            "ok": self.ok,
            "route": str(self.route),
            "strategy": str(self.strategy),
            "unchanged": self.unchanged,
            "decode": self.decode.to_dict(),
            "input_bytes": self.input_bytes,
            "output_bytes": self.output_bytes,
            "removed_bytes_by_reason": {
                str(reason): self.removed_bytes_by_reason.get(str(reason), 0)
                for reason in REMOVAL_REASONS
            },
            "removed_bytes_total": self.removed_bytes_total,
            "source_bytes_kept": self.source_bytes_kept,
            "entity_expansion_bytes": self.entity_expansion_bytes,
            "note_codes": list(self.note_codes),
            "notes": [note.to_dict() for note in self.notes],
            "lines": [line.to_dict() for line in self.lines],
            "ledger": [span.to_dict() for span in self.ledger],
            "text_length": len(self.text),
        }


def zero_removals() -> dict[str, int]:
    """A full accounting with every reason at zero, in declaration order.

    A fresh mapping rather than a shared one: a caller that adds a key to the result must not be
    able to add it to every other result in the process.
    """
    return {str(reason): 0 for reason in REMOVAL_REASONS}


__all__ = [
    "OutputLine",
    "PrimProcContractError",
    "PrimaryResult",
    "SourceSpan",
    "zero_removals",
]
