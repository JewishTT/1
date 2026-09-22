"""Dictionary-entity extraction: OpenSanctions-derived matcher (spec 007, T015/T018).

Matches entity names in narrative text against the versioned mini sanctions
dictionary and stamps every hit with ``dictionary=sanctions@<version>`` and the
entity id as evidence (FR-8). The extractor only *mentions* — it never resolves
or scores anyone (I-2, B-1).
"""

from __future__ import annotations

from dictionaries.data import automaton  # type: ignore[import-not-found]
from extractors.matching import match_terms
from extractors.types import TypedMention
from extractors.util import byte_offset

_KIND_BY_SCHEMA = {
    "Person": "person",
    "Organization": "org",
}


def extract_dictionary_entities(text: str, lang_hint: str | None = None) -> list[TypedMention]:
    """Deterministic sanctions-dictionary entity mentions."""
    meta, automaton_ = automaton("sanctions")
    mentions: list[TypedMention] = []
    for start, term, payload in match_terms(automaton_, text):
        end = start + len(term)
        surface = text[start:end]
        schema = str(payload.get("schema", ""))
        kind = _KIND_BY_SCHEMA.get(schema, "entity")
        evidence: dict[str, object] = {"dictionary_source": payload.get("source", "opensanctions")}
        entity_id = payload.get("id")
        if entity_id:
            evidence["entity_id"] = entity_id
        mentions.append(
            TypedMention(
                kind=kind,
                value=surface,
                offset=byte_offset(text, start),
                end_offset=byte_offset(text, end),
                extractor="sanctions",
                lang=lang_hint,
                source="dictionary",
                confidence=1.0,
                evidence=evidence,
                dictionary=meta.stamp,
            )
        )
    return _dedup(mentions)


def _dedup(mentions: list[TypedMention]) -> list[TypedMention]:
    seen: dict[tuple[int, str], TypedMention] = {}
    for m in sorted(mentions, key=lambda x: (x.offset, x.value, x.dictionary or "")):
        key = (m.offset, m.kind)
        if key not in seen:
            seen[key] = m
    return [seen[k] for k in sorted(seen, key=lambda k: (seen[k].offset, seen[k].value))]