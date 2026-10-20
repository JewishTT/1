"""Person case profile pack (Feature 034).

Declarative obligation templates, allowed claim families, and scoped completeness
policy for the person-research vertical. This is a *pack*, not a separate engine:
it produces initial obligations from anchors and questions, and the existing
planner / frontier / dispatcher execute them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from context_engine.obligations import KnowledgeType, ResearchObligation, SaturationState


@dataclass(frozen=True, slots=True)
class ObligationTemplate:
    """One obligation template: question, evidence type, capabilities, condition."""

    code: str
    question: str
    claim_family: str
    required_evidence_types: tuple[str, ...]
    capabilities: tuple[str, ...]
    scope_condition: str
    satisfaction_condition: str


#: Allowed claim families for the person-research vertical (v1).
#: These describe sourced assertions, not truth.
ALLOWED_CLAIM_FAMILIES: tuple[str, ...] = (
    "public_name_as_published",
    "public_professional_role",
    "public_organization_affiliation",
    "public_authorship_or_publication",
    "public_statement_or_official_action",
    "public_award_or_appointment",
    "public_event_participation",
    "public_registry_record",
    "source_document_metadata",
)

#: Excluded claim families -- never obligated, never satisfied by this vertical.
EXCLUDED_CLAIM_FAMILIES: tuple[str, ...] = (
    "private_contact",
    "precise_home_address",
    "private_relationship",
    "credential",
    "breach_data",
    "biometric_identity",
    "individual_location_tracking",
    "sensitive_inference",
)

#: Launch profiles.
PUBLIC_PROFESSIONAL = "PUBLIC_PROFESSIONAL"
PUBLIC_ROLE_REVIEW = "PUBLIC_ROLE_REVIEW"
CONSENTED_RECORDS = "CONSENTED_RECORDS"
AUTHORISED_CASE = "AUTHORISED_CASE"

LAUNCH_PROFILES: frozenset[str] = frozenset(
    {PUBLIC_PROFESSIONAL, PUBLIC_ROLE_REVIEW, CONSENTED_RECORDS, AUTHORISED_CASE}
)


@dataclass(frozen=True, slots=True)
class PersonCaseProfile:
    """A declarative obligation pack for one case."""

    profile: str
    obligations: tuple[ObligationTemplate, ...]
    allowed_claim_families: tuple[str, ...] = ALLOWED_CLAIM_FAMILIES
    denied_claim_families: tuple[str, ...] = EXCLUDED_CLAIM_FAMILIES
    completeness_policy: str = "coverage_of_approved_scope_only"


#: Default obligation templates. Each has a specific answer type, scope, and
#: satisfaction condition -- none is "find everything".
DEFAULT_OBLIGATIONS: tuple[ObligationTemplate, ...] = (
    ObligationTemplate(
        code="PC-PROFILE-001",
        question="Подтвердить публичную профессиональную биографию",
        claim_family="public_bio",
        required_evidence_types=("official_record", "primary_publication"),
        capabilities=("public_search", "official_web_fetch", "html_parse"),
        scope_condition="organizations and institutions named in the anchor",
        satisfaction_condition="at least one primary public source confirms the biography",
    ),
    ObligationTemplate(
        code="PC-ROLE-002",
        question="Верифицировать публичную должность за заданный период",
        claim_family="public_professional_role",
        required_evidence_types=("official_record", "primary_publication"),
        capabilities=("official_registry_search", "document_capture", "temporal_extract"),
        scope_condition="the role and interval declared in the case scope",
        satisfaction_condition="an official source states the role with valid_from/valid_until covering the asked interval",
    ),
    ObligationTemplate(
        code="PC-PUB-003",
        question="Найти публикации/материалы, прямо заявленные в scope",
        claim_family="publication",
        required_evidence_types=("publisher_record", "repository_record"),
        capabilities=("search", "scholarly_metadata_parse", "document_parser"),
        scope_condition="publications directly tied to the subject in scope",
        satisfaction_condition="publisher or repository record for each claimed publication",
    ),
    ObligationTemplate(
        code="PC-AFF-004",
        question="Проверить конкретную публичную организационную аффилиацию",
        claim_family="public_organization_affiliation",
        required_evidence_types=("registry_record", "official_statement"),
        capabilities=("curated_registry_connector", "claim_extraction"),
        scope_condition="affiliation within the case's valid_time interval",
        satisfaction_condition="registry or official statement with exact time frame",
    ),
    ObligationTemplate(
        code="PC-CONFLICT-005",
        question="Разобрать противоречащие друг другу даты/должности",
        claim_family="public_professional_role",
        required_evidence_types=("primary_record", "primary_record"),
        capabilities=("targeted_search", "temporal_comparison", "source_lineage"),
        scope_condition="contradicting intervals on the same role",
        satisfaction_condition="both primary references resolved, or reason recorded why they cannot be",
    ),
    ObligationTemplate(
        code="PC-ID-006",
        question="Разрешить неоднозначность однофамильца",
        claim_family="public_name_as_published",
        required_evidence_types=("independent_source", "independent_source"),
        capabilities=("blocking", "pair_comparison", "analyst_review"),
        scope_condition="same-name candidates with overlapping public attributes",
        satisfaction_condition="at least two independent discriminators from allowed fields",
    ),
    ObligationTemplate(
        code="PC-GAP-007",
        question="Закрыть вопрос с отсутствующими доказательствами",
        claim_family="coverage",
        required_evidence_types=(),
        capabilities=("capability_registry", "coverage_ledger"),
        scope_condition="an in-scope claim with zero observations",
        satisfaction_condition="coverage ledger records the gap with reason code",
    ),
)


def profile_for(launch_profile: str) -> PersonCaseProfile:
    """Build the obligation pack for a launch profile.

    Every profile starts from the same templates; profile only gates which
    claim families and source classes are permitted. No profile grants "all".
    """
    if launch_profile not in LAUNCH_PROFILES:
        raise ValueError(f"unknown launch profile: {launch_profile}")
    return PersonCaseProfile(
        profile=launch_profile,
        obligations=DEFAULT_OBLIGATIONS,
    )


def initial_obligations(
    *,
    case_id: str,
    tenant_id: str,
    profile: PersonCaseProfile,
    anchors: list[dict[str, str]],
    questions: list[str],
    claim_families: list[str],
    valid_time: dict[str, Any],
) -> list[ResearchObligation]:
    """Create the initial obligations for a case from anchors and questions.

    Each obligation is bound to the case, tenant, and profile, and carries a
    satisfaction condition that can be checked against observations.
    """
    obligations: list[ResearchObligation] = []
    for index, tmpl in enumerate(profile.obligations):
        # Skip templates whose claim family is not allowed for this case.
        if tmpl.claim_family not in profile.allowed_claim_families:
            continue
        if tmpl.claim_family in profile.denied_claim_families:
            continue
        obligation_id = f"OBL-{case_id[:8]}-{index:03d}"
        obligations.append(
            ResearchObligation(
                obligation_id=obligation_id,
                case_id=case_id,
                tenant_id=tenant_id,
                question=tmpl.question,
                claim_family=tmpl.claim_family,
                required_evidence_types=tmpl.required_evidence_types,
                capabilities=list(tmpl.capabilities),
                scope_condition=tmpl.scope_condition,
                satisfaction_condition=tmpl.satisfaction_condition,
                state="NOT_PLANNED",
                knowledge_type=KnowledgeType.ATTRIBUTE,
                saturation=SaturationState(
                    coverage=0.0,
                    coverage_known=False,
                    marginal_gain=0.0,
                    marginal_gain_known=False,
                    distinct_sources=0,
                    source_diversity=0,
                    stopping_condition="not_started",
                    coverage_threshold=1.0,
                    marginal_gain_threshold=0.05,
                ),
            )
        )
    # Add one obligation per explicit question not covered by templates.
    for q_index, question in enumerate(questions):
        obligations.append(
            ResearchObligation(
                obligation_id=f"OBL-{case_id[:8]}-Q{q_index:03d}",
                case_id=case_id,
                tenant_id=tenant_id,
                question=question,
                claim_family="public_bio",
                required_evidence_types=(),
                capabilities=("public_search",),
                scope_condition="question as stated",
                satisfaction_condition="an anchored observation answers the question",
                state="NOT_PLANNED",
                knowledge_type=KnowledgeType.ATTRIBUTE,
                saturation=SaturationState(
                    coverage=0.0,
                    coverage_known=False,
                    marginal_gain=0.0,
                    marginal_gain_known=False,
                    distinct_sources=0,
                    source_diversity=0,
                    stopping_condition="not_started",
                    coverage_threshold=1.0,
                    marginal_gain_threshold=0.05,
                ),
            )
        )
    return obligations


def is_claim_family_allowed(claim_family: str, profile: PersonCaseProfile) -> bool:
    """Whether a claim family may be obligated under this profile."""
    if claim_family in profile.denied_claim_families:
        return False
    return claim_family in profile.allowed_claim_families
