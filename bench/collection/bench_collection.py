"""Collection-fabric micro-benchmark (T114/T123 precursor, R-11).

Deterministic, stack-free (like the T071 harness): exercises the pure fabric
components —

  * two-stage scheduler: decision latency p50/p95/p99 + verdict mix
  * observation gate: content-addressed store throughput (sha256 → manifest)

Reported as JSON so `bench/run --scenario collection` can aggregate it.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2] / "apps"
for _p in (str(_ROOT / "acquisition"), str(_ROOT / "shared")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from adapters import register
from dispatcher.scheduler import Dispatcher


@dataclass
class BenchResult:
    name: str
    values: dict = field(default_factory=dict)


def _fake_registry() -> None:
    register("web", execution_class="http", capabilities={"http", "etag"})
    register("js", execution_class="browser", capabilities={"http", "javascript", "dom"})
    register("ds", execution_class="dataset", capabilities={"parquet", "range-read", "bulk"})


def bench_scheduler(iterations: int = 2000) -> dict:
    _fake_registry()
    d = Dispatcher()
    tasks = [
        {"task_id": f"t-{i}", "uri": f"https://example.com/{i}", "tenant_id": "ten", "source_id": "src", "region": "eu-west",
         "required_capabilities": req, "expected_gain": 0.6, "novelty": 0.7, "relevance": 0.6,
         "freshness": 0.5, "source_quality": 0.8, "network_cost": 0.1, "compute_cost": 0.1}
        for i in range(iterations)
        for req in (["http"], ["http", "javascript"], ["parquet", "bulk"])
    ]
    lat: list[float] = []
    verdicts = {"dispatch": 0, "defer": 0, "reject": 0}
    t0 = time.perf_counter()
    for task in tasks:
        start = time.perf_counter()
        dec = d.schedule(task)
        lat.append((time.perf_counter() - start) * 1e3)
        verdicts[dec.verdict.value] += 1
    total_ms = (time.perf_counter() - t0) * 1e3
    return {
        "iterations": len(tasks),
        "decisions_per_sec": round(len(tasks) / (total_ms / 1e3), 1),
        "decision_ms_p50": round(statistics.median(lat), 4),
        "decision_ms_p95": round(sorted(lat)[int(len(lat) * 0.95)], 4),
        "decision_ms_p99": round(sorted(lat)[int(len(lat) * 0.99)], 4),
        "verdicts": verdicts,
    }


def bench_gate_hash(blobs: int = 400, size: int = 64_000) -> dict:
    """Content-addressing hash throughput (T130 compute core; transport excluded)."""
    import hashlib

    bodies = [bytes((b + blob_idx) % 251 for b in range(size)) for blob_idx in range(blobs)]
    keys: set[str] = set()
    t0 = time.perf_counter()
    for body in bodies:
        digest = hashlib.sha256(body).hexdigest()
        keys.add(f"obs/{digest}")
    total_s = time.perf_counter() - t0
    return {
        "blobs": blobs,
        "bytes_total": blobs * size,
        "hash_ms": round(total_s * 1e3, 1),
        "throughput_mb_s": round((blobs * size) / (total_s * 1024 * 1024), 1),
        "content_addressed_keys": len(keys),
    }


def main() -> int:
    bench = BenchResult(name="collection", values={"scheduler": bench_scheduler(), "gate_hash": bench_gate_hash()})
    print(json.dumps(asdict(bench), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())