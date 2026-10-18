"""River for source-health drift, with the world kept separate from the pipeline.

Spec 030 CE-001 §15.14, DON-TEMP-003, task T140.

**Upstream** : https://github.com/online-ml/river   **Revision** : 0.26.1   **Mode** : B.

River learns online, which is exactly right for a stream of source telemetry and exactly wrong
for a claim about the world. A detector that fires when a source's volume halves must produce one
of two very different statements:

* "this source stopped publishing" — an operational fact about our pipeline;
* "the phenomenon this source measures has changed" — a claim about reality.

Conflating them is how a broken scraper becomes a published finding. So this module emits a
:class:`SourceHealthSignal` about the *instrument*, and there is deliberately no code path here
that produces a statement about the world. Turning a signal into an obligation is the context
kernel's decision, taken under policy, not this operator's.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "RIVER_VERSION_PINNED",
    "DetectorUnavailable",
    "DriftDetector",
    "HealthSignalKind",
    "SourceHealthFeature",
    "SourceHealthSignal",
]


class DetectorUnavailable(RuntimeError):
    """River is not installed.

    Reported as a capability gap. A missing detector must never be reported as "no drift": that
    converts an absent instrument into a negative finding.
    """


RIVER_VERSION_PINNED = "0.26.1"


class HealthSignalKind:
    VOLUME_DROP = "volume_drop"
    VOLUME_SPIKE = "volume_spike"
    ERROR_RATE_RISE = "error_rate_rise"
    SCHEMA_CHANGE = "schema_change"
    QUALITY_DROP = "quality_drop"


@dataclass(frozen=True, slots=True)
class SourceHealthFeature:
    """One telemetry point about a source. Describes the instrument, never the world."""

    source_id: str
    tenant_id: str
    item_count: int
    error_count: int = 0
    bytes_fetched: int = 0
    parse_failures: int = 0
    observed_at: str = ""
    schema_fingerprint: str | None = None

    @property
    def error_rate(self) -> float:
        total = self.item_count + self.error_count
        return (self.error_count / total) if total else 0.0

    @property
    def parse_failure_rate(self) -> float:
        total = self.item_count + self.parse_failures
        return (self.parse_failures / total) if total else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "item_count": self.item_count,
            "error_count": self.error_count,
            "error_rate": round(self.error_rate, 4),
            "parse_failures": self.parse_failures,
            "parse_failure_rate": round(self.parse_failure_rate, 4),
            "bytes_fetched": self.bytes_fetched,
            "schema_fingerprint": self.schema_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class SourceHealthSignal:
    """A measured change in how a source behaves.

    ``is_world_claim`` is False by construction and there is no way to set it True here. The
    only way a signal becomes a statement about the world is through an explicit research
    obligation under policy.
    """

    source_id: str
    tenant_id: str
    kind: str
    detail: dict[str, Any]
    detector_version: str
    features_seen: int
    is_world_claim: bool = False
    notes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.is_world_claim:
            raise ValueError(
                f"a source-health signal about {self.source_id!r} cannot be marked as a world "
                "claim. A change in how a source behaves has two causes -- the phenomenon moved, "
                "or our pipeline broke -- and this operator cannot tell them apart. Turning the "
                "signal into a statement about reality is a research obligation taken under "
                "policy, not something the detector may do (CE-001 §15.14)"
            )

    def describe(self) -> str:
        return (
            f"source-health: {self.source_id} {self.kind} "
            f"(instrument telemetry, not a world finding; {self.features_seen} samples)"
        )


def _read_drift(model: Any, value: float) -> bool:
    """Feed one value and report whether the detector fired.

    River 0.26.1's ``ADWIN.update(x)`` returns **None**; the verdict is on the model's
    ``drift_detected`` attribute afterwards. Reading the return value as a boolean therefore
    makes every detector permanently silent -- which looks exactly like a healthy source and is
    the worst failure mode a drift detector can have. Both shapes are handled so this keeps
    working if a future version returns a verdict directly.
    """
    returned = model.update(value)
    if isinstance(returned, bool):
        return returned
    return bool(getattr(model, "drift_detected", False))


class DriftDetector:
    """Online volume/error drift over per-source telemetry.

    River's ``ADWIN`` detector is used for the volume stream. ``ADWIN`` rather than
    ``HalfHalf``: at 0.26.1 ``HalfHalf`` is not exported from ``river.drift`` (the module
    exposes ``ADWIN``, ``KSWIN``, ``PageHinkley``, ``NoDrift``), and a detector named in a
    comment that does not exist is worse than one that does.

    It is applied to ``item_count`` only. A combined feature would let an error spike and a
    volume collapse cancel out, which is precisely the case where a source is broken and the
    arithmetic says nothing happened.
    """

    def __init__(
        self,
        *,
        threshold: float = 0.05,
        warmup: int = 20,
        detector_version: str = RIVER_VERSION_PINNED,
    ) -> None:
        if not 0.0 < threshold < 1.0:
            raise ValueError(f"threshold must be a fraction, got {threshold}")
        if warmup < 1:
            raise ValueError(f"warmup must be at least one sample, got {warmup}")
        self._threshold = threshold
        self._warmup = warmup
        self._version = detector_version
        self._models: dict[str, Any] = {}
        self._last_volume: dict[str, int] = {}
        self._stable_volume: dict[str, float] = {}
        self._in_change: dict[str, bool] = {}
        self._seen: dict[str, int] = {}
        self._last_schema: dict[str, str | None] = {}

    @staticmethod
    def _require() -> Any:
        try:
            from river import drift
        except ImportError as exc:  # pragma: no cover - environment-dependent
            raise DetectorUnavailable(
                "river is not installed; source-health drift detection is unavailable. This is "
                "a capability gap, not evidence that nothing changed (see CE-001 §15.14)"
            ) from exc
        return drift

    def available(self) -> bool:
        try:
            drift = self._require()
        except DetectorUnavailable:
            return False
        return hasattr(drift, "ADWIN")

    def warm(self, feature: SourceHealthFeature) -> tuple[SourceHealthSignal, ...]:
        """Learn from one point without alarming. Returns signals only after warm-up."""
        drift = self._require()
        key = f"{feature.tenant_id}/{feature.source_id}"
        self._seen[key] = self._seen.get(key, 0) + 1

        model = self._models.get(key)
        if model is None:
            model = drift.ADWIN(delta=self._threshold, grace_period=self._warmup)
            self._models[key] = model

        current = float(feature.item_count)
        change_detected = _read_drift(model, current)

        # The pre-change baseline.
        #
        # ADWIN confirms a change roughly a dozen samples after it starts, and every one of
        # those samples already looks "stable" to it. Updating the baseline on each of them --
        # or on each non-firing sample after -- means that by the time the detector speaks, the
        # baseline is already the new value, so the report reads "previous == current" and a
        # spike is indistinguishable from a drop.
        #
        # So the baseline is frozen the moment the value *starts* to diverge from it, which is a
        # fact about the numbers and not about the detector's confidence.
        baseline = self._stable_volume.get(key)
        diverged = (
            baseline is not None
            and abs(current - baseline) > max(abs(baseline) * self._threshold, 1.0)
        )
        if baseline is None or not diverged:
            self._stable_volume[key] = current
        self._last_volume[key] = feature.item_count

        volume_signal: SourceHealthSignal | None = None
        if change_detected and self._seen[key] > self._warmup:
            previous = self._stable_volume.get(key, baseline)
            kind = (
                HealthSignalKind.VOLUME_SPIKE
                if previous is not None and current > previous
                else HealthSignalKind.VOLUME_DROP
            )
            volume_signal = SourceHealthSignal(
                source_id=feature.source_id,
                tenant_id=feature.tenant_id,
                kind=kind,
                detail={
                    "previous_count": previous,
                    "current_count": feature.item_count,
                    "change_window": feature.observed_at,
                },
                detector_version=self._version,
                features_seen=self._seen[key],
            )

        schema_changed = self._check_schema(feature)
        return tuple(s for s in (volume_signal, schema_changed) if s is not None)

    def _check_schema(self, feature: SourceHealthFeature) -> SourceHealthSignal | None:
        """A parser upgrade changes a source's shape. That is our doing, not the world's."""
        key = f"{feature.tenant_id}/{feature.source_id}"
        previous = self._last_schema.get(key, "__unset__")
        self._last_schema[key] = feature.schema_fingerprint
        if previous == "__unset__" or previous == feature.schema_fingerprint:
            return None
        return SourceHealthSignal(
            source_id=feature.source_id,
            tenant_id=feature.tenant_id,
            kind=HealthSignalKind.SCHEMA_CHANGE,
            detail={"previous_schema": previous, "current_schema": feature.schema_fingerprint},
            detector_version=self._version,
            features_seen=self._seen.get(key, 0),
            notes={"likely_cause": "parser or extractor version change"},
        )

    def observe(
        self, features: Iterable[SourceHealthFeature]
    ) -> tuple[SourceHealthSignal, ...]:
        """Convenience wrapper. Learning and alarming stay separated; this does both."""
        out: list[SourceHealthSignal] = []
        for feature in features:
            out.extend(self.warm(feature))
        return tuple(out)

    def state_ref(self, tenant_id: str, source_id: str) -> dict[str, Any]:
        """Enough to checkpoint and replay a detector's state."""
        key = f"{tenant_id}/{source_id}"
        model = self._models.get(key)
        return {
            "tenant_id": tenant_id,
            "source_id": source_id,
            "features_seen": self._seen.get(key, 0),
            "last_volume": self._last_volume.get(key),
            "last_schema": self._last_schema.get(key),
            "detector_present": model is not None,
            "detector_version": self._version,
            "warmup": self._warmup,
            "threshold": self._threshold,
        }