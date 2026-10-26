"""Durable PostgreSQL registration for raw-first acquisition evidence.

ObjectStore owns immutable bytes; this writer atomically registers the Capture and
Observation rows before the corresponding observation event is published.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError


class EvidenceWriteError(RuntimeError):
    """A capture/observation transaction failed or collided with immutable evidence."""


def _json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )


class PostgresAcquisitionEvidenceWriter:
    """Write through the existing captures and observations schema."""

    def __init__(self, session_factory: Any) -> None:
        if session_factory is None:
            raise ValueError("session_factory is required")
        self._session_factory = session_factory

    async def persist(
        self, *, capture: Any, observation: Mapping[str, Any], raw_ref: str
    ) -> dict[str, str]:
        capture_id = str(getattr(capture, "capture_id", "") or "")
        tenant_id = str(getattr(capture, "tenant_id", "") or "")
        source_id = str(getattr(capture, "source_id", "") or "")
        digest = str(getattr(capture, "content_digest", "") or "")
        fingerprint = str(getattr(capture, "capture_fingerprint", "") or "")
        observation_id = str(observation.get("observation_id") or "")
        observation_tenant = str(observation.get("tenant_id") or "")
        raw_uri = str(observation.get("raw_ref") or raw_ref or "")
        record_digest = str(observation.get("record_digest") or "")
        if not all((capture_id, tenant_id, source_id, digest, fingerprint,
                    observation_id, observation_tenant, raw_uri, record_digest)):
            raise EvidenceWriteError("capture/observation lacks required identity fields")
        if tenant_id != observation_tenant:
            raise EvidenceWriteError("capture and observation tenant_id differ")
        if digest != record_digest:
            raise EvidenceWriteError("capture and observation content digests differ")
        if not raw_uri.startswith("s3://"):
            raise EvidenceWriteError("raw_ref must be a content-addressed s3:// reference")

        basis = getattr(capture, "time_basis", "")
        basis = str(getattr(basis, "value", basis))
        capture_values = {
            "capture_id": capture_id,
            "tenant_id": tenant_id,
            "source_id": source_id,
            "source_family": str(getattr(capture, "source_family", "") or ""),
            "target_uri": str(getattr(capture, "target_uri", "") or ""),
            "locator": str(getattr(capture, "locator", "") or ""),
            "content_digest": digest,
            "content_length": getattr(capture, "content_length", None),
            "media_type": str(getattr(capture, "media_type", "") or ""),
            "fetched_at": getattr(capture, "fetched_at", None),
            "capture_time_basis": basis,
            "transport": str(getattr(capture, "transport", "") or ""),
            "ingest_batch_id": str(getattr(capture, "ingest_batch_id", "unbatched") or "unbatched"),
            "ingest_attempt": int(getattr(capture, "ingest_attempt", 1) or 1),
            "recorded_by": str(getattr(capture, "recorded_by", "") or ""),
            "capture_fingerprint": fingerprint,
        }
        record_metadata = dict(observation.get("record_metadata") or {})
        provenance = dict(observation.get("provenance") or {})
        provenance.update({
            "capture_id": capture_id,
            "capture_fingerprint": fingerprint,
            "locator": str(observation.get("locator") or ""),
            "raw_ref": raw_uri,
            "record_digest": record_digest,
            "parser_hint": str(observation.get("parser_hint") or ""),
            "record_metadata": record_metadata,
        })
        task_id = str(observation.get("work_id") or observation.get("task_id") or "")
        observation_values = {
            "observation_id": observation_id,
            "tenant_id": tenant_id,
            "investigation_id": observation.get("investigation_id"),
            "source_id": str(observation.get("source_id") or source_id),
            "task_id": task_id or None,
            "uri": str(record_metadata.get("target_uri") or record_metadata.get("url")
                       or getattr(capture, "target_uri", "") or ""),
            "raw_ref": raw_uri,
            "content_hash": record_digest,
            "content_type": str(observation.get("content_type") or "") or None,
            "status": str(observation.get("status") or "created"),
            "duplicate": bool(observation.get("duplicate", False)),
            "provenance": _json(provenance),
        }
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    await session.execute(text("""
                        INSERT INTO captures (
                            capture_id, tenant_id, source_id, source_family, target_uri,
                            locator, content_digest, content_length, media_type, fetched_at,
                            capture_time_basis, transport, ingest_batch_id, ingest_attempt,
                            recorded_by, capture_fingerprint
                        ) VALUES (
                            :capture_id, :tenant_id, :source_id, :source_family, :target_uri,
                            :locator, :content_digest, :content_length, :media_type, :fetched_at,
                            :capture_time_basis, :transport, :ingest_batch_id, :ingest_attempt,
                            :recorded_by, :capture_fingerprint
                        ) ON CONFLICT DO NOTHING
                    """), capture_values)
                    result = await session.execute(text("""
                        SELECT capture_id, capture_fingerprint, content_digest
                        FROM captures
                        WHERE tenant_id = :tenant_id
                          AND (capture_id = :capture_id OR capture_fingerprint = :capture_fingerprint)
                        ORDER BY CASE WHEN capture_id = :capture_id THEN 0 ELSE 1 END
                        LIMIT 1
                    """), {
                        "tenant_id": tenant_id, "capture_id": capture_id,
                        "capture_fingerprint": fingerprint,
                    })
                    stored_capture = result.mappings().first()
                    if stored_capture is None or (
                        stored_capture["capture_id"] != capture_id
                        or stored_capture["capture_fingerprint"] != fingerprint
                        or stored_capture["content_digest"] != digest
                    ):
                        raise EvidenceWriteError("capture row missing or collides with immutable evidence")

                    await session.execute(text("""
                        INSERT INTO observations (
                            observation_id, tenant_id, investigation_id, source_id, task_id,
                            uri, raw_ref, content_hash, content_type, status, duplicate, provenance
                        ) VALUES (
                            :observation_id, :tenant_id, :investigation_id, :source_id, :task_id,
                            :uri, :raw_ref, :content_hash, :content_type, :status, :duplicate,
                            CAST(:provenance AS jsonb)
                        ) ON CONFLICT (observation_id) DO NOTHING
                    """), {
                        **{key: value for key, value in observation_values.items() if key != "provenance"},
                        "provenance": observation_values["provenance"],
                    })
                    result = await session.execute(text("""
                        SELECT tenant_id, task_id, raw_ref, content_hash, provenance
                        FROM observations WHERE observation_id = :observation_id
                    """), {"observation_id": observation_id})
                    stored_observation = result.mappings().first()
                    if stored_observation is None:
                        raise EvidenceWriteError("observation insert produced no readable row")
                    stored_provenance = stored_observation["provenance"]
                    if isinstance(stored_provenance, str):
                        stored_provenance = json.loads(stored_provenance)
                    if (
                        stored_observation["tenant_id"] != tenant_id
                        or stored_observation["task_id"] != observation_values["task_id"]
                        or stored_observation["raw_ref"] != raw_uri
                        or stored_observation["content_hash"] != record_digest
                        or not isinstance(stored_provenance, Mapping)
                        or stored_provenance.get("capture_id") != capture_id
                    ):
                        raise EvidenceWriteError("observation row conflicts with immutable evidence")
        except EvidenceWriteError:
            raise
        except (SQLAlchemyError, ValueError, TypeError, KeyError) as exc:
            raise EvidenceWriteError(
                f"PostgreSQL capture/observation transaction failed: {type(exc).__name__}: {exc}"
            ) from exc
        return {
            "capture_id": capture_id,
            "observation_id": observation_id,
            "tenant_id": tenant_id,
            "raw_ref": raw_uri,
            "content_digest": digest,
        }
