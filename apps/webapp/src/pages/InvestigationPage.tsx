import type { Dispatch, SetStateAction } from "react";

export interface InvestigationMetrics {
  objective: string;
  acquisition: { qps: number; queue: number; freshnessSec: number };
  interpretation: { documents: number; mentions: number; candidates: number };
  admission: { accepted: number; rejected: number; pendingApproval: number };
  knowledge: { entities: number; assertions: number; findings: number };
  recrawl: { intervalSec: number; nextAt: string };
}

export const EMPTY_METRICS: InvestigationMetrics = {
  objective: "Untitled investigation",
  acquisition: { qps: 0, queue: 0, freshnessSec: 0 },
  interpretation: { documents: 0, mentions: 0, candidates: 0 },
  admission: { accepted: 0, rejected: 0, pendingApproval: 0 },
  knowledge: { entities: 0, assertions: 0, findings: 0 },
  recrawl: { intervalSec: 0, nextAt: "-" },
};

interface Props {
  metrics: InvestigationMetrics;
  onPause?: () => void;
  onResume?: () => void;
  pauseRequested?: boolean;
  setPauseRequested?: Dispatch<SetStateAction<boolean>>;
}

function MetricTile({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="metric-tile" data-testid={`tile-${label}`}>
      <span className="metric-label">{label}</span>
      <span className="metric-value">{value}</span>
    </div>
  );
}

export function InvestigationPage({
  metrics,
  onPause,
  onResume,
  pauseRequested = false,
  setPauseRequested,
}: Props) {
  return (
    <section data-testid="investigation-page">
      <h1>{metrics.objective}</h1>

      <div className="panel">
        <h2>Acquisition</h2>
        <div className="tiles">
          <MetricTile label="qps" value={metrics.acquisition.qps} />
          <MetricTile label="queue" value={metrics.acquisition.queue} />
          <MetricTile label="freshness" value={`${metrics.acquisition.freshnessSec}s`} />
        </div>
        <div className="panel-actions">
          {pauseRequested ? (
            <button
              type="button"
              data-testid="resume-btn"
              onClick={() => {
                onResume?.();
                setPauseRequested?.(false);
              }}
            >
              Resume
            </button>
          ) : (
            <button
              type="button"
              data-testid="pause-btn"
              onClick={() => {
                onPause?.();
                setPauseRequested?.(true);
              }}
            >
              Pause
            </button>
          )}
        </div>
      </div>

      <div className="panel">
        <h2>Interpretation</h2>
        <div className="tiles">
          <MetricTile label="documents" value={metrics.interpretation.documents} />
          <MetricTile label="mentions" value={metrics.interpretation.mentions} />
          <MetricTile label="candidates" value={metrics.interpretation.candidates} />
        </div>
      </div>

      <div className="panel">
        <h2>Admission</h2>
        <div className="tiles">
          <MetricTile label="accepted" value={metrics.admission.accepted} />
          <MetricTile label="rejected" value={metrics.admission.rejected} />
          <MetricTile label="pending approval" value={metrics.admission.pendingApproval} />
        </div>
      </div>

      <div className="panel">
        <h2>Knowledge</h2>
        <div className="tiles">
          <MetricTile label="entities" value={metrics.knowledge.entities} />
          <MetricTile label="assertions" value={metrics.knowledge.assertions} />
          <MetricTile label="findings" value={metrics.knowledge.findings} />
        </div>
        <p className="analysis-note" data-testid="analysis-panel">
          Analysis panel: topological + recrawl signal summary renders here. Next recrawl at{" "}
          {metrics.recrawl.nextAt} (every {metrics.recrawl.intervalSec}s).
        </p>
      </div>
    </section>
  );
}
