import { useState } from "react";

import { api, type LabExportWire, type LabOverviewWire } from "../../lib/api";
import { figureTone, figureValue, reportFigureRows } from "../model";
import { useLabAction } from "../useLabAction";
import { LabActionButton, LabChip, LabNote, LabPanelShell } from "./labParts";

export function ReportsPanel({
  data,
  refresh,
}: {
  data: LabOverviewWire;
  refresh: () => Promise<void>;
}) {
  const { busy, note, run } = useLabAction(refresh);
  const [campaignId, setCampaignId] = useState(data.campaigns[0]?.campaign_id ?? "");
  const [exported, setExported] = useState<LabExportWire | null>(null);

  const report = data.reports.find((candidate) => candidate.campaign_id === campaignId);

  const generate = () =>
    run(
      () => api.labGenerateReport(campaignId),
      "Report generated. Every figure carries measured, derived or unavailable status.",
    );

  const exportReport = () =>
    run(async () => {
      const res = await api.labExportReport(campaignId);
      setExported(res.export);
    }, "Markdown exported. The digest is bound to the report body.");

  return (
    <LabPanelShell
      title="Assessment reports"
      status={<LabChip label={`${data.reports.length} report(s)`} />}
      testId="lab-reports-panel"
    >
      <div className="ui-ci-col">
        <label className="ui-field-label" htmlFor="lab-report-campaign">
          Campaign
        </label>
        <select
          id="lab-report-campaign"
          className="ui-input"
          value={campaignId}
          onChange={(e) => {
            setCampaignId(e.target.value);
            setExported(null);
          }}
          data-testid="lab-report-campaign"
        >
          <option value="">select campaign</option>
          {data.campaigns.map((campaign) => (
            <option key={campaign.campaign_id} value={campaign.campaign_id}>
              {campaign.name} · {campaign.campaign_id}
            </option>
          ))}
        </select>
        <div className="lab-button-row">
          <LabActionButton
            onClick={() => void generate()}
            disabled={busy || !campaignId}
            testId="lab-generate-report"
          >
            Generate report
          </LabActionButton>
          <LabActionButton
            onClick={() => void exportReport()}
            disabled={busy || !campaignId || !report}
            testId="lab-export-report"
            variant="ghost"
          >
            Export markdown
          </LabActionButton>
        </div>
      </div>

      {report ? (
        <div className="ui-ci-col" data-testid="lab-report">
          <div className="ui-ci-list-head">
            <span className="ui-pane-title">{report.report_id}</span>
            <span className="ui-id">generated {report.generated_at}</span>
          </div>
          <table className="ui-table lab-report-figures" data-testid="lab-report-figures">
            <thead>
              <tr>
                <th>Figure</th>
                <th>Value</th>
                <th>Status</th>
                <th>Source</th>
                <th>Missing instrumentation</th>
              </tr>
            </thead>
            <tbody>
              {reportFigureRows(report.figures).map(({ name, figure }) => (
                <tr key={name}>
                  <td>{name}</td>
                  <td>{figureValue(figure)}</td>
                  <td>
                    <LabChip label={figure.status} tone={figureTone(figure.status)} />
                  </td>
                  <td className="ui-id">{figure.source}</td>
                  <td className="ui-id">{figure.missing ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="ui-ci-col">
            <span className="ui-pane-title">Limitations</span>
            <ul className="ui-ci-list">
              {report.limitations.map((limitation) => (
                <li key={limitation} className="ui-id">
                  {limitation}
                </li>
              ))}
            </ul>
          </div>

          <div className="ui-ci-col">
            <span className="ui-pane-title">Provenance & redaction</span>
            <span className="ui-id">{report.provenance.join(" · ")}</span>
            <span className="ui-id">{report.redaction}</span>
          </div>
        </div>
      ) : (
        <p className="panel-note">No report for this campaign yet. Generate one from its evidence.</p>
      )}

      {exported ? (
        <div className="ui-ci-col" data-testid="lab-report-export">
          <span className="ui-pane-title">Export · digest {exported.digest.slice(0, 16)}…</span>
          <pre className="ui-id lab-export-body">{exported.body}</pre>
        </div>
      ) : null}

      <LabNote note={note} testId="lab-reports-note" />
    </LabPanelShell>
  );
}
