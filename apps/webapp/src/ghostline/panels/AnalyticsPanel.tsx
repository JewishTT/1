import { useCallback, useEffect, useState } from "react";

import { Button } from "../../ui/Button";
import { Input } from "../../ui/Input";
import { api } from "../../lib/api";
import { Chip, classify, Empty, GlShell, Refusal } from "../panelParts";
import { outcomeLabel } from "../model";
import { STAGE_LADDER } from "../types";
import type { GlRefusal } from "../types";

/**
 * Analytics panel (Feature 031) — the donor's `analytics` verb.
 *
 * The CLI writes a CSV and prints a path. That is the right shape for a script and the
 * wrong shape for an assessor: the numbers are only readable by whoever opened the file,
 * and the file is generated separately from anything on screen, so it drifts. Here the
 * export is generated from the same aggregate this panel renders, which is the only way
 * "what I exported" can mean "what I saw".
 *
 * One figure is deliberately not rendered as a number. `conversion_rate` is `null`
 * until at least one call has completed, and it stays `null` on screen — an assessment
 * with no completed calls has no conversion rate, and rendering `0%` would assert the
 * targets resisted rather than that nothing has been measured yet.
 */
export function AnalyticsPanel() {
  const [analytics, setAnalytics] = useState<Awaited<
    ReturnType<typeof api.ghostlineAnalytics>
  >["analytics"] | null>(null);
  const [campaign, setCampaign] = useState("");
  const [busy, setBusy] = useState(false);
  const [refusal, setRefusal] = useState<GlRefusal | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await api.ghostlineAnalytics(campaign || null);
      setAnalytics(res.analytics);
      setRefusal(null);
    } catch (err) {
      setRefusal(classify(err));
      setAnalytics(null);
    }
  }, [campaign]);

  useEffect(() => {
    void load();
  }, [load]);

  const download = useCallback(
    async (format: "csv" | "json") => {
      setBusy(true);
      setRefusal(null);
      setNote(null);
      try {
        const res = await api.exportGhostlineAnalytics(format, campaign || null);
        const payload = res.export.payload;
        const text = typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);
        // Served rather than written server-side: the export is derived data, and a
        // derived artefact on disk that nobody asked for is a liability.
        const blob = new Blob([text], { type: format === "csv" ? "text/csv" : "application/json" });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = res.export.filename;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(url);
        setNote(`Exported ${res.export.filename}.`);
      } catch (err) {
        setRefusal(classify(err));
      } finally {
        setBusy(false);
      }
    },
    [campaign],
  );

  const stageMax = Math.max(1, ...Object.values(analytics?.stage_counts ?? {}));
  const outcomeMax = Math.max(1, ...Object.values(analytics?.outcomes ?? {}));

  return (
    <GlShell
      title="Exercise analytics"
      status={
        analytics ? (
          <Chip
            label={`${analytics.call_count} call(s)`}
            tone={analytics.call_count > 0 ? "accent" : "neutral"}
            testId="gl-analytics-count"
          />
        ) : null
      }
      testId="gl-analytics-panel"
    >
      <Refusal refusal={refusal} testId="gl-analytics-refusal" />

      <div className="ui-gl-actions">
        <Input
          label="Campaign filter"
          value={campaign}
          onChange={(e) => setCampaign(e.target.value)}
          placeholder="all campaigns"
          mono
          data-testid="gl-analytics-campaign"
        />
        <Button size="sm" icon="open-external" disabled={busy} onClick={() => void download("csv")} data-testid="gl-export-csv">
          Export CSV
        </Button>
        <Button size="sm" icon="open-external" disabled={busy} onClick={() => void download("json")} data-testid="gl-export-json">
          Export JSON
        </Button>
      </div>

      {analytics ? (
        <>
          <div className="ui-ci-metrics" data-testid="gl-analytics-metrics">
            <Metric label="calls" value={analytics.call_count} testId="gl-m-calls" />
            <Metric label="completed" value={analytics.completed_count} testId="gl-m-completed" />
            <Metric label="in progress" value={analytics.in_progress_count} testId="gl-m-inprogress" />
            <Metric label="turns" value={analytics.turn_count} testId="gl-m-turns" />
            <Metric
              label="compliance rate"
              value={analytics.conversion_rate === null ? "—" : `${Math.round(analytics.conversion_rate * 100)}%`}
              muted={analytics.conversion_rate === null}
              title={
                analytics.conversion_rate === null
                  ? "No call has completed yet, so there is no rate to report."
                  : undefined
              }
              testId="gl-m-rate"
            />
            <Metric label="credentials captured" value={analytics.credentials_captured} testId="gl-m-captured" />
          </div>

          <div className="ui-gl-split">
            <div className="ui-ci-col">
              <span className="ui-pane-title">Stage distribution</span>
              {Object.keys(analytics.stage_counts).length === 0 ? (
                <Empty>No turns recorded yet.</Empty>
              ) : (
                <ul className="ui-gl-bars" data-testid="gl-stage-bars">
                  {STAGE_LADDER.filter((stage) => analytics.stage_counts[stage] !== undefined).map((stage) => (
                    <li key={stage}>
                      <span className="ui-gl-bar-label">{stage}</span>
                      <span className="ui-gl-bar-track">
                        <span
                          className="ui-ci-bar"
                          style={{ width: `${Math.round(((analytics.stage_counts[stage] ?? 0) / stageMax) * 100)}%` }}
                        />
                      </span>
                      <span className="op-value">{analytics.stage_counts[stage]}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="ui-ci-col">
              <span className="ui-pane-title">Outcomes</span>
              {Object.keys(analytics.outcomes).length === 0 ? (
                <Empty>No outcomes recorded yet.</Empty>
              ) : (
                <ul className="ui-gl-bars" data-testid="gl-outcome-bars">
                  {Object.entries(analytics.outcomes).map(([outcome, count]) => (
                    <li key={outcome} data-outcome={outcome}>
                      <span className="ui-gl-bar-label">{outcomeLabel(outcome)}</span>
                      <span className="ui-gl-bar-track">
                        <span
                          className="ui-ci-bar ui-ci-bar-alt"
                          style={{ width: `${Math.round((count / outcomeMax) * 100)}%` }}
                        />
                      </span>
                      <span className="op-value">{count}</span>
                    </li>
                  ))}
                </ul>
              )}

              <span className="ui-pane-title">Redaction ledger</span>
              {Object.keys(analytics.redaction_kinds).length === 0 ? (
                <Empty>Nothing credential-shaped has passed through the ledger.</Empty>
              ) : (
                <ul className="ui-gl-kinds" data-testid="gl-redaction-kinds">
                  {Object.entries(analytics.redaction_kinds).map(([kind, count]) => (
                    <li key={kind}>
                      <code>{kind}</code>
                      <span className="op-value">{count}</span>
                    </li>
                  ))}
                </ul>
              )}
              <p className="ui-id">
                Every count above is a record that a credential was elicited. None of them is
                the credential.
              </p>
            </div>
          </div>
        </>
      ) : (
        <Empty>Loading the ledger…</Empty>
      )}

      {note ? (
        <p className="panel-note" data-testid="gl-analytics-note">
          {note}
        </p>
      ) : null}
    </GlShell>
  );
}

function Metric({
  label,
  value,
  muted,
  title,
  testId,
}: {
  label: string;
  value: number | string;
  muted?: boolean;
  title?: string;
  testId?: string;
}) {
  return (
    <div className="ui-ci-metric" title={title}>
      <span className="op-label">{label}</span>
      <span className="op-value" data-muted={muted ? "true" : undefined} data-testid={testId}>
        {typeof value === "number" ? value.toLocaleString() : value}
      </span>
    </div>
  );
}