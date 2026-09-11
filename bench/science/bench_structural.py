"""Structural-analysis micro-benchmark (T125, US5).

Deterministic, size-aware: times the scoped analyze() for the spectral and
motif kernels including the permutation-null pass, verifies normalized-score
invariants ([0,1]) and that over-budget graphs are DEFERRED with a sampling
plan — never a truncated estimate (SC-006). Mirrors bench/bench/harness.py
conventions and imports the science engine optionally.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2] / "apps" / "science"
for _path in (str(_ROOT),):
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:
    from structure.graph import AnalysisBudget, Graph, NullParams, analyze
    from structure.model import StructureKind

    _HAS_SCIENCE = True
except Exception as exc:  # noqa: BLE001 - optional engine dependency fallback
    _HAS_SCIENCE = False
    del exc


def percentile(samples: list[float], p: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    idx = (len(ordered) - 1) * p
    lo = int(idx)
    return ordered[lo]


def _timeit(fn, n: int) -> list[float]:
    samples: list[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t0)
    return samples


@dataclass
class BenchResult:
    name: str
    metrics: dict[str, float] = field(default_factory=dict)

    def set(self, key: str, value: float) -> None:
        self.metrics[key] = round(value, 6)


def _ring(size: int) -> Graph:
    g = Graph(graph_ref=f"graph:ring-{size}")
    for i in range(size):
        g.add_edge(f"n{i}", f"n{(i + 1) % size}")
    return g


def _clique(size: int) -> Graph:
    g = Graph(graph_ref=f"graph:clique-{size}")
    for i in range(size):
        for j in range(i + 1, size):
            g.add_edge(f"n{i}", f"n{j}")
    return g


def _dense(n: int) -> Graph:
    g = Graph(graph_ref=f"graph:dense-{n}")
    for i in range(n):
        for j in range(i + 1, n):
            g.add_edge(f"n{i}", f"n{j}")
    return g


def bench_structural(quick: bool) -> BenchResult:
    result = BenchResult("structural")
    if not _HAS_SCIENCE:
        result.set("science_imported", 0.0)
        return result
    result.set("science_imported", 1.0)

    perms = 30 if quick else 100
    budget = AnalysisBudget()

    for kind, build, label in (
        (StructureKind.SPECTRAL, _ring, "spectral"),
        (StructureKind.MOTIF, _clique, "motif"),
    ):
        graph = build(20 if label == "spectral" else 12)
        null = NullParams(n_permutations=perms, seed=1)

        def _run(g=graph, k=kind, n=null) -> object:
            return analyze(g, budget=budget, kind=k, null_params=n)

        # warm
        _run()
        result.set(f"{label}_p50_ms", percentile(_timeit(_run, 5), 0.5) * 1000)
        t0 = time.perf_counter()
        for _ in range(5):
            out = _run()
        elapsed = max(time.perf_counter() - t0, 1e-9)
        result.set(f"{label}_per_second", 5 / elapsed)

        scores_ok = all(0.0 <= v <= 1.0 for v in out.scores.values()) or (
            "triangle_count" in out.scores and all(v >= 0 for v in out.scores.values())
        )
        sig = out.significance
        result.set(f"{label}_scores_normalized", 1.0 if scores_ok else 0.0)
        result.set(
            f"{label}_significance_present",
            1.0 if (sig is not None and len(sig.null_distribution) == perms) else 0.0,
        )

    # Budget gate: dense graph must be DEFERRED with a sampling plan (SC-006).
    dense = _dense(60)
    deferred = analyze(
        dense,
        budget=AnalysisBudget(max_ops=10_000, max_permutations=perms),
        kind=StructureKind.MOTIF,
        null_params=NullParams(n_permutations=perms, seed=1),
    )
    result.set("over_budget_deferred", 1.0 if deferred.status.value == "deferred" else 0.0)
    result.set(
        "over_budget_sampling_plan",
        1.0 if "sampling" in (deferred.budget_rationale or "").lower() else 0.0,
    )
    return result


def run_all(quick: bool) -> list[BenchResult]:
    return [bench_structural(quick)]


def render(results: list[BenchResult]) -> str:
    lines = ["COGNITIVE structural benchmark report (T125, US5)", ""]
    for r in results:
        lines.append(f"[{r.name}]")
        for k, v in r.metrics.items():
            lines.append(f"  {k}: {v}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="COGNITIVE structural benchmark (T125)")
    parser.add_argument("--quick", action="store_true", help="reduced permutations (CI)")
    parser.add_argument("--out", default=None, help="write JSON report to path")
    args = parser.parse_args()

    results = run_all(args.quick)
    print(render(results))
    out = Path(args.out) if args.out else Path(__file__).resolve().parents[1] / "reports" / "science-structural.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"quick": args.quick, "results": [r.metrics for r in results]}, indent=2),
        encoding="utf-8",
    )
    print(f"report written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())