"""Fellegi-Sunter probabilistic matcher (spec/010 §0.8 step 2) — vs Splink.

Standard record linkage on pure stdlib:

- Step 1: blocking — exact keys (email/phone digits) + Soundex on last names.
- Step 2: EM estimation of m/u probabilities for user-defined comparison levels
  (exact / soundex / Jaro-Winkler / token ). Weights: ``w_{k,j} = log2(m/u)``
  and total ``W = log2(lambda/(1-lambda)) + sum_k w_{k,j}``.
- Step 3: TF-adjustment for rare values (``log2(P|M / P|U)``) applied on top of
  the exact/soundex levels.
- Step 4: transitive closure over the matched pairs — see ``zero.resolution.graph``.

   Source lessons: Splink (MIT) comparison/EM model, Fellegi-Sunter (1969)
   formalization. Deterministic given fixed init; EM runs a fixed iteration
   count so results are reproducible.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import log2
from typing import Any

from ..type_detector import make_soundex
from .similarity import jaro_winkler, normalize, token_dice

_EPS = 1e-12


@dataclass(frozen=True)
class ComparisonLevel:
    """One comparison level for a field: name, priors, and its predicate."""

    name: str
    m_prior: float
    u_prior: float
    test: Callable[[Any, Any], bool]


@dataclass(frozen=True)
class ComparisonField:
    """Field under comparison with ordered levels (specific → catch-all)."""

    name: str
    levels: tuple[ComparisonLevel, ...]


def _jaro_level(value: Any, other: Any) -> bool:
    return jaro_winkler(str(value), str(other)) >= 0.8


def _token_level(value: Any, other: Any) -> bool:
    return token_dice(str(value), str(other)) >= 0.5


def name_field(name: str = "name") -> ComparisonField:
    """Name field levels: exact → soundex → Jaro-Winkler → catch-all."""
    return ComparisonField(
        name=name,
        levels=(
            ComparisonLevel("exact", 0.90, 0.001, lambda a, b: normalize(a) == normalize(b)),
            ComparisonLevel("soundex", 0.70, 0.005, lambda a, b: _soundex(a) == _soundex(b)),
            ComparisonLevel("jaro", 0.60, 0.050, _jaro_level),
            ComparisonLevel("else", 0.05, 0.900, lambda _a, _b: True),
        ),
    )


def email_field(name: str = "email") -> ComparisonField:
    """Email field levels: exact local@domain → catch-all."""
    return ComparisonField(
        name=name,
        levels=(
            ComparisonLevel(
                "exact",
                0.95,
                0.0001,
                lambda a, b: normalize(a, "email") == normalize(b, "email"),
            ),
            ComparisonLevel("else", 0.05, 0.9999, lambda _a, _b: True),
        ),
    )


def phone_field(name: str = "phone") -> ComparisonField:
    """Phone field levels: exact digit-normalized → catch-all."""
    return ComparisonField(
        name=name,
        levels=(
            ComparisonLevel(
                "exact",
                0.92,
                0.0005,
                lambda a, b: normalize(a, "phone") == normalize(b, "phone"),
            ),
            ComparisonLevel("else", 0.08, 0.9995, lambda _a, _b: True),
        ),
    )


def text_field(name: str = "org") -> ComparisonField:
    """Free-text field levels: exact → token-dice → catch-all."""
    return ComparisonField(
        name=name,
        levels=(
            ComparisonLevel("exact", 0.85, 0.002, lambda a, b: normalize(a) == normalize(b)),
            ComparisonLevel("tokens", 0.55, 0.060, _token_level),
            ComparisonLevel("else", 0.05, 0.920, lambda _a, _b: True),
        ),
    )


def _soundex(value: Any) -> str:
    text = normalize(str(value))
    if not text:
        return ""
    tokens = text.split()
    return make_soundex(tokens[-1] if len(tokens) > 1 else tokens[0])


def block_pairs(
    records: list[dict],
    *,
    key_fields: tuple[str, ...] = ("email", "phone", "name"),
) -> list[tuple[int, int]]:
    """Pair (i, j) records sharing at least one blocking key (§0.8 step 1).

    Keys: exact email, digit-normalized phone, Soundex of the last name token.
    Returns a deterministic sorted list of unique pairs.
    """
    blocks: dict[tuple[str, str], list[int]] = {}
    for index, record in enumerate(records):
        keys: set[tuple[str, str]] = set()
        for field in key_fields:
            value = record.get(field)
            if not value:
                continue
            if field == "email":
                keys.add(("e", normalize(str(value), "email")))
            elif field == "phone":
                norm = normalize(str(value), "phone")
                if len(norm) >= 7:
                    keys.add(("p", norm))
            elif field == "name":
                code = _soundex(value)
                if code:
                    keys.add(("s", code))
        for key in keys:
            blocks.setdefault(key, []).append(index)
    pairs: set[tuple[int, int]] = set()
    for bucket in blocks.values():
        for i in range(len(bucket)):
            for j in range(i + 1, len(bucket)):
                a, b = bucket[i], bucket[j]
                pairs.add((a, b) if a < b else (b, a))
    return sorted(pairs)


class FellegiSunter:
    """EM-trained probabilistic matcher over comparison fields."""

    def __init__(
        self,
        fields: tuple[ComparisonField, ...],
        *,
        lambda_prior: float = 0.01,
        max_iterations: int = 25,
    ) -> None:
        self._fields = fields
        self._lambda = lambda_prior
        self._max_iterations = max_iterations
        self._m: dict[str, dict[str, float]] = {}
        self._u: dict[str, dict[str, float]] = {}
        self._pairs: list[tuple[int, int]] = []
        self._vectors: list[list[int]] = []
        self._records: list[dict] = []

    # -- EM training ---------------------------------------------------------

    def fit(self, records: list[dict], pairs: list[tuple[int, int]] | None = None) -> FellegiSunter:
        """Estimate m/u by EM over the (blocked) record pairs (deterministic).

        Returns ``self`` for chaining; repeated fit calls are reproducible given
        the same inputs and fixed iteration count.
        """
        self._records = records
        self._pairs = pairs if pairs is not None else block_pairs(records)
        self._vectors = [self._compare(records[a], records[b]) for a, b in self._pairs]

        # init m/u from level priors
        for field in self._fields:
            self._m[field.name] = {level.name: level.m_prior for level in field.levels}
            self._u[field.name] = {level.name: level.u_prior for level in field.levels}

        for _ in range(self._max_iterations):
            posteriors = self._e_step()
            self._m_step(posteriors)
            self._u_step(posteriors)
        return self

    # -- scoring --------------------------------------------------------------

    def weight(self, record_a: dict, record_b: dict) -> float:
        """Total comparison weight ``W`` between two records."""
        vector = self._compare(record_a, record_b)
        w = log2(self._lambda / (1.0 - self._lambda))
        for field, level_index in zip(self._fields, vector, strict=True):
            level = field.levels[level_index]
            m = self._m[field.name].get(level.name, level.m_prior)
            u = self._u[field.name].get(level.name, level.u_prior)
            w += log2(max(m, _EPS) / max(u, _EPS))
        return w

    def weight_tf(self, record_a: dict, record_b: dict) -> float:
        """Weight with rare-value TF adjustment on exact/soundex matches."""
        base = self.weight(record_a, record_b)
        for field in self._fields:
            value_a = record_a.get(field.name)
            value_b = record_b.get(field.name)
            if not value_a or not value_b:
                continue
            if str(value_a) == str(value_b) and str(value_a):
                base += _tf_adjustment(records=self._records, field=field.name, value=str(value_a))
        return base

    def match(
        self,
        records: list[dict],
        *,
        threshold: float = 0.0,
        pairs: list[tuple[int, int]] | None = None,
    ) -> list[tuple[int, int, float]]:
        """Return ``(i, j, weight)`` matches above ``threshold`` (sorted)."""
        candidates = pairs if pairs is not None else block_pairs(records)
        result = []
        for a, b in candidates:
            w = self.weight(records[a], records[b])
            if w > threshold:
                result.append((a, b, w))
        return sorted(result, key=lambda t: (-t[2], t[0], t[1]))

    # -- internals ------------------------------------------------------------

    def _e_step(self) -> list[float]:
        """E-step: posterior ``P(M|gamma)`` per pair."""
        posteriors: list[float] = []
        for vector in self._vectors:
            prob_m = self._lambda
            prob_u = 1.0 - self._lambda
            for field, level_index in zip(self._fields, vector, strict=True):
                level = field.levels[level_index]
                prob_m *= self._m[field.name].get(level.name, level.m_prior)
                prob_u *= self._u[field.name].get(level.name, level.u_prior)
            denom = prob_m + prob_u
            posteriors.append(prob_m / denom if denom else 0.0)
        return posteriors

    def _m_step(self, posteriors: list[float]) -> None:
        self._estimate("m", posteriors)

    def _u_step(self, posteriors: list[float]) -> None:
        self._estimate("u", posteriors)

    def _estimate(self, which: str, posteriors: list[float]) -> None:
        for field_index, field in enumerate(self._fields):
            weights = posteriors if which == "m" else [1.0 - p for p in posteriors]
            total_weight = sum(weights) + _EPS
            for level in field.levels:
                matched = sum(
                    weight
                    for weight, vector, (a, b) in zip(
                        weights, self._vectors, self._pairs, strict=True
                    )
                    if self._records[a].get(field.name) is not None
                    and vector[field_index] == field.levels.index(level)
                )
                if total_weight:
                    estimate = matched / total_weight
                else:
                    estimate = level.u_prior if which == "u" else level.m_prior
                if which == "m":
                    self._m[field.name][level.name] = estimate
                else:
                    self._u[field.name][level.name] = estimate

    def _compare(self, record_a: dict, record_b: dict) -> list[int]:
        """Comparison vector: level index for each field (left-null-tolerant)."""
        vector: list[int] = []
        for field in self._fields:
            value_a = record_a.get(field.name)
            value_b = record_b.get(field.name)
            chosen = len(field.levels) - 1  # catch-all
            if value_a is not None and value_b is not None:
                for index, level in enumerate(field.levels):
                    if level.test(value_a, value_b):
                        chosen = index
                        break
            vector.append(chosen)
        return vector


def _tf_adjustment(records: list[dict], field: str, value: str) -> float:
    """Term-frequency term of the exact match weight (§0.8 step 2)."""
    total = len(records) + _EPS
    frequency = sum(1 for record in records if record.get(field) == value)
    p_value = frequency / total
    return log2((1.0 - p_value) / max(p_value, _EPS))