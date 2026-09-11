import { useState } from "react";

import type { ExperimentRun, ReproductionResult } from "../lib/science/types";

interface Props {
  runs: ExperimentRun[];
  reproductions: ReproductionResult[];
  onRecord?: () => void;
  onReproduce?: (runId: string) => void;
}

export function ExperimentsPage({ runs, reproductions, onRecord, onReproduce }: Props) {
  const [error] = useState<string | null>(null);

  return (
    <section data-testid="experiments-page">
      <h1>Reproducible experiments</h1>
      {error && <p data-testid="error-view">Error: {error}</p>}
      <div className="panel">
        <h2>Registry (FR-012)</h2>
        {onRecord && (
          <button type="button" data-testid="record-btn" onClick={onRecord}>
            Record a sample run
          </button>
        )}
        {runs.length === 0 ? (
          <p data-testid="no-runs">No experiment runs recorded.</p>
        ) : (
          <ul data-testid="run-list">
            {runs.map((run) => (
              <li key={run.run_id} data-testid={`run-item-${run.run_id}`}>
                {run.run_id} — v{run.pipeline_version}, seed {run.seed}, tolerance {run.tolerance}
                {onReproduce && (
                  <button
                    type="button"
                    data-testid={`reproduce-${run.run_id}`}
                    onClick={() => onReproduce(run.run_id)}
                  >
                    Reproduce
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="panel">
        <h2>Reproduction log (SC-007)</h2>
        {reproductions.length === 0 ? (
          <p data-testid="no-reproductions">Nothing reproduced yet.</p>
        ) : (
          <ul data-testid="reproduction-list">
            {reproductions.map((r) => (
              <li
                key={r.run_id}
                data-testid={`reproduction-item-${r.run_id}`}
                data-reproduced={r.reproduced}
              >
                {r.run_id} → {r.reproduced ? "reproduced ✓" : "NOT reproduced"}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
