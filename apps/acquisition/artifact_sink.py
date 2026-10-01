"""The sink: ``AcquisitionArtifact`` -> ``Capture`` + ``Observation`` + event.

Directive §5's ``artifact_sink.accept(artifact)``, and the point where §9's two
seams are used for their intended purpose. An artifact names a thing a runtime
produced; the platform must decide how that thing is stored, what it is addressed
as, and what a consumer is told about it. All three happen here and nowhere else.

**The order is load-bearing.** Raw bytes go to the ObjectStore *first*, because
the capture's identity is built from the stored reference and its digest. An
observation that exists before its raw bytes are durable is a reference to
nothing, and §160 lists ``raw artifact absent`` and ``observation without raw
lineage`` as release blockers - so a store failure must abort before an address is
minted, not after.

**Why the record path is second.** ``ingest_record`` deliberately does not
re-store the blob. For a SearXNG page carrying two hundred results the blob is
stored once and two hundred observations address into it; storing per record
would make the same bytes two hundred objects, which is the §124 idempotency
requirement stated backwards.

**What the sink does not do.** It does not parse, classify, type, resolve or
score. It stores bytes, mints addresses, and publishes a ref-only event (§69).
The distinction matters because this is the last point where the platform still
has the raw artifact in hand: everything downstream of here reads it *through*
``raw_ref``, and nothing downstream may go back to the network (§174).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domain.acquisition_artifact import AcquisitionArtifact, ArtifactContractError
from domain.capture import Capture, CaptureTimeBasis
from domain.observation_identity import ObservationIdentityError, require_deterministic_event_id

#: Reason codes the sink reports. A sink failure is a stage the run manifest
#: names, because §159's failure report has a ``failed_stage`` field and a report
#: that says "acquisition failed" is the generic failure §73 forbids.
STAGE_RAW_STORE = "artifact.raw_store"
STAGE_CAPTURE = "artifact.capture_register"
STAGE_OBSERVATION = "artifact.observation_ingest"
STAGE_PUBLISH = "artifact.publish"


class ArtifactSinkError(RuntimeError):
    """A stage of the sink failed. Carries the stage name for the failure report."""

    def __init__(self, stage: str, code: str, message: str) -> None:
        super().__init__(f"{stage}/{code}: {message}")
        self.stage = stage
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AcceptedArtifact:
    """What the sink did with one artifact. The unit a caller can assert on.

    A sink that returns nothing gives its caller no way to state a requirement -
    §153's "observation created" has to mean an address, a digest and a topic,
    not a log line. So the return value carries the whole chain, and the run
    manifest (§71) is assembled from these.
    """

    artifact: AcquisitionArtifact
    capture_id: str
    capture_payload_key: str
    raw_ref: str
    content_digest: str
    observation_id: str
    locator: str
    event_id: str | None
    topic: str | None

    # Flat read-only views over the artifact, so a caller can assert on the chain
    # directly (``got.observation_id``) instead of digging through ``to_dict()``.
    # A sink that makes its callers index a dict to check a requirement is a sink
    # whose requirements get skipped.
    @property
    def task_id(self) -> str:
        return self.artifact.task_id

    @property
    def source_id(self) -> str:
        return self.artifact.source_id

    @property
    def worker_ref(self) -> str:
        return self.artifact.worker_ref

    @property
    def runtime_producer(self) -> str:
        return self.artifact.producer

    @property
    def runtime_producer_version(self) -> str:
        return self.artifact.producer_version

    @property
    def target_uri(self) -> str:
        return self.artifact.target_uri

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.artifact.task_id,
            "source_id": self.artifact.source_id,
            "worker_ref": self.artifact.worker_ref,
            "runtime_producer": self.artifact.producer,
            "runtime_producer_version": self.artifact.producer_version,
            "target_uri": self.artifact.target_uri,
            "locator": self.locator,
            "capture_id": self.capture_id,
            "capture_payload_key": self.capture_payload_key,
            "raw_ref": self.raw_ref,
            "content_digest": self.content_digest,
            "observation_id": self.observation_id,
            "event_id": self.event_id,
            "topic": self.topic,
            "byte_length": self.artifact.byte_length,
            "schema": self.artifact.schema,
        }


class ArtifactSink:
    """Stores, addresses and announces. One artifact in, one trace out."""

    def __init__(
        self,
        *,
        gate: Any,
        store: Any,
        source_family: str = "",
        recorded_by: str = "acquisition-worker",
    ) -> None:
        self._gate = gate
        self._store = store
        self._source_family = source_family
        self._recorded_by = recorded_by
        self._accepted: list[AcceptedArtifact] = []

    @property
    def accepted(self) -> tuple[AcceptedArtifact, ...]:
        return tuple(self._accepted)

    async def accept(
        self,
        artifact: AcquisitionArtifact,
        *,
        tenant_id: str,
        investigation_id: str | None = None,
        work_id: str | None = None,
        region_id: str | None = None,
        time_basis: CaptureTimeBasis = CaptureTimeBasis.FETCH,
    ) -> AcceptedArtifact:
        """Persist one artifact and address both the blob and this record in it."""
        if not isinstance(artifact, AcquisitionArtifact):
            raise ArtifactSinkError(
                STAGE_OBSERVATION,
                "artifact_type_invalid",
                f"expected AcquisitionArtifact, received {type(artifact).__name__}",
            )

        # --- 1. raw bytes, first and unconditionally (I-1, §160) ---------------
        try:
            ref, _stored_before = await self._store.put_raw_dedup(
                artifact.body,
                tenant_id=tenant_id,
                meta={
                    "content_type": artifact.content_type,
                    "source_id": artifact.source_id,
                    "task_id": artifact.task_id,
                },
            )
        except Exception as exc:  # noqa: BLE001 - re-raised with a stage name
            raise ArtifactSinkError(
                STAGE_RAW_STORE, "raw_store_failed", f"{type(exc).__name__}: {exc}"
            ) from exc

        digest = ref.sha256

        # --- 2. the capture: first-class, verified, not a projection ----------
        # The capture is addressed by the *capture* locator, never the record's.
        # Capture folds locator into its identity material, so a record locator
        # here would make one fetch register as N captures (§20, §6).
        try:
            capture = Capture(
                tenant_id=tenant_id,
                source_id=artifact.source_id,
                source_family=self._source_family,
                target_uri=artifact.target_uri,
                locator=artifact.effective_capture_locator(),
                content_digest=digest,
                content_length=artifact.byte_length,
                media_type=artifact.content_type or "",
                fetched_at=artifact.fetched_at,
                time_basis=time_basis,
                transport=artifact.transport,
                recorded_by=self._recorded_by,
            )
        except Exception as exc:  # noqa: BLE001
            raise ArtifactSinkError(
                STAGE_CAPTURE, "capture_rejected", f"{type(exc).__name__}: {exc}"
            ) from exc

        # --- 3. the record observation, without re-storing the blob (§9) -------
        try:
            observation = await self._gate.ingest_record(
                capture_id=capture.capture_id,
                record_locator=artifact.locator,
                record_digest=digest,
                tenant_id=tenant_id,
                # The bytes the consumer will read back. The gate deliberately does
                # not store them (§9), so the only component that knows the
                # reference is this one - and §69 requires the event to carry it,
                # or the observation is unresolvable.
                raw_ref=ref.uri,
                # The parser hint travels with the record because §63 wants every
                # observation traceable to the parser that reads it, and the
                # consumer has no other way to learn it: the runtime that produced
                # a record (searxng, bbot, a connector) is not the parser that
                # reads it, and routing on the producer name sent every JSON result
                # down the text route.
                parser_hint=artifact.metadata.get("parser_hint", "") or "",
                investigation_id=investigation_id,
                source_id=artifact.source_id,
                work_id=work_id,
                region_id=region_id,
                content_type=artifact.content_type,
                record_metadata={
                    "schema": artifact.schema,
                    "producer": artifact.producer,
                    "producer_version": artifact.producer_version,
                    "transport": artifact.transport,
                    "target_uri": artifact.target_uri,
                    "task_id": artifact.task_id,
                    "worker_ref": artifact.worker_ref,
                    "fetched_at": artifact.fetched_at.isoformat(),
                    # §62: vendor fields the platform did not map are retained
                    # rather than dropped, and the raw artifact stays the source
                    # of truth for anything not listed here.
                    **({"runtime_metadata": dict(artifact.metadata)} if artifact.metadata else {}),
                },
            )
        except (ArtifactContractError, ObservationIdentityError) as exc:
            raise ArtifactSinkError(
                STAGE_OBSERVATION, getattr(exc, "code", "observation_rejected"), str(exc)
            ) from exc

        # --- 4. the address the consumer will look the event up by ------------
        event_id: str | None = None
        topic: str | None = None
        emitted = self._last_emitted_event()
        if emitted is not None:
            event_id = require_deterministic_event_id(emitted[0])
            topic = emitted[1]

        accepted = AcceptedArtifact(
            artifact=artifact,
            capture_id=capture.capture_id,
            capture_payload_key=capture.payload_key,
            raw_ref=ref.uri,
            content_digest=digest,
            observation_id=observation["observation_id"],
            locator=artifact.locator,
            event_id=event_id,
            topic=topic,
        )
        self._accepted.append(accepted)
        return accepted

    def _last_emitted_event(self) -> tuple[str, str] | None:
        """Read back the last event the gate published, if it published one.

        The gate is the component that owns the envelope, and duplicating its
        event construction here to report an ``event_id`` would be a second
        builder of the same message - the drift this feature exists to remove.
        So the gate records what it emitted, and the sink reports it.

        Returns ``(event_id, topic)`` or ``None`` when no producer is attached, in
        which case ``event_id`` is legitimately ``None`` rather than a placeholder:
        an offline run has no event to name.
        """
        recorded = getattr(self._gate, "last_emitted", None)
        if not recorded:
            return None
        return recorded["event_id"], recorded["topic"]
