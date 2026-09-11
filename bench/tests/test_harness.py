"""Tests for the benchmark harness (T071)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench import harness as h


def test_all_benchmarks_produce_metrics():
    results = h.run_all(quick=True)
    assert len(results) == len(h.BENCHMARKS)
    for r in results:
        assert r.name
        assert r.metrics, f"{r.name!r} produced no metrics"


def test_acquisition_has_expected_metrics():
    r = next(x for x in h.run_all(True) if x.name == "acquisition")
    assert r.metrics["requests_per_second"] > 0
    assert r.metrics["new_urls_per_second"] > 0
    assert r.metrics["resolution_latency_p50_ms"] >= 0


def test_search_percentiles_are_ordered():
    r = next(x for x in h.run_all(True) if x.name == "search")
    assert r.metrics["search_p50_ms"] <= r.metrics["search_p95_ms"] <= r.metrics["search_p99_ms"]


def test_tda_feature_stability():
    r = next(x for x in h.run_all(True) if x.name == "tda")
    assert r.metrics["feature_stability_ok"] == 1.0
    assert r.metrics["nodes"] > 0
    assert r.metrics["edges"] > 0
    assert r.metrics["dimensions"] == 3


def test_cost_metrics_positive():
    r = next(x for x in h.run_all(True) if x.name == "cost")
    for v in r.metrics.values():
        assert v > 0


def test_report_json(tmp_path):
    out = tmp_path / "bench.json"
    results = h.run_all(True)
    out.write_text(json.dumps({"results": [r.metrics for r in results]}), encoding="utf-8")
    parsed = json.loads(out.read_text(encoding="utf-8"))
    assert len(parsed["results"]) == len(h.BENCHMARKS)


def test_percentile_helper():
    assert h.percentile([1.0, 2.0, 3.0], 0.5) == 2.0
    assert h.percentile([], 0.5) == 0.0


def test_donor_benchmark_has_expected_metrics():
    r = next(x for x in h.run_all(True) if x.name == "donor")
    for k in (
        "statement_provenance_p50_ms",
        "statement_provenance_p95_ms",
        "correlation_pair_p50_ms",
        "correlation_pair_p95_ms",
        "claim_verdict_p50_ms",
        "claim_verdict_p95_ms",
    ):
        assert k in r.metrics and r.metrics[k] >= 0
    assert r.metrics["engine_imported"] in (0.0, 1.0)


def test_donor_code_extracted_benchmarks_present():
    """spec 003: donor Statement stable keys + evidence vault throughput."""
    r = next(x for x in h.run_all(True) if x.name == "donor")
    for k in (
        "statement_stable_key_p50_ms",
        "statement_stable_key_p95_ms",
        "statement_key_deterministic",
        "evidence_ingest_per_s",
        "evidence_verify_per_s",
        "evidence_verify_ok",
    ):
        assert k in r.metrics, f"missing {k}"
    assert r.metrics["evidence_verify_ok"] == 1.0
    assert r.metrics["statement_key_deterministic"] == 1.0


def test_donor_round2_benchmarks_present():
    """spec 004: temporal conflict scan + target normalization metrics."""
    r = next(x for x in h.run_all(True) if x.name == "donor")
    for k in (
        "temporal_conflict_scan_p50_ms",
        "temporal_conflict_scan_p95_ms",
        "temporal_ordering_detected",
        "target_normalize_p50_ms",
        "target_normalize_p95_ms",
        "target_normalize_ok",
    ):
        assert k in r.metrics, f"missing {k}"
    assert r.metrics["temporal_ordering_detected"] in (0.0, 1.0)
    if h._HAS_DONOR:
        assert r.metrics["temporal_ordering_detected"] == 1.0
        assert r.metrics["target_normalize_ok"] == 1.0