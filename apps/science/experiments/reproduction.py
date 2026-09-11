"""Pinned reproduction with tolerance compare (T131, US6, SC-007).

``reproduce`` re-runs a recorded experiment with identical refs+seed+version,
compares each recorded output within tolerance, and logs a reproduction event
(science.experiment.reproduction). Drift is reported as explicit mismatches —
never swallowed — and unknown runs raise ``ReproductionError``. A caller can
inject a ``rerun`` to simulate a drifted pipeline (e.g. a version bump).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from events.kafka import Envelope

from _events import envelope
from errors import ReproductionError
from experiments.registry import ExperimentRegistry, ExperimentRun, default_recompute


@dataclass(frozen=True)
class ReproductionResult:
    run_id: str
    all_reproduced: bool
    tolerance: float
    mismatches: list[dict[str, Any]]
    recomputed: dict[str, float]
    event_ref: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "reproduced": self.all_reproduced,
            "tolerance": self.tolerance,
            "mismatches": self.mismatches,
            "output_refs": [f"run:{self.run_id}"],
        }


def reproduce(
    run_id: str,
    *,
    registry: ExperimentRegistry,
    rerun: Callable[[ExperimentRun], dict[str, float]] | None = None,
    producer: Any = None,
) -> ReproductionResult:
    """Re-run ``run_id`` pinned and compare recorded output within tolerance."""
    run = registry.get(run_id)
    if run is None:
        raise ReproductionError(run_id)

    recomputed = dict(
        default_recompute(run.input_refs, run.seed) if rerun is None else rerun(run)
    )

    mismatches: list[dict[str, Any]] = []
    for key, expected in run.recorded_output.items():
        actual = recomputed.get(key)
        if actual is None:
            mismatches.append(
                {"key": key, "expected": expected, "actual": None, "delta": float("inf"), "reason": "missing from rerun output"}
            )
            continue
        delta = abs(actual - expected)
        if delta > run.tolerance * max(abs(expected), 1.0):
            mismatches.append(
                {"key": key, "expected": expected, "actual": actual, "delta": round(delta, 9), "reason": "out of tolerance"}
            )

    all_reproduced = not mismatches
    event = _emit_reproduction(
        run=run,
        reproduced=all_reproduced,
        mismatch_keys=[m["key"] for m in mismatches],
        producer=producer,
    )
    return ReproductionResult(
        run_id=run.run_id,
        all_reproduced=all_reproduced,
        tolerance=run.tolerance,
        mismatches=mismatches,
        recomputed=recomputed,
        event_ref=event.event_id,
    )


def _emit_reproduction(
    *,
    run: ExperimentRun,
    reproduced: bool,
    mismatch_keys: list[str],
    producer: Any,
) -> Envelope:
    return envelope(
        event_type="science.experiment.reproduction",
        payload={
            "run_id": run.run_id,
            "reproduced": reproduced,
            "pipeline_version": run.pipeline_version,
            "mismatch_keys": mismatch_keys,
            "output_refs": run.output_refs,
        },
        producer=producer,
        correlation_id=f"repro:{run.run_id}",
    )