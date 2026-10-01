import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InvestigationWorkspaceRoute } from "./Workbench";
import { DEFAULT_PANE_WIDTHS, useWorkspace } from "./workspace/store";
import { OPEN_TIME_RANGE } from "./workspace/types";

/**
 * §68: selecting an object must not re-render the whole workspace.
 *
 * Measured without a profiler, and without instrumenting production code: a
 * `MutationObserver` watches the real DOM subtree of each pane. React only
 * touches the DOM when a component re-renders, so a zero-mutation count on the
 * canvas while the inspector mutates is direct evidence that the canvas did not
 * re-render.
 */

function stubFetch(): void {
  globalThis.fetch = (() => new Promise(() => {})) as unknown as typeof fetch;
}

function renderShell() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/investigations/42"]}>
        <Routes>
          <Route path="/investigations/:id" element={<InvestigationWorkspaceRoute />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/**
 * Counts DOM mutations inside `element`.
 *
 * `MutationObserver` delivers its records in a microtask, so the count is read
 * through an async `total()` rather than a synchronous one — reading it inside
 * the same act() that caused the change would always report zero, including
 * for panes that really did change.
 */
function watch(element: Element): { total: () => Promise<number>; stop: () => void } {
  let mutations = 0;
  const observer = new MutationObserver((records) => {
    mutations += records.length;
  });
  observer.observe(element, {
    subtree: true,
    childList: true,
    attributes: true,
    characterData: true,
  });
  return {
    total: async () => {
      await Promise.resolve();
      return mutations;
    },
    stop: () => observer.disconnect(),
  };
}

beforeEach(async () => {
  stubFetch();
  await act(async () => {
    cleanup();
    useWorkspace.setState({
      investigationId: "42",
      investigationLabel: null,
      view: "overview",
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
      density: "compact",
      theme: "dark",
      commandPaletteOpen: false,
      contextMenu: null,
    });
  });
});

afterEach(() => {
  cleanup();
});

describe("§68 — selection re-renders the inspector, not the workspace", () => {
  it("does not touch the canvas DOM when the selection changes", async () => {
    renderShell();
    const canvas = screen.getByTestId("canvas-overview");
    // Watch the inspector's *pane*, not the inspector element: with no selection
    // it renders the empty state and with a selection it renders the object
    // panel, so React replaces the <aside> itself. The pane is the stable node.
    const inspectorPane = screen.getByTestId("pane-inspector");

    const canvasWatch = watch(canvas);
    const inspectorWatch = watch(inspectorPane);

    act(() => useWorkspace.getState().select({ kind: "Entity", id: "ENT-182" }));

    // The canvas is untouched: the selection is not its business (§7 is a
    // global model, but a view only subscribes to what it renders).
    expect(await canvasWatch.total()).toBe(0);
    // The inspector is where the change belongs, and it did change.
    expect(await inspectorWatch.total()).toBeGreaterThan(0);

    canvasWatch.stop();
    inspectorWatch.stop();
  });

  it("does not touch the canvas when the secondary selection changes", async () => {
    renderShell();
    act(() => useWorkspace.getState().select({ kind: "Entity", id: "ENT-1" }));

    const canvas = screen.getByTestId("canvas-overview");
    const watch1 = watch(canvas);

    act(() => useWorkspace.getState().toggleSecondary({ kind: "Entity", id: "ENT-2" }));
    act(() => useWorkspace.getState().toggleSecondary({ kind: "Entity", id: "ENT-3" }));

    expect(await watch1.total()).toBe(0);
    watch1.stop();
  });

  it("does not touch the canvas when a filter changes", async () => {
    renderShell();
    const canvas = screen.getByTestId("canvas-overview");
    const watcher = watch(canvas);

    act(() => useWorkspace.getState().setEvidenceFilter({ query: "passport" }));
    act(() => useWorkspace.getState().setRailQuery("vpn"));
    act(() => useWorkspace.getState().setTimeRange({ from: "2026-01-01T00:00:00Z", to: null }));

    expect(await watcher.total()).toBe(0);
    watcher.stop();
  });

  it("does not touch the canvas when the layout changes", async () => {
    renderShell();
    const canvas = screen.getByTestId("canvas-overview");
    const watcher = watch(canvas);

    act(() => useWorkspace.getState().setPaneWidth("rail", 300));
    act(() => useWorkspace.getState().setPaneWidth("inspector", 400));
    act(() => useWorkspace.getState().togglePane("activity"));

    expect(await watcher.total()).toBe(0);
    watcher.stop();
  });

  it("does not touch the inspector when only the canvas view changes", async () => {
    renderShell();
    act(() => useWorkspace.getState().select({ kind: "Entity", id: "ENT-182" }));

    const watcher = watch(screen.getByTestId("pane-inspector"));

    act(() => useWorkspace.getState().setView("graph"));
    act(() => useWorkspace.getState().setView("timeline"));
    act(() => useWorkspace.getState().setView("overview"));

    // The inspector subscribes to selection and section state, not to `view`,
    // so switching the canvas leaves it exactly where it was.
    expect(await watcher.total()).toBe(0);
    watcher.stop();
  });
});

describe("§68 — the selection is genuinely global", () => {
  it("one write drives the inspector, the rail and the top bar together", async () => {
    renderShell();
    expect(screen.getByTestId("inspector-empty")).toBeInTheDocument();

    act(() => useWorkspace.getState().select({ kind: "Entity", id: "ENT-182" }));

    expect(screen.queryByTestId("inspector-empty")).not.toBeInTheDocument();
    expect(screen.getByTestId("rail-selection")).toHaveTextContent("ENT-182");
    expect(screen.getByTestId("topbar-selection")).toHaveTextContent("ENT-182");
  });

  it("a selection made while on one view is visible from another (§7)", async () => {
    renderShell();
    act(() => useWorkspace.getState().setView("graph"));
    act(() => useWorkspace.getState().select({ kind: "Observation", id: "OBS-9001" }));

    act(() => useWorkspace.getState().setView("evidence"));
    expect(screen.getByTestId("canvas-evidence-selection")).toHaveTextContent("OBS-9001");
    expect(screen.getByTestId("inspector-subtitle")).toHaveTextContent("OBS-9001");
  });

  it("clearing the selection propagates everywhere at once", async () => {
    renderShell();
    act(() => useWorkspace.getState().select({ kind: "Entity", id: "ENT-182" }));
    act(() => useWorkspace.getState().clearSelection());

    expect(screen.getByTestId("inspector-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("topbar-selection")).not.toBeInTheDocument();
  });

  it("re-rendering on selection produces no act() warning", async () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    renderShell();
    spy.mockClear();

    act(() => useWorkspace.getState().select({ kind: "Claim", id: "REL-42" }));
    act(() => useWorkspace.getState().toggleSecondary({ kind: "Entity", id: "ENT-1" }));
    act(() => useWorkspace.getState().clearSelection());

    const actWarnings = spy.mock.calls.filter(([message]) =>
      String(message).includes("not wrapped in act"),
    );
    spy.mockRestore();
    expect(actWarnings).toEqual([]);
  });
});