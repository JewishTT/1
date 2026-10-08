/**
 * Tests for the normalised navigation.
 *
 * These exist because the navbar was the visible symptom of a structural defect: the
 * router mounted the legacy `components/Layout` *around* the UI 2.0 workspace, so two
 * shells were live and the old navbar was always the one on screen. Nothing asserted
 * which shell owns the chrome, so the defect survived a complete UI 2.0 rebuild.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { AppShell } from "../AppShell";
import { TopNav } from "./TopNav";
import { isNavItemActive, resolveModule, resolveTitle } from "./nav";

function renderAt(path: string, withShell = false) {
  const inner = (
    <Routes>
      <Route path="*" element={<div data-testid="page">page</div>} />
    </Routes>
  );
  const tree = withShell ? <AppShell>{inner}</AppShell> : <TopNav />;
  return render(
    <MemoryRouter initialEntries={[path]}>
      {/* AppShell's work-state bar queries the API, so the shell needs a client. */}
      <QueryClientProvider client={new QueryClient()}>
        {tree}
        {withShell ? null : inner}
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("topnav", () => {
  it("renders the module tabs and the section navigation", () => {
    renderAt("/intel");
    expect(screen.getByTestId("topnav")).toBeInTheDocument();
    expect(screen.getByTestId("topnav-modules")).toBeInTheDocument();
    expect(screen.getByTestId("topnav-sections")).toBeInTheDocument();
  });

it("shows the OSINT destinations by default", () => {
    renderAt("/intel");
    const nav = screen.getByTestId("topnav-sections");
    expect(nav).toHaveTextContent("Intel Board");
    expect(nav).toHaveTextContent("Connectors");
    expect(nav).toHaveTextContent("Science Console");
  });

  it("offers the investigation-scoped graph", () => {
    // Two graphs whose labels both read "graph" is how the tenant-wide one came to
    // look like the investigation's own.
    renderAt("/intel");
    expect(screen.getByTestId("topnav-sections")).toHaveTextContent("Investigation Graph");
  });

  it("names the tenant-wide graph as tenant-wide", () => {
    renderAt("/ops");
    expect(screen.getByTestId("topnav-sections")).toHaveTextContent("Tenant Graph");
  });

  it("switches section sets with the module", () => {
    renderAt("/ops");
    expect(screen.getByTestId("topnav-sections")).toHaveTextContent("SpecOps Console");
    expect(screen.getByTestId("topnav-sections")).not.toHaveTextContent("Intel Board");
  });

  it("marks the active module tab", () => {
    renderAt("/economic");
    const tab = document.querySelector('[data-module="economic"]');
    expect(tab).toHaveAttribute("data-active", "true");
  });

  it("marks the active destination and exposes aria-current", () => {
    renderAt("/connectors");
    const link = screen.getByRole("link", { name: /Connectors/i });
    expect(link).toHaveAttribute("data-active", "true");
    expect(link).toHaveAttribute("aria-current", "page");
  });

  it("navigates when a module tab is pressed", () => {
    renderAt("/intel");
    fireEvent.click(screen.getByRole("tab", { name: "SPEC" }));
    expect(screen.getByTestId("topnav-sections")).toHaveTextContent("SpecOps Console");
  });

  it("renders the breadcrumb trail", () => {
    renderAt("/quarantine");
    expect(screen.getByTestId("topnav")).toHaveTextContent("Quarantine (DLQ)");
  });

  it("ships no question-mark glyph as iconography", () => {
    // The legacy brand mark was a literal "?"; the standard forbids a text glyph
    // standing in for a drawn icon.
    const { container } = renderAt("/intel", true);
    expect(container.querySelector(".brand-mark")).toBeNull();
    expect(container.querySelector(".ui-brand-mark")).not.toBeNull();
  });

  it("ships no connection status it cannot observe", () => {
    // "NEXUS LINK: ACTIVE" was a hardcoded string reporting a state that did not exist.
    const { container } = renderAt("/intel");
    expect(container.textContent).not.toMatch(/NEXUS LINK/i);
  });

  it("renders nothing outside a router rather than throwing", () => {
    // AppShell is mounted bare in tests and stories; navigation is meaningless there.
    const { container } = render(
      <QueryClientProvider client={new QueryClient()}>
        <AppShell>bare</AppShell>
      </QueryClientProvider>
    );
    expect(container.querySelector(".ui-topnav")).toBeNull();
    expect(screen.getByTestId("app-shell")).toBeInTheDocument();
  });
});

describe("nav data", () => {
  it("routes paths to their module", () => {
    expect(resolveModule("/intel")).toBe("osint");
    expect(resolveModule("/ops/graph")).toBe("specops");
    expect(resolveModule("/quarantine")).toBe("specops");
    expect(resolveModule("/economic")).toBe("economic");
  });

it("titles the longest matching prefix, not the first", () => {
    // /ops is a prefix of /ops/graph, so a naive first-match walk mislabels it.
    expect(resolveTitle("/ops")).toBe("SpecOps Console");
    expect(resolveTitle("/ops/graph")).toBe("Tenant Graph (all investigations)");
    // Likewise /investigations is a prefix of /investigations/graph.
    expect(resolveTitle("/investigations")).toBe("Investigation");
    expect(resolveTitle("/investigations/graph")).toBe("Investigation Graph");
  });

  it("does not light up a query destination when only its path matches", () => {
    // "Intel Board" is /intel and "Entities" is /intel?entity=. react-router matches on
    // pathname alone, so without the query check both would render as current.
    const item = { to: "/intel?entity=ENT-1", label: "Entities", icon: "view-objects" } as const;
    expect(isNavItemActive("/intel", item)).toBe(false);
    expect(isNavItemActive("/intel", item, "?entity=ENT-1")).toBe(true);
    expect(isNavItemActive("/intel", item, "?entity=ENT-2")).toBe(false);
  });

  it("matches nested paths but not siblings", () => {
    const item = { to: "/investigations", label: "Investigations", icon: "view-overview" } as const;
    expect(isNavItemActive("/investigations/INV-1", item)).toBe(true);
    expect(isNavItemActive("/investigationsx", item)).toBe(false);
  });
});
