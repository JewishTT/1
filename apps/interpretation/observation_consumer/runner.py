"""Durable consumer for observation.created events.

The input Kafka offset is committed only after parser output has an immutable derived
object and ProcessingResult is transactionally upserted in PostgreSQL. Entity/relation
persistence is performed by the existing InterpretationBridge over those same raw bytes.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
from typing import Any

from confluent_kafka import Consumer, KafkaError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config.settings import get_settings
from events import event_envelope_pb2 as pb
from events.topics import topic_for
from storage.s3 import ObjectStore

from observation_consumer import ObservationConsumer
from observation_consumer.store import PostgresProcessingResultWriter

log = logging.getLogger("cognitive.interpretation.observation-consumer")
_STOP: asyncio.Event | None = None


def _postgres_dsn() -> str:
    dsn = str(get_settings().postgres.dsn or "").strip()
    if not dsn:
        raise RuntimeError("PostgreSQL DSN is required by the observation consumer")
    if "://" in dsn and "+" not in dsn.split("://", 1)[0]:
        dsn = dsn.replace("://", "+asyncpg://", 1)
    return dsn


def _consumer_config() -> dict[str, Any]:
    brokers = os.environ.get("COGNITIVE_KAFKA_BROKERS", "localhost:19092").strip()
    group_id = os.environ.get(
        "COGNITIVE_INTERPRETATION_GROUP", "cognitive-observation-consumer-v1"
    ).strip()
    if not brokers or not group_id:
        raise RuntimeError("Kafka broker and consumer group settings must be non-empty")
    return {
        "bootstrap.servers": brokers,
        "group.id": group_id,
        "enable.auto.commit": False,
        "enable.auto.offset.store": False,
        "auto.offset.reset": os.environ.get("COGNITIVE_INTERPRETATION_OFFSET_RESET", "earliest"),
        "allow.auto.create.topics": False,
        "partition.assignment.strategy": "cooperative-sticky",
    }


async def run_consumer(*, consumer: Any | None = None, max_messages: int | None = None) -> int:
    engine = create_async_engine(_postgres_dsn(), pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    object_store = ObjectStore()
    kafka_consumer = consumer or Consumer(_consumer_config())
    processed = 0

    def bridge_factory(*, envelope: Any, record_metadata: dict[str, Any]):
        from services.interpretation_bridge import EntityStore, InterpretationBridge

        metadata = record_metadata.get("record_metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        runtime_metadata = metadata.get("runtime_metadata")
        if not isinstance(runtime_metadata, dict):
            runtime_metadata = {}
        source_family = str(
            runtime_metadata.get("source_family")
            or record_metadata.get("source_family")
            or envelope.source_id
            or ""
        )
        return InterpretationBridge(
            EntityStore(
                session_factory=session_factory,
                tenant_id=str(envelope.tenant_id or ""),
            ),
            source_family=source_family,
            scope_id=str(envelope.investigation_id or "default"),
        )

    processor = ObservationConsumer(
        store=object_store,
        result_writer=PostgresProcessingResultWriter(session_factory),
        interpretation_bridge_factory=bridge_factory,
    )
    topic = topic_for("observation.created")
    try:
        kafka_consumer.subscribe([topic])
        log.info(
            "observation consumer started topic=%s group=%s",
            topic,
            _consumer_config()["group.id"],
        )
        while _STOP is None or not _STOP.is_set():
            message = kafka_consumer.poll(1.0)
            if message is None:
                continue
            if message.error():
                if message.error().code() == KafkaError._PARTITION_EOF:
                    continue
                raise RuntimeError(f"Kafka consumer error: {message.error()}")
            payload = message.value()
            if not payload:
                raise RuntimeError("observation event has an empty broker value")
            envelope = pb.EventEnvelope()
            try:
                envelope.ParseFromString(payload)
            except Exception as exc:
                raise RuntimeError(f"observation event is not a valid EventEnvelope: {exc}") from exc
            if not envelope.event_type.startswith("observation."):
                raise RuntimeError(f"unexpected event type on observation topic: {envelope.event_type!r}")

            result = await processor.handle(envelope)
            # handle() returns only after PostgresProcessingResultWriter committed.
            # If that write fails it raises and the offset is left uncommitted.
            kafka_consumer.commit(message=message, asynchronous=False)
            processed += 1
            log.info(
                "observation processed id=%s status=%s records=%d mentions=%d derived_ref=%s",
                result.observation_id,
                result.status,
                result.record_count,
                result.mention_count,
                result.derived_ref,
            )
            if max_messages is not None and processed >= max_messages:
                break
        return 0
    finally:
        kafka_consumer.close()
        await engine.dispose()


def _request_shutdown(*_args: object) -> None:
    if _STOP is not None:
        _STOP.set()


def main() -> int:
    global _STOP
    import asyncio

    logging.basicConfig(
        level=os.environ.get("COGNITIVE_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    _STOP = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _request_shutdown)
    try:
        return asyncio.run(run_consumer())
    except Exception:
        log.exception("observation consumer stopped without advancing the failing offset")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
