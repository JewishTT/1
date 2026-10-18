"""Measured, unmeasured, or fabricated — the distinction a dashboard has to preserve.

Spec 030 FR-100 / FR-101 / SC-015, task T167.

An operator writes ``0.0`` because a field is a float and nothing arrived for it. On a dashboard
that renders as "zero", and a missing measurement and a measured zero are now the same claim.
The only way back is to make the difference representable.

``Measured`` carries the value and the instrument that produced it. ``Unmeasured`` carries the
reason it could not be produced. There is no third state that silently becomes a number.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

__all__ = ["Measured", "Unmeasured", "MetricValue", "metric_or_none"]


@dataclass(frozen=True, slots=True)
class Measured:
    """A value that an instrument actually produced."""

    value: float
    instrument: str
    """What produced it. A number without a source is an assertion."""

    sample_size: int | None = None
    unit: str | None = None

    def __post_init__(self) -> None:
        if not str(self.instrument).strip():
            raise ValueError(
                "a measured value must name the instrument that produced it; a number with no "
                "source is an assertion (FR-100)"
            )


@dataclass(frozen=True, slots=True)
class Unmeasured:
    """A value that was not produced, and why.

    Serialises to ``null`` with the reason beside it. Not to ``0.0`` -- a missing measurement
    rendered as zero is the single most common way a platform reports success it never achieved.
    """

    reason: str
    missing_instrumentation: str | None = None

    def __post_init__(self) -> None:
        if not str(self.reason).strip():
            raise ValueError(
                "an unmeasured value must say why it is unmeasured; an empty reason reads as "
                "'zero, for no stated reason' (FR-100)"
            )


MetricValue = Measured | Unmeasured


def metric_or_none(value: Any, *, instrument: str) -> MetricValue:
    """Wrap a possibly-absent reading without inventing one.

    ``None`` and ``NaN`` become :class:`Unmeasured`, never ``0.0``. Every other type must
    already be a number.
    """
    if value is None:
        return Unmeasured(reason="no reading produced", missing_instrumentation=instrument)
    if isinstance(value, float) and value != value:  # NaN
        return Unmeasured(
            reason="instrument produced NaN", missing_instrumentation=instrument
        )
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"metric must be numeric, got {type(value).__name__}")
    return Measured(value=float(value), instrument=instrument)


def serialise(m: MetricValue) -> dict[str, Any]:
    """JSON shape: a number with its instrument, or ``null`` with a reason."""
    if isinstance(m, Measured):
        out: dict[str, Any] = {"value": m.value, "instrument": m.instrument}
        if m.sample_size is not None:
            out["sample_size"] = m.sample_size
        if m.unit is not None:
            out["unit"] = m.unit
        return out
    return {
        "value": None,
        "reason": m.reason,
        "missing_instrumentation": m.missing_instrumentation,
    }


def render(m: MetricValue) -> str:
    """What a human-facing surface should print.

    An unmeasured value prints as ``unmeasured (<reason>)``. It never prints as ``0``, ``0.0``,
    ``0%`` or an empty cell that a reader fills in with a guess.
    """
    if isinstance(m, Measured):
        return f"{m.value:g}" if m.unit is None else f"{m.value:g} {m.unit}"
    return f"unmeasured ({m.reason})"


def to_json(m: MetricValue) -> str:
    return json.dumps(serialise(m), sort_keys=True)