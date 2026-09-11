"""Contract tests: robustness + experiment registry (T126, US6).

Tests-first for ``apps/science/robustness/*`` and ``apps/science/experiments/*``
per interface-contracts §8–9: the perturbation grid covers the three declared
families (missing / flip / biased-subsample), flip rates + sensitivity + noise
regions are reported (FR-011), and pinned reproduction compares recorded output
within tolerance and logs a reproduction event (SC-007).
"""

from __future__ import annotations

import pytest

from claims.model import EvidenceDirection, EvidenceLink
from errors import ReproductionError
from experiments.registry import ExperimentRegistry
from experiments.reproduction import reproduce
from robustness.perturb import PerturbationGrid
from robustness.report import analyze_robustness


class CaptureProducer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object, str | None]] = []

    def produce(self, topic, envelope, key=None, **kwargs) -> None:
        self.sent.append((topic, envelope, key))


def _evidence(n: int) -> list[EvidenceLink]:
    return [
        EvidenceLink(
            link_id=f"L{i}",
            observation_id=f"O{i}",
            raw_sha256=f"sha256:{i}",
            direction=EvidenceDirection.SUPPORTS,
            weight=1.0,
        )
        for i in range(n)
    ]


class TestRobustnessAnalyze:
    def test_three_families_with_flip_rates(self) -> None:
        report = analyze_robustness("CL-1", _evidence(20), perturbations=PerturbationGrid())
        assert report.report_id.startswith("RB-")
        assert report.claim_ref == "CL-1"
        assert set(report.flip_rates) == {"missing", "flip", "biased_subsample"}
        assert report.sensitivity_summary != {}
        assert isinstance(report.noise_regions, list)

    def test_label_flip_detects_flip_region(self) -> None:
        report = analyze_robustness(
            "CL-1",
            _evidence(20),
            perturbations=PerturbationGrid(
                missing_fraction=(),
                label_flip=(0.6,),
                biased_subsample=(),
                seed=11,
            ),
        )
        assert report.flip_rates["flip"] == 1.0
        assert any(r["family"] == "flip" and r["flipped"] for r in report.noise_regions)
        assert any("level" in r and "margin" in r for r in report.noise_regions)

    def test_missing_and_subsample_without_flip(self) -> None:
        report = analyze_robustness(
            "CL-1",
            _evidence(30),
            perturbations=PerturbationGrid(
                missing_fraction=(0.3, 0.5),
                label_flip=(),
                biased_subsample=(0.5, 0.3),
                seed=2,
            ),
        )
        assert report.flip_rates["missing"] == 0.0
        assert report.flip_rates["biased_subsample"] == 0.0

    def test_report_does_not_mutate_evidence(self) -> None:
        evidence = _evidence(10)
        before = [link.to_ref() for link in evidence]
        analyze_robustness("CL-1", evidence, perturbations=PerturbationGrid())
        assert [link.to_ref() for link in evidence] == before


class TestExperimentReproduce:
    def test_identical_run_reproduces_and_events(self) -> None:
        producer = CaptureProducer()
        registry = ExperimentRegistry(producer=producer)
        run = registry.record_run(
            input_refs=["o1", "o2", "o3"],
            output_refs=["CL-1"],
            seed=7,
            pipeline_version="1.2.3",
            dependency_freeze={"uv": "0.6"},
            tolerance=1e-6,
        )
        assert run.run_id.startswith("EX-")
        result = reproduce(run.run_id, registry=registry, producer=producer)
        assert result.all_reproduced
        assert result.run_id == run.run_id
        event_types = [envelope.event_type for _, envelope, _ in producer.sent]
        assert "science.experiment.run" in event_types
        assert "science.experiment.reproduction" in event_types

    def test_unknown_run_id_raises(self) -> None:
        registry = ExperimentRegistry()
        with pytest.raises(ReproductionError):
            reproduce("EX-unknown", registry=registry)

    def test_drift_from_pinned_output_is_reported(self) -> None:
        registry = ExperimentRegistry(producer=CaptureProducer())
        run = registry.record_run(
            input_refs=["o1"],
            output_refs=["CL-1"],
            seed=3,
            pipeline_version="1.2.3",
            dependency_freeze={"uv": "0.6"},
            tolerance=1e-3,
        )

        def drifted(_run) -> dict[str, float]:
            return {"output": (run.recorded_output["output"] or 0.0) + 100.0}

        result = reproduce(run.run_id, registry=registry, rerun=drifted)
        assert not result.all_reproduced
        assert result.mismatches != []