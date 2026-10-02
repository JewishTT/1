import { useCallback, useMemo } from "react";

import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { EmptyState, Skeleton } from "../ui/Feedback";
import { useWorkspace } from "../workspace/store";
import { OBJECT_COLUMNS, type ColumnDefinition } from "./columns";
import {
  activeFacetIds,
  applyFacets,
  defaultLayout,
  resolveColumns,
  setColumnHidden,
  sortRows,
  type ResolvedColumn,
} from "./filters";
import { rowKey } from "./model";
import { usePersistedGrid } from "./persist";
import { ObjectGrid } from "./ObjectGrid";
import { ObjectRecordView } from "./ObjectRecordView";
import { ObjectToolbar } from "./ObjectToolbar";
import { useObjectRows } from "./useObjectRows";
import { ROW_HEIGHT } from "./virtualization";
import {
  EMPTY_SORT,
  kindsFromSelection,
  rowOfKind,
  type ObjectFacets,
  type ObjectRow,
  type ObjectRowKind,
  type ObjectSort,
} from "./types";
import type { WorkspaceObjectKind } from "../workspace/types";

/**
 * ObjectsWorkspace (T132, §25, §26, FR-108, FR-109, FR-114).
 *
 * §25 asks for ONE table over Entity / Observation / Claim / Finding / Capture
 * with a type filter, not five tables. This is that surface, and it is the
 * composition point for the five modules that already existed and were not
 * reachable:
 *
 *   model.ts        platform rows            → what a row IS
 *   filters.ts      faceting + sorting       → which rows are in the table
 *   columns.tsx     the column registry      → what a column shows
 *   persist.ts      saved layout + views     → how it looked last time
 *   virtualization.ts windowing              → how 2 000 rows stay at 16ms/frame
 *   useObjectRows.ts TanStack Query          → where the rows come from
 *
 * NONE of them is rewritten here. This file supplies the wiring and nothing else,
 * which is why it is short for what it does.
 *
 * §7 / §68, THE SPLIT THIS FILE EXISTS TO KEEP:
 *
 *   Store (client state): the type filter, the free-text query, the selected
 *   object, the destination view, and the time range — all of which must survive
 *   a view switch (§76).
 *   Query (server state): the rows themselves.
 *
 * They meet in the `useMemo` below, read-only. No fetched payload is written into
 * the store, and no action here mutates a server record. That is the whole of
 * §7, and keeping the two apart is why switching to the graph and back does not
 * re-fetch the objects and does not lose the filter.
 *
 * WHAT IS PERSISTED AND WHY THAT IS NOT A STORE CHANGE. Column order, widths and
 * hidden columns have no server-side home, and putting them in the store would
 * make them survive a reload whether or not the analyst wants that. `persist.ts`
 * keys them by `investigation + surface`, so each investigation keeps its own
 * layout and the store is untouched — §76 holds without a second global.
 */
export interface ObjectsWorkspaceProps {
  /** Overrides the store-derived investigation. For tests and previews. */
  investigationId?: string | null;
}

export function ObjectsWorkspace({ investigationId }: ObjectsWorkspaceProps) {
  const storeInvestigationId = useWorkspace((state) => state.investigationId);
  const activeInvestigation = investigationId !== undefined ? investigationId : storeInvestigationId;

  const selection = useWorkspace((state) => state.selection);
  const secondary = useWorkspace((state) => state.secondarySelection);
  const railKinds = useWorkspace((state) => state.railKinds);
  const evidenceQuery = useWorkspace((state) => state.evidenceFilter.query);
  const evidenceFilterSourceIds = useWorkspace((state) => state.evidenceFilter.sourceIds);
  const storeTimeRange = useWorkspace((state) => state.timeRange);
  const toggleRailKind = useWorkspace((state) => state.toggleRailKind);
  const setEvidenceFilter = useWorkspace((state) => state.setEvidenceFilter);
  const setTimeRange = useWorkspace((state) => state.setTimeRange);
  const select = useWorkspace((state) => state.select);
  const toggleSecondary = useWorkspace((state) => state.toggleSecondary);
  const setView = useWorkspace((state) => state.setView);
  const density = useWorkspace((state) => state.density);

  const server = useObjectRows(activeInvestigation);
  const persisted = usePersistedGrid({ surface: "objects", investigationId: activeInvestigation });

  // Facets the store owns (survive §76) and facets it does not (persisted),
  // declared together so `applyFacets` gets one object and the two sources
  // cannot be confused for one another at the call site.
  //
  // Nothing here is local `useState`, and that is the point: §76 says a view
  // switch must not lose the working state, and local state is exactly what a
  // view switch throws away. Every facet here is either in the store (kind,
  // query, source, time range) or in `persist.ts` (sort, status), both of which
  // outlive the mount.
  const sort: ObjectSort = persisted.state.sort;
  const statuses = persisted.state.localFacets.statuses;
  const sourceIds = evidenceFilterSourceIds;

  const kinds: ReadonlyArray<ObjectRowKind> = kindsFromSelection(railKinds);

  const facets = useMemo<ObjectFacets>(
    () => ({
      kinds: [...kinds],
      sourceIds: [...sourceIds],
      statuses: [...statuses],
      timeRange: { from: storeTimeRange.from, to: storeTimeRange.to },
      query: evidenceQuery,
    }),
    [kinds, sourceIds, statuses, storeTimeRange.from, storeTimeRange.to, evidenceQuery],
  );

  const rows = useMemo(() => {
    const filtered = applyFacets(server.rows, facets);
    return sortRows(filtered, sort, OBJECT_COLUMNS);
  }, [server.rows, facets, sort]);

  const columns = useMemo<ResolvedColumn[]>(() => {
    const stored = persisted.state.layout;
    const base =
      stored.order.length > 0 ? stored : defaultLayout(OBJECT_COLUMNS, kinds);
    return resolveColumns(base, OBJECT_COLUMNS, kinds);
  }, [persisted.state.layout, kinds]);

  const selectedId = selection === null ? null : rowKey(selection.kind as ObjectRowKind, selection.id);
  const selectedRow = useMemo<ObjectRow | null>(() => {
    if (selection === null) return null;
    const kind = selection.kind as ObjectRowKind;
    if (!(kind in server.counts)) return null;
    return rowOfKind(rows.find((row) => rowKey(row.kind, row.id) === selectedId) ?? null, kind);
  }, [selection, rows, selectedId, server.counts]);

  const secondaryIds = useMemo(
    () => secondary.map((entry) => rowKey(entry.kind as ObjectRowKind, entry.id)),
    [secondary],
  );

  const onSelect = useCallback(
    (row: ObjectRow) => select({ kind: row.kind, id: row.id, label: row.label }),
    [select],
  );

  const onToggleSecondaryRow = useCallback(
    (row: ObjectRow) => toggleSecondary({ kind: row.kind, id: row.id, label: row.label }),
    [toggleSecondary],
  );

  const onSortChange = useCallback(
    (columnId: string) => {
      const previous = persisted.state.sort;
      const next: ObjectSort =
        previous.columnId === columnId
          ? { columnId, direction: previous.direction === "asc" ? "desc" : "asc" }
          : { columnId, direction: "asc" };
      persisted.update({ sort: next });
    },
    [persisted],
  );

  const onColumnVisibility = useCallback(
    (_hidden: ReadonlyArray<string>, definition: ColumnDefinition, hiddenNow: boolean) => {
      // Seed a COMPLETE layout on the first edit. Writing only `hidden` into the
      // empty persisted shape would persist a layout whose `order` is still `[]`,
      // and `columns` above falls back to the defaults whenever `order` is empty —
      // so the hidden set would be silently discarded and the toggle would appear
      // to do nothing.
      const currentLayout =
        persisted.state.layout.order.length > 0
          ? persisted.state.layout
          : defaultLayout(OBJECT_COLUMNS, kinds);
      const next = setColumnHidden(currentLayout.hidden, definition, hiddenNow);
      persisted.update({ layout: { ...currentLayout, hidden: [...next] } });
    },
    [persisted, kinds],
  );

  const onReset = useCallback(() => {
    persisted.update({ sort: EMPTY_SORT, localFacets: { statuses: [] } });
    setEvidenceFilter({ query: "", sourceIds: [] });
    setTimeRange({ from: null, to: null });
    for (const kind of kinds) toggleRailKind(kind as WorkspaceObjectKind);
  }, [persisted, setEvidenceFilter, setTimeRange, toggleRailKind, kinds]);

  /* ── States (§90, §91, §99) ───────────────────────────────────────── */

  if (activeInvestigation === null) {
    return (
      <div className="ui-obj" data-testid="objects-workspace">
        <EmptyState
          icon="view-objects"
          title="No investigation loaded"
          description="The object table is scoped to one investigation. Every row below the scope line would be tenant-wide, and a tenant-wide object presented as this case's is a claim about the record the platform never made."
          testId="objects-no-investigation"
        />
      </div>
    );
  }

  if (server.loading) {
    return (
      <div className="ui-obj" data-testid="objects-workspace">
        <Skeleton rows={10} label="Loading objects" />
      </div>
    );
  }

  if (server.error !== null) {
    return (
      <div className="ui-obj" data-testid="objects-workspace">
        <div className="ui-inspector-error" role="alert" data-testid="objects-error">
          <p className="ui-pane-title">The objects table did not load</p>
          <p className="ui-body" data-testid="objects-error-message">
            {server.error}
          </p>
          <p className="ui-body">
            Scope: the entity graph and the finding list for investigation{" "}
            <span className="ui-mono">{activeInvestigation}</span>. Nothing was dropped — the records
            are on the server and this table simply could not be read.
          </p>
          <div className="ui-insp-next-list">
            <Button size="sm" onClick={server.refetch} data-testid="objects-error-retry">
              Retry
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const activeFacets = activeFacetIds(facets);

  return (
    <div className="ui-obj" data-testid="objects-workspace">
      <header className="ui-obj-head-bar">
        <div className="ui-obj-head-titles">
          <h2 className="ui-title">Objects</h2>
          <span className="ui-id" data-testid="objects-count">
            {rows.length} of {server.rows.length} · {activeFacets.length} facet(s) active
          </span>
        </div>
        {persisted.restored ? (
          <Badge tone="neutral" role="classification" testId="objects-layout-restored">
            saved layout
          </Badge>
        ) : null}
      </header>

      <ObjectToolbar
        rows={server.rows}
        query={evidenceQuery}
        onQueryChange={(query) => setEvidenceFilter({ query })}
        kinds={kinds}
        onKindsChange={(next) => {
          // The type filter is the store's `railKinds`, so it survives §76. Set
          // membership is derived from the rail rather than mirrored, so the two
          // cannot drift.
          for (const kind of kinds) toggleRailKind(kind);
          for (const kind of next) toggleRailKind(kind);
        }}
        statuses={statuses}
        onStatusesChange={(next) => persisted.update({ localFacets: { statuses: [...next] } })}
        sourceIds={sourceIds}
        onSourceIdsChange={(next) => setEvidenceFilter({ sourceIds: [...next] })}
        columns={columns}
        onColumnVisibilityChange={onColumnVisibility}
        onReset={onReset}
        persistFailed={persisted.persistFailed}
      />

      <div className="ui-obj-body">
        <div className="ui-obj-table">
          <ObjectGrid
            rows={rows}
            columns={columns}
            sort={sort}
            onSortChange={onSortChange}
            selectedId={selectedId}
            onSelect={onSelect}
            secondaryIds={secondaryIds}
            onToggleSecondary={onToggleSecondaryRow}
            rowHeight={ROW_HEIGHT[density]}
            emptyState={
              <EmptyState
                icon="view-objects"
                title={server.rows.length === 0 ? "The platform returned no objects" : "Every object is filtered out"}
                description={
                  server.rows.length === 0
                    ? "The entity graph and the finding list both answered with nothing for this investigation. That is the platform's answer, not a missing table."
                    : `${server.rows.length} objects were loaded and the ${activeFacets.length} active facet(s) hide all of them. Relax a facet, or reset.`
                }
                action={
                  server.rows.length > 0 ? (
                    <Button size="sm" onClick={onReset} data-testid="objects-empty-reset">
                      Reset filters
                    </Button>
                  ) : null
                }
                testId="objects-empty-state"
              />
            }
          />
        </div>

        <aside className="ui-obj-detail" aria-label="Object record" data-testid="objects-detail">
          <ObjectRecordView row={selectedRow} onGoToView={setView} />
        </aside>
      </div>

      {/* §99: which endpoints this surface needed and did not get. The gap is
          the finding, so it is on the surface rather than in a comment. */}
      <footer className="ui-obj-coverage" data-testid="objects-coverage">
        <span className="ui-pane-title">Coverage</span>
        <span className="ui-rail-hint">served: {server.coverage.loaded.join(", ") || "nothing yet"}</span>
        <ul className="ui-obj-missing">
          {server.coverage.missing.map((endpoint) => (
            <li key={endpoint} className="ui-obj-missing-item ui-mono">
              {endpoint}
            </li>
          ))}
        </ul>
      </footer>
    </div>
  );
}