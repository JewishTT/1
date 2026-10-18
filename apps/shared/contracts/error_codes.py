"""Stable error codes and the three categories they may never be conflated within.

Spec 030 contract 07 / FR-047, FR-090, FR-096, FR-100 / task T031.

**A client parses a code, not a string.** Every failure surface -- API, event, operator result,
replay -- carries a member of :class:`ErrorCode`. The category it belongs to is a property of
the code itself (:attr:`ErrorCode.category`), not a judgement a handler makes at the call site,
because a handler that guesses the category is exactly how an expected-negative gets retried
until a budget dies.

**Cross-tenant access is indistinguishable from absence, byte for byte.**
:func:`cross_tenant_envelope` deliberately does *not* emit ``TENANT_SCOPE_VIOLATION``. It emits
the same envelope, with the same code, the same fields and the same bytes, that a genuinely
absent object produces -- and the one piece of information that does differ (that this was a
cross-tenant reference rather than a typo) is kept in :attr:`ErrorEnvelope.internal_reason`,
which is deliberately **not** part of :meth:`ErrorEnvelope.as_wire`. Returning a distinguishable
code is an existence oracle: an attacker enumerates tenant-visible ids and reads ``200`` vs
``403`` to learn what other tenants hold. The cost of not distinguishing is one confusing
support ticket. The cost of distinguishing is a directory of other people's investigations.

**No raw content, ever.** :class:`ErrorEnvelope` refuses a field whose name looks like payload
or credential and a value that looks like a secret, because the fastest way to leak source
content is to put it in the ``detail`` of an error (FR-096).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from contracts.canonical import canonical_bytes, canonical_json

__all__ = [
    "ErrorCategory",
    "ErrorCode",
    "ErrorEnvelope",
    "ErrorSurfaceError",
    "EmptyStateEnvelope",
    "CrossTenantIndistinguishabilityError",
    "absence_envelope",
    "cross_tenant_envelope",
    "is_release_blocker",
    "release_blocker_codes",
    "ABSENCE_CODES",
]


class ErrorSurfaceError(ValueError):
    """An error surface would have leaked, lied or degraded. Refused rather than emitted."""


class CrossTenantIndistinguishabilityError(ErrorSurfaceError):
    """Something tried to make a cross-tenant refusal distinguishable from an absence.

    Raised, never warned about. A distinguishable cross-tenant response is a confirmed
    existence path, and an existence path that is merely logged is still an existence path.
    """


class ErrorCategory(StrEnum):
    """The three categories. Retry behaviour is a function of the category, so they stay apart.

    * ``EXPECTED_NEGATIVE`` -- a real answer. Report it; do not retry. Retrying a
      ``POLICY_BLOCKED`` until a budget dies converts a refusal into a denial of service
      against ourselves.
    * ``RETRYABLE_INFRA`` -- the answer is genuinely unknown because the plumbing was not there.
      Back off within budget.
    * ``DEFECT`` -- we are wrong. Fail loudly. **A degraded-but-valid answer is never returned
      where a defect occurred**, which is the rule this category exists to protect.
    """

    EXPECTED_NEGATIVE = "expected_negative"
    RETRYABLE_INFRA = "retryable_infra"
    DEFECT = "defect"

    @property
    def is_retryable(self) -> bool:
        return self is ErrorCategory.RETRYABLE_INFRA


class ErrorCode(StrEnum):
    """Every machine-readable failure the platform may report.

    Members carry their category and their contract-07 section in their names, so a handler
    cannot read a code without also reading how it is meant to be treated. The six codes in
    :attr:`CONTRACT_03_ONLY` are the contract-03 failure classes that contract 07's table does
    not list; they are here because the two documents are both normative and a failure carrying
    a class from one must still have a category from the other.
    """

    # -- context and revision ------------------------------------------------
    UNKNOWN_CONTEXT = "UNKNOWN_CONTEXT"
    STALE_CONTEXT_REVISION = "STALE_CONTEXT_REVISION"
    REVISION_CONFLICT = "REVISION_CONFLICT"
    REPLAY_MISMATCH = "REPLAY_MISMATCH"
    DECISION_RECORD_MISSING = "DECISION_RECORD_MISSING"

    # -- policy, scope and budget -------------------------------------------
    POLICY_BLOCKED = "POLICY_BLOCKED"
    SCOPE_VIOLATION = "SCOPE_VIOLATION"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    TENANT_SCOPE_VIOLATION = "TENANT_SCOPE_VIOLATION"

    # -- capability and source ----------------------------------------------
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    UNSUPPORTED_QUERY = "UNSUPPORTED_QUERY"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    DETECTION_POWER_UNKNOWN = "DETECTION_POWER_UNKNOWN"

    # -- placement -----------------------------------------------------------
    NO_MEMBERSHIP = "NO_MEMBERSHIP"
    NO_ANCHOR = "NO_ANCHOR"
    PLACEMENT_PENDING = "PLACEMENT_PENDING"

    # -- projection and operator --------------------------------------------
    PROJECTION_STALE = "PROJECTION_STALE"
    PROJECTION_FAILED = "PROJECTION_FAILED"
    OPERATOR_TIMEOUT = "OPERATOR_TIMEOUT"
    OPERATOR_OUTPUT_INVALID = "OPERATOR_OUTPUT_INVALID"
    SCHEMA_INCOMPATIBLE = "SCHEMA_INCOMPATIBLE"
    CAPACITY_GAP = "CAPACITY_GAP"

    # -- evidence and provenance --------------------------------------------
    SPAN_UNRESOLVABLE = "SPAN_UNRESOLVABLE"
    SPAN_SEMANTICS_MISMATCH = "SPAN_SEMANTICS_MISMATCH"
    PROVENANCE_INCOMPLETE = "PROVENANCE_INCOMPLETE"
    IMMUTABLE_VIOLATION = "IMMUTABLE_VIOLATION"

    # -- identity ------------------------------------------------------------
    RESOLUTION_DEFERRAL = "RESOLUTION_DEFERRAL"
    RESOLUTION_REJECTED = "RESOLUTION_REJECTED"
    UNVERIFIED_DONOR = "UNVERIFIED_DONOR"
    LICENCE_BLOCKED = "LICENCE_BLOCKED"

    # -- contract-03 failure classes contract 07's table does not name -------
    TIMEOUT = "TIMEOUT"
    TRANSIENT_INFRA = "TRANSIENT_INFRA"
    RESOURCE_CAP = "RESOURCE_CAP"
    EXPECTED_NO_RESULT = "EXPECTED_NO_RESULT"
    MALFORMED_INPUT = "MALFORMED_INPUT"
    PARTIAL_OUTPUT = "PARTIAL_OUTPUT"
    QUARANTINED = "QUARANTINED"
    PERMANENT_OPERATOR_ERROR = "PERMANENT_OPERATOR_ERROR"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    ADMISSION_REJECTED = "ADMISSION_REJECTED"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"

    @property
    def category(self) -> ErrorCategory:
        """How this code must be treated. A property of the code, never a caller decision."""
        return _CATEGORIES[self]

    @property
    def is_retryable(self) -> bool:
        return _CATEGORIES[self].is_retryable

    @property
    def is_release_blocker(self) -> bool:
        """Whether emitting this code in production is a release blocker.

        Three conditions from contract 07's validation table. ``IMMUTABLE_VIOLATION`` because
        an immutable raw object was modified. ``DETECTION_POWER_UNKNOWN`` because presenting it
        as absence is an unearned negative claim. ``REPLAY_MISMATCH`` because the alternative to
        failing loudly is accepting the newer output, which silently discards reproducibility.
        """
        return self in _RELEASE_BLOCKERS

    @property
    def must_degrade(self) -> bool:
        """Whether the response must be an explicit degraded status rather than a valid answer.

        "A degraded-but-valid answer is never returned where a defect occurred." A missing
        dependency must produce an explicit unsupported/degraded status, never silent success.
        """
        return _CATEGORIES[self] is ErrorCategory.DEFECT

    @classmethod
    def parse(cls, raw: str) -> ErrorCode:
        """Read a code off the wire, refusing anything not in the table (R1)."""
        try:
            return cls(str(raw).strip())
        except ValueError as exc:
            raise ErrorSurfaceError(
                f"{raw!r} is not a declared error code; clients parse codes, not message text, "
                "so an unknown code cannot be classified and must not be guessed at"
            ) from exc


#: The codes whose emission in production is a release blocker (contract 07 validation).
_RELEASE_BLOCKERS = frozenset(
    {
        ErrorCode.IMMUTABLE_VIOLATION,
        ErrorCode.DETECTION_POWER_UNKNOWN,
        ErrorCode.REPLAY_MISMATCH,
    }
)

#: The code used when an object is genuinely absent, keyed by the kind of object.
#:
#: Keyed rather than one generic code because contract 07 has no single ``NOT_FOUND``. Several
#: entries currently resolve to ``UNKNOWN_CONTEXT`` because that is the one absence code the
#: table actually declares; the registry exists so that whichever code a ref_type lands on, the
#: cross-tenant path lands on the *same* one. A caller that needs a type-specific code passes
#: it explicitly, and both paths still have to agree.
#:
#: The cross-tenant path uses this table **as well**, which is the whole mechanism: a
#: registry that only the absence path consulted would leave the two free to diverge.
ABSENCE_CODES: dict[str, ErrorCode] = {
    "context": ErrorCode.UNKNOWN_CONTEXT,
    "observation": ErrorCode.UNKNOWN_CONTEXT,
    "investigation": ErrorCode.UNKNOWN_CONTEXT,
    "artifact": ErrorCode.UNKNOWN_CONTEXT,
    "resolution": ErrorCode.UNKNOWN_CONTEXT,
}

_EXPECTED_NEGATIVE = frozenset(
    {
        ErrorCode.UNKNOWN_CONTEXT,
        ErrorCode.POLICY_BLOCKED,
        ErrorCode.SCOPE_VIOLATION,
        ErrorCode.BUDGET_EXHAUSTED,
        ErrorCode.APPROVAL_REQUIRED,
        ErrorCode.CAPABILITY_UNAVAILABLE,
        ErrorCode.UNSUPPORTED_QUERY,
        ErrorCode.DETECTION_POWER_UNKNOWN,
        ErrorCode.PROJECTION_STALE,
        ErrorCode.NO_MEMBERSHIP,
        ErrorCode.NO_ANCHOR,
        ErrorCode.CAPACITY_GAP,
        ErrorCode.RESOLUTION_DEFERRAL,
        ErrorCode.RESOLUTION_REJECTED,
        ErrorCode.UNVERIFIED_DONOR,
        ErrorCode.LICENCE_BLOCKED,
        ErrorCode.EXPECTED_NO_RESULT,
        ErrorCode.MALFORMED_INPUT,
        ErrorCode.ADMISSION_REJECTED,
        ErrorCode.HUMAN_REVIEW_REQUIRED,
    }
)

_RETRYABLE = frozenset(
    {
        ErrorCode.SOURCE_UNAVAILABLE,
        ErrorCode.RATE_LIMITED,
        ErrorCode.TIMEOUT,
        ErrorCode.TRANSIENT_INFRA,
        ErrorCode.RESOURCE_CAP,
        ErrorCode.PARTIAL_OUTPUT,
        ErrorCode.QUARANTINED,
        ErrorCode.PROJECTION_FAILED,
        ErrorCode.OPERATOR_TIMEOUT,
        # Asynchronous membership resolution: not yet placed, so not yet an answer. Retryable
        # and the caller retries; it is not a placement failure.
        ErrorCode.PLACEMENT_PENDING,
    }
)

_DEFECT = frozenset(
    {
        ErrorCode.STALE_CONTEXT_REVISION,
        ErrorCode.REVISION_CONFLICT,
        ErrorCode.REPLAY_MISMATCH,
        ErrorCode.DECISION_RECORD_MISSING,
        ErrorCode.OPERATOR_OUTPUT_INVALID,
        ErrorCode.SCHEMA_INCOMPATIBLE,
        ErrorCode.SCHEMA_MISMATCH,
        ErrorCode.SPAN_UNRESOLVABLE,
        ErrorCode.SPAN_SEMANTICS_MISMATCH,
        ErrorCode.PROVENANCE_INCOMPLETE,
        ErrorCode.IMMUTABLE_VIOLATION,
        ErrorCode.PERMANENT_OPERATOR_ERROR,
        # Reaching this code at all is a defect: it is the answer to a reference, and the
        # answer to a reference is "absent", so any emission confirms existence (FR-090).
        # ``cross_tenant_envelope`` refuses to produce it.
        ErrorCode.TENANT_SCOPE_VIOLATION,
    }
)

_CATEGORIES: dict[ErrorCode, ErrorCategory] = {}
_CATEGORIES.update({code: ErrorCategory.EXPECTED_NEGATIVE for code in _EXPECTED_NEGATIVE})
_CATEGORIES.update({code: ErrorCategory.RETRYABLE_INFRA for code in _RETRYABLE})
_CATEGORIES.update({code: ErrorCategory.DEFECT for code in _DEFECT})

# A code in no category is a defect in this table: an unclassified code is a code no handler
# knows how to treat, which is precisely the conflation the three categories exist to prevent.
# Checked at import time because the alternative is a handler guessing, once, in production.
_UNCLASSIFIED = set(ErrorCode) - set(_CATEGORIES)
if _UNCLASSIFIED:  # pragma: no cover - guard that must never fire
    raise RuntimeError(f"error codes with no category: {sorted(str(c) for c in _UNCLASSIFIED)}")

#: Codes contract 03 names as failure classes that contract 07's table does not list. Both
#: documents are normative, so these live here with their categories rather than being absent.
CONTRACT_03_ONLY = frozenset(
    {
        ErrorCode.TIMEOUT,
        ErrorCode.TRANSIENT_INFRA,
        ErrorCode.RESOURCE_CAP,
        ErrorCode.EXPECTED_NO_RESULT,
        ErrorCode.MALFORMED_INPUT,
        ErrorCode.PARTIAL_OUTPUT,
        ErrorCode.QUARANTINED,
        ErrorCode.PERMANENT_OPERATOR_ERROR,
        ErrorCode.SCHEMA_MISMATCH,
        ErrorCode.ADMISSION_REJECTED,
        ErrorCode.HUMAN_REVIEW_REQUIRED,
    }
)


def is_release_blocker(code: ErrorCode) -> bool:
    return ErrorCode(code).is_release_blocker


def release_blocker_codes() -> tuple[ErrorCode, ...]:
    """The codes whose emission is a release blocker, in a stable order for a CI gate."""
    return tuple(code for code in ErrorCode if code.is_release_blocker)


# ---------------------------------------------------------------------------
# Envelopes. ``as_wire`` is what leaves the process; ``internal_reason`` does not.
# ---------------------------------------------------------------------------

#: Field names that would carry payload or a credential into an error. Refused outright.
_FORBIDDEN_FIELD_TOKENS = (
    "payload",
    "body",
    "raw",
    "content",
    "text",
    "snippet",
    "document",
    "secret",
    "token",
    "password",
    "passwd",
    "credential",
    "authorization",
    "cookie",
    "session_key",
    "private_key",
)

#: Value shapes that look like a leaked secret even under an innocent field name.
_SECRET_VALUE_PATTERNS = (
    re.compile(r"\bBearer\s+\S+", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{12,}"),
    re.compile(r"\b(?:sk|pk)-[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)\b(?:password|secret|api[_-]?key)\s*[=:]\s*\S+"),
)

#: A reason is a human sentence. A 240-character cap is not a style preference: a reason long
#: enough to hold a paragraph of source content is a reason being used as a payload.
_MAX_REASON_CHARS = 240


@dataclass(frozen=True, slots=True)
class ErrorEnvelope:
    """A failure as it leaves the process: code, kind of thing, and a short reason.

    ``internal_reason`` is the one field that may differ between a cross-tenant refusal and an
    absence, and it is excluded from :meth:`as_wire` by construction -- not by a caller
    remembering to strip it.
    """

    code: ErrorCode
    ref_type: str
    reason: str
    detail: dict[str, Any] = field(default_factory=dict)
    internal_reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", ErrorCode(self.code))
        ref_type = str(self.ref_type).strip()
        if not ref_type:
            raise ErrorSurfaceError("an error must name the kind of thing it is about")
        object.__setattr__(self, "ref_type", ref_type)
        reason = str(self.reason).strip()
        if not reason:
            raise ErrorSurfaceError(
                f"{self.code} must carry a reason; 'blocked' without naming what is blocked is "
                "not an answer anybody can act on (R5)"
            )
        if len(reason) > _MAX_REASON_CHARS:
            raise ErrorSurfaceError(
                f"reason is {len(reason)} characters; over {_MAX_REASON_CHARS} it is a payload "
                "carrying source content, not a reason (R3)"
            )
        object.__setattr__(self, "reason", reason)
        _reject_leaking_detail(dict(self.detail))
        object.__setattr__(self, "detail", dict(self.detail))
        object.__setattr__(self, "internal_reason", str(self.internal_reason))

    @property
    def category(self) -> ErrorCategory:
        return self.code.category

    def as_wire(self) -> dict[str, Any]:
        """Exactly the bytes a client sees. ``internal_reason`` is not among them."""
        return {
            "error": {
                "code": str(self.code),
                "category": str(self.code.category),
                "ref_type": self.ref_type,
                "reason": self.reason,
                "detail": dict(self.detail),
            }
        }

    def as_bytes(self) -> bytes:
        return canonical_bytes(self.as_wire())

    def as_json(self) -> str:
        return canonical_json(self.as_wire())


def _reject_leaking_detail(detail: dict[str, Any]) -> None:
    """Refuse a detail payload that carries raw content or a secret (R3).

    Release blocker, so it raises. Two checks because either alone is insufficient: the field
    *name* catches ``payload=...``, and the *value* catches the secret pasted under an
    innocent name.
    """
    for name, value in detail.items():
        lowered = str(name).lower()
        for token in _FORBIDDEN_FIELD_TOKENS:
            if token in lowered:
                raise ErrorSurfaceError(
                    f"error detail field {name!r} looks like it carries {token!r}; errors carry "
                    "identifiers, codes and reasons, never raw payloads or credentials (R3, "
                    "release blocker)"
                )
        for text in _iter_strings(value):
            for pattern in _SECRET_VALUE_PATTERNS:
                if pattern.search(text):
                    raise ErrorSurfaceError(
                        f"error detail field {name!r} carries a value shaped like a credential; "
                        "errors never include secrets (FR-096, release blocker)"
                    )


def _iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _iter_strings(item)
    elif isinstance(value, list | tuple | set | frozenset):
        for item in value:
            yield from _iter_strings(item)


def absence_envelope(
    ref_type: str,
    *,
    code: ErrorCode | None = None,
    reason: str = "",
) -> ErrorEnvelope:
    """The response for an object that does not exist in this tenant.

    ``code`` defaults to the ref-type's absence code. Callers that want the cross-tenant path
    to be indistinguishable pass the same thing here -- which is exactly what
    :func:`cross_tenant_envelope` does internally.
    """
    resolved = ErrorCode(code) if code is not None else ABSENCE_CODES.get(str(ref_type).strip())
    if resolved is None:
        raise ErrorSurfaceError(
            f"no absence code is registered for ref_type {ref_type!r}; the cross-tenant path "
            "cannot be made indistinguishable from absence without one"
        )
    if resolved is ErrorCode.TENANT_SCOPE_VIOLATION:
        raise CrossTenantIndistinguishabilityError(
            "TENANT_SCOPE_VIOLATION must never reach a client as the answer to a reference: it "
            "confirms the object exists in a tenant the caller may not read (R2, FR-090)"
        )
    return ErrorEnvelope(
        code=resolved,
        ref_type=str(ref_type).strip(),
        reason=reason or f"no such {str(ref_type).strip()} in this tenant",
        detail={},
    )


def cross_tenant_envelope(
    ref_type: str,
    *,
    code: ErrorCode | None = None,
    reason: str = "",
) -> ErrorEnvelope:
    """The response for a reference into another tenant.

    Byte-identical to :func:`absence_envelope` for the same ``ref_type`` and ``code``. The
    distinction is recorded in ``internal_reason``, which never leaves the process. **This
    function has no parameter that can make it distinguishable** -- which is the point, and is
    why a future "just add a debug flag" cannot.
    """
    if code is not None and ErrorCode(code) is ErrorCode.TENANT_SCOPE_VIOLATION:
        raise CrossTenantIndistinguishabilityError(
            "the cross-tenant path cannot report TENANT_SCOPE_VIOLATION: doing so is an "
            "existence oracle (FR-090)"
        )
    envelope = absence_envelope(ref_type, code=code, reason=reason)
    return ErrorEnvelope(
        code=envelope.code,
        ref_type=envelope.ref_type,
        reason=envelope.reason,
        detail=dict(envelope.detail),
        internal_reason="cross-tenant reference refused without confirming existence",
    )


@dataclass(frozen=True, slots=True)
class EmptyStateEnvelope:
    """R4: an empty result set is never returned bare.

    A bare ``[]`` does not distinguish no-candidates / provider-unavailable /
    query-unsupported / budget-truncated / policy-blocked. All four of status, coverage,
    provenance and limitations are therefore required, and the refusal is an error rather than
    a default because the default reading of ``[]`` is "looked, found nothing" -- which is a
    claim about the world that may be false.
    """

    status: ErrorCode
    coverage: str
    provenance: str
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", ErrorCode(self.status))
        for name in ("coverage", "provenance"):
            value = str(getattr(self, name)).strip()
            if not value:
                raise ErrorSurfaceError(
                    f"an empty result set must state its {name}; a bare [] does not distinguish "
                    "no-candidates from provider-unavailable from query-unsupported from "
                    "budget-truncated from policy-blocked (R4)"
                )
            object.__setattr__(self, name, value)
        object.__setattr__(self, "limitations", tuple(str(x) for x in self.limitations))

    def as_wire(self) -> dict[str, Any]:
        return {
            "status": str(self.status),
            "category": str(self.status.category),
            "coverage": self.coverage,
            "provenance": self.provenance,
            "limitations": list(self.limitations),
        }