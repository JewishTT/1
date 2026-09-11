"""Integration test: cross-tenant isolation matrix (T058, US3).

Two tenants run parallel investigations with no cross-tenant leakage across
data/events/search/graph/storage/budgets: every backend naming dimension is
tenant-scoped and a cross-tenant access attempt fails closed.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from isolation import TenantIsolation, TenantIsolationViolation, is_valid_tenant_id


@pytest.mark.integration
class TestTenantIsolation:
    def test_two_tenants_never_share_any_dimension(self) -> None:
        a = TenantIsolation("Tenant-Alpha")
        b = TenantIsolation("tenant-beta")
        dimensions = ("kafka_topic", "search_index_alias", "s3_prefix", "graph_namespace", "budget_scope", "dlq_topic")
        for dim in dimensions:
            assert getattr(a, dim) != getattr(b, dim), dim

    def test_backend_scopes_are_namespaced_and_stable(self) -> None:
        a = TenantIsolation("alpha")
        assert a.s3_prefix == "raw/t/alpha/"
        assert a.kafka_topic.startswith("cognitive-events--t-alpha")
        assert a.graph_namespace == "cognitive_alpha"
        assert a.search_index_alias.startswith("observations--t-alpha")

    def test_cross_tenant_access_fails_closed(self) -> None:
        alpha = TenantIsolation("alpha")
        with pytest.raises(TenantIsolationViolation):
            alpha.require_tenant("beta")

    def test_same_tenant_passes(self) -> None:
        TenantIsolation("alpha").require_tenant("alpha")  # no raise

    def test_tenant_id_validation(self) -> None:
        assert is_valid_tenant_id("tenant-1_x")
        assert not is_valid_tenant_id("-no")
        assert not is_valid_tenant_id("has space")

    def test_investment_budgets_are_scoped_per_tenant(self) -> None:
        assert TenantIsolation("alpha").budget_scope == "alpha"
        assert TenantIsolation("gamma").budget_scope == "gamma"