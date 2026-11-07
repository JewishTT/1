import { useCallback, useEffect, useState } from "react";

import { api, type LabOverviewWire } from "../lib/api";

export interface LabOverviewState {
  readonly data: LabOverviewWire | null;
  readonly loading: boolean;
  readonly error: string | null;
  readonly refresh: () => Promise<void>;
}

/**
 * One fetch for the whole canvas. The lab overview is the instrument: every
 * panel renders from it, and a mutation calls `refresh()` rather than stitching
 * a local cache that could disagree with the audit chain.
 */
export function useLabOverview(): LabOverviewState {
  const [data, setData] = useState<LabOverviewWire | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const next = await api.labOverview();
      setData(next);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { data, loading, error, refresh };
}
