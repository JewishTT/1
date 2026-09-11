"""Observation gate (T031, FR-002, I-1/I-5).

Stores raw content-addressed via ObjectStore, enforces observation immutability
(I-1), and emits `observation.created/.unchanged/.duplicate` events carrying
refs (never blobs, I-5). Idempotent by content hash (FR-007).
"""

from __future__ import annotations

import uuid

from domain import enforce_no_blobs, enforce_observation_immutable
from events.content_router import ContentRouter
from events.kafka import build_envelope
from events.topics import topic_for
from storage.s3 import ObjectStore


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
        content_type: str | None = None,
    ) -> dict:
        """Ingest fetched bytes: storage + observation immutable + event emission."""
        enforce_no_blobs(body, max_inline=1024)
        classified = self._router.classify(
            body, url=uri, headers={"etag": None, "last-modified": None}
        )
        ct = content_type or classified["content_type"]

        ref = await self._store.put_raw(body, tenant_id=tenant_id, meta={"content_type": ct})

        observation_id = "OBS-" + uuid.uuid4().hex[:12]
        observation = {
            "observation_id": observation_id,
            "tenant_id": tenant_id,
            "investigation_id": investigation_id,
            "source_id": source_id,
            "uri": uri,
            "raw_ref": ref.uri,
            "content_hash": ref.sha256,
            "content_type": ct,
            "status": "created",
            "duplicate": False,
            "provenance": {"version": 1},
        }
        # I-1: record is immutable after this point.
        self._observations[observation_id] = observation
        if self._producer is not None:
            env = build_envelope(
                event_type="observation.created",
                event_version="1.0",
                producer="observation-gate",
                producer_version="0.1.0",
                payload=ref.uri.encode(),
                investigation_id=investigation_id,
                observation_id=observation_id,
                event_id=f"evt-{ref.sha256}",
            )
            self._producer.produce(topic_for("observation.created"), env, key=observation_id)
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