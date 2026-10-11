"""Spec-ops donor integration + shared gates (Feature 027).

`roe/gate.py` holds the rules-of-engagement gate that every live spec-ops step
(kill-chain emulation, phishing/SAT) passes through before it reaches a donor.
"""

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
