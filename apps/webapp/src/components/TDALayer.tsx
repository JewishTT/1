import type { InvariantResult } from "../lib/science/types";

const DIM_LABELS: Record<string, string> = { "0": "H0", "1": "H1", "2": "H2" };

export interface TDALayerProps {
  active: boolean;
  loading: boolean;
  invariants: Record<string, InvariantResult>;
  notes: Record<string, string>;
  entityLabels: Record<string, string>;
  selectedId?: string | null;
  onToggle: () => void;
}

function bars(dim: number, result: InvariantResult): number {
  return result.stats?.[String(dim)]?.num_bars ?? 0;
}

export function TDALayer({ active, loading, invariants, notes, entityLabels, selectedId, onToggle }: TDALayerProps) {
  if (!active) return null;

  const loopEntities = Object.values(invariants).filter((inv) => bars(1, inv) > 0);
  const selected = selectedId ? invariants[selectedId] : undefined;
  const selectedNote = selectedId ? notes[selectedId] : undefined;

  return (
    <aside className="tda-layer" data-testid="tda-layer">
      <header className="tda-layer-head">
        <span className="tda-layer-title">◬ TOPO LAYER</span>
        <span className={`status-chip ${loading ? "on" : ""}`}>{loading ? "COMPUTING" : "ARMED"}</span>
        <button className="icon-btn" data-testid="tda-close" onClick={onToggle} aria-label="Close TDA layer">
          ✕
        </button>
      </header>

      {loading ? (
        <div className="tda-layer-status">reconstructing topology from observation timelines…</div>
      ) : (
        <div className="tda-layer-body">
          {selected ? (
            <div className="tda-entity" data-testid="tda-selected">
              <div className="tda-entity-name">{entityLabels[selected.entity_id] ?? selected.entity_id}</div>
              <div className="tda-kv">
                <span>series</span>
                <b>{selected.series_len} pts</b>
              </div>
              <div className="tda-kv">
                <span>embed</span>
                <b>
                  τ={selected.embedding.lag}, m={selected.embedding.embed_dim}
                </b>
              </div>
              <div className="tda-kv">
                <span>digest</span>
                <b className="mono">{selected.digest}</b>
              </div>
              {selected.structural_only ? (
                <div className="tda-kv">
                  <span>mode</span>
                  <b>structural_only</b>
                </div>
              ) : null}
              <div className="tda-bars">
                {Object.keys(selected.diagrams ?? {})
                  .sort((a, b) => Number(a) - Number(b))
                  .map((dim) => (
                    <div className="tda-bar-row" key={dim}>
                      <span>{DIM_LABELS[dim] ?? `H${dim}`}</span>
                      <div className="tda-bar-track">
                        <div
                          className="tda-bar-fill"
                          style={{ width: `${Math.min(100, bars(Number(dim), selected) * 14)}%` }}
                        />
                      </div>
                      <b>{bars(Number(dim), selected)}</b>
                    </div>
                  ))}
              </div>
              {bars(1, selected) > 0 ? (
                <div className="tda-loop" data-testid="tda-loop-badge">
                  ◍ H1 loop persistent — cycle materialized
                </div>
              ) : null}
            </div>
          ) : selectedId ? (
            <div className="tda-layer-status" data-testid="tda-note">
              {selectedNote ?? "no topology computed for this selection"}
            </div>
          ) : (
            <div className="tda-layer-status">select a node to inspect its topology</div>
          )}

          <div className="tda-layer-divider" />
          <div className="tda-layers">
            <span className="tda-layers-label">LIVE LAYERS</span>
            {Object.entries(invariants).map(([id, inv]) => (
              <div className="tda-layer-chip" key={id}>
                <span className="tda-layer-chip-name">{entityLabels[id] ?? id}</span>
                <span className="mono">{inv.digest.slice(0, 12)}</span>
                {bars(1, inv) > 0 && <span className="loop-dot" title="H1 loop" />}
              </div>
            ))}
            {Object.entries(notes).map(([id, note]) => (
              <div className="tda-layer-chip" data-testid="tda-chip-note" key={id}>
                <span className="tda-layer-chip-name">{entityLabels[id] ?? id}</span>
                <span className="tda-note-text">{note}</span>
              </div>
            ))}
          </div>

          {loopEntities.length > 1 ? (
            <div className="tda-loop-summary">{loopEntities.length} entities hold persistent H1 loops</div>
          ) : null}
        </div>
      )}
    </aside>
  );
}