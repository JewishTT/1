"""Read-back from the observation topic, shared by the proof scripts.

Why this exists
---------------
Three proof scripts (``_prove_airbyte``, ``_prove_tools``, ``_prove_searxng``) each
reimplemented "publish, then read it back off the broker" and each crashed the same
way: ``protobuf DecodeError: Wire format was corrupt``.

The cause is a real modelling fact, not a flake. ``observation`` is a **shared,
long-lived topic**: every producer in every prior run writes to it, and the topic
outlives any single test. Reading it with ``auto.offset.reset=earliest`` therefore
returns messages this run never wrote - including traffic from other producers whose
payload is not an ``EventEnvelope``. Parsing all of them unconditionally throws, and
because the exception is not caught the proof dies before it can report anything.

The fix is to stop parsing messages that cannot possibly be ours. The producer keys
every observation message by its ``observation_id``, so the key alone decides
membership: **filter on the key, parse only what matched, count what did not.**

A proof that cannot read its own writes back is not a proof, so this is the piece that
makes the other half of every integration script meaningful rather than decorative.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ReadBack:
    """What the broker actually returned."""

    found: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: Messages consumed and deliberately not parsed because the key was not ours.
    foreign: int = 0
    #: Messages that claimed our key but did not decode. Must be zero: it would mean
    #: the broker holds something unreadable under our own identity.
    undecodable: list[str] = field(default_factory=list)
    consumed: int = 0
    elapsed: float = 0.0

    @property
    def complete(self) -> bool:
        return not self.undecodable

    def to_dict(self) -> dict[str, Any]:
        return {
            "found": self.found,
            "foreign_skipped": self.foreign,
            "undecodable": self.undecodable,
            "consumed": self.consumed,
            "elapsed": round(self.elapsed, 2),
            "complete": self.complete,
        }


def read_back(
    brokers: str,
    topic: str,
    wanted: set[str],
    *,
    group: str,
    timeout: float = 60.0,
    parse_envelope: bool = True,
) -> ReadBack:
    """Consume ``topic`` until every id in ``wanted`` is seen or ``timeout`` elapses.

    ``parse_envelope`` decodes each match as an ``EventEnvelope``. Set it False when the
    caller only needs the offset/partition, or when the topic does not carry envelopes.
    """
    from confluent_kafka import Consumer

    result = ReadBack()
    consumer = Consumer(
        {
            "bootstrap.servers": brokers,
            "group.id": group,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    started = time.monotonic()
    try:
        consumer.subscribe([topic])
        while time.monotonic() - started < timeout and len(result.found) < len(wanted):
            msg = consumer.poll(1.0)
            if msg is None or msg.error():
                continue
            result.consumed += 1
            key = msg.key()
            observation_id = key.decode("utf-8", "replace") if key else ""
            if observation_id not in wanted:
                # The whole point: not ours, so not ours to decode.
                result.foreign += 1
                continue
            record: dict[str, Any] = {
                "topic": msg.topic(),
                "partition": msg.partition(),
                "offset": msg.offset(),
                "key": observation_id,
            }
            if parse_envelope:
                envelope = _decode(msg.value())
                if envelope is None:
                    result.undecodable.append(observation_id)
                    continue
                record["event_id"] = getattr(envelope, "event_id", "")
                record["event_type"] = getattr(envelope, "event_type", "")
                record["producer"] = getattr(envelope, "producer", "")
            result.found[observation_id] = record
    finally:
        consumer.close()
        result.elapsed = time.monotonic() - started
    return result


def _decode(payload: bytes | None) -> Any | None:
    if not payload:
        return None
    try:
        from events import event_envelope_pb2 as pb
    except ImportError:  # pragma: no cover - import shape differs by app layout
        try:
            from events import pb2 as pb  # type: ignore[no-redef]
        except ImportError:
            return None
    envelope = pb.EventEnvelope()
    try:
        envelope.ParseFromString(payload)
    except Exception:
        return None
    return envelope


__all__ = ["ReadBack", "read_back"]
