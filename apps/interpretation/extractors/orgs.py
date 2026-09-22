"""Deterministic organization extraction (spec 007, org extractor).

Two deterministic layers: the companies dictionary automaton (RU+EN, includes
declined Russian forms) and shape grammars — capitalized sequences ending an
org keyword (Университет/Институт/Ltd/GmbH…) or quoted «…» names. Dictionary
hits carry the dataset stamp; grammar-only hits are emitted as
``source=pattern`` with reduced confidence (FR-4).
"""

from __future__ import annotations

import re

from dictionaries.data import automaton  # type: ignore[import-not-found]
from extractors.matching import match_terms
from extractors.types import TypedMention
from extractors.util import byte_offset

_RU_KEYWORDS = r"(?:Институт[ауе]{0,2}|Академи[ияюе]{1,2}|Университет[ауе]{0,2}|Банк[ауе]{0,2}|Завод|Фонд[ае]{0,1}|Компани[ияю]{1,2}|Сервис)"
_RU_END_KEYWORD = re.compile(
    rf"\b([А-ЯЁ][а-яёЁ-]+(?:\s+[А-ЯЁ][а-яёЁ-]+)*)\s+({_RU_KEYWORDS})\b"
)
_RU_LEGAL_FORM = re.compile(
    r"\b(?:ООО|ОАО|ПАО|АО|ЗАО|НПО|ГК|НИИ)\s+«?[А-ЯЁ][^.,;(]{2,60}\b"
)
_RU_QUOTED = re.compile(r"«[^»]{3,60}»")
_EN_CONNECTOR = r"(?:\s+(?:of|and|the|for|in))?"
_EN_ORG_WORD = r"[A-Z][A-Za-z0-9&.'-]+"
_EN_ORG = re.compile(
    rf"\b(?:{_EN_ORG_WORD}{_EN_CONNECTOR}\s+){{1,4}}"
    rf"(?:Inc\.?|Corporation|Corp\.?|Ltd\.?|LLC|LLP|GmbH|PLC|University|Institute|"
    rf"Academy|Foundation|Ministry|Bank|Group|School)\b"
)


def extract_organizations(text: str, lang_hint: str | None = None) -> list[TypedMention]:
    """Deterministic org mentions from clean text (dict + grammar layers)."""
    mentions = _dictionary_layer(text, lang_hint)
    mentions += _grammar_layer(text, lang_hint)
    return _dedup(mentions)


def _dictionary_layer(text: str, lang_hint: str | None) -> list[TypedMention]:
    meta, automaton_ = automaton("companies")
    out: list[TypedMention] = []
    for start, term, payload in match_terms(automaton_, text):
        end = start + len(term)
        surface = text[start:end]
        evidence: dict[str, object] = {"company": payload.get("name", surface)}
        if payload.get("domain"):
            evidence["domain"] = payload["domain"]
        if payload.get("country"):
            evidence["country"] = payload["country"]
        out.append(
            TypedMention(
                kind="org",
                value=surface,
                offset=byte_offset(text, start),
                end_offset=byte_offset(text, end),
                extractor="organizations",
                lang=lang_hint,
                source="dictionary",
                confidence=0.9,
                evidence=evidence,
                dictionary=meta.stamp,
            )
        )
    return out


def _grammar_layer(text: str, lang_hint: str | None) -> list[TypedMention]:
    out: list[TypedMention] = []
    for m in _RU_END_KEYWORD.finditer(text):
        raw = m.group(0).strip(" .,;")
        if len(raw.split()) < 2:
            continue
        out.append(
            TypedMention(
                kind="org",
                value=raw,
                offset=byte_offset(text, m.start()),
                end_offset=byte_offset(text, m.end()),
                extractor="organizations",
                lang=lang_hint,
                source="pattern",
                confidence=0.6,
            )
        )
    for pattern in (_RU_LEGAL_FORM, _RU_QUOTED):
        for m in pattern.finditer(text):
            raw = m.group(0).strip(" .,;")
            if raw and len(raw) >= 3:
                out.append(
                    TypedMention(
                        kind="org",
                        value=raw,
                        offset=byte_offset(text, m.start()),
                        end_offset=byte_offset(text, m.end()),
                        extractor="organizations",
                        lang=lang_hint,
                        source="pattern",
                        confidence=0.55,
                    )
                )
    for m in _EN_ORG.finditer(text):
        raw = m.group(0).strip(" .,;")
        if len(raw.split()) < 2:
            continue
        out.append(
            TypedMention(
                kind="org",
                value=raw,
                offset=byte_offset(text, m.start()),
                end_offset=byte_offset(text, m.end()),
                extractor="organizations",
                lang=lang_hint,
                source="pattern",
                confidence=0.5,
            )
        )
    return out


def _dedup(mentions: list[TypedMention]) -> list[TypedMention]:
    seen: dict[tuple[int, str], TypedMention] = {}
    for m in sorted(mentions, key=lambda x: (x.offset, x.value)):
        key = (m.offset, m.kind)
        if key not in seen or (m.source == "dictionary" and seen[key].source != "dictionary"):
            seen[key] = m
    return [seen[k] for k in sorted(seen, key=lambda k: (seen[k].offset, seen[k].value))]