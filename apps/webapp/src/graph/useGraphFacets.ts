import { useCallback, useMemo, useState } from "react";

import { useWorkspace } from "../workspace/store";
import type { TimeRange, WorkspaceObjectKind } from "../workspace/types";
import {
  EMPTY_GRAPH_FACETS,
  activeFacetIds,
  toggleFacetValue,
  type AdmissionState,
  type EvidenceState,
  type GraphFacetId,
  type GraphFacets,
} from "./filters";
import type { EdgeFamily } from "./types";

/**
 * Facet state for the canvas (§22, §76).
 *
 * FOUR OF THE EIGHT FACETS ARE IN THE WORKSPACE STORE, and those four are read
 * and written through it, so they survive a view switch for free:
 *
 *   object type        → `railKinds`      (toggleRailKind)
 *   source             → `evidenceFilter.sourceIds`
 *   free text          → `evidenceFilter.query`
 *   temporal range     → `timeRange`
 *
 * The other four have no home there:
 *
 *   relation           → local
 *   admission          → local
 *   evidence presence  → local
 *   investigation scope→ local
 *
 * They are reported as required integration. Until then they are held here, and
 * `controlled` exists so the integrating pass can lift all eight into the store
 * with one prop rather than by rewriting the filter drawer.
 */

/**
 * The graph kinds the store can hold, because a `WorkspaceObjectKind` covers
 * them. `Hypothesis` cannot: it is a projection of a correlation candidate, not
 * a platform object kind, and putting it in `railKinds` would claim the store
 * has an object type the platform does not have (§99). It is held locally
 * alongside the others.
 */
type StoreBackedGraphKind = "Entity" | "Observation" | "Claim" | "Finding";

const STORE_BACKED_KINDS: ReadonlyArray<WorkspaceObjectKind> = [
  "Entity",
  "Observation",
  "Claim",
  "Finding",
];

function isStoreBackedKind(kind: WorkspaceObjectKind): boolean {
  return STORE_BACKED_KINDS.includes(kind);
}

/**
 * Narrow to the store-backed subset. The single cast is sound: membership in
 * `STORE_BACKED_KINDS` is exactly the four literals above.
 */
function toStoreKind(kind: WorkspaceObjectKind): StoreBackedGraphKind | null {
  return isStoreBackedKind(kind) ? (kind as StoreBackedGraphKind) : null;
}

/** The parts of `GraphFacets` this hook owns locally. */
export type LocalFacets = Pick<GraphFacets, "relations" | "admissions" | "evidenceStates">;

const EMPTY_LOCAL: LocalFacets = { relations: [], admissions: [], evidenceStates: [] };

export interface GraphFacetsControls {
  facets: GraphFacets;
  /** Which facets are narrowing, for the summary and the reset affordance. */
  active: GraphFacetId[];
  /** Toggle one value inside one facet. Store-backed where the store has a home. */
  toggle: (facet: GraphFacetId, value: string) => void;
  setQuery: (query: string) => void;
  setTimeRange: (range: TimeRange) => void;
  setInvestigationScope: (investigationIds: string[]) => void;
  reset: () => void;
}

export interface UseGraphFacetsOptions {
  /**
   * Values supplied by an outer owner. Anything present here wins over the
   * store and over local state — this is the seam the integrating pass uses to
   * put the remaining four facets in the store.
   */
  controlled?: Partial<GraphFacets>;
  onControlledChange?: (patch: Partial<GraphFacets>) => void;
}

export function useGraphFacets(options: UseGraphFacetsOptions = {}): GraphFacetsControls {
  const { controlled, onControlledChange } = options;

  const railKinds = useWorkspace((state) => state.railKinds);
  const toggleRailKind = useWorkspace((state) => state.toggleRailKind);
  const sourceIds = useWorkspace((state) => state.evidenceFilter.sourceIds);
  const query = useWorkspace((state) => state.evidenceFilter.query);
  const timeRange = useWorkspace((state) => state.timeRange);
  const setTimeRange = useWorkspace((state) => state.setTimeRange);
  const setEvidenceFilter = useWorkspace((state) => state.setEvidenceFilter);
  const resetEvidenceFilter = useWorkspace((state) => state.resetEvidenceFilter);

  const [local, setLocal] = useState<LocalFacets>(EMPTY_LOCAL);
  const [localKinds, setLocalKinds] = useState<GraphFacets["kinds"]>([]);
  const [localInvestigationScope, setLocalInvestigationScope] = useState<string[]>([]);

  const storeKinds = useMemo<GraphFacets["kinds"]>(
    () =>
      railKinds
        .map(toStoreKind)
        .filter((kind): kind is StoreBackedGraphKind => kind !== null),
    [railKinds],
  );

  // A hypothesis has no `WorkspaceObjectKind`, so it lives in the local kind
  // set and is merged with the store-backed kinds rather than smuggled in.
  const kinds = useMemo(() => {
    const merged = [...storeKinds];
    for (const kind of localKinds) if (!merged.includes(kind)) merged.push(kind);
    return merged;
  }, [storeKinds, localKinds]);

  const facets = useMemo<GraphFacets>(
    () => ({
      kinds: controlled?.kinds ?? kinds,
      relations: controlled?.relations ?? local.relations,
      sourceIds: controlled?.sourceIds ?? sourceIds,
      evidenceStates: controlled?.evidenceStates ?? local.evidenceStates,
      admissions: controlled?.admissions ?? local.admissions,
      timeRange: controlled?.timeRange ?? timeRange,
      investigationIds: controlled?.investigationIds ?? localInvestigationScope,
      query: controlled?.query ?? query,
    }),
    [controlled, kinds, local, sourceIds, timeRange, localInvestigationScope, query],
  );

  const setInvestigationScope = useCallback(
    (ids: string[]) => {
      if (onControlledChange) {
        onControlledChange({ investigationIds: ids });
        return;
      }
      setLocalInvestigationScope(ids);
    },
    [onControlledChange],
  );

  const toggle = useCallback<GraphFacetsControls["toggle"]>(
    (facet, value) => {
      switch (facet) {
        case "kinds": {
          const kind = toStoreKind(value as WorkspaceObjectKind);
          if (kind === null) {
            // Hypothesis is not a `WorkspaceObjectKind`, so it lives in the local
            // kind set. Smuggling it into `railKinds` would claim the store has
            // an object type the platform does not have (§99).
            setLocalKinds((prev) => toggleFacetValue(prev, value as GraphFacets["kinds"][number]));
            return;
          }
          if (onControlledChange) {
            onControlledChange({ kinds: toggleFacetValue(kinds, kind) });
            return;
          }
          toggleRailKind(kind);
          return;
        }
        case "relations":
          if (onControlledChange) {
            onControlledChange({ relations: toggleFacetValue(local.relations, value as EdgeFamily) });
            return;
          }
          setLocal((prev) => ({ ...prev, relations: toggleFacetValue(prev.relations, value as EdgeFamily) }));
          return;
        case "admissions":
          if (onControlledChange) {
            onControlledChange({ admissions: toggleFacetValue(local.admissions, value as AdmissionState) });
            return;
          }
          setLocal((prev) => ({ ...prev, admissions: toggleFacetValue(prev.admissions, value as AdmissionState) }));
          return;
        case "evidenceStates":
          if (onControlledChange) {
            onControlledChange({
              evidenceStates: toggleFacetValue(local.evidenceStates, value as EvidenceState),
            });
            return;
          }
          setLocal((prev) => ({
            ...prev,
            evidenceStates: toggleFacetValue(prev.evidenceStates, value as EvidenceState),
          }));
          return;
        case "sourceIds":
          if (onControlledChange) {
            onControlledChange({ sourceIds: toggleFacetValue(sourceIds, value) });
            return;
          }
          setEvidenceFilter({ sourceIds: toggleFacetValue(sourceIds, value) });
          return;
        case "investigationIds":
          setInvestigationScope(
            toggleFacetValue(controlled?.investigationIds ?? localInvestigationScope, value),
          );
          return;
        case "timeRange":
        case "query":
          // Not value facets: `setQuery` and `setTimeRange` are their own
          // affordances, so the drawer renders them as fields, not checkboxes.
          return;
      }
    },
    [
      controlled,
      kinds,
      local,
      localInvestigationScope,
      onControlledChange,
      setEvidenceFilter,
      setInvestigationScope,
      sourceIds,
      toggleRailKind,
    ],
  );

  const setQuery = useCallback(
    (next: string) => {
      if (onControlledChange) {
        onControlledChange({ query: next });
        return;
      }
      setEvidenceFilter({ query: next });
    },
    [onControlledChange, setEvidenceFilter],
  );

  const setRange = useCallback(
    (range: TimeRange) => {
      if (onControlledChange) {
        onControlledChange({ timeRange: range });
        return;
      }
      setTimeRange(range);
    },
    [onControlledChange, setTimeRange],
  );

  const reset = useCallback(() => {
    if (onControlledChange) {
      onControlledChange(EMPTY_GRAPH_FACETS);
    }
    setLocal(EMPTY_LOCAL);
    setLocalKinds([]);
    setLocalInvestigationScope([]);
    resetEvidenceFilter();
    for (const kind of railKinds) if (isStoreBackedKind(kind)) toggleRailKind(kind);
    setTimeRange(EMPTY_GRAPH_FACETS.timeRange);
  }, [onControlledChange, resetEvidenceFilter, railKinds, toggleRailKind, setTimeRange]);

  const active = useMemo(() => activeFacetIds(facets), [facets]);

  return { facets, active, toggle, setQuery, setTimeRange: setRange, setInvestigationScope, reset };
}

/**
 * Facets that the store cannot hold today. The filter drawer disables nothing,
 * but the integration report names these so the gap is a known list rather
 * than a behaviour someone has to rediscover.
 */
export const FACETS_WITHOUT_STORE_HOME: ReadonlyArray<GraphFacetId> = [
  "relations",
  "admissions",
  "evidenceStates",
  "investigationIds",
];

export const FACETS_WITH_STORE_HOME: ReadonlyArray<GraphFacetId> = [
  "kinds",
  "sourceIds",
  "query",
  "timeRange",
];

/** Does the store currently hold an investigation scope? Used to seed the facet. */
export function investigationScopeFrom(investigationId: string | null): string[] {
  return investigationId === null ? [] : [investigationId];
}