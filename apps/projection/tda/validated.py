"""Statistically validated hyperedges + order hyper-Laplacian (FR-011, 011).

A raw co-mention fan (e.g. every page that mentions 2+ names in a window) is
NOISY: a random page mentions a dozen unrelated names. Naive "analyst" would
trust them all; REALITY requires evidence that a hyperedge is *more frequent
than chance*. We:

1. filter hyperedges against a deterministic null model (conservative
   hypergeometric / rank model), producing ``ValidatedHyperedgeSet``;
2. compute the order-specific hyper-Laplacian spectrum (smallest eigenvalues)
   as a higher-order topology signal (this is the HypergraphX measure at the
   core — a hyperbolic *community wall* is a low-eigenvalue pattern).

Everything is a pure function of the input fan + null probability: no
randomness, no hidden tuning (I-12, C-3 honest rebuild).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ValidatedHyperedge:
    """A hyperedge that survived the null-model cut."""

    members: tuple[str, ...]
    weight: int = 1
    survival_probability: float = 1.0

    @property
    def size(self) -> int:
        return len(self.members)


@dataclass
class ValidatedHyperedgeSet:
    """Result of the stat-validated cut (FR-011)."""

    valid_edges: list[ValidatedHyperedge] = field(default_factory=list)

    def to_list(self) -> list[tuple[str, ...]]:
        return [e.members for e in self.valid_edges]

    def __len__(self) -> int:
        return len(self.valid_edges)


def _binomial_pmf(k: int, n: int, p: float) -> float:
    if k < 0 or k > n:
        return 0.0
    from math import comb

    return comb(n, k) * (p ** k) * ((1.0 - p) ** (n - k))


def hyperedge_survival(observed: int, n_trials: int, null_p: float) -> float:
    """P(we'd see this many co-occurrences by chance) under the null model.

    ``observed`` repeats of the hyperedge out of ``n_trials`` pages, each
    page containing the memberset with probability ``null_p`` (the baseline
    mention rate). Returns the survival probability: lower = more surprising.
    """
    if n_trials <= 0 or observed <= 0:
        return 1.0
    survival = 0.0
    for k in range(observed, n_trials + 1):
        survival += _binomial_pmf(k, n_trials, null_p)
    return min(max(survival, 0.0), 1.0)


def validate_hyperedges(
    fans: dict[tuple[str, ...], int],
    *,
    n_trials: int,
    null_p: float = 0.01,
    alpha: float = 0.05,
) -> ValidatedHyperedgeSet:
    """Keep only hyperedges significant under the binomial null model.

    Deterministic: same fans/params ⇒ same cut. HF-test is one-sided (we
    reject *too-frequent* hyperedges' null); alpha is the survival threshold.
    """
    valid = ValidatedHyperedgeSet()
    for members, observed in sorted(fans.items()):
        if len(members) < 2:
            continue
        survival = hyperedge_survival(observed, n_trials, null_p)
        if survival <= alpha:
            valid.valid_edges.append(
                ValidatedHyperedge(members=tuple(sorted(members)), weight=observed, survival_probability=survival)
            )
    return valid


def order_hyperlaplacian_values(
    fans: dict[tuple[str, ...], int],
    *,
    order: int = 2,
) -> list[float]:
    """Smallest eigenvalues of the order-k hyper-Laplacian (spectrum).

    Deterministic proxy for the Hodge/order-Laplacian spectrum without
    materializing a dense incidence matrix:

        deg(v)     = total weight of every hyperedge containing v (full fan)
        lamb_min(e)= min(deg members) - mean(deg members)   for each
                     order-uniform hyperedge e

    A tightly coupled, symmetric community yields values near 0 (an echo
    chamber with no internal friction); a hub/star structure (one node in
    every edge) pushes lamb_min(e) < 0 — the fan is *fragile*. Sorted
    ascending, fully deterministic (I-12).
    """
    deg: dict[str, float] = {}
    for members, weight in fans.items():
        for m in members:
            deg[m] = deg.get(m, 0.0) + float(weight)
    values: list[float] = []
    for members in sorted(fans):
        if len(members) != order:
            continue
        degrees = [deg.get(m, 0.0) for m in members]
        if not degrees:
            continue
        avg = sum(degrees) / len(degrees)
        lmin = min(degrees) - avg
        values.append(lmin)
    return sorted(values)


__all__ = [
    "ValidatedHyperedge",
    "ValidatedHyperedgeSet",
    "hyperedge_survival",
    "order_hyperlaplacian_values",
    "validate_hyperedges",
]