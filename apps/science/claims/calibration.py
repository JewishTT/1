"""Calibration harness (T094, FR-003; interface-contracts §2).

Computes per-decile observed-vs-expected buckets, aggregate Brier score and ECE
(m=10) from a model's prediction stream, then issues a verdict. A model with
fewer than ``min_samples`` is never labelled CALIBRATED — the harness refuses to
certify confidence it cannot measure. Reports are immutable and deterministic.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from _events import envelope as _emit
from claims.model import CalibrationReport, CalibrationVerdict


@dataclass(frozen=True)
class Prediction:
    confidence: float
    outcome: bool


@dataclass(frozen=True)
class CalibrationThresholds:
    ece_threshold: float = 0.05
    mean_conf_acc_tol: float = 0.05
    min_samples: int = 40
    n_bins: int = 10

    def to_dict(self) -> dict[str, float]:
        return {
            "ece_threshold": self.ece_threshold,
            "mean_conf_acc_tol": self.mean_conf_acc_tol,
            "min_samples": float(self.min_samples),
            "n_bins": float(self.n_bins),
        }


def _buckets(
    confidences: np.ndarray, outcomes: np.ndarray, n_bins: int
) -> list[dict[str, Any]]:
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    buckets: list[dict[str, Any]] = []
    for low, high in itertools.pairwise(edges):
        mask = (confidences >= low) & (confidences < high)
        count = int(mask.sum())
        bucket = {
            "bin": f"[{low:.2f}, {high:.2f})",
            "n": count,
            "expected": float(low + (high - low) / 2),
        }
        if count:
            bucket["mean_confidence"] = float(confidences[mask].mean())
            bucket["observed_frequency"] = float(outcomes[mask].mean())
        else:
            bucket["mean_confidence"] = 0.0
            bucket["observed_frequency"] = None
        buckets.append(bucket)
    return buckets


def _report_id(model_id: str, predictions: Sequence[Prediction]) -> str:
    digest = hashlib.sha256(
        json.dumps(
            [(p.confidence, bool(p.outcome)) for p in predictions],
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()[:12]
    return f"CL-{hashlib.sha256(model_id.encode()).hexdigest()[:6]}{digest}"


def calibrate(
    model_id: str,
    predictions: Sequence[Prediction],
    *,
    thresholds: CalibrationThresholds | None = None,
    producer: Any = None,
    store: Any = None,
) -> CalibrationReport:
    """Score a model's calibration; never certifies confidence it can't measure."""
    thresholds = thresholds or CalibrationThresholds()
    n = len(predictions)

    confidences = np.array([p.confidence for p in predictions], dtype=float)
    outcomes = np.array([1.0 if p.outcome else 0.0 for p in predictions], dtype=float)

    brier = float(np.mean((confidences - outcomes) ** 2))
    buckets = _buckets(confidences, outcomes, thresholds.n_bins)

    ece = 0.0
    for bucket in buckets:
        bucket_n = bucket["n"]
        if bucket_n and bucket["observed_frequency"] is not None:
            ece += (bucket_n / n) * abs(
                bucket["mean_confidence"] - bucket["observed_frequency"]
            )

    drift = float(np.mean(confidences) - np.mean(outcomes))

    if n < thresholds.min_samples:
        verdict = CalibrationVerdict.UNCALIBRATED
    elif ece <= thresholds.ece_threshold and drift <= thresholds.mean_conf_acc_tol:
        verdict = CalibrationVerdict.CALIBRATED
    elif drift > thresholds.mean_conf_acc_tol:
        verdict = CalibrationVerdict.OVERCONFIDENT
    else:
        verdict = CalibrationVerdict.UNCALIBRATED

    report = CalibrationReport(
        report_id=_report_id(model_id, predictions),
        model_id=model_id,
        buckets=buckets,
        brier=brier,
        ece=ece,
        verdict=verdict,
        thresholds=thresholds.to_dict(),
    )

    env = _emit(
        event_type="science.calibration.report",
        payload={
            "report_id": report.report_id,
            "model_id": report.model_id,
            "ece": report.ece,
            "brier": report.brier,
            "verdict": report.verdict.value,
            "thresholds_ref": report.thresholds,
        },
        producer=producer,
    )
    if store is not None:
        store.apply(env)
    return report