"""WP-C T040/T045: an observation may not be published without resolvable evidence.

**T040 — refuse to publish an observation whose bytes were not stored.**

The audit found three producers publishing observations that no consumer could resolve
to bytes. The worst was ``acquisition/sources/connector.py``, which built the
``observation.created`` event inline with a ``content_digest`` and **no** ``raw_ref``,
and never touched an object store. The platform was asserting that something had been
observed when it had only been claimed.

These tests pin the refusal at the chokepoint rather than at each producer, because
that is the property that matters: the next producer inherits the check.

**T045 — a dropped artefact is counted, not discarded.**

``_run_runtime`` read ``getattr(artifact, "observation_id", "")`` from a dataclass that
has no such field. The value was therefore *always* empty, every artifact hit ``continue``,
and a runtime that worked perfectly reported zero yield — indistinguishable from a runtime
that failed silently.
"""

from __future__ import annotations

import pytest

from events.evidence_store_guard import (
    UNSTORED_EVIDENCE_CODES,
    UnstoredEvidenceRefusal,
    require_stored_evidence,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# The connector's exact defect
# ---------------------------------------------------------------------------

def test_the_connectors_event_is_refused():
    """This is the real shape of ``sources/connector.py``'s event, field for field.

    Copied rather than approximated, because an approximated fixture would pass
    against the original defect and prove nothing. Note ``content_digest`` is present
    and ``raw_ref`` is not — that combination is precisely what made the event look
    legitimate to every consumer.
    """
    connector_event = {
        "event_type": "observation.created",
        "event_version": "1.0",
        "event_id": "OBS-abcdef0123456789abcdef0123456789",
        "task_id": "task-1",
        "tenant_id": "t-1",
        "investigation_id": "inv-1",
        "source_id": "src-1",
        "source_name": "Example",
        "category": "web",
        "query": "acme holdings",
        "page": 1,
        "url": "https://example.test/a",
        "status": 200,
        "content_type": "text/html",
        "content_digest": "d" * 64,
        "byte_length": 4096,
        "retrieved_at": "2026-10-13T00:00:00Z",
    }

    with pytest.raises(UnstoredEvidenceRefusal) as caught:
        import asyncio

        asyncio.run(require_stored_evidence(connector_event))

    assert caught.value.code == "observation_raw_ref_missing"
    assert "unreachable" in str(caught.value)


async def test_a_digest_with_a_ref_is_accepted():
    await require_stored_evidence(
        {
            "event_type": "observation.created",
            "event_id": "evt-1",
            "content_digest": "d" * 64,
            "raw_ref": "s3://knowledge/raw/t-1/202610/" + "d" * 64,
            "tenant_id": "t-1",
        }
    )


# ---------------------------------------------------------------------------
# Refusal vocabulary
# ---------------------------------------------------------------------------

async def test_a_missing_digest_is_refused():
    with pytest.raises(UnstoredEvidenceRefusal) as caught:
        await require_stored_evidence(
            {"event_type": "observation.created", "raw_ref": "s3://x"}
        )
    assert caught.value.code == "observation_content_digest_missing"


async def test_a_non_observation_event_is_refused():
    with pytest.raises(UnstoredEvidenceRefusal) as caught:
        await require_stored_evidence(
            {
                "event_type": "entity.claimed",
                "content_digest": "d" * 64,
                "raw_ref": "s3://x",
            }
        )
    assert caught.value.code == "observation_not_an_observation"


async def test_every_refusal_code_is_declared():
    """A refusal with an undeclared code cannot be routed or counted by a consumer."""
    for code in ("observation_not_an_observation", "observation_raw_ref_missing",
                 "observation_content_digest_missing", "observation_ref_not_resolvable"):
        assert code in UNSTORED_EVIDENCE_CODES


async def test_the_refusal_carries_the_event_id():
    """Quarantine without the id cannot be correlated back to what produced it."""
    with pytest.raises(UnstoredEvidenceRefusal) as caught:
        await require_stored_evidence(
            {"event_id": "evt-xyz", "event_type": "observation.created",
             "content_digest": "d" * 64}
        )
    assert caught.value.event_id == "evt-xyz"


# ---------------------------------------------------------------------------
# Spellings across producer generations
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "digest_field,ref_field",
    [
        ("content_hash", "raw_ref"),
        ("content_digest", "ref"),
        ("sha256", "raw_uri"),
    ],
)
async def test_field_spellings_are_collapsed(digest_field: str, ref_field: str):
    """Producers were written against different drafts of the contract.

    Collapsing the spellings in the guard is cheaper and safer than rewriting every
    producer in one commit. The test exists so the accepted set cannot widen silently.
    """
    await require_stored_evidence(
        {"event_type": "observation.created", digest_field: "d" * 64, ref_field: "s3://x"}
    )


# ---------------------------------------------------------------------------
# Store resolution
# ---------------------------------------------------------------------------

async def test_an_unresolvable_reference_is_refused():
    """A store that cannot produce an address for the digest refuses rather than passes.

    A pass here would be the worst outcome: the platform would believe it had checked
    when it had only failed to check.
    """

    class BrokenStore:
        def ref_uri(self, *, sha256: str, tenant_id: str) -> str:
            raise RuntimeError("partition index unavailable")

    with pytest.raises(UnstoredEvidenceRefusal) as caught:
        await require_stored_evidence(
            {
                "event_type": "observation.created",
                "content_digest": "d" * 64,
                "raw_ref": "s3://x",
                "tenant_id": "t-1",
            },
            store=BrokenStore(),
        )
    assert caught.value.code == "observation_ref_not_resolvable"


async def test_a_well_formed_reference_resolves_through_the_store():
    """The happy path with a real store, proving the check is not vacuously refusing."""

    class Store:
        def ref_uri(self, *, sha256: str, tenant_id: str) -> str:
            return f"s3://knowledge/raw/{tenant_id}/202610/{sha256}"

    await require_stored_evidence(
        {
            "event_type": "observation.created",
            "content_digest": "d" * 64,
            "raw_ref": "s3://knowledge/raw/t-1/202610/" + "d" * 64,
            "tenant_id": "t-1",
        },
        store=Store(),
    )


async def test_tenant_enforcement_is_not_duplicated_here():
    """A missing tenant is *not* refused by this function.

    Tenant enforcement is FR-049 and belongs at the store seam, where it is already
    tested. Inventing a second check here would give two answers to one question, and
    the weaker one would win whenever they disagreed.
    """
    await require_stored_evidence(
        {"event_type": "observation.created", "content_digest": "d" * 64,
         "raw_ref": "s3://x"}
    )