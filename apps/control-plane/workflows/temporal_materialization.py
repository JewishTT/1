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
async def reconcile_and_publish(tenant_id: str, entity_id: str, source_record_ids: list[str], run_id: str, entity_identity: dict[str, str]) -> dict[str, Any]:
    import asyncio
    import os
    from acquisition.entity_search import build_entity_search_surface
    from domain.dynamics import StreamRecord
    from domain.temporal_materialization import materialize_history
    from network.commoncrawl import CommonCrawlClient
    from network.range_pull import HttpByteTransport, pull_warc_range
    from services.cc_temporality import run_cc_temporality

    records: list[StreamRecord] = []
    if source_record_ids:
        raise RuntimeError("source record resolution requires the durable entity_stream repository")
    surface = build_entity_search_surface(entity_id, {str(k): str(v) for k, v in entity_identity.items()})
    plan = surface.cc_plan
    if plan is None:
        raise ValueError("identity has no Common Crawl URL/domain/host/site/name")
    crawl = os.getenv("CC_CRAWL", "CC-MAIN-2025-30")
    client = CommonCrawlClient(timeout=90.0)
    partition_crawls = None if os.getenv("CC_HISTORICAL_PARTITIONS", "0") == "1" else [crawl]
    max_crawls = int(os.getenv("CC_MAX_CRAWLS", "3"))
    max_pages = int(os.getenv("CC_MAX_PAGES", "1"))
    try:
        hits = await client.discover_partitions(plan.url_query, crawls=partition_crawls, max_crawls=max_crawls, max_pages=max_pages, matchType=plan.match_type, filter="status:200", limit=1)
    except Exception:
        if plan.match_type != "domain" or plan.url_query.startswith(("http://", "https://")):
            # Preserve the hermetic activity seam while the live direct path
            # remains the production route.
            cc = await asyncio.to_thread(run_cc_temporality, entity_id, entity_identity, session=None)
            captures = list(cc.get("captures", []))
            if not captures:
                raise ValueError("Common Crawl index returned no captures")
            for capture in captures[:1]:
                records.append(StreamRecord(
                    entity_id=entity_id, tenant_id=tenant_id, kind="cc.capture",
                    ts=datetime.fromisoformat(capture["observed_at"]),
                    payload={"event_at": capture["observed_at"], "source": "common_crawl", "url": capture.get("url", ""), "digest": capture.get("digest", ""), "assertion_id": capture.get("record_id", ""), "admission": {"decision": "ACCEPT_NEW", "status": "ACCEPTED"}},
                    observation_id=capture.get("record_id", ""), sequence=1,
                ))
            hits = []
        else:
            try:
                hits = await client.discover_partitions(f"www.{plan.url_query}/", crawls=partition_crawls, max_crawls=max_crawls, max_pages=max_pages, matchType="prefix", filter="status:200", limit=1)
            except Exception:
                cc = await asyncio.to_thread(run_cc_temporality, entity_id, entity_identity, session=None)
                captures = list(cc.get("captures", []))
                if not captures:
                    raise
                capture = captures[0]
                records.append(StreamRecord(
                    entity_id=entity_id, tenant_id=tenant_id, kind="cc.capture",
                    ts=datetime.fromisoformat(capture["observed_at"]),
                    payload={"event_at": capture["observed_at"], "source": "common_crawl", "url": capture.get("url", ""), "digest": capture.get("digest", ""), "assertion_id": capture.get("record_id", ""), "admission": {"decision": "ACCEPT_NEW", "status": "ACCEPTED"}},
                    observation_id=capture.get("record_id", ""), sequence=1,
                ))
                hits = []
    if not records:
        if not hits:
            raise ValueError("Common Crawl index returned no captures")
        hit = hits[0]
        query = dict(part.split("=", 1) for part in str(hit["uri"]).partition("?")[2].split("&") if "=" in part)
        filename = str(hit["uri"]).partition("?")[0].removeprefix("s3://data.commoncrawl.org/")
        offset, length = int(query["offset"]), int(query["length"])
        warc = await pull_warc_range(HttpByteTransport(timeout=90.0), filename=filename, offset=offset, length=length)
        observed_at = str(hit.get("timestamp", ""))
        if len(observed_at) == 14 and observed_at.isdigit():
            observed_at = f"{observed_at[:4]}-{observed_at[4:6]}-{observed_at[6:8]}T{observed_at[8:10]}:{observed_at[10:12]}:{observed_at[12:]}Z"
        records.append(StreamRecord(
            entity_id=entity_id, tenant_id=tenant_id, kind="cc.capture",
            ts=datetime.fromisoformat(observed_at),
            payload={"event_at": observed_at, "source": "common_crawl", "url": str(hit.get("url", "")), "digest": str(hit.get("digest", "")), "content_sha256": str(hit.get("digest", "")), "locator": f"{filename}@{offset},{length}", "crawl": crawl, "warc_record_id": warc.warc_record_id or "", "assertion_id": "ASR-" + (warc.warc_record_id or filename)[-20:], "admission": {"decision": "ACCEPT_NEW", "status": "ACCEPTED", "confidence": 0.91, "policy": "cc-capture-v1"}, "interpretation": {"byte_length": len(warc.payload), "kind": "web_capture"}},
            observation_id="OBS-CC-" + (warc.warc_record_id or filename).replace("/", "-")[-24:], sequence=1,
        ))
    history = materialize_history(records, tenant_id=tenant_id, entity_id=entity_id)
    durable_sql = False
    if os.getenv("COGNITIVE_DURABLE_SQL", "0") == "1":
        from db.entity_stream import SqlEntityStreamRepository
        from db.session import create_tables, make_session_factory
        from db.temporal_materialization import SqlTemporalMaterializationRepository
        await create_tables()
        factory = make_session_factory()
        async with factory() as session:
            await SqlEntityStreamRepository(session).append_many(records)
            await SqlTemporalMaterializationRepository(session).publish(history, run_id=run_id)
        durable_sql = True
    from domain.graph_invariant import from_entity_stream
    invariant = from_entity_stream(records, tenant_id=tenant_id, type_label="Domain", revision=1)
    return {
        "run_id": run_id,
        "entity_id": entity_id,
        "publication": history.publication.to_dict(),
        "records": [record.to_dict() for record in records],
        "invariant": invariant.as_dict(),
        "durable_sql": durable_sql,
        "status": "READY",
    }


@workflow.defn
class TemporalEntityMaterializationWorkflow:
    @workflow.run
    async def run(self, request: MaterializationWorkflowInput) -> dict[str, Any]:
        if not request.tenant_id or not request.entity_id or not request.run_id:
            raise ValueError("tenant_id, entity_id, and run_id are required")
        workflow.logger.info("materialization.started")
        result = await workflow.execute_activity(
            "temporal_materialization.reconcile_and_publish",
            args=[request.tenant_id, request.entity_id, list(request.source_record_ids), request.run_id, request.entity_identity],
            task_queue=TASK_QUEUE, start_to_close_timeout=timedelta(minutes=30),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )
        workflow.logger.info("materialization.ready")
        return result


__all__ = ["TASK_QUEUE", "MaterializationWorkflowInput", "TemporalEntityMaterializationWorkflow", "reconcile_and_publish"]
