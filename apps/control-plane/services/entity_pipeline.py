"""Development-safe entity pipeline runner for the live vertical slice."""
from __future__ import annotations

import hashlib
import html
import os
import re
from datetime import datetime
from typing import Any

from acquisition.entity_search import build_entity_search_surface
from domain.dynamics import StreamRecord
from network.commoncrawl import CommonCrawlClient
from network.range_pull import HttpByteTransport, pull_warc_range
from services.catalog import Catalog
from services.temporal_materialization_service import temporal_materialization_service

_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)

def _digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()

def _iso_cc(value: str) -> str:
    if len(value) == 14 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}T{value[8:10]}:{value[10:12]}:{value[12:]}Z"
    return value or "1970-01-01T00:00:00Z"

def _interpret_and_admit(url: str, body: bytes, observation_id: str) -> dict[str, Any]:
    text = body.decode("utf-8", errors="replace")
    match = _TITLE_RE.search(text)
    title = html.unescape(re.sub(r"\s+", " ", match.group(1)).strip()) if match else ""
    return {"status": "ACCEPTED", "decision": "ACCEPT_NEW", "reason_codes": ["cc_index_hit", "http_200", "warc_provenance_present"], "interpretation": {"title": title, "emails": sorted(set(_EMAIL_RE.findall(text)))[:20], "byte_length": len(body)}, "admission": {"confidence": 0.91, "policy": "cc-capture-v1"}, "content_hash": _digest(body), "observation_id": observation_id}

async def run_live_entity_pipeline(*, tenant_id: str, entity_id: str, identity: dict[str, Any], source_records: list[dict[str, Any]], catalog: Catalog, operations: Any) -> None:
    runs = [item for item in operations.health(tenant_id=tenant_id) if item["entity_id"] == entity_id]
    run_id = str(runs[-1]["run_id"]) if runs else f"run-local-{entity_id}"
    operations.mark(run_id, "RUNNING")
    try:
        records = [StreamRecord.from_dict(item) for item in source_records]
        if not records:
            plan = build_cc_plan(entity_id, {str(k): str(v) for k, v in identity.items()})
            if plan is None:
                raise ValueError("identity has no Common Crawl URL/domain/host/site/name")
            crawl = os.getenv("CC_CRAWL", "CC-MAIN-2025-30")
            client = CommonCrawlClient(timeout=90.0)
            try:
                hits = await client.discover(plan.url_query, crawl=crawl, page=0, matchType=plan.match_type, filter="status:200", limit=1)
            except Exception:
                if plan.match_type != "domain" or plan.url_query.startswith(("http://", "https://")):
                    raise
                hits = await client.discover(f"www.{plan.url_query}/", crawl=crawl, page=0, matchType="prefix", filter="status:200", limit=1)
            if not hits:
                raise ValueError("Common Crawl index returned no captures")
            transport = HttpByteTransport(timeout=90.0)
            records = []
            for sequence, hit in enumerate(hits[:20], 1):
                locator = str(hit["uri"]).removeprefix("s3://data.commoncrawl.org/")
                filename, _, query_text = locator.partition("?")
                query = dict(part.split("=", 1) for part in query_text.split("&") if "=" in part)
                offset, length = int(query["offset"]), int(query["length"])
                warc = await pull_warc_range(transport, filename=filename, offset=offset, length=length)
                body = warc.payload.split(b"\r\n\r\n", 1)[-1]
                observed_at = _iso_cc(str(hit.get("timestamp", "")))
                observation_id = "OBS-CC-" + hashlib.sha256(f"{entity_id}:{filename}:{offset}:{length}".encode()).hexdigest()[:20]
                result = _interpret_and_admit(str(hit["url"]), body, observation_id)
                catalog.append_observation(entity_id, {"observation_id": observation_id, "uri": str(hit["url"]), "content_hash": result["content_hash"], "observed_at": observed_at, "provenance": {"source": "common_crawl", "crawl": crawl, "warc_filename": filename, "offset": offset, "length": length, "warc_record_id": warc.warc_record_id}, "interpretation": result["interpretation"], "admission": result["admission"]})
                records.append(StreamRecord(entity_id=entity_id, tenant_id=tenant_id, kind="cc.capture", ts=datetime.fromisoformat(observed_at), payload={"event_at": observed_at, "url": str(hit["url"]), "observation_id": observation_id, "source": "common_crawl", "locator": f"{filename}@{offset},{length}", "admission": result["admission"]}, observation_id=observation_id, sequence=sequence))
        if not records:
            raise ValueError("pipeline produced no accepted records")
        # Keep the accepted stream available to the API/UI projection.  The
        # production worker writes these rows transactionally to PostgreSQL.
        from api.routes.entities import _entity_streams
        _entity_streams[(tenant_id, entity_id)] = list(records)
        result = temporal_materialization_service.materialize(records, tenant_id=tenant_id, entity_id=entity_id)
        operations.mark(run_id, "READY")
        operations.mark(run_id, "PUBLISHED")
        from api.sse import hub
        hub.publish("temporal.materialization.ready", {"run_id": run_id, "entity_id": entity_id, "status": "PUBLISHED", "publication_id": result.history.publication.publication_id})
    except Exception as exc:
        operations.mark(run_id, "FAILED", reason=str(exc))
        from api.sse import hub
        hub.publish("temporal.materialization.failed", {"run_id": run_id, "entity_id": entity_id, "status": "FAILED", "reason": str(exc)})

__all__ = ["run_live_entity_pipeline"]
