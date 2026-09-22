"""Deterministic place extraction via the GeoNames automaton (spec 007, T015/T017).

The cities/countries mini-gazetteer (versioned, content-addressed) is matched
by Aho-Corasick over case-folded text; ru case forms are baked into the dataset,
so "Казани"/"Москву" resolve to their nominative GeoNames entries. Honest
confidence: title/uppercase or country matches score higher than bare lowercase
hits. Every mention records ``dictionary=geonames@<version>`` and the geo-id
(FR-8). No gazetteer match -> no place mention; no ML involved.
"""

from __future__ import annotations

from dictionaries.data import automaton  # type: ignore[import-not-found]
from extractors.matching import match_terms
from extractors.types import TypedMention
from extractors.util import byte_offset

_MIN_TERM_LEN = 3


def extract_places(text: str, lang_hint: str | None = None) -> list[TypedMention]:
    """Deterministic place mentions from an artifact's clean text."""
    meta, automaton_ = automaton("geonames")
    mentions: list[TypedMention] = []
    for start, term, payload in match_terms(automaton_, text):
        if len(term) < _MIN_TERM_LEN and not _strong_country(payload, text, start, len(term)):
            continue
        end = start + len(term)
        surface = text[start:end]
        is_title = surface[:1].isupper()
        kind = str(payload.get("kind", "place"))
        confidence = 0.9 if (kind == "country" or is_title) else 0.6
        evidence: dict[str, object] = {"geo_kind": kind}
        geo_id = payload.get("geo_id")
        if geo_id:
            evidence["geo_id"] = geo_id
        if str(payload.get("country", "")):
            evidence["country"] = payload["country"]
        lat = payload.get("lat")
        lon = payload.get("lon")
        if lat is not None and lon is not None:
            evidence["coords"] = {"lat": lat, "lon": lon}
        mentions.append(
            TypedMention(
                kind="place",
                value=surface,
                offset=byte_offset(text, start),
                end_offset=byte_offset(text, end),
                extractor="places",
                lang=lang_hint,
                source="dictionary",
                confidence=confidence,
                evidence=evidence,
                dictionary=meta.stamp,
            )
        )
    return _dedup(mentions)


def _strong_country(payload: dict, text: str, start: int, length: int) -> bool:
    """Short country codes (RU/US/...) accepted only when uppercase + bounded."""
    if payload.get("kind") != "country":
        return False
    surface = text[start : start + length]
    return surface.isupper()


def _dedup(mentions: list[TypedMention]) -> list[TypedMention]:
    """Deterministic per-offset dedup keeping the first (longest-honest) hit."""
    seen: dict[tuple[int, str], TypedMention] = {}
    for m in sorted(mentions, key=lambda x: (x.offset, x.value)):
        key = (m.offset, m.kind)
        if key not in seen:
            seen[key] = m
    return [seen[k] for k in sorted(seen, key=lambda k: (seen[k].offset, seen[k].value))]