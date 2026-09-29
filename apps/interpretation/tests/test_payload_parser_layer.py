"""The parser layer's own contract: totality, bounds, spans, and what a record may contain.

Feature 021 brief §25 (a producer reports what the bytes say, or refuses); constitution IV
(fail-closed) and VI (determinism, Domain Invariant 12).

**What this file is for.** ``donors/estorides/estorides_core/parsers.py`` states the contract
"parsers MUST be total: any unrecognised input must return an empty container, not raise" and
honours it for about five of its fifty-five entries. Everything below exists because a contract
in a comment is believed and a contract in a test is checked:

* **totality** — five hostile payloads, one per failure shape upstream was exposed to, each
  returning a record set and raising nothing;
* **boundedness** — each of the three ceilings, each with the "raise the ceiling and you get
  more records" half that proves the ceiling is the only thing that stopped it;
* **the record's shape** — the fields it carries, and the mechanical check that it carries no
  ``confidence``, no type hypothesis and no resolution, because each of those is a stage this
  layer is not;
* **determinism** — the same bytes twice in one process and twice in two processes with
  different hash seeds, byte-identical records in the same order.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from domain.relation_identity import canonical_material, digest128

from parsers.payload import (
    BOUND_NAMES,
    PAYLOAD_RECORD_VERSION,
    VALUE_TYPES,
    BoundHit,
    DetectionRule,
    ObservedField,
    ParseBounds,
    ParsedPayload,
    PayloadContractError,
    PayloadLabel,
    PayloadParserRegistry,
    ValueType,
    default_registry,
)

pytestmark = pytest.mark.unit

#: ``apps/`` — the root the service packages hang off.
APPS = Path(__file__).resolve().parents[2]
INTERPRETATION = APPS / "interpretation"

_JSON = b'{"ip": "10.0.0.1", "count": 3, "ratio": 1e3, "live": true, "gone": null, ' \
        b'"tags": ["alpha", "beta"], "owner": {"name": "Acme", "id": null}}'

#: Ten megabytes of array elements. Built once, at import, because building it per test is the
#: slowest thing in this file and it is immutable.
_TEN_MB_ARRAY = b"[" + b"1," * 5_000_000 + b"1]"

#: Five thousand nested arrays around one value — deeper than any Python stack this platform
#: would survive and deeper than :attr:`ParseBounds.max_depth` by a wide margin.
_DEEP = b"[" * 5_000 + b"1" + b"]" * 5_000

_BINARY = bytes(range(256)) * 8


def hostile_corpus() -> tuple[tuple[str, bytes], ...]:
    """The payloads totality is measured over, one per failure shape.

    Malformed in four different ways on purpose: upstream's parsers do not fail uniformly, they
    fail on the shape each one happened to be written against, and a corpus with one malformed
    input proves nothing about the other three.
    """
    return (
        ("malformed_trailing_comma", b'{"a": 1,}'),
        ("malformed_missing_colon", b'{"a" 1}'),
        ("malformed_leading_zero", b'{"a": 01}'),
        ("malformed_unterminated", b'{"a": '),
        ("malformed_not_json_at_all", b"this is a sentence, not a document"),
        ("ten_megabyte_body", _TEN_MB_ARRAY),
        ("deeply_nested_body", _DEEP),
        ("binary_bytes", _BINARY),
        ("empty_body", b""),
        ("whitespace_only_body", b"   \t\r\n  "),
        ("nul_bytes", b"\x00\x00\x00"),
        ("unpaired_surrogate", b'{"a": "\\ud800"}'),
        ("bare_high_number", b'{"a": 1e400}'),
    )


def parse(body: bytes, **over: object) -> ParsedPayload:
    """A parse through the shipped registry, with JSON declared unless a test says otherwise.

    **The shipped defaults, deliberately.** Every ceiling is left where the registry puts it, so
    a test about records is never a test about bounds and a 10 MB body is measured against the
    ceiling a caller would actually get. The tests that are *about* a ceiling pass their own.
    """
    arguments: dict[str, object] = {
        "body": body,
        "content_type": "application/json",
        "declared_parser": "structured_fields",
    }
    arguments.update(over)
    return default_registry().parse(**arguments)


# --------------------------------------------------------------------------- #
# Totality: any input returns a record set, nothing raises
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(("label", "body"), hostile_corpus(), ids=lambda v: str(v)[:24])
def test_a_parser_returns_records_and_raises_nothing_for_a_hostile_body(
    label: str, body: bytes
) -> None:
    """The upstream contract, asserted rather than quoted.

    ``label`` is only in the failure message: the point is that the *body* is hostile, and a test
    that names which failure shape it is feeding is a test whose next failure is diagnosable.
    """
    payload = parse(body)
    assert isinstance(payload, ParsedPayload)
    assert isinstance(payload.records, tuple)
    assert isinstance(payload.refusals, tuple)
    assert isinstance(payload.bounds, ParseBounds)
    assert isinstance(payload.detection.is_json, bool)
    # Whatever came back, the two questions a caller asks are answerable: did a ceiling stop it,
    # and did the parser decline anything?
    assert payload.truncated == (payload.bound_hit is not None)
    assert isinstance(payload.truncation_reason, str)


def test_every_registered_parser_is_total_over_the_hostile_corpus() -> None:
    """P1's contract, measured over the corpus rather than asserted in a comment."""
    report = default_registry().totality_report([body for _, body in hostile_corpus()])
    assert report, "the corpus produced no measurements at all"
    failures = [measurement.to_dict() for measurement in report if not measurement.total]
    assert not failures, (
        "a registered parser raised on a hostile payload, and the contract says any input "
        f"returns records:\n  {failures}"
    )
    assert {measurement.parser for measurement in report} == set(default_registry().names())


def test_a_parser_that_raises_is_caught_by_the_totality_report() -> None:
    """The other half of the measurement: the report must be able to *see* a violation.

    A guard that has never been observed to fail has not been shown to guard anything, and a
    totality report that cannot report a non-total parser is a comment with a dataclass around
    it.
    """
    from parsers.payload import RegisteredParser
    from parsers.payload.records import ExtractorResult

    def explodes(**_: object) -> ExtractorResult:
        raise KeyError("a key that is not there")

    registry = PayloadParserRegistry([RegisteredParser(name="explodes", extract=explodes)])
    report = registry.totality_report([b"{}"])
    measured = {measurement.parser: measurement for measurement in report}
    assert measured["explodes"].total is False
    assert measured["explodes"].raised_as == "KeyError"
    # And the built-ins beside it are total, so the report distinguishes the two rather than
    # answering "not total" for the registry as a whole.
    assert all(
        measurement.total
        for name, measurement in measured.items()
        if name != "explodes"
    )


def test_a_parser_that_raises_is_recorded_rather_than_propagated() -> None:
    """And the registry itself is total, which is what makes "any input returns" true."""
    from parsers.payload import RegisteredParser
    from parsers.payload.records import ExtractorResult

    def explodes(**_: object) -> ExtractorResult:
        raise MemoryError("a payload nobody sized")

    registry = PayloadParserRegistry([RegisteredParser(name="explodes", extract=explodes)])
    payload = registry.parse(
        body=b'{"a": 1}',
        content_type="application/json",
        declared_parser="explodes",
    )
    assert payload.records == ()
    assert "parser_raised" in payload.refusal_codes
    assert payload.routed_to == "explodes"


def test_a_non_bytes_payload_is_refused_rather_than_coerced() -> None:
    """An object that carries no bytes is a missing payload, and the difference is countable."""
    payload = default_registry().parse(body=None, content_type="application/json")
    assert payload.byte_length == 0
    assert "payload_not_bytes" in payload.refusal_codes


# --------------------------------------------------------------------------- #
# Boundedness: a ceiling that fires is a recorded fact
# --------------------------------------------------------------------------- #


def _wide_array(pairs: int) -> bytes:
    return b"[" + b",".join(b'"v%d"' % index for index in range(pairs)) + b"]"


def test_a_body_past_the_node_ceiling_reports_truncated_with_its_reason() -> None:
    body = _wide_array(200)
    payload = default_registry().parse(
        body=body,
        content_type="application/json",
        declared_parser="structured_fields",
        bounds=ParseBounds(max_nodes=64, max_records_per_value_type=100_000, max_depth=64),
    )
    assert payload.truncated is True
    assert payload.truncation_reason == "nodes_visited"
    assert payload.bound_hit == BoundHit("nodes_visited", 64, payload.bound_hit.observed)


def test_the_same_body_at_a_raised_node_ceiling_yields_more_records() -> None:
    """The half of the boundedness test that gives the first half its meaning.

    A ceiling that silently dropped everything would also report ``truncated``; only raising the
    ceiling and getting more records shows the ceiling was the thing that stopped the walk.
    """
    body = _wide_array(200)
    low = default_registry().parse(
        body=body,
        content_type="application/json",
        declared_parser="structured_fields",
        bounds=ParseBounds(max_nodes=64, max_records_per_value_type=100_000, max_depth=64),
    )
    high = default_registry().parse(
        body=body,
        content_type="application/json",
        declared_parser="structured_fields",
        bounds=ParseBounds(max_nodes=100_000, max_records_per_value_type=100_000, max_depth=64),
    )
    assert len(high.records) > len(low.records)
    assert high.truncated is False
    assert high.truncation_reason == ""


def test_the_per_value_type_ceiling_fires_independently_of_the_node_ceiling() -> None:
    """Two ceilings for two shapes: many strings hit the type ceiling long before the node one."""
    body = _wide_array(300)
    payload = default_registry().parse(
        body=body,
        content_type="application/json",
        declared_parser="structured_fields",
        bounds=ParseBounds(max_nodes=1_000_000, max_records_per_value_type=16, max_depth=64),
    )
    assert payload.truncated is True
    assert payload.bound_hit is not None
    assert payload.bound_hit.bound == "records_of_value_type"
    assert payload.bound_hit.value_type == str(ValueType.STRING)
    assert len(payload.of_value_type(ValueType.STRING)) == 16


def test_the_depth_ceiling_stops_a_deeply_nested_body_and_records_it() -> None:
    """``max_depth`` is what makes "a deeply nested body raises nothing" true rather than lucky."""
    payload = parse(_DEEP)
    assert payload.truncated is True
    assert payload.truncation_reason == "depth"
    assert payload.bound_hit is not None
    assert payload.bound_hit.observed > payload.bound_hit.ceiling
    # The container the walk stopped inside is not emitted with a half-read span.
    assert all(record.byte_span is not None for record in payload.records)


def test_a_depth_bound_beyond_the_interpreter_stack_is_caught_rather_than_crashing() -> None:
    """The one bound with an environment underneath it, pinned as a fact rather than a hope.

    The structured walk is recursive, so a ``max_depth`` in the thousands is met by the
    interpreter's stack before the ceiling is. The registry catches that and records
    ``parser_raised``, so the layer is total either way — and this test is what keeps the default
    honest: it asserts the shipped default is nowhere near the limit, which is the only reason a
    caller gets the *bound* rather than the fault.
    """
    import sys as _sys

    assert ParseBounds().max_depth * 10 < _sys.getrecursionlimit(), (
        "the shipped depth ceiling is within an order of magnitude of the interpreter's "
        "recursion limit, so a deeply nested body would fault instead of reporting a bound"
    )
    payload = default_registry().parse(
        body=_DEEP,
        content_type="application/json",
        declared_parser="structured_fields",
        bounds=ParseBounds(
            max_nodes=1_000_000, max_records_per_value_type=1_000_000, max_depth=500_000
        ),
    )
    assert payload.records == ()
    assert "parser_raised" in payload.refusal_codes
    assert payload.truncated is False


def test_a_silent_truncation_is_impossible_because_the_two_halves_are_derived() -> None:
    """``truncated`` is derived from ``bound_hit``, so it cannot be set on its own."""
    for measurement in default_registry().totality_report([_JSON]):
        assert measurement.total is True
    hit = BoundHit("nodes_visited", 10, 11)
    assert hit.bound in BOUND_NAMES
    with pytest.raises(PayloadContractError) as raised:
        BoundHit("time_ran_out", 10, 11)
    assert raised.value.code == "bound_name_unknown"


def test_bounds_must_be_positive_integers() -> None:
    for bad in ({"max_nodes": 0}, {"max_depth": -1}, {"max_records_per_value_type": 1.5}):
        with pytest.raises(PayloadContractError) as raised:
            ParseBounds(**bad)
        assert raised.value.code == "parse_bounds_invalid"


def test_a_bound_hit_names_the_ceiling_the_limit_and_what_was_reached() -> None:
    body = _wide_array(80)
    payload = default_registry().parse(
        body=body,
        content_type="application/json",
        declared_parser="structured_fields",
        bounds=ParseBounds(max_nodes=32, max_records_per_value_type=100_000, max_depth=64),
    )
    hit = payload.bound_hit
    assert hit is not None
    assert (hit.ceiling, hit.observed) == (32, 33)
    assert hit.to_dict()["bound"] == "nodes_visited"


# --------------------------------------------------------------------------- #
# The record: four facts about the bytes, and nothing else
# --------------------------------------------------------------------------- #


def test_a_record_carries_exactly_the_documented_fields() -> None:
    """The shape, checked against the record rather than against this file's prose about it."""
    record = parse(_JSON).records[1]
    assert set(record.to_dict()) == {
        "field",
        "value",
        "value_type",
        "byte_span",
        "depth",
        "label",
        "address",
        "address_refusal",
    }


def test_a_payload_declares_the_record_version_it_was_read_with() -> None:
    """A record set read by a consumer written against a different shape is a misread."""
    payload = parse(_JSON)
    assert payload.to_dict()["record_version"] == PAYLOAD_RECORD_VERSION
    assert payload.to_dict()["record_version"] == "1"


def test_a_record_carries_no_confidence_no_type_hypothesis_and_no_resolution() -> None:
    """Upstream collapsed six epistemic levels into ``Entity(..., confidence=1.0)``.

    Each of these three is a *stage*, and a value for one of them here would be a number nobody
    measured: ``confidence`` was defaulted to ``1.0`` upstream, a type hypothesis belongs to the
    stage that reads a schema, and a resolution belongs to a stage with a decision record behind
    it. The check is mechanical — over every field name of every record of a real payload — so a
    field added later cannot arrive without this failing.
    """
    payload = parse(_JSON)
    forbidden = {"confidence", "entity_type", "type", "entity_id", "resolution", "sources"}
    for record in payload.records:
        assert not forbidden & set(record.to_dict())
    assert not forbidden & set(payload.to_dict())


def test_the_value_type_is_a_fact_about_the_bytes_and_never_a_hypothesis() -> None:
    """A string that looks like everything is still a string.

    Upstream's answer to this payload was an *email entity at confidence 1.0*; the honest answer
    is five bytes, two quotes and a ``string``.
    """
    body = b'{"email": "jane@acme.example", "ip": "10.0.0.1", "asn": "AS15169", "zip": "90210"}'
    payload = parse(body)
    by_field = {record.field: record for record in payload.records}
    for key in ("email", "ip", "asn", "zip"):
        record = by_field[f'$["{key}"]']
        assert record.value_type is ValueType.STRING
        assert str(record.value_type) == "string"
    # The value is what the payload wrote, and nothing more.
    assert by_field['$["zip"]'].value == "90210"


def test_number_literals_are_kept_verbatim_and_are_never_reformatted() -> None:
    """``1e3`` and ``1000.0`` are different byte sequences in the payload."""
    body = b'{"a": 1e3, "b": 1000.0, "c": -0.5e-7, "d": 1E400}'
    payload = parse(body)
    numbers = {record.field: record.value for record in payload.of_value_type(ValueType.NUMBER)}
    assert numbers == {
        '$["a"]': "1e3",
        '$["b"]': "1000.0",
        '$["c"]': "-0.5e-7",
        '$["d"]': "1E400",
    }
    # ``1e400`` is a legal JSON number and an illegal Python float, which is the whole reason
    # the literal is never converted.
    assert all(record.value_type is ValueType.NUMBER for record in payload.records[1:])


def test_the_value_type_inventory_is_the_payloads_grammar_and_nothing_else() -> None:
    """Five names, closed. A sixth would be a type hypothesis with a JSON-shaped name on it."""
    assert [str(value) for value in VALUE_TYPES] == [
        "string",
        "number",
        "bool",
        "null",
        "nested",
    ]
    body = b'{"s": "x", "n": 1, "b": true, "z": null, "c": {}}'
    seen = {str(record.value_type) for record in parse(body).records}
    assert seen == {"string", "number", "bool", "null", "nested"}


def test_a_string_span_is_the_quoted_token_and_a_number_span_is_the_literal() -> None:
    """The span is the token the payload wrote, so slicing the payload witnesses the record."""
    body = b'{"s": "abc", "n": 42, "c": {"k": "v"}}'
    payload = parse(body)
    for record in payload.records:
        span = payload.read_span(body, record)
        if record.value_type is ValueType.STRING:
            assert json.loads(span) == record.value
        elif record.value_type is ValueType.NUMBER:
            assert span == record.value
        else:
            assert span == body[record.byte_span[0] : record.byte_span[1]].decode()


def test_the_field_path_is_injective_so_a_key_with_a_dot_is_not_a_nesting() -> None:
    """``{"a.b": 1}`` and ``{"a": {"b": 1}}`` are different documents and must not share a path."""
    dotted = parse(b'{"a.b": 1}')
    nested = parse(b'{"a": {"b": 1}}')
    dotted_paths = {record.field for record in dotted.records} - {"$"}
    nested_paths = {record.field for record in nested.records} - {"$"}
    assert dotted_paths == {'$["a.b"]'}
    assert nested_paths == {'$["a"]', '$["a"]["b"]'}
    assert not dotted_paths & nested_paths


def test_duplicate_keys_are_two_records_because_choosing_one_would_be_a_decision() -> None:
    body = b'{"k": "first", "k": "second"}'
    payload = parse(body)
    values = [record.value for record in payload.of_value_type(ValueType.STRING)]
    assert values == ["first", "second"]


def test_records_arrive_in_document_order_and_are_independent_of_hash_seed() -> None:
    """Document order is the order the scanner appended in; nothing sorts by anything's hash."""
    payload = parse(_JSON)
    assert [record.field for record in payload.records] == [
        "$",
        '$["ip"]',
        '$["count"]',
        '$["ratio"]',
        '$["live"]',
        '$["gone"]',
        '$["tags"]',
        '$["tags"][0]',
        '$["tags"][1]',
        '$["owner"]',
        '$["owner"]["name"]',
        '$["owner"]["id"]',
    ]


# --------------------------------------------------------------------------- #
# Determinism
# --------------------------------------------------------------------------- #


def _fingerprint(payload: ParsedPayload) -> str:
    return digest128(canonical_material(payload.to_dict()))


def test_the_same_bytes_parsed_twice_in_one_process_are_identical() -> None:
    first = parse(_JSON)
    second = parse(_JSON)
    assert _fingerprint(first) == _fingerprint(second)
    assert [record.as_tuple() for record in first.records] == [
        record.as_tuple() for record in second.records
    ]


_DETERMINISM_SCRIPT = """
import sys
from domain.relation_identity import canonical_material, digest128
from parsers.payload import ParseBounds, default_registry

body = open(sys.argv[1], "rb").read()
payload = default_registry().parse(
    body=body,
    content_type="application/json",
    declared_parser="structured_fields",
    bounds=ParseBounds(max_nodes=100000, max_records_per_value_type=100000, max_depth=1000),
)
print(digest128(canonical_material(payload.to_dict())))
print("|".join(record.field + "=" + str(record.byte_span) for record in payload.records))
"""


def test_the_same_payload_parsed_in_two_processes_with_different_hash_seeds_is_identical() -> None:
    """constitution VI / Domain Invariant 12, measured across process boundaries.

    Two child interpreters, ``PYTHONHASHSEED`` pinned differently in each, is the only way to
    show that nothing on the path from bytes to records depends on set or dict iteration order:
    an in-process comparison cannot see it, because the seed is fixed for the whole run.
    """
    with tempfile.TemporaryDirectory(prefix="payload-determinism-") as directory:
        sample = Path(directory) / "payload.json"
        sample.write_bytes(_JSON)
        script = Path(directory) / "fingerprint.py"
        script.write_text(_DETERMINISM_SCRIPT, encoding="utf-8")
        outputs: list[str] = []
        for seed in ("0", "12345"):
            env = dict(os.environ)
            env["PYTHONPATH"] = str(INTERPRETATION)
            env["PYTHONHASHSEED"] = seed
            completed = subprocess.run(
                [sys.executable, str(script), str(sample)],
                capture_output=True,
                text=True,
                cwd=str(INTERPRETATION),
                env=env,
                check=False,
            )
            assert completed.returncode == 0, completed.stderr[-2000:]
            outputs.append(completed.stdout)
    assert outputs[0] == outputs[1], (
        "the same bytes produced different records in two processes with different hash seeds, "
        "so something on the path depends on iteration order"
    )
    assert outputs[0].splitlines()[1], "the child reported no records at all"


# --------------------------------------------------------------------------- #
# What this layer is not allowed to import or contain
# --------------------------------------------------------------------------- #

#: Everything above the parser layer. A parser that reaches for any of these has stopped being
#: an observation and become a decision.
_FORBIDDEN_ROOTS = frozenset(
    {
        "admission",
        "claims",
        "events",
        "graph",
        "projection",
        "resolution",
        "scoring",
        "semantic",
        "sources",
        "storage",
    }
)

#: Names that would be a decision in disguise. ``MN-`` is here too: the parser layer addresses
#: occurrences and must never mint an identity (brief §25, FR-019).
_FORBIDDEN_NAMES = frozenset(
    {
        "Entity",
        "ResolutionDecisionRecord",
        "RelationClaim",
        "RelationSignal",
        "confidence",
        "resolve",
    }
)

_FORBIDDEN_LITERALS = frozenset({"MN-", "RES-", "REL-", "ENT-"})


def _docstrings(tree: ast.AST) -> set[str]:
    """Every docstring in the module, so prose about a forbidden name is not a use of it."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                found.add(body[0].value.value)
    return found


def test_the_parser_layer_imports_nothing_above_it_and_names_no_decision() -> None:
    """The hard requirement, as a mechanical check over the AST of every module in the package.

    Docstrings are excluded, deliberately: this package's own documentation names
    ``RelationSignal``, ``MN-`` and ``sources.catalogue`` constantly, because a boundary nobody
    can name is a boundary nobody will argue about when the first change comes for it.
    """
    package = INTERPRETATION / "parsers" / "payload"
    offenders: list[str] = []
    for module in sorted(package.rglob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        prose = _docstrings(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in _FORBIDDEN_ROOTS:
                        offenders.append(f"{module.name}:{node.lineno} import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                if root in _FORBIDDEN_ROOTS:
                    offenders.append(f"{module.name}:{node.lineno} from {node.module}")
            elif isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
                offenders.append(f"{module.name}:{node.lineno} name {node.id}")
            elif isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_NAMES:
                offenders.append(f"{module.name}:{node.lineno} attribute {node.attr}")
            elif (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value in _FORBIDDEN_LITERALS
                and node.value not in prose
            ):
                offenders.append(f"{module.name}:{node.lineno} literal {node.value!r}")
    assert not offenders, (
        "the parser layer reached above itself or named a decision:\n  "
        + "\n  ".join(sorted(offenders))
    )


def test_the_detection_rule_is_carried_on_every_payload() -> None:
    """A record set separated from the reason it has that shape is the upstream defect."""
    payload = parse(_JSON)
    assert payload.detection.rule is DetectionRule.CONTENT_TYPE_JSON
    assert payload.to_dict()["detection"]["rule"] == "content_type_json"


def test_an_unexpected_payload_object_is_refused_by_type_not_coerced() -> None:
    """A field of the wrong shape is a contract error here, not a silent default."""
    with pytest.raises(PayloadContractError) as raised:
        ObservedField(
            field="$[\"a\"]",
            value="x",
            value_type="not-a-value-type",
            byte_span=(0, 3),
            depth=1,
            label=PayloadLabel.JSON_FIELD,
        )
    assert raised.value.code != ""
