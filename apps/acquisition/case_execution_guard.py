"""Immediate preflight guard for already-dispatched Feature 034 acquisition work.

The producer checks approval before enqueueing. This guard checks it *again* in the
consumer process, immediately before the connector performs network I/O, closing the
revocation/scope-change window between queue publication and execution.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

import yaml
from sqlalchemy import text

from sources.executor import AcquisitionError


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _policy_revision() -> str:
    """Calculate the same full policy revision used by control-plane PersonCasePolicy."""
    path = Path(__file__).resolve().parent / "policies" / "person_case_sources.yaml"
    try:
        with path.open("r", encoding="utf-8") as handle:
            policy = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise RuntimeError(f"cannot load current case source policy: {type(exc).__name__}: {exc}") from exc
    if not isinstance(policy, Mapping):
        raise RuntimeError("current case source policy is not a YAML mapping")
    material = json.dumps(
        dict(policy), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    digest = "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()
    version = str(_mapping(policy.get("metadata")).get("version", "1"))
    return f"{version}:{digest}"


def _expired(value: Any, *, now: datetime) -> bool:
    if value is None or value == "":
        return False
    try:
        instant = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise AcquisitionError(
            "case_expiry_invalid", "stored expires_at is not a valid ISO-8601 timestamp"
        ) from exc
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    return instant <= now


class PostgresCaseExecutionGuard:
    """Fail closed if the case, policy, action or reservation changed after dispatch."""

    def __init__(self, session_factory: Any) -> None:
        if session_factory is None:
            raise ValueError("session_factory is required for case-bound worker preflight")
        self._session_factory = session_factory

    async def __call__(self, task: Any) -> None:
        # Non-case tasks are part of the broader platform and remain on their existing
        # capability path. A partial case binding is rejected by RequestParser earlier.
        case_id = str(getattr(task, "case_id", "") or "")
        if not case_id:
            return

        tenant_id = str(getattr(task, "tenant_id", "") or "")
        investigation_id = str(getattr(task, "investigation_id", "") or "")
        required = {
            "tenant_id": tenant_id,
            "investigation_id": investigation_id,
            "case_id": case_id,
            "scope_digest": str(getattr(task, "scope_digest", "") or ""),
            "policy_digest": str(getattr(task, "policy_digest", "") or ""),
            "policy_revision": str(getattr(task, "policy_revision", "") or ""),
            "scope_revision": int(getattr(task, "scope_revision", 0) or 0),
            "budget_reservation_id": str(getattr(task, "budget_reservation_id", "") or ""),
            "idempotency_key": str(getattr(task, "idempotency_key", "") or ""),
            "run_id": str(getattr(task, "run_id", "") or ""),
            "case_policy_source_id": str(getattr(task, "case_policy_source_id", "") or ""),
            "approved_action_ref": str(getattr(task, "approved_action_ref", "") or ""),
            "action_id": str(getattr(task, "action_id", "") or ""),
        }
        missing = [key for key, value in required.items() if value in ("", 0)]
        if missing:
            raise AcquisitionError(
                "case_dispatch_binding_missing",
                f"case-bound task is missing required authority bindings: {', '.join(missing)}",
            )
        if required["approved_action_ref"] != required["action_id"]:
            raise AcquisitionError(
                "case_action_binding_mismatch",
                "approved_action_ref and action_id do not match",
            )

        # Policy-file errors and database/transport errors are not converted into
        # source-level refusals. They propagate so the worker exits and Kafka does not
        # advance the failing offset.
        current_policy_revision = _policy_revision()
        if required["policy_revision"] != current_policy_revision:
            raise AcquisitionError(
                "case_policy_revision_stale",
                "source policy changed after dispatch; a fresh plan and approval are required",
            )

        now = datetime.now(UTC)
        async with self._session_factory() as session:
            metadata_result = await session.execute(
                text("""
                    SELECT tenant_id, payload
                    FROM person_case_metadata
                    WHERE case_id = :case_id AND tenant_id = :tenant_id
                """),
                {"case_id": case_id, "tenant_id": tenant_id},
            )
            metadata_row = metadata_result.mappings().first()
            if metadata_row is None:
                raise AcquisitionError(
                    "case_not_found", "case metadata is absent for the request tenant"
                )
            metadata = _mapping(metadata_row.get("payload"))
            if metadata.get("tenant_id") != tenant_id:
                raise AcquisitionError("case_tenant_mismatch", "case metadata tenant changed")
            if metadata.get("approved") is not True:
                raise AcquisitionError(
                    "case_approval_revoked", "case scope is not currently approved"
                )
            if (
                str(metadata.get("scope_digest") or "") != required["scope_digest"]
                or int(metadata.get("scope_revision", 0) or 0) != required["scope_revision"]
            ):
                raise AcquisitionError(
                    "case_scope_stale", "case scope changed after this task was dispatched"
                )
            if _expired(metadata.get("expires_at"), now=now):
                raise AcquisitionError("case_scope_expired", "case scope expired before execution")
            allowed_sources = metadata.get("allowed_source_ids")
            if not isinstance(allowed_sources, list) or required["case_policy_source_id"] not in {
                str(value) for value in allowed_sources
            }:
                raise AcquisitionError(
                    "case_source_not_allowed", "task source is no longer in the approved source allowlist"
                )

            context_result = await session.execute(
                text("""
                    SELECT investigation_id, payload
                    FROM investigation_contexts
                    WHERE context_id = :case_id AND tenant_id = :tenant_id
                """),
                {"case_id": case_id, "tenant_id": tenant_id},
            )
            context_row = context_result.mappings().first()
            if context_row is None:
                raise AcquisitionError(
                    "case_context_missing", "canonical context no longer exists for this tenant"
                )
            context = _mapping(context_row.get("payload"))
            if (
                str(context_row.get("investigation_id") or "") != investigation_id
                or str(context.get("investigation_id") or "") != investigation_id
            ):
                raise AcquisitionError(
                    "case_investigation_mismatch", "task investigation does not match canonical case context"
                )
            if str(context.get("policy_snapshot_ref") or "") != required["policy_revision"]:
                raise AcquisitionError(
                    "case_policy_revision_stale",
                    "canonical context policy revision differs from the queued task",
                )
            if str(context.get("state") or "").lower() in {"closed", "suspended"}:
                raise AcquisitionError(
                    "case_not_executable",
                    f"case lifecycle state {context.get('state')!r} does not permit acquisition",
                )

            action_result = await session.execute(
                text("""
                    SELECT a.payload AS payload
                    FROM research_actions a
                    JOIN research_obligations o
                      ON o.obligation_id = a.obligation_id AND o.tenant_id = a.tenant_id
                    WHERE a.action_id = :action_id
                      AND a.tenant_id = :tenant_id
                      AND o.context_id = :case_id
                """),
                {
                    "action_id": required["action_id"],
                    "tenant_id": tenant_id,
                    "case_id": case_id,
                },
            )
            action_row = action_result.mappings().first()
            if action_row is None:
                raise AcquisitionError(
                    "case_action_missing", "approved action is no longer stored under this case"
                )
            action = _mapping(action_row.get("payload"))
            if (
                str(action.get("action_id") or "") != required["action_id"]
                or str(action.get("status") or "").lower() != "approved"
                or bool(action.get("requires_operator_approval", False))
                or str(action.get("scope_digest") or "") != required["scope_digest"]
                or str(action.get("policy_digest") or "") != required["policy_digest"]
                or str(action.get("source_id") or "") != required["case_policy_source_id"]
                or str(action.get("catalogue_source_id") or "") != str(getattr(task, "source_id", "") or "")
            ):
                raise AcquisitionError(
                    "case_action_stale",
                    "durable action approval, scope, policy or catalogue binding no longer matches the queued task",
                )

            intent_result = await session.execute(
                text("""
                    SELECT run_id, payload
                    FROM person_case_dispatch_intents
                    WHERE tenant_id = :tenant_id
                      AND case_id = :case_id
                      AND idempotency_key = :idempotency_key
                      AND scope_digest = :scope_digest
                      AND policy_digest = :policy_digest
                """),
                {
                    "tenant_id": tenant_id,
                    "case_id": case_id,
                    "idempotency_key": required["idempotency_key"],
                    "scope_digest": required["scope_digest"],
                    "policy_digest": required["policy_digest"],
                },
            )
            intent_row = intent_result.mappings().first()
            if intent_row is None or str(intent_row.get("run_id") or "") != required["run_id"]:
                raise AcquisitionError(
                    "case_dispatch_intent_missing", "matching durable dispatch intent does not exist"
                )
            intent = _mapping(intent_row.get("payload"))
            intent_state = str(intent.get("state") or "").upper()
            if intent_state not in {"PREPARED", "PUBLISHED", "PARTIAL"}:
                raise AcquisitionError(
                    "case_dispatch_not_authorized",
                    f"dispatch intent state {intent_state or 'UNKNOWN'} is not executable",
                )
            approved_refs = intent.get("approved_action_refs")
            if not isinstance(approved_refs, list) or required["action_id"] not in {
                str(value) for value in approved_refs
            }:
                raise AcquisitionError(
                    "case_dispatch_action_mismatch", "action is not covered by the durable dispatch intent"
                )

            reservation_result = await session.execute(
                text("""
                    SELECT reservation_id, state, payload
                    FROM person_case_budget_reservations
                    WHERE reservation_id = :reservation_id
                      AND tenant_id = :tenant_id
                      AND case_id = :case_id
                      AND investigation_id = :investigation_id
                      AND idempotency_key = :idempotency_key
                      AND scope_digest = :scope_digest
                      AND policy_digest = :policy_digest
                      AND state IN ('RESERVED', 'PUBLISHED')
                """),
                {
                    "reservation_id": required["budget_reservation_id"],
                    "tenant_id": tenant_id,
                    "case_id": case_id,
                    "investigation_id": investigation_id,
                    "idempotency_key": required["idempotency_key"],
                    "scope_digest": required["scope_digest"],
                    "policy_digest": required["policy_digest"],
                },
            )
            reservation_row = reservation_result.mappings().first()
            if reservation_row is None:
                raise AcquisitionError(
                    "case_budget_not_reserved",
                    "matching active durable budget reservation is absent or was revoked",
                )
            reservation_payload = _mapping(reservation_row.get("payload"))
            if (
                str(reservation_payload.get("reservation_id") or required["budget_reservation_id"])
                != required["budget_reservation_id"]
            ):
                raise AcquisitionError(
                    "case_budget_binding_mismatch", "budget reservation payload does not match task binding"
                )
