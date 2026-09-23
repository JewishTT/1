"""Operational controls for temporal materialization projections."""

from __future__ import annotations

from datetime import UTC, datetime
from threading import RLock
from typing import Any


class MaterializationOperations:
    """Bounded in-memory run registry for hermetic development and tests.

    Production persistence belongs behind the same operations contract. This
    implementation intentionally keeps status transitions explicit and never
    deletes failed/quarantined diagnostics.
    """

    def __init__(self, *, max_in_flight: int = 8, max_retries: int = 3) -> None:
        if max_in_flight <= 0 or max_retries < 0:
            raise ValueError("max_in_flight must be positive and max_retries non-negative")
        self.max_in_flight = max_in_flight
        self.max_retries = max_retries
        self._runs: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    def start(self, run_id: str, *, tenant_id: str, entity_id: str) -> dict[str, Any]:
        with self._lock:
            current = self._runs.get(run_id)
            if current is not None:
                return dict(current)
            active = sum(
                1 for item in self._runs.values() if item["status"] in {"QUEUED", "RUNNING"}
            )
            if active >= self.max_in_flight:
                return {"run_id": run_id, "status": "DEFERRED", "reason": "backpressure"}
            state = {
                "run_id": run_id,
                "tenant_id": tenant_id,
                "entity_id": entity_id,
                "status": "QUEUED",
                "retry_count": 0,
                "reason": "",
                "created_at": datetime.now(UTC),
            }
            self._runs[run_id] = state
            return dict(state)

    def mark(self, run_id: str, status: str, *, reason: str = "") -> dict[str, Any]:
        with self._lock:
            state = self._runs.setdefault(
                run_id,
                {
                    "run_id": run_id,
                    "tenant_id": "",
                    "entity_id": "",
                    "status": "QUEUED",
                    "retry_count": 0,
                    "reason": "",
                    "created_at": datetime.now(UTC),
                },
            )
            if status in {"FAILED", "QUARANTINED"}:
                state["retry_count"] += 1
                if state["retry_count"] > self.max_retries:
                    status = "QUARANTINED"
            state["status"] = status
            state["reason"] = reason
            return dict(state)

    def resume(self, run_id: str, *, tenant_id: str) -> dict[str, Any] | None:
        with self._lock:
            state = self._runs.get(run_id)
            if state is None or state["tenant_id"] != tenant_id:
                return None
            if state["status"] in {"FAILED", "DEFERRED", "QUARANTINED"}:
                state["status"] = "QUEUED"
                state["reason"] = "resumed"
            return dict(state)

    def health(self, *, tenant_id: str) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._runs.values() if item["tenant_id"] == tenant_id]

    def get(self, run_id: str, *, tenant_id: str) -> dict[str, Any] | None:
        with self._lock:
            state = self._runs.get(run_id)
            if state is None or state["tenant_id"] != tenant_id:
                return None
            return dict(state)


def reconcile_fingerprints(expected: set[str], actual: set[str]) -> dict[str, Any]:
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    divergent = sorted(expected & actual) if not missing and not extra else []
    return {
        "ok": not missing and not extra,
        "missing": missing,
        "extra": extra,
        "divergent": divergent,
    }


__all__ = ["MaterializationOperations", "reconcile_fingerprints"]
