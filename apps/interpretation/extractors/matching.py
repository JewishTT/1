"""Deterministic gazetteer matching primitives (spec 007, US2).

Shared by places / sanctions / companies extractors. All matching runs over
case-folded text against automatons whose datasets already carry case-folded
term variants; overlapping hits are resolved longest-first and fully-swallowed
matches are dropped, so the same input always yields the same mention set.
"""

from __future__ import annotations

from datasets import find_matches


def scan(automaton_, folded_text: str) -> list[tuple[int, str, dict]]:
    """All (start, term, payload) hits, longest-first at each start."""
    matches = find_matches(automaton_, folded_text)
    return sorted(matches, key=lambda m: (m[0], -len(m[1]), m[1].casefold()))


def resolve_overlaps(matches: list[tuple[int, str, dict]]) -> list[tuple[int, str, dict]]:
    """Longest-first at each start; drop matches fully inside an accepted span."""
    accepted: list[tuple[int, str, dict]] = []
    for start, term, payload in matches:
        end = start + len(term)
        swallowed = any(
            start >= a_start and end <= (a_start + len(a_term))
            for a_start, a_term, _ in accepted
        )
        if swallowed:
            continue
        accepted.append((start, term, payload))
    return accepted


def boundaries_ok(text: str, start: int, length: int) -> bool:
    before = text[start - 1] if start > 0 else ""
    after = text[start + length] if start + length < len(text) else ""
    return not (before.isalpha() or after.isalpha())


def match_terms(automaton_, text: str) -> list[tuple[int, str, dict]]:
    """Boundary-checked, overlap-resolved term hits on original-case text."""
    folded = text.casefold()
    resolved: list[tuple[int, str, dict]] = []
    for start, term, payload in scan(automaton_, folded):
        if boundaries_ok(text, start, len(term)):
            resolved.append((start, term, payload))
    return resolved