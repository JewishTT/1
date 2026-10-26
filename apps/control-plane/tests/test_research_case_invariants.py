"""Regression tests for the formerly broken Feature 034 case lifecycle.

These exercise the canonical Context Engine store and policy; mocked networking is
deliberately absent because creating/revising/approving a case must not collect data.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from context_engine.person_case_profile import PUBLIC_PROFESSIONAL
from context_engine.store import InMemoryContextStore
from services.research_case_policy import PersonCasePolicy
from services.research_case_service import CaseServiceError, ResearchCaseService


@pytest.fixture
def loaded_policy(monkeypatch: pytest.MonkeyPatch) -> PersonCasePolicy:
    monkeypatch.setenv("COGNITIVE_CROSSREF_MAILTO", "research-tests@example.org")
    policy = PersonCasePolicy()
    policy_path = (
        Path(__file__).resolve().parents[2]
        / "acquisition"
        / "policies"
        / "person_case_sources.yaml"
    )
    policy.load(str(policy_path))
    return policy


@pytest.fixture
def service(loaded_policy: PersonCasePolicy) -> tuple[ResearchCaseService, InMemoryContextStore]:
    store = InMemoryContextStore()
    return ResearchCaseService(store=store, policy=loaded_policy), store


def _create_args(**overrides: object) -> dict:
    args = {
        "tenant_id": "tenant-test-034",
        "created_by": "analyst-test",
        "purpose_code": "public_professional",
        "purpose_text": "Verify the publicly documented professional role",
        "basis_ref": "approval-record:TEST-034",
        "launch_profile": PUBLIC_PROFESSIONAL,
        "subject_anchors": [
            {"kind": "public_name", "value": "Public Example", "evidence_ref": "operator:anchor-1"}
        ],
        "jurisdictions": ["LV"],
        "valid_time": {"from": None, "until": None, "precision": "unknown"},
        "claim_families": ["public_authorship_or_publication"],
        "allowed_source_ids": ["crossref_works"],
        "denied_claim_families": [],
        "budget_ref": "budget-test-034",
        "expires_at": None,
        "questions": ["Which official publication supports this public role?"],
    }
    args.update(overrides)
    return args


@pytest.mark.asyncio
async def test_create_uses_canonical_context_id_and_structured_metadata(service) -> None:
    svc, store = service
    created = await svc.create_case(**_create_args())
    case_id = created["case_id"]

    context = await store.get_context(case_id)
    metadata = await store.get_person_case_metadata(case_id)

    assert context is not None
    assert context.context_id == case_id
    assert metadata is not None
    assert metadata["tenant_id"] == "tenant-test-034"
    assert metadata["subject_anchors"][0]["value"] == "Public Example"
    assert metadata["scope_digest"] == created["scope_digest"]
    assert metadata["approved"] is False
    # Metadata must not masquerade as a research obligation.
    obligations = await store.obligations(case_id)
    assert obligations
    assert all(o.question != "__person_case_metadata__" for o in obligations)
    case_view = await svc.get_case(case_id=case_id, tenant_id="tenant-test-034")
    assert case_view["state"] == "DRAFT"
    assert case_view["subject_anchors"][0]["kind"] == "public_name"


@pytest.mark.asyncio
async def test_approval_requires_exact_digest_and_policy_attestation(service) -> None:
    svc, _store = service
    created = await svc.create_case(**_create_args())

    with pytest.raises(CaseServiceError, match="SCOPE_STALE"):
        await svc.approve_case(
            case_id=created["case_id"],
            tenant_id="tenant-test-034",
            approver_id="admin-test",
            scope_digest="sha256:" + "0" * 64,
            scope_revision=1,
        )

    approved = await svc.approve_case(
        case_id=created["case_id"],
        tenant_id="tenant-test-034",
        approver_id="admin-test",
        scope_digest=created["scope_digest"],
        scope_revision=1,
    )
    assert approved["state"] == "APPROVED"
    case_view = await svc.get_case(
        case_id=created["case_id"], tenant_id="tenant-test-034"
    )
    assert case_view["approved"] is True
    assert case_view["state"] == "APPROVED"


@pytest.mark.asyncio
async def test_scope_revision_changes_digest_and_invalidates_approval(service) -> None:
    svc, store = service
    created = await svc.create_case(**_create_args())
    approved = await svc.approve_case(
        case_id=created["case_id"],
        tenant_id="tenant-test-034",
        approver_id="admin-test",
        scope_digest=created["scope_digest"],
        scope_revision=1,
    )
    assert approved["state"] == "APPROVED"

    revised = await svc.revise_scope(
        case_id=created["case_id"],
        tenant_id="tenant-test-034",
        actor_id="analyst-test",
        purpose_code="public_professional",
        purpose_text="Check the publicly documented role for the new interval",
        basis_ref="approval-record:TEST-034-REV2",
        launch_profile=PUBLIC_PROFESSIONAL,
        subject_anchors=[
            {"kind": "public_name", "value": "Public Example", "evidence_ref": "operator:anchor-1"}
        ],
        jurisdictions=["LV"],
        valid_time={"from": "2024-01-01T00:00:00Z", "until": None, "precision": "day"},
        claim_families=["public_authorship_or_publication"],
        allowed_source_ids=["crossref_works"],
        denied_claim_families=[],
        budget_ref="budget-test-034",
        expires_at=None,
    )

    assert revised["scope_revision"] == 2
    assert revised["scope_digest"] != created["scope_digest"]
    assert revised["re_approval_required"] is True
    case_view = await svc.get_case(
        case_id=created["case_id"], tenant_id="tenant-test-034"
    )
    assert case_view["approved"] is False
    assert case_view["scope_revision"] == 2
    assert case_view["purpose_text"] == "Check the publicly documented role for the new interval"
    history = await store.revisions(created["case_id"])
    assert [revision.revision for revision in history] == [1, 2, 3]
    assert all(revision.is_auditable for revision in history)


@pytest.mark.asyncio
async def test_scope_digest_binds_tenant_and_anchor(service) -> None:
    svc, _store = service
    created_a = await svc.create_case(**_create_args())
    created_b = await svc.create_case(
        **_create_args(
            tenant_id="another-tenant",
            subject_anchors=[{"kind": "public_name", "value": "Different Public Example"}],
        )
    )
    assert created_a["scope_digest"] != created_b["scope_digest"]


def test_source_policy_fails_closed_for_unattested_sources(loaded_policy: PersonCasePolicy) -> None:
    blocked = loaded_policy.source_eligible(
        source_id="official_public_page",
        launch_profile=PUBLIC_PROFESSIONAL,
    )
    assert blocked.eligible is False
    assert blocked.reason_code == "BLOCKED_POLICY"
    assert "disabled" in blocked.detail

    discovery = loaded_policy.source_eligible(
        source_id="searxng_public_search",
        launch_profile=PUBLIC_PROFESSIONAL,
    )
    assert discovery.eligible is True
    # Discovery policy is not silently treated as primary evidence.
    result = loaded_policy._sources["searxng_public_search"]
    assert result.get("result_role") == "DISCOVERY_ONLY"



def test_api_create_read_obligations_and_projection_fail_closed(
    service, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.auth import Role, TenantContext, resolve_tenant
    from api.routes import research_cases

    svc, _store = service
    monkeypatch.setattr(research_cases, "_service", svc)
    app = FastAPI()
    app.include_router(research_cases.router, prefix="/api/v1")
    principal = {
        "ctx": TenantContext(
            tenant_id="tenant-test-034",
            user_id="analyst-test",
            roles=frozenset({Role.ANALYST}),
        )
    }
    app.dependency_overrides[resolve_tenant] = lambda: principal["ctx"]
    request_body = _create_args()
    request_body.pop("tenant_id")
    request_body.pop("created_by")

    with TestClient(app) as client:
        created = client.post("/api/v1/research-cases", json=request_body)
        assert created.status_code == 201, created.text
        case_id = created.json()["case_id"]

        read = client.get(f"/api/v1/research-cases/{case_id}")
        assert read.status_code == 200, read.text
        assert read.json()["case_id"] == case_id
        assert read.json()["state"] == "DRAFT"
        assert read.json()["updated_at"] >= read.json()["created_at"]

        obligations = client.get(f"/api/v1/research-cases/{case_id}/obligations")
        assert obligations.status_code == 200, obligations.text
        assert obligations.json()["obligations"]
        assert all("claim_family" not in item for item in obligations.json()["obligations"])

        # An absent projection backend is reported, never emulated from hardcoded data.
        coverage = client.get(f"/api/v1/research-cases/{case_id}/coverage")
        assert coverage.status_code == 503, coverage.text
        assert "not composed" in coverage.json()["detail"]



@pytest.mark.asyncio
async def test_context_amendment_and_dynamic_anchor_append_scope_revision(service) -> None:
    svc, store = service
    created = await svc.create_case(**_create_args())
    case_id = created["case_id"]

    amendment = await svc.append_context_amendment(
        case_id=case_id,
        tenant_id="tenant-test-034",
        actor_id="analyst-test",
        body="Prefer DOI-backed author records for the declared publication question.",
        rationale="Narrow the next plan to explicit source identifiers.",
        kind="query_hint",
    )
    assert amendment["scope_revision"] == 2
    assert amendment["re_approval_required"] is True
    assert amendment["extension"]["value"]["kind"] == "query_hint"

    invariant = await svc.add_dynamic_invariant_anchor(
        case_id=case_id,
        tenant_id="tenant-test-034",
        actor_id="analyst-test",
        kind="orcid",
        value="0000-0002-1825-0097",
        evidence_ref="operator:reviewed-anchor",
        note="Public professional author identifier; identity admission is still required.",
    )
    assert invariant["scope_revision"] == 3
    assert invariant["re_approval_required"] is True
    assert invariant["extension"]["value"]["state"] == "UNRESOLVED"
    assert invariant["extension"]["value"]["admitted_entity_id"] is None

    view = await svc.get_case(case_id=case_id, tenant_id="tenant-test-034")
    assert view["approved"] is False
    assert view["scope_revision"] == 3
    assert [item["ordinal"] for item in view["context_amendments"]] == [1]
    assert [item["ordinal"] for item in view["dynamic_invariant_anchors"]] == [1]
    assert view["scope_digest"] != created["scope_digest"]
    revisions = await store.revisions(case_id)
    assert [revision.revision for revision in revisions] == [1, 2, 3]
    assert all(revision.is_auditable for revision in revisions)
