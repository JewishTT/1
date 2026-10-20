"""Person case policy gate (Feature 034).

Fail-closed policy evaluation for person-research cases: authority, allowed sources,
claim-family access class, retention, budget, and scope. Every check is a hard gate
-- a missing policy means BLOCKED_POLICY, never a broader investigation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import yaml

from context_engine.obligations import KnowledgeType, ResearchObligation, SaturationState
from context_engine.person_case_profile import (
    AUTHORISED_CASE,
    CONSENTED_RECORDS,
    EXCLUDED_CLAIM_FAMILIES,
    LAUNCH_PROFILES,
    PUBLIC_PROFESSIONAL,
    PUBLIC_ROLE_REVIEW,
    initial_obligations,
    profile_for,
)
from domain.investigation_context import ContextEngineError, InvestigationState, ObligationStatus


class PolicyError(ContextEngineError):
    """Policy evaluation failure with a stable reason code."""


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    reason_code: str
    detail: str
    scope_digest: str | None = None
    policy_revision: str | None = None


@dataclass(frozen=True, slots=True)
class SourceEligibility:
    source_id: str
    eligible: bool
    reason_code: str | None
    detail: str


class PersonCasePolicy:
    """Fail-closed policy gate for person-research cases."""

    def __init__(self, policy_path: str | None = None) -> None:
        self._policy_path = policy_path
        self._policy: dict[str, Any] = {}
        self._sources: dict[str, dict[str, Any]] = {}
        self._loaded = False

    def load(self, path: str | None = None) -> None:
        """Load the source policy YAML. Missing file = fail closed."""
        target = path or self._policy_path
        if target is None:
            raise PolicyError(
                "policy_not_configured",
                "no person-case source policy path configured; fail closed",
            )
        try:
            with open(target, encoding="utf-8") as fh:
                self._policy = yaml.safe_load(fh) or {}
        except FileNotFoundError as exc:
            raise PolicyError(
                "policy_file_missing",
                f"source policy not found at {target}; fail closed",
            ) from exc
        except yaml.YAMLError as exc:
            raise PolicyError(
                "policy_file_invalid",
                f"source policy YAML invalid: {exc}",
            ) from exc
        spec = self._policy.get("spec", {})
        for src in spec.get("source_profiles", []):
            self._sources[str(src.get("source_id"))] = src
        self._loaded = True

    @property
    def loaded(self) -> bool:
        return self._loaded

    def default_deny(self) -> bool:
        return self._policy.get("spec", {}).get("default", "deny") == "deny"

    def excluded_claim_families(self) -> frozenset[str]:
        return frozenset(
            self._policy.get("spec", {}).get("excluded_claim_families", [])
        )

    def case_profiles(self) -> frozenset[str]:
        return frozenset(self._policy.get("spec", {}).get("case_profiles", []))

    def validate_case_scope(
        self,
        *,
        case_id: str,
        tenant_id: str,
        purpose_code: str,
        basis_ref: str | None,
        scope_digest: str,
        scope_revision: int,
        claim_families: list[str],
        allowed_source_ids: list[str],
        expires_at: str | None,
        launch_profile: str,
    ) -> PolicyDecision:
        """Validate a proposed case scope before any acquisition.

        Fail closed: missing basis, unknown profile, excluded claim family,
        unknown source, or expired scope => BLOCKED_POLICY.
        """
        if not self._loaded:
            return PolicyDecision(
                allowed=False,
                reason_code="BLOCKED_POLICY",
                detail="source policy not loaded",
            )

        # Basis must be present and non-empty.
        if not basis_ref or not str(basis_ref).strip():
            return PolicyDecision(
                allowed=False,
                reason_code="BLOCKED_POLICY",
                detail="basis_ref is required; unknown or empty basis blocks the case",
            )

        # Launch profile must be known.
        if launch_profile not in LAUNCH_PROFILES:
            return PolicyDecision(
                allowed=False,
                reason_code="BLOCKED_POLICY",
                detail=f"unknown launch profile: {launch_profile}",
            )

        # AUTHORISED_CASE requires explicit approval (handled by the service layer;
        # here we only check the profile is declared).
        if launch_profile == AUTHORISED_CASE and not basis_ref:
            return PolicyDecision(
                allowed=False,
                reason_code="BLOCKED_POLICY",
                detail="AUTHORISED_CASE requires a valid basis_ref and compliance approval",
            )

        # Claim families: none may be excluded.
        excluded = self.excluded_claim_families()
        for cf in claim_families:
            if cf in excluded:
                return PolicyDecision(
                    allowed=False,
                    reason_code="BLOCKED_POLICY",
                    detail=f"claim family {cf} is excluded for this vertical",
                )

        # Source allowlist: every source must exist in the policy.
        for sid in allowed_source_ids:
            if sid not in self._sources:
                return PolicyDecision(
                    allowed=False,
                    reason_code="BLOCKED_POLICY",
                    detail=f"source {sid} not in source policy allowlist",
                )
            src = self._sources[sid]
            if launch_profile not in src.get("allowed_case_profiles", []):
                return PolicyDecision(
                    allowed=False,
                    reason_code="BLOCKED_POLICY",
                    detail=f"source {sid} not allowed for profile {launch_profile}",
                )
            if not src.get("enabled", False):
                return PolicyDecision(
                    allowed=False,
                    reason_code="BLOCKED_POLICY",
                    detail=f"source {sid} is disabled in policy",
                )

        # Expiry must be in the future.
        if expires_at:
            try:
                exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if exp <= datetime.now(UTC):
                    return PolicyDecision(
                        allowed=False,
                        reason_code="BLOCKED_POLICY",
                        detail="case scope has expired",
                    )
            except ValueError:
                return PolicyDecision(
                    allowed=False,
                    reason_code="BLOCKED_POLICY",
                    detail="expires_at is not a valid RFC3339 timestamp",
                )

        return PolicyDecision(
            allowed=True,
            reason_code="READY",
            detail="scope validated against source policy",
            scope_digest=scope_digest,
            policy_revision=self._policy.get("metadata", {}).get("version", "1"),
        )

    def source_eligible(
        self,
        *,
        source_id: str,
        launch_profile: str,
    ) -> SourceEligibility:
        """Whether a source may be used for a given launch profile."""
        if not self._loaded:
            return SourceEligibility(
                source_id=source_id,
                eligible=False,
                reason_code="BLOCKED_POLICY",
                detail="source policy not loaded",
            )
        src = self._sources.get(source_id)
        if src is None:
            return SourceEligibility(
                source_id=source_id,
                eligible=False,
                reason_code="SOURCE_UNAVAILABLE",
                detail=f"source {source_id} not in policy",
            )
        if launch_profile not in src.get("allowed_case_profiles", []):
            return SourceEligibility(
                source_id=source_id,
                eligible=False,
                reason_code="POLICY_BLOCKED",
                detail=f"source {source_id} not allowed for profile {launch_profile}",
            )
        if not src.get("enabled", False):
            return SourceEligibility(
                source_id=source_id,
                eligible=False,
                reason_code="SOURCE_UNAVAILABLE",
                detail=f"source {source_id} disabled",
            )
        return SourceEligibility(
            source_id=source_id,
            eligible=True,
            reason_code=None,
            detail="eligible",
        )

    def scope_stale(
        self,
        *,
        stored_digest: str,
        current_digest: str,
    ) -> bool:
        """Whether a stored scope digest differs from the current one."""
        return stored_digest != current_digest


# -- obligation creation -------------------------------------------------------


def create_initial_obligations(
    *,
    case_id: str,
    tenant_id: str,
    launch_profile: str,
    anchors: list[dict[str, str]],
    questions: list[str],
    claim_families: list[str],
    valid_time: dict[str, Any],
) -> list[ResearchObligation]:
    """Create the initial obligations for a new case from its profile."""
    profile = profile_for(launch_profile)
    return initial_obligations(
        case_id=case_id,
        tenant_id=tenant_id,
        profile=profile,
        anchors=anchors,
        questions=questions,
        claim_families=claim_families,
        valid_time=valid_time,
    )
