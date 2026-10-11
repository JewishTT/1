import { useCallback, useState } from "react";

import { Button } from "../../ui/Button";
import { Input } from "../../ui/Input";
import { api } from "../../lib/api";
import type { CiProjectionWire } from "../../lib/api";
import type { SocialProjectionRow } from "../types";
import { CiEmpty, CiPanelShell, StatusChip } from "./panelParts";

/**
 * Social-reaction simulation panel (US5).
 *
 * Inject a narrative / information shock into a modeled population and project the
 * reaction over a horizon — reach, polarization, and a phase-transition risk
 * indicator (the r_c analog). A too-small/sparse population reports LOW confidence
 * rather than a confident-looking curve. The run's artifacts are referenced for
 * inspection; the numbers are claims backed by the science operators, never bare
 * dashboard figures (§70).
 */
export function SocialPanel() {
  const [population, setPopulation] = useState("pop-lab-1");
  const [narrative, setNarrative] = useState("");
  const [horizon, setHorizon] = useState("24");
  const [projection, setProjection] = useState<SocialProjectionRow | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = useCallback(async () => {
    setBusy(true);
    setNote(null);
    try {
      const res = await api.runProjection({
        population_ref: population.trim(),
        narrative_input: narrative,
        horizon: Number(horizon) || 24,
      });
      setProjection(toProjectionRow(res.projection));
    } catch (err) {
      setProjection(null);
      setNote(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }, [population, narrative, horizon]);

  return (
    <CiPanelShell
      title="Social-reaction simulation"
      scope="investigation-scoped"
      status={
        projection ? (
          <StatusChip
            label={projection.phase_transition_risk.threshold_crossed ? "phase-transition risk" : "stable"}
            tone={projection.phase_transition_risk.threshold_crossed ? "danger" : "accent"}
            testId="ci-social-risk"
          />
        ) : undefined
      }
      testId="ci-social-panel"
    >
      <div className="ui-ci-col">
        <Input value={population} onChange={(e) => setPopulation(e.target.value)} aria-label="Population reference" data-testid="ci-population-input" />
        <Input value={narrative} onChange={(e) => setNarrative(e.target.value)} placeholder="narrative / information shock" aria-label="Narrative input" data-testid="ci-narrative-input" />
        <Input value={horizon} onChange={(e) => setHorizon(e.target.value)} aria-label="Horizon" data-testid="ci-horizon-input" />
        <Button size="sm" icon="diagram" disabled={busy} onClick={() => void run()} data-testid="ci-run-projection">
          Run projection
        </Button>
      </div>

      {projection ? (
        <div className="ui-ci-col" data-testid="ci-projection">
          <div className="ui-ci-list-head">
            <span className="ui-pane-title">Projection {projection.projection_id}</span>
            <StatusChip label={`confidence ${projection.confidence}`} tone={projection.confidence === "low" ? "gold" : "neutral"} testId="ci-social-confidence" />
          </div>
          <TrajectorySpark rows={projection.trajectories} />
          <div className="ui-ci-metrics">
            <div className="ui-ci-metric">
              <span className="op-label">phase-transition indicator</span>
              <span className="op-value">{projection.phase_transition_risk.indicator.toFixed(2)}</span>
            </div>
            <div className="ui-ci-metric">
              <span className="op-label">threshold crossed</span>
              <span className="op-value">{projection.phase_transition_risk.threshold_crossed ? "yes" : "no"}</span>
            </div>
          </div>
          {projection.artifacts_ref ? (
            <span className="ui-id">artifacts: {projection.artifacts_ref}</span>
          ) : null}
        </div>
      ) : (
        <CiEmpty>Inject a narrative into a modeled population to project the reaction.</CiEmpty>
      )}

      {note ? (
        <p className="panel-note" data-testid="ci-social-note">
          {note}
        </p>
      ) : null}
    </CiPanelShell>
  );
}

/** A minimal inline trajectory read-out (reach/polarization over t). No chart lib needed. */
function TrajectorySpark({ rows }: { rows: SocialProjectionRow["trajectories"] }) {
  if (rows.length === 0) return null;
  const max = Math.max(1, ...rows.map((r) => Math.max(r.reach, r.polarization)));
  return (
    <ul className="ui-ci-trajectory" data-testid="ci-trajectory">
      {rows.map((r) => (
        <li key={r.t}>
          <span className="ui-id">t{r.t}</span>
          <span className="ui-ci-bar" style={{ width: `${(r.reach / max) * 100}%` }} title={`reach ${r.reach}`} />
          <span className="ui-ci-bar ui-ci-bar-alt" style={{ width: `${(r.polarization / max) * 100}%` }} title={`polarization ${r.polarization}`} />
        </li>
      ))}
    </ul>
  );
}

function toProjectionRow(w: CiProjectionWire): SocialProjectionRow {
  return {
    projection_id: w.projection_id,
    trajectories: w.trajectories,
    phase_transition_risk: w.phase_transition_risk,
    confidence: w.confidence,
    artifacts_ref: w.artifacts_ref,
  };
}
