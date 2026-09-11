"""Frontier operational state (T026, FR-003, R-4).

Postgres is authoritative (hierarchical GLOBAL→TENANT→INVESTIGATION→SOURCE→
HOST→TASK); Redis provides hot lease/cooldown/locking. Kafka is never the
frontier queue (I-5/R-4). Looks up items by priority, respects cooldown/lease,
tracks retry and dedup.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class FrontierItem:
    frontier_id: str
    uri: str
    tenant_id: str
    investigation_id: str | None = None
    source_id: str | None = None
    host_key: str | None = None
    priority: float = 0.0
    state: str = "READY"  # READY | LEASED | DONE | COOLDOWN | RETRY | QUARANTINED
    retries: int = 0
    lease_until: float = 0.0
    next_schedule_at: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def schedule_key(self) -> str:
        return f"{self.tenant_id}:{self.uri}"


class Frontier:
    """In-memory authoritative frontier + lease/cooldown semantics.

    Redis-backed variant is a drop-in replacement behind this interface; the
    authoritative hierarchy + lease/cooldown/retry semantics are preserved.
    """

    def __init__(self) -> None:
        self._items: dict[str, FrontierItem] = {}
        self._by_schedule: dict[str, str] = {}  # schedule_key -> frontier_id

    def enqueue(self, item: FrontierItem) -> bool:
        key = item.schedule_key()
        existing_id = self._by_schedule.get(key)
        if existing_id:
            # Dedup: prefer higher priority / retain existing (idempotent enqueue).
            existing = self._items[existing_id]
            if item.priority > existing.priority:
                existing.priority = item.priority
                existing.state = "READY"
            return False
        self._items[item.frontier_id] = item
        self._by_schedule[key] = item.frontier_id
        return True

    def pop_next(self, *, tenant_id: str | None = None, now: float | None = None) -> FrontierItem | None:
        now = now if now is not None else time.time()
        candidates = [i for i in self._items.values() if i.state in ("READY", "RETRY")]
        if tenant_id:
            candidates = [i for i in candidates if i.tenant_id == tenant_id]
        candidates = [i for i in candidates if i.next_schedule_at <= now]
        if not candidates:
            return None
        best = max(candidates, key=lambda i: i.priority)
        best.state = "LEASED"
        best.lease_until = now + 30.0
        return best

    def lease_expired(self, frontier_id: str, now: float | None = None) -> bool:
        item = self._items.get(frontier_id)
        if item is None:
            return True
        now = now if now is not None else time.time()
        return item.lease_until <= now

    def complete(self, frontier_id: str) -> None:
        item = self._items.get(frontier_id)
        if item:
            item.state = "DONE"
            item.next_schedule_at = time.time() + 3600.0  # reseed freshness

    def fail_retry(self, frontier_id: str, *, max_retries: int = 3, cooldown_s: float = 60.0) -> None:
        item = self._items.get(frontier_id)
        if item is None:
            return
        if item.retries >= max_retries:
            item.state = "QUARANTINED"
            return
        item.retries += 1
        item.state = "RETRY"
        item.next_schedule_at = time.time() + cooldown_s

    def cooldown(self, frontier_id: str, until: float) -> None:
        item = self._items.get(frontier_id)
        if item:
            item.state = "COOLDOWN"
            item.next_schedule_at = until

    def cancel(self, frontier_id: str) -> None:
        item = self._items.pop(frontier_id, None)
        if item:
            self._by_schedule.pop(item.schedule_key(), None)

    def count(self, tenant_id: str | None = None) -> int:
        if tenant_id is None:
            return len(self._items)
        return sum(1 for i in self._items.values() if i.tenant_id == tenant_id)

    def ready_count(self, tenant_id: str | None = None) -> int:
        return sum(
            1
            for i in self._items.values()
            if i.state in ("READY", "RETRY") and (tenant_id is None or i.tenant_id == tenant_id)
        )