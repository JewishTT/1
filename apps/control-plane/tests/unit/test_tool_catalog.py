"""Tool catalog (SpecOps entity→tool): determinism, coverage, type inference."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.tool_catalog import TOOLS, all_tools, infer_entity_type, tool, tools_for


def test_all_tools_are_name_sorted_and_stable() -> None:
    assert all_tools() == TOOLS
    ids = [t.tool_id for t in all_tools()]
    assert ids == sorted(ids)


def test_tool_ids_are_unique() -> None:
    ids = [t.tool_id for t in all_tools()]
    assert len(ids) == len(set(ids))


def test_every_tool_has_complete_required_fields() -> None:
    for spec in all_tools():
        assert spec.tool_id
        assert spec.name
        assert spec.category
        assert spec.entity_types
        assert spec.entity_types == tuple(sorted(spec.entity_types))
        assert spec.method
        assert spec.source
        assert spec.license
        assert spec.description
        assert spec.run_mode in {"harvester", "command", "manual"}


def test_tools_for_filters_and_stays_sorted() -> None:
    phone = tools_for("PHONE")
    email = tools_for("EMAIL")
    assert phone
    assert email
    assert all("PHONE" in t.entity_types for t in phone)
    assert all("EMAIL" in t.entity_types for t in email)
    assert [t.tool_id for t in phone] == sorted(t.tool_id for t in phone)
    assert [t.tool_id for t in email] == sorted(t.tool_id for t in email)


def test_tool_lookup_found_and_missing() -> None:
    whois = tool("whois")
    assert whois is not None
    assert whois.entity_types == ("DOMAIN", "IPV4")
    assert tool("no-such-tool") is None


def test_all_three_run_modes_covered() -> None:
    modes = {t.run_mode for t in all_tools()}
    assert modes == {"harvester", "command", "manual"}
    assert all(t.run_mode == "command" and t.command_template for t in all_tools() if t.run_mode == "command")
    assert all(
        t.run_mode in {"harvester", "manual"} and not t.command_template
        for t in all_tools()
        if t.run_mode in {"harvester", "manual"}
    )


def test_infer_entity_type_mapping_cases() -> None:
    assert infer_entity_type({"account": "Yard"}) == "USERNAME"
    assert infer_entity_type({"handle": "x"}) == "USERNAME"
    assert infer_entity_type({"username": "x"}) == "USERNAME"
    assert infer_entity_type({"email": "a@b.com"}) == "EMAIL"
    assert infer_entity_type({"phone": "+12025550199"}) == "PHONE"
    assert infer_entity_type({"telephone": "+1"}) == "PHONE"
    assert infer_entity_type({"domain": "example.com"}) == "DOMAIN"
    assert infer_entity_type({"host": "example.com"}) == "DOMAIN"
    assert infer_entity_type({"url": "https://example.com"}) == "URL"
    assert infer_entity_type({"name": "Jane Doe"}) == "NAME"
    assert infer_entity_type({"full_name": "Jane Doe"}) == "NAME"
    assert infer_entity_type({"person": "Jane Doe"}) == "NAME"
    assert infer_entity_type({"org": "Acme"}) == "ORG"
    assert infer_entity_type({"company": "Acme"}) == "ORG"
    assert infer_entity_type({"location": "Berlin"}) == "LOCATION"
    assert infer_entity_type({"city": "Berlin"}) == "LOCATION"
    assert infer_entity_type({"country": "DE"}) == "LOCATION"
    assert infer_entity_type({"ip": "1.2.3.4"}) == "IPV4"
    assert infer_entity_type({"ipv4": "1.2.3.4"}) == "IPV4"
    assert infer_entity_type({"id_number": "A-1"}) == "DOCUMENT"


def test_infer_entity_type_falls_back_to_unknown() -> None:
    assert infer_entity_type({}) == "UNKNOWN"
    assert infer_entity_type({"unmapped_dimension": "v"}) == "UNKNOWN"