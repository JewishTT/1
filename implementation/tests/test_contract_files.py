"""Fail-fast validation for contract artifacts in this delivery package."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).parents[2]


def test_all_json_schemas_are_valid_draft_2020_12() -> None:
    schemas = sorted((ROOT / "contracts" / "schemas").glob("*.json"))
    assert schemas, "no contract JSON schemas found"
    for path in schemas:
        schema = json.loads(path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)


def test_person_source_policy_is_default_deny_and_scoped() -> None:
    policy = yaml.safe_load((ROOT / "contracts" / "source-policy-example.yaml").read_text(encoding="utf-8"))
    assert policy["spec"]["default"] == "deny"
    assert "PUBLIC_PROFESSIONAL" in policy["spec"]["case_profiles"]
    assert "credential" in policy["spec"]["excluded_claim_families"]
    profiles = policy["spec"]["source_profiles"]
    assert profiles
    for source in profiles:
        assert source.get("contact_class"), source.get("source_id")
        assert source.get("required_response_parser"), source.get("source_id")
        assert source.get("max_requests", 0) > 0, source.get("source_id")
        assert source.get("max_raw_bytes", 0) > 0, source.get("source_id")
        assert source.get("max_decompressed_bytes", 0) > 0, source.get("source_id")
        assert source.get("enabled") is True or source.get("license_status") or source.get("term_status")


def test_model_capabilities_have_no_canonical_write_or_network_tools() -> None:
    registry = yaml.safe_load((ROOT / "contracts" / "model-capabilities.yaml").read_text(encoding="utf-8"))
    model_spec = registry["spec"]
    assert model_spec["default_model"] in model_spec["models"]
    for name, capability in model_spec["capabilities"].items():
        assert capability["model"] in model_spec["models"], name
        assert capability.get("canonical_write") is False, name
        assert capability.get("network_tools") == [], name
        assert capability.get("input_schema") and capability.get("output_schema"), name
        assert capability.get("on_failure"), name


def test_claim_quotes_are_span_addressable_by_contract() -> None:
    schema = json.loads((ROOT / "contracts" / "schemas" / "claim-extractor.output.json").read_text(encoding="utf-8"))
    claim = schema["properties"]["claims"]["items"]
    assert "evidence_quote" in claim["required"]
    assert "start_offset" in claim["required"] and "end_offset" in claim["required"]
    assert claim["properties"]["offset_coordinate_space"]["const"] == "evidence_window_unicode_codepoint"
