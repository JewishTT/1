import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { WorkbenchCanvas } from "./Workbench";
import { CanvasContextMenu } from "./ui/ContextMenu";
import { InvestigationWorkspace } from "./workspace/InvestigationWorkspace";
import { ContextInspector } from "./workspace/inspector/ContextInspector";
import { INSPECTOR_KINDS, actionsForSelection, destinationForAction } from "./workspace/commands";
import { DEFAULT_PANE_WIDTHS, useWorkspace } from "./workspace/store";
import { OPEN_TIME_RANGE, WORKSPACE_VIEWS, type WorkspaceObjectKind, type WorkspaceView } from "./workspace/types";

/**
 * §76 integration test: context survival across view switches, in the real
 * component tree.
 *
 * store.test.ts proves the mechanism — `setView` is a single-field write. This
 * proves the consequence: the rail and the inspector are mounted *outside* the
 * view switch, so a switch does not remount them and their DOM survives.
 */

function renderWorkspace() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <InvestigationWorkspace />
      <ContextInspector />
    </QueryClientProvider>,
  );
}

/**
 * Store writes from outside React must be wrapped in `act`, or the re-render
 * is not flushed before the assertion runs. Test-harness detail, not an
 * application one.
 */
function switchView(view: WorkspaceView) {
  act(() => useWorkspace.getState().setView(view));
}

function selectObject(kind: WorkspaceObjectKind, id: string) {
  act(() => useWorkspace.getState().select({ kind, id }));
}

/**
 * The views this file walks, derived from the product's own list rather than
 * written out again.
 *
 * A literal copy is what let the stage-2 test suite and the stage-3–4 surface
 * set disagree in the first place: the tests asserted eight views while
 * `WORKSPACE_VIEWS` was the thing under test. Deriving it means a new view is
 * covered the moment it is declared, and a view that disappears fails here
 * instead of quietly going untested.
 */
const ALL_VIEWS: ReadonlyArray<WorkspaceView> = WORKSPACE_VIEWS;

beforeEach(() => {
  useWorkspace.setState({
    investigationId: "42",
    investigationLabel: "Operation Ledger",
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

describe("§76 — switching views preserves context in the rendered tree", () => {
  it("keeps the selection through every view", () => {
    selectObject("Entity", "ENT-182");
    renderWorkspace();

    expect(screen.getByTestId("inspector-subtitle")).toHaveTextContent("ENT-182");
    expect(screen.getByTestId("canvas-overview")).toBeInTheDocument();

    for (const view of ALL_VIEWS) {
      switchView(view);
      expect(useWorkspace.getState().selection?.id).toBe("ENT-182");
      expect(screen.getByTestId("inspector-subtitle")).toHaveTextContent("ENT-182");
    }
  });

  it("keeps filters, time range and layout while the canvas changes", () => {
    const store = useWorkspace.getState();
    store.setEvidenceFilter({ query: "passport", hideRejected: true });
    store.setRailQuery("vpn");
    store.setTimeRange({ from: "2026-01-01T00:00:00Z", to: "2026-02-01T00:00:00Z" });
    store.setPaneWidth("rail", 300);
    store.togglePane("activity");

    renderWorkspace();

    const expected = {
      evidenceFilter: { query: "passport", sourceIds: [], hideRejected: true },
      railQuery: "vpn",
      timeRange: { from: "2026-01-01T00:00:00Z", to: "2026-02-01T00:00:00Z" },
      paneWidths: { ...DEFAULT_PANE_WIDTHS, rail: 300 },
      paneVisibility: { rail: true, inspector: true, activity: false },
    };

    for (const view of ALL_VIEWS) {
      switchView(view);
      const now = useWorkspace.getState();
      expect({
        evidenceFilter: now.evidenceFilter,
        railQuery: now.railQuery,
        timeRange: now.timeRange,
        paneWidths: now.paneWidths,
        paneVisibility: now.paneVisibility,
      }).toEqual(expected);
    }
  });

  it("keeps the investigation across views", () => {
    act(() => useWorkspace.getState().setInvestigation("7", "Named case"));
    renderWorkspace();
    switchView("graph");
    expect(useWorkspace.getState().investigationId).toBe("7");
    expect(useWorkspace.getState().investigationLabel).toBe("Named case");
  });

  it("keeps the secondary selection across views", () => {
    selectObject("Entity", "ENT-1");
    act(() => useWorkspace.getState().toggleSecondary({ kind: "Entity", id: "ENT-2" }));
    renderWorkspace();
    switchView("evidence");
    expect(useWorkspace.getState().secondarySelection.map((entry) => entry.id)).toEqual(["ENT-2"]);
  });
});

describe("workspace — only the centre canvas switches", () => {
  it("renders every declared view in the canvas", () => {
    renderWorkspace();
    for (const view of ALL_VIEWS) {
      switchView(view);
      const canvas = screen.getByTestId(`canvas-${view}`);
      expect(canvas).toHaveAttribute("data-view", view);
    }
  });

  it("mounts the inspector once and keeps the same node across views", () => {
    selectObject("Observation", "OBS-1");
    renderWorkspace();

    const before = screen.getByTestId("context-inspector");
    switchView("graph");
    expect(screen.getAllByTestId("context-inspector")).toHaveLength(1);
    expect(screen.getByTestId("context-inspector")).toBe(before);
  });

  it("announces the view change without moving focus", () => {
    renderWorkspace();
    switchView("graph");
    expect(screen.getByTestId("workspace-live-region")).toHaveTextContent("Graph view");
  });

  it("labels unbuilt views with the stage that owns them, rather than faking them", () => {
    renderWorkspace();
    for (const view of ALL_VIEWS.filter((entry) => entry !== "overview")) {
      switchView(view);
      expect(screen.getByTestId(`placeholder-${view}`)).toBeInTheDocument();
      expect(screen.getByTestId("canvas-stage")).toHaveTextContent("stage");
    }
  });

  it("shows the preserved selection inside the placeholder, proving §76 visibly", () => {
    selectObject("Claim", "REL-42");
    renderWorkspace();
    switchView("evidence");
    expect(screen.getByTestId("canvas-evidence-selection")).toHaveTextContent("REL-42");
  });
});

describe("workspace — view switcher is keyboard reachable", () => {
  it("exposes the switcher as a tablist with one tab per declared view and the active one selected", () => {
    renderWorkspace();
    const tablist = screen.getByRole("tablist", { name: "Workspace views" });
    expect(within(tablist).getAllByRole("tab")).toHaveLength(WORKSPACE_VIEWS.length);
    expect(within(tablist).getByRole("tab", { name: /Overview/ })).toHaveAttribute("aria-selected", "true");
  });

  it("moves the canvas when a tab is activated", () => {
    renderWorkspace();
    fireEvent.click(screen.getByTestId("tab-timeline"));
    expect(useWorkspace.getState().view).toBe("timeline");
    expect(screen.getByTestId("canvas-timeline")).toBeInTheDocument();
  });

  it("keeps only the active tab in the tab order (roving tabindex)", () => {
    renderWorkspace();
    expect(screen.getByTestId("tab-overview")).toHaveAttribute("tabindex", "0");
    expect(screen.getByTestId("tab-graph")).toHaveAttribute("tabindex", "-1");
  });
});

describe("inspector — empty and unavailable states are honest", () => {
  it("prompts for a selection instead of showing an empty object", () => {
    renderWorkspace();
    const empty = screen.getByTestId("inspector-empty");
    expect(empty).toHaveTextContent(/global/i);
  });

  it("says a record is not fetched rather than showing a blank panel", () => {
    selectObject("Observation", "OBS-404");
    renderWorkspace();
    expect(screen.getByTestId("inspector-unavailable")).toHaveTextContent(/not fetched/i);
  });

  it("offers a next step for every selected object kind (§69)", () => {
    // Driven by INSPECTOR_KINDS so a newly declared kind cannot slip past this
    // assertion the way Investigation did.
    for (const kind of INSPECTOR_KINDS) {
      selectObject(kind, "X-1");
      const view = renderWorkspace();
      expect(screen.getByTestId("inspector-next"), kind).toBeInTheDocument();
      view.unmount();
    }
  });

  it("gives every next step a declared destination, so no button is a dead end (§69)", () => {
    for (const kind of INSPECTOR_KINDS) {
      selectObject(kind, "X-1");
      for (const action of actionsForSelection({ kind, id: "X-1" }, 1)) {
        expect(destinationForAction(action.id), `${kind} → ${action.id}`).not.toBeNull();
      }
    }
  });

  it("actually navigates when a next step is clicked (§69 — no inert buttons)", () => {
    for (const kind of INSPECTOR_KINDS) {
      selectObject(kind, "X-1");
      const view = renderWorkspace();

      for (const action of actionsForSelection({ kind, id: "X-1" }, 1)) {
        const destination = destinationForAction(action.id);
        switchView("overview");
        const label = screen
          .getAllByRole("button")
          .find((node) => node.textContent?.trim() === action.label);
        expect(label, `${kind} → ${action.label} is rendered`).toBeDefined();
        act(() => label?.click());
        expect(useWorkspace.getState().view, `${kind} → ${action.label} navigated`).toBe(destination);
      }
      view.unmount();
    }
  });

  it("offers no next step when nothing is selected", () => {
    renderWorkspace();
    expect(screen.queryByTestId("inspector-next")).not.toBeInTheDocument();
  });
});

describe("§69 — the context menu cannot drift from the inspector", () => {
  it("navigates for every action it offers, for every object kind", () => {
    for (const kind of INSPECTOR_KINDS) {
      selectObject(kind, "X-1");
      act(() => useWorkspace.getState().openContextMenu({ x: 40, y: 40, targetKind: kind }));
      const view = render(
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <CanvasContextMenu />
        </QueryClientProvider>,
      );

      for (const action of actionsForSelection({ kind, id: "X-1" }, 1)) {
        const destination = destinationForAction(action.id);
        if (destination === null) continue;
        switchView("overview");
        // The menu closes itself when an item is chosen, so it is re-opened
        // before each lookup.
        act(() => useWorkspace.getState().openContextMenu({ x: 40, y: 40, targetKind: kind }));
        expect(
          screen.getByTestId(`ctx-${action.id}`),
          `${kind} → ${action.id} is offered by the menu`,
        ).toBeInTheDocument();
        act(() => screen.getByTestId(`ctx-${action.id}`).click());
        expect(useWorkspace.getState().view, `${kind} → ${action.id} navigated from the menu`).toBe(
          destination,
        );
      }
      view.unmount();
      act(() => useWorkspace.getState().closeContextMenu());
    }
  });
});

describe("workbench canvas — workspace and inspector side by side", () => {
  it("mounts both, with the inspector labelled for assistive tech", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <WorkbenchCanvas />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("workbench-canvas")).toBeInTheDocument();
    expect(screen.getByLabelText("Object inspector")).toBeInTheDocument();
  });
});