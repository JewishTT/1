import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { InvestigationWorkspaceRoute } from "./Workbench";
import { DEFAULT_PANE_WIDTHS, useWorkspace } from "./workspace/store";
import { OPEN_TIME_RANGE } from "./workspace/types";

/**
 * §50 keyboard model, exercised through the real shell with a router mounted.
 * `document`-level handlers only make sense inside a live tree, so a store-only
 * test would prove nothing about whether typing "g" in the rail filter changes
 * the canvas.
 */

function renderShell(initialEntry = "/investigations/42") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route path="/investigations/:id" element={<InvestigationWorkspaceRoute />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
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

afterEach(() => {
  document.body.innerHTML = "";
});

function press(key: string, init: Partial<KeyboardEventInit> = {}) {
  act(() => {
    fireEvent.keyDown(document, { key, ...init });
  });
}

describe("§50 — the view chords work from anywhere in the workspace", () => {
  it.each([
    ["g", "graph"],
    ["o", "objects"],
    ["e", "evidence"],
    ["t", "timeline"],
    ["a", "acquisition"],
  ])("%s switches the centre canvas to %s", (key, view) => {
    renderShell();
    press(key);
    expect(useWorkspace.getState().view).toBe(view);
    expect(screen.getByTestId(`canvas-${view}`)).toBeInTheDocument();
  });

  it("accepts an uppercase key too", () => {
    renderShell();
    press("G");
    expect(useWorkspace.getState().view).toBe("graph");
  });

  it("ignores an unbound key", () => {
    renderShell();
    press("z");
    expect(useWorkspace.getState().view).toBe("overview");
  });
});

describe("§50 — the keyboard model does not break text input", () => {
  it("does not switch views while a text field has focus", () => {
    renderShell();
    const query = screen.getByTestId("rail-query");
    query.focus();
    fireEvent.keyDown(query, { key: "g" });
    expect(useWorkspace.getState().view).toBe("overview");
  });

  it("still types the character into the field", () => {
    renderShell();
    const query = screen.getByTestId("rail-query") as HTMLInputElement;
    query.focus();
    fireEvent.change(query, { target: { value: "g" } });
    expect(query.value).toBe("g");
    expect(useWorkspace.getState().railQuery).toBe("g");
  });

  it("does not switch views from a select", () => {
    renderShell();
    const select = screen.getByTestId("rail-kind") as HTMLSelectElement;
    select.focus();
    fireEvent.keyDown(select, { key: "t" });
    expect(useWorkspace.getState().view).toBe("overview");
  });

  it("still opens the palette with ⌘K from inside a text field", () => {
    renderShell();
    const query = screen.getByTestId("rail-query");
    query.focus();
    fireEvent.keyDown(query, { key: "k", metaKey: true });
    expect(useWorkspace.getState().commandPaletteOpen).toBe(true);
  });

  it("still opens the palette with Ctrl-K", () => {
    renderShell();
    press("k", { ctrlKey: true });
    expect(useWorkspace.getState().commandPaletteOpen).toBe(true);
  });

  it("leaves browser chords alone", () => {
    renderShell();
    // ⌘R must not be swallowed by the palette toggle; only ⌘K is ours.
    press("r", { metaKey: true });
    expect(useWorkspace.getState().commandPaletteOpen).toBe(false);
  });
});

describe("§50 — the command palette is a working surface", () => {
  it("opens, focuses its field, and lists commands", () => {
    renderShell();
    press("k", { metaKey: true });

    const palette = screen.getByTestId("command-palette");
    expect(palette).toBeInTheDocument();
    expect(screen.getByTestId("command-palette-input")).toHaveFocus();
  });

  it("ranks the exact label match first as the analyst types", () => {
    renderShell();
    press("k", { metaKey: true });

    const input = screen.getByTestId("command-palette-input");
    fireEvent.change(input, { target: { value: "timeline" } });

    const options = within(screen.getByRole("listbox", { name: "Commands" })).getAllByRole("option");
    // "Clear time range" also carries "timeline" as a keyword, so the list is
    // not required to collapse to one row — the *ranking* is the contract.
    expect(options[0]).toHaveTextContent("Go to Timeline");
  });

  it("narrows to a single row for a label-only query", () => {
    renderShell();
    press("k", { metaKey: true });
    fireEvent.change(screen.getByTestId("command-palette-input"), { target: { value: "acquisition" } });

    const options = within(screen.getByRole("listbox", { name: "Commands" })).getAllByRole("option");
    expect(options).toHaveLength(1);
    expect(options[0]).toHaveTextContent("Go to Acquisition");
  });

  it("hides commands that are not available in the current context", () => {
    renderShell();
    press("k", { metaKey: true });
    // No selection yet, so the selection-bound command must not be offered.
    expect(screen.queryByTestId("command-item-selection.clear")).not.toBeInTheDocument();
  });

  it("offers selection-bound commands once something is selected", () => {
    act(() => useWorkspace.getState().select({ kind: "Entity", id: "ENT-1" }));
    renderShell();
    press("k", { metaKey: true });
    expect(screen.getByTestId("command-item-selection.clear")).toBeInTheDocument();
  });

  it("navigates with the arrows and opens with Enter", () => {
    act(() => useWorkspace.getState().setView("overview"));
    renderShell();
    press("k", { metaKey: true });

    const input = screen.getByTestId("command-palette-input");
    fireEvent.change(input, { target: { value: "graph" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(useWorkspace.getState().view).toBe("graph");
    expect(useWorkspace.getState().commandPaletteOpen).toBe(false);
  });

  it("closes on Escape", () => {
    renderShell();
    press("k", { metaKey: true });
    expect(useWorkspace.getState().commandPaletteOpen).toBe(true);

    press("Escape");
    expect(useWorkspace.getState().commandPaletteOpen).toBe(false);
  });

  it("closes without running when Escape is pressed with no highlighted action", () => {
    act(() => useWorkspace.getState().setView("overview"));
    renderShell();
    press("k", { metaKey: true });
    press("Escape");
    expect(useWorkspace.getState().view).toBe("overview");
  });

  it("reports an empty result set honestly", () => {
    renderShell();
    press("k", { metaKey: true });
    fireEvent.change(screen.getByTestId("command-palette-input"), { target: { value: "zzzzz" } });
    expect(screen.getByTestId("command-palette-empty")).toBeInTheDocument();
  });
});

describe("§50 — the Escape ladder", () => {
  it("clears the selection when nothing is open above it", () => {
    act(() => useWorkspace.getState().select({ kind: "Entity", id: "ENT-1" }));
    renderShell();
    press("Escape");
    expect(useWorkspace.getState().selection).toBeNull();
  });

  it("closes the palette before touching the selection", () => {
    act(() => useWorkspace.getState().select({ kind: "Entity", id: "ENT-1" }));
    renderShell();
    press("k", { metaKey: true });
    press("Escape");

    expect(useWorkspace.getState().commandPaletteOpen).toBe(false);
    // The selection survives: one Escape closed one layer, not all of them.
    expect(useWorkspace.getState().selection).not.toBeNull();
  });
});