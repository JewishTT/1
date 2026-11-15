import type { LabOverviewWire } from "../../lib/api";
import { LabChip, LabPanelShell } from "./labParts";

export function EngagementLabPanel({ data }: { data: LabOverviewWire }) {
  const engagement = data.engagement;
  const funnel = engagement.channel_funnel;

  return (
    <LabPanelShell
      title="Engagement & training compliance"
      status={<LabChip label={engagement.anonymized ? "anonymized" : "identified"} tone={engagement.anonymized ? "accent" : "gold"} />}
      testId="lab-engagement-panel"
    >
      <div className="ui-ci-col">
        <span className="ui-pane-title">Phishing funnel (all channels)</span>
        <div className="ui-ci-metrics" data-testid="lab-engagement-funnel">
          <Metric label="sent" value={funnel.sent} />
          <Metric label="opened" value={funnel.opened} />
          <Metric label="clicked" value={funnel.clicked} />
          <Metric label="reported" value={funnel.reported} />
          <Metric label="subjects" value={engagement.subjects} />
        </div>
      </div>

      {/* Training is a separate track, never added into the phishing ladder. */}
      <div className="ui-ci-col" data-testid="lab-training-block">
        <span className="ui-pane-title">Training compliance (separate track)</span>
        <div className="ui-ci-metrics">
          <Metric label="assigned" value={engagement.training.assigned} />
          <Metric label="completed" value={engagement.training.completed} />
        </div>
      </div>

      <div className="ui-ci-col">
        <span className="ui-pane-title">Campaign ladders</span>
        {data.campaigns.length === 0 ? <p className="panel-note">No campaign events yet.</p> : null}
        <ul className="ui-ci-list">
          {data.campaigns.map((campaign) => (
            <li key={campaign.campaign_id} className="ui-ci-list-row">
              <span className="ui-ci-list-main">
                <strong>{campaign.name}</strong>
                <span className="ui-id">
                  sent {campaign.funnel.sent} · opened {campaign.funnel.opened} · clicked {campaign.funnel.clicked} ·
                  reported {campaign.funnel.reported} · training {campaign.funnel.training.completed}
                </span>
              </span>
              <LabChip label={campaign.funnel.source} tone="analytical" />
            </li>
          ))}
        </ul>
      </div>
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
