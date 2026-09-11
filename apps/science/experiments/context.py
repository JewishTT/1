"""Experiment run-context builder (T090, FR-012 / US6).

Locks the environment for a reproducible run: entropy seed, pipeline version,
and a dependency freeze anchor (uv-lock based by default) plus recorded input
and output refs. ``ExperimentRun`` snapshots these so the reproduction lane
(US6) can replay within tolerance. No computation happens here — context is
captured *before* a run starts.
"""

from __future__ import annotations

import hashlib
import importlib.metadata as _metadata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Kernels that already exist in the workspace; their versions are pinned by the
# lockfile the deployment resolves (read here, never guessed).
_WORKSPACE_LOCK = Path(__file__).resolve().parents[2] / "uv.lock"

PIPELINE_NAME = "science.fabric"
PIPELINE_VERSION = "0.1.0"


def _dependency_freeze() -> dict[str, Any]:
    """A cheap, honest dependency anchor: key kernel versions + lock hash."""
    anchors: dict[str, str] = {}
    for distro in ("numpy", "scipy", "cognitive-shared"):
        try:
            anchors[distro] = _metadata.version(distro)
        except _metadata.PackageNotFoundError:
            anchors[distro] = "unknown"
    lock_digest = ""
    if _WORKSPACE_LOCK.exists():
        lock_digest = hashlib.sha256(_WORKSPACE_LOCK.read_bytes()).hexdigest()[:16]
    return {"package_versions": anchors, "lock_sha256_16": lock_digest}


@dataclass
class RunContext:
    """Capture everything needed to reproduce a run within tolerance."""

    seed: int
    pipeline_version: str = PIPELINE_VERSION
    dependency_freeze: dict[str, Any] = field(default_factory=_dependency_freeze)
    input_refs: list[str] = field(default_factory=list)
    output_refs: list[str] = field(default_factory=list)
    tolerance: float = 1e-9
    started_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )

    def to_ref(self) -> dict[str, Any]:
        """Refs-only payload for ``science.experiment.run`` (I-5)."""
        return {
            "run_id": self.run_id,
            "input_refs": self.input_refs,
            "output_refs": self.output_refs,
            "seed": self.seed,
            "pipeline_version": self.pipeline_version,
            "dependency_freeze": self.dependency_freeze,
            "tolerance": self.tolerance,
            "started_at": self.started_at,
        }

    @property
    def run_id(self) -> str:
        return "EX-" + hashlib.sha1(
            f"{self.seed}:{self.pipeline_version}:{self.started_at}".encode()
        ).hexdigest()[:12]


def build_context(
    *,
    seed: int,
    input_refs: list[str] | None = None,
    output_refs: list[str] | None = None,
    tolerance: float = 1e-9,
) -> RunContext:
    """Create a locked run context (T090)."""
    return RunContext(
        seed=seed,
        input_refs=input_refs or [],
        output_refs=output_refs or [],
        tolerance=tolerance,
    )