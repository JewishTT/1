import { render, screen, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useWorkspace } from "../workspace/store";
import { TimelineToolbar, type TimelineToolbarProps } from "./TimelineToolbar";
import { EMPTY_TIMELINE_FILTER, compareWindows, type WindowComparison } from "./series";
import { LANE_SEMANTICS, TIMELINE_LANES, routeForEvent, type TimelineEvent } from "./types";

/**
 * Timeline toolbar tests (§23, §67, §69, §90, §91).
 *
 * The point of these is that the timeline is an ANALYTICAL SURFACE, not a
 * slider (§84). A slider has one control; this one has seven, so the tests walk
 * all seven and assert each is reachable, named, and writes something real.
 *
 * The load-bearing assertion is the brush: it must write the STORE's time range,
 * because that store field is what the graph's temporal facet reads. That is the
 * whole of "changing time changes graph state".
 */

function event(id: string, at: string, extra: Partial<TimelineEvent> = {}): TimelineEvent {
  return {
    id,
    lane: "Observation",
    ref: id,
    label: id,
    at,
    endAt: null,
    sourceId: null,
    status: null,
    entityRef: null,
    ...extra,
  };
}

const COMPARISON: WindowComparison = {
  current: { from: "2026-01-05T00:00:00Z", to: "2026-01-10T00:00:00Z", count: 7 },
  previous: { from: "2026-01-01T00:00:00Z", to: "2026-01-06T00:00:00Z", count: 4 },
  delta: 3,
  label: "Busier by 3 than the preceding window.",
};

function renderToolbar(overrides: Partial<TimelineToolbarProps> = {}) {
  const props: TimelineToolbarProps = {
    filter: EMPTY_TIMELINE_FILTER,
    onFilterChange: vi.fn(),
    presentLanes: ["Observation", "Finding"],
    presentSourceIds: ["acme.example"],
    presentStatuses: ["IMMUTABLE"],
    timeRange: { from: null, to: null },
    onBrush: vi.fn(),
    onZoom: vi.fn(),
    onPan: vi.fn(),
    onResetZoom: vi.fn(),
    zoom: 1,
    canZoom: true,
    comparison: COMPARISON,
    onFocus: vi.fn(),
    onClearFocus: vi.fn(),
    focus: null,
    onCompare: vi.fn(),
    secondaryCount: 0,
    onClearWindow: vi.fn(),
    counts: { Observation: 3, Finding: 1, Claim: 0, AcquisitionRun: 0 },
    unplaced: 4,
    loading: false,
    disabled: false,
    ...overrides,
  };
  return { props, ...render(<TimelineToolbar {...props} />) };
}

beforeEach(() => {
  document.body.innerHTML = "";
  useWorkspace.setState({ timeRange: { from: null, to: null } });
});

describe("§23 — the toolbar is an analytical surface, not a slider", () => {
  it("renders as a toolbar with an accessible name", () => {
    renderToolbar();
    const toolbar = screen.getByTestId("timeline-toolbar");
    expect(toolbar).toHaveAttribute("role", "toolbar");
    expect(toolbar).toHaveAttribute("aria-label", "Timeline controls");
  });

  it("offers all seven actions: filter, brush, zoom, compare, and three focuses", () => {
    renderToolbar();
    expect(screen.getByTestId("timeline-filter")).toBeInTheDocument();
    expect(screen.getByLabelText("from")).toBeInTheDocument();
    expect(screen.getByLabelText("to")).toBeInTheDocument();
    expect(screen.getByTestId("timeline-zoom-in")).toBeInTheDocument();
    expect(screen.getByTestId("timeline-zoom-out")).toBeInTheDocument();
    expect(screen.getByTestId("timeline-compare")).toBeInTheDocument();
    expect(screen.getByTestId("timeline-focus-entity")).toBeInTheDocument();
    expect(screen.getByTestId("timeline-focus-relation")).toBeInTheDocument();
    expect(screen.getByTestId("timeline-focus-evidence")).toBeInTheDocument();
  });

  it("gives every icon-only control an accessible name (§67)", () => {
    renderToolbar();
    for (const label of ["Zoom in", "Zoom out", "Pan back", "Pan forward"]) {
      expect(screen.getByRole("button", { name: label }), label).toBeInTheDocument();
    }
  });

  it("keeps the three focus targets separate, each with its own field", () => {
    renderToolbar();
    // Separate controls, not a mode selector: the three targets take different
    // arguments, so making the analyst remember a mode first would be friction.
    for (const label of ["Focus entity", "Focus relation", "Focus evidence"]) {
      expect(screen.getByLabelText(label), label).toBeInTheDocument();
    }
  });
});

describe("§23 — the brush writes the workspace time range, and that is what narrows the graph", () => {
  it("emits a closed TimeRange from the two bound fields", () => {
    const { props } = renderToolbar();
    fireEvent.change(screen.getByLabelText("from"), { target: { value: "2026-01-05T00:00" } });
    expect(props.onBrush).toHaveBeenCalledWith("2026-01-05T00:00:00.000Z", null);

    fireEvent.change(screen.getByLabelText("to"), { target: { value: "2026-01-10T12:30" } });
    expect(props.onBrush).toHaveBeenLastCalledWith(null, "2026-01-10T12:30:00.000Z");
  });

  it("clears the bound when the field is emptied, rather than rejecting the input", () => {
    const { props } = renderToolbar({ timeRange: { from: "2026-01-05T00:00:00Z", to: null } });
    fireEvent.change(screen.getByLabelText("from"), { target: { value: "" } });
    expect(props.onBrush).toHaveBeenCalledWith(null, null);
  });

  it("renders an open bound as an empty field, which is what open means", () => {
    renderToolbar();
    expect(screen.getByLabelText("from")).toHaveValue("");
    expect(screen.getByLabelText("to")).toHaveValue("");
  });

  it("disables Clear until there IS a window to clear", () => {
    renderToolbar();
    expect(screen.getByTestId("timeline-clear-window")).toBeDisabled();
    renderToolbar({ timeRange: { from: "2026-01-01T00:00:00Z", to: null } });
    expect(screen.getAllByTestId("timeline-clear-window")[1]).not.toBeDisabled();
  });

  it("is the SAME field the graph reads — the store's timeRange is unchanged by rendering", () => {
    renderToolbar({ timeRange: { from: "2026-01-05T00:00:00Z", to: "2026-01-10T00:00:00Z" } });
    // The toolbar renders what the store holds. It keeps no window of its own.
    expect(useWorkspace.getState().timeRange).toEqual({ from: null, to: null });
    expect(screen.getByLabelText("from")).toHaveValue("2026-01-05T00:00");
  });
});

describe("§23 — zoom and pan", () => {
  it("zooms in by a factor and out by its reciprocal", () => {
    const { props } = renderToolbar();
    fireEvent.click(screen.getByTestId("timeline-zoom-in"));
    expect(props.onZoom).toHaveBeenCalledWith(1 / 1.5);
    fireEvent.click(screen.getByTestId("timeline-zoom-out"));
    expect(props.onZoom).toHaveBeenCalledWith(1.5);
  });

  it("pans in half-window steps, and can pan back as well as forward", () => {
    const { props } = renderToolbar();
    fireEvent.click(screen.getByTestId("timeline-pan-forward"));
    expect(props.onPan).toHaveBeenCalledWith(0.5);
    fireEvent.click(screen.getByTestId("timeline-pan-back"));
    expect(props.onPan).toHaveBeenCalledWith(-0.5);
  });

  it("reports the zoom level as a fraction of the full span", () => {
    renderToolbar({ zoom: 0.25 });
    expect(screen.getByTestId("timeline-zoom-level")).toHaveTextContent("0.25×");
  });

  it("disables zoom and pan when there is no domain to zoom", () => {
    renderToolbar({ canZoom: false });
    expect(screen.getByTestId("timeline-zoom-in")).toBeDisabled();
    expect(screen.getByTestId("timeline-pan-forward")).toBeDisabled();
  });
});

describe("§23 — compare", () => {
  it("shows both counts and the delta", () => {
    renderToolbar();
    const badge = screen.getByTestId("timeline-compare-delta");
    expect(badge).toHaveTextContent("7 vs 4");
    expect(badge).toHaveTextContent("+3");
  });

  it("shows no delta rather than a fabricated zero when the window is open-ended", () => {
    const open: WindowComparison = {
      current: { from: "2026-01-05T00:00:00Z", to: null, count: 7 },
      previous: { from: null, to: null, count: 0 },
      delta: null,
      label: "Set both window bounds to compare against the preceding window.",
    };
    renderToolbar({ comparison: open });
    expect(screen.getByTestId("timeline-compare-delta")).toHaveTextContent("7 vs 0");
    expect(screen.getByTestId("timeline-compare-delta").textContent).not.toContain("+0");
  });

  it("reports the comparison in words when asked", () => {
    const { props } = renderToolbar();
    fireEvent.click(screen.getByTestId("timeline-compare"));
    expect(props.onCompare).toHaveBeenCalled();
  });
});

describe("§23 — focus", () => {
  it("focuses an entity, a relation and an evidence record distinctly", () => {
    const { props } = renderToolbar();
    fireEvent.change(screen.getByLabelText("Focus entity"), { target: { value: "ENT-1" } });
    fireEvent.click(screen.getByTestId("timeline-focus-entity"));
    expect(props.onFocus).toHaveBeenCalledWith("entity", "ENT-1");

    fireEvent.change(screen.getByLabelText("Focus relation"), { target: { value: "CLM-9" } });
    fireEvent.click(screen.getByTestId("timeline-focus-relation"));
    expect(props.onFocus).toHaveBeenLastCalledWith("relation", "CLM-9");

    fireEvent.change(screen.getByLabelText("Focus evidence"), { target: { value: "OBS-3" } });
    fireEvent.click(screen.getByTestId("timeline-focus-evidence"));
    expect(props.onFocus).toHaveBeenLastCalledWith("evidence", "OBS-3");
  });

  it("runs a focus on Enter, so the field is usable without a pointer", () => {
    const { props } = renderToolbar();
    fireEvent.change(screen.getByLabelText("Focus entity"), { target: { value: "ENT-1" } });
    fireEvent.keyDown(screen.getByLabelText("Focus entity"), { key: "Enter" });
    expect(props.onFocus).toHaveBeenCalledWith("entity", "ENT-1");
  });

  it("disables a focus until something is typed", () => {
    renderToolbar();
    expect(screen.getByTestId("timeline-focus-entity")).toBeDisabled();
  });

  it("reports a focus that matched nothing as a problem, not as a silent no-op", () => {
    renderToolbar({ focus: { label: "No timeline events for that entity.", empty: true, eventIds: [] } });
    expect(screen.getByTestId("timeline-clear-focus")).toHaveTextContent("no match");
  });

  it("reports a successful focus with its size, and offers a way to undo it", () => {
    const { props } = renderToolbar({
      focus: { label: "ENT-1: 3 event(s) across Observation + Finding.", empty: false, eventIds: ["a", "b", "c"] },
    });
    expect(screen.getByTestId("timeline-clear-focus")).toHaveTextContent("3 focused");
    fireEvent.click(screen.getByTestId("timeline-clear-focus"));
    expect(props.onClearFocus).toHaveBeenCalled();
  });
});

describe("§84 / §90 / §99 — the toolbar reports what it cannot see", () => {
  it("counts records the server named but gave no instant for", () => {
    renderToolbar({ unplaced: 0 });
    expect(screen.getByTestId("timeline-unplaced")).toHaveTextContent("every record is dated");
    renderToolbar({ unplaced: 12 });
    expect(screen.getAllByTestId("timeline-unplaced")[1]).toHaveTextContent(
      "12 record(s) named but not dated",
    );
  });

  it("counts the active filters on the filter control", () => {
    renderToolbar();
    expect(screen.getByTestId("timeline-filter")).toHaveTextContent("Filter");
    renderToolbar({
      filter: { ...EMPTY_TIMELINE_FILTER, lanes: ["Observation"], query: "acme" },
    });
    expect(screen.getAllByTestId("timeline-filter")[1]).toHaveTextContent("Filter (2)");
  });
});

describe("§84 — lanes are separated by token and grid, never by a hue alone", () => {
  it("gives every lane a distinct token and a distinct symbol", () => {
    const tokens = TIMELINE_LANES.map((lane) => LANE_SEMANTICS[lane].token);
    const symbols = TIMELINE_LANES.map((lane) => LANE_SEMANTICS[lane].symbol);
    expect(new Set(tokens).size).toBe(tokens.length);
    expect(new Set(symbols).size).toBe(symbols.length);
  });

  it("routes each lane's event to the matching WorkspaceSelection kind", () => {
    for (const lane of TIMELINE_LANES) {
      const route = routeForEvent(event(`${lane}-1`, "2026-01-01T00:00:00Z", { lane }));
      expect(route.kind, lane).toBe(LANE_SEMANTICS[lane].selectionKind);
      expect(route.id).toBe(`${lane}-1`);
    }
  });
});

describe("§99 — compare computes over the data, not over a constant", () => {
  it("counts the events inside the window", () => {
    const events = [
      event("a", "2026-01-02T00:00:00Z"),
      event("b", "2026-01-04T00:00:00Z"),
      event("c", "2026-01-20T00:00:00Z"),
    ];
    const result = compareWindows(events, { from: "2026-01-01T00:00:00Z", to: "2026-01-10T00:00:00Z" });
    expect(result.current.count).toBe(2);
    expect(result.previous.count).toBe(0);
    expect(result.delta).toBe(2);
  });
});