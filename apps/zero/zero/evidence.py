"""Bridge deterministic zero-layer stages into the platform evidence authority.

This module does not store bytes, mint Observation IDs, or publish Kafka events.
It reduces one typed stage record into an AcquisitionArtifact and delegates the
raw-first write to the injected ArtifactSink. The resulting Observation is always
DISCOVERY_ONLY: a harvested candidate is not a fact and cannot satisfy a claim.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from domain.acquisition_artifact import AcquisitionArtifact
from domain.capture import CaptureTimeBasis

_ALLOWED_STAGES = frozenset({"HARVEST", "ENRICHMENT", "RESOLUTION"})


class ArtifactSinkProtocol(Protocol):
    async def accept(
        self,
        artifact: AcquisitionArtifact,
        *,
        tenant_id: str,
        investigation_id: str | None = None,
        work_id: str | None = None,
        region_id: str | None = None,
        time_basis: CaptureTimeBasis = CaptureTimeBasis.FETCH,
    ) -> Any: ...


@dataclass(frozen=True)
class PersistedZeroLayerStage:
    stage: str
    wave_index: int
    seed_id: str
    task_id: str
    capture_id: str
    observation_id: str
    raw_ref: str
    content_digest: str
    event_id: str | None
    topic: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "wave_index": self.wave_index,
            "seed_id": self.seed_id,
            "task_id": self.task_id,
            "capture_id": self.capture_id,
            "observation_id": self.observation_id,
            "raw_ref": self.raw_ref,
            "content_digest": self.content_digest,
            "event_id": self.event_id,
            "topic": self.topic,
            "result_role": "DISCOVERY_ONLY",
            "claim_admission_allowed": False,
        }


class ZeroLayerEvidenceSink:
    """Persist stage outputs through the canonical Capture/Observation path."""

    def __init__(
        self,
        artifact_sink: ArtifactSinkProtocol,
        *,
        source_id: str = "zero-layer",
        worker_ref: str = "zero-layer",
    ) -> None:
        if artifact_sink is None:
            raise ValueError("artifact_sink is required")
        if not source_id or len(source_id) > 36:
            raise ValueError("source_id must be non-empty and fit Observation.source_id")
        if not worker_ref:
            raise ValueError("worker_ref is required")
        self._artifact_sink = artifact_sink
        self._source_id = source_id
        self._worker_ref = worker_ref

    async def persist(
        self,
        record: Any,
        *,
        tenant_id: str,
        investigation_id: str | None = None,
    ) -> PersistedZeroLayerStage:
        if not tenant_id or not str(tenant_id).strip():
            raise ValueError("tenant_id is required")
        data = record.as_dict() if callable(getattr(record, "as_dict", None)) else record
        if not isinstance(data, Mapping):
            raise TypeError("zero-layer stage record must be a mapping or expose as_dict()")

        stage = str(data.get("stage") or "").upper()
        if stage not in _ALLOWED_STAGES:
            raise ValueError(f"unsupported zero-layer stage: {stage!r}")
        seed_id = str(data.get("seed_id") or "").strip()
        if not seed_id:
            raise ValueError("zero-layer stage record requires seed_id")
        wave_index = int(data.get("wave_index", -1))
        if wave_index < 0:
            raise ValueError("zero-layer stage record requires a non-negative wave_index")

        body = json.dumps(
            dict(data),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
        digest = hashlib.sha256(body).hexdigest()
        task_scope = f"{tenant_id}|{investigation_id or ''}|{digest}"
        task_id = "ZL-" + hashlib.sha256(task_scope.encode("utf-8")).hexdigest()[:32]
        # 35 chars; Observation.task_id is VARCHAR(36).
        locator = (
            f"zero-layer/v1/{seed_id}/wave-{wave_index:02d}/"
            f"{stage.lower()}/{digest[:24]}"
        )
        target_uri = f"zero-layer://seed/{seed_id}"
        candidate_count = int(data.get("candidate_count", len(data.get("candidates") or [])))

        metadata = {
            "parser_hint": "json",
            "result_role": "DISCOVERY_ONLY",
            "claim_admission_allowed": False,
            "zero_layer_stage": stage,
            "zero_layer_wave_index": wave_index,
            "zero_layer_seed_id": seed_id,
            "zero_layer_seed_type": str(data.get("seed_type") or "unknown"),
            "parent_observation_id": str(data.get("parent_observation_id") or ""),
            "discovery_observation_id": str(data.get("discovery_observation_id") or ""),
            "zero_layer_candidate_count": candidate_count,
            "zero_layer_worker_commands_pending": int(data.get("pending_worker_commands") or 0),
            "target_uri": target_uri,
        }
        artifact = AcquisitionArtifact(
            task_id=task_id,
            source_id=self._source_id,
            worker_ref=self._worker_ref,
            target_uri=target_uri,
            locator=locator,
            body=body,
            content_type="application/json",
            fetched_at=datetime.now(UTC),
            transport="local",
            producer="zero-layer",
            producer_version="0.2.0",
            metadata=metadata,
        )
        accepted = await self._artifact_sink.accept(
            artifact,
            tenant_id=tenant_id,
            investigation_id=investigation_id,
            work_id=task_id,
            time_basis=CaptureTimeBasis.ABSENT,
        )
        return PersistedZeroLayerStage(
            stage=stage,
            wave_index=wave_index,
            seed_id=seed_id,
            task_id=task_id,
            capture_id=str(accepted.capture_id),
            observation_id=str(accepted.observation_id),
            raw_ref=str(accepted.raw_ref),
            content_digest=str(accepted.content_digest),
            event_id=getattr(accepted, "event_id", None),
            topic=getattr(accepted, "topic", None),
        )


    async def persist_capture(
        self,
        capture: Any,
        *,
        tenant_id: str,
        investigation_id: str | None = None,
    ) -> Any:
        """Persist fetched bytes as the parent capture before stage observations."""
        if not tenant_id or not str(tenant_id).strip():
            raise ValueError("tenant_id is required")
        body = bytes(getattr(capture, "body", b"") or b"")
        if not body:
            raise ValueError("zero-layer raw capture cannot be empty")
        url = str(getattr(capture, "url", "") or "").strip()
        if not url.startswith("https://"):
            raise ValueError("zero-layer raw capture must retain an HTTPS URL")
        fetched_at = getattr(capture, "fetched_at", None)
        if not isinstance(fetched_at, datetime):
            raise ValueError("zero-layer raw capture requires fetched_at")
        digest = hashlib.sha256(body).hexdigest()
        task_scope = f"{tenant_id}|{investigation_id or ''}|{url}|{digest}"
        task_id = "ZL-" + hashlib.sha256(task_scope.encode("utf-8")).hexdigest()[:32]
        metadata = {
            "parser_hint": "html" if "html" in str(getattr(capture, "content_type", "")).lower() else "text",
            "result_role": "DISCOVERY_ONLY",
            "claim_admission_allowed": False,
            "target_uri": url,
            "http_status": int(getattr(capture, "status", 0)),
            "pinned_ip": str(getattr(capture, "pinned_ip", "") or ""),
            "redirects": list(getattr(capture, "redirects", ()) or ()),
            "parent_observation_id": str(getattr(capture, "parent_observation_id", "") or ""),
            "discovery_source_id": str(getattr(capture, "discovery_source_id", "") or ""),
            "action_ref": str(getattr(capture, "action_ref", "") or ""),
        }
        artifact = AcquisitionArtifact(
            task_id=task_id,
            source_id=self._source_id,
            worker_ref=self._worker_ref,
            target_uri=url,
            locator=f"zero-layer/raw/{hashlib.sha256(url.encode('utf-8')).hexdigest()[:24]}/{digest[:24]}",
            body=body,
            content_type=str(getattr(capture, "content_type", "") or "application/octet-stream"),
            fetched_at=fetched_at,
            transport="https",
            producer="zero-layer-secure-public-fetch",
            producer_version="1.0.0",
            metadata=metadata,
            capture_locator=f"zero-layer/capture/{hashlib.sha256(task_scope.encode('utf-8')).hexdigest()[:32]}",
        )
        return await self._artifact_sink.accept(
            artifact,
            tenant_id=tenant_id,
            investigation_id=investigation_id,
            work_id=task_id,
            time_basis=CaptureTimeBasis.FETCH,
        )


__all__ = [
    "ArtifactSinkProtocol",
    "PersistedZeroLayerStage",
    "ZeroLayerEvidenceSink",
]
