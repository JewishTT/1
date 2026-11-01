import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { AppShell } from "../AppShell";
import { TopNav } from "./TopNav";
import {
  NAV_MODULES,
  NAV_SECTIONS,
  isNavItemActive,
  resolveFindingsPath,
  resolveModule,
  resolveTitle,
} from "./nav";

function renderAt(path: string, withShell = false) {
  const inner = (
    <Routes>
      <Route path="*" element={<div data-testid="page">page</div>} />
    </Routes>
  );
  const tree = withShell ? <AppShell>{inner}</AppShell> : <TopNav />;
  return render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={new QueryClient()}>
        {tree}
        {withShell ? null : inner}
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

function openDeck() {
  fireEvent.click(screen.getByTestId("nav-deck-trigger"));
}

describe("command-centre workspace navigation", () => {
  it("keeps only the active workspace trigger visible until requested", () => {
    renderAt("/investigations");
    expect(screen.getByTestId("topnav")).toBeInTheDocument();
    expect(screen.getByTestId("nav-deck-trigger")).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByTestId("nav-deck-trigger")).toHaveTextContent("OSINT");
    expect(screen.getByTestId("nav-deck-trigger")).toHaveTextContent("Investigation");
    expect(screen.queryByTestId("nav-deck")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-module-osint")).not.toBeInTheDocument();
  });

  it("opens all three domains and preserves their direct destinations", () => {
    renderAt("/investigations");
    openDeck();
    expect(screen.getByRole("dialog", { name: "Workspace navigation" })).toBeInTheDocument();
    for (const module of NAV_MODULES) {
      expect(screen.getByTestId(`nav-module-${module.key}`)).toHaveAttribute("href", module.landing);
    }
    expect(screen.getByTestId("nav-module-osint")).toHaveAttribute("data-active", "true");
    expect(screen.getByTestId("nav-module-osint")).toHaveAttribute("aria-current", "location");
    expect(screen.getByTestId("nav-module-specops")).not.toHaveAttribute("aria-current");
  });

  it("keeps all route groups searchable and grouped by their operational domain", () => {
    renderAt("/investigations");
    openDeck();
    const osint = screen.getByRole("navigation", { name: "osint workspaces" });
    const economic = screen.getByRole("navigation", { name: "economic workspaces" });
    const specops = screen.getByRole("navigation", { name: "specops workspaces" });
    expect(osint).toHaveTextContent("COLLECT");
    expect(osint).toHaveTextContent("INVESTIGATE");
    expect(osint).toHaveTextContent("ANALYZE");
    expect(osint).toHaveTextContent("Research Cases");
    expect(economic).toHaveTextContent("Intelligence Economy");
    expect(specops).toHaveTextContent("Pipeline Operations");
    expect(specops).toHaveTextContent("Connectors");
  });

  it("changes the active domain after selecting it and closes the deck", () => {
    renderAt("/investigations");
    openDeck();
    fireEvent.click(screen.getByTestId("nav-module-specops"));
    expect(screen.queryByTestId("nav-deck")).not.toBeInTheDocument();
    expect(screen.getByTestId("nav-deck-trigger")).toHaveTextContent("SPECOPS");
    openDeck();
    expect(screen.getByTestId("nav-module-specops")).toHaveAttribute("aria-current", "location");
    expect(screen.getByTestId("nav-destination-pipeline-operations")).toHaveAttribute("aria-current", "page");
  });

  it("marks the active destination precisely for nested routes", () => {
    renderAt("/specops/connectors");
    openDeck();
    expect(screen.getByTestId("nav-module-specops")).toHaveAttribute("aria-current", "location");
    const active = screen.getByTestId("nav-destination-connectors");
    expect(active).toHaveAttribute("data-active", "true");
    expect(active).toHaveAttribute("aria-current", "page");
  });

  it("searches all modules and reduces the deck to matching workspaces", () => {
    renderAt("/investigations");
    openDeck();
    fireEvent.change(screen.getByTestId("nav-deck-search"), { target: { value: "connectors" } });
    expect(screen.getByTestId("nav-destination-connectors")).toBeInTheDocument();
    expect(screen.getByTestId("nav-module-specops")).toBeInTheDocument();
    expect(screen.queryByTestId("nav-destination-research-cases")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-module-economic")).not.toBeInTheDocument();
  });

  it("clears the search and closes the deck with Escape", () => {
    renderAt("/investigations");
    openDeck();
    fireEvent.change(screen.getByTestId("nav-deck-search"), { target: { value: "science" } });
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByTestId("nav-deck")).not.toBeInTheDocument();
    openDeck();
    expect(screen.getByTestId("nav-deck-search")).toHaveValue("");
  });

  it("closes when the user clicks outside the navigation deck", () => {
    renderAt("/investigations");
    openDeck();
    fireEvent.click(screen.getByRole("button", { name: "Close workspace navigation" }));
    expect(screen.queryByTestId("nav-deck")).not.toBeInTheDocument();
  });

  it("keeps the tenant-wide graph out of the SpecOps section", () => {
    renderAt("/specops");
    openDeck();
    expect(screen.queryByText("Tenant Graph")).not.toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "specops workspaces" })).toHaveTextContent("Pipeline Operations");
  });

  it("retains the consolidated investigation graph destination", () => {
    renderAt("/investigations");
    openDeck();
    const destinations = screen.getByRole("navigation", { name: "osint workspaces" });
    expect(destinations).toHaveTextContent("Investigations");
    expect(destinations).not.toHaveTextContent("Tenant Graph");
    expect(destinations).not.toHaveTextContent("Investigation Graph");
    expect(destinations).not.toHaveTextContent("Intel Board");
  });

  it("handles query-specific destinations without lighting up a path-only sibling", () => {
    const item = { to: "/intel?entity=ENT-1", label: "Entities", icon: "view-objects" } as const;
    expect(isNavItemActive("/intel", item)).toBe(false);
    expect(isNavItemActive("/intel", item, "?entity=ENT-1")).toBe(true);
    expect(isNavItemActive("/intel", item, "?entity=ENT-2")).toBe(false);
  });

  it("matches nested paths but not siblings", () => {
    const item = { to: "/investigations", label: "Investigations", icon: "view-graph" } as const;
    expect(isNavItemActive("/investigations/INV-1", item)).toBe(true);
    expect(isNavItemActive("/investigationsx", item)).toBe(false);
  });

  it("renders nothing outside a router rather than throwing", () => {
    const { container } = render(
      <QueryClientProvider client={new QueryClient()}>
        <AppShell>bare</AppShell>
      </QueryClientProvider>,
    );
    expect(container.querySelector(".ui-primary-nav")).toBeNull();
    expect(screen.getByTestId("app-shell")).toBeInTheDocument();
  });

  it("keeps the full-width workbench separate from the command-bar selector", () => {
    const { container } = renderAt("/investigations", true);
    expect(screen.getByTestId("shell-main")).toBeInTheDocument();
    expect(container.querySelector(".ui-topbar-brand .ui-primary-nav")).not.toBeNull();
    expect(container.querySelector(".ui-shell-body > .ui-primary-nav")).toBeNull();
  });
});

describe("navigation data", () => {
  it("routes paths to their module", () => {
    expect(resolveModule("/intel")).toBe("osint");
    expect(resolveModule("/specops")).toBe("specops");
    expect(resolveModule("/specops/quarantine")).toBe("specops");
    expect(resolveModule("/specops/connectors")).toBe("specops");
    expect(resolveModule("/economic")).toBe("economic");
    expect(resolveModule("/quarantine")).toBe("osint");
  });

  it("titles the longest matching prefix", () => {
    expect(resolveTitle("/ops")).toBe("SpecOps Console");
    expect(resolveTitle("/investigations")).toBe("Investigation");
    expect(resolveTitle("/investigations/graph")).toBe("Investigation");
  });

  it("keeps findings navigation on the list route instead of inventing an id", () => {
    const items = NAV_SECTIONS.osint.flatMap((section) => section.items);
    expect(items.find((item) => item.label === "Findings")?.to).toBe("/findings");
    expect(resolveFindingsPath([])).toBeNull();
    expect(resolveFindingsPath(["", "FND-42"])).toBe("/findings/FND-42");
  });
});
