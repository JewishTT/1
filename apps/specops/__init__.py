"""Compatibility bridge for the archived SpecOps implementation.

The former package lives under spec-ops legacy/apps/specops. New domain
work belongs in specops_ci and must consume the Intelligence read contract;
this bridge exists only for still-mounted legacy API adapters during migration.
"""

from pathlib import Path

_legacy_package = Path(__file__).resolve().parents[2] / "spec-ops legacy" / "apps" / "specops"
if not _legacy_package.is_dir():
    raise ImportError(f"Archived SpecOps package is missing: {_legacy_package}")
if str(_legacy_package) not in __path__:
    __path__.append(str(_legacy_package))

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
