"""Contracts for the optional Tenzir Node structural-normalization stage."""
from __future__ import annotations

import re
from typing import Any

import pytest

from normalization.tenzir import (
    NORMALIZATION_SCHEMA,
    TenzirError,
    TenzirNodeNormalizer,
    TenzirSettings,
    _normalization_definition,
    _tql_literal,
)


def _record(field: str, value: str, value_type: str, span: list[int] | None, depth: int) -> dict[str, Any]:
    return {
        "field": field,
        "value": value,
        "value_type": value_type,
        "byte_span": span,
        "depth": depth,
        "label": "VALUE",
        "address": f"occ-{depth}-{field}",
        "address_refusal": "",
    }


def _lexical_shape(record: dict[str, Any]) -> str:
    """Mirror the documented lexical-hint taxonomy; it deliberately asserts no semantics."""
    value = record["value"]
    value_type = record["value_type"]
    if value_type == "nested":
        return "container"
    if value_type == "null":
        return "null"
    if not value.strip():
        return "empty"
    if re.fullmatch(r"[+-]?[0-9]+(?:[.][0-9]+)?(?:[eE][+-]?[0-9]+)?", value):
        return "numeric"
    if re.fullmatch(r"(?i:true|false)", value):
        return "boolean"
    if re.fullmatch(r"[^@ ]+@[^ ]+[.][^ ]+", value):
        return "email_like"
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", value):
        return "url_like"
    if re.fullmatch(r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}", value):
        return "uuid_like"
    if re.fullmatch(r"(?:[0-9A-Fa-f]{32}|[0-9A-Fa-f]{40}|[0-9A-Fa-f]{64})", value):
        return "hex_digest_like"
    return "text"


def _fake_tenzir(
    client: TenzirNodeNormalizer,
    complete_records: list[dict[str, Any]],
    *,
    mutate_protected: bool = False,
    drop_last: bool = False,
):
    calls: list[tuple[str, dict[str, Any]]] = []
    launched_batches: list[list[int]] = []

    def post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
        calls.append((path, dict(payload)))
        if path == "/pipeline/launch":
            ordinals = [int(x) for x in re.findall(r"_platform_ordinal:\s*(\d+)", payload["definition"])]
            assert ordinals
            launched_batches.append(ordinals)
            return {"id": "pipeline-fixture"}
        if path == "/serve":
            ordinals = launched_batches[-1]
            events = []
            for ordinal in ordinals:
                if drop_last and ordinal == len(complete_records) - 1:
                    continue
                record = complete_records[ordinal]
                value = record["value"]
                span = record["byte_span"]
                data = {
                    **record,
                    "_platform_ordinal": ordinal,
                    "normalized_field_path": record["field"].lower(),
                    "normalized_value_type": record["value_type"].lower(),
                    "value_length_chars": len(value),
                    "value_length_bytes": len(value.encode("utf-8")),
                    "value_is_numeric_lexeme": bool(re.fullmatch(r"[+-]?[0-9]+(?:[.][0-9]+)?(?:[eE][+-]?[0-9]+)?", value)),
                    "has_nonempty_surface": bool(value.strip()),
                    "byte_span_width": span[1] - span[0] if span is not None else None,
                    "structural_role": (
                        "container" if record["value_type"] == "nested"
                        else "null" if record["value_type"] == "null"
                        else "surface"
                    ),
                    "value_shape": _lexical_shape(record),
                }
                if mutate_protected:
                    data["value"] = "changed-source-value"
                events.append({"data": data})
            return {
                "next_continuation_token": None,
                "state": "completed",
                "events": events,
            }
        if path == "/pipeline/delete":
            return {}
        raise AssertionError(f"unexpected Tenzir endpoint: {path}")

    client._post_json = post  # type: ignore[method-assign]
    return calls, launched_batches


def test_disabled_is_an_explicit_noop_without_a_new_dependency(monkeypatch) -> None:
    monkeypatch.delenv("TENZIR_ENABLED", raising=False)
    assert TenzirSettings.from_env() is None


def test_enabled_requires_an_explicit_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("TENZIR_ENABLED", "true")
    monkeypatch.delenv("TENZIR_NODE_URL", raising=False)
    with pytest.raises(TenzirError, match="tenzir_config_missing"):
        TenzirSettings.from_env()


def test_remote_plain_http_is_refused_by_default() -> None:
    with pytest.raises(TenzirError, match="tenzir_insecure_transport"):
        TenzirSettings(node_url="http://tenzir.internal:5160")


def test_remote_plain_http_requires_an_explicit_development_override() -> None:
    settings = TenzirSettings(
        node_url="http://tenzir.internal:5160",
        token="test-token",
        allow_insecure_http=True,
    )
    assert settings.node_url == "http://tenzir.internal:5160"


def test_remote_endpoint_requires_a_node_token() -> None:
    with pytest.raises(TenzirError, match="tenzir_token_missing"):
        TenzirSettings(
            node_url="http://tenzir.internal:5160",
            allow_insecure_http=True,
        )


def test_node_url_rejects_an_api_path_to_prevent_double_prefixing() -> None:
    with pytest.raises(TenzirError, match="must be the node origin"):
        TenzirSettings(node_url="http://localhost:5160/api/v0")


def test_node_client_calls_the_versioned_rest_api(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self, _limit: int) -> bytes:
            return b"{}"

    def _fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["method"] = request.get_method()
        seen["timeout"] = timeout
        return _Response()

    monkeypatch.setattr("normalization.tenzir.urlopen", _fake_urlopen)
    client = TenzirNodeNormalizer(TenzirSettings(node_url="http://localhost:5160"))
    assert client._post_json("/pipeline/list", {}) == {}
    assert seen["url"] == "http://localhost:5160/api/v0/pipeline/list"
    assert seen["method"] == "POST"


def test_tql_literals_escape_source_strings_and_reject_injected_field_names() -> None:
    assert _tql_literal('x"} | where true //') == '"x\\"} | where true //"'
    with pytest.raises(TenzirError, match="tenzir_input_invalid"):
        _tql_literal({"x | where true": "not-a-field"})


def test_transform_is_additive_and_records_the_reproducible_pipeline_digest() -> None:
    records = [_record('$["Name"]', "Ada", "string", [12, 15], 1)]
    definition = _normalization_definition(records)
    assert "normalized_field_path = field.to_lower()" in definition
    assert "value.length_chars()" in definition
    assert "value.length_bytes()" in definition
    assert 'value.match_regex("^[+-]?[0-9]+([.][0-9]+)?([eE][+-]?[0-9]+)?$")' in definition
    assert "byte_span_width" in definition
    assert 'value_shape = "container"' in definition
    assert 'value.match_regex("^[Tt][Rr][Uu][Ee]$|^[Ff][Aa][Ll][Ss][Ee]$")' in definition
    assert 'value.match_regex("^[A-Za-z][A-Za-z0-9+.-]*://")' in definition
    assert "ocsf_cast" not in definition
    assert "address_refusal" in definition
    assert NORMALIZATION_SCHEMA == "cognitive.observed-field-normalization/v2"


@pytest.mark.asyncio
async def test_normalizer_preserves_evidence_and_chunks_by_bounded_record_count() -> None:
    records = [
        _record('$["Name"]', "Ada", "string", [12, 15], 1),
        _record('$["count"]', "123", "string", [20, 23], 1),
        _record('$["city"]', "Rīga", "string", [32, 37], 1),
    ]
    original = [dict(row) for row in records]
    client = TenzirNodeNormalizer(
        TenzirSettings(node_url="http://localhost:5160", max_batch_records=2)
    )
    calls, batches = _fake_tenzir(client, records)

    normalized = await client.normalize_records(records)

    assert batches == [[0, 1], [2]]
    assert [row["ordinal"] for row in normalized.records] == [0, 1, 2]
    assert [row["record"] for row in normalized.records] == original
    assert normalized.records[2]["normalized"]["value_length_chars"] == 4
    assert normalized.records[2]["normalized"]["value_length_bytes"] == 5
    assert normalized.records[1]["normalized"]["value_is_numeric_lexeme"] is True
    assert normalized.records[1]["normalized"]["value_shape"] == "numeric"
    assert normalized.records[0]["normalized"]["byte_span_width"] == 3
    assert normalized.records[0]["normalized"]["structural_role"] == "surface"
    assert normalized.pipeline_digest.startswith("sha256:")
    assert sum(path == "/pipeline/launch" for path, _ in calls) == 2
    assert sum(path == "/serve" for path, _ in calls) == 2


@pytest.mark.asyncio
async def test_normalizer_refuses_source_field_mutation() -> None:
    records = [_record('$["Name"]', "Ada", "string", [12, 15], 1)]
    client = TenzirNodeNormalizer(TenzirSettings(node_url="http://localhost:5160"))
    _fake_tenzir(client, records, mutate_protected=True)

    with pytest.raises(TenzirError, match="tenzir_mutated_evidence"):
        await client.normalize_records(records)


@pytest.mark.asyncio
async def test_normalizer_refuses_dropped_records() -> None:
    records = [
        _record('$["Name"]', "Ada", "string", [12, 15], 1),
        _record('$["Age"]', "41", "number", [20, 22], 1),
    ]
    client = TenzirNodeNormalizer(TenzirSettings(node_url="http://localhost:5160"))
    _fake_tenzir(client, records, drop_last=True)

    with pytest.raises(TenzirError, match="tenzir_output_incomplete"):
        await client.normalize_records(records)


@pytest.mark.asyncio
async def test_normalizer_rejects_invalid_output_width() -> None:
    records = [_record('$["Name"]', "Ada", "string", [12, 15], 1)]
    client = TenzirNodeNormalizer(TenzirSettings(node_url="http://localhost:5160"))
    calls, _ = _fake_tenzir(client, records)

    original_post = client._post_json

    def bad_span_width(path: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = original_post(path, payload)
        if path == "/serve":
            result["events"][0]["data"]["byte_span_width"] = 99
        return result

    client._post_json = bad_span_width  # type: ignore[method-assign]
    with pytest.raises(TenzirError, match="tenzir_output_invalid"):
        await client.normalize_records(records)


@pytest.mark.asyncio
async def test_empty_input_does_not_create_a_pipeline() -> None:
    client = TenzirNodeNormalizer(TenzirSettings(node_url="http://localhost:5160"))
    normalized = await client.normalize_records([])
    assert normalized.records == []
    assert normalized.record_count == 0
    assert normalized.pipeline_digest.startswith("sha256:")


@pytest.mark.asyncio
async def test_lexical_shape_hints_cover_common_structured_surfaces_without_claiming_identity() -> None:
    records = [
        _record('$["enabled"]', "true", "string", None, 1),
        _record('$["email"]', "ops@example.test", "string", None, 1),
        _record('$["url"]', "https://example.test/a", "string", None, 1),
        _record('$["uuid"]', "550e8400-e29b-41d4-a716-446655440000", "string", None, 1),
        _record('$["digest"]', "a" * 64, "string", None, 1),
        _record('$["empty"]', "", "string", None, 1),
        _record('$["null"]', "", "null", None, 1),
        _record('$["container"]', "", "nested", None, 1),
        _record('$["other"]', "Ada Lovelace", "string", None, 1),
    ]
    client = TenzirNodeNormalizer(TenzirSettings(node_url="http://localhost:5160"))
    _fake_tenzir(client, records)

    result = await client.normalize_records(records)

    assert [row["normalized"]["value_shape"] for row in result.records] == [
        "boolean", "email_like", "url_like", "uuid_like", "hex_digest_like",
        "empty", "null", "container", "text",
    ]
    assert [row["record"] for row in result.records] == records
