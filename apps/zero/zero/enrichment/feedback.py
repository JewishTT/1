"""Feedback loop (spec/010 §0.9, FR-005) — Layer 3 → Layer 1.

When an enricher/harvester discovers a new contact it is re-classified by the
deterministic ``TypeDetector`` and, if novel and confident enough, emitted as a
``ZeroLayerSeed`` — the spout of the next harvest wave. Emission goes to the
``zero_layer.feedback_seeds`` topic via an injected producer (the same
refs-only envelope pattern as ``apps/science/_events.py``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import log2

from ..harvesters.contracts import ObservationCandidate
from ..type_detector import InputType, TypeDetector

try:
    from events.kafka import build_envelope
    from events.topics import topic_for
except Exception:  # pragma: no cover - optional shared stack
    build_envelope = None  # type: ignore[assignment]
    topic_for = None  # type: ignore[assignment]

_FEEDBACK_EVENT = "zero_layer.feedback_seeds"


def zero_pure_tf(value: str, count: int, total: int) -> float:
    """Deterministic term-frequency term used by resolution TF-adjustment."""
    if total <= 0 or count <= 0:
        return 0.0
    probability = count / total
    return log2((1.0 - probability) / max(probability, 1e-12))


@dataclass(frozen=True)
class ZeroLayerSeed:
    """Entity link from layer 3 back to layer 1 (key entity ``ZeroLayerSeed``)."""

    derived_value: str
    derived_type: InputType
    confidence: float
    reason: str
    source_module: str
    original_seed_id: str = ""


class FeedbackLoop:
    """Filters harvested candidates into new harvestable seeds (dedup + re-detect)."""

    def __init__(
        self,
        detector: TypeDetector | None = None,
        *,
        min_confidence: float = 0.5,
        kinds: frozenset[str] = frozenset({"email", "phone", "username", "domain", "url"}),
    ) -> None:
        self._detector = detector or TypeDetector()
        self._min_confidence = min_confidence
        self._kinds = kinds

    def new_seeds(
        self,
        candidates: list[ObservationCandidate],
        *,
        seen: set[str] | None = None,
        original_seed_id: str = "",
    ) -> list[ZeroLayerSeed]:
        """Re-classify fresh candidates into seeds, dedup-ed, sorted deterministically."""
        observed = set(seen or set())
        seeds: dict[str, ZeroLayerSeed] = {}
        for candidate in sorted(candidates, key=lambda c: (c.source_module, c.value)):
            if candidate.kind not in self._kinds or candidate.confidence < self._min_confidence:
                continue
            detected = self._detector.detect(candidate.value)
            if detected.detected_type is InputType.UNKNOWN:
                continue
            key = f"{detected.detected_type.value}:{detected.raw_value.lower()}"
            if key in observed:
                continue
            observed.add(key)
            combined = (
                candidate.confidence * detected.confidence
                if detected.detected_type is candidate.kind
                else candidate.confidence
            )
            seeds[key] = ZeroLayerSeed(
                derived_value=detected.raw_value,
                derived_type=detected.detected_type,
                confidence=round(min(1.0, combined), 4),
                reason=f"from {candidate.kind} candidate via {detected.detected_type.value}",
                source_module=candidate.source_module,
                original_seed_id=original_seed_id,
            )
        return [seeds[key] for key in sorted(seeds)]

    def emit(
        self,
        seeds: list[ZeroLayerSeed],
        producer=None,
        *,
        key_prefix: str = "fb-",
    ) -> list[str]:
        """Emit seeds to ``zero_layer.feedback_seeds`` (refs-only JSON payload)."""
        emitted: list[str] = []
        if producer is None or build_envelope is None or topic_for is None:
            return emitted
        for seed in seeds:
            payload = {
                "derived_value": seed.derived_value,
                "derived_type": seed.derived_type.value,
                "confidence": seed.confidence,
                "reason": seed.reason,
                "source_module": seed.source_module,
                "original_seed_id": seed.original_seed_id,
            }
            key = f"{key_prefix}{seed.derived_type.value}:{seed.derived_value}"
            try:
                envelope = build_envelope(
                    event_type=_FEEDBACK_EVENT,
                    event_version="1.0",
                    producer="zero.feedback",
                    producer_version="0.1.0",
                    payload=json.dumps(payload, sort_keys=True).encode(),
                )
                producer.produce(_FEEDBACK_EVENT, envelope, key=key)
                emitted.append(key)
            except Exception:
                continue
        return emitted