"""The seam: consume ``science.*`` results and feed them back into a context.

Before this, the science layer computed verdicts that reached nothing. Every
``envelope()`` call passed ``producer=None``, so ``topics.EVENT_CATALOG`` listed
18 ``science.*`` types on topic ``science`` while no producer published to it and
no consumer subscribed. Eight HTTP routes called the algorithms synchronously
and dropped the result on return.

This module supplies the missing half. It is a plain function rather than a
daemon because the transport is injected: the caller owns the broker connection,
so the same code runs under the Temporal worker, under a test, or under a
one-shot replay without a broker at all.
"""

from __future__ import annotations

import json
from typing import Any

from events.kafka import Envelope
from events.topics import topic_for
from store import shared_store

from context_engine.loop import ScienceFeedback

#: Event types whose payload carries a claim/verdict the context engine can act on.
#: Structure and calibration results are recorded projections, not questions.
FEEDBACK_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "science.claim.status_changed",
        "science.calibration.report",
        "science.causal.classified",
        "science.robustness.report",
        "science.temporal.change_point",
    }
)

_OUTCOME_BY_STATUS: dict[str, str] = {
    "discarded": "refuted",
    "weakened": "drifted",
    "uncertain": "inconclusive",
    "confirmed": "supported",
    "resolved": "supported",
    "identified": "supported",
    "estimated": "supported",
    "refuted": "refuted",
    "inconclusive": "inconclusive",
}


def feedback_from_envelope(envelope: Envelope) -> ScienceFeedback | None:
    """Translate one science envelope, or ``None`` when it carries no verdict.

    Returning ``None`` is normal and not an error: most science events are
    projections an analyst reads later. Only events that change what the
    investigation still needs to ask become signals.
    """
    if envelope.event_type not in FEEDBACK_EVENT_TYPES:
        return None
    try:
        payload = json.loads(envelope.payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        # A malformed record is not a verdict. Silently coercing it into
        # "inconclusive" would manufacture an obligation from a corrupt byte.
        return None
    if not isinstance(payload, dict):
        return None

    outcome = _outcome_for(envelope.event_type, payload)
    if outcome is None:
        return None

    claim_ref = _claim_ref_for(envelope.event_type, payload)
    if not claim_ref:
        return None

    return ScienceFeedback(
        outcome=outcome,
        claim_ref=claim_ref,
        detail=_detail_for(envelope.event_type, payload),
        snapshot_id=str(payload.get("snapshot_id") or ""),
        method_fingerprint=str(payload.get("method_fingerprint") or ""),
    )


def _outcome_for(event_type: str, payload: dict[str, Any]) -> str | None:
    if event_type == "science.claim.status_changed":
        return _OUTCOME_BY_STATUS.get(str(payload.get("to_status") or ""))
    if event_type == "science.calibration.report":
        verdict = str(payload.get("verdict") or "").lower()
        if verdict == "overconfident":
            return "drifted"
        if verdict == "calibrated":
            return "supported"
        return "inconclusive"
    if event_type == "science.causal.classified":
        label = str(payload.get("label") or "").lower()
        return "supported" if label == "causal" else "inconclusive"
    if event_type == "science.robustness.report":
        flip_rate = _worst_flip_rate(payload)
        if flip_rate is None:
            return "inconclusive"
        # A claim that flips under perturbation has a verdict that does not
        # survive contact with the evidence; that is drift, not support.
        return "drifted" if flip_rate > 0.0 else "supported"
    if event_type == "science.temporal.change_point":
        return "drifted"
    return None


def _worst_flip_rate(payload: dict[str, Any]) -> float | None:
    rates = payload.get("flip_rates")
    if not isinstance(rates, dict) or not rates:
        return None
    try:
        return max(float(value) for value in rates.values())
    except (TypeError, ValueError):
        return None


def _claim_ref_for(event_type: str, payload: dict[str, Any]) -> str:
    for key in ("claim_ref", "claim_id", "report_id", "conclusion_id", "result_id", "series_id"):
        value = payload.get(key)
        if value:
            return str(value)
    return ""


def _detail_for(event_type: str, payload: dict[str, Any]) -> str:
    if event_type == "science.calibration.report":
        drift = payload.get("drift")
        return f"calibration verdict={payload.get('verdict')} drift={drift}"
    if event_type == "science.robustness.report":
        rates = payload.get("flip_rates")
        return f"flip rates: {rates}"
    if event_type == "science.temporal.change_point":
        return f"change point at {payload.get('index')}"
    if event_type == "science.causal.classified":
        return f"causal label={payload.get('label')}"
    return f"claim status -> {payload.get('to_status')}"


def project_and_translate(envelope: Envelope) -> ScienceFeedback | None:
    """Apply to the projection, then translate. One pass, both effects.

    Applying first keeps I-12 honest: the log must determine the snapshot, so the
    record is folded in whether or not it yields a signal.
    """
    shared_store().apply(envelope)
    return feedback_from_envelope(envelope)


def science_topic() -> str:
    """The single topic every ``science.*`` type routes to."""
    return topic_for("science.claim.registered")
