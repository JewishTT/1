"""Layer 1: type detection (spec/010 §0.1) — regex + heuristics, NO AI.

A deterministic classifier over the 8 supported input classes. Confidence
follows the spec formula exactly:

    confidence = base_score x format_match x length_factor x (1 + dns_bonus)

``base_score`` is per-type, ``format_match`` is 1.0 iff the validator matches,
``length_factor = min(len(value) / 50, 1.0)`` and ``dns_bonus`` (+0.1) applies
only when an injectable DNS probe (``dns_exists``) confirms an existing record
— with the default ``None`` probe there is no network call and no bonus, so the
whole detector stays deterministic and offline-safe.

The byte form (magic-file header) is used for image / pdf-docx inputs; the
string form is used for every textual class.

   Source lessons: donors/theHarvester (MIT, domain/email regex families),
   donors/user-scanner (MIT, username/email validators), RFC 3966 phone regex.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

# ---------------------------------------------------------------------------
# Input taxonomy
# ---------------------------------------------------------------------------


class InputType(StrEnum):
    """The 8 zero-layer input classes plus the default ``UNKNOWN``."""

    DOMAIN = "domain"
    EMAIL = "email"
    USERNAME = "username"
    PHONE = "phone"
    URL = "url"
    IMAGE = "image"
    NAME = "name"
    DOCUMENT = "pdf/docx"
    UNKNOWN = "unknown"

    @property
    def base_score(self) -> float:
        """Detector base score (spec §0.1 confidence table)."""
        return _BASE_SCORES[self]


_BASE_SCORES = {
    InputType.DOMAIN: 0.95,
    InputType.EMAIL: 0.98,
    InputType.USERNAME: 0.85,
    InputType.PHONE: 0.90,
    InputType.URL: 0.97,
    InputType.IMAGE: 0.99,
    InputType.NAME: 0.60,
    InputType.DOCUMENT: 0.99,
    InputType.UNKNOWN: 0.05,
}

# ---------------------------------------------------------------------------
# Deterministic validators (one per type)
# ---------------------------------------------------------------------------
# ASCII date of spec regex patterns. \p{L} is NOT available on Python 3.11's
# re module, so Unicode letters are expressed as [^\W\d_] (everything except
# non-alphanumeric, digits and underscore).

_DOMAIN_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]{1,61}[a-zA-Z0-9]\.[a-zA-Z]{2,}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,30}$")
_PHONE_RE = re.compile(r"^\+(?:[0-9]\.?){6,15}$")
_URL_RE = re.compile(r"^https?://[^\s/$.?#][^\s]*$")
_NAME_RE = re.compile(r"^[^\W\d_][\w'.\-\s]{2,60}$")

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_WEBP_MAGIC = b"RIFF"
_GIF_MAGIC = b"GIF8"
_PDF_MAGIC = b"%PDF"
_ZIP_MAGIC = b"PK\x03\x04"

_IMAGE_MAGICS = (_JPEG_MAGIC, _PNG_MAGIC, _WEBP_MAGIC, _GIF_MAGIC)
_DOCUMENT_MAGICS = (_PDF_MAGIC, _ZIP_MAGIC)

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}
_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".doc", ".odt", ".xlsx", ".pptx", ".zip"}


@dataclass(frozen=True)
class TypeCandidate:
    """One detected possibility with a deterministic confidence score."""

    input_type: InputType
    confidence: float
    reason: str
    dns_bonus: bool = False


@dataclass(frozen=True)
class SeedInput:
    """Typed seed: the input plus detector output (entity ``SeedInput``)."""

    raw_value: str
    detected_type: InputType
    confidence: float
    metadata: dict = field(default_factory=dict)
    candidates: tuple[TypeCandidate, ...] = ()

    @property
    def seed_id(self) -> str:
        """Content-derived stable id (deterministic, no uuid on purpose)."""
        return "seed-" + _digest(self.raw_value)


def _digest(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def make_soundex(name: str) -> str:
    """Classic Soundex code: leading letter, vowels stripped, consonant classes.

    Example: "Smith" and "Smythe" both collapse to ``S530`` (spec §0.8 step 1).
    """
    if not name:
        return ""
    upper = name.upper()
    first = upper[0]
    mapping = {
        "B": "1", "F": "1", "P": "1", "V": "1",
        "C": "2", "G": "2", "J": "2", "K": "2", "Q": "2", "S": "2", "X": "2", "Z": "2",
        "D": "3", "T": "3",
        "L": "4",
        "M": "5", "N": "5",
        "R": "6",
    }
    code = first
    previous = mapping.get(first, "")
    for char in upper[1:]:
        if char in "AEIOUYH W":
            previous = ""
            continue
        digit = mapping.get(char, "")
        if digit and digit != previous:
            code += digit
            previous = digit
        if len(code) == 4:
            break
    return code.ljust(4, "0")


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


class TypeDetector:
    """Deterministic any-input classifier (Layer 1).

    ``dns_exists`` is an injectable ``Callable[[str], bool]`` used only for the
    DNS bonus term; the default probe returns ``False`` so scoring never
    depends on a live network.
    """

    def __init__(
        self,
        *,
        dns_exists: Callable[[str], bool] | None = None,
    ) -> None:
        self._dns_exists = dns_exists or (lambda _domain: False)

    # -- public API ----------------------------------------------------------

    def detect(self, value: str | bytes, *, filename: str | None = None) -> SeedInput:
        """Classify ``value`` and return the best ``SeedInput`` (deterministic)."""
        candidates = self.candidates(value, filename=filename)
        best = max(candidates, key=lambda c: (c.confidence, -_TYPE_ORDER[c.input_type]))
        raw = _raw_string(value)
        return SeedInput(
            raw_value=raw,
            detected_type=best.input_type,
            confidence=best.confidence,
            metadata={"input_bytes": isinstance(value, bytes)} | _path_metadata(filename),
            candidates=candidates,
        )

    def candidates(self, value: str | bytes, *, filename: str | None = None) -> list[TypeCandidate]:
        """All plausible types with deterministic confidence, best-first not assumed."""
        if isinstance(value, bytes):
            return self._from_bytes(value)
        raw = value.strip()
        if not raw:
            return [TypeCandidate(InputType.UNKNOWN, 0.0, "empty input")]
        candidates = self._text_candidates(raw)
        return sorted(candidates, key=lambda c: (-c.confidence, _TYPE_ORDER[c.input_type]))

    # -- scoring -------------------------------------------------------------

    def confidence(
        self,
        input_type: InputType,
        value: str,
        *,
        format_match: bool = True,
        dns_domain: str | None = None,
    ) -> float:
        """Deterministic score per spec §0.1 (capped at 1.0)."""
        if not format_match:
            return 0.0
        length_factor = min(len(value) / 50.0, 1.0)
        bonus = 0.1 if (dns_domain and self._dns_exists(dns_domain)) else 0.0
        return min(1.0, input_type.base_score * length_factor * (1.0 + bonus))

    # -- byte magic ----------------------------------------------------------

    def _from_bytes(self, data: bytes) -> list[TypeCandidate]:
        for magic in _IMAGE_MAGICS:
            if data.startswith(magic):
                score = self.confidence(InputType.IMAGE, _raw_string(data))
                return [TypeCandidate(InputType.IMAGE, score, "file-magic image header")]
            if magic == _WEBP_MAGIC and data[8:12] == b"WEBP":
                break
        for magic in _DOCUMENT_MAGICS:
            if data.startswith(magic):
                score = self.confidence(InputType.DOCUMENT, _raw_string(data))
                return [TypeCandidate(InputType.DOCUMENT, score, "file-magic document header")]
        return [TypeCandidate(InputType.UNKNOWN, 0.05, "no known file magic")]

    # -- text candidates -----------------------------------------------------

    def _text_candidates(self, raw: str) -> list[TypeCandidate]:
        out: list[TypeCandidate] = []
        if _DOMAIN_RE.match(raw):
            dns = self._dns_exists(raw)
            score = self.confidence(InputType.DOMAIN, raw, dns_domain=raw if dns else None)
            out.append(
                TypeCandidate(InputType.DOMAIN, score, "domain regex", dns_bonus=dns)
            )
        if _EMAIL_RE.match(raw):
            score = self.confidence(InputType.EMAIL, raw)
            out.append(TypeCandidate(InputType.EMAIL, score, "email regex"))
        if _USERNAME_RE.match(raw):
            score = self.confidence(InputType.USERNAME, raw)
            out.append(TypeCandidate(InputType.USERNAME, score, "username regex"))
        if _PHONE_RE.match(raw):
            score = self.confidence(InputType.PHONE, raw)
            out.append(TypeCandidate(InputType.PHONE, score, "RFC 3966 phone regex"))
        if _URL_RE.match(raw):
            score = self.confidence(InputType.URL, raw)
            out.append(TypeCandidate(InputType.URL, score, "http(s) url regex"))
        if _NAME_RE.match(raw) and not _DOMAIN_RE.match(raw) and not _EMAIL_RE.match(raw):
            score = self.confidence(InputType.NAME, raw)
            out.append(TypeCandidate(InputType.NAME, score, "free-text name regex"))
        if not out:
            out.append(TypeCandidate(InputType.UNKNOWN, 0.05, "no validator matched"))
        return out


def _raw_string(value: str | bytes) -> str:
    return value if isinstance(value, str) else value.decode("latin-1", errors="replace")


_TYPE_ORDER = {t: i for i, t in enumerate(
    (InputType.UNKNOWN, InputType.DOMAIN, InputType.EMAIL, InputType.USERNAME,
     InputType.PHONE, InputType.URL, InputType.IMAGE, InputType.NAME, InputType.DOCUMENT)
)}


def _path_metadata(filename: str | None) -> dict:
    if not filename:
        return {}
    lowered = filename.lower()
    for ext in _IMAGE_EXTENSIONS:
        if lowered.endswith(ext):
            return {"extension": ext, "file_hint": "image"}
    for ext in _DOCUMENT_EXTENSIONS:
        if lowered.endswith(ext):
            return {"extension": ext, "file_hint": "document"}
    return {"extension": "", "file_hint": ""}