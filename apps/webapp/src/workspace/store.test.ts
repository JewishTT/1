import { describe, expect, it } from "vitest";

import {
  DEFAULT_PANE_WIDTHS,
  selectSelectionId,
  selectView,
  useWorkspace,
  workspaceContext,
  type WorkspaceStore,
} from "./store";
import { buildWorkspaceSearch, parseWorkspaceSearch } from "./url";
import { DEFAULT_DENSITY, DEFAULT_THEME, OPEN_TIME_RANGE, type WorkspaceSelection } from "./types";

/**
 * Selection store tests (§7, §76, §77).
 *
 * The store is a module singleton, so each test restores the initial shape.
 * `resetWorkspace()` is exported from the store for exactly this; it is not
 * used by application code.
 */
function fresh(): WorkspaceStore {
  return useWorkspace.getState();
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
    // The product's own defaults, not literals: a test that pins `density` here
    // would silently stop testing the default when §4.2 changes it.
    density: DEFAULT_DENSITY,
    theme: DEFAULT_THEME,
    commandPaletteOpen: false,
    contextMenu: null,
  });
}

const ENT: WorkspaceSelection = { kind: "Entity", id: "ENT-182", label: "Организация X" };
const OBS: WorkspaceSelection = { kind: "Observation", id: "OBS-9001" };
const CLAIM: WorkspaceSelection = { kind: "Claim", id: "CLM-55" };

describe("WorkspaceState — selection is one global model (§7)", () => {
  it("has exactly one primary selection slot regardless of which view wrote it", () => {
    reset();
    const store = fresh();
    store.select(ENT);
    expect(fresh().selection).toEqual(ENT);

    // A "different view" writing selection is the same action, not a local copy.
    fresh().select(OBS);
    expect(fresh().selection).toEqual(OBS);
    expect(selectSelectionId(fresh())).toBe("OBS-9001");
  });

  it("keeps the secondary selection separate from the primary one", () => {
    reset();
    fresh().select(ENT);
    fresh().toggleSecondary(CLAIM);
    fresh().toggleSecondary(OBS);

    expect(fresh().selection).toEqual(ENT);
    expect(fresh().secondarySelection).toEqual([CLAIM, OBS]);
  });

  it("toggles a secondary entry off and never promotes it to primary", () => {
    reset();
    fresh().select(ENT);
    fresh().toggleSecondary(CLAIM);
    fresh().toggleSecondary(CLAIM);

    expect(fresh().secondarySelection).toEqual([]);
    expect(fresh().selection).toEqual(ENT);
  });

  it("selectIfEmpty leaves an existing selection alone", () => {
    reset();
    fresh().select(ENT);
    fresh().selectIfEmpty(OBS);
    expect(fresh().selection).toEqual(ENT);
  });

  it("clearSelection clears primary and secondary together", () => {
    reset();
    fresh().select(ENT);
    fresh().toggleSecondary(CLAIM);
    fresh().clearSelection();
    expect(fresh().selection).toBeNull();
    expect(fresh().secondarySelection).toEqual([]);
  });
});

describe("WorkspaceState — §76 view switching destroys nothing", () => {
  it("preserves selection, secondary selection, filters, time range, investigation and layout", () => {
    reset();
    const store = fresh();

    store.setInvestigation("42", "Operation Ledger");
    store.select(ENT);
    store.toggleSecondary(CLAIM);
    store.setEvidenceFilter({ query: "passport", hideRejected: true });
    store.setRailQuery("vpn");
    store.toggleRailKind("Observation");
    store.setTimeRange({ from: "2026-01-01T00:00:00Z", to: "2026-02-01T00:00:00Z" });
    store.setPaneWidth("rail", 320);
    store.togglePane("activity");
    store.setDensity("comfortable");
    store.setInspectorSection("evidence", true);

    const before = fresh();
    const snapshot = {
      selection: before.selection,
      secondarySelection: before.secondarySelection,
      evidenceFilter: before.evidenceFilter,
      railQuery: before.railQuery,
      timeRange: before.timeRange,
      investigationId: before.investigationId,
      investigationLabel: before.investigationLabel,
      paneWidths: before.paneWidths,
      paneVisibility: before.paneVisibility,
      density: before.density,
      openInspectorSections: before.openInspectorSections,
    };

    // Walk every view, the way the canvas switcher does.
    for (const view of ["graph", "objects", "evidence", "timeline", "analysis", "overview"] as const) {
      fresh().setView(view);
      const now = fresh();
      expect(selectView(now)).toBe(view);
      expect({
        selection: now.selection,
        secondarySelection: now.secondarySelection,
        evidenceFilter: now.evidenceFilter,
        railQuery: now.railQuery,
        timeRange: now.timeRange,
        investigationId: now.investigationId,
        investigationLabel: now.investigationLabel,
        paneWidths: now.paneWidths,
        paneVisibility: now.paneVisibility,
        density: now.density,
        openInspectorSections: now.openInspectorSections,
      }).toEqual(snapshot);
    }
  });

  it("returns to the identical state it left, view-for-view", () => {
    reset();
    fresh().select(OBS);
    fresh().setView("graph");
    const atGraph = workspaceContext(fresh());
    fresh().setView("timeline");
    fresh().setView("overview");
    fresh().setView("graph");
    expect(workspaceContext(fresh())).toEqual(atGraph);
  });

  it("keeps the context across an investigation change of view only — setInvestigation does not clear the view", () => {
    reset();
    fresh().setInvestigation("42");
    fresh().setView("graph");
    fresh().setInvestigation("43");
    expect(fresh().view).toBe("graph");
    expect(fresh().investigationId).toBe("43");
  });
});

describe("WorkspaceState — §77 URL round-trip", () => {
  it("parses the documented shape `/investigations/42?view=graph&entity=ENT-182`", () => {
    const patch = parseWorkspaceSearch("?view=graph&entity=ENT-182");
    expect(patch).toEqual({
      view: "graph",
      selection: { kind: "Entity", id: "ENT-182" },
    });
  });

  it("omits defaults when serialising", () => {
    expect(buildWorkspaceSearch({ view: "overview", selection: null })).toBe("");
  });

  it("round-trips a full context without loss", () => {
    reset();
    // The investigation id lives in the path, not the query string.
    fresh().setInvestigation("42");
    fresh().setView("evidence");
    fresh().select(OBS);
    fresh().setEvidenceFilter({ query: "ledger" });
    fresh().setTimeRange({ from: "2026-01-01T00:00:00Z", to: null });

    const serialised = buildWorkspaceSearch(workspaceContext(fresh()));
    expect(parseWorkspaceSearch(serialised)).toEqual(workspaceContext(fresh()));
  });

  it("degrades gracefully on malformed input instead of throwing", () => {
    expect(parseWorkspaceSearch("?view=nonsense&entity=")).toEqual({});
    expect(parseWorkspaceSearch("??&=")).toEqual({});
    expect(parseWorkspaceSearch("")).toEqual({});
  });

  it("a refresh does not zero the workspace: hydrateFromUrl writes only the keys present", () => {
    reset();
    fresh().setInvestigation("42");
    fresh().setView("graph");
    fresh().select(ENT);
    fresh().setEvidenceFilter({ query: "keepme", hideRejected: true });

    // A reload delivers only what the URL carried: view + selection.
    fresh().hydrateFromUrl(parseWorkspaceSearch("?view=timeline&observation=OBS-7"));

    expect(fresh().view).toBe("timeline");
    expect(fresh().selection).toEqual({ kind: "Observation", id: "OBS-7" });
    // Filters and layout are not in the URL, so hydration cannot have touched them.
    expect(fresh().evidenceFilter).toEqual({ query: "keepme", sourceIds: [], hideRejected: true });
  });
});

describe("WorkspaceState — layout actions", () => {
  it("defaults to standard density and walks the three modes in canonical order (§4.2)", () => {
    reset();
    expect(fresh().density).toBe("standard");
    fresh().toggleDensity();
    expect(fresh().density).toBe("comfortable");
    // Comfortable is the last mode, so the cycle wraps rather than sticking.
    fresh().toggleDensity();
    expect(fresh().density).toBe("compact");
    fresh().toggleDensity();
    expect(fresh().density).toBe("standard");
  });

  it("clamps a negative pane width rather than storing it", () => {
    reset();
    fresh().setPaneWidth("inspector", -40);
    expect(fresh().paneWidths.inspector).toBe(0);
  });

  it("keeps the investigation label when re-selecting without one", () => {
    reset();
    fresh().setInvestigation("42", "Operation Ledger");
    fresh().setInvestigation("42");
    expect(fresh().investigationLabel).toBe("Operation Ledger");
  });
});

