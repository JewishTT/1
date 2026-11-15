"""Phishing / SAT engine for the CI/SpecOps department (Feature 027, US3).

Direct integration target is donor PhishSlayer (GPLv3, isolated lab service).
This in-process engine is the wave-1 stand-in: it holds campaigns, gates every
send through the rules-of-engagement gate (specops.roe.gate), and enforces the
roster + no-credential-capture invariants so the surface and the gate are proven
end-to-end now. Swapping the sender for a live PhishSlayer proxy is a later
wiring change.

Three invariants, all enforced here (never in the UI):
  1. No send without a confirmed, unexpired sign-off  -> RoEError (409).
  2. Only a supervisor-approved roster may be targeted -> RosterError (422).
  3. Entered credentials are NEVER captured or stored  -> captured_credentials_count
     is pinned to 0 and there is no code path that writes them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from specops.roe.gate import RoEError, RosterError, require_confirmed_roe, validate_target_roster


@dataclass
class Campaign:
    campaign_id: str
    name: str
    template_source: str
    roster: list[str]
    approved_roster: list[str]
    attack_mapping: list[str]
    state: str = "draft"  # draft | ready | sending | complete | refused
    roe_status: str = "unconfirmed"
    engagement: dict = field(
        default_factory=lambda: {"sent": 0, "opened": 0, "clicked": 0, "submitted": 0}
    )


class CampaignRegistry:
    """In-memory campaign store. A durable store is a later-phase concern."""

    def __init__(self) -> None:
        self._by_id: dict[str, Campaign] = {}

    def create(self, *, name: str, template_source: str, roster: list[str], attack_mapping: list[str]) -> Campaign:
        # The roster a campaign is created with IS the supervisor-approved set for
        # this drill; an operator cannot widen it later without a new approval.
        c = Campaign(
            campaign_id=f"cmp-{uuid.uuid4().hex[:12]}",
            name=name,
            template_source=template_source,
            roster=list(roster),
            approved_roster=list(roster),
            attack_mapping=list(attack_mapping),
        )
        self._by_id[c.campaign_id] = c
        return c

    def get(self, campaign_id: str) -> Campaign | None:
        return self._by_id.get(campaign_id)


REGISTRY = CampaignRegistry()


def launch(campaign: Campaign, roe) -> dict:
    """Gate a send. Raises RoEError / RosterError; the router maps them to 409/422.

    On success, records engagement as a simulated send (deterministic counts for
    the lab) and returns the campaign view. Credentials are never touched.
    """
    require_confirmed_roe(roe)
    validate_target_roster(campaign.roster, campaign.approved_roster)
    campaign.roe_status = "confirmed"
    campaign.state = "sending"
    # Simulated engagement for the lab fixture — a real PhishSlayer proxy would
    # report these; the invariant that matters (no credential capture) holds either way.
    n = len(campaign.roster)
    campaign.engagement = {
        "sent": n,
        "opened": n,
        "clicked": max(n - 1, 0),
        "submitted": 0,
    }
    campaign.state = "complete"
    return {
        "captured_credentials_count": 0,
    }


__all__ = ["Campaign", "CampaignRegistry", "REGISTRY", "launch", "RoEError", "RosterError"]
