from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2]
SHARED = APP.parents[1] / "apps" / "shared"
sys.path.insert(0, str(APP))
sys.path.insert(0, str(SHARED))

from industry_adapters.theharvester import AuthorizationScope, HarvestedRecord, RunEvidence  # noqa: E402
from runtime.theharvester import TheHarvesterRuntime  # noqa: E402


class FakeClient:
    base_url = "http://127.0.0.1:5000"

    def __init__(self, evidence: RunEvidence):
        self.evidence = evidence
        self.calls = []

    def run_authorized_domain(self, target, scope, **kwargs):
        self.calls.append((target, scope, kwargs))
        return self.evidence


def make_scope(**overrides):
    values = {
        "tenant_id": "tenant-a",
        "authorization_ref": "AUTH-2026-001",
        "allowed_domains": ("example.org",),
        "expires_at": datetime.now(UTC) + timedelta(hours=1),
    }
    values.update(overrides)
    return AuthorizationScope(**values)


def make_evidence():
    return RunEvidence(
        run_id="RUN-1",
        lifecycle_status="completed",
        evidence_status="complete",
        records=(
            HarvestedRecord(
                kind="hostname",
                value="mail.example.org",
                source_ids=("crtsh",),
                scope_class="authorized-domain",
                expandable=True,
            ),
            HarvestedRecord(
                kind="ip",
                value="192.0.2.10",
                source_ids=("crtsh",),
                scope_class="external-relationship",
                expandable=False,
            ),
        ),
        source_outcomes=({"source": "crtsh", "status": "completed", "reported_count": 1, "stop_reason": ""},),
        filtered_counts={"email": 1},
        submitted_at="2026-11-11T00:00:00+00:00",
        completed_at="2026-11-11T00:00:04+00:00",
    )


@pytest.mark.asyncio
async def test_runtime_emits_capture_then_discovery_only_records():
    client = FakeClient(make_evidence())
    runtime = TheHarvesterRuntime(client=client, authorization=make_scope())
    task = {
        "tenant_id": "tenant-a",
        "task_id": "TASK-1",
        "source_id": "SRC-1",
        "query": "example.org",
        "result_role": "DISCOVERY_ONLY",
    }

    artifacts = [artifact async for artifact in runtime.acquire(task)]

    assert len(artifacts) == 3
    capture, hostname, ip = artifacts
    manifest = json.loads(capture.body)
    assert capture.locator == "blob"
    assert manifest["evidence_status"] == "complete"
    assert manifest["may_support_qualified_absence"] is True
    assert manifest["filtered_counts"] == {"email": 1}
    assert hostname.capture_locator == "blob"
    assert hostname.locator == "json:records[0]"
    assert json.loads(hostname.body)["value"] == "mail.example.org"
    assert json.loads(hostname.body)["result_role"] == "DISCOVERY_ONLY"
    assert json.loads(ip.body)["expandable"] is False
    assert client.calls[0][0] == "example.org"


@pytest.mark.asyncio
async def test_runtime_refuses_wrong_tenant_and_evidence_role_before_network():
    client = FakeClient(make_evidence())
    runtime = TheHarvesterRuntime(client=client, authorization=make_scope())

    with pytest.raises(Exception, match="authorization_tenant_mismatch"):
        [item async for item in runtime.acquire({
            "tenant_id": "tenant-b", "task_id": "TASK-1", "source_id": "SRC-1",
            "query": "example.org", "result_role": "DISCOVERY_ONLY",
        })]
    with pytest.raises(Exception, match="theharvester_result_role_forbidden"):
        [item async for item in runtime.acquire({
            "tenant_id": "tenant-a", "task_id": "TASK-1", "source_id": "SRC-1",
            "query": "example.org", "result_role": "EVIDENCE",
        })]
    assert client.calls == []


@pytest.mark.asyncio
async def test_runtime_refuses_scope_expiry_before_calling_client():
    client = FakeClient(make_evidence())
    scope = make_scope(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    runtime = TheHarvesterRuntime(client=client, authorization=scope)
    with pytest.raises(Exception):
        [item async for item in runtime.acquire({
            "tenant_id": "tenant-a", "task_id": "TASK-1", "source_id": "SRC-1",
            "query": "example.org", "result_role": "DISCOVERY_ONLY",
        })]
    assert client.calls == []
