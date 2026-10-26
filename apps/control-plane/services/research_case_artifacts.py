"""Static research-case artifacts over the canonical raw-first acquisition path.

Uploads are not stored in a case-local mini-store. They go through the platform's
ObjectStore -> ArtifactSink -> Capture/Observation evidence writer -> observation.created
event; the regular interpretation consumer then processes the same immutable raw bytes.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import PurePath
from typing import Any, Mapping
from urllib.parse import urlsplit

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError

from context_engine.store import ContextStore
from domain.acquisition_artifact import AcquisitionArtifact
from domain.capture import Capture, CaptureTimeBasis
from db.schema import CaptureRow, Observation
from services.research_case_service import CaseNotFound, CaseServiceError


MAX_ARTIFACT_BYTES = 25 * 1024 * 1024
_UPLOAD_SOURCE_ID = "case_upload"
_FILENAME_RE = re.compile(r"[^A-Za-z0-9._() -]+")


class CaseArtifactError(RuntimeError):
    """A case artifact was refused or could not be persisted."""


class PostgresCaseEvidenceWriter:
    """Transactional persistence half of ArtifactSink for the shared evidence tables."""

    def __init__(self, session_factory: Any) -> None:
        if session_factory is None:
            raise ValueError("session_factory is required")
        self._session_factory = session_factory

    async def persist(
        self,
        *,
        capture: Capture,
        observation: dict[str, Any],
        raw_ref: str,
    ) -> None:
        observation_id = str(observation.get("observation_id") or "")
        tenant_id = str(observation.get("tenant_id") or "")
        raw_ref = str(raw_ref or "")
        record_digest = str(observation.get("record_digest") or "")
        if not all((observation_id, tenant_id, raw_ref, record_digest)):
            raise CaseArtifactError("evidence record lacks observation, tenant, raw ref or digest")
        if tenant_id != capture.tenant_id:
            raise CaseArtifactError("capture and observation tenant differ")

        capture_values = {
            "capture_id": capture.capture_id,
            "tenant_id": capture.tenant_id,
            "source_id": capture.source_id,
            "source_family": capture.source_family,
            "target_uri": capture.target_uri,
            "locator": capture.locator,
            "content_digest": capture.content_digest,
            "content_length": capture.content_length,
            "media_type": capture.media_type,
            "fetched_at": capture.fetched_at,
            "capture_time_basis": capture.time_basis.value,
            "transport": capture.transport,
            "ingest_batch_id": capture.ingest_batch_id,
            "ingest_attempt": capture.ingest_attempt,
            "recorded_by": capture.recorded_by,
            "capture_fingerprint": capture.capture_fingerprint,
        }
        record_metadata = observation.get("record_metadata")
        if not isinstance(record_metadata, Mapping):
            record_metadata = {}
        runtime_metadata = record_metadata.get("runtime_metadata")
        if not isinstance(runtime_metadata, Mapping):
            runtime_metadata = {}
        artifact_metadata = runtime_metadata.get("case_artifact")
        if not isinstance(artifact_metadata, Mapping):
            artifact_metadata = {}

        observation_values = {
            "observation_id": observation_id,
            "tenant_id": tenant_id,
            "investigation_id": str(observation.get("investigation_id") or "") or None,
            "source_id": str(observation.get("source_id") or "") or None,
            "task_id": str(observation.get("work_id") or "") or None,
            "uri": str(
                record_metadata.get("target_uri")
                or runtime_metadata.get("target_uri")
                or observation.get("uri")
                or capture.target_uri
                or capture.locator
            ),
            "raw_ref": raw_ref,
            "content_hash": record_digest,
            "content_type": str(observation.get("content_type") or "") or None,
            "status": "created",
            "duplicate": bool(observation.get("duplicate", False)),
            "provenance": {
                **dict(observation.get("provenance") or {}),
                "capture_id": capture.capture_id,
                "capture_fingerprint": capture.capture_fingerprint,
                "raw_ref": raw_ref,
            },
        }

        try:
            async with self._session_factory() as session:
                async with session.begin():
                    await session.execute(
                        pg_insert(CaptureRow)
                        .values(**capture_values)
                        .on_conflict_do_nothing(index_elements=[CaptureRow.capture_id])
                    )
                    await session.execute(
                        pg_insert(Observation)
                        .values(**observation_values)
                        .on_conflict_do_nothing(index_elements=[Observation.observation_id])
                    )

                    stored_capture = await session.get(CaptureRow, capture.capture_id)
                    if (
                        stored_capture is None
                        or stored_capture.tenant_id != tenant_id
                        or stored_capture.capture_fingerprint != capture.capture_fingerprint
                        or stored_capture.content_digest != capture.content_digest
                    ):
                        raise CaseArtifactError("capture identity collision or failed durable write")
                    stored_observation = await session.get(Observation, observation_id)
                    if (
                        stored_observation is None
                        or stored_observation.tenant_id != tenant_id
                        or stored_observation.raw_ref != raw_ref
                        or stored_observation.content_hash != record_digest
                    ):
                        raise CaseArtifactError("observation identity collision or failed durable write")

                    if artifact_metadata:
                        required = (
                            "artifact_id", "case_id", "scope_revision", "content_digest",
                            "byte_length", "filename", "uploaded_by",
                        )
                        missing = [name for name in required if artifact_metadata.get(name) in (None, "")]
                        if missing:
                            raise CaseArtifactError(
                                "case artifact metadata is incomplete: " + ", ".join(missing)
                            )
                        await session.execute(
                            text(
                                """
                                INSERT INTO person_case_artifacts (
                                    artifact_id, tenant_id, case_id, scope_revision,
                                    capture_id, observation_id, raw_ref, content_digest,
                                    byte_length, content_type, filename, caption,
                                    artifact_kind, uploaded_by
                                ) VALUES (
                                    :artifact_id, :tenant_id, :case_id, :scope_revision,
                                    :capture_id, :observation_id, :raw_ref, :content_digest,
                                    :byte_length, :content_type, :filename, :caption,
                                    :artifact_kind, :uploaded_by
                                )
                                ON CONFLICT (artifact_id) DO NOTHING
                                """
                            ),
                            {
                                "artifact_id": str(artifact_metadata["artifact_id"]),
                                "tenant_id": tenant_id,
                                "case_id": str(artifact_metadata["case_id"]),
                                "scope_revision": int(artifact_metadata["scope_revision"]),
                                "capture_id": capture.capture_id,
                                "observation_id": observation_id,
                                "raw_ref": raw_ref,
                                "content_digest": str(artifact_metadata["content_digest"]),
                                "byte_length": int(artifact_metadata["byte_length"]),
                                "content_type": str(artifact_metadata.get("content_type") or "application/octet-stream"),
                                "filename": str(artifact_metadata["filename"]),
                                "caption": str(artifact_metadata.get("caption") or ""),
                                "artifact_kind": str(artifact_metadata.get("artifact_kind") or "static_attachment"),
                                "uploaded_by": str(artifact_metadata["uploaded_by"]),
                            },
                        )
                        row = (
                            await session.execute(
                                text(
                                    """
                                    SELECT tenant_id, case_id, observation_id, content_digest, raw_ref
                                    FROM person_case_artifacts WHERE artifact_id = :artifact_id
                                    """
                                ),
                                {"artifact_id": str(artifact_metadata["artifact_id"])},
                            )
                        ).mappings().first()
                        if (
                            row is None or row["tenant_id"] != tenant_id
                            or row["case_id"] != artifact_metadata["case_id"]
                            or row["observation_id"] != observation_id
                            or row["content_digest"] != record_digest
                            or row["raw_ref"] != raw_ref
                        ):
                            raise CaseArtifactError("durable case artifact row conflicts with its evidence")
        except CaseArtifactError:
            raise
        except Exception as exc:  # noqa: BLE001 - ArtifactSink must not publish on a failed commit
            raise CaseArtifactError(
                f"capture/observation persistence failed: {type(exc).__name__}: {exc}"
            ) from exc


class ResearchCaseArtifactService:
    """Tenant-scoped static artifacts using the platform's existing evidence sink."""

    def __init__(
        self,
        *,
        context_store: ContextStore,
        session_factory: Any,
        object_store: Any | None = None,
        producer: Any | None = None,
    ) -> None:
        self._context_store = context_store
        self._session_factory = session_factory
        self._object_store = object_store
        self._producer = producer

    @staticmethod
    def _filename(value: str) -> str:
        # Use a display basename only. Never interpret a supplied path or execute a file.
        name = PurePath(str(value or "attachment")).name.strip()
        name = _FILENAME_RE.sub("_", name).strip(" .")
        return (name or "attachment.bin")[:255]

    async def upload(
        self,
        *,
        case_id: str,
        tenant_id: str,
        actor_id: str,
        filename: str,
        content_type: str,
        caption: str,
        body: bytes,
    ) -> dict[str, Any]:
        if not body:
            raise CaseArtifactError("empty artifacts are not accepted")
        if len(body) > MAX_ARTIFACT_BYTES:
            raise CaseArtifactError(
                f"artifact exceeds the {MAX_ARTIFACT_BYTES}-byte upload limit"
            )
        if not actor_id.strip():
            raise CaseArtifactError("upload actor is required")

        context = await self._context_store.get_context(case_id)
        if context is None or context.tenant_id != tenant_id:
            raise CaseNotFound("case not found")
        if getattr(context.state, "value", str(context.state)) == "CLOSED":
            raise CaseArtifactError("closed cases cannot receive new artifacts")
        meta = await self._context_store.get_person_case_metadata(case_id)
        if meta is None or meta.get("tenant_id") != tenant_id:
            raise CaseNotFound("case not found")

        filename = self._filename(filename)
        content_type = (str(content_type or "application/octet-stream").split(";", 1)[0].strip().lower()
                        or "application/octet-stream")
        caption = str(caption or "").strip()[:2000]
        digest = hashlib.sha256(body).hexdigest()
        artifact_id = "CA-" + hashlib.sha256(
            f"{tenant_id}|{case_id}|{digest}|{filename}".encode("utf-8")
        ).hexdigest()[:32]
        now = datetime.now(UTC)
        task_id = "UPL-" + hashlib.sha256(
            f"{tenant_id}|{case_id}|{digest}".encode("utf-8")
        ).hexdigest()[:32]
        target_uri = f"case-upload://{case_id}/{digest}"
        locator = f"case-artifact:{case_id}:{digest}"
        artifact_metadata = {
            "artifact_id": artifact_id,
            "case_id": case_id,
            "scope_revision": int(meta.get("scope_revision", 0)),
            "content_digest": digest,
            "byte_length": len(body),
            "content_type": content_type,
            "filename": filename,
            "caption": caption,
            "artifact_kind": "static_attachment",
            "uploaded_by": actor_id,
        }

        try:
            from artifact_sink import ArtifactSink
            from dispatcher.kafka_producer import KafkaProducer
            from domain.capture import CaptureTimeBasis
            from domain.acquisition_artifact import AcquisitionArtifact
            from events.content_router import ContentRouter
            from events.observation_gate import ObservationGate
            from storage.s3 import ObjectStore

            store = self._object_store or ObjectStore()
            producer = self._producer or KafkaProducer()
            gate = ObservationGate(store=store, router=ContentRouter(), producer=producer)
            evidence_writer = PostgresCaseEvidenceWriter(self._session_factory)
            sink = ArtifactSink(
                gate=gate,
                store=store,
                source_family="case_upload",
                recorded_by="research-case-upload",
                evidence_writer=evidence_writer,
            )
            artifact = AcquisitionArtifact(
                task_id=task_id,
                source_id=_UPLOAD_SOURCE_ID,
                worker_ref="research-case-upload",
                target_uri=target_uri,
                locator=locator,
                body=body,
                content_type=content_type,
                fetched_at=now,
                transport="user_upload",
                producer="research-case-upload",
                producer_version="1",
                metadata={
                    "source_family": "case_upload",
                    "case_id": case_id,
                    "filename": filename,
                    "caption": caption,
                    "target_uri": target_uri,
                    "scope_revision": int(meta.get("scope_revision", 0)),
                    "case_artifact": artifact_metadata,
                },
                capture_locator=f"case-upload-capture:{case_id}:{digest}",
            )
            accepted = await sink.accept(
                artifact,
                tenant_id=tenant_id,
                investigation_id=context.investigation_id,
                work_id=task_id,
                region_id="",
                time_basis=CaptureTimeBasis.ABSENT,
            )
        except CaseArtifactError:
            raise
        except Exception as exc:  # noqa: BLE001 - failures must be visible to the caller
            raise CaseArtifactError(
                f"artifact sink refused upload: {type(exc).__name__}: {exc}"
            ) from exc

        artifact_row = await self._artifact_row(
            tenant_id=tenant_id, case_id=case_id, artifact_id=artifact_id
        )
        if artifact_row is None:
            raise CaseArtifactError("artifact event published but durable artifact row is missing")

        # Sidecar references are a convenient read model; the canonical artifact record
        # and capture/observation transaction already live in PostgreSQL above.
        refs = list(meta.get("static_artifact_refs", []))
        if not any(item.get("artifact_id") == artifact_id for item in refs if isinstance(item, Mapping)):
            refs.append(self._public_artifact(artifact_row))
        await self._context_store.put_person_case_metadata(
            case_id=case_id,
            tenant_id=tenant_id,
            purpose_code=str(meta["purpose_code"]),
            basis_ref=str(meta["basis_ref"]),
            launch_profile=str(meta["launch_profile"]),
            claim_families=list(meta.get("claim_families", [])),
            allowed_source_ids=list(meta.get("allowed_source_ids", [])),
            denied_claim_families=list(meta.get("denied_claim_families", [])),
            scope_digest=str(meta["scope_digest"]),
            scope_revision=int(meta["scope_revision"]),
            approved=bool(meta.get("approved", False)),
            budget_ref=meta.get("budget_ref"),
            expires_at=meta.get("expires_at"),
            valid_time=dict(meta.get("valid_time", {})),
            jurisdictions=list(meta.get("jurisdictions", [])),
            subject_anchors=list(meta.get("subject_anchors", [])),
            context_amendments=list(meta.get("context_amendments", [])),
            dynamic_invariant_anchors=list(meta.get("dynamic_invariant_anchors", [])),
            static_artifact_refs=refs,
            latest_report_ref=dict(meta.get("latest_report_ref", {})),
        )
        revision_number = await self._context_store.next_revision_number(case_id)
        from domain.investigation_context import ContextRevision

        await self._context_store.append_revision(
            ContextRevision(
                context_id=case_id,
                revision=revision_number,
                parent_revision=revision_number - 1,
                state=context.state,
                snapshot={
                    "context": context.to_dict(),
                    "artifact": self._public_artifact(artifact_row),
                    "scope_digest": meta.get("scope_digest"),
                    "scope_revision": meta.get("scope_revision"),
                    "raw_bytes_immutable": True,
                },
                operator_actions=(actor_id, "static_artifact_uploaded"),
                rules_version="feature-034-artifact-v1",
                mode="deterministic",
            )
        )
        return {
            **self._public_artifact(artifact_row),
            "event_id": getattr(accepted, "event_id", None),
            "event_topic": getattr(accepted, "topic", None),
            "processing_state": "QUEUED_FOR_INTERPRETATION",
        }

    async def list_artifacts(
        self, *, case_id: str, tenant_id: str
    ) -> dict[str, Any]:
        context = await self._context_store.get_context(case_id)
        if context is None or context.tenant_id != tenant_id:
            raise CaseNotFound("case not found")
        async with self._session_factory() as session:
            result = await session.execute(
                text(
                    """
                    SELECT * FROM person_case_artifacts
                    WHERE tenant_id = :tenant_id AND case_id = :case_id
                    ORDER BY created_at ASC, artifact_id ASC
                    """
                ),
                {"tenant_id": tenant_id, "case_id": case_id},
            )
            rows = [dict(row) for row in result.mappings().all()]
        return {
            "case_id": case_id,
            "artifacts": [self._public_artifact(row) for row in rows],
            "count": len(rows),
            "source_of_truth": "postgres:person_case_artifacts",
        }

    async def download(
        self, *, case_id: str, artifact_id: str, tenant_id: str
    ) -> tuple[dict[str, Any], bytes]:
        context = await self._context_store.get_context(case_id)
        if context is None or context.tenant_id != tenant_id:
            raise CaseNotFound("case not found")
        row = await self._artifact_row(
            tenant_id=tenant_id, case_id=case_id, artifact_id=artifact_id
        )
        if row is None:
            raise CaseNotFound("artifact not found")
        raw_ref = str(row["raw_ref"])
        parsed = urlsplit(raw_ref)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        store = self._object_store
        if store is None:
            from storage.s3 import ObjectStore
            store = ObjectStore()
        if bucket != store.raw_bucket or not key.startswith(f"raw/{tenant_id}/"):
            raise CaseArtifactError("artifact raw reference is outside the current tenant/bucket")
        body = await store.read_range(bucket=bucket, key=key, offset=0, length=None)
        digest = hashlib.sha256(body).hexdigest()
        if digest != row["content_digest"] or len(body) != int(row["byte_length"]):
            raise CaseArtifactError("raw artifact digest/length verification failed")
        return self._public_artifact(row), body

    async def _artifact_row(
        self, *, tenant_id: str, case_id: str, artifact_id: str
    ) -> dict[str, Any] | None:
        async with self._session_factory() as session:
            result = await session.execute(
                text(
                    """
                    SELECT * FROM person_case_artifacts
                    WHERE tenant_id = :tenant_id AND case_id = :case_id AND artifact_id = :artifact_id
                    """
                ),
                {"tenant_id": tenant_id, "case_id": case_id, "artifact_id": artifact_id},
            )
            row = result.mappings().first()
        return dict(row) if row is not None else None

    @staticmethod
    def _public_artifact(row: Mapping[str, Any]) -> dict[str, Any]:
        created = row.get("created_at")
        if isinstance(created, datetime):
            created = created.astimezone(UTC).isoformat().replace("+00:00", "Z")
        return {
            "artifact_id": str(row["artifact_id"]),
            "case_id": str(row["case_id"]),
            "capture_id": str(row["capture_id"]),
            "observation_id": str(row["observation_id"]),
            "raw_ref": str(row["raw_ref"]),
            "content_digest": str(row["content_digest"]),
            "byte_length": int(row["byte_length"]),
            "content_type": str(row["content_type"]),
            "filename": str(row["filename"]),
            "caption": str(row.get("caption") or ""),
            "artifact_kind": str(row.get("artifact_kind") or "static_attachment"),
            "uploaded_by": str(row["uploaded_by"]),
            "created_at": created,
            "download_path": f"/api/v1/research-cases/{row['case_id']}/artifacts/{row['artifact_id']}/download",
        }
