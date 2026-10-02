import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_PANE_WIDTHS, useWorkspace } from "../workspace/store";
import { OPEN_TIME_RANGE } from "../workspace/types";
import { ObjectsWorkspace } from "./ObjectsWorkspace";
import { VIRTUALIZATION_THRESHOLD } from "./ObjectGrid";
import { OVERSCAN } from "./virtualization";

/**
 * The objects surface, end to end through the real components (T132, §25, §26,
 * §13, §99, FR-108, FR-109, FR-114).
 *
 * The point of this file is the SEAMS, because `src/objects/` shipped 2 327
 * lines of model, filters, columns, persistence and windowing with zero
 * components, zero tests and zero imports. Pure functions can be right and the
 * surface can still be wrong; these assertions are about what the composition
 * does — that the store and the Query cache meet read-only, that virtualization
 * is actually connected, and that an absent value reads as absent.
 */

vi.mock("../lib/api", () => ({
  api: {
    specOpsGraph: vi.fn(),
    listFindings: vi.fn(),
  },
}));

// Imported after the mock so the module under test binds the mocked client.
// `vi.mocked` rather than a bare import: the mock factory's `vi.fn()` has no
// `.mockResolvedValue` in its type, and without this the whole file fails
// `tsc` while the runtime behaviour is fine.
const { api } = await import("../lib/api");

const specOpsGraph = vi.mocked(api.specOpsGraph);
const listFindings = vi.mocked(api.listFindings);

/** One entity-projection node in the shape `adaptProjectionNode` expects. */
function projectionNode(index: number) {
  return {
    id: `ENT-${index}`,
    label: `Object ${index}`,
    entity_type: "ENTITY",
    properties: {
      entity_id: `ENT-${index}`,
      label: `Object ${index}`,
      canonical_identity: JSON.stringify({ account: `acct-${index}` }),
      relationships: JSON.stringify([{ type: "candidate_of", target: `ENT-${index + 1}`, status: "OPEN" }]),
      evidence: JSON.stringify([{ evidence_id: `E-${index}`, observation_id: `OBS-${index}`, immutable: true }]),
      timeline: JSON.stringify([
        { observation_id: `OBS-${index}`, uri: `https://example.org/${index}`, immutable: true, observed_at: `2026-03-${String((index % 28) + 1).padStart(2, "0")}T00:00:00Z` },
      ]),
      source_ids: index % 2 === 0 ? "src-a" : "src-b",
      invariant_status: "MATERIALIZED",
      // `properties` is `Record<string, string>` on the wire — an ABSENT value
      // is a key the projection did not send, not a JSON null. Modelling that
      // here is what makes `invariant_continuity: null` in the record view a
      // real "not reported" rather than a test artefact.
      ...(index % 3 === 0 ? { invariant_continuity: "continuous" } : {}),
    },
  };
}

function finding(index: number) {
  return {
    finding_id: `FND-${index}`,
    status: index % 2 === 0 ? "OPEN" : "CONFIRMED",
    why_detected: `finding ${index} fired because the platform said so`,
    structural_evidence: [],
    semantic_evidence: [],
    supporting_graph_region: {},
    supporting_assertions: [],
    observations: [],
    sources: [],
    evidence_resolves: index % 2 === 0,
    tenant_id: "t",
  };
}

function renderObjects(entityCount: number, findingCount: number) {
  specOpsGraph.mockResolvedValue({
    nodes: Array.from({ length: entityCount }, (_, index) => projectionNode(index)),
    edges: [],
  });
  listFindings.mockResolvedValue({
    findings: Array.from({ length: findingCount }, (_, index) => finding(index)),
  });

  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ObjectsWorkspace investigationId="42" />
    </QueryClientProvider>,
  );
}

/**
 * Entities with no timeline and no evidence.
 *
 * The windowing assertions need a row set whose ORDER IS KNOWN. The projection
 * above derives one Observation per entity from its `timeline`, and an Entity's
 * `at` is `invariant_last_seen ?? null` — so under the default descending sort by
 * `observed`, entities (all undated) land last and which row sits at index 500
 * depends on the mix. Dropping the timeline gives one row per entity, all with
 * `at === null`, which `sortRows` puts last-then-stable-by-row-key. Ids are
 * zero-padded because that tiebreak is LEXICOGRAPHIC: `ENT-500` sorts before
 * `ENT-51`, so without padding index 500 is not the row the test means.
 */
function renderEntitiesOnly(count: number) {
  specOpsGraph.mockResolvedValue({
    nodes: Array.from({ length: count }, (_, index) => ({
      id: `ENT-${String(index).padStart(4, "0")}`,
      label: `Object ${index}`,
      entity_type: "ENTITY",
      properties: { entity_id: `ENT-${String(index).padStart(4, "0")}`, label: `Object ${index}` },
    })),
    edges: [],
  });
  listFindings.mockResolvedValue({ findings: [] });

  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ObjectsWorkspace investigationId="42" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  window.localStorage.clear();
  useWorkspace.setState({
    investigationId: "42",
    investigationLabel: null,
    view: "objects",
    selection: null,
    secondarySelection: [],
    evidenceFilter: { query: "", sourceIds: [], hideRejected: false },
    railQuery: "",
    railKinds: [],
    timeRange: OPEN_TIME_RANGE,
    openInspectorSections: {},
    pinnedInspectors: [],
    paneWidths: DEFAULT_PANE_WIDTHS,
    paneVisibility: { rail: true, inspector: true, activity: true },
    density: "standard",
    theme: "dark",
    commandPaletteOpen: false,
    contextMenu: null,
  });
  vi.clearAllMocks();
});

afterEach(() => {
  window.localStorage.clear();
});

async function waitForGrid() {
  await waitFor(() => expect(screen.getByTestId("objects-grid")).toBeInTheDocument());
}

/* ── The surface renders real content, not a placeholder ──────────────── */

describe("§25 — one table over the five kinds, with a type filter", () => {
  it("renders rows built from both served endpoints", async () => {
    renderObjects(4, 2);
    await waitForGrid();

    // 4 entities + 4 observations (one per entity's timeline) + 2 findings.
    expect(screen.getByTestId("objects-count")).toHaveTextContent("10 of 10");
    expect(screen.getByTestId("objects-row-Entity:ENT-0")).toBeInTheDocument();
    expect(screen.getByTestId("objects-row-Finding:FND-0")).toBeInTheDocument();
  });

  it("names the endpoints it needed and did not get", async () => {
    renderObjects(1, 0);
    await waitForGrid();

    // §99 / §116: the gap is the finding, and it says which endpoint would fill
    // it rather than rendering an empty column.
    const coverage = screen.getByTestId("objects-coverage");
    expect(coverage).toHaveTextContent("GET /observations");
    expect(coverage).toHaveTextContent("GET /relations");
    expect(coverage).toHaveTextContent("GET /captures");
  });

  it("offers a kind filter, and it narrows the table through the store's railKinds", async () => {
    renderObjects(4, 3);
    await waitForGrid();

    fireEvent.click(screen.getByTestId("objects-kind-Finding"));
    await waitFor(() => expect(screen.getByTestId("objects-count")).toHaveTextContent("3 of"));

    // The filter is the STORE's field, not local state — that is what makes it
    // survive a view switch (§76).
    expect(useWorkspace.getState().railKinds).toEqual(["Finding"]);
    expect(screen.queryByTestId("objects-row-Entity:ENT-0")).not.toBeInTheDocument();
  });

  it("states an honest empty state when the platform returned nothing at all", async () => {
    renderObjects(0, 0);

    // No grid at all: an empty table with headers and no rows reads as a loading
    // failure, and `computeRowWindow` has nothing to window.
    const empty = await screen.findByTestId("objects-empty-state");
    expect(empty).toHaveTextContent(/returned no objects/i);
    expect(screen.queryByTestId("objects-grid")).not.toBeInTheDocument();
    // Not a "reset filters" button: nothing was filtered, so resetting would be
    // a control that cannot succeed (§69).
    expect(screen.queryByTestId("objects-empty-reset")).not.toBeInTheDocument();
  });

  it("offers the reset when facets, not the server, are hiding everything", async () => {
    renderObjects(4, 0);
    await waitForGrid();

    act(() => useWorkspace.getState().select({ kind: "Entity", id: "ENT-0" }));
    fireEvent.change(screen.getByTestId("objects-query"), { target: { value: "no-such-object" } });
    await waitFor(() => expect(screen.getByTestId("objects-empty-state")).toBeInTheDocument());

    expect(screen.getByTestId("objects-empty-state")).toHaveTextContent(/filtered out/i);
    expect(screen.getByTestId("objects-empty-reset")).toBeInTheDocument();
  });

  it("does not present tenant-wide rows as this investigation's", async () => {
    specOpsGraph.mockResolvedValue({ nodes: [projectionNode(0)], edges: [] });
    listFindings.mockResolvedValue({ findings: [] });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <ObjectsWorkspace investigationId={null} />
      </QueryClientProvider>,
    );

    expect(await screen.findByTestId("objects-no-investigation")).toBeInTheDocument();
    expect(screen.queryByTestId("objects-grid")).not.toBeInTheDocument();
  });

  it("surfaces the error verbatim and offers a retry that cannot lose data", async () => {
    specOpsGraph.mockRejectedValue(new Error("502 from /entities/graph"));
    listFindings.mockResolvedValue({ findings: [] });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <ObjectsWorkspace investigationId="42" />
      </QueryClientProvider>,
    );

    const error = await screen.findByTestId("objects-error");
    expect(error).toHaveTextContent("502 from /entities/graph");
    expect(screen.getByTestId("objects-error-retry")).toBeInTheDocument();
  });
});

/* ── §7 / §68: one global selection, written through the store ───────── */

describe("§7 — clicking a row writes the ONE global selection", () => {
  it("selects the row into the store and shows it in the record pane", async () => {
    renderObjects(3, 0);
    await waitForGrid();

    fireEvent.click(screen.getByTestId("objects-row-Entity:ENT-1"));

    expect(useWorkspace.getState().selection).toMatchObject({ kind: "Entity", id: "ENT-1" });
    // The label is carried so the top bar and rail can show what is selected
    // without a second fetch. It is NOT authoritative — an Entity's label is its
    // canonical identity, which is why it is `acct-1` and not the projection's
    // "Object 1". The inspector always re-reads the record.
    expect(useWorkspace.getState().selection?.label).toBe("acct-1");

    const record = screen.getByTestId("objects-record");
    expect(record).toHaveAttribute("data-kind", "Entity");
    expect(within(record).getByTestId("objects-record-kind")).toHaveTextContent("Entity");
  });

  it("adds a comparison target without making it the primary selection", async () => {
    renderObjects(3, 0);
    await waitForGrid();

    fireEvent.click(screen.getByTestId("objects-row-Entity:ENT-0"));
    fireEvent.click(screen.getByTestId("objects-compare-Entity:ENT-2"));

    expect(useWorkspace.getState().selection?.id).toBe("ENT-0");
    expect(useWorkspace.getState().secondarySelection.map((entry) => entry.id)).toEqual(["ENT-2"]);
    expect(screen.getByTestId("objects-row-Entity:ENT-2")).toHaveAttribute("data-secondary", "true");
  });

  it("moves the selection with the arrow keys, as §12 requires of a table", async () => {
    renderObjects(5, 0);
    await waitForGrid();

    fireEvent.click(screen.getByTestId("objects-row-Entity:ENT-0"));
    fireEvent.keyDown(screen.getByTestId("objects-grid-viewport"), { key: "ArrowDown" });
    expect(useWorkspace.getState().selection?.id).toBe("ENT-1");

    fireEvent.keyDown(screen.getByTestId("objects-grid-viewport"), { key: "ArrowDown" });
    expect(useWorkspace.getState().selection?.id).toBe("ENT-2");

    fireEvent.keyDown(screen.getByTestId("objects-grid-viewport"), { key: "ArrowUp" });
    expect(useWorkspace.getState().selection?.id).toBe("ENT-1");
  });

  it("prompts for a selection instead of rendering an empty record", async () => {
    renderObjects(2, 0);
    await waitForGrid();
    expect(screen.getByTestId("objects-record-empty")).toHaveTextContent(/no object selected/i);
  });
});

/* ── §99: unreported is a value, not an empty cell ───────────────────── */

describe("§99 — an unreported field says so, and never shows a zero", () => {
  it("prints 'not reported' for absent fields and names the missing endpoint", async () => {
    renderObjects(2, 1);
    await waitForGrid();

    fireEvent.click(screen.getByTestId("objects-row-Finding:FND-0"));

    const notes = screen.getByTestId("objects-section-analyst-notes");
    expect(notes).toHaveTextContent("not reported");
    expect(notes).toHaveTextContent("GET /findings/{id}/notes");
  });

  it("shows the platform's raw status beside the §92 projection", async () => {
    renderObjects(0, 2);
    await waitForGrid();

    fireEvent.click(screen.getByTestId("objects-row-Finding:FND-0"));
    const status = screen.getByTestId("objects-section-status");
    // The raw string is what the analyst filters on; the projection is what the
    // dot's colour means. Both, so the mapping stays auditable.
    expect(status).toHaveTextContent("OPEN");
    expect(status).toHaveTextContent(/open/i);
  });
});

/* ── §13 / FR-114: virtualization is actually connected ──────────────── */

describe("§13 — the window is connected, not merely present in the module", () => {
  it(`bounds the rendered rows at every size and windows past ${VIRTUALIZATION_THRESHOLD}`, async () => {
    const { unmount } = renderEntitiesOnly(120);
    await waitForGrid();
    const small = screen.getByTestId("objects-grid");
    expect(small).toHaveAttribute("data-above-threshold", "false");
    expect(small).toHaveAttribute("aria-rowcount", "120");

    // The window is unconditional — there is no branch that renders everything
    // under the threshold — so what the threshold buys is a *bound*, not a
    // different code path. The bound is stated against the geometry the grid
    // actually measured rather than a hard-coded viewport, so the assertion is
    // about the windowing and not about the harness's viewport height.
    const viewport = Number(small.getAttribute("data-viewport-height"));
    const rowHeight = Number(small.getAttribute("data-row-height"));
    expect(viewport).toBeGreaterThan(0);
    expect(rowHeight).toBe(32);
    const visibleRows = Math.max(1, Math.ceil(viewport / rowHeight));
    expect(Number(small.getAttribute("data-rendered"))).toBeLessThanOrEqual(
      visibleRows + 2 * OVERSCAN + 2,
    );
    expect(Number(small.getAttribute("data-rendered"))).toBeLessThan(120);
    unmount();

    renderEntitiesOnly(600);
    await waitForGrid();
    const grid = screen.getByTestId("objects-grid");
    expect(grid).toHaveAttribute("data-above-threshold", "true");
    expect(grid.getAttribute("data-total")).toBe("600");
    expect(Number(grid.getAttribute("data-rendered"))).toBeLessThan(
      Math.max(1, Math.ceil(Number(grid.getAttribute("data-viewport-height")) / 32)) + 2 * OVERSCAN + 2,
    );
  });

  it("shows every row when the whole set fits inside the window", async () => {
    renderEntitiesOnly(8);
    await waitForGrid();
    const grid = screen.getByTestId("objects-grid");
    expect(grid.getAttribute("data-rendered")).toBe(grid.getAttribute("data-total"));
    expect(screen.getByTestId("objects-row-Entity:ENT-0007")).toBeInTheDocument();
  });

  it("keeps the scrollbar honest about how many rows exist", async () => {
    renderEntitiesOnly(600);
    await waitForGrid();

    // The canvas is `totalRows × rowHeight` tall whatever the window renders, so
    // the thumb reflects the row count rather than the DOM size.
    const canvas = document.querySelector(".ui-obj-grid-canvas") as HTMLElement;
    expect(canvas.style.height).toBe(`${600 * 32}px`);
  });

  it("carries the true row count to assistive tech, not the rendered window", async () => {
    renderEntitiesOnly(600);
    await waitForGrid();

    const grid = screen.getByTestId("objects-grid");
    expect(grid).toHaveAttribute("role", "grid");
    expect(grid).toHaveAttribute("aria-rowcount", "600");

    // Row 1 of the window is `aria-rowindex` 1, not 0: the header is not a row
    // of the data grid, and a 0-based index here would understate every row.
    expect(screen.getByTestId("objects-row-Entity:ENT-0000")).toHaveAttribute("aria-rowindex", "1");
  });

  it("marks the spacers as layout so a screen reader sees one grid, not three", async () => {
    renderEntitiesOnly(600);
    await waitForGrid();

    const pads = document.querySelectorAll(".ui-obj-grid-pad");
    expect(pads).toHaveLength(2);
    for (const pad of pads) expect(pad.getAttribute("aria-hidden")).toBe("true");
  });

  it("re-windows on scroll and reveals a row outside the first window", async () => {
    renderEntitiesOnly(600);
    await waitForGrid();

    expect(screen.queryByTestId("objects-row-Entity:ENT-0500")).not.toBeInTheDocument();

    fireEvent.scroll(screen.getByTestId("objects-grid-viewport"), { target: { scrollTop: 500 * 32 } });

    // 8 rows of OVERSCAN above row 500 — the overscan, not luck, is what puts a
    // row on screen before the browser has painted the new position.
    await waitFor(() => expect(screen.getByTestId("objects-grid")).toHaveAttribute("data-window-start", "492"));
    expect(screen.getByTestId("objects-row-Entity:ENT-0500")).toBeInTheDocument();
    expect(screen.queryByTestId("objects-row-Entity:ENT-0000")).not.toBeInTheDocument();
  });

  it("keeps the window inside the row set when the set shrinks under the scroll position", async () => {
    // The regression `computeRowWindow`'s own test pins, seen through the UI: the
    // analyst scrolls deep, then filters. A `start` beyond the row set would
    // render nothing at all with no error anywhere.
    renderEntitiesOnly(600);
    await waitForGrid();

    fireEvent.scroll(screen.getByTestId("objects-grid-viewport"), { target: { scrollTop: 19_000 } });
    fireEvent.change(screen.getByTestId("objects-query"), { target: { value: "ENT-059" } });

    await waitFor(() => expect(screen.getByTestId("objects-grid")).toBeInTheDocument());
    const grid = screen.getByTestId("objects-grid");
    expect(Number(grid.getAttribute("data-window-start"))).toBeLessThanOrEqual(
      Number(grid.getAttribute("data-total")),
    );
    expect(screen.getByTestId("objects-row-Entity:ENT-0590")).toBeInTheDocument();
  });
});

/* ── §26: sorting and column visibility are wired to the persisted state ── */

describe("§26 — sort, columns and saved layout", () => {
  it("sorts by a clicked column header and states the direction to assistive tech", async () => {
    renderEntitiesOnly(6);
    await waitForGrid();

    fireEvent.click(screen.getByTestId("objects-header-id"));
    const header = screen.getByTestId("objects-header-id");
    expect(header).toHaveAttribute("aria-sort", "ascending");

    fireEvent.click(header);
    expect(header).toHaveAttribute("aria-sort", "descending");
  });

  it("hides a column through the column menu and persists the choice", async () => {
    renderEntitiesOnly(3);
    await waitForGrid();

    expect(screen.getByTestId("objects-header-observation.locator")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("objects-column-toggle-observation.locator"));

    await waitFor(() =>
      expect(screen.queryByTestId("objects-header-observation.locator")).not.toBeInTheDocument(),
    );

    const stored = window.localStorage.getItem("cognitive.ui2.objects.v1.42");
    expect(stored, "the layout must survive a reload").toContain("observation.locator");
  });

  it("renders every applicable column when no kind filter is active", async () => {
    // §26: an empty type filter means "all five kinds". Read the other way it
    // resolves to zero columns — a header row with no cells and no error, which
    // looks exactly like an empty result set.
    renderEntitiesOnly(3);
    await waitForGrid();

    const grid = screen.getByTestId("objects-grid");
    const headers = document.querySelectorAll('[role="columnheader"]');
    expect(Number(grid.getAttribute("aria-colcount"))).toBe(headers.length);
    expect(headers.length).toBeGreaterThan(10);
  });

  it("keeps the selection column visible no matter what the layout says", async () => {
    renderObjects(2, 0);
    await waitForGrid();

    // The selection rail is not offered in the menu at all, and the header stays.
    expect(screen.queryByTestId("objects-column-toggle-__select")).not.toBeInTheDocument();
    expect(screen.getByTestId("objects-grid").getAttribute("aria-colcount")).toBe(
      String(document.querySelectorAll('[role="columnheader"]').length),
    );
  });
});

/* ── §7: server state never enters the store ─────────────────────────── */

describe("§7 — Query owns the rows, the store owns the lens", () => {
  it("never writes a fetched payload into the workspace store", async () => {
    renderObjects(5, 2);
    await waitForGrid();
    fireEvent.click(screen.getByTestId("objects-row-Entity:ENT-0"));

    const state = useWorkspace.getState();
    // The store holds a selection, filters and layout. It holds no rows.
    expect(Object.values(state).some((value) => Array.isArray(value) && value.length > 40)).toBe(false);
    expect(JSON.stringify(state)).not.toContain("acct-1");
  });

  it("keys the queries by investigation, so a second case cannot read the first one's rows", async () => {
    const { unmount } = renderObjects(2, 0);
    await waitForGrid();
    expect(specOpsGraph).toHaveBeenCalled();
    const firstCalls = specOpsGraph.mock.calls.length;
    unmount();

    specOpsGraph.mockResolvedValue({ nodes: [projectionNode(99)], edges: [] });
    listFindings.mockResolvedValue({ findings: [] });
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <ObjectsWorkspace investigationId="43" />
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByTestId("objects-row-Entity:ENT-99")).toBeInTheDocument());
    expect(specOpsGraph.mock.calls.length).toBeGreaterThan(firstCalls);
    expect(screen.queryByTestId("objects-row-Entity:ENT-0")).not.toBeInTheDocument();
  });
});