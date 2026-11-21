"""HMAC approval tokens for live execution.

A live run is authorized by a token bound to the plan digest. Editing any node,
amount, destination or edge changes the digest and invalidates the token, so an
approval for one plan cannot be replayed onto another. Tokens expire.

The secret is never logged or returned. An unset or short secret disables live
execution entirely rather than falling back to a weaker check.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from specops.cryptotx.errors import ApprovalRequired, PolicyError

_VERSION = "v1"
_MIN_SECRET = 16


def _secret(secret: str | None) -> str:
    if not secret:
        raise ApprovalRequired(
            "CRYPTOTX_APPROVAL_SECRET is not configured; live broadcasts are disabled"
        )
    if len(secret) < _MIN_SECRET:
        raise PolicyError(
            f"CRYPTOTX_APPROVAL_SECRET must be at least {_MIN_SECRET} characters"
        )
    return secret


def _message(plan_digest: str, expiry: int) -> bytes:
    return f"cryptotx:{_VERSION}:{plan_digest}:{expiry}".encode()


def mint_approval_token(
    plan_digest: str, secret: str | None, *, ttl_s: int = 900
) -> str:
    """Mint ``v1.<expiry>.<hmac>`` for one plan digest."""
    key = _secret(secret)
    if ttl_s <= 0:
        raise PolicyError("approval ttl must be positive")
    expiry = int(time.time()) + int(ttl_s)
    signature = hmac.new(key.encode("utf-8"), _message(plan_digest, expiry),
                         hashlib.sha256).hexdigest()
    return f"{_VERSION}.{expiry}.{signature}"


def verify_approval_token(
    plan_digest: str, token: str | None, secret: str | None
) -> int:
    """Return the expiry when the token authorizes this digest, else raise."""
    key = _secret(secret)
    if not token:
        raise ApprovalRequired("live execution requires an approval token")
    parts = token.strip().split(".")
    if len(parts) != 3 or parts[0] != _VERSION:
        raise ApprovalRequired("approval token is malformed")
    try:
        expiry = int(parts[1])
    except ValueError as exc:
        raise ApprovalRequired("approval token has no valid expiry") from exc
    expected = hmac.new(key.encode("utf-8"), _message(plan_digest, expiry),
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, parts[2]):
        raise ApprovalRequired("approval token does not authorize this plan")
    if expiry <= int(time.time()):
        raise ApprovalRequired("approval token has expired")
    return expiry
