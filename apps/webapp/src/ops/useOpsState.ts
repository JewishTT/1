import { useCallback, useMemo } from "react";
import { useQueries } from "@tanstack/react-query";

import { api } from "../lib/api";
import { withRuntimeHints, type ConnectorWire } from "./fabric";
import { buildOpsState, quarantineRows } from "./model";
import type { PoolWire, QuarantineWire } from "./model";
import type { ConnectorEcho, OpsServerState, QuarantineRow } from "./types";

/**
 * Server state for the operations and quarantine surfaces (§46, §47, §48).
 *
 * TanStack Query owns all of it (§7). Nothing fetched here is written into the
 * workspace store, and no action here mutates a server record without going
 * through the API client — the store holds what the operator is *looking at*,
 * never what the platform *reports*.
 *
 * §68: query keys are constant per surface, so an ops refresh does not
 * invalidate the graph's data and vice versa. Each surface subscribes with a
 * selector to the fields it renders, so a metrics poll does not re-render the
 * quarantine table.
 *
 * WHAT IS AVAILABLE, precisely — this is the honest inventory the surfaces
 * render from:
 *
 *   GET /metrics          throughput, useful obs, yield, duplicate ratio, browser
 *                         utilisation, lags, queues, storage growth, cost
 *   GET /metrics/pools    per-pool healthy/active/capacity/failures
 *   GET /dlq              record_id, reason, topic, partition, preserved, fingerprint
 *   GET /connectors       connector_id, name, status, version, policy, source_types
 *
 * WHAT IS NOT, and is named on the surfaces rather than defaulted:
 *
 *   per-runtime readiness · run history · success rates · quarantine timestamps
 *   · quarantine source/runtime/object · attempt counts · Redpanda consumer-group
 *     lag (the served `lags_s` are stage-hop lags, not broker offsets)
 */

export interface QuarantineServerState {
  readonly rows: ReadonlyArray<QuarantineRow>;
  readonly loading: boolean;
  readonly error: string | null;
  readonly refetch: () => void;
  /** Records as served, before the table's degradation marking. */
  readonly servedCount: number;
  readonly loaded: ReadonlyArray<string>;
  readonly missing: ReadonlyArray<string>;
  /** True when `/dlq` answered with an empty list — distinct from never answering. */
  readonly answered: boolean;
}

export interface CatalogServerState {
  /** The tenant's registered connectors, each carrying its name-derived runtime hint. */
  readonly connectors: ReadonlyArray<ConnectorEcho>;
  readonly loading: boolean;
  readonly error: string | null;
  readonly refetch: () => void;
  readonly loaded: ReadonlyArray<string>;
  readonly missing: ReadonlyArray<string>;
  readonly answered: boolean;
}

export function useOpsState(enabled: boolean = true): OpsServerState {
  const results = useQueries({
    queries: [
      {
        queryKey: ["ops", "metrics"],
        queryFn: () => api.getOpsMetrics(),
        enabled,
        staleTime: 10_000,
        refetchInterval: 15_000,
      },
      {
        queryKey: ["ops", "pools"],
        queryFn: () => api.getWorkerPools(),
        enabled,
        staleTime: 10_000,
        refetchInterval: 15_000,
      },
    ],
  });

  const [metricsQuery, poolsQuery] = results;
  const loading = enabled && (metricsQuery.isPending || poolsQuery.isPending);

  // Both endpoints back one view, so one retry must re-run both. A retry that
  // re-ran half the dashboard would be worse than no retry at all (§91).
  const refetch = useCallback(() => {
    void metricsQuery.refetch();
    void poolsQuery.refetch();
  }, [metricsQuery, poolsQuery]);

  return useMemo<OpsServerState>(() => {
    const firstError = [metricsQuery.error, poolsQuery.error].find(Boolean);
    return buildOpsState({
      metrics: (metricsQuery.data ?? null) as Record<string, unknown> | null,
      pools: (poolsQuery.data?.pools ?? null) as Record<string, PoolWire> | null,
      loading,
      error: firstError instanceof Error ? firstError.message : null,
      refetch,
    });
  }, [metricsQuery.data, poolsQuery.data, loading, refetch]);
}

export function useQuarantineState(topic?: string): QuarantineServerState {
  const results = useQueries({
    queries: [
      {
        // The topic is part of the key, so filtering does not overwrite the
        // unfiltered result — switching back is instant and does not refetch.
        queryKey: ["ops", "quarantine", topic ?? ""],
        queryFn: () => api.listQuarantine(topic),
        enabled: true,
        staleTime: 10_000,
      },
    ],
  });

  const [query] = results;
  const answered = query.data !== undefined;

  const refetch = useCallback(() => {
    void query.refetch();
  }, [query]);

  const rows = useMemo<QuarantineRow[]>(
    () => quarantineRows(((query.data?.records ?? []) as unknown) as QuarantineWire[]),
    [query.data],
  );

  return {
    rows,
    loading: query.isPending,
    error: query.error instanceof Error ? query.error.message : null,
    refetch,
    servedCount: query.data?.records.length ?? 0,
    loaded: answered ? ["/dlq"] : [],
    missing: [
      "GET /dlq (add `recorded_at`, `source_id`, `producer`, `subject_id`, `attempts`)",
      "GET /dlq/stats (count, oldest age, and the reason distribution, so the surface does not have to sum the whole list)",
    ],
    answered,
  };
}

export function useCatalogState(enabled: boolean = true): CatalogServerState {
  const results = useQueries({
    queries: [
      {
        queryKey: ["ops", "connectors"],
        queryFn: () => api.listConnectors(),
        enabled,
        staleTime: 30_000,
      },
    ],
  });

  const [query] = results;
  const refetch = useCallback(() => {
    void query.refetch();
  }, [query]);

  const connectors = useMemo(
    () => withRuntimeHints(((query.data?.connectors ?? []) as unknown) as ConnectorWire[]),
    [query.data],
  );

  return {
    connectors,
    loading: query.isPending,
    error: query.error instanceof Error ? query.error.message : null,
    refetch,
    loaded: query.data !== undefined ? ["/connectors"] : [],
    missing: [
      "GET /acquisition/runtimes (runtime_ref, execution_class, capabilities, readiness)",
      "GET /acquisition/runtimes/{runtime_ref}/health (per-runtime health with its checks dict)",
      "GET /acquisition/runs?runtime_ref=… (last run and success rate)",
      "GET /sources (the Source registry: yield, cost, quality)",
    ],
    answered: query.data !== undefined,
  };
}