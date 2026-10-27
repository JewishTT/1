import type { ReactNode } from "react";

/**
 * DataTable shell (§60).
 *
 * Deliberately a shell, not a data grid: it owns the *semantics* an analyst
 * needs from a table in this workbench — a real caption, semantic column
 * headers, row selection, monospace identifiers and keyboard row navigation.
 * Sorting, virtualisation and column resizing belong to the views that know
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
  if (rows.length === 0 && emptyState) {
    return <>{emptyState}</>;
  }

  const activeId =
    selectedId !== null && rows.some((row) => rowId(row) === selectedId)
      ? selectedId
      : rows.length > 0
        ? rowId(rows[0]!)
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
            >
              {column.header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
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