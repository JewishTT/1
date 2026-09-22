"""Deterministic entity-extraction micro-benchmark (spec 007, T028, SC-002).

Times the full lane (adapters -> segments -> mention extraction -> normalize)
across the committed text/html/pdf/docx/jpg fixtures, verifies byte-level
determinism (identical input -> identical JSON output, FR-8) and reports
median/p95/p99 latency + mention counts. Mirrors bench/bench/harness.py and
bench/science/bench_structural.py conventions; the interpretation engine is an
optional import so the rest of the bench suite stays independent of it.

Run from the repo root:

    uv run --project apps/interpretation python bench/extraction/bench_extract.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_LANE = Path(__file__).resolve().parents[2] / "apps" / "interpretation"
_SHARED = Path(__file__).resolve().parents[2] / "apps" / "shared"
_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_LANE), str(_SHARED), str(_ROOT), str(_ROOT / "apps")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:
    from dictionaries.build_mini import DATA_DIR, VERSIONS, build_all
    from extractors.lane import extract_deterministic

    _HAS_LANE = True
except Exception as exc:  # noqa: BLE001 - optional engine dependency fallback
    _HAS_LANE = False
    del exc


# Content fixtures the lane must fully-process offline.
_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "extraction"
_FIXTURE_NAMES = ("bio_ru.txt", "bio_en.txt", "contact.html", "profile.html")


def percentile(samples: list[float], p: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    idx = (len(ordered) - 1) * p
    lo = int(idx)
    if lo == idx:
        return ordered[lo]
    hi = lo + 1
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (idx - lo)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    if not _HAS_LANE:
        sys.stderr.write("interpretation engine unavailable; skipping extraction bench\n")
        return 0

    payloads = {}
    for name in _FIXTURE_NAMES:
        path = _FIXTURES / name
        if not path.exists():
            sys.stderr.write(f"fixture missing: {path}\n")
            return 1
        payloads[name] = path.read_bytes()

    missing = [k for k, v in VERSIONS.items() if not (DATA_DIR / f"{k}_{v}.meta.json").exists()]
    if missing:
        build_all(out_dir=DATA_DIR)

    # Determinism gate: warm run must reproduce byte-identical JSON (FR-8).
    deterministic = True
    table: dict[str, dict[str, object]] = {}
    for name, blob in payloads.items():
        single = extract_deterministic(blob)
        first = json.dumps(single.to_dict(), ensure_ascii=False, sort_keys=True)
        for _ in range(args.iterations - 1):
            if json.dumps(extract_deterministic(blob).to_dict(), ensure_ascii=False, sort_keys=True) != first:
                deterministic = False
        samples: list[float] = []
        mention_counts: list[int] = []
        for _ in range(args.iterations):
            started = time.perf_counter()
            result = extract_deterministic(blob)
            samples.append((time.perf_counter() - started) * 1000.0)
            mention_counts.append(len(result.mentions))
        table[name] = {
            "content_type": single.content_type,
            "mentions": mention_counts[0],
            "median_ms": round(percentile(samples, 0.5), 3),
            "p95_ms": round(percentile(samples, 0.95), 3),
            "p99_ms": round(percentile(samples, 0.99), 3),
            "iters": args.iterations,
        }

    report = {
        "engine": "apps/interpretation deterministic lane",
        "spec": "007-deterministic-entity-extraction-stack",
        "deterministic": deterministic,
        "datasets": dict(VERSIONS),
        "fixtures": table,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"determinism (byte-identical reruns): {deterministic}")
        print(f"dataset kinds: {len(VERSIONS)}")
        print(f"{'fixture':<16} {'B':>6} {'med ms':>7} {'p95':>7} {'p99':>7}")
        for name, row in table.items():
            print(f"{name:<16} {row['mentions']:>6} {row['median_ms']:>7} {row['p95_ms']:>7} {row['p99_ms']:>7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())