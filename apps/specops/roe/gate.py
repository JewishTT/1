"""Rules-of-Engagement gate for the CI/SpecOps department (Feature 027, T004).

The safety property that makes phishing/SAT and kill-chain emulation shippable.
Pattern adopted from donor PIDSF ("safety in code, not UI"): a live step is
*blocked* here, not warned about, and the block cannot be bypassed from the
frontend because the router calls this before it ever touches the donor.

Three invariants, all enforced in code (never in the UI):

  1. No send without a confirmed, unexpired sign-off  -> ``RoEError``.
  2. Only a supervisor-approved roster may be targeted -> ``RosterError``.
  3. Entered credentials are NEVER captured or stored  -> ``capture_passwords``
     is pinned to ``False`` and there is no code path that writes them.

Adapted (not copied) from PIDSF's ``simulation.launch_campaign`` /
``validate_target_roster``; PIDSF is NO-LICENSE-FILE, so this is a clean-room
reimplementation of the *method*, per the platform's donor policy (rev.2).

Deferred by owner decision (FR-003/SC-007): process isolation, egress policy
and license reconciliation. This gate + lab-only targeting are the wave-1 safety
boundary; broader hardening is a follow-up.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class GateError(Exception):
    """Base for every refusal the gate raises. Carries a stable ``code``."""

    code = "gate-error"

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class RoEError(GateError):
    """A live step was attempted without a confirmed, unexpired sign-off."""

    code = "RoEError"


class RosterError(GateError):
    """A target outside the supervisor-approved roster was supplied."""

    code = "RosterError"

    def __init__(self, reason: str, rejected: list[str] | None = None) -> None:
        super().__init__(reason)
        self.rejected = rejected or []


class RoeStatus(str, Enum):
    """Closed vocabulary for a sign-off's state (maps to WorkStatus at the edge)."""

    UNCONFIRMED = "unconfirmed"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp; ``None``/unparseable means 'no expiry known'."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass(frozen=True)
class RulesOfEngagement:
    """A recorded sign-off authorizing a specific target scope, for a window."""

    roe_id: str
    target_ref: str
    scope: str
    approved_by: str
    signed_at: str
    expires_at: str | None = None

    def status(self, at: datetime | None = None) -> RoeStatus:
        expiry = _parse(self.expires_at)
        if expiry is not None and (at or _now()) >= expiry:
            return RoeStatus.EXPIRED
        # A sign-off with no approver recorded is not a sign-off.
        if not self.approved_by:
            return RoeStatus.UNCONFIRMED
        return RoeStatus.CONFIRMED

    def is_confirmed(self, at: datetime | None = None) -> bool:
        return self.status(at) is RoeStatus.CONFIRMED


@dataclass
class RoeRegistry:
    """In-memory sign-off store. Tenant isolation is enforced by the caller's
    tenant context; this registry only decides confirmation + expiry."""

    _by_id: dict[str, RulesOfEngagement] = field(default_factory=dict)

    def record(self, roe: RulesOfEngagement) -> RulesOfEngagement:
        self._by_id[roe.roe_id] = roe
        return roe

    def get(self, roe_id: str) -> RulesOfEngagement | None:
        return self._by_id.get(roe_id)


# Module-level registry so the router and the gate agree on one source of truth
# within a process. A durable store is a later-phase concern.
REGISTRY = RoeRegistry()


# The one knob that must never move: credentials entered during a simulation are
# not captured, not logged, not stored. There is deliberately no setter.
CAPTURE_PASSWORDS: bool = False


def capture_passwords_enabled() -> bool:
    """Always ``False``. Exists so callers assert the invariant rather than
    re-declaring the literal and drifting."""
    return CAPTURE_PASSWORDS

def require_confirmed_roe(roe: RulesOfEngagement | None, *, at: datetime | None = None) -> None:
    """Raise ``RoEError`` unless ``roe`` is a confirmed, unexpired sign-off."""
    if roe is None:
        raise RoEError("no rules-of-engagement recorded for this target")
    status = roe.status(at)
    if status is RoeStatus.EXPIRED:
        raise RoEError(f"rules-of-engagement {roe.roe_id} expired at {roe.expires_at}")
    if status is RoeStatus.UNCONFIRMED:
        raise RoEError(f"rules-of-engagement {roe.roe_id} is not confirmed")


def validate_target_roster(targets: list[str], approved_roster: list[str]) -> None:
    """Raise ``RosterError`` listing every target not on the approved roster.

    The comparison is exact and case-insensitive on the address; there is no
    fuzzy matching, because a near-miss target is an unauthorized target.
    """
    approved = {a.strip().lower() for a in approved_roster}
    rejected = [t for t in targets if t.strip().lower() not in approved]
    if rejected:
        raise RosterError(
            f"{len(rejected)} target(s) are not on the supervisor-approved roster",
            rejected=rejected,
        )


def launch_campaign(
    *,
    roe: RulesOfEngagement | None,
    targets: list[str],
    approved_roster: list[str],
) -> dict:
    """Gate a phishing/SAT send. Blocks (raises) unless RoE is confirmed and every
    target is approved. Returns a launch descriptor on success.

    Order matters: RoE first (is this authorized at all?), then roster (is this
    specific target authorized?). A send never reaches the donor unless both pass,
    and the caller records ``capture_passwords=False`` on the campaign.
    """
    require_confirmed_roe(roe)
    validate_target_roster(targets, approved_roster)
    return {
        "authorized": True,
        "roe_id": roe.roe_id if roe else None,
        "target_count": len(targets),
        "capture_passwords": capture_passwords_enabled(),
    }

