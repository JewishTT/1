"""Is this payload JSON text? — decided **here**, recorded, and auditable.

Feature 021 brief §25 (producers report what the bytes say); constitution IV (fail-closed) and
VI (determinism, Domain Invariant 12).

**The defect this replaces.** The upstream HTTP client answered "is this JSON?" by looking at
the first non-space character of the body. That is a **semantic gate hidden in the
transport**: it fires before any parser is chosen, it is invisible to every reader of the
transport's code, and it means the same payload can be classified differently by two different
clients that disagree about whitespace or about what counts as JSON. Worse, it makes the
classification *unrecorded* — nothing downstream can tell whether a payload was routed by a
declared content type or by a byte someone happened to look at.

So detection is a **parser-layer** decision with a name, and this module's whole content is
that name. :class:`Detection` carries the rule that decided, the declared media type it
decided from, whether a probe was declared and whether the probe matched, and every
:class:`~parsers.payload.records.ParsedPayload` carries its :class:`Detection` — so a record
set is never separated from the reason it has the shape it has.

**The rule, in the order it is applied, and the order is the contract.**

1. :attr:`DetectionRule.CONTENT_TYPE_JSON` — the **declared** ``content_type`` names a JSON
   media type: the essence is ``application/json`` or ends in ``+json`` (``ld+json``,
   ``rdap+json``, ``geo+json``). This decides ``is_json=True`` and **the probe does not run**.
2. :attr:`DetectionRule.CONTENT_TYPE_DECLARED_NOT_JSON` — a content type was declared and it
   is not a JSON media type. This decides ``is_json=False``, and this is the rule that makes
   "a source that returns JSON under ``text/plain`` is not silently upgraded" true: a body
   whose first non-space byte is ``{`` is still **not** parsed as JSON, because the transport
   declared what it is and a parser that overruled the declaration on a hunch would be
   guessing about the source. The caller can see the rule, the declared type and the missed
   opportunity, and re-parse with the probe declared if it wants to — as a decision it makes
   and records, not one this module makes silently.
3. :attr:`DetectionRule.PROBE_JSON_TEXT` — **no** content type was declared, a probe was
   declared by the caller, and the first byte outside RFC 8259 whitespace is ``{`` or ``[``.
4. :attr:`DetectionRule.PROBE_NOT_JSON` — the same, and the first byte is anything else.
5. :attr:`DetectionRule.NO_DECLARATION` — no content type and no probe declared. The default
   is **not JSON**, and it is recorded as a decision rather than as an absence, so a payload
   that arrives with a missing header is distinguishable from one that arrived as JSON.

``text/json`` is deliberately **not** in rule 1's set. It is not a registered media type, and
accepting an unregistered one is the same guess this module exists to remove; a source that
declares it is routed by rule 2 and the caller sees ``text/json`` in the detection record and
can decide otherwise.

**The probe is byte-level and whitespace-exact.** RFC 8259 whitespace is ``0x20 0x09 0x0A
0x0x0D`` — four bytes, and only those four, because a byte inside a multi-byte UTF-8 sequence
is never one of them and skipping "any byte that looks like space" is a guess about encodings
this layer does not have. The offset of the byte the probe stopped on is recorded as
:attr:`Detection.probe_offset`, so a reader can check the probe's own claim.

**Total and deterministic.** Any ``bytes`` object, any ``str`` (including the empty string)
and any ``None`` for ``content_type`` returns a :class:`Detection`; there is no input that
raises, and no clock, no randomness and no dict iteration anywhere in the answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

#: The four bytes RFC 8259 calls whitespace, and the only four this module skips when probing.
#: Published because "what counts as whitespace" is the whole of the probe, and a probe whose
#: rule is not written down is the upstream defect in miniature.
JSON_WHITESPACE: frozenset[int] = frozenset({0x20, 0x09, 0x0A, 0x0D})

#: The exact media type that declares JSON.
JSON_MEDIA_TYPE = "application/json"

#: The structured-syntax suffix that declares JSON (``application/ld+json``,
#: ``application/rdap+json``, ``application/geo+json``). Registered by RFC 6839, so this is a
#: naming rule rather than a heuristic.
JSON_SUFFIX = "+json"

#: The two bytes that open a JSON object and a JSON array. The probe looks for exactly these
#: and nothing else: ``"5"`` and ``true`` are valid JSON but are not containers, and a probe
#: that treated a bare number as a structured document would be deciding a payload is shaped
#: like something it is not.
JSON_CONTAINER_OPENERS: frozenset[int] = frozenset({ord("{"), ord("[")})


class DetectionRule(StrEnum):
    """Which rule decided whether a payload is JSON text — five members, closed.

    The closure is the point. A reader asking "why was this parsed as JSON?" gets exactly one
    of five answers, and every one of them is a fact about the declaration or about the first
    byte of the body — never about what the content seems to be.
    """

    #: The declared ``content_type`` names a JSON media type. Decided from the declaration;
    #: the probe did not run.
    CONTENT_TYPE_JSON = "content_type_json"
    #: A ``content_type`` was declared and it is not a JSON media type. ``is_json`` is
    #: ``False`` whatever the first byte is.
    CONTENT_TYPE_DECLARED_NOT_JSON = "content_type_declared_not_json"
    #: No declaration, a declared probe, and the first non-whitespace byte opens a container.
    PROBE_JSON_TEXT = "probe_json_text"
    #: No declaration, a declared probe, and it did not open a container.
    PROBE_NOT_JSON = "probe_not_json"
    #: No declaration and no probe: the answer is "not JSON" and it is recorded as a decision.
    NO_DECLARATION = "no_declaration"


#: Every rule, in declaration order — the order is also the precedence order.
DETECTION_RULES: tuple[DetectionRule, ...] = tuple(DetectionRule)


@dataclass(frozen=True, slots=True)
class Detection:
    """The JSON-text decision, and every input it was made from.

    ``declared`` is the ``content_type`` string exactly as the caller passed it (the raw
    header, parameters and all) and ``media_type`` is its essence — lowercased, parameters
    dropped — or ``""`` when nothing was declared. Both are kept because a header of
    ``"application/json; charset=utf-8"`` and one of ``"application/json"`` are the same
    decision and different facts, and a reader checking the decision wants to see the one that
    was actually sent.
    """

    is_json: bool
    rule: DetectionRule
    declared: str
    media_type: str
    probe_declared: bool = False
    probe_matched: bool = False
    probe_offset: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "is_json", bool(self.is_json))
        object.__setattr__(self, "rule", DetectionRule(self.rule))
        object.__setattr__(self, "declared", str(self.declared))
        object.__setattr__(self, "media_type", str(self.media_type))
        object.__setattr__(self, "probe_declared", bool(self.probe_declared))
        object.__setattr__(self, "probe_matched", bool(self.probe_matched))
        if self.probe_offset is not None:
            object.__setattr__(self, "probe_offset", int(self.probe_offset))

    @property
    def declared_json(self) -> bool:
        """Whether a ``content_type`` was declared at all — the fact rule 1 and rule 2 branch on."""
        return bool(self.media_type)

    @property
    def probed(self) -> bool:
        """Whether the probe ran. ``False`` whenever a content type was declared."""
        return self.probe_declared and self.probe_offset is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_json": self.is_json,
            "rule": str(self.rule),
            "declared": self.declared,
            "media_type": self.media_type,
            "probe_declared": self.probe_declared,
            "probe_matched": self.probe_matched,
            "probe_offset": self.probe_offset,
        }


def media_type_essence(content_type: str | None) -> str:
    """``"application/json; charset=utf-8"`` → ``"application/json"``; anything absent → ``""``.

    Lowercased and stripped, because a media type is case-insensitive and a header that says
    ``"Application/JSON"`` declares exactly what ``"application/json"`` declares. Only the
    parameter list is dropped: the parameters are facts about the payload's encoding, and this
    module is deciding the payload's *grammar*, not its encoding.
    """
    text = str(content_type or "").split(";", 1)[0].strip().lower()
    return text


def declares_json(media_type: str) -> bool:
    """Whether this media type names JSON: the exact type, or the RFC 6839 ``+json`` suffix."""
    essence = str(media_type or "").strip().lower()
    return essence == JSON_MEDIA_TYPE or essence.endswith(JSON_SUFFIX)


def probe_json_text(body: bytes) -> tuple[bool, int | None]:
    """``(matched, offset)`` — is the first non-whitespace byte a container opener?

    Returns the offset of the byte it stopped on rather than a bool alone, so the probe's
    decision can be checked against the payload instead of believed. An all-whitespace or empty
    body is ``(False, None)``: there was no byte to judge, and that is different from judging a
    byte and getting ``false``.
    """
    for offset in range(len(body)):
        byte = body[offset]
        if byte in JSON_WHITESPACE:
            continue
        return byte in JSON_CONTAINER_OPENERS, offset
    return False, None


def detect_json_text(
    *,
    content_type: str | None,
    body: bytes,
    probe_when_undeclared: bool = False,
) -> Detection:
    """Decide whether ``body`` is JSON text, and say which rule decided.

    ``probe_when_undeclared`` is the **declared probe**: the caller states, in the call, that
    it wants the byte probe run when — and only when — the transport declared no content type.
    It defaults to ``False``, because the safe default for a payload nobody described is to
    read it as text and to be *seen* having done so. Turning it on is a decision the caller
    makes and this module records (:attr:`Detection.probe_declared`), rather than a behaviour
    the transport performs on its own.

    Pure and total: no input raises, and the answer for the same three arguments is the same in
    a second process (constitution VI, Domain Invariant 12).
    """
    essence = media_type_essence(content_type)
    if essence:
        json_declared = declares_json(essence)
        return Detection(
            is_json=json_declared,
            rule=(
                DetectionRule.CONTENT_TYPE_JSON
                if json_declared
                else DetectionRule.CONTENT_TYPE_DECLARED_NOT_JSON
            ),
            declared=str(content_type or ""),
            media_type=essence,
            probe_declared=bool(probe_when_undeclared),
            probe_matched=False,
            probe_offset=None,
        )
    if not probe_when_undeclared:
        return Detection(
            is_json=False,
            rule=DetectionRule.NO_DECLARATION,
            declared="",
            media_type="",
            probe_declared=False,
            probe_matched=False,
            probe_offset=None,
        )
    matched, offset = probe_json_text(body)
    return Detection(
        is_json=matched,
        rule=DetectionRule.PROBE_JSON_TEXT if matched else DetectionRule.PROBE_NOT_JSON,
        declared="",
        media_type="",
        probe_declared=True,
        probe_matched=matched,
        probe_offset=offset,
    )


__all__ = [
    "DETECTION_RULES",
    "JSON_CONTAINER_OPENERS",
    "JSON_MEDIA_TYPE",
    "JSON_SUFFIX",
    "JSON_WHITESPACE",
    "Detection",
    "DetectionRule",
    "declares_json",
    "detect_json_text",
    "media_type_essence",
    "probe_json_text",
]
