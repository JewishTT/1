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
        dispatch_executor: Any = None,
    ) -> None:
        self._store = store
        self._loop = loop
        self._policy = policy
        self._model_gateway = model_gateway
        self._budget_service = budget_service
        self._artifact_sink = artifact_sink
        self._observation_gate = observation_gate
        self._dispatch_executor = dispatch_executor

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
        if context.state == InvestigationState.CLOSED:
            case_state = "CLOSED"
        elif context.state == InvestigationState.SUSPENDED:
            case_state = "PAUSED"
        elif context.state == InvestigationState.ACTIVE:
            case_state = "RUNNING"
        elif meta.get("approved"):
            case_state = "APPROVED"
        else:
            case_state = "DRAFT"
        return {
            "case_id": context.context_id,
            "tenant_id": context.tenant_id,
            "state": case_state,
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
            "updated_at": context.created_at,
            "expires_at": meta.get("expires_at"),
        }

    async def revise_scope(
        self,
        *,
        case_id: str,
        tenant_id: str,
        actor_id: str,
        purpose_code: str,
        purpose_text: str,
        basis_ref: str,
        launch_profile: str,
        subject_anchors: list[dict[str, str]],
        jurisdictions: list[str],
        valid_time: dict[str, Any],
        claim_families: list[str],
        allowed_source_ids: list[str],
        denied_claim_families: list[str],
        budget_ref: str | None,
        expires_at: str | None,
    ) -> dict[str, Any]:
        """Replace the declared scope as a new revision and invalidate approval."""
        context = await self._store.get_context(case_id)
        if context is None or context.tenant_id != tenant_id:
            raise CaseNotFound(f"case {case_id} not found")
        if context.state == InvestigationState.CLOSED:
            raise CaseServiceError("a closed case cannot receive a new scope revision")
        if not actor_id.strip():
            raise CaseServiceError("scope revision actor is required")
        if launch_profile not in {
            PUBLIC_PROFESSIONAL,
            PUBLIC_ROLE_REVIEW,
            CONSENTED_RECORDS,
            AUTHORISED_CASE,
        }:
            raise CaseServiceError(f"unknown launch profile: {launch_profile}")
        if not subject_anchors or any(
            not str(anchor.get("kind", "")).strip()
            or not str(anchor.get("value", "")).strip()
            for anchor in subject_anchors
        ):
            raise CaseServiceError("at least one typed, non-empty subject anchor is required")

        previous = await self._store.get_person_case_metadata(case_id)
        if previous is None or previous.get("tenant_id") != tenant_id:
            raise CaseNotFound(f"case {case_id} not found")
        policy = self._require_policy()
        policy_revision = str(policy._policy.get("metadata", {}).get("version", "1"))
        scope_revision = int(previous.get("scope_revision", 0)) + 1
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
            denied_claim_families=denied_claim_families,
            allowed_source_ids=allowed_source_ids,
            budget_ref=budget_ref,
            expires_at=expires_at,
            policy_revision=policy_revision,
        )
        scope_digest = self._digest(
            json.dumps(scope_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        )
        updated_context = replace(
            context,
            question=purpose_text,
            state=InvestigationState.UNINVESTIGATED,
            policy_snapshot_ref=policy_revision,
        )
        # Existing context identity is stable; mutable scope lives in its append-only
        # revision snapshot and the canonical metadata sidecar.
        await self._store.put_context(updated_context)
        await self._store.put_person_case_metadata(
            case_id=case_id,
            tenant_id=tenant_id,
            purpose_code=purpose_code,
            basis_ref=basis_ref,
            launch_profile=launch_profile,
            claim_families=claim_families,
            allowed_source_ids=allowed_source_ids,
            denied_claim_families=denied_claim_families,
            scope_digest=scope_digest,
            scope_revision=scope_revision,
            approved=False,
            budget_ref=budget_ref,
            expires_at=expires_at,
            valid_time=valid_time,
            jurisdictions=jurisdictions,
            subject_anchors=subject_anchors,
        )
        await self._append_case_revision(
            context=updated_context,
            snapshot={
                "context": updated_context.to_dict(),
                "person_case_scope": scope_payload,
                "scope_digest": scope_digest,
                "scope_revision": scope_revision,
                "approved": False,
                "supersedes_scope_revision": previous.get("scope_revision"),
            },
            actor=actor_id,
            rule="scope_revision",
        )
        return {
            "case_id": case_id,
            "scope_revision": scope_revision,
            "scope_digest": scope_digest,
            "re_approval_required": True,
            "stale_scope_behavior": "CANCELLED_STALE_SCOPE",
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
        if self._current_scope_digest(context, meta) != meta.get("scope_digest"):
            raise CaseServiceError("SCOPE_STALE: current scope does not match its stored digest")

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
        if str(decision.policy_revision) != str(context.policy_snapshot_ref):
            raise CaseServiceError("POLICY_STALE: policy revision changed; revise the scope before approval")

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
        await self._append_case_revision(
            context=context,
            snapshot={
                "context": context.to_dict(),
                "person_case_scope": self._scope_material(
                    tenant_id=tenant_id,
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
                ),
                "scope_digest": scope_digest,
                "scope_revision": scope_revision,
                "approved": True,
                "approved_by": approver_id,
                "policy_revision": str(decision.policy_revision),
            },
            actor=approver_id,
            rule="approve_scope",
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
        """Return a read-only capability/obligation preview, never a fake plan."""
        context = await self._store.get_context(case_id)
        if context is None or context.tenant_id != tenant_id:
            raise CaseNotFound(f"case {case_id} not found")
        if context.state in {InvestigationState.CLOSED, InvestigationState.SUSPENDED}:
            raise CaseServiceError(f"cannot plan a {context.state.value.lower()} case")

        meta = await self._store.get_person_case_metadata(case_id)
        if meta is None or meta.get("tenant_id") != tenant_id or not meta.get("approved"):
            raise CaseNotApproved(f"case {case_id} is not approved")
        await self._validate_current_scope(context=context, meta=meta)

        obligations = await self._store.obligations(case_id)
        profile = profile_for(str(meta["launch_profile"]))
        family_by_criterion = {
            template.code: template.claim_family for template in profile.obligations
        }
        obligation_views: list[dict[str, Any]] = []
        required_caps: set[str] = set()
        eligible_caps: set[str] = set()
        capability_gaps: list[dict[str, Any]] = []
        for obligation in obligations:
            families = sorted({
                family_by_criterion[criterion.criterion_id]
                for criterion in obligation.acceptance_criteria
                if criterion.criterion_id in family_by_criterion
            })
            required = sorted(set(obligation.required_capabilities))
            eligible = sorted(set(obligation.eligible_capabilities))
            missing = sorted(set(required) - set(eligible))
            required_caps.update(required)
            eligible_caps.update(eligible)
            if missing:
                capability_gaps.append({
                    "obligation_id": obligation.obligation_id,
                    "required": missing,
                    "detail": "No eligible runtime has been bound to this obligation yet.",
                })
            obligation_views.append({
                "obligation_id": obligation.obligation_id,
                "question": obligation.question,
                "claim_family": families[0] if len(families) == 1 else None,
                "claim_families": families,
                "state": obligation.status.value,
                "target_knowledge_type": obligation.target_knowledge_type.value,
                "required_capabilities": required,
                "eligible_capabilities": eligible,
                "missing_capabilities": missing,
                "satisfaction_condition": list(obligation.satisfaction_criteria),
                "acceptance_criteria": [criterion.to_dict() for criterion in obligation.acceptance_criteria],
                "scope_condition": obligation.rationale,
                "priority": obligation.priority,
                "priority_basis": obligation.priority_basis,
            })

        runtime_ready = bool(
            self._budget_service is not None
            and self._artifact_sink is not None
            and self._observation_gate is not None
            and getattr(self, "_dispatch_executor", None) is not None
        )
        status = (
            "BLOCKED_CAPABILITY" if capability_gaps
            else "READY_FOR_REVIEW" if runtime_ready
            else "BLOCKED_RUNTIME"
        )
        return {
            "case_id": case_id,
            "tenant_id": tenant_id,
            "scope_digest": meta["scope_digest"],
            "scope_revision": meta["scope_revision"],
            "obligations": obligation_views,
            "required_capabilities": sorted(required_caps),
            "capabilities_preview": sorted(eligible_caps),
            "capability_gaps": capability_gaps,
            "plan_state": status,
            "ready_to_dispatch": runtime_ready and not capability_gaps,
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
        """Dispatch only a durable approved plan, and never simulate execution."""
        if not idempotency_key.strip():
            raise CaseServiceError("idempotency_key is required")
        if not approved_action_refs:
            raise CaseServiceError("approved_action_refs must contain at least one reviewed action")

        context = await self._store.get_context(case_id)
        if context is None or context.tenant_id != tenant_id:
            raise CaseNotFound(f"case {case_id} not found")
        if context.state in {InvestigationState.CLOSED, InvestigationState.SUSPENDED}:
            raise CaseServiceError(f"cannot run a {context.state.value.lower()} case")

        meta = await self._store.get_person_case_metadata(case_id)
        if meta is None or meta.get("tenant_id") != tenant_id or not meta.get("approved"):
            raise CaseNotApproved(f"case {case_id} is not approved")
        await self._validate_current_scope(context=context, meta=meta)

        # Resolve every caller-supplied ref against durable actions on this case;
        # a string in an HTTP request is not itself an operator approval.
        by_id: dict[str, Any] = {}
        for obligation in await self._store.obligations(case_id):
            for action in await self._store.actions(obligation.obligation_id):
                by_id[action.action_id] = action
        missing = sorted(set(approved_action_refs) - set(by_id))
        if missing:
            raise CaseServiceError(f"action references do not belong to this case: {missing}")
        unapproved = sorted(
            action_id
            for action_id in set(approved_action_refs)
            if by_id[action_id].status != "approved" or by_id[action_id].requires_operator_approval
        )
        if unapproved:
            raise CaseServiceError(f"actions lack a durable approval decision: {unapproved}")

        # A budget reservation alone does not prove acquisition is reachable. Require
        # the real runtime pieces; never create a dispatch intent and report RUNNING
        # when the dispatcher/artifact path is absent.
        if self._budget_service is None:
            raise BudgetNotReserved(
                "budget service is not configured; no reservation can be verified"
            )
        reserved = await self._budget_service.has_reservation(
            case_id=case_id, tenant_id=tenant_id
        )
        if not reserved:
            raise BudgetNotReserved(
                f"no durable budget reservation for case {case_id}; dispatch blocked"
            )
        dispatcher = getattr(self, "_dispatch_executor", None)
        if (
            dispatcher is None
            or self._artifact_sink is None
            or self._observation_gate is None
            or not callable(getattr(dispatcher, "dispatch_case", None))
        ):
            raise CaseServiceError(
                "BLOCKED_RUNTIME: production dispatcher, ArtifactSink and ObservationGate "
                "must be composed before a run can be started"
            )

        run_id = f"run-{uuid.uuid4().hex[:12]}"
        intent = await self._store.put_person_case_dispatch_intent(
            case_id=case_id,
            tenant_id=tenant_id,
            run_id=run_id,
            idempotency_key=idempotency_key,
            approved_action_refs=list(approved_action_refs),
            scope_digest=meta["scope_digest"],
            policy_digest=meta["scope_digest"],
        )
        if not intent.get("created", True):
            return {
                "case_id": case_id,
                "run_id": intent["run_id"],
                "idempotency_key": idempotency_key,
                "state": "ALREADY_REQUESTED",
                "dispatch_intent_created": False,
            }

        outcome = await dispatcher.dispatch_case(
            case_id=case_id,
            tenant_id=tenant_id,
            run_id=run_id,
            idempotency_key=idempotency_key,
            approved_action_refs=list(approved_action_refs),
            scope_digest=meta["scope_digest"],
            policy_digest=meta["scope_digest"],
            budget_ref=meta.get("budget_ref"),
            launch_profile=meta["launch_profile"],
            allowed_source_ids=list(meta["allowed_source_ids"]),
        )
        if not isinstance(outcome, Mapping) or not outcome.get("published"):
            raise CaseServiceError(
                "dispatcher did not confirm broker-acknowledged publication; case remains approved"
            )

        updated = replace(context, state=InvestigationState.ACTIVE)
        await self._store.put_context(updated)
        await self._append_case_revision(
            context=updated,
            snapshot={
                "context": updated.to_dict(),
                "run_id": run_id,
                "dispatch_intent": dict(intent),
                "dispatch_outcome": dict(outcome),
                "scope_digest": meta["scope_digest"],
                "scope_revision": meta["scope_revision"],
            },
            actor="system:dispatcher",
            rule="dispatch_started",
        )
        return {
            "case_id": case_id,
            "run_id": run_id,
            "idempotency_key": idempotency_key,
            "state": "RUNNING",
            "dispatch_intent_created": True,
            "dispatch": dict(outcome),
        }

    # -- pause --------------------------------------------------------------

    async def pause_case(
        self,
        *,
        case_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        """Pause dispatch with an append-only lifecycle revision."""
        context = await self._store.get_context(case_id)
        if context is None or context.tenant_id != tenant_id:
            raise CaseNotFound(f"case {case_id} not found")
        if context.state == InvestigationState.CLOSED:
            raise CaseServiceError("closed case cannot be paused")
        if context.state == InvestigationState.SUSPENDED:
            return {"case_id": case_id, "state": "PAUSED", "already_paused": True}

        meta = await self._store.get_person_case_metadata(case_id)
        if meta is None or meta.get("tenant_id") != tenant_id:
            raise CaseNotFound(f"case {case_id} not found")
        # A paused case must be explicitly approved again if resumed through a future
        # execution path; preserving an old approval bit must not restore dispatch rights.
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
            approved=False,
            budget_ref=meta.get("budget_ref"),
            expires_at=meta.get("expires_at"),
            valid_time=meta.get("valid_time", {}),
            jurisdictions=list(meta.get("jurisdictions", [])),
            subject_anchors=list(meta.get("subject_anchors", [])),
        )
        updated = replace(context, state=InvestigationState.SUSPENDED)
        await self._store.put_context(updated)
        await self._append_case_revision(
            context=updated,
            snapshot={
                "context": updated.to_dict(),
                "lifecycle_action": "PAUSE",
                "scope_digest": meta["scope_digest"],
                "scope_revision": meta["scope_revision"],
                "approval_revoked": True,
            },
            actor="system:pause",
            rule="pause_case",
        )
        return {"case_id": case_id, "state": "PAUSED", "approval_revoked": True}

    # -- close --------------------------------------------------------------

    async def close_case(
        self,
        *,
        case_id: str,
        tenant_id: str,
        disposition: str,
        report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Close a case only with a supported terminal disposition."""
        allowed_dispositions = {
            "COMPLETE", "PARTIAL", "BLOCKED", "CANCELLED", "CLOSED_WITH_NO_FINDING"
        }
        if disposition not in allowed_dispositions:
            raise CaseServiceError(f"unsupported terminal disposition: {disposition}")
        context = await self._store.get_context(case_id)
        if context is None or context.tenant_id != tenant_id:
            raise CaseNotFound(f"case {case_id} not found")
        if context.state == InvestigationState.CLOSED:
            raise CaseServiceError("case is already closed")

        obligations = await self._store.obligations(case_id)
        undisposed = [o for o in obligations if o.status == ObligationStatus.OPEN]
        if undisposed and disposition not in {"BLOCKED", "CANCELLED"}:
            raise CaseServiceError(
                f"cannot close: {len(undisposed)} open obligations not dispositioned"
            )

        updated = replace(context, state=InvestigationState.CLOSED)
        await self._store.put_context(updated)
        closed_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        await self._append_case_revision(
            context=updated,
            snapshot={
                "context": updated.to_dict(),
                "lifecycle_action": "CLOSE",
                "disposition": disposition,
                "report": report or {},
                "closed_at": closed_at,
            },
            actor="system:close",
            rule="close_case",
        )
        return {
            "case_id": case_id,
            "state": "CLOSED",
            "disposition": disposition,
            "report": report or {},
            "closed_at": closed_at,
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
