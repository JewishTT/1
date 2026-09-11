"""Tests for the knowledge-quality harness (T085)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knowledge import quality as q


def test_demo_corpus_shape():
    corpus = q.make_demo_corpus()
    assert len(corpus.entities) == 5
    assert len(corpus.observations) == 10
    assert sum(1 for o in corpus.observations if o.contradicts) == 2


def test_cluster_quality_perfect_resolution():
    corpus = q.make_demo_corpus()
    pred = {}
    for o in corpus.observations:
        pred.setdefault(f"c-{o.entity_id}", set()).add(o.observation_id)
    cq = q.cluster_quality(corpus, pred)
    assert cq.precision == 1.0
    assert cq.recall == 1.0
    assert cq.f1 == 1.0
    assert cq.false_merges == 0
    assert cq.false_splits == 0


def test_cluster_quality_false_merge_detected():
    corpus = q.make_demo_corpus()
    pred = {"c-bad": {"o1", "o4"}}  # o1 (acct-1) + o4 (acct-2) glued
    cq = q.cluster_quality(corpus, pred)
    assert cq.false_merges == 1
    assert cq.f1 < 1.0


def test_calibration_shapes():
    corpus = q.make_demo_corpus()
    cal = q.calibrate(corpus, q.demo_predictions(corpus))
    assert 0.0 <= cal["brier"] <= 1.0
    assert 0.0 <= cal["ece"] <= 1.0
    assert 0.0 <= cal["optimal_threshold"] <= 1.0
    assert cal["n_labeled"] == len(corpus.observations)


def test_brier_and_ece_helpers():
    pairs = [(0.9, True), (0.8, True), (0.2, False), (0.1, False)]
    assert q.brier_score(pairs) < 0.1
    e, curve = q.ece(pairs, bins=10)
    assert e >= 0.0
    assert isinstance(curve, list)
    assert q.brier_score([]) == 0.0


def test_breakdown_dimensions():
    corpus = q.make_demo_corpus()
    for dim in ("entity_type", "language", "script"):
        bd = q.breakdown(corpus, q.demo_predictions(corpus), dim)
        assert bd, f"breakdown for {dim} empty"
        for stats in bd.values():
            assert stats["n"] > 0


def test_contradiction_and_independence_accuracy():
    corpus = q.make_demo_corpus()
    decisions = {o.observation_id: ("REJECT" if o.contradicts else "ACCEPT") for o in corpus.observations}
    indep = {o.observation_id: o.independent for o in corpus.observations}
    ca = q.contradiction_accuracy(corpus, decisions)
    ia = q.independence_accuracy(corpus, indep)
    assert ca["accuracy"] == 1.0
    assert ia["accuracy"] == 1.0


def test_calibrated_profile_emitted():
    corpus = q.make_demo_corpus()
    prof = q.emit_calibrated_profile(corpus, q.demo_predictions(corpus))
    assert prof.version == "CALIBRATED-v2"
    assert prof.threshold_defer < prof.threshold_accept


def test_full_report_gate_passes():
    report = q.run_quality()
    assert report["cluster"]["f1"] == 1.0
    assert report["calibration"]["gate_passed"] is True
    assert report["calibrated_profile"]["version"] == "CALIBRATED-v2"


def test_report_json(tmp_path):
    report = q.run_quality()
    out = tmp_path / "kq.json"
    out.write_text(json.dumps(report), encoding="utf-8")
    parsed = json.loads(out.read_text(encoding="utf-8"))
    assert parsed["cluster"]["n_gold"] == 5