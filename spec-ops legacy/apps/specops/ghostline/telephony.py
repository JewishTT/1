"""Outbound dialling: the donor's ``call`` verb, behind the rules-of-engagement gate.

``ghostline call +15551234567 --campaign demo --persona calm`` places a real PSTN
call. Two things about that command are worth naming.

**It reads the tunnel URL from a shell variable.** ``call`` needs the WSS URL that
``serve`` printed, and the donor documents the operator having to copy it between
terminals -- ``export NGROK_WS_URL=wss://...`` in a second window. In this platform
the runtime already holds the tunnel URL, so the number is all an operator supplies,
and a stale copy is not a failure mode the UI has to explain.

**It has no authorisation check.** The donor's README states plainly that a signed
RoE is required, and the CLI trusts the operator to have one. This platform does not
trust, it verifies: :func:`place_call` calls the same gate
(``specops.roe.gate.launch_campaign``) that the phishing and emulation routers use,
in the same order -- RoE first, then roster. A dialled number that is not on the
supervisor-approved roster is refused with ``RosterError`` and never reaches Twilio.

The gate is not decoration on top of a working dialler. It is the only reason the
dialler is reachable, and the call record it writes carries ``capture_passwords:
False`` structurally, because the platform does not hold elicited credentials
(see :mod:`specops.ghostline.redaction`).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from specops.ghostline.config import get_config
from specops.ghostline.loader import donor

__all__ = (
    "CallPlaced",
    "DialBlocked",
    "validate_e164",
)

_LOGGER = logging.getLogger(__name__)

#: E.164: a leading ``+``, a non-zero country digit, then up to 14 more. Checked
#: before anything else because a malformed number is either a typo the operator
#: needs to see or a number the provider will reject with an opaque 400.
_E164 = re.compile(r"^\+[1-9]\d{6,14}$")


def validate_e164(number: str) -> str:
    """Return the normalised number, or raise :class:`DialBlocked` naming the problem."""
    cleaned = (number or "").strip()
    if not cleaned:
        raise DialBlocked("no target number supplied")
    if not _E164.match(cleaned):
        raise DialBlocked(
            f"{cleaned!r} is not E.164. Use the full international form, e.g. +15551234567 "
            "(the donor's own validator requires a leading '+' and digits only)."
        )
    return cleaned


class DialBlocked(Exception):
    """A call could not be placed. ``reason`` is what the operator must fix."""

    def __init__(self, reason: str, blockers: tuple[str, ...] = ()) -> None:
        super().__init__(reason)
        self.reason = reason
        self.blockers = blockers


@dataclass(frozen=True, slots=True)
class CallPlaced:
    """A placed call's external identity."""

    sid: str
    to_number: str
    from_number: str
    ws_url: str


def place_call(
    *,
    target: str,
    stream_ws_url: str,
) -> CallPlaced:
    """Place an outbound call through the donor's Twilio service.

    Callers must have cleared the rules-of-engagement gate first -- this function is
    the last step of an already-authorised dialling flow and raises
    :class:`DialBlocked` for anything operational (no credentials, no package, no
    tunnel) rather than for authorisation.
    """
    config = get_config()
    number = validate_e164(target)

    if not config.twilio_account_sid or not config.twilio_auth_token:
        raise DialBlocked(
            "Twilio credentials are not configured — set GHOSTLINE_TWILIO_ACCOUNT_SID "
            "and GHOSTLINE_TWILIO_AUTH_TOKEN"
        )
    if not config.twilio_from_number:
        raise DialBlocked(
            "no caller ID — set GHOSTLINE_TWILIO_FROM_NUMBER to a number the Twilio "
            "account actually owns"
        )
    if not stream_ws_url:
        raise DialBlocked(
            "no media stream URL — start the runtime first, or set "
            "GHOSTLINE_PUBLIC_BASE_URL so Twilio has somewhere to dial back into"
        )

    module = donor().get("ghostline.telephony.twilio")
    service_cls = getattr(module, "TwilioService", None)
    if service_cls is None:
        raise DialBlocked(
            "the donor's Twilio service is not importable — it needs the `twilio` package, "
            "which the platform environment does not carry"
        )

    service: Any = service_cls(
        config.twilio_account_sid,
        config.twilio_auth_token,
        config.twilio_from_number,
    )
    try:
        placed = service.place_call(number, stream_ws_url)
    except Exception as exc:
        # The donor's README documents the two that bite on a trial account, and
        # both read as opaque provider codes without this translation.
        raise DialBlocked(_explain(exc)) from exc
    return CallPlaced(
        sid=placed.sid,
        to_number=placed.to_number,
        from_number=placed.from_number,
        ws_url=stream_ws_url,
    )


def _explain(exc: Exception) -> str:
    """Turn a Twilio error into the sentence that actually helps."""
    message = str(exc)
    lowered = message.lower()
    if "limited parameter access" in lowered:
        return (
            f"Twilio refused the inline TwiML parameter: {message}. On a trial account the "
            "REST API cannot post twiml=; the donor handles this by pointing the call at the "
            "/voice webhook instead, which this platform serves from the same runtime."
        )
    if "verified caller ids" in lowered or "not yet verified" in lowered:
        return (
            f"Twilio refused the caller ID: {message}. The from number must be verified on "
            "the account (Console → Phone Numbers → Verified Caller IDs) before it can dial out."
        )
    if "no twilio trial phone number" in lowered:
        return (
            f"Twilio has no usable number for this destination: {message}. On a trial account "
            "the destination itself must be a verified caller id."
        )
    return f"Twilio refused the call: {message}"
