import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { AppShell } from "./AppShell";
import { Workbench } from "./Workbench";
import { DEFAULT_PANE_WIDTHS, useWorkspace } from "./workspace/store";
import { DENSITIES, DEFAULT_DENSITY, THEME_NAMES } from "./workspace/types";
import { applyInitialAppearanceAttributes } from "./workspace/useAppearance";

/**
 * `data-density` and `data-theme` actually reach the DOM (T136, FR-103).
 *
 * This is the smallest change in the whole UI track and the largest defect it
 * closes. `styles/tokens/color.css` and `styles/tokens/density.css` declare
 * their blocks under `[data-density="…"]` and `[data-theme="light"]`, and until
 * T136 nothing in the application ever wrote either attribute — 0 occurrences in
 * any `.ts`/`.tsx`. So `toggleDensity()` moved a Zustand field and changed zero
 * pixels, and `setTheme("light")` did the same, which with `:root` also carrying
 * the dark values meant light mode was not merely unstyled but UNREACHABLE: no
 * path in the app could render it, so it could never be reviewed or found broken.
 *
 * Both facts are invisible to a build, a lint run and a store unit test. They are
 * only visible here, by reading the attribute off `document.documentElement`.
 */

function renderShell() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <Workbench />
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
    timeRange: { from: null, to: null },
    openInspectorSections: {},
    pinnedInspectors: [],
    paneWidths: DEFAULT_PANE_WIDTHS,
    paneVisibility: { rail: true, inspector: true, activity: true },
    density: DEFAULT_DENSITY,
    theme: "dark",
    commandPaletteOpen: false,
    contextMenu: null,
  });
});

afterEach(() => {
  document.documentElement.removeAttribute("data-density");
  document.documentElement.removeAttribute("data-theme");
});

describe("T136 — the shell writes data-density and data-theme to the document", () => {
  it("writes both attributes on mount", () => {
    renderShell();
    expect(document.documentElement.getAttribute("data-density")).toBe(DEFAULT_DENSITY);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("writes them on documentElement, not on a subtree", () => {
    // `documentElement` IS `:root`, so one write themes the whole document —
    // including the legacy pages and the scoped donor sheets, which live outside
    // every `.ui-root` and would otherwise keep the old palette. A modal or a
    // native dialog renders outside the workspace subtree too, so scoping the
    // attribute to the shell would leave those on the default theme.
    renderShell();
    expect(document.documentElement.hasAttribute("data-density")).toBe(true);
    expect(document.documentElement.hasAttribute("data-theme")).toBe(true);
  });

  it("keeps them in step with the store, so a toggle changes real pixels", () => {
    renderShell();
    for (const density of DENSITIES) {
      act(() => useWorkspace.getState().setDensity(density));
      expect(document.documentElement.getAttribute("data-density")).toBe(density);
    }
    for (const theme of THEME_NAMES) {
      act(() => useWorkspace.getState().setTheme(theme));
      expect(document.documentElement.getAttribute("data-theme")).toBe(theme);
    }
  });

  it("reaches light theme — the mode that was previously unreachable", () => {
    renderShell();
    act(() => useWorkspace.getState().setTheme("light"));
    // Not "the store says light" — the ATTRIBUTE, which is what a selector can
    // match. This is the assertion the whole task exists for.
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(document.documentElement.style.colorScheme).toBe("light");
  });

  it("cycles density through all three modes from the store", () => {
    renderShell();
    const seen: string[] = [];
    for (let step = 0; step < 3; step += 1) {
      act(() => useWorkspace.getState().toggleDensity());
      seen.push(document.documentElement.getAttribute("data-density") ?? "");
    }
    expect(seen).toEqual(["comfortable", "compact", "standard"]);
  });

  it("mirrors the attributes onto the shell root, so a scoped selector can use them", () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <AppShell>
          <div />
        </AppShell>
      </QueryClientProvider>,
    );
    const shell = screen.getByTestId("app-shell");
    expect(shell).toHaveAttribute("data-density", DEFAULT_DENSITY);
    expect(shell).toHaveAttribute("data-theme", "dark");
  });

  it("writes the defaults before first paint, from main.tsx's call", () => {
    // The effect above runs after the first render, which would mean the shell
    // paints at the default density and then reflows to the stored one — a layout
    // shift caused by the application rather than by the data.
    act(() => {
      applyInitialAppearanceAttributes();
    });
    expect(document.documentElement.getAttribute("data-density")).toBe(DEFAULT_DENSITY);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("offers all three densities in the Appearance control", () => {
    renderShell();
    fireEvent.click(screen.getByTestId("appearance-menu"));
    for (const density of DENSITIES) {
      expect(screen.getByTestId(`density-${density}`)).toBeInTheDocument();
    }
    // The control writes through the store, which the effect turns into the
    // attribute — so a click is the whole round trip.
    fireEvent.click(screen.getByTestId("density-compact"));
    expect(useWorkspace.getState().density).toBe("compact");
    expect(document.documentElement.getAttribute("data-density")).toBe("compact");
  });

  it("offers both themes, and light is selectable", () => {
    renderShell();
    fireEvent.click(screen.getByTestId("appearance-menu"));
    fireEvent.click(screen.getByTestId("theme-light"));
    expect(useWorkspace.getState().theme).toBe("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });
});