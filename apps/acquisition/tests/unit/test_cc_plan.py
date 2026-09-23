"""CC query planner unit tests (CC-TEMPORALITY v1, task_0006).

Hermetic: pure functions, no network, no fixtures beyond inline dicts.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cc_plan import CcQueryPlan, build_cc_plan, surt_from_host  # noqa: E402


def test_domain_identity_builds_domain_plan_with_surt() -> None:
    plan = build_cc_plan("e1", {"domain": "www.Example.com."})
    assert plan == CcQueryPlan(
        entity_id="e1",
        kind="domain",
        url_query="www.Example.com.",
        match_type="domain",
        surt_prefix="http://com,example,",
        limit=50,
    )


def test_domain_alt_keys_host_and_site() -> None:
    for key in ("host", "site"):
        plan = build_cc_plan("e1", {key: "example.org"})
        assert plan is not None
        assert plan.kind == "domain"
        assert plan.match_type == "domain"
        assert plan.surt_prefix == "http://org,example,"


def test_url_identity_builds_prefix_plan() -> None:
    plan = build_cc_plan("e2", {"url": "https://example.com/docs/page"})
    assert plan is not None
    assert plan.kind == "url"
    assert plan.match_type == "prefix"
    assert plan.url_query == "https://example.com/docs/page"
    assert plan.surt_prefix == "http://com,example,"


def test_url_priority_beats_domain() -> None:
    plan = build_cc_plan("e3", {"url": "https://a.example.com/x", "domain": "b.example.com"})
    assert plan is not None
    assert plan.kind == "url"
    assert plan.url_query == "https://a.example.com/x"


def test_name_identity_builds_name_query_no_surt() -> None:
    plan = build_cc_plan("e4", {"name": "Иван Иванов"})
    assert plan == CcQueryPlan(
        entity_id="e4",
        kind="name",
        url_query="Иван Иванов",
        match_type="prefix",
        surt_prefix=None,
        limit=50,
    )


def test_name_key_never_yields_domain_match() -> None:
    plan = build_cc_plan("e5", {"full_name": "John Smith"})
    assert plan is not None
    assert plan.kind == "name"
    assert plan.match_type == "prefix"
    assert plan.surt_prefix is None


def test_priority_between_name_keys() -> None:
    plan = build_cc_plan("e6", {"account": "acct-1", "name": "Primary"})
    assert plan is not None
    assert plan.kind == "name"
    assert plan.url_query == "Primary"  # "name" precedes "account"


def test_empty_identity_returns_none() -> None:
    assert build_cc_plan("e7", {}) is None


def test_blank_values_return_none() -> None:
    assert build_cc_plan("e7", {"domain": "   "}) is None
    assert build_cc_plan("e7", {"url": "", "name": "  "}) is None


def test_unknown_identity_keys_return_none() -> None:
    assert build_cc_plan("e7", {"phone": "+1-555"}) is None


def test_surt_from_host_edge_cases() -> None:
    assert surt_from_host("example.com") == "http://com,example,"
    assert surt_from_host("a.b.example.co.uk") == "http://uk,co,example,b,a,"
    assert surt_from_host("EXAMPLE.com:8080") == "http://com,example,"
    assert surt_from_host("www.") == "http://www,"
    assert surt_from_host("") is None


def test_plan_is_frozen() -> None:
    plan = build_cc_plan("e8", {"domain": "example.com"})
    assert plan is not None
    try:
        plan.limit = 1  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("CcQueryPlan must be frozen")
