"""P1's routing table and P5's identity-parser answer, plus the two mutations that guard them.

Feature 021 brief §25; constitution IV (fail-closed) and VI (determinism, Domain Invariant 12).

**P5, in one paragraph.** 22 of the catalogue's 145 definitions declare a parser whose upstream
implementation is the identity function, so for those the "structured view" is the payload
itself. The answer this layer gives them is **no bespoke parser and a recorded route**: they are
read as text - one record per line, no key path claimed, no schema invented - unless the
transport declared a JSON media type, in which case the structured walk reports the key paths
the payload states *and* says, in
``declared_parser_is_identity_content_type_is_json``, that the definition declared no parser and
the header declared the grammar. Nothing is claimed that the bytes and the header do not state;
nothing is hidden about which rule fired. The count is asserted against the real catalogue
below, so "22" is a measurement and not a recollection.

**Why 145 and not 146.** The catalogue held 146 *files* but only 145 distinct sources:
``hunter_email`` was declared twice, in ``08_knowledge`` (parser ``raw_text``) and
``16_people`` (parser ``pass_through``). Both resolve to the same ``source_id``, so the registry
was silently keeping one and discarding the other. The duplicate has been removed and the loader
now reports ``duplicate_source_id`` instead of overwriting, so this cannot recur. The identity
population drops 23 -> 22 with it, because one of the two copies was counted as a distinct
identity definition when it never was one.

**The two mutations at the bottom** are the ones the task names: remove the truncation report,
and the suite notices; make the type detector guess, and the suite notices. Each has the
unmutated half too, because a mutation test that would pass against already-broken code proves
nothing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from parsers.payload import (
    IDENTITY_PARSER_NAMES,
    ROUTING_REFUSAL_CODES,
    STRUCTURED_PRODUCER,
    TEXT_PRODUCER,
    ParseBounds,
    PayloadContractError,
    PayloadParserRegistry,
    RegisteredParser,
    default_registry,
)
from parsers.payload.records import ExtractorResult

pytestmark = pytest.mark.unit

APPS = Path(__file__).resolve().parents[2]
INTERPRETATION = APPS / "interpretation"
ESTORIDES = APPS / "acquisition" / "sources" / "estorides"
_COPIED = (
    ("interpretation", ("extractors", "parsers", "semantic", "contracts.py")),
    ("shared", ("domain",)),
)

#: How many of the catalogue's definitions declare an identity parser. Pinned because the
#: routing rule below is stated *about those definitions*, and a rule that quietly stops applying
#: to them because the catalogue grew is a rule nobody re-reads.
IDENTITY_DEFINITION_COUNT = 22


# --------------------------------------------------------------------------- #
# The routing table
# --------------------------------------------------------------------------- #


def test_an_identity_parser_on_a_text_payload_is_read_as_text_and_not_upgraded() -> None:
    payload = default_registry().parse(
        body=b"one\ntwo\n",
        content_type="text/plain",
        declared_parser="raw_text",
        parser_is_identity=True,
    )
    assert payload.routed_to == TEXT_PRODUCER
    assert payload.parser_is_identity is True
    assert payload.declared_parser == "raw_text"
    assert [record.value for record in payload.records] == ["one", "two"]
    assert all(record.label == "text_line" for record in payload.records)
    assert payload.refusals == ()


def test_an_identity_parser_on_a_declared_json_payload_reports_key_paths_and_says_why() -> None:
    payload = default_registry().parse(
        body=b'{"ip": "10.0.0.1"}',
        content_type="application/json",
        declared_parser="raw_text",
        parser_is_identity=True,
    )
    assert payload.routed_to == STRUCTURED_PRODUCER
    assert payload.parser_is_identity is True
    assert "declared_parser_is_identity_content_type_is_json" in payload.refusal_codes
    assert "does not claim" not in " ".join(refusal.detail for refusal in payload.refusals)
    assert {record.label for record in payload.records} == {"json_root", "json_field"}


def test_an_unregistered_parser_name_is_refused_by_name_and_the_payload_read_as_text() -> None:
    """Upstream's ``PARSERS.get(name, parse_raw_text)`` turned a typo into a quiet downgrade."""
    payload = default_registry().parse(
        body=b"line one\n",
        content_type="text/plain",
        declared_parser="amass_json",
    )
    assert "parser_name_unknown" in payload.refusal_codes
    assert payload.routed_to == TEXT_PRODUCER
    assert len(payload.records) == 1


def test_a_registered_parser_is_used_when_the_declaration_says_json() -> None:
    payload = default_registry().parse(
        body=b'{"a": 1}',
        content_type="application/json",
        declared_parser=STRUCTURED_PRODUCER,
    )
    assert payload.routed_to == STRUCTURED_PRODUCER
    assert payload.refusals == ()


def test_a_registered_structured_parser_is_refused_on_a_payload_declared_as_text() -> None:
    payload = default_registry().parse(
        body=b'{"a": 1}',
        content_type="text/plain",
        declared_parser=STRUCTURED_PRODUCER,
    )
    assert "declared_parser_content_type_is_not_json" in payload.refusal_codes
    assert payload.routed_to == TEXT_PRODUCER
    assert payload.refusals[0].code in ROUTING_REFUSAL_CODES


def test_a_missing_declaration_is_recorded_rather_than_defaulted() -> None:
    payload = default_registry().parse(body=b"text\n", content_type="text/plain")
    assert "parser_name_empty" in payload.refusal_codes
    assert payload.declared_parser == ""


@pytest.mark.parametrize(("name", "flag"), [("raw_text", False), ("amass_json", True)])
def test_a_flag_that_disagrees_with_the_declared_name_is_recorded_not_resolved(
    name: str, flag: bool
) -> None:
    """Two sources of truth about one declaration, and picking either would be a decision."""
    payload = default_registry().parse(
        body=b'{"a": 1}',
        content_type="application/json",
        declared_parser=name,
        parser_is_identity=flag,
    )
    assert "parser_identity_flag_disagrees_with_name" in payload.refusal_codes
    assert payload.parser_is_identity is flag, "the caller's flag is taken as given, not corrected"


def test_an_identity_flag_with_no_name_is_a_missing_declaration_not_a_disagreement() -> None:
    """There is nothing to disagree with when nothing was declared, so nothing is invented."""
    payload = default_registry().parse(
        body=b'{"a": 1}',
        content_type="application/json",
        declared_parser="",
        parser_is_identity=True,
    )
    assert "parser_name_empty" in payload.refusal_codes
    assert "parser_identity_flag_disagrees_with_name" not in payload.refusal_codes


def test_a_duplicate_registration_is_refused_rather_than_overwritten() -> None:
    registry = default_registry()
    with pytest.raises(PayloadContractError) as raised:
        registry.register(
            RegisteredParser(name=TEXT_PRODUCER, extract=lambda **_: ExtractorResult(()))
        )
    assert raised.value.code == "parser_name_already_registered"


def test_the_registry_lists_its_names_in_sorted_order_whatever_the_registration_order() -> None:
    """Dispatch order is a property of the names, not of the order they arrived in."""
    first = PayloadParserRegistry(
        [
            RegisteredParser(name="zeta", extract=lambda **_: ExtractorResult(())),
            RegisteredParser(name="alpha", extract=lambda **_: ExtractorResult(())),
        ]
    )
    second = PayloadParserRegistry(
        [
            RegisteredParser(name="alpha", extract=lambda **_: ExtractorResult(())),
            RegisteredParser(name="zeta", extract=lambda **_: ExtractorResult(())),
        ]
    )
    assert first.names() == second.names()
    assert list(first.names()) == sorted(first.names())


def test_the_two_built_ins_are_registered_from_construction_and_never_change() -> None:
    """A registry whose contents depend on whether anybody has parsed yet is not reproducible."""
    registry = PayloadParserRegistry()
    assert registry.names() == (STRUCTURED_PRODUCER, TEXT_PRODUCER)
    registry.parse(body=b"x\n", content_type="text/plain")
    assert registry.names() == (STRUCTURED_PRODUCER, TEXT_PRODUCER)
    assert PayloadParserRegistry().names() == registry.names()


def test_a_parser_with_no_name_is_refused() -> None:
    with pytest.raises(PayloadContractError) as raised:
        RegisteredParser(name="   ", extract=lambda **_: ExtractorResult(()))
    assert raised.value.code == "parser_name_required"


# --------------------------------------------------------------------------- #
# The text route, in detail
# --------------------------------------------------------------------------- #


def _text(body: bytes):
    return default_registry().parse(
        body=body, content_type="text/plain", declared_parser="raw_text", parser_is_identity=True
    )


def test_a_line_is_the_bytes_between_terminators_and_nothing_more() -> None:
    payload = _text(b"alpha\r\nbeta\n")
    assert [record.value for record in payload.records] == ["alpha\r", "beta"]
    for record in payload.records:
        assert payload.read_span(body=b"alpha\r\nbeta\n", record=record) == record.value


def test_a_trailing_terminator_does_not_begin_a_line() -> None:
    """Otherwise every text payload ends with an artefact of the splitter rather than a line."""
    assert [record.value for record in _text(b"only\n").records] == ["only"]
    assert [record.value for record in _text(b"a\n\nb").records] == ["a", "", "b"]


def test_an_empty_line_is_a_record_rather_than_a_filter() -> None:
    payload = _text(b"a\n\nb")
    blank = payload.records[1]
    assert blank.value == ""
    assert blank.address_refusal == "field_surface_empty"
    assert len(payload.records) == 3


def test_the_ceilings_apply_to_the_text_route_too() -> None:
    payload = default_registry().parse(
        body=b"x\n" * 500,
        content_type="text/plain",
        declared_parser="raw_text",
        parser_is_identity=True,
        bounds=ParseBounds(max_nodes=10, max_records_per_value_type=1000, max_depth=64),
    )
    assert payload.truncated is True
    assert payload.truncation_reason == "nodes_visited"
    assert len(payload.records) == 10


def test_binary_bytes_on_the_text_route_are_refused_rather_than_replaced() -> None:
    """A replacement character would be a value the payload does not contain."""
    payload = _text(b"good\n\xff\xfe bad\n")
    assert payload.records == ()
    assert payload.refusal_codes == ("payload_not_utf8",)
    assert payload.refusals[0].offset == 5


# --------------------------------------------------------------------------- #
# P5: the 23 identity-parser definitions, against the real catalogue
# --------------------------------------------------------------------------- #


def declared_parser_of(path: Path) -> tuple[str, str]:
    """``(name, parser)`` from one definition file, read as the two top-level scalars they are.

    Read as text, on purpose: the parser layer does not import ``sources`` (it runs below
    acquisition's transport, reading the published observation), and a test that reached for the
    loader to learn a field the loader already published would be a test of the loader. The scan
    is column-zero ``name:`` and ``parser:`` lines — the two keys, at the top level, nothing
    else.
    """
    name = ""
    parser = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if not parser and line.startswith("parser:"):
            parser = line.split(":", 1)[1].strip().strip("\"'")
        if not name and line.startswith("name:"):
            name = line.split(":", 1)[1].strip().strip("\"'")
    return name, parser


def catalogue_definitions() -> tuple[tuple[str, str], ...]:
    paths = sorted(
        p for p in ESTORIDES.rglob("*") if p.suffix in (".yaml", ".yml") and p.is_file()
    )
    return tuple(declared_parser_of(path) for path in paths)


def test_the_catalogue_holds_the_identity_definitions_this_rule_was_written_for() -> None:
    """The count P5 states, measured rather than recalled."""
    definitions = catalogue_definitions()
    assert len(definitions) == 145, (
        "the catalogue is not the corpus this rule was written against; re-read P5 before "
        "changing the count below"
    )
    identity = [name for name, parser in definitions if parser in IDENTITY_PARSER_NAMES]
    assert len(identity) == IDENTITY_DEFINITION_COUNT
    # Every one of them declares the same name, so "raw_text" is the whole of the identity
    # population in this catalogue and the four-name mirror is wider than the corpus needs.
    assert {parser for _, parser in definitions if parser in IDENTITY_PARSER_NAMES} == {
        "raw_text"
    }


def test_the_identity_name_mirror_agrees_with_the_catalogue_that_owns_the_rule() -> None:
    """The one cross-app read in this suite, and it is a mirror check and nothing else.

    :data:`parsers.payload.registry.IDENTITY_PARSER_NAMES` restates
    ``sources.catalogue.IDENTITY_PARSERS`` because the parser layer must not import the
    acquisition package. A restatement without this check is a second definition of one rule, and
    two definitions of one rule drift — so this test reads the catalogue's own constant and
    fails loudly when the two disagree.
    """
    from sources.catalogue import IDENTITY_PARSERS

    assert IDENTITY_PARSER_NAMES == frozenset(IDENTITY_PARSERS)


@pytest.mark.parametrize("name", sorted(IDENTITY_PARSER_NAMES))
def test_every_identity_parser_name_is_routed_to_the_text_extractor_on_a_text_payload(
    name: str,
) -> None:
    """Per definition, and by name: this is the "either give them a real parser or say what
    happens" half of P5, applied to every name rather than asserted once."""
    payload = default_registry().parse(
        body=b"first line\nsecond line\n",
        content_type="text/plain",
        declared_parser=name,
        parser_is_identity=True,
    )
    assert payload.routed_to == TEXT_PRODUCER
    assert payload.parser_is_identity is True
    assert payload.declared_parser == name
    assert payload.refusals == ()
    assert {record.label for record in payload.records} == {"text_line"}
    assert not any(record.field.startswith("$[") for record in payload.records), (
        "a text route must not emit a JSON key path, however much the payload looks like JSON"
    )


def test_no_bespoke_parser_was_written_for_any_of_the_23_and_that_is_the_decision() -> None:
    """The count of bespoke parsers is **zero**, and the assertion is on what is registered.

    Writing one parser per source would be writing down what 92 APIs *probably* return — the
    key-name heuristic and the defaulted type this layer exists to remove — so the registry ships
    two extractors and refuses every other name.
    """
    assert default_registry().names() == (STRUCTURED_PRODUCER, TEXT_PRODUCER)
    assert IDENTITY_PARSER_NAMES == frozenset({"raw_text", "raw", "identity", "json"})


# --------------------------------------------------------------------------- #
# The mutations: a missing truncation report, and a type detector that guesses
# --------------------------------------------------------------------------- #


def _mutated_package(filename: str, find: str, replace: str) -> Path:
    """A throwaway copy of the two packages with one edit applied to one module."""
    root = Path(tempfile.mkdtemp(prefix="payload-mutation-"))
    for package, members in _COPIED:
        for member in members:
            source = APPS / package / member
            if source.is_dir():
                shutil.copytree(
                    source, root / source.name, ignore=shutil.ignore_patterns("__pycache__")
                )
            elif source.exists():
                shutil.copy2(source, root / source.name)
    target = (root / "parsers" / "payload" / filename).resolve()
    text = target.read_text(encoding="utf-8")
    assert find in text, f"mutation anchor not found in {filename}: {find[:70]!r}"
    target.write_text(text.replace(find, replace, 1), encoding="utf-8")
    return root


def _child_env(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root)
    return env


def _run(script: str, root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(root),
        env=_child_env(root),
        check=False,
    )


_TRUNCATION_SCRIPT = """
from parsers.payload import ParseBounds, default_registry

body = b"[" + b",".join(b'"v%d"' % index for index in range(200)) + b"]"
payload = default_registry().parse(
    body=body,
    content_type="application/json",
    declared_parser="structured_fields",
    bounds=ParseBounds(max_nodes=16, max_records_per_value_type=1000, max_depth=64),
)
print(payload.truncated, payload.bound_hit, len(payload.records))
print("TRUNCATION_LOST" if not payload.truncated else "TRUNCATION_REPORTED")
"""


def test_removing_the_truncation_report_makes_a_source_look_untruncated_and_is_caught() -> None:
    """A silent truncation is how a source looks empty when it is not, so it must be observable.

    The mutation drops the one line that carries the walk's bound hit onto the payload. Records
    still come back — the walk still stopped — which is precisely the failure: everything looks
    like a short answer rather than a stopped read.
    """
    root = _mutated_package(
        "registry.py",
        "            refusals=(*routing, *result.refusals),\n"
        "            bound_hit=result.bound_hit,\n",
        "            refusals=(*routing, *result.refusals),\n            bound_hit=None,\n",
    )
    try:
        completed = _run(_TRUNCATION_SCRIPT, root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert completed.returncode == 0, (
        f"the mutated copy did not run, so the mutation proved nothing: {completed.stderr[-2000:]}"
    )
    assert "TRUNCATION_LOST" in completed.stdout, (
        "dropping the bound hit did not make the parse look untruncated, so nothing guards the "
        f"truncation report. Child said: {completed.stdout!r}"
    )


def test_the_unmutated_registry_reports_the_truncation() -> None:
    completed = _run(_TRUNCATION_SCRIPT, INTERPRETATION)
    assert completed.returncode == 0, completed.stderr[-2000:]
    assert "TRUNCATION_REPORTED" in completed.stdout, (
        f"the truncation report was already missing: {completed.stdout!r}"
    )
    assert "nodes_visited" in completed.stdout


_TYPE_GUESS_SCRIPT = """
from parsers.payload import default_registry

payload = default_registry().parse(
    body=b'{"zip": "90210", "ip": "10.0.0.1"}',
    content_type="application/json",
    declared_parser="structured_fields",
)
kinds = {record.field: str(record.value_type) for record in payload.records}
print(kinds)
guessed = [f for f, k in kinds.items() if k == "number"]
print("TYPE_GUESS_UNCAUGHT" if guessed else "TYPE_HONEST")
"""


def test_a_type_detector_that_guesses_is_caught() -> None:
    """The mutation: a string that looks like a number is reclassified as one.

    That is the shape of the defect this layer exists to remove — ``{"zip": "90210"}`` becoming a
    number because a number is what a zip *looks like* — and it is one ``if`` statement away, so
    it is here as a mutation rather than as a warning in a docstring.
    """
    root = _mutated_package(
        "structured.py",
        "        self._guard_type(value_type)\n        address, refusal = address_for(\n",
        "        if value_type is ValueType.STRING and value.strip().isdigit():\n"
        "            value_type = ValueType.NUMBER\n"
        "        self._guard_type(value_type)\n"
        "        address, refusal = address_for(\n",
    )
    try:
        completed = _run(_TYPE_GUESS_SCRIPT, root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert completed.returncode == 0, (
        f"the mutated copy did not run, so the mutation proved nothing: {completed.stderr[-2000:]}"
    )
    assert "TYPE_GUESS_UNCAUGHT" in completed.stdout, (
        "a digit-shaped string was still reported as a string, so the value-type tests are not "
        f"watching the detector. Child said: {completed.stdout!r}"
    )


def test_the_unmutated_detector_reports_a_digit_shaped_string_as_a_string() -> None:
    completed = _run(_TYPE_GUESS_SCRIPT, INTERPRETATION)
    assert completed.returncode == 0, completed.stderr[-2000:]
    assert "TYPE_HONEST" in completed.stdout, (
        f"the detector was already guessing: {completed.stdout!r}"
    )
