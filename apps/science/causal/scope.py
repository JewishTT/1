"""Shared scope-boundary guard (T086, FR-007 / contracts/scope-boundary.md).

Single code-level implementation wired into every Science entry point so no
future module can bypass the hard exclusion by omission (No-MVP rule): person-
level sensitive outcome classes are refused *before* any computation
(``422 scope_refused`` for consumers).

On refusal the guard builds a ``science.causal.scope_rejected`` audit envelope
(refs + policy, I-5) and optionally produces it through an injected producer.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from _events import Envelope
from _events import envelope as _audit_envelope
from errors import ScopeBoundaryError

POLICY_REF = "contracts/scope-boundary.md"

FORBIDDEN_CLASSES: frozenset[str] = frozenset(
    {
        "political-affiliation",
        "political-views",
        "illegal-activity-involvement",
        "marginalized-group-membership",
    }
)

# Coarse person-attribution sniffing for outcome attributes that missed the
# canonical class vocab. Deliberately conservative: anything "of a natural
# person / individual" is refused over refusing too little.
_PERSON_MARKERS = (
    re.compile(r"\bperson(?:al|ally)?\b", re.IGNORECASE),
    re.compile(r"\bindividual\b", re.IGNORECASE),
    re.compile(r"\b(?:his|her|their)\s+\w+\b", re.IGNORECASE),
)

_POLICY_MARKERS = (
    "political",
    "party_membership",
    "voting",
    "illegal",
    "criminal",
    "felony",
    "marginalized",
    "protected_group",
    "vulnerable_group",
    "minority",
    "politics",
)

_AUDIT_FIELDS = ("event_id", "outcome_class", "entry_point", "actor", "policy", "at")


def _forbidden_reason(outcome_attribute: str) -> str | None:
    """Return the matched forbidden reason, or ``None`` when the attribute is in scope."""
    normalized = outcome_attribute.strip().lower()
    if normalized in FORBIDDEN_CLASSES:
        return "hard-excluded class"
    if any(marker.search(normalized) for marker in _PERSON_MARKERS):
        return "person-level attribution"
    if any(token in normalized for token in _POLICY_MARKERS):
        return "sensitive attribute (policy/illegal/marginalized marker)"
    return None


def ensure_scoped(
    outcome_attribute: str,
    *,
    entry_point: str = "<unspecified>",
    actor: str | None = None,
    producer: Any = None,
    on_error: Callable[[Envelope, Exception], None] | None = None,
) -> None:
    """Refuse person-level sensitive outcomes before any computation (FR-007).

    Registers a ``science.causal.scope_rejected`` audit event on every refusal.
    Raises ``ScopeBoundaryError`` (consumed as ``422 scope_refused``).
    """
    reason = _forbidden_reason(outcome_attribute)
    if reason is None:
        return
    _audit_envelope(
        event_type="science.causal.scope_rejected",
        payload={
            "outcome_class": outcome_attribute.strip(),
            "reason": reason,
            "entry_point": entry_point,
            "policy": POLICY_REF,
        },
        producer=producer,
        on_error=on_error,
        correlation_id=_actor_correlation(actor),
    )
    raise ScopeBoundaryError(outcome_attribute)


def _actor_correlation(actor: str | None) -> str | None:
    return actor


def audit_fields() -> tuple[str, ...]:
    """Canonical scope-rejection audit field names (contracts/scope-boundary.md §Audit)."""
    return _AUDIT_FIELDS