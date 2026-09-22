"""Deterministic Cyrillic↔Latin transliteration (spec 007, R-7, US3).

Pinned pure-python tables — no runtime dependency beyond ``anyascii`` for the
universal (ISC) fallback used by language tiers 2/3. Root variant: GOST 7.79
system-B style; a ``WEB_COMMON`` table covers the most common informal web
spellings (ё→e, й→y, ы→y). Reverse tables drive latin→cyrillic recovery used
by name normalization ("Sergey Ivanov" → "Иванов Сергей").
"""

from __future__ import annotations

import anyascii as _anyascii  # type: ignore[import-not-found]

gost_map = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}
# Common web variants for the human-friendly surface latin form.
web_map = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}

_cyr_single = {
    "a": "а", "b": "б", "c": "ц", "d": "д", "e": "е", "f": "ф", "g": "г",
    "h": "х", "i": "и", "j": "й", "k": "к", "l": "л", "m": "м", "n": "н",
    "o": "о", "p": "п", "r": "р", "s": "с", "t": "т", "u": "у", "v": "в",
    "z": "з", "x": "кс",
}
_cyr_multigram = [
    ("shch", "щ"), ("sh", "ш"), ("ch", "ч"), ("ts", "ц"), ("zh", "ж"),
    ("yu", "ю"), ("ya", "я"), ("yo", "ё"), ("kh", "х"), ("ey", "ей"),
]


def transliterate(text: str, variant: str = "gost") -> str:
    """Cyrillic → Latin. ``variant`` is ``gost`` or ``web`` (deterministic).

    Table keys are lowercase; case is restored per character so title-case
    input like ``Иванов`` maps correctly (``И`` → ``I``).
    """
    table = gost_map if variant == "gost" else web_map
    out: list[str] = []
    for ch in text:
        mapped = table.get(ch.lower())
        if mapped is None:
            out.append(ch)
        elif ch.isupper():
            out.append(mapped.capitalize())
        else:
            out.append(mapped)
    return "".join(out)


def from_latin(text: str) -> str:
    """Latin → Cyrillic; multi-char clusters resolved longest-first."""
    if not text:
        return text
    out: list[str] = []
    i = 0
    lower = text.lower()
    while i < len(text):
        matched = False
        for prefix, cyr in _cyr_multigram:
            if lower.startswith(prefix, i):
                piece = text[i : i + len(prefix)]
                out.append(cyr.upper() if piece[0].isupper() else cyr)
                i += len(prefix)
                matched = True
                break
        if matched:
            continue
        char = text[i]
        cyr_char = _cyr_single.get(char.lower(), char)
        if char.isupper() and cyr_char.isalpha():
            cyr_char = cyr_char.upper()
        out.append(cyr_char)
        i += 1
    return "".join(out)


def universal(text: str) -> str:
    """Universal (ISC anyascii) transliteration for tiers 2/3."""
    return _anyascii.anyascii(text)