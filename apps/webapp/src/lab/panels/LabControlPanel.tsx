import { api, type LabOverviewWire } from "../../lib/api";
import { LabAbsence, LabActionButton, LabChip, LabNote, LabPanelShell } from "./labParts";
import { useLabAction } from "../useLabAction";

export function LabControlPanel({
  data,
  refresh,
}: {
  data: LabOverviewWire;
  refresh: () => Promise<void>;
}) {
  const { busy, note, run } = useLabAction(refresh);
  const readiness = data.readiness;
  const lab = data.lab;

  return (
    <LabPanelShell
      title="Lab control & readiness"
      status={
        <LabChip
          label={`${lab.status} · ${lab.egress_policy}`}
          tone={lab.status === "ready" ? "accent" : "danger"}
          testId="lab-status"
        />
      }
      testId="lab-control-panel"
    >
      <div className="ui-ci-col">
        <span className="ui-pane-title">Readiness matrix</span>
        <ul className="ui-ci-abilities" data-testid="lab-readiness-matrix">
          {readiness.matrix.map((row) => (
            <li key={row.capability} data-state={row.state === "ready" ? "executed" : "failed"}>
              <span className="ui-ci-list-main">
                <strong>{row.capability}</strong>
                <span className="ui-id">{row.detail}</span>
                {row.missing.length > 0 ? (
                  <span className="ui-id">{row.missing.join("; ")}</span>
                ) : null}
              </span>
              <LabChip
                label={row.state}
                tone={row.state === "ready" ? "accent" : "danger"}
                testId={`lab-readiness-${row.capability.replace(/\s+/g, "-")}`}
              />
            </li>
          ))}
        </ul>
      </div>

      <div className="ui-ci-metrics" data-testid="lab-counts">
        <Metric label="campaigns" value={readiness.counts.campaigns ?? 0} />
        <Metric label="sessions" value={readiness.counts.sessions ?? 0} />
        <Metric label="artifacts" value={readiness.counts.artifacts ?? 0} />
        <Metric label="reports" value={readiness.counts.reports ?? 0} />
      </div>

      <div className="ui-ci-col">
        <span className="ui-pane-title">Lifecycle</span>
        <span className="ui-id">
          targets: any RoE-approved host � kill switch{" "}
          {lab.kill_switch_at ? `fired ${lab.kill_switch_at}` : "not fired"}
        </span>
        <span className="ui-id" data-testid="lab-donor-service">
          Phishing Club:{" "}
          <a href={readiness.donor.console_url} target="_blank" rel="noreferrer">
            {readiness.donor.console_url}
          </a>
          {readiness.donor.api_key_configured ? " (API key configured)" : " (API key not configured)"}
        </span>
        <div className="lab-button-row">
          <LabActionButton
            variant="danger"
            disabled={busy}
            onClick={() => void run(() => api.labKillSwitch(), "Kill switch fired. Sessions stopped; evidence preserved.")}
            testId="lab-kill-switch"
          >
            Kill switch
          </LabActionButton>
          <LabActionButton
            disabled={busy}
            onClick={() => void run(() => api.labReset(), "Lab reset to ready. Evidence was not cleared.")}
            testId="lab-reset"
          >
            Reset lab
          </LabActionButton>
          <LabActionButton
            disabled={busy}
            onClick={() => void run(() => api.labTeardown(), "Lab torn down. Evidence counts preserved in the audit.")}
            testId="lab-teardown"
          >
            Teardown
          </LabActionButton>
        </div>
      </div>

      <LabAbsence missing={data.missing} testId="lab-overview-missing" />
      <LabNote note={note} testId="lab-control-note" />
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
