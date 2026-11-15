"""Guarding test for the CI/SpecOps rules-of-engagement gate (Feature 027, T004).

Proves the three safety invariants the department depends on (SC-003, FR-005,
FR-006): no send without a confirmed, unexpired sign-off; only an approved roster
is targeted; credentials are never captured. These are the properties that make
phishing/SAT and kill-chain emulation shippable, so they are asserted here rather
than left to the UI.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from specops.roe.gate import (
    CAPTURE_PASSWORDS,
    RoeStatus,
    RoEError,
    RosterError,
    RulesOfEngagement,
    capture_passwords_enabled,
    launch_campaign,
    require_confirmed_roe,
    validate_target_roster,
)


def _roe(**overrides) -> RulesOfEngagement:
    base = dict(
        roe_id="roe-1",
        target_ref="lab-target-1",
        scope="phishing-sim",
        approved_by="supervisor@lab",
        signed_at=datetime.now(timezone.utc).isoformat(),
        expires_at=None,
    )
    base.update(overrides)
    return RulesOfEngagement(**base)


def test_confirmed_roe_passes():
    require_confirmed_roe(_roe())  # must not raise


def test_missing_roe_is_refused():
    with pytest.raises(RoEError):
        require_confirmed_roe(None)


def test_unapproved_signoff_is_not_confirmed():
    roe = _roe(approved_by="")
    assert roe.status() is RoeStatus.UNCONFIRMED
    with pytest.raises(RoEError):
        require_confirmed_roe(roe)


def test_expired_roe_is_refused():
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with pytest.raises(RoEError):
        require_confirmed_roe(_roe(expires_at=past))


def test_future_expiry_is_still_confirmed():
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    require_confirmed_roe(_roe(expires_at=future))


def test_out_of_roster_targets_are_rejected_and_listed():
    with pytest.raises(RosterError) as excinfo:
        validate_target_roster(["ok@lab", "evil@real"], ["ok@lab"])
    assert excinfo.value.rejected == ["evil@real"]


def test_roster_match_is_case_insensitive_exact():
    # A near-miss is still unauthorized; only the approved address passes.
    validate_target_roster(["OK@LAB"], ["ok@lab"])


def test_launch_blocked_without_confirmed_roe():
    with pytest.raises(RoEError):
        launch_campaign(roe=None, targets=["ok@lab"], approved_roster=["ok@lab"])


def test_launch_blocked_on_out_of_roster_even_with_roe():
    with pytest.raises(RosterError):
        launch_campaign(roe=_roe(), targets=["evil@real"], approved_roster=["ok@lab"])


def test_launch_succeeds_when_authorized_and_never_captures_credentials():
    result = launch_campaign(roe=_roe(), targets=["ok@lab"], approved_roster=["ok@lab"])
    assert result["authorized"] is True
    assert result["capture_passwords"] is False


def test_capture_passwords_is_pinned_false():
    # The invariant is a module constant with no setter; assert it directly so a
    # future change that flips it fails here, not in production.
    assert CAPTURE_PASSWORDS is False
    assert capture_passwords_enabled() is False
