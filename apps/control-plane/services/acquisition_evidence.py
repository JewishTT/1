"""PostgreSQL writer for raw-first Capture + Observation evidence.

The ObjectStore owns immutable bytes. This writer owns the relational evidence records.
The caller must publish the observation event only after this transaction commits.
"""
from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError

from db.schema import CaptureRow, Observation


class AcquisitionEvidenceWriteError(RuntimeError):
    """A Capture/Observation transaction failed or conflicted with existing evidence."""


class PostgresAcquisitionEvidenceWriter:
    """Atomically register a capture and one observation against durable raw bytes."""

    def __init__(self, session_factory: Any) -> None:
        if session_factory is None:
            raise ValueError("session_factory is required")
        self._session_factory = session_factory

    async def persist(
        self,
        *,
        capture: Any,
        observation: Mapping[str, Any],
        raw_ref: str,
    ) -> dict[str, str]:
        capture_id = str(getattr(capture, "capture_id", "") or "")
        tenant_id = str(getattr(capture, "tenant_id", "") or "")
        capture_digest = str(getattr(capture, "content_digest", "") or "")
        capture_fingerprint = str(getattr(capture, "capture_fingerprint", "") or "")
        observation_id = str(observation.get("observation_id") or "")
        observation_tenant = str(observation.get("tenant_id") or "")
        observation_digest = str(observation.get("record_digest") or "")
        observation_raw_ref = str(observation.get("raw_ref") or raw_ref or "")
        if not all((capture_id, tenant_id, capture_digest, capture_fingerprint,
                    observation_id, observation_tenant, observation_digest, observation_raw_ref)):
            raise AcquisitionEvidenceWriteError("capture/observation evidence lacks required identity fields")
        if tenant_id != observation_tenant or not observation_raw_ref.startswith("s3://"):
            raise AcquisitionEvidenceWriteError("capture and observation tenant/raw reference mismatch")
        if capture_digest != observation_digest:
            raise AcquisitionEvidenceWriteError("capture and observation content digests differ")

        capture_values = {
            "capture_id": capture_id,
            "tenant_id": tenant_id,
            "source_id": str(getattr(capture, "source_id", "") or ""),
            "source_family": str(getattr(capture, "source_family", "") or ""),
            "target_uri": str(getattr(capture, "target_uri", "") or ""),
            "locator": str(getattr(capture, "locator", "") or ""),
            "content_digest": capture_digest,
            "content_length": getattr(capture, "content_length", None),
            "media_type": str(getattr(capture, "media_type", "") or ""),
            "fetched_at": getattr(capture, "fetched_at", None),
            "capture_time_basis": str(getattr(getattr(capture, "time_basis", None), "value",
                                              getattr(capture, "time_basis", ""))),
            "transport": str(getattr(capture, "transport", "") or ""),
            "ingest_batch_id": str(getattr(capture, "ingest_batch_id", "unbatched") or "unbatched"),
            "ingest_attempt": int(getattr(capture, "ingest_attempt", 1) or 1),
            "recorded_by": str(getattr(capture, "recorded_by", "") or ""),
            "capture_fingerprint": capture_fingerprint,
        }
        record_metadata = dict(observation.get("record_metadata") or {})
        provenance = dict(observation.get("provenance") or {})
        provenance.update({
            "capture_id": capture_id,
            "locator": str(observation.get("locator") or ""),
            "raw_ref": observation_raw_ref,
            "record_digest": observation_digest,
            "parser_hint": str(observation.get("parser_hint") or ""),
            "record_metadata": record_metadata,
        })
        observation_values = {
            "observation_id": observation_id,
            "tenant_id": tenant_id,
            "investigation_id": observation.get("investigation_id"),
            "source_id": str(observation.get("source_id") or ""),
            "task_id": str(observation.get("work_id") or observation.get("task_id") or ""),
            "uri": str(
                record_metadata.get("target_uri")
                or record_metadata.get("url")
                or getattr(capture, "target_uri", "")
                or ""
            ),
            "raw_ref": observation_raw_ref,
            "content_hash": observation_digest,
            "content_type": str(observation.get("content_type") or "") or None,
            "status": str(observation.get("status") or "created"),
            "duplicate": bool(observation.get("duplicate", False)),
            "provenance": provenance,
        }

        try:
            async with self._session_factory() as session:
                async with session.begin():
                    await session.execute(
                        pg_insert(CaptureRow).values(**capture_values).on_conflict_do_nothing()
                    )
                    stored_capture = await session.execute(
                        select(CaptureRow).where(
                            CaptureRow.tenant_id == tenant_id,
                            CaptureRow.capture_id == capture_id,
                        )
                    )
                    capture_row = stored_capture.scalar_one_or_none()
                    if capture_row is None:
                        # A collision may have been on the (tenant_id, fingerprint)
                        # uniqueness constraint rather than the primary key.
                        stored_capture = await session.execute(
                            select(CaptureRow).where(
                                CaptureRow.tenant_id == tenant_id,
                                CaptureRow.capture_fingerprint == capture_fingerprint,
                            )
                        )
                        capture_row = stored_capture.scalar_one_or_none()
                    if capture_row is None:
                        raise AcquisitionEvidenceWriteError("capture insert did not produce a readable row")
                    if (
                        capture_row.capture_id != capture_id
                        or capture_row.capture_fingerprint != capture_fingerprint
                        or capture_row.content_digest != capture_digest
                    ):
                        raise AcquisitionEvidenceWriteError(
                            "capture identity/fingerprint conflicts with an existing immutable row"
                        )

                    await session.execute(
                        pg_insert(Observation).values(**observation_values).on_conflict_do_nothing()
                    )
                    stored_observation = await session.execute(
                        select(Observation).where(
                            Observation.tenant_id == tenant_id,
                            Observation.observation_id == observation_id,
                        )
                    )
                    observation_row = stored_observation.scalar_one_or_none()
                    if observation_row is None:
                        raise AcquisitionEvidenceWriteError("observation insert did not produce a readable row")
                    if (
                        observation_row.content_hash != observation_digest
                        or observation_row.raw_ref != observation_raw_ref
                        or observation_row.task_id != observation_values["task_id"]
                    ):
                        raise AcquisitionEvidenceWriteError(
                            "observation address conflicts with an existing immutable row"
                        )
        except AcquisitionEvidenceWriteError:
            raise
        except (SQLAlchemyError, ValueError, TypeError) as exc:
            raise AcquisitionEvidenceWriteError(
                f"capture/observation transaction failed: {type(exc).__name__}: {exc}"
            ) from exc

        return {
            "capture_id": capture_id,
            "observation_id": observation_id,
            "raw_ref": observation_raw_ref,
            "content_digest": capture_digest,
            "tenant_id": tenant_id,
        }
