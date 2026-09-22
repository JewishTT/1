"""Harvest module registry (spec/010 FR-003) — SpiderFoot-style pluggable scan.

Each ``HarvestModule`` declares the input types it can process, a stable
``name``, its ``method`` (for provenance), and a ``run(seed, ctx)`` entrypoint
that returns ``HarvestResult`` (candidates + optional worker CommandSpecs, and
quarantine notes on failure — same fault-containment philosophy as
``apps/acquisition/registry.py``). Dispatch order is name-sorted so runs are
reproducible. ``HarvestContext`` carries the injectable transport and an
optional DNS resolver so no module ever opens a socket unprompted.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from ..type_detector import InputType, SeedInput
from .contracts import HarvestResult
from .transport import OfflineTransport, Transport


@dataclass
class HarvestContext:
    """Per-run context shared by all modules (transport + resolvers)."""

    seed: SeedInput
    transport: Transport = field(default_factory=OfflineTransport)
    dns_exists: Callable[[str], bool] | None = None
    dns_records: Callable[[str], dict] | None = None


# Backwards-compatible alias used across the test suite and harvest_wave.
HarvesterContext = HarvestContext


class HarvestModule(Protocol):
    """Protocol for a single deterministic harvest module."""

    name: str
    required_types: frozenset[InputType]
    method: str
    license: str
    attribution: str

    def run(self, seed: SeedInput, ctx: HarvestContext) -> HarvestResult:
        """Harvest candidates for ``seed`` (deterministic, no bare sockets)."""
        ...


@dataclass(frozen=True)
class _ConcreteModule:
    """Frozen adapter wrapping a callable as a registered module."""

    name: str
    required_types: frozenset[InputType]
    method: str
    license: str
    attribution: str
    run: Callable[[SeedInput, HarvestContext], HarvestResult]


class HarvesterRegistry:
    """Deterministic registry + dispatcher for harvest modules.

    Mirrors ``apps/acquisition/registry.py``: register → dispatch sorted by
    module name, fault-contained (a raising module is reported, the rest run).
    """

    def __init__(self) -> None:
        self._modules: dict[str, _ConcreteModule] = {}

    def register(self, module: HarvestModule) -> None:
        if module.name in self._modules:
            raise ValueError(f"duplicate harvest module: {module.name}")
        self._modules[module.name] = _ConcreteModule(
            name=module.name,
            required_types=frozenset(module.required_types),
            method=module.method,
            license=module.license,
            attribution=module.attribution,
            run=module.run,
        )

    def register_all(self, package: str = "zero.harvesters.modules") -> int:
        """Import a module enumerating ``MODULES`` and register every entry."""
        imported = importlib.import_module(package)
        for module in imported.MODULES:
            self.register(module)
        return len(imported.MODULES)

    def names(self) -> list[str]:
        return sorted(self._modules)

    def modules_for(self, input_type: InputType) -> list[_ConcreteModule]:
        """Modules able to process ``input_type``, sorted by name (deterministic)."""
        return sorted(
            (m for m in self._modules.values() if input_type in m.required_types),
            key=lambda m: m.name,
        )

    def run(self, seed: SeedInput, ctx: HarvestContext) -> list[HarvestResult]:
        """Run every module registered for the seed type; collect results."""
        results: list[HarvestResult] = []
        for module in self.modules_for(seed.detected_type):
            try:
                results.append(module.run(seed, ctx))
            except Exception as exc:  # fault containment, quarantine-style
                results.append(
                    HarvestResult(module=module.name, notes=(f"module fault: {exc!r}",))
                )
        return results