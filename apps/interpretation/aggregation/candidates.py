"""Candidate aggregation (T034, FR-011).

Group normalized mentions into a candidate entity per canonical key. A candidate
accumulates source evidence (count, distinct source ids, distinct values) and a
composite confidence derived from structural quality, source diversity, and
mention count.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CanonicalMention:
    kind: str
    canonical: str
    alias: str | None = None
    attrs: dict[str, str] = field(default_factory=dict)


@dataclass
class Candidate:
    kind: str
    key: str
    value: str  # canonical
    aliases: list[str] = field(default_factory=list)
    sources: set[str] = field(default_factory=set)
    count: int = 0
    confidence: float = 0.0
    first_seen_offset: int = 0
    attrs: dict[str, str] = field(default_factory=dict)

    def add(self, mention: CanonicalMention, source_id: str) -> None:
        self.count += 1
        self.sources.add(source_id)
        if mention.alias and mention.alias != self.value and mention.alias not in self.aliases:
            self.aliases.append(mention.alias)


def _structural_quality(value: str) -> float:
    if len(value) >= 40:
        return 0.9
    if len(value) >= 12:
        return 0.8
    if len(value) >= 4:
        return 0.6
    return 0.4


def composite_confidence(structural: float, distinct_sources: int, count: int) -> float:
    source_factor = min(1.0, 0.4 + 0.15 * distinct_sources)
    count_factor = min(1.0, 0.5 + 0.1 * count)
    return round(structural * 0.5 + source_factor * 0.3 + count_factor * 0.2, 3)


class CandidateAggregator:
    """Aggregate canonical mentions → candidates with evidence-based confidence."""

    def __init__(self) -> None:
        self._candidates: dict[tuple[str, str], Candidate] = {}

    def add(self, mention: CanonicalMention, source_id: str, offset: int = 0) -> Candidate:
        key = (mention.kind, mention.canonical)
        cand = self._candidates.get(key)
        if cand is None:
            cand = Candidate(kind=mention.kind, key=mention.canonical, value=mention.canonical)
            self._candidates[key] = cand
        cand.add(mention, source_id)
        if cand.first_seen_offset == 0:
            cand.first_seen_offset = offset
        cand.confidence = composite_confidence(
            _structural_quality(cand.value), len(cand.sources), cand.count
        )
        return cand

    def all(self) -> list[Candidate]:
        return list(self._candidates.values())