import { useCallback, useState } from "react";

import { Button } from "../../ui/Button";
import { Input } from "../../ui/Input";
import { api } from "../../lib/api";
import { campaignRow } from "../model";
import type { CampaignRow } from "../types";
import { CiEmpty, CiPanelShell, StatusChip } from "./panelParts";

/**
 * Phishing / SAT panel (US3, MANDATORY).
 *
 * Prepare a campaign against a supervisor-approved roster; the RoE gate blocks any
 * send until sign-off, and credentials entered during the simulation are never
 * captured. The gate is server-side, so a 409/422 here is the platform refusing —
 * shown verbatim, never swallowed. `captured_credentials_count` is rendered to
 * prove the invariant (always 0, FR-006).
 */
export function PhishingPanel() {
  const [rosterText, setRosterText] = useState("approved@lab");
  const [campaign, setCampaign] = useState<CampaignRow | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const roster = rosterText
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean);

  const create = useCallback(async () => {
    setBusy(true);
    setNote(null);
    try {
      const res = await api.createCampaign({
        name: "SAT drill",
        template_source: "PhishSlayer",
        roster,
        attack_mapping: ["T1566"],
      });
      setCampaign(campaignRow(res.campaign));
      setNote("Draft campaign created. Record a RoE sign-off, then launch.");
    } catch (err) {
      setNote(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [roster]);

  const launch = useCallback(async () => {
    if (!campaign) return;
    setBusy(true);
    setNote(null);
    try {
      const res = await api.launchCampaign(campaign.campaign_id, {
        roe_id: "roe-confirmed-by-supervisor",
      });
      setCampaign(campaignRow(res.campaign));
      setNote("Campaign launched.");
    } catch (err) {
      // 409 RoEError / 422 RosterError arrive here as a message; shown verbatim.
      setNote(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [campaign]);

  return (
    <CiPanelShell
      title="Phishing / SAT simulation"
      scope="tenant-wide"
      status={
        <StatusChip
          label={campaign ? campaign.state : "draft"}
          tone={campaign?.state === "complete" ? "accent" : "neutral"}
          testId="ci-phishing-status"
        />
      }
      testId="ci-phishing-panel"
    >
      <div className="ui-ci-col">
        <span className="ui-pane-title">Approved roster</span>
        <Input
          value={rosterText}
          onChange={(e) => setRosterText(e.target.value)}
          placeholder="approved@lab, approved2@lab"
          aria-label="Approved target roster"
          data-testid="ci-roster-input"
        />
        <span className="ui-id">{roster.length} target(s) · only these may be sent</span>
        <Button
          size="sm"
          icon="plus"
          disabled={busy || roster.length === 0}
          onClick={() => void create()}
          data-testid="ci-create-campaign"
        >
          Create campaign
        </Button>
      </div>

      {campaign ? (
        <div className="ui-ci-col" data-testid="ci-campaign">
          <div className="ui-ci-list-head">
            <span className="ui-pane-title">Campaign {campaign.campaign_id}</span>
            <StatusChip
              label={`RoE ${campaign.roe_status}`}
              tone={campaign.roe_status === "confirmed" ? "accent" : "gold"}
            />
            <StatusChip
              label={`${campaign.captured_credentials_count} credentials captured`}
              tone="neutral"
              testId="ci-no-capture"
            />
          </div>
          <div className="ui-ci-metrics" data-testid="ci-engagement">
            <Metric label="sent" value={campaign.engagement.sent} />
            <Metric label="opened" value={campaign.engagement.opened} />
            <Metric label="clicked" value={campaign.engagement.clicked} />
            <Metric label="submitted" value={campaign.engagement.submitted} />
          </div>
          <Button
            size="sm"
            icon="alert"
            disabled={busy}
            onClick={() => void launch()}
            data-testid="ci-launch-campaign"
          >
            Launch (RoE-gated)
          </Button>
        </div>
      ) : (
        <CiEmpty>No campaign yet. Create one against the approved roster.</CiEmpty>
      )}

      {note ? (
        <p className="panel-note" data-testid="ci-phishing-note">
          {note}
        </p>
      ) : null}
    </CiPanelShell>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="ui-ci-metric">
      <span className="op-label">{label}</span>
      <span className="op-value">{value.toLocaleString()}</span>
    </div>
  );
}
