"""Temporal workflow for deterministic entity materialization (feature 014)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

TASK_QUEUE = "cognitive-temporal-materialization"


@dataclass(frozen=True)
class MaterializationWorkflowInput:
    tenant_id: str
    entity_id: str
    source_record_ids: tuple[str, ...]
    run_id: str
    mode: str = "rebuild"
    entity_identity: dict[str, str] = field(default_factory=dict)


@activity.defn(name="temporal_materialization.reconcile_and_publish")
async def reconcile_and_publish(
    tenant_id: str,
    entity_id: str,
    source_record_ids: list[str],
    run_id: str,
    entity_identity: dict[str, str],
) -> dict[str, Any]:
    """Activity boundary: discover records, fold them, and return publication.

    The activity is intentionally side-effect explicit. The production worker
    should replace the in-process operation with the PostgreSQL repository and
    Kafka/Observation Gate adapters; keeping that boundary here prevents the
    API process from becoming the orchestration authority.
    """
    import asyncio

    from domain.dynamics import StreamRecord
    from domain.temporal_materialization import materialize_history
    from network.range_pull import HttpByteTransport, pull_warc_range

    from services.cc_temporality import run_cc_temporality

    records: list[StreamRecord] = []
    if source_record_ids:
        # A production worker must resolve ids from the durable entity_stream;
        # silently treating ids as payloads would be incorrect.
        raise RuntimeError(
            "source record resolution requires the durable entity_stream repository"
        )
    else:
        cc = await asyncio.to_thread(
            run_cc_temporality, entity_id, entity_identity, session=None
        )
        transport = HttpByteTransport()
        for index, capture in enumerate(cc.get("captures", []), 1):
            filename = capture.get("warc_filename", "")
            offset = int(capture.get("offset", 0) or 0)
            length = int(capture.get("length", 0) or 0)
            if filename and offset >= 0 and length > 0:
                warc = await pull_warc_range(
                    transport,
                    filename=filename,
                    offset=offset,
                    length=length,
                )
                capture["warc_record_id"] = warc.warc_record_id or capture.get(
                    "warc_record_id", ""
                )
            records.append(
                StreamRecord(
                    entity_id=entity_id,
                    tenant_id=tenant_id,
                    kind="cc.capture",
                    ts=datetime.fromisoformat(capture["observed_at"]),
                    payload={
                        "event_at": capture["observed_at"],
                        "source": "common_crawl",
                        "url": capture["url"],
                        "digest": capture.get("digest", ""),
                        "locator": capture.get("locator", ""),
                        "crawl": capture.get("crawl", ""),
                        "subset": capture.get("subset", ""),
                    },
                    observation_id=capture.get("record_id", ""),
                    sequence=index,
                )
            )
    if not records:
        raise ValueError("no accepted source records or CC captures for materialization")
    history = materialize_history(records, tenant_id=tenant_id, entity_id=entity_id)
    return {
        "run_id": run_id,
        "entity_id": entity_id,
        "publication": history.publication.to_dict(),
        "status": "READY",
    }


@workflow.defn
class TemporalEntityMaterializationWorkflow:
    """Thin durable orchestration around deterministic materialization activities."""

    @workflow.run
    async def run(self, request: MaterializationWorkflowInput) -> dict[str, Any]:
        if not request.tenant_id or not request.entity_id or not request.run_id:
            raise ValueError("tenant_id, entity_id, and run_id are required")
        workflow.record_marker(
            "materialization.started",
            {
                "tenant_id": request.tenant_id,
                "entity_id": request.entity_id,
                "run_id": request.run_id,
                "source_record_ids": list(request.source_record_ids),
            },
        )
        result = await workflow.execute_activity(
            "temporal_materialization.reconcile_and_publish",
            args=[
                request.tenant_id,
                request.entity_id,
                list(request.source_record_ids),
                request.run_id,
                request.entity_identity,
            ],
            task_queue=TASK_QUEUE,
            start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        workflow.record_marker("materialization.ready", result)
        return result


__all__ = [
    "TASK_QUEUE",
    "MaterializationWorkflowInput",
    "TemporalEntityMaterializationWorkflow",
    "reconcile_and_publish",
]
