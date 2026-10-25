"""Person case policy gate (Feature 034).

Fail-closed policy evaluation for person-research cases: authority, allowed sources,
claim-family access class, retention, budget, and scope. Every check is a hard gate
-- a missing policy means BLOCKED_POLICY, never a broader investigation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import os
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
        self._sources = {}
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

        # Every requested claim must belong to the vertical's declared ontology.
        profile_spec = profile_for(launch_profile)
        for claim_family in claim_families:
            if claim_family not in profile_spec.allowed_claim_families:
                return PolicyDecision(
                    allowed=False,
                    reason_code="BLOCKED_POLICY",
                    detail=f"claim family {claim_family} is not allowed for this profile",
                )

        # An approved scope must have at least one policy-eligible source. A discovery
        # engine may propose URLs, but it is never silently treated as an evidence source.
        if not allowed_source_ids:
            return PolicyDecision(
                allowed=False,
                reason_code="BLOCKED_POLICY",
                detail="no source selected; cannot approve a collection scope",
            )
        for sid in allowed_source_ids:
            reason = self._source_block_reason(sid, launch_profile)
            if reason:
                return PolicyDecision(
                    allowed=False,
                    reason_code="BLOCKED_POLICY",
                    detail=reason,
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

    def _source_block_reason(self, source_id: str, launch_profile: str) -> str | None:
        """One fail-closed gate shared by approval and per-source eligibility."""
        src = self._sources.get(source_id)
        if src is None:
            return f"source {source_id} is not in the policy allowlist"
        if launch_profile not in self._policy.get("spec", {}).get("case_profiles", []):
            return f"launch profile {launch_profile} is not approved by current policy"
        if launch_profile not in src.get("allowed_case_profiles", []):
            return f"source {source_id} is not allowed for profile {launch_profile}"
        if not src.get("enabled", False):
            return f"source {source_id} is disabled in policy"

        runtime_ref = str(src.get("runtime_ref", "")).strip()
        operation = str(src.get("operation", "")).strip()
        parser = str(src.get("required_response_parser", "")).strip()
        if not runtime_ref or not operation or not parser:
            return f"source {source_id} has an incomplete runtime/operation/parser manifest"

        term_status = str(src.get("term_status", "")).strip()
        allowed_terms = {"PUBLIC_METADATA_API_DOCUMENTED", "DEPLOYMENT_POLICY"}
        if term_status not in allowed_terms:
            return f"source {source_id} terms are not attested for use ({term_status or 'missing'})"
        term_ref = str(src.get("term_policy_ref", "")).strip()
        if not term_ref or term_ref.lower().startswith("owner-attestation-required"):
            return f"source {source_id} has no accepted terms-policy reference"
        if term_status == "DEPLOYMENT_POLICY" and not term_ref.startswith("deployment-policy:"):
            return f"source {source_id} requires an explicit deployment-policy reference"

        license_status = str(src.get("license_status", "")).strip()
        allowed_licenses = {
            "PUBLIC_METADATA_ONLY_ABSTRACTS_SEPARATELY_GATED",
            "NOT_APPLICABLE_INTERNAL_DISCOVERY",
        }
        if license_status not in allowed_licenses:
            return f"source {source_id} licence status is not approved ({license_status or 'missing'})"

        egress_hosts = src.get("egress_hosts")
        if not isinstance(egress_hosts, list) or not egress_hosts or any(
            not isinstance(host, str) or not host.strip() for host in egress_hosts
        ):
            return f"source {source_id} has no explicit egress-host allowlist"

        required_env = src.get("required_env", [])
        if not isinstance(required_env, list):
            return f"source {source_id} required_env manifest is invalid"
        missing_env = [
            name for name in required_env
            if not isinstance(name, str) or not name.strip() or not os.getenv(name, "").strip()
        ]
        if missing_env:
            return f"source {source_id} is missing required environment: {', '.join(missing_env)}"
        return None

    def source_eligible(
        self,
        *,
        source_id: str,
        launch_profile: str,
    ) -> SourceEligibility:
        """Whether a source passes the exact same gate used for approval."""
        if not self._loaded:
            return SourceEligibility(
                source_id=source_id,
                eligible=False,
                reason_code="BLOCKED_POLICY",
                detail="source policy not loaded",
            )
        reason = self._source_block_reason(source_id, launch_profile)
        if reason:
            return SourceEligibility(
                source_id=source_id,
                eligible=False,
                reason_code="BLOCKED_POLICY",
                detail=reason,
            )
        return SourceEligibility(
            source_id=source_id,
            eligible=True,
            reason_code=None,
            detail="eligible under current policy",
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
