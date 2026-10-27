import { useMemo, useState, type ReactNode } from "react";

import { Icon } from "./Icon";

/**
 * DataTable shell (§60).
 *
 * Deliberately a shell, not a data grid: it owns the *semantics* an analyst
 * needs from a table in this workbench — a real caption, semantic and sortable
 * column headers, row selection, monospace identifiers and keyboard row
 * navigation. Virtualisation and column resizing remain with views that know
 * their data (stages 3–8); this shell does not pretend to implement them.
 *
 * Callers: the activity layer's event table, and the object/evidence tables in
 * stages 4 and 5.
 */

export interface DataTableColumn<T> {
  /** Stable column id. Used as the sort key and the column header id. */
  key: string;
  header: string;
  /** Right-align numeric columns; mono for anything copyable. */
  align?: "start" | "end";
  mono?: boolean;
  /** Extract a comparable string/number to enable the shared sort behavior. */
  sortValue?: (row: T) => string | number;
  width?: string;
  render: (row: T) => ReactNode;
}

export interface DataTableProps<T> {
  caption: string;
  columns: ReadonlyArray<DataTableColumn<T>>;
  rows: ReadonlyArray<T>;
  rowId: (row: T) => string;
  /** The row currently held by the global selection model (§7). */
  selectedId?: string | null;
  onRowSelect?: (id: string) => void;
  /** Secondary (comparison) ids, rendered with the muted secondary marker. */
  secondaryIds?: ReadonlyArray<string>;
  emptyState?: ReactNode;
  testId?: string;
}

export function DataTable<T>({
  caption,
  columns,
  rows,
  rowId,
  selectedId = null,
  onRowSelect,
  secondaryIds = [],
  emptyState,
  testId,
}: DataTableProps<T>) {
  const [sort, setSort] = useState<{ key: string; direction: "ascending" | "descending" } | null>(null);

  const sortedRows = useMemo(() => {
    if (!sort) return rows;
    const column = columns.find((candidate) => candidate.key === sort.key);
    if (!column?.sortValue) return rows;

    const direction = sort.direction === "ascending" ? 1 : -1;
    return [...rows].sort((left, right) => {
      const a = column.sortValue!(left);
      const b = column.sortValue!(right);
      const comparison =
        typeof a === "number" && typeof b === "number"
          ? a - b
          : String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" });
      return comparison * direction;
    });
  }, [columns, rows, sort]);

  if (rows.length === 0 && emptyState) {
    return <>{emptyState}</>;
  }

  const activeId =
    selectedId !== null && rows.some((row) => rowId(row) === selectedId)
      ? selectedId
      : sortedRows.length > 0
        ? rowId(sortedRows[0]!)
        : null;

  return (
    <div className="ui-table-scroll" role="region" aria-label={`${caption} table`} tabIndex={0} data-testid={testId != null ? `${testId}-scroll` : undefined}>
    <table className="ui-table" data-testid={testId}>
      <caption className="ui-sr-only">{caption}</caption>
      <thead>
        <tr>
          {columns.map((column) => (
            <th
              key={column.key}
              scope="col"
              style={column.width ? { width: column.width } : undefined}
              data-align={column.align ?? "start"}
              aria-sort={sort?.key === column.key ? sort.direction : undefined}
            >
              {column.sortValue ? (
                <button
                  type="button"
                  className="ui-table-sort"
                  data-direction={sort?.key === column.key ? sort.direction : "none"}
                  aria-label={`Sort by ${column.header}`}
                  onClick={() =>
                    setSort((current) => ({
                      key: column.key,
                      direction:
                        current?.key === column.key && current.direction === "ascending"
                          ? "descending"
                          : "ascending",
                    }))
                  }
                >
                  <span>{column.header}</span>
                  <Icon name="chevron-down" size={12} />
                </button>
              ) : column.header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {sortedRows.map((row) => {
          const id = rowId(row);
          const selected = selectedId === id;
          const secondary = secondaryIds.includes(id);
          return (
            <tr
              key={id}
              data-selected={selected}
              data-secondary={secondary}
              aria-selected={onRowSelect ? selected : undefined}
              tabIndex={onRowSelect ? (activeId === id ? 0 : -1) : undefined}
              onClick={onRowSelect ? () => onRowSelect(id) : undefined}
              onKeyDown={
                onRowSelect
                  ? (event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onRowSelect(id);
                        return;
                      }

                      const current = event.currentTarget;
                      const rowGroup = current.parentElement;
                      let target: HTMLTableRowElement | null = null;
                      if (event.key === "ArrowDown") target = current.nextElementSibling as HTMLTableRowElement | null;
                      else if (event.key === "ArrowUp") target = current.previousElementSibling as HTMLTableRowElement | null;
                      else if (event.key === "Home") target = rowGroup?.firstElementChild as HTMLTableRowElement | null;
                      else if (event.key === "End") target = rowGroup?.lastElementChild as HTMLTableRowElement | null;

                      if (target?.dataset.rowId) {
                        event.preventDefault();
                        onRowSelect(target.dataset.rowId);
                        target.focus();
                      }
                    }
                  : undefined
              }
              data-row-id={id}
              data-testid={`row-${id}`}
            >
              {columns.map((column) => (
                <td key={column.key} data-align={column.align ?? "start"} data-mono={column.mono ? "true" : undefined}>
                  {column.render(row)}
                </td>
              ))}
            </tr>
          );
        })}
      </tbody>
    </table>
    </div>
  );
}