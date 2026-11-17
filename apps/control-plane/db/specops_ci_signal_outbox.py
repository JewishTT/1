"""Durable outbox helpers for SpecOps&CI Temporal operator-decision signals."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.schema import SpecOpsDecisionSignalOutbox


SPECOPS_DECISION_SIGNAL = "provide_operator_decision"
OUTBOX_LEASE = timedelta(minutes=2)
MAX_BACKOFF_SECONDS = 3600


def outbox_id_for(*, tenant_id: str, decision_id: str) -> str:
    digest = hashlib.sha256(f"{tenant_id}\x00{decision_id}".encode()).hexdigest()
    return "scio-" + digest[:60]


async def enqueue_decision_signal(
    session: AsyncSession,
    *,
    tenant_id: str,
    operation_id: str,
    step_id: str,
    spec_digest: str,
    decision_id: str,
    payload: dict[str, Any],
) -> SpecOpsDecisionSignalOutbox:
    """Add a signal intent to the caller's transaction; do not commit independently."""
    existing = await session.execute(
        select(SpecOpsDecisionSignalOutbox).where(
            SpecOpsDecisionSignalOutbox.tenant_id == tenant_id,
            SpecOpsDecisionSignalOutbox.decision_id == decision_id,
        )
    )
    row = existing.scalar_one_or_none()
    if row is not None:
        if (
            row.operation_id != operation_id
            or row.step_id != step_id
            or row.spec_digest != spec_digest
            or row.payload != payload
        ):
            raise ValueError("decision outbox key already exists with different payload")
        return row

    row = SpecOpsDecisionSignalOutbox(
        outbox_id=outbox_id_for(tenant_id=tenant_id, decision_id=decision_id),
        tenant_id=tenant_id,
        operation_id=operation_id,
        step_id=step_id,
        spec_digest=spec_digest,
        decision_id=decision_id,
        signal_name=SPECOPS_DECISION_SIGNAL,
        payload=payload,
        status="PENDING",
        attempts=0,
        last_error="",
    )
    session.add(row)
    return row


class SpecOpsDecisionSignalOutboxRelay:
    """Claim, send and acknowledge decision signals with lease-based crash recovery."""

    def __init__(self, session_factory: async_sessionmaker[Any]) -> None:
        self._session_factory = session_factory

    async def claim_ready(self, *, limit: int = 20) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(SpecOpsDecisionSignalOutbox)
                    .where(
                        or_(
                            and_(
                                SpecOpsDecisionSignalOutbox.status.in_(("PENDING", "FAILED")),
                                SpecOpsDecisionSignalOutbox.available_at <= now,
                            ),
                            and_(
                                SpecOpsDecisionSignalOutbox.status == "DISPATCHING",
                                SpecOpsDecisionSignalOutbox.lease_until <= now,
                            ),
                        )
                    )
                    .order_by(
                        SpecOpsDecisionSignalOutbox.available_at,
                        SpecOpsDecisionSignalOutbox.created_at,
                    )
                    .limit(max(1, min(limit, 100)))
                    .with_for_update(skip_locked=True)
                )
                rows = list(result.scalars().all())
                claimed: list[dict[str, Any]] = []
                for row in rows:
                    row.status = "DISPATCHING"
                    row.attempts += 1
                    row.lease_until = now + OUTBOX_LEASE
                    claimed.append(
                        {
                            "outbox_id": row.outbox_id,
                            "tenant_id": row.tenant_id,
                            "operation_id": row.operation_id,
                            "step_id": row.step_id,
                            "spec_digest": row.spec_digest,
                            "decision_id": row.decision_id,
                            "signal_name": row.signal_name,
                            "payload": dict(row.payload or {}),
                            "attempts": row.attempts,
                        }
                    )
                return claimed

    async def mark_dispatched(self, outbox_id: str) -> None:
        now = datetime.now(timezone.utc)
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(SpecOpsDecisionSignalOutbox)
                    .where(SpecOpsDecisionSignalOutbox.outbox_id == outbox_id)
                    .with_for_update()
                )
                row = result.scalar_one_or_none()
                if row is None:
                    return
                row.status = "DISPATCHED"
                row.dispatched_at = now
                row.lease_until = None
                row.last_error = ""

    async def mark_failed(self, outbox_id: str, reason: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    select(SpecOpsDecisionSignalOutbox)
                    .where(SpecOpsDecisionSignalOutbox.outbox_id == outbox_id)
                    .with_for_update()
                )
                row = result.scalar_one_or_none()
                if row is None:
                    return
                backoff = min(MAX_BACKOFF_SECONDS, 2 ** min(row.attempts, 10))
                row.status = "FAILED"
                row.lease_until = None
                row.available_at = datetime.now(timezone.utc) + timedelta(seconds=backoff)
                row.last_error = str(reason)[:2000]


__all__ = [
    "SPECOPS_DECISION_SIGNAL",
    "SpecOpsDecisionSignalOutboxRelay",
    "enqueue_decision_signal",
    "outbox_id_for",
]
