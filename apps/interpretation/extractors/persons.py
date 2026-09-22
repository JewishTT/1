"""Deterministic person extraction, invariant across ML (spec 007, T014/T016).

No neural/statistical models: three rule layers — name-shape grammar patterns
(initials + full + comma forms for ru; title-case windows for en), morphology
validation via the ru pack (pymorphy3 proper-noun tags), and first-name /
surname dictionary evidence. Matches that only pattern-match are emitted with
``source=pattern`` and reduced confidence — never dropped, never resolved
(FR-4, I-2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from dictionaries import first_names as _names  # type: ignore[import-not-found]
from extractors.language import get_pack
from extractors.types import TypedMention
from extractors.util import byte_offset

_RU_UPPER = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЫЭЮЯ"
_NAME_WORD = rf"[{_RU_UPPER}][а-яёА-ЯЁ'-]+"
_INITIAL = rf"[{_RU_UPPER}]\."
_SPACE = r"\s*"

# И. О. Фамилия  |  Фамилия И. О.  |  Фамилия, Имя Отчество  |  Имя Отчество Фамилия
_PATTERNS_RU = [
    re.compile(
        rf"(?<![\wА-ЯЁа-яё])(?:{_INITIAL}{_SPACE}){{1,2}}{_NAME_WORD}"
        rf"|[А-ЯЁ][а-яё'-]+(?:{_SPACE}{_INITIAL}){{1,2}}{_SPACE}{_INITIAL}"
    ),
    re.compile(r"\b([А-ЯЁ][а-яё'-]+)\s*,\s*([А-ЯЁ][а-яё]+)(?:\s+([А-ЯЁ][а-яё]+))?"),
    re.compile(rf"(?<![А-ЯЁа-яё])({_NAME_WORD})\s+({_NAME_WORD})\s+({_NAME_WORD})(?![-А-ЯЁа-яё])"),
    # Declined two-word full names ("Сергеем Ивановым") — conservative fallback:
    # morphology-validated, and never a sub-slice of a longer matched name.
    re.compile(rf"(?<![А-ЯЁа-яё])({_NAME_WORD})\s+({_NAME_WORD})(?![-А-ЯЁа-яё])"),
]

_WORD = r"[A-Za-z][A-Za-z'-]*"
_TITLE_WORD = r"[A-Z][a-z'\-]+"
_TITLE_WINDOW = re.compile(rf"\b(?:{_TITLE_WORD})(?:\s+{_TITLE_WORD}){{1,3}}\b")

# Words that reliably open English place names / orgs, never person names.
_EN_SKIP_WORDS = frozenset(
    ["saint", "new", "north", "south", "east", "west", "mount", "lake", "sea", "fort", "federal", "university", "institute", "ministry", "academy", "the", "of", "and", "in", "on", "foundation", "society"]
)
_EN_ORG_SUFFIX = re.compile(
    r"(University|Institute|Inc\.?|Corp\.?|Ltd\.?|LLC|LLP|Academy|Ministry|Foundation)$", re.IGNORECASE
)


@dataclass
class _NameParts:
    family: str | None = None
    given: str | None = None
    patronymic: str | None = None
    initials: tuple[str, ...] = ()


def _capital(word: str) -> str:
    return word[:1].upper() + word[1:] if word else word


def _is_ru_patronymic(word: str) -> bool:
    return word.lower().endswith(_names.PATRONYMIC_ENDINGS)


def _parse_ru(raw: str, *, morph=None) -> _NameParts | None:
    """Split a ru name surface into parts by shape grammar (deterministic).

    When a morphology pack is available, three-word surfaces are disambiguated
    by proper-noun role: ``Иванов Сергей Петрович`` is Surn/Name/Patr and is
    family-first, not the naive given/patronymic/family order.
    """
    if "," in raw:
        family, rest = raw.split(",", 1)
        tokens = rest.strip().split()
        given = tokens[0] if tokens else None
        patronymic = tokens[1] if len(tokens) > 1 else None
        return _NameParts(family=family.strip(), given=given, patronymic=patronymic)
    initials: list[str] = []
    words: list[str] = []
    for tok in re.split(r"\s+", raw.replace(".", " . ")):
        if tok.strip(" .") and tok.strip(".").isalpha() and len(tok.strip(".")) == 1:
            if tok.strip(".").isupper() and tok.strip(".") in _RU_UPPER:
                initials.append(tok.strip("."))
        elif len(tok) > 1 and tok.isupper() and tok in ("И", "О", "П"):
            initials.append(tok)
        elif re.fullmatch(rf"{_NAME_WORD}[.]?", tok):
            words.append(tok)
    if not words:
        return None
    if initials:
        if len(words) == 1:
            return _NameParts(family=words[0].rstrip("."), initials=tuple(initials))
        return _NameParts(family=words[-1].rstrip("."), given=words[0], initials=tuple(initials))
    if len(words) == 2:
        if morph is not None:
            roles = [morph.word_role(w) for w in words]
            if roles.count("family") == 1 and roles.count("given") == 1 and roles.index("family") == 0:
                return _NameParts(family=words[0], given=words[1])
        return _NameParts(given=words[0], family=words[1])
    if len(words) >= 3:
        first_three = words[:3]
        roles = []
        if morph is not None:
            roles = [morph.word_role(w) for w in first_three]
        if roles.count("family") == 1 and roles.count("given") == 1 and roles.count("patronymic") == 1:
            return _NameParts(
                family=first_three[roles.index("family")],
                given=first_three[roles.index("given")],
                patronymic=first_three[roles.index("patronymic")],
            )
        # Fallback: "Имя Отчество Фамилия" ordering (e.g. "Сергей Петрович Иванов").
        return _NameParts(given=words[0], patronymic=words[1], family=words[2])
    return None


def _ru_validation(
    parts: _NameParts, *, first_names: set[str], surnames: set[str], morph
) -> tuple[str, float]:
    """Honest confidence/source: dictionary > morph > pattern."""
    if parts.given and _capital(parts.given).casefold() in first_names:
        return "dictionary", 0.9
    if parts.family and parts.family.casefold() in surnames:
        return "dictionary", 0.9
    proper = 0
    for word in (parts.family, parts.given, parts.patronymic):
        if not word:
            continue
        if _capital(word).casefold() in first_names or word.casefold() in surnames:
            proper += 2
        elif _is_ru_patronymic(word) or morph.analyzer_parse_name(word):
            proper += 1
    if proper >= 3:
        return "morph", 0.7
    if proper >= 2:
        return "pattern", 0.6
    return "pattern", 0.5


def _ru_mentions(
    text: str, *, lang: str, first_names: set[str], surnames: set[str], morph, gazetteer: set[str]
) -> list[TypedMention]:
    out: list[TypedMention] = []
    captured: list[tuple[int, int]] = []
    for index, pattern in enumerate(_PATTERNS_RU):
        multi_word = index >= 2
        is_fallback = index == len(_PATTERNS_RU) - 1
        for m in pattern.finditer(text):
            raw = m.group(0).strip(" ,.")
            if not raw or " " not in raw:
                continue
            if is_fallback and _overlaps(m.start(), m.end(), captured):
                continue  # sub-slices of longer names are not separate entities
            if multi_word and _titular_phrase(raw, gazetteer):
                continue  # "Казанский федеральный университет" is not a person
            parts = _parse_ru(raw, morph=morph)
            if parts is None or parts.given is None and parts.initials == ():
                continue
            source, confidence = _ru_validation(parts, first_names=first_names, surnames=surnames, morph=morph)
            if is_fallback and confidence < 0.55:
                continue  # declension-only candidates still need morphology evidence
            evidence: dict = {"shape": "ru"}
            if parts.initials:
                evidence["initials"] = list(parts.initials)
            if not is_fallback:
                captured.append((m.start(), m.end()))
            out.append(
                TypedMention(
                    kind="person",
                    value=raw,
                    offset=byte_offset(text, m.start()),
                    end_offset=byte_offset(text, m.end()),
                    extractor="persons",
                    lang=lang,
                    source=source,
                    confidence=confidence,
                    evidence=evidence,
                )
            )
    return out


_RU_TITULAR_TAILS = frozenset(
    ["университет", "академия", "институт", "министерство", "фонд", "компания", "завод", "фабрика", "банк", "корпорация", "корпорации", "госкорпорация", "госкомитет", "край", "область", "республика", "центр", "школа", "лицей", "гимназия", "отель", "гостиница", "аэропорт", "вокзал", "станция", "улица", "проспект", "площадь", "набережная", "парк", "музей", "театр", "опера", "мост", "завод"]
)


def _titular_phrase(raw: str, gazetteer: set[str]) -> bool:
    words = raw.split()
    if not words:
        return False
    if words[-1].casefold() in _RU_TITULAR_TAILS:
        return True
    return any(w.casefold() in gazetteer for w in words)


def _overlaps(start: int, end: int, captured: list[tuple[int, int]]) -> bool:
    return any(cs < end and start < ce for cs, ce in captured)


def en_name_from_window(raw: str) -> tuple[str, str, bool]:
    """(given, family, dict_hit) via nameparser; empty tuple when not a name."""
    from nameparser import HumanName  # type: ignore[import-not-found]

    parsed = HumanName(raw)
    return parsed.first or "", parsed.last or "", bool(parsed.first and parsed.last)


def _en_mentions(text: str, *, lang: str, first_names: set[str], gazetteer: set[str]) -> list[TypedMention]:
    out: list[TypedMention] = []
    for m in _TITLE_WINDOW.finditer(text):
        raw = m.group(0).strip(" ,.")
        words = raw.split()
        if len(words) < 2:
            continue
        if words[0].lower() in _EN_SKIP_WORDS or words[-1].lower() in _EN_SKIP_WORDS:
            continue
        if _EN_ORG_SUFFIX.search(words[-1]):
            continue
        if raw.casefold() in gazetteer or any(w.lower() in gazetteer for w in words):
            continue
        given, _family, is_name = en_name_from_window(raw)
        if not is_name:
            continue
        dict_hit = given.lower() in first_names
        if not dict_hit and len(words) > 2:
            continue  # "Kazan Federal University"-class false positives need name evidence
        source = "morph" if dict_hit else "pattern"
        confidence = 0.85 if dict_hit else 0.55
        out.append(
            TypedMention(
                kind="person",
                value=raw,
                offset=byte_offset(text, m.start()),
                end_offset=byte_offset(text, m.end()),
                extractor="persons",
                lang=lang,
                source=source,
                confidence=confidence,
                evidence={"shape": "latin"},
            )
        )
    return out


def _gazetteer_terms() -> set[str]:
    """Lowercased place terms, lazily resolved (used to reject place-like windows)."""
    try:
        from datasets import iter_entries

        from dictionaries.data import dataset_root

        root = dataset_root()
        path = root / "geonames_2026.08.jsonl"
        if not path.exists():
            return set()
        return {str(e.get("term", "")).casefold() for e in iter_entries(path)}
    except Exception:  # noqa: BLE001 - gazetteer absence only weakens the filter
        return set()


def extract_persons(text: str, lang_hint: str | None = None) -> list[TypedMention]:
    """Deterministic person mentions from running text (ru/en)."""
    first_ru = {n.casefold() for n in _names.RU_FIRST_NAMES}
    first_en = {n.casefold() for n in _names.EN_FIRST_NAMES}
    surnames = {e["term"].casefold() for e in _names.surname_entries()}
    mentions: list[TypedMention] = []
    has_cyr = _has_cyrillic(text)
    has_latin = _has_latin(text)

    if _wants_ru(lang_hint, has_cyr):
        morph = get_pack("ru")
        mentions.extend(
            _ru_mentions(
                text,
                lang=lang_hint or "ru",
                first_names=first_ru,
                surnames=surnames,
                morph=morph,
                gazetteer=_gazetteer_terms(),
            )
        )
    if _wants_en(lang_hint, has_cyr, has_latin):
        mentions.extend(
            _en_mentions(
                text,
                lang=lang_hint or "en",
                first_names=first_en,
                gazetteer=_gazetteer_terms(),
            )
        )
    return _dedup(mentions)


def _wants_ru(lang_hint: str | None, has_cyr: bool) -> bool:
    if lang_hint == "ru":
        return True
    if lang_hint is None:
        return has_cyr
    return False


def _wants_en(lang_hint: str | None, has_cyr: bool, has_latin: bool) -> bool:
    if lang_hint == "en":
        return True
    if lang_hint is None:
        return has_latin and not has_cyr
    return False


def _has_cyrillic(text: str) -> bool:
    return any("\u0400" <= ch <= "\u04FF" for ch in text)


def _has_latin(text: str) -> bool:
    return any(ch.isalpha() and "a" <= ch.lower() <= "z" for ch in text)


def _dedup(mentions: list[TypedMention]) -> list[TypedMention]:
    """Deterministic dedup: keep first mention per (offset, kind, value)."""
    seen: dict[tuple[int, str], TypedMention] = {}
    for m in sorted(mentions, key=lambda x: (x.offset, x.value, x.kind)):
        key = (m.offset, m.kind)
        if key in seen:
            continue
        seen[key] = m
    return [seen[k] for k in sorted(seen, key=lambda k: (seen[k].offset, seen[k].value))]