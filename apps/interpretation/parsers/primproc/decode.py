"""Decode a payload's bytes to text, and say which rule said so — or refuse, by name.

**The rule that is not here is the point.** A statistical charset detector would be three lines
long and would return an answer for every payload, including the ones where the answer is a
guess. This module has exactly three deciding rules (:class:`~parsers.primproc.reasons.DecodeRule`)
and six refusals (:class:`~parsers.primproc.reasons.DecodeRefusal`), and none of the six is
"decoded it anyway". Mojibake is not noisy text — it is *wrong* text that looks like text, it
silently corrupts every name, number and address downstream of it, and nothing in the output
carries a mark saying a guess was made. A named refusal is worth more than a plausible answer
about evidence, so that is what a payload nobody described and nobody can decode gets.

The refusal that matters most is
:attr:`~parsers.primproc.reasons.DecodeRefusal.CHARSET_UNDECLARED`: no declaration anywhere, and
the bytes are not valid UTF-8. That is precisely the case a detector "solves", and precisely the
case where a wrong answer is invisible. Note what it is **not** for: an ASCII body decodes under
:attr:`~parsers.primproc.reasons.DecodeRule.UTF8_DEFAULT` because ASCII *is* a subset of UTF-8,
so that is a statement rather than a guess.

**Order, and the order is the contract.**

1. :attr:`~parsers.primproc.reasons.DecodeRule.CONTENT_TYPE_CHARSET` — the declared
   ``content_type`` carried a ``charset=``. This is the transport stating a fact about the
   payload it fetched, and it is the only source that outranks the payload's own claims. If it
   names a codec this interpreter does not know, or if the bytes do not decode under it, that
   is a **refusal** and not a fall-through: a source that declared windows-1252 and sent
   something else has told us something, and quietly trying the next rule would erase it.
2. :attr:`~parsers.primproc.reasons.DecodeRule.META_CHARSET` — nothing was declared, the caller
   **declared a probe** (``probe_when_undeclared=True``), and a ``<meta charset>`` or
   ``<meta http-equiv="content-type" …>`` in the first bytes names one. A probe that nobody
   declared does not run, which is the same contract :func:`parsers.payload.detect.detect_json_text`
   offers and for the same reason: the safe default for an undescribed payload is to say so.
3. :attr:`~parsers.primproc.reasons.DecodeRule.UTF8_DEFAULT` — nothing declared, no probe, and
   the bytes are valid UTF-8.

**A near neighbour, deliberately not used.**
``extractors.language.decode_bytes`` does this job for the extraction lane and it ends in
``charset_normalizer`` — a real detector, doing exactly what this stage refuses to do. It is not
called here, and the divergence is deliberate rather than an oversight: that function's contract
is "always return text", and this stage's contract is "return text or a named refusal". Two
contracts, two functions; sharing one would mean importing the guessing into the place that
exists to keep it out. Its HTML-charset probe is likewise re-derived here rather than imported,
because it is module-private and because its failure mode differs — it falls back rather than
refusing.

**Pure and total.** No input raises, no clock and no randomness is read, and the answer for the
same ``(body, content_type, probe_when_undeclared)`` is the same in a second process (constitution
VI, Domain Invariant 12).
"""

from __future__ import annotations

import codecs
import re
from dataclasses import dataclass
from typing import Any, Final

from parsers.payload.detect import media_type_essence
from parsers.primproc.reasons import DecodeRefusal, DecodeRule

#: The alias set this stage treats as "UTF-8 under another name", borrowed in spirit from
#: ``extractors.language._UTF8_FAMILY``. A source that declares ``us-ascii`` over ASCII bytes has
#: declared the truth with a different word for it, and refusing that would be pedantry.
UTF8_ALIASES: Final[frozenset[str]] = frozenset(
    {"utf-8", "utf8", "utf", "us-ascii", "ascii", "unicode-1-1-utf-8"}
)

#: How far into the payload a ``<meta>`` probe may look. Bounded because a probe that reads the
#: whole body to find a charset is a scan whose cost is the document, and because a ``<meta>``
#: past the first few kilobytes is not a declaration about the encoding — it is a string
#: somewhere in the content that happens to look like one.
META_PROBE_WINDOW: Final[int] = 4096

#: A payload must *look* like markup before a ``<meta>`` in it is allowed to declare an
#: encoding. Without the guard, a JSON payload containing the text ``<meta charset=x>`` in a
#: string would be decoded by a rule that fired on its own content.
_HTML_GUARD: Final[re.Pattern[str]] = re.compile(r"<\s*(?:!doctype|html|head|body)\b", re.IGNORECASE)

_CHARSET_PARAM: Final[re.Pattern[str]] = re.compile(
    r";\s*charset\s*=\s*[\"']?\s*([A-Za-z0-9._:+-]+)", re.IGNORECASE
)
_META_CHARSET: Final[re.Pattern[bytes]] = re.compile(
    rb"<\s*meta[^>]*?charset\s*=\s*[\"']?\s*([A-Za-z0-9._:+-]+)", re.IGNORECASE
)


def charset_parameter(content_type: str | None) -> str | None:
    """The ``charset=`` a ``Content-Type`` declared, or ``None``.

    Parameter syntax only, and only the ``charset`` parameter: a media type's other parameters
    (``boundary``, ``q``) are facts about a MIME container rather than about the encoding of a
    body this stage is about to read. Returns ``None`` for a header with no charset rather than
    an empty string, so "no declaration" and "a declaration that is blank" cannot be confused
    with "the declaration was ``charset=``".
    """
    essence = media_type_essence(content_type)
    if not essence:
        return None
    match = _CHARSET_PARAM.search(str(content_type or ""))
    if match is None:
        return None
    return match.group(1).strip().lower() or None


def probe_meta_charset(body: bytes) -> tuple[str | None, int | None]:
    """``(charset, offset)`` — what a ``<meta>`` in the first bytes declares, if anything.

    ``(None, None)`` when there is no declaration, and that is different from declaring a codec
    this interpreter does not know, which is ``(name, offset)`` and then a refusal downstream.
    The offset is the byte position of the name, so the probe's own claim can be checked against
    the payload rather than believed.

    The bytes are matched as bytes, not decoded first: the name is ASCII by construction, so
    decoding would only add a way to fail before the rule that decides anything has run.
    """
    window = body[:META_PROBE_WINDOW]
    if not _HTML_GUARD.search(window.decode("latin-1")):
        return None, None
    match = _META_CHARSET.search(window)
    if match is None:
        return None, None
    return match.group(1).decode("ascii", errors="ignore").strip().lower() or None, match.start(1)


@dataclass(frozen=True, slots=True)
class DecodeDecision:
    """The decode, and every input it was made from.

    ``declared`` is the ``content_type`` exactly as the caller passed it — parameters and all —
    and ``media_type`` is its essence, so a header of ``"text/html; charset=windows-1251"`` and
    one of ``"text/html"`` are the same decision and different facts, and both are kept.

    ``refusal`` is the empty string exactly when this decision produced text. When it is set,
    :attr:`text` is the empty string: there is no partial decode and no ``errors="replace"``
    fallback, because a partially-decoded page is a page whose mangled bytes are indistinguishable
    from the source's own.
    """

    text: str
    charset: str
    rule: DecodeRule
    declared: str
    media_type: str
    probe_declared: bool = False
    probe_matched: bool = False
    probe_offset: int | None = None
    refusal: str = ""
    refusal_detail: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "text", str(self.text))
        object.__setattr__(self, "charset", str(self.charset))
        object.__setattr__(self, "rule", DecodeRule(self.rule))
        object.__setattr__(self, "declared", str(self.declared))
        object.__setattr__(self, "media_type", str(self.media_type))
        object.__setattr__(self, "probe_declared", bool(self.probe_declared))
        object.__setattr__(self, "probe_matched", bool(self.probe_matched))
        object.__setattr__(self, "refusal", str(self.refusal))
        object.__setattr__(self, "refusal_detail", str(self.refusal_detail))

    @property
    def ok(self) -> bool:
        """Whether this decision produced text rather than a refusal."""
        return not self.refusal

    @property
    def utf8(self) -> bool:
        """Whether the decided charset is UTF-8 — the offset mapping needs to know."""
        return self.charset.lower().replace("_", "-") in UTF8_ALIASES

    def to_dict(self) -> dict[str, Any]:
        return {
            "charset": self.charset,
            "rule": str(self.rule),
            "declared": self.declared,
            "media_type": self.media_type,
            "probe_declared": self.probe_declared,
            "probe_matched": self.probe_matched,
            "probe_offset": self.probe_offset,
            "refusal": self.refusal,
            "refusal_detail": self.refusal_detail,
        }


def _known(name: str) -> bool:
    try:
        codecs.lookup(name)
    except (LookupError, ValueError):
        return False
    return True


def _decode_or_none(body: bytes, codec: str) -> str | None:
    """Decode under ``codec``, or ``None`` — never ``errors="replace"``.

    The refusal to substitute ``U+FFFD`` is the whole of this module's position. A replacement
    character is a lie about the source that costs nothing to emit and everything to discover
    later: it survives into extracted names, into digests and into a human-readable raw view,
    looking like a character the source contained.
    """
    try:
        return body.decode(codec)
    except (UnicodeDecodeError, LookupError, ValueError):
        return None


def _refusal(refusal: DecodeRefusal, detail: str) -> DecodeDecision:
    return DecodeDecision(
        text="",
        charset="",
        rule=DecodeRule.UTF8_DEFAULT,
        declared="",
        media_type="",
        refusal=str(refusal),
        refusal_detail=detail,
    )


def decode_body(
    *,
    body: bytes,
    content_type: str | None,
    probe_when_undeclared: bool = False,
) -> DecodeDecision:
    """Decode ``body``, and say which rule decided — or refuse, by name.

    Total: any input returns a :class:`DecodeDecision`, and no input raises. ``body`` that is not
    ``bytes`` is refused as
    :attr:`~parsers.primproc.reasons.DecodeRefusal.BODY_NOT_BYTES` rather than coerced, because
    a caller that hands this stage an object is a caller with a bug and the stage that hides it
    is the last place the bug can be found.
    """
    if not isinstance(body, bytes):
        return _refusal(
            DecodeRefusal.BODY_NOT_BYTES,
            f"the body is {type(body).__name__}, which carries no bytes. Primary processing "
            "reads bytes: a runtime that handed over a decoded object has crossed §3's boundary "
            "before this stage could refuse it",
        )

    declared = str(content_type or "")
    media_type = media_type_essence(content_type)
    charset = charset_parameter(content_type)
    if charset is not None:
        if not _known(charset):
            return DecodeDecision(
                text="",
                charset=charset,
                rule=DecodeRule.CONTENT_TYPE_CHARSET,
                declared=declared,
                media_type=media_type,
                probe_declared=bool(probe_when_undeclared),
                refusal=str(DecodeRefusal.CHARSET_UNKNOWN_IN_CONTENT_TYPE),
                refusal_detail=(
                    f"the declared content type names charset={charset!r}, which this "
                    "interpreter has no codec for. Falling through to the payload's own claims "
                    "would hide that the transport stated a charset nobody can honour"
                ),
            )
        decoded = _decode_or_none(body, charset)
        if decoded is None:
            return DecodeDecision(
                text="",
                charset=charset,
                rule=DecodeRule.CONTENT_TYPE_CHARSET,
                declared=declared,
                media_type=media_type,
                probe_declared=bool(probe_when_undeclared),
                refusal=str(DecodeRefusal.CHARSET_FAILED_IN_CONTENT_TYPE),
                refusal_detail=(
                    f"the declared content type names charset={charset!r} and these "
                    f"{len(body)} bytes do not decode under it. The declaration is reported as "
                    "the failure rather than worked around: a source that declares an encoding it "
                    "did not send is a fact about the source"
                ),
            )
        return DecodeDecision(
            text=decoded,
            charset=charset,
            rule=DecodeRule.CONTENT_TYPE_CHARSET,
            declared=declared,
            media_type=media_type,
            probe_declared=bool(probe_when_undeclared),
            probe_matched=False,
            probe_offset=None,
        )

    if probe_when_undeclared:
        meta_charset, offset = probe_meta_charset(body)
        if meta_charset is not None:
            if not _known(meta_charset):
                return DecodeDecision(
                    text="",
                    charset=meta_charset,
                    rule=DecodeRule.META_CHARSET,
                    declared="",
                    media_type="",
                    probe_declared=True,
                    probe_matched=True,
                    probe_offset=offset,
                    refusal=str(DecodeRefusal.CHARSET_UNKNOWN_IN_META),
                    refusal_detail=(
                        f"the payload declares charset={meta_charset!r} in a meta element at "
                        f"byte {offset}, and this interpreter has no codec for it"
                    ),
                )
            decoded = _decode_or_none(body, meta_charset)
            if decoded is None:
                return DecodeDecision(
                    text="",
                    charset=meta_charset,
                    rule=DecodeRule.META_CHARSET,
                    declared="",
                    media_type="",
                    probe_declared=True,
                    probe_matched=True,
                    probe_offset=offset,
                    refusal=str(DecodeRefusal.CHARSET_FAILED_IN_META),
                    refusal_detail=(
                        f"the payload declares charset={meta_charset!r} at byte {offset} and "
                        f"these {len(body)} bytes do not decode under it"
                    ),
                )
            return DecodeDecision(
                text=decoded,
                charset=meta_charset,
                rule=DecodeRule.META_CHARSET,
                declared="",
                media_type="",
                probe_declared=True,
                probe_matched=True,
                probe_offset=offset,
            )

    decoded = _decode_or_none(body, "utf-8")
    if decoded is not None:
        return DecodeDecision(
            text=decoded,
            charset="utf-8",
            rule=DecodeRule.UTF8_DEFAULT,
            declared=declared,
            media_type=media_type,
            probe_declared=bool(probe_when_undeclared),
            probe_matched=False,
            probe_offset=None,
        )
    return DecodeDecision(
        text="",
        charset="",
        rule=DecodeRule.UTF8_DEFAULT,
        declared=declared,
        media_type=media_type,
        probe_declared=bool(probe_when_undeclared),
        probe_matched=False,
        probe_offset=None,
        refusal=str(DecodeRefusal.CHARSET_UNDECLARED),
        refusal_detail=(
            f"no content type declared a charset, the probe "
            f"{'was' if probe_when_undeclared else 'was not'} declared, and these "
            f"{len(body)} bytes are not valid UTF-8. This stage does not guess an encoding: a "
            "guessed decoding produces text that reads as text while every name, number and "
            "address in it is wrong"
        ),
    )


__all__ = [
    "META_PROBE_WINDOW",
    "UTF8_ALIASES",
    "DecodeDecision",
    "charset_parameter",
    "decode_body",
    "probe_meta_charset",
]
