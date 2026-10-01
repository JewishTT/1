import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "../../lib/api";
import { useWorkspace } from "../store";
import { buildInspectorModel } from "./model";
import { EMPTY_INSPECTOR_DATA, type InspectorData } from "./types";

/**
 * Server state for the inspector (§7: Zustand and TanStack Query must not mix).
 *
 * The selection comes from Zustand; the records come from Query. This hook is
 * the only place the two meet, and they meet read-only: nothing here writes a
 * fetched payload into the workspace store.
 *
 * Queries are keyed on the selection id, so selecting a different object
 * fetches that object and nothing else (§68). A query is enabled only when the
 * selection names a kind that has a record endpoint — no speculative requests
 * for objects nobody selected.
 *
 * Only Entity, Finding and Investigation have record endpoints wired at stage 2.
 * Observation, Capture, Claim, Source, AcquisitionTask and AcquisitionRun have
 * no fetcher yet; the model reports them as `unavailable`, which the panel shows
 * as "not fetched" rather than as an object with no properties (§99).
 */

export interface InspectorQueryResult {
  data: InspectorData;
  /** True while an enabled query is in flight. */
  loading: boolean;
  /** First error message, or null. Shown verbatim; never swallowed. */
  error: string | null;
}

export function useInspectorData(): InspectorQueryResult {
  const kind = useWorkspace((state) => state.selection?.kind ?? null);
  const id = useWorkspace((state) => state.selection?.id ?? null);

  const wantsEntity = kind === "Entity" && id !== null;
  const wantsFinding = kind === "Finding" && id !== null;
  const wantsInvestigation = kind === "Investigation" && id !== null;

  const entity = useQuery({
    queryKey: ["workspace", "entity", id],
    queryFn: () => api.getEntity(id ?? ""),
    enabled: wantsEntity,
  });

  const finding = useQuery({
    queryKey: ["workspace", "finding", id],
    queryFn: () => api.getFinding(id ?? ""),
    enabled: wantsFinding,
  });

  const investigation = useQuery({
    queryKey: ["workspace", "investigation", id],
    queryFn: () => api.getInvestigation(id ?? ""),
    enabled: wantsInvestigation,
  });

  const loading = entity.isPending || finding.isPending || investigation.isPending;
  const firstError = [entity.error, finding.error, investigation.error].find(Boolean);

  const data: InspectorData = useMemo(
    () => ({
      ...EMPTY_INSPECTOR_DATA,
      entity: wantsEntity ? (entity.data ?? null) : null,
      finding: wantsFinding ? (finding.data ?? null) : null,
      // The finding record carries no correlations of its own; they come from
      // the separate /findings/{id}/correlations shape, wired in stage 4. Until
      // then this is an honest empty list rather than a derived guess.
      findingCorrelations: [],
      investigation: wantsInvestigation ? (investigation.data ?? null) : null,
    }),
    [wantsEntity, entity.data, wantsFinding, finding.data, wantsInvestigation, investigation.data],
  );

  return {
    data,
    loading: wantsEntity || wantsFinding || wantsInvestigation ? loading : false,
    error: firstError instanceof Error ? firstError.message : null,
  };
}

/**
 * The inspector model for the current selection: a pure derivation of
 * (selection, server data). Memoised so a re-render from an unrelated slice
 * does not rebuild the section tree (§68).
 */
export function useInspectorModel() {
  const selection = useWorkspace((state) => state.selection);
  const { data, loading, error } = useInspectorData();
  return useMemo(
    () => ({ model: buildInspectorModel(selection, data), loading, error }),
    [selection, data, loading, error],
  );
}