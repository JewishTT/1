from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP))

from industry_adapters.capabilities import (  # noqa: E402
    blocked_capability_reason,
    require_approved_capability,
)
from industry_adapters.domain_posture import probe_authorized_tls  # noqa: E402
from industry_adapters.followthemoney import (  # noqa: E402
    FtMExportError,
    build_ftm_export,
    stable_ftm_id,
)
from industry_adapters.theharvester import (  # noqa: E402
    AuthorizationError,
    AuthorizationScope,
    TheHarvesterApiClient,
    normalize_findings,
)


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
def test_invalid_or_non_domain_hostname_results_are_filtered(value):
    records, filtered = normalize_findings(
        [{"type": "hostname", "value": value}],
        scope(),
        target="example.org",
    )
    assert records == []
    assert filtered == {"hostname": 1}


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


def test_external_results_never_become_qualified_absence_without_coverage_measurement():
    from industry_adapters.theharvester import RunEvidence

    evidence = RunEvidence(
        run_id="RUN-1",
        lifecycle_status="completed",
        evidence_status="complete",
        records=(),
        source_outcomes=({"source": "crtsh", "status": "completed"},),
        filtered_counts={},
        submitted_at="2026-11-15T00:00:00Z",
        completed_at="2026-11-15T00:01:00Z",
    )
    assert evidence.may_support_qualified_absence is False


def test_tls_probe_requires_an_explicit_tls_authorization_before_network_io():
    allowed = scope()
    touched = False

    def socket_factory(*args, **kwargs):
        nonlocal touched
        touched = True
        raise AssertionError("network must not be touched without TLS authorization")

    with pytest.raises(AuthorizationError):
        probe_authorized_tls("example.org", allowed, socket_factory=socket_factory)
    assert touched is False


def test_tls_authorization_is_domain_bound():
    allowed = scope(allow_tls_probe=True)
    assert allowed.assert_tls_probe("mail.example.org") == "mail.example.org"
    with pytest.raises(AuthorizationError):
        allowed.assert_tls_probe("elsewhere.invalid")


class _FakeResponse:
    status = 200

    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, size=-1):
        return self._body if size < 0 else self._body[:size]


class _FakeOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        return _FakeResponse(self.responses.pop(0))


def test_theharvester_rest_run_is_finite_authenticated_and_passive():
    import json

    export = "\n".join([
        json.dumps({"record_type": "summary", "evidence_status": "complete"}),
        json.dumps({"type": "hostname", "value": "mail.example.org", "sources": ["crtsh"]}),
        json.dumps({"type": "email", "value": "private@example.org", "sources": ["provider"]}),
    ]).encode()
    opener = _FakeOpener([
        json.dumps({"run_id": "RUN-1"}).encode(),
        json.dumps({
            "status": "completed",
            "evidence_status": "complete",
            "completed_at": "2026-11-15T12:00:00Z",
            "source_executions": [{"source": "crtsh", "status": "completed", "result_count": 1}],
        }).encode(),
        export,
    ])
    client = TheHarvesterApiClient(
        base_url="http://127.0.0.1:5000",
        api_key="local-service-secret",
        max_wait_seconds=1,
        poll_interval_seconds=0.1,
        opener=opener,
    )

    evidence = client.run_authorized_domain("example.org", scope())

    assert evidence.lifecycle_status == "completed"
    assert evidence.evidence_status == "complete"
    assert evidence.may_support_qualified_absence is False
    assert [(record.kind, record.value) for record in evidence.records] == [
        ("hostname", "mail.example.org")
    ]
    assert evidence.filtered_counts["email"] == 1
    submitted = json.loads(opener.requests[0][0].data)
    assert submitted["sources"] == ["subdomains"]
    assert submitted["deadline_seconds"] == 600
    assert all(
        request.get_header("X-api-key") == "local-service-secret"
        for request, _timeout in opener.requests
    )
    assert len(opener.requests) == 3


def test_theharvester_never_accepts_plain_http_for_remote_service():
    with pytest.raises(ValueError, match="HTTPS"):
        TheHarvesterApiClient(
            base_url="http://harvester.example.net",
            api_key="local-service-secret",
        )


def test_source_outcomes_need_method_backed_coverage_to_qualify_absence():
    from industry_adapters.theharvester import RunEvidence

    unmeasured = RunEvidence(
        run_id="RUN-2",
        lifecycle_status="completed",
        evidence_status="complete",
        records=(),
        source_outcomes=({"source": "crtsh", "status": "completed"},),
        filtered_counts={},
        submitted_at="2026-11-15T11:59:00Z",
        completed_at="2026-11-15T12:00:00Z",
    )
    measured = RunEvidence(
        run_id="RUN-3",
        lifecycle_status="completed",
        evidence_status="complete",
        records=(),
        source_outcomes=({
            "source": "fixture",
            "status": "completed",
            "detection_power": 0.95,
            "detection_power_method": "versioned completeness test",
        },),
        filtered_counts={},
        submitted_at="2026-11-15T11:59:00Z",
        completed_at="2026-11-15T12:00:00Z",
    )
    assert unmeasured.may_support_qualified_absence is False
    assert measured.may_support_qualified_absence is True
