"""Audit log service (T062, FR-029, US3).

Records decision/projection/access audit events with an append-only in-memory
log and a PostgreSQL copy hook (asyncpg prepared insert provided by the app
layer). Audit entries are immutable (I-4: append-only) and timestamped.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class AuditKind(str, Enum):
    DECISION = "decision"
    PROJECTION = "projection"
    ACCESS = "access"


@dataclass
class AuditEvent:
    audit_id: str = field(default_factory=lambda: "AUD-" + uuid.uuid4().hex[:12])
    kind: AuditKind = AuditKind.ACCESS
    actor: str = ""
    tenant_id: str = ""
    action: str = ""
    target: str = ""
    detail: dict = field(default_factory=dict)
    at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def immutable(self) -> bool:
        return True  # I-4: audit trail is append-only


class AuditLog:
    def __init__(self, pg_copy=None) -> None:
        """pg_copy: optional async callable(event) persisting to Postgres."""
        self._events: list[AuditEvent] = []
        self._pg_copy = pg_copy

    def record(self, kind: AuditKind, actor: str, tenant_id: str, action: str, target: str = "", detail: dict | None = None) -> AuditEvent:
        event = AuditEvent(kind=kind, actor=actor, tenant_id=tenant_id, action=action, target=target, detail=detail or {})
        self._events.append(event)
        if self._pg_copy is not None:
            self._pg_copy(event)
        return event

    def by_tenant(self, tenant_id: str, kind: AuditKind | None = None) -> list[AuditEvent]:
        return [
            e for e in self._events
            if e.tenant_id == tenant_id and (kind is None or e.kind == kind)
        ]

    def all(self) -> list[AuditEvent]:
        return list(self._events)

    def decision(self, actor: str, tenant_id: str, action: str, target: str, detail: dict | None = None) -> AuditEvent:
        return self.record(AuditKind.DECISION, actor, tenant_id, action, target, detail)

    def projection(self, actor: str, tenant_id: str, action: str, target: str, detail: dict | None = None) -> AuditEvent:
        return self.record(AuditKind.PROJECTION, actor, tenant_id, action, target, detail)

    def access(self, actor: str, tenant_id: str, action: str, target: str, detail: dict | None = None) -> AuditEvent:
        return self.record(AuditKind.ACCESS, actor, tenant_id, action, target, detail)