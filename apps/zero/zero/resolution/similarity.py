"""Fuzzy string similarity (spec/010 §0.8 step 3) — pure stdlib.

Deterministic implementations of Levenshtein distance, Jaro and Jaro-Winkler
(JW bonus over shared prefix ``l * p * (1 - Jaro)``), Token-based Sørensen-Dice,
plus canonical normalization for the whole resolution layer. Soundex lives in
``zero.type_detector`` (blocking key factory) and is re-exported here for
convenience.
"""

from __future__ import annotations

from math import log2

from ..type_detector import make_soundex


def levenshtein(a: str, b: str) -> int:
    """Levenshtein edit distance (insert / delete / replace) between two strings."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            insertion = current[j - 1] + 1
            deletion = previous[j] + 1
            substitution = previous[j - 1] + (ca != cb)
            current.append(min(insertion, deletion, substitution))
        previous = current
    return previous[-1]


def jaro(a: str, b: str) -> float:
    """Jaro similarity (0.0–1.0); the base for Jaro-Winkler."""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    match_distance = max(len(a), len(b)) // 2 - 1
    match_distance = max(match_distance, 0)
    a_matches = [False] * len(a)
    b_matches = [False] * len(b)
    matches = 0
    for i, ca in enumerate(a):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len(b))
        for j in range(start, end):
            if b_matches[j] or ca != b[j]:
                continue
            a_matches[i] = True
            b_matches[j] = True
            matches += 1
            break
    if matches == 0:
        return 0.0
    transpositions = 0
    k = 0
    for i, ca in enumerate(a):
        if not a_matches[i]:
            continue
        while not b_matches[k]:
            k += 1
        if ca != b[k]:
            transpositions += 1
        k += 1
    transpositions /= 2
    m = float(matches)
    return (m / len(a) + m / len(b) + (m - transpositions) / m) / 3.0


def jaro_winkler(a: str, b: str, *, p: float = 0.1, limit: int = 4) -> float:
    """Jaro-Winkler with prefix bonus up to the first ``limit`` equal chars.

    Sensitivity ~97.4% at threshold 0.8 for name matching (spec §0.8 note).
    """
    jaro_score = jaro(a, b)
    prefix = 0
    for ca, cb in zip(a, b, strict=False):
        if ca != cb or prefix >= limit:
            break
        prefix += 1
    return jaro_score + prefix * p * (1 - jaro_score)


def _tokens(value: str) -> list[str]:
    return [token for token in value.lower().split() if token]


def token_dice(a: str, b: str, *, weights: dict[str, float] | None = None) -> float:
    """Weighted Sørensen-Dice over bag-of-tokens of two strings.

    ``weights`` lets rare tokens dominate (term-frequency adjustment); default
    gives uniform 1.0 per token.
    """
    a_tokens = _tokens(a)
    b_tokens = _tokens(b)
    if not a_tokens or not b_tokens:
        return 0.0
    weights = weights or {}
    a_multi: dict[str, int] = {}
    b_multi: dict[str, int] = {}
    for token in a_tokens:
        a_multi[token] = a_multi.get(token, 0) + 1
    for token in b_tokens:
        b_multi[token] = b_multi.get(token, 0) + 1
    a_total = sum(weights.get(token, 1.0) * count for token, count in a_multi.items())
    b_total = sum(weights.get(token, 1.0) * count for token, count in b_multi.items())
    intersect = 0.0
    for token in set(a_multi) & set(b_multi):
        weight = weights.get(token, 1.0)
        intersect += weight * min(a_multi[token], b_multi[token])
    return (2 * intersect) / (a_total + b_total) if (a_total + b_total) else 0.0


def normalize(value: str, kind: str = "") -> str:
    """Canonical form for blocking keys / dedup (spec §0.8 step 1)."""
    if not value:
        return ""
    if kind in ("email",):
        return value.strip().lower()
    if kind in ("phone",):
        return "".join(ch for ch in value if ch.isdigit())
    if kind in ("domain", "url"):
        return value.strip().lower().rstrip("/")
    return " ".join(value.strip().lower().split())


def idf_weight(token: str, corpus_count: int, token_frequency: int) -> float:
    """TF-adjustment term ``log2(P|M / P|U)`` for rarity (spec §0.8 step 2)."""
    if corpus_count <= 0 or token_frequency <= 0:
        return 0.0
    p_value = token_frequency / corpus_count
    return log2((1.0 - p_value) / max(p_value, 1e-9))  # rare tokens weigh more


__all__ = [
    "idf_weight",
    "jaro",
    "jaro_winkler",
    "levenshtein",
    "make_soundex",
    "normalize",
    "token_dice",
]