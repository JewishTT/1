import type { TemporalFeatureView, TemporalHistoryView } from "../lib/api";

export interface TemporalMaterializationPanelProps {
  entityId: string;
  history: TemporalHistoryView;
  features: TemporalFeatureView[];
}

export function TemporalMaterializationPanel({ entityId, history, features }: TemporalMaterializationPanelProps) {
  const cut = history.publication.source_cut;
  return (
    <section className="panel" data-testid="temporal-materialization-panel">
      <h2>Temporal materialization</h2>
      <div className="chip-row">
        <span className="status-chip" data-testid="temporal-publication-id">{history.publication.publication_id}</span>
        <span className="status-chip" data-testid="temporal-cut-id">cut {cut.cut_id}</span>
        <span className="status-chip">generation {history.publication.projection_generation}</span>
        <span className="status-chip">entity {entityId}</span>
      </div>
      <div data-testid="temporal-windows">
        {history.publication.revisions.map((revision) => (
          <div
            className="node-card-row"
            data-testid={revision.window.lifecycle === "dormant" ? "temporal-window-dormant" : "temporal-window"}
            key={revision.revision_id}
          >
            <span className="node-card-attr-v">{revision.window.window_start.slice(0, 10)}</span>
            <span className="op-label">{revision.window.lifecycle} · {revision.window.event_count} events</span>
            <span className="op-value">{revision.revision_id}</span>
          </div>
        ))}
      </div>
      {features.length > 0 ? (
        <div data-testid="temporal-features">
          <div className="op-label">FEATURES</div>
          {features.map((feature) => (
            <div className="node-card-row" key={feature.feature_fingerprint}>
              <span className="op-label">{feature.feature_name}</span>
              <span className="op-value">{feature.available ? String(feature.value) : "unavailable"}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="panel-note" data-testid="temporal-features-empty">No feature records for this source cut.</p>
      )}
    </section>
  );
}
