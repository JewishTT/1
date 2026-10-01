import type { Density } from "../workspace/types";

/**
 * Row virtualization (§26, §64).
 *
 * §64 forbids a new runtime dependency, so the windowing is here: an
 * index range derived from `scrollTop`, `viewportHeight` and a fixed row height,
 * plus the two spacer heights that make the scrollbar honest about how many rows
 * exist. No virtual-list library, no IntersectionObserver, no measurement pass.
 *
 * WHY FIXED HEIGHTS. The grid reads `--ui-row-h` per density (§66), so every row
 * is exactly the same height and `index × rowHeight` IS the row's offset. That
 * turns windowing into arithmetic and makes it testable without a layout engine —
 * which is the only reason it can be asserted in jsdom at all.
 *
 * OVERSCAN. A window sized to the viewport exactly produces blank rows at the
 * edges during a fast scroll, because the scroll handler runs after the pixels
 * have already moved. `OVERSCA` rows are rendered above and below the viewport
 * so there is always content under the pointer. 8 is enough for a 120ms scroll
 * frame at any sane row height and costs 16 extra rows out of a ~44-row window.
 */

export const OVERSCAN = 8;

/**
 * Row height per density, in px.
 *
 * These mirror `--ui-row-h` in `styles/tokens/density.css` (22px compact,
 * 30px comfortable). They are numbers rather than a `getComputedStyle` read
 * because windowing needs them in the scroll handler, synchronously, before the
 * browser has painted — a style read there is a forced reflow per scroll event.
 *
 * The pairing is asserted in `objects.test.ts`: if a token changes and these do
 * not, that test fails rather than the grid quietly mis-measuring itself.
 */
export const ROW_HEIGHT: Readonly<Record<Density, number>> = {
  compact: 22,
  comfortable: 30,
};

/**
 * Fallback viewport height when the element has not been measured yet.
 *
 * jsdom reports `clientHeight` as 0 for every element, and a zero viewport would
 * make the window empty — an empty table in a test that should show rows. 480px
 * is roughly one compact screenful, so the default renders a full window and the
 * measurement takes over in a browser on the first scroll.
 */
export const FALLBACK_VIEWPORT_HEIGHT = 480;

export interface RowWindowInput {
  /** Total rows in the filtered, sorted set. */
  totalRows: number;
  /** Vertical scroll offset of the grid viewport, in px. */
  scrollTop: number;
  /** Measured height of the scroll viewport, in px. */
  viewportHeight: number;
  rowHeight: number;
  overscan?: number;
}

export interface RowWindow {
  /** First rendered index, inclusive. */
  start: number;
  /** Last rendered index, EXCLUSIVE. */
  end: number;
  /** Rows actually rendered. `end - start`. */
  rendered: number;
  /** Rows the viewport can physically show, before overscan. */
  visibleRows: number;
  /** Spacer height above the first rendered row, in px. */
  padTop: number;
  /** Spacer height below the last rendered row, in px. */
  padBottom: number;
  /** Full scroll height, in px. The scrollbar's real size. */
  totalHeight: number;
}

/**
 * The rendered row range for a scroll position.
 *
 * INVARIANTS, all of them load-bearing and all asserted in `objects.test.ts`:
 *
 *   0 ≤ start ≤ end ≤ totalRows        the window is a sub-range, always
 *   start ≤ firstVisible               no gap above the viewport
 *   end   ≥ lastVisible + 1            no gap below it
 *   padTop + rendered×rowHeight + padBottom == totalHeight
 *   rendered ≤ visibleRows + 2×overscan + 2
 *
 * A degenerate input (zero rows, a zero row height, a negative scroll, a NaN
 * viewport) returns an EMPTY window rather than a window that indexes outside the
 * array. Rendering row 4 of a zero-row table is how a virtualization bug turns
 * into a crash.
 */
export function computeRowWindow(input: RowWindowInput): RowWindow {
  const rowHeight = Number.isFinite(input.rowHeight) && input.rowHeight > 0 ? input.rowHeight : ROW_HEIGHT.compact;
  const totalRows = Number.isFinite(input.totalRows) ? Math.max(0, Math.floor(input.totalRows)) : 0;
  const overscan = Math.max(0, Math.floor(input.overscan ?? OVERSCAN));

  const totalHeight = totalRows * rowHeight;

  if (totalRows === 0) {
    return {
      start: 0,
      end: 0,
      rendered: 0,
      visibleRows: 0,
      padTop: 0,
      padBottom: 0,
      totalHeight: 0,
    };
  }

  const viewport = Number.isFinite(input.viewportHeight) && input.viewportHeight > 0 ? input.viewportHeight : FALLBACK_VIEWPORT_HEIGHT;
  const scrollTop = Number.isFinite(input.scrollTop) ? Math.max(0, input.scrollTop) : 0;

  const firstVisible = Math.floor(scrollTop / rowHeight);
  const visibleRows = Math.max(1, Math.ceil(viewport / rowHeight));

  // Clamp to the scrollable range: a scrollTop past the end (which happens when
  // the row set shrinks under a scroll position) must not produce start > total.
  const lastVisible = Math.min(totalRows - 1, Math.floor((scrollTop + viewport) / rowHeight));

  const start = Math.max(0, firstVisible - overscan);
  const end = Math.min(totalRows, lastVisible + 1 + overscan);

  return {
    start,
    end,
    rendered: end - start,
    visibleRows,
    padTop: start * rowHeight,
    padBottom: Math.max(0, (totalRows - end) * rowHeight),
    totalHeight,
  };
}

/** The pixel offset of a row, for absolutely positioning the window. */
export function rowOffset(index: number, rowHeight: number): number {
  return index * rowHeight;
}

/**
 * Scroll offset that brings `index` into view, or `null` when it already is.
 *
 * Returning null rather than the unchanged offset matters for the keyboard path:
 * `scrollTop` is a controlled input to the window computation, so writing the
 * current value back on every arrow key would fight the user's own scrolling.
 */
export function scrollOffsetToReveal(
  index: number,
  scrollTop: number,
  viewportHeight: number,
  rowHeight: number,
): number | null {
  if (rowHeight <= 0) return null;
  const top = index * rowHeight;
  const bottom = top + rowHeight;
  if (top < scrollTop) return Math.max(0, top);
  if (bottom > scrollTop + viewportHeight) return Math.max(0, bottom - viewportHeight);
  return null;
}

/** The largest scroll offset for a row set — where "jump to the end" lands. */
export function maxScrollOffset(totalRows: number, viewportHeight: number, rowHeight: number): number {
  return Math.max(0, totalRows * rowHeight - viewportHeight);
}

/**
 * The rendered-row budget, stated once so the report and the tests can quote the
 * same number. Compact over a 480px fallback viewport:
 *   visible = ceil(480 / 22) = 22 rows
 *   window = 22 + 2×8 + up to 1 = 39 rows
 * Comfortable over the same viewport:
 *   visible = ceil(480 / 30) = 16 rows
 *   window = 16 + 2×8 + up to 1 = 33 rows
 */
export const WINDOW_BUDGET = {
  compact: { visibleRows: Math.ceil(FALLBACK_VIEWPORT_HEIGHT / ROW_HEIGHT.compact), overscan: OVERSCAN },
  comfortable: {
    visibleRows: Math.ceil(FALLBACK_VIEWPORT_HEIGHT / ROW_HEIGHT.comfortable),
    overscan: OVERSCAN,
  },
} as const;
