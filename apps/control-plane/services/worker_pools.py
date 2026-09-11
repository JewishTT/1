"""Worker pool failure isolation (T066, US3).

HTTP, browser, document, OCR, vision and TDA worker pools are independent:
a failing pool retires its own tasks and never blocks the others. Orchestrators
route by pool kind and bypass an unhealthy pool; healthy pools keep draining.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class WorkerKind(str, Enum):
    HTTP = "http"
    BROWSER = "browser"
    DOCUMENT = "document"
    OCR = "ocr"
    VISION = "vision"
    TDA = "tda"


@dataclass
class PoolStatus:
    healthy: bool = True
    active: int = 0
    capacity: int = 4
    failures: int = 0
    last_error: str = ""

    def mark_failure(self, error: str) -> None:
        self.failures += 1
        self.last_error = error
        if self.failures >= 3:
            self.healthy = False


@dataclass
class EnqueuedTask:
    task_id: str
    kind: WorkerKind
    payload: dict = field(default_factory=dict)


class WorkerPoolRegistry:
    """Routes tasks to independent per-kind pools."""

    def __init__(self, capacities: dict[str, int] | None = None) -> None:
        capacities = capacities or {k.value: 4 for k in WorkerKind}
        self._pools: dict[WorkerKind, PoolStatus] = {
            WorkerKind(k): PoolStatus(capacity=capacities.get(k, 4)) for k in capacities
        }
        self._pending: list[EnqueuedTask] = []

    def status(self, kind: WorkerKind) -> PoolStatus:
        return self._pools[kind]

    def submit(self, task: EnqueuedTask) -> bool:
        """Returns True if the task lands in a healthy pool."""
        pool = self._pools[task.kind]
        if not pool.healthy:
            return False
        if pool.active >= pool.capacity:
            return False
        pool.active += 1
        self._pending.append(task)
        return True

    def fail(self, kind: WorkerKind, error: str) -> None:
        self._pools[kind].mark_failure(error)

    def complete(self, kind: WorkerKind) -> None:
        pool = self._pools[kind]
        pool.active = max(0, pool.active - 1)
        poll = [t for t in self._pending if t.kind == kind]
        if poll:
            self._pending.remove(poll[0])

    def drain(self, kind: WorkerKind) -> list[EnqueuedTask]:
        """Drain remaining tasks of a kind (after failure or shutdown)."""
        drained = [t for t in self._pending if t.kind == kind]
        self._pending = [t for t in self._pending if t.kind != kind]
        self._pools[kind].active = 0
        return drained

    def healthy_kinds(self) -> list[WorkerKind]:
        return [k for k in WorkerKind if self._pools[k].healthy]