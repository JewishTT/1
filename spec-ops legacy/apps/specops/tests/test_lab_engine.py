"""Engine-level proofs for the Red-Team Lab (Feature 036).

These exercise the boundary and the engine without FastAPI: no launch without a
confirmed RoE, no secret in any returned view, cross-tenant reads are 404, and the
kill switch actually stops new activity. The engagement log is a private fabric so a
test never writes into ``logs/engagement``.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from specops.engagement.config import clear_engagement_config_cache
from specops.engagement.fabric import EngagementFabric
from specops.lab.audit import AuditLog
from specops.lab.boundary import LabNotFound, AuthorizationRefused
from specops.lab.engine import LabEngine
from specops.roe.gate import REGISTRY as ROE
from specops.roe.gate import RoEError, RulesOfEngagement


def _ctx(tenant: str = "ten-lab-a", user: str = "user-lab-a") -> SimpleNamespace:
    return SimpleNamespace(tenant_id=tenant, user_id=user)


@pytest.fixture()
def lab(tmp_path, monkeypatch) -> LabEngine:
    monkeypatch.setenv("GHOSTLINE_ENGAGEMENT_DIR", str(tmp_path / "engagement"))
    clear_engagement_config_cache()
    yield LabEngine(records=EngagementFabric(), audit=AuditLog())
    clear_engagement_config_cache()


@pytest.fixture()
def roe_id() -> str:
    roe = RulesOfEngagement(
        roe_id=f"roe-lab-{uuid.uuid4().hex[:8]}",
        target_ref="lab-target-1",
        scope="drill",
        approved_by="supervisor@lab",
        signed_at="2026-11-01T00:00:00+00:00",
    )
    ROE.record(roe)
    return roe.roe_id


def _campaign(lab: LabEngine, ctx, roster=("a@lab.test", "b@lab.test")) -> str:
    view = lab.create_campaign(
        ctx,
        name="drill",
        roster=list(roster),
        attack_mapping=["T1566"],
    )
    return view["campaign_id"]


def test_launch_requires_a_confirmed_roe(lab, roe_id):
    ctx = _ctx()
    campaign_id = _campaign(lab, ctx)
    with pytest.raises(RoEError):
        lab.launch_campaign(ctx, campaign_id=campaign_id, roe_id="roe-does-not-exist")
    assert lab.get_campaign(ctx, campaign_id)["state"] == "draft"


def test_launch_records_an_anonymised_funnel(lab, roe_id):
    ctx = _ctx()
    campaign_id = _campaign(lab, ctx)
    view = lab.launch_campaign(ctx, campaign_id=campaign_id, roe_id=roe_id)
    assert view["state"] == "complete"
    funnel = view["funnel"]
    assert (funnel["sent"], funnel["opened"], funnel["clicked"], funnel["submitted"]) == (2, 2, 1, 0)
    assert funnel["source"] == "derived"
    assert lab.overview(ctx)["engagement"]["subjects"] == 2


def test_capture_returns_a_redacted_view_never_the_secret(lab, roe_id):
    ctx = _ctx()
    session = lab.start_session(
        ctx, mode="reverse_proxy", target_host="specops-lab.local", roe_id=roe_id
    )
    artifact = lab.capture(
        ctx, session_id=session["session_id"], kind="token", secret="tok-top-secret", label="lab"
    )
    assert "tok-top-secret" not in repr(artifact)
    assert "tok-top-secret" not in artifact["redacted_preview"]
    assert lab.stop_session(ctx, session["session_id"])["state"] == "stopped"
    assert lab.audit.verify() is None


def test_cross_tenant_campaign_is_not_found(lab, roe_id):
    owner, other = _ctx(), _ctx(tenant="ten-lab-b", user="user-lab-b")
    campaign_id = _campaign(lab, owner)
    with pytest.raises(LabNotFound):
        lab.get_campaign(other, campaign_id)


def test_kill_switch_blocks_new_work_until_reset(lab, roe_id):
    ctx = _ctx()
    lab.kill_switch(ctx)
    with pytest.raises(AuthorizationRefused):
        lab.create_campaign(ctx, name="after kill", roster=["a@lab.test"])
    res = lab.reset(ctx)
    assert res["status"] == "ready"
    assert lab.create_campaign(ctx, name="after reset", roster=["a@lab.test"])["name"] == "after reset"


def test_full_mode_starts_external_target_after_roe(lab, roe_id):
    session = lab.start_session(
        _ctx(), mode="reverse_proxy", target_host="external.example", roe_id=roe_id
    )
    assert session["target_host"] == "external.example"
    assert session["state"] == "running"


def test_report_marks_engagement_figures_derived_and_unavailable_before_launch(lab, roe_id):
    ctx = _ctx()
    campaign_id = _campaign(lab, ctx)
    report = lab.generate_report(ctx, campaign_id)
    assert report["figures"]["sent"]["status"] == "unavailable"
    lab.launch_campaign(ctx, campaign_id=campaign_id, roe_id=roe_id)
    report = lab.generate_report(ctx, campaign_id)
    assert report["figures"]["sent"]["status"] == "derived"
    assert report["figures"]["clicked"]["source"] == "engagement:campaign_recipient_page_visited"
    assert any(p.startswith("audit:") for p in report["provenance"])
