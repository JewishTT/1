"""Unit tests: audit log (T062) + worker pool isolation (T066), US3."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.audit import AuditKind, AuditLog
from services.worker_pools import EnqueuedTask, WorkerKind, WorkerPoolRegistry


class TestAudit:
    def test_append_only_immutable_events(self):
        log = AuditLog()
        event = log.decision("analyst-1", "tenant-a", "admit", "OBS-1", {"verdict": "accepted"})
        assert event.immutable is True
        assert event.kind == AuditKind.DECISION
        assert log.all() == [event]

    def test_projection_and_access_events(self):
        log = AuditLog()
        log.projection("svc", "tenant-a", "index", "entities")
        log.access("viewer", "tenant-a", "read", "finding/FND-1")
        kinds = {e.kind for e in log.by_tenant("tenant-a")}
        assert kinds == {AuditKind.PROJECTION, AuditKind.ACCESS}

    def test_tenant_scoped_queries(self):
        log = AuditLog()
        log.record(AuditKind.ACCESS, "u", "tenant-a", "read", "obs/X")
        log.record(AuditKind.ACCESS, "u", "tenant-b", "read", "obs/Y")
        assert len(log.by_tenant("tenant-a")) == 1
        assert len(log.by_tenant("tenant-a", AuditKind.ACCESS)) == 1

    def test_postgres_copy_hook_invoked(self):
        copies = []
        log = AuditLog(pg_copy=copies.append)
        log.decision("svc", "tenant-a", "admit", "x")
        assert len(copies) == 1
        assert copies[0].action == "admit"


class TestWorkerPools:
    def test_pools_are_independent(self):
        registry = WorkerPoolRegistry()
        assert registry.submit(EnqueuedTask("t1", WorkerKind.HTTP))
        registry.fail(WorkerKind.HTTP, "connection refused")
        registry.fail(WorkerKind.HTTP, "connection refused")
        registry.fail(WorkerKind.HTTP, "connection refused")
        # HTTP is now unhealthy; browser + tda unaffected.
        assert not registry.submit(EnqueuedTask("t2", WorkerKind.HTTP))
        assert registry.submit(EnqueuedTask("t3", WorkerKind.BROWSER))
        assert registry.submit(EnqueuedTask("t4", WorkerKind.TDA))
        assert WorkerKind.BROWSER in registry.healthy_kinds()

    def test_failing_pool_drains_without_stalling_others(self):
        registry = WorkerPoolRegistry()
        for task in ("t1", "t2"):
            registry.submit(EnqueuedTask(task, WorkerKind.OCR))
        drained = registry.drain(WorkerKind.OCR)
        assert len(drained) == 2
        # Other pools still accept work.
        assert registry.submit(EnqueuedTask("t3", WorkerKind.VISION))

    def test_capacity_rejects_overload(self):
        registry = WorkerPoolRegistry(capacities={"vision": 1})
        assert registry.submit(EnqueuedTask("t1", WorkerKind.VISION))
        assert not registry.submit(EnqueuedTask("t2", WorkerKind.VISION))
        registry.complete(WorkerKind.VISION)
        assert registry.submit(EnqueuedTask("t3", WorkerKind.VISION))