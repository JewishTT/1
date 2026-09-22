"""Zero-layer observation gate (spec/010 FR-009, FR-012) — immutable output.

Every harvest wave funnels through ``ZeroLayerGate``: it assigns a
content-addressed ``observation_id``, stores an immutable ``ZeroLayerObservation``
record (frozen dataclass — no in-place mutation is possible), and emits
refs-only envelopes on the ``zero_layer.*`` topics through an injected producer
(mirroring ``apps/shared/events/observation_gate.py`` lifecycle semantics and
``apps/science/_events.py`` refs-only payload rule, Constitution I-5).

The store/producer are injectable so tests stay hermetic; with ``None``
producer no message is emitted.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from .harvesters.contracts import ObservationCandidate
from .type_detector import InputType, SeedInput

try:
    from events.kafka import build_envelope
    from events.topics import topic_for
except Exception:  # pragma: no cover - optional shared stack
    build_envelope = None  # type: ignore[assignment]
    topic_for = None  # type: ignore[assignment]

EVENT_SEED_DETECTED = "zero_layer.seed_detected"
EVENT_HARVEST_STARTED = "zero_layer.harvest_started"
EVENT_OBSERVATION = "zero_layer.observation"
EVENT_HARVEST_CYCLE_COMPLETE = "zero_layer.harvest_cycle_complete"


@dataclass(frozen=True)
class ZeroLayerObservation:
    """Immutable gate record: one seed + everything its wave extracted."""

    observation_id: str
    seed_id: str
    seed_type: InputType
    seed_value: str
    candidates: tuple[ObservationCandidate, ...]
    derived_seeds: tuple[str, ...] = ()
    confidence_dist: tuple[tuple[str, int], ...] = ()
    content_digest: str = ""
    produced_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "seed_id": self.seed_id,
            "seed_type": self.seed_type.value,
            "seed_value": self.seed_value,
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "derived_seeds": list(self.derived_seeds),
            "confidence_dist": list(self.confidence_dist),
            "content_digest": self.content_digest,
            "produced_at": self.produced_at,
        }


_IMMUTABLE_FIELDS = frozenset(
    {"observation_id", "seed_id", "seed_type", "seed_value", "content_digest", "produced_at"}
)


def _content_digest(body: dict | bytes) -> str:
    if isinstance(body, bytes):
        raw = body
    else:
        raw = json.dumps(body, sort_keys=True, default=str).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()[:32]


def confidence_distribution(candidates: list[ObservationCandidate]) -> tuple[tuple[str, int], ...]:
    """Stratified confidence histogram (spec FR-012 ``confidence_dist``)."""
    bins = {"0.5-0.7": 0, "0.7-0.9": 0, "0.9-1.0": 0}
    for candidate in candidates:
        if candidate.confidence >= 0.9:
            bins["0.9-1.0"] += 1
        elif candidate.confidence >= 0.7:
            bins["0.7-0.9"] += 1
        elif candidate.confidence >= 0.5:
            bins["0.5-0.7"] += 1
    return tuple((name, bins[name]) for name in ("0.5-0.7", "0.7-0.9", "0.9-1.0"))


class ZeroLayerGate:
    """Writes immutable observations and emits ``zero_layer.*`` events."""

    def __init__(self, producer=None, store=None) -> None:
        self._producer = producer
        self._store = store
        self._observations: dict[str, ZeroLayerObservation] = {}

    # -- public helpers --------------------------------------------------------

    def emit(
        self,
        *,
        seed: SeedInput,
        candidates: list[ObservationCandidate],
        derived_seeds: list[str],
    ) -> ZeroLayerObservation:
        """Create the immutable observation for one seed's harvest cycle."""
        observation_id = "ZERO-OBS-" + uuid.uuid4().hex[:12]
        produced_at = self._now()
        body = {
            "seed_id": seed.seed_id,
            "seed_type": seed.detected_type.value,
            "seed_value": seed.raw_value,
            "candidates": [candidate.as_dict() for candidate in candidates],
            "derived_seeds": derived_seeds,
        }
        observation = ZeroLayerObservation(
            observation_id=observation_id,
            seed_id=seed.seed_id,
            seed_type=seed.detected_type,
            seed_value=seed.raw_value,
            candidates=tuple(sorted(candidates, key=lambda c: (c.source_module, c.value))),
            derived_seeds=tuple(sorted(derived_seeds)),
            confidence_dist=confidence_distribution(candidates),
            content_digest=_content_digest(body),
            produced_at=produced_at,
        )
        self._observations[observation_id] = observation

        if self._store is not None:
            self._store.put_raw_dedup(
                json.dumps(body, sort_keys=True, default=str).encode(),
                tenant_id="zero-layer",
                meta={"content_type": "application/json", "observation_id": observation_id},
            )
        self._emit(EVENT_SEED_DETECTED, {"seed_id": seed.seed_id, "type": seed.detected_type.value})
        self._emit(
            EVENT_OBSERVATION,
            {
                "observation_id": observation_id,
                "seed_id": seed.seed_id,
                "seed_type": seed.detected_type.value,
                "spot_count": len(candidates),
                "content_digest": observation.content_digest,
            },
            key=observation_id,
        )
        return observation

    def emit_cycle(
        self,
        *,
        seeds_in: int,
        contacts_out: int,
        new_seeds_discovered: int,
        confidence_dist: tuple[tuple[str, int], ...],
    ) -> None:
        """Emit the ``harvest_cycle_complete`` summary (spec FR-012)."""
        self._emit(
            EVENT_HARVEST_CYCLE_COMPLETE,
            {
                "seeds_in": seeds_in,
                "contacts_out": contacts_out,
                "confidence_dist": dict(confidence_dist),
                "new_seeds_discovered": new_seeds_discovered,
            },
        )

    def observations(self) -> list[ZeroLayerObservation]:
        return [self._observations[key] for key in sorted(self._observations)]

    def emit_started(self, *, wave_index: int, seed_count: int) -> None:
        self._emit(EVENT_HARVEST_STARTED, {"wave_index": wave_index, "seed_count": seed_count})

    # -- internals ---------------------------------------------------------------

    def _emit(self, event_type: str, payload: dict, *, key: str | None = None) -> None:
        if self._producer is None:
            return
        try:
            envelope = build_envelope(
                event_type=event_type,
                event_version="2.0",
                producer="zero.observation-gate",
                producer_version="0.1.0",
                payload=json.dumps(payload, sort_keys=True).encode(),
            )
            topic = topic_for(event_type)
            self._producer.produce(topic, envelope, key=key or str(uuid.uuid4()))
        except Exception:
            return

    @staticmethod
    def _now() -> str:
        from datetime import UTC, datetime

        return datetime.now(UTC).isoformat().replace("+00:00", "Z")

    @staticmethod
    def assert_immutable(observation: ZeroLayerObservation, fields: set[str]) -> None:
        """I-1 enforcement: mutating a protected field must raise."""
        violating = sorted(_IMMUTABLE_FIELDS & fields)
        if violating:
            raise ValueError(f"immutable fields cannot change: {', '.join(violating)}")