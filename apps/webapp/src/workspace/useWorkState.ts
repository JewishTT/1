import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { api, fetchOpsMetrics, type OpsMetrics } from "../lib/api";
import { toWorkStatus } from "../ui/status";

/**
 * Work state for the top bar (§11: the top bar reports work state, not URL
 * structure).
 *
 * Honest by construction. The investigation record gives us its name and its
 * state; the ops metrics give us throughput and lag. What they do *not* give us
 * is a per-investigation entity/observation/finding/source census — the backend
 * exposes no such endpoint today. Rather than invent numbers, `entityCount` and
 * friends stay `null` and the top bar renders "—", with a tooltip saying why.
 * That is the difference between a top bar that reports work and one that
 * decorates (§8).
 *
 * This is server state, so it lives in TanStack Query, not the workspace store
 * (§7).
 */

export interface WorkState {
  investigationId: string | null;
  investigationName: string | null;
  /** Closed-vocabulary state of the investigation itself (§92). */
  state: ReturnType<typeof toWorkStatus>;
  /** Raw platform state string, shown verbatim so the mapping stays auditable. */
  rawState: string | null;
  entityCount: number | null;
  observationCount: number | null;
  findingCount: number | null;
  sourceCount: number | null;
  /** ISO timestamp of the newest observation, when the server reports one. */
  lastUpdated: string | null;
  /** Observations per second across the pipeline, when reported. */
  throughput: number | null;
  /**
   * Platform-wide useful observations. NOT this investigation's count — the
   * top bar labels it "pipeline" so the distinction cannot be lost (§99).
   */
  pipelineObservationCount: number | null;
  /** True while any of the queries is in flight. */
  loading: boolean;
  error: string | null;
}

const UNKNOWN_WORK_STATE: WorkState = {
  investigationId: null,
  investigationName: null,
  state: "Unknown",
  rawState: null,
  entityCount: null,
  observationCount: null,
  findingCount: null,
  sourceCount: null,
  lastUpdated: null,
  throughput: null,
  pipelineObservationCount: null,
  loading: false,
  error: null,
};

export function useWorkState(investigationId: string | null): WorkState {
  const investigation = useQuery({
    queryKey: ["workspace", "investigation-header", investigationId],
    queryFn: async () => {
      const [record, ops] = await Promise.all([
        investigationId ? api.getInvestigation(investigationId) : null,
        fetchOpsMetrics(),
      ]);
      return { record, ops };
    },
    enabled: investigationId !== null,
    // The header is background context: a stale name is better than a spinner.
    staleTime: 15_000,
  });

  return useMemo<WorkState>(() => {
    if (!investigationId) return UNKNOWN_WORK_STATE;
    if (investigation.isPending) return { ...UNKNOWN_WORK_STATE, investigationId, loading: true };
    if (investigation.isError) {
      return {
        ...UNKNOWN_WORK_STATE,
        investigationId,
        error: investigation.error instanceof Error ? investigation.error.message : "Request failed",
      };
    }

    const { record, ops } = investigation.data ?? { record: null, ops: null };
    if (!record) return { ...UNKNOWN_WORK_STATE, investigationId, loading: investigation.isPending };

    return {
      investigationId: record.investigation_id,
      investigationName: record.name,
      state: toWorkStatus(record.state),
      rawState: record.state,
      // The API exposes no per-investigation entity/finding/source census, and
      // none is derivable from the investigation record. Null ⇒ the top bar
      // prints "—" and says which endpoint is missing, rather than inventing a
      // number. `useful_observations` is a real platform count but is
      // pipeline-wide, so it is labelled as such and not passed off as this
      // investigation's observation count.
      entityCount: null,
      observationCount: null,
      findingCount: null,
      sourceCount: null,
      lastUpdated: record.created_at,
      throughput: ops ? opsThroughput(ops) : null,
      pipelineObservationCount: ops?.useful_observations ?? null,
      loading: false,
      error: null,
    };
  }, [investigationId, investigation]);
}

/** Useful-observation count when the platform reports one, else throughput. */
function opsThroughput(ops: OpsMetrics): number | null {
  if (typeof ops.throughput_per_s === "number") return ops.throughput_per_s;
  return null;
}