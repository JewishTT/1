"""Adapter from zero-layer stage values to the canonical ArtifactSink.

Zero-layer does not mint Observation/Capture identifiers and never writes directly
to PostgreSQL, S3 or Kafka. This adapter is the only bridge from a stage record or
a guarded public fetch to the platform's ArtifactSink -> Capture -> Observation
path. Every output is DISCOVERY_ONLY and cannot be admitted as a factual claim.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from domain.acquisition_artifact import AcquisitionArtifact
from domain.capture import CaptureTimeBasis


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class CanonicalArtifactSink:
    def __init__(
        self,
        *,
        artifact_sink: Any,
        case_id: str,
        scope_digest: str,
        scope_revision: int,
        run_id: str,
    ) -> None:
        if artifact_sink is None:
            raise ValueError("ArtifactSink is required")
        if not all((case_id, scope_digest, run_id)):
            raise ValueError("case scope and run identity are required")
        self._sink = artifact_sink
        self._case_id = case_id
        self._scope_digest = scope_digest
        self._scope_revision = int(scope_revision)
        self._run_id = run_id

    async def persist_capture(
        self,
        capture: Any,
        *,
        tenant_id: str,
        investigation_id: str | None,
    ) -> Any:
        body = bytes(capture.body)
        digest = hashlib.sha256(body).hexdigest()
        identity = _digest(
            "|".join((tenant_id, self._case_id, capture.url, digest, self._run_id))
        )[:32]
        artifact = AcquisitionArtifact(
            task_id=f"ZLPAGE-{identity}",
            source_id="public_web_document_fetch",
            worker_ref="zero-layer-public-document",
            target_uri=str(capture.url),
            locator=f"public-document-response:{identity}",
            capture_locator=f"public-document-capture:{identity}",
            body=body,
            content_type=str(capture.content_type or "application/octet-stream"),
            fetched_at=capture.fetched_at,
            transport="https",
            producer="zero-layer-public-document",
            producer_version="1.0",
            metadata={
                "source_family": "public_web_document",
                "result_role": "DISCOVERY_ONLY",
                "claim_admission_allowed": False,
                "case_id": self._case_id,
                "scope_digest": self._scope_digest,
                "scope_revision": self._scope_revision,
                "run_id": self._run_id,
                "http_status": int(capture.status),
                "pinned_ip": str(capture.pinned_ip),
                "redirect_chain": list(capture.redirects),
                "captured_url": str(capture.url),
                "parent_observation_id": str(getattr(capture, "parent_observation_id", "")),
                "discovery_source_id": str(getattr(capture, "discovery_source_id", "")),
                "action_ref": str(getattr(capture, "action_ref", "")),
                "target_uri": str(capture.url),
            },
        )
        return await self._sink.accept(
            artifact,
            tenant_id=tenant_id,
            investigation_id=investigation_id,
            work_id=artifact.task_id,
            time_basis=CaptureTimeBasis.FETCH,
        )

    async def persist(
        self,
        record: Any,
        *,
        tenant_id: str,
        investigation_id: str | None,
    ) -> Any:
        payload = record.as_dict()
        payload.update({
            "result_role": "DISCOVERY_ONLY",
            "claim_admission_allowed": False,
            "case_id": self._case_id,
            "scope_digest": self._scope_digest,
            "scope_revision": self._scope_revision,
            "run_id": self._run_id,
        })
        body = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        record_key = "|".join((
            self._case_id,
            str(record.wave_index),
            str(record.seed_id),
            str(record.stage),
            self._run_id,
        ))
        identity = _digest(record_key)[:32]
        target_uri = f"zero-layer://{self._case_id}/{record.seed_id}/{record.stage.lower()}"
        artifact = AcquisitionArtifact(
            task_id=f"ZLSTAGE-{identity}",
            source_id="public_web_document_fetch",
            worker_ref="zero-layer-deterministic-pipeline",
            target_uri=target_uri,
            locator=f"zero-layer-stage:{identity}",
            capture_locator=f"zero-layer-stage-capture:{identity}",
            body=body,
            content_type="application/json",
            fetched_at=datetime.now(UTC),
            transport="derived",
            producer="zero-layer-deterministic-pipeline",
            producer_version="1.0",
            metadata={
                "source_family": "zero_layer",
                "result_role": "DISCOVERY_ONLY",
                "claim_admission_allowed": False,
                "case_id": self._case_id,
                "scope_digest": self._scope_digest,
                "scope_revision": self._scope_revision,
                "run_id": self._run_id,
                "stage": str(record.stage),
                "seed_id": str(record.seed_id),
                "parent_observation_id": str(getattr(record, "parent_observation_id", "")),
                "discovery_source_id": str(getattr(record, "source_id", "")),
                "target_uri": target_uri,
            },
        )
        return await self._sink.accept(
            artifact,
            tenant_id=tenant_id,
            investigation_id=investigation_id,
            work_id=artifact.task_id,
            time_basis=CaptureTimeBasis.ABSENT,
        )
