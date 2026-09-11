"""Connector module registry (feature 005 US4, SpiderFoot pattern).

SpiderFoot-style pluggable scan modules: each ``ConnectorModule`` has a stable
``name``, a ``capabilities()`` list, a ``run(task, channel)`` entrypoint that
pushes events onto one shared channel, and a prompt ``stop()``. ``ConnectorRegistry``
owns module lifecycle (REGISTERED → ACTIVE → STOPPED/FAILED) and emits
``connector.registered`` / ``connector.status_changed`` envelopes (refs only, I-5)
when a producer is supplied. ``ConnectorRunner`` is a bounded worker pool
(SpiderFoot threadpool pattern) that executes tasks per module with strict fault
isolation: a raising module is quarantined (shared DLQ semantics) and the other
modules keep scanning. Event targets are normalized through the canonical target
vocabulary (``shared/donor/target.py``).

   Source repo : donors/spiderfoot/spiderfoot/{plugin,event,threadpool}.py
   License     : MIT (logic layer only)
   What changed: event/threadpool/plugin state machines reduced to the module
                 lifecycle + channel; logging removed; canonical Target
                 normalization replaces SpiderFoot's free-form event types;
                 isolated faults go to the platform quarantine lane instead of
                 being swallowed.
"""

from __future__ import annotations

import json
import queue
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from donor.target import TargetType, classify, normalize
from events.dlq import DLQRecord
from events.kafka import build_envelope
from events.topics import topic_for

_MODULE_REQUIRED = ("name", "capabilities", "run", "stop")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def normalize_event_target(raw: str) -> dict[str, str]:
    """Canonical target from raw harvest input (shared/donor/target.py reuse)."""
    value = (raw or "").strip()
    type_name = classify(value) if value else TargetType.UNKNOWN
    return {
        "raw": value,
        "type": type_name,
        "value": normalize(value, type_name) if value else "",
    }


class ConnectorStatus:
    REGISTERED = "REGISTERED"
    ACTIVE = "ACTIVE"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


@runtime_checkable
class ConnectorModule(Protocol):
    """SpiderFoot-style scan module.

    ``run`` is called by the runner with a ``task`` dict and the shared
    ``EventChannel`` it should push scan events to. ``stop`` must be prompt and
    idempotent. Implementations also expose ``name: str``.
    """

    name: str

    def capabilities(self) -> list[str]: ...
    def run(self, task: dict, channel: EventChannel) -> None: ...
    def stop(self) -> None: ...


@dataclass
class ModuleEvent:
    """One event a module pushed on the shared channel (refs-only)."""

    event_id: str = field(default_factory=lambda: "EVT-" + uuid.uuid4().hex[:12])
    module_name: str = ""
    kind: str = "scan_result"
    target_type: str = ""
    target_value: str = ""
    normalized: dict[str, str] = field(default_factory=dict)
    detail: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "module": self.module_name,
            "kind": self.kind,
            "target_type": self.target_type,
            "target_value": self.target_value,
            "normalized": dict(self.normalized),
            "detail": dict(self.detail),
            "created_at": self.created_at,
        }


class EventChannel:
    """Thread-safe shared channel a module pushes scan events onto."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[ModuleEvent] = []

    def emit(self, event: ModuleEvent) -> None:
        with self._lock:
            self._events.append(event)

    def events(self) -> list[ModuleEvent]:
        with self._lock:
            return list(self._events)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


class ConnectorRegistry:
    """Module lifecycle registry with connector.* envelope emissions."""

    def __init__(self, producer=None) -> None:
        self._modules: dict[str, ConnectorModule] = {}
        self._status: dict[str, str] = {}
        self._producer = producer

    def register(self, module: ConnectorModule) -> ConnectorModule:
        missing = [req for req in _MODULE_REQUIRED if not hasattr(module, req)]
        if missing:
            raise TypeError(f"{module!r} missing required member(s): {', '.join(missing)}")
        if not callable(module.capabilities):
            raise TypeError(f"{module!r} does not satisfy the ConnectorModule protocol")
        if not callable(module.run):
            raise TypeError(f"{module!r} does not satisfy the ConnectorModule protocol")
        if not callable(module.stop):
            raise TypeError(f"{module!r} does not satisfy the ConnectorModule protocol")
        if module.name in self._modules:
            raise ValueError(f"connector module already registered: {module.name}")
        self._modules[module.name] = module
        self._status[module.name] = ConnectorStatus.REGISTERED
        self._emit("connector.registered", module.name, ConnectorStatus.REGISTERED)
        return module

    def activate(self, name: str) -> str:
        self._require(name)
        self._status[name] = ConnectorStatus.ACTIVE
        self._emit("connector.status_changed", name, ConnectorStatus.ACTIVE)
        return self._status[name]

    def deactivate(self, name: str) -> str:
        self._require(name)
        self._status[name] = ConnectorStatus.STOPPED
        self._emit("connector.status_changed", name, ConnectorStatus.STOPPED)
        return self._status[name]

    def fail(self, name: str) -> str:
        self._require(name)
        self._status[name] = ConnectorStatus.FAILED
        self._emit("connector.status_changed", name, ConnectorStatus.FAILED)
        return self._status[name]

    def status(self, name: str) -> str:
        self._require(name)
        return self._status[name]

    def module(self, name: str) -> ConnectorModule:
        self._require(name)
        return self._modules[name]

    def names(self) -> list[str]:
        return sorted(self._modules)

    def dispatch(
        self, task: dict, channel: EventChannel, only: list[str] | None = None
    ) -> list[str]:
        """Run ACTIVE modules over ``channel`` in deterministic (name-sorted) order.

        Returns the ordered names actually dispatched. Faults are contained per
        module (a raising module is marked FAILED; the rest still run) so one
        broken module never blocks the pipeline.
        """
        order = [
            name
            for name in self.names()
            if self._status[name] == ConnectorStatus.ACTIVE and (only is None or name in only)
        ]
        for name in order:
            try:
                self._modules[name].run(task, channel)
            except Exception:  # noqa: BLE001 - fault containment per module
                self.fail(name)
        return order

    def _require(self, name: str) -> None:
        if name not in self._modules:
            raise KeyError(f"connector module not registered: {name}")

    def _emit(self, event_type: str, module_name: str, status: str) -> None:
        if self._producer is None:
            return
        envelope = build_envelope(
            event_type=event_type,
            event_version="1.0",
            producer="acquisition.registry",
            producer_version="0.1.0",
            payload=json.dumps(
                {"connector": module_name, "status": status}, default=str
            ).encode("utf-8"),
            entity_id=module_name,
            event_id=f"evt-{module_name}-{status}",
        )
        self._producer.produce(topic_for(event_type), envelope, key=module_name)


class ConnectorRunner:
    """Bounded worker pool executing module tasks (SpiderFoot threadpool port).

    Workers are spawned once and reused; ``submit`` feeds a bounded queue so an
    overloaded backlog can never grow unboundedly. A module whose ``run`` raises
    is quarantined (shared DLQ semantics) and marked FAILED in the registry —
    the remaining tasks and modules keep going untouched.
    """

    def __init__(
        self,
        registry: ConnectorRegistry,
        *,
        max_threads: int = 4,
        max_queue: int = 1000,
    ) -> None:
        self._registry = registry
        self._max_threads = int(max_threads)
        self._tasks: queue.Queue[tuple[str, dict]] = queue.Queue(maxsize=int(max_queue))
        self._workers: list[threading.Thread] = []
        self._stop_flag = threading.Event()
        self._lock = threading.Lock()
        self._quarantined: list[DLQRecord] = []
        self._channel = EventChannel()

    def __enter__(self) -> ConnectorRunner:
        self.start()
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.stop()

    @property
    def channel(self) -> EventChannel:
        return self._channel

    def start(self) -> None:
        if self._workers:
            return
        self._stop_flag.clear()
        for i in range(self._max_threads):
            worker = threading.Thread(
                target=self._work,
                name=f"connector-runner-{i + 1}",
                daemon=True,
            )
            worker.start()
            self._workers.append(worker)

    def submit(self, module_name: str, task: dict) -> None:
        if module_name not in self._registry.names():
            raise KeyError(f"connector module not registered: {module_name}")
        if self._registry.status(module_name) != ConnectorStatus.ACTIVE:
            raise ValueError(f"connector module not active: {module_name}")
        if self._stop_flag.is_set():
            raise RuntimeError("runner is stopped")
        self._tasks.put((module_name, dict(task)))

    def events(self) -> list[ModuleEvent]:
        return self._channel.events()

    def quarantined(self) -> list[DLQRecord]:
        with self._lock:
            return list(self._quarantined)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_flag.set()
        for worker in self._workers:
            worker.join(timeout=timeout)
        self._workers.clear()

    def _work(self) -> None:
        while True:
            if self._stop_flag.is_set():
                if not self._run_one_nowait():
                    return
                continue
            try:
                module_name, task = self._tasks.get(timeout=0.2)
            except queue.Empty:
                continue
            self._run_one(module_name, task)

    def _run_one_nowait(self) -> bool:
        try:
            module_name, task = self._tasks.get_nowait()
        except queue.Empty:
            return False
        self._run_one(module_name, task)
        return True

    def _run_one(self, module_name: str, task: dict) -> None:
        try:
            module = self._registry.module(module_name)
            module.run(task, self._channel)
        except Exception as exc:  # noqa: BLE001 - fault containment: one bad module must not fail others
            record = DLQRecord(
                reason=f"connector.module_fault:{module_name}",
                payload=json.dumps(task, default=str).encode("utf-8"),
                topic="acquisition",
            )
            record.reason = f"{record.reason}: {exc}"
            with self._lock:
                self._quarantined.append(record)
            try:
                self._registry.fail(module_name)
            except KeyError:
                pass
        finally:
            self._tasks.task_done()