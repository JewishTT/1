/**
 * Timelapse slider (011/FR-009) — scrub / play the state-at-time
 * reconstruction.
 *
 * Controlled range input over [min, max] epoch-ms bounds plus a play/pause
 * toggle; emits T via ``onScrub``. Displays the current instant and, when
 * provided, live node/edge counts at T. Pure additive UI — reads/writes
 * nothing to storage (persistence is owned upstream).
 */

import { useEffect, useId, useRef, useState } from "react";

export interface TimelineSliderCounts {
  nodes: number;
  edges: number;
}

export interface TimelineSliderProps {
  /** Epoch-ms lower bound of the replay window. */
  min: number;
  /** Epoch-ms upper bound of the replay window. */
  max: number;
  /** Current instant T (epoch ms), controlled by the parent. */
  value: number;
  /** Live node/edge counts at T, when the parent computes them. */
  counts?: TimelineSliderCounts;
  /** Called with the next T on scrub and on every play tick. */
  onScrub: (t: number) => void;
  /** Optional tick instants (epoch ms) rendered as a datalist axis. */
  ticks?: number[];
}

function formatInstant(ms: number): string {
  if (!Number.isFinite(ms)) return "—";
  return `${new Date(ms).toISOString().slice(0, 16).replace("T", " ")}Z`;
}

export function TimelineSlider({
  min,
  max,
  value,
  counts,
  onScrub,
  ticks = [],
}: TimelineSliderProps) {
  const [playing, setPlaying] = useState(false);
  const listId = useId();

  const onScrubRef = useRef(onScrub);
  onScrubRef.current = onScrub;
  // Play cursor: while playing the slider advances its own position (a
  // controlled parent echoes onScrub back into `value`; if it does not, the
  // cursor still walks deterministically to the window end). A closed window
  // (min === max) has nothing to scrub — the controls are honestly disabled.
  const playRef = useRef(value);

  const disabled = !(Number.isFinite(min) && Number.isFinite(max) && min < max);
  const clamped = disabled ? min : Math.min(Math.max(value, min), max);
  const step = disabled ? 1 : Math.max(1, Math.floor((max - min) / 200));
  const axis = [...new Set(ticks.filter((tk) => Number.isFinite(tk) && tk >= min && tk <= max))].sort(
    (a, b) => a - b,
  );

  // Keep the play cursor in sync with the controlled value (parent echo).
  useEffect(() => {
    playRef.current = value;
  }, [value]);

  const togglePlay = () => {
    if (disabled) return;
    if (!playing) playRef.current = clamped; // start from the shown instant
    setPlaying((p) => !p);
  };

  // Deterministic play: advance fixed steps until the window end, then stop.
  useEffect(() => {
    if (!playing) return;
    const span = Math.max(1, max - min);
    const stepMs = span / 60;
    const id = window.setInterval(() => {
      const current = playRef.current;
      if (current >= max) {
        setPlaying(false);
        return;
      }
      const next = Math.min(max, current + stepMs);
      playRef.current = next;
      onScrubRef.current(next);
    }, 150);
    return () => window.clearInterval(id);
  }, [playing, min, max]);

  return (
    <div data-testid="timelapse-slider" style={{ display: "flex", flexDirection: "column", gap: "0.45rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <button
          type="button"
          className="toolbar-btn"
          onClick={togglePlay}
          disabled={disabled}
          aria-label={playing ? "pause timelapse" : "play timelapse"}
          data-testid="timelapse-play"
        >
          {playing ? "❚❚" : "▶"}
        </button>
        <span className="op-label" data-testid="timelapse-t">
          T {disabled ? "—" : formatInstant(clamped)}
        </span>
        {counts ? (
          <span className="status-chip" data-testid="timelapse-counts">
            N {counts.nodes} · E {counts.edges}
          </span>
        ) : null}
      </div>
      <input
        type="range"
        list={listId}
        min={disabled ? undefined : min}
        max={disabled ? undefined : max}
        step={disabled ? undefined : step}
        value={disabled ? 0 : clamped}
        disabled={disabled}
        aria-label="timelapse position"
        data-testid="timelapse-range"
        onChange={(e) => onScrub(Number(e.target.value))}
        style={{ width: "100%" }}
      />
      <datalist id={listId}>
        {axis.map((tk) => (
          <option key={tk} value={tk} />
        ))}
      </datalist>
    </div>
  );
}