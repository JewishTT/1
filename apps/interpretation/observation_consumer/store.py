"""Durable idempotent persistence for observation processing results."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Mapping

from sqlalchemy.dialects.postgresql import insert as pg_insert

from db.schema import ProcessingResultRow


def _instant(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _payload(envelope: Any) -> dict[str, Any]:
    raw = bytes(getattr(envelope, "payload", b"") or b"")
    if not raw:
        return {}
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return {}
    return dict(result) if isinstance(result, Mapping) else {}


class ProcessingResultWriteError(RuntimeError):
    """A processing result was not durably committed."""


class PostgresProcessingResultWriter:
    """Upsert one result per tenant/observation/consumer version."""

    def __init__(self, session_factory: Any) -> None:
        if session_factory is None:
            raise ValueError("session_factory is required")
        self._session_factory = session_factory

    async def persist(self, envelope: Any, result: Any) -> str:
        tenant_id = str(getattr(envelope, "tenant_id", "") or "")
        observation_id = str(getattr(result, "observation_id", "") or "")
        consumer = str(getattr(result, "consumer", "") or "")
        consumer_version = str(getattr(result, "consumer_version", "") or "")
        if not all((tenant_id, observation_id, consumer, consumer_version)):
            raise ProcessingResultWriteError("processing result lacks tenant/observation/consumer identity")
        processing_result_id = "PR-" + hashlib.sha256(
            f"{tenant_id}|{observation_id}|{consumer}|{consumer_version}".encode()
        ).hexdigest()[:32]
        record_meta = _payload(envelope)
        values = {
            "processing_result_id": processing_result_id,
            "processing_run_id": str(getattr(result, "processing_run_id", "") or ""),
            "tenant_id": tenant_id,
            "investigation_id": str(getattr(envelope, "investigation_id", "") or "") or None,
            "observation_id": observation_id,
            "capture_id": str(record_meta.get("capture_id") or getattr(result, "capture_id", "") or ""),
            "raw_ref": str(record_meta.get("raw_ref") or ""),
            "consumer": consumer,
            "consumer_version": consumer_version,
            "processed_at": _instant(getattr(result, "processed_at")),
            "status": str(getattr(result, "status", "") or "refused"),
            "derived_ref": str(getattr(result, "derived_ref", "") or ""),
            "locator": str(getattr(result, "locator", "") or ""),
            "record_count": max(0, int(getattr(result, "record_count", 0) or 0)),
            "mention_count": max(0, int(getattr(result, "mention_count", 0) or 0)),
            "truncated": bool(getattr(result, "truncated", False)),
            "failure_code": str(getattr(result, "failure_code", "") or ""),
            "detail": str(getattr(result, "detail", "") or ""),
            "normalization": getattr(result, "normalization", None),
            "interpretation": getattr(result, "interpretation", None),
        }
        statement = pg_insert(ProcessingResultRow).values(**values)
        updates = {
            key: getattr(statement.excluded, key)
            for key in (
                "processing_run_id", "processed_at", "status", "derived_ref", "locator",
                "record_count", "mention_count", "truncated", "failure_code", "detail",
                "normalization", "interpretation", "raw_ref", "capture_id", "investigation_id",
            )
        }
        statement = statement.on_conflict_do_update(
            index_elements=[
                ProcessingResultRow.tenant_id,
                ProcessingResultRow.observation_id,
                ProcessingResultRow.consumer,
                ProcessingResultRow.consumer_version,
            ],
            set_=updates,
        )
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    await session.execute(statement)
        except Exception as exc:  # noqa: BLE001 - the Kafka offset must remain uncommitted
            raise ProcessingResultWriteError(
                f"processing result persistence failed: {type(exc).__name__}: {exc}"
            ) from exc
        return processing_result_id
