"""Contract tests for the Context-to-Discovery compiler."""

from __future__ import annotations

import sys
from pathlib import Path

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP))

import pytest

from context_discovery import (
    ContextDiscoveryCompiler,
    EntitySeed,
    EvidenceFacet,
    ResearchContext,
)


def _context(**overrides) -> ResearchContext:
    values = {
        "tenant_id": "tenant-1",
        "investigation_id": "case-1",
        "context_text": "Investigate the public history and corporate relationships of Acme Systems.",
        "entities": (
            EntitySeed(
                ref="entity-acme",
                name="Acme Systems",
                aliases=("Acme", "Acme Technologies"),
                domains=("acme.example",),
                kind="organization",
            ),
        ),
    }
    values.update(overrides)
    return ResearchContext(**values)


def test_compilation_is_deterministic_and_content_addressed() -> None:
    compiler = ContextDiscoveryCompiler()
    first = compiler.compile(_context())
    second = compiler.compile(_context())

    assert first == second
    assert first.plan_id.startswith("DP-")
    assert len({task.query_id for task in first.tasks}) == len(first.tasks)
    assert [task.ordinal for task in first.tasks] == list(range(len(first.tasks)))


def test_one_context_expands_across_distinct_public_search_slices() -> None:
    plan = ContextDiscoveryCompiler().compile(_context())
    strategies = {task.strategy for task in plan.tasks}
    facets = {task.facet for task in plan.tasks}

    assert {
        "exact_phrase",
        "contextual_web",
        "public_records",
        "public_affiliations",
        "public_statements",
        "research_publications",
        "public_incident_advisories",
        "public_relationships",
        "public_filings",
        "first_party_documents",
        "certificate_transparency",
        "public_dns_registry",
        "domain_scoped_search",
        "archive_discovery",
    } <= strategies
    assert set(EvidenceFacet) <= facets


def test_domain_queries_are_scoped_and_use_safe_dork_operators() -> None:
    plan = ContextDiscoveryCompiler().compile(_context())
    queries = [task.query for task in plan.tasks]

    assert any('site:acme.example' in query for query in queries)
    assert any('site:crt.sh' in query for query in queries)
    assert any('filetype:pdf' in query for query in queries)
    assert all(len(query) <= 512 for query in queries)
    assert all("password" not in query.casefold() for query in queries)


def test_incident_strategy_targets_public_advisories_not_stolen_data() -> None:
    plan = ContextDiscoveryCompiler().compile(_context(facets=(EvidenceFacet.PUBLIC_INCIDENTS,)))
    queries = [task.query for task in plan.tasks]

    assert queries
    assert all("site:cisa.gov" in query or "site:cert.europa.eu" in query or "site:enisa.europa.eu" in query for query in queries)
    assert not any(token in " ".join(queries).casefold() for token in ("combo list", "stealer log", "password dump"))


def test_dispatch_shape_is_discovery_only_and_keeps_tenant_scope() -> None:
    context = _context()
    plan = ContextDiscoveryCompiler().compile(context)
    task = plan.tasks[0].as_dispatch_task(
        plan_id=plan.plan_id,
        context=context,
        context_digest=plan.context_digest,
        source_id="SRC-searxng-catalogue",
        source_name="searxng_public_search",
    )

    assert task["tenant_id"] == "tenant-1"
    assert task["case_id"] == "case-1"
    assert task["runtime_ref"] == "searxng"
    assert task["source_id"] == "SRC-searxng-catalogue"
    assert task["source_name"] == "searxng_public_search"
    assert task["result_role"] == "DISCOVERY_ONLY"
    assert task["required_capabilities"] == ["search", "json-output", "paged"]
    assert {item["kind"] for item in task["constraints"]} >= {
        "public_source_only",
        "discovery_only",
        "no_access_control_bypass",
        "no_private_contact_extraction",
    }


def test_time_window_is_carried_into_query_and_dispatch_constraints() -> None:
    context = _context(time_from="2020-01-01", time_to="2024-12-31")
    plan = ContextDiscoveryCompiler().compile(context)

    assert all("after:2020-01-01" in task.query and "before:2024-12-31" in task.query for task in plan.tasks)
    dispatch = plan.tasks[0].as_dispatch_task(
        plan_id=plan.plan_id, context=context, context_digest=plan.context_digest
    )
    assert {"kind": "time_window", "from": "2020-01-01", "to": "2024-12-31"} in dispatch["constraints"]


def test_missing_domain_is_an_explicit_coverage_gap() -> None:
    context = _context(
        entities=(EntitySeed(ref="topic-1", name="Public policy", kind="topic"),),
        facets=(EvidenceFacet.TECHNICAL_INFRASTRUCTURE,),
    )
    plan = ContextDiscoveryCompiler().compile(context)

    assert plan.tasks == ()
    coverage = plan.coverage[0]
    assert coverage.status == "not_plannable"
    assert coverage.reason == "no_domain_anchor"


def test_query_budget_is_hard_and_truncation_is_visible() -> None:
    plan = ContextDiscoveryCompiler().compile(_context(max_queries=3))

    assert len(plan.tasks) == 3
    assert plan.truncated is True
    assert any("Query budget reached" in warning for warning in plan.warnings)


def test_quoted_topic_can_be_used_without_guessing_a_person() -> None:
    context = _context(
        entities=(),
        context_text='Research the public policy debate around "critical infrastructure resilience".',
        facets=(EvidenceFacet.IDENTITY, EvidenceFacet.PUBLICATIONS),
    )
    plan = ContextDiscoveryCompiler().compile(context)

    assert plan.tasks
    assert {task.subject_ref for task in plan.tasks} == {plan.tasks[0].subject_ref}
    assert plan.tasks[0].subject_ref.startswith("topic-")


def test_direct_contact_and_credential_material_is_rejected() -> None:
    with pytest.raises(ValueError, match="contact identifiers"):
        EntitySeed(ref="bad", name="analyst@example.test")
    with pytest.raises(ValueError, match="contact identifier"):
        ResearchContext(
            tenant_id="t",
            investigation_id="c",
            context_text="Investigate analyst@example.test",
        )
    with pytest.raises(ValueError, match="credential-like"):
        ResearchContext(
            tenant_id="t",
            investigation_id="c",
            context_text="Investigate Acme; api_key=do-not-search-this",
        )


def test_plan_is_explicitly_not_dispatched_or_admitted() -> None:
    context = _context()
    plan = ContextDiscoveryCompiler().compile(context)
    rendered = plan.as_dict(context=context, source_id="SRC-searxng-catalogue", source_name="searxng_public_search")

    assert rendered["status"] == "PLANNED_NOT_DISPATCHED"
    assert rendered["guarantees"]["results_are_unverified_leads"] is True
    assert rendered["guarantees"]["claim_admission_allowed"] is False
    assert rendered["guarantees"]["private_contact_collection"] is False
