"""Observation gate (T031, FR-002, I-1/I-5).

Stores raw content-addressed via ObjectStore and classifies lifecycle exactly
like the Rust gate (R-08 three-way split) so every observation converges on one
semantics: ``created`` / ``changed`` / ``unchanged`` / ``duplicate``. Ref-only
events carry v2 routing fields (tenant_id, source_id, work_id, region_id) and
never blobs (I-5). Idempotent by content hash (FR-007).

**Feature 023 changed the identity, not the lifecycle.** This module used to cut
``observation_id`` from ``uuid.uuid4()``, which is release blocker
``observation_id random`` (§160) and breaks the §12 replay invariant - a replay
produced a second, differently-named observation of identical evidence, so
reconstructing what was collected meant trusting the store rather than the
address. Identity now comes from
:mod:`domain.observation_identity`, which is the single writer, and the two
paths are distinguished by §9's two seams:

``ingest`` / ``ingest_capture``
    blob-level. A whole response becomes a capture plus one parent observation
    addressed at ``locator="capture"`` with the response digest as
    ``record_digest``.

``ingest_record``
    record-level. One addressable record inside that capture, addressed at its
    own locator with its own digest. It does **not** re-store the blob (§9).

A parent capture observation and its record observations are therefore different
addresses over the same bytes, which is the §6 distinction between *what was
received* and *what was addressed in it*.
"""

from __future__ import annotations

import json

from domain import enforce_no_blobs, enforce_observation_immutable
from domain.observation_identity import ObservationIdentity, event_id_for
from events.content_router import ContentRouter
from events.kafka import build_envelope
from events.topics import topic_for
from storage.s3 import ObjectStore

#: Locator for the observation that stands for a whole stored blob. A reserved
#: name rather than an empty string: §10 locators are provenance addresses, and
#: "no locator" for a blob-level capture is a fact worth naming, not an absence.
CAPTURE_LOCATOR: str = "capture"

#: Named once because it is part of every event's identity material (§11). It
#: was a literal repeated at three call sites before, which is how a version bump
#: becomes a partial change.
GATE_PRODUCER: str = "observation-gate"
GATE_PRODUCER_VERSION: str = "0.1.0"


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
        #: What this gate last published: ``event_id`` and ``topic`` of the most
        #: recent emission, or ``None``. Exists so ``acquisition.artifact_sink``
        #: can report the address the gate actually used instead of rebuilding
        #: the envelope to guess at one - two builders of one message is the drift
        #: this module was refactored to remove. ``None`` when no producer is
        #: attached, which honestly means "no event was published".
        self.last_emitted: dict[str, str] | None = None

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
        """Ingest fetched bytes: storage + lifecycle + ref-only event emission.

        Blob-level path. §9 calls for this to be reachable as ``ingest_capture``
        so the two seams are distinguishable at the call site rather than by
        which keyword the caller happened to use; :meth:`ingest_capture` is that
        name, and this method stays as the original spelling.
        """
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
        # §11: the address is cut from identity material, never from a clock or a
        # random source. capture_id is the ref's own content address, so a replay
        # of identical bytes recomputes the identical observation_id instead of
        # minting a second name for evidence that did not change (§12).
        identity = ObservationIdentity.for_record(
            tenant_id=tenant_id,
            capture_id="CAP-" + digest,
            locator=CAPTURE_LOCATOR,
            record_digest=digest,
        )
        observation_id = identity.observation_id
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
            "provenance": {
                "version": 2,
                "collector": collector,
                "collector_version": collector_version,
            },
        }
        # I-1: record is immutable after this point.
        self._observations[observation_id] = observation
        if self._producer is not None:
            event_type = f"observation.{lifecycle}"
            env = build_envelope(
                event_type=event_type,
                event_version="2.0",
                producer="observation-gate",
                producer_version=GATE_PRODUCER_VERSION,
                payload=json.dumps(
                    {
                        "capture_id": "CAP-" + digest,
                        "observation_id": observation_id,
                        "locator": CAPTURE_LOCATOR,
                        "raw_ref": ref.uri,
                        "content_hash": digest,
                        "content_type": ct or "",
                        "tenant_id": tenant_id,
                        "source_id": source_id or "",
                        "runtime_producer": GATE_PRODUCER,
                        "runtime_producer_version": GATE_PRODUCER_VERSION,
                        "investigation_id": investigation_id or "",
                        "work_id": work_id or "",
                        "lifecycle": lifecycle,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode("utf-8"),
                investigation_id=investigation_id,
                observation_id=observation_id,
                tenant_id=tenant_id,
                source_id=source_id or "",
                work_id=work_id or "",
                region_id=region_id or "",
                # §11's six components, in one place, rather than the previous
                # f"evt-{sha256}-{lifecycle}" - which collided for two different
                # observations of identical bytes and omitted the producer, so a
                # second producer reading the same capture would have had to
                # publish under the first's address.
                event_id=event_id_for(
                    event_type=event_type,
                    event_version="2.0",
                    observation_id=observation_id,
                    producer="observation-gate",
                    producer_version=GATE_PRODUCER_VERSION,
                    lifecycle=lifecycle,
                ),
            )
            self._producer.produce(topic_for(event_type), env, key=observation_id)
        return observation

    def publish_record_event(
        self,
        observation: dict,
        *,
        producer: str = "observation-gate",
        producer_version: str = GATE_PRODUCER_VERSION,
    ) -> Any | None:
        """Publish a previously persisted record observation using its canonical address.

        The caller must persist Capture and Observation first when a durable writer is
        configured. Event IDs are deterministic; a retry may safely publish the same
        event again because consumers deduplicate by event_id/observation_id.
        """
        if self._producer is None:
            self.last_emitted = None
            return None

        observation_id = str(observation.get("observation_id") or "").strip()
        capture_id = str(observation.get("capture_id") or "").strip()
        raw_ref = str(observation.get("raw_ref") or "").strip()
        locator = str(observation.get("locator") or "").strip()
        tenant_id = str(observation.get("tenant_id") or "").strip()
        if not all((observation_id, capture_id, raw_ref, locator, tenant_id)):
            raise ValueError("cannot publish an observation without observation/capture/raw/locator/tenant refs")

        event_type = "observation.created"
        payload = json.dumps(
            {
                "capture_id": capture_id,
                "observation_id": observation_id,
                "locator": locator,
                "record_digest": str(observation.get("record_digest") or ""),
                "raw_ref": raw_ref,
                "parser_hint": str(observation.get("parser_hint") or ""),
                "tenant_id": tenant_id,
                "source_id": str(observation.get("source_id") or ""),
                "content_type": str(observation.get("content_type") or ""),
                "runtime_producer": producer,
                "runtime_producer_version": producer_version,
                "investigation_id": str(observation.get("investigation_id") or ""),
                "work_id": str(observation.get("work_id") or ""),
                "region_id": str(observation.get("region_id") or ""),
                "record_metadata": dict(observation.get("record_metadata") or {}),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        event_id = event_id_for(
            event_type=event_type,
            event_version="2.0",
            observation_id=observation_id,
            producer=producer,
            producer_version=producer_version,
            lifecycle="created",
        )
        env = build_envelope(
            event_type=event_type,
            event_version="2.0",
            producer=producer,
            producer_version=producer_version,
            payload=payload,
            investigation_id=str(observation.get("investigation_id") or ""),
            observation_id=observation_id,
            event_id=event_id,
            tenant_id=tenant_id,
            source_id=str(observation.get("source_id") or ""),
            work_id=str(observation.get("work_id") or ""),
            region_id=str(observation.get("region_id") or ""),
        )
        topic = topic_for(event_type)
        publish_sync = getattr(self._producer, "publish_sync", None)
        if callable(publish_sync):
            publish_sync(topic, env, key=observation_id, event_type=event_type)
        else:
            self._producer.produce(topic, env, key=observation_id)
            flush = getattr(self._producer, "flush", None)
            if callable(flush):
                remaining = flush(15.0)
                if isinstance(remaining, int) and remaining > 0:
                    raise RuntimeError(f"observation event was not acknowledged: {remaining} pending")
        self.last_emitted = {"event_id": event_id, "topic": topic}
        return env

    async def ingest_record(
        self,
        *,
        capture_id: str,
        record_locator: str,
        record_digest: str,
        tenant_id: str,
        raw_ref: str = "",
        parser_hint: str = "",
        investigation_id: str | None = None,
        source_id: str | None = None,
        work_id: str | None = None,
        region_id: str | None = None,
        content_type: str | None = None,
        record_metadata: dict | None = None,
        producer: str = "observation-gate",
        producer_version: str = GATE_PRODUCER_VERSION,
        publish_event: bool = True,
    ) -> dict:
        """Address one record inside an already-stored capture.

        The raw bytes are already durable under ``raw_ref``; this operation creates
        the finer record address without storing the blob a second time. When
        ``publish_event=False``, a caller may commit Capture + Observation in the
        same transaction before invoking ``publish_record_event``.
        """
        if not all((capture_id, record_locator, record_digest, tenant_id, raw_ref)):
            raise ValueError(
                "capture_id, record_locator, record_digest, tenant_id and raw_ref are required"
            )
        identity = ObservationIdentity.for_record(
            tenant_id=tenant_id,
            capture_id=capture_id,
            locator=record_locator,
            record_digest=record_digest,
        )
        observation_id = identity.observation_id
        existing = self._observations.get(observation_id)
        if existing is not None:
            # A replay keeps the same address. Republishing that deterministic event
            # is safe and lets a caller recover from a publish failure after commit.
            if publish_event:
                self.publish_record_event(
                    existing,
                    producer=producer,
                    producer_version=producer_version,
                )
            return existing

        observation = {
            "observation_id": observation_id,
            "tenant_id": tenant_id,
            "investigation_id": investigation_id,
            "source_id": source_id,
            "work_id": work_id,
            "region_id": region_id,
            "capture_id": capture_id,
            "locator": record_locator,
            "record_digest": record_digest,
            "content_type": content_type,
            "raw_ref": raw_ref,
            "parser_hint": parser_hint,
            "status": "created",
            "duplicate": False,
            "provenance": {
                "version": 2,
                "collector": producer,
                "collector_version": producer_version,
                "identity_schema": identity.identity_schema,
            },
        }
        if record_metadata is not None:
            observation["record_metadata"] = dict(record_metadata)

        # The gate's in-process index is a cache only. Production persistence is
        # owned by ArtifactSink's injected evidence writer before event publication.
        self._observations[observation_id] = observation
        if publish_event:
            self.publish_record_event(
                observation,
                producer=producer,
                producer_version=producer_version,
            )
        return observation

    #: Named ``ingest`` historically; §9 asks for the blob-level seam to be
    #: visibly distinct from the record-level one at the call site. One
    #: implementation, two names, zero behavioural difference.
    ingest_capture = ingest

    def mutate_attempt(self, observation_id: str, patch: dict) -> None:
        """I-1 enforcement: any immutable-field mutation raises."""
        existing = self._observations.get(observation_id)
        if existing is None:
            raise KeyError(observation_id)
        enforce_observation_immutable(existing, patch)
        for k, v in patch.items():
            existing[k] = v
        return existing