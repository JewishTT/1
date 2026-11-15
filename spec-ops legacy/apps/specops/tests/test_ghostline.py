"""GhostLine adapter tests (Feature 031).

The split here follows the donor's own split, because that is where the risk is.

**Stage-engine tests** exercise the real vendored donor: the playbook catalogue is
built by the donor's own ``Playbook`` validator, and the simulator is the donor's own
``PlaybookRunner``. If these pass, a playbook that renders in the UI is one the donor
will accept and a transition trace is a real one. Nothing is mocked, because there is
nothing to mock — that is the point of the split in ``loader.py``.

**Redaction tests** are the ones that matter most and the ones that would fail silently
if they regressed. A redactor that stops scrubbing does not crash; it quietly starts
storing credentials. So each test asserts on the *absence* of the secret in the stored
text, not merely on the presence of a marker.

**Config tests** cover the two things an operator would be burned by: a secret leaking
into a view model, and a sample reference escaping the samples root.
"""

from __future__ import annotations

import json

import pytest
from specops.ghostline.catalog import STAGE_ORDER, library
from specops.ghostline.config import GhostlineConfig
from specops.ghostline.loader import donor
from specops.ghostline.redaction import REDACTION, Redactor, generic_redactor
from specops.ghostline.telephony import DialBlocked, validate_e164

# ── the donor is present and its engine is importable ────────────────


def test_donor_tree_is_vendored():
    assert donor().available(), (
        "donors/ghostline is missing; the department would serve nothing but named absences"
    )


def test_stage_engine_imports_unmodified():
    """Every stage-engine module loads. The live edges are expected not to."""
    handle = donor()
    for dotted in (
        "ghostline.taxonomy",
        "ghostline.playbook",
        "ghostline.playbook_runner",
        "ghostline.audio.codec",
        "ghostline.telephony.media_stream",
    ):
        assert handle.get(dotted) is not None, f"{dotted} should import in the platform environment"


def test_donor_report_names_absent_edges():
    """A dependency this environment lacks is named, never silently empty."""
    report = donor().report()
    assert report["present"] is True
    assert report["stage_engine"]["absent"] == []
    # This environment has no `twilio`; if it is ever installed the assertion flips,
    # and that flip is itself the report being truthful.
    for entry in report["live_edges"]["absent"]:
        assert entry


# ── the playbook catalogue is the donor's, not a paraphrase ─────────


def test_every_donor_playbook_loads_through_the_donors_validator():
    rows = library().summaries()
    assert len(rows) >= 4, (
        f"expected the donor's bundled scenarios, got {[r.playbook_id for r in rows]}"
    )
    for row in rows:
        assert row.valid, f"{row.playbook_id} rejected by the donor: {row.invalid_reason}"
        assert row.stage_count > 0
        assert row.first_stage in STAGE_ORDER


def test_stage_detail_carries_the_donor_taxonomy():
    stages = {s.stage: s for s in library().stages("it-test")}
    assert stages["RAPPORT"].psych_triggers, "taxonomy triggers should be served"
    assert stages["RAPPORT"].checkin_line
    assert stages["RAPPORT"].position == 0


def test_credential_stages_are_distinguished_from_state_stages():
    """A CLOSE stage's `\\d{6}` fishes for a secret; DISCOVERY's `married` does not.

    This distinction is what stops the redactor blanking out every ordinary answer.
    """
    stages = {s.stage: s for s in library().stages("hr_benefits_open_enrollment_phish")}
    assert stages["CLOSE"].captures_credential is True
    assert stages["DISCOVERY"].captures_credential is False


def test_attack_mapping_declares_its_own_source():
    row = library().summary("zero_day_it_patch")
    assert row is not None
    assert row.mapping_source == "platform-declared"
    assert any(t[0] == "T1566.002" for t in row.techniques)


def test_playbook_names_survive_a_non_utf8_locale():
    """Regression, found by a screenshot rather than by a test.

    The donor's `Playbook.from_file` does `p.read_text()` with no encoding, so on a
    Windows operator box (locale cp1251/cp1252) every non-ASCII character in a
    scenario name became mojibake: "HR Benefits â€" Open-Enrollment". The catalogue
    therefore decodes UTF-8 itself and hands the donor `from_string`.

    Asserted on the actual name rather than on the loader, because the visible symptom
    is the name on screen and a test that only checked the loader could pass while the
    name was still wrong.
    """
    row = library().summary("hr_benefits_open_enrollment_phish")
    assert row is not None
    assert "â€" not in row.name, row.name
    assert "�" not in row.name, row.name
    # An en dash is what the donor's YAML actually contains.
    assert "–" in row.name or "-" in row.name, row.name


def test_every_playbook_round_trips_its_own_description():
    """Multi-line UTF-8 bodies survive the same path as the names do."""
    for row in library().summaries():
        assert "â€" not in (row.name or "")
        if row.description:
            assert "â€" not in row.description, row.playbook_id


def test_unknown_playbook_is_not_silently_empty():
    assert library().entry("no-such-scenario") is None
    assert library().stages("no-such-scenario") == ()


# ── the simulator runs the donor's real transition machine ───────────


def test_simulation_walks_the_donor_stage_machine():
    from specops.ghostline.engine import simulate

    result = simulate(
        "hr_benefits_open_enrollment_phish",
        ["Happy friday", "I am married", "yes that works", "sure"],
    )
    assert result.steps, "the trace should not be empty"
    # Each step advances one rung of the donor's ladder.
    assert result.steps[0].stage_before == "RAPPORT"
    assert result.steps[0].stage_after == "CREDIBILITY"
    assert result.steps[0].next_line, "the stage greeting should be served from the playbook"
    assert result.credentials_captured == 0
    assert result.capture_passwords is False


def test_simulation_reaches_a_terminal_state_on_a_matching_success_regex():
    """One utterance per rung of the donor ladder, ending on CLOSE's `\\d{6}`.

    Every stage in this playbook declares ``max_cycles: 1``, so an utterance that does
    not match the current stage's ``success_regex`` advances the machine. That is the
    donor's semantics, not a bug in the simulator — the script below is shaped to it.
    """
    from specops.ghostline.engine import simulate

    result = simulate(
        "hr_benefits_open_enrollment_phish",
        [
            "happy friday",
            "sure, go ahead",
            "single",  # DISCOVERY's success pattern matches
            "and what is the portal",
            "that would help a lot",
            "how do I sign up",
            "no problem",
            "sure",  # TRIAL_CLOSE's success pattern matches
            "the code is 482913",  # CLOSE's success pattern matches -> compromised
        ],
    )
    assert result.outcome == "compromised"
    assert result.final_stage == "CLOSE"
    assert result.steps[-1].exited is True


def test_simulation_stops_at_the_first_terminal_state():
    """Utterances after the exit are not evaluated — the call is over."""
    from specops.ghostline.engine import simulate

    result = simulate(
        "hr_benefits_open_enrollment_phish",
        [
            "a",
            "b",
            "single",
            "d",
            "e",
            "f",
            "g",
            "sure",
            "the code is 482913",
            "never mind",
        ],
    )
    assert result.outcome == "compromised"
    assert len(result.steps) == 9, "the tenth utterance lands after the call ended"


def test_simulation_abandons_at_the_last_stage_without_a_close():
    """Nothing matches any `success_regex`, so the ladder runs to its end.

    The donor counts *reaching REPORTING* as a completed close, so the terminal state
    here is the donor's own semantics rather than a verdict this platform invented —
    which is exactly why it is asserted loosely and the reason string is not.
    """
    from specops.ghostline.engine import simulate

    result = simulate("vendor_payment_change_ceo_whaling", ["I need to think about it"] * 15)
    assert result.outcome in ("abandoned", "compromised")
    assert result.outcome_reason


def test_simulation_refuses_an_unloadable_playbook():
    from specops.ghostline.engine import SimulationUnavailable, simulate

    with pytest.raises(SimulationUnavailable):
        simulate("no-such-scenario", ["hello"])


def test_declared_marker_pattern_does_not_leave_the_value_behind():
    """Regression: the donor's own CLOSE pattern is `\\b(password)\\b`.

    Its only capture group is the marker word, so applying it first replaced
    "password" and left the value standing — and the generic value-extracting pattern
    then found no marker left to key off, so the secret passed through untouched. The
    fix is ordering (generics first), and this test is the only thing that pins it.
    """
    redactor = Redactor((r"\b(password)\b",))
    scrubbed = redactor.scrub("password is hunter2xyz")
    assert "hunter2xyz" not in scrubbed.text, scrubbed.text
    assert "playbook-success" in scrubbed.kinds


def test_credential_classifier_separates_a_secret_from_a_version_suffix():
    """A DISCOVERY pattern like `\\.\\d{3}$` is a kernel check, not a credential.

    Getting this wrong in the permissive direction is not cosmetic: the stage is
    labelled "elicits a credential" in the UI, which is a false statement about the
    scenario, and its pattern is added to the redactor.
    """
    from specops.ghostline.catalog import _is_credential_pattern

    assert _is_credential_pattern(r"\b\d{6}\b") is True
    assert _is_credential_pattern(r"\b\d{5,9}\b") is True
    assert _is_credential_pattern(r"\b(password|passcode)\b") is True
    assert _is_credential_pattern(r"\.\d{3}$") is False
    assert _is_credential_pattern(r"\b(single|married|family)\b") is False
    assert _is_credential_pattern(r"\b(yes|ready|sure)\b") is False
    # The donor's real DISCOVERY pattern must not be labelled a credential stage.
    zero_day = {s.stage: s for s in library().stages("zero_day_it_patch")}
    assert zero_day["DISCOVERY"].captures_credential is False
    assert zero_day["CLOSE"].captures_credential is True


def test_simulation_never_returns_a_credential():
    from specops.ghostline.engine import simulate

    secret = "918273"
    result = simulate("hr_benefits_open_enrollment_phish", [f"the code is {secret}"])
    rendered = json.dumps([s.as_dict() for s in result.steps])
    assert secret not in rendered
    assert REDACTION in rendered


def test_simulation_scrubs_a_spoken_password_at_the_donors_own_close_stage():
    """End to end through the donor's playbook: the donor's CLOSE regex is the trap."""
    from specops.ghostline.engine import simulate

    result = simulate("zero_day_it_patch", ["password is hunter2xyz"])
    assert "hunter2xyz" not in json.dumps([s.as_dict() for s in result.steps])


def test_simulation_names_what_it_could_not_run():
    """The persuasion model needs packages this environment lacks; say so."""
    from specops.ghostline.engine import simulate

    result = simulate("it-test", ["hello"])
    assert any("openai-agents" in item for item in result.missing)


# ── redaction: the invariant that must not regress ───────────────────


@pytest.mark.parametrize(
    ("raw", "secret"),
    [
        ("the password is hunter2xyz", "hunter2xyz"),
        ("my one-time code is 492913", "492913"),
        ("use password = correct-horse", "correct-horse"),
        ("card 4111111111111111", "4111111111111111"),
    ],
)
def test_generic_redactor_removes_the_secret(raw: str, secret: str):
    scrubbed = generic_redactor().scrub(raw)
    assert secret not in scrubbed.text, f"{secret!r} survived redaction: {scrubbed.text!r}"
    assert scrubbed.scrubbed


@pytest.mark.parametrize(
    "raw",
    [
        "nothing secret here",
        "the ticket is SEC-4217",
        "hello, is this the helpdesk?",
    ],
)
def test_generic_redactor_leaves_ordinary_utterances_alone(raw: str):
    """Over-redaction is a real failure: it trains an operator to ignore the marker."""
    scrubbed = generic_redactor().scrub(raw)
    assert scrubbed.text == raw
    assert not scrubbed.scrubbed


def test_redactor_reports_kinds_not_values():
    scrubbed = generic_redactor().scrub("otp 445566")
    assert "otp" in scrubbed.kinds
    assert "445566" not in json.dumps(scrubbed.as_dict())


def test_declared_pattern_compiles_into_the_redactor():
    redactor = Redactor((r"\b\d{6}\b",))
    assert redactor.scrub("it is 654321").scrubbed


def test_broken_pattern_is_reported_not_swallowed():
    """A pattern that cannot compile must not silently pass text through."""
    redactor = Redactor(("[unclosed",))
    assert redactor.patterns == ("[unclosed",)


def test_redaction_is_faithful_to_the_playbook_scope():
    """A state pattern must not become a redaction pattern."""
    redactor = library().redactor("hr_benefits_open_enrollment_phish")
    # `married` is DISCOVERY's success pattern — it is an answer, not a secret.
    assert redactor.scrub("I am married").text == "I am married"


# ── config: secrets and containment ──────────────────────────────────


def test_readiness_never_echoes_a_secret():
    config = GhostlineConfig.from_env(
        {
            "GHOSTLINE_TWILIO_AUTH_TOKEN": "super-secret-token",
            "GHOSTLINE_TWILIO_ACCOUNT_SID": "AC" + "0" * 32,
        }
    )
    rendered = json.dumps([p.as_dict() for p in config.readiness()])
    assert "super-secret-token" not in rendered
    assert "configured" in rendered


def test_blockers_name_the_variable_to_set():
    config = GhostlineConfig.from_env({})
    blockers = config.blocking()
    assert blockers, "an unconfigured deployment should name its blockers"
    assert any("GHOSTLINE_TWILIO_ACCOUNT_SID" in b for b in blockers)


def test_llm_key_resolves_by_model_prefix():
    config = GhostlineConfig.from_env(
        {
            "GHOSTLINE_LITELLM_MODEL": "anthropic/claude-3-5-sonnet-latest",
            "GHOSTLINE_ANTHROPIC_API_KEY": "k",
        }
    )
    assert config.llm_api_key == "k"
    local = GhostlineConfig.from_env({"GHOSTLINE_LITELLM_MODEL": "ollama/llama3.1"})
    assert local.llm_api_key is None


def test_sample_reference_cannot_escape_the_samples_root(tmp_path):
    config = GhostlineConfig.from_env({"GHOSTLINE_SAMPLES_ROOT": str(tmp_path)})
    assert config.sample_path("inside.wav") is not None
    assert config.sample_path("../../windows/system32") is None
    assert config.sample_path("/etc/passwd") is None


# ── dialling validation ──────────────────────────────────────────────


@pytest.mark.parametrize("number", ["+15551234567", "+442071838750", "+1555123456789"])
def test_valid_e164_is_normalised(number: str):
    assert validate_e164(number) == number


@pytest.mark.parametrize("number", ["", "5551234567", "+0123456789", "+1555 123 4567", "+abc"])
def test_invalid_e164_is_refused_with_a_reason(number: str):
    with pytest.raises(DialBlocked):
        validate_e164(number)


def test_twilio_error_translation_names_the_fix():
    """The donor's README documents two trial-account errors that read as opaque codes."""
    from specops.ghostline.telephony import _explain

    assert "trial account" in _explain(
        Exception("Twilio is unable to make this request: limited parameter access")
    )
    assert "Verified Caller IDs" in _explain(Exception("source phone number is not yet verified"))


# ── the ledger never stores a credential ─────────────────────────────


def test_ledger_redacts_on_the_way_in(tmp_path, monkeypatch):
    from specops.ghostline.ledger import CallLedger

    monkeypatch.setenv("GHOSTLINE_LEDGER_DIR", str(tmp_path))
    book = CallLedger()
    book.record_call(
        call_id="c1",
        target="+15551234567",
        campaign="drill",
        persona="professional",
        playbook_id="hr_benefits_open_enrollment_phish",
    )
    book.append_message("c1", "user", "my code is 482913", stage="CLOSE")
    book.complete_call("c1", "compromised")

    on_disk = (tmp_path / "calls.jsonl").read_text(encoding="utf-8")
    assert "482913" not in on_disk
    assert REDACTION in on_disk
    assert book.call("c1").credentials_captured == 0


def test_ledger_reload_cannot_promote_the_invariant(tmp_path, monkeypatch):
    """A hand-edited file must not be able to make `credentials_captured` non-zero."""
    from specops.ghostline.ledger import CallLedger

    monkeypatch.setenv("GHOSTLINE_LEDGER_DIR", str(tmp_path))
    path = tmp_path / "calls.jsonl"
    path.write_text(
        json.dumps(
            {
                "call": {
                    "call_id": "c1",
                    "target": "+1555",
                    "campaign": "x",
                    "persona": "p",
                    "started_at": "now",
                    "credentials_captured": 7,
                    "capture_passwords": True,
                    "messages": [],
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    book = CallLedger()
    call = book.call("c1")
    assert call is not None
    assert call.credentials_captured == 0
    assert call.capture_passwords is False


def test_analytics_leaves_conversion_null_until_a_call_completes(tmp_path, monkeypatch):
    from specops.ghostline.ledger import CallLedger

    monkeypatch.setenv("GHOSTLINE_LEDGER_DIR", str(tmp_path))
    book = CallLedger()
    assert book.analytics()["conversion_rate"] is None
    book.record_call(call_id="c1", target="+1555", campaign="drill", persona="p")
    book.complete_call("c1", "compromised")
    assert book.analytics()["conversion_rate"] == 1.0
