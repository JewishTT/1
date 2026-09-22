/* eslint-disable @typescript-eslint/no-explicit-any */

/** Topological invariant panel (011/FR-009).

Runs a series + Takens embedding through ``/api/science/invariant`` and shows
the persistence barcodes per dimension, per-dimension statistics, the content
digest and — when a previous diagram was clamped — the drift (changed?). The
result is labelled STRUCTURAL ONLY (I-6): a shape descriptor, never an identity
claim. Pure-python VR (``vr-z2-science``) means no gudhi dependency.
*/

import { useState } from "react";

import type { InvariantParams, InvariantResult } from "../lib/science/types";

const DIM_COLORS = ["#4caf50", "#2196f3", "#ff9800"];
const BW = 560;
const BPAD = 26;

function defaultSeries(): string {
  return Array.from({ length: 48 }, (_, i) =>
    +(Math.sin((2 * Math.PI * i) / 24) * 10).toFixed(2),
  ).join(", ");
}

interface BarcodePanelProps {
  diagrams: InvariantResult["diagrams"];
}

function BarcodePanel({ diagrams }: BarcodePanelProps) {
  const dims = Object.keys(diagrams)
    .map(Number)
    .sort((a, b) => a - b);
  if (dims.length === 0) {
    return <p data-testid="barcode-empty">No persistence diagram computed.</p>;
  }
  return (
    <div data-testid="barcode-panel">
      {dims.map((dim) => {
        const bars = diagrams[String(dim)].sort(
          (a, b) => (a[1] ?? Number.POSITIVE_INFINITY) - (b[1] ?? Number.POSITIVE_INFINITY),
        );
        const maxDeath = Math.max(
          ...bars.map(([, d]) => (d === null ? 0 : d)),
          1,
        );
        const inner = BW - 2 * BPAD;
        const rowH = 16;
        return (
          <div key={dim} data-testid={`barcode-dim-${dim}`}>
            <p className="op-label">DIMENSION H{dim}</p>
            <svg viewBox={`0 0 ${BW} ${bars.length * rowH + 20}`} width="100%">
              {bars.map(([birth, death], i) => {
                const x = BPAD + (birth / maxDeath) * inner;
                const infinite = death === null;
                const xEnd = infinite ? BW - BPAD : BPAD + (death! / maxDeath) * inner;
                const y = 14 + i * rowH;
                return (
                  <g key={i}>
                    <line
                      x1={x}
                      y1={y}
                      x2={xEnd}
                      y2={y}
                      stroke={DIM_COLORS[dim % DIM_COLORS.length]}
                      strokeWidth={4}
                      data-testid={`barcode-bar-${dim}`}
                    />
                    {infinite && (
                      <polygon
                        points={`${xEnd - 6},${y - 3} ${xEnd - 6},${y + 3} ${xEnd},${y}`}
                        fill={DIM_COLORS[dim % DIM_COLORS.length]}
                        data-testid={`barcode-inf-${dim}`}
                      />
                    )}
                  </g>
                );
              })}
            </svg>
          </div>
        );
      })}
    </div>
  );
}

interface Props {
  entityId: string;
  result: InvariantResult | null;
  loading: boolean;
  error: string | null;
  onRun: (params: InvariantParams) => void;
}

export function TDAPanel({ entityId, result, loading, error, onRun }: Props) {
  const [seriesText, setSeriesText] = useState(defaultSeries);
  const [lag, setLag] = useState(2);
  const [embedDim, setEmbedDim] = useState(2);
  const [maxDim, setMaxDim] = useState(1);

  const run = () => {
    const series = seriesText
      .split(/[,;\s]+/)
      .map(Number)
      .filter((v) => Number.isFinite(v));
    if (series.length === 0) return;
    onRun({
      entity_id: entityId,
      series,
      lag,
      embed_dim: embedDim,
      max_dim: maxDim,
      prev_diagram: result?.diagrams,
    });
  };

  return (
    <div data-testid="tda-panel">
      <div className="tda-controls">
        <label>
          Series (observations)
          <textarea
            data-testid="topology-series"
            rows={3}
            value={seriesText}
            onChange={(e) => setSeriesText(e.target.value)}
          />
        </label>
        <label>
          lag
          <input
            type="number"
            min={1}
            value={lag}
            onChange={(e) => setLag(Number(e.target.value))}
          />
        </label>
        <label>
          embed dim
          <input
            type="number"
            min={2}
            value={embedDim}
            onChange={(e) => setEmbedDim(Number(e.target.value))}
          />
        </label>
        <label>
          max homology
          <input
            type="number"
            min={0}
            max={2}
            value={maxDim}
            onChange={(e) => setMaxDim(Number(e.target.value))}
          />
        </label>
        <button type="button" data-testid="run-topology-btn" onClick={run} disabled={loading}>
          {loading ? "Computing…" : "Run invariant"}
        </button>
      </div>

      {error && <p data-testid="topology-error">Error: {error}</p>}

      {result && (
        <div className="tda-result" data-testid="topology-result">
          <p className="op-label">
            provider {result.provider} · {result.series_len} points ·{" "}
            <span data-testid="structural-badge" title="structural signals never imply identity (I-6)">
              STRUCTURAL ONLY
            </span>{" "}
            · sha256:{result.digest.slice(0, 12)}…
          </p>
          {result.drift && (
            <p data-testid="topology-drift" title={result.drift.metric}>
              drift: {result.drift.changed ? "CHANGED" : "stable"} · Δmax persistence{" "}
              {result.drift.delta_max_persistence.toFixed(6)}
            </p>
          )}
          <BarcodePanel diagrams={result.diagrams} />
          <div className="tda-stats" data-testid="topology-stats">
            {Object.entries(result.stats)
              .sort(([a], [b]) => Number(a) - Number(b))
              .map(([dim, s]) => (
                <span key={dim} className="op-tile" data-testid={`stat-${dim}`}>
                  H{dim}: {s.num_bars} bars · mean {s.mean_persistence.toFixed(3)} · max{" "}
                  {s.max_persistence.toFixed(3)} · total {s.total_persistence.toFixed(3)}
                </span>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}