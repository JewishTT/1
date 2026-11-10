from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP))

from industry_adapters.capabilities import blocked_capability_reason, require_approved_capability  # noqa: E402
from industry_adapters.followthemoney import FtMExportError, build_ftm_export, stable_ftm_id  # noqa: E402
from industry_adapters.theharvester import AuthorizationError, AuthorizationScope, TheHarvesterApiClient, normalize_findings  # noqa: E402


def scope(**kwargs):
    values = {
        "tenant_id": "TENANT-1",
        "authorization_ref": "AUTH-1",
        "allowed_domains": ("example.org",),
        "expires_at": datetime.now(UTC) + timedelta(hours=1),
    }
    values.update(kwargs)
    return AuthorizationScope(**values)


def test_authorized_domain_uses_label_boundary_and_time_bound():
    allowed = scope()
    assert allowed.assert_domain("portal.example.org") == "portal.example.org"
    assert allowed.assert_domain("example.org") == "example.org"
    assert not allowed.contains_domain("example.org.attacker.invalid")
    assert not allowed.contains_domain("notexample.org")
    with pytest.raises(AuthorizationError):
        allowed.assert_domain("example.net")


def test_authorization_expiry_fails_closed():
    expired = scope(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    with pytest.raises(AuthorizationError):
        expired.assert_domain("example.org")


@pytest.mark.parametrize("value", ["https://example.org", "192.0.2.1", "example.org/path", "bad..example.org"])
def test_only_bare_dns_domains_are_accepted(value):
    with pytest.raises(ValueError):
        normalize_findings([{"type": "hostname", "value": value}], scope(), target="example.org")


def test_theharvester_request_selects_only_passive_subdomain_capability():
    request = TheHarvesterApiClient.safe_run_request("example.org")
    assert request["sources"] == ["subdomains"]
    assert request["limit"] == 500
    assert request["deadline_seconds"] == 600
    assert not any(key in request for key in (
        "dns_brute", "dns_lookup", "takeover", "screenshot", "vhost", "api_scan", "people", "emails"
    ))


def test_export_normalization_filters_sensitive_and_out_of_scope_records():
    rows = [
        {"type": "hostname", "value": "mail.example.org", "sources": ["crtsh"]},
        {"type": "hostname", "value": "example.org.attacker.invalid", "sources": ["crtsh"]},
        {"type": "ip", "value": "192.0.2.7", "sources": ["crtsh"]},
        {"type": "asn", "value": "AS64500", "sources": ["routeviews"]},
        {"type": "email", "value": "person@example.org", "sources": ["provider"]},
        {"type": "person", "value": "Example Person", "sources": ["provider"]},
    ]
    records, filtered = normalize_findings(rows, scope(), target="example.org")
    assert [(item.kind, item.value) for item in records] == [
        ("asn", "AS64500"),
        ("hostname", "mail.example.org"),
        ("ip", "192.0.2.7"),
    ]
    assert all(not item.expandable for item in records if item.kind in {"ip", "asn"})
    assert next(item for item in records if item.kind == "hostname").expandable
    assert filtered["email"] == 1
    assert filtered["person"] == 1
    assert filtered["hostname"] == 1


def test_stable_ftm_id_is_tenant_scoped():
    assert stable_ftm_id("tenant-a", "entity-1") == stable_ftm_id("tenant-a", "entity-1")
    assert stable_ftm_id("tenant-a", "entity-1") != stable_ftm_id("tenant-b", "entity-1")


def test_ftm_export_is_curated_and_provenance_is_separate():
    exported = build_ftm_export(
        tenant_id="tenant-a",
        entity_id="ENT-1",
        schema="Company",
        properties={
            "name": "Example Ltd",
            "registrationNumber": "123",
            "jurisdiction": "GB",
            "email": "private@example.org",
            "address": "private address",
        },
        dataset_id="cognitive:tenant-a",
        source_ids=["SRC-1"],
        observation_refs=["OBS-1"],
        claim_refs=["CLM-1"],
    )
    assert exported.record["schema"] == "Company"
    assert exported.record["properties"] == {
        "name": ["Example Ltd"],
        "registrationNumber": ["123"],
        "jurisdiction": ["GB"],
    }
    assert exported.provenance["observation_refs"] == ["OBS-1"]
    assert exported.provenance["identity_merge_performed"] is False
    assert "observation_refs" not in exported.record


def test_ftm_rejects_unapproved_schema():
    with pytest.raises(FtMExportError):
        build_ftm_export(
            tenant_id="tenant-a",
            entity_id="ENT-1",
            schema="Passport",
            properties={"name": "Example"},
            dataset_id="cognitive:tenant-a",
        )


def test_bigbrother_reference_modules_are_not_executable_by_default():
    assert blocked_capability_reason("face_matcher")
    assert blocked_capability_reason("breach_vault")
    assert blocked_capability_reason("cam_vector")
    with pytest.raises(PermissionError):
        require_approved_capability("face_matcher", registered=frozenset())
    with pytest.raises(LookupError):
        require_approved_capability("domain_oracle", registered=frozenset())
