"""Deterministic observation and event identity. **The only place either is written.**

Feature 023, directive §11, §160. The defect this module exists to remove is at
``apps/shared/events/observation_gate.py:74``, which read::

    observation_id = "OBS-" + uuid.uuid4().hex[:12]

A random id makes replay unreconstructable, which is release blocker
``observation_id random`` in §160 and violates constitution Domain Invariant 12
(determinism). The fix is not "a better random source"; it is that identity stops
being random at all.

**Why a module and not a helper inside the gate.** The gate had become one of
three places that could mint an identity - itself, ``kafka.py`` (whose
``build_envelope`` fell back to ``str(uuid4())``) and whoever called them - and a
rule with three homes is a rule that has already drifted once. This module is
the single writer; the gate and the envelope builder both delegate here, and
:func:`require_deterministic_event_id` is the guard that fails closed if a
random id reaches the wire by any other route.

**The material, and what is deliberately absent from it.** Per §11 an
observation is addressed by::

    identity_schema | tenant_id | capture_id | locator | record_digest

Two omissions are load-bearing:

``record_digest`` is required, and *not* the record's content alone. Directive
§34 gives the reason: ``record A in stream X`` and ``record A in stream Y`` can
carry identical JSON and still be two different observed occurrences. Identity
therefore includes the capture that bounds it, so the same record in two runs of
two connectors is two observations, and the same record in a replay is one.

The clock is absent. ``fetched_at``, ``ingest_attempt`` and ``ingest_batch_id``
are recorded on the capture but excluded from observation identity, exactly as
``Capture.payload_key`` excludes them (``domain/capture.py``). Two fetches of one
target returning identical bytes are one payload and two publications; collapsing
them into one identity would erase the second publication, which is evidence.

**What this module does not do.** It does not decide whether a record is
interesting, does not rank, does not score and does not touch storage. It
addresses; that is all. And it refuses rather than degrading: a missing locator
is a named refusal, because a record addressed only by content would silently
merge the two occurrences §34 separates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from domain.relation_identity import canonical_material, digest128

#: Bumped when the *shape* of identity material changes, so an id minted under an
#: older schema cannot be mistaken for one minted under this one. This is
#: directive §11's ``identity_schema``, and it is a value rather than a constant
#: on purpose: the value goes into the digest, so changing it genuinely changes
#: every address instead of silently reusing the old scheme.
IDENTITY_SCHEMA_V1: Final = "observation-identity/v1"

OBSERVATION_PREFIX: Final = "OBS-"
EVENT_PREFIX: Final = "evt-"

#: Named refusals. A caller that reaches one of these has a bug upstream, and the
#: point of naming them is that the caller cannot mistake it for an id.
REFUSAL_LOCATOR_MISSING: Final = "observation_locator_missing"
REFUSAL_RECORD_DIGEST_MISSING: Final = "observation_record_digest_missing"
REFUSAL_CAPTURE_ID_MISSING: Final = "observation_capture_id_missing"
REFUSAL_TENANT_MISSING: Final = "observation_tenant_missing"
REFUSAL_EVENT_NOT_DETERMINISTIC: Final = "event_id_not_deterministic"


class ObservationIdentityError(ValueError):
    """An identity could not be written. Carries a closed refusal code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _require(code: str, name: str, value: str | None) -> str:
    """Refuse a missing component by name rather than hashing an empty string.

    Hashing ``None`` would produce a well-formed address for a malformed input,
    which is the failure mode this whole chain exists to remove: an id that looks
    real and means nothing.
    """
    if value is None or not str(value).strip():
        raise ObservationIdentityError(code, f"{name} is required for an observation address")
    return str(value).strip()


@dataclass(frozen=True)
class ObservationIdentity:
    """The material an observation address is built from, and the address itself."""

    observation_id: str
    tenant_id: str
    capture_id: str
    locator: str
    record_digest: str
    identity_schema: str = IDENTITY_SCHEMA_V1

    @classmethod
    def for_record(
        cls,
        *,
        tenant_id: str,
        capture_id: str,
        locator: str,
        record_digest: str,
        identity_schema: str = IDENTITY_SCHEMA_V1,
    ) -> ObservationIdentity:
        """Address one addressable record inside one capture (directive §9/§10/§11)."""
        tenant = _require(REFUSAL_TENANT_MISSING, "tenant_id", tenant_id)
        capture = _require(REFUSAL_CAPTURE_ID_MISSING, "capture_id", capture_id)
        where = _require(REFUSAL_LOCATOR_MISSING, "locator", locator)
        digest = _require(REFUSAL_RECORD_DIGEST_MISSING, "record_digest", record_digest)
        material = canonical_material(
            {
                "identity_schema": identity_schema,
                "tenant_id": tenant,
                "capture_id": capture,
                "locator": where,
                "record_digest": digest,
            }
        )
        return cls(
            observation_id=OBSERVATION_PREFIX + digest128(material),
            tenant_id=tenant,
            capture_id=capture,
            locator=where,
            record_digest=digest,
            identity_schema=identity_schema,
        )

    @property
    def material(self) -> str:
        """The exact string the address was cut from, kept for forensic replay.

        Storing it is what makes a disputed address answerable: given the
        material, the digest is recomputable; given only the digest, it is not.
        """
        return canonical_material(
            {
                "identity_schema": self.identity_schema,
                "tenant_id": self.tenant_id,
                "capture_id": self.capture_id,
                "locator": self.locator,
                "record_digest": self.record_digest,
            }
        )

    def verify(self) -> None:
        """Re-derive the address and raise if it disagrees with itself.

        The same discipline :class:`domain.capture.Capture` applies to
        ``capture_id`` in ``__post_init__`` - verify, do not trust - so a row or
        message whose address was written by something else is caught at the
        boundary instead of being indexed under an id that means nothing.
        """
        expected = OBSERVATION_PREFIX + digest128(self.material)
        if expected != self.observation_id:
            raise ObservationIdentityError(
                "observation_id_mismatch",
                f"carries {self.observation_id!r} but its own material addresses to {expected!r}",
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "observation_id": self.observation_id,
            "tenant_id": self.tenant_id,
            "capture_id": self.capture_id,
            "locator": self.locator,
            "record_digest": self.record_digest,
            "identity_schema": self.identity_schema,
        }


def observation_id_for(
    *, tenant_id: str, capture_id: str, locator: str, record_digest: str
) -> str:
    """The one-line form of :meth:`ObservationIdentity.for_record`."""
    return ObservationIdentity.for_record(
        tenant_id=tenant_id,
        capture_id=capture_id,
        locator=locator,
        record_digest=record_digest,
    ).observation_id


def event_id_for(
    *,
    event_type: str,
    event_version: str,
    observation_id: str,
    producer: str,
    producer_version: str,
    lifecycle: str,
) -> str:
    """Deterministic event address over §11's six components.

    ``lifecycle`` is in the material because the same observation legitimately
    produces different events at different points in its life, and those must not
    collide. A clock is *not* in the material: replaying an unchanged observation
    must reproduce the address, which is the §12 replay invariant.
    """
    material = canonical_material(
        {
            "event_type": event_type,
            "event_version": event_version,
            "observation_id": observation_id,
            "producer": producer,
            "producer_version": producer_version,
            "lifecycle": lifecycle,
        }
    )
    return EVENT_PREFIX + digest128(material)


def require_deterministic_event_id(event_id: str) -> str:
    """Refuse a random event id at the wire (§160, ``event_id random``).

    A UUID appears in a ``uuid4`` hex form. Any id that is not the ``evt-``
    content address, and that *looks* like a UUID, is rejected by name rather
    than passed downstream where a consumer would trust it as an address.
    """
    candidate = (event_id or "").strip()
    if not candidate:
        raise ObservationIdentityError(
            REFUSAL_EVENT_NOT_DETERMINISTIC, "event_id is empty; §160 forbids a random one"
        )
    # The address is ``evt-`` + 32 lowercase hex, and nothing else. Validating the
    # *whole* shape rather than just the prefix is the point: the previous gate
    # minted f"evt-{sha256}-{lifecycle}", which also starts with "evt-" and so
    # passed a prefix-only check while being exactly the form §11 forbids. A
    # guard that admits the shape it exists to reject is worse than no guard.
    if candidate.startswith(EVENT_PREFIX):
        body = candidate[len(EVENT_PREFIX) :]
        if len(body) == 32 and all(c in "0123456789abcdef" for c in body.lower()):
            return candidate
        raise ObservationIdentityError(
            REFUSAL_EVENT_NOT_DETERMINISTIC,
            f"{candidate!r} is not an evt- content address: expected evt- plus 32 hex "
            f"characters, got {body!r}",
        )
    # A bare 32-hex digest is still a content address, just unprefixed.
    if len(candidate) == 32 and all(c in "0123456789abcdef" for c in candidate.lower()):
        return EVENT_PREFIX + candidate
    lowered = candidate.lower()
    looks_random = ("-" in lowered and len(lowered) >= 32) or "uuid" in lowered
    if looks_random:
        raise ObservationIdentityError(
            REFUSAL_EVENT_NOT_DETERMINISTIC,
            f"{candidate!r} is not a content address (§11); a replay must reproduce it",
        )
    return candidate
