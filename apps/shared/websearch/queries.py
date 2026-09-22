"""Entity → web-search query derivation (feature 010/011, slice web-discovery).

An atomic entity is reduced, in the UI, to an arbitrary set of *identifiers*:
FIO, phone, email, domain, username/handle, crypto address, geo, txid — any
piece of information that points at the entity. This module turns that bag of
identifiers into a bounded, intent-tagged set of search queries: the exact
phrase first (highest signal), then each unique identifier as its own query.

Deterministic and bounded: the same entity always yields the same queries, and
an adversarial bag of identifiers cannot explode query count (dedup by text).
"""

from __future__ import annotations

import re
from collections import OrderedDict

from websearch.contracts import SearchQuery

# Identifier keys we can interpret into a query intent (name is the superset).
_INTENT_BY_KEY: dict[str, str] = {
    "full_name": "entity",
    "name": "entity",
    "names": "entity",
    "alias": "alias",
    "aliases": "alias",
    "phone": "phone",
    "tel": "phone",
    "email": "email",
    "mail": "email",
    "domain": "domain",
    "website": "domain",
    "handle": "handle",
    "username": "handle",
    "user": "handle",
    "crypto": "crypto",
    "address": "crypto",
    "txid": "txid",
    "transaction": "txid",
    "geo": "geo",
    "location": "geo",
    "city": "geo",
    "org": "org",
    "organization": "org",
    "employer": "org",
}

_PHONE_DIGITS = re.compile(r"\D+")
_TOKEN_SPLIT = re.compile(r"[^\w]+", re.I)

_CYRILLIC = re.compile(r"[а-яёА-ЯЁ]")

# Output-level transliteration of Cyrillic → Latin for search-query variants.
# A Russian name like "Олег Тинькофф" also has to be searchable where the
# archive transliterated it ("Oleg Tinkoff"). Order matters: without it, "ё"
# (single key) would be shadowed by "е".
_TRANSLIT: dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def identify_lang(value: str | None) -> str:
    """Best-effort BCP47-ish language hint for a value ("" when unknown).

    Heuristic: Cyrillic → "ru", otherwise "". ``-``/other scripts return "" so
    providers fall back to their marketplace default instead of a wrong locale.
    """
    if not value:
        return ""
    if _CYRILLIC.search(value):
        return "ru"
    return ""


def transliterate(value: str) -> str:
    """Cyrillic → Latin transliteration (search-query variant), no-op otherwise.

    Case-preserving; non-ASCII non-Cyrillic chars are dropped, ASCII latin
    letters/digits/whitespace pass through. Used so the pipeline searches both
    the native spelling and the latinized one search engines actually index.
    """
    out: list[str] = []
    for ch in value:
        low = ch.lower()
        r = _TRANSLIT.get(low)
        if r is not None:
            out.append(r.upper() if ch.isupper() else r)
        elif ch.isascii() and (ch.isalnum() or ch in " -_."):
            out.append(ch)
        # everything else (arabic/han/… without a table) is dropped
    return _as_query("".join(out))


def _as_query(q: str) -> str:
    return " ".join(q.split())


def _phone_to_query(value: str) -> str:
    digits = _PHONE_DIGITS.sub("", value)
    clean = digits if digits.startswith("+") else digits.lstrip("0").strip()
    return _as_query(clean) if clean else _as_query(value)


def entity_identifiers_to_queries(
    identifiers: dict[str, str], *, max_queries: int = 12
) -> list[SearchQuery]:
    """Deterministically materialize search queries from entity identifiers.

    Primary signal is the human name (exact quoted phrase first), then each
    unique identifier tokenized on its own intent. A Cyrillic name also gets a
    latinized variant (``Олег Тинькофф`` → ``"Oleg Tinkoff"``) because search
    engines index the transliteration too. Queries are deduplicated by text
    (adversarial identifier bags cannot explode the query set) and bounded.
    """
    ordered: OrderedDict[str, SearchQuery] = OrderedDict()

    def _push(text: str, intent: str, weight: float, lang: str = "") -> None:
        text = _as_query(text)
        if not text or text in ordered:
            return
        ordered[text] = SearchQuery(text=text, intent=intent, weight=weight, lang=lang)

    # 1) The name always goes first, quoted for exact-match signal.
    name = identifiers.get("full_name") or identifiers.get("name") or identifiers.get("names")
    lang = identify_lang(name)
    if name:
        _push(f'"{name}"', "entity", 1.5, lang=lang)
        latin = transliterate(name)
        # bilingual: also probe the transliterated spelling (lower weight).
        if latin and latin.lower() != _as_query(name).lower():
            _push(f'"{latin}"', "entity", 1.1, lang="" if lang else "en")

    # 2) Every identifier in a deterministic order (insertion order of the dict
    #    is meaningful — the UI's "primary identity" comes first).
    for key, value in identifiers.items():
        norm = _as_query(str(value))
        if not norm or norm == _as_query(name or ""):
            continue
        intent = _INTENT_BY_KEY.get(key, "entity")
        qlang = identify_lang(str(value)) or lang
        if intent == "phone":
            norm = _phone_to_query(str(value))
            if not norm:
                continue
            _push(norm, "phone", 1.2, lang=qlang)
        elif intent == "entity":
            _push(f'"{norm}"', "alias" if key in ("alias", "aliases") else "entity", 1.0, lang=qlang)
        else:
            _push(norm, intent, 1.0, lang=qlang)

    # 3) Deterministic selection: first N by intent priority, then positional.
    priority = {
        "entity": 0,
        "alias": 1,
        "phone": 2,
        "email": 3,
        "domain": 4,
        "handle": 5,
        "crypto": 6,
        "txid": 7,
        "geo": 8,
        "org": 9,
    }
    ranked = sorted(ordered.values(), key=lambda q: (priority.get(q.intent, 99), q.weight))
    return ranked[: max(1, max_queries)]


def identifiers_to_tokens(identifiers: dict[str, str]) -> str:
    """Single line of normalized identifier tokens for snippet/exact matching."""
    seen: OrderedDict[str, bool] = OrderedDict()
    for value in identifiers.values():
        for tok in _TOKEN_SPLIT.sub(" ", str(value)).lower().split():
            seen[tok] = True
    return " ".join(seen)
