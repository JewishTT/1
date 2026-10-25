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
from dataclasses import replace
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
    PUBLIC_ROLE_REVIEW,
)
from domain.investigation_context import (
    ContextEngineError,
    ContextRevision,
    InvestigationContext,
    InvestigationState,
    ObligationStatus,
)
from services.research_case_policy import (
    PersonCasePolicy,
    create_initial_obligations,
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


class PolicyNotLoaded(CaseServiceError):
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

    def _require_policy(self) -> PersonCasePolicy:
        """Fail closed when the policy gate is not loaded."""
        if self._policy is None or not self._policy.loaded:
            raise PolicyNotLoaded(
                "person-case source policy is not loaded; fail closed"
            )
        return self._policy

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
            PUBLIC_ROLE_REVIEW,
            CONSENTED_RECORDS,
            AUTHORISED_CASE,
        }:
            raise CaseServiceError(f"unknown launch profile: {launch_profile}")

        # Fail closed: policy must be loaded before any case is created.
        policy = self._require_policy()

        if not subject_anchors or any(
            not str(anchor.get("kind", "")).strip()
            or not str(anchor.get("value", "")).strip()
            for anchor in subject_anchors
        ):
            raise CaseServiceError("at least one typed, non-empty subject anchor is required")

        policy_revision = str(policy._policy.get("metadata", {}).get("version", "1"))
        scope_payload = self._scope_material(
            tenant_id=tenant_id,
            purpose_code=purpose_code,
            purpose_text=purpose_text,
            basis_ref=basis_ref,
            launch_profile=launch_profile,
            subject_anchors=subject_anchors,
            jurisdictions=jurisdictions,
            valid_time=valid_time,
            claim_families=claim_families,
            denied_claim_families=denied_claim_families or [],
            allowed_source_ids=allowed_source_ids,
            budget_ref=budget_ref,
            expires_at=expires_at,
            policy_revision=policy_revision,
        )
        scope_digest = self._digest(
            json.dumps(scope_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        )

        # The InvestigationContext identity is content-addressed over
        # tenant_id + investigation_id + title + scope_refs. context_id is
        # computed by the model itself; we never pass a random one.
        investigation_id = f"case-{uuid.uuid4().hex[:12]}"
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        context = InvestigationContext(
            tenant_id=tenant_id,
            investigation_id=investigation_id,
            title=f"Person case: {purpose_text[:80]}",
            scope_refs=tuple(a.get("value", "") for a in subject_anchors),
            question=purpose_text,
            state=InvestigationState.UNINVESTIGATED,
            policy_snapshot_ref=policy_revision,
            created_at=now,
        )

        # The externally visible case identifier is the canonical context address,
        # not the random investigation_id. Every route and obligation must use the same
        # key that ContextStore.get_context() actually addresses.
        case_id = context.context_id
        await self._store.put_context(context)
        revision_number = await self._store.next_revision_number(context.context_id)
        revision = ContextRevision(
            context_id=context.context_id,
            revision=revision_number,
            parent_revision=revision_number - 1,
            state=context.state,
            snapshot={
                "context": context.to_dict(),
                "person_case_scope": scope_payload,
                "scope_digest": scope_digest,
                "scope_revision": 1,
            },
            operator_actions=(created_by,),
            rules_version="feature-034-v1",
            mode="deterministic",
        )
        await self._store.append_revision(revision)
        await self._store.put_person_case_metadata(
            case_id=case_id,
            tenant_id=tenant_id,
            purpose_code=purpose_code,
            basis_ref=basis_ref,
            launch_profile=launch_profile,
            claim_families=claim_families,
            allowed_source_ids=allowed_source_ids,
            denied_claim_families=denied_claim_families or [],
            scope_digest=scope_digest,
            scope_revision=1,
            approved=False,
            budget_ref=budget_ref,
            expires_at=expires_at,
            valid_time=valid_time,
            jurisdictions=jurisdictions,
            subject_anchors=subject_anchors,
        )

        # Create initial obligations.
        obligations = create_initial_obligations(
            case_id=case_id,
            tenant_id=tenant_id,
            launch_profile=launch_profile,
            anchors=subject_anchors,
            questions=questions or [],
            claim_families=claim_families,
            valid_time=valid_time,
        )
        for obl in obligations:
            await self._store.put_obligation(obl)

        return {
            "case_id": case_id,
            "tenant_id": tenant_id,
            "state": "DRAFT",
            "scope_digest": scope_digest,
            "scope_revision": 1,
            "created_at": now,
            "obligation_count": len(obligations),
        }

    async def get_case(self, *, case_id: str, tenant_id: str) -> dict[str, Any]:
        """Return canonical context plus its tenant-bound person-case sidecar."""
        context = await self._store.get_context(case_id)
        if context is None or context.tenant_id != tenant_id:
            raise CaseNotFound(f"case {case_id} not found")
        meta = await self._store.get_person_case_metadata(case_id)
        if meta is None or meta.get("tenant_id") != tenant_id:
            raise CaseNotFound(f"case {case_id} not found")
        return {
            "case_id": context.context_id,
            "tenant_id": context.tenant_id,
            "state": context.state.value,
            "purpose_code": meta["purpose_code"],
            "purpose_text": context.question,
            "basis_ref": meta["basis_ref"],
            "scope_digest": meta["scope_digest"],
            "scope_revision": meta["scope_revision"],
            "launch_profile": meta["launch_profile"],
            "claim_families": list(meta["claim_families"]),
            "denied_claim_families": list(meta.get("denied_claim_families", [])),
            "allowed_source_ids": list(meta["allowed_source_ids"]),
            "subject_anchors": [dict(a) for a in meta.get("subject_anchors", [])],
            "jurisdictions": list(meta.get("jurisdictions", [])),
            "valid_time": dict(meta.get("valid_time", {})),
            "budget_ref": meta.get("budget_ref"),
            "approved": bool(meta["approved"]),
            "created_at": context.created_at,
            "expires_at": meta.get("expires_at"),
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

        # Fail closed: re-validate against policy every time.
        policy = self._require_policy()
        meta = await self._store.get_person_case_metadata(case_id)
        if meta is None or meta.get("tenant_id") != tenant_id:
            raise CaseNotFound(f"case {case_id} metadata not found")
        if scope_revision != int(meta.get("scope_revision", 0)):
            raise CaseServiceError("SCOPE_STALE: approval revision does not match current scope")
        if scope_digest != meta.get("scope_digest"):
            raise CaseServiceError("SCOPE_STALE: approval digest does not match current scope")
        if not approver_id.strip():
            raise CaseServiceError("approver identity is required")

        decision = policy.validate_case_scope(
            case_id=case_id,
            tenant_id=tenant_id,
            purpose_code=meta["purpose_code"],
            basis_ref=meta["basis_ref"],
            scope_digest=scope_digest,
            scope_revision=scope_revision,
            claim_families=list(meta["claim_families"]),
            allowed_source_ids=list(meta["allowed_source_ids"]),
            expires_at=meta.get("expires_at"),
            launch_profile=meta["launch_profile"],
        )
        if not decision.allowed:
            raise CaseServiceError(f"BLOCKED_POLICY: {decision.detail}")

        # Update metadata (durable). The context itself is not mutated for
        # approval; approval lives in the person-case sidecar record.
        await self._store.put_person_case_metadata(
            case_id=case_id,
            tenant_id=tenant_id,
            purpose_code=meta["purpose_code"],
            basis_ref=meta["basis_ref"],
            launch_profile=meta["launch_profile"],
            claim_families=list(meta["claim_families"]),
            allowed_source_ids=list(meta["allowed_source_ids"]),
            denied_claim_families=list(meta.get("denied_claim_families", [])),
            scope_digest=scope_digest,
            scope_revision=scope_revision,
            approved=True,
            budget_ref=meta.get("budget_ref"),
            expires_at=meta.get("expires_at"),
            valid_time=meta.get("valid_time", {}),
            jurisdictions=list(meta.get("jurisdictions", [])),
            subject_anchors=list(meta.get("subject_anchors", [])),
        )

        return {
            "case_id": case_id,
            "tenant_id": tenant_id,
            "state": "APPROVED",
            "scope_digest": scope_digest,
            "scope_revision": scope_revision,
            "approved_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
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

        meta = await self._store.get_person_case_metadata(case_id)
        if meta is None or meta.get("tenant_id") != tenant_id or not meta.get("approved"):
            raise CaseNotApproved(f"case {case_id} is not approved")
        await self._validate_current_scope(context=context, meta=meta)

        obligations = await self._store.obligations(case_id)
        return {
            "case_id": case_id,
            "tenant_id": tenant_id,
            "scope_digest": meta["scope_digest"],
            "scope_revision": meta["scope_revision"],
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

        meta = await self._store.get_person_case_metadata(case_id)
        if meta is None or meta.get("tenant_id") != tenant_id or not meta.get("approved"):
            raise CaseNotApproved(f"case {case_id} is not approved")
        await self._validate_current_scope(context=context, meta=meta)

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

        # Fail closed: scope staleness check. Any change to scope_digest
        # invalidates queued actions and reservations.
        # (In production, compare stored digest against current plan digest.)

        run_id = f"run-{uuid.uuid4().hex[:12]}"

        # Record the dispatch intent through the existing change publisher
        # seam rather than inventing a new store method.
        await self._store.put_person_case_dispatch_intent(
            case_id=case_id,
            tenant_id=tenant_id,
            run_id=run_id,
            idempotency_key=idempotency_key,
            approved_action_refs=approved_action_refs,
            scope_digest=meta["scope_digest"],
            policy_digest=meta["scope_digest"],
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

        meta = await self._store.get_person_case_metadata(case_id)
        if meta is None:
            raise CaseNotFound(f"case {case_id} metadata not found")

        await self._store.put_person_case_metadata(
            case_id=case_id,
            tenant_id=tenant_id,
            purpose_code=meta["purpose_code"],
            basis_ref=meta["basis_ref"],
            launch_profile=meta["launch_profile"],
            claim_families=list(meta["claim_families"]),
            allowed_source_ids=list(meta["allowed_source_ids"]),
            denied_claim_families=list(meta.get("denied_claim_families", [])),
            scope_digest=meta["scope_digest"],
            scope_revision=meta["scope_revision"],
            approved=meta.get("approved", False),
            budget_ref=meta.get("budget_ref"),
            expires_at=meta.get("expires_at"),
            valid_time=meta.get("valid_time", {}),
            jurisdictions=list(meta.get("jurisdictions", [])),
            subject_anchors=list(meta.get("subject_anchors", [])),
        )

        # Suspend the canonical context without relying on __dict__ on a slots dataclass.
        updated = replace(context, state=InvestigationState.SUSPENDED)
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

        obligations = await self._store.obligations(case_id)
        undisposed = [o for o in obligations if o.status == ObligationStatus.OPEN]
        if undisposed and disposition not in {"BLOCKED", "CANCELLED"}:
            raise CaseServiceError(
                f"cannot close: {len(undisposed)} open obligations not dispositioned"
            )

        updated = replace(context, state=InvestigationState.CLOSED)
        await self._store.put_context(updated)

        return {
            "case_id": case_id,
            "state": "CLOSED",
            "disposition": disposition,
            "report": report or {},
            "closed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _scope_material(
        *,
        tenant_id: str,
        purpose_code: str,
        purpose_text: str,
        basis_ref: str,
        launch_profile: str,
        subject_anchors: list[dict[str, str]],
        jurisdictions: list[str],
        valid_time: dict[str, Any],
        claim_families: list[str],
        denied_claim_families: list[str],
        allowed_source_ids: list[str],
        budget_ref: str | None,
        expires_at: str | None,
        policy_revision: str,
    ) -> dict[str, Any]:
        """Canonical material bound to approval and every downstream task."""
        return {
            "tenant_id": tenant_id,
            "purpose_code": purpose_code,
            "purpose_text": purpose_text,
            "basis_ref": basis_ref,
            "launch_profile": launch_profile,
            "subject_anchors": [dict(a) for a in subject_anchors],
            "jurisdictions": list(jurisdictions),
            "valid_time": dict(valid_time),
            "claim_families": list(claim_families),
            "denied_claim_families": list(denied_claim_families),
            "allowed_source_ids": list(allowed_source_ids),
            "budget_ref": budget_ref,
            "expires_at": expires_at,
            "policy_revision": str(policy_revision),
        }

    def _current_scope_digest(
        self,
        context: InvestigationContext,
        meta: Mapping[str, Any],
    ) -> str:
        payload = self._scope_material(
            tenant_id=context.tenant_id,
            purpose_code=str(meta["purpose_code"]),
            purpose_text=context.question,
            basis_ref=str(meta["basis_ref"]),
            launch_profile=str(meta["launch_profile"]),
            subject_anchors=list(meta.get("subject_anchors", [])),
            jurisdictions=list(meta.get("jurisdictions", [])),
            valid_time=dict(meta.get("valid_time", {})),
            claim_families=list(meta.get("claim_families", [])),
            denied_claim_families=list(meta.get("denied_claim_families", [])),
            allowed_source_ids=list(meta.get("allowed_source_ids", [])),
            budget_ref=meta.get("budget_ref"),
            expires_at=meta.get("expires_at"),
            policy_revision=str(context.policy_snapshot_ref),
        )
        return self._digest(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        )

    async def _validate_current_scope(
        self,
        *,
        context: InvestigationContext,
        meta: Mapping[str, Any],
    ) -> None:
        """Reject stale or no-longer-authorized scope before planning or dispatch."""
        if self._current_scope_digest(context, meta) != meta.get("scope_digest"):
            raise CaseServiceError("SCOPE_STALE: stored scope no longer matches its digest")
        policy = self._require_policy()
        decision = policy.validate_case_scope(
            case_id=context.context_id,
            tenant_id=context.tenant_id,
            purpose_code=str(meta["purpose_code"]),
            basis_ref=meta.get("basis_ref"),
            scope_digest=str(meta["scope_digest"]),
            scope_revision=int(meta["scope_revision"]),
            claim_families=list(meta.get("claim_families", [])),
            allowed_source_ids=list(meta.get("allowed_source_ids", [])),
            expires_at=meta.get("expires_at"),
            launch_profile=str(meta["launch_profile"]),
        )
        if not decision.allowed:
            raise CaseServiceError(f"BLOCKED_POLICY: {decision.detail}")
        if str(decision.policy_revision) != str(context.policy_snapshot_ref):
            raise CaseServiceError("POLICY_STALE: policy revision changed; scope needs review")

    async def _append_case_revision(
        self,
        *,
        context: InvestigationContext,
        snapshot: dict[str, Any],
        actor: str,
        rule: str,
    ) -> None:
        revision_number = await self._store.next_revision_number(context.context_id)
        revision = ContextRevision(
            context_id=context.context_id,
            revision=revision_number,
            parent_revision=revision_number - 1,
            state=context.state,
            snapshot=snapshot,
            operator_actions=(f"{rule}:{actor}",),
            rules_version="feature-034-v1",
            mode="deterministic",
        )
        await self._store.append_revision(revision)

    @staticmethod
    def _digest(material: str) -> str:
        return "sha256:" + hashlib.sha256(material.encode("utf-8")).hexdigest()
