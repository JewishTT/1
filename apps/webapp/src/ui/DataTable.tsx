import type { ReactNode } from "react";

/**
 * DataTable shell (§60).
 *
 * Deliberately a shell, not a data grid: it owns the *semantics* an analyst
 * needs from a table in this workbench — column headers with sort state,
 * row selection wired to the global selection model, a mono column for
 * identifiers, and keyboard row navigation — and takes cell content as
 * children. Sorting, virtualisation and column resizing belong to the views
 * that know their data (stages 3–8); adding them here would mean guessing.
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
  /** Value used for sorting. Omit for a column that never sorts. */
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
  if (rows.length === 0 && emptyState) {
    return <>{emptyState}</>;
  }

  return (
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
              tabIndex={onRowSelect ? 0 : undefined}
              onClick={onRowSelect ? () => onRowSelect(id) : undefined}
              onKeyDown={
                onRowSelect
                  ? (event) => {
                      // Rows are focusable when selectable, so Enter/Space must
                      // activate them or keyboard users cannot reach the object.
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onRowSelect(id);
                      }
                    }
                  : undefined
              }
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
  );
}