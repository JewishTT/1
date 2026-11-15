import { useState } from "react";

import { api, type LabCampaignWire, type LabOverviewWire } from "../../lib/api";
import { Input } from "../../ui/Input";
import { campaignTone, shortId } from "../model";
import { useLabAction } from "../useLabAction";
import { LabActionButton, LabChip, LabNote, LabPanelShell } from "./labParts";

export function CampaignsPanel({
  data,
  refresh,
}: {
  data: LabOverviewWire;
  refresh: () => Promise<void>;
}) {
  const { busy, note, setNote, run } = useLabAction(refresh);
  const [name, setName] = useState("Q4 lab drill");
  const [roster, setRoster] = useState("alice@lab.test, bob@lab.test");
  const [roeId, setRoeId] = useState("");

  const recordRoe = () =>
    run(async () => {
      const roe = await api.recordRoe({
        target_ref: "lab-target-1",
        scope: "drill",
        approved_by: "supervisor@lab",
      });
      setRoeId(roe.roe_id);
    }, "RoE sign-off recorded. Launch is now authorized against the lab roster.");

  const create = () =>
    run(
      () =>
        api.labCreateCampaign({
          name,
          roster: roster.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean),
          attack_mapping: ["T1566"],
        }),
      "Draft campaign created. Launch requires the recorded RoE id.",
    );

  const launch = (campaign: LabCampaignWire) =>
    run(
      () => api.labLaunchCampaign(campaign.campaign_id, { roe_id: roeId }),
      "Campaign launched. The funnel is re-derived from engagement events.",
    );

  return (
    <LabPanelShell
      title="Campaigns"
      status={<LabChip label={`${data.campaigns.length} campaign(s)`} />}
      testId="lab-campaigns-panel"
    >
      <div className="lab-grid">
        <div className="ui-ci-col">
          <span className="ui-pane-title">Create draft</span>
          <Input label="Campaign name" value={name} onChange={(e) => setName(e.target.value)} />
          <Input
            label="Roster"
            value={roster}
            onChange={(e) => setRoster(e.target.value)}
            hint="Any valid email; duplicates are refused. Launch remains RoE-gated."
            data-testid="lab-roster"
          />
          <LabActionButton onClick={() => void create()} disabled={busy} testId="lab-create-campaign">
            Create campaign
          </LabActionButton>
        </div>

        <div className="ui-ci-col">
          <span className="ui-pane-title">Authorization</span>
          <Input
            label="RoE id"
            value={roeId}
            onChange={(e) => setRoeId(e.target.value)}
            placeholder="record a sign-off or paste an id"
            data-testid="lab-roe-id"
          />
          <LabActionButton onClick={() => void recordRoe()} disabled={busy} testId="lab-record-roe">
            Record supervisor RoE
          </LabActionButton>
          <span className="ui-id">
            No confirmed sign-off means 409 at the gate; the launch is refused, not queued.
          </span>
        </div>
      </div>

      <div className="ui-ci-col" data-testid="lab-campaign-list">
        {data.campaigns.length === 0 ? (
          <p className="panel-note">No campaign yet. Create a draft against the lab roster.</p>
        ) : null}
        {data.campaigns.map((campaign) => (
          <div key={campaign.campaign_id} className="ui-ci-col" data-testid={`lab-campaign-${campaign.campaign_id}`}>
            <div className="ui-ci-list-head">
              <span className="ui-pane-title">{campaign.name}</span>
              <LabChip label={campaign.state} tone={campaignTone(campaign.state)} />
              <LabChip
                label={`RoE ${campaign.roe_status}`}
                tone={campaign.roe_status === "confirmed" ? "accent" : "gold"}
              />
              <LabChip label={`${campaign.captured_credentials_count} credentials captured`} />
            </div>
            <span className="ui-id">
              {shortId(campaign.campaign_id)} · template {campaign.template_id} · sender{" "}
              {campaign.sender_id ?? "none"} · {campaign.roster.length} recipient(s)
            </span>
            <div className="ui-ci-metrics">
              <Metric label="sent" value={campaign.funnel.sent} />
              <Metric label="opened" value={campaign.funnel.opened} />
              <Metric label="clicked" value={campaign.funnel.clicked} />
              <Metric label="reported" value={campaign.funnel.reported} />
              <Metric label="training completed" value={campaign.funnel.training.completed} />
            </div>
            <div className="lab-button-row">
              <LabActionButton
                disabled={busy || campaign.state !== "draft"}
                onClick={() => void launch(campaign)}
                testId={`lab-launch-${campaign.campaign_id}`}
              >
                Launch (RoE-gated)
              </LabActionButton>
              <LabActionButton
                variant="ghost"
                disabled={busy}
                onClick={() => {
                  setNote(`Assessment link is created from the Operations panel for ${campaign.name}.`);
                }}
                testId={`lab-link-hint-${campaign.campaign_id}`}
              >
                Link operation
              </LabActionButton>
            </div>
          </div>
        ))}
      </div>

      <LabNote note={note} testId="lab-campaigns-note" />
    </LabPanelShell>
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
