"""Harvester contracts (spec/010 FR-003, entities from §Key Entities).

``ObservationCandidate`` is the atomic provenance-carrier emitted by every
harvester module: the extracted value, a coarse ``kind`` taxonomy, a
deterministic confidence, and the provenance chain ``(source_module, method,
raw_fields, evidence)`` exactly as FR-003 requires. ``CommandSpec`` represents
the *initialization* of a vendored CLI worker (maigret / sherlock / tesseract)
that the platform may schedule out-of-band — the core keeps thin adapters and
never shells out during a synchronous harvest. ``HarvestResult`` groups
everything one module produced for one seed.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ObservationCandidate:
    """One deterministic observation produced by a harvest module (FR-003)."""

    value: str
    kind: str
    confidence: float
    source_module: str
    method: str
    raw_fields: dict = field(default_factory=dict)
    evidence: str = ""

    def as_dict(self) -> dict:
        return {
            "value": self.value,
            "kind": self.kind,
            "confidence": self.confidence,
            "source_module": self.source_module,
            "method": self.method,
            "raw_fields": self.raw_fields,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class CommandSpec:
    """Initialization spec for a vendored worker command (maigret/sherlock/tesseract)."""

    tool: str
    args: tuple[str, ...]
    method: str
    timeout_s: float = 60.0

    def as_dict(self) -> dict:
        return {"tool": self.tool, "args": list(self.args), "method": self.method}


@dataclass(frozen=True)
class HarvestResult:
    """Everything one module produced for one seed (candidates, workers, notes)."""

    module: str
    candidates: tuple[ObservationCandidate, ...] = ()
    commands: tuple[CommandSpec, ...] = ()
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "module": self.module,
            "candidates": [c.as_dict() for c in self.candidates],
            "commands": [c.as_dict() for c in self.commands],
            "notes": list(self.notes),
        }