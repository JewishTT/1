"""Evidence-storage enforcement for observation publication.

**This module exists because the gate was not the only exit.**

`ObservationGate` was always documented as the single path by which an observation
enters the platform. It was not. Three production producers published observations
without it, and the worst of them — `acquisition/sources/connector.py` — built the
`observation.created` event inline, carrying a ``content_digest`` but **no**
``raw_ref``, and never touched an object store. A consumer of that event had no way to
resolve it to bytes. The platform was asserting that something had been observed when
it had only been claimed.

Fixing three call sites would leave the fourth open. A producer added next year, or a
donor adapter written next month, would reintroduce the same hole, because nothing
would make it fail.

So the check lives at publication, not at production. Every producer — existing,
bypassing, and future — converges on one chokepoint, and the refusal is cheap and
typed. That is the difference between a gate and a convention.

---

## What this guarantees, precisely

**Guaranteed.** A published observation event carries a content digest *and* a raw
reference, both non-empty, and the reference names a well-formed, tenant-scoped address.
An event without them is refused before it reaches the broker.

**Not claimed.** That the referenced object is physically present at publish time. The
object stores address raw content by
``raw/{tenant}/{year_month}/{sha256}``, and the year-month partition depends on the
store's clock, which the publisher does not own. Verifying presence across partitions
would mean either a new store capability or a clock assumption — both are real changes
with their own risks, and neither belongs in a refusal path that has to stay fast and
dependency-free.

The consequence is stated rather than hidden: this catches *an observation that names
no evidence*, which is the actual defect in all three bypass sites. It does not catch
*an observation whose named evidence was garbage-collected*, which is a storage-lifecycle
question and belongs with the repair paths in FR-030, not here.

When a caller passes ``store``, the address is additionally resolved through the store's
own ``ref_uri`` so that a malformed or non-tenant-scoped reference is refused here
rather than at read time by a consumer that has no way to report the original failure.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = [
    "UNSTORED_EVIDENCE_CODES",
    "UnstoredEvidenceRefusal",
    "require_stored_evidence",
]


class UnstoredEvidenceRefusal(Exception):
    """An observation was offered for publication without resolvable evidence.

    Carries a code from :data:`UNSTORED_EVIDENCE_CODES` so a caller can route the
    event to quarantine with a machine-readable reason rather than dropping it. A
    silent drop here is the same defect one layer down.
    """

    def __init__(self, code: str, detail: str, *, event_id: str = "") -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail
        self.event_id = event_id


#: Closed vocabulary. A refusal with a bare message is a refusal nobody can act on.
UNSTORED_EVIDENCE_CODES = frozenset(
    {
        "observation_not_an_observation",
        "observation_raw_ref_missing",
        "observation_content_digest_missing",
        "observation_ref_not_resolvable",
    }
)

#: Field spellings accepted for the content digest. Producers were written at
#: different times against different drafts of the contract, and collapsing them here
#: is cheaper -- and safer -- than rewriting every producer in one commit. A future
#: cleanup may narrow this once the producers agree.
_DIGEST_FIELDS = ("content_hash", "content_digest", "sha256")
_REF_FIELDS = ("raw_ref", "ref", "raw_uri")


def _first(event: Mapping[str, Any], names: tuple[str, ...]) -> str:
    for name in names:
        value = event.get(name)
        if value not in (None, ""):
            return str(value).strip()
    return ""


async def require_stored_evidence(
    event: Mapping[str, Any], *, store: Any | None = None
) -> None:
    """Refuse an observation event that names no evidence. Returns when it does.

    Raises :class:`UnstoredEvidenceRefusal`. Callers MUST NOT swallow it -- the whole
    value of this function is that the platform says no instead of publishing a claim
    it cannot substantiate.
    """
    event_id = str(event.get("event_id", "") or "")

    event_type = str(event.get("event_type", "") or "")
    if event_type and not event_type.startswith("observation."):
        raise UnstoredEvidenceRefusal(
            "observation_not_an_observation",
            f"event_type {event_type!r} is not an observation event",
            event_id=event_id,
        )

    digest = _first(event, _DIGEST_FIELDS)
    if not digest:
        raise UnstoredEvidenceRefusal(
            "observation_content_digest_missing",
            "no content digest: the observation cannot be tied to bytes",
            event_id=event_id,
        )

    ref = _first(event, _REF_FIELDS)
    if not ref:
        raise UnstoredEvidenceRefusal(
            "observation_raw_ref_missing",
            f"content digest {digest[:12]}… is named but no raw reference is, so the "
            "bytes behind this observation are unreachable",
            event_id=event_id,
        )

    if store is None:
        return

    tenant_id = str(event.get("tenant_id", "") or "")
    if not tenant_id:
        # Not this function's refusal to make. Tenant enforcement is FR-049 and has
        # its own codes, enforced at the store seam; inventing a second tenant check
        # here would give two answers to one question.
        return

    ref_uri = getattr(store, "ref_uri", None)
    if ref_uri is None:
        return

    try:
        expected = ref_uri(sha256=digest, tenant_id=tenant_id)
    except Exception as exc:  # noqa: BLE001 - any store failure is a refusal, not a pass
        raise UnstoredEvidenceRefusal(
            "observation_ref_not_resolvable",
            f"raw reference {ref!r} does not resolve for tenant {tenant_id!r}: {exc}",
            event_id=event_id,
        ) from exc

    if not str(expected).strip():
        raise UnstoredEvidenceRefusal(
            "observation_ref_not_resolvable",
            f"raw reference {ref!r} produced an empty address",
            event_id=event_id,
        )