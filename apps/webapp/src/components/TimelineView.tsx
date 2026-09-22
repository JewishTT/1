/** Timeline view — temporality UI (011/FR-009).

Renders entity observations on a time axis (positions derived from
``observed_at`` when available, fallback to even spacing by sequence order).
Pure SVG — no library dependencies.
*/

import type { TimelineMetrics, TimelineEntry } from "../lib/timelineTypes";

const W = 560;
const H = 92;
const PAD = 30;
const AXIS_Y = 44;

function truncate(text: string, max = 22): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

export interface TimelineViewProps {
  entries: TimelineEntry[];
  metrics?: TimelineMetrics;
  title?: string;
}

export function TimelineView({ entries, metrics, title = "Timeline" }: TimelineViewProps) {
  if (entries.length === 0) {
    return (
      <section data-testid="entity-timeline" className="timeline-panel">
        <h2>{title}</h2>
        <p>No timeline observed.</p>
      </section>
    );
  }

  const epochs = entries.map((e) => e.at ?? null);
  const valid = epochs.filter((v): v is string => v !== null).map((v) => Date.parse(v));
  const usable = Math.min(...valid);
  const span = valid.length > 0 ? Math.max(...valid) - usable : 0;

  const xs = entries.map((entry, i) => {
    if (valid.length >= 2) {
      return PAD + ((Date.parse(entry.at ?? "") - usable) / (span || 1)) * (W - 2 * PAD);
    }
    // Evenly spaced fallback (sequence order) when no timestamps are known.
    return entries.length === 1 ? W / 2 : PAD + (i / (entries.length - 1)) * (W - 2 * PAD);
  });

  const firstLabel = valid.length >= 2 ? new Date(usable).toISOString() : null;
  const lastMilestone = valid.length >= 2 ? Math.max(...valid) : null;

  return (
    <section data-testid="entity-timeline" className="timeline-panel">
      <h2>{title}</h2>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        role="img"
        aria-label="entity timeline"
        data-testid="timeline-svg"
      >
        <line x1={PAD} y1={AXIS_Y} x2={W - PAD} y2={AXIS_Y} stroke="var(--c-muted, #888)" />
        {entries.map((entry, i) => (
          <g key={entry.id} data-testid="timeline-marker">
            <circle cx={xs[i]} cy={AXIS_Y} r={4} fill="var(--c-accent, #4caf50)" />
            {i % 3 === 0 && (
              <text
                x={xs[i]}
                y={AXIS_Y + 18}
                textAnchor="middle"
                fontSize={9}
                fill="var(--c-fg-muted, #bbb)"
              >
                {truncate(`${entry.id} · ${entry.label}`)}
              </text>
            )}
            {i % 3 === 0 && (
              <text x={xs[i]} y={19} textAnchor="middle" fontSize={8} fill="var(--c-muted, #999)">
                {i + 1}
              </text>
            )}
          </g>
        ))}
      </svg>
      <p className="op-label">
        {firstLabel
          ? `window ${firstLabel} → ${new Date(lastMilestone ?? usable).toISOString()}`
          : "sequence order (no timestamps)"}
      </p>
      {(metrics?.burstiness !== null && metrics?.burstiness !== undefined) ||
      (metrics?.events_per_day !== null && metrics?.events_per_day !== undefined) ? (
        <p data-testid="timeline-metrics" className="op-label">
          burstiness {metrics.burstiness === null ? "–" : metrics.burstiness.toFixed(2)} · events/day{" "}
          {metrics.events_per_day === null ? "–" : metrics.events_per_day.toFixed(1)}
        </p>
      ) : null}
    </section>
  );
}