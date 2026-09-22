"""Observation gate (T031, FR-002, I-1/I-5).

Stores raw content-addressed via ObjectStore and classifies lifecycle exactly
like the Rust gate (R-08 three-way split) so every observation converges on one
semantics: ``created`` / ``changed`` / ``unchanged`` / ``duplicate``. Ref-only
events carry v2 routing fields (tenant_id, source_id, work_id, region_id) and
never blobs (I-5). Idempotent by content hash (FR-007).
"""

from __future__ import annotations

import uuid

from domain import enforce_no_blobs, enforce_observation_immutable
from events.content_router import ContentRouter
from events.kafka import build_envelope
from events.topics import topic_for
from storage.s3 import ObjectStore


def resolve_lifecycle(stored_before: bool, previous_digest: str | None, new_digest: str) -> str:
    """R-08 three-way split, same order as the Rust gate: a same-source refresh
    with identical content is `unchanged` (reachable even though the store holds
    the bytes); a content-address collision from another context is `duplicate`;
    otherwise created/changed by first difference."""
    if previous_digest is not None and previous_digest == new_digest:
        return "unchanged"
    if stored_before:
        return "duplicate"
    if previous_digest is None:
        return "created"
    return "changed"


_ZERO_FIELDS = {"tenant_id", "observation_id"}


class ObservationGate:
    def __init__(self, store: ObjectStore, router: ContentRouter, producer=None) -> None:
        self._store = store
        self._router = router
        self._producer = producer
        self._observations: dict[str, dict] = {}

    async def ingest(
        self,
        *,
        body: bytes,
        uri: str,
        tenant_id: str,
        investigation_id: str | None = None,
        source_id: str | None = None,
        work_id: str | None = None,
        region_id: str | None = None,
        content_type: str | None = None,
        previous_digest: str | None = None,
        collector: str = "acquisition-worker",
        collector_version: str = "0.1.0",
        source_kind: str = "web",
    ) -> dict:
        """Ingest fetched bytes: storage + lifecycle + ref-only event emission."""
        enforce_no_blobs(body, max_inline=1024)
        classified = self._router.classify(
            body, url=uri, headers={"etag": None, "last-modified": None}
        )
        ct = content_type or classified["content_type"]
        digest = classified["sha256"]

        ref, stored_before = await self._store.put_raw_dedup(
            body, tenant_id=tenant_id, meta={"content_type": ct}
        )

        lifecycle = resolve_lifecycle(stored_before, previous_digest, digest)
        observation_id = "OBS-" + uuid.uuid4().hex[:12]
        observation = {
            "observation_id": observation_id,
            "tenant_id": tenant_id,
            "investigation_id": investigation_id,
            "source_id": source_id,
            "work_id": work_id,
            "region_id": region_id,
            "uri": uri,
            "raw_ref": ref.uri,
            "content_hash": ref.sha256,
            "content_type": ct,
            "status": lifecycle,
            "duplicate": lifecycle == "duplicate",
            "provenance": {"version": 2, "collector": collector, "collector_version": collector_version},
        }
        # I-1: record is immutable after this point.
        self._observations[observation_id] = observation
        if self._producer is not None:
            event_type = f"observation.{lifecycle}"
            env = build_envelope(
                event_type=event_type,
                event_version="2.0",
                producer="observation-gate",
                producer_version="0.1.0",
                payload=ref.uri.encode(),
                investigation_id=investigation_id,
                observation_id=observation_id,
                tenant_id=tenant_id,
                source_id=source_id or "",
                work_id=work_id or "",
                region_id=region_id or "",
                event_id=f"evt-{ref.sha256}-{lifecycle}",
            )
            self._producer.produce(topic_for(event_type), env, key=observation_id)
        return observation

    def mutate_attempt(self, observation_id: str, patch: dict) -> None:
        """I-1 enforcement: any immutable-field mutation raises."""
        existing = self._observations.get(observation_id)
        if existing is None:
            raise KeyError(observation_id)
        enforce_observation_immutable(existing, patch)
        for k, v in patch.items():
            existing[k] = v
        return existing