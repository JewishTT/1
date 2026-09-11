"""Unit tests for investigation/policy/source domain models (US1 core, T021-T024)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from domain.investigation import (
    Investigation,
    InvestigationInvalidTransition,
    InvestigationState,
    InvestigationValidationError,
)
from domain.policy import Budget, Policy, PolicyDecision, PolicyEngine, ResourceLimit
from services.policy_service import PolicyService
from services.source_registry import SourceProfile, SourceRegistry


def _inv(**kw) -> Investigation:
    base = {
        "investigation_id": "INV-1",
        "name": "smoke-val",
        "tenant_id": "default-tenant",
        "objective": {"type": "osint", "description": "validate"},
    }
    base.update(kw)
    return Investigation(**base)


class TestInvestigation:
    def test_starts_in_draft(self) -> None:
        assert _inv().state is InvestigationState.DRAFT

    def test_planning_then_run(self) -> None:
        inv = _inv()
        inv.start()
        assert inv.state is InvestigationState.PLANNING
        inv.run()
        assert inv.state is InvestigationState.RUNNING

    def test_invalid_transition_rejected(self) -> None:
        inv = _inv()
        with pytest.raises(InvestigationInvalidTransition):
            inv.transition(InvestigationState.COMPLETED)  # DRAFT -> COMPLETED not allowed

    def test_pause_resume(self) -> None:
        inv = _inv()
        inv.start(); inv.run()
        inv.transition(InvestigationState.PAUSED)
        assert inv.state is InvestigationState.PAUSED
        inv.transition(InvestigationState.RUNNING)
        assert inv.state is InvestigationState.RUNNING

    def test_complete_then_archive(self) -> None:
        inv = _inv()
        inv.start(); inv.run()
        inv.transition(InvestigationState.COMPLETED)
        inv.transition(InvestigationState.ARCHIVED)
        assert inv.state is InvestigationState.ARCHIVED

    def test_validation_requires_name(self) -> None:
        with pytest.raises(InvestigationValidationError):
            _inv(name="  ").validate()

    def test_validation_rejects_unknown_scope(self) -> None:
        with pytest.raises(InvestigationValidationError):
            _inv(scope={"bogus": 1}).validate()


class TestPolicyAndBudget:
    def test_default_policy_allows_http(self) -> None:
        service = PolicyService()
        assert (
            service.check(
                policy_id="policies/default",
                source_class="HTTP",
                host="fixtures.local",
                worker_class="http",
                units=1,
            )
            is PolicyDecision.ALLOW
        )

    def test_policy_forbids_host(self) -> None:
        policy = Policy(policy_id="p", tenant_id="t", name="restrict", forbidden_hosts=["bad.com"])
        engine = PolicyEngine({"p": policy}, {})
        assert engine.check(policy_id="p", source_class="HTTP", host="bad.com",
                            worker_class="http", units=1) is PolicyDecision.DENY

    def test_budget_denies_over_limit(self) -> None:
        budget = Budget(budget_id="b", tenant_id="t",
                        limits={"http": ResourceLimit(max_units_per_window=10)})
        budget.usage["http"] = 10.0
        engine = PolicyEngine({}, {"b": budget})
        assert engine.check(policy_id="p", source_class="HTTP", host="h",
                            worker_class="http", units=5, budget_id="b") is PolicyDecision.DENY

    def test_budget_allows_under_limit(self) -> None:
        budget = Budget(budget_id="b", tenant_id="t",
                        limits={"http": ResourceLimit(max_units_per_window=100)})
        engine = PolicyEngine({"p": Policy(policy_id="p", tenant_id="t", name="x")}, {"b": budget})
        assert engine.check(policy_id="p", source_class="HTTP", host="h",
                            worker_class="http", units=5, budget_id="b") is PolicyDecision.ALLOW

    def test_budget_charge_and_over_limit(self) -> None:
        budget = Budget(budget_id="b", tenant_id="t",
                        limits={"http": ResourceLimit(max_units_per_window=10)})
        budget.charge("http", 11)
        assert budget.over_limit() == ["http"]


class TestSourceRegistry:
    def test_register_and_get(self) -> None:
        reg = SourceRegistry()
        p = SourceProfile(source_id="s1", tenant_id="t", uri="http://x", source_class="HTML",
                          worker_class="html-http")
        reg.register(p)
        assert reg.get("t", "http://x") == p

    def test_list_by_tenant(self) -> None:
        reg = SourceRegistry()
        reg.register(SourceProfile(source_id="s1", tenant_id="t1", uri="http://a", source_class="HTML",
                                   worker_class="w"))
        reg.register(SourceProfile(source_id="s2", tenant_id="t2", uri="http://b", source_class="HTML",
                                   worker_class="w"))
        assert len(reg.list("t1")) == 1

    def test_default_for_sitemap_uri(self) -> None:
        reg = SourceRegistry()
        p = reg.default_for_uri("http://fixtures.local/sitemap.xml")
        assert p.source_class in ("RSS", "HTML")
        assert p.capabilities == ["capabilities", "estimate", "acquire"]