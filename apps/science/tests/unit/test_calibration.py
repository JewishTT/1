"""Unit tests: calibration harness verdict on synthetic models (T092, US1).

The harness must label an overconfident synthetic model OVERCONFIDENT and a
well-calibrated one CALIBRATED — the MVP guard against fabricated confidence
(FR-002/FR-003).
"""

from __future__ import annotations

import numpy as np

from claims.calibration import CalibrationThresholds, Prediction, calibrate
from claims.model import CalibrationVerdict


class TestCalibrationHarness:
    def test_overconfident_drift_flags_overconfident(self) -> None:
        rng = np.random.default_rng(42)
        predictions = [
            Prediction(confidence=0.9, outcome=bool(rng.random() < 0.55)) for _ in range(300)
        ]
        report = calibrate("logit@1.0", predictions, thresholds=CalibrationThresholds())
        assert report.verdict == CalibrationVerdict.OVERCONFIDENT
        assert report.ece > report.thresholds.get("ece_threshold", 0.05)

    def test_calibrated_curve_stays_calibrated(self) -> None:
        rng = np.random.default_rng(5)
        confidences = rng.uniform(0.0, 1.0, size=800)
        predictions = [
            Prediction(confidence=float(c), outcome=bool(rng.random() < c)) for c in confidences
        ]
        report = calibrate("binomial-kde@1.0", predictions, thresholds=CalibrationThresholds())
        assert report.verdict == CalibrationVerdict.CALIBRATED

    def test_too_few_samples_never_claims_calibrated(self) -> None:
        predictions = [Prediction(confidence=0.7, outcome=True) for _ in range(9)]
        report = calibrate("binomial-kde@1.0", predictions, thresholds=CalibrationThresholds())
        assert report.verdict == CalibrationVerdict.UNCALIBRATED

    def test_report_is_immutable_and_deterministic(self) -> None:
        rng = np.random.default_rng(3)
        predictions = [
            Prediction(confidence=float(rng.uniform()), outcome=bool(rng.random() < 0.5))
            for _ in range(200)
        ]
        first = calibrate("m@1", predictions, thresholds=CalibrationThresholds())
        second = calibrate("m@1", predictions, thresholds=CalibrationThresholds())
        assert first.report_id == second.report_id