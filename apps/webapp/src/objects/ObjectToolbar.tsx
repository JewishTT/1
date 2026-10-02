import { useMemo } from "react";

import { Icon } from "../ui/Icon";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";
import { Input, Select } from "../ui/Input";
import { Popover } from "../ui/Overlay";
import { hideableColumns, type ColumnDefinition } from "./columns";
import {
  activeFacetIds,
  allKinds,
  presentFacetOptions,
  setColumnHidden,
  sourceIdsIn,
  type FacetOptions,
  type ResolvedColumn,
} from "./filters";
import { OBJECT_ROW_KINDS, type ObjectRow, type ObjectRowKind } from "./types";

/**
 * ObjectToolbar (T132, §26).
 *
 * The §26 control surface in one place: free text, the type filter, the facets
 * that are present in the data, column visibility, and the reset that undoes all
 * of it.
 *
 * TWO RULES THAT SHAPE THIS COMPONENT.
 *
 *   FACET OPTIONS COME FROM THE ROWS. `presentFacetOptions` derives the status
 *   and source lists from what the server actually returned. Offering a status
 *   that never appears is §69's dead end wearing a filter's clothes: the only
 *   result of choosing it is an empty table, and the analyst cannot tell a broken
 *   query from a wrong one. Counts come from the same pass, so the number beside
 *   each kind is a fact about the current result set rather than a total that
 *   changes under the filter.
 *
 *   EVERY FILTER HAS A VISIBLE WAY OUT. `Reset` is always rendered — not only when
 *   something is active — because a control that appears and disappears is a
 *   control whose absence has to be interpreted. It reports how many facets are
 *   narrowing, which is the answer to "why is my table smaller than it was".
 */

export interface ObjectToolbarProps {
  /** The rows currently in play, for facet options and counts. */
  rows: ReadonlyArray<ObjectRow>;
  query: string;
  onQueryChange: (query: string) => void;
  kinds: ReadonlyArray<ObjectRowKind>;
  onKindsChange: (kinds: ReadonlyArray<ObjectRowKind>) => void;
  statuses: ReadonlyArray<string>;
  onStatusesChange: (statuses: ReadonlyArray<string>) => void;
  sourceIds: ReadonlyArray<string>;
  onSourceIdsChange: (sourceIds: ReadonlyArray<string>) => void;
  columns: ReadonlyArray<ResolvedColumn>;
  onColumnVisibilityChange: (hidden: ReadonlyArray<string>, definition: ColumnDefinition, hiddenNow: boolean) => void;
  onReset: () => void;
  /** True when storage refused the last layout write (§26 persistence). */
  persistFailed?: boolean;
}

function toggle<T extends string>(current: ReadonlyArray<T>, value: T): T[] {
  return current.includes(value) ? current.filter((entry) => entry !== value) : [...current, value];
}

export function ObjectToolbar({
  rows,
  query,
  onQueryChange,
  kinds,
  onKindsChange,
  statuses,
  onStatusesChange,
  sourceIds,
  onSourceIdsChange,
  columns,
  onColumnVisibilityChange,
  onReset,
  persistFailed = false,
}: ObjectToolbarProps) {
  const options: FacetOptions = useMemo(() => presentFacetOptions(rows), [rows]);
  const availableSources = useMemo(() => sourceIdsIn(rows), [rows]);
  const hideable = useMemo(
    () => columns.filter((column) => hideableColumns().some((entry) => entry.key === column.definition.key)),
    [columns],
  );

  return (
    <div className="ui-obj-toolbar" role="toolbar" aria-label="Object table controls" data-testid="objects-toolbar">
      <Input
        label="Filter objects"
        mono
        value={query}
        placeholder="identifier, label, uri, digest"
        onChange={(event) => onQueryChange(event.target.value)}
        adornment={<Icon name="search" size={12} />}
        data-testid="objects-query"
      />

      <div className="ui-obj-kind-group" role="group" aria-label="Object kinds">
        {allKinds().map((kind) => {
          const active = kinds.includes(kind);
          const count = options.kindCounts[kind];
          return (
            <Button
              key={kind}
              size="sm"
              variant={active ? "primary" : "default"}
              aria-pressed={active}
              onClick={() => onKindsChange(toggle(kinds, kind))}
              data-testid={`objects-kind-${kind}`}
            >
              <span className="ui-obj-kind-label">{kind}</span>
              <span className="ui-obj-kind-count">{count}</span>
            </Button>
          );
        })}
      </div>

      {statuses.length > 0 ? (
        <Select
          label="Status"
          value={statuses[0]}
          onValueChange={(value) => onStatusesChange([value])}
          options={[
            { value: "", label: `all statuses (${options.statuses.length})` },
            ...options.statuses.map((status) => ({ value: status, label: status })),
          ]}
          data-testid="objects-status"
        />
      ) : null}

      {availableSources.length > 0 ? (
        <Popover
          label="Sources"
          testId="objects-sources-popover"
          trigger={
            <Button size="sm" iconAfter="chevron-down" data-testid="objects-sources">
              {sourceIds.length === 0 ? "sources" : `${sourceIds.length} source(s)`}
            </Button>
          }
        >
          <div className="ui-menu" role="group" aria-label="Source filter">
            {availableSources.map((id) => (
              <label key={id} className="ui-menu-check">
                <input
                  type="checkbox"
                  checked={sourceIds.includes(id)}
                  onChange={() => onSourceIdsChange(toggle(sourceIds, id))}
                  data-testid={`objects-source-${id}`}
                />
                <span className="ui-mono">{id}</span>
              </label>
            ))}
          </div>
        </Popover>
      ) : null}

      <Popover
        label="Columns"
        testId="objects-columns-popover"
        trigger={
          <Button size="sm" iconAfter="chevron-down" data-testid="objects-columns">
            columns
          </Button>
        }
      >
        <div className="ui-menu" role="group" aria-label="Column visibility">
          {hideable.map((column) => (
            <label key={column.definition.key} className="ui-menu-check">
              <input
                type="checkbox"
                checked={column.visible}
                onChange={(event) =>
                  onColumnVisibilityChange([], column.definition, !event.target.checked)
                }
                data-testid={`objects-column-toggle-${column.definition.key}`}
              />
              <span>{column.definition.header}</span>
            </label>
          ))}
        </div>
      </Popover>

      <Button
        size="sm"
        variant="ghost"
        onClick={onReset}
        data-testid="objects-reset"
        disabled={activeFacetIds({
          kinds: [...kinds],
          sourceIds: [...sourceIds],
          statuses: [...statuses],
          timeRange: { from: null, to: null },
          query,
        }).length === 0}
      >
        Reset
      </Button>

      {persistFailed ? (
        // §91: a failed write is disclosed, not swallowed. The layout still works
        // for this session; it simply will not be there next time.
        <Badge tone="gold" role="classification" testId="objects-persist-failed">
          layout not saved
        </Badge>
      ) : null}
    </div>
  );
}

/** The kinds the toolbar renders, in canvas order. Re-exported for tests. */
export const TOOLBAR_KINDS = OBJECT_ROW_KINDS;

/** Re-exported so a caller can hide a column without importing `filters`. */
export { setColumnHidden };