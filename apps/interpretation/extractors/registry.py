"""Extractor registry (T033, FR-011).

Turn parser segments into typed entities: persons, orgs, indicators (IP/URL/hash/
email/domain/CVE), temporal expressions, geolocations. Each extractor returns
typed mentions; the registry fans a segment across all applicable extractors and
tags output with a stable source id.

Spec 007 (deterministic extraction stack): this module also exposes
``DeterministicExtractorSet`` — the deterministic post-processor that runs the
no-ML extractors (persons, places, orgs, dictionary entities, contacts) over a
decoded segment and returns spec ``TypedMention`` records.
``register_deterministic_extractors`` additionally mirrors the deterministic
extractors into the legacy fan-out registry as stable ``Mention`` producers.

Spec 017 (semantic fabric, FR-002): the world is open. A bound ``OntologyPack`` is
a *hint* surface only — it annotates each mention with what the pack recognizes,
and it can never drop, filter or reject one. An unknown, unregistered or typeless
kind is admitted carrying the absence of semantic commitment as a hint.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from extractors import contacts, dictionary_entities, orgs, persons, places
from extractors.types import TypedMention


@dataclass
class Mention:
    kind: str
    value: str
    offset: int = 0
    confidence: float = 1.0
    attrs: dict[str, str] = field(default_factory=dict)


Extractor = Callable[[str], list[Mention]]


@dataclass(frozen=True)
class SemanticHint:
    """What an ontology pack knows about one kind — a hint, never a verdict.

    ``recognized`` is ranking/expansion input for downstream consumers and the
    record that semantic commitment was (or was not) made. A pack that does not
    know a kind yields ``recognized=False``, which is a legitimate state, not a
    rejection: nothing here can refuse a mention.
    """

    kind: str = ""
    recognized: bool = False
    pack_id: str | None = None
    pack_version: str | None = None

    @property
    def flag(self) -> str:
        return "recognized" if self.recognized else "unrecognized"


def semantic_hint(pack: Any, kind: str | None) -> SemanticHint | None:
    """Ask ``pack`` what it knows about ``kind``; ``None`` when no pack is bound.

    An empty or absent kind is reported as unrecognized rather than raising, so a
    typeless mention is hinted like any other unknown kind instead of vanishing.
    """
    if pack is None:
        return None
    name = (kind or "").strip()
    return SemanticHint(
        kind=name,
        recognized=bool(name) and bool(pack.allows_type(name)),
        pack_id=getattr(pack, "pack_id", None),
        pack_version=getattr(pack, "pack_version", None),
    )


_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "url": re.compile(r"https?://[^\s<>\"']+"),
    "ipv4": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "domain": re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b"),
    "cve": re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE),
    "sha256": re.compile(r"\b[a-f0-9]{64}\b", re.IGNORECASE),
    "md5": re.compile(r"\b[a-f0-9]{32}\b", re.IGNORECASE),
    "windows_file": re.compile(r"\b[A-Z]:\\[^\s\"'<>]+"),
    "gateway_ip": re.compile(r"\b(?:192\.168|10\.|172\.16\.|172\.31\.|169\.254\.)\d*\.\d*\d*\.\d*\.\d*\b"),
    "crypto_address": re.compile(
        r"\b(?:bc1[a-z0-9]{25,39}|1[a-zA-Z0-9]{25,34}|3[a-zA-Z0-9]{25,34})\b"
    ),
    "strong_token": re.compile(r"\b[A-Fa-f0-9]{40}\b"),
}


def _ipv4_valid(m: re.Match[str]) -> bool:
    try:
        ipaddress.ip_address(m.group(0))
        return True
    except ValueError:
        return False


class ExtractorRegistry:
    """Fan-out a segment to every registered extractor, dedup by kind+value.

    A bound OntologyPack is advisory (FR-002): every mention an extractor reports
    is admitted, annotated with a ``semantic_hint`` attribute when a pack is
    bound. Kinds the pack does not know are kept, not filtered.
    """

    def __init__(self, ontology_pack=None) -> None:
        self._extractors: list[tuple[str, Extractor]] = []
        self._ontology = ontology_pack
        self.register_builtin()

    def hint(self, kind: str) -> SemanticHint | None:
        """Pack knowledge about ``kind`` for ranking/expansion; never a veto."""
        return semantic_hint(self._ontology, kind)

    def register(self, name: str, extractor: Extractor) -> None:
        if name not in [n for n, _ in self._extractors]:
            self._extractors.append((name, extractor))

    def register_builtin(self) -> None:
        for kind, pat in _PATTERNS.items():
            def make(k: str, p: re.Pattern[str]) -> Extractor:
                def ex(text: str) -> list[Mention]:
                    out: list[Mention] = []
                    for m in p.finditer(text):
                        if k == "ipv4":
                            octets = m.group(0).split(".")
                            if not all(0 <= int(o) <= 255 for o in octets):
                                continue
                        out.append(Mention(kind=k, value=m.group(0), offset=m.start()))
                    return out
                return ex
            self.register(kind, make(kind, pat))

    def extract(self, text: str, source_id: str | None = None) -> list[Mention]:
        seen: set[tuple[str, str]] = set()
        out: list[Mention] = []
        for name, ex in self._extractors:
            for m in ex(text):
                key = (m.kind, m.value)
                if key in seen:
                    continue
                seen.add(key)
                m.attrs.setdefault("extractor", name)
                m.attrs.setdefault("source", source_id or "unknown")
                hint = self.hint(m.kind)
                if hint is not None:
                    m.attrs.setdefault("semantic_hint", hint.flag)
                out.append(m)
        return out


class DeterministicExtractorSet:
    """Spec-007 deterministic extractor fan-out over a decoded text segment.

    Runs the no-ML extractors in a fixed name order, deduplicates on
    ``(kind, value, normalized.canonical)`` keeping first-in-order, and tags
    output with a stable ``segment`` reference. Pure rule + dictionary logic.

    A bound OntologyPack is advisory (FR-002): it annotates each mention with
    ``evidence["semantic_hint"]`` and never removes one, so an unknown or typeless
    kind reaches the caller with no semantic commitment rather than as a gap.
    """

    def __init__(self, ontology_pack=None) -> None:
        self._ontology = ontology_pack
        self._extractors: list[tuple[str, Callable[[str], list[TypedMention]]]] = []

    def hint(self, kind: str) -> SemanticHint | None:
        """Pack knowledge about ``kind`` for ranking/expansion; never a veto."""
        return semantic_hint(self._ontology, kind)

    def register(self, name: str, fn: Callable[[str], list[TypedMention]]) -> None:
        if name not in [n for n, _ in self._extractors]:
            self._extractors.append((name, fn))

    def register_builtin(self) -> None:
        self.register("contacts", contacts.extract_contacts)
        self.register("dictionary_entities", dictionary_entities.extract_dictionary_entities)
        self.register("orgs", orgs.extract_organizations)
        self.register("persons", persons.extract_persons)
        self.register("places", places.extract_places)

    def names(self) -> list[str]:
        return [n for n, _ in sorted(self._extractors, key=lambda e: e[0])]

    def extract(
        self,
        text: str,
        *,
        segment_ref: str | None = None,
        lang: str | None = None,
    ) -> list[TypedMention]:
        extractors = dict(sorted(self._extractors, key=lambda e: e[0]))
        out: list[TypedMention] = []
        seen: set[tuple] = set()
        for fn in extractors.values():
            for m in fn(text, lang_hint=lang):
                key = (m.kind, m.value, m.normalized.canonical if m.normalized else None)
                if key in seen:
                    continue
                seen.add(key)
                if m.lang is None:
                    m.lang = lang
                if segment_ref and not m.evidence.get("segment_ref"):
                    m.evidence["segment_ref"] = segment_ref
                hint = self.hint(m.kind)
                if hint is not None:
                    m.evidence.setdefault("semantic_hint", hint.flag)
                out.append(m)
        return sorted(out, key=lambda m: (m.offset, m.kind, m.value))


def register_deterministic_extractors(registry: ExtractorRegistry) -> None:
    """Mirror the deterministic extractors into a legacy ExtractorRegistry.

    Producers are stable-name wrappers around the spec-007 extractors so the
    existing fan-out path (pipeline) also thrives: same rules, zero ML.
    """

    def wrap(fn: Callable[[str], list[TypedMention]]) -> Extractor:
        def ex(text: str) -> list[Mention]:
            return [
                Mention(
                    kind=m.kind,
                    value=m.value,
                    offset=m.offset,
                    confidence=m.confidence,
                    attrs={
                        "extractor": m.extractor,
                        "source": m.source,
                        "lang": m.lang or "unknown",
                    },
                )
                for m in fn(text)
            ]

        return ex

    registry.register("persons", wrap(persons.extract_persons))
    registry.register("contacts", wrap(contacts.extract_contacts))