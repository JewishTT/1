"""Durable PostgreSQL registration for raw-first acquisition evidence.

Raw bytes are stored by ObjectStore; this writer registers the corresponding Capture
and Observation rows in one transaction. The caller publishes the observation event
only after this method returns.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError


class EvidenceWriteError(RuntimeError):
    """A durable capture/observation write failed or conflicted with immutable evidence."""


def _json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


class PostgresAcquisitionEvidenceWriter:
    """Own the relational write, without importing control-plane ORM classes into Layer 0."""

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
        source_id = str(getattr(capture, "source_id", "") or "")
        capture_digest = str(getattr(capture, "content_digest", "") or "")
        capture_fingerprint = str(getattr(capture, "capture_fingerprint", "") or "")
        observation_id = str(observation.get("observation_id") or "")
        observation_tenant = str(observation.get("tenant_id") or "")
        record_digest = str(observation.get("record_digest") or "")
        resolved_raw_ref = str(observation.get("raw_ref") or raw_ref or "")
        if not all((capture_id, tenant_id, source_id, capture_digest, capture_fingerprint,
                    observation_id, observation_tenant, record_digest, resolved_raw_ref)):
            raise EvidenceWriteError("capture/observation is missing required identity fields")
        if tenant_id != observation_tenant:
            raise EvidenceWriteError("capture and observation tenant_id differ")
        if capture_digest != record_digest:
            raise EvidenceWriteError("capture and observation content digests differ")
        if not resolved_raw_ref.startswith("s3://"):
            raise EvidenceWriteError("raw_ref is not a content-addressed s3:// reference")

        provenance = dict(observation.get("provenance") or {})
        provenance.update({
            "capture_id": capture_id,
            "capture_fingerprint": capture_fingerprint,
            "locator": str(observation.get("locator") or ""),
            "raw_ref": resolved_raw_ref,
            "record_digest": record_digest,
            "parser_hint": str(observation.get("parser_hint") or ""),
            "record_metadata": dict(observation.get("record_metadata") or {}),
        })
        record_metadata = dict(observation.get("record_metadata") or {})
        time_basis = getattr(capture, "time_basis", "")
        time_basis = str(getattr(time_basis, "value", time_basis))
        capture_values = {
            "capture_id": capture_id,
            "tenant_id": tenant_id,
            "source_id": source_id,
            "source_family": str(getattr(capture, "source_family", "") or ""),
            "target_uri": str(getattr(capture, "target_uri", "") or ""),
            "locator": str(getattr(capture, "locator", "") or ""),
            "content_digest": capture_digest,
            "content_length": getattr(capture, "content_length", None),
            "media_type": str(getattr(capture, "media_type", "") or ""),
            "fetched_at": getattr(capture, "fetched_at", None),
            "capture_time_basis": time_basis,
            "transport": str(getattr(capture, "transport", "") or ""),
            "ingest_batch_id": str(getattr(capture, "ingest_batch_id", "unbatched") or "unbatched"),
            "ingest_attempt": int(getattr(capture, "ingest_attempt", 1) or 1),
            "recorded_by": str(getattr(capture, "recorded_by", "") or ""),
            "capture_fingerprint": capture_fingerprint,
        }
        task_id = str(observation.get("work_id") or observation.get("task_id") or "")
        observation_values = {
            "observation_id": observation_id,
            "tenant_id": tenant_id,
            "investigation_id": observation.get("investigation_id"),
            "source_id": str(observation.get("source_id") or source_id),
            "task_id": task_id or None,
            "uri": str(record_metadata.get("target_uri") or record_metadata.get("url")
                       or getattr(capture, "target_uri", "") or ""),
            "raw_ref": resolved_raw_ref,
            "content_hash": record_digest,
            "content_type": str(observation.get("content_type") or "") or None,
            "status": str(observation.get("status") or "created"),
            "duplicate": bool(observation.get("duplicate", False)),
            "provenance": _json(provenance),
        }

        try:
            async with self._session_factory() as session:
                async with session.begin():
                    await session.execute(
                        text("""
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
                            )
                            ON CONFLICT DO NOTHING
                        """),
                        capture_values,
                    )
                    result = await session.execute(
                        text("""
                            SELECT capture_id, capture_fingerprint, content_digest
                            FROM captures
                            WHERE tenant_id = :tenant_id
                              AND (capture_id = :capture_id OR capture_fingerprint = :capture_fingerprint)
                            ORDER BY CASE WHEN capture_id = :capture_id THEN 0 ELSE 1 END
                            LIMIT 1
                        """),
                        {
                            "tenant_id": tenant_id,
                            "capture_id": capture_id,
                            "capture_fingerprint": capture_fingerprint,
                        },
                    )
                    stored_capture = result.mappings().first()
                    if stored_capture is None:
                        raise EvidenceWriteError("capture row was not visible after insert")
                    if (
                        stored_capture["capture_id"] != capture_id
                        or stored_capture["capture_fingerprint"] != capture_fingerprint
                        or stored_capture["content_digest"] != capture_digest
                    ):
                        raise EvidenceWriteError("capture address conflicts with existing immutable evidence")

                    await session.execute(
                        text("""
                            INSERT INTO observations (
                                observation_id, tenant_id, investigation_id, source_id, task_id,
                                uri, raw_ref, content_hash, content_type, status, duplicate, provenance
                            ) VALUES (
                                :observation_id, :tenant_id, :investigation_id, :source_id, :task_id,
                                :uri, :raw_ref, :content_hash, :content_type, :status, :duplicate,
                                CAST(:provenance AS jsonb)
                            )
                            ON CONFLICT (observation_id) DO NOTHING
                        """),
                        {
                            **{k: v for k, v in observation_values.items() if k != "provenance"},
                            "provenance": observation_values["provenance"],
                        },
                    )
                    result = await session.execute(
                        text("""
                            SELECT tenant_id, task_id, raw_ref, content_hash, provenance
                            FROM observations
                            WHERE observation_id = :observation_id
                        """),
                        {"observation_id": observation_id},
                    )
                    stored_observation = result.mappings().first()
                    if stored_observation is None:
                        raise EvidenceWriteError("observation row was not visible after insert")
                    stored_provenance = stored_observation["provenance"]
                    if isinstance(stored_provenance, str):
                        stored_provenance = json.loads(stored_provenance)
                    if (
                        stored_observation["tenant_id"] != tenant_id
                        or stored_observation["task_id"] != observation_values["task_id"]
                        or stored_observation["raw_ref"] != resolved_raw_ref
                        or stored_observation["content_hash"] != record_digest
                        or not isinstance(stored_provenance, Mapping)
                        or stored_provenance.get("capture_id") != capture_id
                    ):
                        raise EvidenceWriteError("observation address conflicts with existing immutable evidence")
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
            "raw_ref": resolved_raw_ref,
            "content_digest": capture_digest,
        }
