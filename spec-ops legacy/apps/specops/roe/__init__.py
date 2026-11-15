"""Spec-ops rules-of-engagement subpackage (Feature 027)."""

from specops.roe.gate import (
    CAPTURE_PASSWORDS,
    REGISTRY,
    GateError,
    RoEError,
    RoeRegistry,
    RoeStatus,
    RosterError,
    RulesOfEngagement,
    capture_passwords_enabled,
    launch_campaign,
    require_confirmed_roe,
    validate_target_roster,
)

__all__ = [
    "CAPTURE_PASSWORDS",
    "REGISTRY",
    "GateError",
    "RoEError",
    "RoeRegistry",
    "RoeStatus",
    "RosterError",
    "RulesOfEngagement",
    "capture_passwords_enabled",
    "launch_campaign",
    "require_confirmed_roe",
    "validate_target_roster",
]
