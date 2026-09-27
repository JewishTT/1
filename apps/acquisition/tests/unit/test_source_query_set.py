"""Multi-route source query set unit tests (feature 015, US2).

The search surface is multidimensional but execution used to be one-dimensional:
a single prioritized ``CcQueryPlan`` was executed and every other identity
dimension was discarded. These tests pin the replacement contract: one
deterministic query per applicable route, deduplicated with provenance, with
routes that cannot be executed declared rather than dropped.
"""

from __future__ import annotations

import sys
from pathlib import Path

_APPS_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_APPS_DIR / "shared"))
sys.path.insert(0, str(_APPS_DIR))

from acquisition.cc_plan import build_cc_plan  # noqa: E402
from acquisition.entity_search import build_entity_search_surface  # noqa: E402
from acquisition.source_query_set import (  # noqa: E402
    COMMON_CRAWL_PROVIDER,
    RouteProvider,
    build_source_query_set,
)

FULL_IDENTITY = {
    "url": "https://acme.test/docs",
    "domain": "acme.test",
    "name": "Acme Corporation",
    "alias": "Acme Corp",
    "historical_name": "Acme Ltd",
    "username": "acme",
    "email": "ops@acme.test",
    "phone": "+1 555 0100",
}


def _plan(identity: dict[str, str], providers: tuple = (COMMON_CRAWL_PROVIDER,)):
    surface = build_entity_search_surface("ENT-1", identity)
    return build_source_query_set(
        entity_id="ENT-1", surface=surface, providers=providers
    )


def test_one_query_per_applicable_route() -> None:
    """A multidimensional identity must not collapse to a single query (FR-001)."""
    query_set = _plan(FULL_IDENTITY)

    kinds = {query.route_kind for query in query_set.queries}
    assert kinds == {
        "exact_url",
        "url_prefix",
        "domain",
        "name",
        "alias",
        "historical_name",
        "username_derived",
        "email_derived",
        "phone_derived",
    }
    # The legacy planner would have produced exactly one of these.
    assert len(query_set.queries) > 1


def test_no_route_is_silently_dropped() -> None:
    """Every dimension is either executable or explicitly unsupported (FR-004)."""
    query_set = _plan(FULL_IDENTITY)

    assert query_set.unsupported, "expected declared-unsupported routes"
    for query in query_set.unsupported:
        assert query.unsupported_reason, (
            f"route {query.route_kind} is unsupported without a reason"
        )
    assert not query_set.is_complete


def test_query_set_is_independent_of_identity_key_order() -> None:
    """Equivalent identities must yield byte-identical plans (FR-002)."""
    forward = _plan(FULL_IDENTITY)
    reversed_keys = _plan(dict(reversed(list(FULL_IDENTITY.items()))))
    padded = _plan({k: f"  {v}  " for k, v in FULL_IDENTITY.items()})

    assert forward == reversed_keys == padded
    assert forward.query_set_id == reversed_keys.query_set_id == padded.query_set_id


def test_unsupported_routes_carry_a_machine_readable_reason() -> None:
    """A route with no registered provider is declared, never invented (D2)."""
    query_set = _plan(FULL_IDENTITY)

    by_kind = {query.route_kind: query for query in query_set.queries}
    for kind in ("username_derived", "email_derived", "phone_derived"):
        query = by_kind[kind]
        assert query.executable is False
        assert query.unsupported_reason == "no_provider_for_route"
        assert query.provider is None


def test_registering_a_provider_makes_a_route_executable() -> None:
    """The unsupported set is a registry fact, not a hardcoded dead end (D2)."""
    provider = RouteProvider(name="cc", route_kinds=frozenset({"email_derived"}))
    query_set = _plan(FULL_IDENTITY, providers=(provider,))

    email_query = next(q for q in query_set.queries if q.route_kind == "email_derived")
    assert email_query.executable is True
    assert email_query.provider == "cc"
    assert email_query.unsupported_reason is None


def test_identity_with_no_executable_route_does_not_raise() -> None:
    """An unexecutable identity plans cleanly and fails later, not here (AS-008)."""
    query_set = _plan({"phone": "+1 555 0100", "username": "acme"})

    assert query_set.executable == ()
    assert len(query_set.unsupported) == 2
    assert query_set.is_complete is False
    assert query_set.executable_count == 0


def test_short_values_are_reported_as_too_short() -> None:
    """Normalization failures are declared reasons, not crashes (FR-004)."""
    query_set = _plan({"name": "A"})

    query = next(q for q in query_set.queries if q.route_kind == "name")
    assert query.executable is False
    assert query.unsupported_reason == "value_too_short"


def test_ordinals_are_contiguous_and_ordered() -> None:
    """Ordinals are the plan's execution order and must be stable (FR-001)."""
    query_set = _plan(FULL_IDENTITY)

    assert [q.ordinal for q in query_set.queries] == list(range(len(query_set.queries)))


def test_domain_query_carries_surt_prefix_and_domain_match() -> None:
    """Domain routes keep the SURT semantics of the existing planner."""
    query_set = _plan({"domain": "acme.test"})

    query = next(q for q in query_set.queries if q.route_kind == "domain")
    assert query.match_type == "domain"
    assert query.surt_prefix == "http://test,acme,"
    assert query.executable is True
    assert query.provider == COMMON_CRAWL_PROVIDER.name


def test_query_ids_are_stable_across_plans() -> None:
    """Query identity is content-derived, so frontier keys stay stable (FR-007)."""
    first = _plan(FULL_IDENTITY)
    second = _plan(FULL_IDENTITY)

    ids = [q.query_id for q in first.queries]
    assert ids == [q.query_id for q in second.queries]
    assert len(set(ids)) == len(ids)


def test_legacy_single_plan_planner_is_unchanged() -> None:
    """The legacy prioritized planner must stay available (FR-005).

    Existing deployments and tests depend on ``build_cc_plan``; this feature adds
    multi-route execution beside it rather than replacing its contract.
    """
    plan = build_cc_plan("ENT-1", {"url": "https://acme.test/docs", "domain": "acme.test"})

    assert plan is not None
    assert plan.kind == "url"
    assert plan.match_type == "prefix"
    assert plan.surt_prefix == "http://test,acme,"
    # Priority is unchanged: url still wins over domain.
    assert build_cc_plan("ENT-1", {"domain": "acme.test", "name": "Acme"}).kind == "domain"
    assert build_cc_plan("ENT-1", {"name": "Acme"}).kind == "name"
    assert build_cc_plan("ENT-1", {}) is None


def test_duplicate_route_values_collapse_but_keep_provenance() -> None:
    """Two attributes yielding one route produce one query, two refs (FR-003)."""
    query_set = _plan({"domain": "acme.test", "host": "acme.test", "site": "acme.test"})

    domain_queries = [q for q in query_set.queries if q.route_kind == "domain"]
    assert len(domain_queries) == 1
    assert domain_queries[0].query_value == "acme.test"
    assert set(domain_queries[0].origin_refs) == {"domain", "host", "site"}
