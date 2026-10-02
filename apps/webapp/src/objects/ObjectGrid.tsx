import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { IconButton } from "../ui/Button";
import { Tooltip } from "../ui/Overlay";
import { SELECT_COLUMN_KEY, type ColumnDefinition } from "./columns";
import type { ResolvedColumn } from "./filters";
import { rowKey } from "./model";
import { FALLBACK_VIEWPORT_HEIGHT, ROW_HEIGHT, computeRowWindow, scrollOffsetToReveal } from "./virtualization";
import type { ObjectRow, ObjectSort } from "./types";

/**
 * ObjectGrid — the virtualised objects table (T132, §13, §26, FR-109, FR-114).
 *
 * WHY THIS IS NOT `ui/DataTable`, STATED PLAINLY.
 *
 * `DataTable` renders every row it is given. §13 requires virtualisation above
 * 500 rows, and this surface is handed the whole entity projection plus the
 * finding list — routinely thousands of rows. Rendering those eagerly is the
 * defect, not the feature. So this is a different component with a different
 * job, not a second name for the same one (§11 is about not duplicating a
 * component, and duplicating `DataTable` with a window inside it would be exactly
 * that). What it borrows is the semantics: same global selection model (§7),
 * same mono convention, same `--ui-row-h` density token.
 *
 * WHY ARIA GRID AND NOT A `<table>`.
 *
 * A windowed table is the one case where `role="grid"` is the correct answer
 * rather than a fallback: a `<table>` claims a complete set of rows, and a
 * windowed one does not have one. `aria-rowcount` states the true total and
 * `aria-rowindex` states each rendered row's real position, which is the only
 * way a screen reader can tell row 4 of 1 800 from row 4 of 12. The spacers
 * carry `aria-hidden`, because they are layout, not data.
 *
 * §68 re-render discipline: the grid subscribes to `selection` and
 * `secondarySelection` through narrow selectors and reads each row's own
 * booleans, so selecting one row of 2 000 re-renders that row and not the set.
 *
 * THE WINDOW IS ARITHMETIC, NOT MEASUREMENT.
 *
 * `--ui-row-h` is fixed per density, so `index × rowHeight` IS a row's offset
 * and `computeRowWindow` is pure (see `virtualization.ts`). Nothing here reads
 * layout inside the scroll handler, which is why a 2 000-row table does not
 * force a reflow per scroll event (§13).
 */

/**
 * §13: "virtualized tables and lists beyond 500 rows".
 *
 * A floor the surface must clear, not a switch. The window runs at every row
 * count — see `ObjectGrid` — so this constant exists to let the DOM say which
 * side of the floor it is on (`data-above-threshold`) and to let a test assert
 * that 500+ rows stay bounded.
 */
export const VIRTUALIZATION_THRESHOLD = 500;

export interface ObjectGridProps {
  rows: ReadonlyArray<ObjectRow>;
  columns: ReadonlyArray<ResolvedColumn>;
  sort: ObjectSort;
  onSortChange: (columnId: string) => void;
  /** Primary selection — the one global model (§7). */
  selectedId: string | null;
  onSelect: (row: ObjectRow) => void;
  /** Comparison targets, rendered with the muted secondary marker. */
  secondaryIds: ReadonlyArray<string>;
  onToggleSecondary: (row: ObjectRow) => void;
  /** Rendered instead of the grid when `rows` is empty. Never a bare "no data". */
  emptyState: ReactNode;
  /** px per row for the current density. Overridable so a test can pin it. */
  rowHeight?: number;
}

export function ObjectGrid({
  rows,
  columns,
  sort,
  onSortChange,
  selectedId,
  onSelect,
  secondaryIds,
  onToggleSecondary,
  emptyState,
  rowHeight: rowHeightOverride,
}: ObjectGridProps) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(FALLBACK_VIEWPORT_HEIGHT);

  // The density token is the source; the override exists so a test can assert the
  // window without depending on which density the store happens to hold.
  const densityRowHeight = rowHeightOverride ?? ROW_HEIGHT.standard;

  const visible = useMemo(() => columns.filter((column) => column.visible), [columns]);

  const window = useMemo(
    () =>
      computeRowWindow({
        totalRows: rows.length,
        scrollTop,
        viewportHeight,
        rowHeight: densityRowHeight,
      }),
    [rows.length, scrollTop, viewportHeight, densityRowHeight],
  );

  // One measurement, not one per scroll event. `clientHeight` is 0 under jsdom,
  // which is why `computeRowWindow` substitutes `FALLBACK_VIEWPORT_HEIGHT`
  // rather than dividing by it.
  useEffect(() => {
    const element = viewportRef.current;
    if (element === null) return;
    const measure = () => {
      const next = element.clientHeight;
      if (next > 0) setViewportHeight(next);
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const onScroll = useCallback((event: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(event.currentTarget.scrollTop);
  }, []);

  /**
   * Reveal a row and select it, in one gesture.
   *
   * `scrollOffsetToReveal` returns `null` when the row is already visible, and
   * that null is load-bearing: `scrollTop` is a controlled input to the window
   * computation, so writing the current value back on every arrow key would
   * fight the analyst's own scrolling.
   */
  const reveal = useCallback(
    (index: number) => {
      const offset = scrollOffsetToReveal(index, scrollTop, viewportHeight, densityRowHeight);
      if (offset !== null && viewportRef.current !== null) viewportRef.current.scrollTop = offset;
    },
    [scrollTop, viewportHeight, densityRowHeight],
  );

  const moveFocus = useCallback(
    (delta: -1 | 1) => {
      if (rows.length === 0 || selectedId === null) return;
      const index = rows.findIndex((row) => rowKey(row.kind, row.id) === selectedId);
      if (index === -1) return;
      const next = rows[index + delta];
      if (next === undefined) return;
      reveal(index + delta);
      onSelect(next);
    },
    [rows, selectedId, reveal, onSelect],
  );

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        moveFocus(1);
        return;
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        moveFocus(-1);
      }
    },
    [moveFocus],
  );

  if (rows.length === 0) return <>{emptyState}</>;

  // The window runs at every size, not only above the threshold. There is no
  // branch to take here and no reason to have one: a window that covers the
  // viewport renders every row when there are fewer rows than the viewport is
  // tall, so small tables are unaffected, and the single code path is the one
  // that is exercised by the small cases.
  //
  // `VIRTUALIZATION_THRESHOLD` is therefore a REPORT, not a switch:
  // `data-above-threshold` states whether §13's floor is in play, so the assertion
  // that 500+ rows stay bounded is readable from the DOM instead of inferred.
  const aboveThreshold = rows.length > VIRTUALIZATION_THRESHOLD;
  const slice = rows.slice(window.start, window.end);
  const totalWidth = visible.reduce((sum, column) => sum + column.width, 0);

  return (
    <div
      className="ui-obj-grid"
      role="grid"
      aria-rowcount={rows.length}
      aria-colcount={visible.length}
      data-testid="objects-grid"
      data-above-threshold={aboveThreshold ? "true" : "false"}
      data-total={rows.length}
      data-rendered={slice.length}
      data-window-start={window.start}
      /* The geometry the window was computed from, stated in the DOM. Without it
         a window assertion has to hard-code the environment's viewport height —
         and that number changes the moment jsdom gains a layout stub, so the
         test would be asserting the harness rather than the grid. */
      data-viewport-height={viewportHeight}
      data-row-height={densityRowHeight}
      onKeyDown={onKeyDown}
    >
      <div className="ui-obj-grid-head" role="row" style={{ minWidth: totalWidth }}>
        {visible.map((column) => (
          <GridHeader
            key={column.definition.key}
            column={column.definition}
            width={column.width}
            sort={sort}
            onSortChange={onSortChange}
          />
        ))}
      </div>

      <div
        className="ui-obj-grid-viewport ui-scroll"
        ref={viewportRef}
        onScroll={onScroll}
        data-testid="objects-grid-viewport"
        tabIndex={0}
        aria-label="Objects table. Arrow keys move the selection between rows."
      >
        {/* The honest scrollbar: total height is the FULL row count, so the thumb
            reflects how many rows exist rather than how many are rendered. */}
        <div className="ui-obj-grid-canvas" style={{ height: window.totalHeight, minWidth: totalWidth }}>
          <div className="ui-obj-grid-pad" aria-hidden="true" style={{ height: window.padTop }} />
          {slice.map((row, offset) => {
            const index = window.start + offset;
            return (
              <GridRow
                key={rowKey(row.kind, row.id)}
                row={row}
                columns={visible}
                index={index}
                selected={selectedId === rowKey(row.kind, row.id)}
                secondary={secondaryIds.includes(rowKey(row.kind, row.id))}
                onSelect={onSelect}
                onToggleSecondary={onToggleSecondary}
              />
            );
          })}
          <div className="ui-obj-grid-pad" aria-hidden="true" style={{ height: window.padBottom }} />
        </div>
      </div>
    </div>
  );
}

/* ── Header ───────────────────────────────────────────────────────────── */

function GridHeader({
  column,
  width,
  sort,
  onSortChange,
}: {
  column: ColumnDefinition;
  width: number;
  sort: ObjectSort;
  onSortChange: (columnId: string) => void;
}) {
  if (column.key === SELECT_COLUMN_KEY) {
    return <span role="columnheader" className="ui-obj-cell" style={{ width }} aria-label="Select" />;
  }

  const sortable = column.sortValue !== undefined;
  const active = sort.columnId === column.key;

  if (!sortable) {
    return (
      <span role="columnheader" className="ui-obj-cell ui-obj-head" style={{ width }} data-align={column.align ?? "start"}>
        {column.header}
      </span>
    );
  }

  return (
    <Tooltip content={`Sort by ${column.header}`}>
      <button
        type="button"
        role="columnheader"
        className="ui-obj-cell ui-obj-head ui-obj-head-sortable"
        style={{ width }}
        data-align={column.align ?? "start"}
        data-active={active}
        aria-sort={active ? (sort.direction === "asc" ? "ascending" : "descending") : "none"}
        onClick={() => onSortChange(column.key)}
        data-testid={`objects-header-${column.key}`}
      >
        {column.header}
        <span className="ui-obj-sort" aria-hidden="true">
          {active ? (sort.direction === "asc" ? "↑" : "↓") : ""}
        </span>
      </button>
    </Tooltip>
  );
}

/* ── Row ──────────────────────────────────────────────────────────────── */

function GridRow({
  row,
  columns,
  index,
  selected,
  secondary,
  onSelect,
  onToggleSecondary,
}: {
  row: ObjectRow;
  columns: ReadonlyArray<ResolvedColumn>;
  index: number;
  selected: boolean;
  secondary: boolean;
  onSelect: (row: ObjectRow) => void;
  onToggleSecondary: (row: ObjectRow) => void;
}) {
  const id = rowKey(row.kind, row.id);

  return (
    <div
      role="row"
      className="ui-obj-grid-row"
      aria-rowindex={index + 1}
      aria-selected={selected}
      data-selected={selected}
      data-secondary={secondary}
      data-testid={`objects-row-${id}`}
      onClick={() => onSelect(row)}
    >
      {columns.map((column) => (
        <span
          key={column.definition.key}
          role="gridcell"
          className="ui-obj-cell"
          style={{ width: column.width }}
          data-align={column.definition.align ?? "start"}
          data-mono={column.definition.mono ? "true" : undefined}
        >
          {column.definition.key === SELECT_COLUMN_KEY ? (
            <Tooltip content={secondary ? "Remove from comparison" : "Add to comparison"}>
              <IconButton
                icon="copy"
                size="sm"
                label={`${secondary ? "Remove" : "Add"} ${row.id} ${secondary ? "from" : "to"} comparison`}
                aria-pressed={secondary}
                // `stopPropagation` matters: without it the row's own click
                // handler fires too and the row becomes BOTH primary and
                // secondary, which is a selection no view can interpret.
                onClick={(event) => {
                  event.stopPropagation();
                  onToggleSecondary(row);
                }}
                data-testid={`objects-compare-${id}`}
              />
            </Tooltip>
          ) : (
            column.definition.render(row)
          )}
        </span>
      ))}
    </div>
  );
}