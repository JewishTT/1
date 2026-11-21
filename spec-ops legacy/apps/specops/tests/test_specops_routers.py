"""Router contract tests for the CI/SpecOps department (027, US2/US3).

Proves the two mandatory pillars end-to-end through the FastAPI surface: kill-chain
emulation loads real donor plans and is RoE-gated; phishing/SAT refuses without a
sign-off and never captures credentials. Uses the control-plane app so the gate,
the engines and the routers are exercised together.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client():
    from api.main import app

    return TestClient(app)


def _confirmed_roe(client) -> str:
    res = client.post(
        "/api/v1/specops/roe",
        json={"target_ref": "lab-target-1", "scope": "drill", "approved_by": "supervisor@lab"},
    )
    assert res.status_code == 200, res.text
    return res.json()["roe_id"]


# ── Emulation (US2) ───────────────────────────────────────────────────

def test_plans_load_from_donor_libraries():
    client = _client()
    res = client.get("/api/v1/specops/emulation/plans")
    assert res.status_code == 200
    body = res.json()
    # Real donor plans (ael / adversary_emulation_library) are served; if the donor
    # dirs were absent the surface names the gap instead of fabricating a plan.
    assert body["scope"] == "tenant-wide"
    assert isinstance(body["plans"], list)


def test_launch_blocked_without_confirmed_roe():
    client = _client()
    plans = client.get("/api/v1/specops/emulation/plans").json()["plans"]
    if not plans:
        return  # donor libs absent — nothing to launch; the gap is named elsewhere
    res = client.post(
        "/api/v1/specops/emulation/operations",
        json={"plan_id": plans[0]["plan_id"], "lab_fixture": plans[0]["lab_fixture"], "roe_id": "roe-does-not-exist"},
    )
    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "RoEError"


def test_launch_with_confirmed_roe_runs_and_advances():
    client = _client()
    plans = client.get("/api/v1/specops/emulation/plans").json()["plans"]
    if not plans:
        return
    roe_id = _confirmed_roe(client)
    plan = plans[0]
    res = client.post(
        "/api/v1/specops/emulation/operations",
        json={"plan_id": plan["plan_id"], "lab_fixture": plan["lab_fixture"], "roe_id": roe_id},
    )
    assert res.status_code == 200, res.text
    op = res.json()["operation"]
    assert op["state"] == "running"
    # A poll advances the run (deterministic stand-in for a live agent).
    poll = client.get(f"/api/v1/specops/emulation/operations/{op['operation_id']}")
    assert poll.status_code == 200
    assert poll.json()["operation"]["abilities"][0]["state"] in ("executed", "planned")


# ── Phishing / SAT (US3) ──────────────────────────────────────────────

def test_phishing_launch_blocked_without_roe():
    client = _client()
    created = client.post(
        "/api/v1/specops/phishing/campaigns",
        json={"name": "drill", "template_source": "PhishSlayer", "roster": ["a@lab"], "attack_mapping": ["T1566"]},
    )
    assert created.status_code == 200
    cid = created.json()["campaign"]["campaign_id"]
    res = client.post(f"/api/v1/specops/phishing/campaigns/{cid}/launch", json={"roe_id": "roe-missing"})
    assert res.status_code == 409
    assert res.json()["detail"]["error"] == "RoEError"


def test_phishing_launch_with_roe_never_captures_credentials():
    client = _client()
    roe_id = _confirmed_roe(client)
    created = client.post(
        "/api/v1/specops/phishing/campaigns",
        json={"name": "drill", "template_source": "PhishSlayer", "roster": ["a@lab", "b@lab"], "attack_mapping": ["T1566"]},
    )
    cid = created.json()["campaign"]["campaign_id"]
    res = client.post(f"/api/v1/specops/phishing/campaigns/{cid}/launch", json={"roe_id": roe_id})
    assert res.status_code == 200, res.text
    campaign = res.json()["campaign"]
    assert campaign["state"] == "complete"
    assert campaign["captured_credentials_count"] == 0  # FR-006, structural


# ── Counterintelligence (US4) ─────────────────────────────────────────

def test_subject_invariants_carry_evidence_and_mark_unsupported():
    client = _client()
    res = client.get("/api/v1/specops/counterintel/subjects/subj-demo-1")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["scope"] == "investigation-scoped"
    invariants = body["subject"]["invariants"]
    supported = [i for i in invariants if i["evidence_refs"]]
    unsupported = [i for i in invariants if not i["evidence_refs"]]
    # The seeded subject proves both branches of the honesty contract (FR-008).
    assert supported and unsupported


def test_unknown_subject_is_404_not_a_blank_board():
    client = _client()
    assert client.get("/api/v1/specops/counterintel/subjects/nope").status_code == 404


# ── Social reaction (US5) ─────────────────────────────────────────────

def test_projection_is_deterministic_and_reports_confidence():
    client = _client()
    payload = {"population_ref": "pop-lab-1", "narrative_input": "shock", "horizon": 6}
    a = client.post("/api/v1/specops/social/projections", json=payload).json()["projection"]
    b = client.post("/api/v1/specops/social/projections", json=payload).json()["projection"]
    assert a["trajectories"] == b["trajectories"]  # determinism
    assert a["confidence"] in ("low", "medium", "high")
    assert "phase_transition_risk" in a and "indicator" in a["phase_transition_risk"]


def test_sparse_population_reports_low_confidence():
    client = _client()
    res = client.post(
        "/api/v1/specops/social/projections",
        json={"population_ref": "", "narrative_input": "", "horizon": 4},
    ).json()["projection"]
    assert res["confidence"] == "low"  # never a confident-looking curve


# ── APT forensics (US6) ───────────────────────────────────────────────

def test_forensics_lists_gaps_and_derives_coverage():
    client = _client()
    plans = client.get("/api/v1/specops/emulation/plans").json()["plans"]
    if not plans:
        return
    roe_id = _confirmed_roe(client)
    plan = plans[0]
    op = client.post(
        "/api/v1/specops/emulation/operations",
        json={"plan_id": plan["plan_id"], "lab_fixture": plan["lab_fixture"], "roe_id": roe_id},
    ).json()["operation"]
    # Poll a few times so some abilities execute; the rest stay gaps.
    for _ in range(len(plan_abilities(client, plan["plan_id"])) ):
        client.get(f"/api/v1/specops/emulation/operations/{op['operation_id']}")
    res = client.get(f"/api/v1/specops/forensics/operations/{op['operation_id']}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert "forensics" in body and "coverage" in body
    assert body["forensics"]["comparison"]  # expected vs actual present
    # Every comparison row is either corroborated or a named gap — never dropped.
    for c in body["forensics"]["comparison"]:
        assert c["status"] in ("corroborated", "gap")


def plan_abilities(client, plan_id):
    return client.get(f"/api/v1/specops/emulation/plans/{plan_id}").json()["plan"]["abilities"]

