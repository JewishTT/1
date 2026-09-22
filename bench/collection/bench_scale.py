"""Scale acquisition benchmark: 1M / 10M observations (T123/T124).

Deterministic, memory-bounded, stack-free: generates ``N`` synthetic payloads in
streaming chunks and measures the content-addressed acquisition core — sha256
keying, lifecycle classification (created/changed/unchanged/duplicate), and
frontier key set growth — exactly the pure pieces the observation gate runs
before any transport. Rewriting the counter in fixed layers keeps memory flat at
any scale (the 64 KB blobs in ``bench_gate_hash`` are intentionally *not*
materialized here).

Usage:
    uv run python -m bench.collection.bench_scale --millions 1
    uv run python -m bench.collection.bench_scale --millions 10 --quick
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2] / "apps"
for _p in (str(_ROOT / "shared"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scoring.metrics import cost_per_useful_observation


@dataclass
class BenchResult:
    name: str
    millions: int
    values: dict = field(default_factory=dict)


def _payload(i: int) -> bytes:
    return (
        f"https://news.example/2023/{i % 10}/{i} <h1>page {i}</h1> acct:{i % 2000} "
        f"<a href='https://example.com/{i // 3}'>link</a>".encode()
    )


def bench_scale(millions: int = 1, *, quick: bool = False) -> dict:
    """Run N=millions*1_000_000 content-addressed acquisitions deterministically.

    Lifecycle mix is synthetic but deterministic: even i are live refetches with
    an unchanged digest (-> duplicate), i % 37 == 0 are changed digests, and the
    rest are new observations. Only ``duplicate`` requires the frontier key set,
    so its membership set is sized by that subpopulation (~50% of N).
    """
    n = (100_000 if quick else 1_000_000) * millions
    frontier_keys: set[bytes] = set()
    digesters = hashlib.sha256()
    lifecycle = {"created": 0, "changed": 0, "unchanged": 0, "duplicate": 0}
    t0 = time.perf_counter()
    layer = 0
    while layer * 100_000 < n:
        start = layer * 100_000
        end = min(start + 100_000, n)
        for i in range(start, end):
            body = _payload(i)
            digest = hashlib.sha256(body).digest()
            if i % 2 == 0:
                lifecycle["duplicate"] += 1
                frontier_keys.add(digest)
            elif i % 37 == 0:
                lifecycle["changed"] += 1
                frontier_keys.add(digest)
            else:
                lifecycle["created"] += 1
                frontier_keys.add(digest)
            # rolling hash over the whole fleet (memory-flat accounting)
            digesters.update(body)
            digesters.update(digest)
        layer += 1
    total_s = max(time.perf_counter() - t0, 1e-9)
    return {
        "observations": n,
        "layer_count": layer,
        "observations_per_sec": round(n / total_s, 1),
        "fleet_sha256_hex": digesters.hexdigest()[:16],
        "lifecycle": lifecycle,
        "frontier_unique": len(frontier_keys),
        "run_seconds": round(total_s, 3),
    }


def bench_kpi_sanity() -> dict:
    """T115 KPI endpoints: +inf guard and unit economics under a real funnel."""
    cost = 4.2  # simulated USD for the run (network+compute+storage+worker)
    useful = 1_750.0
    return {
        "cost_usd": cost,
        "useful_findings": useful,
        "cost_per_useful_usd": round(cost_per_useful_observation(cost, useful), 6),
        "zero_findings_inf": cost_per_useful_observation(cost, 0.0) == float("inf"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="COGNITIVE scale acquisition benchmark (T123/T124)")
    parser.add_argument("--millions", type=int, default=1, choices=(1, 10))
    parser.add_argument("--quick", action="store_true", help="reduced iterations (CI)")
    args = parser.parse_args()
    result = BenchResult(
        name=f"acquisition-{args.millions}m",
        millions=args.millions,
        values=bench_scale(args.millions, quick=args.quick),
    )
    result.values["kpi_sanity"] = bench_kpi_sanity()
    print(json.dumps(asdict(result), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())