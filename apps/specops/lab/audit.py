"""Append-only, hash-chained audit log for the Red-Team Lab.

The lab performs high-risk red-team actions under a confirmed RoE, so
the record of who did what has to be stronger than a log line. Each row commits to the
previous row's hash; `verify()` recomputes the chain and names the first broken sequence
number. Nothing here can update or delete a row.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from typing import Any

from specops.lab.models import now_iso

_FORBIDDEN_DETAIL_KEYS = ("password", "passwd", "secret", "token", "cookie", "credential")


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _clean_detail(detail: dict[str, Any]) -> dict[str, Any]:
    """Refuse a secret-shaped key rather than relying on every caller to remember.

    The lab's structural promise is that no raw secret reaches an audit row, a report or
    a log. A key named `token` is not a value the auditor needs; refusing it is cheaper
    than inspecting arbitrary strings.
    """
    for key in detail:
        lowered = key.lower()
        if any(marker in lowered for marker in _FORBIDDEN_DETAIL_KEYS):
            raise ValueError(f"audit detail key {key!r} is secret-shaped and must not be recorded")
    return dict(detail)


@dataclass(frozen=True)
class AuditEvent:
    seq: int
    tenant_id: str
    actor: str
    action: str
    object_type: str
    object_id: str
    outcome: str
    at: str
    correlation_id: str
    detail: dict[str, Any]
    prev_hash: str
    row_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "tenant_id": self.tenant_id,
            "actor": self.actor,
            "action": self.action,
            "object_type": self.object_type,
            "object_id": self.object_id,
            "outcome": self.outcome,
            "at": self.at,
            "correlation_id": self.correlation_id,
            "detail": dict(self.detail),
            "prev_hash": self.prev_hash,
            "row_hash": self.row_hash,
        }


class AuditLog:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rows: list[AuditEvent] = []

    def append(
        self,
        *,
        tenant_id: str,
        actor: str,
        action: str,
        object_type: str,
        object_id: str,
        outcome: str = "ok",
        correlation_id: str = "",
        detail: dict[str, Any] | None = None,
    ) -> AuditEvent:
        clean = _clean_detail(detail or {})
        with self._lock:
            seq = len(self._rows) + 1
            prev_hash = self._rows[-1].row_hash if self._rows else "GENESIS"
            body = {
                "seq": seq,
                "tenant_id": tenant_id,
                "actor": actor,
                "action": action,
                "object_type": object_type,
                "object_id": object_id,
                "outcome": outcome,
                "at": now_iso(),
                "correlation_id": correlation_id,
                "detail": clean,
                "prev_hash": prev_hash,
            }
            row_hash = hashlib.sha256((prev_hash + _canonical(body)).encode("utf-8")).hexdigest()
            row = AuditEvent(
                seq=seq,
                tenant_id=tenant_id,
                actor=actor,
                action=action,
                object_type=object_type,
                object_id=object_id,
                outcome=outcome,
                at=str(body["at"]),
                correlation_id=correlation_id,
                detail=clean,
                prev_hash=prev_hash,
                row_hash=row_hash,
            )
            self._rows.append(row)
            return row

    def rows(self, *, limit: int | None = 100, tenant_id: str | None = None) -> list[AuditEvent]:
        with self._lock:
            rows = list(self._rows)
        if tenant_id is not None:
            rows = [row for row in rows if row.tenant_id == tenant_id]
        if limit is not None:
            rows = rows[-max(limit, 0) :]
        return rows

    def verify(self) -> str | None:
        """Return the first broken `seq` as a string, or `None` when intact."""
        with self._lock:
            rows = list(self._rows)
        prev_hash = "GENESIS"
        for row in rows:
            body = {
                "seq": row.seq,
                "tenant_id": row.tenant_id,
                "actor": row.actor,
                "action": row.action,
                "object_type": row.object_type,
                "object_id": row.object_id,
                "outcome": row.outcome,
                "at": row.at,
                "correlation_id": row.correlation_id,
                "detail": row.detail,
                "prev_hash": row.prev_hash,
            }
            expected = hashlib.sha256((prev_hash + _canonical(body)).encode("utf-8")).hexdigest()
            if row.prev_hash != prev_hash or row.row_hash != expected:
                return str(row.seq)
            prev_hash = row.row_hash
        return None
