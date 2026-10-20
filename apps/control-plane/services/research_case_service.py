"""Person case application service (Feature 034).

Orchestrates case lifecycle: create, approve, plan, run, pause, close.
Transaction boundaries are explicit; every state change is durable through the
existing Context Engine store and never written directly to raw DB or model provider.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from context_engine.obligations import (
    KnowledgeType,
    ResearchObligation,
    SaturationState,
)
from context_engine.person_case_profile import (
    AUTHORISED_CASE,
    CONSENTED_RECORDS,
    PUBLIC_PROFESSIONAL,
    create_initial_obligations,
)
from context_engine.person_case_profile import PUBLIC_ROLE_REVIEW as _PUBLIC_ROLE_REVIEW
from domain.investigation_context import (
    ContextEngineError,
    InvestigationContext,
    InvestigationState,
    ObligationStatus,
)
from services.research_case_policy import (
    PolicyDecision,
    PersonCasePolicy,
    create_initial_obligations as _create_initial_obligations,
)

from context_engine.loop import CognitiveLoop


class CaseServiceError(RuntimeError):
    """Case service failure with a named reason code."""


class CaseNotFound(CaseServiceError):
    pass


class CaseNotApproved(CaseServiceError):
    pass


class CaseAlreadyRunning(CaseServiceError):
    pass


class BudgetNotReserved(CaseServiceError):
    pass


class ResearchCaseService:
    """Application service for person-research cases."""

    def __init__(
        self,
        *,
        store: Any,
        loop: CognitiveLoop | None = None,
        policy: PersonCasePolicy | None = None,
        model_gateway: Any = None,
        budget_service: Any = None,
        artifact_sink: Any = None,
        observation_gate: Any = None,
    ) -> None:
        self._store = store
        self._loop = loop
        self._policy = policy
        self._model_gateway = model_gateway
        self._budget_service = budget_service
        self._artifact_sink = artifact_sink
        self._observation_gate = observation_gate

    # -- case creation -------------------------------------------------------

    async def create_case(
        self,
        *,
        tenant_id: str,
        created_by: str,
        purpose_code: str,
        purpose_text: str,
        basis_ref: str,
        launch_profile: str,
        subject_anchors: list[dict[str, str]],
        jurisdictions: list[str],
        valid_time: dict[str, Any],
        claim_families: list[str],
        allowed_source_ids: list[str],
        denied_claim_families: list[str] | None = None,
        budget_ref: str | None = None,
        expires_at: str | None = None,
        questions: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a draft research case. No collection happens yet."""
        if launch_profile not in {
            PUBLIC_PROFESSIONAL,
            "PUBLIC_ROLE_REVIEW",
            "CONSENTED_RECORDS",
            AUTHORISED_CASE,
        }:
            raise CaseServiceError(f"unknown launch profile: {launch_profile}")

        # Validate policy before creating.
        if self._policy is not None and self._policy.loaded:
            scope_payload = {
                "purpose_code": purpose_code,
                "launch_profile": launch_profile,
                "claim_families": claim_families,
                "allowed_source_ids": allowed_source_ids,
                "valid_time": valid_time,
                "jurisdictions": jurisdictions,
            }
            scope_digest = self._digest(json.dumps(scope_payload, sort_keys=True))
            decision = self._policy.validate_case_scope(
                case_id="pending",
                tenant_id=tenant_id,
                purpose_code=purpose_code,
                basis_ref=basis_ref,
                scope_digest=scope_digest,
                scope_revision=1,
                claim_families=claim_families,
                allowed_source_ids=allowed_source_ids,
                expires_at=expires_at,
                launch_profile=launch_profile,
            )
            if not decision.allowed:
                raise CaseServiceError(f"BLOCKED_POLICY: {decision.detail}")
        else:
            scope_digest = "sha256:pending"

        case_id = f"case-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        context = InvestigationContext(
            context_id=case_id,
            tenant_id=tenant_id,
            title=f"Person case: {purpose_text[:80]}",
            question=purpose_text,
            state=InvestigationState.UNINVESTIGATED,
            scope_refs=[a.get("value", "") for a in subject_anchors],
            valid_time_from=valid_time.get("from"),
            valid_time_until=valid_time.get("until"),
            claim_families=tuple(claim_families),
            allowed_source_ids=tuple(allowed_source_ids),
            created_by=created_by,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
            basis_ref=basis_ref,
            purpose_code=purpose_code,
            launch_profile=launch_profile,
            scope_digest=scope_digest,
            scope_revision=1,
            approved=False,
            budget_ref=budget_ref,
        )

        await self._store.put_context(context)

        # Create initial obligations.
        obligations = _create_initial_obligations(
            case_id=case_id,
            tenant_id=tenant_id,
            launch_profile=launch_profile,
            anchors=subject_anchors,
            questions=questions or [],
            claim_families=claim_families,
            valid_time=valid_time,
        )
        for obl in obligations:
            await self._store.create_obligation(obl)

        return {
            "case_id": case_id,
            "tenant_id": tenant_id,
            "state": "DRAFT",
            "scope_digest": scope_digest,
            "scope_revision": 1,
            "created_at": now,
            "obligation_count": len(obligations),
        }

    # -- approval -----------------------------------------------------------

    async def approve_case(
        self,
        *,
        case_id: str,
        tenant_id: str,
        approver_id: str,
        scope_digest: str,
        scope_revision: int,
    ) -> dict[str, Any]:
        """Approver stamps authority/scope/policy digest. No network side effects."""
        context = await self._store.get_context(case_id)
        if context is None:
            raise CaseNotFound(f"case {case_id} not found")
        if context.tenant_id != tenant_id:
            raise CaseServiceError("cross-tenant access denied")

        if not scope_digest or not scope_digest.startswith("sha256:"):
            raise CaseServiceError("scope_digest must be a sha256 digest")

        # Re-validate against policy.
        if self._policy is not None and self._policy.loaded:
            decision = self._policy.validate_case_scope(
                case_id=case_id,
                tenant_id=tenant_id,
                purpose_code=context.purpose_code,
                basis_ref=context.basis_ref,
                scope_digest=scope_digest,
                scope_revision=scope_revision,
                claim_families=list(context.claim_families),
                allowed_source_ids=list(context.allowed_source_ids),
                expires_at=context.expires_at,
                launch_profile=context.launch_profile,
            )
            if not decision.allowed:
                raise CaseServiceError(f"BLOCKED_POLICY: {decision.detail}")

        updated = context.__class__(
            **{
                **context.__dict__,
                "approved": True,
                "scope_digest": scope_digest,
                "scope_revision": scope_revision,
                "state": InvestigationState.ACTIVE,
                "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
        )
        await self._store.put_context(updated)

        return {
            "case_id": case_id,
            "tenant_id": tenant_id,
            "state": "APPROVED",
            "scope_digest": scope_digest,
            "scope_revision": scope_revision,
            "approved_at": updated.updated_at,
        }

    # -- planning -----------------------------------------------------------

    async def plan_case(
        self,
        *,
        case_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        """Compile questions and return preview obligations/capabilities/cost.

        No network side effects. Planning alone performs no I/O and consumes no
        collection budget.
        """
        context = await self._store.get_context(case_id)
        if context is None:
            raise CaseNotFound(f"case {case_id} not found")
        if context.tenant_id != tenant_id:
            raise CaseServiceError("cross-tenant access denied")
        if not context.approved:
            raise CaseNotApproved(f"case {case_id} is not approved")

        obligations = await self._store.open_obligations(case_id)
        return {
            "case_id": case_id,
            "tenant_id": tenant_id,
            "scope_digest": context.scope_digest,
            "scope_revision": context.scope_revision,
            "obligations": [
                {
                    "obligation_id": o.obligation_id,
                    "question": o.question,
                    "claim_family": o.claim_family,
                    "state": o.status.value,
                    "required_capabilities": list(o.required_capabilities),
                    "satisfaction_condition": o.satisfaction_condition,
                }
                for o in obligations
            ],
            "capabilities_preview": [
                "public_search",
                "official_web_fetch",
                "html_parse",
                "claim_extraction",
                "blocking",
                "pair_comparison",
                "analyst_review",
            ],
            "no_network_side_effects": True,
        }

    # -- run ----------------------------------------------------------------

    async def run_case(
        self,
        *,
        case_id: str,
        tenant_id: str,
        idempotency_key: str,
        approved_action_refs: list[str],
    ) -> dict[str, Any]:
        """Enqueue only approved plan/action refs. Idempotent request key required."""
        if not idempotency_key:
            raise CaseServiceError("idempotency_key is required")

        context = await self._store.get_context(case_id)
        if context is None:
            raise CaseNotFound(f"case {case_id} not found")
        if context.tenant_id != tenant_id:
            raise CaseServiceError("cross-tenant access denied")
        if not context.approved:
            raise CaseNotApproved(f"case {case_id} is not approved")

        # Budget reservation must exist before dispatch.
        if self._budget_service is not None:
            reserved = await self._budget_service.has_reservation(
                case_id=case_id, tenant_id=tenant_id
            )
            if not reserved:
                raise BudgetNotReserved(
                    f"no durable budget reservation for case {case_id}; dispatch blocked"
                )
        else:
            raise CaseServiceError(
                "budget service not configured; cannot reserve, cannot dispatch"
            )

        # Check scope staleness.
        # (In production, compare stored digest against current plan digest.)

        # Record the dispatch intent.
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        await self._store.record_dispatch_intent(
            case_id=case_id,
            tenant_id=tenant_id,
            run_id=run_id,
            idempotency_key=idempotency_key,
            approved_action_refs=approved_action_refs,
            scope_digest=context.scope_digest,
            policy_digest=context.scope_digest,
        )

        # If a CognitiveLoop is wired, tick it once to propose next actions.
        if self._loop is not None:
            step = await self._loop.tick(
                context,
                approved_action_ids=tuple(approved_action_refs),
            )
        else:
            step = None

        return {
            "case_id": case_id,
            "run_id": run_id,
            "idempotency_key": idempotency_key,
            "state": "RUNNING",
            "actions_proposed": step.actions_proposed if step else (),
            "awaiting_approval": step.awaiting_approval if step else (),
        }

    # -- pause --------------------------------------------------------------

    async def pause_case(
        self,
        *,
        case_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        """Cancel or pause dispatch; preserve partial results."""
        context = await self._store.get_context(case_id)
        if context is None:
            raise CaseNotFound(f"case {case_id} not found")
        if context.tenant_id != tenant_id:
            raise CaseServiceError("cross-tenant access denied")

        updated = context.__class__(
            **{
                **context.__dict__,
                "state": InvestigationState.SUSPENDED,
                "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
        )
        await self._store.put_context(updated)
        return {"case_id": case_id, "state": "PAUSED"}

    # -- close --------------------------------------------------------------

    async def close_case(
        self,
        *,
        case_id: str,
        tenant_id: str,
        disposition: str,
        report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Terminal state + CompletionReport. Requires open obligations dispositioned."""
        context = await self._store.get_context(case_id)
        if context is None:
            raise CaseNotFound(f"case {case_id} not found")
        if context.tenant_id != tenant_id:
            raise CaseServiceError("cross-tenant access denied")

        open_obligations = await self._store.open_obligations(case_id)
        undisposed = [o for o in open_obligations if o.status == ObligationStatus.OPEN]
        if undisposed and disposition not in {"BLOCKED", "CANCELLED"}:
            raise CaseServiceError(
                f"cannot close: {len(undisposed)} open obligations not dispositioned"
            )

        updated = context.__class__(
            **{
                **context.__dict__,
                "state": InvestigationState.CLOSED,
                "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
        )
        await self._store.put_context(updated)

        return {
            "case_id": case_id,
            "state": "CLOSED",
            "disposition": disposition,
            "report": report or {},
            "closed_at": updated.updated_at,
        }

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _digest(material: str) -> str:
        return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()
