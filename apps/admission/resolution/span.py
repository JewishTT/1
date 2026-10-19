"""Evidence spans on identity candidates (spec 030 contract 02, R4/R5/R6/R8).

A merge decision an analyst cannot interrogate is a decision they have to take on faith, so
R4 requires every resolution candidate offered for merge or split to carry the span of *each*
side's evidence — or to be explicitly rendered un-grounded. That "or" is the load-bearing half:
silently omitting a span and rendering nothing is not the same claim as saying "this is not
grounded", and only one of the two is honest.

Scope note, stated rather than implied. This module implements the ``char_span`` selector and
refuses the others. Contract 02 R1 makes the selector a typed union and R2 makes the semantics
version mandatory per producer; inventing a ``page_box`` or ``time_range`` variant here would
mean inventing a convention nobody has agreed, and R2's whole point is that two spans whose
semantics versions differ must not be compared or summed. So the unimplemented variants are a
refusal with a named cause, not a placeholder that silently degrades to a character offset.

R6 is enforced structurally: a normalized form is a *different* span carrying ``derived_from``,
never a rewrite of the original. R8 is enforced by :meth:`EvidenceSpanRef.staleness` — the blob
digest is the identity, and a span that disagrees with its blob is reported, not honoured.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "CHAR_SPAN_SEMANTICS_VERSION",
    "CharSpanSelector",
    "EvidenceSpanRef",
    "Grounding",
    "SourceLocator",
    "SpanError",
    "blob_digest_for",
    "grounding_of",
    "ungrounded",
]

#: R2 — which producer convention this span was written under. Two spans with different values
#: are not comparable, and this module refuses to compare them.
CHAR_SPAN_SEMANTICS_VERSION = "document_char/1"


class SpanError(ValueError):
    """A span that cannot address anything. Raised, not repaired."""


class Grounding(StrEnum):
    """R5 — whether the span actually resolves. Never a bare boolean in the data."""

    GROUNDED = "grounded"
    UNGROUNDED = "ungrounded"
    STALE = "stale"


def blob_digest_for(source_text: str) -> str:
    """Content address of the raw bytes a span points into (R8)."""
    return "sha256:" + hashlib.sha256(source_text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CharSpanSelector:
    """Half-open ``[start, end)`` character range in the declared encoding."""

    start: int
    end: int
    encoding: str = "utf-8"

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise SpanError(
                f"char_span.end ({self.end}) must exceed char_span.start ({self.start}); "
                "a zero-width span addresses no bytes and is not a position"
            )
        if self.start < 0:
            raise SpanError(
                "negative char_span offsets are the extractor's explicit 'unlocatable'; "
                "use Grounding.UNGROUNDED rather than a negative position"
            )

    def slice_of(self, source_text: str) -> str:
        """Round trip (contract 02 round-trip requirement), no normalisation applied."""
        return source_text[self.start : self.end]


@dataclass(frozen=True, slots=True)
class SourceLocator:
    """How to re-fetch the source the span addresses."""

    uri: str
    fragment: str = ""

    def __post_init__(self) -> None:
        if not self.uri:
            raise SpanError("source_locator.uri is REQUIRED (contract 02 shape)")


@dataclass(frozen=True, slots=True)
class EvidenceSpanRef:
    """One span: which observation, which bytes, which range, under which convention."""

    observation_ref: str
    blob_digest: str
    selector: CharSpanSelector
    source_locator: SourceLocator
    selector_semantics_version: str = CHAR_SPAN_SEMANTICS_VERSION
    #: R6 — a normalized/transliterated form points back at the span it was derived from and
    #: never replaces it.
    derived_from: str | None = None
    #: R5 — why this span does not resolve, when it does not.
    ungrounded_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.observation_ref:
            raise SpanError("observation_ref is REQUIRED (contract 02 shape)")
        if not self.blob_digest:
            raise SpanError("blob_digest is REQUIRED (contract 02 shape)")
        if self.selector_semantics_version != CHAR_SPAN_SEMANTICS_VERSION:
            # R2: refuse rather than guess. Comparing across conventions manufactures
            # provenance that was never produced.
            raise SpanError(
                f"selector_semantics_version {self.selector_semantics_version!r} is not "
                f"{CHAR_SPAN_SEMANTICS_VERSION!r}; this module compares only its own convention"
            )

    @property
    def grounding(self) -> Grounding:
        if self.ungrounded_reason:
            return Grounding.UNGROUNDED
        return Grounding.GROUNDED

    def staleness(self, actual_digest: str) -> str | None:
        """R8 — mismatch between span and blob, or ``None`` when they agree.

        The blob wins. This returns the reason it disagreed; it does not repair the span,
        because a repair would be a rewrite.
        """
        if actual_digest and actual_digest != self.blob_digest:
            return f"span_digest_mismatch:{self.blob_digest}!={actual_digest}"
        return None


def grounding_of(spans: tuple[EvidenceSpanRef, ...] | list[EvidenceSpanRef]) -> Grounding:
    """R5 — the weakest grounding in the set, so a grounded left never hides an ungrounded right."""
    if not spans:
        return Grounding.UNGROUNDED
    return max((s.grounding for s in spans), key=lambda g: g.value)


def ungrounded(
    observation_ref: str,
    reason: str,
    source_locator: SourceLocator,
    *,
    blob_digest: str = "",
) -> EvidenceSpanRef:
    """An explicitly un-grounded span (R4's "or be explicitly rendered un-grounded")."""
    return EvidenceSpanRef(
        observation_ref=observation_ref,
        blob_digest=blob_digest or "sha256:unlocated",
        selector=CharSpanSelector(0, 1),
        source_locator=source_locator,
        ungrounded_reason=reason,
    )