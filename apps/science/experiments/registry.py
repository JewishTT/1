"""Reproducible experiment run registry (T130, US6, FR-012).

Records every run with its inputs, outputs, seed, pipeline version, dependency
freeze (uv-lock anchor), and tolerance — the "recording, not hoping" that
SC-007 requires. Re-recording identical inputs/seeds/versions is idempotent
(returns the same ``EX-`` run). Events: ``science.experiment.run`` (I-5 refs/
fields-only payload).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any

from events.kafka import Envelope

from _events import envelope


def default_recompute(input_refs: list[str], seed: int) -> dict[str, float]:
    """Deterministic KVK-regression kernel for hermetic reproduction.

    No stochasticity: identical refs+seed yield identical floats, so a pinned
    re-run reproduces trivially within any tolerance ≥ 0 (SC-007). Production
    deployments replace this with the registered pipeline function.
    """
    acc = 0.0
    for ref in sorted(input_refs):
        digest = sha256(f"{ref}:{seed}".encode()).hexdigest()
        acc += int(digest[:8], 16) % 10_000 / 10_000.0
    divisor = (seed % 7) + 3
    return {"output": round(acc / divisor, 6)}


@dataclass(frozen=True)
class ExperimentRun:
    run_id: str
    input_refs: list[str]
    output_refs: list[str]
    seed: int
    pipeline_version: str
    dependency_freeze: dict[str, str]
    tolerance: float
    recorded_output: dict[str, float] = field(default_factory=dict)
    reproductions: list[str] = field(default_factory=list)


class ExperimentRegistry:
    """Hermetic registry + emitter for reproducible experiment runs (FR-012)."""

    def __init__(self, *, producer: Any = None, store: Any = None) -> None:
        self._producer = producer
        self._runs: dict[str, ExperimentRun] = {}

    def record_run(
        self,
        *,
        input_refs: list[str] | tuple[str, ...],
        output_refs: list[str] | tuple[str, ...],
        seed: int,
        pipeline_version: str,
        dependency_freeze: dict[str, str],
        tolerance: float,
        recompute: Callable[[list[str], int], dict[str, float]] | None = None,
    ) -> ExperimentRun:
        refs = sorted(input_refs)
        if not refs:
            raise ValueError("an experiment run needs at least one input ref")
        digest = sha256(
            f"ex:{refs}:{seed}:{pipeline_version}".encode()
        ).hexdigest()[:12]
        run_id = f"EX-{digest}"
        existing = self._runs.get(run_id)
        if existing is not None:
            return existing  # idempotent re-record (SC-008)

        output = dict((recompute or default_recompute)(refs, seed))
        run = ExperimentRun(
            run_id=run_id,
            input_refs=refs,
            output_refs=sorted(output_refs),
            seed=seed,
            pipeline_version=pipeline_version,
            dependency_freeze=dict(dependency_freeze),
            tolerance=tolerance,
            recorded_output=output,
        )
        self._runs[run_id] = run
        self._emit(
            event_type="science.experiment.run",
            payload={
                "run_id": run.run_id,
                "input_refs": run.input_refs,
                "output_refs": run.output_refs,
                "seed": run.seed,
                "pipeline_version": run.pipeline_version,
                "dependency_freeze": run.dependency_freeze,
                "tolerance": run.tolerance,
            },
            correlation_id=f"run:{run.run_id}",
        )
        return run

    def get(self, run_id: str) -> ExperimentRun | None:
        return self._runs.get(run_id)

    def list(self) -> list[ExperimentRun]:
        return list(self._runs.values())

    def _emit(self, *, event_type: str, payload: dict[str, Any], correlation_id: str) -> Envelope:
        return envelope(
            event_type=event_type,
            payload=payload,
            producer=self._producer,
            correlation_id=correlation_id,
            event_id=f"{event_type.split('.')[-1]}:{correlation_id}",
        )