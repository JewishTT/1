"""Shared ingestion helper for engine adapters (T096/T098/T099/T100).

Every engine adapter converges on the single Observation Gate exactly like the
Wave 3 adapters: bytes + metadata only, no storage/event writes outside the
gate call (Observation boundary, adapters/README).
"""

from __future__ import annotations

from .warc.collect import WarcRecord


async def ingest_warc_records(
    task: dict,
    records: list[WarcRecord],
    *,
    collector: str,
    source_kind: str,
) -> list[dict]:
    """Push ``WarcRecord``-shaped payloads through the gate; returns outcomes."""
    gate = task.get("observation_gate")
    if gate is None:
        raise ValueError("task requires 'observation_gate' (Observation boundary)")
    observations = []
    for rec in records:
        obs = await gate.ingest(
            body=rec.payload,
            uri=rec.url,
            tenant_id=task.get("tenant_id", "tenant-demo"),
            investigation_id=task.get("investigation_id"),
            source_id=task.get("source_id"),
            work_id=task.get("work_id"),
            region_id=task.get("region_id"),
            content_type=rec.content_type or "application/octet-stream",
            collector=collector,
            collector_version="2.1.0",
            source_kind=source_kind,
        )
        observations.append(
            {
                "uri": rec.url,
                "observation_id": obs["observation_id"],
                "status": obs["status"],
                "raw_ref": obs["raw_ref"],
            }
        )
    return observations


def fetch_record(
    url: str, content_type: str | None, payload: bytes, warc_date: str | None = None
) -> WarcRecord:
    """Build a WarcRecord-morphic fetch from an engine's raw output."""
    return WarcRecord(
        url=url,
        warc_date=warc_date,
        content_type=(content_type or "").split(";")[0].strip() or None,
        payload=payload,
        digest=None,
    )