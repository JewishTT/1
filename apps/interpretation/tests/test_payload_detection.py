"""P3: the JSON-text decision is a named rule, and dropping the rule is observable.

Feature 021 brief §25; constitution IV (fail-closed) and VI (determinism, Domain Invariant 12).

**The defect this pins.** The upstream HTTP client decided "is this JSON?" by looking at the
first non-space character — inside the transport, unrecorded, and invisible to every reader of
the transport. Two consequences follow and both are tested here: a payload the transport
declared to be text was parsed as JSON anyway, and nothing downstream could tell which rule had
decided anything.

So detection lives in :mod:`parsers.payload.detect`, decides from the **declared** content type
first and a **declared** probe second, and returns the rule that decided. The three properties
worth having a test for are: a JSON body served as ``text/plain`` is **not** upgraded; the rule
that decided travels with the answer; and removing the content-type rule is a change of
behaviour a test notices — which is the mutation at the bottom of this file.
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
    DETECTION_RULES,
    Detection,
    DetectionRule,
    declares_json,
    detect_json_text,
    media_type_essence,
    parse_structured_fields,
    probe_json_text,
)

pytestmark = pytest.mark.unit

APPS = Path(__file__).resolve().parents[2]
INTERPRETATION = APPS / "interpretation"
PAYLOAD = INTERPRETATION / "parsers" / "payload"
_COPIED = (
    ("interpretation", ("extractors", "parsers", "semantic", "contracts.py")),
    ("shared", ("domain",)),
)

_JSON_BODY = b'{"ip": "10.0.0.1"}'


# --------------------------------------------------------------------------- #
# The rule table
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("content_type", "expected"),
    [
        ("application/json", DetectionRule.CONTENT_TYPE_JSON),
        ("application/json; charset=utf-8", DetectionRule.CONTENT_TYPE_JSON),
        ("Application/JSON", DetectionRule.CONTENT_TYPE_JSON),
        ("  application/json  ", DetectionRule.CONTENT_TYPE_JSON),
        ("application/ld+json", DetectionRule.CONTENT_TYPE_JSON),
        ("application/rdap+json", DetectionRule.CONTENT_TYPE_JSON),
        ("application/geo+json", DetectionRule.CONTENT_TYPE_JSON),
        ("text/plain", DetectionRule.CONTENT_TYPE_DECLARED_NOT_JSON),
        ("text/plain; charset=us-ascii", DetectionRule.CONTENT_TYPE_DECLARED_NOT_JSON),
        ("text/html", DetectionRule.CONTENT_TYPE_DECLARED_NOT_JSON),
        ("application/octet-stream", DetectionRule.CONTENT_TYPE_DECLARED_NOT_JSON),
        # ``text/json`` is not a registered media type. Accepting it would be a guess, so it is
        # routed by the non-JSON rule and the caller can see it was declared.
        ("text/json", DetectionRule.CONTENT_TYPE_DECLARED_NOT_JSON),
        ("", DetectionRule.NO_DECLARATION),
        (None, DetectionRule.NO_DECLARATION),
    ],
)
def test_the_declared_content_type_decides_and_the_rule_says_which(
    content_type: str | None, expected: DetectionRule
) -> None:
    detection = detect_json_text(content_type=content_type, body=_JSON_BODY)
    assert detection.rule is expected
    assert detection.is_json is (expected is DetectionRule.CONTENT_TYPE_JSON)


def test_the_probe_only_runs_when_nothing_was_declared() -> None:
    """Rules 1 and 2 decide from the declaration; the probe is rule 3's job alone."""
    declared = detect_json_text(
        content_type="application/json", body=_JSON_BODY, probe_when_undeclared=True
    )
    assert declared.rule is DetectionRule.CONTENT_TYPE_JSON
    assert declared.probe_matched is False
    assert declared.probe_offset is None
    undeclared = detect_json_text(
        content_type=None, body=_JSON_BODY, probe_when_undeclared=True
    )
    assert undeclared.rule is DetectionRule.PROBE_JSON_TEXT
    assert undeclared.probe_offset == 0
    assert undeclared.probe_matched is True


def test_an_undeclared_payload_with_no_probe_is_not_json_and_says_so() -> None:
    """The safe default is "not JSON", recorded as a decision rather than as an absence."""
    detection = detect_json_text(content_type=None, body=_JSON_BODY, probe_when_undeclared=False)
    assert detection.rule is DetectionRule.NO_DECLARATION
    assert detection.is_json is False
    assert detection.probe_offset is None


def test_the_probe_skips_exactly_the_four_bytes_json_calls_whitespace() -> None:
    """A probe whose whitespace rule is not written down is the upstream defect in miniature."""
    matched, offset = probe_json_text(b" \t\r\n{")
    assert (matched, offset) == (True, 4)
    matched, offset = probe_json_text(b"   ")
    assert (matched, offset) == (False, None)
    matched, offset = probe_json_text(b"")
    assert (matched, offset) == (False, None)
    # A bare scalar is a legal JSON document and is not a container, so the probe declines it.
    assert probe_json_text(b'"a string"') == (False, 0)
    assert probe_json_text(b"[1,2]") == (True, 0)


def test_a_json_body_served_as_text_plain_is_not_upgraded_and_the_rule_is_reported() -> None:
    """**The** property P3 exists for, on the whole registry rather than on the seam alone.

    A source that returns JSON under ``text/plain`` is read as text — one record per line, no
    structure claimed — and the payload says which rule decided, so an operator looking at a
    payload that "should have parsed" can see that it was the header, not the bytes.
    """
    from parsers.payload import TEXT_PRODUCER, default_registry

    payload = default_registry().parse(
        body=_JSON_BODY,
        content_type="text/plain",
        declared_parser="raw_text",
        parser_is_identity=True,
    )
    assert payload.detection.rule is DetectionRule.CONTENT_TYPE_DECLARED_NOT_JSON
    assert payload.detection.is_json is False
    assert payload.detection.to_dict()["rule"] == "content_type_declared_not_json"
    assert payload.routed_to == TEXT_PRODUCER
    assert payload.records, "a text route must still produce records"
    assert all(record.label == "text_line" for record in payload.records)
    # The body is one line here, so the line is the whole payload and no key path is claimed.
    assert payload.records[0].value == _JSON_BODY.decode()


def test_a_declared_probe_does_not_override_a_declared_content_type() -> None:
    """Asking for the probe must not become permission to ignore a declaration."""
    from parsers.payload import TEXT_PRODUCER, default_registry

    payload = default_registry().parse(
        body=_JSON_BODY,
        content_type="text/plain",
        declared_parser="raw_text",
        parser_is_identity=True,
        probe_when_undeclared=True,
    )
    assert payload.detection.rule is DetectionRule.CONTENT_TYPE_DECLARED_NOT_JSON
    assert payload.routed_to == TEXT_PRODUCER
    assert payload.records[0].label == "text_line"


def test_the_structured_parser_refuses_a_payload_the_seam_ruled_not_json() -> None:
    """Defence in depth: the routing decision cannot be made anywhere but the seam."""
    detection = detect_json_text(content_type="text/plain", body=_JSON_BODY)
    result = parse_structured_fields(_JSON_BODY, detection=detection)
    assert result.records == ()
    assert [refusal.code for refusal in result.refusals] == ["payload_not_json"]
    assert detection.rule in result.refusals[0].detail


def test_the_media_type_essence_drops_parameters_and_case_and_nothing_else() -> None:
    assert media_type_essence("application/json; charset=utf-8") == "application/json"
    assert media_type_essence("TEXT/HTML") == "text/html"
    assert media_type_essence(None) == ""
    assert media_type_essence("   ") == ""


def test_only_a_registered_json_media_type_declares_json() -> None:
    assert declares_json("application/json")
    assert declares_json("application/vnd.api+json")
    assert not declares_json("text/json")
    assert not declares_json("application/jsonx")
    assert not declares_json("json")
    assert not declares_json("")


def test_the_rule_vocabulary_is_closed_and_five_members_long() -> None:
    """A rule nobody can enumerate is a decision nobody can audit."""
    assert [str(rule) for rule in DETECTION_RULES] == [
        "content_type_json",
        "content_type_declared_not_json",
        "probe_json_text",
        "probe_not_json",
        "no_declaration",
    ]
    with pytest.raises(ValueError):
        DetectionRule("first_non_space_character")


def test_detection_is_total_for_any_content_type_and_any_bytes() -> None:
    for content_type in ("", None, "application/json", "!!!not a media type!!!"):
        for body in (b"", b"  ", b"\x00\xff", _JSON_BODY):
            assert isinstance(detect_json_text(content_type=content_type, body=body), Detection)


def test_the_detection_record_is_deterministic_and_carries_its_own_inputs() -> None:
    first = detect_json_text(content_type="application/json; charset=utf-8", body=_JSON_BODY)
    second = detect_json_text(content_type="application/json; charset=utf-8", body=_JSON_BODY)
    assert first.to_dict() == second.to_dict()
    assert first.to_dict()["declared"] == "application/json; charset=utf-8"
    assert first.to_dict()["media_type"] == "application/json"


# --------------------------------------------------------------------------- #
# The mutation: drop the content_type rule and this suite must notice
# --------------------------------------------------------------------------- #

_RULE_DROPPED_SCRIPT = """
from parsers.payload import default_registry

payload = default_registry().parse(
    body=b'{"ip": "10.0.0.1"}',
    content_type="text/plain",
    declared_parser="raw_text",
    parser_is_identity=True,
    probe_when_undeclared=True,
)
print(payload.detection.rule, payload.detection.is_json, payload.routed_to)
print(
    "CONTENT_TYPE_RULE_DROPPED"
    if payload.detection.is_json
    else "CONTENT_TYPE_RULE_HONOURED"
)
"""


def _mutated_package(find: str, replace: str) -> Path:
    """A throwaway copy of the two packages with one edit applied to ``detect.py``.

    The copy is flat — ``domain``, ``extractors``, ``parsers`` and ``semantic`` side by side —
    because that is the single ``PYTHONPATH`` entry a child interpreter needs. The repository is
    never written to.
    """
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
    target = (root / "parsers" / "payload" / "detect.py").resolve()
    text = target.read_text(encoding="utf-8")
    assert find in text, f"mutation anchor not found in detect.py: {find[:70]!r}"
    target.write_text(text.replace(find, replace, 1), encoding="utf-8")
    return root


def _child_env(root: Path) -> dict[str, str]:
    """The current environment with only ``PYTHONPATH`` redirected.

    Inherited rather than hand-built: a hand-built ``PATH`` without System32 is not a smaller
    environment on Windows, it is a broken one, and every child then fails with a Winsock error
    that looks like a test failure.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root)
    return env


def test_dropping_the_content_type_rule_upgrades_a_text_plain_body_and_is_caught() -> None:
    """The mutation test, and the reason the ``content_type`` tests are believed.

    Removing the declaration branch makes every payload undeclared, so the probe takes over and
    the JSON body served as ``text/plain`` is parsed as JSON — the exact defect P3 removes. The
    child reports the rule and the outcome, and this test asserts the outcome is the wrong one;
    ``test_the_unmutated_seam_still_honours_the_declaration`` is the other half, because a
    mutation test proves nothing if the unmutated code already failed.
    """
    root = _mutated_package(
        "    essence = media_type_essence(content_type)\n    if essence:\n",
        "    essence = \"\"\n    if essence:\n",
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-c", _RULE_DROPPED_SCRIPT],
            capture_output=True,
            text=True,
            cwd=str(root),
            env=_child_env(root),
            # The child's exit status is the subject of this test, not an error here.
            check=False,
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert completed.returncode == 0, (
        f"the mutated copy did not run, so the mutation proved nothing: {completed.stderr[-2000:]}"
    )
    assert "CONTENT_TYPE_RULE_DROPPED" in completed.stdout, (
        "removing the content-type rule did not change the routing of a JSON body served as "
        f"text/plain, so nothing in the suite guards it. Child said: {completed.stdout!r}"
    )


def test_the_unmutated_seam_still_honours_the_declaration() -> None:
    """The half that is easy to skip: the same script, the unmutated source."""
    completed = subprocess.run(
        [sys.executable, "-c", _RULE_DROPPED_SCRIPT],
        capture_output=True,
        text=True,
        cwd=str(INTERPRETATION),
        env=_child_env(INTERPRETATION),
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    assert "CONTENT_TYPE_RULE_HONOURED" in completed.stdout, (
        f"the declaration was already being ignored: {completed.stdout!r}"
    )
    assert "content_type_declared_not_json" in completed.stdout


def test_the_mutation_would_not_have_needed_this_package_to_be_imported_by_a_test() -> None:
    """The copy really does carry the package: a child can read the detector from it."""
    root = _mutated_package(
        "    essence = media_type_essence(content_type)\n    if essence:\n",
        "    essence = \"\"\n    if essence:\n",
    )
    try:
        assert (root / "parsers" / "payload" / "detect.py").exists()
        assert (root / "domain" / "mention_occurrence_index.py").exists()
        completed = subprocess.run(
            [sys.executable, "-c", "import parsers.payload; print(parsers.payload.__name__)"],
            capture_output=True,
            text=True,
            cwd=str(root),
            env=_child_env(root),
            check=False,
        )
        assert completed.returncode == 0, completed.stderr[-2000:]
        assert "parsers.payload" in completed.stdout
    finally:
        shutil.rmtree(root, ignore_errors=True)
    assert not (PAYLOAD / "detect.py.mutated").exists()
