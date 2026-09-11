"""Contract tests: claim registration + calibration (T091, interface-contracts §1–2).

Tests-first: these import the public contract surface of ``claims.registry``
(register_claim) and ``claims.calibration`` (calibrate) and fail until those
are implemented. They intentionally cover the failure gates too — provenance
(FR-001), declared-model method (FR-002), and the scope boundary (FR-007)
with its audit envelope.
"""

from __future__ import annotations

import numpy as np
import pytest

from claims.calibration import CalibrationThresholds, Prediction, calibrate
from claims.model import CredenceDistribution, EvidenceDirection, EvidenceLink
from claims.registry import register_claim, set_observations
from errors import ProvenanceRequiredError, ScopeBoundaryError, UnknownModelError


class CaptureProducer:
    """Hermetic producer stub mirroring admission's ``_MockProducer``."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, object, str | None]] = []

    def produce(self, topic, envelope, key=None, **kwargs) -> None:
        self.sent.append((topic, envelope, key))


def _link(observation_id: str, sha: str = "sha256:abc") -> EvidenceLink:
    return EvidenceLink(
        link_id=f"L-{observation_id}",
        observation_id=observation_id,
        raw_sha256=sha,
        direction=EvidenceDirection.SUPPORTS,
        weight=0.5,
    )


def _distribution(method: str = "binomial-kde@1.0") -> CredenceDistribution:
    return CredenceDistribution(
        states=["growth", "stable", "decay"],
        labels=["Growth", "Stable", "Decay"],
        probs=[0.6, 0.3, 0.1],
        method=method,
    )


class TestRegisterClaim:
    def test_full_provenance_registers_and_emits(self) -> None:
        set_observations({"OBS-1": "sha256:abc"})
        producer = CaptureProducer()
        claim = register_claim(
            project_id="P-1",
            statement="transmission growth class for a process network",
            distribution=_distribution(),
            provenance=[_link("OBS-1")],
            tenant_id="t-1",
            producer=producer,
        )
        assert claim.claim_id.startswith("SC-")
        assert claim.status == "draft"
        assert [env.event_type for _t, env, _k in producer.sent] == [
            "science.claim.registered"
        ]
        assert producer.sent[0][0] == "science"

    def test_empty_provenance_raises(self) -> None:
        with pytest.raises(ProvenanceRequiredError):
            register_claim(
                project_id="P-1",
                statement="some structural claim",
                distribution=_distribution(),
                provenance=[],
                tenant_id="t-1",
            )

    def test_unknown_method_raises(self) -> None:
        set_observations({"OBS-1": "sha256:abc"})
        with pytest.raises(UnknownModelError):
            register_claim(
                project_id="P-1",
                statement="some structural claim",
                distribution=_distribution(method="mystery-model@99.9"),
                provenance=[_link("OBS-1")],
                tenant_id="t-1",
            )

    def test_sensitive_statement_raises_scope_refusal_and_audits(self) -> None:
        producer = CaptureProducer()
        with pytest.raises(ScopeBoundaryError):
            register_claim(
                project_id="P-1",
                statement="political affiliation of an individual",
                distribution=_distribution(),
                provenance=[_link("OBS-1")],
                tenant_id="t-1",
                producer=producer,
            )
        kinds = [env.event_type for _t, env, _k in producer.sent]
        assert "science.causal.scope_rejected" in kinds


class TestCalibration:
    def test_overconfident_model_verdict(self) -> None:
        rng = np.random.default_rng(7)
        predictions = [
            Prediction(confidence=float(rng.uniform(0.6, 1.0)), outcome=bool(rng.random() < 0.5))
            for _ in range(500)
        ]
        report = calibrate(
            "logit@1.0",
            predictions,
            thresholds=CalibrationThresholds(min_samples=100),
        )
        assert report.verdict.value == "overconfident"
        assert isinstance(report.brier, float)
        assert isinstance(report.ece, float)
        assert len(report.buckets) == 10

    def test_calibrated_model_verdict(self) -> None:
        rng = np.random.default_rng(11)
        confidences = rng.uniform(0.0, 1.0, size=1000)
        predictions = [
            Prediction(confidence=float(c), outcome=bool(rng.random() < c)) for c in confidences
        ]
        report = calibrate(
            "binomial-kde@1.0",
            predictions,
            thresholds=CalibrationThresholds(min_samples=100),
        )
        assert report.verdict.value == "calibrated"

    def test_insufficient_samples_uncertain(self) -> None:
        predictions = [Prediction(confidence=0.5, outcome=True) for _ in range(5)]
        report = calibrate("binomial-kde@1.0", predictions, thresholds=CalibrationThresholds())
        assert report.verdict.value == "uncalibrated"