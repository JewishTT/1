"""``envelope()`` emitter helper for the Scientific Intelligence Fabric (T089).

First-party scientific module (feature 006); emission pattern mirrors the
admission/resolution modules (feature 005): build a ``build_envelope`` envelope,
validate the event type against ``EVENT_CATALOG``/``topic_for``, serialise the
payload as refs-only JSON (Constitution I-5 — no raw blobs), and optionally
produce through an injected ``IdempotentProducer`` so tests stay hermetic.

The Science fabric emits ``science.*`` events only (registered in
``events.topics``); every topic is append-only and replayable (I-12).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from events.kafka import Envelope, build_envelope
from events.topics import topic_for

PRODUCER_NAME = "science.fabric"
PRODUCER_VERSION = "0.1.0"

SCALAR = (str, int, float, bool, type(None))


def _assert_refs_only(payload: dict[str, Any], _path: str = "payload") -> None:
    """Enforce refs-only payloads (I-5): no bytes, no arbitrary objects."""
    for key, value in payload.items():
        if isinstance(value, dict):
            _assert_refs_only(value, f"{_path}.{key}")
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, list):
                    _assert_refs_only({str(i): item for i in range(len(item))}, f"{_path}.{key}")
                elif isinstance(item, dict):
                    _assert_refs_only(item, f"{_path}.{key}")
                elif not isinstance(item, SCALAR):
                    raise TypeError(f"{_path}.{key}: non-ref value {type(item).__name__}")
        elif not isinstance(value, SCALAR):
            raise TypeError(f"{_path}.{key}: non-ref value {type(value).__name__}")


def envelope(
    *,
    event_type: str,
    payload: dict[str, Any],
    producer: Any = None,
    key: str | None = None,
    on_error: Callable[[Envelope, Exception], None] | None = None,
    **ids: str | None,
) -> Envelope:
    """Build (and optionally emit) a ``science.*`` envelope.

    ``ids`` pass through to ``build_envelope`` (``investigation_id``,
    ``correlation_id``, ``causation_id``, ``observation_id``, ``entity_id``,
    ``event_id``). The topic is resolved from ``EVENT_CATALOG`` — an unknown
    event type fails fast. Payloads must be refs/fields-only scalar JSON.
    """
    topic = topic_for(event_type)  # KeyError -> UnknownEventTypeError
    _assert_refs_only(payload)
    env = build_envelope(
        event_type=event_type,
        event_version="1.0",
        producer=PRODUCER_NAME,
        producer_version=PRODUCER_VERSION,
        payload=json.dumps(payload, default=str, sort_keys=True).encode("utf-8"),
        **ids,
    )
    if producer is not None:
        producer.produce(topic, env, key=(key or env.event_id), on_error=on_error)
    return env