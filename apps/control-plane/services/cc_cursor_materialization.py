"""Checkpointed Common Crawl materialization for the Temporal worker."""
from __future__ import annotations

import os
from dataclasses import replace
from datetime import datetime
from typing import Any


async def run_cursor_materialization(*, tenant_id: str, entity_id: str, run_id: str, surface: Any) -> dict[str, Any]:
    """Process bounded crawl pages and resume from per-page durable cursors."""
    from domain.dynamics import StreamAppendRejected, StreamRecord
    from domain.graph_invariant import from_entity_stream
    from domain.temporal_materialization import materialize_history
    from domain.temporal_worldline import build_worldline
    from network.commoncrawl import CommonCrawlClient, crawl_badge
    from network.range_pull import HttpByteTransport, pull_warc_range

    # Deferred with the rest: importing the reducer at module scope would make this
    # module depend on the context engine's package layout, and this module is
    # loaded by the Temporal worker in deployments that never construct a loop.
    from context_engine.invariant_reducer import InvariantReducer
    from db.entity_stream import SqlEntityStreamRepository
    from db.materialization_cursor import SqlMaterializationCursorRepository
    from db.session import create_tables, make_session_factory
    from db.temporal_materialization import SqlTemporalMaterializationRepository
    from services.capture_interpretation import interpret_warc_capture

    plan = surface.cc_plan
    if plan is None:
        raise ValueError("identity has no Common Crawl URL/domain/host/site/name")
    default_crawl = os.getenv("CC_CRAWL", "CC-MAIN-2025-30")
    client = CommonCrawlClient(timeout=90.0)
    available = await client.list_indexes() if os.getenv("CC_HISTORICAL_PARTITIONS", "0") == "1" else [default_crawl]
    if os.getenv("CC_HISTORICAL_PARTITIONS", "0") == "1":
        # Pin the configured known-good crawl first; CC may advertise a
        # future index whose CDN shard is not ready yet (504).
        available = [default_crawl, *available]
    partitions = list(dict.fromkeys(str(x).strip() for x in available if str(x).strip()))
    if os.getenv("CC_HISTORICAL_PARTITIONS", "0") == "1":
        partitions = sorted(partitions, key=lambda x: (x != default_crawl, crawl_badge(x) or ("", 0, 0), x))
    partitions = partitions[:max(1, int(os.getenv("CC_MAX_CRAWLS", "3")))]
    if not partitions:
        raise ValueError("Common Crawl returned no crawl partitions")
    await create_tables()
    factory = make_session_factory()
    async with factory() as session:
        streams = SqlEntityStreamRepository(session)
        cursors = SqlMaterializationCursorRepository(session)
        for partition in partitions:
            for page in range(max(1, int(os.getenv("CC_MAX_PAGES", "1")))):
                row = await cursors.ensure(tenant_id=tenant_id, entity_id=entity_id, run_id=run_id, crawl=partition, page=page)
                if row.status == "COMPLETED":
                    continue
                if row.status == "PROCESSING" and isinstance(row.result_payload, dict) and isinstance(row.result_payload.get("records"), list):
                    for item in row.result_payload["records"]:
                        record = StreamRecord.from_dict(item)
                        if record.record_hash != record.compute_hash():
                            record = replace(record, record_hash="", record_id="")
                        try:
                            await streams.append(record)
                        except StreamAppendRejected:
                            current = await streams.replay(tenant_id=tenant_id, entity_id=entity_id)
                            await streams.append(replace(record, sequence=max((x.sequence for x in current), default=0) + 1, record_hash="", record_id=""))
                    await cursors.complete(row, result_payload=row.result_payload)
                    await session.commit()
                    continue
                try:
                    hits = await client.discover(plan.url_query, crawl=partition, page=page, limit=max(1, int(os.getenv("CC_PAGE_LIMIT", "50"))), matchType=plan.match_type, filter="status:200")
                except Exception as exc:  # noqa: BLE001 - one unavailable epoch must not abort the backfill
                    await cursors.fail(row, repr(exc))
                    await session.commit()
                    continue
                if not hits:
                    await cursors.complete(row, result_payload={"record": None})
                    await session.commit()
                    continue
                records: list[StreamRecord] = []
                for hit in hits:
                    query = dict(part.split("=", 1) for part in str(hit["uri"]).partition("?")[2].split("&") if "=" in part)
                    filename = str(hit["uri"]).partition("?")[0].removeprefix("s3://data.commoncrawl.org/")
                    offset, length = int(query["offset"]), int(query["length"])
                    locator = f"{filename}@{offset},{length}"
                    existing = await streams.replay(tenant_id=tenant_id, entity_id=entity_id)
                    if any(item.payload.get("locator") == locator for item in existing):
                        continue
                    warc = await pull_warc_range(HttpByteTransport(timeout=90.0), filename=filename, offset=offset, length=length)
                    observed_at = str(hit.get("timestamp", ""))
                    if len(observed_at) == 14 and observed_at.isdigit():
                        observed_at = f"{observed_at[:4]}-{observed_at[4:6]}-{observed_at[6:8]}T{observed_at[8:10]}:{observed_at[10:12]}:{observed_at[12:]}Z"
                    capture = interpret_warc_capture(entity_id=entity_id, tenant_id=tenant_id, warc=warc, url=str(hit.get("url", "")), observed_at=observed_at, observation_id="OBS-CC-" + (warc.warc_record_id or filename).replace("/", "-")[-24:], crawl=partition, page=page, locator=locator)
                    records.append(StreamRecord(entity_id=entity_id, tenant_id=tenant_id, kind="cc.capture", ts=datetime.fromisoformat(observed_at), sequence=max((x.sequence for x in existing), default=0) + len(records) + 1, payload=capture, observation_id=capture["observation_id"]))
                if not records:
                    await cursors.complete(row, result_payload={"records": [], "capture_count": 0})
                    await session.commit()
                    continue
                await cursors.prepare(row, result_payload={"records": [r.to_dict() for r in records], "capture_count": len(records)})
                await session.commit()
                stored = await streams.append_many(records)
                await cursors.complete(row, result_payload={"records": [r.to_dict() for r in stored], "capture_count": len(stored)})
                await session.commit()
        records = await streams.replay(tenant_id=tenant_id, entity_id=entity_id)
        if not records:
            counts = await cursors.counts(tenant_id=tenant_id, entity_id=entity_id, run_id=run_id)
            raise RuntimeError(f"Common Crawl partitions produced no captures: {counts}")
        publication_repo = SqlTemporalMaterializationRepository(session)
        previous = await publication_repo.current(tenant_id=tenant_id, entity_id=entity_id)

        # **WP-D T060: the revision is gated on the accumulated stream, not on the
        # sweep having run.**
        #
        # This line used to read
        #
        #     generation = int((previous or {}).get("projection_generation", 0)) + 1
        #
        # which mints a new revision on every run whether or not anything changed.
        # A re-run over an unchanged stream is not new knowledge, and publishing a
        # new generation for it makes every consumer's history longer than the
        # evidence justifies and makes "did anything move?" unanswerable by
        # inspecting revisions.
        #
        # The comparison is over a digest of the whole accumulated stream, so the
        # question asked is the right one: *does the knowledge state differ from what
        # we last published?* Not *did this function get called again?*
        #
        # `InvariantReducer` already implements exactly this discipline and has 33
        # tests; it had no caller. It is used here for its fold and its
        # revision numbering, which are the same shape `from_entity_stream` produces
        # so the digest below is comparable to the one that was published.
        reducer = InvariantReducer(tenant_id=tenant_id, type_label="Domain")
        reduced = reducer.reduce(records)
        state_digest = reduced.invariant.integrity_digest
        previous_digest = str((previous or {}).get("state_digest", "") or "")

        if previous is not None and previous_digest and previous_digest == state_digest:
            # Nothing moved. Republish nothing, renumber nothing, and say so.
            generation = int((previous or {}).get("projection_generation", 0))
        else:
            generation = int((previous or {}).get("projection_generation", 0)) + 1

        history = materialize_history(
            records, tenant_id=tenant_id, entity_id=entity_id, projection_generation=generation
        )
        if previous is None or not previous_digest or previous_digest != state_digest:
            await publication_repo.publish(history, run_id=run_id)
        persisted = await publication_repo.current(tenant_id=tenant_id, entity_id=entity_id)
        published_payload = persisted or history.publication.to_dict()
        # The digest travels with the publication so the next sweep can answer
        # "did anything move?" without re-deriving it. Without this the gate could
        # only ever fire on its first comparison.
        if published_payload is not None:
            published_payload["state_digest"] = state_digest
        invariant = from_entity_stream(
            records, tenant_id=tenant_id, type_label="Domain", revision=generation
        )
        worldline = build_worldline(
            records, tenant_id=tenant_id, entity_id=entity_id,
            require_evidence=False, projection_generation=generation,
        )
        return {"run_id": run_id, "entity_id": entity_id, "publication": published_payload, "worldline": worldline.to_dict(), "records": [x.to_dict() for x in records], "invariant": invariant.as_dict(), "durable_sql": True, "cursors": await cursors.counts(tenant_id=tenant_id, entity_id=entity_id, run_id=run_id), "status": "READY"}


__all__ = ["run_cursor_materialization"]
