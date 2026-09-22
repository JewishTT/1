/**
 * TDA overlay layer sources (I-1, I-3).
 *
 * We do NOT fabricate synthetic series for entities. Instead a temporal series
 * is derived honestly from an entity's immutable observation timeline:
 * `observed_at` timestamps are bucketed per day across [min..max] of the
 * available dates. If fewer than MIN_DATES valid timestamps exist the entity
 * gets `null` and the UI reports "insufficient temporal data".
 */

export const MIN_DATES = 3;

export interface TemporalSeriesResult {
  series: number[] | null;
  startDay: string | null;
  endDay: string | null;
}

function parseDay(iso: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}/.test(iso)) return null;
  const d = new Date(iso.slice(0, 10) + "T00:00:00Z");
  if (Number.isNaN(d.getTime())) return null;
  return iso.slice(0, 10);
}

/**
 * Buckets an entity timeline into a daily-count series. Deterministic and
 * gap-aware: every day between the first and last observation is represented
 * (absent days count 0) exactly like the control-plane resolves it.
 */
export function buildTemporalSeriesFromTimeline(
  timeline: Array<{ observed_at?: string | null }>,
): TemporalSeriesResult {
  const days: string[] = [];
  for (const entry of timeline ?? []) {
    if (!entry.observed_at) continue;
    const day = parseDay(entry.observed_at);
    if (day) days.push(day);
  }
  if (days.length < MIN_DATES) return { series: null, startDay: null, endDay: null };

  const start = days.slice().sort()[0];
  const end = days.slice().sort()[days.length - 1];
  const cursor = new Date(start + "T00:00:00Z");
  const stop = new Date(end + "T00:00:00Z");
  const counts: number[] = [];
  while (cursor <= stop) {
    const key = cursor.toISOString().slice(0, 10);
    counts.push(days.filter((d) => d === key).length);
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return { series: counts, startDay: start, endDay: end };
}

export function isHonestSeries(result: TemporalSeriesResult): result is TemporalSeriesResult & { series: number[] } {
  return result.series !== null;
}