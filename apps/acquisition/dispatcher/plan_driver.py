"""Drive the real Dispatcher with a `plan()` result (W1).

The dispatcher already exists and already knows how to score a task, match a
capability and emit `acquisition.request`. What was missing is the thing that
*feeds* it: a function that takes the connector's plan and turns each task into
a real, acknowledged publication. Without this the backbone has a contract and
no traffic.

Three properties this module is responsible for:

The dispatcher is used, not reimplemented
    Every task goes through :meth:`dispatcher.scheduler.Dispatcher.schedule` and
    :meth:`~dispatcher.scheduler.Dispatcher.emit_request`. The verdict that
    decides whether a request is published at all comes from the scheduler's own
    two stages, so this module cannot drift into a second opinion about what
    should run.

Publication is acknowledged, not assumed
    ``emit_request`` calls the producer's async ``produce``. This module flushes
    and reads the delivery report, so :class:`DispatchRecord` carries the
    partition and offset the broker actually assigned. A plan that produced
    nothing is visible as a deferral with a reason, not as a success.

The envelope the scheduler emits is the envelope that goes on the wire
    :func:`assert_request_contract` pins the fields a worker is entitled to rely
    on. It is checked here rather than only in tests because the contract is a
    promise to the consumer, and a producer that breaks it silently is worse
    than one that refuses to start.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from sources.connector import AcquisitionTask

from dispatcher.kafka_producer import DeliveryResult, KafkaProducer
from dispatcher.scheduler import Dispatcher, ScheduleDecision, Verdict, host_of

#: The scheduler emits these; a worker that reads anything else is reading a
#: promise this module does not keep. Pinned as a tuple so the order is stable.
REQUEST_CONTRACT_FIELDS: tuple[str, ...] = (
    "event_id",
    "event_type",
    "event_version",
    "tenant_id",
    "investigation_id",
    "source_id",
    "work_id",
    "region_id",
    "payload",
    "produced_at",
)

REQUEST_EVENT_TYPE = "acquisition.request"
REQUEST_EVENT_VERSION = "2.0"
REQUEST_PRODUCER = "acquisition-plan-driver"


class ContractViolation(RuntimeError):
    """The scheduler emitted an envelope the worker contract does not describe."""


@dataclass(frozen=True)
class DispatchRecord:
    """What happened to one task, and where the broker put it."""

    task_id: str
    source_id: str
    query: str
    verdict: str
    reason: str
    published: bool
    topic: str = ""
    partition: int = -1
    offset: int = -1
    key: str = ""
    utility: float = 0.0
    execution_class: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "source_id": self.source_id,
            "query": self.query,
            "verdict": self.verdict,
            "reason": self.reason,
            "published": self.published,
            "topic": self.topic,
            "partition": self.partition,
            "offset": self.offset,
            "key": self.key,
            "utility": self.utility,
            "execution_class": self.execution_class,
        }


def task_mapping(
    task: AcquisitionTask,
    *,
    uri: str = "",
    context_score_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The task dict the scheduler already accepts.

    ``AcquisitionTask.to_task`` is the canonical mapping; this adds only what the
    scheduler reads and the connector cannot know — the host key used for
    concurrency limits, and whatever the caller wants scored. Sorted so the
    mapping is a pure function of its inputs (Invariant 12).
    """
    mapping = dict(task.to_task())
    if uri:
        mapping["uri"] = uri
        mapping["host_key"] = host_of(uri)
    for key, value in (context_score_fields or {}).items():
        mapping[key] = value
    return {key: mapping[key] for key in sorted(mapping)}


def assert_request_contract(envelope: Any) -> None:
    """Refuse to publish a request whose envelope the worker cannot read.

    Checks the fields a consumer depends on rather than the whole protobuf
    surface: a future envelope field is additive and fine, a missing one is a
    silent loss of routing data.
    """
    if envelope is None:
        raise ContractViolation("scheduler produced no envelope for a dispatched task")
    if getattr(envelope, "event_type", "") != REQUEST_EVENT_TYPE:
        raise ContractViolation(
            f"expected {REQUEST_EVENT_TYPE}, got {getattr(envelope, 'event_type', '')!r}"
        )
    if getattr(envelope, "event_version", "") != REQUEST_EVENT_VERSION:
        raise ContractViolation(
            f"expected event_version {REQUEST_EVENT_VERSION}, "
            f"got {getattr(envelope, 'event_version', '')!r}"
        )
    if not getattr(envelope, "source_id", ""):
        raise ContractViolation("request envelope carries no source_id for the worker to resolve")
    if not getattr(envelope, "tenant_id", ""):
        raise ContractViolation("request envelope carries no tenant_id")
    missing = [f for f in REQUEST_CONTRACT_FIELDS if not hasattr(envelope, f)]
    if missing:
        raise ContractViolation(f"request envelope is missing fields: {sorted(missing)}")


def request_key(task: AcquisitionTask) -> str:
    """Partition key for the request. Per-task ordering depends on this."""
    return task.task_id


class PlanDispatcher:
    """Turn a plan into acknowledged `acquisition.request` publications."""

    def __init__(
        self,
        *,
        dispatcher: Dispatcher | None = None,
        producer: KafkaProducer | None = None,
        flush_timeout: float = 15.0,
    ) -> None:
        self.dispatcher = dispatcher or Dispatcher()
        self.producer = producer if producer is not None else KafkaProducer()
        self.flush_timeout = flush_timeout

    def dispatch(
        self,
        tasks: Iterable[AcquisitionTask],
        *,
        context: dict[str, Any] | None = None,
        context_score_fields: dict[str, Any] | None = None,
        uris: dict[str, str] | None = None,
    ) -> tuple[DispatchRecord, ...]:
        """Schedule and publish every task. Deterministic order in, records out."""
        records: list[DispatchRecord] = []
        for task in tasks:
            records.append(
                self.dispatch_one(
                    task,
                    context=context,
                    context_score_fields=context_score_fields,
                    uri=(uris or {}).get(task.source_id, ""),
                )
            )
        return tuple(records)

    def dispatch_one(
        self,
        task: AcquisitionTask,
        *,
        context: dict[str, Any] | None = None,
        context_score_fields: dict[str, Any] | None = None,
        uri: str = "",
    ) -> DispatchRecord:
        """One task through the real scheduler, with the acknowledgement recorded."""
        mapping = task_mapping(task, uri=uri, context_score_fields=context_score_fields)
        decision: ScheduleDecision = self.dispatcher.schedule(mapping, context)

        if decision.verdict is not Verdict.DISPATCH:
            # A defer or a reject is a decision, not a publication. Recording it
            # with the scheduler's own reason is what makes "nothing was
            # scheduled" a reportable fact.
            return DispatchRecord(
                task_id=task.task_id,
                source_id=task.source_id,
                query=task.query,
                verdict=decision.verdict.value,
                reason=decision.reason,
                published=False,
                utility=decision.utility,
                execution_class=decision.execution_class or "",
            )

        self.dispatcher.emit_request(mapping, decision)
        acked = self._await_acknowledgement()

        if acked is None:
            return DispatchRecord(
                task_id=task.task_id,
                source_id=task.source_id,
                query=task.query,
                verdict=decision.verdict.value,
                reason="dispatched but the broker acknowledged nothing",
                published=False,
                utility=decision.utility,
                execution_class=decision.execution_class or "",
            )

        return DispatchRecord(
            task_id=task.task_id,
            source_id=task.source_id,
            query=task.query,
            verdict=decision.verdict.value,
            reason=decision.reason,
            published=True,
            topic=acked.topic,
            partition=acked.partition,
            offset=acked.offset,
            key=acked.key,
            utility=decision.utility,
            execution_class=decision.execution_class or "",
        )

    def _await_acknowledgement(self) -> DeliveryResult | None:
        """Block until the broker reports, then return *this* task's delivery.

        ``emit_request`` is the async surface, so the acknowledgement arrives in
        a delivery callback rather than a return value. ``flush`` clears the
        acknowledgement list before draining the client, so whatever is drained
        afterwards belongs to the task just published — a task can never be
        credited with another task's offset.
        """
        self.producer.flush(self.flush_timeout)
        fresh = self.producer.drain()
        if not fresh:
            return None
        return fresh[0]


@dataclass
class PlanDriver:
    """`plan()` in, acknowledged requests out — the W1 entry point.

    Holds the capability registration the scheduler needs. The scheduler
    resolves a task against `adapters.registry.REGISTRY`, and that registry is
    empty in a fresh process: without an http registration every task defers
    with a capability gap and nothing is ever published. Registering the
    connector's own execution surface here is what makes the plan actionable,
    and it is idempotent so a second call cannot widen the capability surface.
    """

    producer: KafkaProducer | None = None
    dispatcher: Dispatcher | None = None
    context: dict[str, Any] = field(default_factory=dict)
    _registered: bool = False

    def __post_init__(self) -> None:
        self.ensure_capability()
        self.dispatcher = self.dispatcher or Dispatcher(producer=self.producer)
        self.producer = self.producer or KafkaProducer()

    def ensure_capability(self) -> None:
        """Register the http execution surface the connector actually uses."""
        if self._registered:
            return
        from adapters.registry import REGISTRY, register

        if not any(
            "http" in registration.capabilities for registration in REGISTRY
        ):
            register("catalogue-http", execution_class="http", capabilities={"http"})
        self._registered = True

    def run(
        self,
        query: str,
        *,
        categories: Sequence[str] | None = None,
        tenant_id: str = "default-tenant",
        investigation_id: str = "",
        uris: dict[str, str] | None = None,
    ) -> tuple[DispatchRecord, ...]:
        """Plan ``query`` and publish a request for every task that dispatches."""
        from sources.connector import plan

        tasks = plan(
            query,
            tenant_id=tenant_id,
            investigation_id=investigation_id,
            categories=categories,
        )
        driver = PlanDispatcher(
            dispatcher=self.dispatcher,
            producer=self.producer,
        )
        return driver.dispatch(tasks, context=self.context, uris=uris or {})
