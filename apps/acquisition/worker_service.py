"""Production Kafka worker for policy-approved acquisition requests.

Run as a separate process from the control plane:
    python -m worker_service

The offset is committed only after the task has either emitted broker-acknowledged
evidence or durably routed a typed failure. Unexpected infrastructure errors stop
the process so a higher offset cannot commit past an unprocessed message.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
from typing import Any

from confluent_kafka import Consumer, KafkaError

from config.settings import get_settings
from dispatcher.kafka_producer import KafkaProducer, ensure_topics
from events import event_envelope_pb2 as pb
from events.content_router import ContentRouter
from events.observation_gate import ObservationGate
from events.topics import TOPICS, topic_for
from storage.s3 import ObjectStore
from sources.connector import SourceConnector
from worker_acquisition import AcquisitionWorker, kafka_failure_sink
from evidence_writer import PostgresAcquisitionEvidenceWriter

log = logging.getLogger("cognitive.acquisition.worker")


def _postgres_dsn() -> str:
    dsn = str(get_settings().postgres.dsn or "").strip()
    if not dsn:
        raise RuntimeError("PostgreSQL DSN is required by the acquisition worker")
    if "://" in dsn and "+" not in dsn.split("://", 1)[0]:
        dsn = dsn.replace("://", "+asyncpg://", 1)
    return dsn


def _consumer_config() -> dict[str, Any]:
    brokers = os.environ.get("COGNITIVE_KAFKA_BROKERS", "localhost:19092").strip()
    group_id = os.environ.get("COGNITIVE_ACQUISITION_GROUP", "cognitive-acquisition-http-v1").strip()
    if not brokers or not group_id:
        raise RuntimeError("COGNITIVE_KAFKA_BROKERS and COGNITIVE_ACQUISITION_GROUP must be non-empty")
    return {
        "bootstrap.servers": brokers,
        "group.id": group_id,
        "enable.auto.commit": False,
        "enable.auto.offset.store": False,
        "auto.offset.reset": os.environ.get("COGNITIVE_ACQUISITION_OFFSET_RESET", "earliest"),
        "allow.auto.create.topics": False,
        "partition.assignment.strategy": "cooperative-sticky",
    }


async def run_worker(*, consumer: Any | None = None, max_messages: int | None = None) -> int:
    """Consume the canonical acquisition.request topic until stopped.

    max_messages exists for operational smoke runs; it does not alter delivery semantics.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    settings = get_settings()
    engine = create_async_engine(_postgres_dsn(), pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    object_store = ObjectStore()
    producer = KafkaProducer()
    connector: SourceConnector | None = None
    kafka_consumer = consumer or Consumer(_consumer_config())
    handled = 0

    async def shutdown_requested() -> bool:
        return _STOP.is_set()

    try:
        # This verifies the canonical topic catalog before consuming. It never creates
        # per-source/per-donor topics; source identity travels in the envelope metadata.
        ensure_topics(TOPICS)
        gate = ObservationGate(
            store=object_store,
            router=ContentRouter(),
            producer=producer,
        )
        evidence_writer = PostgresAcquisitionEvidenceWriter(session_factory)

        def sink_factory(definition):
            return __import__(
                "artifact_sink", fromlist=["ArtifactSink"]
            ).ArtifactSink(
                gate=gate,
                store=object_store,
                source_family=definition.source_family,
                evidence_writer=evidence_writer,
            )

        connector = SourceConnector(
            gate=gate,
            artifact_sink_factory=sink_factory,
        )
        worker = AcquisitionWorker(
            connector=connector,
            sink=kafka_failure_sink(producer),
            # The gate publishes the one canonical protobuf event, after the DB transaction.
            # The worker validates its evidence refs but must not publish a second JSON event.
            publish=None,
            store=object_store,
        )
        topic = topic_for("acquisition.request")
        kafka_consumer.subscribe([topic])
        log.info("acquisition worker consuming topic=%s group=%s", topic, _consumer_config()["group.id"])

        while not _STOP.is_set():
            msg = kafka_consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                raise RuntimeError(f"Kafka consumer error: {msg.error()}")
            payload = msg.value()
            if not payload:
                # Malformed broker bytes are not consumed as a successful task. Fail the
                # process so the same partition position is replayed after operator action.
                raise RuntimeError("acquisition.request message has an empty value")
            envelope = pb.EventEnvelope()
            try:
                envelope.ParseFromString(payload)
            except Exception as exc:
                raise RuntimeError(f"acquisition.request is not a valid EventEnvelope: {exc}") from exc
            if envelope.event_type != "acquisition.request":
                raise RuntimeError(f"wrong event type on acquisition.request: {envelope.event_type!r}")

            # handle routes source-level failures synchronously to DLQ/quarantine, and
            # returns only when that routing has succeeded. Unexpected exceptions bubble up.
            result = await worker.handle(envelope)
            producer.flush()
            kafka_consumer.commit(message=msg, asynchronous=False)
            handled += 1
            log.info(
                "acquisition request handled task_id=%s source_id=%s observations=%s failures=%s",
                result.task_id,
                result.source_id,
                len(result.observations),
                len(result.failures),
            )
            if max_messages is not None and handled >= max_messages:
                break
        return 0
    finally:
        try:
            if connector is not None:
                await connector.aclose()
        finally:
            try:
                producer.flush(15.0)
            finally:
                kafka_consumer.close()
                await engine.dispose()


_STOP = asyncio.Event()


def _request_shutdown(*_args: object) -> None:
    _STOP.set()


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("COGNITIVE_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _request_shutdown)
    try:
        return asyncio.run(run_worker())
    except Exception:
        log.exception("acquisition worker stopped without advancing the failing offset")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
