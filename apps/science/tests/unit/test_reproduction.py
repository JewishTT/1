"""Unit tests: perturbation flip rates + reproduction tolerance (T127, US6).

``apps/science/robustness/`` must produce per-family flip rates and noise
regions; ``apps/science/experiments/`` must reproduce identical seeds/versions
within tolerance and report (not silently swallow) drift on changed reruns.
"""

from __future__ import annotations

from claims.model import EvidenceDirection, EvidenceLink
from experiments.registry import ExperimentRegistry, default_recompute
from experiments.reproduction import reproduce
from robustness.perturb import PerturbationFamily, PerturbationGrid, apply_perturbation
from robustness.report import analyze_robustness


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


class TestPerturb:
    def test_missing_removes_fraction(self) -> None:
        original = _evidence(10)
        removed = apply_perturbation(original, PerturbationFamily.MISSING, 0.5, seed=1)
        assert len(removed) == 5

    def test_flip_reverses_directions(self) -> None:
        flipped = apply_perturbation(_evidence(10), PerturbationFamily.FLIP, 1.0, seed=1)
        flipped_directions = {link.direction for link in flipped}
        assert flipped_directions == {EvidenceDirection.REFUTES}

    def test_subsample_keeps_fraction(self) -> None:
        kept = apply_perturbation(_evidence(10), PerturbationFamily.BIASED_SUBSAMPLE, 0.3, seed=3)
        assert len(kept) == 3

    def test_grid_levels_per_family(self) -> None:
        grid = PerturbationGrid()
        assert grid.levels(PerturbationFamily.MISSING) == (0.2,)
        assert grid.levels(PerturbationFamily.FLIP) == (0.1,)
        assert set(grid.levels(PerturbationFamily.BIASED_SUBSAMPLE)) == {0.5, 0.7}


class TestFlipRates:
    def test_per_family_flip_rates(self) -> None:
        report = analyze_robustness(
            "CL-1",
            _evidence(20),
            perturbations=PerturbationGrid(
                missing_fraction=(0.5,),
                label_flip=(0.5, 0.8),
                biased_subsample=(0.2, 0.5),
                seed=5,
            ),
        )
        assert report.flip_rates["missing"] == 0.0
        assert report.flip_rates["flip"] > 0.0
        assert report.flip_rates["biased_subsample"] == 0.0
        assert all(0.0 <= value <= 1.0 for value in report.flip_rates.values())

    def test_noise_regions_are_explicit(self) -> None:
        report = analyze_robustness(
            "CL-2",
            _evidence(12),
            perturbations=PerturbationGrid(
                missing_fraction=(),
                label_flip=(0.9,),
                biased_subsample=(),
                seed=6,
            ),
        )
        flipped = [r for r in report.noise_regions if r["flipped"]]
        assert flipped != []
        for region in flipped:
            assert {"family", "level", "flipped", "margin"} <= set(region)


class TestReproduction:
    def test_default_rerun_is_deterministic(self) -> None:
        registry = ExperimentRegistry()
        a = registry.record_run(
            input_refs=["a", "b"],
            output_refs=["CL-1"],
            seed=42,
            pipeline_version="1.0",
            dependency_freeze={},
            tolerance=1e-9,
        )
        b = registry.record_run(
            input_refs=["a", "b"],
            output_refs=["CL-1"],
            seed=42,
            pipeline_version="1.0",
            dependency_freeze={},
            tolerance=1e-9,
        )
        for key in a.recorded_output:
            assert a.recorded_output[key] == b.recorded_output[key]

    def test_identical_run_reproduces_within_tolerance(self) -> None:
        registry = ExperimentRegistry()
        run = registry.record_run(
            input_refs=["o1", "o2"],
            output_refs=["CL-1"],
            seed=9,
            pipeline_version="2.0.0",
            dependency_freeze={"uv": "0.6.1"},
            tolerance=1e-6,
        )
        again = default_recompute(run.input_refs, run.seed)
        for key, value in run.recorded_output.items():
            assert abs(again[key] - value) <= 1e-6 * max(abs(value), 1.0)
        result = reproduce(run.run_id, registry=registry)
        assert result.all_reproduced

    def test_drift_returns_mismatches(self) -> None:
        registry = ExperimentRegistry()
        run = registry.record_run(
            input_refs=["o1"],
            output_refs=["CL-1"],
            seed=5,
            pipeline_version="1.0",
            dependency_freeze={},
            tolerance=1e-4,
        )
        result = reproduce(
            run.run_id,
            registry=registry,
            rerun=lambda _r: {"output": run.recorded_output["output"] + 1.0},
        )
        assert result.all_reproduced is False
        assert result.mismatches[0]["key"] == "output"
        assert result.mismatches[0]["delta"] > 0.0