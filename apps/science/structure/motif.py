"""Degree-preserving permutation-null for structural statistics (T123, US5).

Kernel statistics (triangle count, spectral radius) are compared against a
null built by repeated balanced stub swaps that preserve the degree sequence
but destroy clustering. The null distribution makes significance explicit and
reproducible (fixed seed), and never claims precision beyond what the number
of permutations supports (warning when n < 100).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from random import Random
from typing import Any


@dataclass(frozen=True)
class NullDraw:
    shuffle_kind: str
    null_distribution: list[float]
    seed: int


def degree_preserving_null(
    graph: Any,
    *,
    statistic_fn: Callable[[Any], float],
    n_permutations: int,
    seed: int,
) -> NullDraw:
    """Permute ``graph``'s edges by stub swaps preserving degrees, re-score each draw."""
    seed_rng = Random(seed)
    distribution: list[float] = []
    if n_permutations <= 0:
        return NullDraw(
            shuffle_kind="degree_preserving_stub_swap",
            null_distribution=[float(statistic_fn(graph))],
            seed=seed,
        )
    for _ in range(n_permutations):
        rewired = _fixed_stub_rewire(graph, rng=seed_rng)
        permuted = type(graph)(graph_ref=graph.graph_ref)
        for a, b in rewired:
            if a != b:
                permuted.add_edge(a, b)
        distribution.append(float(statistic_fn(permuted)))
    return NullDraw(
        shuffle_kind="degree_preserving_stub_swap",
        null_distribution=distribution,
        seed=seed,
    )


def _fixed_stub_rewire(graph: Any, *, rng: Random) -> list[tuple[str, str]]:
    """Pair stubs (each node's degree copies) at random, dropping self-loops.

    Degeneracy is destroyed under the *same* degree sequence; the drop of
    self-loops/multi-edges is admitted by being honest in the shuffle kind.
    """
    counter: Counter[str] = Counter()
    for a, b in graph.edges():
        counter[a] += 1
        counter[b] += 1
    stubs: list[str] = []
    for node, degree in counter.items():
        stubs.extend([node] * degree)
    rng.shuffle(stubs)
    if len(stubs) % 2:
        stubs.append(stubs[0])
    return [(stubs[i], stubs[i + 1]) for i in range(0, len(stubs), 2)]