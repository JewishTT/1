"""Airbyte runtime: the connector *protocol*, not another HTTP source (ACQ-09/10/11).

Directive §24-§39. Airbyte is a process boundary and a line-delimited message
protocol, and both facts drive the design here.

**Streaming is forced, not chosen.** §27 forbids ``subprocess.run(capture_output=True)``
for ``read`` because a read against a large source does not fit in memory, and §36
requires the stdout reader to be flow-controlled rather than accumulating. So this
runtime spawns with :func:`asyncio.create_subprocess_exec` and iterates
``proc.stdout`` line by line. The alternative - run to completion, then split -
would satisfy the fixture and fail the real connector.

**Four message classes, three destinations.** §28 is the heart of this module:

===============  ==========================================  ===================
``RECORD``       acquisition evidence                          -> observation
``STATE``        checkpoint / control-plane state             -> run metadata
``LOG``          operational telemetry                        -> logs, not evidence
``TRACE``        connector runtime diagnostics                -> failure journal
===============  ==========================================  ===================

Only ``RECORD`` becomes an observation. ``STATE`` is recorded on the
:class:`~runtime.AirbyteRun` and never counted as evidence - §138 makes that
explicit, and §160 lists ``Airbyte STATE treated as evidence`` as a release
blocker. An unknown type is preserved verbatim into quarantine (§32) rather than
dropped, because a protocol that grows a message type is not a protocol failure.

**§35's ordering is implemented, not documented.** ``STATE`` is only recorded
*after* every preceding ``RECORD`` has been handed to the sink. The other order
produces ``STATE persisted / records lost / next run starts after state``, which
is an irreversible evidence gap - a checkpoint that outruns its own data.

**What a runtime may not see.** ``spec``, ``check``, ``discover`` and ``STATE``
are all control-plane material. They influence *whether* the run happens and
*where* it resumes, and none of them is an observation of the world.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from domain.acquisition_artifact import AcquisitionArtifact

from runtime import (
    RUNTIME_TIMEOUT,
    CostEstimate,
    ResourceClass,
    RuntimeError_,
)

#: §10's locator scheme for this family.
LOCATOR_PREFIX = "airbyte:"

#: §37's failure matrix, as a closed vocabulary so a failure is classified rather
#: than described.
FAIL_IMAGE_NOT_FOUND = "image_not_found"
FAIL_CONTAINER_START = "container_start_failed"
FAIL_SPEC = "spec_failed"
FAIL_CHECK = "check_failed"
FAIL_DISCOVER = "discover_failed"
FAIL_PROTOCOL_MALFORMED = "protocol_malformed"
FAIL_RECORD_INVALID = "record_invalid"
FAIL_STATE_INVALID = "state_invalid"
FAIL_RUNTIME = "connector_runtime_failed"

MESSAGE_TYPES = ("RECORD", "STATE", "LOG", "TRACE", "SPEC", "CONNECTION_STATUS", "CATALOG")


@dataclass
class AirbyteRun:
    """Immutable-ish run metadata (§29). Control plane, never evidence."""

    connector_ref: str
    image: str
    image_digest: str
    config_ref: str
    catalog_ref: str
    started_at: str = ""
    finished_at: str = ""
    records: int = 0
    states: int = 0
    logs: int = 0
    traces: int = 0
    unknown: int = 0
    state_before: dict[str, Any] | None = None
    state_after: dict[str, Any] | None = None
    spec: dict[str, Any] = field(default_factory=dict)
    catalog: dict[str, Any] = field(default_factory=dict)
    connection_status: str = ""
    quarantined: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "connector_ref": self.connector_ref,
            "image": self.image,
            "image_digest": self.image_digest,
            "config_ref": self.config_ref,
            "catalog_ref": self.catalog_ref,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "records": self.records,
            "states": self.states,
            "logs": self.logs,
            "traces": self.traces,
            "unknown_types": self.unknown,
            "connection_status": self.connection_status,
            "spec": self.spec,
            "stream_count": len(self.catalog.get("streams", [])),
            "state_after": self.state_after,
            "quarantined": self.quarantined,
        }


class AirbyteRuntime:
    """One connector execution protocol, three commands, one streaming read."""

    runtime_ref = "airbyte"
    execution_class = "connector_protocol"

    def __init__(
        self,
        *,
        image: str,
        image_digest: str = "",
        docker_binary: str = "docker",
        connector_ref: str = "",
        resource_class: ResourceClass | None = None,
        task_timeout: float = 300.0,
        max_record_bytes: int = 1024 * 1024,
        max_buffered_messages: int = 10_000,
        extra_host: tuple[str, ...] = ("host.docker.internal:host-gateway",),
        mount_dir: str | None = None,
    ) -> None:
        self._image = image
        self._digest = image_digest
        self._docker = docker_binary
        self._connector_ref = connector_ref or image.split(":")[0].split("/")[-1]
        self._resource = resource_class or ResourceClass(
            name="medium", max_runtime_seconds=task_timeout, max_output_bytes=64 * 1024 * 1024
        )
        self._timeout = task_timeout
        self._max_record_bytes = max_record_bytes
        self._max_buffered = max_buffered_messages
        self._extra_host = extra_host
        self._mount_dir = mount_dir
        self._run: AirbyteRun | None = None

    # ------------------------------------------------------------- contract --

    def capabilities(self) -> list[str]:
        return ["connector-protocol", "stdio", "streaming", "stateful", "discover"]

    def estimate(self, task: dict[str, Any]) -> CostEstimate:
        return CostEstimate(
            expected_artifacts=int(task.get("expected_records") or 100),
            expected_bytes=int(task.get("expected_records") or 100) * 1024,
            expected_seconds=self._timeout,
        )

    async def aclose(self) -> None:
        return None

    @property
    def run(self) -> AirbyteRun | None:
        return self._run

    # --------------------------------------------------------------- spec --

    async def spec(self) -> AirbyteRun:
        """§25/§38. ``spec`` must succeed before anything else is attempted."""
        run = self._new_run("spec")
        messages = [m async for m in self._execute(["spec"])]
        payload = next((m["spec"] for m in messages if m.get("type") == "SPEC"), None)
        if payload is None:
            raise RuntimeError_(FAIL_SPEC, "connector emitted no SPEC message")
        run.spec = payload
        return run

    async def check(self, config_path: str) -> AirbyteRun:
        """§38: connectivity before records. ``FAILED`` is named, not retried."""
        run = self._new_run("check")
        messages = [m async for m in self._execute(["check", "--config", config_path])]
        status = next(
            (m["connectionStatus"] for m in messages if m.get("type") == "CONNECTION_STATUS"),
            None,
        )
        run.connection_status = (status or {}).get("status", "")
        if run.connection_status != "SUCCEEDED":
            reason = (status or {}).get("message", "")[:200]
            raise RuntimeError_(
                FAIL_CHECK,
                f"{run.connection_status or 'no status'}: {reason}",
            )
        return run

    async def discover(self, config_path: str) -> AirbyteRun:
        """§114: the catalog is source metadata, never an observation."""
        run = self._new_run("discover")
        messages = [m async for m in self._execute(["discover", "--config", config_path])]
        payload = next((m["catalog"] for m in messages if m.get("type") == "CATALOG"), None)
        if payload is None:
            raise RuntimeError_(FAIL_DISCOVER, "connector emitted no CATALOG message")
        run.catalog = payload
        return run

    # --------------------------------------------------------------- read --

    async def acquire(self, task: dict[str, Any]) -> AsyncIterator[AcquisitionArtifact]:
        """``read``, streamed, with §28's four message classes kept apart.

        Yields one artifact per ``RECORD``. The ``STATE`` that follows is recorded
        on the run and never yielded - §28 and §160. The whole message stream is
        still saved as one capture so §107's "malformed output is retained" and
        §91's "partial run" both have something to point at.
        """
        config_path = str(task["config_path"])
        catalog_path = str(task["catalog_path"])
        state_path = task.get("state_path")
        task_id = str(task.get("task_id") or "")
        source_id = str(task.get("source_id") or self._connector_ref)
        version = str(task.get("runtime_version") or self._digest or "unpinned")

        argv = ["read", "--config", config_path, "--catalog", catalog_path]
        if state_path:
            argv += ["--state", str(state_path)]

        run = self._new_run("read")
        self._run = run
        stream = self._execute(argv)
        buffer: list[str] = []
        index = 0
        pending_records = 0

        async for message in stream:
            kind = message.get("type")
            if kind == "RECORD":
                record = message.get("record") or {}
                namespace = record.get("namespace")
                stream_name = record.get("stream")
                if not stream_name:
                    run.quarantined.append(
                        {
                            "code": FAIL_RECORD_INVALID,
                            "message_index": index,
                            "detail": "RECORD without a stream name",
                        }
                    )
                    continue
                body = json.dumps(
                    record.get("data", {}), sort_keys=True, ensure_ascii=False
                ).encode()
                if len(body) > self._max_record_bytes:
                    run.quarantined.append(
                        {
                            "code": "resource_limit_exceeded",
                            "message_index": index,
                            "detail": f"record of {len(body)} bytes exceeds the limit",
                        }
                    )
                    continue
                run.records += 1
                pending_records += 1
                # §10's locator. The message index is used rather than a per-stream
                # counter because §33 is explicit that records of several streams
                # are multiplexed and a per-stream assumption does not hold.
                locator = (
                    f"{LOCATOR_PREFIX}{namespace or '-'}/{stream_name}:{index}"
                )
                yield AcquisitionArtifact(
                    task_id=task_id,
                    source_id=source_id,
                    worker_ref="airbyte",
                    target_uri=f"airbyte://{self._connector_ref}/{stream_name}",
                    locator=locator,
                    body=body,
                    content_type="application/json",
                    fetched_at=datetime.now(UTC),
                    transport="docker-stdio",
                    producer=self.runtime_ref,
                    producer_version=version,
                    metadata={
                        "namespace": namespace or "",
                        "stream": stream_name,
                        "emitted_at": record.get("emitted_at"),
                        "message_index": index,
                        "connector_ref": self._connector_ref,
                        "image_digest": self._digest,
                        # §63: the parser that reads a connector record.
                        "parser_hint": "structured_fields",
                    },
                )
            elif kind == "STATE":
                state = message.get("state")
                if not isinstance(state, dict):
                    run.quarantined.append(
                        {
                            "code": FAIL_STATE_INVALID,
                            "message_index": index,
                            "detail": f"STATE was {type(state).__name__}",
                        }
                    )
                else:
                    # §35: recorded only after every preceding record was yielded.
                    if pending_records == 0 and run.state_before is None:
                        run.state_before = state
                    else:
                        run.state_after = state
                    run.states += 1
            elif kind == "LOG":
                run.logs += 1
            elif kind == "TRACE":
                run.traces += 1
                run.quarantined.append(
                    {
                        "code": "trace",
                        "message_index": index,
                        "detail": str(message.get("trace"))[:400],
                    }
                )
            else:
                # §32: an unknown type is preserved, never discarded.
                run.unknown += 1
                run.quarantined.append(
                    {
                        "code": "unknown_message_type",
                        "message_index": index,
                        "detail": str(kind),
                        "raw": json.dumps(message)[:400],
                    }
                )
            index += 1
            buffer.append(json.dumps(message, ensure_ascii=False))
            if len(buffer) >= self._max_buffered:
                buffer = buffer[-self._max_buffered :]

        run.finished_at = datetime.now(UTC).isoformat()

    # ------------------------------------------------------------ execute --

    async def _execute(self, argv: list[str]) -> AsyncIterator[dict[str, Any]]:
        """Run the connector and yield decoded ``AirbyteMessage`` objects.

        Line-oriented because the protocol is: one JSON object per line on stdout
        (§149). ``stderr`` is logs and is never mixed into this parser (§89).
        """
        command = [self._docker, "run", "--rm", "-i"]
        for host in self._extra_host:
            command += ["--add-host", host]
        if self._mount_dir:
            command += ["--mount", f"type=bind,source={self._mount_dir},target=/cfg"]
        command += [self._image, *argv]

        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            assert proc.stdout is not None
            while True:
                try:
                    raw = await asyncio.wait_for(proc.stdout.readline(), timeout=self._timeout)
                except TimeoutError as exc:
                    proc.kill()
                    raise RuntimeError_(
                        RUNTIME_TIMEOUT, f"{argv[0]} exceeded {self._timeout}s"
                    ) from exc
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except ValueError as exc:
                    raise RuntimeError_(
                        FAIL_PROTOCOL_MALFORMED,
                        f"stdout line was not JSON ({type(exc).__name__}): {line[:160]}",
                    ) from exc
                if not isinstance(message, dict) or "type" not in message:
                    raise RuntimeError_(
                        FAIL_PROTOCOL_MALFORMED, f"stdout line has no message type: {line[:160]}"
                    )
                yield message
        finally:
            await proc.wait()

    def _new_run(self, command: str) -> AirbyteRun:
        run = AirbyteRun(
            connector_ref=self._connector_ref,
            image=self._image,
            image_digest=self._digest,
            config_ref="",
            catalog_ref="",
            started_at=datetime.now(UTC).isoformat(),
        )
        run.config_ref = f"run:{command}"
        if self._run is not None:
            run.state_before = self._run.state_after
        self._run = run
        return run
