"""Contract test: connector AcquisitionWorker compliance (T025, FR-008/FR-009)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apps" / "control-plane"))

import pytest
from services.source_registry import Connector, ConnectorRegistry, ReconPlanService


class _CompliantImpl:
    def capabilities(self) -> dict:
        return {"source_types": ["HTTP"], "content_types": ["text/html"]}

    def estimate(self, task: dict) -> dict:
        return {"expected_cost": 0.01}

    def acquire(self, task: dict) -> dict:
        return {"outcome": "observation_created"}


class _BrokenImpl:
    def capabilities(self) -> dict:
        return {"source_types": ["HTTP"]}


@pytest.mark.integration
class TestConnectorCompliance:
    def test_compliant_connector_activates(self) -> None:
        registry = ConnectorRegistry()
        connector = registry.register(
            Connector(name="web-fixture", tenant_id="t1", impl=_CompliantImpl())
        )
        assert connector.status.value == "REGISTERED"
        assert connector.to_dict()["contract_compliant"] is True
        assert registry.activate("web-fixture").status.value == "ACTIVE"

    def test_noncompliant_connector_cannot_activate(self) -> None:
        registry = ConnectorRegistry()
        registry.register(Connector(name="broken", tenant_id="t1", impl=_BrokenImpl()))
        with pytest.raises(ValueError):
            registry.activate("broken")

    def test_duplicate_registration_rejected(self) -> None:
        registry = ConnectorRegistry()
        registry.register(Connector(name="dup", tenant_id="t1", impl=_CompliantImpl()))
        with pytest.raises(ValueError):
            registry.register(Connector(name="dup", tenant_id="t1", impl=_CompliantImpl()))

    def test_recon_plan_lifecycle(self) -> None:
        plans = ReconPlanService()
        plan = plans.create(investigation_id="INV-1", tenant_id="t1")
        assert plan.status.value == "PLANNED"
        started = plans.start(plan.plan_id, ["TASK-1", "TASK-2"])
        assert started.status.value == "RUNNING"
        assert started.task_ids == ["TASK-1", "TASK-2"]
        assert plans.complete(plan.plan_id).status.value == "COMPLETED"

    def test_recon_plan_fail_records_reason(self) -> None:
        plans = ReconPlanService()
        plan = plans.create(investigation_id="INV-2", tenant_id="t1")
        plans.start(plan.plan_id, ["TASK-3"])
        failed = plans.fail(plan.plan_id, reason="connector timeout")
        assert failed.status.value == "FAILED"
        assert failed.strategy["failure_reason"] == "connector timeout"