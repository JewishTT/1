"""GhostLine router tests (Feature 031).

These go through the whole control plane over HTTP, because the properties that matter
are properties of the *route*, not of the adapter:

* the department's envelope is present on every response,
* the rules-of-engagement gate is reached before the donor is,
* an absent provider is a 424 with a reason and not a 500,
* ``credentials_captured`` is 0 everywhere, including on the error paths.

The last one gets its own test because it is the invariant most likely to be broken by
a future edit: it is asserted on the success path, on a refusal, and on the analytics
rollup, so no one can add a field that reports a captured credential without a test
noticing.
"""

from __future__ import annotations

import base64

import pytest
from fastapi.testclient import TestClient

BASE = "/api/v1/specops/ghostline"


@pytest.fixture
def client():
    from api.main import app

    return TestClient(app)


@pytest.fixture
def confirmed_roe(client):
    """A confirmed sign-off for the roster used below."""
    res = client.post(
        "/api/v1/specops/roe",
        json={
            "target_ref": "lab-target-1",
            "scope": "vishing drill",
            "approved_by": "supervisor@lab",
        },
    )
    assert res.status_code == 200, res.text
    return res.json()["roe_id"]


# ── envelope + status ────────────────────────────────────────────────


def test_status_carries_the_department_envelope(client):
    res = client.get(f"{BASE}/status")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["served"] == ["/specops/ghostline"]
    assert body["scope"] == "tenant-wide"
    assert isinstance(body["missing"], list)
    assert body["donor"]["present"] is True
    assert body["donor"]["license"] == "MIT"


def test_status_reports_provider_readiness_without_secrets(client, monkeypatch):
    monkeypatch.setenv("GHOSTLINE_TWILIO_AUTH_TOKEN", "a-secret-that-must-not-leak")
    res = client.get(f"{BASE}/status")
    assert res.status_code == 200
    assert "a-secret-that-must-not-leak" not in res.text
    assert any(p["name"] == "twilio" for p in res.json()["providers"])


def test_playbooks_are_served_with_their_techniques(client):
    res = client.get(f"{BASE}/playbooks")
    assert res.status_code == 200
    playbooks = res.json()["playbooks"]
    assert len(playbooks) >= 4
    for entry in playbooks:
        assert entry["mapping_source"] == "platform-declared"
        assert entry["techniques"], "a served technique list is never empty in this platform"
        if entry["techniques"]:
            assert "id" in entry["techniques"][0] and "reason" in entry["techniques"][0]


def test_playbook_detail_carries_stages_and_persona(client):
    res = client.get(f"{BASE}/playbooks/it-test")
    assert res.status_code == 200
    body = res.json()
    assert body["playbook"]["playbook_id"] == "it-test"
    assert len(body["stages"]) == body["playbook"]["stage_count"]
    assert body["persona"]["name"].startswith("Alex Morgan")
    # RUNG_ORDER: stages come back in the donor's canonical progression.
    assert body["stages"][0]["stage"] == "RAPPORT"


def test_unknown_playbook_is_a_404(client):
    assert client.get(f"{BASE}/playbooks/nope").status_code == 404


# ── the simulator ────────────────────────────────────────────────────


def test_simulate_runs_the_donor_stage_machine(client):
    res = client.post(
        f"{BASE}/playbooks/hr_benefits_open_enrollment_phish/simulate",
        json={"utterances": ["hello there", "that is fine", "single"]},
    )
    assert res.status_code == 200, res.text
    sim = res.json()["simulation"]
    assert sim["steps"][0]["stage_before"] == "RAPPORT"
    assert sim["credentials_captured"] == 0
    assert sim["capture_passwords"] is False


def test_simulate_never_returns_a_credential(client):
    res = client.post(
        f"{BASE}/playbooks/hr_benefits_open_enrollment_phish/simulate",
        json={"utterances": ["the code is 918273"]},
    )
    assert res.status_code == 200
    assert "918273" not in res.text


def test_simulate_on_an_unknown_playbook_is_a_424(client):
    res = client.post(f"{BASE}/playbooks/nope/simulate", json={"utterances": ["hi"]})
    assert res.status_code == 424
    assert res.json()["detail"]["error"] == "SimulationUnavailable"


# ── the runtime ──────────────────────────────────────────────────────


def test_runtime_start_reports_blockers_rather_than_a_500(client):
    """No credentials are configured in tests, so the runtime is blocked by design."""
    res = client.post(
        f"{BASE}/runtime/start",
        json={"voice_id": "v1", "playbook_id": "it-test"},
    )
    assert res.status_code == 424, res.text
    detail = res.json()["detail"]
    assert detail["error"] == "RuntimeUnavailable"
    assert detail["blockers"], "a blocked runtime must name what is missing"


def test_runtime_state_is_readable_before_anything_is_started(client):
    res = client.get(f"{BASE}/status")
    assert res.json()["runtime"]["state"] == "stopped"


# ── the gate ─────────────────────────────────────────────────────────


def test_dial_without_a_sign_off_is_a_409(client):
    res = client.post(
        f"{BASE}/calls",
        json={
            "target": "+15551234567",
            "campaign": "drill",
            "persona": "professional",
            "roe_id": "roe-that-does-not-exist",
            "approved_roster": ["+15551234567"],
        },
    )
    assert res.status_code == 409, res.text
    detail = res.json()["detail"]
    assert detail["error"] == "RoEError"


def test_dial_with_an_unrostered_target_is_a_422_naming_the_number(client, confirmed_roe):
    res = client.post(
        f"{BASE}/calls",
        json={
            "target": "+15559999999",
            "campaign": "drill",
            "persona": "professional",
            "roe_id": confirmed_roe,
            "approved_roster": ["+15551234567"],
        },
    )
    assert res.status_code == 422, res.text
    detail = res.json()["detail"]
    assert detail["error"] == "RosterError"
    assert "+15559999999" in detail["rejected_targets"]
    # The gate ran first: nothing reached the provider, so nothing was recorded.
    assert client.get(f"{BASE}/calls").json()["calls"] == []


def test_dial_with_a_malformed_number_is_refused_by_the_gate_before_validation(
    client, confirmed_roe
):
    """A number the roster does not contain is refused even if it is also malformed.

    Ordering is the point: the gate answers the authorisation question before any
    format question, so the refusal an operator sees is the one that matters.
    """
    res = client.post(
        f"{BASE}/calls",
        json={
            "target": "not-a-number",
            "campaign": "drill",
            "persona": "professional",
            "roe_id": confirmed_roe,
            "approved_roster": ["+15551234567"],
        },
    )
    assert res.status_code == 422
    assert res.json()["detail"]["error"] == "RosterError"


def test_authorised_dial_without_a_runtime_is_a_424_setup_fact(client, confirmed_roe):
    """Past the gate, blocked by setup — a different fact with a different code."""
    res = client.post(
        f"{BASE}/calls",
        json={
            "target": "+15551234567",
            "campaign": "drill",
            "persona": "professional",
            "roe_id": confirmed_roe,
            "approved_roster": ["+15551234567"],
        },
    )
    assert res.status_code == 424, res.text
    assert res.json()["detail"]["error"] == "DialBlocked"


# ── voices ───────────────────────────────────────────────────────────


def test_premade_voice_registration_serves_a_voice(client):
    res = client.post(
        f"{BASE}/voices",
        json={"voice_id": "21m00Tcm4TlvDq8ikWAM", "name": "support desk", "origin": "premade"},
    )
    assert res.status_code == 201, res.text
    voice = res.json()["voice"]
    assert voice["origin"] == "premade"
    assert voice["voice_id"] == "21m00Tcm4TlvDq8ikWAM"
    assert any(
        v["voice_id"] == "21m00Tcm4TlvDq8ikWAM"
        for v in client.get(f"{BASE}/voices").json()["voices"]
    )


def test_clone_without_a_provider_is_a_422_naming_the_variable(client):
    res = client.post(
        f"{BASE}/voices/clone",
        json={
            "name": "helpdesk",
            "sample_base64": base64.b64encode(b"RIFF").decode(),
            "sample_filename": "s.wav",
        },
    )
    assert res.status_code == 422, res.text
    assert "GHOSTLINE_ELEVENLABS_API_KEY" in res.json()["detail"]["reason"]


def test_clone_rejects_an_unreadable_format(client, monkeypatch):
    # The credential check runs first — it is the more fundamental blocker — so the
    # sample's *format* is only reached once a provider key is present.
    monkeypatch.setenv("GHOSTLINE_ELEVENLABS_API_KEY", "key-for-format-validation")
    res = client.post(
        f"{BASE}/voices/clone",
        json={
            "name": "helpdesk",
            "sample_base64": base64.b64encode(b"ID3").decode(),
            "sample_filename": "sample.mp3",
        },
    )
    assert res.status_code == 422, res.text
    assert ".wav" in res.json()["detail"]["reason"]


def test_clone_rejects_a_traversing_sample_name(client, monkeypatch):
    monkeypatch.setenv("GHOSTLINE_ELEVENLABS_API_KEY", "key-for-path-validation")
    res = client.post(
        f"{BASE}/voices/clone", json={"name": "x", "sample_ref": "../../../etc/passwd"}
    )
    assert res.status_code == 422, res.text
    assert "samples root" in res.json()["detail"]["reason"]


def test_clone_rejects_an_oversized_upload(client, monkeypatch, tmp_path):
    monkeypatch.setenv("GHOSTLINE_ELEVENLABS_API_KEY", "key-for-size-validation")
    monkeypatch.setenv("GHOSTLINE_SAMPLES_ROOT", str(tmp_path))
    # 25 MB cap. The payload is generated rather than embedded so the test file stays small.
    oversized = base64.b64encode(b"\0" * (26 * 1024 * 1024)).decode()
    res = client.post(
        f"{BASE}/voices/clone",
        json={"name": "x", "sample_base64": oversized, "sample_filename": "big.wav"},
    )
    assert res.status_code == 422
    assert "cap" in res.json()["detail"]["reason"]


def test_forget_unknown_voice_is_a_404(client):
    assert client.delete(f"{BASE}/voices/nope").status_code == 404


# ── the ledger ───────────────────────────────────────────────────────


def test_call_not_in_the_ledger_is_a_404(client):
    assert client.get(f"{BASE}/calls/gl-nope").status_code == 404


def test_analytics_reports_a_null_rate_before_anything_completes(client):
    res = client.get(f"{BASE}/analytics")
    assert res.status_code == 200
    body = res.json()["analytics"]
    assert body["conversion_rate"] is None, "an unmeasured rate must not be 0"
    assert body["credentials_captured"] == 0
    assert body["capture_passwords"] is False


def test_analytics_export_is_served_not_written(client):
    res = client.get(f"{BASE}/analytics/export?format=csv")
    assert res.status_code == 200
    export = res.json()["export"]
    assert export["format"] == "csv"
    assert export["filename"].endswith(".csv")
    assert "credentials_captured" in export["payload"]


def test_analytics_export_rejects_an_unknown_format(client):
    assert client.get(f"{BASE}/analytics/export?format=xlsx").status_code == 422


def test_turns_on_an_unknown_call_are_a_404(client):
    res = client.post(f"{BASE}/calls/gl-nope/turns", json={"role": "target", "content": "hi"})
    assert res.status_code == 404


def test_every_response_carries_the_envelope(client):
    """One assertion over the read surface, because the envelope is a contract."""
    for path in (
        "/status",
        "/playbooks",
        "/playbooks/it-test",
        "/voices",
        "/calls",
        "/analytics",
        "/analytics/export?format=json",
    ):
        body = client.get(f"{BASE}{path}").json()
        assert body["served"] == ["/specops/ghostline"], path
        assert body["scope"] == "tenant-wide", path
        assert isinstance(body["missing"], list), path
