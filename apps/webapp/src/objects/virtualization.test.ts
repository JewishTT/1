import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { DENSITIES } from "../workspace/types";
import {
  FALLBACK_VIEWPORT_HEIGHT,
  OVERSCAN,
  ROW_HEIGHT,
  WINDOW_BUDGET,
  computeRowWindow,
  maxScrollOffset,
  rowOffset,
  scrollOffsetToReveal,
} from "./virtualization";

/**
 * The windowing arithmetic (§13, §26, FR-114).
 *
 * This file is the reason `virtualization.ts` is written as pure functions over
 * numbers. jsdom has no layout engine, so anything that measured an element
 * would be untestable here; anything derived from `scrollTop`, a viewport height
 * and a row height is testable to the row. That is not a testing convenience —
 * it is the same reason the module takes row heights as numbers instead of
 * reading `--ui-row-h` in the scroll handler: a style read per scroll event is a
 * forced reflow per scroll event, which is the 16ms budget spent on bookkeeping.
 */

/** The §4.2 table, quoted here independently of `density.css` on purpose. */
const SPEC_ROW_HEIGHT: Readonly<Record<string, number>> = {
  compact: 26,
  standard: 32,
  comfortable: 40,
};

function window(overrides: Partial<Parameters<typeof computeRowWindow>[0]>) {
  return computeRowWindow({
    totalRows: 1000,
    scrollTop: 0,
    viewportHeight: 480,
    rowHeight: ROW_HEIGHT.standard,
    ...overrides,
  });
}

/**
 * The shipped density stylesheet.
 *
 * Read from disk rather than imported. Vite resolves a CSS import to a stylesheet
 * side effect, and `?raw` on a `.css` file yields an empty string — so neither
 * gives the text. `import.meta.url` is not a `file:` URL under the jsdom
 * environment either, so the path is resolved from the working directory, which
 * Vitest sets to the Vite root. Walking up rather than assuming one level keeps
 * the test working if the runner is invoked from a subdirectory.
 */
function readShippedDensityCss(): string {
  let dir = process.cwd();
  for (let depth = 0; depth < 6; depth += 1) {
    const candidate = path.join(dir, "src", "styles", "tokens", "density.css");
    if (existsSync(candidate)) return readFileSync(candidate, "utf8");
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  throw new Error("density.css not found above " + process.cwd());
}

describe("§4.2 — the row heights are the spec's, in the spec's order", () => {
  it("declares exactly the three modes, compact → standard → comfortable", () => {
    expect([...DENSITIES]).toEqual(["compact", "standard", "comfortable"]);
  });

  it("matches the row height ui-upgrade §4.2 fixes for every mode", () => {
    for (const density of DENSITIES) {
      expect(ROW_HEIGHT[density], density).toBe(SPEC_ROW_HEIGHT[density]);
    }
  });

  it("mirrors the `--ui-row-h` token in density.css rather than a third copy", () => {
    // Read the shipped stylesheet, not a copy of it: a token re-tuned without
    // this number would otherwise mis-measure every row in the window and no test
    // would notice.
    const densityCss = readShippedDensityCss();
    for (const density of DENSITIES) {
      const block = densityCss.split(`[data-density="${density}"]`)[1]?.split("}")[0] ?? "";
      const declared = block.match(/--ui-row-h:\s*(\d+)px/)?.[1];
      expect(Number(declared), `--ui-row-h for ${density}`).toBe(ROW_HEIGHT[density]);
    }
  });

  it("has a :root block carrying the default mode, so first paint is not unstyled", () => {
    // Without this the cascade resolves to nothing until the shell writes the
    // attribute, and the density the analyst sees on load is not the one the
    // store holds.
    const densityCss = readShippedDensityCss();
    const rootBlock = densityCss.split(":root,")[1]?.split("}")[0] ?? "";
    expect(rootBlock, ":root must declare --ui-row-h").toContain("--ui-row-h");
    expect(densityCss.indexOf(':root,')).toBeLessThan(densityCss.indexOf('[data-density="comfortable"]'));
  });

  it("orders the modes by row height, so 'more comfortable' always means 'taller'", () => {
    const heights = DENSITIES.map((density) => ROW_HEIGHT[density]);
    expect([...heights].sort((a, b) => a - b)).toEqual(heights);
  });
});

describe("computeRowWindow — the invariants, all of them load-bearing", () => {
  it("renders a sub-range of the rows", () => {
    for (const scrollTop of [0, 500, 12_000, 31_999]) {
      const result = window({ scrollTop });
      expect(result.start).toBeGreaterThanOrEqual(0);
      expect(result.end).toBeLessThanOrEqual(1000);
      expect(result.start).toBeLessThanOrEqual(result.end);
    }
  });

  it("never leaves a gap above or below the viewport", () => {
    for (const scrollTop of [0, 137, 4_096, 20_001]) {
      const result = window({ scrollTop, totalRows: 1000 });
      const firstVisible = Math.floor(scrollTop / ROW_HEIGHT.standard);
      const lastVisible = Math.min(999, Math.floor((scrollTop + 480) / ROW_HEIGHT.standard));
      expect(result.start, `start at ${scrollTop}`).toBeLessThanOrEqual(firstVisible);
      expect(result.end, `end at ${scrollTop}`).toBeGreaterThanOrEqual(lastVisible + 1);
    }
  });

  it("keeps the spacers honest: pad + rows + pad is the full scroll height", () => {
    for (const scrollTop of [0, 512, 9_000, 31_000]) {
      const result = window({ scrollTop, totalRows: 1000 });
      expect(result.padTop + result.rendered * ROW_HEIGHT.standard + result.padBottom).toBe(
        result.totalHeight,
      );
      expect(result.totalHeight).toBe(1000 * ROW_HEIGHT.standard);
    }
  });

  it("renders no more than the viewport plus the overscan, at any scroll position", () => {
    for (const scrollTop of [0, 33, 1_024, 8_192, 31_500]) {
      const result = window({ scrollTop });
      expect(result.rendered).toBeLessThanOrEqual(result.visibleRows + 2 * OVERSCAN + 2);
    }
  });

  it("renders a bounded number of rows for 5 000 records — the §9/§13 case", () => {
    const result = window({ totalRows: 5000, scrollTop: 40_000 });
    expect(result.rendered).toBeLessThan(60);
    expect(result.totalHeight).toBe(5000 * ROW_HEIGHT.standard);
  });
});

describe("computeRowWindow — degenerate input returns an empty window, never an index", () => {
  it("returns nothing for zero rows", () => {
    expect(window({ totalRows: 0 })).toEqual({
      start: 0,
      end: 0,
      rendered: 0,
      visibleRows: 0,
      padTop: 0,
      padBottom: 0,
      totalHeight: 0,
    });
  });

  it("clamps a negative scroll rather than producing a negative start", () => {
    expect(window({ scrollTop: -400 }).start).toBe(0);
  });

  it("survives a scroll position past the end after the row set shrinks", () => {
    // The case that turns a virtualization bug into a crash: the analyst
    // filters, the set shrinks under the scrollbar, and the handler is handed a
    // scrollTop that no longer exists.
    const result = window({ totalRows: 5, scrollTop: 90_000 });
    expect(result.start).toBeLessThanOrEqual(5);
    expect(result.end).toBeLessThanOrEqual(5);
    expect(result.rendered).toBeLessThanOrEqual(5);
  });

  it("substitutes the fallback viewport for a zero or NaN measurement", () => {
    for (const viewportHeight of [0, Number.NaN, -10]) {
      const result = window({ viewportHeight });
      expect(result.visibleRows).toBe(Math.ceil(FALLBACK_VIEWPORT_HEIGHT / ROW_HEIGHT.standard));
    }
  });

  it("falls back to a real row height rather than dividing by zero", () => {
    const result = window({ rowHeight: 0 });
    expect(Number.isFinite(result.totalHeight)).toBe(true);
    expect(result.totalHeight).toBe(1000 * ROW_HEIGHT.compact);
  });

  it("returns an empty window for a non-finite row count", () => {
    expect(window({ totalRows: Number.NaN }).rendered).toBe(0);
  });
});

describe("scrollOffsetToReveal — null when the row is already visible", () => {
  const H = ROW_HEIGHT.standard;

  it("returns null for a row inside the viewport", () => {
    expect(scrollOffsetToReveal(5, 0, 480, H)).toBeNull();
  });

  it("scrolls down to put a row below the viewport at its bottom edge", () => {
    const index = 40;
    const offset = scrollOffsetToReveal(index, 0, 480, H);
    expect(offset).toBe(index * H + H - 480);
  });

  it("scrolls up to put a row above the viewport at its top edge", () => {
    const offset = scrollOffsetToReveal(2, 4_000, 480, H);
    expect(offset).toBe(2 * H);
  });

  it("never returns a negative offset", () => {
    expect(scrollOffsetToReveal(0, 0, 480, H)).toBeNull();
    expect(scrollOffsetToReveal(0, 1_000, 480, H)).toBe(0);
  });

  it("returns null rather than dividing by a zero row height", () => {
    expect(scrollOffsetToReveal(3, 0, 480, 0)).toBeNull();
  });
});

describe("The scroll extent and the row offset agree with the window", () => {
  it("maxScrollOffset is the last scroll position that still shows a row", () => {
    const total = 1000;
    const max = maxScrollOffset(total, 480, ROW_HEIGHT.standard);
    const atEnd = window({ totalRows: total, scrollTop: max, viewportHeight: 480 });
    expect(atEnd.end).toBe(total);
    expect(atEnd.start).toBeLessThanOrEqual(total - 1);
  });

  it("maxScrollOffset is zero when everything fits", () => {
    expect(maxScrollOffset(3, 480, ROW_HEIGHT.standard)).toBe(0);
  });

  it("rowOffset is index × height, which is what makes windowing arithmetic", () => {
    for (const index of [0, 1, 137, 4_999]) {
      expect(rowOffset(index, ROW_HEIGHT.comfortable)).toBe(index * ROW_HEIGHT.comfortable);
    }
  });
});

describe("WINDOW_BUDGET — the documented numbers, restated from the live constants", () => {
  it("covers every density, so adding a mode cannot leave the report stale", () => {
    expect(Object.keys(WINDOW_BUDGET).sort()).toEqual([...DENSITIES].sort());
  });

  it("quotes the same visible-row count the window actually reports", () => {
    for (const density of DENSITIES) {
      const result = window({ rowHeight: ROW_HEIGHT[density] });
      expect(result.visibleRows, density).toBe(WINDOW_BUDGET[density].visibleRows);
      expect(WINDOW_BUDGET[density].overscan, density).toBe(OVERSCAN);
    }
  });
});