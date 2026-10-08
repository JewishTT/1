"""The acquisition worker: `acquisition.request` → fetch → `observation.created` (W2/W3).

This is the half of the loop that did not exist. The dispatcher could emit a
request and the connector could execute a definition, but nothing consumed a
request: the backbone had two ends and no wire between them.

One rule governs the shape of what comes out: **this module does not build an
observation.** It calls :meth:`sources.connector.SourceConnector.collect` and
publishes the event that method yields. The alternative — assembling an
observation envelope here — produces two producers of `observation.created` that
agree until the first field is added to one of them, and the pipeline then rots
in the way that is hardest to detect, because both shapes still parse.

The failure taxonomy (W3)
-------------------------
The interesting boundary is not "did the fetch work" but *who decided it did not*:

A 4xx is an answer
    A source returning 404 has told us the target does not exist; 400 says our
    request was malformed. Both are facts about the world, collected at a
    specific time from a specific URL, and they are exactly as re-derivable as a
    200. Suppressing them would make the catalogue lie by omission — a source
    that returns 404 for everything looks identical to one that was never
    reached. So a 4xx becomes an **observation carrying that status**.

A 5xx is not an answer
    A 5xx is the source failing to answer. Nothing was learned about the target,
    and the condition is usually transient, so it is retryable: it goes to the
    **dead-letter** lane with a reason code.

A refusal is not a failure either
    A host in a reserved range, an unknown ``source_id``, a non-HTTP source: we
    declined, or we could not even identify what to run. Retrying cannot help
    and the answer is a standing fact about the configuration, so it goes to
    **quarantine** — preserved, replayable, and never silently dropped.

Transport failure is a dead letter
    A timeout or a refused connection is the environment, not the source and not
    the target. DLQ, with the exception type, so a replay can tell a DNS failure
    from a TLS failure from a reset.

Determinism (Invariant 12)
--------------------------
Nothing here mints an id. ``observation_id`` is content-addressed by
``SourceConnector`` from (source, query, page, digest), so re-running a request
produces the *same* id — which is precisely what makes replay idempotent rather
than duplicating. The seen-set is keyed on that id, so a replayed request is
recognised and not republished.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

#: The lane names come from the shared topic catalog rather than being spelled
#: here, so a rename cannot leave this module publishing to a topic nobody reads.
from events.topics import TOPIC_DLQ, TOPIC_QUARANTINE, topic_for
from sources.connector import AcquisitionTask, SourceConnector
from sources.executor import AcquisitionError

WORKER_GROUP_ID = "cognitive-acquisition-worker-v1"
REQUEST_EVENT_TYPE = "acquisition.request"
OBSERVATION_EVENT_TYPE = "observation.created"

#: 4xx is the source answering. Everything else in this range is a fact we keep.
#: 401/403 in particular are *answers about access*, not about the target, and a
#: source that rate-limits us (429) has still told us something true.
def is_valid_answer(status: int) -> bool:
    """Is this status an answer rather than a failure?

    The line is drawn at 5xx, and only at 5xx. A 4xx is a deliberate response
    describing the request or the target; a 5xx is the server failing to respond
    at all. Anything else (2xx, 3xx — redirects are not followed) is an answer.
    """
    return status < 500


@dataclass(frozen=True)
class Failure:
    """A refusal, named and routed. Never a silent drop."""

    code: str
    reason: str
    topic: str
    source_id: str = ""
    task_id: str = ""
    status: int = 0
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "reason": self.reason,
            "topic": self.topic,
            "source_id": self.source_id,
            "task_id": self.task_id,
            "status": self.status,
            "detail": dict(self.detail),
        }


def classify_error(
    error: AcquisitionError, *, source_id: str = "", task_id: str = ""
) -> Failure:
    """Route an `AcquisitionError` to a named lane.

    Split is on *who can fix it*: a transient environment condition is a dead
    letter (replay it later), a standing property of the request or the
    configuration is quarantine (replay it only after something changed).
    """
    code = error.code
    if code in {"transport_failed"}:
        return Failure(
            code=code,
            reason=error.message,
            topic=TOPIC_DLQ,
            source_id=source_id,
            task_id=task_id,
        )
    if code in {
        "unknown_source",
        "not_an_http_source",
        "host_in_reserved_range",
        "keyed_source_without_key_env",
        "source_has_no_url",
    }:
        return Failure(
            code=code,
            reason=error.message,
            topic=TOPIC_QUARANTINE,
            source_id=source_id,
            task_id=task_id,
        )
    # An unrecognised code is surfaced by its own name rather than defaulted into
    # a lane: a new guard added upstream must not be silently routed as if it
    # were one of the known ones.
    return Failure(
        code=code,
        reason=error.message,
        topic=TOPIC_QUARANTINE,
        source_id=source_id,
        task_id=task_id,
    )


def classify_status(
    status: int, *, source_id: str = "", task_id: str = "", page: int = 0
) -> Failure | None:
    """A 5xx is a dead letter. A 4xx is an observation, so this returns ``None``."""
    if is_valid_answer(status):
        return None
    return Failure(
        code="upstream_server_error",
        reason=f"source returned {status}",
        topic=TOPIC_DLQ,
        source_id=source_id,
        task_id=task_id,
        status=status,
        detail={"page": page} if page else {},
    )


class RequestParser:
    """Decode an `acquisition.request` envelope into an :class:`AcquisitionTask`."""

    def parse(self, envelope: Any) -> AcquisitionTask:
        payload = getattr(envelope, "payload", b"") or b"{}"
        try:
            data = json.loads(payload)
        except (TypeError, ValueError) as exc:
            raise AcquisitionError(
                "request_payload_unreadable",
                f"request payload is not JSON: {exc}",
            ) from exc
        if not isinstance(data, dict):
            raise AcquisitionError("request_payload_unreadable", "request payload is not an object")

        task_id = str(data.get("task_id") or getattr(envelope, "work_id", "") or "")
        source_id = str(data.get("source_id") or getattr(envelope, "source_id", "") or "")
        if not task_id:
            raise AcquisitionError("request_without_task_id", "request names no task_id")
        if not source_id:
            raise AcquisitionError("request_without_source_id", "request names no source_id")
        return AcquisitionTask(
            task_id=task_id,
            source_id=source_id,
            source_name=str(data.get("source_name") or ""),
            query=str(data.get("query") or ""),
            category=str(data.get("category") or "unknown"),
            tenant_id=str(getattr(envelope, "tenant_id", "") or "default-tenant"),
            investigation_id=str(getattr(envelope, "investigation_id", "") or ""),
            # Restored from the envelope rather than re-derived: the runtime choice was
            # made by the planner, and a consumer that recomputed it would be guessing.
            runtime_ref=str(data.get("runtime_ref") or ""),
            query_ref=str(data.get("query_ref") or ""),
            constraints=tuple(
                dict(item) for item in (data.get("constraints") or []) if isinstance(item, dict)
            ),
        )


class FailureSink(Protocol):
    """Where a named failure goes. Bind to a Kafka producer in production."""

    def __call__(self, failure: Failure, envelope: Any) -> None: ...


@dataclass
class ObservationResult:
    """What one request produced. Every page is accounted for."""

    task_id: str
    source_id: str
    observations: tuple[dict[str, Any], ...] = ()
    failures: tuple[Failure, ...] = ()
    duplicates: tuple[str, ...] = ()
    superseded: bool = False

    @property
    def observation_ids(self) -> tuple[str, ...]:
        return tuple(str(o.get("event_id", "")) for o in self.observations)


class AcquisitionWorker:
    """Consume `acquisition.request`, execute it, publish one observation per page."""

    def __init__(
        self,
        *,
        connector: SourceConnector | None = None,
        sink: FailureSink | None = None,
        publish: Any | None = None,
        parser: RequestParser | None = None,
        seen: set[str] | None = None,
        completed: set[str] | None = None,
        runtimes: Mapping[str, Any] | None = None,
        config_dir: str | None = None,
    ) -> None:
        self.connector = connector or SourceConnector()
        self.sink = sink
        #: Called as ``publish(topic, envelope, key=...)`` for each observation.
        #: Injectable so the worker can be driven without a broker.
        self.publish = publish
        self.parser = parser or RequestParser()
        #: runtime_ref -> constructed runtime. Empty by default: a runtime is only
        #: constructed when a deployment wires one, so importing this module never pulls
        #: in a docker dependency or a connector image.
        self.runtimes: Mapping[str, Any] = dict(runtimes or {})
        #: Where per-source ``config.json`` / ``catalog.json`` for connector runtimes live.
        #: A connector protocol runtime needs both files and cannot invent them, so a
        #: missing one is a reported failure rather than a silently empty read.
        self.config_dir = config_dir or ""
        #: Idempotency: observation ids already published (Invariant 12 / FR-007).
        self.seen: set[str] = seen if seen is not None else set()
        #: Requests whose pages were all published. A replay of one of these is a
        #: no-op; a request that *failed* is deliberately absent, so replaying it
        #: re-runs it (the constitution requires rejected work stay replayable).
        self.completed: set[str] = completed if completed is not None else set()

    async def _run_runtime(
        self, envelope: Any, task: AcquisitionTask
    ) -> ObservationResult:
        """Execute a task on the runtime it names, and publish what it yields.

        Every failure mode here is reported as a :class:`Failure` with the reason named,
        because a task that names a runtime it cannot reach must say *which* part is
        missing -- an unknown runtime, an unwired runtime, a missing config file -- rather
        than surfacing as a generic acquisition error that reads like a source failure.
        """
        runtime = self.runtimes.get(task.runtime_ref)
        if runtime is None:
            return self._runtime_failure(
                envelope,
                task,
                "runtime_unavailable",
                f"task names runtime {task.runtime_ref!r}, "
                "which this worker has no instance of",
            )
        if not self.config_dir:
            return self._runtime_failure(
                envelope,
                task,
                "runtime_unconfigured",
                f"runtime {task.runtime_ref!r} needs a config directory, none was wired",
            )

        stem = task.source_name or task.source_id
        config_path = str(Path(self.config_dir) / f"{stem}.config.json")
        catalog_path = str(Path(self.config_dir) / f"{stem}.catalog.json")
        missing = [path for path in (config_path, catalog_path) if not Path(path).exists()]
        if missing:
            return self._runtime_failure(
                envelope,
                task,
                "runtime_config_missing",
                f"missing connector files: {', '.join(missing)}",
            )

        payload = task.to_task()
        payload["config_path"] = config_path
        payload["catalog_path"] = catalog_path

        observations: list[dict[str, Any]] = []
        duplicates: list[str] = []
        failures: list[Failure] = []
        try:
            async for artifact in runtime.acquire(payload):
                observation_id = str(getattr(artifact, "observation_id", "") or "")
                if not observation_id:
                    continue
                if observation_id in self.seen:
                    duplicates.append(observation_id)
                    continue
                self.seen.add(observation_id)
                observation = {
                    "event_id": observation_id,
                    "observation_id": observation_id,
                    "source_id": task.source_id,
                    "task_id": task.task_id,
                    "runtime_ref": task.runtime_ref,
                    "uri": str(getattr(artifact, "uri", "") or ""),
                    "content_hash": str(getattr(artifact, "content_hash", "") or ""),
                }
                self._publish_observation(observation)
                observations.append(observation)
        except Exception as exc:  # noqa: BLE001 - a runtime failure is a source failure
            failures.append(
                classify_error(
                    AcquisitionError("runtime_execution_failed", str(exc)),
                    source_id=task.source_id,
                    task_id=task.task_id,
                )
            )
            for failure in failures:
                self._route(failure, envelope)

        return ObservationResult(
            task_id=task.task_id,
            source_id=task.source_id,
            observations=tuple(observations),
            failures=tuple(failures),
            duplicates=tuple(duplicates),
        )

    def _runtime_failure(
        self, envelope: Any, task: AcquisitionTask, reason: str, detail: str
    ) -> ObservationResult:
        failure = classify_error(
            AcquisitionError(reason, detail),
            source_id=task.source_id,
            task_id=task.task_id,
        )
        self._route(failure, envelope)
        return ObservationResult(
            task_id=task.task_id,
            source_id=task.source_id,
            failures=(failure,),
        )

    async def handle(self, envelope: Any) -> ObservationResult:
        """Run one request to completion. Never raises for a source-level failure."""
        envelope_task_id = str(getattr(envelope, "work_id", "") or "")
        source_id = str(getattr(envelope, "source_id", "") or "")
        try:
            task = self.parser.parse(envelope)
        except AcquisitionError as exc:
            failure = classify_error(exc, source_id=source_id, task_id=envelope_task_id)
            self._route(failure, envelope)
            return ObservationResult(
                task_id=envelope_task_id,
                source_id=source_id,
                failures=(failure,),
            )

        # Replay of a request whose observations are already published is a no-op.
        # Keyed on the request's own identity, which is stable across a replay,
        # because the content-addressed observation id is not knowable until the
        # fetch has happened.
        marker = f"{task.task_id}|{task.source_id}|{task.query}"
        if marker in self.completed:
            return ObservationResult(
                task_id=task.task_id,
                source_id=task.source_id,
                superseded=True,
            )

        # A task naming a runtime goes to that runtime, not to the HTTP connector. The
        # fallback below would hand a connector-shaped source to ``HttpSourceExecutor``,
        # which refuses every non-HTTP kind -- so the task would fail with a message about
        # the wrong problem, and the operator would go looking at the source definition
        # instead of at the missing runtime.
        if task.runtime_ref:
            return await self._run_runtime(envelope, task)

        observations: list[dict[str, Any]] = []
        failures: list[Failure] = []
        duplicates: list[str] = []
        try:
            async for _capture, event in self.connector.collect(task):
                status = int(event.get("status", 0))
                failure = classify_status(
                    status, source_id=task.source_id, task_id=task.task_id
                )
                if failure is not None:
                    # The page failed. Stop: page N+1 of a failing source is not
                    # evidence of anything, and continuing would multiply one
                    # upstream outage into N dead letters.
                    failures.append(failure)
                    self._route(failure, envelope)
                    break

                observation_id = str(event.get("event_id", ""))
                if observation_id in self.seen:
                    duplicates.append(observation_id)
                    continue

                self._publish_observation(event)
                self.seen.add(observation_id)
                observations.append(event)
        except AcquisitionError as exc:
            failure = classify_error(exc, source_id=task.source_id, task_id=task.task_id)
            failures.append(failure)
            self._route(failure, envelope)

        if not failures:
            # Only a request that produced every page it could is marked done.
            # A dead-lettered request stays replayable.
            self.completed.add(marker)

        return ObservationResult(
            task_id=task.task_id,
            source_id=task.source_id,
            observations=tuple(observations),
            failures=tuple(failures),
            duplicates=tuple(duplicates),
        )

    def _publish_observation(self, event: dict[str, Any]) -> None:
        """Publish the connector's event verbatim.

        The shape is the connector's, not this module's. If a field is missing
        here it is missing for every other producer of `observation.created`
        too, which is the point.
        """
        if self.publish is None:
            return
        self.publish(
            topic_for(OBSERVATION_EVENT_TYPE),
            event,
            key=str(event.get("event_id", "")),
        )

    def _route(self, failure: Failure, envelope: Any) -> None:
        if self.sink is not None:
            self.sink(failure, envelope)

    async def aclose(self) -> None:
        await self.connector.aclose()


def kafka_failure_sink(producer: Any) -> FailureSink:
    """Bind a :class:`Failure` to its named topic on a real producer.

    Returns the broker's acknowledgement so a caller can prove the refusal was
    durably recorded rather than merely offered to a producer.
    """

    def sink(failure: Failure, envelope: Any) -> Any:
        record = {
            "code": failure.code,
            "reason": failure.reason,
            "source_id": failure.source_id,
            "task_id": failure.task_id,
            "status": failure.status,
            "detail": failure.detail,
            "original_event_type": str(getattr(envelope, "event_type", "") or ""),
        }
        return producer.publish_sync(
            failure.topic,
            json.dumps(record, sort_keys=True).encode("utf-8"),
            key=failure.task_id or failure.source_id or failure.code,
            event_type=failure.code,
        )

    return sink


def observation_publisher(producer: Any) -> Any:
    """Bind the connector's event to `topic_for('observation.created')`."""

    def publish(topic: str, event: dict[str, Any], *, key: str = "") -> Any:
        return producer.publish_sync(
            topic,
            json.dumps(event, sort_keys=True).encode("utf-8"),
            key=key,
            event_type=OBSERVATION_EVENT_TYPE,
        )

    return publish


def worker_topics() -> Iterable[str]:
    """Topics this worker touches: one input, one output, two failure lanes."""
    return (
        topic_for(REQUEST_EVENT_TYPE),
        topic_for(OBSERVATION_EVENT_TYPE),
        TOPIC_DLQ,
        TOPIC_QUARANTINE,
    )
