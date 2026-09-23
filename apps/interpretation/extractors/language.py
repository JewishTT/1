"""Charset + language tiers (spec 007, T026/T027, US5, FR-7).

Charset detection always precedes decoding (charset-normalizer, no blind
utf-8-replace). Language tagging is heuristic — script ranges + stopword
counts, no model. Morphology packs are swappable and tiered:

- tier 1: ru (pymorphy3) and en (nameparser shapes) — full normalization.
- tier 2/3: universal structural/dictionary extraction; when no pack is
  installed a typed ``lang_pack`` note is recorded (never a silent zero).
"""

from __future__ import annotations

import codecs
import re
import threading
from dataclasses import dataclass
from typing import Protocol

import charset_normalizer  # type: ignore[import-not-found]

_CYRILLIC = "\u0400\u04FF"
_UTF8_FAMILY = frozenset({"utf-8", "utf8", "utf", "us-ascii", "ascii", "unicode-1-1-utf-8"})
_HTML_GUARD = rb"(?:<html|<head|<body|<!doctype)"
_CHARSET_META = re.compile(
    rb"(?:<meta[^>]+charset\s*=\s*[\"']?\s*|charset\s*=\s*)([a-zA-Z0-9._+-]+)",
    re.IGNORECASE,
)


def _declared_charset(data: bytes) -> str | None:
    """Charset declared in an HTML payload head (deterministic, None otherwise)."""
    if not re.search(_HTML_GUARD, data[:2048], re.IGNORECASE):
        return None
    match = _CHARSET_META.search(data[:4096])
    if match is None:
        return None
    codec = match.group(1).decode("ascii", errors="ignore").strip()
    try:
        codecs.lookup(codec)
    except (LookupError, ValueError):
        return None
    return codec


def _decode_clean(data: bytes, codec: str) -> str | None:
    """Decode with ``codec`` only when it produces no replacement chars."""
    try:
        text = data.decode(codec)
    except (UnicodeDecodeError, LookupError, ValueError):
        return None
    if "\ufffd" in text:
        return None
    return text


def decode_bytes(data: bytes) -> tuple[str, str]:
    """Decode bytes using detected charset; returns (text, charset_name).

    Deterministic: same bytes → same detection result (charset-normalizer is
    a pure heuristic with a stable best() choice for a given input). An HTML
    payload that DECLARES a single-byte charset is honored — but only when the
    bytes are not valid UTF-8, so a stale/mislabeled UTF-8 page ("windows-1251"
    over real UTF-8 bytes) still decodes correctly instead of becoming mojibake.
    """
    if not data:
        return "", "utf-8"
    declared = _declared_charset(data)
    is_utf8 = _decode_clean(data, "utf-8")
    if is_utf8 is None and declared is not None and declared.lower() not in _UTF8_FAMILY:
        decoded = _decode_clean(data, declared)
        if decoded is not None:
            return decoded, declared
    try:
        best = charset_normalizer.from_bytes(data).best()
    except Exception:  # noqa: BLE001 - a detection failure never kills the lane
        best = None
    if best is not None:
        text = best.output().decode("utf-8", errors="replace")
        return text, best.encoding
    return data.decode("utf-8", errors="replace"), "utf-8"


def script_ratio(text: str) -> float:
    """Fraction of chars in the Cyrillic block (0.0..1.0)."""
    if not text:
        return 0.0
    letters = sum(1 for ch in text if ch.isalpha())
    if not letters:
        return 0.0
    cyr = sum(1 for ch in text if _CYRILLIC[0] <= ch <= _CYRILLIC[1])
    return cyr / letters


_EN_STOPWORDS = frozenset(
    ["the", "a", "an", "and", "of", "to", "in", "on", "for", "with", "at", "by", "from", "as", "is", "are", "was", "were", "he", "she", "it", "they", "this", "that", "his", "her", "their", "who", "what", "when", "where", "which", "born", "lives", "works", "contact"]
)
_RU_STOPWORDS = frozenset(
    ["и", "в", "во", "на", "с", "со", "по", "из", "за", "у", "от", "для", "о", "об", "при", "к", "до", "бы", "не", "же", "его", "её", "их", "нам", "вас", "это", "этот", "тот", "что", "как", "который", "года", "году", "живёт", "работает", "контакт", "тел"]
)


def detect_language(text: str) -> str | None:
    """Heuristic language tag: 'ru' / 'en' / None (script + stopwords)."""
    words = text.lower().split()
    if not words:
        return None
    ratio = script_ratio(text)
    if ratio > 0.3:
        en_hits = sum(1 for w in words if w in _EN_STOPWORDS)
        ru_hits = sum(1 for w in words if w in _RU_STOPWORDS)
        return "en" if en_hits > ru_hits * 2 else "ru"
    en_hits = sum(1 for w in words if w in _EN_STOPWORDS)
    if en_hits >= 1:
        return "en"
    return None


class MorphologyPack(Protocol):
    """Tier interface: language-specific morphology & name parsing."""

    name: str
    tier: int
    language: str

    def is_name_word(self, word: str) -> bool: ...
    def lemmatize(self, word: str) -> str | None: ...
    def word_role(self, word: str) -> str | None:
        """Optional: 'given'|'family'|'patronymic' for a proper-noun word."""
        return None


@dataclass(frozen=True)
class _NoPack:
    """Typed absence of a morphology pack (honest tier2/3 note)."""

    name: str
    tier: int
    language: str

    def is_name_word(self, word: str) -> bool:
        return False

    def lemmatize(self, word: str) -> str | None:
        return None

    def word_role(self, word: str) -> str | None:
        return None


class _RussianPack:
    name = "pymorphy3"
    tier = 1
    language = "ru"

    _morph = None
    _lock = threading.Lock()

    @classmethod
    def _analyzer(cls):
        import pymorphy3  # type: ignore[import-not-found]

        with cls._lock:
            if cls._morph is None:
                cls._morph = pymorphy3.MorphAnalyzer()  # lazy singleton (NFR-2)
        return cls._morph

    def lemmatize(self, word: str) -> str | None:
        if not word:
            return None
        try:
            return self._analyzer().parse(word)[0].normal_form or None
        except Exception:  # noqa: BLE001 - morphology must never crash the lane
            return None

    def is_name_word(self, word: str) -> bool:
        if not word:
            return False
        try:
            tags = self._analyzer().parse(word)
        except Exception:  # noqa: BLE001
            return False
        return any("Name" in (t.tag or "") for t in tags[:4])

    def analyzer_parse_name(self, word: str) -> bool:
        """True when the word parses as a proper noun (Name/Surn tag)."""
        if not word:
            return False
        try:
            tags = self._analyzer().parse(word)
        except Exception:  # noqa: BLE001
            return False
        tag_text = " ".join(str(t.tag or "") for t in tags[:4])
        return "Name" in tag_text or "Surn" in tag_text

    def word_role(self, word: str) -> str | None:
        """Word role: 'given' | 'family' | 'patronymic' | None (deterministic).

        Feeds ФИО order disambiguation: ``Иванов Сергей Петрович`` unambiguously
        has Surn/Name/Patr roles even though the surface order is family-first.
        """
        if not word:
            return None
        try:
            tags = self._analyzer().parse(word)
        except Exception:  # noqa: BLE001
            return None
        for t in tags[:4]:
            tag_text = str(t.tag or "")
            if "Patr" in tag_text:
                return "patronymic"
            if "Surn" in tag_text:
                return "family"
            if "Name" in tag_text:
                return "given"
        return None


class _EnglishPack:
    name = "nameparser"
    tier = 1
    language = "en"

    def is_name_word(self, word: str) -> bool:
        from nameparser import HumanName  # type: ignore[import-not-found]

        parsed = HumanName(word)
        return bool(word) and word[0].isupper() and bool(parsed.first)

    def lemmatize(self, word: str) -> str | None:
        return None

    def word_role(self, word: str) -> str | None:
        return None


_TIER_NOTES = {
    "en": _EnglishPack(),
    "ru": _RussianPack(),
}


def get_pack(language: str | None) -> MorphologyPack | _NoPack:
    """Return the morphology pack for a language (tier 1) or a typed absence."""
    if language in _TIER_NOTES:
        return _TIER_NOTES[language]
    if language in {"uk", "pl", "de", "fr", "es", "tr", "it", "pt", "nl"}:
        return _NoPack(name=f"tier2-structural@{language}", tier=2, language=language or "")
    return _NoPack(name=f"tier3-dictionary@{language or 'unknown'}", tier=3, language=language or "")


def pack_note(language: str | None, *, lang_tag: str | None = None) -> str | None:
    """Morphology pack string stamped on mentions (e.g. ``pymorphy3@ru``).

    Tier-1 packs carry ``<tool>@<lang>``; tier-2/3 notes already embed the
    language in their name (``tier2-structural@de``, ``tier3-dictionary@zh``)
    so no second ``@<tag>`` is appended (a double tag would be noise, not a
    typed absence). ``lang_tag`` is kept for backward call-compatibility only.
    """
    pack = get_pack(language)
    if pack.tier == 1:
        return f"{pack.name}@{pack.language}"
    return f"{pack.name}"