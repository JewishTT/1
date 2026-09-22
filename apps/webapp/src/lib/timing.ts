/** Time-window statistics for the entity timeline (011/FR-009, temporality UI).

Pure functions over ``observed_at`` timestamps: burstiness (coefficient of
variation of inter-event gaps) and events-per-day. Honest when data is thin —
a window with <3 events yields no burstiness, never a fabricated value (I-3).
*/

export type TimestampInput = string | number;

export function toEpochMs(t: TimestampInput): number | null {
  if (typeof t === "number") return Number.isFinite(t) ? t : null;
  const ms = Date.parse(t);
  return Number.isFinite(ms) ? ms : null;
}

function sortedEpochs(at: TimestampInput[]): number[] {
  return at
    .map(toEpochMs)
    .filter((v): v is number => v !== null)
    .sort((a, b) => a - b);
}

/** Coefficient of variation of inter-event gaps; null for <3 events or zero span. */
export function burstiness(at: TimestampInput[]): number | null {
  const ms = sortedEpochs(at);
  if (ms.length < 3) return null;
  const gaps: number[] = [];
  for (let i = 1; i < ms.length; i++) gaps.push(ms[i] - ms[i - 1]);
  const mean = gaps.reduce((sum, g) => sum + g, 0) / gaps.length;
  if (mean <= 0) return null;
  const variance = gaps.reduce((sum, g) => sum + (g - mean) ** 2, 0) / gaps.length;
  return Math.sqrt(variance) / mean;
}

/** Events per 24h spanned by the window; null with fewer than 2 distinct stamps. */
export function eventsPerDay(at: TimestampInput[]): number | null {
  const ms = sortedEpochs(at);
  if (ms.length < 2) return null;
  const spanMs = ms[ms.length - 1] - ms[0];
  if (spanMs <= 0) return null;
  return (ms.length / spanMs) * 86_400_000;
}