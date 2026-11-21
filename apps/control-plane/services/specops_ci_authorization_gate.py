"""PostgreSQL-backed approval gate used by the SpecOps&CI Temporal Activities.

This adapter is deliberately independent of ARTEX graph/evaluation implementations.
It verifies current authorizations and durable operator decisions; an ARTEX graph adapter
and a read-only assessment evaluator must still be supplied by the worker deployment.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from specops_ci.domain import AssessmentKind
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from db.schema import (
    SpecOpsEngagementAuthorization,
    SpecOpsOperationDecision,
)


class PostgresSpecOpsAuthorizationGate:
    """Revalidate current engagement scope and signed-off operator decisions."""

    def __init__(self, session_factory: async_sessionmaker[Any]) -> None:
        self._session_factory = session_factory

    async def revalidate(
        self,
        *,
        tenant_id: str,
        authorization_id: str,
        snapshot_id: str,
        operation_expires_at: str,
        target_entity_ids: list[str] | tuple[str, ...],
        assessment_kind: AssessmentKind,
    ) -> bool:
        """Return true only while the durable authorization still covers this step."""
        try:
            operation_expiry = datetime.fromisoformat(operation_expires_at)
        except (TypeError, ValueError):
            return False
        now = datetime.now(UTC)
        if (
            operation_expiry.tzinfo is None
            or operation_expiry.utcoffset() is None
            or not now < operation_expiry
        ):
            return False
        async with self._session_factory() as session:
            result = await session.execute(
                select(SpecOpsEngagementAuthorization).where(
                    SpecOpsEngagementAuthorization.authorization_id == authorization_id,
                    SpecOpsEngagementAuthorization.tenant_id == tenant_id,
                )
            )
            row = result.scalar_one_or_none()
        if row is None or row.revoked_at is not None:
            return False
        if row.source_snapshot_id != snapshot_id:
            return False
        if not row.issued_at <= now < row.expires_at:
            return False
        approved_targets = set(row.allowed_entity_ids or ())
        if not set(target_entity_ids).issubset(approved_targets):
            return False
        allowed = set(row.allowed_assessments or ())
        return assessment_kind.value in allowed

    async def verify_operator_decision(
        self,
        *,
        tenant_id: str,
        operation_id: str,
        spec_digest: str,
        step_id: str,
        decision: dict[str, Any],
    ) -> bool:
        """Verify the signal maps to one append-only admin decision and live approval."""
        approved = decision.get("approved")
        if not isinstance(approved, bool):
            return False
        decision_id = decision.get("decision_id")
        authorization_id = decision.get("authorization_id")
        snapshot_id = decision.get("snapshot_id")
        reviewer_id = decision.get("reviewer_id")
        approval_ref = decision.get("approval_ref")
        if not all(
            isinstance(value, str) and value
            for value in (
                decision_id,
                authorization_id,
                snapshot_id,
                reviewer_id,
                approval_ref,
            )
        ):
            return False

        now = datetime.now(UTC)
        async with self._session_factory() as session:
            decision_result = await session.execute(
                select(SpecOpsOperationDecision).where(
                    SpecOpsOperationDecision.decision_id == decision_id,
                    SpecOpsOperationDecision.tenant_id == tenant_id,
                    SpecOpsOperationDecision.operation_id == operation_id,
                    SpecOpsOperationDecision.authorization_id == authorization_id,
                    SpecOpsOperationDecision.snapshot_id == snapshot_id,
                    SpecOpsOperationDecision.spec_digest == spec_digest,
                    SpecOpsOperationDecision.step_id == step_id,
                    SpecOpsOperationDecision.approved.is_(approved),
                    SpecOpsOperationDecision.reviewer_id == reviewer_id,
                    SpecOpsOperationDecision.reviewer_role == "admin",
                    SpecOpsOperationDecision.approval_ref == approval_ref,
                )
            )
            decision_row = decision_result.scalar_one_or_none()
            if decision_row is None:
                return False
            authorization_result = await session.execute(
                select(SpecOpsEngagementAuthorization).where(
                    SpecOpsEngagementAuthorization.authorization_id == authorization_id,
                    SpecOpsEngagementAuthorization.tenant_id == tenant_id,
                )
            )
            authorization = authorization_result.scalar_one_or_none()
        return bool(
            authorization is not None
            and authorization.revoked_at is None
            and authorization.source_snapshot_id == snapshot_id
            and authorization.issued_at <= now < authorization.expires_at
            and decision_row.decided_at <= now
        )


__all__ = ["PostgresSpecOpsAuthorizationGate"]
