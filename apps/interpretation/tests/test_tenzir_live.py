"""Opt-in acceptance against a real Tenzir Node.

The usual suite mocks the REST responses to pin adapter contracts. CI starts the pinned
Tenzir image and sets TENZIR_LIVE_NODE_URL so this test additionally exercises actual TQL
compilation, the launch API, the serve stream, and output preservation.
"""
from __future__ import annotations

import os

import pytest

from normalization.tenzir import TenzirNodeNormalizer, TenzirSettings


@pytest.mark.asyncio
async def test_live_tenzir_node_compiles_tql_and_preserves_source_records() -> None:
    endpoint = os.getenv("TENZIR_LIVE_NODE_URL", "").strip()
    if not endpoint:
        pytest.skip("TENZIR_LIVE_NODE_URL is not configured; live-node acceptance runs in CI")

    records = [
        {
            "field": '$["Name"]',
            "value": "München",
            "value_type": "string",
            "byte_span": [12, 21],
            "depth": 1,
            "label": "VALUE",
            "address": "occ-name-1",
            "address_refusal": "",
        },
        {
            "field": '$["Count"]',
            "value": "123",
            "value_type": "number",
            "byte_span": [30, 33],
            "depth": 1,
            "label": "VALUE",
            "address": "occ-count-1",
            "address_refusal": "",
        },
        {
            "field": '$["Child"]',
            "value": "",
            "value_type": "nested",
            "byte_span": None,
            "depth": 1,
            "label": "CONTAINER",
            "address": "",
            "address_refusal": "field_value_is_nested",
        },
    ]
    settings = TenzirSettings(
        node_url=endpoint,
        token=os.getenv("TENZIR_LIVE_NODE_TOKEN", ""),
        timeout_seconds=60,
        max_batch_records=16,
        max_request_bytes=256_000,
        max_response_bytes=512_000,
        max_output_records=64,
        engine_version=os.getenv("TENZIR_NODE_VERSION", "unknown"),
    )
    normalized = await TenzirNodeNormalizer(settings).normalize_records(records)

    assert len(normalized.records) == len(records)
    assert [item["ordinal"] for item in normalized.records] == [0, 1, 2]
    assert [item["record"] for item in normalized.records] == records
    assert normalized.records[0]["normalized"]["field_path"] == '$["name"]'
    assert normalized.records[0]["normalized"]["value_length_chars"] == len("München")
    assert normalized.records[0]["normalized"]["value_length_bytes"] == len("München".encode("utf-8"))
    assert normalized.records[1]["normalized"]["value_is_numeric_lexeme"] is True
    assert normalized.records[1]["normalized"]["structural_role"] == "surface"
    assert normalized.records[2]["normalized"]["structural_role"] == "container"
    assert normalized.records[2]["normalized"]["byte_span_width"] is None
