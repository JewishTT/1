"""Normalization post-pass: canonical forms + identity evidence (spec 007, T020/T021, US3).

Pure rules and tables — no ML. Ru declensions collapse to lemmas (pymorphy3),
Cyrillic↔Latin transliteration maps surface variants onto one canonical form,
initials expand into *hypotheses* (``hypothesis=True``, ``credence=null`` —
never resolved claims, I-2), and structured identity links (``sameAs``,
profile URLs) + document-local co-occurrence surface as typed evidence
attributes, feeding the later resolution lane without resolving anything here.
"""

from __future__ import annotations

import hashlib
import re

from dictionaries import cities  # type: ignore[import-not-found]
from dictionaries import first_names as _names  # type: ignore[import-not-found]
from extractors.language import pack_note
from extractors.persons import _parse_ru  # type: ignore[import-untyped]
from extractors.translit import from_latin, transliterate
from extractors.types import NormalizedName, TypedMention

_INITIAL = re.compile(r"^([А-ЯЁ])\.?\s+([А-ЯЁ])\.?\s+(.+)$")
_FAMILY_FIRST_INITIAL = re.compile(r"^(.+?)\s+([А-ЯЁ])\.\s*([А-ЯЁ])\.?$")
_MAX_HYPOTHESES = 8


def normalize_person_name(
    value: str,
    *,
    lang: str | None = None,
    initials: tuple[str, ...] | None = None,
    evidence: dict | None = None,
) -> NormalizedName:
    """Build the canonical form + transform chain for a person mention."""
    evidence = evidence if evidence is not None else {}
    transforms: list[str] = []

    if initials:
        return _initials_hypothesis(value, initials, evidence, transforms)
    if _is_latin(value):
        return _latin_name(value, evidence, transforms)
    from extractors.language import get_pack

    parts = _parse_ru(value, morph=get_pack("ru"))
    if parts is None or not parts.given:
        return _plain_name(value, evidence, transforms)
    return _ru_parts_canonical(parts, value, evidence, transforms)


def _ru_parts_canonical(parts, raw: str, evidence: dict, transforms: list[str]) -> NormalizedName:
    pack, given, family, patronymic = _lemmatize_parts(parts)
    if pack is not None and any(w for w in (given, family, patronymic)):
        transforms.append("pymorphy3-lemma")
    if not family and not given:
        return _plain_name(raw, evidence, transforms)
    canonical = _capitalize(" ".join(p for p in (family, given, patronymic) if p))
    latin = _latin_of(canonical, given)
    if latin != canonical:
        transforms.append("anyascii-web-translit")
    return NormalizedName(
        canonical=canonical,
        latin=latin,
        given=given,
        family=family,
        patronymic=patronymic,
        transforms=transforms,
        hypothesis=False,
    )


def _latin_name(raw: str, evidence: dict, transforms: list[str]) -> NormalizedName:
    from nameparser import HumanName  # type: ignore[import-not-found]

    parsed = HumanName(raw)
    given = parsed.first or ""
    family = parsed.last or ""
    transforms.append("nameparser-segment")
    cyr_given = _names.LATIN_TO_CYRILLIC_FIRST_NAMES.get(parsed.first, from_latin(given))
    cyr_family = from_latin(family)
    canonical = _capitalize(" ".join(p for p in (cyr_family, cyr_given) if p))
    transforms.append("latin-reverse-translit")
    return NormalizedName(
        canonical=canonical,
        latin=_capitalize(f"{family} {given}".strip()),
        given=cyr_given or None,
        family=cyr_family or None,
        transforms=transforms,
        hypothesis=False,
    )


def _lemmatize_parts(parts):
    from extractors.language import get_pack

    pack = get_pack("ru")
    given = _cap(pack.lemmatize(parts.given)) if parts.given else None
    family = _cap(pack.lemmatize(parts.family)) if parts.family else None
    patronymic = _cap(pack.lemmatize(parts.patronymic)) if parts.patronymic else None
    return pack, given or parts.given, family or parts.family, patronymic or parts.patronymic


def _initials_hypothesis(
    raw: str, initials: tuple[str, ...], evidence: dict, transforms: list[str]
) -> NormalizedName:
    transforms.append("initials-expand")
    canonical = f"{_cap_from(raw)} (иниц. {'.'.join(initials)}.)"
    normalized = NormalizedName(
        canonical=canonical,
        family=_family_of_initials(raw),
        given=None,
        patronymic=None,
        transforms=transforms,
        hypothesis=True,
    )
    evidence["expansion_hypotheses"] = _expansion_hypotheses(initials)
    return normalized


def _expansion_hypotheses(initials: tuple[str, ...]) -> list[dict]:
    """Given/patronymic pairs consistent with the initials; credence=null."""
    if len(initials) < 2:
        return []
    g, p = initials[0], initials[1]
    given_hits = sorted(
        n for n in _names.RU_FIRST_NAMES if n.startswith(g)
    )
    patronymic_hits: list[str] = []
    for root in sorted(_names.RU_FIRST_NAMES if not patronymic_hits else []):
        if not root.startswith(p):
            continue
        stem = root[:-1] if root.endswith(("а", "я")) else root
        patr_m = stem + "ович"
        patr_f = stem + "овна"
        if patr_m not in patronymic_hits:
            patronymic_hits.append(patr_m)
        if patr_f not in patronymic_hits:
            patronymic_hits.append(patr_f)
        if len(patronymic_hits) >= 6:
            break
    out: list[dict] = []
    for given in given_hits[: _MAX_HYPOTHESES]:
        for patr in patronymic_hits[: _MAX_HYPOTHESES]:
            out.append({"given": given, "patronymic": patr, "credence": None})
    return sorted(out, key=lambda h: (h["given"], h["patronymic"]))[:_MAX_HYPOTHESES]


def _family_of_initials(raw: str) -> str | None:
    m = _INITIAL.match(raw.strip())
    if m:
        return m.group(3)
    m = _FAMILY_FIRST_INITIAL.match(raw.strip())
    if m:
        return m.group(1)
    return None


def _plain_name(raw: str, evidence: dict, transforms: list[str]) -> NormalizedName:
    return NormalizedName(
        canonical=_cap(raw),
        transforms=[*transforms, "nfc"],
        hypothesis=False,
    )


def _latin_of(canonical: str, given: str | None) -> str:
    parts = canonical.split()
    out = []
    for part in parts:
        mapped = _names.CYRILLIC_TO_LATIN_FIRST_NAMES.get(part) if part in _names.CYRILLIC_TO_LATIN_FIRST_NAMES else None
        out.append(mapped or transliterate(part, variant="web"))
    return _cap(" ".join(out))


def _cap(word: str) -> str:
    return word[:1].upper() + word[1:] if word else word


def _capitalize(value: str) -> str:
    return " ".join(_cap(w) for w in value.split())


def _cap_from(raw: str) -> str:
    for word in raw.split():
        if word and word[0].isalpha():
            return _cap(raw)
    return raw


def _is_latin(value: str) -> bool:
    alpha = [ch for ch in value if ch.isalpha()]
    return bool(alpha) and all("a" <= ch.lower() <= "z" for ch in alpha)


def normalize_pass(
    mentions: list[TypedMention],
    *,
    structured: list[TypedMention] | None = None,
    lang_hint: str | None = None,
) -> list[TypedMention]:
    """Post-pass: canonical forms, evidence attrs, co-occurrence (deterministic)."""
    structured = structured or []
    contact_refs = _contact_refs(mentions)

    out: list[TypedMention] = []
    for m in sorted(mentions, key=lambda x: (x.offset, x.kind, x.value)):
        _apply_normalization(m, lang_hint, contact_refs)
        out.append(m)

    _co_occurrence(out)
    _attach_structured_evidence(out, structured)
    return out


def _apply_normalization(m: TypedMention, lang_hint: str | None, contact_refs: list[str]) -> None:
    if m.kind == "person":
        if m.normalized is None:
            m.normalized = normalize_person_name(
                m.value,
                lang=lang_hint,
                initials=tuple(m.evidence.get("initials", [])),
                evidence=m.evidence,
            )
        if m.evidence.get("initials"):
            m.evidence["hypothesis"] = True
        # Only stamp a tier-1 morphology pack when the language is actually
        # known; unknown scripts (e.g. zh) get the honest typed tier-3 note
        # instead of an unwarranted `pymorphy3@ru` (T027, FR-4 honesty).
        m.lang_pack = pack_note(lang_hint or m.lang)
        if contact_refs:
            m.evidence["contact_hashes"] = _hash_contacts(contact_refs)
        return
    if m.kind == "place":
        if m.normalized is None:
            m.normalized = NormalizedName(canonical=_cap(m.value.casefold()), transforms=["nfc-lower"])
        if "coords" not in m.evidence:
            coords = _city_coords(m.value)
            if coords:
                m.evidence["coords"] = coords
        return
    if m.kind == "email" and m.normalized is None:
        m.normalized = NormalizedName(canonical=m.value.lower(), transforms=["nfc-lower"])
    if m.kind == "handle" and m.normalized is None:
        service = m.evidence.get("service", "social")
        m.normalized = NormalizedName(
            canonical=f"{service}:{m.value.lstrip('@').lower()}", transforms=["nfc-lower"]
        )


def _person_canonical(m: TypedMention, lang_hint: str | None) -> str:
    if m.normalized is not None:
        return m.normalized.canonical
    return normalize_person_name(
        m.value, lang=lang_hint, initials=tuple(m.evidence.get("initials", []))
    ).canonical


def _contact_refs(mentions: list[TypedMention]) -> list[str]:
    refs: list[str] = []
    for m in mentions:
        if m.kind == "person":
            continue
        canonical = m.normalized.canonical if m.normalized else m.value
        if m.kind in {"email", "phone", "handle"}:
            refs.append(canonical)
    return sorted(set(refs))


def _hash_contacts(refs: list[str]) -> list[str]:
    return [hashlib.sha1(r.encode("utf-8")).hexdigest() for r in sorted(refs)]


def _co_occurrence(mentions: list[TypedMention]) -> None:
    persons = [m for m in mentions if m.kind == "person"]
    by_canonical: dict[str, list[TypedMention]] = {}
    for m in persons:
        key = m.normalized.canonical if m.normalized else m.value
        by_canonical.setdefault(key, []).append(m)
    for m in persons:
        values = sorted({c for k, ms in by_canonical.items() for c in [k]})
        others = [k for k in values if k != (m.normalized.canonical if m.normalized else m.value)]
        if others:
            m.evidence["co_occurrence"] = others


def _attach_structured_evidence(
    mentions: list[TypedMention], structured: list[TypedMention]
) -> None:
    """Copy sameAs/profile_urls from structured person mentions onto body matches."""
    src: list[TypedMention] = [m for m in structured if m.kind == "person"]
    if not src:
        return
    for m in mentions:
        if m.kind != "person" or m.normalized is None:
            continue
        for s in src:
            if s.normalized and s.normalized.canonical == m.normalized.canonical:
                merged = {
                    k: (m.evidence.get(k, []) + list(s.evidence.get(k, [])))
                    for k in ("sameAs", "profile_urls")
                }
                m.evidence.update(
                    {k: _unique_list(v) for k, v in merged.items() if v}
                )
                break


def _unique_list(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _city_coords(value: str) -> dict | None:
    for city in cities.CITIES:
        for variant in (*city["case_ru"], city["name"], city["name_ru"]):
            if variant.casefold() == value.casefold():
                return {"lat": city["lat"], "lon": city["lon"]}
    return None