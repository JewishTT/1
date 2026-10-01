import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";

import { InvestigationWorkspaceRoute } from "./Workbench";
import { DEFAULT_PANE_WIDTHS, useWorkspace } from "./workspace/store";
import { OPEN_TIME_RANGE } from "./workspace/types";

/**
 * §77: "the URL preserves context, e.g. `/investigations/42?view=graph&entity=ENT-182`;
 * a refresh must not zero the workspace."
 *
 * These tests drive the real route with a real router and assert on both
 * directions: what the store does with an inbound URL, and what the URL does
 * when the store changes.
 */

/**
 * The shell fetches the investigation record and the ops metrics on mount. This
 * file is about URL behaviour, not about server state, so the transport is
 * stubbed with a request that never settles. React Query then stays in its
 * pending state for the whole test: no async resolution lands outside `act()`,
 * and no rejected promise escapes either. The top bar renders its loading
 * state, which is the honest thing for it to show when there is no answer.
 *
 * The stub is installed once for the whole file and never restored: a query
 * issued by one test must not be able to resolve during a later one.
 */
function stubFetch(): void {
  globalThis.fetch = (() => new Promise(() => {})) as unknown as typeof fetch;
}

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location">{`${location.pathname}${location.search}`}</span>;
}

async function renderRoute(entry: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const result = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/investigations/:id" element={<InvestigationWorkspaceRoute />} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  // The top bar's work-state query settles asynchronously (two probes, one for
  // the investigation record and one for the ops metrics). Draining the
  // microtask *and* macrotask queues inside act() keeps those state updates
  // inside the act scope instead of leaking a warning after the test body.
  // Mount effects (the route's setInvestigation, the URL write) need one flush.
  await act(async () => {
    await Promise.resolve();
  });
  return result;
}

function reset() {
  useWorkspace.setState({
    investigationId: null,
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
}


/**
 * Order matters here. The previous test's tree must be unmounted *before* the
 * store is reset: `reset()` writes to the store, and any component still
 * subscribed to it would re-render outside act(). Testing Library's automatic
 * cleanup runs in its own afterEach, which is too late for that, so the
 * teardown is done explicitly here.
 */
beforeEach(async () => {
  stubFetch();
  await act(async () => {
    cleanup();
    reset();
  });
  window.history.replaceState({}, "", "/");
});

describe("§77 — an inbound URL hydrates the workspace", () => {
  it("restores the view and the selection from the query string", async () => {
    await renderRoute("/investigations/42?view=graph&entity=ENT-182");

    const state = useWorkspace.getState();
    expect(state.investigationId).toBe("42");
    expect(state.view).toBe("graph");
    expect(state.selection).toEqual({ kind: "Entity", id: "ENT-182" });
  });

  it("renders the restored selection in the inspector", async () => {
    await renderRoute("/investigations/42?view=graph&entity=ENT-182");
    expect(screen.getByTestId("inspector-subtitle")).toHaveTextContent("ENT-182");
    expect(screen.getByTestId("canvas-graph")).toBeInTheDocument();
  });

  it("restores an observation selection", async () => {
    await renderRoute("/investigations/42?observation=OBS-9001");
    expect(useWorkspace.getState().selection).toEqual({ kind: "Observation", id: "OBS-9001" });
  });

  it("restores the evidence query and the time range", async () => {
    await renderRoute("/investigations/42?q=passport&from=2026-01-01T00%3A00%3A00Z&to=2026-02-01T00%3A00%3A00Z");

    const state = useWorkspace.getState();
    expect(state.evidenceFilter.query).toBe("passport");
    expect(state.timeRange).toEqual({ from: "2026-01-01T00:00:00Z", to: "2026-02-01T00:00:00Z" });
  });

  it("ignores an unknown view rather than breaking", async () => {
    await renderRoute("/investigations/42?view=not-a-view");
    expect(useWorkspace.getState().view).toBe("overview");
  });

  it("does not clear layout preferences, which are deliberately not in the URL", async () => {
    useWorkspace.setState({ density: "comfortable", paneWidths: { ...DEFAULT_PANE_WIDTHS, rail: 333 } });
    await renderRoute("/investigations/42?view=timeline");

    const state = useWorkspace.getState();
    expect(state.density).toBe("comfortable");
    expect(state.paneWidths.rail).toBe(333);
  });
});

describe("§77 — an outbound change updates the URL", () => {
  it("writes the view into the query string", async () => {
    await renderRoute("/investigations/42");

    act(() => useWorkspace.getState().setView("graph"));
    expect(screen.getByTestId("location")).toHaveTextContent("/investigations/42?view=graph");
  });

  it("writes the selection as kind:id", async () => {
    await renderRoute("/investigations/42?view=graph");

    act(() => useWorkspace.getState().select({ kind: "Entity", id: "ENT-182" }));
    expect(screen.getByTestId("location")).toHaveTextContent("entity=ENT-182");
  });

  it("omits the default view rather than spelling out ?view=overview", async () => {
    await renderRoute("/investigations/42?view=graph");
    act(() => useWorkspace.getState().setView("overview"));
    expect(screen.getByTestId("location")).toHaveTextContent(/^(\/investigations\/42)?$/);
  });

  it("writes the evidence query and the time range", async () => {
    await renderRoute("/investigations/42");

    act(() => useWorkspace.getState().setEvidenceFilter({ query: "ledger" }));
    act(() => useWorkspace.getState().setTimeRange({ from: "2026-01-01T00:00:00Z", to: null }));

    const location = screen.getByTestId("location").textContent ?? "";
    expect(location).toContain("q=ledger");
    expect(location).toContain("from=2026-01-01T00%3A00%3A00Z");
  });

  it("does not write density, theme or pane widths into the URL", async () => {
    await renderRoute("/investigations/42");

    act(() => useWorkspace.getState().toggleDensity());
    act(() => useWorkspace.getState().toggleTheme());
    act(() => useWorkspace.getState().setPaneWidth("rail", 400));

    expect(screen.getByTestId("location")).not.toHaveTextContent("density");
    expect(screen.getByTestId("location")).not.toHaveTextContent("theme");
    expect(screen.getByTestId("location")).not.toHaveTextContent("rail");
  });
});

describe("§77 — round trip", () => {
  it("reproduces the same workspace from its own URL", async () => {
    await renderRoute("/investigations/42");

    act(() => useWorkspace.getState().setView("evidence"));
    act(() => useWorkspace.getState().select({ kind: "Claim", id: "REL-42" }));
    act(() => useWorkspace.getState().setEvidenceFilter({ query: "ledger" }));

    const produced = screen.getByTestId("location").textContent ?? "";

    // A refresh. The previous tree is unmounted first: leaving it subscribed
    // while the store is reset would have the old shell re-render against a
    // workspace it no longer owns.
    await act(async () => {
      cleanup();
      reset();
    });
    await renderRoute(produced);

    const state = useWorkspace.getState();
    expect(state.investigationId).toBe("42");
    expect(state.view).toBe("evidence");
    expect(state.selection).toEqual({ kind: "Claim", id: "REL-42" });
    expect(state.evidenceFilter.query).toBe("ledger");
  });
});