"""Logical-time validation for event payloads.

Feature 024, decision D5=b. ``EventEnvelope`` stays at 16 fields -- ``observed_at``
and ``logical_time`` travel inside typed payloads. This module is the executable
half of the convention written up in
``specs/024-context-driven-continuous-intelligence/contracts.md``.

Pure and broker-free on purpose: the convention must be checkable without standing
up infrastructure, and without a live broker in the import path.

Taken from platform code: ``events.kafka.now_rfc3339`` supplies the canonical
RFC 3339 UTC format, so this module does not invent a second time format.
"""

from __future__ import annotations

from datetime import UTC, datetime

OBSERVED_AT = "observed_at"
LOGICAL_TIME = "logical_time"

#: Event types that legitimately carry no evidence/logical time, with the reason.
#: Anything added needs a justification -- an observation-bearing event never
#: belongs here. A transport-level signal does.
NO_LOGICAL_TIME: dict[str, str] = {}


class TimestampContractError(ValueError):
    """A payload violates the logical-time convention."""


def _parse(value: object, *, field: str, event_type: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise TimestampContractError(
            f"[{event_type}] {field} must be a non-empty RFC 3339 string, got {value!r}"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TimestampContractError(
            f"[{event_type}] {field} is not RFC 3339: {value!r}"
        ) from exc
    if parsed.tzinfo is None:
        raise TimestampContractError(
            f"[{event_type}] {field} is timezone-naive: {value!r}. A naive timestamp "
            "crossing the transport boundary is a defect."
        )
    return parsed


def validate_payload(event_type: str, payload: dict[str, object]) -> None:
    """Validate one decoded payload against the convention.

    Raises ``TimestampContractError`` on violation. Returns None when valid.
    """
    if not isinstance(payload, dict):
        raise TimestampContractError(
            f"[{event_type}] payload must be a mapping, got {type(payload).__name__}"
        )

    has_observed = OBSERVED_AT in payload
    has_logical = LOGICAL_TIME in payload

    if not has_observed and not has_logical:
        reason = NO_LOGICAL_TIME.get(event_type)
        if reason is None:
            raise TimestampContractError(
                f"[{event_type}] carries no {OBSERVED_AT} and no {LOGICAL_TIME}. "
                "Events that describe something that happened must declare its time. "
                "If this event genuinely has no logical time, register it in "
                "NO_LOGICAL_TIME with a reason."
            )
        return

    if has_observed:
        _parse(payload[OBSERVED_AT], field=OBSERVED_AT, event_type=event_type)

    if has_logical:
        span = payload[LOGICAL_TIME]
        if not isinstance(span, dict):
            raise TimestampContractError(
                f"[{event_type}] {LOGICAL_TIME} must be a mapping with 'from' and 'to'."
            )
        for bound in ("from", "to"):
            if bound not in span:
                raise TimestampContractError(
                    f"[{event_type}] {LOGICAL_TIME} is missing '{bound}'."
                )
        start = _parse(span["from"], field=f"{LOGICAL_TIME}.from", event_type=event_type)
        end = _parse(span["to"], field=f"{LOGICAL_TIME}.to", event_type=event_type)
        if end < start:
            raise TimestampContractError(
                f"[{event_type}] {LOGICAL_TIME} is inverted: {span['from']!r} > {span['to']!r}"
            )


def validate_against_produced_at(
    event_type: str, payload: dict[str, object], produced_at: str
) -> None:
    """Additionally reject a ``produced_at`` copied into ``observed_at``.

    Envelope time answers "when did the platform learn this"; payload time answers
    "when did this happen". Copying one into the other fabricates evidence, so it is
    treated as a contract violation rather than a style issue.
    """
    validate_payload(event_type, payload)
    if produced_at and payload.get(OBSERVED_AT) == produced_at:
        raise TimestampContractError(
            f"[{event_type}] {OBSERVED_AT} equals the envelope produced_at "
            f"({produced_at!r}). Transport production time is not evidence time."
        )


__all__ = [
    "LOGICAL_TIME",
    "NO_LOGICAL_TIME",
    "OBSERVED_AT",
    "TimestampContractError",
    "UTC",
    "validate_against_produced_at",
    "validate_payload",
]
